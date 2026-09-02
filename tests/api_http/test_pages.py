"""The anonymous HTML pages — landing, privacy, terms.

These pages exist to be read before any token exists (Google's consent screen links
them, and a stranger reads them to decide whether to sign in), so the property under
test is that they answer **anonymously in token mode** — an authenticated-only page
here would 401 exactly the audience it was written for. Local mode serves them too,
because nothing about them depends on who the caller is.

The content assertions pin the claims the pages were built to make — the wipe notice,
what is stored, the contact channel — rather than the prose around them, so wording can
be edited freely while the load-bearing claims cannot silently disappear.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from tests.conftest import auth_for, seed_login

PAGES = ["/", "/privacy", "/terms"]


def _token_app(tmp_path: Path, **overrides):
    db = tmp_path / "m.db"
    app = build_app(Config(db_path=db, user_id="alvi", **overrides), auth=auth_for("alvi"))
    seed_login(db)
    return app


def _local_app(tmp_path: Path):
    return build_app(Config(db_path=tmp_path / "m.db", user_id="alvi", auth_mode="off"))


def _anonymous(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize("path", PAGES)
async def test_pages_answer_anonymously_in_token_mode(tmp_path: Path, path: str) -> None:
    """The whole point: readable before sign-in, on the mode the hosted demo runs."""
    async with _anonymous(_token_app(tmp_path)) as client:
        resp = await client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", PAGES)
async def test_pages_answer_in_local_mode(tmp_path: Path, path: str) -> None:
    async with _anonymous(_local_app(tmp_path)) as client:
        resp = await client.get(path)
    assert resp.status_code == 200


async def test_landing_carries_the_demo_notice_and_connect_line(tmp_path: Path) -> None:
    async with _anonymous(_token_app(tmp_path)) as client:
        text = (await client.get("/")).text
    assert "wiped on a regular schedule" in text
    assert "claude mcp add --transport http munnin" in text
    assert "github.com/alvseek/agent-memory-server" in text


async def test_landing_shows_this_instances_own_mcp_url(tmp_path: Path) -> None:
    """The connect snippet is built from ``public_base_url``, not from any baked-in host —
    a self-hoster's page must name *their* instance."""
    app = _token_app(tmp_path, public_base_url="https://munnin.example.test")
    async with _anonymous(app) as client:
        text = (await client.get("/")).text
    assert "https://munnin.example.test/mcp" in text
    assert "lok.quest" not in text


async def test_privacy_states_what_is_stored_and_the_contact(tmp_path: Path) -> None:
    async with _anonymous(_token_app(tmp_path)) as client:
        text = (await client.get("/privacy")).text
    assert "issuer and subject" in text
    assert "email address" in text
    assert "wiped on a regular schedule" in text
    assert "github.com/alvseek/agent-memory-server/issues" in text


async def test_terms_state_as_is_and_the_licence(tmp_path: Path) -> None:
    async with _anonymous(_token_app(tmp_path)) as client:
        text = (await client.get("/terms")).text
    assert "as is" in text
    assert "Apache License 2.0" in text
    assert "without notice" in text


async def test_pages_load_no_external_resources(tmp_path: Path) -> None:
    """The pages' "no tracking" claim is structural: nothing on them makes a reader's
    browser call a third party. ``href`` links a reader may click are fine; ``src``
    and ``link`` fetches, which fire on load, are what must not exist."""
    async with _anonymous(_token_app(tmp_path)) as client:
        for path in PAGES:
            text = (await client.get(path)).text
            assert "src=" not in text, path
            assert "<link" not in text, path
