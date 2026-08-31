"""Composition root — build the co-hosted ASGI app + wire the DI graph.

One uvicorn app serves both faces over one core:
  - FastMCP streamable-HTTP mounted at ``/mcp``
  - FastAPI (``/health`` + the ``/api`` surface)

The mounted MCP app carries a lifespan (its session manager) that MUST be handed
to the parent FastAPI app, or the MCP session manager never starts.

Both faces verify tokens through **one** provider object rather than two independently
configured ones. Two verifiers would have to agree with each other forever, with nothing
reporting the moment they stopped — which is the drift ``test_twin_parity`` exists to
catch, applied to the one seam where drift means an open door.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from fastmcp.server.auth import AuthProvider, MultiAuth, RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.workos import AuthKitProvider
from pydantic import AnyHttpUrl

from munnin import __version__
from munnin.api_http.api import build_router
from munnin.api_mcp.server import build_mcp
from munnin.business_services.identity_service import IdentityService
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.tenant_resolver import TokenTenantResolver
from munnin.configuration.config import Config, load_config
from munnin.content.loader import ContentLoader
from munnin.data_repositories.identity_repository import IdentityRepository


class AuthNotConfiguredError(RuntimeError):
    """Raised when the server is started without an issuer to verify tokens against."""


class _ResourceBoundVerifier(JWTVerifier):
    """A JWT verifier that binds its own audience once the mount path is known.

    ``MultiAuth`` forwards ``set_mcp_path`` to every verifier it holds, but a plain
    ``JWTVerifier`` inherits the base implementation, which records the resource URL and
    never tells itself about it. A fallback verifier built the obvious way would therefore
    leave ``audience`` at ``None`` and accept tokens minted for any resource at all —
    silently, because a check that is skipped looks exactly like a check that passed.
    """

    def set_mcp_path(self, mcp_path: str | None) -> None:
        super().set_mcp_path(mcp_path)
        if self.audience is None and self._resource_url is not None:
            self.audience = str(self._resource_url)


class LogtoAuthProvider(RemoteAuthProvider):
    """Logto as the authorization server; Munnin stays a pure resource server.

    Logto ships no FastMCP provider class and needs none — the shape is a JWKS verifier
    plus the address of whoever mints the tokens, which is all FastMCP's own
    ``KeycloakAuthProvider`` is. Both OIDC paths are derived from the tenant endpoint
    because Logto fixes them and does not allow either to be customised.

    ``set_mcp_path`` is overridden for one reason, and omitting it would fail quietly: the
    base class records the resource URL without passing it to the verifier, so ``audience``
    would stay ``None`` and every token would clear the audience check by never being
    subjected to it. ``AuthKitProvider`` overrides it for exactly this reason;
    ``KeycloakAuthProvider`` does not, which is the trap in copying that file as-is.

    ``scopes_supported`` is passed for a symmetrical reason, and omitting it also failed
    quietly. A client builds its authorization request from what this server advertises in
    its protected-resource metadata, so an empty list tells the client to ask for nothing —
    and an authorization request carrying a resource but no scopes leaves the issuer with
    nothing to grant, which Logto answers with ``access_denied`` *after* the person has
    already signed in. Nothing in the server logs an error; the failure looks like a
    refused login. ``KeycloakAuthProvider`` defaults to ``["openid"]`` for this reason and
    the original copy dropped it.
    """

    #: Advertised so clients know what to ask for. ``openid`` is what makes it an OIDC
    #: request at all; ``profile`` and ``email`` populate the label on an account row;
    #: ``offline_access`` buys a refresh token, without which a connector silently stops
    #: working whenever the access token expires.
    DEFAULT_SCOPES = ("openid", "profile", "email", "offline_access")

    def __init__(
        self, *, endpoint: str, base_url: str, audience: Sequence[str] = ()
    ) -> None:
        oidc = f"{endpoint.rstrip('/')}/oidc"
        self._pinned_audience = tuple(audience)
        super().__init__(
            token_verifier=JWTVerifier(
                jwks_uri=f"{oidc}/jwks",
                issuer=oidc,
                algorithm="RS256",
                # A list even for a single entry, because the plural form is what lets
                # two registered identifiers be trusted at the same time.
                audience=list(self._pinned_audience) or None,
            ),
            authorization_servers=[AnyHttpUrl(oidc)],
            base_url=AnyHttpUrl(base_url.rstrip("/")),
            # Advertised, deliberately not required. Enforcing ``openid`` on an incoming
            # token adds a rejection path while proving almost nothing — every OIDC token
            # carries it — and the access control that matters here is the audience check
            # plus tenant resolution, both of which already run.
            scopes_supported=list(self.DEFAULT_SCOPES),
        )

    def set_mcp_path(self, mcp_path: str | None) -> None:
        """Bind the verifier's audience to the resource URL this server advertises."""
        super().set_mcp_path(mcp_path)
        if self._pinned_audience:
            return
        if self._resource_url is not None and isinstance(self.token_verifier, JWTVerifier):
            self.token_verifier.audience = str(self._resource_url)


def build_auth(config: Config) -> MultiAuth:
    """The single verifier both faces share.

    Exactly one issuer owns discovery — it is the address a client is sent to in order to
    log in. A second one, when present, contributes verification only, and that asymmetry
    is what makes replacing an issuer safe: new logins go to the replacement while tokens
    the old issuer already minted keep working, so the swap needs no window in which
    nobody can get in. Logto takes the discovery role whenever it is configured, because a
    swap moves toward it and never back.

    Both paths verify locally against a public JWKS. Neither ``WorkOSTokenVerifier`` nor
    ``ClerkProvider`` appears anywhere here: both call the vendor on every single request,
    and ``ClerkProvider`` additionally proxies OAuth, which would put a client secret on
    the box and make this server the issuer of its own tokens.
    """
    if not config.logto_endpoint and not config.authkit_domain:
        raise AuthNotConfiguredError(
            "Neither MUNNIN_LOGTO_ENDPOINT nor MUNNIN_AUTHKIT_DOMAIN is set, so no issuer "
            "exists to verify tokens against. Refusing to start: a server that cannot "
            "check a token is a server that serves everyone's memory to anyone."
        )

    if not config.logto_endpoint:
        return MultiAuth(
            server=AuthKitProvider(
                authkit_domain=config.authkit_domain,
                base_url=config.public_base_url,
            )
        )

    # AuthKit stays on as a verify-only fallback for as long as both are configured. It is
    # rebuilt here rather than lifted off an ``AuthKitProvider``, because that provider
    # binds its verifier's audience inside its own ``set_mcp_path`` — a hook nothing calls
    # once the verifier is held directly by ``MultiAuth``.
    fallback = (
        [
            _ResourceBoundVerifier(
                jwks_uri=f"{config.authkit_domain}/oauth2/jwks",
                issuer=config.authkit_domain,
                algorithm="RS256",
                base_url=config.public_base_url,
            )
        ]
        if config.authkit_domain
        else []
    )
    return MultiAuth(
        server=LogtoAuthProvider(
            endpoint=config.logto_endpoint,
            base_url=config.public_base_url,
            audience=config.logto_audience,
        ),
        verifiers=fallback,
    )


def build_app(config: Config | None = None, auth: AuthProvider | None = None) -> FastAPI:
    """Wire the whole graph.

    ``auth`` exists so tests can present a chosen subject through a doubled verifier.
    It replaces *which* issuer is trusted and never whether verification happens — there
    is deliberately no value here that switches auth off, because the path under test
    has to stay the path that ships.
    """
    config = config or load_config()
    auth = auth if auth is not None else build_auth(config)

    # DI graph: store -> per-tenant service factory -> adapters; content served live from
    # the submodule. The factory replaces the single boot-time service: the tenant is now
    # a property of each request rather than of the process.
    factory = ServiceFactory(config.db_path)
    content = ContentLoader(config.content_root)

    # Both faces resolve their tenant from the same verified token, through the same
    # identity service — the MCP face from FastMCP's request context, the HTTP face from
    # a dependency, because those are the only places each transport exposes it.
    identity = IdentityService(IdentityRepository(config.db_path))
    mcp = build_mcp(factory, TokenTenantResolver(identity), content, auth=auth)
    mcp_app = mcp.http_app(path="/")  # StarletteWithLifespan (streamable-HTTP)

    # The parent app takes the MCP app's lifespan, or its session manager never starts.
    #
    # The schema routes are the only HTTP surface the guard cannot reach: FastAPI adds
    # them to the app itself, not to a router, so they can be present or absent but never
    # protected. Absent by default, and ``openapi_url=None`` removes /docs and /redoc with
    # it, since both are rendered from the schema.
    app = FastAPI(
        title="munnin",
        version=__version__,
        lifespan=mcp_app.lifespan,
        openapi_url="/openapi.json" if config.docs_enabled else None,
    )
    app.include_router(build_router(factory, content, auth=auth, identity=identity))
    app.mount("/mcp", mcp_app)

    # OAuth discovery, served from the **root**. FastMCP builds its app believing it sits
    # at "/", so it advertises root-level metadata URLs and puts its own copies of these
    # routes inside the sub-app — which FastAPI then mounts under /mcp, leaving the
    # advertised URLs 404. Measured: a 401 answers
    # `WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource"`
    # while the document only existed at `/mcp/.well-known/...`, so a client following the
    # standard flow would fail discovery and never reach a login screen.
    #
    # These two are deliberately unauthenticated, and must be: a client reads them to find
    # out how to obtain a token, so requiring one would be circular (RFC 9728).
    app.router.routes.extend(auth.get_well_known_routes())
    return app
