"""HTTP content endpoints (SP-5) — /api/prompts + /api/resources list/get/404."""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config

CF = Path(__file__).resolve().parents[2] / "control-files"


def _client(tmp_path: Path) -> httpx.AsyncClient:
    app = build_app(Config(db_path=tmp_path / "m.db", content_root=CF, user_id="alvi"))
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_prompts_list_get_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        prompts = (await c.get("/api/prompts")).json()["prompts"]
        assert len(prompts) == 12
        assert "wrap-up" in prompts
        assert "create-agent" in prompts
        assert "list-agents" in prompts

        ok = await c.get("/api/prompts/update-episodic")
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "text/markdown; charset=utf-8"
        body = ok.text
        assert "insert(" in body and "MOVE-TO-TODAY" not in body

        assert (await c.get("/api/prompts/does-not-exist")).status_code == 404


async def test_resources_list_get_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        resources = (await c.get("/api/resources")).json()["resources"]
        assert "episodic-entry-template" in resources
        assert "knowledge-file-template" in resources

        ok = await c.get("/api/resources/reasoning-pattern-template")
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "Reasoning Pattern Template" in ok.text

        assert (await c.get("/api/resources/nope")).status_code == 404
