# Release Changeset Map

**Date:** 2026-08-01
**Integration branch:** `codex/production-readiness-20260801`
**Source branch:** `codex/latency-hardening`
**Purpose:** Turn the green but dirty recovery worktree into reviewable release commits.

## Inventory summary

The reproducible inventory is generated with:

```bash
.venv/bin/python scripts/release_change_inventory.py \
  --output reports/release-change-inventory-20260801.json
```

Initial grouping before assembly:

| Concern | Paths |
| --- | ---: |
| API runtime | 22 |
| API tests | 31 |
| Authority registry | 23 |
| Data and retrieval | 6 |
| Web | 12 |
| Infrastructure and CI | 4 |
| Documentation and governance | 9 |
| Evaluation evidence | 2 |
| Tooling | 5 |
| **Total** | **114** |

The original worktree was functionally coherent but not file-separable. In particular,
`main.py`, `matter_router.py`, `legal_issue_plan.py`, `source_gap.py`,
`source_packs.py`, `test_endpoints.py`, and `test_common_workflow_contracts.py`
contained changes from several stages. Exact staged-snapshot testing showed
that the API runtime and matter-contract changes shared `main.py` and their
evaluation authority-alias contract, so those two planned slices were combined
rather than forcing a misleading hunk split.

## Assembly result

| Commit | Scope | Acceptance evidence |
| --- | --- | --- |
| `c0cf002` | Readiness governance and reproducible dirty inventory | Inventory unit test and Ruff |
| `4cc75cb` | Immutable authority registry and corpus repair | 82 focused tests, 2 live PostgreSQL rollback tests, wheel build/inspection |
| `4a9f91d` | Production API runtime, MatterPlan, routing, answer ownership, and evaluator alias compatibility | 2,449 deterministic tests, 68 live-stack tests, 7 model tests, 2 evaluation-data tests |
| `283b285` | Authenticated web proxy, fail-closed SSE UI, Compose/environment hardening | 26 web tests, TypeScript, production build, Compose merge, live browser contract |
| `1ce286b` | Legal-safety evaluator and dated release evidence | 58 evaluator tests; all holdout documents retain NO-GO decisions |

The remaining governance/documentation commit records the final local
checkpoint. Remote CI, branch reconciliation, independent legal-quality
holdouts, and production operations remain release gates.

## Proposed stacked commits

Each commit must pass its listed gate before the next commit is formed. If a
hunk cannot pass independently, move it together with the smallest owning
contract rather than weakening a test.

### 1. Production runtime boundaries

Scope:

- API configuration, database lifecycle, runtime identity, LLM preflight,
  readiness, metrics, privacy, admission control, and failure behavior.
- Browser-to-API server proxy, request guard, session budgeting, and disconnect
  cancellation.
- Base/production Compose settings and environment documentation.
- Corresponding configuration, database, LLM, readiness, privacy, admission,
  and runtime-identity tests.

Primary paths:

- `.env.example`, `infra/docker-compose.yml`, `infra/docker-compose.prod.yml`
- `apps/api/admission.py`, `config.py`, `db.py`, `llm.py`, `metrics.py`,
  `privacy.py`, `runtime_identity.py`
- runtime/readiness hunks in `apps/api/main.py`
- `apps/web/app/api/**`, `apps/web/app/lib/request-guard.ts`
- `test_admission_control.py`, `test_config.py`, `test_db.py`, `test_llm.py`,
  `test_privacy.py`, `test_readiness.py`, `test_runtime_identity.py`

Gate:

```bash
PYTHONPATH=. .venv/bin/pytest \
  apps/api/tests/test_admission_control.py \
  apps/api/tests/test_config.py \
  apps/api/tests/test_db.py \
  apps/api/tests/test_llm.py \
  apps/api/tests/test_privacy.py \
  apps/api/tests/test_readiness.py \
  apps/api/tests/test_runtime_identity.py -q
cd apps/web && npm test && npm run type-check && npm run build
```

Then run the real Redis/PostgreSQL variants and the merged production Compose
contract.

### 2. Canonical matter and answer ownership

Scope:

- MatterPlan production, routing, incident fact extraction, guided intake,
  source-gap ownership, deterministic action contracts, and answer rendering.
- V1 and adjacent route-specific policy, including the corrected MGNREGA
  Section 19 wage / conditional Section 17 social-audit boundary.
- Corresponding plan, router, source-pack, source-gap, workflow, endpoint, and
  ownership tests.

Primary paths:

- `apps/api/authority_graph.py`, `common_workflow_contracts.py`,
  `incident_facts.py`, `intake.py`, `legal_issue_plan.py`, `local_authority.py`,
  `matter_router.py`, `pmla_asset.py`, `source_gap.py`, `source_packs.py`
- policy/rendering hunks in `apps/api/main.py`
- the matching API contract tests

Gate:

```bash
PYTHONPATH=. .venv/bin/pytest \
  apps/api/tests/test_common_workflow_contracts.py \
  apps/api/tests/test_incident_facts.py \
  apps/api/tests/test_intake.py \
  apps/api/tests/test_legal_issue_plan.py \
  apps/api/tests/test_local_authority.py \
  apps/api/tests/test_matter_router.py \
  apps/api/tests/test_plan_answer_ownership.py \
  apps/api/tests/test_source_gap.py \
  apps/api/tests/test_source_packs.py \
  apps/api/tests/test_endpoints.py -q
```

### 3. Immutable authority registry and corpus repair

Scope:

- Authority migrations `0008` through `0029` and their registry-owned workflow
  declarations.
- Registry ingestion, exact projection, promotion, quarantine, and repair
  tooling.
- Rollback, idempotence, wheel-content, natural-retrieval, and provenance tests.

Primary paths:

- `packages/authority_registry/**`
- `scripts/promote_source_pack_sections.py`,
  `quarantine_misanchored_act_chunks.py`, `repair_canonical_act_chunks.py`,
  `repair_lok_adalat_retirement_metadata.py`,
  `repair_stage37_verified_authority_chunks.py`, `verify_provenance.py`
- authority migration/registry/provenance tests

Gate:

```bash
PYTHONPATH=. .venv/bin/pytest \
  apps/api/tests/test_authority_migrations.py \
  apps/api/tests/test_authority_registry.py \
  apps/api/tests/test_authority_migration_stack.py \
  apps/api/tests/test_promote_source_pack_sections.py \
  apps/api/tests/test_provenance_document_scope.py \
  apps/api/tests/test_provenance_repair_scripts.py \
  apps/api/tests/test_repair_stage37_verified_authority_chunks.py -q
```

Build the wheel and run `scripts/check_authority_registry_wheel.py` before the
commit is accepted.

### 4. Browser matter-plan and stream contract

Scope:

- MatterPlan validation, event typing, SSE lifecycle, answer visibility,
  intake/source-gap display, and index/readiness status.
- Frontend contract tests and the production Next.js configuration.

Primary paths:

- `apps/web/app/components/answer-view.tsx`
- `apps/web/app/components/index-status.tsx`
- `apps/web/app/lib/matter-plan.ts`, `matter-plan.test.mjs`, `sse.ts`, `types.ts`
- `apps/web/next.config.mjs`

Gate:

```bash
cd apps/web
npm test
npm run type-check
npm run build
```

### 5. Evaluation and release evidence

Scope:

- Timed evaluation, legal-safety scoring, ownership audit inputs, holdout
  guards, and final dated reports.
- Evidence documents must identify candidate fingerprints and distinguish
  synthetic prompts from independent human/legal review.

Primary paths:

- `scripts/eval_timed_100.py`, `scripts/legal_safety_eval.py`
- evaluation tests and the dated production holdout/admission reports
- relevant recovery TODO evidence entries

Gate:

```bash
PYTHONPATH=. .venv/bin/pytest \
  apps/api/tests/test_eval_timed_100.py \
  apps/api/tests/test_legal_safety_eval.py \
  apps/api/tests/test_eval_common_user_gate.py \
  apps/api/tests/test_launch_holdout_gate.py \
  apps/api/tests/test_substance_oracle_eval.py -q
```

### 6. Release governance and reproducibility

Scope:

- README/Makefile accuracy, architecture/recovery documentation, production
  readiness roadmap, changeset map, and release-inventory tooling.

Primary paths:

- `README.md`, `Makefile`, `AGENTS.md`
- `docs/ARCHITECTURE_KNOWLEDGE_BASE.md`, `PRODUCT_RECOVERY_TODO.md`,
  `PRODUCTION_READINESS_PLAN_20260801.md`, this file
- `scripts/release_change_inventory.py` and its tests

Gate:

```bash
PYTHONPATH=. .venv/bin/pytest apps/api/tests/test_release_change_inventory.py -q
.venv/bin/ruff check scripts/release_change_inventory.py \
  apps/api/tests/test_release_change_inventory.py
git diff --check
```

## Final integration gate

After the stacked commits are assembled on a temporary integration branch:

```bash
PYTHONPATH=. .venv/bin/pytest apps/api/tests \
  -m "not needs_stack and not needs_models and not needs_eval_data" -q
PYTHONPATH=. .venv/bin/pytest apps/api/tests -m needs_stack -q
PYTHONPATH=. .venv/bin/pytest apps/api/tests -m needs_models -q
PYTHONPATH=. .venv/bin/pytest apps/api/tests -m needs_eval_data -q
cd apps/web && npm test && npm run type-check && npm run build
```

Also require the release wheel check, production Compose validation, live deep
readiness, clean worktree, and remote CI on the exact integration commit.

## Commit-safety rules

- Preserve pre-existing work; do not reset or discard hunks to simplify the
  split.
- Review staged diffs before every commit.
- Do not mix generated corpus/evaluation data or secrets into Git.
- Do not count a focused green test as proof for a broad commit.
- Do not merge to `main` until all stacked commits and the final integration
  gate pass on the exact head.
