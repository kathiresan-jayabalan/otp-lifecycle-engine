# Cross-repo research summary - OTP vs. passkey risk-adaptive MFA

Generated: 2026-09-05T01:59:50.306932+00:00Z

Reads `pci-dss-otp-mfa-research` (this repo) and `fido2-nist-mfa-research` (sibling
checkout) results side-by-side. See each source repo's own `research/README.md` and
`research/results/summary_table.md` for the full, single-repo detail behind each
number here. See the 'Modeling assumptions & limitations' section at the end before
citing any number from this document.

## 1. Login-risk / anomaly classifiers (common columns only)

### 1a. RBA login-risk classifier (OTP repo, `classifier_eval_rba.py`)

| model | accuracy | precision | recall | f1 | roc_auc |
|---|---|---|---|---|---|
| logistic_regression | 0.760 | 0.615 | 0.648 | 0.631 | 0.791 |
| random_forest | 0.765 | 0.638 | 0.597 | 0.617 | 0.787 |

### 1b. WebAuthn ceremony-anomaly classifier (passkey repo, `classifier_eval_ceremony.py`)

| model | accuracy | precision | recall | f1 | roc_auc |
|---|---|---|---|---|---|
| logistic_regression | 0.887 | 0.423 | 0.642 | 0.510 | 0.826 |
| random_forest | 0.940 | 0.751 | 0.506 | 0.605 | 0.802 |

Note: the OTP repo's table above excludes `dummy_most_frequent`/`dummy_stratified`
baseline rows for a fair comparison - the passkey repo does not yet compute these
baselines at all (see limitations). PR-AUC is available for the OTP repo's classifiers
but not the passkey repo's - see limitations.

## 2. Compliance-violation early-warning classifiers (common columns only)

### 2a. OTP compliance-violation classifier (OTP repo, `classifier_eval_compliance.py`)

| model | accuracy | precision | recall | f1 | roc_auc |
|---|---|---|---|---|---|
| logistic_regression | 0.954 | 0.977 | 0.930 | 0.953 | 0.989 |
| gradient_boosting | 0.971 | 0.998 | 0.944 | 0.970 | 0.994 |

### 2b. Passkey compliance-violation classifier (passkey repo, `classifier_eval_passkey_compliance.py`)

| model | accuracy | precision | recall | f1 | roc_auc |
|---|---|---|---|---|---|
| logistic_regression | 0.905 | 0.919 | 0.888 | 0.903 | 0.973 |
| gradient_boosting | 0.898 | 0.910 | 0.883 | 0.896 | 0.973 |

## 3. Friction / completion-rate comparison

Both repos' friction models share the same user-patience log-normal distribution
(`PATIENCE_LOGNORMAL_MEAN_LOG`/`PATIENCE_LOGNORMAL_SIGMA`, identical in both
`friction_completion.py` files) so this comparison is apples-to-apples on the
usability axis - only the channel/ceremony mechanics differ.

### 3a. OTP delivery channels (OTP repo)

| Scenario | Mean completion rate | Mean abandonment rate | Mean time to complete (s) |
|---|---|---|---|
| email_baseline | 0.818 | 0.182 | 10.103 |
| email_degraded | 0.159 | 0.841 | 20.175 |
| sms_baseline | 0.955 | 0.045 | 6.541 |
| sms_degraded | 0.346 | 0.654 | 16.569 |

### 3b. Passkey ceremony scenarios (passkey repo)

| Scenario | Mean completion rate | Mean abandonment rate | Mean time to complete (s) |
|---|---|---|---|
| cross_device_fallback | 0.584 | 0.416 | 12.702 |
| platform_authenticator_enrolled | 0.998 | 0.002 | 1.302 |

## 4. Risk-adaptive step-up policy comparison (OTP repo, `risk_adaptive_policy.py`)

Simulated over the OTP repo's RBA login population; passkey step-up assignments use
the sibling repo's friction results for the abandonment-rate side of the trade-off.

| Policy | Mean attack success rate | Mean legitimate abandonment rate | Step-up: passkey | Step-up: OTP | Step-up: none |
|---|---|---|---|---|---|
| always_otp | 0.350 | 0.045 | 0.000 | 1.000 | 0.000 |
| always_passkey | 0.040 | 0.002 | 1.000 | 0.000 | 0.000 |
| risk_adaptive | 0.380 | 0.018 | 0.169 | 0.267 | 0.563 |

## 5. Modeling assumptions & limitations

- **Statistical-instrumentation parity gap**: the passkey repo's classifiers
  (`classifier_eval_ceremony.py`, `classifier_eval_passkey_compliance.py`) do not yet
  compute PR-AUC or dummy-baseline (`dummy_most_frequent`/`dummy_stratified`) rows, and
  its ablation study (`ablation_features.py`) does not apply Benjamini-Hochberg
  multiple-testing correction - all three are present in this (OTP) repo. This is a
  known, deliberately out-of-scope gap, not a silently dropped comparison.
- **Friction/completion-rate constants are illustrative, not measured** - see the
  "Honesty note" in each repo's `friction_completion.py` module docstring. Treat the
  relative comparison between scenarios/channels as the informative signal, not the
  absolute completion-rate numbers.
- **Risk-adaptive policy residual-risk multipliers are illustrative and
  literature-grounded, not fit from data** - see the "Honesty note" in
  `risk_adaptive_policy.py`'s module docstring for the specific citations behind each
  constant.
- **`risk_adaptive` is not Pareto-dominant over `always_otp` in §4 above** - it
  trades a small security regression (mean attack success rate 0.380 vs. 0.350) for a
  large usability gain (mean legitimate abandonment rate 0.018 vs. 0.045). This is not
  a result tuned to manufacture an "adaptive wins" claim (see this repo's "no result
  is hand-edited or backfilled" convention in `research/README.md`); it reflects the
  synthetic RBA dataset's intentionally elevated ~32% attack prevalence (chosen for
  classifier-benchmarking difficulty, not deployment realism - see `research/README.md`
  headline results), which leaves the risk-adaptive policy's majority no-step-up tier
  absorbing a meaningful share of true attacks even after its thresholds are calibrated
  against the legitimate-only risk-score distribution (see `_assign_tier` in
  `risk_adaptive_policy.py`). Read as a genuine finding rather than a limitation: naive
  percentile-based risk tiers calibrated on baseline/normal traffic can under-protect
  during periods of elevated attack prevalence (e.g. a credential-stuffing campaign)
  unless tier sizes are widened dynamically.
- **The risk-adaptive and always-passkey policies assume a platform authenticator is
  already enrolled** for every passkey step-up (`platform_authenticator_enrolled`
  scenario). The slower, less reliable `cross_device_fallback` case is not modeled in
  the policy simulation - a real deployment's passkey step-up would sometimes hit that
  path, worsening `always_passkey`'s and `risk_adaptive`'s abandonment numbers
  accordingly.
- **Cross-repo comparisons assume both checkouts are at the commit each repo's
  `run_all.py` and `friction_completion.py` were most recently run at** - this script
  does not verify commit hashes match; re-run both repos' pipelines before trusting a
  stale comparison.
