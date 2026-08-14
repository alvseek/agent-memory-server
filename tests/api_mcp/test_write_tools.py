"""MCP face — full tool surface (SP-3 Step 3.1).

In-process fastmcp Client over a MemoryService on a seeded temp DB.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client

from munnin.api_mcp.server import build_mcp
from munnin.business_services.memory_service import MemoryService
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _mcp(tmp_path: Path):
    repo = SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi")
    return build_mcp(MemoryService(repo, user_id="alvi"))


async def test_tool_surface_present(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        names = {t.name for t in await client.list_tools()}
    assert {
        "awaken", "insert", "edit", "append", "prepend", "multi_edit",
        "get", "query", "search", "archive", "soft_delete",
    } <= names


async def test_insert_get_round_trip(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        ins = await client.call_tool(
            "insert",
            {"agent_id": "meta", "record_type": "episode", "content": "body", "uuid": "e1"},
        )
        assert ins.data["uuid"] == "e1"
        got = await client.call_tool("get", {"uuid": "e1"})
        assert got.data["content"] == "body"


async def test_edit_archive_search(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool("insert", {"agent_id": "meta", "record_type": "knowledge",
                                          "content": "hello world token", "uuid": "k1"})
        ed = await client.call_tool("edit", {"uuid": "k1", "old_string": "world",
                                             "new_string": "there"})
        assert ed.data["content"] == "hello there token"
        await client.call_tool("archive", {"uuid": "k1"})
        assert (await client.call_tool("query", {"agent_id": "meta"})).data == []
        hits = await client.call_tool("search", {"text": "token"})
        assert [r["uuid"] for r in hits.data] == ["k1"]


async def test_append_prepend_multi_edit_tools(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool("insert", {"agent_id": "meta", "record_type": "episode",
                                          "content": "mid", "uuid": "e1"})
        ap = await client.call_tool("append", {"uuid": "e1", "text": " end"})
        assert ap.data["content"] == "mid end"
        pp = await client.call_tool("prepend", {"uuid": "e1", "text": "start "})
        assert pp.data["content"] == "start mid end"
        me = await client.call_tool("multi_edit", {"uuid": "e1", "edits": [
            {"old_string": "start", "new_string": "S"},
            {"old_string": "end", "new_string": "E"},
        ]})
        assert me.data["content"] == "S mid E"


async def test_soft_delete(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool("insert", {"agent_id": "meta", "record_type": "knowledge",
                                          "content": "x", "uuid": "k1"})
        await client.call_tool("soft_delete", {"uuid": "k1"})
        got = await client.call_tool("get", {"uuid": "k1"})
        assert got.data is None
