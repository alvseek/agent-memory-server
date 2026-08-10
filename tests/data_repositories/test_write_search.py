"""SqliteMemoryRepository write + search tests (SP-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _repo(tmp_path: Path, user_id: str = "alvi") -> SqliteMemoryRepository:
    return SqliteMemoryRepository(tmp_path / "mem.db", user_id=user_id)


def _rec(uuid: str, content: str, **kw: object) -> MemoryRecord:
    base = dict(
        uuid=uuid,
        user_id="",
        agent_id="meta",
        record_type=RecordType.episode,
        full_content=content,
        title=uuid,
        created_date="2026-01-01",
    )
    base.update(kw)
    return MemoryRecord(**base)  # type: ignore[arg-type]


# --- edit ---

def test_edit_unique_replace(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello world"))
    out = repo.edit("u1", "world", "there")
    assert out.full_content == "hello there"
    assert out.modified_date != out.created_date  # bumped


def test_edit_replace_all(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "a a a"))
    out = repo.edit("u1", "a", "b", replace_all=True)
    assert out.full_content == "b b b"


def test_edit_not_found_string_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello"))
    with pytest.raises(ValueError, match="not found"):
        repo.edit("u1", "zzz", "x")


def test_edit_ambiguous_without_replace_all_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "a a"))
    with pytest.raises(ValueError, match="ambiguous"):
        repo.edit("u1", "a", "b")


def test_edit_missing_record_raises_lookup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(LookupError):
        repo.edit("nope", "a", "b")


def test_edit_deleted_record_raises_lookup(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello"))
    repo.soft_delete("u1")
    with pytest.raises(LookupError):
        repo.edit("u1", "hello", "bye")


def test_edit_archived_record_ok(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello"))
    repo.archive("u1")
    out = repo.edit("u1", "hello", "bye")  # archived is still editable
    assert out.full_content == "bye"


# --- archive / soft_delete ---

def test_archive_hides_from_hot_query_but_keeps_in_include_archived(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "body"))
    repo.archive("u1")
    assert repo.query() == []
    assert {r.uuid for r in repo.query(include_archived=True)} == {"u1"}


def test_soft_delete_hides_everywhere(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "body"))
    repo.soft_delete("u1")
    assert repo.query() == []
    assert repo.query(include_archived=True) == []
    assert repo.get("u1") is None


def test_archive_is_idempotent_first_timestamp_kept(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "body"))
    repo.archive("u1")
    first = repo.query(include_archived=True)[0].archived_date
    repo.archive("u1")  # again
    again = repo.query(include_archived=True)[0].archived_date
    assert first == again


def test_lifecycle_missing_record_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(LookupError):
        repo.archive("nope")
    with pytest.raises(LookupError):
        repo.soft_delete("nope")


# --- search ---

def _seed_search(repo: SqliteMemoryRepository) -> None:
    repo.insert(_rec("m1", "the memory system remembers", title="memory"))
    repo.insert(_rec("m2", "unrelated content about weather", title="weather"))
    repo.insert(_rec("arch1", "archived memory note", archived_date="2026-02-01"))
    repo.insert(_rec("del1", "deleted memory note", deleted_date="2026-02-01"))


def test_search_matches_and_excludes_deleted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_search(repo)
    # matches m1 + archived (searchable), NOT m2 (no term), NOT del1 (tombstone)
    assert {r.uuid for r in repo.search("memory")} == {"m1", "arch1"}


def test_search_excludes_archived_when_flag_false(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_search(repo)
    assert {r.uuid for r in repo.search("memory", include_archived=False)} == {"m1"}


def test_search_ranks_more_relevant_first(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("hi", "fork fork fork"))
    repo.insert(_rec("lo", "a b c d e f g h fork i j k"))
    res = repo.search("fork")
    assert res[0].uuid == "hi"  # higher term frequency, shorter doc


def test_search_special_chars_do_not_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello"))
    # arbitrary punctuation / operators must not raise
    for q in ("C++", 'a "quote', "store≠repo", "AND OR NEAR"):
        assert repo.search(q) == []


def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _seed_search(repo)
    assert repo.search("") == []
    assert repo.search("   ") == []


def test_search_is_tenant_scoped(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    a = SqliteMemoryRepository(db, user_id="alvi")
    b = SqliteMemoryRepository(db, user_id="other")
    a.insert(_rec("u1", "secret memory"))
    assert {r.uuid for r in a.search("memory")} == {"u1"}
    assert b.search("memory") == []


def test_search_reflects_edits(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert(_rec("u1", "hello world"))
    assert {r.uuid for r in repo.search("hello")} == {"u1"}
    repo.edit("u1", "hello", "goodbye")
    assert repo.search("hello") == []  # FTS re-synced via trigger
    assert {r.uuid for r in repo.search("goodbye")} == {"u1"}
