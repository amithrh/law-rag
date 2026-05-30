# Stage32.3 citation and authority repair

Date: 2026-05-28
Branch: `codex/latency-hardening`
Worktree: `/Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc`

## Scope

Stage32.2 closed the route-safety blockers. Stage32.3 targets the next production gap: answers were often legally safe but failed expected-authority cited coverage because companion authorities were retrieved but not cited.

## Changes

- Added deterministic citation templates in `apps/api/main.py` for:
  - private complaint before Magistrate / police inaction,
  - caste-atrocity FIR refusal,
  - domestic acid/chemical threat,
  - khap/honour threat,
  - cyber blackmail/extortion/private-image abuse,
  - senior parent maintenance + bounced cheque,
  - education loan denial,
  - undertrial legal-aid failure,
  - nationality/origin police-threat framing.

- Updated routing/source support:
  - `apps/api/matter_router.py`: private Magistrate complaint now routes to `court_procedure`.
  - `apps/api/source_packs.py`: improved BNSS private-complaint packs, BNS threat anchors, IT Act cyber anchors, and Constitution Article 21 support for identity/police-threat facts.
  - `apps/api/query_expand.py`: private Magistrate complaint expansion is now BNSS-first with CrPC retained as the companion legacy procedure variant.

- Added regression tests in:
  - `apps/api/tests/test_endpoints.py`
  - `apps/api/tests/test_matter_router.py`
  - `apps/api/tests/test_source_packs.py`
  - existing query-expansion regression remains green.

## Verification

Focused citation/router/source tests:

```text
6 passed, 1 warning
4 passed, 1 warning
1 passed, 1 warning
```

Broad API regression:

```text
415 passed, 8 warnings
```

Live old hard-failure probe, same 15 prompt classes from the Stage32 100-run failure table:

```text
hard=0/15
act_miss=0/15
cited_miss=0/15
quality={}
relevance={'partial': 10, 'ok': 5}
```

| prompt class | route | expected act | cited expected act | hard safety | quality flags |
| --- | --- | ---: | ---: | ---: | --- |
| juvenile adult jail | `criminal_defence_bail` | 1 | 1 | 0 | none |
| security cheque drawer | `banking_credit_dispute` | 1 | 1 | 0 | none |
| caste FIR refusal | `police_fir` | 1 | 1 | 0 | none |
| undertrial lawyer absent | `undertrial_review_release` | 1 | 1 | 0 | none |
| FRA bamboo/patta | `tribal_caste_atrocity` | 1 | 1 | 0 | none |
| nude leak | `cyber_fraud_or_harassment` | 1 | 1 | 0 | none |
| dating-app blackmail screenshots | `cyber_fraud_or_harassment` | 1 | 1 | 0 | none |
| nationality/origin police threat | `criminal_general` | 1 | 1 | 0 | none |
| domestic acid threat | `police_fir` | 1 | 1 | 0 | none |
| senior parent bounced cheque | `senior_citizen` | 1 | 1 | 0 | none |
| education loan denial | `education_loan_denial` | 1 | 1 | 0 | none |
| pregnant undertrial medical bail | `criminal_defence_bail` | 1 | 1 | 0 | none |
| khap/honour threat | `police_fir` | 1 | 1 | 0 | none |
| private complaint before Magistrate | `court_procedure` | 1 | 1 | 0 | none |
| dating-app extortion/took phone | `cyber_fraud_or_harassment` | 1 | 1 | 0 | none |

## Remaining Risk

This stage is validated on the old hard-failure slice, not a fresh 100-prompt population. The next gate must be a fresh final-100 eval to verify whether the improvements generalize and whether median/p90 latency remain below the product target.

## Review Closure

Fermat blocked the first Stage32.3 review with a P1 citation-integrity issue: several templates bundled multiple forum/action tracks under whichever companion source happened to be present.

Closure fix:

- Split each next-step line into source-specific actions.
- If a companion authority is absent, the action for that forum/track is not emitted.
- Added single-source negative fixtures so missing BNSS/PWDVA/RBI/Senior/LSA sources cannot be silently replaced by another citation.

Closure tests:

```text
8 passed, 1 warning
415 passed, 8 warnings
```

Closure live probe after restart:

```text
hard=0/15
act_miss=0/15
cited_miss=0/15
quality={}
relevance={'partial': 10, 'ok': 5}
```

Second closure fix:

- Fermat found one remaining BNS-only khap/honour threat branch that still bundled written-police-complaint escalation under a BNS-only citation.
- `_police_threat_template_lines()` now splits BNS threat comparison, BNSS FIR/refusal procedure, and BNSS court-complaint route into separate action lines.
- Added the exact BNS-only honour-threat negative fixture to `test_single_source_templates_do_not_bundle_missing_forums`.

Second closure verification:

```text
2 passed, 1 warning
honour live smoke: relevance=ok, act=True, cited=True, hard=False, flags=[]
415 passed, 8 warnings
```

Third closure fix:

- Schrodinger found that the caste-FIR template treated BNSS 173 as the Magistrate-investigation authority.
- `_caste_fir_refusal_template_lines()` now separates:
  - SC/ST POA offence matching,
  - BNSS 173 FIR/refusal procedure,
  - BNSS 175 or CrPC 156 Magistrate investigation-order authority.
- `source_packs.py` now adds a focused `bnss_2023_magistrate_investigation` source pack for SC/ST FIR-refusal prompts.
- Added a BNSS-173-only negative fixture asserting no Magistrate-investigation wording.

Third closure verification:

```text
3 passed, 1 warning
caste FIR live smoke: relevance=partial, act=True, cited=True, hard=False, flags=[]
415 passed, 8 warnings
```

Fourth closure fix:

- Schrodinger found BNSS 216 was still too broad for khap/honour threats because that section is witness/false-evidence specific, not a general honour-threat complaint route.
- `_police_threat_template_lines()` now considers BNSS 216 only for explicit witness/false-evidence threat facts.
- Added a BNSS-216-only honour-threat negative fixture.
- Added `bnss_2023_fir_information` source pack for honour/khap threat prompts so the live path cites BNSS 173 for police-information/FIR-refusal procedure instead of falling back to BNSS 216.

Fourth closure verification:

```text
2 passed, 1 warning
honour live smoke: relevance=ok, act=True, cited=True, hard=False, flags=[]
416 passed, 8 warnings
```
