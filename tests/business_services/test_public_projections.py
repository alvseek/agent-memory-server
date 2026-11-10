"""The two public projections that are **not** a body: a browse entry and a search hit.

The rule these tests defend is one sentence — a listing or a keyword search must never hand
out a record's body. ``query`` answers what matches plus how many blocks the body holds;
``search`` answers what matched plus the excerpt that matched. The body is a deliberate
``get`` in both cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import Agent
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account

ROLLING = "".join(
    f"### 2026-11-10 10.0{index} - block {index}\n\nbody {index}\n" for index in range(5, 0, -1)
)


def _service(tmp_path: Path) -> MemoryService:
    db = tmp_path / "m.db"
    seed_account(db, "alvi")
    repo = SqliteMemoryRepository(db, user_id="alvi")
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Meta"))
    return MemoryService(repo, user_id="alvi")


def _episode(svc: MemoryService, uuid: str, *, project: str | None, body: str = ROLLING) -> None:
    svc.insert(
        content_summary="a rolling episode", agent_id="meta", record_type="episode",
        project=project, content=body, uuid=uuid,
    )


# --- browse ---------------------------------------------------------------------------


def test_a_browse_entry_never_carries_a_body(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project="munnin")
    rows = svc.query(agent_id="meta")
    assert len(rows) == 1
    row = rows[0]
    assert "content" not in row and "full_content" not in row
    # What it does carry: identity, owner, lifecycle metadata, and the group count.
    assert row["uuid"] == "ep000001"
    assert row["agent_id"] == "meta"
    assert row["record_type"] == "episode"
    assert row["project"] == "munnin"
    assert row["archived_date"] is None
    assert row["blocks_total"] == 5


def test_both_corpora_are_listed_and_only_agent_rows_are_labelled(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project=None)
    svc.insert(scope="shared", record_type="reasoning", title="A rule", content="be slow")
    rows = svc.query()
    ownerless = [row for row in rows if "agent_id" not in row]
    owners = [row for row in rows if "agent_id" in row]
    assert len(owners) == 1 and len(ownerless) == 1
    assert ownerless[0]["record_type"] == "reasoning"


def test_record_type_and_project_filters_still_select_exactly(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project="munnin")
    _episode(svc, "ep000002", project="telemachus")
    assert [r["uuid"] for r in svc.query(project="munnin")] == ["ep000001"]
    assert [r["uuid"] for r in svc.query(record_type="episode")] == ["ep000001", "ep000002"]
    assert [r["uuid"] for r in svc.query(record_type="reasoning")] == []


def test_archived_is_opt_in_and_deleted_never_appears(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project=None)
    _episode(svc, "ep000002", project=None)
    svc.archive("ep000001")
    svc.soft_delete("ep000002")
    assert [r["uuid"] for r in svc.query(agent_id="meta")] == []
    assert [r["uuid"] for r in svc.query(agent_id="meta", include_archived=True)] == [
        "ep000001"
    ]
    assert svc.query(agent_id="meta", include_archived=True)[0]["archived_date"] is not None


def test_the_group_total_matches_the_page_engine_for_every_shape(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project=None)                       # five timestamp groups
    _episode(svc, "ep000002", project=None, body="no headings")   # untimed episode
    svc.insert(
        scope="shared", record_type="knowledge", title="Doc",
        content_summary="a doc with headings",
        content="### 2026-11-10 10.05 - looks like one\n\ntext\n",  # non-episode
    )
    totals = {row["uuid"]: row["blocks_total"] for row in svc.query(agent_id="meta")}
    assert totals == {"ep000001": 5, "ep000002": 1}
    shared = [row for row in svc.query() if row["record_type"] == "knowledge"]
    assert shared[0]["blocks_total"] == 1
    # And the number agrees with the page that a deliberate read would return.
    assert svc.get("ep000001", limit=1)["blocks_total"] == 5


# --- search ---------------------------------------------------------------------------


def test_a_search_hit_carries_a_snippet_and_no_body(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.insert(
        content_summary="a searchable note", agent_id="meta", record_type="episode",
        content="the pangolin lives in this body", uuid="ep000001",
    )
    hits = svc.search("pangolin")
    assert len(hits) == 1
    hit = hits[0]
    assert "content" not in hit and "full_content" not in hit
    assert "pangolin" in hit["snippet"]
    assert hit["uuid"] == "ep000001" and hit["agent_id"] == "meta"


def test_both_corpora_are_grouped_and_owner_absence_labels_the_fleet(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc.insert(
        content_summary="a searchable note", agent_id="meta", record_type="episode",
        content="pangolin in agent memory", uuid="ep000001",
    )
    svc.insert(scope="shared", record_type="reasoning", title="Fleet", content="pangolin rule")
    hits = svc.search("pangolin")
    assert [hit.get("agent_id") for hit in hits] == ["meta", None]
    assert all("snippet" in hit for hit in hits)


def test_search_never_returns_a_deleted_record_and_keeps_archived_by_default(
    tmp_path: Path,
) -> None:
    svc = _service(tmp_path)
    for uuid in ("ep000001", "ep000002"):
        svc.insert(
            content_summary="a searchable note", agent_id="meta", record_type="episode",
            content="wombat", uuid=uuid,
        )
    svc.archive("ep000001")
    svc.soft_delete("ep000002")
    assert [h["uuid"] for h in svc.search("wombat")] == ["ep000001"]
    assert svc.search("wombat", include_archived=False) == []


@pytest.mark.parametrize("query", ["", "   "])
def test_a_blank_search_is_empty(tmp_path: Path, query: str) -> None:
    svc = _service(tmp_path)
    _episode(svc, "ep000001", project=None)
    assert svc.search(query) == []


# --- cross-tenant control -------------------------------------------------------------


def test_neither_projection_crosses_a_tenant_boundary(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    for tenant in ("alvi", "interviewer"):
        seed_account(db, tenant)
        SqliteMemoryRepository(db, user_id=tenant).upsert_agent(
            Agent(user_id="", agent_id="meta", name="Meta")
        )
    mine = MemoryService(SqliteMemoryRepository(db, user_id="alvi"), user_id="alvi")
    theirs = MemoryService(SqliteMemoryRepository(db, user_id="interviewer"), user_id="interviewer")
    mine.insert(
        content_summary="a searchable note", agent_id="meta", record_type="episode",
        content="pangolin", uuid="ep000001",
    )
    assert theirs.query() == []
    assert theirs.search("pangolin") == []
