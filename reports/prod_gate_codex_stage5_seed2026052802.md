# Legal RAG Production Gate

Input: `data/processed/timed_eval_codex_stage5_seed2026052802.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 49/100 (49.0%) | >= 85.0% |
| expected_act_hit | 41/49 (83.7%) | >= 85.0% |
| usable_answer | 7/100 (7.0%) | >= 85.0% |
| action_pack | 89/100 (89.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 92/100 (92.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 23 | <= 0 |
| unsafe_refusal | 8 (8.0%) | <= 2.0% |
| dangerous_framing | 1 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 1 | <= 0 |
| wall_p50 | 19.5s | <= 20.0s |
| wall_p90 | 23.7s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| wrong_forum | 18 |
| unsafe_refusal | 8 |
| dangerous_off_topic | 1 |
| dangerous_framing | 1 |

## Failures

- scored_act_coverage_pct 49.0 < 85.0
- expected_act_hit_pct 83.6734693877551 < 85.0
- usable_answer_pct 7.000000000000001 < 85.0
- timing_telemetry_pct 92.0 < 95.0
- legal_safety_hard_fails 23 > 0
- dangerous_framing 1 > 0
- dangerous_off_topic 1 > 0
- unsafe_refusal_pct 8.0 > 2.0
