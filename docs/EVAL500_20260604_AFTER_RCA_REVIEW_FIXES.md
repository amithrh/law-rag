# 500-prompt benchmark — after RCA/review fixes

Date: 2026-06-04

Branch: `codex/latency-hardening`

Prompt pack: `data/eval_500` (`500` selected from `501` rows with seed `20260604`)

Raw artifacts:

- Timed JSONL: `/tmp/law_rag_20260604_eval500/timed_eval_500_after_rca_review_fixes.jsonl`
- Timed report: `/tmp/law_rag_20260604_eval500/timed_eval_500_after_rca_review_fixes.md`
- Product gate report: `/tmp/law_rag_20260604_eval500/product_gate_500_after_rca_review_fixes.md`
- Product gate failures: `/tmp/law_rag_20260604_eval500/product_gate_500_failures_after_rca_review_fixes.jsonl`

## Commands

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8038 \
  --queries-dir data/eval_500 \
  --limit 500 \
  --seed 20260604 \
  --timeout-s 180 \
  --out /tmp/law_rag_20260604_eval500/timed_eval_500_after_rca_review_fixes.jsonl \
  --report /tmp/law_rag_20260604_eval500/timed_eval_500_after_rca_review_fixes.md

PYTHONPATH=. .venv/bin/python scripts/eval_common_user_gate.py \
  /tmp/law_rag_20260604_eval500/timed_eval_500_after_rca_review_fixes.jsonl \
  --prompts data/eval_500 \
  --min-rows 500 \
  --min-high-priority-pass-pct 0 \
  --min-critical-rows 0 \
  --min-critical-priority-pass-pct 0 \
  --report /tmp/law_rag_20260604_eval500/product_gate_500_after_rca_review_fixes.md \
  --failures-jsonl /tmp/law_rag_20260604_eval500/product_gate_500_failures_after_rca_review_fixes.jsonl \
  --allow-fail
```

The high/critical priority thresholds were neutralized only because `data/eval_500` does not include `product_priority` metadata. Other production thresholds were left strict.

## Result

Gate: **FAIL**

| Metric | Result | Production target |
| --- | ---: | ---: |
| Product pass | 338/500 (67.6%) | >= 95% |
| Route match | 496/500 (99.2%) | >= 95% |
| Expected Act hit | 456/484 (94.2%) | diagnostic |
| Expected Act cited | 447/484 (92.4%) | >= 93.5% |
| First cited actionable | 500/500 (100.0%) | >= 95% |
| Errors | 0 | 0 |
| Refusals | 0 | 0 |
| Bad route fallbacks | 4 | 0 |
| Safety hard fails | 4 | 0 |
| p50 latency | 6.3s | <= 10s |
| p90 latency | 18.8s | <= 20s |
| Max latency | 24.9s | monitor |

Outcome verdicts:

- `ok`: 370/500
- `partial`: 118/500
- `off_topic`: 12/500

Answer quality flags:

- `expected_act_not_cited`: 37
- `zero_ok_legal_sentences`: 14

## What Improved

- The post-review fixes held live:
  - physical `stalks me near my house` routes to `police_fir` and cites expected BNS/BNSS sources;
  - cyber `stalks me on insta` routes to `cyber_fraud_or_harassment`;
  - `draft/register my will` routes to `succession_inheritance`.
- No runtime errors and no unintended refusals occurred in 500 rows.
- Latency is inside the current p50/p90 production gate.
- First cited source was actionable in all 500 answers.

## Main Failure Clusters

1. Hard route fallbacks:
   - Mediation Act standalone procedure fell to `general_legal`.
   - Will/testamentary variants fell to `general_legal`: `wrote will`, `make will`, `registered my will`.

2. State/scheme/special-law source gaps:
   - Scheduled-area and tribal land transfer variants.
   - Witch-hunting state Acts.
   - Shops and Establishments state registration/renewal.
   - State welfare schemes such as Kanya Vivah and ASHA honorarium.
   - Cattle preservation / state excise edge cases.
   - Pattadar/passbook and ration/Aadhaar mismatch variants.

3. Retrieved-but-not-cited authority:
   - NHRC / Article 21 police custody complaints.
   - SC/ST FIR and atrocity rows.
   - Platform/gig deactivation rows.
   - Principal-employer / contract labour liability.
   - Builder sale-deed registration.

4. Relevance verifier calibration:
   - Some answers routed and cited correctly but received `off_topic`, including consumer, GST, UAPA bail, business contract, and street-vendor examples.
   - Treat relevance as a QA signal, not as a final product-quality oracle.

## Next Fix Order

1. Remove all 4 safety hard fails:
   - add Mediation Act route/source/template;
   - broaden will/testamentary detection without reintroducing future-tense false positives.

2. Raise expected Act cited above 93.5%:
   - pin/cite exact state and scheme packs for tribal land transfer, witch-hunting, shops, state welfare, cattle/excise, and ration/Aadhaar variants;
   - strengthen answer-layer citation priority when exact sources are already retrieved.

3. Relevance calibration:
   - sample the 12 `off_topic` rows and 118 `partial` rows;
   - separate weak answers from false-negative verifier judgments;
   - adjust template phrasing or verifier prompts only after manual inspection.

4. Rerun:
   - targeted failures subset;
   - 200 fresh human-style prompts;
   - full 500 again only after targeted gates are clean.
