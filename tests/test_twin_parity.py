"""Twin parity (SP-3 Step 4.2) — both adapters go through one MemoryService core,
so the same op over the same DB yields equivalent serialized records.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastmcp import Client
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.app import build_app
from munnin.business_services.memory_service import MemoryService
from munnin.configuration.config import Config
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _mcp(db: Path):
    return build_mcp(MemoryService(SqliteMemoryRepository(db, user_id="alvi"), user_id="alvi"))


def _http(db: Path) -> httpx.AsyncClient:
    app = build_app(Config(db_path=db, user_id="alvi"))
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_insert_http_get_mcp(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    async with _http(db) as http:
        http_rec = (await http.post("/api/insert", json={
            "agent_id": "meta", "record_type": "episode", "content": "twin body", "uuid": "p1",
        })).json()
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("get", {"uuid": "p1"})).data
    assert http_rec == mcp_rec


async def test_insert_mcp_get_http(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("insert", {
            "agent_id": "meta", "record_type": "knowledge", "content": "twin2", "uuid": "p2",
        })).data
    async with _http(db) as http:
        http_rec = (await http.get("/api/record/p2")).json()
    assert mcp_rec == http_rec
