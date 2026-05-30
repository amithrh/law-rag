# Timed 100-question eval

Rows: 7
Input/output: `data/processed/timed_eval_stage36_blockers_seed2026052919.jsonl`

## Outcome

- Refused: 0/7
- Errors: 0/7
- Relevance verdicts: {'ok': 6, 'partial': 1}
- Expected Act hit: 7/7 (100.0%)
- Expected Act cited hit: 7/7 (100.0%)
- Expected Act unscored: 0/7
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'zero_ok_legal_sentences': 1}
- Legal-safety gate: PASS (0/7 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 4.7s | 10.4s | 16.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.0s | 4.0s | 6.3s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 3.4s | 6.0s | 9.7s |
| retrieval_ms | 4.5s | 10.0s | 16.1s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 0.0s |
| verification_ms | 0.2s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| tribal_caste_atrocity | 2 |
| legal_aid | 1 |
| environment_compensation | 1 |
| banking_credit_dispute | 1 |
| trademark_ip | 1 |
| labour_compliance | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| tribal_caste_atrocity | 2 |
| legal_aid | 1 |
| environment_compensation | 1 |
| banking_credit_dispute | 1 |
| trademark_ip | 1 |
| labour_compliance | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| zero_ok_legal_sentences | 1 |

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
| 16.4s | 16.1s | 0.0s | 0.2s | legal_aid | how to approach Lok Adalat for pending traffic challan settlement |
| 6.4s | 6.0s | 0.0s | 0.3s | labour_compliance | maharashtra labour department raid kiya overtime register not maintained 11 workers what t |
| 5.6s | 5.3s | 0.0s | 0.2s | tribal_caste_atrocity | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp |
| 4.7s | 4.5s | 0.0s | 0.1s | environment_compensation | my land taken for highway 4 years back compensation still not received who to ask |
| 4.6s | 4.4s | 0.0s | 0.1s | trademark_ip | trademark application opposed by a bigger company saying it is similar to their mark, hear |
| 4.3s | 4.0s | 0.0s | 0.2s | tribal_caste_atrocity | village headman saying my caste cannot enter temple in festival dindori what rights |
| 4.3s | 3.9s | 0.0s | 0.3s | banking_credit_dispute | bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and th |

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
