#!/usr/bin/env bash
# R/I/A/O category: ACT — scope: server
# Boot Munnin (uvicorn) in the background. PID -> qa/.munnin.pid, log -> qa/.munnin.log.
# Stop it with qa/scripts/stop-server.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${MUNNIN_HOST:-127.0.0.1}"; PORT="${MUNNIN_PORT:-8200}"
# Exported, because the server reads these from the environment: assigning them to shell
# variables and stopping there left the process on its own defaults, so a bench told to use
# another port quietly answered on 8200.
export MUNNIN_HOST="$HOST" MUNNIN_PORT="$PORT"
# The server requires an issuer unless local mode is chosen explicitly, and local mode is
# the bench shape (one tenant, loopback only). Without this the ACT step dies at boot with
# `AuthNotConfiguredError` — measured 2026-10-31, which is why the line is here rather than
# in a README. A caller with a real issuer exports MUNNIN_AUTH=token to override it.
export MUNNIN_AUTH="${MUNNIN_AUTH:-off}"
# Start the server through the project's own interpreter rather than `uv run`, so the pid
# recorded below is the server itself. Through a wrapper the recorded pid belongs to `uv`,
# and stopping it leaves uvicorn serving — measured 2026-10-31, after `stop-server.sh`
# reported success and the port still answered.
if [ -x .venv/Scripts/python.exe ]; then
  PYTHON=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi
"$PYTHON" -m munnin > qa/.munnin.log 2>&1 &
echo $! > qa/.munnin.pid
echo "act: munnin starting (pid $(cat qa/.munnin.pid)) on $HOST:$PORT (auth=$MUNNIN_AUTH) — log: qa/.munnin.log"
