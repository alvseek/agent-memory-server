"""Exporter tests: store records that markdown lacks get a markdown home, so a --purge
reimport keeps them instead of dropping them."""

from __future__ import annotations

from pathlib import Path

from munnin.data_entities.identity import Account
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_migrations.exporter import compare, export_db_only
from munnin.data_migrations.importer import import_fleet
from munnin.data_repositories.identity_repository import IdentityRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

FOLDER = "\U0001f4c2"


def _store(root: Path) -> Path:
    agent = root / "agent-meta"
    (agent / "episodes").mkdir(parents=True)
    (root / "shared-memory").mkdir(parents=True)
    (agent / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nI am meta.\n**Name**: Claude Meta\n**Role**: Meta Agent\n"
        "# DOMAIN CORE KNOWLEDGE\ncore\n"
        "# DOMAIN RAS\ntrig\n"
        "# DOMAIN REASONING MEMORY\n<!-- none -->\n"
        "# DOMAIN EMOTIONAL MEMORY\n### 2026-08-09 - FIRST\nyay\n",
        encoding="utf-8",
    )
    (agent / "agent-memory-index.md").write_text(
        "# Recent Context Episodes\n"
        "## Interactions List\n"
        f"{FOLDER} 2026-10-07:\n"
        "- [e1.md](episodes/e1.md) - newest\n"
        "\n---\n\n"
        "# Core Knowledge Base\n"
        "## Knowledge Directory\n"
        "### Research Knowledge:\n"
        "- **[Existing](research/existing.md)** - an existing entry\n",
        encoding="utf-8",
    )
    (agent / "episodes" / "e1.md").write_text("# E1\nbody", encoding="utf-8")
    kb = agent / "knowledge-base" / "research"
    kb.mkdir(parents=True)
    (kb / "existing.md").write_text("# Existing\nbody", encoding="utf-8")
    (root / "shared-memory" / "core-reasoning-memory.md").write_text(
        "# REASONING\n### **THOROUGH**\n**UUID**: fc94d140-905e-4f3d-8175-fafd8b84a109\nslow\n",
        encoding="utf-8",
    )
    (root / "shared-memory" / "core-knowledge-memory.md").write_text(
        "# KNOWLEDGE\n### **Line Endings**\nLF\n", encoding="utf-8"
    )
    (root / "shared-memory" / "core-ras-memory.md").write_text(
        "# RAS\n### **TRIGGER**\n**UUID**: 176b0df7-036f-48f9-927d-432e27cd4116\nact\n",
        encoding="utf-8",
    )
    return root


def _import(store: Path, db: Path) -> SqliteMemoryRepository:
    if db.exists():
        db.unlink()
    IdentityRepository(db).ensure_account(Account(user_id="alvi"))
    repo = SqliteMemoryRepository(db, user_id="alvi")
    import_fleet(repo, store)
    return repo


def test_export_materialises_records_markdown_lacks(tmp_path: Path) -> None:
    store = _store(tmp_path / "store")
    db = tmp_path / "store.db"
    repo = _import(store, db)
    repo.insert(
        MemoryRecord(
            uuid="00000000-0000-5000-a000-000000000001",
            user_id="",
            agent_id="meta",
            record_type=RecordType.episode,
            title="db-only-episode",
            full_content="### 2026-10-08 12.00 - DB ONLY\n\nbody here",
            created_date="2026-10-08",
            project="agent-memory",
            tags=["x"],
        )
    )
    repo.insert(
        MemoryRecord(
            uuid="00000000-0000-5000-a000-000000000002",
            user_id="",
            agent_id="meta",
            record_type=RecordType.knowledge,
            title="Db Only Knowledge",
            full_content="# Db Only Knowledge\nbody",
            created_date="2026-10-08",
        )
    )

    db_only, _markdown_only, _changed = compare(db, store)
    assert {r["title"] for r in db_only.values()} == {"db-only-episode", "Db Only Knowledge"}

    written = export_db_only(db, store, knowledge_anchor="- **[Existing](research/existing.md)**")
    assert len(written) == 2
    assert (store / "agent-meta" / "episodes" / "db-only-episode.md").is_file()
    assert (store / "agent-meta" / "knowledge-base" / "db-only-knowledge.md").is_file()

    # reimport: the record round-trips, hot, with its project
    repo2 = _import(store, tmp_path / "after.db")
    episodes = [
        e
        for e in repo2.query(agent_id="meta", record_type=RecordType.episode)
        if e.title == "db-only-episode"
    ]
    assert len(episodes) == 1
    assert episodes[0].project == "agent-memory"
    assert episodes[0].archived_date is None  # indexed -> active
    assert "body here" in episodes[0].full_content
    knowledge = [
        k
        for k in repo2.query(agent_id="meta", record_type=RecordType.knowledge)
        if k.title == "Db Only Knowledge"
    ]
    assert len(knowledge) == 1
