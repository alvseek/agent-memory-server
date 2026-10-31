"""The tenant-sharing tables and the selection column, exercised as DDL.

The same approach as `test_schema`: a bare connection with the migration set applied and
foreign keys on. What the *service* refuses (a self-grant, an expired invite) is not here;
this file only proves the store can hold the shape and cannot hold a contradiction of it.
"""

from __future__ import annotations

import sqlite3

import pytest

from munnin.data_entities.schema_migrations import apply_migrations

_INVITE = (
    "INSERT INTO tenant_invite VALUES "
    "('{code}','{tenant}','alvi','d','2026-11-30T00:00:00+00:00',NULL,NULL,NULL)"
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("INSERT INTO account (user_id, created_date) VALUES ('alvi','2026-10-31')")
    conn.execute("INSERT INTO account (user_id, created_date) VALUES ('roy','2026-10-31')")
    return conn


def test_the_sharing_tables_exist() -> None:
    names = {r[0] for r in _db().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tenant_access", "tenant_invite"} <= names


def test_the_selection_column_exists_and_is_null_by_default() -> None:
    """NULL is the answer for every existing account, and it means "act as yourself"."""
    row = _db().execute("SELECT active_user_id FROM account WHERE user_id = 'alvi'").fetchone()
    assert row[0] is None


def test_a_grant_must_name_two_real_accounts() -> None:
    conn = _db()
    conn.execute("INSERT INTO tenant_access VALUES ('alvi','roy','d',NULL)")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute("INSERT INTO tenant_access VALUES ('alvi','ghost','d',NULL)")


def test_a_grant_is_one_row_per_pair() -> None:
    conn = _db()
    conn.execute("INSERT INTO tenant_access VALUES ('alvi','roy','d',NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tenant_access VALUES ('alvi','roy','d',NULL)")


def test_an_invite_needs_a_real_tenant_and_a_unique_code() -> None:
    conn = _db()
    conn.execute(_INVITE.format(code="code1", tenant="alvi"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_INVITE.format(code="code1", tenant="alvi"))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute(_INVITE.format(code="code2", tenant="ghost"))
