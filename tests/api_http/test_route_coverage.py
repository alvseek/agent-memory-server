"""No HTTP route is reachable without a token, except the one that must be.

This is the guard that outlives the people who wrote it. Every other auth test names a
route, so it can only protect routes somebody remembered to name; this one enumerates the
surface and holds it to a single rule, which means a route added next year is covered on
the day it is added rather than on the day somebody notices.

The surface is read from the OpenAPI schema rather than by walking ``app.routes``. That is
not a stylistic preference: FastAPI keeps an included router as one opaque
``_IncludedRouter`` object with no ``path`` and no ``routes``, so the obvious traversal
finds **four** built-in routes, misses all eighteen real operations, and passes. A guard
that silently checks nothing is worse than no guard, because it also stops anyone looking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp.server.auth import MultiAuth
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from tests.conftest import auth_for, bearer, seed_login

# The routes that must answer without a credential, each for a stated reason:
# ``/health`` because Kamal's health gate calls it, so guarding it would fail the deploy
# and the cutover would never happen (decision 17); the three HTML pages because Google's
# consent screen links them and a stranger reads them to decide whether to sign in —
# both audiences exist before any token can. Everything else answers 401 anonymously.
OPEN_ROUTES = {("GET", "/health"), ("GET", "/"), ("GET", "/privacy"), ("GET", "/terms")}

# A coarse tripwire beside the per-route rule below. The rule is what protects a new
# route; this notices when the surface changes size at all, so growth is a decision
# somebody made rather than something that happened.
EXPECTED_OPERATIONS = 21


def _app(tmp_path: Path):
    db = tmp_path / "m.db"
    app = build_app(Config(db_path=db, user_id="alvi"), auth=auth_for("alvi"))
    seed_login(db)
    return app


def _app_with_real_provider(tmp_path: Path):
    """An app wired to a genuine ``AuthKitProvider``.

    The token double these other tests use is a bare ``MultiAuth`` with verifiers and no
    server, which correctly publishes no OAuth metadata — there is no authorization server
    behind it to describe. Discovery therefore has to be checked against the real provider,
    or the test asserts the absence of routes it never asked for.
    """
    return build_app(
        Config(
            db_path=tmp_path / "m.db",
            authkit_domain="https://munnin-test.authkit.app",
            public_base_url="https://munnin.example.test",
        )
    )


def _operations(app: Any) -> list[tuple[str, str]]:
    """Every (method, path) the HTTP face publishes."""
    return [
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    ]


def _probe(path: str) -> str:
    return path.replace("{uuid}", "x").replace("{name}", "x")


async def test_every_route_outside_the_open_set_rejects_an_absent_token(tmp_path: Path) -> None:
    app = _app(tmp_path)
    transport = ASGITransport(app=app)
    reachable = []
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for method, path in _operations(app):
            if (method, path) in OPEN_ROUTES:
                continue
            kwargs = {"json": {}} if method == "POST" else {}
            resp = await client.request(method, _probe(path), **kwargs)
            if resp.status_code != 401:
                reachable.append(f"{method} {path} -> {resp.status_code}")
    assert reachable == [], f"reachable without a token: {reachable}"


@pytest.mark.parametrize("method,path", sorted(OPEN_ROUTES))
async def test_the_open_routes_still_answer(tmp_path: Path, method: str, path: str) -> None:
    """The other half of the rule — every exception must keep working: a guarded ``/health``
    stops the deploy, and a guarded page 401s the stranger it was written for."""
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(tmp_path)), base_url="http://test"
    ) as client:
        resp = await client.request(method, path)
    assert resp.status_code == 200


async def test_the_surface_is_the_size_we_think_it_is(tmp_path: Path) -> None:
    """Fails when a route is added or removed, so the count is never a surprise.

    If this is the only failure, the fix is to update the number — after checking the new
    route landed on the guarded router.
    """
    assert len(_operations(_app(tmp_path))) == EXPECTED_OPERATIONS


async def test_oauth_discovery_is_served_where_the_challenge_says_it_is(tmp_path: Path) -> None:
    """The 401 tells a client where to look; that URL has to answer.

    FastMCP builds its app believing it sits at ``/``, so it advertises root-level
    metadata and serves its own copies inside the sub-app — which FastAPI mounts under
    ``/mcp``, leaving the advertised URL a 404. A client following the standard flow would
    then fail discovery and never reach a login screen, and nothing about the server would
    look broken. The two URLs are asserted **together** for that reason: they agreeing is
    the property, not either one existing.
    """
    app = _app_with_real_provider(tmp_path)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        challenged = await client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        advertised = challenged.headers["www-authenticate"].split('resource_metadata="')[1]
        advertised = advertised.rstrip('"')
        metadata = await client.get(httpx.URL(advertised).path)

    assert challenged.status_code == 401
    assert metadata.status_code == 200, f"the challenge points at {advertised}, which 404s"
    assert metadata.json()["authorization_servers"]


async def test_discovery_is_reachable_without_a_token(tmp_path: Path) -> None:
    """And it must be: a client reads it to learn how to get a token (RFC 9728).

    So this is a third open endpoint beside ``/health``, deliberately, and it is recorded
    here rather than left to be rediscovered as a hole during the next audit.

    Only the protected-resource document is asserted. Its sibling,
    ``/.well-known/oauth-authorization-server``, is a **forwarder**: it fetches AuthKit's
    metadata over the network on every request, so offline it answers 500 and asserting it
    here would be testing the vendor's uptime rather than this server. That live dependency
    is worth knowing about on its own — discovery stops working if AuthKit is unreachable.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app_with_real_provider(tmp_path)), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
async def test_the_schema_routes_are_absent_by_default(tmp_path: Path, path: str) -> None:
    """FastAPI's own routes are the one surface the guard cannot reach.

    They are added to the app rather than to a router, so they can be present or absent
    but never protected — a browser cannot attach a bearer token to its own page load.
    Absent is therefore the only way ``no endpoint is reachable unauthenticated`` is true,
    and reading ``/openapi.json`` is how the live server's original hole was found.
    """
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(tmp_path)), base_url="http://test"
    ) as client:
        resp = await client.get(path)
    assert resp.status_code == 404


async def test_the_schema_routes_can_be_turned_on_for_local_work(tmp_path: Path) -> None:
    """Negative control: they are absent by configuration, not by being broken."""
    db = tmp_path / "m.db"
    app = build_app(
        Config(db_path=db, user_id="alvi", docs_enabled=True), auth=auth_for("alvi")
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/openapi.json")
    assert resp.status_code == 200


async def test_an_unknown_token_is_refused(tmp_path: Path) -> None:
    """Presenting *a* token is not the same as presenting a valid one."""
    async with httpx.AsyncClient(
        transport=ASGITransport(app=_app(tmp_path)),
        base_url="http://test",
        headers={"Authorization": "Bearer not-a-real-token"},
    ) as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 401


async def test_a_token_naming_no_subject_is_refused(tmp_path: Path) -> None:
    """A token can verify and still identify nobody, and that must not resolve to a tenant.

    This is the branch that would otherwise be tempting to paper over with a default: the
    signature checks out, so the caller looks legitimate, but nothing in the token says
    *who* they are. Choosing a tenant here is guessing at an identity, which is the whole
    failure the ``(iss, sub)`` key exists to prevent.
    """
    subjectless = MultiAuth(
        verifiers=[StaticTokenVerifier({"anon": {"client_id": "munnin-tests"}})]
    )
    db = tmp_path / "m.db"
    app = build_app(Config(db_path=db, user_id="alvi"), auth=subjectless)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer anon"},
    ) as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path", [("GET", "/api/agents"), ("POST", "/api/insert")])
async def test_a_valid_token_is_accepted_on_both_verbs(
    tmp_path: Path, method: str, path: str
) -> None:
    """Negative control for the file: the 401s above are the guard, not a broken app.

    Without this, a server that rejected every request for an unrelated reason would make
    the whole file pass. A read and a write are checked because they take different paths
    through the dependency.
    """
    app = _app(tmp_path)
    kwargs = {"json": {"record_type": "knowledge", "content": "x", "scope": "shared"}}
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer()
    ) as client:
        resp = await client.request(method, path, **(kwargs if method == "POST" else {}))
    assert resp.status_code != 401
