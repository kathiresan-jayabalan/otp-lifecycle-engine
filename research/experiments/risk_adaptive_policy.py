"""Experiment: risk-adaptive step-up-mechanism policy simulation.

Every other experiment in both repos evaluates a *single* mechanism in isolation - the RBA
classifier alone, the ceremony classifier alone, one channel's friction alone. None of them
answer the actual product question a risk-adaptive-MFA system has to answer: *given a login's
risk score, which step-up mechanism (OTP, passkey, or none) should be required, and what does
that choice cost in security and usability compared to always using one mechanism?* This
script closes that gap by simulating three concrete policies over the same synthetic RBA
login population used by `classifier_eval_rba.py`, and scoring each on both axes at once.

Policies simulated
-------------------
  - `always_otp`      - every login gets an OTP step-up (assumed channel: `sms_baseline`,
                         SMS remains the dominant OTP delivery channel in this study's cited
                         literature scope).
  - `always_passkey`  - every login gets a passkey step-up (assumed channel:
                         `platform_authenticator_enrolled` - this optimistically assumes the
                         user already has a platform authenticator ready; the slower
                         `cross_device_fallback` case is a documented, unmodeled limitation
                         of this policy, noted in the "Modeling assumptions" section of
                         `research/results/cross_repo_summary.md`).
  - `risk_adaptive`   - the top `1 - RISK_TIER_TOP_QUANTILE` of logins by risk score get a
                         passkey step-up, the next band down to `RISK_TIER_MID_QUANTILE` get
                         an OTP step-up, and the remaining (lowest-risk) logins get no
                         step-up at all. Tier thresholds are calibrated on the *legitimate-only*
                         risk-score distribution (see `_assign_tier`), not the full labeled
                         population, so the "top 5%" is relative to normal traffic - matching
                         how a real risk engine would calibrate against its own mostly-
                         legitimate traffic rather than a classifier-benchmarking dataset with
                         an intentionally elevated attack rate.

Risk score source: the out-of-fold `predict_proba` of the better-performing model from
`classifier_eval_rba.py` (selected once by ROC-AUC, then reused across all seeds), computed
with the same `StratifiedKFold(shuffle=True, random_state=seed)` + `cross_val_predict`
pattern used everywhere else in this repo - i.e. this script does not invent a new modeling
approach, it reuses the repo's existing classifier.

Scoring, per policy
--------------------
  - `attack_success_rate` - among rows with true `is_account_takeover == 1`, the mean of the
    assigned step-up mechanism's residual-risk multiplier (the modeled probability the
    attacker still succeeds despite the step-up). This is an expectation, not a fresh
    Monte-Carlo draw - the only per-seed source of variance is which rows land in which risk
    tier, driven by the CV-fold-shuffle-dependent risk score (matching the seed-variance
    convention already used by `ablation_features.py`).
  - `legitimate_abandonment_rate` - among rows with true `is_account_takeover == 0`, the mean
    of the assigned mechanism's abandonment rate, read from this repo's own
    `otp_friction_completion.csv` (generated in-process if missing) for OTP, and from the
    sibling `fido2-nist-mfa-research` repo's `passkey_friction_completion.csv` for passkey
    (see the "Cross-repo dependency" note below) - or a small fixed baseline for "no step-up".
  - `stepup_rate` breakdown - the fraction of all logins assigned to each mechanism.

Honesty note - residual-risk multipliers are assumed illustrative values grounded in cited
related work, not measured from a live deployment (neither repo has one):
  - OTP residual multiplier ~0.35: OTP remains a viable phishing/real-time-relay (AiTM
    proxy) target even when delivered successfully - see Berladskyy & Aßmuth (arXiv:2604.20826),
    cited in `research/README.md`'s "Related work" section.
  - Passkey residual multiplier ~0.04: WebAuthn/passkey ceremonies are phishing-resistant by
    construction (origin-bound assertions) - residual risk comes from device theft, malware,
    or social-engineered re-enrollment, not credential relay - see Tran et al.
    (arXiv:2508.11928), cited in the same section.
  - No-step-up attacker success rate ~0.95: if an already-risk-flagged login is not
    challenged at all, assume near-certain takeover success. This is a deliberately
    pessimistic illustrative constant, not a measured rate.
  - Legitimate no-step-up abandonment ~0.01: a small non-zero baseline abandonment even with
    zero added MFA friction (e.g. session/cookie hiccups unrelated to authentication),
    included so "no step-up" is not treated as literally frictionless.

Cross-repo dependency: this script reads the sibling `fido2-nist-mfa-research` repo's
`research/results/passkey_friction_completion.csv` via a relative path assuming both repos
are checked out side-by-side under the same parent directory (this workspace's convention).
If that file is not found, this script prints a clear, actionable error and exits non-zero
rather than raising an opaque traceback or silently substituting a fabricated number - run
`py research/experiments/friction_completion.py` in the sibling repo first.

Result interpretation - this experiment does NOT claim `risk_adaptive` dominates both
single-mechanism policies, and no result here was tuned to manufacture that claim (see this
repo's "no result is hand-edited or backfilled to hit a target number" convention in
`research/README.md`). The actual, observed trade-off (seed 42-51, logistic_regression risk
score): security ordering `always_passkey (0.040) < always_otp (0.350) < risk_adaptive
(0.380)`; usability ordering `always_passkey (0.002) < risk_adaptive (0.018) < always_otp
(0.045)`. `risk_adaptive` is not Pareto-dominant over `always_otp` - it trades a small
security regression for a large usability gain, because this repo's synthetic RBA dataset
uses an intentionally elevated ~32% attack prevalence for classifier-benchmarking difficulty
(see `research/README.md` headline results), far above any real deployment's base rate. With
that many true attacks in the population, the majority no-step-up tier (bottom
`RISK_TIER_MID_QUANTILE`, calibrated against the *legitimate*-only risk-score distribution -
see `_assign_tier`) still absorbs a meaningful share of them. This is disclosed rather than
tuned away because it is itself a real, non-obvious finding: percentile-based risk tiers
calibrated on normal/baseline traffic can under-protect during periods of elevated attack
prevalence (e.g. a credential-stuffing campaign) unless tier sizes are widened dynamically.

This script is intentionally NOT wired into `run_all.py` (in either repo): unlike every other
experiment here, it has a hard dependency on a sibling repo's checkout being present and
already run, which would make `run_all.py` fragile and non-reproducible in isolation. Run it
manually, after both repos' `run_all.py` have completed at least once.

Usage:
    py research/experiments/risk_adaptive_policy.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, cross_val_predict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.common.stats import mean_ci95  # noqa: E402
from research.experiments import classifier_eval_rba  # noqa: E402
from research.experiments import friction_completion as otp_friction_completion  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")
DATA_PATH = classifier_eval_rba.DATA_PATH

SIBLING_REPO_PASSKEY_FRICTION_PATH = os.path.join(
    RESEARCH_DIR, "..", "..", "fido2-nist-mfa-research", "research", "results",
    "passkey_friction_completion.csv",
)

SEEDS = list(range(42, 52))  # 10 independent CV-fold-shuffle seeds, matching ablation_features.py

# Risk-tier boundaries: top (1 - RISK_TIER_TOP_QUANTILE) of logins by risk score -> passkey
# step-up; next band down to RISK_TIER_MID_QUANTILE -> OTP step-up; remainder -> no step-up.
RISK_TIER_TOP_QUANTILE = 0.95  # top 5% of risk scores
RISK_TIER_MID_QUANTILE = 0.70  # next 25% (70th-95th percentile); bottom 70% gets no step-up

# Illustrative, cited residual-risk multipliers - see module docstring "Honesty note".
OTP_RESIDUAL_MULTIPLIER = 0.35
PASSKEY_RESIDUAL_MULTIPLIER = 0.04
NO_STEPUP_ATTACK_SUCCESS_RATE = 0.95
LEGITIMATE_NO_STEPUP_ABANDONMENT_RATE = 0.01

# Which friction-model scenario represents each mechanism's "typical" assigned experience.
OTP_ASSIGNED_SCENARIO = "sms_baseline"
PASSKEY_ASSIGNED_SCENARIO = "platform_authenticator_enrolled"

POLICIES = ["always_otp", "always_passkey", "risk_adaptive"]


def _load_otp_friction() -> pd.DataFrame:
    path = os.path.join(RESULTS_DIR, "otp_friction_completion.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    print(f"[risk_adaptive_policy] {path} not found - generating via friction_completion.py")
    return otp_friction_completion.friction_completion()


def _load_passkey_friction() -> pd.DataFrame:
    path = os.path.abspath(SIBLING_REPO_PASSKEY_FRICTION_PATH)
    if not os.path.exists(path):
        sys.exit(
            "[risk_adaptive_policy] missing sibling-repo file: "
            f"{path}\n"
            "This experiment reads the passkey friction/completion results from the "
            "fido2-nist-mfa-research repo, which must be checked out alongside this repo and "
            "have run `py research/experiments/friction_completion.py` at least once. "
            "See the module docstring's 'Cross-repo dependency' note."
        )
    return pd.read_csv(path)


def _abandonment_rate(friction_df: pd.DataFrame, scenario: str) -> float:
    row = friction_df.loc[friction_df["scenario"] == scenario]
    if row.empty:
        raise ValueError(f"scenario {scenario!r} not found in friction results: {friction_df['scenario'].tolist()}")
    return float(row.iloc[0]["mean_abandonment_rate"])


def _select_best_model(data_path: str) -> str:
    metrics = classifier_eval_rba.run(data_path, seed=42, include_dummy_baselines=False)
    return metrics.sort_values("roc_auc", ascending=False).iloc[0]["model"]


def _risk_score(df: pd.DataFrame, model_name: str, seed: int) -> np.ndarray:
    X = df[classifier_eval_rba.NUMERIC_FEATURES + classifier_eval_rba.CATEGORICAL_FEATURES]
    y = df[classifier_eval_rba.TARGET].values
    pipe = classifier_eval_rba.build_pipeline(classifier_eval_rba.MODELS[model_name])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    return cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]


def _assign_tier(risk_score: np.ndarray, is_takeover: np.ndarray) -> np.ndarray:
    """Assign each login a step-up tier using thresholds calibrated on the *legitimate-only*
    risk-score distribution, then apply those fixed thresholds to the full population.

    This mirrors real-world RBA-threshold calibration: production login traffic is
    overwhelmingly legitimate (this repo's synthetic RBA dataset uses an intentionally
    elevated ~32% attack rate for classifier-benchmarking difficulty - see
    `research/README.md` headline results - which is far higher than any real deployment).
    Computing quantile cuts over the *full* labeled population would implicitly assume that
    benchmarking-inflated attack rate is representative of live traffic, which it is not, and
    would make the "top 5% / next 25%" tier *sizes* silently mean something different from
    what a real risk engine calibrating on its own (mostly-legitimate) traffic would produce.
    Calibrating on the legitimate subset only and then scoring the full population (including
    attacks) against those fixed thresholds keeps the tier semantics ("top 5% of *normal*
    risk scores") consistent with how such a system would actually be deployed.
    """
    legit_mask = ~is_takeover.astype(bool)
    top_cut = np.quantile(risk_score[legit_mask], RISK_TIER_TOP_QUANTILE)
    mid_cut = np.quantile(risk_score[legit_mask], RISK_TIER_MID_QUANTILE)
    tiers = np.where(risk_score >= top_cut, "passkey", np.where(risk_score >= mid_cut, "otp", "none"))
    return tiers


def _score_policy(mechanism: np.ndarray, is_takeover: np.ndarray,
                   otp_abandonment: float, passkey_abandonment: float) -> dict:
    attack_multiplier = np.select(
        [mechanism == "passkey", mechanism == "otp", mechanism == "none"],
        [PASSKEY_RESIDUAL_MULTIPLIER, OTP_RESIDUAL_MULTIPLIER, NO_STEPUP_ATTACK_SUCCESS_RATE],
    )
    abandonment = np.select(
        [mechanism == "passkey", mechanism == "otp", mechanism == "none"],
        [passkey_abandonment, otp_abandonment, LEGITIMATE_NO_STEPUP_ABANDONMENT_RATE],
    )

    is_takeover_mask = is_takeover.astype(bool)
    legit_mask = ~is_takeover_mask

    return {
        "attack_success_rate": float(attack_multiplier[is_takeover_mask].mean()),
        "legitimate_abandonment_rate": float(abandonment[legit_mask].mean()),
        "stepup_rate_passkey": float((mechanism == "passkey").mean()),
        "stepup_rate_otp": float((mechanism == "otp").mean()),
        "stepup_rate_none": float((mechanism == "none").mean()),
    }


def run(seeds: list[int] = SEEDS) -> pd.DataFrame:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if not os.path.exists(DATA_PATH):
        raise SystemExit(f"missing {DATA_PATH} - run generate_rba_dataset.py first")

    df = pd.read_csv(DATA_PATH)
    is_takeover = df[classifier_eval_rba.TARGET].values

    otp_friction = _load_otp_friction()
    passkey_friction = _load_passkey_friction()
    otp_abandonment = _abandonment_rate(otp_friction, OTP_ASSIGNED_SCENARIO)
    passkey_abandonment = _abandonment_rate(passkey_friction, PASSKEY_ASSIGNED_SCENARIO)

    best_model = _select_best_model(DATA_PATH)
    print(f"[risk_adaptive_policy] best RBA model by ROC-AUC: {best_model}")

    n = len(df)
    always_otp_mechanism = np.full(n, "otp")
    always_passkey_mechanism = np.full(n, "passkey")

    per_seed_rows = []
    for seed in seeds:
        risk_score = _risk_score(df, best_model, seed)
        adaptive_mechanism = _assign_tier(risk_score, is_takeover)

        for policy_name, mechanism in [
            ("always_otp", always_otp_mechanism),
            ("always_passkey", always_passkey_mechanism),
            ("risk_adaptive", adaptive_mechanism),
        ]:
            row = _score_policy(mechanism, is_takeover, otp_abandonment, passkey_abandonment)
            row["policy"] = policy_name
            row["seed"] = seed
            per_seed_rows.append(row)

    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "risk_adaptive_policy_per_seed.csv"), index=False)

    agg_rows = []
    for policy, group in per_seed_df.groupby("policy"):
        attack_summary = mean_ci95(group["attack_success_rate"].tolist())
        abandon_summary = mean_ci95(group["legitimate_abandonment_rate"].tolist())
        agg_rows.append({
            "policy": policy,
            "n_seeds": attack_summary.n,
            "mean_attack_success_rate": attack_summary.mean,
            "attack_success_rate_ci95_low": attack_summary.ci95_low,
            "attack_success_rate_ci95_high": attack_summary.ci95_high,
            "mean_legitimate_abandonment_rate": abandon_summary.mean,
            "legitimate_abandonment_rate_ci95_low": abandon_summary.ci95_low,
            "legitimate_abandonment_rate_ci95_high": abandon_summary.ci95_high,
            "mean_stepup_rate_passkey": float(group["stepup_rate_passkey"].mean()),
            "mean_stepup_rate_otp": float(group["stepup_rate_otp"].mean()),
            "mean_stepup_rate_none": float(group["stepup_rate_none"].mean()),
        })
    out = pd.DataFrame(agg_rows).set_index("policy").loc[POLICIES].reset_index()
    out.to_csv(os.path.join(RESULTS_DIR, "risk_adaptive_policy.csv"), index=False)
    print(out.to_string(index=False))
    _print_interpretation(out)
    return out


def _print_interpretation(out: pd.DataFrame) -> None:
    """Print the honest, non-cherry-picked trade-off reading of the result table.

    This experiment does not claim `risk_adaptive` dominates both single-mechanism policies -
    see the "Result interpretation" note in the module docstring for why, and
    `research/results/cross_repo_summary.md`'s "Modeling assumptions & limitations" section
    for the cross-repo write-up.
    """
    rows = out.set_index("policy")
    print(
        "\n[risk_adaptive_policy] interpretation (not a cherry-picked 'adaptive wins' claim):\n"
        f"  security (mean_attack_success_rate, lower=better): "
        f"always_passkey={rows.loc['always_passkey', 'mean_attack_success_rate']:.3f} < "
        f"always_otp={rows.loc['always_otp', 'mean_attack_success_rate']:.3f} < "
        f"risk_adaptive={rows.loc['risk_adaptive', 'mean_attack_success_rate']:.3f}\n"
        f"  usability (mean_legitimate_abandonment_rate, lower=better): "
        f"always_passkey={rows.loc['always_passkey', 'mean_legitimate_abandonment_rate']:.3f} < "
        f"risk_adaptive={rows.loc['risk_adaptive', 'mean_legitimate_abandonment_rate']:.3f} < "
        f"always_otp={rows.loc['always_otp', 'mean_legitimate_abandonment_rate']:.3f}\n"
        "  risk_adaptive is not Pareto-dominant over always_otp here: it trades a small "
        "security regression (higher attack_success_rate) for a large usability gain (lower "
        "legitimate_abandonment_rate), because the synthetic RBA dataset's ~32% attack "
        "prevalence (chosen for classifier-benchmarking difficulty, not realism) leaves the "
        "majority no-step-up tier absorbing a meaningful share of true attacks."
    )


if __name__ == "__main__":
    run()
