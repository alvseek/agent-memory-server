"""Importer tests — hermetic fake tree + real-source smoke.

SP-4: full-fleet, `import_shared` extracted, active/archived split (archived = a file
absent from the index), real knowledge bodies, project-knowledge skip.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import RecordType
from munnin.data_migrations.importer import (
    ImportAborted,
    import_agent,
    import_fleet,
    import_shared,
    main,
)
from munnin.data_repositories.identity_repository import IdentityRepository
from tests.conftest import AutoAgentRepository


def _fake_source(root: Path) -> Path:
    agent = root / "agent-meta"
    (agent / "episodes").mkdir(parents=True)
    (root / "shared-memory").mkdir(parents=True)
    (agent / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nI am meta.\n**Name**: Claude Meta\n**Role**: Meta Agent\n"
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
        "# DOMAIN AGENT IDENTITY\nI am foo.\n**Name**: Agent Foo\n", encoding="utf-8"
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
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    shared = import_shared(repo, src)
    counts = import_agent(repo, src, "meta")

    assert counts["meta/identity"] == 3
    assert "meta/reasoning" not in counts  # empty domain reasoning
    assert counts["meta/emotional"] == 2
    assert shared["shared/reasoning"] == 1
    assert shared["shared/knowledge"] == 1
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
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    active_kn = repo.query(agent_id="meta", record_type=RecordType.knowledge)
    pain = next(k for k in active_kn if k.title == "Pain")
    assert "real pain body" in pain.full_content  # real file, not the index description


def test_archived_episode_split(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
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
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_agent(repo, src, "meta")
    allkn = repo.query(agent_id="meta", record_type=RecordType.knowledge, include_archived=True)
    assert not any("project knowledge" in (k.full_content or "") for k in allkn)
    # the archived (unindexed, non-project) orphan IS imported
    assert any(k.title == "Orphan" for k in allkn)


def test_import_fleet_imports_all_agents_shared_once(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    totals = import_fleet(repo, src)
    assert totals["meta/identity"] == 3
    assert totals["foo/identity"] == 1
    # shared imported exactly once (2 rows total), not once-per-agent
    shared_rows = repo.query_shared(include_archived=True)
    assert len(shared_rows) == 2


def test_import_is_idempotent(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
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
        "# DOMAIN AGENT IDENTITY\nI am arch.\n**Name**: Claude Arch\n", encoding="utf-8"
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

    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
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
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    shared = import_shared(repo, _REAL)
    counts = import_agent(repo, _REAL, "meta")
    assert counts["meta/identity"] == 3
    assert counts["meta/emotional"] >= 10
    assert shared["shared/reasoning"] >= 10
    assert counts["meta/episode"] >= 100  # active + archived
    active = repo.query(agent_id="meta", record_type=RecordType.episode)
    allep = repo.query(agent_id="meta", record_type=RecordType.episode, include_archived=True)
    assert len(active) < len(allep)  # archived split holds
    assert len(allep) == counts["meta/episode"]


# --- pass 1: the agent table, and the abort that protects it ---


def test_import_fleet_creates_agent_rows_with_their_fields(tmp_path: Path) -> None:
    """Pass 1's product. Name, role and the agent's own uuid are read once, here, and
    stored as columns — which is what turns the roster into a plain SELECT."""
    src = _fake_source(tmp_path / "src")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_fleet(repo, src)
    roster = {a.agent_id: a for a in repo.list_agents()}
    assert sorted(roster) == ["foo", "meta"]
    assert roster["meta"].name == "Claude Meta"
    assert roster["meta"].role == "Meta Agent"
    assert roster["foo"].role is None  # a real agent that simply states no role


def test_pass_one_aborts_before_writing_anything(tmp_path: Path) -> None:
    """The success criterion for the two-pass split: a bad folder leaves the database
    **empty**, not partially filled. Skipping the folder and carrying on is what let
    five agents import as hollow shells for months while every run reported success."""
    src = _fake_source(tmp_path / "src")
    broken = src / "agent-broken"
    broken.mkdir()
    (broken / "agent-core-memory.md").write_text(
        "# DOMAIN AGENT IDENTITY\nno name line here\n", encoding="utf-8"
    )
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")

    with pytest.raises(ImportAborted, match="broken: identity has no"):
        import_fleet(repo, src)

    assert list(repo.list_agents()) == []
    assert list(repo.query(include_archived=True)) == []
    assert list(repo.query_shared(include_archived=True)) == []


def test_pass_one_reports_every_bad_folder_not_just_the_first(tmp_path: Path) -> None:
    """One run, one list. Surfacing them one at a time would mean one full re-run per
    broken agent, and the check costs a single pass over a few dozen small files."""
    src = _fake_source(tmp_path / "src")
    for name in ("agent-alpha", "agent-omega"):
        d = src / name
        d.mkdir()
        (d / "agent-core-memory.md").write_text("# DOMAIN AGENT IDENTITY\nx\n", encoding="utf-8")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")

    with pytest.raises(ImportAborted) as exc:
        import_fleet(repo, src)
    assert "alpha:" in str(exc.value)
    assert "omega:" in str(exc.value)
    assert "2 agent folder(s)" in str(exc.value)


def test_a_missing_core_file_is_also_an_abort(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    (src / "agent-empty").mkdir()
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    with pytest.raises(ImportAborted, match="empty: no agent-core-memory.md"):
        import_fleet(repo, src)
    assert list(repo.list_agents()) == []


_PROFILE_FILE = (
    "## AI Agent - User Profile\n"
    "\n"
    "- **[USER-NAME]** = Alvi\n"
    "- **[USER-PHILOSOPHY]** = ship something that works\n"
    "- **[USER-AGENT-VISION]** = a fleet that remembers\n"
)


def test_shared_import_creates_exactly_one_profile_row(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    (src / "shared-memory" / "user-profile.md").write_text(_PROFILE_FILE, encoding="utf-8")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")

    shared = import_shared(repo, src)

    assert shared["shared/user_profile"] == 1
    rows = repo.query_shared(record_type=RecordType.user_profile)
    assert len(rows) == 1
    assert "[USER-NAME]" in rows[0].full_content


def test_a_missing_profile_file_imports_quietly(tmp_path: Path) -> None:
    """The fleet fixture ships no profile. Reasoning and knowledge are invariants whose
    absence is a broken store; a profile is a fact about someone who may not have been
    asked yet, so its absence must not raise."""
    src = _fake_source(tmp_path / "src")
    assert not (src / "shared-memory" / "user-profile.md").exists()
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")

    shared = import_shared(repo, src)

    assert "shared/user_profile" not in shared
    assert shared["shared/reasoning"] == 1  # the rest of the layer still landed
    assert repo.query_shared(record_type=RecordType.user_profile) == []


def test_a_profile_file_without_the_marker_imports_nothing(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    (src / "shared-memory" / "user-profile.md").write_text("# not a profile\n", encoding="utf-8")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")

    shared = import_shared(repo, src)

    assert "shared/user_profile" not in shared
    assert repo.query_shared(record_type=RecordType.user_profile) == []


def test_reimporting_the_profile_updates_rather_than_duplicates(tmp_path: Path) -> None:
    src = _fake_source(tmp_path / "src")
    path = src / "shared-memory" / "user-profile.md"
    path.write_text(_PROFILE_FILE, encoding="utf-8")
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    import_shared(repo, src)
    first = repo.query_shared(record_type=RecordType.user_profile)[0]

    path.write_text(_PROFILE_FILE.replace("Alvi", "Alvi Widiasto"), encoding="utf-8")
    import_shared(repo, src)
    rows = repo.query_shared(record_type=RecordType.user_profile)

    assert len(rows) == 1, "an edited profile must update the row, not add a second"
    assert rows[0].uuid == first.uuid
    assert "Alvi Widiasto" in rows[0].full_content


# --- the entrypoint builds the ownership chain downwards (account, then agents) ---


def test_main_creates_the_tenant_before_importing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main` uses the real repository, not the auto-creating double, so an import into
    a fresh database is the honest test of the new constraint: without the account row
    the very first agent write would fail on the foreign key."""
    src = _fake_source(tmp_path / "src")
    db = tmp_path / "m.db"
    monkeypatch.setattr(
        sys, "argv", ["importer", "--source", str(src), "--db", str(db), "--all"]
    )
    main()

    identities = IdentityRepository(db)
    account = identities.get_account("alvi")
    assert account is not None
    assert account.created_date  # stamped, not left null


def test_running_the_import_twice_leaves_one_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-importing is the normal way this store is refreshed, so it must not accumulate
    a tenant per run."""
    src = _fake_source(tmp_path / "src")
    db = tmp_path / "m.db"
    monkeypatch.setattr(
        sys, "argv", ["importer", "--source", str(src), "--db", str(db), "--all"]
    )
    main()
    main()

    repo = IdentityRepository(db)
    with repo._conn() as conn:  # noqa: SLF001 — counting rows, not exercising a path
        assert conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 1
