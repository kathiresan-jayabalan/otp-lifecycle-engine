# otp-lifecycle-engine

PCI DSS v4.0.1 / NIST SP 800-63B-4 compliance-as-code engine for email & SMS OTP MFA,
combining a deterministic lifecycle-validation engine with a companion statistical/ML
research layer.

1. A **deterministic compliance-as-code engine** (`src/policy/`) that models OTP MFA as an
   explicit lifecycle (generated → valid → expired / consumed / superseded / locked) and
   evaluates a real running demo application against cited PCI-DSS v4.0.1 controls, proven via
   9 passing Playwright-BDD end-to-end scenarios (`features/`).
2. A **statistical/ML research layer** (`research/`) that asks a complementary question: how
   well can a classifier predict eventual control-violation behaviour from partial signal, how
   sensitive is that performance to which features or controls are present (ablation), and
   what does a realistic delayed/jittered TTL boundary or a naive timing side-channel look like
   under statistical testing?

This is **not a certified PCI-DSS assessment**. It is a research artifact demonstrating a
compliance-as-code methodology with an accompanying, honestly-scoped, synthetic-data ML
evaluation layer. See [`compliance/pci-dss-v4-otp-control-map.md`](compliance/pci-dss-v4-otp-control-map.md)
for the full citation rationale and stated confidence levels, and
[`research/README.md`](research/README.md) for what is real vs. synthetic in every dataset.

## Repository layout

```
demo-app/                 Express app under test - OTP-only login lifecycle (email + SMS)
src/policy/                Deterministic control predicates + evaluation engine
control-profiles/          otp-controls.yaml - 6 controls, each cited against PCI-DSS v4.0.1 / NIST SP 800-63B-4
features/, steps/, support/  Playwright-BDD test suite (9 scenarios, all passing)
compliance/                 Citation-rationale document (methodology, per-control reasoning, limitations)
research/                   Python statistical/ML layer (datasets, classifiers, ablations, delayed-OTP analysis)
research/results/            Generated CSVs, ROC PNGs, and summary_table.md - all reproducible with seed 42
```

## Quick start

Tested with **Node 20.14 / Python 3.12**. Other versions may work but are unverified.

### 1. Compliance-as-code test suite (TypeScript / Playwright-BDD)

```bash
npm install
npx playwright install chromium
npx bddgen
npx playwright test --project=chromium --reporter=list
```

Expected: **9/9 passed** (5 email-OTP scenarios, 4 SMS-OTP scenarios), each tagged with the
control ID it exercises (e.g. `@control:otp.replay-resistance`).

By default the test suite runs against `demo-app/lib/channels/localSimulator.js`, a local
in-memory stand-in for OTP delivery so the suite is reproducible without any external account.
To run the same scenarios against **real, externally delivered** email and SMS messages (the
production-grade pattern this repository formalizes), copy `.env.example` to `.env`, fill in a
[Mailosaur](https://mailosaur.com) API key and server IDs, and set the channel router
(`demo-app/lib/channels/channelRouter.js`) to use `mailosaurAdapter.js`. The lifecycle engine,
assertions, and compliance mapping do not change between the two modes — only the delivery
capture adapter does.

### 2. Statistical research layer (Python)

```bash
pip install -r research/requirements.txt
python research/experiments/run_all.py
```

Regenerates every dataset and result under `research/results/` from the fixed seed (`42`).
Re-running with the same dependency versions (see `research/requirements.txt`) produces
bit-for-bit identical numbers on that seed. Per-seed variance across multiple seeds is reported
separately in each `*_per_seed.csv` file — the point estimates below are seed 42 only and should
be read alongside that variance, not as a single definitive number.

## Headline results (seed 42 — see [`research/results/summary_table.md`](research/results/summary_table.md) for full tables and [`research/results/*_per_seed.csv`](research/results/) for cross-seed variance)

All rows below are computed on **synthetic, seeded data** unless noted otherwise — see
[Limitations](#limitations--threats-to-validity).

| Experiment | Headline metric (seed 42) | Data |
|---|---|---|
| RBA login-risk classifier | Best F1 0.631 (logistic regression), ROC-AUC 0.791 — intentionally non-trivial, noisy task | synthetic |
| OTP compliance-violation early-warning classifier | Best F1 0.970, ROC-AUC 0.994 (gradient boosting) predicting eventual control violation from a partial (30–100%) session view | synthetic |
| Feature ablation | Removing `any_cross_session_so_far` or `n_valid_so_far` costs the most F1 (-0.12 / -0.08); most individual features are near-redundant | synthetic |
| Control ablation | Disabling any single deterministic control drops the overall violation rate by ~9–10 percentage points; disabling `replayRejected` specifically makes the *remaining* violation types easier to classify (F1 rises to 0.999) — flagged as a real, explainable finding, not suppressed | synthetic |
| Delayed-OTP TTL boundary sweep | Accept rate transitions sharply from ~100% to ~0% within roughly ±0.5s of the TTL boundary under ±120ms simulated jitter | synthetic |
| Delayed-OTP timing side-channel | Under a simulated constant-time comparison, Welch's t-test does not reach significance at α=0.01; under a simulated naive early-exit comparison (motivated by the real `!==` comparison in `demo-app/lib/otpStore.js`), both Welch's t-test and Mann-Whitney U reject at p<0.001 | synthetic, static-finding-motivated |
| OTP delivery friction/completion-rate proxy | `sms_baseline` completion 0.955 vs. `email_degraded` 0.159 | synthetic usability proxy |
| Risk-adaptive step-up policy (OTP vs. passkey vs. adaptive) | `risk_adaptive` is **not** Pareto-dominant over `always_otp`: it trades a small security regression (mean attack-success 0.380 vs. 0.350) for a large usability gain (mean legitimate-abandonment 0.018 vs. 0.045) — disclosed as a genuine finding, not tuned away | synthetic simulation |

The **only** empirically validated (non-synthetic) claim in this repository is that the demo
application passes 9/9 Playwright-BDD scenarios encoding the 6 controls in
`control-profiles/otp-controls.yaml`, against both delivery-channel adapters.

See [`research/results/cross_repo_summary.md`](research/results/cross_repo_summary.md) for
side-by-side comparison notes.

## Limitations & threats to validity

- **All classifier/ablation/delayed-OTP/friction numbers above are computed on synthetic,
  seeded, documented data** — see `research/README.md` for the exact generative model behind
  every dataset. None are measurements of live network behaviour or a production system, and
  none should be read as evidence about real-world attacker or user populations.
- The timing side-channel analysis is a **statistical-methodology demonstration**, motivated by
  a genuine static-code finding (`demo-app/lib/otpStore.js` compares codes with `!==`, not
  `crypto.timingSafeEqual`), not a live measurement over the real HTTP/network stack.
- **PCI-DSS v4.0.1 and NIST SP 800-63B-4 clause citations in `control-profiles/otp-controls.yaml`
  and `compliance/pci-dss-v4-otp-control-map.md` are graded `high`/`medium`/`low` confidence and
  were derived from training-data recall, not a line-by-line diff against a licensed copy of the
  published standard at the time of writing.** Readers citing specific clause numbers from this
  repository in downstream work should independently verify them against the current published
  standard text before relying on them; `compliance/pci-dss-v4-otp-control-map.md` documents the
  known-limitation and confidence-grading methodology per control.
- Reproducibility ("bit-for-bit identical") is scoped to a fixed seed (`42`) and the dependency
  versions pinned in `research/requirements.txt` / `package-lock.json`; it is not a claim of
  determinism across arbitrary environments or library versions.
- This repository has not undergone independent third-party audit or formal PCI-DSS assessment,
  and no human-subjects or personally identifiable data is used anywhere in the demo app,
  datasets, or evaluation.

## Related work (2024–2026)

- Berladskyy & Aßmuth, "An Analysis of Attack Vectors Against FIDO2 Authentication," CROSS-SEC 2026 (peer-reviewed; arXiv:2604.20826)
- Chen, "Quantum-Safe Web Service Architecture Using Time-Based One-Time Passwords" (preprint; arXiv:2608.16961, Aug 2026)
- Tran et al., "The Passwordless Authentication with Passkey Technology from an Implementation Perspective" (preprint; arXiv:2508.11928, Aug 2025)
- Mitra et al., "SSHafe: A Real-Time SSH Brute Force Attack Detection and Novel Credential Rotation Standard" (preprint; arXiv:2608.09066, Aug 2026)
- Amft et al., "'We've Disabled MFA for You': An Evaluation of the Security and Usability of Multi-Factor Authentication Recovery Deployments" (preprint; arXiv:2306.09708)
