"""The two ways resolving a tenant refuses rather than guesses.

Both branches are unreachable in the shipped server — the transport rejects an
unauthenticated request long before a handler runs. That is exactly why they are tested
here: a guard whose first execution happens in production is a guard nobody knows works,
and the whole point of these two is to be loud on the day the guarantee above them slips.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.server.auth.auth import AccessToken

from munnin.business_services.identity_service import IdentityService
from munnin.business_services.tenant_resolver import MissingTokenError, TokenTenantResolver
from munnin.data_repositories.identity_repository import IdentityRepository


def _resolver(tmp_path: Path) -> TokenTenantResolver:
    return TokenTenantResolver(IdentityService(IdentityRepository(tmp_path / "m.db")))


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
