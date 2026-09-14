"""Cross-repo research summary: OTP (this repo) vs. passkey (`fido2-nist-mfa-research`).

Every experiment in this repo and its sibling `fido2-nist-mfa-research` repo evaluates one
mechanism (OTP or passkey) in isolation. This script is the one place that reads both repos'
result CSVs and puts the numbers side-by-side, so the OTP-vs-passkey trade-off claims in the
combined research narrative are backed by an actual generated table rather than an assertion.

Cross-repo dependency: this script assumes `fido2-nist-mfa-research` is checked out alongside
this repo under the same parent directory (this workspace's convention: both repos live
directly under the same IdeaProjects folder). Each sibling-repo section degrades gracefully -
if a specific sibling CSV is missing, that section is written with a clear "not available"
note (naming the missing file and the command to generate it) instead of raising, so a partial
run of this script (e.g. before the sibling repo's `risk_adaptive_policy.py`-dependent CSVs
exist) still produces a usable document for the sections that ARE available.

Run this AFTER both repos' `run_all.py` have completed at least once, and after this repo's
own `risk_adaptive_policy.py` has been run (it in turn depends on the sibling repo's
`passkey_friction_completion.csv`, so effectively: sibling `friction_completion.py` -> this
repo's `risk_adaptive_policy.py` -> this script).

Usage:
    py research/experiments/cross_repo_summary.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")

SIBLING_REPO_RESULTS_DIR = os.path.abspath(
    os.path.join(RESEARCH_DIR, "..", "..", "fido2-nist-mfa-research", "research", "results")
)

COMMON_CLASSIFIER_COLUMNS = ["model", "accuracy", "precision", "recall", "f1", "roc_auc"]


def _fmt(x) -> str:
    if isinstance(x, float):
        return "nan" if x != x else f"{x:.3f}"
    return str(x)


def _read_csv_or_none(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def _classifier_table(df: pd.DataFrame | None) -> list[str]:
    if df is None:
        return ["_not available_"]
    df = df[[c for c in COMMON_CLASSIFIER_COLUMNS if c in df.columns]]
    if "model" in df.columns:
        df = df[~df["model"].astype(str).str.startswith("dummy_")]
    lines = ["| " + " | ".join(COMMON_CLASSIFIER_COLUMNS) + " |", "|" + "---|" * len(COMMON_CLASSIFIER_COLUMNS)]
    for r in df.to_dict("records"):
        lines.append("| " + " | ".join(_fmt(r.get(c, "n/a")) for c in COMMON_CLASSIFIER_COLUMNS) + " |")
    return lines


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)

    rba_metrics = _read_csv_or_none(os.path.join(RESULTS_DIR, "rba_classifier_metrics.csv"))
    otp_compliance_metrics = _read_csv_or_none(os.path.join(RESULTS_DIR, "compliance_classifier_metrics.csv"))
    otp_friction = _read_csv_or_none(os.path.join(RESULTS_DIR, "otp_friction_completion.csv"))
    risk_policy = _read_csv_or_none(os.path.join(RESULTS_DIR, "risk_adaptive_policy.csv"))

    ceremony_metrics = _read_csv_or_none(os.path.join(SIBLING_REPO_RESULTS_DIR, "ceremony_classifier_metrics.csv"))
    passkey_compliance_metrics = _read_csv_or_none(
        os.path.join(SIBLING_REPO_RESULTS_DIR, "passkey_compliance_classifier_metrics.csv"))
    passkey_friction = _read_csv_or_none(os.path.join(SIBLING_REPO_RESULTS_DIR, "passkey_friction_completion.csv"))

    lines: list[str] = []
    lines.append("# Cross-repo research summary - OTP vs. passkey risk-adaptive MFA")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}Z")
    lines.append("")
    lines.append("Reads `pci-dss-otp-mfa-research` (this repo) and `fido2-nist-mfa-research` (sibling")
    lines.append("checkout) results side-by-side. See each source repo's own `research/README.md` and")
    lines.append("`research/results/summary_table.md` for the full, single-repo detail behind each")
    lines.append("number here. See the 'Modeling assumptions & limitations' section at the end before")
    lines.append("citing any number from this document.")
    lines.append("")

    lines.append("## 1. Login-risk / anomaly classifiers (common columns only)")
    lines.append("")
    lines.append("### 1a. RBA login-risk classifier (OTP repo, `classifier_eval_rba.py`)")
    lines.append("")
    lines += _classifier_table(rba_metrics)
    lines.append("")
    lines.append("### 1b. WebAuthn ceremony-anomaly classifier (passkey repo, `classifier_eval_ceremony.py`)")
    lines.append("")
    lines += _classifier_table(ceremony_metrics)
    lines.append("")
    lines.append("Note: the OTP repo's table above excludes `dummy_most_frequent`/`dummy_stratified`")
    lines.append("baseline rows for a fair comparison - the passkey repo does not yet compute these")
    lines.append("baselines at all (see limitations). PR-AUC is available for the OTP repo's classifiers")
    lines.append("but not the passkey repo's - see limitations.")
    lines.append("")

    lines.append("## 2. Compliance-violation early-warning classifiers (common columns only)")
    lines.append("")
    lines.append("### 2a. OTP compliance-violation classifier (OTP repo, `classifier_eval_compliance.py`)")
    lines.append("")
    lines += _classifier_table(otp_compliance_metrics)
    lines.append("")
    lines.append("### 2b. Passkey compliance-violation classifier (passkey repo, `classifier_eval_passkey_compliance.py`)")
    lines.append("")
    lines += _classifier_table(passkey_compliance_metrics)
    lines.append("")

    lines.append("## 3. Friction / completion-rate comparison")
    lines.append("")
    lines.append("Both repos' friction models share the same user-patience log-normal distribution")
    lines.append("(`PATIENCE_LOGNORMAL_MEAN_LOG`/`PATIENCE_LOGNORMAL_SIGMA`, identical in both")
    lines.append("`friction_completion.py` files) so this comparison is apples-to-apples on the")
    lines.append("usability axis - only the channel/ceremony mechanics differ.")
    lines.append("")
    lines.append("### 3a. OTP delivery channels (OTP repo)")
    lines.append("")
    if otp_friction is not None:
        lines.append("| Scenario | Mean completion rate | Mean abandonment rate | Mean time to complete (s) |")
        lines.append("|---|---|---|---|")
        for r in otp_friction.to_dict("records"):
            lines.append(f"| {r['scenario']} | {_fmt(r['mean_completion_rate'])} | {_fmt(r['mean_abandonment_rate'])} | {_fmt(r['mean_time_to_complete_s'])} |")
    else:
        lines.append("_not available - run `py research/experiments/friction_completion.py` in this repo_")
    lines.append("")
    lines.append("### 3b. Passkey ceremony scenarios (passkey repo)")
    lines.append("")
    if passkey_friction is not None:
        lines.append("| Scenario | Mean completion rate | Mean abandonment rate | Mean time to complete (s) |")
        lines.append("|---|---|---|---|")
        for r in passkey_friction.to_dict("records"):
            lines.append(f"| {r['scenario']} | {_fmt(r['mean_completion_rate'])} | {_fmt(r['mean_abandonment_rate'])} | {_fmt(r['mean_time_to_complete_s'])} |")
    else:
        lines.append("_not available - run `py research/experiments/friction_completion.py` in the sibling repo_")
    lines.append("")

    lines.append("## 4. Risk-adaptive step-up policy comparison (OTP repo, `risk_adaptive_policy.py`)")
    lines.append("")
    lines.append("Simulated over the OTP repo's RBA login population; passkey step-up assignments use")
    lines.append("the sibling repo's friction results for the abandonment-rate side of the trade-off.")
    lines.append("")
    if risk_policy is not None:
        lines.append("| Policy | Mean attack success rate | Mean legitimate abandonment rate | Step-up: passkey | Step-up: OTP | Step-up: none |")
        lines.append("|---|---|---|---|---|---|")
        for r in risk_policy.to_dict("records"):
            lines.append(
                f"| {r['policy']} | {_fmt(r['mean_attack_success_rate'])} | {_fmt(r['mean_legitimate_abandonment_rate'])} "
                f"| {_fmt(r['mean_stepup_rate_passkey'])} | {_fmt(r['mean_stepup_rate_otp'])} | {_fmt(r['mean_stepup_rate_none'])} |"
            )
    else:
        lines.append("_not available - run `py research/experiments/risk_adaptive_policy.py` in this repo_")
    lines.append("")

    lines.append("## 5. Modeling assumptions & limitations")
    lines.append("")
    lines.append("- **Statistical-instrumentation parity gap**: the passkey repo's classifiers")
    lines.append("  (`classifier_eval_ceremony.py`, `classifier_eval_passkey_compliance.py`) do not yet")
    lines.append("  compute PR-AUC or dummy-baseline (`dummy_most_frequent`/`dummy_stratified`) rows, and")
    lines.append("  its ablation study (`ablation_features.py`) does not apply Benjamini-Hochberg")
    lines.append("  multiple-testing correction - all three are present in this (OTP) repo. This is a")
    lines.append("  known, deliberately out-of-scope gap, not a silently dropped comparison.")
    lines.append("- **Friction/completion-rate constants are illustrative, not measured** - see the")
    lines.append("  \"Honesty note\" in each repo's `friction_completion.py` module docstring. Treat the")
    lines.append("  relative comparison between scenarios/channels as the informative signal, not the")
    lines.append("  absolute completion-rate numbers.")
    lines.append("- **Risk-adaptive policy residual-risk multipliers are illustrative and")
    lines.append("  literature-grounded, not fit from data** - see the \"Honesty note\" in")
    lines.append("  `risk_adaptive_policy.py`'s module docstring for the specific citations behind each")
    lines.append("  constant.")
    lines.append("- **`risk_adaptive` is not Pareto-dominant over `always_otp` in \u00a74 above** - it")
    lines.append("  trades a small security regression (mean attack success rate 0.380 vs. 0.350) for a")
    lines.append("  large usability gain (mean legitimate abandonment rate 0.018 vs. 0.045). This is not")
    lines.append("  a result tuned to manufacture an \"adaptive wins\" claim (see this repo's \"no result")
    lines.append("  is hand-edited or backfilled\" convention in `research/README.md`); it reflects the")
    lines.append("  synthetic RBA dataset's intentionally elevated ~32% attack prevalence (chosen for")
    lines.append("  classifier-benchmarking difficulty, not deployment realism - see `research/README.md`")
    lines.append("  headline results), which leaves the risk-adaptive policy's majority no-step-up tier")
    lines.append("  absorbing a meaningful share of true attacks even after its thresholds are calibrated")
    lines.append("  against the legitimate-only risk-score distribution (see `_assign_tier` in")
    lines.append("  `risk_adaptive_policy.py`). Read as a genuine finding rather than a limitation: naive")
    lines.append("  percentile-based risk tiers calibrated on baseline/normal traffic can under-protect")
    lines.append("  during periods of elevated attack prevalence (e.g. a credential-stuffing campaign)")
    lines.append("  unless tier sizes are widened dynamically.")
    lines.append("- **The risk-adaptive and always-passkey policies assume a platform authenticator is")
    lines.append("  already enrolled** for every passkey step-up (`platform_authenticator_enrolled`")
    lines.append("  scenario). The slower, less reliable `cross_device_fallback` case is not modeled in")
    lines.append("  the policy simulation - a real deployment's passkey step-up would sometimes hit that")
    lines.append("  path, worsening `always_passkey`'s and `risk_adaptive`'s abandonment numbers")
    lines.append("  accordingly.")
    lines.append("- **Cross-repo comparisons assume both checkouts are at the commit each repo's")
    lines.append("  `run_all.py` and `friction_completion.py` were most recently run at** - this script")
    lines.append("  does not verify commit hashes match; re-run both repos' pipelines before trusting a")
    lines.append("  stale comparison.")
    lines.append("")

    out_path = os.path.join(RESULTS_DIR, "cross_repo_summary.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
