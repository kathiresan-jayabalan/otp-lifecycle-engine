"""Experiment: OTP delivery friction / completion-rate proxy.

Every other experiment in this repo measures *security* signal (can a classifier detect a
compliance-violation pattern, is the TTL boundary sharp under jitter). None of them measure
the other side of the risk-adaptive-MFA trade-off this repo's sibling research direction is
built around: *usability* - does the user actually receive and enter the code before giving
up, or does delivery latency/failure cause abandonment? This experiment adds that missing
axis as an explicit, documented synthetic proxy (there is no live user-abandonment telemetry
in this repo to measure directly), following the same "real computation over a documented,
honest synthetic model" convention used by every other experiment here.

Data-generating process
------------------------
Two delivery channels (`sms`, `email`) x two delivery conditions (`baseline`,
`degraded`) - four scenarios total:

  - `sms` / `baseline`   - typical carrier delivery latency, low but non-zero failure rate
                            (carrier filtering / SMPP queuing).
  - `sms` / `degraded`   - simulates a carrier-side delay or partial outage (a real,
                            recurring operational failure mode for SMS OTP - carriers
                            routinely rate-limit or delay application-to-person traffic).
  - `email` / `baseline` - typical SMTP relay + inbox delivery latency, low failure rate.
  - `email` / `degraded` - simulates spam-folder placement / greylisting delay, a real and
                            common email-OTP failure mode independent of any code defect.

For each simulated delivery: draw a delivery latency and a delivery-failure flag from the
scenario's distribution; on failure, the user may request a resend (scenario-dependent
resend probability), which adds further latency and is itself subject to the same failure
rate. Independently, draw a user "patience" - the longest total elapsed time the user will
tolerate before abandoning - from a log-normal distribution. An attempt counts as *completed*
only if the code ultimately arrives (first send or resend) within the drawn patience window;
otherwise it is an abandonment.

IMPORTANT - cross-repo comparability: `PATIENCE_LOGNORMAL_MEAN_LOG` / `PATIENCE_LOGNORMAL_SIGMA`
below are deliberately identical to the constants of the same name in the sibling
`fido2-nist-mfa-research` repo's `research/experiments/friction_completion.py`. Using the same
user-patience distribution in both repos is what makes the OTP-vs-passkey completion-rate
comparison in `research/results/cross_repo_summary.md` a fair, apples-to-apples read rather
than two differently-calibrated models that happen to share a file name. If you change these
constants here, change them identically in the sibling file.

Honesty note: every latency/failure-rate/resend-probability constant below is an assumed
illustrative value chosen to produce a plausible, checkable simulation - none are benchmarked
from a real SMS/email delivery deployment's telemetry (this repo has none to draw from).
Treat the *relative* comparison between scenarios (and against the sibling passkey repo's
scenarios) as the informative signal, not the absolute completion-rate numbers.

Usage:
    py research/experiments/friction_completion.py
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.common.stats import mean_ci95  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")

SEEDS = list(range(42, 52))  # 10 independent seeds, matching the ablation studies

# Shared with fido2-nist-mfa-research/research/experiments/friction_completion.py - see the
# "cross-repo comparability" note in the module docstring above. Do not change one without
# the other.
PATIENCE_LOGNORMAL_MEAN_LOG = math.log(20.0)  # median user patience ~20s
PATIENCE_LOGNORMAL_SIGMA = 0.5

SCENARIOS = {
    "sms_baseline": {
        "latency_mean_log": math.log(6.0),       # ~6s median carrier delivery
        "latency_sigma": 0.45,
        "p_delivery_failure": 0.03,               # carrier filtering / SMPP queuing drops
        "resend_latency_mean_log": math.log(6.0),
        "resend_latency_sigma": 0.45,
        "resend_probability": 0.85,
    },
    "sms_degraded": {
        "latency_mean_log": math.log(25.0),      # simulated carrier-side delay/partial outage
        "latency_sigma": 0.70,
        "p_delivery_failure": 0.15,
        "resend_latency_mean_log": math.log(25.0),
        "resend_latency_sigma": 0.70,
        "resend_probability": 0.70,               # users less willing to wait again once already delayed
    },
    "email_baseline": {
        "latency_mean_log": math.log(10.0),      # ~10s median SMTP relay + inbox delivery
        "latency_sigma": 0.50,
        "p_delivery_failure": 0.04,               # greylisting / minor relay delay
        "resend_latency_mean_log": math.log(10.0),
        "resend_latency_sigma": 0.50,
        "resend_probability": 0.80,
    },
    "email_degraded": {
        "latency_mean_log": math.log(45.0),      # simulated spam-folder placement / greylisting delay
        "latency_sigma": 0.80,
        "p_delivery_failure": 0.20,
        "resend_latency_mean_log": math.log(45.0),
        "resend_latency_sigma": 0.80,
        "resend_probability": 0.65,
    },
}


def _simulate_scenario(rng: np.random.Generator, params: dict, n: int) -> pd.DataFrame:
    latency1 = rng.lognormal(params["latency_mean_log"], params["latency_sigma"], size=n)
    failure1 = rng.binomial(1, params["p_delivery_failure"], size=n).astype(bool)

    will_resend = rng.binomial(1, params["resend_probability"], size=n).astype(bool)
    resend_latency = rng.lognormal(params["resend_latency_mean_log"], params["resend_latency_sigma"], size=n)
    resend_failure = rng.binomial(1, params["p_delivery_failure"], size=n).astype(bool)

    attempts_resend = failure1 & will_resend
    total_latency = np.where(attempts_resend, latency1 + resend_latency, latency1)
    delivery_succeeded = np.where(
        ~failure1, True,
        np.where(attempts_resend, ~resend_failure, False),
    )

    patience = rng.lognormal(PATIENCE_LOGNORMAL_MEAN_LOG, PATIENCE_LOGNORMAL_SIGMA, size=n)
    completed = delivery_succeeded & (total_latency <= patience)

    return pd.DataFrame({
        "total_latency_s": total_latency,
        "delivery_succeeded": delivery_succeeded,
        "completed": completed,
    })


def friction_completion(seeds: list[int] = SEEDS, n_per_scenario: int = 5000) -> pd.DataFrame:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    per_seed_rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for scenario, params in SCENARIOS.items():
            df = _simulate_scenario(rng, params, n_per_scenario)
            completed_only = df.loc[df["completed"], "total_latency_s"]
            per_seed_rows.append({
                "scenario": scenario,
                "seed": seed,
                "completion_rate": float(df["completed"].mean()),
                "abandonment_rate": float(1.0 - df["completed"].mean()),
                "mean_time_to_complete_s": float(completed_only.mean()) if len(completed_only) else float("nan"),
            })

    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "otp_friction_completion_per_seed.csv"), index=False)

    agg_rows = []
    for scenario, group in per_seed_df.groupby("scenario"):
        completion_summary = mean_ci95(group["completion_rate"].tolist())
        time_summary = mean_ci95(group["mean_time_to_complete_s"].dropna().tolist())
        agg_rows.append({
            "scenario": scenario,
            "n_seeds": completion_summary.n,
            "mean_completion_rate": completion_summary.mean,
            "completion_rate_ci95_low": completion_summary.ci95_low,
            "completion_rate_ci95_high": completion_summary.ci95_high,
            "mean_abandonment_rate": 1.0 - completion_summary.mean,
            "mean_time_to_complete_s": time_summary.mean,
            "time_to_complete_ci95_low": time_summary.ci95_low,
            "time_to_complete_ci95_high": time_summary.ci95_high,
        })
    out = pd.DataFrame(agg_rows).sort_values("scenario").reset_index(drop=True)
    out.to_csv(os.path.join(RESULTS_DIR, "otp_friction_completion.csv"), index=False)
    print(out.to_string(index=False))
    return out


if __name__ == "__main__":
    friction_completion()
