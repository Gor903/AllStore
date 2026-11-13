#!/usr/bin/env bash
# Снимок базы в объектное хранилище — туда же, где лежат фотографии товаров.
#
# Решение и его цена — docs/adr/0029-postgres-backups.md. Коротко: `pg_dump` в своём формате,
# сжатый, в бакет, отдельный от бакета с картинками. Это снимок на момент, а не
# непрерывный архив: потерять можно всё, что произошло после последнего запуска.
#
# Хранилище спрашивается у самого стека, а не задаётся отдельно: бэкап, который пишет не туда,
# куда смотрит восстановление, обнаруживается в худший день.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

db="${POSTGRES_DB:-allstore}"
user="${POSTGRES_USER:-allstore}"
bucket="${BACKUP_BUCKET:-allstore-backups}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
object="$bucket/$db/$stamp.dump"

# MC_HOST_* вместо `mc alias set`: ключи живут в окружении одной команды и не оседают в
# конфиге контейнера, который переживёт этот запуск
access="${MINIO_ROOT_USER:-minioadmin}"
secret="${MINIO_ROOT_PASSWORD:-minioadmin}"
mc() {
    docker compose exec -T -e "MC_HOST_local=http://$access:$secret@127.0.0.1:9000" minio mc "$@"
}

mc mb --ignore-existing "local/$bucket" >/dev/null

# -Fc, а не обычный SQL: так восстановление умеет идти параллельно и выбирать объекты, а не
# только проигрывать файл сверху вниз
docker compose exec -T postgres pg_dump -Fc -U "$user" "$db" | mc pipe "local/$object"

size="$(mc stat --json "local/$object" | sed -n 's/.*"size":\([0-9]*\).*/\1/p')"
if [[ -z "$size" || "$size" -lt 1024 ]]; then
    echo "снимок $object подозрительно мал ($size байт) — проверьте вручную" >&2
    exit 1
fi

# Старое убирается здесь же, а не отдельной задачей: хранилище, которое никто не подметает,
# однажды кончается, и узнают об этом по неудавшемуся бэкапу.
mc rm --recursive --force --older-than "${keep_days}d" "local/$bucket/$db/" >/dev/null || true

echo "$object ($size байт)"
