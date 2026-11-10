"""Integration boundary: snippet search against a real PostgreSQL engine.

**One real dependency**: PostgreSQL. The issuer, the transport and the fixture rows are the
test's own. What is real is the component the SQLite tests cannot stand in for — the
``ts_headline`` excerpt and PostgreSQL's own membership rules.

The database is the disposable one named by ``MUNNIN_PG_TEST_URL``; the schema is reset here
so a re-run proves the same thing from clean. Never point this at a shared or production
database.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.identity import Account
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType, SharedRecord
from munnin.data_repositories.postgres_identity_repository import PostgresIdentityRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository

pytestmark = pytest.mark.postgres


def _url() -> str:
    url = os.getenv("MUNNIN_PG_TEST_URL")
    if not url:
        pytest.skip("MUNNIN_PG_TEST_URL not set")
    assert conninfo_to_dict(url)["dbname"].startswith("pagination_qa_"), (
        "refusing to reset a schema on a database that is not a disposable test database"
    )
    return url


def _seed(url: str) -> None:
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()
    identity = PostgresIdentityRepository(url)
    for tenant in ("alvi", "interviewer"):
        identity.ensure_account(Account(user_id=tenant))
        repo = PostgresMemoryRepository(url, user_id=tenant)
        repo.upsert_agent(Agent(user_id="", agent_id="meta", name="Meta"))
        repo.insert(
            MemoryRecord(
                uuid=f"{tenant[:4]}-body", user_id="", agent_id="meta",
                record_type=RecordType.episode, title="A plain note",
                full_content="the pangolin lives in this body", content_summary="body match",
            )
        )
    mine = PostgresMemoryRepository(url, user_id="alvi")
    mine.insert(
        MemoryRecord(
            uuid="alvi-title", user_id="", agent_id="meta", record_type=RecordType.episode,
            title="pangolin in the title only", full_content="unrelated words here",
            content_summary="title match",
        )
    )
    mine.insert(
        MemoryRecord(
            uuid="alvi-tag", user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Nothing relevant", tags=["pangolin"], full_content="unrelated words too",
            content_summary="tag match",
        )
    )
    mine.insert(
        MemoryRecord(
            uuid="alvi-archived", user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Archived", full_content="pangolin archived", content_summary="archived",
        )
    )
    mine.insert(
        MemoryRecord(
            uuid="alvi-deleted", user_id="", agent_id="meta", record_type=RecordType.episode,
            title="Deleted", full_content="pangolin deleted", content_summary="deleted",
        )
    )
    mine.archive("alvi-archived")
    mine.soft_delete("alvi-deleted")
    mine.insert_shared(
        SharedRecord(
            uuid="fleet-rule", user_id="", record_type=RecordType.reasoning,
            title="Fleet rule", full_content="a pangolin rule for the fleet",
        )
    )


def _service(url: str, tenant: str = "alvi") -> MemoryService:
    return MemoryService(PostgresMemoryRepository(url, user_id=tenant), user_id=tenant)


def test_search_on_real_postgres_reports_membership_and_snippets_without_bodies() -> None:
    url = _url()
    _seed(url)
    mine = _service(url)
    repo = PostgresMemoryRepository(url, user_id="alvi")

    hits = mine.search("pangolin")
    # Membership is unchanged from the full-entity reads the internal path still uses; the
    # service merges both corpora exactly as it did before the projection existed.
    assert {hit["uuid"] for hit in hits} == {
        row.uuid for row in (*repo.search("pangolin"), *repo.search_shared("pangolin"))
    }
    assert {hit["uuid"] for hit in hits} == {
        "alvi-body", "alvi-title", "alvi-tag", "alvi-archived", "fleet-rule",
    }
    for hit in hits:
        assert "content" not in hit and "full_content" not in hit
        assert hit["snippet"].strip()
        # Plain text: the engine's markers are empty, so no HTML reaches a prompt.
        assert "<b>" not in hit["snippet"] and "</b>" not in hit["snippet"]

    by_uuid = {hit["uuid"]: hit for hit in hits}
    assert "pangolin" in by_uuid["alvi-body"]["snippet"]
    # A title-only and a tag-only match still produce a usable window.
    assert by_uuid["alvi-title"]["snippet"]
    assert by_uuid["alvi-tag"]["snippet"]
    # The fleet corpus is labelled by the absence of an owner.
    assert "agent_id" not in by_uuid["fleet-rule"]
    # Archiving keeps a record searchable; deleting removes it.
    assert "alvi-deleted" not in by_uuid


def test_search_does_not_cross_a_tenant_boundary_on_real_postgres() -> None:
    url = _url()
    _seed(url)
    theirs = _service(url, "interviewer")
    assert {hit["uuid"] for hit in theirs.search("pangolin")} == {"inte-body"}
    assert all(hit.get("agent_id") == "meta" for hit in theirs.search("pangolin"))
