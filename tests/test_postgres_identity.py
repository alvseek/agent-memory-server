"""``PostgresIdentityRepository`` tests (marked ``postgres``)."""

from __future__ import annotations

import os

import psycopg
import pytest

from munnin.data_entities import postgres_migrations as pgm
from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_repositories.postgres_identity_repository import (
    PostgresIdentityRepository,
)

URL = os.getenv("MUNNIN_PG_TEST_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set"),
]


@pytest.fixture()
def repo() -> PostgresIdentityRepository:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
        pgm.ensure_schema(conn)
    return PostgresIdentityRepository(URL)


def test_ensure_account_is_idempotent_and_does_not_refresh(
    repo: PostgresIdentityRepository,
) -> None:
    first = repo.ensure_account(Account(user_id="alvi", display_name="Alvi"))
    assert first.user_id == "alvi" and first.display_name == "Alvi"
    second = repo.ensure_account(Account(user_id="alvi", display_name="Changed"))
    assert second.display_name == "Alvi"  # an existing tenant is not rewritten


def test_link_identity_and_find_user_id(repo: PostgresIdentityRepository) -> None:
    repo.ensure_account(Account(user_id="alvi"))
    assert repo.find_user_id("https://iss", "sub-a") is None
    repo.link_identity(UserIdentity(iss="https://iss", sub="sub-a", user_id="alvi"))
    assert repo.find_user_id("https://iss", "sub-a") == "alvi"
    # Idempotent: a second link on the same pair leaves the first mapping in place.
    repo.link_identity(UserIdentity(iss="https://iss", sub="sub-a", user_id="other"))
    assert repo.find_user_id("https://iss", "sub-a") == "alvi"


def test_link_to_a_missing_account_is_refused(repo: PostgresIdentityRepository) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repo.link_identity(UserIdentity(iss="https://iss", sub="sub-b", user_id="ghost"))
