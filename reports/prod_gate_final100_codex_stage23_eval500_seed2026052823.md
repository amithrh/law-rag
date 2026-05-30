# Legal RAG Production Gate

Input: `data/processed/timed_eval_final100_codex_stage23_eval500_seed2026052823.jsonl`
Gate: **FAIL**

## Metrics

| metric | value | target |
| --- | ---: | ---: |
| rows | 100 | >= 100 |
| scored_act_coverage | 97/100 (97.0%) | >= 85.0% |
| expected_act_hit | 67/97 (69.1%) | >= 85.0% |
| usable_answer | 35/100 (35.0%) | >= 85.0% |
| action_pack | 96/100 (96.0%) | >= 85.0% |
| route_telemetry | 100/100 (100.0%) | >= 95.0% |
| timing_telemetry | 98/100 (98.0%) | >= 95.0% |
| wall_latency_coverage | 100/100 (100.0%) | >= 100.0% |
| errors | 0 | <= 0 |
| legal_safety_hard_fails | 9 | <= 0 |
| unsafe_refusal | 2 (2.0%) | <= 2.0% |
| dangerous_framing | 0 | <= 0 |
| wrong_regime | 0 | <= 0 |
| dangerous_off_topic | 3 | <= 0 |
| wall_p50 | 16.5s | <= 20.0s |
| wall_p90 | 20.2s | <= 30.0s |

## Safety Labels

| label | count |
| --- | ---: |
| wrong_forum | 5 |
| dangerous_off_topic | 3 |
| unsafe_refusal | 2 |

## Failures

- expected_act_hit_pct 69.0721649484536 < 85.0
- usable_answer_pct 35.0 < 85.0
- legal_safety_hard_fails 9 > 0
- dangerous_off_topic 3 > 0
