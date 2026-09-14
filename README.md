# otp-lifecycle-engine

PCI DSS v4.0.1 / NIST SP 800-63B-4 compliance-as-code engine for email and SMS OTP MFA,
combining a deterministic lifecycle-validation engine with a companion statistical/ML
research layer.

1. A deterministic compliance-as-code engine (`src/policy/`) that models OTP MFA as an
   explicit lifecycle (generated, valid, then expired, consumed, superseded, or locked) and
   evaluates a real running demo application against cited PCI-DSS v4.0.1 controls, proven via
   9 passing Playwright-BDD end-to-end scenarios (`features/`).
2. A statistical/ML research layer (`research/`) that asks a complementary question: how well
   can a classifier predict eventual control-violation behaviour from partial signal, how
   sensitive is that performance to which features or controls are present (ablation), and what
   does a realistic delayed or jittered TTL boundary, or a naive timing side-channel, look like
   under statistical testing?

It's a research artifact demonstrating a compliance-as-code methodology, with an accompanying 
synthetic-data ML evaluation layer scoped as honestly as I could manage.
See [`compliance/pci-dss-v4-otp-control-map.md`](compliance/pci-dss-v4-otp-control-map.md)
for the full citation rationale and stated confidence levels, and
[`research/README.md`](research/README.md) for what's real versus synthetic in each dataset.

## Repository layout

```
demo-app/                 Express app under test - OTP-only login lifecycle (email + SMS)
src/policy/                Deterministic control predicates + evaluation engine
control-profiles/          otp-controls.yaml - 6 controls, each cited against PCI-DSS v4.0.1 / NIST SP 800-63B-4
features/, steps/, support/  Playwright-BDD test suite (9 scenarios, all passing)
compliance/                 Citation-rationale document (methodology, per-control reasoning, limitations)
research/                   Python statistical/ML layer (datasets, classifiers, ablations, delayed-OTP analysis)
research/results/            Generated CSVs, ROC PNGs, and summary_table.md, all reproducible with seed 42
```

## Quick start

Tested with Node 20.14 and Python 3.12. Other versions may work but haven't been checked.

### 1. Compliance-as-code test suite (TypeScript / Playwright-BDD)

```bash
npm install
npx playwright install chromium
npx bddgen
npx playwright test --project=chromium --reporter=list
```

Expected: 9/9 passed (5 email-OTP scenarios, 4 SMS-OTP scenarios), each tagged with the control
ID it exercises (e.g. `@control:otp.replay-resistance`).

By default the test suite runs against `demo-app/lib/channels/localSimulator.js`, a local
in-memory stand-in for OTP delivery so the suite is reproducible without any external account.
To run the same scenarios against real, externally delivered email and SMS messages (the
production-grade pattern this repository formalizes), copy `.env.example` to `.env`, fill in a
[Mailosaur](https://mailosaur.com) API key and server IDs, and set the channel router
(`demo-app/lib/channels/channelRouter.js`) to use `mailosaurAdapter.js`. Neither the lifecycle
engine, the assertions, nor the compliance mapping change between the two modes. Only the
delivery capture adapter does.

### 2. Statistical research layer (Python)

```bash
pip install -r research/requirements.txt
python research/experiments/run_all.py
```

Regenerates every dataset and result under `research/results/` from the fixed seed (`42`).
Re-running with the same dependency versions (see `research/requirements.txt`) reproduces the
same numbers on that seed. Variance across multiple seeds is reported separately in each
`*_per_seed.csv` file; the point estimates below are seed 42 only and should be read alongside
that variance, not treated as a single definitive number.

## Experiments results (seed 42)

All rows below are computed on synthetic, seeded data unless noted otherwise. See
[Limitations](#limitations--threats-to-validity) before citing any of them.

| Experiment | Headline metric (seed 42) | Data |
|---|---|---|
| RBA login-risk classifier | Best F1 0.631 (logistic regression), ROC-AUC 0.791. Intentionally a non-trivial, noisy task | synthetic |
| OTP compliance-violation early-warning classifier | Best F1 0.970, ROC-AUC 0.994 (gradient boosting), predicting eventual control violation from a partial (30-100%) session view | synthetic |
| Feature ablation | Removing `any_cross_session_so_far` or `n_valid_so_far` costs the most F1 (-0.12 / -0.08). Most individual features are near-redundant | synthetic |
| Control ablation | Disabling any single deterministic control drops the overall violation rate by about 9-10 percentage points. Disabling `replayRejected` specifically makes the remaining violation types easier to classify (F1 rises to 0.999), which I'm flagging as a real, explainable finding rather than smoothing over | synthetic |
| Delayed-OTP TTL boundary sweep | Accept rate transitions from roughly 100% to 0% within about ±0.5s of the TTL boundary, under ±120ms simulated jitter | synthetic |
| Delayed-OTP timing side-channel | Under a simulated constant-time comparison, Welch's t-test doesn't reach significance at α=0.01. Under a simulated naive early-exit comparison (motivated by the real `!==` comparison in `demo-app/lib/otpStore.js`), both Welch's t-test and Mann-Whitney U reject at p<0.001 | synthetic, motivated by a static code finding |
| OTP delivery friction/completion-rate proxy | `sms_baseline` completion 0.955 vs. `email_degraded` 0.159 | synthetic usability proxy |
| Risk-adaptive step-up policy (OTP vs. passkey vs. adaptive) | `risk_adaptive` is not Pareto-dominant over `always_otp`. It trades a small security regression (mean attack-success 0.380 vs. 0.350) for a large usability gain (mean legitimate-abandonment 0.018 vs. 0.045). Kept in as a genuine finding rather than tuned away | synthetic simulation |

The only empirically validated, non-synthetic claim in this repository is that the demo
application passes 9/9 Playwright-BDD scenarios encoding the 6 controls in
`control-profiles/otp-controls.yaml`, against both delivery-channel adapters.

See [`research/results/cross_repo_summary.md`](research/results/cross_repo_summary.md) for
side-by-side comparison notes.

## Limitations

- All classifier, ablation, delayed-OTP, and friction numbers above are computed on synthetic,
  seeded, documented data. See `research/README.md` for the exact generative model behind each
  dataset. None of them measure live network behaviour or a production system, and none should
  be read as evidence about real attacker or user populations.
- The timing side-channel analysis is a statistical-methodology demonstration. It's motivated by
  a genuine static-code finding (`demo-app/lib/otpStore.js` compares codes with `!==`, not
  `crypto.timingSafeEqual`), but it isn't a live measurement over the real HTTP or network stack.
- PCI-DSS v4.0.1 and NIST SP 800-63B-4 clause citations in `control-profiles/otp-controls.yaml`
  and `compliance/pci-dss-v4-otp-control-map.md` are graded high, medium, or low confidence, and
  were drafted from training-data recall rather than a line-by-line diff against a licensed copy
  of the published standard. If you're citing specific clause numbers from this repository in
  downstream work, verify them independently against the current standard text first.
  `compliance/pci-dss-v4-otp-control-map.md` documents the confidence-grading methodology per
  control, along with its known limitations.
- Reproducibility ("bit-for-bit identical") is scoped to a fixed seed (42) and the dependency
  versions pinned in `research/requirements.txt` and `package-lock.json`. It isn't a claim of
  determinism across arbitrary environments or library versions.
- This repository hasn't undergone independent third-party audit or a formal PCI-DSS assessment.
  No human-subjects or personally identifiable data is used anywhere in the demo app, datasets,
  or evaluation.

## Related work (2024-2026)

- Berladskyy & Aßmuth, "An Analysis of Attack Vectors Against FIDO2 Authentication," CROSS-SEC 2026 (peer-reviewed; arXiv:2604.20826)
- Chen, "Quantum-Safe Web Service Architecture Using Time-Based One-Time Passwords" (preprint; arXiv:2608.16961, Aug 2026)
- Tran et al., "The Passwordless Authentication with Passkey Technology from an Implementation Perspective" (preprint; arXiv:2508.11928, Aug 2025)
- Mitra et al., "SSHafe: A Real-Time SSH Brute Force Attack Detection and Novel Credential Rotation Standard" (preprint; arXiv:2608.09066, Aug 2026)
- Amft et al., "'We've Disabled MFA for You': An Evaluation of the Security and Usability of Multi-Factor Authentication Recovery Deployments" (preprint; arXiv:2306.09708)
