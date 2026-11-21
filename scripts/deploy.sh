#!/bin/sh
# Rebuild step on the server. Called by GitHub Actions (after rsync) or by hand.
# Code is already in APP_DIR (rsync or manual clone); this only rebuilds the stack.
set -eu
APP_DIR="${APP_DIR:-/opt/seo-builder/app}"
cd "$APP_DIR"

echo ">> docker compose up -d --build"
docker compose up -d --build

echo ">> prune dangling images"
docker image prune -f >/dev/null

echo ">> health check"
sleep 3
curl -sk -o /dev/null -w "healthz: %{http_code}\n" https://localhost:8443/healthz \
  || echo "WARN: healthz not reachable on :8443"

echo ">> deploy done: $(date -u +%FT%TZ)"
