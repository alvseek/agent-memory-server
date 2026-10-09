"""``PostgresMemoryRepository`` tests (marked ``postgres``).

A focused smoke suite for the Postgres repository. The full cross-engine contract suite
lands in Phase 2 (parametrized conftest); this one proves each method behaves before that.
"""

from __future__ import annotations

import os
import uuid as uuidlib

import psycopg
import pytest

from munnin.data_entities import postgres_migrations as pgm
from munnin.data_entities.memory_record import (
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
)
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository

URL = os.getenv("MUNNIN_PG_TEST_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set"),
]
USER = "alvi"


@pytest.fixture()
def repo() -> PostgresMemoryRepository:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
        pgm.ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                "insert into account(user_id, created_date) values (%s, %s)",
                (USER, "2026-01-01"),
            )
        conn.commit()
    r = PostgresMemoryRepository(URL, user_id=USER)
    r.create_agent(Agent(user_id=USER, agent_id="meta", name="Meta", role="r"))
    return r


def _mem(agent: str = "meta", content: str = "hello memory", **kw) -> MemoryRecord:
    return MemoryRecord(
        uuid=str(uuidlib.uuid4()),
        user_id=USER,
        agent_id=agent,
        record_type=kw.pop("record_type", RecordType.episode),
        full_content=content,
        **kw,
    )


def _shared(rtype: RecordType, content: str) -> SharedRecord:
    return SharedRecord(
        uuid=str(uuidlib.uuid4()), user_id=USER, record_type=rtype, full_content=content
    )


def test_agents(repo: PostgresMemoryRepository) -> None:
    assert [a.agent_id for a in repo.list_agents()] == ["meta"]
    with pytest.raises(ValueError):
        repo.create_agent(Agent(user_id=USER, agent_id="meta"))
    repo.upsert_agent(Agent(user_id=USER, agent_id="meta", name="Meta2", role="r2"))
    assert repo.list_agents()[0].name == "Meta2"


def test_insert_get_query(repo: PostgresMemoryRepository) -> None:
    rec = _mem(title="T", tags=["a", "b"])
    repo.insert(rec)
    got = repo.get(rec.uuid)
    assert got is not None and got.full_content == "hello memory"
    assert got.tags == ["a", "b"]
    assert [
        r.uuid for r in repo.query(agent_id="meta", record_type=RecordType.episode)
    ] == [rec.uuid]


def test_insert_requires_an_existing_agent(repo: PostgresMemoryRepository) -> None:
    with pytest.raises(ValueError):
        repo.insert(_mem(agent="ghost"))


def test_edit_append_prepend_multi_edit(repo: PostgresMemoryRepository) -> None:
    rec = _mem(content="alpha beta alpha")
    repo.insert(rec)
    with pytest.raises(ValueError):
        repo.edit(rec.uuid, "alpha", "x")  # ambiguous without replace_all
    repo.edit(rec.uuid, "alpha", "gamma", replace_all=True)
    assert repo.get(rec.uuid).full_content == "gamma beta gamma"
    repo.append(rec.uuid, "!")
    assert repo.get(rec.uuid).full_content == "gamma beta gamma!"
    repo.prepend(rec.uuid, ">> ")
    assert repo.get(rec.uuid).full_content.startswith(">> ")
    repo.multi_edit(rec.uuid, [(">> ", "", False), ("!", "", False)])
    assert repo.get(rec.uuid).full_content == "gamma beta gamma"


def test_archive_and_soft_delete(repo: PostgresMemoryRepository) -> None:
    rec = _mem(title="gone")
    repo.insert(rec)
    repo.archive(rec.uuid)
    assert repo.get(rec.uuid).archived_date is not None
    assert repo.query(agent_id="meta") == []
    assert [r.uuid for r in repo.query(agent_id="meta", include_archived=True)] == [rec.uuid]
    repo.soft_delete(rec.uuid)
    assert repo.get(rec.uuid) is None


def test_search_agent_and_shared(repo: PostgresMemoryRepository) -> None:
    hit = _mem(title="memory note", content="the store moved to postgres")
    miss = _mem(title="other", content="nothing relevant here")
    repo.insert(hit)
    repo.insert(miss)
    assert [r.uuid for r in repo.search("postgres")] == [hit.uuid]
    assert repo.search("   ") == []
    shared = _shared(RecordType.reasoning, "reasoning about velocity")
    repo.insert_shared(shared)
    assert [r.uuid for r in repo.search_shared("velocity")] == [shared.uuid]


def test_shared_record_types_are_enforced(repo: PostgresMemoryRepository) -> None:
    repo.insert_shared(_shared(RecordType.reasoning, "r"))
    repo.insert_shared(_shared(RecordType.user_profile, "p"))
    with pytest.raises(ValueError):
        repo.insert_shared(_shared(RecordType.user_profile, "second profile"))
    with pytest.raises(ValueError):
        repo.insert_shared(_shared(RecordType.episode, "an episode cannot be shared"))


def test_query_without_agent_spans_both_tables(repo: PostgresMemoryRepository) -> None:
    mem = _mem(title="mem")
    repo.insert(mem)
    shared = _shared(RecordType.knowledge, "k")
    repo.insert_shared(shared)
    uuids = {r.uuid for r in repo.query()}
    assert {mem.uuid, shared.uuid} <= uuids
