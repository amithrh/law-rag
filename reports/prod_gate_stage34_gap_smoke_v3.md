# Timed 100-question eval

Rows: 10
Input/output: `data/processed/timed_eval_stage34_gap_smoke_v3.jsonl`

## Outcome

- Refused: 0/10
- Errors: 0/10
- Relevance verdicts: {'partial': 5, 'ok': 5}
- Expected Act hit: 10/10 (100.0%)
- Expected Act cited hit: 10/10 (100.0%)
- Expected Act unscored: 0/10
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'missing_next_step_section': 1, 'suppressed_sentences': 1}
- Legal-safety gate: PASS (0/10 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 5.8s | 7.6s | 17.3s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 2.1s | 2.9s | 7.5s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 3.7s | 4.5s | 9.2s |
| retrieval_ms | 5.5s | 7.4s | 16.9s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 0.0s | 0.0s | 0.0s |
| verification_ms | 0.1s | 0.2s | 0.2s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| senior_citizen | 3 |
| cyber_fraud_or_harassment | 2 |
| tribal_caste_atrocity | 1 |
| ibc_nclt | 1 |
| criminal_defence_bail | 1 |
| business_license_compliance | 1 |
| court_procedure | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| senior_citizen | 3 |
| cyber | 2 |
| tribal_caste_atrocity | 1 |
| ibc_nclt | 1 |
| criminal_defence_bail | 1 |
| business_license_compliance | 1 |
| court_procedure | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| missing_next_step_section | 1 |
| suppressed_sentences | 1 |

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
| 17.3s | 16.9s | 0.0s | 0.2s | cyber_fraud_or_harassment | telegram channel leaked my onlyfans content without permission what to do |
| 6.5s | 6.3s | 0.0s | 0.1s | business_license_compliance | drug inspector picked up samples from my medical store schedule h sale without prescriptio |
| 6.3s | 5.9s | 0.0s | 0.2s | cyber_fraud_or_harassment | got porn video featuring lookalike of me 2 lakh views not me but face same |
| 6.2s | 6.0s | 0.0s | 0.1s | court_procedure | how is court fee calculated for civil suit valuation 25 lakh recovery |
| 6.2s | 6.0s | 0.0s | 0.1s | senior_citizen | I gave my house to son in gift deed now he wants to throw me out can I cancel |
| 5.3s | 5.1s | 0.0s | 0.1s | criminal_defence_bail | cops at delhi airport found my vape with thc oil what is the punishment |
| 5.1s | 5.0s | 0.0s | 0.1s | senior_citizen | mother in delhi son refuses to pay maintenance how much can tribunal order maximum |
| 5.0s | 4.8s | 0.0s | 0.1s | ibc_nclt | llp partner refusing to sign form 11 annual return 2 years pending strike off threat |
| 5.0s | 4.7s | 0.0s | 0.2s | senior_citizen | my father wants to know if registered gift deed to son can be cancelled if son not caring |
| 4.7s | 4.3s | 0.0s | 0.2s | tribal_caste_atrocity | company building dam will submerge 4 tribal villages no consent gram sabha odisha |

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
