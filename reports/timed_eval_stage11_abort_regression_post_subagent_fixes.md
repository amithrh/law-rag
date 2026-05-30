# Timed 100-question eval

Rows: 8
Input/output: `data/processed/timed_eval_stage11_abort_regression_post_subagent_fixes.jsonl`

## Outcome

- Refused: 0/8
- Errors: 0/8
- Relevance verdicts: {'ok': 7, 'no_relevance': 1}
- Expected Act hit: 4/8 (50.0%)
- Legal-safety gate: PASS (0/8 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 20.3s | 25.5s | 32.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.5s | 3.2s | 5.8s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.6s | 5.2s | 8.6s |
| retrieval_ms | 5.0s | 8.6s | 14.5s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 15.5s | 16.9s | 17.7s |
| verification_ms | 0.4s | 0.7s | 0.7s |
| relevance_ms | 0.1s | 0.1s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| court_procedure | 1 |
| social_welfare_identity | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| bonded_labour_rescue | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 2 |
| court_procedure | 1 |
| social_welfare_identity | 1 |
| police_fir | 1 |
| labour_exploitation_discrimination | 1 |
| business_license_compliance | 1 |
| bonded_labour_rescue | 1 |

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
| 32.4s | 14.5s | 17.7s | 0.7s | court_procedure | magistrate refused to take cognizance complaint how to challenge |
| 22.5s | 5.8s | 16.5s | 0.4s | business_license_compliance | auto driver bangalore traffic police taking 500 every week no challan saying tamil license |
| 21.8s | 5.4s | 16.3s | 0.3s | criminal_defence_bail | police caught me drinking village they saying case under prohibition law what punishment |
| 20.4s | 4.6s | 15.6s | 0.3s | labour_exploitation_discrimination | girl child 12 helping mother in our migrant camp domestic work delhi is this illegal she i |
| 20.1s | 4.7s | 15.3s | 0.6s | criminal_defence_bail | passport seized in mumbai airport for vape cartridge cbd legal in goa |
| 19.6s | 6.1s | 13.6s | 0.1s | bonded_labour_rescue | bonded labour my chacha working for thakur 12 years no wages just food bihar |
| 18.4s | 4.6s | 13.6s | 0.7s | social_welfare_identity | papa ki pension 6 month se nahi aayi rti kaise file karein |
| 18.0s | 4.3s | 13.5s | 0.4s | police_fir | father custodial death lockup byculla police saying suicide what is 196 procedure |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage10_abort_regression | RTI Act, State Pension Scheme | social_welfare_identity | papa ki pension 6 month se nahi aayi rti kaise file karein | Right to Information Act 2005 |
| stage10_abort_regression | MV Act, Motor Vehicles Act, Prevention of Corruption Act | business_license_compliance | auto driver bangalore traffic police taking 500 every week no challan saying tamil license | TheMotorVehiclesAct,1988 |
| stage10_abort_regression | State Excise Act | criminal_defence_bail | police caught me drinking village they saying case under prohibition law what punishment | Code of Criminal Procedure 1973 |
| stage10_abort_regression | Bonded Labour Act, SC/ST POA Act | bonded_labour_rescue | bonded labour my chacha working for thakur 12 years no wages just food bihar | Bonded Labour System (Abolition) Act 1976 |
