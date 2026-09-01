"""MCP face — the framework content as tools: list/read procedures and resources.

The Prompt and Resource primitives carry the same content, but a Prompt is user-invoked
and a Resource client-attached; the tools are the door an agent can open itself.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import Client

from munnin.api_mcp.server import INSTRUCTIONS
from munnin.content.loader import ContentLoader
from tests.conftest import mcp_for

CF = Path(__file__).resolve().parents[2] / "control-files"


def _mcp(tmp_path: Path):
    return mcp_for(tmp_path / "m.db", content=ContentLoader(CF))


async def test_content_tools_present_only_with_content(tmp_path: Path) -> None:
    async with Client(mcp_for(tmp_path / "m.db")) as client:
        bare = {t.name for t in await client.list_tools()}
    async with Client(_mcp(tmp_path)) as client:
        full = {t.name for t in await client.list_tools()}
    content_tools = {"list_procedures", "read_procedure", "list_resources", "read_resource"}
    assert not (content_tools & bare)
    assert content_tools <= full
    assert "help" in bare and "help" in full  # the one door that is always there


async def test_initialize_carries_the_instructions(tmp_path: Path) -> None:
    """What a client is told before it calls anything — returned by the handshake itself,
    byte for byte the constant, so a stranger can act with no other reading."""
    async with Client(_mcp(tmp_path)) as client:
        result = client.initialize_result
    assert result is not None
    assert result.instructions == INSTRUCTIONS
    # permanent-layer text, re-sent on every call of every session: a budget, not a manual
    assert len(result.instructions) <= 600


async def test_help_is_the_instructions_plus_the_menu(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        out = (await client.call_tool("help", {})).data
        rows = (await client.call_tool("list_procedures", {})).data
    assert out["instructions"] == INSTRUCTIONS
    assert out["procedures"] == rows  # one row-builder behind both
    assert len(out["procedures"]) == 13


async def test_help_answers_without_served_content(tmp_path: Path) -> None:
    # a server built with no framework content still says what it is; the menu is empty
    async with Client(mcp_for(tmp_path / "m.db")) as client:
        out = (await client.call_tool("help", {})).data
    assert out == {"instructions": INSTRUCTIONS, "procedures": []}


async def test_list_procedures_carries_name_title_and_purpose(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        rows = (await client.call_tool("list_procedures", {})).data
    by_name = {r["name"]: r for r in rows}
    assert len(rows) == 13
    assert by_name["awaken-agent"] == {
        "name": "awaken-agent",
        "title": "Awaken Agent",
        "description": "Load agent memory and activate a domain-specific agent.",
    }
    assert "wait-options" in by_name  # served with no list naming it
    assert "push-memory" not in by_name  # excluded by policy
    # a menu is only readable if its rows differ
    assert len({r["description"] for r in rows}) == 13


async def test_read_procedure_composes_for_the_db_backend(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        out = (await client.call_tool("read_procedure", {"name": "update-episodic"})).data
    assert out["served"] is True
    assert out["name"] == "update-episodic"
    assert "insert(" in out["content"]
    assert "MOVE-TO-TODAY" not in out["content"]  # markdown mechanics never reach the wire


async def test_read_procedure_fills_the_argument(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        bare = (await client.call_tool("read_procedure", {"name": "awaken-agent"})).data
        filled = (
            await client.call_tool(
                "read_procedure", {"name": "awaken-agent", "argument": "software-architect"}
            )
        ).data
    assert "$ARGUMENTS" in bare["content"]
    assert "$ARGUMENTS" not in filled["content"]
    assert "software-architect" in filled["content"]


async def test_awakening_carries_the_resolution_rule(tmp_path: Path) -> None:
    """The rule that turns "execute `/wrap-up`" into read_procedure("wrap-up") rides in the
    awakening procedure's db mechanics — every agent that awakens has it, and no
    markdown-side command ever carries it."""
    async with Client(_mcp(tmp_path)) as client:
        out = (await client.call_tool("read_procedure", {"name": "awaken-agent"})).data
    assert 'read_procedure("<name>")' in out["content"]
    assert 'read_resource("<stem>")' in out["content"]
    assert "list_procedures()" in out["content"]


async def test_unserved_procedure_is_an_answer_not_an_error(tmp_path: Path) -> None:
    # the caller is an agent typing whatever a procedure told it to type: an unknown name
    # gets an answer that points at the listing, not a raised error
    async with Client(_mcp(tmp_path)) as client:
        out = (await client.call_tool("read_procedure", {"name": "high-wizard"})).data
    assert out["served"] is False
    assert out["name"] == "high-wizard"
    assert "list_procedures()" in out["note"]


async def test_resources_as_tools(tmp_path: Path) -> None:
    async with Client(_mcp(tmp_path)) as client:
        rows = (await client.call_tool("list_resources", {})).data
        body = (
            await client.call_tool("read_resource", {"name": "reasoning-pattern-template"})
        ).data
        missing = (
            await client.call_tool("read_resource", {"name": "episodic-memory-template"})
        ).data
    assert {r["name"] for r in rows} == {
        "episodic-entry-template",
        "emotional-moment-template",
        "knowledge-file-template",
        "reasoning-pattern-template",
    }
    assert all(r["title"] and r["description"] for r in rows)
    assert body["served"] is True
    assert "Reasoning Pattern Template" in body["content"]
    # the markdown scaffold is excluded from the resource surface on every door
    assert missing == {
        "served": False,
        "name": "episodic-memory-template",
        "note": (
            "no served resource named 'episodic-memory-template'; "
            "call list_resources() to see what is"
        ),
    }
