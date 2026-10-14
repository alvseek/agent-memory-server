"""The ``MemoryRepository`` contract, run against **both** backends.

Every test here takes the parametrized ``memory_repo`` fixture (``tests/conftest.py``),
which yields a SQLite repository for the default run and a PostgreSQL repository under the
``postgres`` mark. Same assertions, two engines: the only intended behavioural difference is
search ranking, which none of these assert on (they check membership, not order), so a pass
here is the seam holding (high-wizard decision 5).

The full PostgreSQL schema/FTS surface and the identity repository have their own modules.
"""

from __future__ import annotations

import uuid as uuidlib
from typing import Any

import pytest

from munnin.data_entities.memory_record import (
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
)

USER = "alvi"


def _mem(agent: str = "meta", content: str = "hello memory", **kw: Any) -> MemoryRecord:
    return MemoryRecord(
        uuid=str(uuidlib.uuid4()),
        user_id=USER,
        agent_id=agent,
        record_type=kw.pop("record_type", RecordType.episode),
        full_content=content,
        **kw,
    )


def _shared(rtype: RecordType, content: str, **kw: Any) -> SharedRecord:
    return SharedRecord(
        uuid=str(uuidlib.uuid4()),
        user_id=USER,
        record_type=rtype,
        full_content=content,
        **kw,
    )


def test_agent_is_listed(memory_repo: Any) -> None:
    assert [a.agent_id for a in memory_repo.list_agents()] == ["meta"]


def test_create_agent_refuses_a_taken_domain(memory_repo: Any) -> None:
    with pytest.raises(ValueError):
        memory_repo.create_agent(Agent(user_id=USER, agent_id="meta"))


def test_upsert_agent_refreshes_name_and_role(memory_repo: Any) -> None:
    memory_repo.upsert_agent(Agent(user_id=USER, agent_id="meta", name="Meta2", role="r2"))
    assert memory_repo.list_agents()[0].name == "Meta2"


def test_insert_get_query_roundtrip(memory_repo: Any) -> None:
    rec = _mem(title="T", tags=["a", "b"])
    memory_repo.insert(rec)
    got = memory_repo.get(rec.uuid)
    assert got is not None and got.full_content == "hello memory"
    assert got.tags == ["a", "b"]
    assert [
        r.uuid for r in memory_repo.query(agent_id="meta", record_type=RecordType.episode)
    ] == [rec.uuid]


def test_insert_requires_an_existing_agent(memory_repo: Any) -> None:
    with pytest.raises(ValueError):
        memory_repo.insert(_mem(agent="ghost"))


def test_edit_append_prepend_multi_edit(memory_repo: Any) -> None:
    rec = _mem(content="alpha beta alpha")
    memory_repo.insert(rec)
    with pytest.raises(ValueError):
        memory_repo.edit(rec.uuid, "alpha", "x")  # ambiguous without replace_all
    memory_repo.edit(rec.uuid, "alpha", "gamma", replace_all=True)
    assert memory_repo.get(rec.uuid).full_content == "gamma beta gamma"
    memory_repo.append(rec.uuid, "!")
    assert memory_repo.get(rec.uuid).full_content == "gamma beta gamma!"
    memory_repo.prepend(rec.uuid, ">> ")
    assert memory_repo.get(rec.uuid).full_content.startswith(">> ")
    memory_repo.multi_edit(rec.uuid, [(">> ", "", False), ("!", "", False)])
    assert memory_repo.get(rec.uuid).full_content == "gamma beta gamma"


def test_archive_then_soft_delete(memory_repo: Any) -> None:
    rec = _mem(title="gone")
    memory_repo.insert(rec)
    memory_repo.archive(rec.uuid)
    assert memory_repo.get(rec.uuid).archived_date is not None
    assert memory_repo.query(agent_id="meta") == []
    assert [
        r.uuid for r in memory_repo.query(agent_id="meta", include_archived=True)
    ] == [rec.uuid]
    memory_repo.soft_delete(rec.uuid)
    assert memory_repo.get(rec.uuid) is None


def test_search_finds_agent_and_shared(memory_repo: Any) -> None:
    hit = _mem(title="memory note", content="the store moved to postgres")
    miss = _mem(title="other", content="nothing relevant here")
    memory_repo.insert(hit)
    memory_repo.insert(miss)
    assert [r.uuid for r in memory_repo.search("postgres")] == [hit.uuid]
    assert memory_repo.search("   ") == []
    shared = _shared(RecordType.reasoning, "reasoning about velocity")
    memory_repo.insert_shared(shared)
    assert [r.uuid for r in memory_repo.search_shared("velocity")] == [shared.uuid]


def test_shared_record_types_are_enforced(memory_repo: Any) -> None:
    memory_repo.insert_shared(_shared(RecordType.reasoning, "r"))
    memory_repo.insert_shared(_shared(RecordType.user_profile, "p"))
    with pytest.raises(ValueError):
        memory_repo.insert_shared(_shared(RecordType.user_profile, "second profile"))
    with pytest.raises(ValueError):
        memory_repo.insert_shared(_shared(RecordType.episode, "an episode is not shared"))


def test_query_without_agent_spans_both_tables(memory_repo: Any) -> None:
    mem = _mem(title="mem")
    memory_repo.insert(mem)
    shared = _shared(RecordType.knowledge, "k")
    memory_repo.insert_shared(shared)
    uuids = {r.uuid for r in memory_repo.query()}
    assert {mem.uuid, shared.uuid} <= uuids


# --- the corpus boundary: a project-keyed `knowledge` row is Hermod's, not Munnin's ---


def test_a_project_keyed_episode_is_still_readable(memory_repo: Any) -> None:
    """Episodes keep their `project`, because that column is how a caller picks the episode
    for its own project out of the awakening payload's index. A filter that reached them
    would hide real memory: measured on the live store, 728 of 770 episodes carry a
    project."""
    ep = _mem(record_type=RecordType.episode, project="hermod-server")
    memory_repo.insert(ep)
    assert [r.uuid for r in memory_repo.query()] == [ep.uuid]
    assert [
        r.uuid for r in memory_repo.query(agent_id="meta", record_type=RecordType.episode)
    ] == [ep.uuid]
    assert [r.uuid for r in memory_repo.search("hello")] == [ep.uuid]


def test_a_project_keyed_knowledge_row_is_not_munnin_memory(memory_repo: Any) -> None:
    """A ``knowledge`` row carrying a ``project`` is Hermod's project context, so no read
    Munnin serves may return it, not even one that asks for that project by name. The
    unfiltered sibling is asserted alongside it, so a filter that excluded *everything*
    fails here too rather than passing quietly."""
    ours = _shared(RecordType.knowledge, "shipping cadence")
    theirs = _shared(RecordType.knowledge, "hermod store notes", project="hermod-server")
    agent_knowledge = _mem(
        record_type=RecordType.knowledge, content="hermod store notes too",
        project="hermod-server",
    )
    memory_repo.insert_shared(ours)
    memory_repo.insert_shared(theirs)
    memory_repo.insert(agent_knowledge)

    assert [
        r.uuid for r in memory_repo.query_shared(record_type=RecordType.knowledge)
    ] == [ours.uuid]
    assert [r.uuid for r in memory_repo.query(record_type=RecordType.knowledge)] == [ours.uuid]
    assert memory_repo.query(project="hermod-server") == []
    assert [r.uuid for r in memory_repo.search_shared("shipping")] == [ours.uuid]
    assert memory_repo.search_shared("hermod") == []
    assert memory_repo.search("hermod") == []


# --- the metadata write: a field changes without the body being read or rewritten ---


def test_set_fields_touches_only_the_fields_it_is_given(memory_repo: Any) -> None:
    rec = _mem(title="T", tags=["a"], content="body stays", content_summary="s")
    memory_repo.insert(rec)
    memory_repo.set_fields(rec.uuid, tags=["b", "c"])
    got = memory_repo.get(rec.uuid)
    assert got.tags == ["b", "c"]
    assert got.title == "T"  # omitted means untouched, not cleared
    assert got.content_summary == "s"
    assert got.full_content == "body stays"  # the body is never part of the statement


def test_set_fields_reaches_a_shared_record(memory_repo: Any) -> None:
    shared = _shared(RecordType.knowledge, "k", title="before")
    memory_repo.insert_shared(shared)
    memory_repo.set_fields(shared.uuid, title="after")
    assert memory_repo.get(shared.uuid).title == "after"


def test_set_fields_clears_to_null_empties_tags_and_refuses_an_empty_change(
    memory_repo: Any,
) -> None:
    """The three refusals are the contract, and the NULL is the load-bearing one: clearing
    `project` to `''` would leave the row in the other corpus, because both engines read a
    project row by `IS NULL`."""
    rec = _mem(project="hermod-server", content_summary="s", tags=["a"])
    memory_repo.insert(rec)
    memory_repo.set_fields(rec.uuid, clearing=["project"], tags=[])
    got = memory_repo.get(rec.uuid)
    assert got.project is None
    assert got.tags == []
    assert got.content_summary == "s"
    with pytest.raises(ValueError):
        memory_repo.set_fields(rec.uuid)
    with pytest.raises(ValueError):
        memory_repo.set_fields(rec.uuid, title="x", clearing=["title"])
    with pytest.raises(ValueError):
        memory_repo.set_fields(rec.uuid, clearing=["record_type"])
    with pytest.raises(LookupError):
        memory_repo.set_fields(str(uuidlib.uuid4()), title="x")


def test_set_fields_reindexes_a_changed_title(memory_repo: Any) -> None:
    """Both engines index `title` — SQLite through its AFTER UPDATE trigger, PostgreSQL
    through the STORED `search_tsv` — so a metadata-only write is findable with no extra
    step. A trigger narrowed to `full_content` would fail here and nowhere else."""
    rec = _mem(title="unremarkable", content="body text")
    memory_repo.insert(rec)
    assert memory_repo.search("needle") == []
    memory_repo.set_fields(rec.uuid, title="needle")
    assert [r.uuid for r in memory_repo.search("needle")] == [rec.uuid]
