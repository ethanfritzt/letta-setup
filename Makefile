.PHONY: help setup agents up down logs restart clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: copy env template and install Python deps
	@test -f .env || (cp env.template .env && echo "Created .env from template — edit it with your keys")
	@test -f .env && echo ".env already exists, skipping copy" || true
	pip install letta-client

agents: ## Create/update all Letta agents (idempotent)
	python -m agents.create_all

up: ## Start all services (Letta server, sandbox, Discord bot)
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

restart: ## Restart all services
	docker compose restart

status: ## Show status of all services
	docker compose ps

clean: ## Remove persisted Letta data (WARNING: deletes all agents and memory)
	@echo "This will delete all Letta data at ~/.letta/.persist/pgdata"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && \
		docker compose down -v && rm -rf ~/.letta/.persist/pgdata && \
		echo "Cleaned." || echo "Aborted."
