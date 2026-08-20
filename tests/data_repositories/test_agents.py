"""The agent entity — `upsert_agent` and `list_agents` against the real repository.

Deliberately does **not** use the `AutoAgentRepository` double from conftest: these tests
are about who creates agent rows and what the roster contains, so a repository that
creates them as a side effect would prove nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _repo(tmp_path: Path, user_id: str = "alvi", name: str = "m.db") -> SqliteMemoryRepository:
    return SqliteMemoryRepository(tmp_path / name, user_id=user_id)


def _agent(agent_id: str, **kw: object) -> Agent:
    return Agent(user_id="", agent_id=agent_id, **kw)  # type: ignore[arg-type]


def test_upsert_returns_the_stored_agent(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    got = repo.upsert_agent(_agent("meta", name="Claude Meta", role="Meta Agent", uuid="u1"))
    assert (got.agent_id, got.name) == ("meta", "Claude Meta")
    assert (got.role, got.uuid) == ("Meta Agent", "u1")
    assert got.user_id == "alvi"  # stamped server-side, not taken from the caller
    assert got.created_date  # defaulted on write


def test_upsert_is_idempotent_and_refreshes_fields(tmp_path: Path) -> None:
    """A re-import must update name/role without inventing a second agent."""
    repo = _repo(tmp_path)
    first = repo.upsert_agent(_agent("meta", name="Old Name", role="Old Role"))
    second = repo.upsert_agent(_agent("meta", name="New Name", role="New Role"))
    assert len(repo.list_agents()) == 1
    assert (second.name, second.role) == ("New Name", "New Role")
    assert second.created_date == first.created_date  # birth date survives a refresh


def test_roster_is_sorted_by_domain(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for d in ("meta", "aquazone", "linux"):
        repo.upsert_agent(_agent(d))
    assert [a.agent_id for a in repo.list_agents()] == ["aquazone", "linux", "meta"]


def test_roster_returns_columns_not_parsed_text(tmp_path: Path) -> None:
    """The point of the entity: name and role are fields, not lines found in a blob."""
    repo = _repo(tmp_path)
    repo.upsert_agent(_agent("meta", name="Claude Meta", role="Meta Agent for Alvi"))
    (row,) = repo.list_agents()
    assert isinstance(row, Agent)
    assert row.name == "Claude Meta"
    assert row.role == "Meta Agent for Alvi"


def test_an_agent_with_no_memory_is_still_an_agent(tmp_path: Path) -> None:
    """Existence stops being an inference from memory — this is the whole change."""
    repo = _repo(tmp_path)
    repo.upsert_agent(_agent("newborn", name="Claude Newborn"))
    assert [a.agent_id for a in repo.list_agents()] == ["newborn"]


def test_roster_is_tenancy_scoped(tmp_path: Path) -> None:
    """The security-critical rule: another tenant's agents are invisible."""
    db = tmp_path / "m.db"
    SqliteMemoryRepository(db, user_id="someone-else").upsert_agent(_agent("hidden"))
    mine = SqliteMemoryRepository(db, user_id="alvi")
    mine.upsert_agent(_agent("meta"))
    assert [a.agent_id for a in mine.list_agents()] == ["meta"]


def test_same_domain_under_two_tenants_is_two_agents(tmp_path: Path) -> None:
    """The composite key is what makes this safe rather than a collision."""
    db = tmp_path / "m.db"
    theirs = SqliteMemoryRepository(db, user_id="someone-else")
    theirs.upsert_agent(_agent("meta", name="Their Meta"))
    mine = SqliteMemoryRepository(db, user_id="alvi")
    mine.upsert_agent(_agent("meta", name="My Meta"))
    assert [a.name for a in mine.list_agents()] == ["My Meta"]
    assert [a.name for a in theirs.list_agents()] == ["Their Meta"]


def test_upsert_rejects_an_illegal_domain(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid agent domain"):
        _repo(tmp_path).upsert_agent(_agent("Not A Domain"))


def test_archiving_all_of_an_agents_memory_leaves_the_agent(tmp_path: Path) -> None:
    """Archive retires a memory item, never an agent — the entity is unaffected."""
    repo = _repo(tmp_path)
    repo.upsert_agent(_agent("linux", name="Claude Linux"))
    repo.insert(
        MemoryRecord(
            uuid="e1", user_id="", agent_id="linux",
            record_type=RecordType.episode, full_content="x",
        )
    )
    repo.archive("e1")
    assert [a.agent_id for a in repo.list_agents()] == ["linux"]
