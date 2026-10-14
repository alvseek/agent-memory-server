"""MemoryService write ops — insert / edit / archive / soft_delete (SP-3 Step 1.2).

The service assembles the record server-side; the repo stamps user_id + dates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import AutoAgentRepository


def _svc(tmp_path: Path) -> tuple[SqliteMemoryRepository, MemoryService]:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def test_insert_round_trip_generates_uuid(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    out = svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="body", title="t")
    assert out["uuid"]  # server-generated
    assert out["content"] == "body"
    assert out["record_type"] == "episode"
    assert svc.get(out["uuid"])["content"] == "body"


def test_insert_carries_the_content_summary_to_the_record_and_the_index(
    tmp_path: Path,
) -> None:
    """The summary is authored at the write, so it has to survive both reads: the full
    record, and the browse index that shows it beside the title."""
    _repo, svc = _svc(tmp_path)
    out = svc.insert(
        agent_id="meta",
        record_type="episode",
        content="body",
        title="t",
        content_summary="one line about the body",
    )
    assert out["content_summary"] == "one line about the body"
    assert svc.get(out["uuid"])["content_summary"] == "one line about the body"
    assert (
        svc.awaken("meta")["episodic_index"][0]["content_summary"]
        == "one line about the body"
    )


def test_insert_with_a_blank_summary_is_refused(tmp_path: Path) -> None:
    """The summary is authored, so a blank one is not an answer - it is a missing field."""
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="blank content_summary is not a value"):
        svc.insert(
            content_summary="   ",
            agent_id="meta",
            record_type="episode",
            content="body",
        )


def test_insert_without_a_summary_for_an_index_type_is_refused(tmp_path: Path) -> None:
    """The other half, and a different question: episode and knowledge are read through a
    browse index, so for those the summary is required rather than merely non-blank."""
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="content_summary is required"):
        svc.insert(agent_id="meta", record_type="knowledge", content="body")


def test_insert_allows_no_summary_where_nothing_reads_it(tmp_path: Path) -> None:
    """Identity is loaded whole at awakening, so a summary there would be data nothing
    reads - and a blank one is refused on every type, which is the rule this pins."""
    _repo, svc = _svc(tmp_path)
    out = svc.insert(agent_id="meta", record_type="identity", content="body")
    assert out["content_summary"] is None
    with pytest.raises(ValueError, match="blank content_summary is not a value"):
        svc.insert(agent_id="meta", record_type="identity", content="body", content_summary="")


def test_a_rolling_record_moves_its_summary_in_a_second_call(tmp_path: Path) -> None:
    """A rolling record's summary describes its newest content, so the write that changes
    the body is followed by one that moves the summary. Two calls, on purpose: the summary
    is metadata, and ``edit_metadata`` is its only writer, so a body edit cannot move it in
    passing."""
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="first take",
        agent_id="meta",
        record_type="episode",
        content="body",
        uuid="e1",
    )
    out = svc.edit("e1", "body", "newest body")
    assert out["content"] == "newest body"
    assert out["content_summary"] == "first take"  # the body write leaves it standing
    moved = svc.edit_metadata("e1", content_summary="second take")
    assert moved["content"] == "newest body"
    assert moved["content_summary"] == "second take"


def test_insert_is_idempotent_upsert(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="A", uuid="dup")
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="B", uuid="dup")
    rows = svc.query(agent_id="meta")
    assert len(rows) == 1
    assert rows[0]["content"] == "B"


def test_insert_shared_scope_writes_fleet_memory(tmp_path: Path) -> None:
    """Fleet memory is written by naming a scope, not by naming a fake agent. The
    returned projection carries **no** ``agent_id`` — that absence is the label."""
    _repo, svc = _svc(tmp_path)
    out = svc.insert(
        content_summary="a one-line summary of this record",
        scope="shared", record_type="reasoning", content="pattern")
    assert "agent_id" not in out
    assert out["content"] == "pattern"


def test_insert_shared_scope_accepts_the_coding_reasoning_lane(tmp_path: Path) -> None:
    """The coding lane is a shared type of its own, so a shared insert names it and the
    row lands ownerless like any other fleet memory."""
    _repo, svc = _svc(tmp_path)
    out = svc.insert(
        content_summary="a one-line summary of this record",
        scope="shared", record_type="coding_reasoning", content="a coding pattern")
    assert "agent_id" not in out
    assert out["record_type"] == "coding_reasoning"
    assert [r["content"] for r in svc.query(record_type="coding_reasoning")] == [
        "a coding pattern"
    ]


def test_the_coding_lane_is_readable_but_absent_from_a_chat_awakening(tmp_path: Path) -> None:
    """The lane is fleet memory, so it is readable on demand; but `awaken` selects its
    universal layer by `record_type`, so a chat agent's payload never carries it."""
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        scope="shared", record_type="coding_reasoning", content="a coding pattern")
    svc.insert(
        content_summary="a one-line summary of this record",
        scope="shared", record_type="reasoning", content="a universal pattern")
    assert [r["content"] for r in svc.coding_reasoning()] == ["a coding pattern"]
    shared = [r["content"] for r in svc.awaken("meta")["shared"]["reasoning"]]
    assert shared == ["a universal pattern"]


def test_insert_agent_scope_without_an_agent_id_is_refused(tmp_path: Path) -> None:
    """Neither contradiction may be resolved by guessing: either guess would put the
    row in a table the caller did not mean, and an insert cannot be undone by retrying."""
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="requires an agent_id"):
        svc.insert(
            content_summary="a one-line summary of this record",
            record_type="episode", content="x")


def test_insert_shared_scope_with_an_agent_id_is_refused(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="no agent_id"):
        svc.insert(
            content_summary="a one-line summary of this record",
            scope="shared", agent_id="meta", record_type="reasoning", content="x")


def test_insert_rejects_an_unknown_scope(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="invalid scope"):
        svc.insert(
            content_summary="a one-line summary of this record",
            scope="fleet", record_type="reasoning", content="x")


def test_insert_rejects_bad_agent_and_type(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.insert(
            content_summary="a one-line summary of this record",
            agent_id="Bad_Name", record_type="episode", content="x")
    with pytest.raises(ValueError):
        svc.insert(
            content_summary="a one-line summary of this record",
            agent_id="meta", record_type="bogus", content="x")


def test_edit_replaces_body_and_bumps_modified(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(
        MemoryRecord(
            uuid="k1", user_id="", agent_id="meta", record_type=RecordType.knowledge,
            full_content="hello world", created_date="2026-01-01",
        )
    )
    out = svc.edit("k1", "world", "there")
    assert out["content"] == "hello there"
    assert out["modified_date"] != "2026-01-01"


def test_edit_errors(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(MemoryRecord(uuid="k1", user_id="", agent_id="meta",
                             record_type=RecordType.knowledge, full_content="abc"))
    with pytest.raises(LookupError):
        svc.edit("missing", "a", "b")
    with pytest.raises(ValueError):
        svc.edit("k1", "not-present", "b")


def test_append_and_prepend(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="middle", uuid="e1")
    assert svc.append("e1", " end")["content"] == "middle end"
    assert svc.prepend("e1", "start ")["content"] == "start middle end"


def test_append_missing_raises_lookup(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(LookupError):
        svc.append("nope", "x")


def test_multi_edit_atomic_and_ordered(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="one two", uuid="e1")
    out = svc.multi_edit("e1", [
        {"old_string": "one", "new_string": "1"},
        {"old_string": "two", "new_string": "2"},
    ])
    assert out["content"] == "1 2"


def test_multi_edit_malformed_edit_raises_value(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="episode", content="body", uuid="e1")
    with pytest.raises(ValueError, match="old_string"):
        svc.multi_edit("e1", [{"new_string": "x"}])  # missing old_string


def test_archive_drops_from_hot_index_but_searchable(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="knowledge", content="findable token", uuid="k1")
    ack = svc.archive("k1")
    assert ack == {"uuid": "k1", "status": "archived"}
    assert svc.query(agent_id="meta") == []
    assert [r["uuid"] for r in svc.search("findable")] == ["k1"]


def test_soft_delete_excluded_everywhere(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type="knowledge", content="gone token", uuid="k1")
    ack = svc.soft_delete("k1")
    assert ack == {"uuid": "k1", "status": "deleted"}
    assert svc.get("k1") is None
    assert svc.query(agent_id="meta", include_archived=True) == []
    assert svc.search("gone") == []


def test_edit_metadata_changes_a_field_without_the_body(tmp_path: Path) -> None:
    """The whole point of the op: a field changes and the body is never handed back."""
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="first summary",
        agent_id="meta", record_type="knowledge", content="the body", uuid="k1",
        title="before", tags=["a"], project="hermod-server")
    out = svc.edit_metadata("k1", content_summary="second summary")
    assert out["content_summary"] == "second summary"
    assert out["content"] == "the body"
    assert out["title"] == "before"  # untouched, not cleared
    assert out["tags"] == ["a"]
    assert out["project"] == "hermod-server"


def test_edit_metadata_clears_and_empties(tmp_path: Path) -> None:
    """`clearing` is the only route to NULL, and `tags=[]` is a value rather than a blank:
    an empty string must not be able to remove a project, because both engines read a
    project row by `IS NULL`."""
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="s", agent_id="meta", record_type="knowledge", content="b",
        uuid="k1", project="hermod-server", tags=["a"])
    out = svc.edit_metadata("k1", clearing=["project"], tags=[])
    assert out["project"] is None
    assert out["tags"] == []
    assert out["content_summary"] == "s"


def test_edit_metadata_refuses_blank_values_and_empty_changes(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(
        content_summary="s", agent_id="meta", record_type="knowledge", content="b",
        uuid="k1", title="t")
    for field in ("title", "project", "content_summary"):
        with pytest.raises(ValueError, match=f"blank {field}"):
            svc.edit_metadata("k1", **{field: "   "})
    with pytest.raises(ValueError, match="nothing to change"):
        svc.edit_metadata("k1")
    with pytest.raises(ValueError, match="cannot clear"):
        svc.edit_metadata("k1", clearing=["record_type"])
    with pytest.raises(LookupError):
        svc.edit_metadata("absent", title="t")
