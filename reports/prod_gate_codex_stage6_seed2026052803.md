# Legal RAG Production Gate

Input: `data/processed/timed_eval_codex_stage6_seed2026052803.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 98/100 (98.0%) | >= 85.0% |
| expected_act_hit | 50/98 (51.0%) | >= 85.0% |
| usable_answer | 5/100 (5.0%) | >= 85.0% |
| action_pack | 89/100 (89.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 93/100 (93.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 15 | <= 0 |
| unsafe_refusal | 7 (7.0%) | <= 2.0% |
| dangerous_framing | 1 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 3 | <= 0 |
| wall_p50 | 19.6s | <= 20.0s |
| wall_p90 | 23.4s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| wrong_forum | 10 |
| unsafe_refusal | 7 |
| dangerous_off_topic | 3 |
| wrong_deadline | 2 |
| dangerous_framing | 1 |

## Failures

- expected_act_hit_pct 51.02040816326531 < 85.0
- usable_answer_pct 5.0 < 85.0
- timing_telemetry_pct 93.0 < 95.0
- legal_safety_hard_fails 15 > 0
- dangerous_framing 1 > 0
- dangerous_off_topic 3 > 0
- unsafe_refusal_pct 7.000000000000001 > 2.0
