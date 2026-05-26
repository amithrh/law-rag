# Codex Source-Pack Eval — 2026-05-26

Branch: `codex/latency-hardening`

## What Changed

- Added stable `doc_id` matching for required-source packs, so exact Acts do not depend on OCR/title spacing.
- Added optional preferred anchor matching for known procedural sections, such as RTI section 19, BNSS section 173, and BNSS section 187.
- Preserved at least one required-source chunk at the final prompt top-K boundary.
- Backfilled the orphan `rti-2005` document with 42 chunks.
- Normalized display titles for BNS, BNSS, Code on Wages, and RTI.

## Focused Tests

Command:

```bash
PYTHONPATH=. .venv/bin/pytest \
  apps/api/tests/test_source_packs.py \
  apps/api/tests/test_matter_router.py \
  apps/api/tests/test_retrieval.py \
  apps/api/tests/test_endpoints.py -q
```

Result: `84 passed, 3 warnings`.

## Live 10-Query Eval

Command:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --limit 10 \
  --api http://localhost:8002 \
  --out data/processed/codex_source_pack_10_20260526.jsonl \
  --report data/processed/codex_source_pack_10_20260526.md
```

Result summary:

- Expected Act hit: `6/7` scored rows (`85.7%`).
- Refused: `2/10`.
- Errors: `0/10`.
- p50 total latency: `18.7s`.
- p50 retrieval latency: `3.5s`.
- Only expected-Act miss: Street Vendors Act, which is still absent from the indexed bare-Act corpus.

## Targeted Live Checks

| Prompt | Route | Required source result |
| --- | --- | --- |
| `I filed an RTI and it was rejected what is first appeal time limit` | `rti` | Hit: `Right to Information Act 2005`, including section 19 chunks |
| `police refused to register FIR for theft of my bike` | `police_fir` | Hit: BNSS section 173 and BNS theft sections |
| `brother in jail 60 days completed no chargesheet can he get default bail` | `criminal_defence_bail` | Hit after prompt-boundary preservation: BNSS section 187 |

## Remaining Gaps

- Street Vendors Act is still a true corpus gap.
- CrPC/IPC legacy bare Acts are still not safely indexed, so explicit pre-2024 criminal prompts must continue to carry the dual-regime warning.
- Warm rows are close to the 20s product gate, but cold model/retriever loads still exceed it.
