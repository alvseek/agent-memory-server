"""The MCP face answers under both slash forms, and neither form is a redirect.

The specification tells a client to use the no-slash resource identifier consistently,
and at least one client normalises its configured URL to match — so ``/mcp`` is what
arrives, whatever was typed. Starlette's ``Mount`` only matches *below* ``/mcp`` and
answers the bare path with a slash-appending 307; behind the TLS-terminating proxy that
redirect is built from the scheme uvicorn saw, so it points at ``http://`` and the client
is bounced to plaintext before it ever sees a 401. That is the live failure these tests
pin: measured as ``307 Location: http://munnin.lok.quest/mcp/`` on 2026-09-01.

Every assertion here is made with redirects *not* followed, because following them is
exactly how the defect hides.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from munnin.app import _NormalisePath, build_app
from munnin.configuration.config import Config

BASE_URL = "https://munnin.example.test"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _app(tmp_path: Path):
    """An app behind the real Logto provider, so the advertised identifier is the real one."""
    return build_app(
        Config(
            db_path=tmp_path / "m.db",
            logto_endpoint="https://auth.example.test",
            public_base_url=BASE_URL,
        )
    )


def _client(app) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    )


async def test_both_slash_forms_answer_the_same_challenge(tmp_path: Path) -> None:
    """One endpoint, two spellings: the challenge must be identical, down to the metadata URL.

    A client that strips the slash and a client that keeps it must be sent to the same
    document naming the same resource, or they mint tokens for two different audiences.
    """
    async with _client(_app(tmp_path)) as client:
        bare = await client.post("/mcp", json=INIT, headers=MCP_HEADERS)
        slashed = await client.post("/mcp/", json=INIT, headers=MCP_HEADERS)
    assert (bare.status_code, slashed.status_code) == (401, 401)
    assert bare.headers["www-authenticate"] == slashed.headers["www-authenticate"]
    assert f'resource_metadata="{BASE_URL}{METADATA_PATH}"' in bare.headers["www-authenticate"]


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_nothing_on_the_mcp_path_redirects(tmp_path: Path, path: str, method: str) -> None:
    """No spelling and no method on the MCP face may answer 3xx.

    A redirect here is not a detour but a broken login: it carries the scheme the app saw
    behind the proxy, and the client follows it to plaintext or refuses it outright.
    """
    async with _client(_app(tmp_path)) as client:
        kwargs = {"json": INIT} if method == "POST" else {}
        resp = await client.request(method, path, headers=MCP_HEADERS, **kwargs)
    assert not 300 <= resp.status_code < 400, f"{method} {path} -> {resp.status_code}"


async def test_metadata_document_is_served_under_both_forms(tmp_path: Path) -> None:
    """The document lives at the no-slash path RFC 9728 derives; the slashed form is an alias.

    The ``resource`` it carries is the no-slash identifier — the string a client sends the
    issuer on every authorization and refresh request, matched character for character.
    """
    async with _client(_app(tmp_path)) as client:
        bare = await client.get(METADATA_PATH)
        slashed = await client.get(f"{METADATA_PATH}/")
    assert (bare.status_code, slashed.status_code) == (200, 200)
    assert bare.json() == slashed.json()
    assert bare.json()["resource"] == f"{BASE_URL}/mcp"


async def test_without_the_normaliser_the_bare_path_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: prove the assertions above can fail, and name what makes them pass.

    With the rewrite table emptied the app is exactly what shipped before — and the bare
    path answers a 307 again. A guard whose failure mode has never been observed is not a
    guard, so this test observes it.
    """
    monkeypatch.setattr(_NormalisePath, "_REWRITES", {})
    async with _client(_app(tmp_path)) as client:
        resp = await client.post("/mcp", json=INIT, headers=MCP_HEADERS)
    assert resp.status_code == 307
    assert resp.headers["location"].endswith("/mcp/")
