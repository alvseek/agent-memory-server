"""Paged episode reads over both faces — HTTP ``/api/record/{uuid}`` and MCP ``get``.

Both adapters are thin over one service, so the assertions that matter are: the two faces
return the *same* page, the paging arguments reach the service unmangled, a bad argument is
an error on both, and ``awaken`` carries the page on both.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.data_entities.memory_record import MemoryRecord, RecordType
from tests.conftest import (
    AutoAgentRepository,
    auth_for,
    bearer,
    mcp_for,
    seed_login,
)

BLOCKS = [
    "### 2026-11-10 10.05 - five\n\nbody five\n",
    "### 2026-11-10 10.04 - four\n\nbody four\n",
    "### 2026-11-10 10.03 - three\n\nbody three\n",
    "### 2026-11-10 10.02 - two\n\nbody two\n",
    "### 2026-11-10 10.01 - one\n\nbody one\n",
]
EPISODE = "".join(BLOCKS)
EPISODE_UUID = "abcdef0123456789abcdef0123456789"


def _seed(db: Path) -> None:
    repo = AutoAgentRepository(db, user_id="alvi")
    repo.insert(
        MemoryRecord(
            uuid="id1", user_id="", agent_id="meta", record_type=RecordType.identity,
            title="Identity", full_content="I am meta", created_date="2026-01-01",
        )
    )
    repo.insert(
        MemoryRecord(
            uuid=EPISODE_UUID, user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Rolling", project="munnin", full_content=EPISODE,
            created_date="2026-11-10", content_summary="five sub-episodes",
        )
    )


def _app(db: Path):
    return build_app(Config(db_path=db, user_id="alvi"), auth=auth_for("alvi"))


async def _http_client(app):
    return httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer()
    )


async def test_both_faces_return_the_same_page(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with await _http_client(_app(db)) as http:
        http_page = (
            await http.get(f"/api/record/{EPISODE_UUID}", params={"limit": 2})
        ).json()
    async with Client(mcp_for(db)) as mcp:
        mcp_page = (
            await mcp.call_tool("get", {"uuid": EPISODE_UUID, "limit": 2})
        ).data
    assert http_page == mcp_page
    assert http_page["content"] == BLOCKS[0] + BLOCKS[1]
    assert http_page["next_cursor"] == "2026-11-10 10.03"


async def test_continuation_round_trips_across_the_faces(tmp_path: Path) -> None:
    """Read page one on one face, continue on the other: the cursor is a value, not a
    session on the server, so it has to travel."""
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with Client(mcp_for(db)) as mcp:
        first = (await mcp.call_tool("get", {"uuid": EPISODE_UUID, "limit": 2})).data
    async with await _http_client(_app(db)) as http:
        second = (
            await http.get(
                f"/api/record/{EPISODE_UUID}",
                params={"cursor": first["next_cursor"], "limit": 2},
            )
        ).json()
    assert second["content"] == BLOCKS[2] + BLOCKS[3]
    assert second["next_cursor"] == "2026-11-10 10.01"


async def test_a_prefix_reference_can_be_paged(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with await _http_client(_app(db)) as http:
        page = (
            await http.get(f"/api/record/{EPISODE_UUID[:6]}", params={"limit": 1})
        ).json()
    assert page["uuid"] == EPISODE_UUID
    assert page["content"] == BLOCKS[0]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": -2},
        {"cursor": "not-a-timestamp"},
        {"cursor": "2020-01-01 00.00"},
    ],
    ids=["zero-limit", "negative-limit", "malformed-cursor", "unknown-cursor"],
)
async def test_http_maps_a_bad_paging_argument_to_a_client_error(
    tmp_path: Path, params: dict
) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with await _http_client(_app(db)) as http:
        response = await http.get(f"/api/record/{EPISODE_UUID}", params=params)
    assert response.status_code == 400
    assert "cursor" in response.json()["detail"] or "limit" in response.json()["detail"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 0},
        {"cursor": "not-a-timestamp"},
        {"cursor": "2020-01-01 00.00"},
    ],
    ids=["zero-limit", "malformed-cursor", "unknown-cursor"],
)
async def test_mcp_reports_a_bad_paging_argument_as_a_tool_error(
    tmp_path: Path, arguments: dict
) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    async with Client(mcp_for(db)) as mcp:
        with pytest.raises(ToolError) as caught:
            await mcp.call_tool("get", {"uuid": EPISODE_UUID, **arguments})
    message = str(caught.value)
    assert "cursor" in message or "limit" in message


async def test_an_absent_record_is_still_a_404_on_http(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with await _http_client(_app(db)) as http:
        response = await http.get(f"/api/record/{'0' * 32}", params={"limit": 1})
    assert response.status_code == 404


async def test_neither_listing_nor_search_hands_out_a_body(tmp_path: Path) -> None:
    """The one rule both projections exist for, asserted on both faces."""
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    app = _app(db)
    async with await _http_client(app) as http:
        browse = (await http.get("/api/query", params={"agent_id": "meta"})).json()
        hits = (await http.get("/api/search", params={"text": "five"})).json()
    assert browse and "content" not in browse[0] and "full_content" not in browse[0]
    episode_row = next(row for row in browse if row["uuid"] == EPISODE_UUID)
    assert episode_row["blocks_total"] == 5
    assert hits and "content" not in hits[0] and "full_content" not in hits[0]
    assert hits[0]["snippet"]

    async with Client(mcp_for(db)) as mcp:
        mcp_browse = (await mcp.call_tool("query", {"agent_id": "meta"})).data
        mcp_hits = (await mcp.call_tool("search", {"text": "five"})).data
    assert mcp_browse == browse
    assert mcp_hits == hits


async def test_awaken_carries_the_page_on_both_faces(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    _seed(db)
    seed_login(db)
    async with await _http_client(_app(db)) as http:
        payload = (await http.get("/api/awaken", params={"agent_id": "meta"})).json()
    latest = payload["latest_episode"]
    assert (latest["blocks_returned"], latest["blocks_total"]) == (3, 5)
    assert latest["next_cursor"] == "2026-11-10 10.02"
    assert latest["content"] == "".join(BLOCKS[:3])
    assert payload["identity"][0]["content"] == "I am meta"

    async with Client(mcp_for(db)) as mcp:
        mcp_payload = (await mcp.call_tool("awaken", {"domain": "meta"})).data
    assert mcp_payload["latest_episode"] == latest
