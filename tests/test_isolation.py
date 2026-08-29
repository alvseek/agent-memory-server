"""Two identities, one server, and nothing crossing between them.

This is the test the whole plan exists to make possible, and it is the only one that
answers the question a user would actually ask. Everything else in the suite proves a
mechanism works; this proves the consequence — that the person who signs in next cannot
reach what you wrote.

It runs through the **started** app on both faces, because the guard and the tenant
resolution live at the transport and in a dependency, neither of which a
directly-constructed service would exercise. Every attempt is made through a route a real
caller has, never by reaching into the store.

``search`` is checked separately from ``query`` on purpose. It reaches records through the
FTS5 index rather than the browse query — a different code path with its own WHERE clause,
and therefore the likeliest place for a leak to survive a change that looked safe.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from tests.conftest import auth_for, mcp_client_for, running, token_for

ALICE, BOB = "subj-alice", "subj-bob"
SECRET = "alice-private-marker-zebra"


def _app(tmp_path: Path):
    return build_app(
        Config(db_path=tmp_path / "m.db", user_id="alvi"), auth=auth_for(ALICE, BOB)
    )


def _client(app, subject: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token_for(subject)}"},
    )


async def _write_as_alice(app) -> str:
    """Alice creates her own agent and writes one record. Returns its uuid."""
    async with _client(app, ALICE) as alice:
        created = await alice.post("/api/agents", json={"agent_id": "meta", "name": "Meta"})
        assert created.status_code == 200, created.text
        written = await alice.post(
            "/api/insert",
            json={"agent_id": "meta", "record_type": "knowledge", "content": SECRET},
        )
        assert written.status_code == 200, written.text
        return written.json()["uuid"]


async def test_alice_can_read_her_own_record(tmp_path: Path) -> None:
    """Negative control, and it comes first.

    Every other test here asserts an absence, and an absence is also what a completely
    broken write path produces. If this one fails, none of the others mean anything.
    """
    app = _app(tmp_path)
    uuid = await _write_as_alice(app)
    async with _client(app, ALICE) as alice:
        got = await alice.get(f"/api/record/{uuid}")
        found = await alice.get("/api/search", params={"text": SECRET})
    assert got.status_code == 200
    assert SECRET in got.json()["content"]
    assert len(found.json()) == 1


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/record/{uuid}", None),
        ("POST", "/api/edit", {"old_string": "zebra", "new_string": "hijacked"}),
        ("POST", "/api/append", {"text": "tampered"}),
        ("POST", "/api/prepend", {"text": "tampered"}),
        ("POST", "/api/archive", {}),
        ("POST", "/api/soft-delete", {}),
    ],
)
async def test_bob_cannot_touch_alices_record_by_uuid(
    tmp_path: Path, method: str, path: str, body: dict | None
) -> None:
    """Knowing the uuid is not authority to read or change it.

    The uuid is handed to Bob directly, which is the strongest form of the test: it removes
    discovery from the question and asks only whether the tenant check holds.
    """
    app = _app(tmp_path)
    uuid = await _write_as_alice(app)
    async with _client(app, BOB) as bob:
        if method == "GET":
            resp = await bob.get(path.format(uuid=uuid))
        else:
            resp = await bob.request(method, path, json={"uuid": uuid, **(body or {})})
    assert resp.status_code == 404, f"{method} {path} leaked: {resp.status_code}"


async def test_bob_cannot_find_alices_record_by_browsing_or_search(tmp_path: Path) -> None:
    """The discovery half: not merely protected when named, but invisible."""
    app = _app(tmp_path)
    await _write_as_alice(app)
    async with _client(app, BOB) as bob:
        queried = await bob.get("/api/query")
        searched = await bob.get("/api/search", params={"text": SECRET})
        agents = await bob.get("/api/agents")
    assert queried.json() == []
    assert searched.json() == [], "FTS index leaked across tenants"
    assert agents.json() == [], "Alice's agent is visible to Bob"


async def test_bobs_write_does_not_reach_alices_agent(tmp_path: Path) -> None:
    """Bob naming Alice's agent must not attach his record to it.

    ``meta`` exists — for Alice. The composite foreign key is what makes this a rejection
    rather than a silent cross-tenant write, so it is worth proving rather than trusting.
    """
    app = _app(tmp_path)
    await _write_as_alice(app)
    async with _client(app, BOB) as bob:
        resp = await bob.post(
            "/api/insert",
            json={"agent_id": "meta", "record_type": "knowledge", "content": "bob was here"},
        )
    assert resp.status_code == 400

    async with _client(app, ALICE) as alice:
        still = await alice.get("/api/query")
    assert [r["content"] for r in still.json()] == [SECRET]


async def test_isolation_holds_on_the_mcp_face_too(tmp_path: Path) -> None:
    """Both faces or neither — a leak on one is a leak.

    Checked over MCP as well because the two faces resolve their tenant by different
    routes (FastMCP's request context versus a FastAPI dependency), so they could hold
    the boundary differently and the HTTP tests above would never notice.
    """
    app = _app(tmp_path)
    uuid = await _write_as_alice(app)

    async with running(app), mcp_client_for(app, token_for(BOB)) as bob:
        got = await bob.call_tool("get", {"uuid": uuid})
        found = await bob.call_tool("search", {"text": SECRET})
        agents = await bob.call_tool("list_agents", {})

    assert not got.data
    assert not found.data, "FTS index leaked across tenants on the MCP face"
    assert not agents.data
