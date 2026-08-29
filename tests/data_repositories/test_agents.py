"""The agent entity — `create_agent`, `upsert_agent` and `list_agents`, against the real
repository.

Deliberately does **not** use the `AutoAgentRepository` double from conftest: these tests
are about who creates agent rows and what the roster contains, so a repository that
creates them as a side effect would prove nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account


def _repo(tmp_path: Path, user_id: str = "alvi", name: str = "m.db") -> SqliteMemoryRepository:
    seed_account(tmp_path / name, user_id)
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
    seed_account(db, "someone-else")
    seed_account(db, "alvi")
    SqliteMemoryRepository(db, user_id="someone-else").upsert_agent(_agent("hidden"))
    mine = SqliteMemoryRepository(db, user_id="alvi")
    mine.upsert_agent(_agent("meta"))
    assert [a.agent_id for a in mine.list_agents()] == ["meta"]


def test_same_domain_under_two_tenants_is_two_agents(tmp_path: Path) -> None:
    """The composite key is what makes this safe rather than a collision."""
    db = tmp_path / "m.db"
    seed_account(db, "someone-else")
    seed_account(db, "alvi")
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


def test_soft_deleting_all_of_an_agents_memory_leaves_the_agent(tmp_path: Path) -> None:
    """A deliberate reversal, recorded here so it cannot be mistaken for a regression.

    Under the old `SELECT DISTINCT` enumeration, tombstoning an agent's last record made
    the agent itself vanish from the roster — existence was inferred from memory, so
    deleting the memory deleted the agent. It now has a row, and nothing in the system
    retires an agent (decision 8), so an agent whose memory is entirely tombstoned is
    still an agent. Erasing an entity was never what `soft_delete` was asked to do."""
    repo = _repo(tmp_path)
    repo.upsert_agent(_agent("ghost", name="Claude Ghost"))
    repo.insert(
        MemoryRecord(
            uuid="e1", user_id="", agent_id="ghost",
            record_type=RecordType.episode, full_content="x",
        )
    )
    repo.soft_delete("e1")
    assert list(repo.query(agent_id="ghost")) == []  # the memory is gone
    assert [a.agent_id for a in repo.list_agents()] == ["ghost"]  # the agent is not


# --- create_agent: the strict twin, and the only one fit for a served surface ---


def test_create_agent_returns_the_stored_entity(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    made = repo.create_agent(_agent("newborn", name="Claude Newborn", role="Test Agent"))
    assert made.agent_id == "newborn"
    assert made.user_id == "alvi"  # server-stamped
    assert made.created_date
    assert [a.agent_id for a in repo.list_agents()] == ["newborn"]


def test_create_agent_refuses_an_existing_domain(tmp_path: Path) -> None:
    """Creation is honestly non-idempotent. Upsert refreshes name and role by design,
    which is right for a re-import replaying the source and wrong for a caller — it would
    let one agent silently rewrite another's identity with nothing raised to notice."""
    repo = _repo(tmp_path)
    repo.create_agent(_agent("meta", name="Claude Meta"))
    with pytest.raises(ValueError, match="agent already exists: meta"):
        repo.create_agent(_agent("meta", name="Impostor"))
    (only,) = repo.list_agents()
    assert only.name == "Claude Meta"  # untouched


def test_create_agent_rejects_an_illegal_domain(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid agent domain"):
        _repo(tmp_path).create_agent(_agent("Not A Domain"))


def test_create_agent_is_tenancy_scoped(tmp_path: Path) -> None:
    """The same domain under two tenants is two agents, so neither blocks the other."""
    db = tmp_path / "m.db"
    seed_account(db, "alvi")
    seed_account(db, "someone-else")
    SqliteMemoryRepository(db, user_id="alvi").create_agent(_agent("meta"))
    other = SqliteMemoryRepository(db, user_id="someone-else")
    other.create_agent(_agent("meta"))  # must not raise
    assert [a.agent_id for a in other.list_agents()] == ["meta"]


def test_create_then_insert_is_the_working_order(tmp_path: Path) -> None:
    """The whole reason this tool exists: memory names an owner the store checks, so
    creation has to come first. Before `create_agent` there was no way to do this at all
    through a face, which quietly broke `/create-agent` on the DB backend."""
    repo = _repo(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(
            MemoryRecord(
                uuid="i1", user_id="", agent_id="newborn",
                record_type=RecordType.identity, full_content="x",
            )
        )
    repo.create_agent(_agent("newborn", name="Claude Newborn"))
    saved = repo.insert(
        MemoryRecord(
            uuid="i1", user_id="", agent_id="newborn",
            record_type=RecordType.identity, full_content="x",
        )
    )
    assert saved.agent_id == "newborn"


def test_create_agent_does_not_mislabel_other_integrity_failures(tmp_path: Path) -> None:
    """The duplicate message is narrowed to the primary key on purpose. Today that is
    the only constraint reachable on this INSERT, so a blanket catch would be right by
    luck — and would start calling some future column's violation a duplicate."""
    repo = _repo(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed"):
        with repo._conn() as conn:  # noqa: SLF001 — reaching past the API is the point
            conn.execute(
                "INSERT INTO agent (user_id, agent_id, created_date) VALUES (?,?,NULL)",
                ("alvi", "nulldate"),
            )
