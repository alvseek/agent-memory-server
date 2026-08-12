#!/usr/bin/env bash
# R/I/A/O category: RESET — scope: db
# Drop the SQLite memory DB (+ WAL/SHM) back to a clean, empty state.
set -euo pipefail
cd "$(dirname "$0")/../.."
DB="${MUNNIN_DB_PATH:-data/valaskjalf-memory.db}"
rm -f "$DB" "$DB-wal" "$DB-shm"
mkdir -p "$(dirname "$DB")"
echo "reset: removed $DB (+wal/shm) — clean state"
