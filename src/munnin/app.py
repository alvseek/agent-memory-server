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
from munnin.business_services.memory_service import MemoryService
from munnin.configuration.config import Config, load_config
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def build_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()

    # DI graph: store -> service -> adapters
    repo = SqliteMemoryRepository(config.db_path, user_id=config.user_id)
    service = MemoryService(repo, user_id=config.user_id)

    mcp = build_mcp(service)
    mcp_app = mcp.http_app(path="/")  # StarletteWithLifespan (streamable-HTTP)

    # Propagate the MCP app's lifespan to the parent app.
    app = FastAPI(title="munnin", version=__version__, lifespan=mcp_app.lifespan)
    app.include_router(build_router(service))
    app.mount("/mcp", mcp_app)
    return app
