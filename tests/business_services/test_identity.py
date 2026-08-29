"""Resolving a verified token to a tenant.

The security-critical claim in the whole plan lives here: two different subjects must
never resolve to the same tenant, and a known pair must resolve to the same one every
time. Everything downstream trusts this answer without re-checking it.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from munnin.business_services.identity_service import IdentityService
from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_repositories.identity_repository import IdentityRepository

ISS = "https://alvi.authkit.app"
OTHER_ISS = "https://alvi.supabase.co/auth/v1"


def _svc(tmp_path: Path) -> tuple[IdentityRepository, IdentityService]:
    repo = IdentityRepository(tmp_path / "m.db")
    return repo, IdentityService(repo)


def _count(repo: IdentityRepository, table: str) -> int:
    with repo._conn() as conn:  # noqa: SLF001 — counting rows, not exercising a path
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_a_known_pair_resolves_to_its_tenant(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    repo.ensure_account(Account(user_id="alvi"))
    repo.link_identity(UserIdentity(iss=ISS, sub="sub_1", user_id="alvi"))
    assert svc.resolve(ISS, "sub_1") == "alvi"
    assert _count(repo, "account") == 1


def test_an_unknown_pair_creates_exactly_one_tenant_and_one_mapping(tmp_path: Path) -> None:
    repo, svc = _svc(tmp_path)
    user_id = svc.resolve(ISS, "sub_new")
    assert user_id
    assert _count(repo, "account") == 1
    assert _count(repo, "user_identity") == 1
    assert repo.find_user_id(ISS, "sub_new") == user_id


def test_resolving_the_same_unknown_pair_twice_is_idempotent(tmp_path: Path) -> None:
    """A second call must not mint a second tenant — otherwise every request from a new
    person would create one, which is a write amplification with no bound."""
    _, svc = _svc(tmp_path)
    first = svc.resolve(ISS, "sub_new")
    second = svc.resolve(ISS, "sub_new")
    assert first == second


def test_two_subjects_get_two_tenants(tmp_path: Path) -> None:
    """The claim everything else rests on."""
    repo, svc = _svc(tmp_path)
    a = svc.resolve(ISS, "sub_a")
    b = svc.resolve(ISS, "sub_b")
    assert a != b
    assert _count(repo, "account") == 2


def test_the_same_subject_string_under_two_issuers_is_two_tenants(tmp_path: Path) -> None:
    """A subject is unique only within its issuer, so the same string from a different
    authorization server is a different person until somebody says otherwise."""
    _, svc = _svc(tmp_path)
    assert svc.resolve(ISS, "same") != svc.resolve(OTHER_ISS, "same")


def test_two_issuers_may_map_to_one_tenant(tmp_path: Path) -> None:
    """What makes changing issuers an insert rather than a migration: during a swap both
    logins have to land on the same memory."""
    repo, svc = _svc(tmp_path)
    user_id = svc.resolve(ISS, "sub_1")
    repo.link_identity(UserIdentity(iss=OTHER_ISS, sub="uuid-b", user_id=user_id))
    assert svc.resolve(OTHER_ISS, "uuid-b") == user_id
    assert _count(repo, "account") == 1


def test_creating_a_tenant_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The replacement for a sign-up flag: detection instead of a second gate."""
    _, svc = _svc(tmp_path)
    with caplog.at_level(logging.WARNING, logger="munnin.identity"):
        user_id = svc.resolve(ISS, "sub_new")
    assert any(user_id in r.getMessage() for r in caplog.records)


def test_resolving_a_known_pair_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A warning on every ordinary request would train the reader to ignore it."""
    repo, svc = _svc(tmp_path)
    repo.ensure_account(Account(user_id="alvi"))
    repo.link_identity(UserIdentity(iss=ISS, sub="sub_1", user_id="alvi"))
    with caplog.at_level(logging.WARNING, logger="munnin.identity"):
        svc.resolve(ISS, "sub_1")
    assert caplog.records == []


def test_email_is_stored_as_a_label_but_never_used_to_resolve(tmp_path: Path) -> None:
    """Two people may present the same address across issuers — or the same person may
    change theirs. Either way the mapping, not the label, decides the tenant."""
    repo, svc = _svc(tmp_path)
    first = svc.resolve(ISS, "sub_a", email="alvi@example.com")
    second = svc.resolve(OTHER_ISS, "sub_b", email="alvi@example.com")
    assert first != second
    account = repo.get_account(first)
    assert account is not None and account.email == "alvi@example.com"


def test_the_pragma_is_on_for_this_repository_too(tmp_path: Path) -> None:
    """It opens its own connections, so it cannot inherit the other repository's pragma."""
    repo = IdentityRepository(tmp_path / "m.db")
    with repo._conn() as conn:  # noqa: SLF001
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_a_mapping_cannot_name_a_tenant_that_does_not_exist(tmp_path: Path) -> None:
    repo = IdentityRepository(tmp_path / "m.db")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repo.link_identity(UserIdentity(iss=ISS, sub="sub_1", user_id="ghost"))
