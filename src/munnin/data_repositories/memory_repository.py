"""The store seam (DI boundary).

The core depends on this Protocol, never on a concrete database. v1 ships
``SqliteMemoryRepository``; a future ``PostgresMemoryRepository`` swaps in via DI
with zero core changes (rite Decision 3).

Note: ``user_id`` is NOT a parameter here — it is stamped server-side and applied
by the implementation on every query (the load-bearing tenancy rule). Callers can
never pass a tenant id in.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType, SharedRecord


class MemoryRepository(Protocol):
    """Read/write API over Valaskjalf/memory. Write surface mirrors the Edit tool."""

    # --- writes (Edit-tool parity) ---
    def insert(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new agent-owned item. Idempotent on ``uuid`` (upsert). The named
        agent must already exist — the store enforces it with a foreign key."""
        ...

    def insert_shared(self, record: SharedRecord) -> SharedRecord:
        """Append a new fleet-shared item (reasoning or knowledge, owned by no agent).
        Idempotent on ``uuid`` (upsert).

        The only write that needs a shared twin: every other write addresses an existing
        record, whose uuid already says which table holds it, while an insert is choosing
        where the row goes and nothing in the arguments can imply that."""
        ...

    def edit(
        self,
        uuid: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> SharedRecord:
        """Targeted string replace inside a record's ``full_content`` (server-side
        read-replace-write). Per-word/line granularity — token-identical to the Edit tool.
        Unique-replace by default (raises if absent/ambiguous); ``replace_all=True``
        replaces every occurrence."""
        ...

    def append(self, uuid: str, text: str) -> SharedRecord:
        """Add ``text`` verbatim to the END of a record's ``full_content`` (caller
        controls any leading newline). Bumps ``modified_date``; raises ``LookupError``
        if the record is missing/deleted."""
        ...

    def prepend(self, uuid: str, text: str) -> SharedRecord:
        """Add ``text`` verbatim to the START of a record's ``full_content`` (caller
        controls any trailing newline). Bumps ``modified_date``; raises ``LookupError``
        if the record is missing/deleted."""
        ...

    def multi_edit(
        self, uuid: str, edits: Sequence[tuple[str, str, bool]]
    ) -> SharedRecord:
        """Apply a sequence of ``(old_string, new_string, replace_all)`` edits to one
        record, in order, **atomically** — each edit operates on the result of the
        previous, and if ANY edit fails nothing is written. Bumps ``modified_date``.
        Raises ``LookupError`` if missing/deleted, ``ValueError`` if the list is empty or
        any edit's ``old_string`` is absent/ambiguous."""
        ...

    def archive(self, uuid: str) -> None:
        """Set ``archived_date`` — out of the hot index, still searchable on demand."""
        ...

    def soft_delete(self, uuid: str) -> None:
        """Set ``deleted_date`` — tombstone, excluded from all reads."""
        ...

    # --- reads ---
    def get(self, uuid: str) -> SharedRecord | None:
        """Fetch one record by uuid (excludes soft-deleted)."""
        ...

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[SharedRecord]:
        """Filter memory by exact field values, returning whole records with bodies.

        Naming an ``agent_id`` reads that agent's memory alone; omitting it means all
        memory this tenant can see, which spans both tables, so fleet-shared rows are
        included. The result is self-labelling — an agent's row is a ``MemoryRecord``
        carrying ``agent_id``, a fleet row is a ``SharedRecord`` with no such field."""
        ...

    def query_shared(
        self,
        *,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[SharedRecord]:
        """Fleet-shared memory only, filtered by exact field values, bodies included.
        There is no ``agent_id`` parameter because the table has no such column."""
        ...

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        """Full-text search (FTS5) over agent memory's content + title + tags. Fleet
        memory has its own index and its own method — FTS5 external-content binds one
        index to one table, so the caller merges the two groups."""
        ...

    def search_shared(
        self, text: str, *, include_archived: bool = True
    ) -> Sequence[SharedRecord]:
        """Full-text search (FTS5) over fleet-shared memory. bm25 ranks per corpus, so
        scores from here are not strictly comparable with ``search``'s."""
        ...

    # --- the agent entity ---
    def upsert_agent(self, agent: Agent) -> Agent:
        """Create or update one agent. Idempotent on ``(user_id, agent_id)``, so a
        re-import refreshes name/role/uuid and preserves ``created_date``."""
        ...

    def create_agent(self, agent: Agent) -> Agent:
        """Create one agent, raising ``ValueError`` if the domain is already taken.

        The served twin of ``upsert_agent``: upsert refreshes an existing agent, which
        the importer needs and a caller must not have, or one agent could quietly rewrite
        another's identity."""
        ...

    def list_agents(self) -> Sequence[Agent]:
        """Every agent in this tenant, sorted by domain. Reads the entity table: an
        agent is listed because it has a row, not because memory mentions it — so a
        newly created agent with no memory yet still appears, and enumeration no
        longer depends on a DISTINCT over memory items."""
        ...
