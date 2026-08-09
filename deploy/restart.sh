#!/usr/bin/env bash
# Restart Munnin on RackNerd. Reads deploy/deploy.env (gitignored).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/deploy.env"   # DEPLOY_HOST, SSH_KEY

ssh -i "$SSH_KEY" "$DEPLOY_HOST" "sudo systemctl restart munnin && systemctl status munnin --no-pager"
