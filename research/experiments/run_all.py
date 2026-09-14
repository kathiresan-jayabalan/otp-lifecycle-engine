"""Orchestrates the full research layer: generate datasets, run every experiment, and
assemble a single `results/summary_table.md` with every headline number in one place.

Usage:
    py research/experiments/run_all.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.data.generate_rba_dataset import generate as generate_rba  # noqa: E402
from research.data.generate_otp_timelines import generate as generate_otp  # noqa: E402
from research.experiments import classifier_eval_rba, classifier_eval_compliance  # noqa: E402
from research.experiments import ablation_features, ablation_controls, delayed_otp  # noqa: E402
from research.experiments import friction_completion  # noqa: E402

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..")
RESULTS_DIR = os.path.join(RESEARCH_DIR, "results")
GENERATED_DIR = os.path.join(RESEARCH_DIR, "data", "generated")


def _fmt(x) -> str:
    if isinstance(x, float):
        return "nan" if x != x else f"{x:.3f}"
    return str(x)


def main() -> None:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("== generating datasets ==")
    rba_df = generate_rba(n=6000, seed=42)
    rba_path = os.path.join(GENERATED_DIR, "rba_synthetic.csv")
    rba_df.to_csv(rba_path, index=False)
    print(f"rba_synthetic.csv: {len(rba_df)} rows, positive rate {rba_df['is_account_takeover'].mean():.4f}")

    otp_df = generate_otp(n=4000, seed=42)
    otp_path = os.path.join(GENERATED_DIR, "otp_timelines.csv")
    otp_df.to_csv(otp_path, index=False)
    print(f"otp_timelines.csv: {len(otp_df)} rows, violation rate {otp_df['label'].mean():.4f}")

    print("\n== classifier_eval_rba ==")
    rba_metrics = classifier_eval_rba.run(rba_path)

    print("\n== classifier_eval_compliance ==")
    compliance_metrics = classifier_eval_compliance.run(otp_path)

    print("\n== ablation_features ==")
    feat_ablation = ablation_features.run_ablation(otp_path)

    print("\n== ablation_controls ==")
    control_ablation = ablation_controls.run_ablation()

    print("\n== delayed_otp ==")
    ttl_sweep = delayed_otp.ttl_boundary_sweep()
    timing = delayed_otp.timing_side_channel_demo()

    print("\n== friction_completion ==")
    friction = friction_completion.friction_completion()

    # --- assemble summary_table.md ---
    lines = []
    lines.append("# Research layer - results summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}Z")
    lines.append("")
    lines.append("All numbers below are produced by `research/experiments/run_all.py` against")
    lines.append("seeded, documented synthetic datasets (see `research/README.md` for what is real")
    lines.append("vs. synthetic). Regenerate with the same seed to reproduce bit-for-bit.")
    lines.append("")

    lines.append("## 1. RBA login-risk classifier (`classifier_eval_rba.py`)")
    lines.append("")
    lines.append("`dummy_most_frequent`/`dummy_stratified` are trivial baselines (see")
    lines.append("`research/common/metrics.py:dummy_baseline_rows`) - every learned model should be")
    lines.append("read against these, not against 0.5/chance.")
    lines.append("")
    lines.append("| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rba_metrics.to_dict("records"):
        lines.append(f"| {r['model']} | {_fmt(r['accuracy'])} | {_fmt(r['precision'])} | {_fmt(r['recall'])} | {_fmt(r['f1'])} | {_fmt(r['roc_auc'])} | {_fmt(r['pr_auc'])} |")
    lines.append("")

    lines.append("## 2. OTP compliance-violation early-warning classifier (`classifier_eval_compliance.py`)")
    lines.append("")
    lines.append("Predicts eventual control-violation pattern from a partial (30-100% revealed) view")
    lines.append("of each synthetic session's event timeline. `dummy_most_frequent`/`dummy_stratified`")
    lines.append("are trivial baselines - see note in section 1.")
    lines.append("")
    lines.append("| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in compliance_metrics.to_dict("records"):
        lines.append(f"| {r['model']} | {_fmt(r['accuracy'])} | {_fmt(r['precision'])} | {_fmt(r['recall'])} | {_fmt(r['f1'])} | {_fmt(r['roc_auc'])} | {_fmt(r['pr_auc'])} |")
    lines.append("")

    lines.append("## 3. Feature ablation (`ablation_features.py`)")
    lines.append("")
    lines.append("Mean ΔF1 / ΔROC-AUC vs. the full-feature baseline when one feature is removed,")
    lines.append(f"aggregated over {ablation_features.SEEDS.__len__()} independent CV-fold-shuffle seeds")
    lines.append("(best learned model shown; scope note: this seed variance is fold-assignment only,")
    lines.append("see module docstring). 95% CI is a Student-t interval across seeds; `Wilcoxon p` is")
    lines.append("the raw two-sided Wilcoxon signed-rank p-value against zero; `BH sig.` is whether the")
    lines.append("effect survives Benjamini-Hochberg correction across all")
    lines.append(f"{len(ablation_features.FEATURE_COLUMNS) * 2} simultaneous tests in this study.")
    lines.append("")
    best_model = compliance_metrics[~compliance_metrics["model"].str.startswith("dummy_")] \
        .sort_values("f1", ascending=False).iloc[0]["model"]
    sub = feat_ablation[feat_ablation["model"] == best_model].sort_values("mean_delta_f1")
    lines.append(f"Best model by F1: **{best_model}**")
    lines.append("")
    lines.append("| Ablated feature | F1 | Mean ΔF1 | ΔF1 95% CI | Wilcoxon p | BH sig. | ΔROC-AUC |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in sub.to_dict("records"):
        ci = f"[{_fmt(r['delta_f1_ci95_low'])}, {_fmt(r['delta_f1_ci95_high'])}]"
        lines.append(f"| {r['ablated_feature']} | {_fmt(r['f1'])} | {_fmt(r['mean_delta_f1'])} | {ci} | {_fmt(r['delta_f1_wilcoxon_p'])} | {r['delta_f1_bh_significant']} | {_fmt(r['mean_delta_roc_auc'])} |")
    lines.append("")

    lines.append("## 4. Control ablation (`ablation_controls.py`)")
    lines.append("")
    lines.append("Effect of disabling one deterministic predicate on the overall violation rate and")
    lines.append(f"on downstream classifier metrics, aggregated over {ablation_controls.SEEDS.__len__()}")
    lines.append("independent dataset-generation seeds (best model shown; this seed variance is true")
    lines.append("data-generation variance, stronger than section 3's fold-only variance). 95% CI is a")
    lines.append("Student-t interval across seeds; `Wilcoxon p` is the raw two-sided Wilcoxon")
    lines.append("signed-rank p-value; `BH sig.` is whether the effect survives Benjamini-Hochberg")
    lines.append(f"correction across all {len(ablation_controls.ALL_PREDICATES) * 2} simultaneous tests in this study.")
    lines.append("")
    sub2 = control_ablation[control_ablation["model"] == best_model].sort_values("mean_delta_violation_rate")
    lines.append("| Disabled control | Violation rate | Mean ΔViolation rate | 95% CI | Wilcoxon p | BH sig. | F1 | Mean ΔF1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in sub2.to_dict("records"):
        ci = f"[{_fmt(r['delta_violation_rate_ci95_low'])}, {_fmt(r['delta_violation_rate_ci95_high'])}]"
        lines.append(f"| {r['disabled_control']} | {_fmt(r['violation_rate'])} | {_fmt(r['mean_delta_violation_rate'])} | {ci} | {_fmt(r['delta_violation_rate_wilcoxon_p'])} | {r['delta_violation_rate_bh_significant']} | {_fmt(r['f1'])} | {_fmt(r['mean_delta_f1'])} |")
    lines.append("")

    lines.append("## 5. Delayed-OTP: TTL boundary sweep (`delayed_otp.py`)")
    lines.append("")
    lines.append(f"Empirical accept rate vs. verify-attempt delay offset from the TTL boundary,")
    lines.append(f"under +/-120ms simulated clock/network jitter, aggregated over {delayed_otp.SEEDS.__len__()}")
    lines.append("independent RNG seeds with a Student-t 95% CI per offset (see `delayed_otp_ttl_sweep.png`).")
    lines.append("")
    lines.append("| Offset from TTL (s) | Mean accept rate | 95% CI |")
    lines.append("|---|---|---|")
    for r in ttl_sweep.to_dict("records"):
        ci = f"[{_fmt(r['accept_rate_ci95_low'])}, {_fmt(r['accept_rate_ci95_high'])}]"
        lines.append(f"| {r['offset_from_ttl_s']:+.1f} | {_fmt(r['accept_rate'])} | {ci} |")
    lines.append("")

    lines.append("## 6. Delayed-OTP: timing side-channel statistical-power demonstration (`delayed_otp.py`)")
    lines.append("")
    lines.append("Simulated verification-latency distributions under two comparison strategies, re-run")
    lines.append(f"over {delayed_otp.SEEDS.__len__()} independent seeds and combined via Fisher's method (not a")
    lines.append("single seed's p-value). See the module docstring for the concrete static-code finding")
    lines.append("this models (`demo-app/lib/otpStore.js` uses `!==`, not `crypto.timingSafeEqual`) and for")
    lines.append("the honesty caveat on the assumed effect size.")
    lines.append("")
    lines.append("| Scenario | Mean latency (correct, ms) | Mean latency (incorrect, ms) | Welch combined p (Fisher) | Mann-Whitney combined p (Fisher) | Significant @0.01 |")
    lines.append("|---|---|---|---|---|---|")
    for r in timing.to_dict("records"):
        lines.append(f"| {r['scenario']} | {_fmt(r['mean_latency_correct_ms'])} | {_fmt(r['mean_latency_incorrect_ms'])} | {_fmt(r['welch_combined_p_fisher'])} | {_fmt(r['mannwhitney_combined_p_fisher'])} | {r['significant_at_0_01']} |")
    lines.append("")

    lines.append("## 7. OTP delivery friction / completion-rate proxy (`friction_completion.py`)")
    lines.append("")
    lines.append("Synthetic usability proxy - see the module docstring for the full data-generating")
    lines.append("process and honesty notes. `PATIENCE_LOGNORMAL_MEAN_LOG`/`PATIENCE_LOGNORMAL_SIGMA`")
    lines.append("are shared with the sibling `fido2-nist-mfa-research` repo's passkey version of this")
    lines.append("experiment for a fair cross-repo completion-rate comparison (see")
    lines.append("`research/results/cross_repo_summary.md` if present).")
    lines.append("")
    lines.append(f"Aggregated over {friction_completion.SEEDS.__len__()} independent simulation seeds. 95% CI is a")
    lines.append("Student-t interval across seeds.")
    lines.append("")
    lines.append("| Scenario | Mean completion rate | 95% CI | Mean abandonment rate | Mean time to complete (s) | 95% CI |")
    lines.append("|---|---|---|---|---|---|")
    for r in friction.to_dict("records"):
        rate_ci = f"[{_fmt(r['completion_rate_ci95_low'])}, {_fmt(r['completion_rate_ci95_high'])}]"
        time_ci = f"[{_fmt(r['time_to_complete_ci95_low'])}, {_fmt(r['time_to_complete_ci95_high'])}]"
        lines.append(f"| {r['scenario']} | {_fmt(r['mean_completion_rate'])} | {rate_ci} | {_fmt(r['mean_abandonment_rate'])} | {_fmt(r['mean_time_to_complete_s'])} | {time_ci} |")
    lines.append("")

    with open(os.path.join(RESULTS_DIR, "summary_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nwrote {os.path.join(RESULTS_DIR, 'summary_table.md')}")


if __name__ == "__main__":
    main()
