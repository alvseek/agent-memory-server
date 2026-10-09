"""PostgreSQL implementation of ``MemoryRepository`` (Valaskjalf/memory).

The Postgres twin of ``SqliteMemoryRepository``. Same contract, same server-side tenancy
stamping, same lifecycle columns, same upsert-on-``uuid`` semantics. What differs:

- **Driver and SQL dialect**: ``psycopg`` (sync), ``%s`` placeholders, ``ON CONFLICT``.
- **Errors are typed**: SQLite matched on message strings; Postgres raises
  ``UniqueViolation`` / ``ForeignKeyViolation`` / ``CheckViolation``, which are translated
  into ``ValueError`` so both faces report bad input rather than a broken server.
- **Full text is a column, not a table**: ``search_tsv`` is a generated ``tsvector`` on the
  row, so there is no external-content index to join and no sync triggers; search filters
  and ranks directly. ``plainto_tsquery('simple', …)`` is the closest analogue to FTS5's
  no-stemming, literal-AND behaviour (high-wizard decision 3, 10).

Connections are opened per operation, mirroring the SQLite implementation; a connection
pool is a later optimization, not a correctness need at this load (see the plan log).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from munnin.data_entities.memory_record import (
    SHARED_RECORD_TYPES,
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
    validate_domain,
)
from munnin.data_entities.postgres_migrations import ensure_schema

# One source of truth for column order (identical to the SQLite repository).
_COL = (
    "id", "uuid", "user_id", "agent_id", "record_type", "project", "title",
    "tags", "created_date", "modified_date", "archived_date", "deleted_date",
    "full_content",
)
_COLUMNS = ", ".join(_COL)
_SHARED_COL = tuple(c for c in _COL if c != "agent_id")
_SHARED_COLUMNS = ", ".join(_SHARED_COL)
_TABLES: dict[str, str] = {"memory_record": _COLUMNS, "shared_record": _SHARED_COLUMNS}
_SHARED_TYPE_NAMES = [f"{t.value!r}" for t in SHARED_RECORD_TYPES]
_SHARED_RECORD_TYPES = (
    " or ".join(_SHARED_TYPE_NAMES)
    if len(_SHARED_TYPE_NAMES) < 3
    else f"{', '.join(_SHARED_TYPE_NAMES[:-1])} or {_SHARED_TYPE_NAMES[-1]}"
)
_AGENT_COL = ("user_id", "agent_id", "name", "role", "uuid", "created_date")
_AGENT_COLUMNS = ", ".join(_AGENT_COL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PostgresMemoryRepository:
    """Implements ``MemoryRepository`` (structural) over PostgreSQL."""

    def __init__(self, dsn: str, *, user_id: str) -> None:
        self._dsn = dsn
        # Stamped server-side from config/auth — NEVER read from agent input.
        self._user_id = user_id
        self._ensured = False

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self._dsn, row_factory=dict_row)
        if not self._ensured:
            ensure_schema(conn)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- writes (Edit-tool parity) ---

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new agent-owned item. Idempotent UPSERT on ``uuid``."""
        created = record.created_date or _now()
        modified = record.modified_date or created
        with self._conn() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO memory_record
                        (uuid, user_id, agent_id, record_type, project, title,
                         tags, created_date, modified_date, archived_date,
                         deleted_date, full_content)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        agent_id=excluded.agent_id, record_type=excluded.record_type,
                        project=excluded.project, title=excluded.title, tags=excluded.tags,
                        modified_date=excluded.modified_date,
                        archived_date=excluded.archived_date,
                        deleted_date=excluded.deleted_date,
                        full_content=excluded.full_content
                    """,
                    (
                        record.uuid, self._user_id, record.agent_id,
                        record.record_type.value, record.project, record.title,
                        json.dumps(record.tags or []), created, modified,
                        record.archived_date, record.deleted_date, record.full_content,
                    ),
                )
            except psycopg.errors.ForeignKeyViolation as exc:
                raise ValueError(
                    f"no agent {record.agent_id!r} exists for this account. Create it "
                    "first, then insert its memory."
                ) from exc
            cur.execute(
                f"SELECT {_COLUMNS} FROM memory_record WHERE uuid=%s AND user_id=%s",
                (record.uuid, self._user_id),
            )
            row = cur.fetchone()
        return _row_to_record(row)

    def insert_shared(self, record: SharedRecord) -> SharedRecord:
        """Append a new fleet-shared item (reasoning, knowledge, ras, user_profile)."""
        created = record.created_date or _now()
        modified = record.modified_date or created
        with self._conn() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO shared_record
                        (uuid, user_id, record_type, project, title,
                         tags, created_date, modified_date, archived_date,
                         deleted_date, full_content)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        record_type=excluded.record_type,
                        project=excluded.project, title=excluded.title, tags=excluded.tags,
                        modified_date=excluded.modified_date,
                        archived_date=excluded.archived_date,
                        deleted_date=excluded.deleted_date,
                        full_content=excluded.full_content
                    """,
                    (
                        record.uuid, self._user_id, record.record_type.value,
                        record.project, record.title, json.dumps(record.tags or []),
                        created, modified, record.archived_date,
                        record.deleted_date, record.full_content,
                    ),
                )
            except psycopg.errors.CheckViolation as exc:
                raise ValueError(
                    f"fleet-shared memory cannot be {record.record_type.value!r}: "
                    f"it may only be {_SHARED_RECORD_TYPES}. Memory of any other kind "
                    "belongs to an agent — insert it with that agent's id instead."
                ) from exc
            except psycopg.errors.UniqueViolation as exc:
                raise ValueError(
                    "this tenant already has a user profile: only one 'user_profile' "
                    "record may exist per user, because awaken answers \"has anyone "
                    "been asked yet\" with the presence of a row. Edit the existing "
                    "record instead of inserting a second one."
                ) from exc
            cur.execute(
                f"SELECT {_SHARED_COLUMNS} FROM shared_record WHERE uuid=%s AND user_id=%s",
                (record.uuid, self._user_id),
            )
            row = cur.fetchone()
        return _row_to_shared(row)

    def edit(
        self, uuid: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> SharedRecord:
        return self._rewrite(
            uuid, lambda c: _apply_edit(c, old_string, new_string, replace_all, uuid)
        )

    def append(self, uuid: str, text: str) -> SharedRecord:
        return self._rewrite(uuid, lambda c: c + text)

    def prepend(self, uuid: str, text: str) -> SharedRecord:
        return self._rewrite(uuid, lambda c: text + c)

    def multi_edit(
        self, uuid: str, edits: Sequence[tuple[str, str, bool]]
    ) -> SharedRecord:
        if not edits:
            raise ValueError("multi_edit requires at least one edit")

        def _transform(content: str) -> str:
            for i, (old_string, new_string, replace_all) in enumerate(edits):
                content = _apply_edit(
                    content, old_string, new_string, replace_all, uuid, index=i
                )
            return content

        return self._rewrite(uuid, _transform)

    def _rewrite(self, uuid: str, transform: Callable[[str], str]) -> SharedRecord:
        with self._conn() as conn, conn.cursor() as cur:
            table = self._locate(cur, uuid)
            if table is None:
                raise LookupError(f"record not found: {uuid}")
            cur.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=%s AND user_id=%s",
                (uuid, self._user_id),
            )
            new_content = transform(cur.fetchone()["full_content"] or "")
            cur.execute(
                f"UPDATE {table} SET full_content=%s, modified_date=%s "
                "WHERE uuid=%s AND user_id=%s",
                (new_content, _now(), uuid, self._user_id),
            )
            cur.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=%s AND user_id=%s",
                (uuid, self._user_id),
            )
            updated = cur.fetchone()
        return _row_from(table, updated)

    def archive(self, uuid: str) -> None:
        self._set_lifecycle("archived_date", uuid)

    def soft_delete(self, uuid: str) -> None:
        self._set_lifecycle("deleted_date", uuid)

    def _set_lifecycle(self, column: str, uuid: str) -> None:
        # `column` is a literal constant from archive/soft_delete, never caller input;
        # `table` comes from the _TABLES whitelist. Neither can be parameterised.
        with self._conn() as conn, conn.cursor() as cur:
            table = self._locate(cur, uuid, include_deleted=True)
            if table is None:
                raise LookupError(f"record not found: {uuid}")
            cur.execute(
                f"UPDATE {table} SET {column}=COALESCE({column}, %s) "
                "WHERE uuid=%s AND user_id=%s",
                (_now(), uuid, self._user_id),
            )

    # --- reads ---

    def get(self, uuid: str) -> SharedRecord | None:
        with self._conn() as conn, conn.cursor() as cur:
            table = self._locate(cur, uuid)
            if table is None:
                return None
            cur.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=%s AND user_id=%s",
                (uuid, self._user_id),
            )
            row = cur.fetchone()
        return _row_from(table, row)

    def _filtered_sql(
        self,
        table: str,
        *,
        agent_id: str | None,
        record_type: RecordType | None,
        project: str | None,
        include_archived: bool,
    ) -> tuple[str, list[object]]:
        where = ["user_id = %s", "deleted_date IS NULL"]
        params: list[object] = [self._user_id]
        if not include_archived:
            where.append("archived_date IS NULL")
        if agent_id is not None:
            where.append("agent_id = %s")
            params.append(agent_id)
        if record_type is not None:
            where.append("record_type = %s")
            params.append(record_type.value)
        if project is not None:
            where.append("project = %s")
            params.append(project)
        return (
            f"SELECT {_TABLES[table]} FROM {table} "
            f"WHERE {' AND '.join(where)} ORDER BY id",
            params,
        )

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[SharedRecord]:
        sql, params = self._filtered_sql(
            "memory_record",
            agent_id=agent_id,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            records: list[SharedRecord] = [_row_to_record(r) for r in cur.fetchall()]
            if agent_id is None:
                shared_sql, shared_params = self._filtered_sql(
                    "shared_record",
                    agent_id=None,
                    record_type=record_type,
                    project=project,
                    include_archived=include_archived,
                )
                cur.execute(shared_sql, shared_params)
                records += [_row_to_shared(r) for r in cur.fetchall()]
        return records

    def query_shared(
        self,
        *,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[SharedRecord]:
        sql, params = self._filtered_sql(
            "shared_record",
            agent_id=None,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_shared(r) for r in rows]

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        rows = self._search_rows("memory_record", text, include_archived=include_archived)
        return [_row_to_record(r) for r in rows]

    def search_shared(
        self, text: str, *, include_archived: bool = True
    ) -> Sequence[SharedRecord]:
        rows = self._search_rows("shared_record", text, include_archived=include_archived)
        return [_row_to_shared(r) for r in rows]

    def _search_rows(
        self, table: str, text: str, *, include_archived: bool
    ) -> list[dict]:
        """One full-text search over a memory table's generated ``tsvector``.

        ``plainto_tsquery`` ANDs the whitespace terms and neutralises operator syntax, the
        closest match to the SQLite ``_to_fts_query`` literal behaviour. ``ts_rank`` ranks;
        there is no ``bm25`` here, so ordering differs by design."""
        if not text.strip():
            return []
        where = [
            "search_tsv @@ plainto_tsquery('simple', %s)",
            "user_id = %s",
            "deleted_date IS NULL",
        ]
        params: list[object] = [text, self._user_id]
        if not include_archived:
            where.append("archived_date IS NULL")
        params.append(text)  # for ts_rank
        query = (
            f"SELECT {_TABLES[table]} FROM {table} "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY ts_rank(search_tsv, plainto_tsquery('simple', %s)) DESC"
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    # --- addressing a record by uuid, across both memory tables ---

    def _locate(
        self, cur: psycopg.Cursor, uuid: str, *, include_deleted: bool = False
    ) -> str | None:
        tail = "" if include_deleted else " AND deleted_date IS NULL"
        for table in _TABLES:
            cur.execute(
                f"SELECT 1 FROM {table} WHERE uuid=%s AND user_id=%s{tail}",
                (uuid, self._user_id),
            )
            if cur.fetchone():
                return table
        return None

    # --- the agent entity ---

    def upsert_agent(self, agent: Agent) -> Agent:
        created = agent.created_date or _now()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent (user_id, agent_id, name, role, uuid, created_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, agent_id) DO UPDATE SET
                    name=excluded.name, role=excluded.role, uuid=excluded.uuid
                """,
                (
                    self._user_id, validate_domain(agent.agent_id), agent.name,
                    agent.role, agent.uuid, created,
                ),
            )
            cur.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=%s AND agent_id=%s",
                (self._user_id, agent.agent_id),
            )
            row = cur.fetchone()
        return _row_to_agent(row)

    def create_agent(self, agent: Agent) -> Agent:
        created = agent.created_date or _now()
        domain = validate_domain(agent.agent_id)
        with self._conn() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO agent (user_id, agent_id, name, role, uuid, created_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (self._user_id, domain, agent.name, agent.role, agent.uuid, created),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise ValueError(f"agent already exists: {domain}") from exc
            cur.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=%s AND agent_id=%s",
                (self._user_id, domain),
            )
            row = cur.fetchone()
        return _row_to_agent(row)

    def list_agents(self) -> Sequence[Agent]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=%s ORDER BY agent_id",
                (self._user_id,),
            )
            rows = cur.fetchall()
        return [_row_to_agent(r) for r in rows]


def _apply_edit(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
    uuid: str,
    *,
    index: int | None = None,
) -> str:
    """One Edit-tool-parity string replace. Raises ``ValueError`` when absent/ambiguous."""
    where = f" (edit {index})" if index is not None else ""
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found in record {uuid}{where}")
    if count > 1 and not replace_all:
        raise ValueError(
            f"old_string is ambiguous ({count} occurrences) in {uuid}{where}; "
            "pass replace_all=True to replace every occurrence"
        )
    return (
        content.replace(old_string, new_string)
        if replace_all
        else content.replace(old_string, new_string, 1)
    )


def _row_from(table: str, row: dict) -> SharedRecord:
    return _row_to_record(row) if table == "memory_record" else _row_to_shared(row)


def _row_to_shared(row: dict) -> SharedRecord:
    return SharedRecord(
        id=row["id"],
        uuid=row["uuid"],
        user_id=row["user_id"],
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


def _row_to_agent(row: dict) -> Agent:
    return Agent(
        user_id=row["user_id"],
        agent_id=row["agent_id"],
        name=row["name"],
        role=row["role"],
        uuid=row["uuid"],
        created_date=row["created_date"],
    )


def _row_to_record(row: dict) -> MemoryRecord:
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
