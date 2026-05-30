# Timed 100-question eval

Rows: 5
Input/output: `data/processed/timed_eval_codex_stage8_smoke_seed2026052805.jsonl`

## Outcome

- Refused: 1/5
- Errors: 0/5
- Relevance verdicts: {'ok': 2, 'refused': 1, 'partial': 1, 'no_relevance': 1}
- Expected Act hit: 3/5 (60.0%)
- Legal-safety gate: FAIL (1/5 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 17.4s | 29.8s | 36.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | 0.5s | 0.5s | 0.5s |
| single_expanded_retrieval_ms | 0.8s | 4.2s | 5.7s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 3.1s | 7.5s | 10.1s |
| retrieval_ms | 4.0s | 11.3s | 15.8s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 14.3s | 19.0s | 20.4s |
| verification_ms | 0.6s | 0.7s | 0.7s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| succession_inheritance | 1 |
| general_legal | 1 |
| criminal_defence_bail | 1 |
| ibc_nclt | 1 |
| labour_exploitation_discrimination | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| succession_inheritance | 1 |
| none | 1 |
| criminal_defence_bail | 1 |
| ibc_nclt | 1 |
| labour_exploitation_discrimination | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 1 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 1 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_forum, unsafe_refusal | general_legal | wage_theft | site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskil | answerable legal prompt produced refusal, error, or zero cited sentences; expected wage_theft route, got general_legal |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 36.4s | 15.8s | 20.4s | 0.7s | succession_inheritance | father wrote will but only registered one not the latest one which is valid |
| 20.0s | 4.0s | 15.8s | 0.7s | criminal_defence_bail | brother arrested NDPS 50 gram heroin commercial or not bail chances |
| 17.4s | 4.6s | 12.8s | 0.1s | ibc_nclt | appeal against NCLT order to NCLAT how many days limit |
| 15.7s | 3.7s | 11.9s | 0.5s | labour_exploitation_discrimination | I am ASHA worker not paid honorarium 6 months who can help |
| 2.0s | 2.0s | n/a | n/a | general_legal | site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskil |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| migrant_labour | Code on Wages | general_legal | site supervisor saying minimum wage 350 only but karnataka rate is 600 construction unskil |  |
| rural_dlsa | State Welfare Scheme | labour_exploitation_discrimination | I am ASHA worker not paid honorarium 6 months who can help | Bonded Labour System (Abolition) Act 1976 |
