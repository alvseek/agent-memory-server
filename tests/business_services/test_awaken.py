"""MemoryService.awaken() 4-layer assembly (SP-1 Step 3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import MemoryRecord, RecordType, SharedRecord
from tests.conftest import AutoAgentRepository


def _rec(uuid: str, agent_id: str, rtype: RecordType, **kw: object) -> MemoryRecord:
    base = dict(
        uuid=uuid,
        user_id="",
        agent_id=agent_id,
        record_type=rtype,
        full_content=f"body-{uuid}",
        title=uuid,
        created_date="2026-01-01",
    )
    base.update(kw)
    return MemoryRecord(**base)  # type: ignore[arg-type]


def _shared(uuid: str, rtype: RecordType, **kw: object) -> SharedRecord:
    base = dict(
        uuid=uuid,
        user_id="",
        record_type=rtype,
        full_content=f"body-{uuid}",
        title=uuid,
        created_date="2026-01-01",
    )
    base.update(kw)
    return SharedRecord(**base)  # type: ignore[arg-type]


def _service(tmp_path: Path) -> MemoryService:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    # layer i (shared) — its own table now, seeded through its own write path. The
    # assertions below are untouched: what changed is where fleet memory is stored,
    # not what awaken returns.
    repo.insert_shared(_shared("sr1", RecordType.reasoning))
    repo.insert_shared(_shared("sk1", RecordType.knowledge))
    # layer ii (domain)
    repo.insert(_rec("id1", "meta", RecordType.identity))
    repo.insert(_rec("em1", "meta", RecordType.emotional))
    # layer iii (domain)
    repo.insert(_rec("kn1", "meta", RecordType.knowledge, tags=["t"]))
    repo.insert(_rec("ep_old", "meta", RecordType.episode, created_date="2026-08-01"))
    repo.insert(_rec("ep_new", "meta", RecordType.episode, created_date="2026-08-09"))
    # noise: archived + deleted episodes must not surface
    repo.insert(_rec("ep_arch", "meta", RecordType.episode, archived_date="2026-02-01"))
    repo.insert(_rec("ep_del", "meta", RecordType.episode, deleted_date="2026-02-01"))
    return MemoryService(repo, user_id="alvi")


def test_awaken_assembles_four_layers(tmp_path: Path) -> None:
    payload = _service(tmp_path).awaken("meta")

    # layer i — shared, whole (has body)
    assert [r["uuid"] for r in payload["shared"]["reasoning"]] == ["sr1"]
    assert [r["uuid"] for r in payload["shared"]["knowledge"]] == ["sk1"]
    assert payload["shared"]["reasoning"][0]["content"] == "body-sr1"

    # layer ii — whole (has body)
    assert [r["uuid"] for r in payload["identity"]] == ["id1"]
    assert payload["identity"][0]["content"] == "body-id1"
    assert [r["uuid"] for r in payload["emotional"]] == ["em1"]

    # layer iii — index only (NO body key)
    assert [r["uuid"] for r in payload["knowledge_index"]] == ["kn1"]
    assert "content" not in payload["knowledge_index"][0]
    assert payload["knowledge_index"][0]["tags"] == ["t"]


def test_awaken_episodes_newest_first_and_latest_has_body(tmp_path: Path) -> None:
    payload = _service(tmp_path).awaken("meta")
    # newest-first, archived+deleted excluded
    assert [r["uuid"] for r in payload["episodic_index"]] == ["ep_new", "ep_old"]
    assert "content" not in payload["episodic_index"][0]
    # latest episode carries the body
    assert payload["latest_episode"]["uuid"] == "ep_new"
    assert payload["latest_episode"]["content"] == "body-ep_new"


def test_awaken_rejects_invalid_domain(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _service(tmp_path).awaken("__shared__")
