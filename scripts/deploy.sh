#!/bin/sh
# Idempotent deploy step, executed on the server (by hand or by CI on push to main).
set -eu

APP_DIR="${APP_DIR:-/opt/seo-builder/app}"
cd "$APP_DIR"

echo ">> git pull"
git pull --ff-only origin main

echo ">> docker compose up -d --build"
docker compose up -d --build

echo ">> cleanup dangling images"
docker image prune -f >/dev/null

echo ">> health check"
sleep 3
curl -sk -o /dev/null -w "healthz: %{http_code}\n" https://localhost:8443/healthz \
  || echo "WARN: healthz not reachable on :8443"

echo ">> deploy done: $(date -u +%FT%TZ)"
