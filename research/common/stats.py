"""Statistical aggregation helpers for multi-seed ablation studies.

A single-seed ablation delta (e.g. "removing feature X drops F1 by 0.007") is a point
estimate and cannot, on its own, distinguish a real effect from cross-validation-fold
noise. Every ablation script in this repo re-runs its estimate across multiple
independent seeds and reports the distribution of the resulting deltas through
`seed_distribution_summary`, rather than a single number.

Two important scope notes, since "N independent seeds" means different things in
different experiments:
  - `ablation_features.py` reuses one fixed synthetic dataset and only reshuffles the
    cross-validation fold assignment per seed - its seed distribution captures
    robustness to fold assignment only, not to a different draw of the underlying data.
  - `ablation_controls.py` and `delayed_otp.py`'s TTL sweep regenerate a fresh synthetic
    dataset per seed - their seed distribution captures true data-generation variance.

Every ablation/experiment script that runs multiple simultaneous hypothesis tests (one
per feature, control, or offset) must pass its raw p-values through `benjamini_hochberg`
before reporting `significant`, rather than comparing each p-value to 0.05 in isolation -
otherwise the family-wise false-positive rate grows with the number of simultaneous
tests (e.g. 10 features x 2 models = 20 tests at uncorrected alpha=0.05 yields an
expected ~1 false positive even if every ablated feature were truly inert).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Sequence

import numpy as np
from scipy import stats


@dataclass
class SeedDistributionSummary:
    n_seeds: int
    mean: float
    std: float
    ci95_low: float
    ci95_high: float
    wilcoxon_p_value: float
    significant_at_0_05: bool

    def as_dict(self) -> dict:
        return asdict(self)


def seed_distribution_summary(deltas: Sequence[float]) -> SeedDistributionSummary:
    """Summarize a sequence of per-seed deltas (e.g. ΔF1 for one ablated feature, one
    value per random seed) into a mean, standard deviation, a 95% confidence interval
    (Student-t, appropriate for the small seed counts used here), and a two-sided
    Wilcoxon signed-rank test against the null hypothesis that the deltas are drawn
    from a distribution centered at zero (i.e. the ablation has no real effect).

    Falls back to a p-value of 1.0 (no evidence of an effect) when every delta is
    exactly zero, since scipy's Wilcoxon test raises on an all-zero-difference input
    rather than returning a p-value.
    """
    arr = np.asarray(list(deltas), dtype=float)
    n = len(arr)
    if n < 2:
        raise ValueError("seed_distribution_summary requires at least 2 seeds")

    mean = float(arr.mean())
    std = float(arr.std(ddof=1))

    sem = std / np.sqrt(n)
    t_crit = stats.t.ppf(0.975, df=n - 1)
    ci_low = mean - t_crit * sem
    ci_high = mean + t_crit * sem

    if np.allclose(arr, 0.0):
        p_value = 1.0
    else:
        _, p_value = stats.wilcoxon(arr, zero_method="wilcox", alternative="two-sided")
        p_value = float(p_value)

    return SeedDistributionSummary(
        n_seeds=n,
        mean=mean,
        std=std,
        ci95_low=float(ci_low),
        ci95_high=float(ci_high),
        wilcoxon_p_value=p_value,
        significant_at_0_05=bool(p_value < 0.05),
    )


@dataclass
class MeanCI95:
    n: int
    mean: float
    std: float
    ci95_low: float
    ci95_high: float

    def as_dict(self) -> dict:
        return asdict(self)


def mean_ci95(values: Sequence[float]) -> MeanCI95:
    """Mean and a Student-t 95% confidence interval across independent seed draws of a
    quantity that has no natural "zero effect" null hypothesis (e.g. an accept rate at
    one TTL offset, aggregated over independent dataset-generation seeds). Unlike
    `seed_distribution_summary`, this does not run a Wilcoxon test - there is nothing to
    test against zero here, only a quantity to describe.
    """
    arr = np.asarray(list(values), dtype=float)
    n = len(arr)
    if n < 2:
        raise ValueError("mean_ci95 requires at least 2 values")

    mean = float(arr.mean())
    std = float(arr.std(ddof=1))
    sem = std / np.sqrt(n)
    t_crit = stats.t.ppf(0.975, df=n - 1)

    return MeanCI95(
        n=n,
        mean=mean,
        std=std,
        ci95_low=float(mean - t_crit * sem),
        ci95_high=float(mean + t_crit * sem),
    )


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg step-up false-discovery-rate correction.

    Returns a boolean array, same order/length as `p_values`, indicating which
    hypotheses remain significant at the given FDR level after correction. Use this
    instead of comparing each p-value to `alpha` in isolation whenever a study runs
    more than one simultaneous test (e.g. one Wilcoxon test per ablated feature).

    Reference: Benjamini & Hochberg (1995), "Controlling the False Discovery Rate:
    A Practical and Powerful Approach to Multiple Testing", JRSS-B 57(1):289-300.
    """
    p = np.asarray(list(p_values), dtype=float)
    m = len(p)
    if m == 0:
        return np.array([], dtype=bool)

    order = np.argsort(p)
    ranked = p[order]
    thresholds = (np.arange(1, m + 1) / m) * alpha

    below = ranked <= thresholds
    if not np.any(below):
        return np.zeros(m, dtype=bool)

    # Largest rank k where p_(k) <= (k/m)*alpha; every hypothesis at or below that
    # rank is declared significant (the BH step-up procedure).
    max_significant_rank = np.max(np.nonzero(below)[0])
    significant_sorted = np.zeros(m, dtype=bool)
    significant_sorted[: max_significant_rank + 1] = True

    significant = np.zeros(m, dtype=bool)
    significant[order] = significant_sorted
    return significant
