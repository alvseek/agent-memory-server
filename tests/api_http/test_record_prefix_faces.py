"""MCP and HTTP accept the same record references and refuse ambiguous writes."""

from dataclasses import asdict
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from httpx import ASGITransport

from munnin.app import build_app
from munnin.configuration.config import Config
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import auth_for, bearer, mcp_for, seed_agent, seed_login
from tests.data_repositories.test_record_prefix import A, B, seed

CF = Path(__file__).resolve().parents[2] / "control-files"
REQUESTS = [
    ("get", None),
    ("edit", {"old_string": "original", "new_string": "changed"}),
    ("append", {"text": " tail"}),
    ("prepend", {"text": "head "}),
    ("multi_edit", {"edits": [{"old_string": "original", "new_string": "changed"}]}),
    ("edit_metadata", {"title": "changed"}),
    ("archive", {}), ("unarchive", {}), ("soft_delete", {}),
]


def setup(tmp_path):
    db = tmp_path / "prefix.db"
    seed_agent(db)
    seed_login(db)
    repo = SqliteMemoryRepository(db, user_id="alvi")
    seed(repo)
    app = build_app(Config(db_path=db, content_root=CF), auth=auth_for("alvi"))
    return db, repo, app


async def http_call(client, operation, body, reference):
    if operation == "get":
        return await client.get(f"/api/record/{reference}")
    return await client.post(f"/api/{operation.replace('_', '-')}",
                             json={"uuid": reference, **body})


@pytest.mark.parametrize("operation,body", REQUESTS)
@pytest.mark.parametrize("face", ["http", "mcp"])
async def test_unique_prefix_success(tmp_path, operation, body, face):
    db, repo, app = setup(tmp_path)
    if operation == "unarchive":
        repo.archive(A)
    if face == "http":
        async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                    base_url="http://test", headers=bearer()) as client:
            response = await http_call(client, operation, body, "AB-CD-EF")
            assert response.status_code == 200, response.text
            result = response.json()
    else:
        async with Client(mcp_for(db)) as client:
            result = (await client.call_tool(operation, {"uuid": "AB-CD-EF", **(body or {})})).data
    assert result["uuid"] == A


@pytest.mark.parametrize("operation,body", REQUESTS)
@pytest.mark.parametrize("face", ["http", "mcp"])
async def test_ambiguity_error_and_no_write(tmp_path, operation, body, face):
    db, repo, app = setup(tmp_path)
    seed(repo, B, shared=True)
    before = [asdict(repo.get(uid)) for uid in (A, B)]
    if face == "http":
        async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                    base_url="http://test", headers=bearer()) as client:
            response = await http_call(client, operation, body, "abcdef")
            assert response.status_code == 409, response.text
            detail = response.json()["detail"]
            assert detail["error"] == "ambiguous_uuid"
            assert {row["uuid"] for row in detail["candidates"]} == {A, B}
            assert all(row["title"] for row in detail["candidates"])
    else:
        async with Client(mcp_for(db)) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(operation, {"uuid": "abcdef", **(body or {})})
            assert "ambiguous UUID" in str(caught.value)
            assert A in str(caught.value) and B in str(caught.value)
    assert [asdict(repo.get(uid)) for uid in (A, B)] == before


@pytest.mark.parametrize("operation,body", REQUESTS)
async def test_invalid_prefix_is_http_400_not_500(tmp_path, operation, body):
    _, _, app = setup(tmp_path)
    async with httpx.AsyncClient(transport=ASGITransport(app=app),
                                base_url="http://test", headers=bearer()) as client:
        response = await http_call(client, operation, body, "abcde")
        assert response.status_code == 400, response.text
