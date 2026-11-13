# Цели lint-* / unit-* / integration-back — это ровно то, что зовёт CI. Один список команд на
# «линт» и на «тесты», а не два: добавить линтер значит дописать строку здесь, и она тут же
# работает и в CI, и локально, и в pre-commit. Workflow при этом не меняется.
.PHONY: up down logs ps rebuild migrate revision api-types api-types-fresh \
	lint-back lint-front lint-search unit-back integration-back unit-front unit-search \
	coverage-back \
	backend-check frontend-check check e2e backup restore-drill

E2E_MODERATOR_EMAIL ?= e2e-moderator@e2e.allstore.am
E2E_MODERATOR_PASSWORD ?= e2e-password-1

# прогон идёт на отдельной базе: дефолт DATABASE_URL смотрит на базу стенда, и тесты её травят
TEST_DATABASE_URL ?= postgresql+asyncpg://allstore:allstore@localhost:5433/allstore_test

# Экспорт схемы импортирует приложение, а оно проверяет настройки на импорте. Значения
# заведомо негодные и ровно те же, что в CI: ничего из этого никуда не ходит, а генератору
# нужен импортируемый app, не рабочая конфигурация.
SCHEMA_ENV = APP_ENV=local \
	SECRET_KEY=ci-secret-value-at-least-32-characters \
	DATABASE_URL="$(TEST_DATABASE_URL)" \
	S3_ENDPOINT_URL=http://localhost:9000 S3_ACCESS_KEY=ci S3_SECRET_KEY=ci S3_BUCKET=allstore-ci

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

lint-back: ## стиль, типы и свежесть сгенерированного
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy
	$(MAKE) api-types-fresh

lint-front:
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run typecheck

lint-search:
	cd search && uv run ruff check .
	cd search && uv run ruff format --check .
	cd search && uv run mypy

# Базы здесь нет намеренно: ни один файл в tests/unit к ней не обращается, и это стоит
# держать правдой — прогон за восемь секунд без сервисов ловит логику раньше всего прочего.
# `--cov-fail-under=0` глушит порог здесь намеренно: гейт один и стоит на объединённом
# отчёте (цель coverage-back). Применённый к половине набора, он мерил бы не то и падал бы
# всегда — unit-тесты сами по себе дают около шестидесяти процентов, и это нормально.
unit-back:
	cd backend && COVERAGE_FILE=.coverage.unit uv run pytest -m "not integration" \
		--cov --cov-report=term-missing --cov-fail-under=0

integration-back:
	cd backend && $(SCHEMA_ENV) uv run alembic upgrade head
	cd backend && DATABASE_URL="$(TEST_DATABASE_URL)" COVERAGE_FILE=.coverage.integration \
		uv run pytest -m integration --cov --cov-report=term-missing --cov-fail-under=0

# с покрытием: пороги живут в vitest.config.mts и без этого флага не применяются
unit-front:
	cd frontend && npm run test:coverage

# Схема принадлежит бэкенду: сервис поиска читает её, а не заводит свою, поэтому миграции
# накатываются отсюда — миграция, ломающая поиск, ловится здесь.
unit-search:
	cd backend && $(SCHEMA_ENV) uv run alembic upgrade head
	cd search && DATABASE_URL="$(TEST_DATABASE_URL)" EMBEDDER=fake uv run pytest

# Единственное место, где порог применяется: два прогона складываются, и число проверяется
# по всему проекту. `fail_under` живёт в backend/pyproject.toml.
coverage-back:
	cd backend && uv run coverage combine .coverage.unit .coverage.integration
	cd backend && uv run coverage report

backend-check: lint-back unit-back integration-back coverage-back

frontend-check: lint-front unit-front

check: backend-check frontend-check

e2e: ## поднять стек и прогнать сквозной сценарий (нужен браузер: npx playwright install chromium)
	docker compose up --build -d --wait
	docker compose exec -T backend python -m scripts.grant_role $(E2E_MODERATOR_EMAIL) $(E2E_MODERATOR_PASSWORD) moderator --reset-password
	# адрес спрашивается у самого стека: HTTP_PORT переопределяется в .env
	port=$$(docker compose port nginx 80 | cut -d: -f2); cd frontend && E2E_BASE_URL=http://localhost:$$port npx playwright test

api-types:
	$(SCHEMA_ENV) ./scripts/gen-api-types.sh

# Проверка свежести сгенерированного файла, а не тест: нужен импортируемый app, но не база.
# Падает у того PR, который сменил схему, — у него же и перегенерировать.
api-types-fresh:
	$(SCHEMA_ENV) ./scripts/gen-api-types.sh
	git diff --exit-code -- frontend/src/lib/api-types.ts

backup: ## снимок базы в объектное хранилище (ADR 29)
	./infra/backup/backup.sh

restore-drill: ## развернуть последний снимок рядом и сверить с источником
	./infra/backup/restore-drill.sh
