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
from munnin.business_services.service_factory import ServiceFactory
from munnin.configuration.config import load_config
from tests.conftest import FixedTenantResolver, auth_for


async def test_health_endpoint() -> None:
    app = build_app(auth=auth_for("alvi"))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "munnin"


async def test_mcp_initialize_and_ping() -> None:
    # Built without seeding a tenant on purpose: this runs against the *configured*
    # database path, and `ping` touches no store, so creating rows there would be a
    # side effect on a real developer store for no gain.
    config = load_config()
    mcp = build_mcp(ServiceFactory(config.db_path), FixedTenantResolver(config.user_id))
    async with Client(mcp) as client:  # enters = MCP initialize handshake
        tools = await client.list_tools()
        assert any(t.name == "ping" for t in tools)
        result = await client.call_tool("ping", {})
    assert getattr(result, "data", None) == "pong" or "pong" in str(result)
