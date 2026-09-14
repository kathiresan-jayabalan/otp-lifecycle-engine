# Research layer - results summary

Generated: 2026-09-05T01:46:22.208402+00:00Z

All numbers below are produced by `research/experiments/run_all.py` against
seeded, documented synthetic datasets (see `research/README.md` for what is real
vs. synthetic). Regenerate with the same seed to reproduce bit-for-bit.

## 1. RBA login-risk classifier (`classifier_eval_rba.py`)

`dummy_most_frequent`/`dummy_stratified` are trivial baselines (see
`research/common/metrics.py:dummy_baseline_rows`) - every learned model should be
read against these, not against 0.5/chance.

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| logistic_regression | 0.760 | 0.615 | 0.648 | 0.631 | 0.791 | 0.696 |
| random_forest | 0.765 | 0.638 | 0.597 | 0.617 | 0.787 | 0.682 |
| dummy_most_frequent | 0.683 | 0.000 | 0.000 | 0.000 | 0.500 | 0.317 |
| dummy_stratified | 0.567 | 0.318 | 0.321 | 0.320 | 0.501 | 0.317 |

## 2. OTP compliance-violation early-warning classifier (`classifier_eval_compliance.py`)

Predicts eventual control-violation pattern from a partial (30-100% revealed) view
of each synthetic session's event timeline. `dummy_most_frequent`/`dummy_stratified`
are trivial baselines - see note in section 1.

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| logistic_regression | 0.954 | 0.977 | 0.930 | 0.953 | 0.989 | 0.991 |
| gradient_boosting | 0.971 | 0.998 | 0.944 | 0.970 | 0.994 | 0.995 |
| dummy_most_frequent | 0.505 | 0.505 | 1.000 | 0.672 | 0.500 | 0.505 |
| dummy_stratified | 0.504 | 0.509 | 0.502 | 0.506 | 0.504 | 0.507 |

## 3. Feature ablation (`ablation_features.py`)

Mean ΔF1 / ΔROC-AUC vs. the full-feature baseline when one feature is removed,
aggregated over 10 independent CV-fold-shuffle seeds
(best learned model shown; scope note: this seed variance is fold-assignment only,
see module docstring). 95% CI is a Student-t interval across seeds; `Wilcoxon p` is
the raw two-sided Wilcoxon signed-rank p-value against zero; `BH sig.` is whether the
effect survives Benjamini-Hochberg correction across all
20 simultaneous tests in this study.

Best model by F1: **gradient_boosting**

| Ablated feature | F1 | Mean ΔF1 | ΔF1 95% CI | Wilcoxon p | BH sig. | ΔROC-AUC |
|---|---|---|---|---|---|---|
| any_cross_session_so_far | 0.849 | -0.121 | [-0.122, -0.120] | 0.002 | True | -0.058 |
| n_valid_so_far | 0.897 | -0.073 | [-0.074, -0.073] | 0.002 | True | -0.042 |
| n_invalid_so_far | 0.962 | -0.009 | [-0.009, -0.008] | 0.002 | True | -0.002 |
| (none - full feature set) | 0.970 | 0.000 | [0.000, 0.000] | 1.000 | False | 0.000 |
| any_valid_near_or_after_ttl_so_far | 0.970 | 0.000 | [0.000, 0.000] | 1.000 | False | 0.000 |
| max_time_offset_so_far | 0.970 | 0.000 | [-0.000, 0.000] | 0.778 | False | -0.001 |
| channel_is_sms | 0.970 | 0.000 | [-0.000, 0.000] | 1.000 | False | 0.000 |
| any_valid_after_reissue_so_far | 0.970 | 0.000 | [-0.000, 0.000] | 0.893 | False | -0.000 |
| mean_invalid_attempt_gap_s | 0.970 | 0.000 | [-0.000, 0.000] | 0.270 | False | -0.000 |
| n_reissues_so_far | 0.970 | 0.000 | [-0.000, 0.000] | 0.207 | False | 0.000 |
| fraction_observed | 0.971 | 0.001 | [0.000, 0.001] | 0.008 | True | -0.012 |

## 4. Control ablation (`ablation_controls.py`)

Effect of disabling one deterministic predicate on the overall violation rate and
on downstream classifier metrics, aggregated over 10
independent dataset-generation seeds (best model shown; this seed variance is true
data-generation variance, stronger than section 3's fold-only variance). 95% CI is a
Student-t interval across seeds; `Wilcoxon p` is the raw two-sided Wilcoxon
signed-rank p-value; `BH sig.` is whether the effect survives Benjamini-Hochberg
correction across all 10 simultaneous tests in this study.

| Disabled control | Violation rate | Mean ΔViolation rate | 95% CI | Wilcoxon p | BH sig. | F1 | Mean ΔF1 |
|---|---|---|---|---|---|---|---|
| replayRejected | 0.399 | -0.102 | [-0.106, -0.098] | 0.002 | True | 0.999 | 0.030 |
| expiryBoundaryEnforced | 0.400 | -0.102 | [-0.105, -0.098] | 0.002 | True | 0.961 | -0.008 |
| attemptLockoutEnforced | 0.401 | -0.100 | [-0.103, -0.097] | 0.002 | True | 0.961 | -0.008 |
| sessionBindingEnforced | 0.401 | -0.100 | [-0.103, -0.098] | 0.002 | True | 0.960 | -0.008 |
| supersessionEnforced | 0.405 | -0.097 | [-0.100, -0.093] | 0.002 | True | 0.961 | -0.008 |
| (none - all controls active) | 0.501 | 0.000 | [0.000, 0.000] | 1.000 | False | 0.969 | 0.000 |

## 5. Delayed-OTP: TTL boundary sweep (`delayed_otp.py`)

Empirical accept rate vs. verify-attempt delay offset from the TTL boundary,
under +/-120ms simulated clock/network jitter, aggregated over 10
independent RNG seeds with a Student-t 95% CI per offset (see `delayed_otp_ttl_sweep.png`).

| Offset from TTL (s) | Mean accept rate | 95% CI |
|---|---|---|
| -5.0 | 1.000 | [1.000, 1.000] |
| -4.5 | 1.000 | [1.000, 1.000] |
| -4.0 | 1.000 | [1.000, 1.000] |
| -3.5 | 1.000 | [1.000, 1.000] |
| -3.0 | 1.000 | [1.000, 1.000] |
| -2.5 | 1.000 | [1.000, 1.000] |
| -2.0 | 1.000 | [1.000, 1.000] |
| -1.5 | 1.000 | [1.000, 1.000] |
| -1.0 | 1.000 | [1.000, 1.000] |
| -0.5 | 1.000 | [1.000, 1.000] |
| +0.0 | 0.507 | [0.492, 0.521] |
| +0.5 | 0.000 | [-0.000, 0.001] |
| +1.0 | 0.000 | [0.000, 0.000] |
| +1.5 | 0.000 | [0.000, 0.000] |
| +2.0 | 0.000 | [0.000, 0.000] |
| +2.5 | 0.000 | [0.000, 0.000] |
| +3.0 | 0.000 | [0.000, 0.000] |
| +3.5 | 0.000 | [0.000, 0.000] |
| +4.0 | 0.000 | [0.000, 0.000] |
| +4.5 | 0.000 | [0.000, 0.000] |
| +5.0 | 0.000 | [0.000, 0.000] |

## 6. Delayed-OTP: timing side-channel statistical-power demonstration (`delayed_otp.py`)

Simulated verification-latency distributions under two comparison strategies, re-run
over 10 independent seeds and combined via Fisher's method (not a
single seed's p-value). See the module docstring for the concrete static-code finding
this models (`demo-app/lib/otpStore.js` uses `!==`, not `crypto.timingSafeEqual`) and for
the honesty caveat on the assumed effect size.

| Scenario | Mean latency (correct, ms) | Mean latency (incorrect, ms) | Welch combined p (Fisher) | Mann-Whitney combined p (Fisher) | Significant @0.01 |
|---|---|---|---|---|---|
| H0_constant_time | 1.999 | 2.002 | 0.196 | 0.303 | False |
| H1_naive_comparison | 2.002 | 1.847 | 0.000 | 0.000 | True |

## 7. OTP delivery friction / completion-rate proxy (`friction_completion.py`)

Synthetic usability proxy - see the module docstring for the full data-generating
process and honesty notes. `PATIENCE_LOGNORMAL_MEAN_LOG`/`PATIENCE_LOGNORMAL_SIGMA`
are shared with the sibling `fido2-nist-mfa-research` repo's passkey version of this
experiment for a fair cross-repo completion-rate comparison (see
`research/results/cross_repo_summary.md` if present).

Aggregated over 10 independent simulation seeds. 95% CI is a
Student-t interval across seeds.

| Scenario | Mean completion rate | 95% CI | Mean abandonment rate | Mean time to complete (s) | 95% CI |
|---|---|---|---|---|---|
| email_baseline | 0.818 | [0.815, 0.821] | 0.182 | 10.103 | [10.042, 10.164] |
| email_degraded | 0.159 | [0.155, 0.163] | 0.841 | 20.175 | [19.793, 20.557] |
| sms_baseline | 0.955 | [0.952, 0.958] | 0.045 | 6.541 | [6.517, 6.565] |
| sms_degraded | 0.346 | [0.341, 0.351] | 0.654 | 16.569 | [16.435, 16.704] |
