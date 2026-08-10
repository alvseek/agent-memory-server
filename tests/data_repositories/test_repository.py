"""SqliteMemoryRepository read-slice tests (SP-1 Step 1.2).

Uses a temp file DB (connection-per-op means :memory: would not persist)."""

from __future__ import annotations

from pathlib import Path

from munnin.data_entities.memory_record import SHARED_AGENT_ID, MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _repo(tmp_path: Path, user_id: str = "alvi") -> SqliteMemoryRepository:
    return SqliteMemoryRepository(tmp_path / "mem.db", user_id=user_id)


def _rec(uuid: str, **kw: object) -> MemoryRecord:
    base = dict(
        uuid=uuid,
        user_id="ignored",  # repo stamps its own
        agent_id="meta",
        record_type=RecordType.identity,
        full_content="body",
        created_date="2026-01-01",
    )
    base.update(kw)
    return MemoryRecord(**base)  # type: ignore[arg-type]


def test_insert_then_get_roundtrip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saved = repo.insert(_rec("u1", title="T", tags=["a", "b"]))
    assert saved.id is not None
    got = repo.get("u1")
    assert got is not None
    assert got.uuid == "u1"
    assert got.user_id == "alvi"  # server-stamped, not the "ignored" input
    assert got.tags == ["a", "b"]
    assert got.full_content == "body"


def test_insert_is_idempotent_upsert_on_uuid(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", title="first"))
    repo.insert(_rec("u1", title="second"))  # same uuid → update, no dup
    rows = repo.query()
    assert len(rows) == 1
    assert rows[0].title == "second"
    assert rows[0].created_date == "2026-01-01"  # preserved across upsert


def test_query_filters_agent_and_type_and_shared(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", agent_id="meta", record_type=RecordType.identity))
    repo.insert(_rec("u2", agent_id="meta", record_type=RecordType.emotional))
    repo.insert(_rec("u3", agent_id=SHARED_AGENT_ID, record_type=RecordType.reasoning))
    assert {r.uuid for r in repo.query(agent_id="meta")} == {"u1", "u2"}
    assert {r.uuid for r in repo.query(agent_id="meta", record_type=RecordType.identity)} == {"u1"}
    assert {r.uuid for r in repo.query(agent_id=SHARED_AGENT_ID)} == {"u3"}


def test_archived_and_deleted_excluded_by_default(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("active"))
    repo.insert(_rec("arch", archived_date="2026-02-01"))
    repo.insert(_rec("del", deleted_date="2026-02-01"))
    ids = {r.uuid for r in repo.query()}
    assert ids == {"active"}
    # archived visible when asked; deleted never
    ids_arch = {r.uuid for r in repo.query(include_archived=True)}
    assert ids_arch == {"active", "arch"}
    assert repo.get("del") is None


def test_tenancy_isolation(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    a = SqliteMemoryRepository(db, user_id="alvi")
    b = SqliteMemoryRepository(db, user_id="other")
    a.insert(_rec("u1"))
    assert {r.uuid for r in a.query()} == {"u1"}
    assert list(b.query()) == []  # other tenant cannot see alvi's row
    assert b.get("u1") is None
