"""Shared metric/plotting helpers used by every experiment script.

Kept dependency-light and deterministic: every function here is a thin, well-tested
wrapper around scikit-learn/matplotlib so that experiment scripts stay focused on
*what* is being measured rather than *how* metrics are computed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    roc_curve,
    average_precision_score,
    accuracy_score,
)
from sklearn.model_selection import cross_val_predict


@dataclass
class BinaryMetrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    pr_auc: float
    support_positive: int
    support_negative: int

    def as_dict(self) -> dict:
        return asdict(self)


def compute_binary_metrics(y_true: Iterable[int], y_score: Iterable[float], threshold: float = 0.5) -> BinaryMetrics:
    """Compute accuracy/precision/recall/F1 at `threshold` plus threshold-free ROC-AUC and PR-AUC.

    y_score must be a continuous score (probability or decision function output) so that
    roc_auc_score/average_precision_score reflect ranking quality independent of the chosen
    operating threshold.

    PR-AUC (average precision) is reported alongside ROC-AUC because ROC-AUC can look
    deceptively strong under severe class imbalance (it is insensitive to the negative
    class's overwhelming size); PR-AUC is the standard complement for that case and its
    baseline (a random/no-skill classifier) is the positive rate itself, not 0.5.
    """
    y_true = np.asarray(list(y_true))
    y_score = np.asarray(list(y_score), dtype=float)
    y_pred = (y_score >= threshold).astype(int)

    n_pos = int((y_true == 1).sum())
    n_neg = int((y_true == 0).sum())

    if n_pos == 0 or n_neg == 0:
        # ROC-AUC/PR-AUC are undefined with a single class present; report NaN rather
        # than silently emitting a misleading 0.0/1.0.
        roc_auc = float("nan")
        pr_auc = float("nan")
    else:
        roc_auc = float(roc_auc_score(y_true, y_score))
        pr_auc = float(average_precision_score(y_true, y_score))

    return BinaryMetrics(
        accuracy=float(accuracy_score(y_true, y_pred)),
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall_score(y_true, y_pred, zero_division=0)),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        roc_auc=roc_auc,
        pr_auc=pr_auc,
        support_positive=n_pos,
        support_negative=n_neg,
    )


def dummy_baseline_rows(X, y: Iterable[int], cv, threshold: float = 0.5) -> list[dict]:
    """Cross-validated metrics for two trivial baselines: always-predict-majority-class
    and stratified-random-guess. Every learned-model result in this repo should be read
    against these numbers - a learned model that doesn't clear the stratified baseline's
    F1/PR-AUC by a meaningful margin isn't demonstrating learnable signal.

    Returns plain dicts (not BinaryMetrics) tagged with a `model` name so callers can
    concatenate them directly onto a results DataFrame.
    """
    y = np.asarray(list(y))
    rows = []
    strategies = {
        "dummy_most_frequent": DummyClassifier(strategy="most_frequent"),
        "dummy_stratified": DummyClassifier(strategy="stratified", random_state=42),
    }
    for name, dummy in strategies.items():
        y_score = cross_val_predict(dummy, X, y, cv=cv, method="predict_proba")[:, 1]
        metrics = compute_binary_metrics(y, y_score, threshold=threshold)
        row = metrics.as_dict()
        row["model"] = name
        rows.append(row)
    return rows


def plot_roc(y_true: Iterable[int], y_score: Iterable[float], out_path: str, label: str = "model") -> float:
    """Plot an ROC curve to out_path (PNG) and return the ROC-AUC value plotted."""
    import matplotlib
    matplotlib.use("Agg")  # headless - no display available in CI/terminal runs
    import matplotlib.pyplot as plt

    y_true = np.asarray(list(y_true))
    y_score = np.asarray(list(y_score), dtype=float)

    if len(np.unique(y_true)) < 2:
        raise ValueError("plot_roc requires both classes present in y_true")

    fpr, tpr, _ = roc_curve(y_true, y_score)
    auc = float(roc_auc_score(y_true, y_score))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.figure(figsize=(5, 5))
    plt.plot(fpr, tpr, label=f"{label} (AUC={auc:.3f})")
    plt.plot([0, 1], [0, 1], linestyle="--", color="grey", label="chance")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    return auc
