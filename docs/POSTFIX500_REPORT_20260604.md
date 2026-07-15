# Post-Fix Fresh 500 Report - 2026-06-04

## Summary

This run tested a new 500-prompt human-messy pack after the Stage 1 fixes for:

- testamentary/will routing;
- general Mediation Act routing;
- future-tense `will` near misses;
- third-party completed-suicide legal routing;
- adult family violence vs child-assault routing;
- generic HR harassment vs explicit POSH source boundaries.

Result: **improved, but not production-ready**.

The system is now much better at routing common questions, and the known will hard-fails are fixed. The remaining production blockers are answer relevance, exact Act citation, state/local source coverage, and p90/max latency.

## Research Direction

Research and Claude CLI review both point to the same architecture direction:

- Legal RAG needs precise snippet-level retrieval and citation support, not broad chunks. See LegalBench-RAG: https://arxiv.org/abs/2408.10343
- Evaluation should split context relevance, answer faithfulness, and answer relevance instead of relying on one opaque product verdict. See ARES: https://arxiv.org/abs/2311.09476
- Retrieval should be adaptive/corrective when the first retrieval set is weak. See Self-RAG and CRAG: https://arxiv.org/abs/2310.11511 and https://arxiv.org/abs/2401.15884
- Product readiness needs an explicit risk/governance gate. See NIST AI RMF and GenAI Profile: https://www.nist.gov/itl/ai-risk-management-framework and https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf

Claude's CLI review called out the same structural issue: the repo is still too dependent on route/source/template rules. That can fix high-frequency failures, but the route tail is unbounded unless we add authority graph + corrective retrieval + calibrated eval.

## Implemented

Files changed in this stage:

- `apps/api/matter_router.py`
- `apps/api/source_packs.py`
- `apps/api/tests/test_matter_router.py`
- `apps/api/tests/test_source_packs.py`
- `docs/RESEARCH_IMPROVEMENT_PLAN_20260604.md`

Key behavior changes:

- Will/testamentary prompts now route to `succession_inheritance` before criminal/high-risk catchalls.
- Future-tense prompts like "will police register FIR..." no longer route to succession.
- "Mediation Act 2023 / initiate mediation" routes to `court_procedure`; plain "without going to court" no longer steals divorce/salary/landlord queries.
- Completed third-party suicide/abetment facts no longer become crisis-only helpline answers.
- Adult son/daughter violence against parent no longer falls into child/JJ route.
- Generic HR harassment/PIP no longer gets POSH unless sexual harassment, ICC, or POSH facts are present.

## Reviews

Subagent review 1 found:

- over-broad testamentary `will` routing;
- crisis route stealing completed third-party suicide/abetment facts;
- adult family violence misread as child assault;
- generic workplace harassment pulling POSH;
- packaging risk around `crisis_resources.py`.

All code-level findings above were fixed and covered by tests.

Subagent review 2 found:

- general mediation was too broad because "without going to court" alone triggered it;
- unqualified "my son beats his mother" still fell into child assault/general fallback;
- completed-suicide route lacked substantive BNS/IPC source packs.

All three were fixed and covered by tests.

## Local Verification

Command:

```bash
PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_matter_router.py apps/api/tests/test_source_packs.py -q
```

Result:

- `354 passed`
- one existing pytest config warning: `Unknown config option: asyncio_mode`

## Fresh 500 Eval

Prompt generation:

```bash
PYTHONPATH=. .venv/bin/python scripts/build_human_messy_eval.py \
  --source data/eval_500 \
  --out-dir /tmp/law_rag_20260604_postfix500/prompts \
  --limit 500 \
  --seed 2026060403
```

Timed eval:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8038 \
  --queries-dir /tmp/law_rag_20260604_postfix500/prompts \
  --limit 500 \
  --seed 2026060403 \
  --out /tmp/law_rag_20260604_postfix500/out/timed_eval_postfix500_human_messy_seed2026060403.jsonl \
  --report /tmp/law_rag_20260604_postfix500/out/timed_eval_postfix500_human_messy_seed2026060403.md
```

Product gate:

```bash
PYTHONPATH=. .venv/bin/python scripts/eval_common_user_gate.py \
  /tmp/law_rag_20260604_postfix500/out/timed_eval_postfix500_human_messy_seed2026060403.jsonl \
  --prompts /tmp/law_rag_20260604_postfix500/prompts \
  --report /tmp/law_rag_20260604_postfix500/out/product_gate_postfix500_human_messy_seed2026060403.md \
  --failures-jsonl /tmp/law_rag_20260604_postfix500/out/product_gate_postfix500_failures_human_messy_seed2026060403.jsonl \
  --allow-fail
```

## Metrics

| metric | previous fresh 500 | post-fix fresh 500 | delta |
| --- | ---: | ---: | ---: |
| product pass | 392/500 (78.4%) | 401/500 (80.2%) | +1.8pp |
| route match | 499/500 (99.8%) | 500/500 (100.0%) | +0.2pp |
| expected Act hit | 456/484 (94.2%) | 457/484 (94.4%) | +0.2pp |
| expected Act cited | 446/484 (92.1%) | 445/484 (91.9%) | -0.2pp |
| relevance ok | 430/500 | 445/500 | +15 |
| partial | 62/500 | 53/500 | -9 |
| off_topic | 8/500 | 2/500 | -6 |
| safety hard fails | 3/500 | 0/500 | fixed |
| p50 latency | 7.0s | 6.7s | improved |
| p90 latency | 21.0s | 19.2s | improved, within current gate |
| max latency | 46.9s | 47.2s | flat |
| errors/refusals | 0/0 | 0/0 | stable |
| bad route fallback | 1 | 0 | fixed |

Strict product gate result: **FAIL**.

Main failures:

- `relevance_not_ok`: 55
- `expected_act_not_cited`: 39
- `expected_act_missing`: 27
- `zero_ok_legal_sentences`: 15

The gate also reports high-priority rows as `0/0`; this appears to be missing priority metadata in this generated prompt pack, not an answer-quality signal. The product-pass and Act/citation numbers remain valid.

## What Improved

- The three will/testamentary hard-fail examples now pass route + Act + citation + relevance.
- Bad route fallback went to zero.
- Safety hard fails went to zero.
- Route match reached 100%.
- Relevance improved materially: `ok` increased from 430 to 445; `off_topic` dropped from 8 to 2.
- p90 latency improved from 21.0s to 19.2s.

## Still Not Production-Ready

The system is still not above the production gate because:

- Product pass is only 80.2%, target 95%.
- Expected Act cited is 91.9%, target 93.5%.
- 55 rows are not directly useful enough to users even when route and citation often pass.
- State/local coverage remains uneven.
- Max latency remains high at 47.2s.

## Top Failure Clusters

1. Digital sexual/privacy harms:
   - deepfake porn;
   - AI-CSAM;
   - OnlyFans/content leak;
   - lookalike porn/video.

2. Tribal/caste/state-specific law:
   - tribal land transfer/restoration;
   - witch-branding/daayan/tonhi outside Assam;
   - caste violence in school;
   - Sarna/pahan/adivasi religious targeting.

3. Police/custody/defence details:
   - lockup beating/bribe expected-source citation;
   - default bail/undertrial review answer usefulness;
   - juvenile transfer to observation home;
   - NDPS quantity/commercial bail.

4. Welfare and state schemes:
   - ASHA honorarium;
   - Kanya Vivah;
   - Aadhaar/ration mismatch variants;
   - pattadar/passbook state records.

5. State business/labour/local compliance:
   - Tamil Nadu / Rajasthan Shops and Establishments;
   - cattle transport/state animal preservation;
   - municipal/local shop sealing and street vendor variants.

6. Answer-layer usefulness:
   - answers cite correct law but do not answer the actual next step;
   - procedural answers often state generic source facts instead of forum/form/deadline/action.

7. Latency:
   - slowest row: 47.2s;
   - p90 is within current gate at 19.2s, but max and many high-stakes procedural rows remain slow.

## Next Fix Order

1. Citation repair pass:
   - if expected/required Act is retrieved but not cited, re-prompt or deterministic repair before response.

2. Digital harm action pack:
   - deepfake/AI-CSAM/non-consensual image abuse with IT Act + BNS + POCSO + platform takedown + cyber portal steps.

3. Tribal/state coverage ledger:
   - add or mark gaps for Jharkhand/Chhattisgarh witch-branding, tribal land transfer/restoration, Odisha/AP/Jharkhand scheduled-area rules.

4. Custody/defence templates:
   - default bail, UAPA/NDPS, juvenile transfer, lockup beating/bribe, undertrial review, medical bail.

5. Welfare/state scheme packs:
   - ASHA, Kanya Vivah, Aadhaar/ration mismatch, pattadar/passbook.

6. Latency:
   - deterministic procedural answer paths for repeated criminal/court/tax/compliance routes;
   - cache source-pack retrieval;
   - reduce or parallelize slow LLM generation paths.

## Bottom Line

This stage landed real improvements, especially eliminating legal-safety hard fails and will/testamentary routing failures. But the product is still not ready. The next milestone is not "more hard routes"; it is authority/citation repair plus source coverage ledger plus route-specific procedural action packs for the repeated failure clusters.
