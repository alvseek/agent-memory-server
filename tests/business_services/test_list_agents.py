"""Fleet roster — repository enumeration + service assembly.

Enumeration is the one read that is not agent-scoped, so it needs its own coverage:
the tenancy filter, the `__shared__` exclusion, and the lifecycle rule (archived
counts, soft-deleted does not) all live in a single DISTINCT query with no other
caller to catch a regression.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import SHARED_AGENT_ID, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import AutoAgentRepository

IDENTITY = """# DOMAIN AGENT IDENTITY

## Agent Identity
**Name**: Claude Meta
**Role**: Meta Agent for Alvi
**Folder**: `claude-meta/`
"""


def _svc(tmp_path: Path) -> tuple[SqliteMemoryRepository, MemoryService]:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def _mk(uuid: str, agent: str, rtype: RecordType, content: str, **kw: object) -> MemoryRecord:
    return MemoryRecord(
        uuid=uuid, user_id="", agent_id=agent, record_type=rtype, full_content=content, **kw
    )


# --- repository: list_agent_domains ---


def test_domains_are_distinct_and_sorted(tmp_path: Path) -> None:
    repo, _svc_ = _svc(tmp_path)
    repo.insert(_mk("a", "meta", RecordType.episode, "x"))
    repo.insert(_mk("b", "meta", RecordType.knowledge, "x"))
    repo.insert(_mk("c", "aquazone", RecordType.episode, "x"))
    assert list(repo.list_agent_domains()) == ["aquazone", "meta"]


def test_shared_sentinel_excluded(tmp_path: Path) -> None:
    repo, _svc_ = _svc(tmp_path)
    repo.insert(_mk("s", SHARED_AGENT_ID, RecordType.reasoning, "fleet-wide"))
    repo.insert(_mk("m", "meta", RecordType.episode, "x"))
    assert list(repo.list_agent_domains()) == ["meta"]


def test_archived_agent_still_listed(tmp_path: Path) -> None:
    """Archive is cold, not gone — an agent whose every record is archived exists."""
    repo, _svc_ = _svc(tmp_path)
    repo.insert(_mk("a", "linux", RecordType.episode, "x"))
    repo.archive("a")
    assert list(repo.list_agent_domains()) == ["linux"]


def test_soft_deleted_agent_not_listed(tmp_path: Path) -> None:
    repo, _svc_ = _svc(tmp_path)
    repo.insert(_mk("a", "ghost", RecordType.episode, "x"))
    repo.soft_delete("a")
    assert list(repo.list_agent_domains()) == []


def test_other_tenant_not_listed(tmp_path: Path) -> None:
    """The security-critical rule: enumeration is tenancy-scoped like every read."""
    db = tmp_path / "m.db"
    AutoAgentRepository(db, user_id="someone-else").insert(
        _mk("x", "hidden", RecordType.episode, "x")
    )
    mine = AutoAgentRepository(db, user_id="alvi")
    mine.insert(_mk("y", "meta", RecordType.episode, "x"))
    assert list(mine.list_agent_domains()) == ["meta"]


# --- service: list_agents ---


def test_roster_carries_name_and_role(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("i", "meta", RecordType.identity, IDENTITY, title="Domain Agent Identity"))
    assert svc.list_agents() == [
        {"agent_id": "meta", "name": "Claude Meta", "role": "Meta Agent for Alvi"}
    ]


def test_roster_omits_bodies(tmp_path: Path) -> None:
    """The whole reason this is a dedicated primitive — `query` would ship the body."""
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("i", "meta", RecordType.identity, IDENTITY, title="Domain Agent Identity"))
    (row,) = svc.list_agents()
    assert set(row) == {"agent_id", "name", "role"}
    assert "Folder" not in str(row)


def test_agent_without_identity_is_kept(tmp_path: Path) -> None:
    """Never drop an agent silently — absent identity is a finding, not an absence."""
    repo, svc = _svc(tmp_path)
    repo.insert(_mk("e", "linux", RecordType.episode, "just an episode"))
    assert svc.list_agents() == [{"agent_id": "linux", "name": None, "role": None}]


def test_db_born_identity_title_still_parses(tmp_path: Path) -> None:
    """create-agent titles its record "Agent Identity"; the importer titles it "Domain
    Agent Identity". Matching by line rather than title is what keeps both visible."""
    repo, svc = _svc(tmp_path)
    repo.insert(
        _mk("i", "newborn", RecordType.identity, IDENTITY, title="Agent Identity")
    )
    (row,) = svc.list_agents()
    assert row["name"] == "Claude Meta"


def test_main_purpose_is_the_role_fallback(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    body = "# DOMAIN AGENT IDENTITY\n**Name**: Claude Old\n**Main Purpose**: Legacy duty\n"
    repo.insert(_mk("i", "old", RecordType.identity, body, title="Domain Agent Identity"))
    (row,) = svc.list_agents()
    assert row["role"] == "Legacy duty"


def test_role_wins_over_main_purpose_regardless_of_order(tmp_path: Path) -> None:
    """Precedence must come from the rule, not from which line the file happens to put
    first — an alternation regex would return whichever appeared earlier."""
    repo, svc = _svc(tmp_path)
    body = (
        "# DOMAIN AGENT IDENTITY\n**Name**: Claude Odd\n"
        "**Main Purpose**: the long purpose paragraph\n**Role**: The Role\n"
    )
    repo.insert(_mk("i", "odd", RecordType.identity, body, title="Domain Agent Identity"))
    (row,) = svc.list_agents()
    assert row["role"] == "The Role"


def test_identity_searched_across_all_records(tmp_path: Path) -> None:
    """An agent has three identity records; Name/Role live in only one of them."""
    repo, svc = _svc(tmp_path)
    ras = "# DOMAIN RAS\ntriggers"
    repo.insert(_mk("i1", "meta", RecordType.identity, ras, title="Domain Ras"))
    repo.insert(_mk("i2", "meta", RecordType.identity, IDENTITY, title="Domain Agent Identity"))
    (row,) = svc.list_agents()
    assert row["role"] == "Meta Agent for Alvi"
