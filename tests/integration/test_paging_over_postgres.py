"""Integration boundary: the two HTTP/MCP faces paging a record in a real PostgreSQL store.

**One real dependency**: PostgreSQL. Everything else is the test's own — the issuer is a
``StaticTokenVerifier`` triple, the transport is in-process ASGI, and the episode body is
seeded through the service's own public write. That is the boundary an agent actually
crosses when it continues a paged read, with the one component the unit tests cannot supply
(the engine) made real.

The database is the disposable one named by ``MUNNIN_PG_TEST_URL``; its schema is reset
here, exactly as the repository contract fixture does, so a re-run proves the same thing
from clean. Never point this at a shared stack or production database.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from psycopg.conninfo import conninfo_to_dict

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType
from munnin.data_repositories.postgres_identity_repository import PostgresIdentityRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from tests.conftest import (
    TEST_ISSUER,
    auth_for,
    bearer,
    mcp_client_for,
    running,
)

pytestmark = pytest.mark.postgres

BLOCKS = [
    "### 2026-11-10 10.05 - five\n\nbody five\n",
    "### 2026-11-10 10.04 - four\n\nbody four\n",
    "### 2026-11-10 10.03 - three\n\nbody three\n",
    "### 2026-11-10 10.02 - two\n\nbody two\n",
    "### 2026-11-10 10.01 - one\n\nbody one\n",
]
EPISODE = "".join(BLOCKS)
EPISODE_UUID = "abcdef0123456789abcdef0123456789"


def _url() -> str:
    url = os.getenv("MUNNIN_PG_TEST_URL")
    if not url:
        pytest.skip("MUNNIN_PG_TEST_URL not set")
    # A reset fixture must never reach a database that is not a disposable test one.
    assert conninfo_to_dict(url)["dbname"].startswith("pagination_qa_"), (
        "refusing to reset a schema on a database that is not a disposable test database"
    )
    return url


def _seed(url: str) -> None:
    """Provision the world: a fresh schema, one account, one agent, one rolling episode."""
    import psycopg

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
    identity = PostgresIdentityRepository(url)
    identity.ensure_account(Account(user_id="alvi"))
    identity.link_identity(UserIdentity(iss=TEST_ISSUER, sub="alvi", user_id="alvi"))
    repo = PostgresMemoryRepository(url, user_id="alvi")
    repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Meta"))
    repo.insert(
        MemoryRecord(
            uuid=EPISODE_UUID, user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Rolling", project="munnin", full_content=EPISODE,
            created_date="2026-11-10", content_summary="five sub-episodes",
        )
    )


def _app(url: str):
    return build_app(
        Config(
            db_backend="postgres",
            db_url=url,
            user_id="alvi",
            content_root=Path("control-files"),
        ),
        auth=auth_for("alvi"),
    )


async def _http_get(app, path: str, **params):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=bearer()
    ) as client:
        return await client.get(path, params=params)


async def test_a_paged_read_continues_across_faces_over_real_postgres() -> None:
    url = _url()
    _seed(url)
    app = _app(url)
    async with running(app):
        first = (await _http_get(app, f"/api/record/{EPISODE_UUID}", limit=2)).json()
        assert first["content"] == BLOCKS[0] + BLOCKS[1]
        assert (first["blocks_returned"], first["blocks_total"]) == (2, 5)
        assert first["next_cursor"] == "2026-11-10 10.03"

        # Continue on the other face, through the mounted app and its lifespan.
        async with mcp_client_for(app, "test-token-alvi") as mcp:
            second = (
                await mcp.call_tool(
                    "get", {"uuid": EPISODE_UUID, "cursor": first["next_cursor"], "limit": 2}
                )
            ).data
            third = (
                await mcp.call_tool(
                    "get", {"uuid": EPISODE_UUID, "cursor": second["next_cursor"]}
                )
            ).data
        assert second["content"] == BLOCKS[2] + BLOCKS[3]
        assert second["next_cursor"] == "2026-11-10 10.01"
        assert third["content"] == BLOCKS[4]
        assert third["next_cursor"] is None

        # A browse listing answers metadata only, and its count agrees with the page engine.
        browse = (await _http_get(app, "/api/query", agent_id="meta")).json()
        assert browse[0]["blocks_total"] == 5
        assert "content" not in browse[0]

        # An awakening carries page one of the same record, not the whole body.
        latest = (await _http_get(app, "/api/awaken", agent_id="meta")).json()["latest_episode"]
        assert latest["content"] == "".join(BLOCKS[:3])
        assert latest["next_cursor"] == "2026-11-10 10.02"


async def test_a_bad_cursor_is_refused_by_the_store_backed_face() -> None:
    url = _url()
    _seed(url)
    app = _app(url)
    async with running(app):
        response = await _http_get(app, f"/api/record/{EPISODE_UUID}", cursor="2099-01-01 00.00")
    assert response.status_code == 400
    assert "cursor" in response.json()["detail"]
