"""Delayed-OTP analysis: two complementary angles.

(A) TTL boundary sweep - simulates verify attempts at a range of delay offsets around the
    configured TTL boundary, with a jitter term standing in for real-world network/clock
    latency variance between when a client submits a code and when the server evaluates
    elapsed time. Demonstrates that the accept/reject boundary is not an infinitely sharp
    step function once realistic jitter is present, and quantifies the width of that "grey
    zone" - directly relevant to `otp.bounded-validity` (see ../../control-profiles/otp-controls.yaml).
    Re-run under `N_SEEDS` independent RNG seeds and aggregated to a mean + 95% CI per
    offset (see `research/common/stats.py:mean_ci95`), matching the multi-seed rigor used
    elsewhere in this repo rather than reporting a single-draw curve.

(B) Timing side-channel statistical-power demonstration - simulates two verification-latency
    distributions (H0: constant-time comparison, no leak; H1: a naive early-exit string
    comparison that runs slightly faster the sooner it hits a mismatching character) and runs
    Welch's t-test and the Mann-Whitney U test on each, showing the tests correctly fail to
    reject H0 under the constant-time model and correctly detect a difference under the
    naive-comparison model at a given effect size / sample size. Re-run under `N_SEEDS`
    independent draws; per-seed p-values are combined via Fisher's method
    (`scipy.stats.combine_pvalues`), the standard way to summarize repeated independent
    significance tests of the same hypothesis, rather than reporting one seed's p-value.

    Honesty note: this is a **simulated statistical-power demonstration of the methodology**,
    not a measurement of the actual demo app's live HTTP response timing (that would need
    real timing instrumentation across thousands of network round trips, which is out of
    scope here and would be dominated by Node event-loop and OS scheduling noise at this
    request volume). It is included because a concrete, checkable static-code finding makes
    the demonstration directly relevant: `demo-app/lib/otpStore.js`'s `verify()` compares the
    submitted code with `submittedCode !== record.code` - a native JS string comparison, not
    `crypto.timingSafeEqual` - so the "naive early-exit comparison" scenario modeled in H1 is
    a plausible (not hypothetical) property of this codebase, and is flagged here as a
    concrete remediation recommendation, independent of whether it is measurably exploitable
    over a real network in practice. The H1 effect size (`naive_effect_ms = 0.15`) is an
    assumed illustrative constant chosen to be small-but-detectable at this sample size, not
    a value benchmarked from `otpStore.js`'s actual `!==` comparison latency - no such
    benchmark exists in this repo.

Usage:
    py research/experiments/delayed_otp.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.common.stats import mean_ci95  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")

TTL_SECONDS = 300
SEEDS = list(range(42, 52))  # 10 independent RNG seeds, matching the ablation studies


def _ttl_sweep_single_seed(seed: int, jitter_ms_sd: float, trials_per_offset: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    offsets_s = np.arange(-5.0, 5.01, 0.5)  # seconds relative to the TTL boundary
    rows = []
    for offset in offsets_s:
        nominal_delay = TTL_SECONDS + offset
        jitter = rng.normal(0, jitter_ms_sd / 1000.0, size=trials_per_offset)
        effective_delay = nominal_delay + jitter
        accepted = effective_delay < TTL_SECONDS  # mirrors otpStore.js: clock.now() >= expiresAt -> reject
        rows.append({"offset_from_ttl_s": float(offset), "accept_rate": float(accepted.mean()), "seed": seed})
    return pd.DataFrame(rows)


def ttl_boundary_sweep(seeds: list[int] = SEEDS, jitter_ms_sd: float = 120.0,
                        trials_per_offset: int = 500) -> pd.DataFrame:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    per_seed_df = pd.concat(
        [_ttl_sweep_single_seed(seed, jitter_ms_sd, trials_per_offset) for seed in seeds],
        ignore_index=True,
    )
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "delayed_otp_ttl_sweep_per_seed.csv"), index=False)

    agg_rows = []
    for offset, group in per_seed_df.groupby("offset_from_ttl_s"):
        summary = mean_ci95(group["accept_rate"].tolist())
        agg_rows.append({
            "offset_from_ttl_s": float(offset),
            "accept_rate": summary.mean,
            "accept_rate_ci95_low": summary.ci95_low,
            "accept_rate_ci95_high": summary.ci95_high,
            "n_seeds": summary.n,
        })
    df = pd.DataFrame(agg_rows).sort_values("offset_from_ttl_s").reset_index(drop=True)
    df.to_csv(os.path.join(RESULTS_DIR, "delayed_otp_ttl_sweep.csv"), index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(6, 4))
    plt.plot(df["offset_from_ttl_s"], df["accept_rate"], marker="o",
              label=f"mean accept rate ({len(seeds)} seeds)")
    plt.fill_between(df["offset_from_ttl_s"], df["accept_rate_ci95_low"], df["accept_rate_ci95_high"],
                      alpha=0.2, label="95% CI")
    plt.axvline(0, color="grey", linestyle="--", label="nominal TTL boundary")
    plt.xlabel("Verify attempt time offset from TTL boundary (s)")
    plt.ylabel("Empirical accept rate")
    plt.title(f"otp.bounded-validity: TTL boundary under +/-{jitter_ms_sd:.0f}ms jitter")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(RESULTS_DIR, "delayed_otp_ttl_sweep.png"), dpi=150)
    plt.close()
    return df


def timing_side_channel_demo(seeds: list[int] = SEEDS, n_per_group: int = 2000) -> pd.DataFrame:
    per_seed_rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)

        # H0: constant-time comparison - both "correct" and "incorrect" verify calls draw
        # latency from the identical distribution (crypto.timingSafeEqual-style behaviour).
        base_latency_ms = 2.0
        noise_sd_ms = 0.6
        correct_h0 = rng.normal(base_latency_ms, noise_sd_ms, n_per_group)
        incorrect_h0 = rng.normal(base_latency_ms, noise_sd_ms, n_per_group)

        # H1: naive early-exit comparison - an incorrect code that matches fewer leading
        # characters returns faster; model incorrect-code latency as slightly *lower* on
        # average with the same noise, per the classic timing side-channel literature.
        naive_effect_ms = 0.15  # assumed illustrative constant - see module docstring
        correct_h1 = rng.normal(base_latency_ms, noise_sd_ms, n_per_group)
        incorrect_h1 = rng.normal(base_latency_ms - naive_effect_ms, noise_sd_ms, n_per_group)

        for label, correct, incorrect in [("H0_constant_time", correct_h0, incorrect_h0),
                                           ("H1_naive_comparison", correct_h1, incorrect_h1)]:
            t_stat, t_p = stats.ttest_ind(correct, incorrect, equal_var=False)  # Welch's t-test
            u_stat, u_p = stats.mannwhitneyu(correct, incorrect, alternative="two-sided")
            per_seed_rows.append({
                "seed": seed,
                "scenario": label,
                "mean_latency_correct_ms": float(np.mean(correct)),
                "mean_latency_incorrect_ms": float(np.mean(incorrect)),
                "welch_t_stat": float(t_stat),
                "welch_p_value": float(t_p),
                "mannwhitney_u_stat": float(u_stat),
                "mannwhitney_p_value": float(u_p),
            })

    os.makedirs(RESULTS_DIR, exist_ok=True)
    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "delayed_otp_timing_side_channel_per_seed.csv"), index=False)

    agg_rows = []
    for scenario, group in per_seed_df.groupby("scenario"):
        _, welch_combined_p = stats.combine_pvalues(group["welch_p_value"].tolist(), method="fisher")
        _, mw_combined_p = stats.combine_pvalues(group["mannwhitney_p_value"].tolist(), method="fisher")
        agg_rows.append({
            "scenario": scenario,
            "n_seeds": int(len(group)),
            "mean_latency_correct_ms": float(group["mean_latency_correct_ms"].mean()),
            "mean_latency_incorrect_ms": float(group["mean_latency_incorrect_ms"].mean()),
            "welch_fraction_seeds_significant_0_01": float((group["welch_p_value"] < 0.01).mean()),
            "welch_combined_p_fisher": float(welch_combined_p),
            "mannwhitney_fraction_seeds_significant_0_01": float((group["mannwhitney_p_value"] < 0.01).mean()),
            "mannwhitney_combined_p_fisher": float(mw_combined_p),
            "significant_at_0_01": bool(welch_combined_p < 0.01),
        })
    df = pd.DataFrame(agg_rows)
    df.to_csv(os.path.join(RESULTS_DIR, "delayed_otp_timing_side_channel.csv"), index=False)
    return df


if __name__ == "__main__":
    sweep = ttl_boundary_sweep()
    print(sweep.to_string(index=False))
    timing = timing_side_channel_demo()
    print(timing.to_string(index=False))
