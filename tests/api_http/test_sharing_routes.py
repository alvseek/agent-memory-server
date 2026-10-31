"""The membership routes on the HTTP face, including the one refusal only it can show.

The same rules are proven through the service and through MCP. This file exists for the
third path: that the HTTP face applies the remembered selection on **every** route, and
answers 403 rather than silently serving the caller's own memory once the selection is
revoked.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from tests.conftest import auth_for, bearer, seed_login

CF = Path(__file__).resolve().parents[2] / "control-files"


def _client(tmp_path: Path) -> httpx.AsyncClient:
    db = tmp_path / "m.db"
    app = build_app(
        Config(db_path=db, content_root=CF, user_id="alvi"), auth=auth_for("alvi", "roy")
    )
    seed_login(db, "alvi")
    seed_login(db, "roy")
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer("alvi")
    )


def _as(subject: str) -> dict[str, str]:
    return bearer(subject)


async def test_the_owner_flow_and_the_selection_refusal(tmp_path: Path) -> None:
    async with _client(tmp_path) as http:
        invite = (await http.post("/api/invites", json={"days": 7})).json()
        assert invite["tenant_user_id"] == "alvi"

        joined = (
            await http.post(
                "/api/invites/redeem", json={"code": invite["code"]}, headers=_as("roy")
            )
        )
        assert joined.status_code == 200
        assert joined.json()["role"] == "guest"

        tenants = (await http.get("/api/tenants", headers=_as("roy"))).json()
        assert [(t["user_id"], t["role"], t["active"]) for t in tenants] == [
            ("roy", "owner", True),
            ("alvi", "guest", False),
        ]

        switched = await http.post(
            "/api/tenants/use", json={"tenant": "alvi"}, headers=_as("roy")
        )
        assert switched.status_code == 200 and switched.json()["user_id"] == "alvi"

        members = (await http.get("/api/members", headers=_as("roy"))).json()
        assert [m["user_id"] for m in members] == ["alvi", "roy"]

        # While Roy sits inside Alvi's account the payload says both things at once: the
        # memory is Alvi's, and the person signed in is Roy.
        inside = (await http.get("/api/awaken?agent_id=meta", headers=_as("roy"))).json()
        assert inside["caller"] == {"user_id": "roy", "display_name": None, "is_guest": True}

        revoked = await http.post(
            "/api/members/revoke", json={"member": "roy"}, headers=_as("alvi")
        )
        assert revoked.status_code == 200

        # Every memory route now refuses, by name, rather than answering from Roy's own
        # tenant — the failure this check exists to prevent.
        refused = await http.get("/api/awaken?agent_id=meta", headers=_as("roy"))
        assert refused.status_code == 403
        assert "was revoked" in refused.json()["detail"]

        # And the way out is still reachable, because it resolves the home tenant only.
        back = await http.post(
            "/api/tenants/use", json={"tenant": None}, headers=_as("roy")
        )
        assert back.status_code == 200 and back.json()["user_id"] == "roy"
        assert (await http.get("/api/awaken?agent_id=meta", headers=_as("roy"))).status_code == 200


async def test_a_guest_cannot_grant_from_somebody_elses_tenant(tmp_path: Path) -> None:
    async with _client(tmp_path) as http:
        invite = (await http.post("/api/invites", json={})).json()
        await http.post(
            "/api/invites/redeem", json={"code": invite["code"]}, headers=_as("roy")
        )
        await http.post("/api/tenants/use", json={"tenant": "alvi"}, headers=_as("roy"))

        refused = await http.post("/api/invites", json={}, headers=_as("roy"))
        assert refused.status_code == 403
        assert "only the owner" in refused.json()["detail"]


async def test_a_bad_code_is_a_400_with_the_reason(tmp_path: Path) -> None:
    async with _client(tmp_path) as http:
        response = await http.post(
            "/api/invites/redeem", json={"code": "never-existed"}, headers=_as("roy")
        )
        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]
