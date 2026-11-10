"""Per-tenant services over one database.

This is the first form of the isolation proof: not that a query filters correctly, but
that two services handed out by the same factory cannot reach each other's records at
all. Everything the adapters do rests on this holding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.business_services.memory_service import MemoryService
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
        content_summary="a one-line summary of this record",
        agent_id="meta", record_type=RecordType.episode.value, content=content, uuid=uuid
    )


def test_two_tenants_cannot_see_each_others_records(tmp_path: Path) -> None:
    """The claim the whole plan exists to make true."""
    factory = _factory(tmp_path, "alvi", "interviewer")
    mine = factory.for_user("alvi")
    theirs = factory.for_user("interviewer")

    _write(mine, "fedcba00123443219876123456789abc", "my private memory")

    assert mine.get("fedcba00123443219876123456789abc") is not None
    assert theirs.get("fedcba00123443219876123456789abc") is None


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


# --- the page ceiling is policy, not data ---------------------------------------------------

_THREE_GROUPS = (
    "### 2026-11-10 10.03 - three\n\n" + "c" * 60 + "\n"
    "### 2026-11-10 10.02 - two\n\n" + "b" * 60 + "\n"
    "### 2026-11-10 10.01 - one\n\n" + "a" * 60 + "\n"
)


def test_one_ceiling_serves_every_tenant_without_crossing_them(tmp_path: Path) -> None:
    """The setting is a transport fact, so every tenant gets the same page boundary — and
    still reaches only its own row. Both halves asserted together: a shared policy that
    leaked rows would be as wrong as a per-tenant policy."""
    db = tmp_path / "m.db"
    for tenant, uuid in (
        ("alvi", "aaaaaa00000000000000000000000001"),
        ("interviewer", "bbbbbb00000000000000000000000002"),
    ):
        seed_account(db, tenant)
        SqliteMemoryRepository(db, user_id=tenant).upsert_agent(
            Agent(user_id="", agent_id="meta", name="Claude Meta")
        )
    factory = ServiceFactory(db, max_body_bytes=40)
    for tenant, uuid in (
        ("alvi", "aaaaaa00000000000000000000000001"),
        ("interviewer", "bbbbbb00000000000000000000000002"),
    ):
        factory.for_user(tenant).insert(
            content_summary="a one-line summary of this record",
            agent_id="meta",
            record_type=RecordType.episode.value,
            content=_THREE_GROUPS,
            uuid=uuid,
        )

    mine = factory.for_user("alvi").get("aaaaaa00000000000000000000000001")
    theirs = factory.for_user("interviewer").get("bbbbbb00000000000000000000000002")
    assert mine["blocks_returned"] == theirs["blocks_returned"] == 1
    assert mine["blocks_total"] == theirs["blocks_total"] == 3
    assert mine["next_cursor"] == theirs["next_cursor"] == "2026-11-10 10.02"
    assert factory.for_user("alvi").get("bbbbbb00000000000000000000000002") is None


def test_the_ceiling_is_injected_not_looked_up_ambiently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two services over the same store page differently, and an ambient environment value
    changes neither: the number is a constructor argument, which is what makes it testable."""
    db = tmp_path / "m.db"
    seed_account(db, "alvi")
    SqliteMemoryRepository(db, user_id="alvi").upsert_agent(
        Agent(user_id="", agent_id="meta", name="Claude Meta")
    )
    monkeypatch.setenv("MUNNIN_MAX_BODY_BYTES", "1")
    repo = SqliteMemoryRepository(db, user_id="alvi")
    wide = MemoryService(repo, user_id="alvi", max_body_bytes=10_000)
    narrow = MemoryService(repo, user_id="alvi", max_body_bytes=40)
    wide.insert(
        content_summary="a one-line summary of this record",
        agent_id="meta",
        record_type=RecordType.episode.value,
        content=_THREE_GROUPS,
        uuid="cccccc00000000000000000000000003",
    )

    whole = wide.get("cccccc00000000000000000000000003")
    paged = narrow.get("cccccc00000000000000000000000003")
    assert whole["blocks_returned"] == whole["blocks_total"] == 3
    assert whole["next_cursor"] is None
    assert paged["blocks_returned"] == 1 and paged["next_cursor"] == "2026-11-10 10.02"


def test_a_repository_argument_can_never_supply_the_ceiling() -> None:
    """The ceiling is not a record field and not a caller argument: a bad constructor value
    is refused rather than coerced."""
    with pytest.raises(ValueError):
        ServiceFactory(Path("unused.db"), max_body_bytes=0)
    with pytest.raises(ValueError):
        ServiceFactory(Path("unused.db"), max_body_bytes=True)
