"""Every declared prompt argument must reach its body; new procedures need no registry edit."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastmcp import Client

from munnin.content.loader import ContentLoader
from tests.conftest import mcp_for

CF = Path(__file__).resolve().parents[2] / "control-files"
LOADER = ContentLoader(CF)
MARKER = "argument-probe: preserve spaces and punctuation!"


@pytest.fixture(scope="module")
def prompt_server(tmp_path_factory):
    return mcp_for(tmp_path_factory.mktemp("prompt-arguments") / "memory.db", content=LOADER)


@pytest.mark.parametrize("name", LOADER.list_prompts())
async def test_every_served_prompt_preserves_its_arguments(prompt_server, name: str) -> None:
    authored = LOADER.get_prompt(name)
    async with Client(prompt_server) as client:
        prompts = {prompt.name: prompt for prompt in await client.list_prompts()}
        arguments = prompts[name].arguments or []
        plain = await client.get_prompt(name)
        assert plain.messages[0].content.text == authored
        if "$ARGUMENTS" not in authored:
            assert not arguments, f"{name} advertises an argument its body cannot use"
            return
        assert len(arguments) == 1, f"{name} has a placeholder but no argument slot"
        argument = arguments[0]
        assert not argument.required
        filled = await client.get_prompt(name, {argument.name: MARKER})
        expected = authored.replace("$ARGUMENTS", MARKER)
        assert filled.messages[0].content.text == expected
        assert MARKER in expected
        through_tool = await client.call_tool("read_procedure", {"name": name, "argument": MARKER})
        assert through_tool.data["content"] == expected


def _synthetic_content(tmp_path: Path, name: str, body: str) -> ContentLoader:
    root = tmp_path / "content"
    # Reuse the framework's real discovery/inlining mechanics, not a mock command inventory.
    for relative in ("procedures/command_set.py", "procedures/components/inline.py"):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CF / relative, destination)
    (root / "procedures" / f"{name}.md").write_text(body, encoding="utf-8", newline="\n")
    return ContentLoader(root)


async def test_a_new_procedure_declares_and_binds_input_without_a_map_entry(tmp_path: Path) -> None:
    name = "new-unlisted-procedure"
    authored = "# New Procedure\n\n## Arguments\n\n$ARGUMENTS\n"
    loader = _synthetic_content(tmp_path, name, authored)
    async with Client(mcp_for(tmp_path / "memory.db", content=loader)) as client:
        prompt = (await client.list_prompts())[0]
        assert len(prompt.arguments) == 1
        assert prompt.arguments[0].name == "argument"
        assert not prompt.arguments[0].required
        filled = await client.get_prompt(name, {"argument": MARKER})
    assert filled.messages[0].content.text == authored.replace("$ARGUMENTS", MARKER)


async def test_a_parameterless_source_does_not_advertise_a_stale_named_slot(tmp_path: Path) -> None:
    # Even a name in the compatibility map cannot declare input absent from its source.
    name = "awaken-agent"
    authored = "# Awaken Agent\n\nA procedure without an input placeholder.\n"
    loader = _synthetic_content(tmp_path, name, authored)
    async with Client(mcp_for(tmp_path / "memory.db", content=loader)) as client:
        prompt = (await client.list_prompts())[0]
        assert not prompt.arguments
        plain = await client.get_prompt(name)
    assert plain.messages[0].content.text == authored


def test_existing_named_slots_keep_their_names() -> None:
    expected = {
        "update-episodic": "mode",
        "add-reasoning": "context",
        "update-emotional": "moment_type",
        "update-knowledge": "context",
        "load-episodic": "keyword",
        "load-knowledge": "keyword",
        "archive-old-memories": "scope",
        "update-memory": "mode",
        "wrap-up": "mode",
        "create-agent": "domain",
        "list-agents": "keyword",
        "awaken-agent": "domain",
        "anchor-memory": "harness",
        "register-core-access": "harness",
        "tenant-sharing": "request",
    }
    for name, argument in expected.items():
        assert LOADER.argument_prompt(name)[0] == argument
