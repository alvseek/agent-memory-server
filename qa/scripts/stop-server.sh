#!/usr/bin/env bash
# R/I/A/O category: ACT — scope: server-stop
# Stop the backgrounded Munnin started by start-server.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -f qa/.munnin.pid ]; then
  PID="$(cat qa/.munnin.pid)"
  # `kill` first, because `$!` in this shell is a POSIX pid and that is what `kill` takes.
  # `taskkill` wants a Windows pid, so handing it the same number can signal an unrelated
  # process and report success while the server keeps serving — measured 2026-10-31.
  kill "$PID" 2>/dev/null || true
  sleep 1
  if kill -0 "$PID" 2>/dev/null && command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$PID" //T //F >/dev/null 2>&1 || true
  fi
  rm -f qa/.munnin.pid
  echo "stop: munnin (pid $PID) stopped"
else
  echo "stop: no qa/.munnin.pid — nothing to stop"
fi
