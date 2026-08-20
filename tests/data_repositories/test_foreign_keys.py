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

from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _repo(tmp_path: Path, user_id: str = "alvi") -> SqliteMemoryRepository:
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
    """The test that matters. Without the pragma this insert quietly succeeds."""
    repo = _repo(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repo.insert(_rec("m2", "ghost"))


def test_insert_across_tenants_is_rejected(tmp_path: Path) -> None:
    """`meta` exists for `alvi`; another tenant's repository still cannot write to it."""
    db = tmp_path / "m.db"
    mine = SqliteMemoryRepository(db, user_id="alvi")
    _seed_agent(mine, "meta")
    theirs = SqliteMemoryRepository(db, user_id="someone-else")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        theirs.insert(_rec("m3", "meta"))


def test_nothing_is_written_when_the_insert_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert(_rec("m4", "ghost"))
    assert repo.get("m4") is None
