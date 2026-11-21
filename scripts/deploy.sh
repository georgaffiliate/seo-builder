#!/bin/sh
# Rebuild step on the server. Called by GitHub Actions (after rsync) or by hand.
# Code is already in APP_DIR (rsync or manual clone); this only rebuilds the stack.
set -eu
APP_DIR="${APP_DIR:-/opt/seo-builder/app}"
SERVER_IP="${SERVER_IP:-84.200.80.37}"
cd "$APP_DIR"

echo ">> self-signed TLS cert (only if missing)"
if [ ! -f certs/cert.pem ]; then
    mkdir -p certs
    openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
        -keyout certs/key.pem -out certs/cert.pem \
        -subj "/CN=seo-builder" \
        -addext "subjectAltName=DNS:localhost,DNS:seo-builder-tls,DNS:seo-builder,IP:127.0.0.1,IP:${SERVER_IP}" \
        >/dev/null 2>&1
    chmod 600 certs/key.pem
    echo "   generated for: localhost, seo-builder-tls, ${SERVER_IP}"
else
    echo "   already exists - kept"
fi

echo ">> docker compose up -d --build"
docker compose up -d --build

echo ">> prune dangling images"
docker image prune -f >/dev/null

echo ">> health check (up to 5 tries)"
ok=0
for i in 1 2 3 4 5; do
    sleep 3
    code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/healthz || true)
    echo "   try $i: healthz ${code}"
    [ "$code" = "200" ] && { ok=1; break; }
done
[ "$ok" = "1" ] || { echo "!! healthz not reachable on :8443"; exit 1; }

echo ">> deploy done: $(date -u +%FT%TZ)"
