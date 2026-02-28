.PHONY: up dev dev-llm down logs ps reset setup check-env up-llm pull-model

# ── Quick start ──────────────────────────────────────────────────────────────
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅  Created .env from .env.example"; \
	else \
		echo "ℹ️   .env already exists — skipping copy"; \
	fi

check-env:
	@if [ ! -f .env ]; then \
		echo "❌  No .env found. Run: make setup"; exit 1; \
	fi

# ── Production mode ──────────────────────────────────────────────────────────
up: check-env
	docker compose up -d --build
	@echo ""
	@echo "✅  Services started"
	@echo "    → Web UI:  http://localhost:$$(grep ^WEB_PORT .env | cut -d= -f2 || echo 3000)"
	@echo "    → API:     http://localhost:$$(grep ^API_PORT .env | cut -d= -f2 || echo 8000)/docs"
	@echo "    For live code editing: make dev"

# ── Dev mode (hot reload — edit code, no rebuild needed) ─────────────────────
dev: check-env
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
	@echo ""
	@echo "✅  Dev mode started (hot reload active)"
	@echo "    → Web UI:  http://localhost:$$(grep ^WEB_PORT .env | cut -d= -f2 || echo 3000)"
	@echo "    → API:     http://localhost:$$(grep ^API_PORT .env | cut -d= -f2 || echo 8000)/docs"
	@echo ""
	@echo "    Edit web/app/**     → browser refreshes automatically"
	@echo "    Edit backend/app/** → API & worker reload automatically"

dev-llm: check-env
	docker compose -f docker-compose.yml -f docker-compose.llm.yml -f docker-compose.dev.yml up -d --build
	@echo ""
	@echo "✅  Dev + Ollama started"
	@echo "    → Web UI:  http://localhost:$$(grep ^WEB_PORT .env | cut -d= -f2 || echo 3000)"

# ── LLM mode (Ollama) ────────────────────────────────────────────────────────
up-llm: check-env
	docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d --build

pull-model:
	@MODEL=$$(grep ^OLLAMA_MODEL .env | cut -d= -f2 || echo "qwen2.5-coder:7b"); \
	echo "Pulling $$MODEL ..."; \
	docker compose exec ollama ollama pull $$MODEL

# ── Utilities ────────────────────────────────────────────────────────────────
logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

down:
	docker compose down -v

reset:
	bash scripts/reset_sample_workspace.sh
