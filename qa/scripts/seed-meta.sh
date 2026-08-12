#!/usr/bin/env bash
# R/I/A/O category: INJECT — scope: meta (importer, single agent)
# Seed the DB from the real markdown tree for agent-meta (+ the shared layer)
# via the production importer CLI. For the full fleet, run with --all instead.
set -euo pipefail
cd "$(dirname "$0")/../.."
SOURCE="${MUNNIN_IMPORT_SOURCE:-$HOME/.claude/@agent-memory}"
DB="${MUNNIN_DB_PATH:-data/valaskjalf-memory.db}"
if [ "${1:-}" = "--all" ]; then
  echo "seed: importing the FULL fleet from $SOURCE"
  uv run python -m munnin.data_migrations.importer --all --source "$SOURCE" --db "$DB"
else
  echo "seed: importing agent-meta (+shared) from $SOURCE"
  uv run python -m munnin.data_migrations.importer --agent meta --source "$SOURCE" --db "$DB"
fi
