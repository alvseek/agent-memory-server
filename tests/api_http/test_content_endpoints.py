"""HTTP content endpoints (SP-5) — /api/prompts + /api/resources list/get/404."""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.content.loader import ContentLoader
from tests.conftest import auth_for, bearer, mcp_client_for, running, seed_login, token_for

CF = Path(__file__).resolve().parents[2] / "control-files"


def _client(tmp_path: Path) -> httpx.AsyncClient:
    app = build_app(
        Config(db_path=tmp_path / "m.db", content_root=CF, user_id="alvi"),
        auth=auth_for("alvi"),
    )
    seed_login(tmp_path / "m.db")
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer()
    )


async def test_prompts_list_get_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        prompts = (await c.get("/api/prompts")).json()["prompts"]
        assert prompts == ContentLoader(CF).list_prompts()
        assert "wait-options" in prompts  # discovered from the command set, listed nowhere
        assert "wrap-up" in prompts
        assert "create-agent" in prompts
        assert "list-agents" in prompts

        ok = await c.get("/api/prompts/update-episodic")
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "text/markdown; charset=utf-8"
        body = ok.text
        assert "create_episode(" in body and "MOVE-TO-TODAY" not in body

        assert (await c.get("/api/prompts/does-not-exist")).status_code == 404


async def test_resources_list_get_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        resources = (await c.get("/api/resources")).json()["resources"]
        assert "episodic-entry-template" in resources
        assert "knowledge-file-template" in resources
        assert "copy-lines" in resources

        ok = await c.get("/api/resources/reasoning-pattern-template")
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "Reasoning Pattern Template" in ok.text

        assert (await c.get("/api/resources/nope")).status_code == 404


async def test_catalog_search_matches_across_mounted_faces(tmp_path: Path) -> None:
    app = build_app(
        Config(db_path=tmp_path / "m.db", content_root=CF, user_id="alvi"),
        auth=auth_for("alvi"),
    )
    seed_login(tmp_path / "m.db")
    async with (
        running(app),
        mcp_client_for(app, token_for("alvi")) as mcp,
        httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        for kind, tool, cases in [
            ("procedures", "search_procedure", [
                (" TENANT__SHARING ", ["tenant-sharing"]),  # name only
                ("a-Shared account", ["tenant-sharing"]),  # title only
                ("memory update", []),
                ("fetching the instructions", []),  # description only
            ]),
            ("resources", "search_resources", [
                ("EPISODIC_entry", ["episodic-entry-template"]),  # name only
                ("BETWEEN-files", ["copy-lines"]),  # title only
                ("files between", []),
                ("automatic backup", []),  # description only
            ]),
        ]:
            url = f"/api/search/{kind}"
            menu = (await mcp.call_tool(f"list_{kind}")).data
            assert (await http.get(url, params={"query": "test"})).status_code == 401
            # A broader query should retain the existing list order and descriptions.
            broad = "update" if kind == "procedures" else "template"
            cases.append((broad, [row["name"] for row in menu if broad in row["name"]]))
            for query, names in cases:
                rows = (await mcp.call_tool(tool, {"query": query})).data
                response = await http.get(url, params={"query": query}, headers=bearer())
                assert response.status_code == 200
                assert response.json() == rows
                assert [row["name"] for row in rows] == names
                assert rows == [row for row in menu if row["name"] in names]

            for query in ("", " \t ", "_-"):
                result = await mcp.call_tool(tool, {"query": query}, raise_on_error=False)
                assert result.is_error
                response = await http.get(url, params={"query": query}, headers=bearer())
                assert response.status_code == 400
