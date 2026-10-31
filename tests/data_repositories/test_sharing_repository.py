"""The ``SharingRepository`` contract, run against whichever backend is asked for.

The same arrangement as the memory repository contract: the SQLite parameter is the
default fast suite, the Postgres one is marked and skips unless ``MUNNIN_PG_TEST_URL`` is
set, and the *same* assertions prove both engines. What differs between the two
implementations is dialect; what must not differ is behaviour, and especially the two
properties that are easy to get subtly wrong: a re-grant revives the existing row, and
``redeem`` has exactly one winner.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from munnin.data_entities.identity import Account
from munnin.data_entities.sharing import TenantInvite
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sharing_repository import SqliteSharingRepository

PAST = "2000-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


@pytest.fixture(params=["sqlite", "postgres"])
def sharing_repo(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "sqlite":
        db = tmp_path / "sharing.db"
        identity = SqliteIdentityRepository(db)
        identity.ensure_account(Account(user_id="alvi"))
        identity.ensure_account(Account(user_id="roy", display_name="Roy", email="roy@example.com"))
        identity.ensure_account(Account(user_id="sam", email="sam@example.com"))
        return SqliteSharingRepository(db)

    url = os.getenv("MUNNIN_PG_TEST_URL")
    if not url:
        pytest.skip("MUNNIN_PG_TEST_URL not set")
    import psycopg

    from munnin.data_repositories.postgres_identity_repository import PostgresIdentityRepository
    from munnin.data_repositories.postgres_sharing_repository import PostgresSharingRepository

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
    identity = PostgresIdentityRepository(url)
    identity.ensure_account(Account(user_id="alvi"))
    identity.ensure_account(Account(user_id="roy", display_name="Roy", email="roy@example.com"))
    identity.ensure_account(Account(user_id="sam", email="sam@example.com"))
    return PostgresSharingRepository(url)


def _invite(code: str = "code-1", tenant: str = "alvi", expires: str = FUTURE) -> TenantInvite:
    return TenantInvite(
        code=code,
        tenant_user_id=tenant,
        created_by=tenant,
        created_date=_now(),
        expires_date=expires,
    )


# --- the remembered selection ---


def test_the_selection_is_absent_until_it_is_set(sharing_repo) -> None:
    assert sharing_repo.find_active("roy") is None


def test_the_selection_round_trips_and_can_be_cleared(sharing_repo) -> None:
    sharing_repo.set_active("roy", "alvi")
    assert sharing_repo.find_active("roy") == "alvi"
    sharing_repo.set_active("roy", None)
    assert sharing_repo.find_active("roy") is None


# --- grants ---


def test_a_grant_is_idempotent_and_shows_on_both_sides(sharing_repo) -> None:
    sharing_repo.grant("alvi", "roy")
    sharing_repo.grant("alvi", "roy")
    assert [a.member_user_id for a in sharing_repo.members_of("alvi")] == ["roy"]
    assert [a.tenant_user_id for a in sharing_repo.grants_for("roy")] == ["alvi"]


def test_revoking_marks_the_row_and_re_granting_revives_it(sharing_repo) -> None:
    sharing_repo.grant("alvi", "roy")
    assert sharing_repo.revoke("alvi", "roy") is True
    revoked = sharing_repo.find_access("alvi", "roy")
    assert revoked is not None and revoked.live is False
    assert sharing_repo.revoke("alvi", "roy") is False  # nothing left to revoke

    revived = sharing_repo.grant("alvi", "roy")
    assert revived.live is True
    assert len(sharing_repo.members_of("alvi")) == 1  # revived, not a second row


def test_revoked_access_still_appears_in_the_lists(sharing_repo) -> None:
    """A tombstone, not a deletion: the history of who has been in the account survives."""
    sharing_repo.grant("alvi", "roy")
    sharing_repo.revoke("alvi", "roy")
    assert sharing_repo.find_access("alvi", "roy") is not None
    assert len(sharing_repo.grants_for("roy")) == 1


# --- invitations ---


def test_an_invite_round_trips(sharing_repo) -> None:
    created = sharing_repo.create_invite(_invite())
    found = sharing_repo.find_invite("code-1")
    assert found is not None
    assert created.code == found.code == "code-1"
    assert found.used_by is None


def test_redeeming_consumes_the_invite_and_writes_the_grant(sharing_repo) -> None:
    sharing_repo.create_invite(_invite())
    assert sharing_repo.redeem("code-1", "roy") is True
    used = sharing_repo.find_invite("code-1")
    assert used is not None and used.used_by == "roy"
    assert sharing_repo.find_access("alvi", "roy").live is True  # type: ignore[union-attr]


def test_a_code_works_exactly_once(sharing_repo) -> None:
    sharing_repo.create_invite(_invite())
    assert sharing_repo.redeem("code-1", "roy") is True
    assert sharing_repo.redeem("code-1", "sam") is False
    assert sharing_repo.find_access("alvi", "sam") is None


def test_an_expired_or_revoked_or_unknown_code_writes_nothing(sharing_repo) -> None:
    sharing_repo.create_invite(_invite("old", expires=PAST))
    assert sharing_repo.redeem("old", "roy") is False

    sharing_repo.create_invite(_invite("pulled"))
    assert sharing_repo.revoke_invite("pulled") is True
    assert sharing_repo.redeem("pulled", "roy") is False

    assert sharing_repo.redeem("never-existed", "roy") is False
    assert sharing_repo.find_access("alvi", "roy") is None


def test_a_code_cannot_admit_the_tenant_to_itself(sharing_repo) -> None:
    sharing_repo.create_invite(_invite())
    assert sharing_repo.redeem("code-1", "alvi") is False
    assert sharing_repo.find_access("alvi", "alvi") is None


def test_revoking_a_used_invite_does_not_un_use_it(sharing_repo) -> None:
    sharing_repo.create_invite(_invite())
    sharing_repo.redeem("code-1", "roy")
    assert sharing_repo.revoke_invite("code-1") is False
    assert sharing_repo.find_invite("code-1").used_by == "roy"  # type: ignore[union-attr]


# --- labels ---


def test_the_label_prefers_the_display_name_then_the_email(sharing_repo) -> None:
    assert sharing_repo.account_label("roy") == "Roy"
    assert sharing_repo.account_label("sam") == "sam@example.com"
    assert sharing_repo.account_label("nobody") is None
