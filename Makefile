.PHONY: up down logs ps rebuild migrate revision api-types backend-check frontend-check check e2e

E2E_MODERATOR_EMAIL ?= e2e-moderator@e2e.allstore.am
E2E_MODERATOR_PASSWORD ?= e2e-password-1

up: ## поднять весь локальный стек
	docker compose up --build -d

down: ## остановить стек (данные в volume сохраняются)
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

rebuild:
	docker compose build --no-cache

migrate:
	docker compose exec backend alembic upgrade head

revision:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

backend-check:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest

frontend-check:
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test

check: backend-check frontend-check

e2e: ## поднять стек и прогнать сквозной сценарий (нужен браузер: npx playwright install chromium)
	docker compose up --build -d --wait
	docker compose exec -T backend python -m scripts.grant_role $(E2E_MODERATOR_EMAIL) $(E2E_MODERATOR_PASSWORD) moderator --reset-password
	# адрес спрашивается у самого стека: HTTP_PORT переопределяется в .env
	port=$$(docker compose port nginx 80 | cut -d: -f2); cd frontend && E2E_BASE_URL=http://localhost:$$port npx playwright test

api-types:
	./scripts/gen-api-types.sh
