"""The shared verifier both faces sit behind.

These assert the three properties the tenancy design leans on, each of which is easy to
believe without checking and expensive to be wrong about: the server refuses to start
with no issuer, verification is local against a JWKS rather than a call per request, and
the audience really is bound to this server rather than left open.

The audience assertions call ``set_mcp_path`` explicitly. That is not a shortcut around
the real wiring — it *is* the real trigger. Binding happens there rather than in
``__init__``, so a freshly constructed provider legitimately has ``audience is None``, and
a test that skipped this step would assert nothing while appearing to assert everything.

Three issuer arrangements are covered rather than one, because replacing an issuer passes
through all of them in order: AuthKit alone, both at once while the swap is in flight, and
Logto alone at the end. The middle one carries the risk — a token that verifies against
the old issuer must still be checked as strictly as one from the new.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.providers.jwt import JWTVerifier

from munnin.app import AuthNotConfiguredError, LogtoAuthProvider, build_auth
from munnin.configuration.config import Config

DOMAIN = "https://munnin-test.authkit.app"
LOGTO = "https://munnin-test.logto.app"
BASE_URL = "https://munnin.example.test"


def _config() -> Config:
    """AuthKit alone — what shipped, and still the shape whenever Logto is unset."""
    return Config(authkit_domain=DOMAIN, public_base_url=BASE_URL)


def _swapping() -> Config:
    """Mid-swap: Logto owns discovery, AuthKit still verifies its outstanding tokens."""
    return Config(logto_endpoint=LOGTO, authkit_domain=DOMAIN, public_base_url=BASE_URL)


def _logto_only() -> Config:
    """The end state, once AuthKit is removed from the deploy config."""
    return Config(logto_endpoint=LOGTO, public_base_url=BASE_URL)


def test_missing_issuer_refuses_to_build() -> None:
    """No issuer at all stops the server rather than quietly opening it.

    Both names have to be absent now. Checking only one would let a half-configured
    deploy through, and a half-configured deploy is precisely what a swap creates.
    """
    with pytest.raises(AuthNotConfiguredError):
        build_auth(Config(authkit_domain="", logto_endpoint=""))


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


@pytest.mark.parametrize("config", [_config(), _swapping(), _logto_only()])
def test_no_client_secret_is_held(config: Config) -> None:
    """A resource server verifies with public keys only (decision 16).

    This is what keeps the work clear of the deploy's secret-handling boundary, so it is
    worth failing loudly if a provider swap starts demanding a credential. All three
    arrangements are checked, because the rejected alternative — ``ClerkProvider`` — is an
    OAuth proxy that cannot be constructed without one.
    """
    provider = build_auth(config).server
    assert [name for name in vars(provider) if "secret" in name.lower()] == []


def test_logto_owns_discovery_once_it_is_configured() -> None:
    """The swap's direction: whichever provider is ``server`` is where logins are sent."""
    auth = build_auth(_swapping())
    assert isinstance(auth.server, LogtoAuthProvider)
    advertised = str(auth.server.authorization_servers[0]).rstrip("/")
    assert advertised == f"{LOGTO}/oidc"


def test_logto_verifier_is_jwks_based_with_derived_paths() -> None:
    """Logto fixes both OIDC paths and forbids customising them, so deriving is safe."""
    verifier = build_auth(_logto_only()).server.token_verifier
    assert isinstance(verifier, JWTVerifier)
    assert verifier.jwks_uri == f"{LOGTO}/oidc/jwks"
    assert verifier.issuer == f"{LOGTO}/oidc"
    assert verifier.algorithm == "RS256"


def test_logto_audience_binds_to_this_server() -> None:
    """The same late binding AuthKit gets, reimplemented because the base class has none."""
    auth = build_auth(_logto_only())
    auth.set_mcp_path("/mcp")
    assert auth.server.token_verifier.audience == f"{BASE_URL}/mcp"


def test_the_authkit_fallback_still_checks_its_audience() -> None:
    """The trap this arrangement had to step around, and the reason for a verifier subclass.

    ``MultiAuth`` does forward ``set_mcp_path`` to its verifiers, but the base
    implementation only records the resource URL — it never tells the verifier about it.
    A fallback built as a plain ``JWTVerifier`` would keep ``audience is None`` and accept
    a token minted for any resource at all, while every other test in this file passed.
    """
    auth = build_auth(_swapping())
    auth.set_mcp_path("/mcp")
    assert auth.verifiers
    assert auth.verifiers[0].audience == f"{BASE_URL}/mcp"


def test_no_fallback_remains_once_authkit_is_removed() -> None:
    """The end state — one issuer, and nothing left quietly trusting the retired one."""
    assert build_auth(_logto_only()).verifiers == []


def test_a_pinned_audience_wins_over_the_derived_one() -> None:
    """The escape hatch for an API Identifier that is not this server's resource URL.

    Logto matches a token request's ``resource`` against the registered identifier
    character for character, and will not let that identifier be edited after creation —
    so config has to be able to state what was actually registered.
    """
    auth = build_auth(
        Config(
            logto_endpoint=LOGTO,
            public_base_url=BASE_URL,
            logto_audience=("https://pinned.example.test/api",),
        )
    )
    auth.set_mcp_path("/mcp")
    assert auth.server.token_verifier.audience == ["https://pinned.example.test/api"]


def test_scopes_are_advertised_so_a_client_knows_what_to_ask_for() -> None:
    """A client builds its authorization request from what we advertise.

    Advertising nothing made Claude send an authorization request carrying a resource
    and no scopes, which left Logto nothing to grant and produced ``access_denied``
    *after* a successful sign-in — with no error logged anywhere. The empty list was
    the whole defect, so it is pinned here rather than left to be re-omitted.
    """
    provider = LogtoAuthProvider(
        endpoint="https://auth.lok.quest",
        base_url="https://munnin.lok.quest",
    )
    assert provider._scopes_supported == ["openid", "profile", "email", "offline_access"]
    assert "openid" in provider._scopes_supported, (
        "openid is what makes this an OIDC request at all"
    )


def test_scopes_are_advertised_but_not_required() -> None:
    """Advertising is the fix; enforcing would add a rejection path worth nothing.

    Every OIDC token carries ``openid``, so requiring it proves almost nothing, while
    the checks that do carry weight — audience binding and tenant resolution — already
    run on every request.
    """
    provider = LogtoAuthProvider(
        endpoint="https://auth.lok.quest",
        base_url="https://munnin.lok.quest",
    )
    assert not provider.required_scopes
    assert not provider.token_verifier.required_scopes
