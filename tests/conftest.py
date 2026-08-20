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

from munnin.data_entities.memory_record import Agent, MemoryRecord
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


class AutoAgentRepository(SqliteMemoryRepository):
    """A repository that creates an agent row on demand before inserting its memory."""

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        self.upsert_agent(
            Agent(
                user_id=self._user_id,
                agent_id=record.agent_id,
                name=f"Agent {record.agent_id}",
                role=f"{record.agent_id} agent",
            )
        )
        return super().insert(record)
