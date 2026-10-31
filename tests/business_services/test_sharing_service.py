"""The sharing rules, one test per rule, against the real SQLite repository.

The service is where every decision lives, so this file is the one that would catch a rule
moving into an adapter later: each test fails if its rule is removed, and the refusal
messages are asserted on their distinctive wording because that wording is what a person
reads when access ends.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.sharing_service import (
    AmbiguousLabel,
    BadInvite,
    NotOwner,
    NotPermitted,
    SharingService,
)
from munnin.data_entities.identity import Account
from munnin.data_entities.sharing import TenantInvite
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sharing_repository import SqliteSharingRepository

PAST = "2000-01-01T00:00:00+00:00"


def _world(tmp_path: Path) -> tuple[SqliteSharingRepository, Path]:
    db = tmp_path / "sharing.db"
    identity = SqliteIdentityRepository(db)
    identity.ensure_account(Account(user_id="alvi", display_name="Alvi"))
    identity.ensure_account(Account(user_id="alvi2", display_name="Alvi"))
    identity.ensure_account(Account(user_id="roy", display_name="Roy", email="roy@example.com"))
    identity.ensure_account(Account(user_id="roy2", display_name="Roy"))
    identity.ensure_account(Account(user_id="sam", email="sam@example.com"))
    return SqliteSharingRepository(db), db


def _service(
    tmp_path: Path, *, home: str = "alvi", selected: str | None = None
) -> tuple[SharingService, SqliteSharingRepository]:
    repo, _ = _world(tmp_path)
    return SharingService(repo, home_user_id=home, selected_user_id=selected), repo


# --- where am I ---


def test_the_default_tenant_is_your_own_and_it_comes_first(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    refs = service.list_tenants()
    assert [r.user_id for r in refs] == ["alvi"]
    assert refs[0].role == "owner" and refs[0].active is True


def test_only_live_grants_appear_as_tenants_you_may_enter(tmp_path: Path) -> None:
    service, repo = _service(tmp_path, home="roy")
    repo.grant("alvi", "roy")
    repo.grant("roy2", "roy")
    repo.revoke("roy2", "roy")
    assert [(r.user_id, r.role) for r in service.list_tenants()] == [
        ("roy", "owner"),
        ("alvi", "guest"),
    ]


def test_switching_by_id_and_by_label_both_work(tmp_path: Path) -> None:
    repo, _ = _world(tmp_path)
    repo.grant("alvi", "roy")
    service = SharingService(repo, home_user_id="roy")

    by_id = service.use_tenant("alvi")
    assert by_id.user_id == "alvi" and by_id.active is True
    assert repo.find_active("roy") == "alvi"

    service.use_tenant("Alvi")
    assert repo.find_active("roy") == "alvi"

    service.use_tenant(None)
    assert repo.find_active("roy") is None
    assert service.acting_user_id == "roy"


def test_an_ambiguous_label_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    service, repo = _service(tmp_path, home="roy")
    repo.grant("alvi", "roy")
    repo.grant("alvi2", "roy")
    with pytest.raises(AmbiguousLabel, match="names more than one tenant"):
        service.use_tenant("Alvi")


def test_an_unknown_tenant_is_refused(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    with pytest.raises(NotPermitted, match="no tenant called"):
        service.use_tenant("nobody")


def test_a_revoked_tenant_says_it_was_revoked(tmp_path: Path) -> None:
    service, repo = _service(tmp_path, home="roy")
    repo.grant("alvi", "roy")
    repo.revoke("alvi", "roy")
    with pytest.raises(NotPermitted, match="was revoked"):
        service.use_tenant("alvi")


def test_a_selection_that_lost_access_is_still_shown_and_still_active(tmp_path: Path) -> None:
    """A person whose access just ended is standing somewhere real. Reporting no active
    tenant at all leaves them with no visible reason for every refusal, and no statement of
    where they are — so the dead selection is listed, marked, and cannot be re-entered."""
    repo, _ = _world(tmp_path)
    repo.grant("alvi", "roy")
    repo.revoke("alvi", "roy")
    service = SharingService(repo, home_user_id="roy", selected_user_id="alvi")

    refs = service.list_tenants()

    assert [(r.user_id, r.role, r.active, r.revoked) for r in refs] == [
        ("roy", "owner", False, False),
        ("alvi", "guest", True, True),
    ]
    with pytest.raises(NotPermitted, match="was revoked"):
        service.use_tenant("alvi")


# --- who may grant ---


def test_only_the_owner_of_the_acting_tenant_may_invite(tmp_path: Path) -> None:
    repo, _ = _world(tmp_path)
    repo.grant("alvi", "roy")
    service = SharingService(repo, home_user_id="roy", selected_user_id="alvi")
    with pytest.raises(NotOwner, match="only the owner"):
        service.create_invite()
    with pytest.raises(NotOwner, match="only the owner"):
        service.revoke_member("sam")
    with pytest.raises(NotOwner, match="only the owner"):
        service.revoke_invite("whatever")


def test_an_invite_is_minted_for_the_acting_tenant_with_an_expiry(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    invite = service.create_invite()
    assert invite.tenant_user_id == "alvi"
    assert invite.created_by == "alvi"
    assert invite.used_by is None and invite.revoked_date is None
    assert invite.expires_date > invite.created_date
    assert repo.find_invite(invite.code) is not None


def test_members_list_the_owner_first(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    repo.grant("alvi", "roy")
    repo.revoke("alvi", "roy")
    repo.grant("alvi", "roy2")
    rows = service.list_members()
    assert [r["user_id"] for r in rows] == ["alvi", "roy2"]
    assert rows[0]["role"] == "owner" and rows[0]["label"] == "Alvi"
    assert rows[1]["label"] == "Roy"


def test_revoking_a_member_ends_their_access_and_reviving_restores_one_row(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    repo.grant("alvi", "roy")

    service.revoke_member("roy")
    roy = SharingService(repo, home_user_id="roy")
    with pytest.raises(NotPermitted, match="was revoked"):
        roy.use_tenant("alvi")
    assert [r["user_id"] for r in service.list_members()] == ["alvi"]

    invite = service.create_invite()
    roy.redeem(invite.code)
    assert len(repo.members_of("alvi")) == 1
    assert [r["user_id"] for r in service.list_members()] == ["alvi", "roy"]


def test_revoking_your_own_account_is_refused(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    with pytest.raises(BadInvite, match="your own account"):
        service.revoke_member("alvi")


def test_revoking_somebody_without_access_is_refused(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    with pytest.raises(NotPermitted, match="no live access"):
        service.revoke_member("sam")


# --- joining ---


def test_redeeming_joins_without_switching(tmp_path: Path) -> None:
    alvi, repo = _service(tmp_path)
    roy = SharingService(repo, home_user_id="roy")
    invite = alvi.create_invite()

    joined = roy.redeem(invite.code)

    assert joined == {"tenant_user_id": "alvi", "label": "Alvi", "role": "guest"}
    assert repo.find_active("roy") is None
    assert [r.user_id for r in roy.list_tenants()] == ["roy", "alvi"]


def test_a_code_cannot_be_used_twice(tmp_path: Path) -> None:
    alvi, repo = _service(tmp_path)
    roy = SharingService(repo, home_user_id="roy")
    sam = SharingService(repo, home_user_id="sam")
    invite = alvi.create_invite()

    roy.redeem(invite.code)
    with pytest.raises(BadInvite, match="already been used"):
        sam.redeem(invite.code)


def test_a_revoked_expired_or_unknown_code_says_which(tmp_path: Path) -> None:
    alvi, repo = _service(tmp_path)
    roy = SharingService(repo, home_user_id="roy")

    pulled = alvi.create_invite()
    alvi.revoke_invite(pulled.code)
    with pytest.raises(BadInvite, match="was revoked"):
        roy.redeem(pulled.code)

    repo.create_invite(
        TenantInvite(
            code="stale",
            tenant_user_id="alvi",
            created_by="alvi",
            created_date=PAST,
            expires_date=PAST,
        )
    )
    with pytest.raises(BadInvite, match="has expired"):
        roy.redeem("stale")

    with pytest.raises(BadInvite, match="does not exist"):
        roy.redeem("never-existed")


def test_your_own_tenant_needs_no_invitation(tmp_path: Path) -> None:
    alvi, repo = _service(tmp_path)
    invite = repo.create_invite(
        TenantInvite(
            code="self",
            tenant_user_id="alvi",
            created_by="alvi",
            created_date=PAST,
            expires_date="2999-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(BadInvite, match="you already own"):
        alvi.redeem(invite.code)
