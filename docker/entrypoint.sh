#!/bin/sh
set -e

# Seed runtime dirs from image snapshots on first use.
# Named docker volumes start empty; without this the static content banks
# and the plan history baked into the image would be shadowed by the mount.
cp -Rn /app/content-dist/. /app/content/ 2>/dev/null || true
cp -Rn /app/plans-dist/.  /app/plans/  2>/dev/null || true

exec python3 server/api.py
