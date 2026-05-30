# Timed 100-question eval

Rows: 8
Input/output: `data/processed/timed_eval_stage10_abort_regression.jsonl`

## Outcome

- Refused: 0/8
- Errors: 0/8
- Relevance verdicts: {'ok': 7, 'partial': 1}
- Expected Act hit: 5/8 (62.5%)
- Legal-safety gate: PASS (0/8 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 21.7s | 27.1s | 32.5s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.4s | 3.1s | 5.7s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.4s | 5.0s | 8.5s |
| retrieval_ms | 4.8s | 8.2s | 14.3s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 16.7s | 18.5s | 19.4s |
| verification_ms | 0.7s | 0.8s | 0.8s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| court_procedure | 1 |
| social_welfare_identity | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| tribal_caste_atrocity | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| court_procedure | 1 |
| social_welfare_identity | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| tribal_caste_atrocity | 1 |

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
| 32.5s | 14.3s | 18.0s | 0.6s | court_procedure | magistrate refused to take cognizance complaint how to challenge |
| 24.8s | 5.3s | 19.4s | 0.7s | criminal_defence_bail | police caught me drinking village they saying case under prohibition law what punishment |
| 23.0s | 5.6s | 17.3s | 0.8s | business_license_compliance | auto driver bangalore traffic police taking 500 every week no challan saying tamil license |
| 22.7s | 4.5s | 18.1s | 0.7s | labour_exploitation_discrimination | girl child 12 helping mother in our migrant camp domestic work delhi is this illegal she i |
| 20.7s | 4.5s | 16.2s | 0.7s | criminal_defence_bail | passport seized in mumbai airport for vape cartridge cbd legal in goa |
| 19.6s | 4.1s | 15.4s | 0.7s | police_fir | father custodial death lockup byculla police saying suicide what is 196 procedure |
| 19.2s | 5.0s | 14.1s | 0.7s | tribal_caste_atrocity | bonded labour my chacha working for thakur 12 years no wages just food bihar |
| 17.8s | 4.5s | 13.2s | 0.6s | social_welfare_identity | papa ki pension 6 month se nahi aayi rti kaise file karein |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage10_abort_regression | RTI Act, State Pension Scheme | social_welfare_identity | papa ki pension 6 month se nahi aayi rti kaise file karein | Right to Information Act 2005 |
| stage10_abort_regression | MV Act, Motor Vehicles Act, Prevention of Corruption Act | business_license_compliance | auto driver bangalore traffic police taking 500 every week no challan saying tamil license | TheMotorVehiclesAct,1988 |
| stage10_abort_regression | State Excise Act | criminal_defence_bail | police caught me drinking village they saying case under prohibition law what punishment | SATVINDER SINGH @ SATVINDER SINGH SALUJA & ORS versus THE STATE OF BIHAR |
