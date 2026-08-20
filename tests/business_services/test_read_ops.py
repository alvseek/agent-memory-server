"""MemoryService read ops — get / query / search (SP-3 Step 1.1).

Seed a temp SqliteMemoryRepository directly, then exercise the core read methods.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import AutoAgentRepository


def _svc(tmp_path: Path) -> tuple[SqliteMemoryRepository, MemoryService]:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def _mk(uuid: str, agent: str, rtype: RecordType, content: str, **kw: object) -> MemoryRecord:
    return MemoryRecord(
        uuid=uuid, user_id="", agent_id=agent, record_type=rtype, full_content=content, **kw
    )


def test_get_round_trip(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("ep1", "meta", RecordType.episode, "episode body", title="t1"))
    got = svc.get("ep1")
    assert got is not None
    assert got["uuid"] == "ep1"
    assert got["content"] == "episode body"
    assert got["record_type"] == "episode"
    # internal fields are not exposed
    assert "id" not in got
    assert "user_id" not in got


def test_get_missing_returns_none(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    assert svc.get("nope") is None


def test_query_filters_by_agent_and_type(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("ep1", "meta", RecordType.episode, "e"))
    repo.insert(_mk("kn1", "meta", RecordType.knowledge, "k"))
    repo.insert(_mk("ep2", "other", RecordType.episode, "e2"))

    eps = svc.query(agent_id="meta", record_type="episode")
    assert {r["uuid"] for r in eps} == {"ep1"}


def test_query_excludes_archived_unless_requested(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("ep1", "meta", RecordType.episode, "live"))
    repo.insert(_mk("ep2", "meta", RecordType.episode, "old"))
    repo.archive("ep2")

    hot = {r["uuid"] for r in svc.query(agent_id="meta")}
    assert hot == {"ep1"}
    witharch = {r["uuid"] for r in svc.query(agent_id="meta", include_archived=True)}
    assert witharch == {"ep1", "ep2"}


def test_search_finds_by_text(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("kn1", "meta", RecordType.knowledge, "the FTS5 inverted index"))
    repo.insert(_mk("kn2", "meta", RecordType.knowledge, "unrelated content"))

    hits = svc.search("inverted")
    assert [r["uuid"] for r in hits] == ["kn1"]
