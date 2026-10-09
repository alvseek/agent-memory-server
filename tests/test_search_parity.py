"""Search parity between SQLite FTS5 and PostgreSQL full text (marked ``postgres``).

The guard for `qa/fixtures/postgres-search-parity.md`. A synthetic store carrying the token
classes where the two engines differ (hyphenated words, underscored identifiers, plain
words) is migrated into a fresh Postgres, and each query is asserted to return the **same
set** on both engines. Every query is also asserted non-empty, so a fixture that matches
nothing on either side fails instead of passing vacuously.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from munnin.data_entities.identity import Account
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_migrations.sqlite_to_postgres import migrate
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

URL = os.getenv("MUNNIN_PG_TEST_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set"),
]
USER = "alvi"

# uuid -> (title, content). Chosen to exercise the token classes and the three indexed
# columns (content, title, tags).
_RECORDS: dict[str, tuple[str, str, list[str]]] = {
    "r1": ("agent-memory", "shared-memory is the fleet identity layer", ["memory"]),
    "r2": ("backend-nestjs report", "the ocx-platform inventory query", []),
    "r3": ("plain note", "the word memory stands alone here", []),
    "r4": ("end-to-end test", "foo-bar and baz_qux tokenization", []),
    "r5": ("C++ compiler", "the compiler handles plus plus", ["tooling"]),
}

# Queries that must match at least one record and agree across engines.
_QUERIES = [
    "memory", "agent", "shared", "fleet", "layer",
    "nestjs", "backend", "inventory", "query", "platform", "ocx",
    "note", "stands", "end", "foo", "baz", "compiler", "tooling",
]


def test_search_membership_matches_between_engines(tmp_path: Path) -> None:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()

    source = tmp_path / "source.db"
    SqliteIdentityRepository(source).ensure_account(Account(user_id=USER))
    sqlite_repo = SqliteMemoryRepository(source, user_id=USER)
    sqlite_repo.upsert_agent(Agent(user_id=USER, agent_id="meta", name="Meta", role="r"))
    for uuid, (title, content, tags) in _RECORDS.items():
        sqlite_repo.insert(
            MemoryRecord(
                uuid=uuid,
                user_id=USER,
                agent_id="meta",
                record_type=RecordType.episode,
                title=title,
                tags=tags,
                full_content=content,
            )
        )

    migrate(source, URL)
    pg_repo = PostgresMemoryRepository(URL, user_id=USER)

    for query in _QUERIES:
        sqlite_hits = {r.uuid for r in sqlite_repo.search(query)}
        pg_hits = {r.uuid for r in pg_repo.search(query)}
        assert sqlite_hits, f"query {query!r} matched nothing on SQLite (vacuous fixture)"
        assert sqlite_hits == pg_hits, (
            f"parity mismatch for {query!r}: "
            f"missing={sorted(sqlite_hits - pg_hits)} extra={sorted(pg_hits - sqlite_hits)}"
        )
