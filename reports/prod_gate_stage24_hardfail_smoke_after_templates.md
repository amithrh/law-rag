# Timed 100-question eval

Rows: 12
Input/output: `data/processed/timed_eval_stage24_hardfail_smoke_after_templates.jsonl`

## Outcome

- Refused: 0/12
- Errors: 0/12
- Relevance verdicts: {'ok': 10, 'partial': 2}
- Expected Act hit: 12/12 (100.0%)
- Legal-safety gate: PASS (0/12 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 13.7s | 21.8s | 35.3s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 1.9s | 2.2s | 7.3s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.3s |
| variant_rerank_ms | 3.5s | 3.7s | 10.9s |
| retrieval_ms | 5.1s | 5.9s | 18.2s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 9.5s | 16.6s | 17.2s |
| verification_ms | 0.2s | 0.3s | 0.3s |
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
| 35.3s | 18.2s | 16.8s | 0.3s | employment_wages | ESI dispensary refusing treatment saying my employer contribution pending what can I do |
| 22.0s | 4.7s | 17.2s | 0.3s | family_domestic | my husband's brother has been making me uncomfortable saying things and now grabbed my han |
| 20.1s | 5.9s | 14.1s | 0.2s | arrest_custody_safeguard | police arrested my brother but did not tell grounds or give arrest memo DK Basu kya rule h |
| 17.2s | 5.9s | 11.3s | 0.2s | criminal_defence_bail | brother in NDPS case arrested 110 days no chargesheet default bail possible |
| 15.4s | 4.7s | 10.6s | 0.3s | police_fir | police notice for release of seized phone after investigation |
| 14.5s | 4.2s | 10.2s | 0.3s | police_fir | my company laptop has been seized by police as part of investigation against my colleague, |
| 12.9s | 4.0s | 8.8s | 0.3s | legal_aid | i am poor brother arrested can court give free lawyer nalsa kya hota hai |
| 6.2s | 5.9s | 0.0s | 0.1s | bonded_labour_rescue | thekedar took 18000 advance from me darbhanga not letting leave bangalore site |
| 6.1s | 5.8s | 0.0s | 0.2s | workplace_injury_compensation | fell from 5th floor site whitefield bangalore leg broken thekedar saying no insurance no b |
| 5.5s | 5.2s | 0.0s | 0.2s | child_custody_adoption | we are not a hindu family adopted child from sister no papers now real parents want him ba |
| 5.2s | 5.0s | 0.0s | 0.1s | criminal_defence_bail | they say i am tonhi after child died in village false case filed chhattisgarh |
| 5.0s | 4.7s | 0.0s | 0.2s | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
