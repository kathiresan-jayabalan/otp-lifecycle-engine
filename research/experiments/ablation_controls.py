"""Ablation study #2: control ablation on the OTP compliance-violation dataset.

For each deterministic predicate this repo enforces (replayRejected, expiryBoundaryEnforced,
attemptLockoutEnforced, sessionBindingEnforced, supersessionEnforced), regenerate the
synthetic scenario dataset **as if that control were not checked at all** (its violation
condition is forced false) and observe two things:

  1. How much the overall violation rate drops (control criticality - how much of the total
     detected violation surface that control alone accounts for).
  2. How much the early-warning classifier's F1/ROC-AUC changes when trained/evaluated
     against the control-blind label definition, holding the feature set fixed.

This is a control ablation, not a feature ablation (see `ablation_features.py` for that) -
here the *ground truth definition* changes, not the model's inputs.

Statistical rigor: both the violation-rate shift and the downstream F1/ROC-AUC shift are
re-computed under `N_SEEDS` independent dataset-generation seeds (a fresh synthetic dataset
each time, not just a fresh CV-fold split), and reported as a mean, 95% confidence interval,
and two-sided Wilcoxon signed-rank test against zero (see `research/common/stats.py`). Contrast
with `ablation_features.py`, which reuses one fixed dataset and only reshuffles CV folds per
seed - this study's seed variance is a strictly stronger robustness check.

Multiple comparisons: this script runs one Wilcoxon test per (model, control) pair per
metric simultaneously. `*_wilcoxon_p` is the raw, uncorrected p-value; `*_bh_significant`
applies a Benjamini-Hochberg false-discovery-rate correction across that family of tests
and is the flag that should be used to decide whether a control's effect is trustworthy.

Usage:
    py research/experiments/ablation_controls.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.data.generate_otp_timelines import generate  # noqa: E402
from research.experiments.classifier_eval_compliance import run, FEATURE_COLUMNS  # noqa: E402
from research.common.stats import seed_distribution_summary, benjamini_hochberg  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")
GENERATED_DIR = os.path.join(RESEARCH_DIR, "data", "generated")

ALL_PREDICATES = [
    "replayRejected", "expiryBoundaryEnforced", "attemptLockoutEnforced",
    "sessionBindingEnforced", "supersessionEnforced",
]
SEEDS = list(range(42, 52))  # 10 independent dataset-generation seeds


def run_ablation(n: int = 4000, seeds: list[int] = SEEDS) -> pd.DataFrame:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    per_seed_rows = []
    for seed in seeds:
        baseline_df = generate(n=n, seed=seed)
        baseline_path = os.path.join(GENERATED_DIR, f"_ablation_baseline_{seed}.csv")
        baseline_df.to_csv(baseline_path, index=False)
        baseline_violation_rate = float(baseline_df["label"].mean())
        baseline_metrics = run(baseline_path, feature_columns=FEATURE_COLUMNS, seed=seed, plot=False,
                               include_dummy_baselines=False)
        baseline_by_model = {r["model"]: r for r in baseline_metrics.to_dict("records")}

        for r in baseline_metrics.to_dict("records"):
            r = dict(r)
            r["disabled_control"] = "(none - all controls active)"
            r["violation_rate"] = baseline_violation_rate
            r["delta_violation_rate"] = 0.0
            r["delta_f1"] = 0.0
            r["delta_roc_auc"] = 0.0
            per_seed_rows.append(r)

        for predicate in ALL_PREDICATES:
            df = generate(n=n, seed=seed, disabled_predicates=frozenset({predicate}))
            path = os.path.join(GENERATED_DIR, f"_ablation_{predicate}_{seed}.csv")
            df.to_csv(path, index=False)
            violation_rate = float(df["label"].mean())

            metrics = run(path, feature_columns=FEATURE_COLUMNS, seed=seed, plot=False,
                         include_dummy_baselines=False)
            for r in metrics.to_dict("records"):
                r = dict(r)
                base = baseline_by_model[r["model"]]
                r["disabled_control"] = predicate
                r["violation_rate"] = violation_rate
                r["delta_violation_rate"] = violation_rate - baseline_violation_rate
                r["delta_f1"] = r["f1"] - base["f1"]
                r["delta_roc_auc"] = r["roc_auc"] - base["roc_auc"]
                per_seed_rows.append(r)

            os.remove(path)
        os.remove(baseline_path)

    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "ablation_controls_per_seed.csv"), index=False)

    agg_rows = []
    for (model, control), group in per_seed_df.groupby(["model", "disabled_control"]):
        rate_summary = seed_distribution_summary(group["delta_violation_rate"].tolist())
        f1_summary = seed_distribution_summary(group["delta_f1"].tolist())
        auc_summary = seed_distribution_summary(group["delta_roc_auc"].tolist())
        agg_rows.append({
            "model": model,
            "disabled_control": control,
            "violation_rate": float(group["violation_rate"].mean()),
            "mean_delta_violation_rate": rate_summary.mean,
            "delta_violation_rate_ci95_low": rate_summary.ci95_low,
            "delta_violation_rate_ci95_high": rate_summary.ci95_high,
            "delta_violation_rate_wilcoxon_p": rate_summary.wilcoxon_p_value,
            "f1": float(group["f1"].mean()),
            "mean_delta_f1": f1_summary.mean,
            "delta_f1_wilcoxon_p": f1_summary.wilcoxon_p_value,
            "roc_auc": float(group["roc_auc"].mean()),
            "mean_delta_roc_auc": auc_summary.mean,
            "delta_roc_auc_wilcoxon_p": auc_summary.wilcoxon_p_value,
            "n_seeds": rate_summary.n_seeds,
        })

    out = pd.DataFrame(agg_rows)

    # Family-wise correction across the simultaneous per-control Wilcoxon tests (see
    # ablation_features.py for the same treatment and rationale). The "(none - all
    # controls active)" baseline row is excluded (trivially zero delta / p=1.0).
    real_mask = out["disabled_control"] != "(none - all controls active)"
    for col in ("delta_violation_rate", "delta_f1", "delta_roc_auc"):
        sig_col = f"{col}_bh_significant"
        out[sig_col] = False
        out.loc[real_mask, sig_col] = benjamini_hochberg(out.loc[real_mask, f"{col}_wilcoxon_p"])

    out.to_csv(os.path.join(RESULTS_DIR, "ablation_controls.csv"), index=False)
    print(out[["model", "disabled_control", "violation_rate", "mean_delta_violation_rate",
               "delta_violation_rate_ci95_low", "delta_violation_rate_ci95_high",
               "delta_violation_rate_wilcoxon_p", "delta_violation_rate_bh_significant",
               "f1", "mean_delta_f1", "roc_auc", "mean_delta_roc_auc"]].to_string(index=False))
    return out


if __name__ == "__main__":
    run_ablation()
