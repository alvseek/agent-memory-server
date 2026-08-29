"""Composition root — build the co-hosted ASGI app + wire the DI graph.

One uvicorn app serves both faces over one core:
  - FastMCP streamable-HTTP mounted at ``/mcp``
  - FastAPI (``/health`` now, ``/api`` ops in Phase 5)

The mounted MCP app carries a lifespan (its session manager) that MUST be handed
to the parent FastAPI app, or the MCP session manager never starts.
"""

from __future__ import annotations

from fastapi import FastAPI

from munnin import __version__
from munnin.api_http.api import build_router
from munnin.api_mcp.server import build_mcp
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.tenant_resolver import StaticTenantResolver
from munnin.configuration.config import Config, load_config
from munnin.content.loader import ContentLoader


def build_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()

    # DI graph: store -> per-tenant service factory -> adapters; content served live from
    # the submodule. The factory replaces the single boot-time service: the tenant is now
    # a property of each request rather than of the process.
    factory = ServiceFactory(config.db_path)
    # TEMPORARY (deleted in Step 3.4): reproduces the old single-tenant behaviour so the
    # plumbing can move before token verification exists. This is the one path by which a
    # tenant is chosen without a token, and it must not outlive that step.
    resolver = StaticTenantResolver(config.user_id)
    content = ContentLoader(config.content_root)

    mcp = build_mcp(factory, resolver, content)
    mcp_app = mcp.http_app(path="/")  # StarletteWithLifespan (streamable-HTTP)

    # Propagate the MCP app's lifespan to the parent app.
    app = FastAPI(title="munnin", version=__version__, lifespan=mcp_app.lifespan)
    app.include_router(build_router(factory, resolver, content))
    app.mount("/mcp", mcp_app)
    return app
