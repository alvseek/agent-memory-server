"""Smoke test — the Phase 4 exit gate: the empty skeleton boots on both faces.

- HTTP face: GET /health via httpx ASGITransport (no deprecated TestClient).
- MCP face: initialize + list_tools + call ``ping`` via the in-memory fastmcp Client.
"""

from __future__ import annotations

import httpx
from fastmcp import Client
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.app import build_app
from munnin.business_services.memory_service import MemoryService
from munnin.configuration.config import load_config
from tests.conftest import AutoAgentRepository


async def test_health_endpoint() -> None:
    app = build_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "munnin"


def _service() -> MemoryService:
    config = load_config()
    repo = AutoAgentRepository(config.db_path, user_id=config.user_id)
    return MemoryService(repo, user_id=config.user_id)


async def test_mcp_initialize_and_ping() -> None:
    mcp = build_mcp(_service())
    async with Client(mcp) as client:  # enters = MCP initialize handshake
        tools = await client.list_tools()
        assert any(t.name == "ping" for t in tools)
        result = await client.call_tool("ping", {})
    assert getattr(result, "data", None) == "pong" or "pong" in str(result)
