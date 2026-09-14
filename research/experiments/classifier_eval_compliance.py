"""Experiment: OTP compliance-violation early-warning classifier.

Trains a classifier to predict, from a *partial, early* view of a login session's OTP
lifecycle events (see `../data/generate_otp_timelines.py` for the full framing and the
deterministic ground-truth labeling function), whether the session's full behavior pattern
constitutes a control-violation pattern (replay, expired-code use, brute-force, cross-session
redemption, or stale-code-after-reissue) as defined by this repo's own predicates.

This is deliberately a *harder* task than the RBA experiment: because only a random prefix
of each scenario's events is revealed to the feature extractor, a meaningful fraction of
violation scenarios look identical to benign ones at feature-extraction time (the
violating event simply hasn't happened yet in what was observed). That is intentional and
is what keeps the reported metrics informative rather than saturating at ~1.0.

Usage:
    py research/experiments/classifier_eval_compliance.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.common.metrics import compute_binary_metrics, plot_roc, dummy_baseline_rows  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_PATH = os.path.join(RESEARCH_DIR, "data", "generated", "otp_timelines.csv")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")

FEATURE_COLUMNS = [
    "n_invalid_so_far", "n_valid_so_far", "n_reissues_so_far", "max_time_offset_so_far",
    "any_cross_session_so_far", "any_valid_after_reissue_so_far",
    "any_valid_near_or_after_ttl_so_far", "mean_invalid_attempt_gap_s",
    "channel_is_sms", "fraction_observed",
]
TARGET = "label"

MODELS = {
    "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "gradient_boosting": GradientBoostingClassifier(random_state=42),
}


def build_pipeline(model) -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", model)])


def run(data_path: str = DATA_PATH, feature_columns: list | None = None, seed: int = 42,
        plot: bool | None = None, include_dummy_baselines: bool = True) -> pd.DataFrame:
    cols = feature_columns or FEATURE_COLUMNS
    df = pd.read_csv(data_path)
    X = df[cols]
    y = df[TARGET].values

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    results = []
    os.makedirs(RESULTS_DIR, exist_ok=True)
    do_plot = plot if plot is not None else (feature_columns is None)

    for name, model in MODELS.items():
        pipe = build_pipeline(model)
        y_score = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
        metrics = compute_binary_metrics(y, y_score)
        row = metrics.as_dict()
        row["model"] = name
        row["experiment"] = "compliance_violation_early_warning"
        row["n_features"] = len(cols)
        row["seed"] = seed
        results.append(row)
        if do_plot:  # only plot/print for the full-feature baseline run
            plot_roc(y, y_score, os.path.join(RESULTS_DIR, f"roc_compliance_{name}.png"), label=name)
            print(f"[compliance/{name}] {row}")

    # Trivial baselines (majority-class / stratified-random) so learned-model metrics can
    # be read against something. Skipped by ablation scripts (include_dummy_baselines=False)
    # since ablating features against a dummy that ignores X entirely is meaningless.
    if include_dummy_baselines:
        for row in dummy_baseline_rows(X, y, cv):
            row["experiment"] = "compliance_violation_early_warning"
            row["n_features"] = len(cols)
            row["seed"] = seed
            results.append(row)

    out = pd.DataFrame(results)
    if feature_columns is None:
        out.to_csv(os.path.join(RESULTS_DIR, "compliance_classifier_metrics.csv"), index=False)
    return out


if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        raise SystemExit(f"missing {DATA_PATH} - run generate_otp_timelines.py first")
    run()
