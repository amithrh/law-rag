# Timed 100-question eval

Rows: 5
Input/output: `data/processed/timed_eval_codex_stage8_smoke2_seed2026052805.jsonl`

## Outcome

- Refused: 0/5
- Errors: 0/5
- Relevance verdicts: {'ok': 3, 'no_relevance': 1, 'partial': 1}
- Expected Act hit: 5/5 (100.0%)
- Legal-safety gate: PASS (0/5 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 18.7s | 30.9s | 36.3s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 0.9s | 3.9s | 5.8s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 3.1s | 7.4s | 10.2s |
| retrieval_ms | 4.1s | 11.3s | 16.1s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 14.6s | 19.6s | 20.1s |
| verification_ms | 0.7s | 0.9s | 0.9s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| labour_exploitation_discrimination | 2 |
| succession_inheritance | 1 |
| criminal_defence_bail | 1 |
| ibc_nclt | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| labour_exploitation_discrimination | 2 |
| succession_inheritance | 1 |
| criminal_defence_bail | 1 |
| ibc_nclt | 1 |

## Legal Safety Gate

Gate: **PASS**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 36.3s | 16.1s | 20.1s | 0.8s | succession_inheritance | father wrote will but only registered one not the latest one which is valid |
| 22.7s | 3.7s | 18.9s | 0.9s | labour_exploitation_discrimination | I am ASHA worker not paid honorarium 6 months who can help |
| 18.7s | 4.1s | 14.6s | 0.7s | criminal_defence_bail | brother arrested NDPS 50 gram heroin commercial or not bail chances |
| 17.6s | 3.7s | 13.7s | 0.7s | ibc_nclt | appeal against NCLT order to NCLAT how many days limit |
| 14.7s | 4.3s | 10.5s | 0.3s | labour_exploitation_discrimination | site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskil |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
