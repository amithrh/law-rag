# law-rag — top-level Makefile
# Usage: `make help` for the full list.
.DEFAULT_GOAL := help

ROOT       := $(shell pwd)
COMPOSE    := docker compose --env-file $(ROOT)/.env -f $(ROOT)/infra/docker-compose.yml
ENVFILE    := $(ROOT)/.env

.PHONY: help env up down restart logs ps doctor psql redis-cli pull-models \
        bench-day0 ingest-slice eval clean nuke

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

env: ## Copy .env.example -> .env if missing.
	@test -f $(ENVFILE) || (cp $(ROOT)/.env.example $(ENVFILE) && echo "Created .env from .env.example — edit secrets before running stack.")
	@test -f $(ENVFILE) && echo ".env present."

up: env ## Start the data plane (postgres, redis, ollama, tei, minio).
	$(COMPOSE) up -d
	@echo ""
	@echo "Stack started. First run downloads TEI model (~2 GB) — watch: docker logs -f lawrag-tei"
	@echo "Then run: make pull-models  (Ollama LLM pulls)"
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

pull-models: ## Pull Ollama LLMs (TEI auto-pulls on container start).
	@bash $(ROOT)/scripts/pull-models.sh

bench-day0: ## Run Day-0 model-dependent benches (Q1 verifier, Q3 embedding, Q4 reranker, Q2 HNSW). Requires stack up + models pulled.
	@bash $(ROOT)/scripts/bench-day0.sh

ingest-slice: ## Ingest the slice corpus (SC + selected common-public acts + Tier-A HCs). Days 3-7 work.
	@echo "Not yet implemented — placeholder for Days 3-7."

eval: ## Run golden-set eval and dump JSON to eval/results/.
	@echo "Not yet implemented — placeholder for Days 14-15."

clean: ## Stop services and remove volumes (DANGEROUS — wipes data).
	@echo "This will delete all postgres data, model caches, and MinIO contents."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) down -v

nuke: clean ## Alias for clean.
