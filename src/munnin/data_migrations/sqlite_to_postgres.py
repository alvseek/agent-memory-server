"""One-shot migration: copy the Valaskjalf store from SQLite to PostgreSQL.

This is **not** the served path. It is a deliberate, verified, cold migration (high-wizard
decision 3): read the five tables from a SQLite file and insert them into PostgreSQL
preserving ``id`` (the FTS link and the ordering key) and the ISO date strings verbatim,
then reset the identity sequences.

The target must be **empty**. The tool refuses to run against a store that already holds
rows, which makes a partial or duplicate migration impossible rather than merely unlikely,
and lets :func:`verify` treat a count match as proof of a complete copy.

``verify`` asserts per-table and per-tenant counts and that every ``(iss, sub)`` mapping
resolves to the same tenant it did in SQLite. A green verification is the gate before any
cutover (Phase 5), not a nicety.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import psycopg

from munnin.data_entities.postgres_migrations import ensure_schema

# (table, columns) in insert order — parents before children, so foreign keys hold.
_TABLES: list[tuple[str, tuple[str, ...]]] = [
    ("account", ("user_id", "display_name", "email", "created_date")),
    ("user_identity", ("iss", "sub", "user_id", "linked_date")),
    ("agent", ("user_id", "agent_id", "name", "role", "uuid", "created_date")),
    (
        "shared_record",
        (
            "id", "uuid", "user_id", "record_type", "project", "title", "tags",
            "created_date", "modified_date", "archived_date", "deleted_date",
            "full_content",
        ),
    ),
    (
        "memory_record",
        (
            "id", "uuid", "user_id", "agent_id", "record_type", "project", "title",
            "tags", "created_date", "modified_date", "archived_date", "deleted_date",
            "full_content",
        ),
    ),
]

#: Tables whose ``id`` is an identity column, needing a ``setval`` after explicit-id inserts.
_IDENTITY_TABLES = ("shared_record", "memory_record")


def _read_sqlite(path: Path, table: str, columns: tuple[str, ...]) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    finally:
        conn.close()


def _count_sqlite(path: Path, table: str, *, where: str = "", params: tuple = ()) -> int:
    conn = sqlite3.connect(str(path))
    try:
        sql = f"SELECT count(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


def _count_pg(conn: psycopg.Connection, table: str, *, where: str = "", params: tuple = ()) -> int:
    with conn.cursor() as cur:
        sql = f"SELECT count(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


def migrate(sqlite_path: Path | str, dsn: str) -> dict[str, int]:
    """Copy every table from ``sqlite_path`` into an empty PostgreSQL store at ``dsn``.

    Returns the per-table row counts that were written. Raises ``RuntimeError`` if the
    target already holds any row in a target table.
    """
    sqlite_path = Path(sqlite_path)
    rows = {table: _read_sqlite(sqlite_path, table, cols) for table, cols in _TABLES}
    with psycopg.connect(dsn) as conn:
        ensure_schema(conn)
        for table, _cols in _TABLES:
            if _count_pg(conn, table) != 0:
                raise RuntimeError(
                    f"target table {table!r} is not empty; migrate into a fresh store"
                )
        for table, cols in _TABLES:
            data = rows[table]
            if not data:
                continue
            placeholders = ", ".join(["%s"] * len(cols))
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", data
                )
        for table in _IDENTITY_TABLES:
            with conn.cursor() as cur:
                cur.execute(f"SELECT max(id) FROM {table}")
                high = cur.fetchone()[0]
                if high is not None:
                    # Table name is a whitelist constant, never caller input.
                    cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), %s)", (high,)
                    )
        conn.commit()
    return {table: len(rows[table]) for table, _cols in _TABLES}


def verify(sqlite_path: Path | str, dsn: str) -> None:
    """Assert the Postgres store is a faithful copy of the SQLite one; raise otherwise."""
    sqlite_path = Path(sqlite_path)
    problems: list[str] = []
    with psycopg.connect(dsn) as conn:
        for table, _cols in _TABLES:
            src, dst = _count_sqlite(sqlite_path, table), _count_pg(conn, table)
            if src != dst:
                problems.append(f"{table}: sqlite {src} vs postgres {dst}")

        for (user_id,) in _read_sqlite(sqlite_path, "account", ("user_id",)):
            for table in ("memory_record", "shared_record"):
                src = _count_sqlite(sqlite_path, table, where="user_id = ?", params=(user_id,))
                dst = _count_pg(conn, table, where="user_id = %s", params=(user_id,))
                if src != dst:
                    problems.append(f"{table}[{user_id}]: sqlite {src} vs postgres {dst}")

        for iss, sub, user_id in _read_sqlite(
            sqlite_path, "user_identity", ("iss", "sub", "user_id")
        ):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM user_identity WHERE iss = %s AND sub = %s",
                    (iss, sub),
                )
                row = cur.fetchone()
            if row is None or row[0] != user_id:
                problems.append(f"identity ({iss},{sub}) does not resolve to {user_id!r}")

    if problems:
        raise RuntimeError("migration verification failed:\n  " + "\n  ".join(problems))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy the Valaskjalf store from SQLite to PostgreSQL, then verify."
    )
    parser.add_argument("--sqlite", required=True, help="path to the source SQLite database")
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN of the EMPTY target")
    parser.add_argument(
        "--verify-only", action="store_true", help="skip the copy and only verify"
    )
    args = parser.parse_args(argv)
    try:
        if not args.verify_only:
            for table, count in migrate(args.sqlite, args.dsn).items():
                print(f"copied {table}: {count}")
        verify(args.sqlite, args.dsn)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("verification OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
