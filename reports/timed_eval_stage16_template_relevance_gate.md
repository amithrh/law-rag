# Timed 100-question eval

Rows: 8
Input/output: `data/processed/timed_eval_stage16_template_relevance_gate.jsonl`

## Outcome

- Refused: 0/8
- Errors: 0/8
- Relevance verdicts: {'no_relevance': 1, 'ok': 7}
- Expected Act hit: 7/7 (100.0%)
- Legal-safety gate: PASS (0/8 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 15.6s | 23.0s | 30.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.4s | 3.6s | 6.7s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.6s | 5.4s | 9.5s |
| retrieval_ms | 4.8s | 9.0s | 16.5s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 10.8s | 13.9s | 13.9s |
| verification_ms | 0.2s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| bonded_labour_rescue | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| social_welfare_identity | 1 |
| court_procedure | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| bonded_labour_rescue | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| social_welfare_identity | 1 |
| court_procedure | 1 |

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
| 30.4s | 16.5s | 13.9s | 0.0s | bonded_labour_rescue | bonded labour my chacha working for thakur 12 years no wages just food bihar |
| 19.8s | 5.8s | 13.9s | 0.3s | criminal_defence_bail | passport seized in mumbai airport for vape cartridge cbd legal in goa |
| 18.2s | 4.6s | 13.5s | 0.2s | labour_exploitation_discrimination | girl child 12 helping mother in our migrant camp domestic work delhi is this illegal she i |
| 16.2s | 4.3s | 11.7s | 0.3s | police_fir | father custodial death lockup byculla police saying suicide what is 196 procedure |
| 15.0s | 5.0s | 10.0s | 0.2s | court_procedure | magistrate refused to take cognizance complaint how to challenge |
| 6.1s | 5.8s | 0.0s | 0.2s | social_welfare_identity | papa ki pension 6 month se nahi aayi rti kaise file karein |
| 4.9s | 4.6s | 0.0s | 0.1s | business_license_compliance | auto driver bangalore traffic police taking 500 every week no challan saying tamil license |
| 3.9s | 3.7s | 0.0s | 0.1s | criminal_defence_bail | police caught me drinking village they saying case under prohibition law what punishment |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
