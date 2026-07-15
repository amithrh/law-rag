# UI-real 50 v2 freeze - 2026-06-07

This file records the pre-run snapshot for the next product gate. The working tree
is intentionally dirty because the branch contains the current repair work; this
is a freeze manifest, not a clean release tag.

## Goal gate

- product pass: >= 95%
- critical pass: 100%
- safety hard fails: 0
- refusals/errors/bad route fallback: 0
- p90 latency: <= 20s

## One-shot rule

The prompt pack below is a one-shot eval. If the system is patched after seeing
the results, this pack becomes diagnostic only. Any later product claim must use
a fresh prompt draw that excludes this pack too.

## Git state

- branch: `codex/latency-hardening`
- head: `6c687348bba21d20ea413d861ea3de4e0b76566c`
- prompt pack: `data/eval_ui_real_50_v2_seed2026060702/human_messy_50_v2.jsonl`
- builder command:

```bash
PYTHONPATH=. .venv/bin/python scripts/build_human_messy_eval.py \
  --source data/eval_500 \
  --out-dir data/eval_ui_real_50_v2_seed2026060702 \
  --limit 50 \
  --seed 2026060702 \
  --filename human_messy_50_v2.jsonl \
  --exclude-prompts data/eval_ui_real_50_seed20260607
```

## Prompt provenance

- source inventory: `data/eval_500`
- generated style: human-like messy rewrites
- explicit limitation: not real production user logs
- previous UI-real 50 source-query overlap: 0
- rows: 50
- critical rows: 20
- personas: 10 personas x 5 rows
- common issues: 36

## Checksums

```text
a0790c21758df0293258cc3bc88de5fda75d292070a813b99d52c8518e92a802  data/eval_ui_real_50_v2_seed2026060702/human_messy_50_v2.jsonl
c17b7d7fdde18e1d31bbe832be1299727e6af8a9d7e43d25d888dd3ec2a23705  scripts/build_human_messy_eval.py
838cedb4cce4738caf26d3251ccb5e3c0ecf85fb958cb8ed5e97794a99cddb02  apps/api/main.py
d1f58bc2a7d201e9eb69919182d433ad705b0a56b767a9ca39b2eb8462410d61  apps/api/common_workflow_contracts.py
b921ee3b4efed49f1cdf00f2546e80f979add4678da10c3cc6b33172c5fa7e90  apps/api/authority_graph.py
35eb7ad7771b36323c71d1e9c3f1d7aa870112abc92782f5657900a9edfd6353  scripts/eval_timed_100.py
ef3c152afa0c38676037d1bff1c038e3704e630096e73cc83f9ae6233350f27a  scripts/eval_common_user_gate.py
da92c383151aa0570082b638601d3da41ca9dfe38937d06ec700ca8859671b98  scripts/legal_safety_eval.py
```

## Focused checks before run

```bash
.venv/bin/python -m pytest \
  apps/api/tests/test_eval_common_user_gate.py::test_human_messy_eval_carries_product_gate_metadata \
  apps/api/tests/test_eval_common_user_gate.py::test_human_messy_eval_can_exclude_burned_prompt_source_queries \
  -q
```

Result: `2 passed, 1 warning`.
