#!/usr/bin/env bash
# Regenerates frontend types from the backend OpenAPI schema, see docs/adr/0004-api-types-generation.md
# The generator version comes from frontend/package.json so CI and developers agree on it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
schema="$(mktemp -t allstore-openapi-XXXXXX.json)"
trap 'rm -f "$schema"' EXIT

version="$(node -p "require('$root/frontend/package.json').devDependencies['openapi-typescript']")"

(cd "$root/backend" && uv run python -m scripts.export_openapi) > "$schema"
npx --yes "openapi-typescript@$version" "$schema" -o "$root/frontend/src/lib/api-types.ts"
