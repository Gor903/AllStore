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

## Миграции

```bash
make migrate                     # alembic upgrade head в контейнере backend
make revision m="add products"   # автогенерация ревизии
```

Схема БД меняется только миграциями, у каждой ревизии обязателен рабочий `downgrade()`.
