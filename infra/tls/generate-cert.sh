#!/usr/bin/env bash
# A certificate for the https stand, see infra/docker-compose.https.yml.
#
# Self-signed and wildcard, because the thing being exercised is the platform's own behaviour
# over https — `__Host-` cookies, `Secure`, CSRF `Origin`, storefront CORS — and none of that
# depends on who signed the certificate. A browser will warn once and let you through; for a
# browser that does not warn, use mkcert instead and point the two paths below at its output.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
domain="${BASE_DOMAIN:-allstore.localhost}"

if [[ -f "$here/$domain.crt" && "${FORCE:-}" != "1" ]]; then
    echo "$domain.crt already exists; FORCE=1 to replace it" >&2
    exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout "$here/$domain.key" -out "$here/$domain.crt" \
    -subj "/CN=$domain" \
    -addext "subjectAltName=DNS:$domain,DNS:*.$domain" \
    2>/dev/null

# nginx runs as a user that is not the one who generated these
chmod 644 "$here/$domain.key" "$here/$domain.crt"
echo "$here/$domain.crt"
