"""Both real adapters project shared knowledge, while get keeps the original body."""
from pathlib import Path

import httpx
from fastmcp import Client
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.content.loader import ContentLoader
from munnin.data_entities.memory_record import RecordType, SharedRecord
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import auth_for, bearer, mcp_for, seed_agent, seed_login


async def test_both_faces_send_index_and_can_read_the_body(tmp_path):
    db = tmp_path / "index.db"
    seed_agent(db)
    seed_login(db)
    repo = SqliteMemoryRepository(db, user_id="alvi")
    uid = "11111111111111111111111111111111"
    repo.insert_shared(SharedRecord(
        uuid=uid, user_id="alvi", record_type=RecordType.knowledge,
        title="Example", content_summary="Relevant reference", full_content="original body",
    ))
    app = build_app(
        Config(db_path=db, content_root=Path(__file__).resolve().parents[2] / "control-files"),
        auth=auth_for("alvi"),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=bearer(),
    ) as client:
        response = await client.get("/api/awaken", params={"agent_id": "meta"})
        assert response.status_code == 200
        http_payload = response.json()
        assert (await client.get(f"/api/record/{uid}")).json()["content"] == "original body"
    async with Client(mcp_for(db)) as client:
        mcp_payload = (await client.call_tool("awaken", {"domain": "meta"})).data
        assert (await client.call_tool("get", {"uuid": uid})).data["content"] == "original body"
    assert http_payload["shared"] == mcp_payload["shared"]
    assert "knowledge" not in http_payload["shared"]
    entry, = http_payload["shared"]["knowledge_index"]
    assert entry["uuid"] == uid and entry["content_summary"] == "Relevant reference"
    assert "content" not in entry


def test_served_instructions_do_not_reload_all_shared_bodies():
    loader = ContentLoader(Path(__file__).resolve().parents[2] / "control-files")
    awaken = loader.get_prompt("awaken-agent")
    knowledge = loader.get_prompt("load-knowledge")
    assert "shared.knowledge_index" in awaken
    assert "do not fetch every body" in awaken
    assert "empty index is valid" in awaken
    assert "shared.knowledge_index" in knowledge
    assert "Never include another agent's private rows" in knowledge
