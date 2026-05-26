# Codex Source-Pack Eval — 2026-05-26

Branch: `codex/latency-hardening`

## What Changed

- Added stable `doc_id` matching for required-source packs, so exact Acts do not depend on OCR/title spacing.
- Added optional preferred anchor matching for known procedural sections, such as RTI section 19, BNSS section 173, and BNSS section 187.
- Preserved at least one required-source chunk at the final prompt top-K boundary.
- Ported the useful TurboVec idea of post-rerank source authority scoring: bare Acts, Supreme Court judgments, High Court judgments, and repeated matches from the same document now get small bounded rerank nudges.
- Promoted exact required-source packs into the first few contexts, so the answer sees the operative Act before a long run of similar case paragraphs.
- Made criminal bail query expansion query-sensitive: default-bail/no-chargesheet queries now expand to BNSS section 187 / CrPC section 167 instead of generic anticipatory-bail terms.
- Added fielded full-text retrieval for bare Acts: a fourth retrieval head now searches weighted document title, statute short name, doc id, chunk anchor, and body text. This is intentionally bare-Act-only to avoid slow/noisy judgment-header matches.
- Backfilled the orphan `rti-2005` document with 42 chunks.
- Normalized display titles for BNS, BNSS, Code on Wages, and RTI.

## Tests

Command:

```bash
PYTHONPATH=. .venv/bin/pytest apps/api/tests -q
```

Result: `163 passed, 10 warnings`.

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
| `brother in jail 60 days completed no chargesheet can he get default bail` | `criminal_defence_bail` | Hit after authority rerank + visible-window promotion: BNSS section 187 at rank 4 / 7, with expansion `BNSS 2023 section 187 CrPC 1973 section 167 default bail` |
| `BNSS section 187 default bail` | direct fielded BM25 | Hit: BNSS section 187 chunks ranked 1-5 in `0.464s` |
| `Right to Information Act first appeal section 19` | direct fielded BM25 | Hit: RTI section 19 chunks ranked 1-3 |
| `Consumer Protection Act 2019 district commission refund` | direct fielded BM25 | Hit: Consumer Protection Act chunks ranked 1-8 |

## Remaining Gaps

- Street Vendors Act is still a true corpus gap.
- CrPC/IPC legacy bare Acts are still not safely indexed, so explicit pre-2024 criminal prompts must continue to carry the dual-regime warning.
- Warm rows are close to the 20s product gate, but cold model/retriever loads still exceed it.
- Source packs are still hardcoded Python config; they should move to YAML or DB-backed configuration before this becomes a serious legal product surface.
- The fielded head currently targets bare Acts only. That is intentional for latency/noise; judgment fielding needs a separate cleaner that suppresses header blobs before it is useful.
