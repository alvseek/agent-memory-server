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
from urllib.parse import urlsplit

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
from munnin.business_services.tenant_resolver import (
    LocalTenantResolver,
    TenantResolver,
    TokenTenantResolver,
)
from munnin.configuration.config import Config, load_config
from munnin.content.loader import ContentLoader
from munnin.data_entities.identity import Account
from munnin.data_repositories.identity_repository import IdentityRepository

#: Where the MCP face is mounted, and therefore the address clients actually connect to.
#: It is a constant rather than two literals because the resource identifier this server
#: advertises has to be the same string, and the one time they disagreed the failure was
#: silent: FastMCP builds its app believing it sits at the root, so it advertised
#: ``https://munnin.lok.quest/`` while every client refreshed against
#: ``https://munnin.lok.quest/mcp/``. A refresh token is frozen to one resource at the
#: moment it is minted, so the issuer answered ``invalid_target`` forever after — and the
#: client quietly fell back to the advertised identifier, which meant nothing broke and
#: every connection paid several failed round trips first.
MCP_MOUNT_PATH = "/mcp"

#: The document a client fetches to learn who issues tokens for this server, at the
#: path RFC 9728 derives from the resource identifier: the well-known prefix followed by
#: the identifier's own path. It is spelled out here only so the normaliser below can
#: name it without reconstructing the derivation.
PROTECTED_RESOURCE_METADATA_PATH = f"/.well-known/oauth-protected-resource{MCP_MOUNT_PATH}"


def mcp_resource_url(public_base_url: str) -> str:
    """The one identifier that names the MCP face — deliberately without a trailing slash.

    This string is what a client sends as ``resource`` on both the authorization and the
    refresh request, and the issuer matches it character for character, so the slash
    question is not cosmetic. The MCP specification settles it: implementations *should
    consistently use the form without the trailing slash*, and clients act on that by
    normalising away any slash they are configured with. The identifier therefore has to
    be the no-slash form, because a client can be made to send nothing else.
    """
    return f"{public_base_url.rstrip('/')}{MCP_MOUNT_PATH}"


class _NormalisePath:
    """Serve the MCP face and its metadata document under both slash forms, no redirect.

    Starlette's ``Mount`` only matches paths *below* the mount, so a request to the bare
    ``/mcp`` never reaches the sub-app — the router answers with a slash-appending 307
    instead. Behind a TLS-terminating proxy that redirect is worse than a detour: it is
    built from the scheme uvicorn saw, so it points at ``http://``, and a client that
    dropped the slash (which the specification tells it to do) is bounced to plaintext
    before it ever sees a 401. The same happens in the other direction for the metadata
    document, which the SDK registers at the no-slash path.

    Rewriting the path before routing is the smallest change that removes the redirect
    entirely: both forms land on the one handler, and nothing on ``/mcp*`` can answer 3xx.
    It rewrites only the two exact paths it names, so every other route keeps Starlette's
    default behaviour. ``raw_path`` is kept in step because middleware further down may
    read either.
    """

    _REWRITES = {
        MCP_MOUNT_PATH: f"{MCP_MOUNT_PATH}/",
        f"{PROTECTED_RESOURCE_METADATA_PATH}/": PROTECTED_RESOURCE_METADATA_PATH,
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            target = self._REWRITES.get(scope["path"])
            if target is not None:
                scope = dict(scope)
                scope["path"] = target
                scope["raw_path"] = target.encode("ascii")
        await self.app(scope, receive, send)


class AuthNotConfiguredError(RuntimeError):
    """Raised when the server is started without an issuer to verify tokens against."""


class LocalModeNotLoopbackError(RuntimeError):
    """Raised when ``MUNNIN_AUTH=off`` would leave the server reachable beyond this machine.

    Local mode serves everyone's memory to whoever can reach the port, which is safe on a
    laptop and a disclosure anywhere else. Two settings say where the server is reachable
    from, and both are checked: the public base URL, which states where it believes it is
    addressed, and the bind address, which decides which interfaces actually answer. A
    container has to bind ``0.0.0.0`` to be reachable even from its own host, so the bind
    check can be waived — but only by ``MUNNIN_LOCAL_BIND_ALL=1``, an explicit statement
    that something in front of the process (a port published on the host's loopback)
    keeps it local. The server cannot detect that; it asks to be told.
    """


#: Hosts a URL may name and still be "this machine only". ``urlsplit`` strips the brackets
#: from an IPv6 literal, so ``::1`` is compared bare.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_host(host: str | None) -> bool:
    """Whether a bare host — a bind address, or the host part of a URL — is this machine."""
    return host is not None and host.strip("[]").lower() in _LOOPBACK_HOSTS


def is_loopback_url(url: str) -> bool:
    """Whether ``url`` names this machine and nothing beyond it."""
    return is_loopback_host(urlsplit(url).hostname)


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
        self,
        *,
        endpoint: str,
        base_url: str,
        audience: Sequence[str] = (),
        resource_base_url: str | None = None,
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
            # What goes in the protected-resource metadata, and so what a client asks the
            # issuer to stamp the token for. It is separate from ``base_url`` because this
            # server is re-hosted: the metadata is served from the root while the resource
            # it describes lives under the mount, and only the caller knows that.
            resource_base_url=resource_base_url,
            # Advertised, deliberately not required. Enforcing ``openid`` on an incoming
            # token adds a rejection path while proving almost nothing — every OIDC token
            # carries it — and the access control that matters here is the audience check
            # plus tenant resolution, both of which already run.
            scopes_supported=list(self.DEFAULT_SCOPES),
        )

    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        """The advertised identifier, fixed rather than assembled from the mount path.

        The base class appends whatever path FastMCP believes it is serving at, which is a
        fact the sub-app gets wrong by construction — it is built for ``/`` and then
        re-hosted under ``/mcp``. Since ``resource_base_url`` already names the face in
        full, ignoring the path is what stops the two disagreeing, in either direction: a
        missing segment, or the doubled ``/mcp/mcp`` a plausible mount would produce.
        """
        if self.resource_base_url is not None:
            return self.resource_base_url
        return super()._get_resource_url(path)

    def set_mcp_path(self, mcp_path: str | None) -> None:
        """Bind the verifier's audience to the resource URL this server advertises."""
        super().set_mcp_path(mcp_path)
        if self._pinned_audience:
            return
        if self._resource_url is not None and isinstance(self.token_verifier, JWTVerifier):
            self.token_verifier.audience = str(self._resource_url)


class _PinnedMultiAuth(MultiAuth):
    """``MultiAuth`` that lets the provider it wraps name the resource identifier.

    FastMCP asks the *outer* auth object for the resource URL when it builds the 401
    challenge, and ``MultiAuth`` inherits the base derivation: ``resource_base_url`` plus
    whatever path the sub-app believes it serves at — ``/`` here, since the app is built
    for the root and re-hosted under the mount. That turns ``…/mcp`` into ``…/mcp/`` on
    the challenge alone, while the route and the document underneath already say
    ``…/mcp``. The mismatch was invisible for as long as the identifier itself ended in a
    slash, which is exactly why it is pinned in one place and every path to it delegates.
    """

    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        if self.server is not None:
            return self.server._get_resource_url(path)
        return super()._get_resource_url(path)


def build_auth(config: Config) -> MultiAuth | None:
    """The single verifier both faces share — or ``None``, in local mode.

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

    ``None`` is returned in exactly one case: ``MUNNIN_AUTH=off`` with a loopback public
    base URL. That is the laptop shape — no identity provider, one tenant — and the guard
    lives here rather than in the config loader so that the same refusal fires whether the
    config came from the environment or was constructed directly.
    """
    if config.auth_mode == "off":
        if not is_loopback_url(config.public_base_url):
            raise LocalModeNotLoopbackError(
                f"MUNNIN_AUTH=off is only accepted while MUNNIN_PUBLIC_BASE_URL names this "
                f"machine (127.0.0.1, localhost or ::1); it is {config.public_base_url!r}. "
                "Refusing to start: a server anyone can reach and nobody has to log in to "
                "serves everyone's memory to anyone."
            )
        if not is_loopback_host(config.host) and not config.local_bind_all:
            raise LocalModeNotLoopbackError(
                f"MUNNIN_AUTH=off with MUNNIN_HOST={config.host!r} would answer on every "
                "interface of this machine with no authentication. Bind to 127.0.0.1, or — "
                "only when something in front of this process publishes the port on the "
                "host's loopback, as compose.yaml does — set MUNNIN_LOCAL_BIND_ALL=1 to say so."
            )
        return None

    if not config.logto_endpoint and not config.authkit_domain:
        raise AuthNotConfiguredError(
            "Neither MUNNIN_LOGTO_ENDPOINT nor MUNNIN_AUTHKIT_DOMAIN is set, so no issuer "
            "exists to verify tokens against. Refusing to start: a server that cannot "
            "check a token is a server that serves everyone's memory to anyone."
        )

    if not config.logto_endpoint:
        return _PinnedMultiAuth(
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
    return _PinnedMultiAuth(
        server=LogtoAuthProvider(
            endpoint=config.logto_endpoint,
            base_url=config.public_base_url,
            audience=config.logto_audience,
            resource_base_url=mcp_resource_url(config.public_base_url),
        ),
        verifiers=fallback,
    )


def build_app(config: Config | None = None, auth: AuthProvider | None = None) -> FastAPI:
    """Wire the whole graph.

    ``auth`` exists so tests can present a chosen subject through a doubled verifier.
    It replaces *which* issuer is trusted and never whether verification happens — no
    value of this parameter switches auth off. The one way to run without verification is
    ``MUNNIN_AUTH=off`` in the config, which ``build_auth`` grants only for a loopback
    public URL; ``local`` below is true exactly when it did.
    """
    config = config or load_config()
    auth = auth if auth is not None else build_auth(config)
    local = auth is None

    # DI graph: store -> per-tenant service factory -> adapters; content served live from
    # the submodule. The factory replaces the single boot-time service: the tenant is now
    # a property of each request rather than of the process.
    factory = ServiceFactory(config.db_path)
    content = ContentLoader(config.content_root)

    # Both faces resolve their tenant the same way — the MCP face from FastMCP's request
    # context, the HTTP face from a dependency, because those are the only places each
    # transport exposes it. In token mode that is the verified token's (iss, sub) pair
    # through the identity service; in local mode it is the one constant tenant, whose
    # account row is created here so the first write does not fail its foreign key.
    identity_repo = IdentityRepository(config.db_path)
    identity = IdentityService(identity_repo)
    resolver: TenantResolver
    if local:
        identity_repo.ensure_account(Account(user_id=config.user_id))
        resolver = LocalTenantResolver(config.user_id)
    else:
        resolver = TokenTenantResolver(identity)
    mcp = build_mcp(factory, resolver, content, auth=auth)
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
    app.include_router(
        build_router(
            factory,
            content,
            auth=auth,
            identity=identity,
            local_user_id=config.user_id if local else None,
        )
    )
    app.mount(MCP_MOUNT_PATH, mcp_app)

    # OAuth discovery, served from the **root**. FastMCP builds its app believing it sits
    # at "/", so it advertises root-level metadata URLs and puts its own copies of these
    # routes inside the sub-app — which FastAPI then mounts under /mcp, leaving the
    # advertised URLs 404. Measured: a 401 answers
    # `WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource"`
    # while the document only existed at `/mcp/.well-known/...`, so a client following the
    # standard flow would fail discovery and never reach a login screen.
    #
    # These two are deliberately unauthenticated, and must be: a client reads them to find
    # out how to obtain a token, so requiring one would be circular (RFC 9728). In local
    # mode there is nothing to discover — no issuer exists — so advertising one would only
    # send a client to a login that cannot happen.
    if auth is not None:
        app.router.routes.extend(auth.get_well_known_routes())

    # Outermost, so the rewrite happens before any router looks at the path — see the
    # class for why a redirect here is a broken login rather than a detour.
    app.add_middleware(_NormalisePath)
    return app
