"""Episode reads: a page of timestamp groups from ``awaken`` and from ``get``.

The page engine's own contract is proven in ``test_episode_page.py`` against shared vectors.
What is proven here is the *service* around it: which layer is paged, what stays whole, and
that a deliberate read resumes exactly where a previous one stopped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType, SharedRecord
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account

#: A rolling episode: five sub-episodes, newest first, each one timestamp group.
BLOCKS = [
    "### 2026-11-10 10.05 - five\n\nbody five\n",
    "### 2026-11-10 10.04 - four\n\nbody four\n",
    "### 2026-11-10 10.03 - three\n\nbody three\n",
    "### 2026-11-10 10.02 - two\n\nbody two\n",
    "### 2026-11-10 10.01 - one\n\nbody one\n",
]
EPISODE = "".join(BLOCKS)
#: A real 32-hex id, because prefix addressing is part of what this read must keep working.
EPISODE_UUID = "abcdef0123456789abcdef0123456789"
#: An identity body that happens to contain H3 headings â€” none of them may be a page boundary.
IDENTITY = "# Meta identity\n\n### Standing rules\n\nstay slow\n"


def _service(tmp_path: Path, *, ceiling: int = 32_000):
    db = tmp_path / "m.db"
    seed_account(db, "alvi")
    repo = SqliteMemoryRepository(db, user_id="alvi")
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Meta"))
    return repo, MemoryService(repo, user_id="alvi", max_body_bytes=ceiling)


def _seed(repo: SqliteMemoryRepository, *, project: str | None = "munnin") -> None:
    repo.insert(
        MemoryRecord(
            uuid="identity-1", user_id="", agent_id="meta",
            record_type=RecordType.identity, title="Identity",
            full_content=IDENTITY, created_date="2026-01-01",
        )
    )
    repo.insert_shared(
        SharedRecord(
            uuid="reasoning-1", user_id="", record_type=RecordType.reasoning,
            title="Slow is fast", full_content="Be thorough. ### Not a boundary",
            created_date="2026-01-01",
        )
    )
    repo.insert(
        MemoryRecord(
            uuid=EPISODE_UUID, user_id="", agent_id="meta",
            record_type=RecordType.episode, title="Rolling episode",
            project=project, full_content=EPISODE, created_date="2026-11-10",
            content_summary="five sub-episodes",
        )
    )


# --- awaken ---------------------------------------------------------------------------


def test_awaken_pages_the_latest_episode_and_keeps_every_other_layer_whole(
    tmp_path: Path,
) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)

    payload = svc.awaken("meta")
    latest = payload["latest_episode"]
    assert latest["uuid"] == EPISODE_UUID
    assert latest["blocks_returned"] == 3
    assert latest["blocks_total"] == 5
    assert latest["next_cursor"] == "2026-11-10 10.02"
    assert latest["content"] == "".join(BLOCKS[:3])
    # The other layers are byte-for-byte what they always were, headings included.
    assert payload["identity"][0]["content"] == IDENTITY
    assert payload["shared"]["reasoning"][0]["content"] == "Be thorough. ### Not a boundary"


def test_awakening_traversal_reaches_the_whole_body(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)

    latest = svc.awaken("meta")["latest_episode"]
    collected = [latest["content"]]
    cursor = latest["next_cursor"]
    while cursor is not None:
        page = svc.get(latest["uuid"], cursor=cursor)
        collected.append(page["content"])
        cursor = page["next_cursor"]
    assert "".join(collected) == EPISODE
    assert len(collected) == 2


def test_awaken_without_an_episode_answers_none(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    repo.insert(
        MemoryRecord(
            uuid="identity-1", user_id="", agent_id="meta",
            record_type=RecordType.identity, title="Identity", full_content="only me",
            created_date="2026-01-01",
        )
    )
    assert svc.awaken("meta")["latest_episode"] is None


def test_awaken_stays_project_blind_and_the_index_still_names_every_project(
    tmp_path: Path,
) -> None:
    """The newest episode overall is what a chat agent gets, and the index still carries
    the whole choice â€” a project is selected by the caller, never resolved here."""
    repo, svc = _service(tmp_path)
    _seed(repo, project="munnin")
    repo.insert(
        MemoryRecord(
            uuid="episode-2", user_id="", agent_id="meta",
            record_type=RecordType.episode, title="Another project",
            project="telemachus", full_content="### 2026-11-11 09.00 - newer\n\nnewer\n",
            created_date="2026-11-11", content_summary="one block",
        )
    )

    payload = svc.awaken("meta")
    assert payload["latest_episode"]["uuid"] == "episode-2"
    assert payload["latest_episode"]["project"] == "telemachus"
    assert {row["project"] for row in payload["episodic_index"]} == {"munnin", "telemachus"}


# --- deliberate reads -----------------------------------------------------------------


def test_get_returns_the_whole_record_by_default(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)

    record = svc.get(EPISODE_UUID)
    assert record["content"] == EPISODE
    assert record["blocks_returned"] == record["blocks_total"] == 5
    assert record["next_cursor"] is None


def test_get_pages_on_request_and_resumes_inclusively(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)

    first = svc.get(EPISODE_UUID, limit=2)
    assert first["content"] == BLOCKS[0] + BLOCKS[1]
    assert (first["blocks_returned"], first["blocks_total"]) == (2, 5)
    assert first["next_cursor"] == "2026-11-10 10.03"

    second = svc.get(EPISODE_UUID, cursor=first["next_cursor"], limit=2)
    assert second["content"] == BLOCKS[2] + BLOCKS[3]
    assert second["next_cursor"] == "2026-11-10 10.01"

    last = svc.get(EPISODE_UUID, cursor=second["next_cursor"], limit=2)
    assert last["content"] == BLOCKS[4]
    assert (last["blocks_returned"], last["blocks_total"]) == (1, 5)
    assert last["next_cursor"] is None


def test_a_final_page_can_return_fewer_than_total_with_nothing_left(tmp_path: Path) -> None:
    """The reason ``next_cursor`` â€” not the count inequality â€” is the continuation signal."""
    repo, svc = _service(tmp_path)
    _seed(repo)
    last = svc.get(EPISODE_UUID, cursor="2026-11-10 10.03")
    assert last["blocks_returned"] < last["blocks_total"]
    assert last["next_cursor"] is None


def test_the_ceiling_caps_a_default_read_without_splitting_a_block(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path, ceiling=70)
    _seed(repo)

    page = svc.get(EPISODE_UUID)
    assert page["blocks_returned"] == 1
    assert page["blocks_total"] == 5
    assert page["content"] == BLOCKS[0]
    assert page["next_cursor"] == "2026-11-10 10.04"


def test_get_refuses_bad_paging_arguments(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)
    with pytest.raises(ValueError, match="cursor"):
        svc.get(EPISODE_UUID, cursor="not-a-timestamp")
    with pytest.raises(ValueError, match="cursor"):
        svc.get(EPISODE_UUID, cursor="2020-01-01 00.00")
    with pytest.raises(ValueError, match="limit"):
        svc.get(EPISODE_UUID, limit=0)


def test_an_absent_record_is_still_none(tmp_path: Path) -> None:
    """Absence wins before paging is even considered: a missing record has no page to
    refuse, and inventing an error for it would replace today's answer."""
    repo, svc = _service(tmp_path)
    assert svc.get("deadbeef" * 4, cursor="nonsense") is None
    assert svc.get("deadbeef" * 4, limit=0) is None


def test_a_prefix_reference_pages_identically_to_the_full_id(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)
    full = svc.get(EPISODE_UUID, limit=2)
    by_prefix = svc.get(EPISODE_UUID[:6], limit=2)
    assert by_prefix == full


def test_a_non_episode_record_is_one_indivisible_block(tmp_path: Path) -> None:
    """A knowledge body may contain H3 headings that look like timestamps; the record type,
    not the text, decides whether a body is a rolling document."""
    repo, svc = _service(tmp_path)
    repo.insert_shared(
        SharedRecord(
            uuid="knowledge-1", user_id="", record_type=RecordType.knowledge,
            title="Knowledge", content_summary="a doc with headings",
            full_content="### 2026-11-10 10.05 - looks like a boundary\n\ntext\n",
        )
    )
    page = svc.get("knowledge-1", limit=1)
    assert page["blocks_total"] == 1
    assert page["content"] == "### 2026-11-10 10.05 - looks like a boundary\n\ntext\n"


def test_an_episode_without_timestamps_is_one_block(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    repo.insert(
        MemoryRecord(
            uuid="episode-plain", user_id="", agent_id="meta",
            record_type=RecordType.episode, title="Plain", content_summary="no timestamps",
            full_content="a body with no sub-episode headings at all",
        )
    )
    page = svc.get("episode-plain")
    assert page["blocks_total"] == page["blocks_returned"] == 1
    assert page["next_cursor"] is None


def test_reads_never_mutate_the_store(tmp_path: Path) -> None:
    repo, svc = _service(tmp_path)
    _seed(repo)
    before = repo.get(EPISODE_UUID)
    svc.awaken("meta")
    svc.get(EPISODE_UUID, limit=1)
    svc.get(EPISODE_UUID, cursor="2026-11-10 10.03")
    after = repo.get(EPISODE_UUID)
    assert (after.full_content, after.modified_date, after.archived_date) == (
        before.full_content, before.modified_date, before.archived_date
    )


# --- both engines ---------------------------------------------------------------------
#
# The ``memory_repo`` fixture is the repository contract's own seat: SQLite in the default
# suite, and the same assertions against a real PostgreSQL once ``MUNNIN_PG_TEST_URL`` is
# set (the CI-backed fixture, which resets its own schema). Paging is a service-layer rule
# over a body, so proving it here proves it on both stores without a second implementation.


def test_the_page_contract_holds_on_both_engines(memory_repo) -> None:
    svc = MemoryService(memory_repo, user_id="alvi")
    memory_repo.insert(
        MemoryRecord(
            uuid=EPISODE_UUID, user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Rolling", full_content=EPISODE, content_summary="five sub-episodes",
        )
    )

    first = svc.get(EPISODE_UUID, limit=2)
    assert first["content"] == BLOCKS[0] + BLOCKS[1]
    assert (first["blocks_returned"], first["blocks_total"]) == (2, 5)
    second = svc.get(EPISODE_UUID, cursor=first["next_cursor"], limit=2)
    assert second["content"] == BLOCKS[2] + BLOCKS[3]
    assert second["next_cursor"] == "2026-11-10 10.01"
    # An unbounded read still returns the stored body byte for byte on either engine.
    whole = svc.get(EPISODE_UUID)
    assert whole["content"].encode("utf-8") == EPISODE.encode("utf-8")
    assert whole["next_cursor"] is None


def test_a_browse_listing_carries_no_body_on_either_engine(memory_repo) -> None:
    svc = MemoryService(memory_repo, user_id="alvi")
    memory_repo.insert(
        MemoryRecord(
            uuid=EPISODE_UUID, user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Rolling", full_content=EPISODE, content_summary="five sub-episodes",
        )
    )
    rows = svc.query(record_type="episode")
    assert len(rows) == 1
    assert rows[0]["blocks_total"] == 5
    assert "content" not in rows[0] and "full_content" not in rows[0]

