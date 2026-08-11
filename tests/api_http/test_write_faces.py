"""HTTP face — full /api/* read/write surface (SP-3 Step 2.1).

ASGI in-process via httpx; the whole DI graph is built by build_app over a temp DB.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config


def _client(tmp_path: Path) -> httpx.AsyncClient:
    app = build_app(Config(db_path=tmp_path / "m.db", user_id="alvi"))
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_insert_get_round_trip(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        r = await c.post(
            "/api/insert",
            json={"agent_id": "meta", "record_type": "episode", "content": "body", "uuid": "e1"},
        )
        assert r.status_code == 200
        assert r.json()["uuid"] == "e1"

        g = await c.get("/api/record/e1")
        assert g.status_code == 200
        assert g.json()["content"] == "body"


async def test_get_missing_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        assert (await c.get("/api/record/nope")).status_code == 404


async def test_edit_and_query(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        await c.post("/api/insert", json={"agent_id": "meta", "record_type": "knowledge",
                                          "content": "hello world", "uuid": "k1"})
        e = await c.post("/api/edit", json={"uuid": "k1", "old_string": "world",
                                            "new_string": "there"})
        assert e.status_code == 200
        assert e.json()["content"] == "hello there"

        q = await c.get("/api/query", params={"agent_id": "meta", "record_type": "knowledge"})
        assert [row["uuid"] for row in q.json()] == ["k1"]


async def test_archive_then_search(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        await c.post("/api/insert", json={"agent_id": "meta", "record_type": "knowledge",
                                          "content": "findable token", "uuid": "k1"})
        a = await c.post("/api/archive", json={"uuid": "k1"})
        assert a.json() == {"uuid": "k1", "status": "archived"}
        assert (await c.get("/api/query", params={"agent_id": "meta"})).json() == []
        s = await c.get("/api/search", params={"text": "findable"})
        assert [row["uuid"] for row in s.json()] == ["k1"]


async def test_soft_delete_then_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        await c.post("/api/insert", json={"agent_id": "meta", "record_type": "knowledge",
                                          "content": "x", "uuid": "k1"})
        await c.post("/api/soft-delete", json={"uuid": "k1"})
        assert (await c.get("/api/record/k1")).status_code == 404


async def test_insert_bad_record_type_400(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        r = await c.post("/api/insert", json={"agent_id": "meta", "record_type": "bogus",
                                              "content": "x"})
        assert r.status_code == 400


async def test_edit_missing_404(tmp_path: Path) -> None:
    async with _client(tmp_path) as c:
        r = await c.post("/api/edit", json={"uuid": "nope", "old_string": "a", "new_string": "b"})
        assert r.status_code == 404
