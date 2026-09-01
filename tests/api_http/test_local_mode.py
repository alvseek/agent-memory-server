"""Local mode — ``MUNNIN_AUTH=off`` on a loopback public URL.

The laptop shape: no identity provider, every call acts as the one configured tenant.
What these pin is the *boundary* of that shape as much as the shape itself. The HTTP
router cannot be built unguarded by omission — asking for neither mode raises, and so
does asking for both. Both faces answer without a credential only when local mode was
chosen, and the mounted app carries no OAuth discovery in that mode because there is no
issuer to discover. A token-mode app built the ordinary way is checked alongside, so a
regression that opened it would fail here and not only in ``test_route_coverage``.

The MCP face is driven through the **mounted** app over streamable-HTTP, as every face
test does, because authentication — and its deliberate absence here — is a property of
the transport, not of the tool bodies.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from munnin.api_http.api import build_router
from munnin.app import LocalModeNotLoopbackError, build_app
from munnin.business_services.identity_service import IdentityService
from munnin.business_services.service_factory import ServiceFactory
from munnin.configuration.config import Config
from munnin.data_repositories.identity_repository import IdentityRepository
from tests.conftest import auth_for, mcp_client_for, running


def _local_app(tmp_path: Path):
    """The app exactly as ``python -m munnin`` builds it under ``MUNNIN_AUTH=off``."""
    return build_app(Config(db_path=tmp_path / "m.db", user_id="alvi", auth_mode="off"))


def _anonymous(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _tool_text(result) -> str:
    """The plain text a tool returned, whichever field this client version carries it in."""
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    return result.content[0].text


# --- the router refuses to be built unguarded ---------------------------------------------


def test_router_refuses_neither_mode(tmp_path: Path) -> None:
    """No ``auth`` and no ``local_user_id`` is an omission, and an omission must raise
    rather than build a router that answers everyone."""
    db = tmp_path / "m.db"
    with pytest.raises(ValueError):
        build_router(
            ServiceFactory(db),
            auth=None,
            identity=IdentityService(IdentityRepository(db)),
        )


def test_router_refuses_both_modes(tmp_path: Path) -> None:
    """Both given is ambiguous about who a request acts as, so it raises too."""
    db = tmp_path / "m.db"
    with pytest.raises(ValueError):
        build_router(
            ServiceFactory(db),
            auth=auth_for("alvi"),
            identity=IdentityService(IdentityRepository(db)),
            local_user_id="alvi",
        )


# --- local mode, end to end through the mounted app --------------------------------------


def test_build_app_enforces_the_loopback_guard(tmp_path: Path) -> None:
    """The guard is reached through the composition root, not only through ``build_auth``."""
    with pytest.raises(LocalModeNotLoopbackError):
        build_app(
            Config(
                db_path=tmp_path / "m.db",
                auth_mode="off",
                public_base_url="https://munnin.lok.quest",
            )
        )


async def test_http_face_answers_without_a_bearer(tmp_path: Path) -> None:
    app = _local_app(tmp_path)
    async with _anonymous(app) as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_mcp_face_answers_without_a_token(tmp_path: Path) -> None:
    app = _local_app(tmp_path)
    async with running(app):
        async with mcp_client_for(app, None) as client:
            result = await client.call_tool("ping", {})
    assert _tool_text(result) == "pong"


async def test_writes_land_in_the_configured_tenant(tmp_path: Path) -> None:
    """The account row is created at boot, so the very first write does not fail its
    foreign key — and what one face writes the other face reads, under the same tenant."""
    app = _local_app(tmp_path)
    async with running(app):
        async with mcp_client_for(app, None) as client:
            await client.call_tool(
                "create_agent", {"agent_id": "meta", "name": "Meta", "role": "test agent"}
            )
    async with _anonymous(app) as http:
        resp = await http.get("/api/agents")
    assert resp.status_code == 200
    assert [a["agent_id"] for a in resp.json()] == ["meta"]


async def test_local_mode_serves_no_oauth_discovery(tmp_path: Path) -> None:
    """Nothing issues tokens here, so advertising an authorization server would only send
    a client to a login that cannot happen."""
    app = _local_app(tmp_path)
    async with _anonymous(app) as client:
        resp = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 404


# --- token mode is what it was --------------------------------------------------------------


async def test_token_mode_still_refuses_an_anonymous_call(tmp_path: Path) -> None:
    """The ordinary build — an ``auth`` provider given — is unchanged by local mode's
    existence: no bearer, no answer."""
    app = build_app(Config(db_path=tmp_path / "m.db", user_id="alvi"), auth=auth_for("alvi"))
    async with _anonymous(app) as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 401
