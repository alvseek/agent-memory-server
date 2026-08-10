"""SQLite implementation of MemoryRepository — STUB (Phase 4 scaffold).

Real schema (uniform record + FTS5 external-content + browse index) and method
bodies land in Phase 5 (Core Dev). This stub establishes the DI shape and the
server-side ``user_id`` stamping seam.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from munnin.data_entities.memory_record import MemoryRecord, RecordType


class SqliteMemoryRepository:
    """Implements ``MemoryRepository`` (structural). One writer per file (WAL)."""

    def __init__(self, db_path: Path, *, user_id: str) -> None:
        self._db_path = db_path
        # Stamped server-side from auth/config — NEVER read from agent input.
        self._user_id = user_id

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def edit(self, uuid: str, old_string: str, new_string: str) -> MemoryRecord:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def archive(self, uuid: str) -> None:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def soft_delete(self, uuid: str) -> None:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def get(self, uuid: str) -> MemoryRecord | None:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[MemoryRecord]:
        raise NotImplementedError("Phase 5 (Core Dev)")

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        raise NotImplementedError("Phase 5 (Core Dev)")
