"""awaken over both faces — HTTP /api/awaken + MCP awaken tool (SP-1 Step 3.2).

Both go through the same MemoryService.awaken() over a seeded temp DB."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastmcp import Client
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.app import build_app
from munnin.business_services.memory_service import MemoryService
from munnin.configuration.config import Config
from munnin.data_entities.memory_record import SHARED_AGENT_ID, MemoryRecord, RecordType
from tests.conftest import AutoAgentRepository


def _mk(uuid: str, agent: str, rtype: RecordType, content: str, date: str) -> MemoryRecord:
    return MemoryRecord(
        uuid=uuid,
        user_id="",
        agent_id=agent,
        record_type=rtype,
        title=uuid,
        full_content=content,
        created_date=date,
    )


def _seed(db: Path) -> None:
    repo = AutoAgentRepository(db, user_id="alvi")
    repo.insert(_mk("id1", "meta", RecordType.identity, "I am meta", "2026-01-01"))
    repo.insert(_mk("sr1", SHARED_AGENT_ID, RecordType.reasoning, "go slow", "2026-01-01"))
    repo.insert(_mk("ep1", "meta", RecordType.episode, "episode body", "2026-08-09"))


async def test_http_awaken(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    app = build_app(Config(db_path=db, user_id="alvi"))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/awaken", params={"agent_id": "meta"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["agent_id"] == "meta"
    assert payload["identity"][0]["content"] == "I am meta"
    assert payload["shared"]["reasoning"][0]["uuid"] == "sr1"
    assert payload["latest_episode"]["uuid"] == "ep1"


async def test_http_awaken_invalid_domain_400(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    app = build_app(Config(db_path=db, user_id="alvi"))
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/awaken", params={"agent_id": "__shared__"})
    assert resp.status_code == 400


async def test_mcp_awaken_tool(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    service = MemoryService(AutoAgentRepository(db, user_id="alvi"), user_id="alvi")
    mcp = build_mcp(service)
    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        assert "awaken" in tools
        result = await client.call_tool("awaken", {"domain": "meta"})
    data = getattr(result, "data", None)
    assert data is not None
    assert data["agent_id"] == "meta"
    assert data["identity"][0]["content"] == "I am meta"
