"""``python -m munnin.migrate`` — inspect and apply the store's schema migrations.

The server applies pending migrations automatically at startup. This is the same runner
run deliberately, with each step visible, so a deploy can migrate a database before the
new code boots and an operator can see exactly what is pending.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from munnin.configuration.config import load_config
from munnin.data_entities.schema_migrations import apply_migrations, known, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Schema migrations for the Valaskjalf store.")
    parser.add_argument("command", choices=["status", "apply"], nargs="?", default="status")
    parser.add_argument("--db", default=None, help="database path (default: MUNNIN_DB_PATH)")
    args = parser.parse_args(argv)

    db_path = args.db or str(load_config().db_path)
    print(f"database: {db_path}")

    if args.command == "status" and not (Path(db_path).exists() or db_path == ":memory:"):
        for migration in known():
            print(f"  {migration.name:<34} pending (no database yet)")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        if args.command == "apply":
            ran = apply_migrations(conn)
            if ran:
                for name in ran:
                    print(f"applied {name}")
            else:
                print("already up to date")
            return 0
        for migration, state in status(conn):
            print(f"  {migration.name:<34} {state}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
