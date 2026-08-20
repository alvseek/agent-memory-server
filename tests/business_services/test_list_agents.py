"""Fleet roster — the service's assembly over the agent entity.

This file used to test enumeration *and* identity parsing, because the roster was
assembled by running regexes over identity bodies pulled through the service. Both
halves have moved to where they belong: enumeration is a column read covered in
`tests/data_repositories/test_agents.py`, and the `**Name**` / `**Role**` extraction
now lives beside the parser in `tests/data_migrations/test_markdown_parser.py`, which
runs it once at import instead of once per request.

What is left here is the service's own job — the projection. The roster must stay three
short fields per agent, because the reason it exists at all is that whole identity
records run past the MCP output cap and truncate silently.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

IDENTITY = """# DOMAIN AGENT IDENTITY

## Agent Identity
**Name**: Claude Meta
**Role**: Meta Agent for Alvi
**Folder**: `claude-meta/`
"""


def _svc(tmp_path: Path) -> tuple[SqliteMemoryRepository, MemoryService]:
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    return repo, MemoryService(repo, user_id="alvi")


def test_roster_carries_name_and_role_from_columns(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.upsert_agent(
        Agent(user_id="", agent_id="meta", name="Claude Meta", role="Meta Agent for Alvi")
    )
    assert svc.list_agents() == [
        {"agent_id": "meta", "name": "Claude Meta", "role": "Meta Agent for Alvi"}
    ]


def test_roster_omits_bodies(tmp_path: Path) -> None:
    """The whole reason this is a dedicated primitive — `query` would ship the body."""
    repo, svc = _svc(tmp_path)
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Claude Meta", role="Meta"))
    repo.insert(
        MemoryRecord(
            uuid="i", user_id="", agent_id="meta",
            record_type=RecordType.identity, full_content=IDENTITY,
            title="Domain Agent Identity",
        )
    )
    (row,) = svc.list_agents()
    assert set(row) == {"agent_id", "name", "role"}
    assert "Folder" not in str(row)


def test_agent_without_identity_is_kept(tmp_path: Path) -> None:
    """Never drop an agent silently — absent identity is a finding, not an absence.
    It reaches the roster as NULL columns now rather than as an unparseable body."""
    repo, svc = _svc(tmp_path)
    repo.upsert_agent(Agent(user_id="", agent_id="linux"))
    assert svc.list_agents() == [{"agent_id": "linux", "name": None, "role": None}]


def test_roster_is_sorted_and_tenancy_scoped(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    other = SqliteMemoryRepository(db, user_id="someone-else")
    other.upsert_agent(Agent(user_id="", agent_id="hidden", name="Not Mine"))
    repo, svc = _svc(tmp_path)
    repo.upsert_agent(Agent(user_id="", agent_id="meta"))
    repo.upsert_agent(Agent(user_id="", agent_id="aquazone"))
    assert [r["agent_id"] for r in svc.list_agents()] == ["aquazone", "meta"]
