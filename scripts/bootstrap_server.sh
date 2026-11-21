#!/bin/sh
# Run once on the server. Idempotent - safe to re-run.
# Sets up: docker, a read-only GitHub deploy key, the repo, cron auto-deploy.
# You only do by hand: paste the printed public key into GitHub (Deploy keys)
# and fill in .env.
set -eu
APP_DIR="${APP_DIR:-/opt/seo-builder/app}"
REPO_URL="${REPO_URL:-git@github.com:georgaffiliate/seo-builder.git}"
KEY="$HOME/.ssh/seo_builder_deploy"

echo "== 1/5 docker"
command -v docker >/dev/null 2>&1 || { curl -fsSL https://get.docker.com | sh; }
echo "   $(docker --version)"

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow OpenSSH >/dev/null 2>&1 || true
    ufw allow 8443/tcp >/dev/null 2>&1 || true
    echo "   ufw: 22 + 8443/tcp allowed"
fi

echo "== 2/5 deploy key"
if [ ! -f "$KEY" ]; then
    mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
    ssh-keygen -t ed25519 -N "" -f "$KEY" -C "seo-builder-deploy" -q
fi
if ! grep -q "seo_builder_deploy" "$HOME/.ssh/config" 2>/dev/null; then
    printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$KEY" \
        >> "$HOME/.ssh/config"
    chmod 600 "$HOME/.ssh/config"
fi
echo ""
echo "   ADD THIS PUBLIC KEY TO GITHUB:"
echo "   repo -> Settings -> Deploy keys -> Add deploy key (read-only):"
echo ""
sed 's/^/     /' "$KEY.pub"

echo "== 3/5 repo"
if [ ! -d "$APP_DIR/.git" ]; then
    mkdir -p "$(dirname "$APP_DIR")"
    if ! git clone "$REPO_URL" "$APP_DIR" 2>/dev/null; then
        echo "   !! clone failed - the deploy key is not on GitHub yet."
        echo "      Add the key printed above (repo -> Settings -> Deploy keys),"
        echo "      then re-run this script - it is idempotent."
        exit 1
    fi
fi
cd "$APP_DIR"
git fetch origin main
git reset --hard origin/main

echo "== 4/5 .env"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   created $APP_DIR/.env - fill it in: nano $APP_DIR/.env"
    echo "   (API_TOKEN / VENICE_API_KEY / PANEL_API_KEY)"
else
    echo "   .env already exists - kept as is"
fi

echo "== 5/5 cron auto-deploy (every 5 min, only rebuilds when main changed)"
CRON_LINE="*/5 * * * * $APP_DIR/scripts/poll_deploy.sh >> /var/log/seo-builder-deploy.log 2>&1"
( crontab -l 2>/dev/null | grep -v "poll_deploy.sh" ; echo "$CRON_LINE" ) | crontab -
echo "   $(crontab -l | tail -1)"

echo ""
echo "== done. next steps by hand:"
echo "   1) nano $APP_DIR/.env          (secrets)"
echo "   2) cd $APP_DIR && docker compose up -d --build"
echo "   3) curl -sk https://localhost:8443/healthz"
