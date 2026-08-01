# Limited V1 Supported-Route Matrix

**Date:** 2026-08-01
**Scope manifest:** `config/release_scope_v1_20260801.json`
**Decision:** **NO-GO** — this is a candidate boundary, not a production support claim.

## Purpose

The first production release is deliberately narrower than the application’s
33 plan-owned scenario families. The manifest places 10 scenarios in four V1
candidate lanes and explicitly excludes the other 23. Every unlisted or
excluded matter must end in `source_gap_handoff`; it cannot fall through to a
freeform LLM answer.

The manifest cannot approve itself. `scripts/audit_release_scope.py` resolves
each representative query through the production router and MatterPlan, checks
the exact owner and fallback, audits every active must-cite authority against
the immutable registry and retrieval pack, and requires fingerprinted evidence
for:

- active-corpus provenance;
- uninjected natural retrieval recall@8; and
- independent legal review.

Run the inventory audit with `make audit-release-scope`, the exact live-corpus
projection gate with `make audit-release-scope-live`, and the no-source-pack
expanded-query recall gate with `make audit-release-scope-retrieval`. The strict
release gate is `make gate-release-scope`; it currently exits nonzero by design.

## Candidate lanes

| Lane | Candidate scenarios | Current boundary |
| --- | ---: | --- |
| FIR/arrest/custody safeguards | 4 | Arrest/custody disclosure, identity-only arrest, stolen-vehicle FIR refusal, seized-device return |
| Domestic/family safety | 1 | Immediate domestic-violence safety only |
| Cyber/financial harm | 2 | Loan-app contact harassment and investigating-authority bank hold |
| Consumer/banking grievance | 3 | Wrongful debit, insurance grievance, defective goods/refund |

Specialist bail/PMLA, tax/identity, state/local registry, property/succession,
non-safety matrimonial, environment/land, SC/ST specialist, employment,
Lok Adalat, and MGNREGA families are explicitly post-V1.

## Current machine audit

| Scenario | Registry contract | Live snapshot evidence | Status |
| --- | --- | --- | --- |
| Arrest/custody disclosure | Ready | Provenance pass; retrieval 3/3; legal review pending | Blocked |
| Police-seized device return | Ready | Provenance pass; retrieval 2/2; legal review pending | Blocked |
| Loan-app harassment | Ready | Provenance pass; retrieval 5/5; legal review pending | Blocked |
| Investigating-authority bank hold | Ready | Provenance pass; retrieval 5/5; legal review pending | Blocked |
| Wrongful bank debit | Ready | Provenance pass; retrieval 5/5; legal review pending | Blocked |
| LGBTQ identity-only arrest safeguard | CrPC/BNSS must-cite identity gap | Not eligible for evidence promotion | Blocked |
| Stolen-vehicle FIR refusal | BNS/IPC must-cite records not registry-owned | Not eligible for evidence promotion | Blocked |
| Immediate domestic-violence safety | PWDVA must-cite record not registry-owned | Not eligible for evidence promotion | Blocked |
| Insurance grievance | Insurance Ombudsman provisions not registry-owned | Not eligible for evidence promotion | Blocked |
| Defective goods/refund | Consumer Protection Act obligation remains provisional | Not eligible for evidence promotion | Blocked |

Current totals: **5/10 registry-contract ready, 5/5 registry-ready scenarios
passing the live provenance and natural-retrieval snapshots, and 0/10 launch
ready**. The live checks are not release evidence until rerun after candidate
freeze and attached to that exact candidate fingerprint.

## Promotion rule

A scenario may move from `candidate_blocked` to `approved` only when all of the
following are true on the same candidate fingerprint:

1. every active must-cite authority has a canonical registry key and authority
   ID, exact source-pack binding, and exact anchor binding;
2. the active corpus projection is provenance-verified for those authorities;
3. the route’s uninjected recall@8 report meets the manifest threshold;
4. independent legal review has an attached evidence artifact; and
5. the global release decision changes to `go` with the exact candidate SHA-256.

Changing a status string without those artifacts leaves the strict gate red.
