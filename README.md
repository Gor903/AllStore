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

### Сервис семантического поиска

`search/` — отдельный сервис (ADR 10): многоязычная модель считает эмбеддинги товаров и ищет
по смыслу. Наружу он не смотрит — отвечает только backend.

```bash
docker compose up -d search                       # модель качается один раз, ~2.2 ГБ в volume
docker compose exec search python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read())"
```

Первый старт долгий: модель скачивается и загружается в память. Дальше она живёт в томе
`fastembed-cache` и переживает пересборку образа.

Индексация фоновая: сервис раз в несколько минут обходит каталог и пересчитывает то, что
разошлось с текущим текстом товара или моделью. Разово можно попросить прямо:

```bash
docker compose exec search python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:8000/reindex',method='POST'),timeout=3600).read()"
```

Тесты сервиса гоняются на детерминированном эмбеддере, модель для них не нужна:

```bash
cd search
EMBEDDER=fake DATABASE_URL="postgresql+asyncpg://allstore:allstore@localhost:5433/allstore_test" uv run pytest
```

### Помощник покупателя

Экран `/assistant`: человек описывает словами, что ищет, модель выбирает инструмент (точный
поиск или поиск по смыслу), а ответ собирается из того, что вернул каталог.

Думает локальная модель в Ollama — без ключа, без аккаунта и без счёта за токены:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b   # ~2 ГБ, один раз
```

Backend говорит по OpenAI-совместимому протоколу, поэтому модель меняется переменными
`ASSISTANT_BASE_URL` и `ASSISTANT_MODEL` — хоть на другую локальную, хоть на хостинг с ключом
в `ASSISTANT_API_KEY`. Пустой `ASSISTANT_BASE_URL` выключает помощника: экран скажет, что он не
подключён, остальной сайт работает как обычно.

На восьми ядрах без GPU модель на 3B отвечает за несколько секунд; модель побольше (`qwen2.5:7b`)
отвечает заметно лучше и заметно дольше.

### Первый администратор и роли

Администратор на площадке ровно один, и в обычной регистрации его нет. Заводится он
идемпотентной командой из секретов окружения — `ADMIN_EMAIL` и `ADMIN_PASSWORD`. Compose
прокидывает обе переменные в контейнер, так что задать их нужно в `.env` в корне
репозитория (образец — `.env.example`, полный список переменных backend —
`infra/env/backend.env.example`):

```bash
docker compose exec backend python -m scripts.bootstrap_admin
```

Без этих двух переменных команда ничего не заведёт и честно скажет об этом.

Повторный запуск ничего не меняет и не переписывает пароль, поэтому команду можно держать
в скрипте развёртывания. Если администратор потерял пароль или сам себя запер, доступ
восстанавливается явно и только на сервере:

```bash
docker compose exec backend python -m scripts.bootstrap_admin --reset-password
```

Пароль не попадает ни в вывод команды, ни в журнал. С этапа 19 приложение делает то же самое
само при старте, так что на чистой базе ручной запуск нужен только для восстановления.

Пароль из окружения считается временным: до тех пор, пока администратор не задаст свой на
экране `/password`, остальная площадка для него закрыта. Логин и пароль меняются в
`/admin/security`, обе смены завершают все сессии и попадают в журнал.

Роль администратора не снимают — её **передают**: на экране `/admin` у модератора есть
кнопка «Передать админку», которая в одном действии делает преемника администратором, а
нажавшего — модератором. Площадка при этом ни на мгновение не остаётся без управления.

Модератором становятся только по персональному приглашению: `/admin/moderators` → «Создать
приглашение». Ссылка показывается один раз (в базе лежит только отпечаток), работает один
раз и только для того адреса, на который выписана. Письма пока не отправляются (ADR 5
открыт) — ссылку передаёт администратор, и экран об этом говорит.

Аварийный путь, когда администратора ещё нет и приглашать некому:

```bash
docker compose exec backend python -m scripts.grant_role someone@example.com secret moderator
```

Роль `admin` эта команда не выдаёт.

Кто что может — `docs/adr/0015-roles-and-moderation.md` и проверка маршрут за маршрутом в
`backend/tests/integration/test_access_matrix.py`.

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

Браузер проходит путь «регистрация продавца → магазин → товар → модерация → каталог →
правка одобренного товара → каталог держит прежнюю версию → одобрение правки» через nginx,
то есть по тому же стеку, которым пользуется человек. Подробности — в
`frontend/e2e/README.md`.

Сценарий рассчитан на **пустую** базу, как в CI: на стенде с данными очередь модератора
начинается с чужих заявок, и товар сценария оказывается на второй странице. Локально стек
переводится на отдельную базу переменной `POSTGRES_DB`.

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
