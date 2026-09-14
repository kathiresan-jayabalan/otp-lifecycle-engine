"""Experiment: risk-based-authentication (RBA) login-risk classifier.

Trains a classifier to predict `is_account_takeover` from login-context features on the
synthetic-but-documented dataset produced by `../data/generate_rba_dataset.py`. Reports
accuracy/precision/recall/F1/ROC-AUC via 5-fold stratified cross-validation (not a single
train/test split) to keep the reported numbers stable against the specific seed used to
generate the data.

Usage:
    py research/experiments/classifier_eval_rba.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.common.metrics import compute_binary_metrics, plot_roc, dummy_baseline_rows  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_PATH = os.path.join(RESEARCH_DIR, "data", "generated", "rba_synthetic.csv")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")

NUMERIC_FEATURES = ["country_risk", "asn_reputation_risk", "is_new_country", "is_new_device",
                     "round_trip_time_ms", "hour_of_day", "is_attack_ip"]
CATEGORICAL_FEATURES = ["device_type"]
TARGET = "is_account_takeover"

MODELS = {
    "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "random_forest": RandomForestClassifier(n_estimators=300, max_depth=8, random_state=42, class_weight="balanced"),
}


def build_pipeline(model) -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def run(data_path: str = DATA_PATH, seed: int = 42, include_dummy_baselines: bool = True) -> pd.DataFrame:
    df = pd.read_csv(data_path)
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET].values

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    results = []
    os.makedirs(RESULTS_DIR, exist_ok=True)

    for name, model in MODELS.items():
        pipe = build_pipeline(model)
        y_score = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
        metrics = compute_binary_metrics(y, y_score)
        auc = plot_roc(y, y_score, os.path.join(RESULTS_DIR, f"roc_rba_{name}.png"), label=name)
        row = metrics.as_dict()
        row["model"] = name
        row["experiment"] = "rba_login_risk_classifier"
        row["seed"] = seed
        results.append(row)
        print(f"[rba/{name}] {row}")

    if include_dummy_baselines:
        for row in dummy_baseline_rows(X, y, cv):
            row["experiment"] = "rba_login_risk_classifier"
            row["seed"] = seed
            results.append(row)

    out = pd.DataFrame(results)
    out.to_csv(os.path.join(RESULTS_DIR, "rba_classifier_metrics.csv"), index=False)
    return out


if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        raise SystemExit(f"missing {DATA_PATH} - run generate_rba_dataset.py first")
    run()
