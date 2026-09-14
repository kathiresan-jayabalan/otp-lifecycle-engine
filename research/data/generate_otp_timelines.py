"""Synthetic OTP-lifecycle behavior-pattern generator + Python re-implementation of this
repo's deterministic control predicates, used as the ground-truth labeling function.

Framing (read this before citing any number downstream): this experiment does **not**
measure whether the demo application is PCI-DSS compliant - that question is already
answered, for real, by the 9/9 passing Playwright-BDD scenarios in `../../features/`. This
experiment instead asks a different, complementary question: *given only a partial,
early view of a login session's event sequence (as a real-time risk engine would see it
before the session concludes), can a classifier predict whether the session's full
behavior pattern would trigger one of this repo's control violations* (replay, stale/expired
code use, cross-session redemption, brute-force attempts, or stale-code use after a
reissue)? This models the practical value of a *statistical* early-warning layer sitting in
front of the *deterministic* compliance engine, not a replacement for it.

Ground truth is computed by `label_scenario()`, a direct Python port of the semantics in
`../../src/policy/predicates.ts` (replayRejected, expiryBoundaryEnforced,
attemptLockoutEnforced, sessionBindingEnforced, supersessionEnforced) - so "ground truth"
here means "what this repo's own rules would decide against the full timeline," not an
external oracle.

Usage:
    py research/data/generate_otp_timelines.py [--n 4000] [--seed 42] [--out <path>]
"""
from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

TTL_SECONDS = 300
MAX_ATTEMPTS = 5

ScenarioType = Literal[
    "benign_single_use", "benign_retry_then_success", "benign_sms_normal",
    "replay_attempt", "late_verify", "brute_force", "cross_session", "stale_after_reissue",
]
VIOLATION_TYPES = {"replay_attempt", "late_verify", "brute_force", "cross_session", "stale_after_reissue"}


@dataclass
class Event:
    t: float                 # seconds since code issue
    kind: str                # 'invalid_attempt' | 'valid_attempt' | 'reissue'
    session_match: bool = True


@dataclass
class Scenario:
    scenario_type: ScenarioType
    channel: str
    events: list = field(default_factory=list)

    @property
    def label(self) -> int:
        return 1 if self.scenario_type in VIOLATION_TYPES else 0


def _build_events(rng: np.random.Generator, scenario_type: ScenarioType) -> list:
    events: list = []
    if scenario_type == "benign_single_use":
        events.append(Event(t=rng.uniform(5, 60), kind="valid_attempt"))
    elif scenario_type == "benign_sms_normal":
        events.append(Event(t=rng.uniform(5, 90), kind="valid_attempt"))
    elif scenario_type == "benign_retry_then_success":
        n_typos = rng.integers(1, 3)
        t = 0.0
        for _ in range(n_typos):
            t += rng.uniform(3, 15)
            events.append(Event(t=t, kind="invalid_attempt"))
        t += rng.uniform(3, 15)
        events.append(Event(t=t, kind="valid_attempt"))
    elif scenario_type == "replay_attempt":
        t0 = rng.uniform(5, 60)
        events.append(Event(t=t0, kind="valid_attempt"))
        events.append(Event(t=t0 + rng.uniform(2, 40), kind="valid_attempt"))  # same code reused
    elif scenario_type == "late_verify":
        events.append(Event(t=TTL_SECONDS + rng.uniform(1, 120), kind="valid_attempt"))
    elif scenario_type == "brute_force":
        # attemptLockoutEnforced fires on len(invalid) > MAX_ATTEMPTS (strictly greater), so
        # the low end here must be MAX_ATTEMPTS + 1, not MAX_ATTEMPTS, or a drawn count of
        # exactly MAX_ATTEMPTS would be labeled "brute_force" by scenario type but "benign" by
        # the predicate - an off-by-one caught by the generator/label-mismatch assertion below.
        n_invalid = int(rng.integers(MAX_ATTEMPTS + 1, MAX_ATTEMPTS + 7))
        t = 0.0
        for _ in range(n_invalid):
            t += rng.uniform(1, 6)  # rapid-fire, unlike the slower benign retry pattern
            events.append(Event(t=t, kind="invalid_attempt"))
    elif scenario_type == "cross_session":
        events.append(Event(t=rng.uniform(5, 60), kind="valid_attempt", session_match=False))
    elif scenario_type == "stale_after_reissue":
        t0 = rng.uniform(5, 60)
        events.append(Event(t=t0, kind="reissue"))
        events.append(Event(t=t0 + rng.uniform(2, 60), kind="valid_attempt"))  # old code, post-reissue
    else:
        raise ValueError(scenario_type)
    return events


def label_scenario(scn: Scenario, disabled_predicates: frozenset = frozenset()) -> int:
    """Ground truth: recomputed independently from the generator's own `label` property to
    double-check the deterministic-predicate port agrees with how the scenario was built.
    Mirrors src/policy/predicates.ts semantics over the full (unobserved-prefix) timeline.

    `disabled_predicates` simulates a control-ablation run: pass predicate names (matching
    src/policy/predicates.ts function names) to treat as if that control were not checked at
    all, i.e. its violation condition is forced to False regardless of the timeline.
    """
    events = scn.events
    valid = [e for e in events if e.kind == "valid_attempt"]
    invalid = [e for e in events if e.kind == "invalid_attempt"]
    reissues = [e for e in events if e.kind == "reissue"]

    # replayRejected: two valid_attempt events on the same (never-reissued) code = replay.
    replay_violation = "replayRejected" not in disabled_predicates and len(reissues) == 0 and len(valid) >= 2

    # expiryBoundaryEnforced: a valid_attempt at/after TTL should have been rejected.
    late_violation = "expiryBoundaryEnforced" not in disabled_predicates and any(e.t >= TTL_SECONDS for e in valid)

    # attemptLockoutEnforced: more than MAX_ATTEMPTS invalid attempts without a lockout.
    lockout_violation = "attemptLockoutEnforced" not in disabled_predicates and len(invalid) > MAX_ATTEMPTS

    # sessionBindingEnforced: a valid_attempt from a mismatched session should be rejected.
    session_violation = "sessionBindingEnforced" not in disabled_predicates and any(
        e.kind == "valid_attempt" and not e.session_match for e in events
    )

    # supersessionEnforced: a valid_attempt on the pre-reissue code after a reissue happened.
    supersession_violation = "supersessionEnforced" not in disabled_predicates and len(reissues) > 0 and any(
        e.t > reissues[0].t for e in valid
    )

    return int(replay_violation or late_violation or lockout_violation or session_violation or supersession_violation)


def _extract_features(observed: list, channel: str, fraction_observed: float) -> dict:
    valid_so_far = [e for e in observed if e.kind == "valid_attempt"]
    invalid_so_far = [e for e in observed if e.kind == "invalid_attempt"]
    reissues_so_far = [e for e in observed if e.kind == "reissue"]

    max_t = max((e.t for e in observed), default=0.0)
    any_cross_session = any(e.kind == "valid_attempt" and not e.session_match for e in observed)
    any_valid_after_reissue = bool(reissues_so_far) and any(e.t > reissues_so_far[0].t for e in valid_so_far)
    any_valid_near_or_after_ttl = any(e.t >= 0.9 * TTL_SECONDS for e in valid_so_far)
    max_invalid_gap = 0.0
    if len(invalid_so_far) >= 2:
        gaps = [b.t - a.t for a, b in zip(invalid_so_far, invalid_so_far[1:])]
        max_invalid_gap = float(np.mean(gaps))

    return {
        "n_invalid_so_far": len(invalid_so_far),
        "n_valid_so_far": len(valid_so_far),
        "n_reissues_so_far": len(reissues_so_far),
        "max_time_offset_so_far": max_t,
        "any_cross_session_so_far": int(any_cross_session),
        "any_valid_after_reissue_so_far": int(any_valid_after_reissue),
        "any_valid_near_or_after_ttl_so_far": int(any_valid_near_or_after_ttl),
        "mean_invalid_attempt_gap_s": max_invalid_gap,
        "channel_is_sms": int(channel == "sms"),
        "fraction_observed": fraction_observed,
    }


def generate(n: int = 4000, seed: int = 42, min_observed_fraction: float = 0.3,
             disabled_predicates: frozenset = frozenset()) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Balance violation vs. benign roughly 50/50 so F1/ROC-AUC aren't dominated by class skew;
    # within each side, scenario sub-types are drawn uniformly.
    rows = []
    for _ in range(n):
        is_violation = rng.integers(0, 2)
        pool = list(VIOLATION_TYPES) if is_violation else ["benign_single_use", "benign_retry_then_success", "benign_sms_normal"]
        scenario_type = rng.choice(pool)
        channel = rng.choice(["email", "sms"])
        events = sorted(_build_events(rng, scenario_type), key=lambda e: e.t)
        scn = Scenario(scenario_type=scenario_type, channel=channel, events=events)

        full_label = label_scenario(scn, disabled_predicates)
        if not disabled_predicates:
            assert full_label == scn.label, f"generator/label mismatch for {scenario_type}"

        fraction_observed = float(rng.uniform(min_observed_fraction, 1.0))
        n_observed = max(1, math.ceil(fraction_observed * len(events))) if events else 0
        observed = events[:n_observed]

        features = _extract_features(observed, channel, fraction_observed)
        features["scenario_type"] = scenario_type
        features["label"] = full_label
        rows.append(features)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default=os.path.join(os.path.dirname(__file__), "generated", "otp_timelines.csv"))
    args = parser.parse_args()

    df = generate(args.n, args.seed)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")
    print(f"violation rate (label=1): {df['label'].mean():.4f}")
    print(df["scenario_type"].value_counts())
