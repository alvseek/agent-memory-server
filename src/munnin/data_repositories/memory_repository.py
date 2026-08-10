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

from munnin.data_entities.memory_record import MemoryRecord, RecordType


class MemoryRepository(Protocol):
    """Read/write API over Valaskjalf/memory. Write surface mirrors the Edit tool."""

    # --- writes (Edit-tool parity) ---
    def insert(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new item. Idempotent on ``uuid`` (upsert)."""
        ...

    def edit(self, uuid: str, old_string: str, new_string: str) -> MemoryRecord:
        """Targeted string replace inside a record's ``full_content`` (server-side
        read-replace-write). Per-word/line granularity — token-identical to the Edit tool."""
        ...

    def archive(self, uuid: str) -> None:
        """Set ``archived_date`` — out of the hot index, still searchable on demand."""
        ...

    def soft_delete(self, uuid: str) -> None:
        """Set ``deleted_date`` — tombstone, excluded from all reads."""
        ...

    # --- reads ---
    def get(self, uuid: str) -> MemoryRecord | None:
        """Fetch one record by uuid (excludes soft-deleted)."""
        ...

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[MemoryRecord]:
        """Browse the index (metadata projection; bodies included)."""
        ...

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        """Full-text search (FTS5) over content + title + tags."""
        ...
