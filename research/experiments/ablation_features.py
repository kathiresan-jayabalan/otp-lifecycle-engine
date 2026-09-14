"""Ablation study #1: feature ablation on the compliance early-warning classifier.

For each feature in the full feature set, retrain with that single feature removed and
record the delta in F1 / ROC-AUC vs. the full-feature baseline. A large negative delta means
that feature carries load-bearing signal for detecting violation patterns from partial
observation; a delta near zero means the remaining features already capture that signal.

Statistical rigor: a single train/eval run's delta is a point estimate that cannot, by
itself, separate a real effect from cross-validation-fold noise. This script re-runs the
baseline-vs-ablated comparison under `N_SEEDS` independent stratified-K-fold shuffles (same
dataset, different fold assignment each time) and reports, per feature, the mean delta, a
95% confidence interval, and a two-sided Wilcoxon signed-rank test against the null
hypothesis that the delta is centered at zero (see `research/common/stats.py`).

Scope of "seed" here: each seed only reshuffles which rows land in which cross-validation
fold - the underlying synthetic dataset itself is generated once (see `DATA_PATH`) and
reused across all seeds. This tells you the delta is not an artifact of a particular fold
split; it does NOT tell you the delta would replicate under a different synthetic-data
draw. Compare with `ablation_controls.py`, which regenerates a fresh dataset per seed and
therefore captures true data-generation variance in addition to fold-assignment variance.

Multiple comparisons: this script runs one Wilcoxon test per (model, feature) pair
simultaneously (`len(FEATURE_COLUMNS) * len(MODELS)` tests). `delta_f1_significant` is the
raw, uncorrected p<0.05 flag; `delta_f1_bh_significant` applies a Benjamini-Hochberg
false-discovery-rate correction across that whole family of tests and is the flag that
should be used to decide whether a feature's effect is trustworthy.

Usage:
    py research/experiments/ablation_features.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.experiments.classifier_eval_compliance import run, FEATURE_COLUMNS, DATA_PATH  # noqa: E402
from research.common.stats import seed_distribution_summary, benjamini_hochberg  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
SEEDS = list(range(42, 52))  # 10 independent CV-fold-shuffle seeds


def run_ablation(data_path: str = DATA_PATH, seeds: list[int] = SEEDS) -> pd.DataFrame:
    per_seed_rows = []
    for seed in seeds:
        baseline = run(data_path, feature_columns=FEATURE_COLUMNS, seed=seed, plot=(seed == seeds[0]),
                       include_dummy_baselines=False)
        baseline_by_model = {r["model"]: r for r in baseline.to_dict("records")}

        for r in baseline.to_dict("records"):
            r = dict(r)
            r["ablated_feature"] = "(none - full feature set)"
            r["delta_f1"] = 0.0
            r["delta_roc_auc"] = 0.0
            per_seed_rows.append(r)

        for feature in FEATURE_COLUMNS:
            remaining = [c for c in FEATURE_COLUMNS if c != feature]
            ablated = run(data_path, feature_columns=remaining, seed=seed, plot=False,
                          include_dummy_baselines=False)
            for r in ablated.to_dict("records"):
                r = dict(r)
                base = baseline_by_model[r["model"]]
                r["ablated_feature"] = feature
                r["delta_f1"] = r["f1"] - base["f1"]
                r["delta_roc_auc"] = r["roc_auc"] - base["roc_auc"]
                per_seed_rows.append(r)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    per_seed_df = pd.DataFrame(per_seed_rows)
    per_seed_df.to_csv(os.path.join(RESULTS_DIR, "ablation_features_per_seed.csv"), index=False)

    agg_rows = []
    for (model, feature), group in per_seed_df.groupby(["model", "ablated_feature"]):
        f1_summary = seed_distribution_summary(group["delta_f1"].tolist())
        auc_summary = seed_distribution_summary(group["delta_roc_auc"].tolist())
        agg_rows.append({
            "model": model,
            "ablated_feature": feature,
            "f1": float(group["f1"].mean()),
            "mean_delta_f1": f1_summary.mean,
            "delta_f1_ci95_low": f1_summary.ci95_low,
            "delta_f1_ci95_high": f1_summary.ci95_high,
            "delta_f1_wilcoxon_p": f1_summary.wilcoxon_p_value,
            "delta_f1_significant": f1_summary.significant_at_0_05,
            "roc_auc": float(group["roc_auc"].mean()),
            "mean_delta_roc_auc": auc_summary.mean,
            "delta_roc_auc_ci95_low": auc_summary.ci95_low,
            "delta_roc_auc_ci95_high": auc_summary.ci95_high,
            "delta_roc_auc_wilcoxon_p": auc_summary.wilcoxon_p_value,
            "n_seeds": f1_summary.n_seeds,
        })

    out = pd.DataFrame(agg_rows)

    # Family-wise correction: this study runs one Wilcoxon test per (model, feature)
    # pair simultaneously (len(FEATURE_COLUMNS) x len(MODELS) tests). Comparing each
    # raw p-value to 0.05 in isolation inflates the false-positive rate across that
    # family; Benjamini-Hochberg controls it. The "(none - full feature set)" baseline
    # row is excluded from the correction (its delta is trivially 0 / p=1.0, not a
    # real test of an ablation effect).
    real_mask = out["ablated_feature"] != "(none - full feature set)"
    out["delta_f1_bh_significant"] = False
    out["delta_roc_auc_bh_significant"] = False
    out.loc[real_mask, "delta_f1_bh_significant"] = benjamini_hochberg(out.loc[real_mask, "delta_f1_wilcoxon_p"])
    out.loc[real_mask, "delta_roc_auc_bh_significant"] = benjamini_hochberg(out.loc[real_mask, "delta_roc_auc_wilcoxon_p"])

    out.to_csv(os.path.join(RESULTS_DIR, "ablation_features.csv"), index=False)
    print(out[["model", "ablated_feature", "f1", "mean_delta_f1", "delta_f1_ci95_low",
               "delta_f1_ci95_high", "delta_f1_wilcoxon_p", "delta_f1_significant",
               "delta_f1_bh_significant"]].to_string(index=False))
    return out


if __name__ == "__main__":
    run_ablation()
