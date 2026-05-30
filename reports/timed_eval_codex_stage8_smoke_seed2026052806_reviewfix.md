# Timed 100-question eval

Rows: 5
Input/output: `data/processed/timed_eval_codex_stage8_smoke_seed2026052806_reviewfix.jsonl`

## Outcome

- Refused: 0/5
- Errors: 0/5
- Relevance verdicts: {'ok': 4, 'partial': 1}
- Expected Act hit: 5/5 (100.0%)
- Legal-safety gate: PASS (0/5 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 17.0s | 29.7s | 37.7s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 0.8s | 3.8s | 5.6s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 3.0s | 6.5s | 8.9s |
| retrieval_ms | 3.8s | 10.4s | 14.6s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 13.0s | 19.3s | 23.0s |
| verification_ms | 0.7s | 0.9s | 1.0s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| senior_citizen | 1 |
| labour_exploitation_discrimination | 1 |
| police_fir | 1 |
| legal_aid | 1 |
| social_welfare_identity | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| senior_citizen | 1 |
| labour_exploitation_discrimination | 1 |
| police_fir | 1 |
| legal_aid | 1 |
| social_welfare_identity | 1 |

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
| 37.7s | 14.6s | 23.0s | 1.0s | senior_citizen | my mother 81 not allowed in her own kitchen by daughter in law mumbai legal remedy |
| 17.7s | 3.7s | 13.8s | 0.7s | social_welfare_identity | kanya vivah scheme money not given by government after my daughter wedding |
| 17.0s | 3.8s | 13.0s | 0.7s | police_fir | brother arrested no fir copy given family police saying secret kya rule |
| 16.6s | 4.1s | 12.4s | 0.5s | labour_exploitation_discrimination | principal employer reliance site contractor ran away with 4 months wages 22 workers what t |
| 15.9s | 3.7s | 12.1s | 0.7s | legal_aid | BPL card holder eligibility for free legal aid from DLSA SLSA |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
