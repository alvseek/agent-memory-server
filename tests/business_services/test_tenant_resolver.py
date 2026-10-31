"""Every way resolving a tenant refuses rather than guesses.

Two of these branches are unreachable in the shipped server — the transport rejects an
unauthenticated request long before a handler runs. That is exactly why they are tested
here: a guard whose first execution happens in production is a guard nobody knows works,
and the whole point of these is to be loud on the day the guarantee above them slips.

The third branch is very reachable: a person whose access to the tenant they were sitting
in has just been revoked. It must refuse rather than quietly serve their own memory, which
would look like a successful call and land the wrong data in the conversation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.server.auth.auth import AccessToken

from munnin.business_services.identity_service import IdentityService
from munnin.business_services.tenant_resolver import (
    MissingTokenError,
    TenantAccessRevoked,
    TokenTenantResolver,
)
from munnin.data_entities.identity import Account
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sharing_repository import SqliteSharingRepository


def _parts(
    tmp_path: Path,
) -> tuple[TokenTenantResolver, SqliteSharingRepository, SqliteIdentityRepository]:
    db = tmp_path / "m.db"
    identity_repo = SqliteIdentityRepository(db)
    sharing = SqliteSharingRepository(db)
    return TokenTenantResolver(IdentityService(identity_repo), sharing), sharing, identity_repo


def _resolver(tmp_path: Path) -> TokenTenantResolver:
    return _parts(tmp_path)[0]


def _token(**claims: str) -> AccessToken:
    return AccessToken(token="t", client_id="c", scopes=[], claims=claims)


def test_no_token_at_all_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A handler running outside the guard must fail, not pick somebody."""
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token", lambda: None
    )
    with pytest.raises(MissingTokenError, match="no verified token"):
        _resolver(tmp_path).current_user_id()


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"iss": "https://issuer.test"},
        {"sub": "someone"},
        {"iss": "", "sub": "someone"},
        {"iss": "https://issuer.test", "sub": ""},
    ],
)
def test_a_token_that_names_nobody_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claims: dict[str, str]
) -> None:
    """Verified is not identified.

    Half a pair is as useless as none: ``(iss, sub)`` is the key, so an issuer without a
    subject names an authority rather than a person. Empty strings are included because
    they are what a claim stripped by a misconfigured issuer actually looks like — falsy
    but present, which a ``in claims`` check would wave through.
    """
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(**claims),
    )
    with pytest.raises(MissingTokenError, match="names no tenant"):
        _resolver(tmp_path).current_user_id()


def test_a_complete_token_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: the refusals above are the check, not a broken resolver."""
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(iss="https://issuer.test", sub="someone"),
    )
    resolver = _resolver(tmp_path)
    first = resolver.current_user_id()
    assert first
    assert resolver.current_user_id() == first


# --- the remembered selection ---


def test_a_live_selection_is_what_the_call_acts_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(iss="https://issuer.test", sub="someone"),
    )
    resolver, sharing, identity = _parts(tmp_path)
    home = resolver.current_home_user_id()
    identity.ensure_account(Account(user_id="other", display_name="Other"))
    sharing.grant("other", home)
    sharing.set_active(home, "other")

    assert resolver.current_user_id() == "other"
    assert resolver.current_home_user_id() == home


def test_a_revoked_selection_refuses_and_names_the_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alternative — falling back to the caller's own tenant — would answer a question
    nobody asked, with somebody else's memory, and look like success."""
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(iss="https://issuer.test", sub="someone"),
    )
    resolver, sharing, identity = _parts(tmp_path)
    home = resolver.current_home_user_id()
    identity.ensure_account(Account(user_id="other", display_name="Other"))
    sharing.grant("other", home)
    sharing.set_active(home, "other")
    sharing.revoke("other", home)

    with pytest.raises(TenantAccessRevoked, match="was revoked"):
        resolver.current_user_id()
    # The home tenant is still answerable, which is what keeps use_tenant reachable.
    assert resolver.current_home_user_id() == home


def test_a_selection_to_a_never_granted_tenant_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(iss="https://issuer.test", sub="someone"),
    )
    resolver, sharing, identity = _parts(tmp_path)
    home = resolver.current_home_user_id()
    identity.ensure_account(Account(user_id="other", display_name="Other"))
    sharing.set_active(home, "other")

    with pytest.raises(TenantAccessRevoked, match="was revoked"):
        resolver.current_user_id()


def test_selecting_your_own_tenant_is_the_same_as_no_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "munnin.business_services.tenant_resolver.get_access_token",
        lambda: _token(iss="https://issuer.test", sub="someone"),
    )
    resolver, sharing, _ = _parts(tmp_path)
    home = resolver.current_home_user_id()
    sharing.set_active(home, home)
    assert resolver.current_user_id() == home
