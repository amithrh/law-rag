# Legal RAG Production Gate

Input: `data/processed/timed_eval_codex_stage4_seed2026052801.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 52/100 (52.0%) | >= 85.0% |
| expected_act_hit | 38/52 (73.1%) | >= 85.0% |
| usable_answer | 12/100 (12.0%) | >= 85.0% |
| action_pack | 85/100 (85.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 91/100 (91.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 14 | <= 0 |
| unsafe_refusal | 9 (9.0%) | <= 2.0% |
| dangerous_framing | 1 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 1 | <= 0 |
| wall_p50 | 20.5s | <= 20.0s |
| wall_p90 | 23.9s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| unsafe_refusal | 9 |
| wrong_forum | 7 |
| dangerous_off_topic | 1 |
| dangerous_framing | 1 |

## Failures

- scored_act_coverage_pct 52.0 < 85.0
- expected_act_hit_pct 73.07692307692307 < 85.0
- usable_answer_pct 12.0 < 85.0
- timing_telemetry_pct 91.0 < 95.0
- legal_safety_hard_fails 14 > 0
- dangerous_framing 1 > 0
- dangerous_off_topic 1 > 0
- unsafe_refusal_pct 9.0 > 2.0
- wall_p50_ms 20464.95 > 20000.0
