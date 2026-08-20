"""Shared test infrastructure.

`memory_record.agent_id` now carries a foreign key to the `agent` table, so every insert
needs its agent to exist first. That is a real and wanted constraint, but it is not what
most tests are about: a test for `append` or for FTS ranking should not have to restate
an unrelated precondition on every fixture.

`AutoAgentRepository` supplies it. It is a **test double only** — the foreign key itself
is exercised against the real `SqliteMemoryRepository` in
`tests/data_repositories/test_foreign_keys.py`, and the importer's own two-pass agent
creation is exercised against the real class in `tests/data_migrations/`. Anything
asserting *who creates agent rows* must use the real class, or it proves nothing.
"""

from __future__ import annotations

from pathlib import Path

from munnin.data_entities.memory_record import Agent, MemoryRecord
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def seed_agent(
    db: Path, agent_id: str = "meta", *, user_id: str = "alvi", **fields: str
) -> None:
    """Create an agent row directly in ``db``, for tests that reach the store through a
    face rather than through a repository they constructed.

    ``build_app`` wires the **real** repository, so an API-level test cannot use the
    auto-creating double — and it should not want to: "the agent must exist first" is the
    precondition under test everywhere else, and a face test that quietly invented one
    would be asserting against a store no deployment can produce."""
    SqliteMemoryRepository(db, user_id=user_id).upsert_agent(
        Agent(user_id="", agent_id=agent_id, **fields)
    )


class AutoAgentRepository(SqliteMemoryRepository):
    """A repository that creates an agent row on demand before inserting its memory.

    It fills the gap **only when nothing else has**. `upsert_agent` refreshes name and
    role by design, so an unconditional call here would silently overwrite whatever a
    real pass-1 import had just written with a placeholder — the double would then be
    destroying the very fields the test is about."""

    def __init__(self, db_path: Path, *, user_id: str) -> None:
        super().__init__(db_path, user_id=user_id)
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
