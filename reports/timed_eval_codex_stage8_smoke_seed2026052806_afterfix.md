# Timed 100-question eval

Rows: 5
Input/output: `data/processed/timed_eval_codex_stage8_smoke_seed2026052806_afterfix.jsonl`

## Outcome

- Refused: 0/5
- Errors: 0/5
- Relevance verdicts: {'ok': 3, 'partial': 1, 'no_relevance': 1}
- Expected Act hit: 5/5 (100.0%)
- Legal-safety gate: PASS (0/5 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 16.1s | 21.2s | 23.3s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | n/a | n/a | n/a |
| single_expanded_retrieval_ms | 0.9s | 1.6s | 1.9s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.1s |
| variant_rerank_ms | 2.9s | 3.3s | 3.6s |
| retrieval_ms | 4.0s | 4.8s | 5.0s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 12.2s | 16.8s | 18.6s |
| verification_ms | 0.6s | 0.9s | 1.0s |
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
| 23.3s | 4.5s | 18.6s | 1.0s | senior_citizen | my mother 81 not allowed in her own kitchen by daughter in law mumbai legal remedy |
| 18.1s | 4.0s | 14.0s | 0.6s | labour_exploitation_discrimination | principal employer reliance site contractor ran away with 4 months wages 22 workers what t |
| 16.1s | 3.8s | 12.2s | 0.6s | police_fir | brother arrested no fir copy given family police saying secret kya rule |
| 15.9s | 3.7s | 12.1s | 0.7s | legal_aid | BPL card holder eligibility for free legal aid from DLSA SLSA |
| 13.5s | 5.0s | 8.5s | 0.2s | social_welfare_identity | kanya vivah scheme money not given by government after my daughter wedding |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
