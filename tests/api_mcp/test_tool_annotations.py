"""Every tool declares what it does to the store.

A client reads these before it lets a tool run — a read-only tool needs no confirmation,
a destructive one earns a prompt — so a tool with no hints is a tool the client has to
guess about. The set below is the decision, pinned: adding a tool without placing it
here is what this file refuses.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client

from munnin.content.loader import ContentLoader
from tests.conftest import mcp_for

CF = Path(__file__).resolve().parents[2] / "control-files"

READ_ONLY = {
    "ping",
    "help",
    "awaken",
    "coding_reasoning",
    "get",
    "query",
    "search",
    "list_agents",
    "list_procedures",
    "read_procedure",
    "list_resources",
    "read_resource",
    "permanent_layer",
    "list_tenants",
    "list_members",
}
ADDITIVE = {
    "insert",
    "create_agent",
    "append",
    "prepend",
    "use_tenant",
    "create_invite",
    "redeem_invite",
}
DESTRUCTIVE = {
    "edit",
    "edit_metadata",
    "multi_edit",
    "archive",
    "soft_delete",
    "revoke_invite",
    "revoke_member",
    "archive_memories",
    "unarchive",
}
IDEMPOTENT_DESTRUCTIVE = {"archive", "soft_delete", "archive_memories", "unarchive"}


async def _tools(tmp_path: Path):
    async with Client(mcp_for(tmp_path / "m.db", content=ContentLoader(CF))) as client:
        return {t.name: t for t in await client.list_tools()}


async def test_every_tool_has_a_title_and_a_read_only_hint(tmp_path: Path) -> None:
    tools = await _tools(tmp_path)
    assert set(tools) == READ_ONLY | ADDITIVE | DESTRUCTIVE  # the whole surface is placed
    for name, tool in tools.items():
        assert tool.title, name
        assert tool.annotations is not None, name
        assert tool.annotations.readOnlyHint is not None, name
        assert tool.annotations.openWorldHint is False, name  # nothing reaches past the store


async def test_the_hints_say_what_each_tool_does(tmp_path: Path) -> None:
    tools = await _tools(tmp_path)
    for name in READ_ONLY:
        assert tools[name].annotations.readOnlyHint is True, name
    for name in ADDITIVE | DESTRUCTIVE:
        a = tools[name].annotations
        assert a.readOnlyHint is False, name
        # the spec defaults destructiveHint to true, so the additive writes must say so
        assert a.destructiveHint is (name in DESTRUCTIVE), name
    for name in IDEMPOTENT_DESTRUCTIVE:
        assert tools[name].annotations.idempotentHint is True, name


async def test_titles_are_human_names_not_tool_names(tmp_path: Path) -> None:
    tools = await _tools(tmp_path)
    for name, tool in tools.items():
        assert tool.title != name, name
        assert " " in tool.title, name  # a phrase a picker can show, not an identifier


async def test_every_tool_and_parameter_explains_its_contract(tmp_path: Path) -> None:
    tools = await _tools(tmp_path)
    for name, tool in tools.items():
        assert tool.description, name
        for parameter, schema in tool.inputSchema.get("properties", {}).items():
            assert schema.get("description"), (name, parameter)

    get_schema = tools["get"].inputSchema
    assert get_schema["required"] == ["uuid"]
    assert get_schema["properties"]["cursor"]["default"] is None
    assert get_schema["properties"]["limit"]["default"] is None
    assert "same record" in get_schema["properties"]["cursor"]["description"]
    assert "6 hex" in get_schema["properties"]["uuid"]["description"]
    assert tools["query"].inputSchema["properties"]["include_archived"]["default"] is False
    assert tools["search"].inputSchema["properties"]["include_archived"]["default"] is True
    assert tools["archive_memories"].inputSchema["properties"]["apply"]["default"] is False
    assert "whole-tenant access" in tools["create_invite"].description
    assert "every client" in tools["use_tenant"].description
    assert "no undelete tool" in tools["soft_delete"].description
    assert "upsert key" in tools["insert"].description
