# Stage32.2 blocker follow-up

Date: 2026-05-28
Branch: `codex/latency-hardening`
Worktree: `/Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc`

## Scope

Closed the Stage32.2 reviewer blockers:

- Security-cheque drawer defence must not answer as if the drawer/payee should file a Section 138 complaint.
- Education-loan denial must not be routed through generic RTE/school-rights sources.
- Live smoke additionally found a juvenile intake phrase miss: `adult lockup` for a minor was not treated like `adult jail`.

## Changes

- `apps/api/main.py`
  - Added deterministic security-cheque drawer-defence answer path.
  - The answer frames Section 138 as payee/holder notice to the drawer, then gives drawer-defence next steps.

- `apps/api/matter_router.py`
  - Added `education_loan_denial` routing separate from `education_rights`.
  - Added security-cheque and senior-maintenance cheque actor-sensitive routes.
  - Added `adult lockup` as juvenile/adult-custody phrasing.

- `apps/api/source_packs.py`
  - `education_loan_denial` now uses RBI Integrated Ombudsman + Consumer Protection sources only.
  - RTE remains reserved for school/RTE access facts.

- `scripts/eval_timed_100.py`
  - Conditional expected-key logic maps bank education-loan prompts away from RTE and toward Banking Ombudsman.

- Tests added/updated in:
  - `apps/api/tests/test_endpoints.py`
  - `apps/api/tests/test_matter_router.py`
  - `apps/api/tests/test_source_packs.py`
  - `apps/api/tests/test_eval_timed_100.py`

## Verification

Focused blocker regressions:

```text
5 passed, 1 warning
```

Adult-lockup focused regressions:

```text
3 passed, 1 warning
```

Broad API regression after all fixes:

```text
403 passed, 8 warnings
```

Live seven-prompt smoke against `http://127.0.0.1:8012`:

```text
hard_safety=0/7
custom_blocker_fail=0/7
```

| prompt class | observed route | hard safety | blocker check |
| --- | --- | ---: | --- |
| juvenile adult lockup | `criminal_defence_bail` | 0 | route repaired |
| security cheque drawer | `banking_credit_dispute` / `security_cheque_defence` | 0 | drawer-safe, no payee complaint framing |
| FRA bamboo/patta | `tribal_caste_atrocity` | 0 | clean |
| acid threat | `police_fir` | 0 | clean |
| senior maintenance + cheque | `senior_citizen` | 0 | clean |
| education loan denial | `education_loan_denial` | 0 | no RTE leak |
| pregnant undertrial medical bail | `criminal_defence_bail` | 0 | clean |

## Reviewer Follow-Up

Schrodinger accepted the education-loan closure.

Fermat initially blocked the cheque fix because the deterministic drawer-defence template was gated by a narrower phrase list than the router. Follow-up fix:

- `apps/api/main.py` now triggers the security-cheque template whenever `route.action_pack.id == "security_cheque_defence"`.
- `apps/api/tests/test_endpoints.py` now covers blank-cheque and landlord/threatening-138 variants.

Focused closure checks:

```text
6 passed, 1 warning
```

Live closure smoke for Fermat's three risky phrasings:

| prompt | route | cited NI Act | hard safety | custom failure |
| --- | --- | ---: | ---: | ---: |
| blank cheque to landlord as security + notice under 138 | `banking_credit_dispute/security_cheque_defence` | 1 | 0 | 0 |
| landlord took cheque as security + threatening 138 | `banking_credit_dispute/security_cheque_defence` | 1 | 0 | 0 |
| rent security cheque deposited after vacating | `banking_credit_dispute/security_cheque_defence` | 1 | 0 | 0 |

## Remaining Metric Gaps

The smoke still shows citation-metric misses on broad expected hints, especially when the expected hint includes multiple authorities but the answer cites only the primary procedural authority. This is not a new hard-safety blocker from Stage32.2, but it is the next production gate to improve before claiming readiness:

- juvenile: route and answer are correct, but broad expected hint includes JJ procedure + Article 21.
- education loan: Banking Ombudsman route is correct, but broad expected hint may also include Consumer Protection.
- medical bail: answer hits primary bail route, but broad expected hint may also include prison/Article 21 materials.

Next stage should focus on deterministic multi-authority citation coverage and expected-source calibration.
