#!/bin/sh
# Poll GitHub; rebuild the stack only when origin/main actually moved.
# Installed as a cron job by scripts/bootstrap_server.sh (every 5 min).
set -eu
APP_DIR="${APP_DIR:-/opt/seo-builder/app}"
cd "$APP_DIR"

git fetch --quiet origin main
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
[ "$LOCAL" = "$REMOTE" ] && exit 0

echo ">> new commit ${REMOTE} - deploying $(date -u +%FT%TZ)"
git reset --hard origin/main
docker compose up -d --build
docker image prune -f >/dev/null

sleep 3
curl -sk -o /dev/null -w "healthz: %{http_code}\n" https://localhost:8443/healthz \
  || echo "WARN: healthz not reachable on :8443"
echo ">> deploy done: $(date -u +%FT%TZ)"
