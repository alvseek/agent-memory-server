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

# One source of truth for column order.
_COL = (
    "id", "uuid", "user_id", "agent_id", "record_type", "project", "title",
    "tags", "created_date", "modified_date", "archived_date", "deleted_date",
    "full_content",
)
_COLUMNS = ", ".join(_COL)
# Insert set = every column except the autoincrement id.
_INSERT_COLUMNS = ", ".join(_COL[1:])
# Alias-prefixed list for joins (e.g. the FTS search join on `m`).
_M_COLUMNS = ", ".join(f"m.{c}" for c in _COL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_fts_query(text: str) -> str:
    """Turn arbitrary text into a safe FTS5 MATCH string: each whitespace term is
    quoted (embedded ``"`` doubled) and joined with a space (implicit AND). This
    neutralises FTS5 operator syntax so any input (``C++``, ``store≠repo``, stray
    quotes) matches literally instead of erroring or injecting operators."""
    return " ".join('"' + term.replace('"', '""') + '"' for term in text.split())


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

    def edit(
        self,
        uuid: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> MemoryRecord:
        """Edit-tool-parity content edit. Unique-replace by default (raises if the
        substring is absent or ambiguous); ``replace_all=True`` replaces every
        occurrence. Bumps ``modified_date``; FTS re-syncs via the AFTER UPDATE trigger.

        Raises ``LookupError`` if the record is missing/deleted, ``ValueError`` if
        ``old_string`` is not found or (without ``replace_all``) ambiguous."""
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM memory_record "
                "WHERE uuid=? AND user_id=? AND deleted_date IS NULL",
                (uuid, self._user_id),
            ).fetchone()
            if row is None:
                raise LookupError(f"record not found: {uuid}")
            content = row["full_content"] or ""
            count = content.count(old_string)
            if count == 0:
                raise ValueError(f"old_string not found in record {uuid}")
            if count > 1 and not replace_all:
                raise ValueError(
                    f"old_string is ambiguous ({count} occurrences) in {uuid}; "
                    "pass replace_all=True to replace every occurrence"
                )
            new_content = (
                content.replace(old_string, new_string)
                if replace_all
                else content.replace(old_string, new_string, 1)
            )
            conn.execute(
                "UPDATE memory_record SET full_content=?, modified_date=? "
                "WHERE uuid=? AND user_id=?",
                (new_content, _now(), uuid, self._user_id),
            )
            updated = conn.execute(
                f"SELECT {_COLUMNS} FROM memory_record WHERE uuid=? AND user_id=?",
                (uuid, self._user_id),
            ).fetchone()
        return _row_to_record(updated)

    def archive(self, uuid: str) -> None:
        """Set ``archived_date`` (idempotent — first timestamp preserved)."""
        self._set_lifecycle("archived_date", uuid)

    def soft_delete(self, uuid: str) -> None:
        """Set ``deleted_date`` tombstone (idempotent)."""
        self._set_lifecycle("deleted_date", uuid)

    def _set_lifecycle(self, column: str, uuid: str) -> None:
        # `column` is a literal constant from archive/soft_delete, never caller input.
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE memory_record SET {column}=COALESCE({column}, ?) "
                "WHERE uuid=? AND user_id=?",
                (_now(), uuid, self._user_id),
            )
            if cur.rowcount == 0:
                raise LookupError(f"record not found: {uuid}")

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
        """Full-text search (FTS5) over content + title + tags. Safe plain-text
        (see ``_to_fts_query``); ``user_id``-stamped; soft-deleted excluded; archived
        included by default (still searchable). Ranked most-relevant-first (bm25)."""
        match = _to_fts_query(text)
        if not match:
            return []
        where = ["memory_fts MATCH ?", "m.user_id = ?", "m.deleted_date IS NULL"]
        params: list[object] = [match, self._user_id]
        if not include_archived:
            where.append("m.archived_date IS NULL")
        sql = (
            f"SELECT {_M_COLUMNS} FROM memory_fts "
            "JOIN memory_record m ON m.id = memory_fts.rowid "
            f"WHERE {' AND '.join(where)} ORDER BY memory_fts.rank"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]


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
