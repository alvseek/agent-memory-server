"""Guarded editor calls through authenticated HTTP and MCP with real SQLite state."""

import uuid

import httpx
import pytest
from fastmcp.exceptions import ToolError

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import (
    auth_for,
    bearer,
    mcp_client_for,
    running,
    seed_agent,
    seed_login,
    token_for,
)


def fixture(tmp_path):
    db = tmp_path / "memory.db"
    app = build_app(Config(db_path=db, content_root=tmp_path / "no-content", user_id="alvi"),
                    auth=auth_for("alvi", "roy"))
    for user in ("alvi", "roy"):
        seed_login(db, user)
    seed_agent(db, "meta")
    repo = SqliteMemoryRepository(db, user_id="alvi")
    identity = uuid.uuid4().hex
    repo.insert(MemoryRecord(uuid=identity, user_id="", agent_id="meta",
                             record_type=RecordType.identity, full_content="private body"))
    return app, repo, identity


def guards(context):
    return {"expected_revision": context["revision"], "expected_tenant": context["tenant"]}


async def invite_guest(http):
    invite = (await http.post("/api/invites", json={}, headers=bearer("alvi"))).json()
    joined = await http.post("/api/invites/redeem", json={"code": invite["code"]},
                             headers=bearer("roy"))
    assert joined.status_code == 200
    selected = await http.post("/api/tenants/use", json={"tenant": "alvi"},
                               headers=bearer("roy"))
    assert selected.status_code == 200


async def test_http_owner_guest_conflicts_and_revocation(tmp_path):
    app, repo, identity = fixture(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url="http://test", headers=bearer("alvi")) as http:
        bare = (await http.get(f"/api/record/{identity}")).json()
        assert "edit_context" not in bare
        loaded = (await http.get(f"/api/record/{identity}",
                                params={"include_edit_context": True})).json()
        context = loaded["edit_context"]
        saved = await http.post("/api/edit", json={
            "uuid": identity, "old_string": "private body", "new_string": "edited body",
            **guards(context),
        })
        assert saved.status_code == 200
        assert "content" not in saved.json() and "edit_context" in saved.json()
        stale = await http.post("/api/edit-metadata",
                                json={"uuid": identity, "title": "lost", **guards(context)})
        assert stale.status_code == 409 and "private body" not in stale.text
        partial = await http.post("/api/edit", json={
            "uuid": identity, "old_string": "edited body", "new_string": "lost",
            "expected_revision": context["revision"],
        })
        assert partial.status_code == 400
        await invite_guest(http)
        guest = (await http.get(f"/api/record/{identity}",
                                params={"include_edit_context": True},
                                headers=bearer("roy"))).json()
        guest_save = await http.post("/api/edit-metadata", json={
            "uuid": identity, "title": "Guest title", **guards(guest["edit_context"]),
        }, headers=bearer("roy"))
        assert guest_save.status_code == 200 and "content" not in guest_save.json()
        context = guest_save.json()["edit_context"]
        assert (await http.post("/api/members/revoke", json={"member": "roy"})).status_code == 200
        refused = await http.post("/api/edit-metadata", json={
            "uuid": identity, "title": "revoked", **guards(context),
        }, headers=bearer("roy"))
        assert refused.status_code == 403
        await http.post("/api/tenants/use", json={"tenant": None}, headers=bearer("roy"))
        changed_account = await http.post("/api/edit-metadata", json={
            "uuid": identity, "title": "wrong account", **guards(context),
        }, headers=bearer("roy"))
        assert changed_account.status_code == 409
        assert repo.get(identity).title == "Guest title"
        assert repo.get(identity).full_content == "edited body"


async def test_mcp_schema_guards_and_guest_authorization(tmp_path):
    app, repo, identity = fixture(tmp_path)
    async with running(app), mcp_client_for(app, token_for("alvi")) as owner:
        tools = {tool.name: tool for tool in await owner.list_tools()}
        assert "include_edit_context" in tools["get_memory"].inputSchema["properties"]
        for name in ("edit_memory_body", "edit_memory_metadata"):
            assert {"expected_revision", "expected_tenant"} <= set(
                tools[name].inputSchema["properties"]
            )
        loaded = (await owner.call_tool("get_memory", {
            "uuid": identity, "include_edit_context": True,
        })).data
        bare = (await owner.call_tool("get_memory", {"uuid": identity})).data
        assert "edit_context" not in bare
        saved = (await owner.call_tool("edit_memory_body", {
            "uuid": identity, "old_string": "private body", "new_string": "edited body",
            **guards(loaded["edit_context"]),
        })).data
        assert "content" not in saved and "edit_context" in saved
        with pytest.raises(ToolError, match="together"):
            await owner.call_tool("edit_memory_body", {
                "uuid": identity, "old_string": "edited body", "new_string": "lost",
                "expected_revision": saved["edit_context"]["revision"],
            })
        with pytest.raises(ToolError, match="record changed"):
            await owner.call_tool("edit_memory_metadata", {
                "uuid": identity, "title": "lost", **guards(loaded["edit_context"]),
            })
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://test") as http:
            await invite_guest(http)
        async with mcp_client_for(app, token_for("roy")) as guest:
            fresh = (await guest.call_tool("get_memory", {
                "uuid": identity, "include_edit_context": True,
            })).data
            saved = (await guest.call_tool("edit_memory_metadata", {
                "uuid": identity, "title": "Guest", **guards(fresh["edit_context"]),
            })).data
            await owner.call_tool("revoke_member", {"member": "roy"})
            with pytest.raises(ToolError, match="revoked"):
                await guest.call_tool("edit_memory_metadata", {
                    "uuid": identity, "title": "lost", **guards(saved["edit_context"]),
                })
            await guest.call_tool("use_tenant", {"tenant": None})
            with pytest.raises(ToolError, match="account changed"):
                await guest.call_tool("edit_memory_metadata", {
                    "uuid": identity, "title": "wrong account", **guards(saved["edit_context"]),
                })
        assert repo.get(identity).title == "Guest"
