"""MCP face â€” full tool surface (SP-3 Step 3.1).

In-process fastmcp Client over a MemoryService on a seeded temp DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from munnin.content.loader import ContentLoader
from tests.conftest import mcp_for, seed_agent

CF = Path(__file__).resolve().parents[2] / "control-files"


def _mcp(tmp_path: Path):
    # The face now runs over a per-tenant factory, which wires the **real** repository â€”
    # so the agent these tools write to has to exist, where the auto-creating double used
    # to invent it. Seeding it explicitly is the honest version of that precondition.
    db = tmp_path / "m.db"
    seed_agent(db, "meta")
    return mcp_for(db)


def _mcp_content(tmp_path: Path):
    db = tmp_path / "m.db"
    seed_agent(db, "meta")
    return mcp_for(db, content=ContentLoader(CF))


def _ver(resource: str) -> str:
    """The live stamp of a template â€” what a well-behaved writer declares."""
    return ContentLoader(CF).template_version(resource)


async def test_tool_surface_present(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        names = {t.name for t in await client.list_tools()}
    assert {
        "awaken", "insert", "edit", "append", "prepend", "multi_edit",
        "get", "query", "search", "archive", "soft_delete",
        "archive_memories", "unarchive",
    } <= names


async def test_insert_get_round_trip(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        ins = await client.call_tool(
            "insert",
            {
                "content_summary": "a one-line summary of this record",
                "agent_id": "meta", "record_type": "episode", "content": "body", "uuid": "e1"},
        )
        assert ins.data["uuid"] == "e1"
        got = await client.call_tool("get", {"uuid": "e1"})
        assert got.data["content"] == "body"


async def test_edit_archive_search(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool("insert", {
            "content_summary": "a one-line summary of this record",
            "agent_id": "meta", "record_type": "knowledge",
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
        await client.call_tool("insert", {
            "content_summary": "a one-line summary of this record",
            "agent_id": "meta", "record_type": "episode",
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
        await client.call_tool("insert", {
            "content_summary": "a one-line summary of this record",
            "agent_id": "meta", "record_type": "knowledge",
                                          "content": "x", "uuid": "k1"})
        await client.call_tool("soft_delete", {"uuid": "k1"})
        got = await client.call_tool("get", {"uuid": "k1"})
        assert got.data is None


async def test_insert_matching_template_version_round_trip(tmp_path: Path) -> None:
    async with Client(_mcp_content(tmp_path)) as client:
        ins = await client.call_tool(
            "insert",
            {
                "content_summary": "a one-line summary of this record",
                "agent_id": "meta", "record_type": "episode", "content": "body", "uuid": "e1",
             "template_version": _ver("episodic-entry-template")},
        )
        assert ins.data["uuid"] == "e1"


async def test_insert_without_template_version_is_refused(tmp_path: Path) -> None:
    async with Client(_mcp_content(tmp_path)) as client:
        with pytest.raises(ToolError, match="template_version is required"):
            await client.call_tool(
                "insert",
                {
                    "content_summary": "a one-line summary of this record",
                    "agent_id": "meta", "record_type": "episode", "content": "x"},
            )


async def test_insert_stale_template_version_is_refused(tmp_path: Path) -> None:
    async with Client(_mcp_content(tmp_path)) as client:
        with pytest.raises(ToolError, match="stale template"):
            await client.call_tool(
                "insert",
                {
                    "content_summary": "a one-line summary of this record",
                    "agent_id": "meta", "record_type": "episode", "content": "x",
                 "template_version": "2000-01-01-00-00"},
            )


async def test_insert_ungated_type_needs_no_version(tmp_path: Path) -> None:
    async with Client(_mcp_content(tmp_path)) as client:
        ins = await client.call_tool(
            "insert",
            {
                "content_summary": "a one-line summary of this record",
                "agent_id": "meta", "record_type": "identity", "title": "Agent Identity",
             "content": "**Name**: Claude Meta", "uuid": "i1"},
        )
        assert ins.data["uuid"] == "i1"


async def test_edit_metadata_omits_clears_and_empties(tmp_path: Path) -> None:
    """A field left out keeps its value, `clearing` removes one, `tags=[]` empties the
    list, and the body comes back unchanged because it is never part of the write."""
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool("insert", {
            "content_summary": "first summary",
            "agent_id": "meta", "record_type": "knowledge", "content": "the body",
            "uuid": "k1", "title": "before", "tags": ["a"], "project": "hermod-server"})
        out = await client.call_tool(
            "edit_metadata", {"uuid": "k1", "content_summary": "second summary"})
        assert out.data["content_summary"] == "second summary"
        assert out.data["content"] == "the body"
        assert out.data["title"] == "before"  # omitted, so untouched
        assert out.data["tags"] == ["a"]
        cleared = await client.call_tool(
            "edit_metadata", {"uuid": "k1", "clearing": ["project"], "tags": []})
        assert cleared.data["project"] is None
        assert cleared.data["tags"] == []
        with pytest.raises(ToolError, match="nothing to change"):
            await client.call_tool("edit_metadata", {"uuid": "k1"})
        with pytest.raises(ToolError, match="blank title"):
            await client.call_tool("edit_metadata", {"uuid": "k1", "title": "  "})


async def test_archive_memories_defaults_to_a_dry_run(tmp_path: Path) -> None:
    """The tool's own default must be the safe one: a scan that writes nothing."""
    async with Client(_mcp(tmp_path)) as client:
        await client.call_tool(
            "insert",
            {
                "content_summary": "a one-line summary of this record",
                "agent_id": "meta", "record_type": "episode", "content": "body",
                "uuid": "e1", "title": "proj-theme", "project": "proj",
            },
        )
        out = await client.call_tool("archive_memories", {"agent_id": "meta"})
        assert out.data["applied"] is False
        assert out.data["archived"] == []
        assert set(out.data) >= {"auto", "ask", "protected"}
        got = await client.call_tool("get", {"uuid": "e1"})
        assert got.data["archived_date"] is None


async def test_summary_length_limit_over_mcp(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        args = {
            "agent_id": "meta", "record_type": "knowledge", "content": "body",
            "uuid": "bounded-summary", "content_summary": "界" * 1000,
        }
        inserted = await client.call_tool("insert", args)
        assert inserted.data["content_summary"] == "界" * 1000
        for tool, fields in (
            ("insert", {**args, "content_summary": "界" * 1001}),
            ("edit_metadata", {
                "uuid": "bounded-summary", "content_summary": "界" * 1001,
                "title": "must not change",
            }),
        ):
            with pytest.raises(
                ToolError, match="at most 1000 characters; received 1001 characters",
            ):
                await client.call_tool(tool, fields)
        stored = (await client.call_tool("get", {"uuid": "bounded-summary"})).data
        assert stored["content_summary"] == "界" * 1000
        assert stored["title"] is None
        updated = await client.call_tool("edit_metadata", {
            "uuid": "bounded-summary", "content_summary": "😀" * 1000,
        })
        assert updated.data["content_summary"] == "😀" * 1000
        tools = {tool.name: tool for tool in await client.list_tools()}
        for name in ("insert", "edit_metadata"):
            assert "1000 Unicode characters" in tools[name].inputSchema["properties"][
                "content_summary"
            ]["description"]
