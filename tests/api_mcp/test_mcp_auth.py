"""The MCP face behind a token.

These drive the **mounted** MCP app rather than an in-memory ``FastMCP``, because that is
the only place the guard exists: authentication is enforced at the transport, so an
in-memory client would sail past it and report success on a server that is wide open.
That distinction is the whole point of the file — a test that cannot observe the guard
cannot prove the guard.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.app import build_app
from munnin.business_services.service_factory import ServiceFactory
from munnin.configuration.config import Config
from munnin.data_repositories.identity_repository import IdentityRepository
from tests.conftest import (
    TEST_ISSUER,
    FixedTenantResolver,
    auth_for,
    mcp_client_for,
    running,
    token_for,
)

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "tests", "version": "0"},
    },
}
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _app(db: Path, *subjects: str):
    return build_app(Config(db_path=db, user_id="alvi"), auth=auth_for(*subjects))


def _raw(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_mcp_rejects_a_call_with_no_token(tmp_path: Path) -> None:
    async with _raw(_app(tmp_path / "m.db", "subj-a")) as client:
        resp = await client.post("/mcp/", json=INIT, headers=MCP_HEADERS)
    assert resp.status_code == 401


async def test_mcp_rejects_an_unknown_token(tmp_path: Path) -> None:
    """A token the issuer never minted is refused, not merely unmapped to a tenant."""
    headers = {**MCP_HEADERS, "Authorization": "Bearer not-a-real-token"}
    async with _raw(_app(tmp_path / "m.db", "subj-a")) as client:
        resp = await client.post("/mcp/", json=INIT, headers=headers)
    assert resp.status_code == 401


async def test_health_is_still_reachable_without_a_token(tmp_path: Path) -> None:
    """Decision 17: the Kamal health gate calls this unauthenticated, so it must stay open."""
    async with _raw(_app(tmp_path / "m.db", "subj-a")) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


async def test_authenticated_call_lands_in_the_subject_s_own_tenant(tmp_path: Path) -> None:
    """The end of the chain: a verified token becomes a tenant that did not exist before.

    Asserted against the store rather than against the tool's reply, because the reply
    would look identical if the resolver had quietly fallen back to a configured tenant —
    which is exactly the failure this phase exists to remove.
    """
    db = tmp_path / "m.db"
    app = _app(db, "subj-a")
    assert IdentityRepository(db).find_user_id(TEST_ISSUER, "subj-a") is None

    async with running(app), mcp_client_for(app, token_for("subj-a")) as client:
        await client.call_tool("list_agents", {})

    user_id = IdentityRepository(db).find_user_id(TEST_ISSUER, "subj-a")
    assert user_id is not None
    assert user_id != "alvi"  # not the configured tenant — the caller's own


async def test_two_subjects_get_two_tenants(tmp_path: Path) -> None:
    """The precondition isolation rests on: distinct subjects are never the same tenant."""
    db = tmp_path / "m.db"
    app = _app(db, "subj-a", "subj-b")

    for subject in ("subj-a", "subj-b"):
        async with running(app), mcp_client_for(app, token_for(subject)) as client:
            await client.call_tool("list_agents", {})

    repo = IdentityRepository(db)
    assert repo.find_user_id(TEST_ISSUER, "subj-a") != repo.find_user_id(TEST_ISSUER, "subj-b")


async def test_a_returning_subject_keeps_its_tenant(tmp_path: Path) -> None:
    """Resolution is stable: signing in twice does not mint a second tenant."""
    db = tmp_path / "m.db"
    app = _app(db, "subj-a")

    seen = []
    for _ in range(2):
        async with running(app), mcp_client_for(app, token_for("subj-a")) as client:
            await client.call_tool("list_agents", {})
        seen.append(IdentityRepository(db).find_user_id(TEST_ISSUER, "subj-a"))

    assert seen[0] is not None
    assert seen[0] == seen[1]


@pytest.mark.parametrize("tool", ["ping", "list_agents"])
async def test_no_tool_is_reachable_unauthenticated(tmp_path: Path, tool: str) -> None:
    """``ping`` touches no store and is the likeliest thing to be waved through."""
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool}}
    async with _raw(_app(tmp_path / "m.db", "subj-a")) as client:
        resp = await client.post("/mcp/", json=body, headers=MCP_HEADERS)
    assert resp.status_code == 401


async def test_the_same_call_is_not_rejected_when_the_guard_is_absent(tmp_path: Path) -> None:
    """Negative control — proves the 401s above come from the guard and not from the request.

    Every assertion in this file is that something is *refused*, and a malformed request
    would be refused too. So one unguarded face is built and the identical call made
    against it: if this ever starts returning 401 as well, the tests above have stopped
    testing authentication and nothing else would say so.
    """
    unguarded = FastAPI()
    mcp = build_mcp(
        ServiceFactory(tmp_path / "m.db"), FixedTenantResolver("alvi"), auth=None
    )
    mcp_app = mcp.http_app(path="/")
    unguarded.router.lifespan_context = mcp_app.lifespan
    unguarded.mount("/mcp", mcp_app)

    async with running(unguarded), _raw(unguarded) as client:
        resp = await client.post("/mcp/", json=INIT, headers=MCP_HEADERS)

    assert resp.status_code != 401
