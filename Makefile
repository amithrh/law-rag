# law-rag — top-level Makefile
# Usage: `make help` for the full list.
.DEFAULT_GOAL := help

ROOT       := $(shell pwd)
COMPOSE    := docker compose --env-file $(ROOT)/.env -f $(ROOT)/infra/docker-compose.yml
ENVFILE    := $(ROOT)/.env
UV         ?= uv

.PHONY: help env up down restart logs ps doctor psql redis-cli pull-models \
        bench-day0 clean nuke sync test-api test-api-ci test-models \
        test-eval-data test-workflows test-eval-gates typecheck-web verify \
        api-dev web-dev corpus-manifest seed-ci-corpus promote-source-packs

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

env: ## Copy .env.example -> .env if missing.
	@test -f $(ENVFILE) || (cp $(ROOT)/.env.example $(ENVFILE) && echo "Created .env from .env.example — edit secrets before running stack.")
	@test -f $(ENVFILE) && echo ".env present."

up: env ## Start the Mac-dev data plane (postgres, redis, ollama, minio).
	$(COMPOSE) up -d
	@echo ""
	@echo "Stack started. Mac dev uses the Ollama container for LLMs and embeddings."
	@echo "Then run: make pull-models  (Ollama model pulls)"
	@echo "Then run: make doctor       (health check)"

down: ## Stop services (keeps volumes).
	$(COMPOSE) down

restart: ## Restart services.
	$(COMPOSE) restart

logs: ## Tail compose logs (Ctrl-C to exit).
	$(COMPOSE) logs -f

ps: ## Show service status.
	$(COMPOSE) ps

doctor: ## Run health checks (services, extensions, models, buckets).
	@bash $(ROOT)/scripts/doctor.sh

psql: ## Open a psql shell against the law-rag db.
	@set -a; . $(ENVFILE); set +a; \
	docker exec -it lawrag-postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

redis-cli: ## Open a redis-cli shell.
	docker exec -it lawrag-redis redis-cli

pull-models: ## Pull LLM and embedding models into the Mac-dev Ollama container.
	@bash $(ROOT)/scripts/pull-models.sh

sync: ## Install Python development dependencies from uv.lock.
	$(UV) sync --extra dev --frozen

test-api: ## Run the FastAPI/API regression suite.
	PYTHONPATH=. $(UV) run pytest apps/api/tests -q

test-api-ci: ## Run clean-clone deterministic tests without corpus, models, or private eval data.
	PYTHONPATH=. $(UV) run pytest apps/api/tests \
		-m "not needs_stack and not needs_models and not needs_eval_data" -q

test-models: ## Run model-backed integration tests using local weights/runtime.
	PYTHONPATH=. $(UV) run pytest apps/api/tests -m needs_models -q

test-eval-data: ## Run tests that validate ignored local eval datasets.
	PYTHONPATH=. $(UV) run pytest apps/api/tests -m needs_eval_data -q

test-workflows: ## Run deterministic answer-owner and authority-contract checks.
	PYTHONPATH=. $(UV) run pytest apps/api/tests/test_common_workflow_contracts.py -q

test-eval-gates: ## Test eval scoring, holdout guards, and substance-oracle contracts.
	PYTHONPATH=. $(UV) run pytest \
		apps/api/tests/test_eval_common_user_gate.py \
		apps/api/tests/test_launch_holdout_gate.py \
		apps/api/tests/test_substance_oracle_eval.py \
		-m "not needs_eval_data" -q

typecheck-web: ## Type-check the Next.js frontend.
	cd $(ROOT)/apps/web && npm ci && npm run type-check

verify: ## Run the current full local quality gate.
	$(MAKE) test-api
	$(MAKE) typecheck-web

api-dev: ## Run the API locally on http://127.0.0.1:8000.
	PYTHONPATH=. $(UV) run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload

web-dev: ## Run the web app locally on http://127.0.0.1:3000.
	cd $(ROOT)/apps/web && npm run dev

corpus-manifest: ## Write a DB-backed corpus/runtime snapshot to reports/.
	PYTHONPATH=. $(UV) run python scripts/corpus_manifest.py --output reports/corpus-manifest.json

seed-ci-corpus: env ## Load one synthetic row for clean-clone/API smoke tests only.
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) exec -T postgres psql -U lawrag -d lawrag \
		-f /dev/stdin < $(ROOT)/infra/postgres/ci-seed.sql

promote-source-packs: env ## Promote hash-pinned official Act sections before a production release.
	PYTHONPATH=$(ROOT) $(UV) run python $(ROOT)/scripts/promote_source_pack_sections.py

bench-day0: ## Run Day-0 model-dependent benches (Q1 verifier, Q3 embedding, Q4 reranker, Q2 HNSW). Requires stack up + models pulled.
	@bash $(ROOT)/scripts/bench-day0.sh

clean: ## Stop services and remove volumes (DANGEROUS — wipes data).
	@echo "This will delete all postgres data, model caches, and MinIO contents."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) down -v

nuke: clean ## Alias for clean.
