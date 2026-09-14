# PCI-DSS v4.0.1 → OTP MFA Control Map

**Status:** research-grade mapping, self-derived from trained knowledge of the published
standard text. Not a substitute for review against a licensed copy of PCI-DSS v4.0.1 before
any external/journal publication. Every control below states an explicit `confidence` level;
treat `medium`/`low` entries as hypotheses, not settled fact.

## Methodology

This repository's policy engine (`src/policy/engine.ts`) evaluates a fixed set of deterministic
predicates against captured lifecycle events and produces one of `PASS` / `FAIL` /
`INCONCLUSIVE` per control (see `src/policy/predicates.ts` and Algorithm 1 in the engine's
header comment). Each control in `control-profiles/otp-controls.yaml` is traced to a source
standard clause under one of three confidence bands:

| Band | Meaning |
|---|---|
| `true` / `high` | Requirement ID and operative bullet text recalled with high confidence from the PCI-DSS v4.0.1 published standard. Still recommend a final text diff against a licensed copy before external citation. |
| `false` / `medium` | PCI-DSS sets an **outcome-level** mandate (e.g. "MFA must resist replay") but does not itself specify **implementation mechanics** at OTP granularity (TTL seconds, session-binding semantics, supersession-on-reissue). The cited NIST SP 800-63B-4 section is the informative "how" reference. The section number for the **-4 revision specifically** (2025) is a medium-confidence recall - my training exposure to 800-63B **revision 3** (2017, widely cited) is far deeper than to the newer -4 draft/final text, so exact §-numbers for -4 are flagged, not asserted. |
| `false` / `low` | Mapped for research completeness only; verify independently before citing. |

No control in this profile is currently `low` confidence.

## Requirement 8 family - why it applies

PCI-DSS v4.0.1 Requirement 8, "Identify Users and Authenticate Access to System Components,"
is organized as: 8.2 (account management), 8.3 (strong authentication - factors, complexity),
8.4 (MFA is implemented), 8.5 (MFA systems are configured to prevent misuse), 8.6 (application/
system accounts). OTP delivered by email or SMS is one of the "something you have" factors
8.3.1 recognizes, and is almost always deployed to satisfy the MFA mandates in 8.4.1–8.4.3
(administrative non-console access to the CDE, all CDE access, and remote network access
originating outside the entity's network, respectively). Requirement 8.5.1 is the sub-clause
that constrains *how* an MFA system - OTP included - must behave once deployed; it is the
direct source for this repo's two `high`-confidence controls.

## Per-control citation rationale

### `otp.replay-resistance` - PCI-DSS 4.0.1 §8.5.1(a) - **high confidence**
Requirement 8.5.1 lists (a)–(d) as configuration mandates for any MFA system in CDE scope:
(a) the MFA system is not susceptible to replay attacks, (b) MFA systems cannot be bypassed by
any user (including administrative users) absent a documented, time-limited, management-
authorized exception, (c) at least two different types of authentication factors are used, and
(d) success of all authentication factors is required before access is granted. Bullet (a) maps
directly and unambiguously onto "a previously consumed OTP must not be redeemable a second
time" - this repo's `replayRejected` predicate.

### `otp.attempt-limit` - PCI-DSS 4.0.1 §8.3.4 - **high confidence**
Requirement 8.3.4 requires invalid authentication attempts to be limited by locking out the
user ID after no more than 10 attempts, with a lockout duration of at least 30 minutes or until
an administrator re-enables the account (or an equivalent dynamic-limiting control). This maps
directly onto `attemptLockoutEnforced`, which asserts a lockout event follows a bounded run of
rejected OTP submissions.

### `otp.bounded-validity` - NIST SP 800-63B-4 (informative) - **medium confidence**
PCI-DSS 4.0.1 does not specify a numeric validity window for a one-time authentication factor;
it only requires (via 8.5.1) that the MFA system as a whole resist misuse. The specific idea of
a short, bounded OTP validity window is a NIST SP 800-63B authenticator-lifecycle concept
(historically §5.1.3–5.1.4 authenticator families in rev. 3). The exact section number in the
**-4** revision is not independently verified here - flagged medium, not asserted.

### `otp.session-binding` - NIST SP 800-63B-4 (informative) - **medium confidence**
Binding an issued OTP to the session/subject that requested it is the practical mechanism by
which PCI-DSS 8.5.1(d)'s "success of all authentication factors is required" is achieved without
a factor becoming a bearer token usable by an unrelated session. PCI-DSS itself does not name
"session binding" as a control; NIST SP 800-63B's authenticator-binding language is the
informative source, again with un-verified exact section numbering for the -4 revision.

### `otp.supersession` - NIST SP 800-63B-4 (informative) - **medium confidence**
Same rationale as session-binding: PCI-DSS does not specify that reissuing an OTP must
invalidate the prior one, but a single-active-secret-per-channel model is standard practice
attributed to NIST SP 800-63B authenticator lifecycle guidance.

### `otp.channel-restriction` - NIST SP 800-63B-4 (informative), non-mandatory - **medium confidence**
PCI-DSS v4.0.1 is delivery-channel agnostic - it does not restrict or prohibit SMS-delivered
OTP. The caution around SMS/PSTN-delivered out-of-band codes as a "restricted authenticator"
originates in NIST SP 800-63B (rev. 3 popularized the "SHOULD NOT" language for PSTN-based
OOB). This control is marked `mandatory: false` in the profile precisely because it is not a
PCI-DSS obligation - it is recorded for research/comparative purposes (email vs. SMS channel
risk) rather than treated as a pass/fail compliance gate.

## Supporting audit-trail requirements (not modeled as a standalone control)

PCI-DSS 4.0.1 Requirement 10.2.1 enumerates the event classes an audit log must capture.
Two sub-bullets are directly relevant to why this repo's evidence-bundle-as-code approach
(`src/evidence/seal.ts`) is itself compliance-relevant, independent of any single OTP control:

- **10.2.1.4** - invalid logical access attempts are logged.
- **10.2.1.5** - changes to identification and authentication credentials are logged.

These are cited here as *supporting context* for the evidence-sealing design, not encoded as a
`control_id` in the YAML profile, since the demo app's event log is a synthetic research
harness, not a production audit-log implementation being asserted compliant.
