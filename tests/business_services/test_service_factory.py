"""Per-tenant services over one database.

This is the first form of the isolation proof: not that a query filters correctly, but
that two services handed out by the same factory cannot reach each other's records at
all. Everything the adapters do rests on this holding.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.service_factory import ServiceFactory
from munnin.data_entities.memory_record import Agent, RecordType
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from tests.conftest import seed_account


def _factory(tmp_path: Path, *tenants: str) -> ServiceFactory:
    db = tmp_path / "m.db"
    for tenant in tenants:
        seed_account(db, tenant)
        SqliteMemoryRepository(db, user_id=tenant).upsert_agent(
            Agent(user_id="", agent_id="meta", name="Claude Meta")
        )
    return ServiceFactory(db)


def _write(svc, uuid: str, content: str) -> None:
    svc.insert(
        agent_id="meta", record_type=RecordType.episode.value, content=content, uuid=uuid
    )


def test_two_tenants_cannot_see_each_others_records(tmp_path: Path) -> None:
    """The claim the whole plan exists to make true."""
    factory = _factory(tmp_path, "alvi", "interviewer")
    mine = factory.for_user("alvi")
    theirs = factory.for_user("interviewer")

    _write(mine, "mine-1", "my private memory")

    assert mine.get("mine-1") is not None
    assert theirs.get("mine-1") is None


def test_a_second_tenant_cannot_reach_the_record_by_query(tmp_path: Path) -> None:
    factory = _factory(tmp_path, "alvi", "interviewer")
    _write(factory.for_user("alvi"), "mine-2", "my private memory")
    assert factory.for_user("interviewer").query() == []


def test_a_second_tenant_cannot_reach_the_record_by_search(tmp_path: Path) -> None:
    """Search reaches records through the full-text index rather than the browse query,
    so it is a separate path and the likeliest place for a leak to hide."""
    factory = _factory(tmp_path, "alvi", "interviewer")
    _write(factory.for_user("alvi"), "mine-3", "distinctive phrase pangolin")
    assert factory.for_user("alvi").search("pangolin")
    assert factory.for_user("interviewer").search("pangolin") == []


def test_each_tenant_sees_only_its_own_agents(tmp_path: Path) -> None:
    factory = _factory(tmp_path, "alvi", "interviewer")
    SqliteMemoryRepository(tmp_path / "m.db", user_id="alvi").upsert_agent(
        Agent(user_id="", agent_id="aquazone", name="Claude Aquazone")
    )
    mine = [a["agent_id"] for a in factory.for_user("alvi").list_agents()]
    theirs = [a["agent_id"] for a in factory.for_user("interviewer").list_agents()]
    assert mine == ["aquazone", "meta"]
    assert theirs == ["meta"]


def test_the_same_tenant_gets_the_same_service(tmp_path: Path) -> None:
    """Kept per tenant so the schema is not re-applied on every request."""
    factory = _factory(tmp_path, "alvi")
    assert factory.for_user("alvi") is factory.for_user("alvi")


def test_different_tenants_get_different_services(tmp_path: Path) -> None:
    factory = _factory(tmp_path, "alvi", "interviewer")
    assert factory.for_user("alvi") is not factory.for_user("interviewer")
