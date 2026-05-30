# Legal RAG Production Gate

Input: `data/processed/timed_eval_codex_stage3_seed2026052708.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 42/100 (42.0%) | >= 85.0% |
| expected_act_hit | 27/42 (64.3%) | >= 85.0% |
| usable_answer | 4/100 (4.0%) | >= 85.0% |
| action_pack | 89/100 (89.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 91/100 (91.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 16 | <= 0 |
| unsafe_refusal | 9 (9.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 4 | <= 0 |
| wall_p50 | 20.0s | <= 20.0s |
| wall_p90 | 24.3s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| unsafe_refusal | 9 |
| dangerous_off_topic | 4 |
| wrong_forum | 4 |
| wrong_deadline | 3 |

## Failures

- scored_act_coverage_pct 42.0 < 85.0
- expected_act_hit_pct 64.28571428571429 < 85.0
- usable_answer_pct 4.0 < 85.0
- timing_telemetry_pct 91.0 < 95.0
- legal_safety_hard_fails 16 > 0
- dangerous_off_topic 4 > 0
- unsafe_refusal_pct 9.0 > 2.0
- wall_p50_ms 20027.45 > 20000.0
