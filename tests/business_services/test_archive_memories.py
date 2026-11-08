"""MemoryService.archive_memories and unarchive ��" the scan, the apply, and the undo."""

from __future__ import annotations

import uuid as uuidlib
from pathlib import Path
from typing import Any

import pytest

from munnin.business_services.archive_rule import (
    FINISHED_TAG,
    NEWEST_OF_PROJECT,
    NEWEST_OVERALL,
)
from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from tests.conftest import AutoAgentRepository


def _svc(tmp_path: Path) -> tuple[Any, MemoryService]:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def _episode(
    *,
    project: str | None = "proj",
    created: str = "2026-01-01",
    modified: str | None = None,
    tags: list[str] | None = None,
    content: str = "body",
) -> MemoryRecord:
    return MemoryRecord(
        uuid=str(uuidlib.uuid4()),
        user_id="alvi",
        agent_id="meta",
        record_type=RecordType.episode,
        project=project,
        title=f"{project or 'none'}-theme-{uuidlib.uuid4().hex[:6]}",
        full_content=content,
        tags=tags or [],
        created_date=created,
        modified_date=modified or created,
    )


def _seed(repo: Any) -> dict[str, str]:
    """One tagged older episode and one newer live episode in the same project."""
    done = _episode(created="2026-01-01", tags=[FINISHED_TAG])
    live = _episode(created="2026-06-01")
    repo.insert(done)
    repo.insert(live)
    return {"done": done.uuid, "live": live.uuid}


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    ids = _seed(repo)
    out = svc.archive_memories("meta")
    assert [r["uuid"] for r in out["auto"]] == [ids["done"]]
    assert out["archived"] == []
    assert out["applied"] is False
    # the record is still live: a dry run must not have touched it
    assert [r["uuid"] for r in svc.query(agent_id="meta", record_type="episode")] == [
        ids["done"],
        ids["live"],
    ]


def test_apply_archives_exactly_the_auto_set(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    ids = _seed(repo)
    out = svc.archive_memories("meta", apply=True)
    assert out["archived"] == [ids["done"]]
    assert ids["done"] not in [
        r["uuid"] for r in svc.query(agent_id="meta", record_type="episode")
    ]
    assert ids["live"] in [
        r["uuid"] for r in svc.query(agent_id="meta", record_type="episode")
    ]


def test_a_second_apply_is_a_no_op(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    _seed(repo)
    first = svc.archive_memories("meta", apply=True)
    second = svc.archive_memories("meta", apply=True)
    assert first["archived"]
    assert second["archived"] == []
    assert second["auto"] == []


def test_the_newest_row_is_reported_protected_with_a_reason(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    ids = _seed(repo)
    other = _episode(project="other", created="2026-07-01")
    repo.insert(other)
    out = svc.archive_memories("meta")
    reasons = {r["uuid"]: r["reason"] for r in out["protected"]}
    assert reasons[ids["live"]] == NEWEST_OF_PROJECT
    assert reasons[other.uuid] == NEWEST_OVERALL


def test_ask_carries_the_aging_untagged_rows(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    stale = _episode(created="2026-01-01")
    live = _episode(created="2026-06-01")
    repo.insert(stale)
    repo.insert(live)
    out = svc.archive_memories("meta")
    assert [r["uuid"] for r in out["ask"]] == [stale.uuid]
    assert out["auto"] == []


def test_the_days_window_is_validated(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    for days in (0, -1, 3651):
        with pytest.raises(ValueError):
            svc.archive_memories("meta", days=days)


def test_an_invalid_domain_is_refused(tmp_path: Path) -> None:
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.archive_memories("Not A Domain")


def test_an_unknown_agent_is_refused(tmp_path: Path) -> None:
    """An agent this account does not have must not scan to three empty lists: that
    answer is indistinguishable from 'nothing to archive'."""
    _repo, svc = _svc(tmp_path)
    with pytest.raises(ValueError, match="no agent"):
        svc.archive_memories("no-such-agent")


def test_unarchive_returns_the_record_and_refuses_a_tombstone(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    ids = _seed(repo)
    svc.archive_memories("meta", apply=True)
    out = svc.unarchive(ids["done"])
    assert out == {"uuid": ids["done"], "status": "active"}
    assert ids["done"] in [
        r["uuid"] for r in svc.query(agent_id="meta", record_type="episode")
    ]
    repo.soft_delete(ids["done"])
    with pytest.raises(LookupError):
        svc.unarchive(ids["done"])


def test_the_scan_reads_no_body(tmp_path: Path) -> None:
    """A scan over a real store must not pay for content it never reads, which is what
    separates it from ``query``."""
    repo, svc = _svc(tmp_path)
    big = "x" * 20000
    done = _episode(created="2026-01-01", tags=[FINISHED_TAG], content=big)
    live = _episode(created="2026-06-01", content=big)
    repo.insert(done)
    repo.insert(live)
    out = svc.archive_memories("meta")
    for row in out["auto"] + out["ask"] + out["protected"]:
        assert "content" not in row
