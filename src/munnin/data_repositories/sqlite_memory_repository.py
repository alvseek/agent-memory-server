"""SQLite implementation of ``MemoryRepository`` (Valaskjalf/memory).

SP-1 (M0 read slice) implements ``insert`` / ``get`` / ``query`` — enough to
bootstrap via the importer and assemble an awaken payload. ``edit`` / ``archive``
/ ``soft_delete`` / ``search`` land in SP-2.

Design: one writer per file (WAL); ``user_id`` stamped server-side and injected on
every query (never a method parameter — the load-bearing tenancy rule). Connection
per operation for thread-safety under the ASGI threadpool (SQLite open is
microseconds; WAL persists across connections). NOTE: therefore a ``:memory:``
db_path will not persist between ops — tests use a temp file.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from munnin.data_entities.memory_record import MemoryRecord, RecordType

_SCHEMA_SQL = (
    Path(__file__).resolve().parent.parent / "data_entities" / "schema.sql"
).read_text(encoding="utf-8")

_COLUMNS = (
    "id, uuid, user_id, agent_id, record_type, project, title, tags, "
    "created_date, modified_date, archived_date, deleted_date, full_content"
)
# Insert set = every column except the autoincrement id.
_INSERT_COLUMNS = (
    "uuid, user_id, agent_id, record_type, project, title, tags, "
    "created_date, modified_date, archived_date, deleted_date, full_content"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteMemoryRepository:
    """Implements ``MemoryRepository`` (structural)."""

    def __init__(self, db_path: Path, *, user_id: str) -> None:
        self._db_path = Path(db_path)
        # Stamped server-side from config/auth — NEVER read from agent input.
        self._user_id = user_id
        self._ensured = False

    # --- connection / schema ---

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        if not self._ensured:
            conn.executescript(_SCHEMA_SQL)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- writes (SP-1: insert only) ---

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new item. Idempotent UPSERT on ``uuid`` — a re-import of the
        same content is a no-op (updates the row in place, preserves ``created_date``)."""
        created = record.created_date or _now()
        modified = record.modified_date or created
        rtype = record.record_type.value
        tags = json.dumps(record.tags or [])
        with self._conn() as conn:
            conn.execute(
                f"""
                INSERT INTO memory_record
                    ({_INSERT_COLUMNS})
                VALUES (:uuid, :user_id, :agent_id, :record_type, :project, :title,
                        :tags, :created_date, :modified_date, :archived_date,
                        :deleted_date, :full_content)
                ON CONFLICT(uuid) DO UPDATE SET
                    agent_id=excluded.agent_id, record_type=excluded.record_type,
                    project=excluded.project, title=excluded.title, tags=excluded.tags,
                    modified_date=excluded.modified_date, archived_date=excluded.archived_date,
                    deleted_date=excluded.deleted_date, full_content=excluded.full_content
                """,
                {
                    "uuid": record.uuid,
                    "user_id": self._user_id,
                    "agent_id": record.agent_id,
                    "record_type": rtype,
                    "project": record.project,
                    "title": record.title,
                    "tags": tags,
                    "created_date": created,
                    "modified_date": modified,
                    "archived_date": record.archived_date,
                    "deleted_date": record.deleted_date,
                    "full_content": record.full_content,
                },
            )
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM memory_record WHERE uuid=? AND user_id=?",
                (record.uuid, self._user_id),
            ).fetchone()
        return _row_to_record(row)

    def edit(self, uuid: str, old_string: str, new_string: str) -> MemoryRecord:
        raise NotImplementedError("SP-2 (Store Write + Search)")

    def archive(self, uuid: str) -> None:
        raise NotImplementedError("SP-2 (Store Write + Search)")

    def soft_delete(self, uuid: str) -> None:
        raise NotImplementedError("SP-2 (Store Write + Search)")

    # --- reads ---

    def get(self, uuid: str) -> MemoryRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM memory_record "
                "WHERE uuid=? AND user_id=? AND deleted_date IS NULL",
                (uuid, self._user_id),
            ).fetchone()
        return _row_to_record(row) if row else None

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[MemoryRecord]:
        # Tenancy + lifecycle invariants injected on every read.
        where = ["user_id = ?", "deleted_date IS NULL"]
        params: list[object] = [self._user_id]
        if not include_archived:
            where.append("archived_date IS NULL")
        if agent_id is not None:
            where.append("agent_id = ?")
            params.append(agent_id)
        if record_type is not None:
            where.append("record_type = ?")
            params.append(record_type.value)
        if project is not None:
            where.append("project = ?")
            params.append(project)
        sql = (
            f"SELECT {_COLUMNS} FROM memory_record "
            f"WHERE {' AND '.join(where)} ORDER BY id"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        raise NotImplementedError("SP-2 (Store Write + Search)")


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        uuid=row["uuid"],
        user_id=row["user_id"],
        agent_id=row["agent_id"],
        record_type=RecordType(row["record_type"]),
        project=row["project"],
        title=row["title"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        created_date=row["created_date"],
        modified_date=row["modified_date"],
        archived_date=row["archived_date"],
        deleted_date=row["deleted_date"],
        full_content=row["full_content"],
    )
