"""The seven uuid-addressed operations, across both memory tables.

Splitting shared memory into its own table could have doubled the operation surface.
It does not, because a uuid already identifies one row across both tables — `_locate`
resolves which, and the caller keeps a single signature. These tests are what makes that
claim checkable: every one of the seven has to behave identically whether the uuid names
agent memory or fleet memory.

Shared rows are seeded with raw SQL rather than `insert_shared` (Step 2.3) so the tests
bind to `_locate` alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_entities.memory_record import (
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
)
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account


def _repo(tmp_path: Path) -> SqliteMemoryRepository:
    seed_account(tmp_path / "m.db")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Claude Meta"))
    repo.insert(
        MemoryRecord(
            uuid="agent-1", user_id="", agent_id="meta",
            record_type=RecordType.episode, full_content="one two",
        )
    )
    with repo._conn() as conn:  # noqa: SLF001 — insert_shared arrives in Step 2.3
        conn.execute(
            "INSERT INTO shared_record (uuid,user_id,record_type,created_date,modified_date,"
            "full_content) VALUES ('shared-1','alvi','reasoning','d','d','one two')"
        )
    return repo


BOTH = pytest.mark.parametrize("uuid", ["agent-1", "shared-1"])


@BOTH
def test_get_finds_records_in_either_table(tmp_path: Path, uuid: str) -> None:
    got = _repo(tmp_path).get(uuid)
    assert got is not None
    assert got.full_content == "one two"


def test_get_result_is_self_labelling(tmp_path: Path) -> None:
    """No wrapper needed: agent memory carries `agent_id`, fleet memory has no such field."""
    repo = _repo(tmp_path)
    agent_rec = repo.get("agent-1")
    shared_rec = repo.get("shared-1")
    assert isinstance(agent_rec, MemoryRecord)
    assert agent_rec.agent_id == "meta"
    assert isinstance(shared_rec, SharedRecord)
    assert not isinstance(shared_rec, MemoryRecord)
    assert not hasattr(shared_rec, "agent_id")


@BOTH
def test_edit_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    assert _repo(tmp_path).edit(uuid, "one", "1").full_content == "1 two"


@BOTH
def test_append_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    assert _repo(tmp_path).append(uuid, " three").full_content == "one two three"


@BOTH
def test_prepend_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    assert _repo(tmp_path).prepend(uuid, "zero ").full_content == "zero one two"


@BOTH
def test_multi_edit_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    got = _repo(tmp_path).multi_edit(uuid, [("one", "1", False), ("two", "2", False)])
    assert got.full_content == "1 2"


@BOTH
def test_archive_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    repo = _repo(tmp_path)
    repo.archive(uuid)
    got = repo.get(uuid)
    assert got is not None and got.archived_date is not None


@BOTH
def test_soft_delete_works_in_either_table(tmp_path: Path, uuid: str) -> None:
    repo = _repo(tmp_path)
    repo.soft_delete(uuid)
    assert repo.get(uuid) is None


@BOTH
def test_soft_delete_is_idempotent_in_either_table(tmp_path: Path, uuid: str) -> None:
    """A deleted row stays addressable, or the second call would raise instead of no-op."""
    repo = _repo(tmp_path)
    repo.soft_delete(uuid)
    repo.soft_delete(uuid)


def test_get_returns_none_for_an_unknown_uuid(tmp_path: Path) -> None:
    assert _repo(tmp_path).get("nowhere") is None


@pytest.mark.parametrize(
    "op",
    [
        lambda r: r.edit("nowhere", "a", "b"),
        lambda r: r.append("nowhere", "x"),
        lambda r: r.prepend("nowhere", "x"),
        lambda r: r.multi_edit("nowhere", [("a", "b", False)]),
        lambda r: r.archive("nowhere"),
        lambda r: r.soft_delete("nowhere"),
    ],
)
def test_unknown_uuid_still_raises_lookup_error(tmp_path: Path, op) -> None:  # noqa: ANN001
    """Resolution across two tables must not soften a miss into silence."""
    with pytest.raises(LookupError, match="record not found"):
        op(_repo(tmp_path))
