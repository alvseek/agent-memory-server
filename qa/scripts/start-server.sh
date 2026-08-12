#!/usr/bin/env bash
# R/I/A/O category: ACT — scope: server
# Boot Munnin (uvicorn) in the background. PID -> qa/.munnin.pid, log -> qa/.munnin.log.
# Stop it with qa/scripts/stop-server.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${MUNNIN_HOST:-127.0.0.1}"; PORT="${MUNNIN_PORT:-8200}"
uv run python -m munnin > qa/.munnin.log 2>&1 &
echo $! > qa/.munnin.pid
echo "act: munnin starting (pid $(cat qa/.munnin.pid)) on $HOST:$PORT — log: qa/.munnin.log"
