#!/usr/bin/env bash
# R/I/A/O category: OBSERVE — scope: server
# Probe the live server end-to-end. Waits for /health, then asserts the data
# read path (awaken) + the content surface (prompts/resources). Non-zero exit on any failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
BASE="http://${MUNNIN_HOST:-127.0.0.1}:${MUNNIN_PORT:-8200}"
fail=0

# wait for health (up to ~15s)
for _ in $(seq 1 30); do
  curl -sf "$BASE/health" >/dev/null 2>&1 && break
  sleep 0.5
done

probe() { # name url [needle]
  local name="$1" url="$2" needle="${3:-}" body code
  body=$(curl -s -w $'\n%{http_code}' "$url") || { echo "FAIL $name: curl error"; fail=1; return; }
  code=$(printf '%s' "$body" | tail -n1)
  body=$(printf '%s' "$body" | sed '$d')
  if [ "$code" != "200" ]; then echo "FAIL $name: HTTP $code"; fail=1; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$body" | grep -q "$needle"; then
    echo "FAIL $name: '$needle' missing from body"; fail=1; return
  fi
  echo "PASS $name (200)"
}

probe health    "$BASE/health"
probe awaken    "$BASE/api/awaken?agent_id=meta"
probe prompts   "$BASE/api/prompts"                     update-episodic
probe prompt1   "$BASE/api/prompts/update-episodic"     'insert('
probe resources "$BASE/api/resources"                   episodic-entry-template

[ "$fail" -eq 0 ] && echo "SMOKE OK" || echo "SMOKE FAILED"
exit $fail
