"""MemoryService write ops — insert / edit / archive / soft_delete (SP-3 Step 1.2).

The service assembles the record server-side; the repo stamps user_id + dates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _svc(tmp_path: Path) -> tuple[SqliteMemoryRepository, MemoryService]:
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def test_insert_round_trip_generates_uuid(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    out = svc.insert(agent_id="meta", record_type="episode", content="body", title="t")
    assert out["uuid"]  # server-generated
    assert out["content"] == "body"
    assert out["record_type"] == "episode"
    assert svc.get(out["uuid"])["content"] == "body"


def test_insert_is_idempotent_upsert(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(agent_id="meta", record_type="episode", content="A", uuid="dup")
    svc.insert(agent_id="meta", record_type="episode", content="B", uuid="dup")
    rows = svc.query(agent_id="meta")
    assert len(rows) == 1
    assert rows[0]["content"] == "B"


def test_insert_accepts_shared_sentinel(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    out = svc.insert(agent_id="__shared__", record_type="reasoning", content="pattern")
    assert out["agent_id"] == "__shared__"


def test_insert_rejects_bad_agent_and_type(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.insert(agent_id="Bad_Name", record_type="episode", content="x")
    with pytest.raises(ValueError):
        svc.insert(agent_id="meta", record_type="bogus", content="x")


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
    svc.insert(agent_id="meta", record_type="episode", content="middle", uuid="e1")
    assert svc.append("e1", " end")["content"] == "middle end"
    assert svc.prepend("e1", "start ")["content"] == "start middle end"


def test_append_missing_raises_lookup(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(LookupError):
        svc.append("nope", "x")


def test_multi_edit_atomic_and_ordered(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(agent_id="meta", record_type="episode", content="one two", uuid="e1")
    out = svc.multi_edit("e1", [
        {"old_string": "one", "new_string": "1"},
        {"old_string": "two", "new_string": "2"},
    ])
    assert out["content"] == "1 2"


def test_multi_edit_malformed_edit_raises_value(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(agent_id="meta", record_type="episode", content="body", uuid="e1")
    with pytest.raises(ValueError, match="old_string"):
        svc.multi_edit("e1", [{"new_string": "x"}])  # missing old_string


def test_archive_drops_from_hot_index_but_searchable(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(agent_id="meta", record_type="knowledge", content="findable token", uuid="k1")
    ack = svc.archive("k1")
    assert ack == {"uuid": "k1", "status": "archived"}
    assert svc.query(agent_id="meta") == []
    assert [r["uuid"] for r in svc.search("findable")] == ["k1"]


def test_soft_delete_excluded_everywhere(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    svc.insert(agent_id="meta", record_type="knowledge", content="gone token", uuid="k1")
    ack = svc.soft_delete("k1")
    assert ack == {"uuid": "k1", "status": "deleted"}
    assert svc.get("k1") is None
    assert svc.query(agent_id="meta", include_archived=True) == []
    assert svc.search("gone") == []
