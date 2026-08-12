#!/usr/bin/env bash
# R/I/A/O category: ACT — scope: server-stop
# Stop the backgrounded Munnin started by start-server.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -f qa/.munnin.pid ]; then
  PID="$(cat qa/.munnin.pid)"
  # Windows/git-bash: taskkill is more reliable than kill for the uvicorn child tree.
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$PID" //T //F >/dev/null 2>&1 || true
  else
    kill "$PID" 2>/dev/null || true
  fi
  rm -f qa/.munnin.pid
  echo "stop: munnin (pid $PID) stopped"
else
  echo "stop: no qa/.munnin.pid — nothing to stop"
fi
