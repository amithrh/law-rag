# Timed 100-question eval

Rows: 1
Input/output: `data/processed/timed_eval_stage35_msme_quality_seed2026052917.jsonl`

## Outcome

- Refused: 0/1
- Errors: 0/1
- Relevance verdicts: {'ok': 1}
- Expected Act hit: 1/1 (100.0%)
- Expected Act cited hit: 1/1 (100.0%)
- Expected Act unscored: 0/1
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {}
- Legal-safety gate: PASS (0/1 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 28.2s | 28.2s | 28.2s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 9.6s | 9.6s | 9.6s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 10.0s | 10.0s | 10.0s |
| retrieval_ms | 19.7s | 19.7s | 19.7s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 8.2s | 8.2s | 8.2s |
| verification_ms | 0.3s | 0.3s | 0.3s |
| relevance_ms | 0.3s | 0.3s | 0.3s |

## Route Distribution

| route | count |
| --- | ---: |
| business_contract_partnership | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| business_contract_partnership | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| none | 0 |

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
| 28.2s | 19.7s | 8.2s | 0.3s | business_contract_partnership | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |
