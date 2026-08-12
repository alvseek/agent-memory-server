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
from munnin.content.loader import ContentLoader
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

CF = Path(__file__).resolve().parents[1] / "control-files"


def _mcp(db: Path):
    return build_mcp(MemoryService(SqliteMemoryRepository(db, user_id="alvi"), user_id="alvi"))


def _mcp_content(db: Path):
    return build_mcp(
        MemoryService(SqliteMemoryRepository(db, user_id="alvi"), user_id="alvi"),
        ContentLoader(CF),
    )


def _http(db: Path) -> httpx.AsyncClient:
    app = build_app(Config(db_path=db, content_root=CF, user_id="alvi"))
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


# --- content surface parity (SP-5): both faces serve the same composed prompts/resources ---


async def test_prompt_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    expected = ContentLoader(CF).get_prompt("update-episodic")
    async with Client(_mcp_content(db)) as mcp:
        mcp_txt = (await mcp.get_prompt("update-episodic")).messages[0].content.text
    async with _http(db) as http:
        http_txt = (await http.get("/api/prompts/update-episodic")).json()["content"]
    assert mcp_txt == expected == http_txt


async def test_resource_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    expected = ContentLoader(CF).get_resource("episodic-entry-template")
    async with Client(_mcp_content(db)) as mcp:
        mcp_txt = (await mcp.read_resource("resource://templates/episodic-entry-template"))[0].text
    async with _http(db) as http:
        http_txt = (await http.get("/api/resources/episodic-entry-template")).json()["content"]
    assert mcp_txt == expected == http_txt


async def test_prompt_list_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    async with Client(_mcp_content(db)) as mcp:
        mcp_names = sorted(p.name for p in await mcp.list_prompts())
    async with _http(db) as http:
        http_names = sorted((await http.get("/api/prompts")).json()["prompts"])
    assert mcp_names == http_names
    assert len(http_names) == 9
