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

from fastapi import FastAPI
from fastmcp.server.auth import AuthProvider, MultiAuth
from fastmcp.server.auth.providers.workos import AuthKitProvider

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


def build_auth(config: Config) -> MultiAuth:
    """The single verifier both faces share.

    ``MultiAuth`` wraps one provider today and takes a list entry to accept a second
    issuer later — telegent's machine token is the named future occupant. With no extra
    verifiers it behaves exactly as the provider alone, and it forwards ``set_mcp_path``
    to the wrapped server, so the audience binding below still happens.

    ``AuthKitProvider`` — never ``WorkOSTokenVerifier``, which calls a userinfo endpoint
    on every single request. This one builds a ``JWTVerifier`` against AuthKit's public
    JWKS, so verification is local, and binds the token audience to this server's own
    resource URL once the mount path is known.
    """
    if not config.authkit_domain:
        raise AuthNotConfiguredError(
            "MUNNIN_AUTHKIT_DOMAIN is not set, so no issuer exists to verify tokens "
            "against. Refusing to start: a server that cannot check a token is a "
            "server that serves everyone's memory to anyone."
        )
    return MultiAuth(
        server=AuthKitProvider(
            authkit_domain=config.authkit_domain,
            base_url=config.public_base_url,
        )
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
