"""M0 semantic fidelity gate (SP-1 Step 4.1).

Import agent-meta's real markdown → awaken('meta') → assert the assembled payload
is semantically equivalent to the source (every item present, correct layer). Not
byte-identical (Decision D4). Skipped if the real @agent-memory tree is absent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import RecordType
from munnin.data_migrations import markdown_parser as P
from munnin.data_migrations.importer import import_agent, import_fleet, import_shared
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import AutoAgentRepository

_REAL = Path.home() / ".claude" / "@agent-memory"
_UUID_RE = re.compile(r"\*\*UUID\*\*:\s*`?([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})`?")

pytestmark = pytest.mark.skipif(not _REAL.exists(), reason="real @agent-memory source not present")


def _awaken_meta(tmp_path: Path) -> dict:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_shared(repo, _REAL)
    import_agent(repo, _REAL, "meta")
    return MemoryService(repo, user_id="alvi").awaken("meta")


def test_shared_reasoning_uuids_all_present(tmp_path: Path) -> None:
    payload = _awaken_meta(tmp_path)
    src = (_REAL / "shared-memory" / "core-reasoning-memory.md").read_text(encoding="utf-8")
    file_uuids = set(_UUID_RE.findall(src))
    got = {r["uuid"] for r in payload["shared"]["reasoning"]}
    assert file_uuids, "expected embedded UUIDs in shared reasoning"
    assert file_uuids <= got  # every shared reasoning pattern survived import→awaken


def test_identity_and_emotional_counts_match_source(tmp_path: Path) -> None:
    payload = _awaken_meta(tmp_path)
    core = (_REAL / "agent-meta" / "agent-core-memory.md").read_text(encoding="utf-8")
    parsed = P.parse_agent_core(core)
    assert len(payload["identity"]) == 3
    assert len(payload["emotional"]) == len(parsed["emotional"]) >= 10
    # bodies are present for always-load sections
    assert all(item["content"] for item in payload["emotional"])


def test_episodic_and_knowledge_index_match_source(tmp_path: Path) -> None:
    payload = _awaken_meta(tmp_path)
    idx = (_REAL / "agent-meta" / "agent-memory-index.md").read_text(encoding="utf-8")
    active = P.parse_active_episodes(idx)
    assert len(payload["episodic_index"]) == len(active) >= 5
    assert len(payload["knowledge_index"]) == len(P.parse_knowledge_index(idx))
    # index items are metadata-only (no body); latest episode carries a body
    assert all("content" not in item for item in payload["episodic_index"])
    assert payload["latest_episode"] and payload["latest_episode"]["content"]


def test_shared_knowledge_present(tmp_path: Path) -> None:
    payload = _awaken_meta(tmp_path)
    assert len(payload["shared"]["knowledge"]) >= 1
    assert all(item["content"] for item in payload["shared"]["knowledge"])


# --- SP-4: full-fleet round-trip fidelity gate ---


_Fleet = tuple["MemoryService", "SqliteMemoryRepository", Path]


@pytest.fixture(scope="module")
def _fleet() -> _Fleet:
    import tempfile

    db = Path(tempfile.mkdtemp(prefix="munnin-fleet-")) / "m.db"
    repo = AutoAgentRepository(db, user_id="alvi")
    import_fleet(repo, _REAL)
    return MemoryService(repo, user_id="alvi"), repo, db


def test_fleet_fidelity_all_agents(_fleet: _Fleet) -> None:
    svc, _repo, _db = _fleet
    for agent_dir in sorted(_REAL.glob("agent-*")):
        if not agent_dir.is_dir():
            continue
        agent = agent_dir.name[len("agent-") :]
        payload = svc.awaken(agent)
        core = (agent_dir / "agent-core-memory.md").read_text(encoding="utf-8")
        parsed = P.parse_agent_core(core)
        idx_path = agent_dir / "agent-memory-index.md"
        idx = idx_path.read_text(encoding="utf-8") if idx_path.exists() else ""
        # always-load layers: exact per-section item counts vs the source markdown
        assert len(payload["identity"]) == len(parsed["identity"]), f"{agent} identity"
        assert len(payload["reasoning"]) == len(parsed["reasoning"]), f"{agent} reasoning"
        assert len(payload["emotional"]) == len(parsed["emotional"]), f"{agent} emotional"
        # on-demand indexes: active only (archived excluded). A dangling index ref (points
        # at a file no longer on disk) can't be migrated, so compare against refs that exist.
        active_refs = [r for r in P.parse_active_episodes(idx) if (agent_dir / r["file"]).is_file()]
        assert len(payload["episodic_index"]) == len(active_refs), f"{agent} episodic"
        knowledge_refs = P.parse_knowledge_index(idx)
        assert len(payload["knowledge_index"]) == len(knowledge_refs), f"{agent} knowledge"


def test_fleet_active_archived_split(_fleet: _Fleet) -> None:
    svc, repo, _db = _fleet
    payload = svc.awaken("meta")
    active = len(payload["episodic_index"])
    allep = len(repo.query(agent_id="meta", record_type=RecordType.episode, include_archived=True))
    assert allep > active  # archived episodes exist and are excluded from awaken's hot index
    # a known archived (unindexed) episode is still findable via search
    hits = repo.search("4layer", include_archived=True)
    assert any(r.record_type is RecordType.episode and r.archived_date for r in hits)


def test_fleet_import_idempotent(tmp_path: Path) -> None:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_fleet(repo, _REAL)
    n1 = len(repo.query(include_archived=True))
    import_fleet(repo, _REAL)  # re-run over the real fleet
    n2 = len(repo.query(include_archived=True))
    assert n1 == n2  # deterministic uuid5 → upsert, no duplicates
