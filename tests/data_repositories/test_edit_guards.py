"""Guard real repository transactions, not only a mocked service comparison."""

import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import psycopg
import pytest

from munnin.data_entities.edit_context import RevisionConflict, record_revision
from munnin.data_entities.memory_record import MemoryRecord, RecordType, SharedRecord


def insert(repo, shared=False, content="alpha"):
    common = dict(uuid=uuid.uuid4().hex, user_id="", record_type=RecordType.reasoning,
                  full_content=content, title="Original", content_summary="Summary")
    if shared:
        return repo.insert_shared(SharedRecord(**common))
    return repo.insert(MemoryRecord(**common, agent_id="meta"))


@pytest.mark.parametrize("shared", [False, True])
def test_guarded_body_and_metadata_writes_are_independent(memory_repo, shared):
    repo = memory_repo
    before = insert(repo, shared)
    token = record_revision(before)
    edited = repo.edit(before.uuid, "alpha", "beta", expected_revision=token)
    assert edited.full_content == "beta"
    assert edited.title == before.title and edited.content_summary == before.content_summary
    with pytest.raises(RevisionConflict):
        repo.set_fields(before.uuid, title="Lost edit", expected_revision=token)
    current = repo.get(before.uuid)
    assert current.title == before.title and current.full_content == "beta"
    updated = repo.set_fields(
        before.uuid, title="Changed", expected_revision=record_revision(current)
    )
    assert updated.title == "Changed" and updated.full_content == "beta"
    with pytest.raises(RevisionConflict):
        repo.edit(before.uuid, "beta", "lost", expected_revision=record_revision(edited))
    assert repo.get(before.uuid).full_content == "beta"


@pytest.mark.parametrize("shared", [False, True])
def test_lifecycle_and_empty_body_guards(memory_repo, shared):
    repo = memory_repo
    before = insert(repo, shared, "")
    token = record_revision(before)
    changed = repo.edit(before.uuid, "", "終\n", expected_revision=token)
    emptied = repo.edit(
        before.uuid, "終\n", "", expected_revision=record_revision(changed)
    )
    assert emptied.full_content == ""
    repo.archive(before.uuid)
    with pytest.raises(RevisionConflict):
        repo.set_fields(before.uuid, tags=["stale"], expected_revision=record_revision(emptied))
    assert repo.get(before.uuid).tags == []
    # An arbitrary non-ASCII token is a conflict, never an unhandled encoding error.
    with pytest.raises(RevisionConflict):
        repo.edit(before.uuid, "", "lost", expected_revision="é")


def test_revision_counts_every_entity_field_without_timestamp_resolution():
    record = SharedRecord(uuid="record", user_id="tenant", record_type=RecordType.reasoning,
                          full_content="alpha", modified_date="same-second")
    original = record_revision(record)
    variants = [
        replace(record, full_content="beta"),
        replace(record, title="changed"),
        replace(record, tags=["changed"]),
        replace(record, content_summary="changed"),
        replace(record, project="changed"),
        replace(record, archived_date="changed"),
        replace(record, deleted_date="changed"),
        replace(record, user_id="different"),
        MemoryRecord(**record.__dict__, agent_id="meta"),
    ]
    assert all(record_revision(other) != original for other in variants)
    assert record_revision(record) == original


def assert_write_lock_held(repo, record):
    if hasattr(repo, "_db_path"):
        connection = sqlite3.connect(repo._db_path, timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                connection.execute("BEGIN IMMEDIATE")
        finally:
            connection.close()
    else:
        table = "memory_record" if isinstance(record, MemoryRecord) else "shared_record"
        with psycopg.connect(repo._dsn) as connection:
            with pytest.raises(psycopg.errors.LockNotAvailable):
                connection.execute(
                    f"SELECT uuid FROM {table} WHERE uuid=%s FOR UPDATE NOWAIT",
                    (record.uuid,),
                )


@pytest.mark.parametrize("shared", [False, True])
def test_body_is_read_and_transformed_only_under_the_real_write_lock(memory_repo, shared):
    repo = memory_repo
    record = insert(repo, shared)
    seen = []

    def transform(body):
        assert_write_lock_held(repo, record)
        seen.append(body)
        return body + "-under-lock"

    result = repo._rewrite(record.uuid, transform, expected_revision=record_revision(record))
    assert seen == ["alpha"]
    assert result.full_content == "alpha-under-lock"


def test_failed_guard_never_runs_a_body_transform(memory_repo):
    repo = memory_repo
    record = insert(repo)
    repo.append(record.uuid, " changed")
    transformed = []
    with pytest.raises(RevisionConflict):
        repo._rewrite(record.uuid, lambda body: transformed.append(body) or "lost",
                      expected_revision=record_revision(record))
    assert transformed == []
    assert repo.get(record.uuid).full_content == "alpha changed"


@pytest.mark.parametrize("shared", [False, True])
def test_two_writers_with_one_baseline_cannot_both_commit(memory_repo, shared):
    repo = memory_repo
    record = insert(repo, shared)
    token = record_revision(record)
    ready = Barrier(3)

    def save(body):
        ready.wait(timeout=10)
        try:
            return repo.edit(record.uuid, "alpha", body, expected_revision=token).full_content
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(save, "first")
        second = workers.submit(save, "second")
        ready.wait(timeout=10)
        outcomes = [first.result(timeout=10), second.result(timeout=10)]
    assert outcomes.count(None) == 1
    winner = next(value for value in outcomes if value is not None)
    assert repo.get(record.uuid).full_content == winner
