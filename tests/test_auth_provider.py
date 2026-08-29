"""The shared verifier both faces sit behind.

These assert the three properties the tenancy design leans on, each of which is easy to
believe without checking and expensive to be wrong about: the server refuses to start
with no issuer, verification is local against a JWKS rather than a call per request, and
the audience really is bound to this server rather than left open.

The audience assertions call ``set_mcp_path`` explicitly. That is not a shortcut around
the real wiring — it *is* the real trigger. Binding happens there rather than in
``__init__``, so a freshly constructed provider legitimately has ``audience is None``, and
a test that skipped this step would assert nothing while appearing to assert everything.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.providers.jwt import JWTVerifier

from munnin.app import AuthNotConfiguredError, build_auth
from munnin.configuration.config import Config

DOMAIN = "https://munnin-test.authkit.app"
BASE_URL = "https://munnin.example.test"


def _config() -> Config:
    return Config(authkit_domain=DOMAIN, public_base_url=BASE_URL)


def test_missing_issuer_refuses_to_build() -> None:
    """An unset issuer stops the server rather than quietly opening it."""
    with pytest.raises(AuthNotConfiguredError):
        build_auth(Config(authkit_domain=""))


def test_verifier_is_jwks_based_not_userinfo() -> None:
    """Local verification against AuthKit's public JWKS — no outbound call per request.

    The failure this guards is picking ``WorkOSTokenVerifier``, which is in the same
    module, is named more obviously, and calls a userinfo endpoint on every request.
    """
    verifier = build_auth(_config()).server.token_verifier
    assert isinstance(verifier, JWTVerifier)
    assert verifier.jwks_uri == f"{DOMAIN}/oauth2/jwks"
    assert verifier.issuer == DOMAIN
    assert verifier.algorithm == "RS256"


def test_audience_is_unbound_until_the_mount_path_is_known() -> None:
    """Documents the late binding, so a future reader does not test the wrong moment."""
    assert build_auth(_config()).server.token_verifier.audience is None


def test_audience_binds_to_this_server_through_multiauth() -> None:
    """The property decision 8 rests on: wrapping in ``MultiAuth`` costs nothing.

    ``MultiAuth`` owns no audience of its own — it forwards ``set_mcp_path`` to the
    provider it wraps. If that forwarding ever stopped, tokens would be accepted with no
    audience check at all and every test above would still pass, which is why the
    assertion is made through the wrapper rather than on the provider directly.
    """
    auth = build_auth(_config())
    auth.set_mcp_path("/mcp")
    assert auth.server.token_verifier.audience == f"{BASE_URL}/mcp"


def test_no_client_secret_is_held() -> None:
    """A resource server verifies with public keys only (decision 16).

    This is what keeps the work clear of the deploy's secret-handling boundary, so it is
    worth failing loudly if a future provider swap starts demanding a credential.
    """
    provider = build_auth(_config()).server
    assert [name for name in vars(provider) if "secret" in name.lower()] == []
