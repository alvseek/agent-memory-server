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
from munnin.data_migrations import markdown_parser as P
from munnin.data_migrations.importer import import_agent
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

_REAL = Path.home() / ".claude" / "@agent-memory"
_UUID_RE = re.compile(r"\*\*UUID\*\*:\s*`?([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})`?")

pytestmark = pytest.mark.skipif(not _REAL.exists(), reason="real @agent-memory source not present")


def _awaken_meta(tmp_path: Path) -> dict:
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
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
