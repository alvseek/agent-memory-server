"""The schema migration runner — history, ordering, idempotency, and the retrofitted case.

The base schema is applied with ``IF NOT EXISTS``, so a database that already has it is
unaffected; every later migration then runs once on both a fresh and an existing store.
These tests exercise both paths, because the existing-store path is the one the runner
exists for.
"""

from __future__ import annotations

import sqlite3

import pytest

from munnin.data_entities.schema_migrations import apply_migrations, known, status


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _base_sql() -> str:
    return next(m for m in known() if m.version == "0001").sql


def _shared_ddl(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT sql FROM sqlite_master WHERE name = 'shared_record'").fetchone()[0]


def _history(conn: sqlite3.Connection) -> set[str]:
    return {r["version"] for r in conn.execute("SELECT version FROM migration_history")}


def test_a_fresh_database_applies_every_migration_and_records_them() -> None:
    conn = _conn()
    ran = apply_migrations(conn)
    assert ran == [m.name for m in known()]
    assert _history(conn) == {m.version for m in known()}


def test_a_fresh_database_admits_ras() -> None:
    """The whole point of 0002: the widened CHECK is present on a new store."""
    conn = _conn()
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO shared_record "
        "(uuid, user_id, record_type, created_date, modified_date, full_content) "
        "VALUES ('s1', 'alvi', 'ras', 'd', 'd', 'body')"
    )  # no CHECK failure
    assert conn.execute("SELECT COUNT(*) FROM shared_record").fetchone()[0] == 1


def test_reapplying_is_a_no_op() -> None:
    conn = _conn()
    apply_migrations(conn)
    assert apply_migrations(conn) == []


def test_an_existing_base_schema_gets_the_ras_migration() -> None:
    """The retrofitted case: an old database carries the base schema and no history. 0001
    is idempotent so it records as a no-op; 0002 is the one that changes anything, and the
    store ends able to hold `ras`."""
    conn = _conn()
    conn.executescript(_base_sql())  # as an existing store looks before the runner existed
    assert "ras" not in _shared_ddl(conn)
    ran = apply_migrations(conn)
    assert ran == ["0001_init", "0002_shared_record_ras"]
    assert "'ras'" in _shared_ddl(conn)
    assert conn.execute("SELECT COUNT(*) FROM migration_history").fetchone()[0] == 2


def test_the_ras_migration_preserves_rows_and_rebuilds_the_fts_index() -> None:
    """A table rebuild that dropped the shared rows, or left the FTS index stale, would
    pass a schema-only check and be worthless."""
    conn = _conn()
    conn.executescript(_base_sql())
    conn.execute(
        "INSERT INTO shared_record "
        "(id, uuid, user_id, record_type, created_date, modified_date, full_content) "
        "VALUES (7, 's1', 'alvi', 'reasoning', 'd', 'd', 'deep thought')"
    )
    conn.commit()
    apply_migrations(conn)
    assert conn.execute("SELECT COUNT(*) FROM shared_record").fetchone()[0] == 1
    hits = conn.execute("SELECT rowid FROM shared_fts WHERE shared_fts MATCH 'thought'").fetchall()
    assert [h[0] for h in hits] == [7]


def test_status_reports_pending_then_applied() -> None:
    conn = _conn()
    assert [state for _, state in status(conn)] == ["pending"] * len(known())
    apply_migrations(conn)
    assert [state for _, state in status(conn)] == ["applied"] * len(known())


def test_editing_an_applied_migration_is_refused() -> None:
    """An edited migration must fail loudly: re-running it would silently do nothing,
    which is the exact failure the runner was built to end."""
    conn = _conn()
    apply_migrations(conn)
    conn.execute("UPDATE migration_history SET checksum = 'tampered' WHERE version = '0001'")
    conn.commit()
    with pytest.raises(RuntimeError, match="changed after it was applied"):
        apply_migrations(conn)
