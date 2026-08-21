"""Fleet-shared memory: its own write path, its own reads, its own search corpus.

Splitting shared memory out of `memory_record` is what lets `agent_id` carry an
unconditional foreign key. These tests pin the two halves of that bargain:

  * **Isolation** — naming an agent must never return fleet rows, and `query_shared`
    must never return an agent's.
  * **Union** — naming no agent must return both, because "all memory this tenant can
    see" is still one question even though it now spans two tables.

Both are asserted against the **real** repository rather than the auto-agent double:
the point at issue is which table a row lands in, and a double that creates agent rows
would obscure exactly that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_entities.memory_record import (
    SHARED_RECORD_TYPES,
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
)
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _repo(tmp_path: Path, user_id: str = "alvi") -> SqliteMemoryRepository:
    return SqliteMemoryRepository(tmp_path / "mem.db", user_id=user_id)


def _shared(uuid: str, **kw: object) -> SharedRecord:
    base = dict(
        uuid=uuid,
        user_id="ignored",  # repo stamps its own
        record_type=RecordType.reasoning,
        full_content="body",
        created_date="2026-01-01",
    )
    base.update(kw)
    return SharedRecord(**base)  # type: ignore[arg-type]


def _seeded(tmp_path: Path) -> SqliteMemoryRepository:
    """One agent with two memory items, plus two fleet items."""
    repo = _repo(tmp_path)
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Claude Meta"))
    repo.insert(
        MemoryRecord(
            uuid="a1", user_id="", agent_id="meta", record_type=RecordType.identity,
            full_content="meta identity", created_date="2026-01-01",
        )
    )
    repo.insert(
        MemoryRecord(
            uuid="a2", user_id="", agent_id="meta", record_type=RecordType.reasoning,
            full_content="agent reasoning", created_date="2026-01-02",
        )
    )
    repo.insert_shared(_shared("s1", full_content="fleet reasoning"))
    repo.insert_shared(
        _shared("s2", record_type=RecordType.knowledge, full_content="fleet knowledge")
    )
    return repo


# --- insert_shared ---


def test_insert_shared_roundtrips_without_an_owner(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saved = repo.insert_shared(_shared("s1", title="T", tags=["a", "b"]))
    assert saved.id is not None
    assert saved.user_id == "alvi"  # server-stamped, not the "ignored" input
    assert saved.tags == ["a", "b"]
    assert not hasattr(saved, "agent_id")


def test_insert_shared_needs_no_agent_to_exist(tmp_path: Path) -> None:
    """The whole reason for the split: an agent insert requires its agent row, a fleet
    insert requires nothing, because fleet memory has no owner to check."""
    repo = _repo(tmp_path)  # no agents at all
    repo.insert_shared(_shared("s1"))
    assert [r.uuid for r in repo.query_shared()] == ["s1"]


def test_insert_shared_is_idempotent_upsert_on_uuid(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("s1", title="first"))
    repo.insert_shared(_shared("s1", title="second"))
    rows = repo.query_shared()
    assert len(rows) == 1
    assert rows[0].title == "second"
    assert rows[0].created_date == "2026-01-01"  # preserved across upsert


@pytest.mark.parametrize(
    "record_type", [RecordType.episode, RecordType.identity, RecordType.emotional]
)
def test_insert_shared_rejects_agent_only_record_types(
    tmp_path: Path, record_type: RecordType
) -> None:
    """The CHECK enforces what used to be convention. An episode belongs to whoever
    lived it, so it cannot be fleet memory — and the store says so rather than trusting
    every future caller to remember."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="cannot be"):
        repo.insert_shared(_shared("s1", record_type=record_type))
    assert list(repo.query_shared()) == []


def test_shared_type_rejection_names_what_is_allowed(tmp_path: Path) -> None:
    """The schema does the enforcing; this only gives its refusal a shape the faces can
    report. An untranslated IntegrityError reaches an agent as an opaque database string
    and an HTTP caller as a 500.

    Asserted against the declared set rather than a literal: the previous version of this
    test hardcoded "'reasoning' or 'knowledge'", so when `user_profile` became legal the
    message kept naming two of three types and the test held it there."""
    with pytest.raises(ValueError) as exc:
        _repo(tmp_path).insert_shared(_shared("s1", record_type=RecordType.episode))
    for rtype in SHARED_RECORD_TYPES:
        assert repr(rtype.value) in str(exc.value)
    assert "episode" in str(exc.value)


def test_a_second_profile_is_refused_as_a_caller_error_not_a_crash(tmp_path: Path) -> None:
    """The partial unique index already stopped the write; this pins how the refusal is
    *reported*. Only `CHECK constraint failed` was translated, so a second profile raised a
    bare IntegrityError and surfaced over HTTP as a 500 — a broken-server answer to what is
    really a caller asking for something the model forbids."""
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("p1", record_type=RecordType.user_profile))
    with pytest.raises(ValueError, match="already has a user profile"):
        repo.insert_shared(_shared("p2", record_type=RecordType.user_profile))
    assert len([r for r in repo.query_shared() if r.record_type is RecordType.user_profile]) == 1


# --- isolation and union ---


def test_naming_an_agent_returns_no_fleet_rows(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    assert {r.uuid for r in repo.query(agent_id="meta")} == {"a1", "a2"}


def test_naming_no_agent_returns_both_tables(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    assert {r.uuid for r in repo.query()} == {"a1", "a2", "s1", "s2"}


def test_query_shared_returns_no_agent_rows(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    assert {r.uuid for r in repo.query_shared()} == {"s1", "s2"}


def test_union_results_are_self_labelling(tmp_path: Path) -> None:
    """Decision 6's "two labelled groups" needs no envelope: each row is already the
    type its table implies, so the caller reads the label off the record."""
    by_uuid = {r.uuid: r for r in _seeded(tmp_path).query()}
    assert isinstance(by_uuid["a1"], MemoryRecord)
    assert by_uuid["a1"].agent_id == "meta"
    assert not isinstance(by_uuid["s1"], MemoryRecord)
    assert not hasattr(by_uuid["s1"], "agent_id")


def test_union_order_is_agent_rows_then_fleet_rows(tmp_path: Path) -> None:
    """Per-table insertion order, concatenated — not interleaved. The two `id` sequences
    are independent, so a global sort on them would imply a chronology neither carries."""
    assert [r.uuid for r in _seeded(tmp_path).query()] == ["a1", "a2", "s1", "s2"]


def test_record_type_filter_applies_to_both_tables(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    reasoning = repo.query(record_type=RecordType.reasoning)
    assert {r.uuid for r in reasoning} == {"a2", "s1"}  # one from each table


def test_query_shared_filters_by_record_type(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    assert {r.uuid for r in repo.query_shared(record_type=RecordType.knowledge)} == {"s2"}


# --- lifecycle and tenancy on the shared table ---


def test_shared_archived_and_deleted_follow_the_same_rules(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("active"))
    repo.insert_shared(_shared("arch", archived_date="2026-02-01"))
    repo.insert_shared(_shared("del", deleted_date="2026-02-01"))
    assert {r.uuid for r in repo.query_shared()} == {"active"}
    assert {r.uuid for r in repo.query_shared(include_archived=True)} == {"active", "arch"}
    # And the union honours the same lifecycle rules on the rows it pulls in.
    assert {r.uuid for r in repo.query()} == {"active"}


def test_shared_memory_is_tenancy_scoped(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    a = SqliteMemoryRepository(db, user_id="alvi")
    b = SqliteMemoryRepository(db, user_id="other")
    a.insert_shared(_shared("s1"))
    assert {r.uuid for r in a.query_shared()} == {"s1"}
    assert list(b.query_shared()) == []
    assert list(b.query()) == []


# --- the search split ---


def test_each_search_returns_only_its_own_corpus(tmp_path: Path) -> None:
    """FTS5 external-content binds one index to one table, so the split is the schema's
    doing. What matters here is that neither index leaks into the other's results."""
    repo = _seeded(tmp_path)
    repo.insert(
        MemoryRecord(
            uuid="a3", user_id="", agent_id="meta", record_type=RecordType.episode,
            full_content="a shibboleth in agent memory", created_date="2026-01-03",
        )
    )
    repo.insert_shared(_shared("s3", full_content="a shibboleth in fleet memory"))

    assert [r.uuid for r in repo.search("shibboleth")] == ["a3"]
    assert [r.uuid for r in repo.search_shared("shibboleth")] == ["s3"]


def test_search_results_carry_their_own_type(tmp_path: Path) -> None:
    repo = _seeded(tmp_path)
    (agent_hit,) = repo.search("identity")
    (fleet_hit,) = repo.search_shared("knowledge")
    assert isinstance(agent_hit, MemoryRecord)
    assert not isinstance(fleet_hit, MemoryRecord)


def test_search_shared_excludes_deleted_and_gates_archived(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("live", full_content="findme live"))
    repo.insert_shared(_shared("arch", full_content="findme arch", archived_date="2026-02-01"))
    repo.insert_shared(_shared("del", full_content="findme del", deleted_date="2026-02-01"))
    assert {r.uuid for r in repo.search_shared("findme")} == {"live", "arch"}
    assert {r.uuid for r in repo.search_shared("findme", include_archived=False)} == {"live"}


def test_shared_search_survives_fts_operator_syntax(tmp_path: Path) -> None:
    """The shared index gets the same plain-text safety as the agent one — it is the
    same `_to_fts_query`, but a second index is a second chance to wire it wrongly."""
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("s1", full_content="store≠repo and C++ notes"))
    assert {r.uuid for r in repo.search_shared("C++")} == {"s1"}
    assert list(repo.search_shared("   ")) == []


def test_shared_search_reindexes_after_a_rewrite(tmp_path: Path) -> None:
    """`append` routes through `_locate` to the shared table; the shared FTS triggers
    have to keep up, or a rewritten fleet record becomes unfindable by its new text."""
    repo = _repo(tmp_path)
    repo.insert_shared(_shared("s1", full_content="original"))
    repo.append("s1", " appended-token")
    assert {r.uuid for r in repo.search_shared("appended-token")} == {"s1"}
