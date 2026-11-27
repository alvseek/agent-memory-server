"""Exercise workspace access through the authenticated, mounted service."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastmcp.exceptions import ToolError
from httpx import ASGITransport
from valaskjalf_workspace_access import PostgresWorkspaceAccess

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.data_entities.memory_record import RecordType, SharedRecord
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import (
    TEST_ISSUER,
    auth_for,
    bearer,
    mcp_client_for,
    running,
    seed_login,
    token_for,
)


async def test_authenticated_faces_switch_revoke_and_recover(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    seed_login(db, "alice")
    seed_login(db, "bob")
    for user, uid in (
        ("alice", "aaaaaaaa000000000000000000000001"),
        ("bob", "bbbbbbbb000000000000000000000002"),
    ):
        SqliteMemoryRepository(db, user_id=user).insert_shared(
            SharedRecord(
                uuid=uid,
                user_id=user,
                record_type=RecordType.knowledge,
                title=user,
                full_content=f"{user} secret",
                content_summary=user,
            )
        )
    app = build_app(Config(db_path=db), auth=auth_for("alice", "bob"))
    async with (
        running(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        mcp_client_for(app, token_for("alice")) as mcp,
    ):

        async def read(uid: str):
            return await http.get(f"/api/record/{uid}", headers=bearer("alice"))

        alice = "aaaaaaaa000000000000000000000001"
        bob = "bbbbbbbb000000000000000000000002"
        assert (await read(alice)).json()["content"] == "alice secret"
        invite = (await http.post("/api/invites", json={}, headers=bearer("bob"))).json()
        assert (
            await http.post(
                "/api/invites/redeem", json={"code": invite["code"]}, headers=bearer("alice")
            )
        ).status_code == 200
        assert (
            await http.post("/api/tenants/use", json={"tenant": "bob"}, headers=bearer("alice"))
        ).status_code == 200
        assert (await read(bob)).json()["content"] == "bob secret"
        assert (await mcp.call_tool("get_memory", {"uuid": bob})).data["content"] == "bob secret"
        assert (await read(alice)).status_code == 404
        assert (
            await http.post("/api/members/revoke", json={"member": "alice"}, headers=bearer("bob"))
        ).status_code == 200
        assert (await read(bob)).status_code == 403
        with pytest.raises(ToolError, match="was revoked"):
            await mcp.call_tool("get_memory", {"uuid": bob})
        assert (
            await http.post("/api/tenants/use", json={"tenant": None}, headers=bearer("alice"))
        ).status_code == 200
        assert (await read(alice)).json()["content"] == "alice secret"


async def test_seed_failure_does_not_reject_first_login(tmp_path: Path, monkeypatch) -> None:
    def fail_seed(*args):
        raise RuntimeError("seed failed")

    monkeypatch.setattr("munnin.app.seed_profile", fail_seed)
    app = build_app(Config(db_path=tmp_path / "new.db"), auth=auth_for("alice"))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer("alice")
    ) as http:
        assert (await http.get("/api/agents")).status_code == 200
        assert (await http.get("/api/agents")).status_code == 200


def test_simultaneous_first_logins_leave_one_account(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    repo = SqliteIdentityRepository(db)
    assert repo.find_user_id(TEST_ISSUER, "new") is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.get_or_create_home(TEST_ISSUER, "new"), range(8)))
    assert len({result.user_id for result in results}) == 1
    assert sum(result.created for result in results) == 1
    with repo._conn() as conn:
        assert conn.execute("SELECT count(*) FROM account").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM user_identity").fetchone()[0] == 1


@pytest.mark.postgres
async def test_postgres_authenticated_workspace_flow(tmp_path: Path) -> None:
    dsn = os.getenv("MUNNIN_PG_TEST_URL")
    if not dsn:
        pytest.skip("MUNNIN_PG_TEST_URL not set")
    suffix = uuid4().hex
    alice, bob = f"alice-{suffix}", f"bob-{suffix}"
    app = build_app(
        Config(db_path=tmp_path / "unused.db", db_backend="postgres", db_url=dsn),
        auth=auth_for(alice, bob),
    )
    async with (
        running(app),
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        mcp_client_for(app, token_for(alice)) as mcp,
    ):
        for subject in (alice, bob):
            assert (await http.get("/api/agents", headers=bearer(subject))).status_code == 200
        access = PostgresWorkspaceAccess(dsn)
        alice_home = access.lookup_home(TEST_ISSUER, alice)
        bob_home = access.lookup_home(TEST_ISSUER, bob)
        assert alice_home and bob_home and alice_home != bob_home
        alice_id, bob_id = uuid4().hex, uuid4().hex
        for user, uid, text in (
            (alice_home, alice_id, "alice secret"),
            (bob_home, bob_id, "bob secret"),
        ):
            PostgresMemoryRepository(dsn, user_id=user).insert_shared(
                SharedRecord(
                    uuid=uid,
                    user_id=user,
                    record_type=RecordType.knowledge,
                    title=text,
                    full_content=text,
                    content_summary=text,
                )
            )
        invite = (await http.post("/api/invites", json={}, headers=bearer(bob))).json()
        assert (
            await http.post(
                "/api/invites/redeem", json={"code": invite["code"]}, headers=bearer(alice)
            )
        ).status_code == 200
        assert (
            await http.post("/api/tenants/use", json={"tenant": bob_home}, headers=bearer(alice))
        ).status_code == 200
        assert (await mcp.call_tool("get_memory", {"uuid": bob_id})).data["content"] == "bob secret"
        bob_record = await http.get(f"/api/record/{bob_id}", headers=bearer(alice))
        assert bob_record.json()["content"] == "bob secret"
        awakening = await http.get("/api/awaken?agent_id=meta", headers=bearer(alice))
        caller = awakening.json()["caller"]
        assert caller["user_id"] == alice_home and caller["is_guest"] is True
        assert (await http.get(f"/api/record/{alice_id}", headers=bearer(alice))).status_code == 404
        assert (
            await http.post("/api/members/revoke", json={"member": alice_home}, headers=bearer(bob))
        ).status_code == 200
        assert (await http.get(f"/api/record/{bob_id}", headers=bearer(alice))).status_code == 403
        with pytest.raises(ToolError, match="was revoked"):
            await mcp.call_tool("get_memory", {"uuid": bob_id})
        assert (
            await http.post("/api/tenants/use", json={"tenant": None}, headers=bearer(alice))
        ).status_code == 200
        alice_record = await http.get(f"/api/record/{alice_id}", headers=bearer(alice))
        assert alice_record.json()["content"] == "alice secret"
