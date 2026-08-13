"""Importer tests — hermetic fake tree + real-source smoke.

SP-4: full-fleet, `import_shared` extracted, active/archived split (archived = a file
absent from the index), real knowledge bodies, project-knowledge skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import SHARED_AGENT_ID, RecordType
from munnin.data_migrations.importer import (
    import_agent,
    import_fleet,
    import_shared,
)
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
    # episodes: e1/e2 are indexed (active); the dated one is NOT indexed (archived)
    (agent / "episodes" / "e1.md").write_text("# Newest episode\nbody1", encoding="utf-8")
    (agent / "episodes" / "e2.md").write_text("# Older episode\nbody2", encoding="utf-8")
    (agent / "episodes" / "2025-01-01-old-session.md").write_text(
        "# Old session\narchived body", encoding="utf-8"
    )
    # knowledge-base: pain.md indexed (active, real body); orphan.md unindexed (archived);
    # agent-memory/ is project-scoped (has context-index.md) → skipped.
    kb = agent / "knowledge-base"
    (kb / "memory-architecture").mkdir(parents=True)
    (kb / "memory-architecture" / "pain.md").write_text(
        "# Pain\nreal pain body", encoding="utf-8"
    )
    (kb / "research").mkdir(parents=True)
    (kb / "research" / "orphan.md").write_text("# Orphan\norphan body", encoding="utf-8")
    (kb / "agent-memory").mkdir(parents=True)
    (kb / "agent-memory" / "context-index.md").write_text("# ctx", encoding="utf-8")
    (kb / "agent-memory" / "proj.md").write_text("# Proj\nproject knowledge", encoding="utf-8")
    # a second, minimal agent for the fleet test
    foo = root / "agent-foo"
    foo.mkdir(parents=True)
    (foo / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nI am foo.\n", encoding="utf-8"
    )
    # shared always-load layer
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
    shared = import_shared(repo, src)
    counts = import_agent(repo, src, "meta")

    assert counts["meta/identity"] == 3
    assert "meta/reasoning" not in counts  # empty domain reasoning
    assert counts["meta/emotional"] == 2
    assert shared[f"{SHARED_AGENT_ID}/reasoning"] == 1
    assert shared[f"{SHARED_AGENT_ID}/knowledge"] == 1
    assert counts["meta/knowledge"] == 2  # 1 active (pain) + 1 archived (orphan); proj.md skipped
    assert counts["meta/episode"] == 3  # 2 active + 1 archived

    # shared reasoning reused its embedded UUID
    assert repo.get("fc94d140-905e-4f3d-8175-fafd8b84a109") is not None
    # active episodes carry the index date + full body
    active_eps = repo.query(agent_id="meta", record_type=RecordType.episode)
    assert {e.created_date for e in active_eps} == {"2026-08-09", "2026-08-08"}
    assert any("body1" in e.full_content for e in active_eps)


def test_active_knowledge_uses_real_file_body(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    active_kn = repo.query(agent_id="meta", record_type=RecordType.knowledge)
    pain = next(k for k in active_kn if k.title == "Pain")
    assert "real pain body" in pain.full_content  # real file, not the index description


def test_archived_episode_split(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    hot = repo.query(agent_id="meta", record_type=RecordType.episode)  # active only
    allep = repo.query(agent_id="meta", record_type=RecordType.episode, include_archived=True)
    assert len(hot) == 2
    assert len(allep) == 3
    archived = next(e for e in allep if e.title == "2025-01-01-old-session")
    assert archived.archived_date == "2025-01-01"
    # archived is out of the hot index but still searchable
    assert any(r.title == "2025-01-01-old-session" for r in repo.search("archived"))


def test_project_knowledge_skipped(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    allkn = repo.query(agent_id="meta", record_type=RecordType.knowledge, include_archived=True)
    assert not any("project knowledge" in (k.full_content or "") for k in allkn)
    # the archived (unindexed, non-project) orphan IS imported
    assert any(k.title == "Orphan" for k in allkn)


def test_import_fleet_imports_all_agents_shared_once(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    totals = import_fleet(repo, src)
    assert totals["meta/identity"] == 3
    assert totals["foo/identity"] == 1
    # shared imported exactly once (2 rows total), not once-per-agent
    shared_rows = repo.query(agent_id=SHARED_AGENT_ID, include_archived=True)
    assert len(shared_rows) == 2


def test_import_is_idempotent(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_fleet(repo, src)
    n1 = len(repo.query(include_archived=True))
    import_fleet(repo, src)  # re-run
    n2 = len(repo.query(include_archived=True))
    assert n1 == n2  # upsert, no duplicates


def test_awaken_latest_episode_is_newest_by_real_date(tmp_path: Path) -> None:
    """Regression (P8): rich index headers (`📂 YYYY-MM-DD HH.MM (label):`) name
    THEME-named active episodes (no date filename prefix). Their real index date must
    flow through to ``created_date`` so awaken's ``latest_episode`` is the genuinely-newest
    by date — NOT an arbitrary import-time tie among undated rows. Filenames are chosen so
    the id-tiebreak alone would pick the WRONG (older) episode pre-fix."""
    src = tmp_path / "src"
    agent = src / "agent-arch"
    (agent / "episodes").mkdir(parents=True)
    (src / "shared-memory").mkdir(parents=True)
    (src / "shared-memory" / "core-reasoning-memory.md").write_text("# R\n", encoding="utf-8")
    (src / "shared-memory" / "core-knowledge-memory.md").write_text("# K\n", encoding="utf-8")
    (agent / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nI am arch.\n", encoding="utf-8"
    )
    # a-newest (2026-08-11) sorts BEFORE z-middle (2026-08-10) in the glob → lower id.
    # Pre-fix both are undated → import-time tie → id-desc tiebreak picks z-middle (WRONG).
    (agent / "agent-memory-index.md").write_text(
        "# Recent Context Episodes\n"
        "## 📅 Interactions List\n"
        "📂 2026-08-11 10.44 (NEWEST: theme-named, rich header):\n"
        "- [a-newest.md](episodes/a-newest.md) - newest active\n"
        "📂 2026-08-10 07.40 (MIDDLE):\n"
        "- [z-middle.md](episodes/z-middle.md) - middle active\n",
        encoding="utf-8",
    )
    (agent / "episodes" / "a-newest.md").write_text("# Newest\nbody", encoding="utf-8")
    (agent / "episodes" / "z-middle.md").write_text("# Middle\nbody", encoding="utf-8")
    # an UNINDEXED theme-named file → archived → must never win latest_episode even though
    # its created_date defaults to the (lexically-largest) import timestamp.
    (agent / "episodes" / "orphan.md").write_text("# Orphan\nbody", encoding="utf-8")

    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    import_shared(repo, src)
    import_agent(repo, src, "arch")

    # (a) active theme-named episodes carry their REAL index date, not the import timestamp
    active = repo.query(agent_id="arch", record_type=RecordType.episode)
    assert {e.created_date for e in active} == {"2026-08-11", "2026-08-10"}

    # (b) awaken's latest_episode is the genuinely-newest by real date
    payload = MemoryService(repo, user_id="alvi").awaken("arch")
    assert payload["latest_episode"]["title"] == "a-newest"
    assert payload["latest_episode"]["created_date"] == "2026-08-11"


_REAL = Path.home() / ".claude" / "@agent-memory"


@pytest.mark.skipif(not _REAL.exists(), reason="real @agent-memory source not present")
def test_import_real_agent_meta(tmp_path: Path) -> None:
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    shared = import_shared(repo, _REAL)
    counts = import_agent(repo, _REAL, "meta")
    assert counts["meta/identity"] == 3
    assert counts["meta/emotional"] >= 10
    assert shared[f"{SHARED_AGENT_ID}/reasoning"] >= 10
    assert counts["meta/episode"] >= 100  # active + archived
    active = repo.query(agent_id="meta", record_type=RecordType.episode)
    allep = repo.query(agent_id="meta", record_type=RecordType.episode, include_archived=True)
    assert len(active) < len(allep)  # archived split holds
    assert len(allep) == counts["meta/episode"]
