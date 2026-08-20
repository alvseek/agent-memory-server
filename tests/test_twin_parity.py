"""Twin parity (SP-3 Step 4.2) — both adapters go through one MemoryService core,
so the same op over the same DB yields equivalent serialized records.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.app import build_app
from munnin.business_services.memory_service import MemoryService
from munnin.configuration.config import Config
from munnin.content.loader import ContentLoader
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_agent

CF = Path(__file__).resolve().parents[1] / "control-files"


def _mcp(db: Path):
    # The **real** repository on both sides. The auto-creating double would have made
    # the MCP face conjure agent rows the HTTP face refuses to, which is precisely the
    # kind of asymmetry a parity test exists to catch.
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
    seed_agent(db, "meta")
    async with _http(db) as http:
        http_rec = (await http.post("/api/insert", json={
            "agent_id": "meta", "record_type": "episode", "content": "twin body", "uuid": "p1",
        })).json()
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("get", {"uuid": "p1"})).data
    assert http_rec == mcp_rec


async def test_insert_mcp_get_http(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    seed_agent(db, "meta")
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("insert", {
            "agent_id": "meta", "record_type": "knowledge", "content": "twin2", "uuid": "p2",
        })).data
    async with _http(db) as http:
        http_rec = (await http.get("/api/record/p2")).json()
    assert mcp_rec == http_rec


async def test_append_http_then_multi_edit_mcp_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    seed_agent(db, "meta")
    async with _http(db) as http:
        await http.post("/api/insert", json={
            "agent_id": "meta", "record_type": "episode", "content": "one", "uuid": "p1",
        })
        http_rec = (await http.post("/api/append", json={"uuid": "p1", "text": " two"})).json()
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("multi_edit", {"uuid": "p1", "edits": [
            {"old_string": "one", "new_string": "1"},
        ]})).data
    # both ops went through the same core over the same DB; final read is consistent
    assert http_rec["content"] == "one two"
    assert mcp_rec["content"] == "1 two"


async def test_list_agents_parity(tmp_path: Path) -> None:
    """The same expected roster as before the entity landed, reached a different way:
    name and role are columns set once at creation, not lines parsed on every call."""
    db = tmp_path / "m.db"
    seed_agent(db, "meta", name="Claude Meta", role="Meta Agent for Alvi")
    seed_agent(db, "linux")  # a real agent with no identity recorded
    async with _http(db) as http:
        http_roster = (await http.get("/api/agents")).json()
    async with Client(_mcp(db)) as mcp:
        mcp_roster = (await mcp.call_tool("list_agents", {})).data
    assert http_roster == mcp_roster
    assert http_roster == [
        {"agent_id": "linux", "name": None, "role": None},
        {"agent_id": "meta", "name": "Claude Meta", "role": "Meta Agent for Alvi"},
    ]


async def test_shared_insert_parity(tmp_path: Path) -> None:
    """A fleet insert must behave identically on both faces, and neither may need an
    agent: `scope="shared"` is the whole reason the sentinel could go."""
    db = tmp_path / "m.db"  # deliberately no agent anywhere in this store
    async with _http(db) as http:
        http_rec = (await http.post("/api/insert", json={
            "scope": "shared", "record_type": "reasoning",
            "content": "fleet pattern", "uuid": "s1",
        })).json()
    async with Client(_mcp(db)) as mcp:
        mcp_rec = (await mcp.call_tool("get", {"uuid": "s1"})).data
    assert http_rec == mcp_rec
    assert "agent_id" not in http_rec


async def test_shared_insert_contradiction_parity(tmp_path: Path) -> None:
    """Both faces refuse the same contradiction — HTTP as a 400, MCP as a raised error —
    rather than one of them quietly picking a table."""
    db = tmp_path / "m.db"
    seed_agent(db, "meta")
    async with _http(db) as http:
        r = await http.post("/api/insert", json={
            "scope": "shared", "agent_id": "meta",
            "record_type": "reasoning", "content": "x",
        })
    assert r.status_code == 400
    assert "no agent_id" in r.json()["detail"]
    async with Client(_mcp(db)) as mcp:
        with pytest.raises(ToolError, match="no agent_id"):
            await mcp.call_tool("insert", {
                "scope": "shared", "agent_id": "meta",
                "record_type": "reasoning", "content": "x",
            })


# --- content surface parity (SP-5): both faces serve the same composed prompts/resources ---


async def test_prompt_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    expected = ContentLoader(CF).get_prompt("update-episodic")
    async with Client(_mcp_content(db)) as mcp:
        mcp_txt = (await mcp.get_prompt("update-episodic")).messages[0].content.text
    async with _http(db) as http:
        http_txt = (await http.get("/api/prompts/update-episodic")).text
    assert mcp_txt == expected == http_txt


async def test_resource_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    expected = ContentLoader(CF).get_resource("episodic-entry-template")
    async with Client(_mcp_content(db)) as mcp:
        mcp_txt = (await mcp.read_resource("resource://templates/episodic-entry-template"))[0].text
    async with _http(db) as http:
        http_txt = (await http.get("/api/resources/episodic-entry-template")).text
    assert mcp_txt == expected == http_txt


async def test_prompt_list_parity(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    async with Client(_mcp_content(db)) as mcp:
        mcp_names = sorted(p.name for p in await mcp.list_prompts())
    async with _http(db) as http:
        http_names = sorted((await http.get("/api/prompts")).json()["prompts"])
    assert mcp_names == http_names
    assert len(http_names) == 11
    assert "list-agents" in http_names


async def test_create_agent_parity(tmp_path: Path) -> None:
    """Creation over both faces. `/create-agent` is a served procedure agents follow on
    either transport, so a face that could not create one would leave the command working
    on paper and broken in practice."""
    db = tmp_path / "m.db"
    async with _http(db) as http:
        made = (await http.post("/api/agents", json={
            "agent_id": "newborn", "name": "Claude Newborn", "role": "Test Agent",
        })).json()
    assert made == {
        "agent_id": "newborn", "name": "Claude Newborn", "role": "Test Agent", "uuid": None,
    }
    async with Client(_mcp(db)) as mcp:
        roster = (await mcp.call_tool("list_agents", {})).data
    assert roster == [{"agent_id": "newborn", "name": "Claude Newborn", "role": "Test Agent"}]


async def test_create_agent_duplicate_refused_on_both_faces(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    seed_agent(db, "meta", name="Claude Meta")
    async with _http(db) as http:
        r = await http.post("/api/agents", json={"agent_id": "meta", "name": "Impostor"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"]
    async with Client(_mcp(db)) as mcp:
        with pytest.raises(ToolError, match="already exists"):
            await mcp.call_tool("create_agent", {"agent_id": "meta", "name": "Impostor"})
        roster = (await mcp.call_tool("list_agents", {})).data
    assert roster[0]["name"] == "Claude Meta"  # neither face overwrote it


async def test_create_agent_then_insert_over_the_faces(tmp_path: Path) -> None:
    """The order `/create-agent` actually follows: make the agent, then persist identity."""
    db = tmp_path / "m.db"
    async with Client(_mcp(db)) as mcp:
        await mcp.call_tool("create_agent", {"agent_id": "newborn", "name": "Claude Newborn"})
    async with _http(db) as http:
        r = await http.post("/api/insert", json={
            "agent_id": "newborn", "record_type": "identity",
            "title": "Agent Identity", "content": "**Name**: Claude Newborn", "uuid": "i1",
        })
    assert r.status_code == 200
    assert r.json()["agent_id"] == "newborn"


async def test_tool_surface_is_the_documented_size(tmp_path: Path) -> None:
    """Pinned deliberately. Tool definitions are permanent-layer — they ship on every
    single call — so the surface growing is a cost decision, not an implementation
    detail, and it should not be possible to add one without this test saying so."""
    async with Client(_mcp(tmp_path / "m.db")) as mcp:
        names = sorted(t.name for t in await mcp.list_tools())
    assert len(names) == 14
    assert names == [
        "append", "archive", "awaken", "create_agent", "edit", "get", "insert",
        "list_agents", "multi_edit", "ping", "prepend", "query", "search", "soft_delete",
    ]
