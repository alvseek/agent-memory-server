"""Does the repository actually *enable* the foreign key?

Separate from `tests/data_entities/test_schema.py`, which proves the constraint is
declared. SQLite defaults `foreign_keys` OFF and this repository opens a connection per
operation, so a declared-but-unenabled constraint is the realistic failure: the schema
looks right, every happy-path test passes, and nothing is enforced. Only a rejection
observed *through the repository* distinguishes the two.

Agent rows are seeded with raw SQL rather than `upsert_agent` so these tests bind to the
pragma alone, not to the agent write path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account


def _repo(tmp_path: Path, user_id: str = "alvi") -> SqliteMemoryRepository:
    seed_account(tmp_path / "m.db", user_id)
    return SqliteMemoryRepository(tmp_path / "m.db", user_id=user_id)


def _seed_agent(repo: SqliteMemoryRepository, agent_id: str, user_id: str = "alvi") -> None:
    with repo._conn() as conn:  # noqa: SLF001 — deliberately bypassing the write path
        conn.execute(
            "INSERT OR IGNORE INTO agent (user_id, agent_id, name, role, uuid, created_date)"
            " VALUES (?,?,?,?,?,'2026-08-20')",
            (user_id, agent_id, "Claude Test", "Test Agent", "u1"),
        )


def _rec(uuid: str, agent_id: str) -> MemoryRecord:
    return MemoryRecord(
        uuid=uuid, user_id="", agent_id=agent_id,
        record_type=RecordType.episode, full_content="body",
    )


def test_pragma_is_on_for_every_connection(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with repo._conn() as conn:  # noqa: SLF001
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    # a second, independent connection must also have it — the pragma is per-connection
    with repo._conn() as conn:  # noqa: SLF001
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_insert_for_a_known_agent_succeeds(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_agent(repo, "meta")
    assert repo.insert(_rec("m1", "meta")).uuid == "m1"


def test_insert_for_an_unknown_agent_is_rejected(tmp_path: Path) -> None:
    """The test that matters. Without the pragma this insert quietly succeeds.

    The repository reports it as ``ValueError`` so both faces answer 400 rather than 500,
    but the cause is asserted too: it must be the **database** refusing, not a Python
    pre-check. A pre-check would pass this test with the foreign keys switched off."""
    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="no agent 'ghost' exists") as caught:
        repo.insert(_rec("m2", "ghost"))
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


def test_insert_across_tenants_is_rejected(tmp_path: Path) -> None:
    """`meta` exists for `alvi`; another tenant's repository still cannot write to it."""
    db = tmp_path / "m.db"
    seed_account(db, "alvi")
    seed_account(db, "someone-else")
    mine = SqliteMemoryRepository(db, user_id="alvi")
    _seed_agent(mine, "meta")
    theirs = SqliteMemoryRepository(db, user_id="someone-else")
    with pytest.raises(ValueError, match="no agent 'meta' exists") as caught:
        theirs.insert(_rec("m3", "meta"))
    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


def test_nothing_is_written_when_the_insert_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        repo.insert(_rec("m4", "ghost"))
    assert repo.get("m4") is None


# --- the second link in the chain: an agent must name a tenant that exists ---


def test_agent_for_an_unknown_tenant_is_rejected(tmp_path: Path) -> None:
    """The link that makes a mistyped tenant an error instead of a new tenant.

    Without it, `user_id="alvii"` would silently create a parallel store that no login
    can ever reach — a leak of nothing, but an unbounded write surface all the same."""
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="ghost-tenant")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repo.upsert_agent(
            Agent(user_id="", agent_id="meta", name="Claude Meta", role="Meta Agent")
        )


def test_agent_for_a_known_tenant_succeeds(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.upsert_agent(Agent(user_id="", agent_id="meta")).agent_id == "meta"


def test_identity_for_an_unknown_tenant_is_rejected(tmp_path: Path) -> None:
    """`user_identity` points at `account` for the same reason: a mapping to a tenant
    that does not exist would authenticate somebody into nothing."""
    repo = _repo(tmp_path)
    with repo._conn() as conn:  # noqa: SLF001 — deliberately bypassing the write path
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            conn.execute(
                "INSERT INTO user_identity (iss, sub, user_id, linked_date)"
                " VALUES ('https://x.authkit.app','sub_1','ghost-tenant','2026-08-28')"
            )
