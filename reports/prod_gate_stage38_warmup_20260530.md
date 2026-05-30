# Timed 100-question eval

Rows: 1
Input/output: `data/processed/timed_eval_stage38_warmup_20260530.jsonl`

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
| total_ms | 105.5s | 105.5s | 105.5s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 94.2s | 94.2s | 94.2s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.2s | 0.2s | 0.2s |
| variant_rerank_ms | 10.6s | 10.6s | 10.6s |
| retrieval_ms | 105.0s | 105.0s | 105.0s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 0.0s |
| verification_ms | 0.2s | 0.2s | 0.2s |
| relevance_ms | 0.2s | 0.2s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| bonded_labour_rescue | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| bonded_labour_rescue | 1 |

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
| 105.5s | 105.0s | 0.0s | 0.2s | bonded_labour_rescue | bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office |

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
