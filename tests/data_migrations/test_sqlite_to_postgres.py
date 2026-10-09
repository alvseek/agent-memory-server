"""The SQLite-to-Postgres migration tool (marked ``postgres``).

Builds a real source store through the real SQLite repositories, migrates it into a fresh
Postgres schema, and proves the copy: counts match, `id` is preserved, verification passes,
and verification *fails* on a deliberately-dropped row (a check that cannot fail in the
direction you care about is not a check).
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType, SharedRecord
from munnin.data_migrations.sqlite_to_postgres import migrate, verify
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

URL = os.getenv("MUNNIN_PG_TEST_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set"),
]
USER = "alvi"


def _source(tmp_path: Path) -> Path:
    db = tmp_path / "source.db"
    ident = SqliteIdentityRepository(db)
    ident.ensure_account(Account(user_id=USER, display_name="Alvi"))
    ident.link_identity(UserIdentity(iss="https://iss", sub="sub-a", user_id=USER))
    repo = SqliteMemoryRepository(db, user_id=USER)
    repo.upsert_agent(Agent(user_id=USER, agent_id="meta", name="Meta", role="r"))
    repo.insert(
        MemoryRecord(
            uuid="m1",
            user_id=USER,
            agent_id="meta",
            record_type=RecordType.episode,
            title="T",
            full_content="body",
        )
    )
    repo.insert_shared(
        SharedRecord(uuid="s1", user_id=USER, record_type=RecordType.reasoning, full_content="r")
    )
    return db


def _fresh_pg() -> None:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()


def test_migrate_copies_every_table_and_preserves_ids(tmp_path: Path) -> None:
    _fresh_pg()
    source = _source(tmp_path)
    counts = migrate(source, URL)
    assert counts == {
        "account": 1,
        "user_identity": 1,
        "agent": 1,
        "shared_record": 1,
        "memory_record": 1,
    }
    verify(source, URL)  # does not raise
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        cur.execute("select id, uuid, full_content from memory_record")
        assert cur.fetchall() == [(1, "m1", "body")]


def test_verify_fails_on_a_dropped_row(tmp_path: Path) -> None:
    _fresh_pg()
    source = _source(tmp_path)
    migrate(source, URL)
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from memory_record")
        conn.commit()
    with pytest.raises(RuntimeError):
        verify(source, URL)


def test_migrate_refuses_a_non_empty_target(tmp_path: Path) -> None:
    _fresh_pg()
    source = _source(tmp_path)
    migrate(source, URL)
    with pytest.raises(RuntimeError):
        migrate(source, URL)
