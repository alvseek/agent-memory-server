"""The membership tools, driven through the real MCP face.

Every other test of these rules goes through the service directly. This one exists for the
two things only the face can prove: that the tools are listed with the arguments they
declare, and that a refusal arrives as a tool error carrying the message a person reads,
rather than a traceback or a success-shaped empty result.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from munnin.data_entities.identity import UserIdentity
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sharing_repository import SqliteSharingRepository
from tests.conftest import TEST_ISSUER, mcp_for

TOOLS = {
    "list_tenants",
    "use_tenant",
    "list_members",
    "create_invite",
    "revoke_invite",
    "redeem_invite",
    "revoke_member",
}


def _seed_second_person(db: Path, user_id: str = "roy") -> None:
    """A second account, with a login that maps to it, exactly as a real sign-in would."""
    identity = SqliteIdentityRepository(db)
    identity.ensure_account(_account(user_id))
    identity.link_identity(UserIdentity(iss=TEST_ISSUER, sub=user_id, user_id=user_id))


def _account(user_id: str):
    from munnin.data_entities.identity import Account

    return Account(user_id=user_id)


async def test_the_membership_tools_are_served(tmp_path: Path) -> None:
    async with Client(mcp_for(tmp_path / "m.db")) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert TOOLS <= set(tools)
    for name in TOOLS:
        assert tools[name].title, name


async def test_the_whole_flow_runs_through_the_face(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed_second_person(db)
    sharing = SqliteSharingRepository(db)

    async with Client(mcp_for(db, user_id="alvi")) as alvi:
        invite = await alvi.call_tool("create_invite", {"days": 7})
        code = invite.data["code"]
        assert invite.data["tenant_user_id"] == "alvi"

        # The owner sees themselves, and nobody else yet.
        members = await alvi.call_tool("list_members", {})
        assert [m["user_id"] for m in members.data] == ["alvi"]

    async with Client(mcp_for(db, user_id="roy")) as roy:
        joined = await roy.call_tool("redeem_invite", {"code": code})
        assert joined.data == {"tenant_user_id": "alvi", "label": None, "role": "guest"}

        tenants = await roy.call_tool("list_tenants", {})
        assert [(t["user_id"], t["role"], t["active"]) for t in tenants.data] == [
            ("roy", "owner", True),
            ("alvi", "guest", False),
        ]

        switched = await roy.call_tool("use_tenant", {"tenant": "alvi"})
        assert switched.data["user_id"] == "alvi"
        assert sharing.find_active("roy") == "alvi"

        members = await roy.call_tool("list_members", {})
        assert [m["user_id"] for m in members.data] == ["alvi", "roy"]
        assert sharing.find_access("alvi", "roy").live is True  # type: ignore[union-attr]

    async with Client(mcp_for(db, user_id="alvi")) as alvi:
        await alvi.call_tool("revoke_member", {"member": "roy"})

    assert sharing.find_access("alvi", "roy").live is False  # type: ignore[union-attr]


async def test_a_guest_cannot_grant_while_acting_in_somebody_elses_tenant(
    tmp_path: Path,
) -> None:
    db = tmp_path / "m.db"
    _seed_second_person(db, "roy")
    _seed_second_person(db, "alvi")
    sharing = SqliteSharingRepository(db)
    sharing.grant("alvi", "roy")
    sharing.set_active("roy", "alvi")

    async with Client(mcp_for(db, user_id="roy")) as roy:
        with pytest.raises(ToolError, match="only the owner"):
            await roy.call_tool("create_invite", {})
        with pytest.raises(ToolError, match="only the owner"):
            await roy.call_tool("revoke_member", {"member": "alvi"})


async def test_a_used_or_unknown_code_is_a_tool_error_not_a_crash(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed_second_person(db)
    async with Client(mcp_for(db, user_id="roy")) as roy:
        with pytest.raises(ToolError, match="does not exist"):
            await roy.call_tool("redeem_invite", {"code": "never-existed"})
