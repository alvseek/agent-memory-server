#!/usr/bin/env bash
# Deploy Munnin to RackNerd (systemd + uv, no Docker).
# Reads deploy/deploy.env (gitignored). AUTHORED IN PHASE 4 — first real run is Phase 8 (cutover).
#
# Prereqs on the box (one-time): `deploy` user, uv installed, deploy/munnin.env placed,
# NOPASSWD sudo for the systemctl forms used below.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/deploy.env"   # DEPLOY_HOST, DEPLOY_PATH, SSH_KEY

echo ">> Syncing source → $DEPLOY_HOST:$DEPLOY_PATH"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data/*.db*' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  -e "ssh -i $SSH_KEY" \
  "$SCRIPT_DIR/../" "$DEPLOY_HOST:$DEPLOY_PATH/"

echo ">> Remote: install unit, sync deps, (re)start"
ssh -i "$SSH_KEY" "$DEPLOY_HOST" bash -lc "
  set -euo pipefail
  cd '$DEPLOY_PATH'
  uv sync --no-dev
  sudo cp deploy/munnin.service /etc/systemd/system/munnin.service
  sudo systemctl daemon-reload
  sudo systemctl enable munnin
  sudo systemctl restart munnin
  systemctl status munnin --no-pager || true
"
echo ">> Done. Tunnel from your machine:  ssh -N -L 8200:127.0.0.1:8200 \$DEPLOY_HOST -i \$SSH_KEY"
