# AllStore.am

Монорепозиторий платформы AllStore.am: общий каталог и магазины на субдоменах.

Документы проекта — в `docs/`:

- `docs/AllStore_build_plan.md` — инженерный план сборки MVP (стек, архитектура, этапы).
- `docs/AllStore_acceptance_criteria.md` — acceptance criteria по задачам и журнал выполнения.
- `docs/adr/` — architecture decision records.

## Стек

Backend — Python 3.13 / FastAPI / SQLAlchemy 2 (async) / Alembic / PostgreSQL.
Frontend — Next.js (App Router) / TypeScript strict / Tailwind.
Инфраструктура — Docker Compose, Nginx, S3-совместимое хранилище (MinIO локально).

## Запуск локально одной командой

```bash
docker compose up --build
```

Поднимутся `postgres`, `minio`, `backend` (миграции применяются при старте), `frontend`, `nginx`.
Эквивалент через Makefile — `make up` (то же самое, но в фоне).

| Адрес                                          | Что это                               |
| ---------------------------------------------- | ------------------------------------- |
| http://localhost:8080                          | витрина (frontend через nginx)        |
| http://localhost:8080/health                   | health-check backend                  |
| http://localhost:8080/docs                     | OpenAPI-документация (только в dev)   |
| http://localhost:9001                          | консоль MinIO (minioadmin/minioadmin) |
| postgresql://allstore:allstore@localhost:5433/ | PostgreSQL с хоста                    |

Остановить — `docker compose down` (данные остаются в volume) или `make down`.

### Переменные окружения

Дефолтов в `compose.yaml` достаточно для локального запуска, файл `.env` не обязателен.

- `.env.example` (корень) — порты и учётные данные dev-стека; скопируйте в `.env`, чтобы
  переопределить (например, `HTTP_PORT=8081`, если 8080 занят).
- `infra/env/backend.env.example` — полный список переменных backend; нужен при запуске
  backend вне docker (копируется в `backend/.env`) и как чек-лист для staging/prod.
- `infra/env/frontend.env.example` — то же для frontend (копируется в `frontend/.env.local`).

Секреты в репозиторий не коммитятся: `.env` и `infra/env/*.env` в `.gitignore`.

## Разработка без docker

```bash
# backend
cd backend && uv sync && uv run uvicorn app.main:app --reload

# frontend
cd frontend && npm ci && npm run dev
```

## Проверки перед коммитом

```bash
make check          # backend + frontend целиком
make backend-check  # ruff + ruff format + mypy strict + pytest
make frontend-check # eslint + prettier + tsc --noEmit + vitest
```

Установить git-хук (запускает те же линтеры на commit):

```bash
uv tool install pre-commit   # или pipx install pre-commit
pre-commit install
```

### Наполнение стенда данными

```bash
docker compose exec backend python -m scripts.seed_demo   # четыре витрины, всё через публичный API
docker compose exec backend python -m scripts.seed_bulk   # ~60 магазинов и ~2000 товаров, прямо в базу
```

`seed_demo` показывает, как данные проходят через приложение; `seed_bulk` нужен, когда
важен объём — поиск, пагинация, очереди модератора. Всё, что он создаёт, живёт на домене
`@fake.allstore.am`, и `--reset` удаляет только это. Пароль у всех аккаунтов обоих
скриптов — `demo-password-1`.

### Сквозной сценарий (e2e)

```bash
cd frontend && npx playwright install chromium   # один раз
make e2e                                         # поднимет стек и прогонит сценарий
```

Браузер проходит путь «регистрация продавца → магазин → товар → модерация → каталог»
через nginx, то есть по тому же стеку, которым пользуется человек. Подробности — в
`frontend/e2e/README.md`.

### Тесты backend: отдельная база и накатанные миграции

`pytest` не создаёт схему и не поднимает Postgres — он ждёт готовую базу, так же как
`backend-ci.yml`. Прогон на чистой машине даёт сотни падений `relation "users" does not
exist`, пока миграции не накатаны, а прогон на базе с данными — падения тестов, которые
ждут пустую базу (после `seed_demo` их около тридцати). И то и другое выглядит как
регрессия, хотя код ни при чём.

Поэтому тесты гоняются на **отдельной** базе, а не на той, что обслуживает
`docker compose`:

```bash
docker compose up -d postgres minio
docker compose exec postgres psql -U allstore -d postgres -c "CREATE DATABASE allstore_test OWNER allstore;"

cd backend
export DATABASE_URL="postgresql+asyncpg://allstore:allstore@localhost:5433/allstore_test"
uv run alembic upgrade head   # один раз и после каждой новой ревизии
uv run pytest
```

Остальные переменные окружения у тестов есть по умолчанию (см. `tests/conftest.py`);
`DATABASE_URL` переопределяется, потому что его дефолт указывает на базу стенда.

## Миграции

```bash
make migrate                     # alembic upgrade head в контейнере backend
make revision m="add products"   # автогенерация ревизии
```

Схема БД меняется только миграциями, у каждой ревизии обязателен рабочий `downgrade()`.

### PostgreSQL с pgvector

Стек использует образ `pgvector/pgvector:pg17` — та же PostgreSQL 17, но с расширением `vector`:
эмбеддинги товаров лежат в общей базе, отдельная векторная БД не заводится (см.
`docs/rag-first.md`, раздел 24).

Если стенд поднимался раньше на `postgres:17-alpine`, данные переживут смену образа — мажорная
версия та же. Но вместе с образом меняется libc, а с ней порядок сортировки текста, поэтому
индексы стоит пересобрать один раз:

```bash
docker compose exec postgres psql -U allstore -d allstore -c "REINDEX DATABASE allstore;"
```

То же для `allstore_test`, если тестовая база уже создана. На чистой установке делать ничего не
нужно.
