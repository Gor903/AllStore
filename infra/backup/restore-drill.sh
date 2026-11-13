#!/usr/bin/env bash
# Проверка, что снимок восстанавливается, — а не что он создался.
#
# Бэкап, который никто ни разу не разворачивал, это не бэкап, а файл. Проверяется он в тот
# день, когда проверять уже поздно, и выясняется что-нибудь вроде отсутствующего расширения
# или недобравшегося до конца пайпа.
#
# Скрипт берёт последний снимок, разворачивает его в отдельную базу рядом, сверяет с
# источником и базу убирает. Боевую базу он не трогает ни на одном шаге.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

db="${POSTGRES_DB:-allstore}"
user="${POSTGRES_USER:-allstore}"
bucket="${BACKUP_BUCKET:-allstore-backups}"
scratch="${db}_restore_drill"

access="${MINIO_ROOT_USER:-minioadmin}"
secret="${MINIO_ROOT_PASSWORD:-minioadmin}"
mc() {
    docker compose exec -T -e "MC_HOST_local=http://$access:$secret@127.0.0.1:9000" minio mc "$@"
}
psql_source() { docker compose exec -T postgres psql -qtAX -U "$user" -d "$db" -c "$1"; }
# stderr гасится: на битом снимке запрос падает сам, и вердикт должен быть один, а не
# psql-трассировка поверх него
psql_drill() { docker compose exec -T postgres psql -qtAX -U "$user" -d "$scratch" -c "$1" 2>/dev/null; }

latest="$(mc ls --json "local/$bucket/$db/" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p' | sort | tail -1)"
if [[ -z "$latest" ]]; then
    echo "в local/$bucket/$db/ нет ни одного снимка" >&2
    exit 1
fi
echo "снимок: $latest"

cleanup() {
    docker compose exec -T postgres psql -qtAX -U "$user" -d postgres \
        -c "DROP DATABASE IF EXISTS $scratch;" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
docker compose exec -T postgres psql -qtAX -U "$user" -d postgres \
    -c "CREATE DATABASE $scratch OWNER $user;" >/dev/null

# --no-owner: база учений принадлежит тому, кто её создал, а не тому, кто владел исходной
mc cat "local/$bucket/$db/$latest" \
    | docker compose exec -T postgres pg_restore --no-owner -U "$user" -d "$scratch" 2>&1 \
    | grep -vE '^$' | tail -5 || true

failed=0

# Строки сверять с источником нельзя: между снимком и прогоном живая база меняется, и такая
# сверка «падала» бы на исправном бэкапе. Проверяется то, что от снимка действительно
# зависит, — что он развернулся и развернулся целиком.
expect() {
    local what="$1" query="$2" want="$3"
    local got
    # `|| true`: с pipefail неудачный запрос оборвал бы скрипт здесь же, и вердикт о том,
    # что именно не так со снимком, никто бы не увидел
    got="$(psql_drill "$query" | tr -d '[:space:]' || true)"
    if [[ "$got" == "$want" ]]; then
        echo "  $what: $got"
    else
        echo "  $what: $got, ожидалось $want — СНИМОК НЕПОЛНЫЙ"
        failed=1
    fi
}

schema_source="$(psql_source "select version_num from alembic_version" | tr -d '[:space:]')"
tables_source="$(psql_source \
    "select count(*) from information_schema.tables where table_schema='public'" | tr -d '[:space:]')"

echo "развёрнутый снимок:"
# Версия схемы и набор таблиц — то, что между снимком и прогоном не меняется само: миграция
# в этом промежутке событие редкое и само по себе достойное внимания.
expect "версия схемы" "select version_num from alembic_version" "$schema_source"
expect "таблиц" \
    "select count(*) from information_schema.tables where table_schema='public'" "$tables_source"

# Строки — не сверка, а то, по чему человек видит, что развернулись данные, а не пустая схема.
echo "  строк: аккаунтов $(psql_drill 'select count(*) from users' | tr -d '[:space:]')," \
    "магазинов $(psql_drill 'select count(*) from stores' | tr -d '[:space:]')," \
    "товаров $(psql_drill 'select count(*) from products' | tr -d '[:space:]')"

if [[ "$failed" -ne 0 ]]; then
    echo "прогон не сошёлся" >&2
    exit 1
fi
echo "снимок разворачивается целиком"
