"""Importer tests (SP-1 Step 2.2) — hermetic fake tree + real-source smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_entities.memory_record import SHARED_AGENT_ID, RecordType
from munnin.data_migrations.importer import import_agent
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _fake_source(root: Path) -> Path:
    agent = root / "agent-meta"
    (agent / "episodes").mkdir(parents=True)
    (root / "shared-memory").mkdir(parents=True)
    (agent / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nI am meta.\n"
        "# DOMAIN CORE KNOWLEDGE\ncore\n"
        "# DOMAIN RAS\ntrig\n"
        "# DOMAIN REASONING MEMORY\n<!-- content here -->\n"
        "# DOMAIN EMOTIONAL MEMORY\n### 2026-08-09 - FIRST\nyay\n### 2026-08-07 - SECOND\nnice\n",
        encoding="utf-8",
    )
    (agent / "agent-memory-index.md").write_text(
        "# Recent Context Episodes\n"
        "📂 2026-08-09:\n- [e1.md](episodes/e1.md) - newest\n"
        "📂 2026-08-08:\n- [e2.md](episodes/e2.md) - older\n"
        "# Core Knowledge Base\n"
        "- **[Pain](memory-architecture/pain.md)** - anchoring\n",
        encoding="utf-8",
    )
    (agent / "episodes" / "e1.md").write_text("# Newest episode\nbody1", encoding="utf-8")
    (agent / "episodes" / "e2.md").write_text("# Older episode\nbody2", encoding="utf-8")
    (root / "shared-memory" / "core-reasoning-memory.md").write_text(
        "# REASONING\n### **BE THOROUGH**\n"
        "**UUID**: fc94d140-905e-4f3d-8175-fafd8b84a109\ngo slow\n",
        encoding="utf-8",
    )
    (root / "shared-memory" / "core-knowledge-memory.md").write_text(
        "# KNOWLEDGE\n## AREA\n### **Line Endings**\nuse LF\n",
        encoding="utf-8",
    )
    return root


def test_import_fake_tree_counts_and_layers(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    counts = import_agent(repo, src, "meta")

    assert counts["meta/identity"] == 3
    assert "meta/reasoning" not in counts  # empty domain reasoning
    assert counts["meta/emotional"] == 2
    assert counts[f"{SHARED_AGENT_ID}/reasoning"] == 1
    assert counts[f"{SHARED_AGENT_ID}/knowledge"] == 1
    assert counts["meta/knowledge"] == 1
    assert counts["meta/episode"] == 2

    # shared reasoning reused its embedded UUID
    assert repo.get("fc94d140-905e-4f3d-8175-fafd8b84a109") is not None
    # episodes carry the index date + full body
    eps = repo.query(agent_id="meta", record_type=RecordType.episode)
    assert {e.created_date for e in eps} == {"2026-08-09", "2026-08-08"}
    assert any("body1" in e.full_content for e in eps)


def test_import_is_idempotent(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    n1 = len(repo.query()) + len(repo.query(include_archived=True))
    import_agent(repo, src, "meta")  # re-run
    n2 = len(repo.query()) + len(repo.query(include_archived=True))
    assert n1 == n2  # upsert, no duplicates


_REAL = Path.home() / ".claude" / "@agent-memory"


@pytest.mark.skipif(not _REAL.exists(), reason="real @agent-memory source not present")
def test_import_real_agent_meta(tmp_path: Path) -> None:
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    counts = import_agent(repo, _REAL, "meta")
    assert counts["meta/identity"] == 3
    assert counts["meta/emotional"] >= 10
    assert counts[f"{SHARED_AGENT_ID}/reasoning"] >= 10
    assert counts["meta/episode"] >= 5
    # all imported active (archived_date NULL) → visible without include_archived
    active_eps = repo.query(agent_id="meta", record_type=RecordType.episode)
    assert len(active_eps) == counts["meta/episode"]
