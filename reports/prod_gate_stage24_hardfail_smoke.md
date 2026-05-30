# Timed 100-question eval

Rows: 12
Input/output: `data/processed/timed_eval_stage24_hardfail_smoke.jsonl`

## Outcome

- Refused: 0/12
- Errors: 0/12
- Relevance verdicts: {'ok': 7, 'off_topic': 3, 'partial': 2}
- Expected Act hit: 11/12 (91.7%)
- Legal-safety gate: PASS (0/12 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 17.0s | 22.2s | 33.8s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.9s | 2.2s | 6.6s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.3s |
| variant_rerank_ms | 3.6s | 3.7s | 9.7s |
| retrieval_ms | 5.1s | 6.0s | 16.3s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 11.4s | 17.1s | 17.4s |
| verification_ms | 0.3s | 0.3s | 0.3s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| police_fir | 2 |
| criminal_defence_bail | 2 |
| employment_wages | 1 |
| social_welfare_identity | 1 |
| family_domestic | 1 |
| legal_aid | 1 |
| bonded_labour_rescue | 1 |
| workplace_injury_compensation | 1 |
| arrest_custody_safeguard | 1 |
| child_custody_adoption | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| police_fir | 2 |
| criminal_defence_bail | 2 |
| employment_wages | 1 |
| social_welfare_identity | 1 |
| family_domestic | 1 |
| legal_aid | 1 |
| bonded_labour_rescue | 1 |
| workplace_injury_compensation | 1 |
| arrest_custody_safeguard | 1 |
| child_custody_adoption | 1 |

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
| 33.8s | 16.3s | 17.3s | 0.3s | employment_wages | ESI dispensary refusing treatment saying my employer contribution pending what can I do |
| 22.3s | 4.8s | 17.4s | 0.3s | family_domestic | my husband's brother has been making me uncomfortable saying things and now grabbed my han |
| 21.1s | 6.0s | 15.0s | 0.2s | bonded_labour_rescue | thekedar took 18000 advance from me darbhanga not letting leave bangalore site |
| 20.0s | 5.9s | 14.0s | 0.1s | arrest_custody_safeguard | police arrested my brother but did not tell grounds or give arrest memo DK Basu kya rule h |
| 17.6s | 5.8s | 11.7s | 0.3s | workplace_injury_compensation | fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no b |
| 17.5s | 6.0s | 11.5s | 0.3s | criminal_defence_bail | brother in NDPS case arrested 110 days no chargesheet default bail possible |
| 16.4s | 4.9s | 11.4s | 0.2s | criminal_defence_bail | they say i am tonhi after child died in village false case filed chhattisgarh |
| 15.6s | 4.8s | 10.7s | 0.3s | police_fir | police notice for release of seized phone after investigation |
| 15.0s | 5.2s | 9.7s | 0.2s | child_custody_adoption | we are not a hindu family adopted child from sister no papers now real parents want him ba |
| 14.8s | 4.3s | 10.4s | 0.3s | police_fir | my company laptop has been seized by police as part of investigation against my colleague, |
| 13.5s | 4.1s | 9.3s | 0.3s | legal_aid | i am poor brother arrested can court give free lawyer nalsa kya hota hai |
| 5.1s | 4.7s | 0.0s | 0.2s | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| stage24_hardfail | Guardians and Wards Act, Juvenile Justice Act | child_custody_adoption | we are not a hindu family adopted child from sister no papers now real parents want him ba | Guardians and Wards Act 1890 |
