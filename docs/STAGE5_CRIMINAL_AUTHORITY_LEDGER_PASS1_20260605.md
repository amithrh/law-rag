# Stage 5 Criminal Authority Ledger Pass 1 - 2026-06-05

## Verdict

This is progress, not production readiness.

The first criminal-procedure authority-ledger slice converts several Stage 5
generic criminal answers into variant-specific, cited procedural answers. It
does not close the production gate. The remaining failures show that the next
blocker is source/corpus coverage and citation repair for state/special-law
gaps, plus undertrial/custody compensation variants.

## Implemented

- Added `apps/api/authority_ledger.py`.
- Added data-backed criminal contracts for:
  - regular bail for first-time accused,
  - bail granted but surety unaffordable,
  - anticipatory-bail refiling after rejection,
  - anticipatory-bail duration / threat after grant,
  - default-bail / no-charge-sheet custody calculation including MCOCA caveat,
  - PMLA/ED pre-arrest bail,
  - interim bail between regular-bail hearings,
  - IT Act 67 complaint over a non-nude selfie,
  - simple assault accusation after domestic conflict.
- Wired the criminal authority ledger into `_grounded_template_lines` before
  the generic criminal-defence floor.
- Strengthened existing templates for:
  - juvenile in adult jail -> transfer/removal to JJ Board / observation-home
    route,
  - pregnancy/medical interim bail -> medical status report, hospital
    examination, DLSA/court motion,
  - NDPS heroin quantity -> seizure memo, lab/FSL, small/intermediate/commercial
    classification, Section 37, Special NDPS Court/High Court/Supreme Court
    route.
- Added regression coverage in `apps/api/tests/test_endpoints.py`.

## Validation

Syntax:

```bash
PYTHONPATH=. .venv/bin/python -m py_compile apps/api/authority_ledger.py apps/api/main.py
```

Result: passed.

Focused endpoint tests:

```bash
PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_endpoints.py -q -k "stage5_criminal_authority_ledger or stage5_criminal_existing_templates or criminal_defence_floor or juvenile or ndps or pregnant_undertrial or medical_bail or uapa_default_bail or anticipatory"
```

Initial result: `8 passed, 179 deselected`.

Subagent review then found two P1 issues:

- PMLA contract used a bare `ed ` substring trigger.
- Contracts could fire from any neighboring source because controlling sources
  were not required per variant.

Fixes applied:

- Removed the bare `ed ` PMLA trigger.
- Added `required_source_keys_any` to each criminal contract.
- Added negative tests for:
  - PMLA query without PMLA source,
  - regular-bail query with only IPC/theft source,
  - non-PMLA anticipatory-bail query with a stray PMLA source.

Post-review focused endpoint tests:

```bash
PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_endpoints.py -q -k "stage5_criminal_authority_ledger or stage5_criminal_existing_templates or criminal_defence_floor or juvenile or ndps or pregnant_undertrial or medical_bail or uapa_default_bail or anticipatory"
```

Result: `9 passed, 179 deselected`.

Focused 34-row Stage 5 criminal-failure slice before the final verifier-facing
patch:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8038 \
  --queries-dir /tmp/law_rag_20260605_criminal_pass1/prompts \
  --limit 34 \
  --seed 2026060501 \
  --out /tmp/law_rag_20260605_criminal_pass1b/out/timed_criminal_stage5_failures_pass1b.jsonl \
  --report /tmp/law_rag_20260605_criminal_pass1b/out/timed_criminal_stage5_failures_pass1b.md
```

Product gate:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_common_user_gate.py \
  /tmp/law_rag_20260605_criminal_pass1b/out/timed_criminal_stage5_failures_pass1b.jsonl \
  --prompts /tmp/law_rag_20260605_criminal_pass1/prompts \
  --report /tmp/law_rag_20260605_criminal_pass1b/out/product_gate_criminal_stage5_failures_pass1b.md \
  --failures-jsonl /tmp/law_rag_20260605_criminal_pass1b/out/product_gate_criminal_stage5_failures_pass1b_failures.jsonl \
  --allow-fail
```

Result:

- product pass: `13/34` (`38.2%`)
- critical pass: `13/31` (`41.9%`)
- route match: `34/34` (`100%`)
- expected Act cited: `24/32` (`75.0%`)
- safety hard fails: `0`
- refusals/errors: `0`
- p50 latency: `6.1s`
- p90 latency: `6.9s`

Important interpretation: this slice contained only known Stage 5 failures, so
`13/34` means 13 failures were converted to product passes. It is not a
production gate pass.

Micro live check after the final verifier-facing patch:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8038 \
  --queries-dir /tmp/law_rag_20260605_criminal_micro/prompts \
  --limit 2 \
  --seed 2026060502 \
  --out /tmp/law_rag_20260605_criminal_micro/out/timed_micro.jsonl \
  --report /tmp/law_rag_20260605_criminal_micro/out/timed_micro.md
```

Micro product gate:

- product pass: `2/2`
- expected Act cited: `2/2`
- critical pass: `2/2`
- product failures: `0`

## Remaining Failures In This Slice

The 34-row slice still fails mainly on:

- false-charge / false-FIR variants,
- source gaps for cattle/buffalo transport and state witch-branding / tonhi,
- NDPS personal-use classification such as bhang-lassi and MDMA quantity,
- undertrial delay / legal-aid replacement,
- custody compensation after acquittal,
- state/tribal land transfer and mutation source coverage.

Failure counts from the focused slice:

- `relevance_not_ok`: `9`
- `expected_act_not_cited`: `8`
- `expected_act_missing`: `6`
- `zero_ok_legal_sentences`: `5` before final micro patch
- `missing_scenario_terms`: `2`

## Next Required Stage

Do not add more broad criminal prose. The next stage should implement the
reviewer-recommended source/corpus ledger:

1. Classify every remaining required-source miss as:
   - `retrieved_not_cited`,
   - `retrieval_missed`,
   - `corpus_gap`,
   - `wrong_anchor`.
2. Add honest corpus-gap language when state/special law is not indexed.
3. Patch source packs for repeated critical gaps only:
   - cattle/buffalo transport state law,
   - Chhattisgarh/Jharkhand/Odisha witch-branding and tribal land variants,
   - NDPS quantity/personal-use classification anchors,
   - undertrial legal-aid / custody-delay routes.
4. Re-run the same 34-row focused slice.
5. Only after the criminal slice crosses `>=95%` product pass and `100%`
   critical pass should this move to a fresh 500 run.
