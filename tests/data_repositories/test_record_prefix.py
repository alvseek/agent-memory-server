"""One addressing contract exercised against real SQLite and PostgreSQL engines."""

from dataclasses import asdict

import pytest

from munnin.data_entities.identity import Account
from munnin.data_entities.memory_record import MemoryRecord, RecordType, SharedRecord
from munnin.data_entities.record_reference import (
    AmbiguousRecordReference,
    InvalidRecordReference,
    normalize_prefix,
)
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.postgres_identity_repository import PostgresIdentityRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

A = "abcdef01-1234-4321-9876-123456789abc"
B = "abcdef02123443219876123456789abc"


def seed(repo, uuid=A, *, shared=False):
    fields = dict(uuid=uuid, user_id="", record_type=RecordType.knowledge,
                  full_content="original", title=uuid, content_summary="summary")
    if shared:
        return repo.insert_shared(SharedRecord(**fields))
    return repo.insert(MemoryRecord(**fields, agent_id="meta"))


def act(repo, operation, reference):
    return {
        "get": lambda: repo.get(reference),
        "edit": lambda: repo.edit(reference, "original", "changed"),
        "append": lambda: repo.append(reference, " tail"),
        "prepend": lambda: repo.prepend(reference, "head "),
        "multi_edit": lambda: repo.multi_edit(reference, [("original", "changed", False)]),
        "metadata": lambda: repo.set_fields(reference, title="changed"),
        "archive": lambda: repo.archive(reference),
        "unarchive": lambda: repo.unarchive(reference),
        "soft_delete": lambda: repo.soft_delete(reference),
    }[operation]()


OPERATIONS = ["get", "edit", "append", "prepend", "multi_edit", "metadata",
              "archive", "unarchive", "soft_delete"]


@pytest.mark.parametrize("reference", ["ABCDEF", "ab-cd-ef", "ABCDEF011234", A.upper(),
                                       A.replace("-", "")])
def test_normalized_prefix_read(memory_repo, reference):
    seed(memory_repo)
    assert memory_repo.get(reference).uuid == A


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_unique_prefix_for_every_operation(memory_repo, operation, shared):
    seed(memory_repo, shared=shared)
    if operation == "unarchive":
        memory_repo.archive(A)
    result = act(memory_repo, operation, "ABCDEF")
    assert (result if isinstance(result, str) else result.uuid) == A
    if operation == "soft_delete":
        assert memory_repo.get(A) is None
    elif operation == "archive":
        assert memory_repo.get(A).archived_date is not None
    elif operation == "unarchive":
        assert memory_repo.get(A).archived_date is None
    elif operation == "metadata":
        assert memory_repo.get(A).title == "changed"
    elif operation != "get":
        assert memory_repo.get(A).full_content != "original"


@pytest.mark.parametrize("operation", OPERATIONS)
def test_cross_table_ambiguity_never_writes(memory_repo, operation):
    seed(memory_repo)
    seed(memory_repo, B, shared=True)
    before = [asdict(memory_repo.get(uid)) for uid in (A, B)]
    with pytest.raises(AmbiguousRecordReference) as caught:
        act(memory_repo, operation, "ABCDEF")
    assert {r.uuid for r in caught.value.candidates} == {A, B}
    assert all(r.title for r in caught.value.candidates)
    assert [asdict(memory_repo.get(uid)) for uid in (A, B)] == before


def test_zero_matches_and_longer_prefix_disambiguation(memory_repo):
    assert memory_repo.get("fedcba") is None
    seed(memory_repo)
    seed(memory_repo, B)
    assert memory_repo.get("abcdef01").uuid == A
    assert memory_repo.get("abcdef02").uuid == B


def test_exact_legacy_ids_take_precedence(memory_repo):
    seed(memory_repo)
    for uid in ("p1", "abcdef"):
        seed(memory_repo, uid, shared=True)
        assert memory_repo.get(uid).uuid == uid


def test_normalization_collision_is_ambiguous_but_exact_id_wins(memory_repo):
    seed(memory_repo)
    seed(memory_repo, A.replace("-", ""), shared=True)
    assert memory_repo.get(A).uuid == A
    with pytest.raises(AmbiguousRecordReference):
        memory_repo.get(A.upper())


def test_lifecycle_visibility_is_preserved(memory_repo):
    seed(memory_repo)
    seed(memory_repo, B)
    memory_repo.soft_delete(B)
    assert memory_repo.get("abcdef").uuid == A
    with pytest.raises(AmbiguousRecordReference):
        memory_repo.archive("abcdef")
    assert memory_repo.soft_delete("abcdef02") == B
    with pytest.raises(LookupError):
        memory_repo.unarchive("abcdef02")


@pytest.mark.parametrize("reference", ["", "abcde", "%%%%%%", "______", "xyzxyz", "a" * 33])
def test_invalid_prefix_is_refused(memory_repo, reference):
    with pytest.raises(InvalidRecordReference):
        memory_repo.get(reference)


def test_normalize_prefix():
    assert normalize_prefix("AB-CD-EF") == "abcdef"


def test_other_tenant_does_not_match_or_cause_ambiguity(memory_repo):
    repo = memory_repo
    if isinstance(repo, SqliteMemoryRepository):
        SqliteIdentityRepository(repo._db_path).ensure_account(Account(user_id="other"))
        other = SqliteMemoryRepository(repo._db_path, user_id="other")
    else:
        PostgresIdentityRepository(repo._dsn).ensure_account(Account(user_id="other"))
        other = PostgresMemoryRepository(repo._dsn, user_id="other")
    seed(repo)
    seed(other, B, shared=True)
    assert repo.get("abcdef").uuid == A
    assert other.get("abcdef").uuid == B
    assert repo.get("abcdef02") is None
    repo.append("abcdef", " changed")
    assert other.get(B).full_content == "original"


def test_legacy_ids_do_not_participate_in_prefix_matching(memory_repo):
    seed(memory_repo, "abcdef-legacy", shared=True)
    assert memory_repo.get("abcdef") is None


def test_same_exact_uuid_in_both_tables_is_never_arbitrarily_selected(memory_repo):
    seed(memory_repo)
    seed(memory_repo, A, shared=True)
    with pytest.raises(AmbiguousRecordReference) as caught:
        memory_repo.append(A, " forbidden")
    assert len(caught.value.candidates) == 2
    assert {row.table for row in caught.value.candidates} == {"memory_record", "shared_record"}


def test_exact_deleted_legacy_id_is_not_reinterpreted_as_a_prefix(memory_repo):
    seed(memory_repo)
    seed(memory_repo, "abcdef", shared=True)
    memory_repo.soft_delete("abcdef")
    assert memory_repo.get("abcdef") is None
    assert memory_repo.get("abcdef01").uuid == A
