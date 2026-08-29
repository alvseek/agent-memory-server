"""Shared test infrastructure.

The store enforces a chain of ownership: a memory record names an agent, and an agent
names a tenant. Both links are foreign keys, so an insert needs its agent to exist, and
an agent needs its `account` row to exist. Both are real and wanted constraints, and
neither is what most tests are about — a test for `append` or for FTS ranking should not
have to restate two unrelated preconditions on every fixture.

`seed_account` and `AutoAgentRepository` supply them. Both are **test doubles only**: the
foreign keys themselves are exercised against the real `SqliteMemoryRepository` in
`tests/data_repositories/test_foreign_keys.py`, and the importer's own tenant and agent
creation is exercised against the real class in `tests/data_migrations/`. Anything
asserting *who creates account or agent rows* must use the real class, or it proves
nothing.

`seed_account` writes raw SQL rather than going through a repository, for the same reason
`test_foreign_keys.py` does: a helper that leans on the production write path stops being
able to set up a test *of* that path.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from munnin.api_mcp.server import build_mcp
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.tenant_resolver import StaticTenantResolver
from munnin.content.loader import ContentLoader
from munnin.data_entities.memory_record import Agent, MemoryRecord
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def mcp_for(
    db: Path, *, user_id: str = "alvi", content: ContentLoader | None = None
) -> FastMCP:
    """Build the MCP face the way ``build_app`` does — over a per-tenant factory.

    Tests used to hand ``build_mcp`` a service they had constructed, which stopped being
    possible when the tenant moved from the process to the request. Going through the
    factory here keeps every face test on the same wiring the server actually runs."""
    seed_account(db, user_id)
    return build_mcp(ServiceFactory(db), StaticTenantResolver(user_id), content)


def seed_account(db: Path, user_id: str = "alvi") -> None:
    """Create the tenant row ``user_id`` in ``db``, so an agent may reference it.

    Idempotent, and safe against an empty path: the schema is applied by the repository's
    own connection helper, which is also what enables the foreign keys."""
    repo = SqliteMemoryRepository(db, user_id=user_id)
    with repo._conn() as conn:  # noqa: SLF001 — deliberately bypassing the write path
        conn.execute(
            "INSERT OR IGNORE INTO account (user_id, created_date) VALUES (?, '2026-08-28')",
            (user_id,),
        )


def seed_agent(
    db: Path, agent_id: str = "meta", *, user_id: str = "alvi", **fields: str
) -> None:
    """Create an agent row directly in ``db``, for tests that reach the store through a
    face rather than through a repository they constructed.

    ``build_app`` wires the **real** repository, so an API-level test cannot use the
    auto-creating double — and it should not want to: "the agent must exist first" is the
    precondition under test everywhere else, and a face test that quietly invented one
    would be asserting against a store no deployment can produce."""
    seed_account(db, user_id)
    SqliteMemoryRepository(db, user_id=user_id).upsert_agent(
        Agent(user_id="", agent_id=agent_id, **fields)
    )


class AutoAgentRepository(SqliteMemoryRepository):
    """A repository that creates an agent row on demand before inserting its memory.

    It fills the gap **only when nothing else has**. `upsert_agent` refreshes name and
    role by design, so an unconditional call here would silently overwrite whatever a
    real pass-1 import had just written with a placeholder — the double would then be
    destroying the very fields the test is about.

    It also ensures the tenant row the agent will reference, since an agent cannot exist
    without one. Same rule: supplied once, and only because it is a precondition rather
    than a subject."""

    def __init__(self, db_path: Path, *, user_id: str) -> None:
        super().__init__(db_path, user_id=user_id)
        seed_account(db_path, user_id)
        self._seen: set[str] = set()

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        seen = self._seen
        if record.agent_id not in seen:
            # Checked once per distinct domain, not once per record: a fleet import
            # writes thousands of rows and this repository opens a connection per call.
            if not any(a.agent_id == record.agent_id for a in self.list_agents()):
                self.upsert_agent(
                    Agent(
                        user_id=self._user_id,
                        agent_id=record.agent_id,
                        name=f"Agent {record.agent_id}",
                        role=f"{record.agent_id} agent",
                    )
                )
            seen.add(record.agent_id)
        return super().insert(record)
