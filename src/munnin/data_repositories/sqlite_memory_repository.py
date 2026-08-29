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
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from munnin.data_entities.memory_record import (
    SHARED_RECORD_TYPES,
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
    validate_domain,
)

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
# shared_record is memory_record minus its owner — the same difference the dataclasses have.
_SHARED_COL = tuple(c for c in _COL if c != "agent_id")
_SHARED_COLUMNS = ", ".join(_SHARED_COL)
# The two tables a uuid can live in, with the column list to read each. Iteration order is
# the lookup order for `_locate`; values are interpolated into SQL, so this mapping is the
# whitelist that keeps that safe — a table name can never be parameterised in SQLite.
_TABLES: dict[str, str] = {"memory_record": _COLUMNS, "shared_record": _SHARED_COLUMNS}
# What `shared_record`'s CHECK admits, rendered for the error message. Derived from the
# entity's declared set rather than retyped, because the previous hardcoded string went on
# saying "reasoning or knowledge" for as long as `user_profile` had been legal — and the
# test that should have caught it was asserting the stale string instead.
_SHARED_TYPE_NAMES = [f"{t.value!r}" for t in SHARED_RECORD_TYPES]
_SHARED_RECORD_TYPES = (
    " or ".join(_SHARED_TYPE_NAMES)
    if len(_SHARED_TYPE_NAMES) < 3
    else f"{', '.join(_SHARED_TYPE_NAMES[:-1])} or {_SHARED_TYPE_NAMES[-1]}"
)
# The agent entity's column order — one source of truth, same discipline as _COL.
_AGENT_COL = ("user_id", "agent_id", "name", "role", "uuid", "created_date")
_AGENT_COLUMNS = ", ".join(_AGENT_COL)
# Insert set = every column except the autoincrement id.
_INSERT_COLUMNS = ", ".join(_COL[1:])
_SHARED_INSERT_COLUMNS = ", ".join(_SHARED_COL[1:])
# Alias-prefixed lists for joins (the FTS search joins, on `m` and `s`).
_M_COLUMNS = ", ".join(f"m.{c}" for c in _COL)
_S_COLUMNS = ", ".join(f"s.{c}" for c in _SHARED_COL)


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
        # Per-connection, and SQLite defaults it OFF — without this the memory_record →
        # agent foreign key is declared but never enforced, so every insert succeeds and
        # the constraint fails silently. Connection-per-operation means it must be set here.
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._ensured:
            conn.executescript(_SCHEMA_SQL)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- writes (Edit-tool parity) ---

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        """Append a new item. Idempotent UPSERT on ``uuid`` — a re-import of the
        same content is a no-op (updates the row in place, preserves ``created_date``).

        The composite foreign key means the agent must already exist **for this tenant**.
        Its rejection is translated into ``ValueError``, the same way the shared table's
        CHECK is, so both faces report it as bad input rather than as a broken server.
        Naming an agent that exists for somebody else is the ordinary case here, not an
        exotic one: agent ids are short and shared by convention across the fleet, so two
        tenants both having a ``meta`` is expected and one of them asking for the other's
        must read as "you have no such agent"."""
        created = record.created_date or _now()
        modified = record.modified_date or created
        rtype = record.record_type.value
        tags = json.dumps(record.tags or [])
        with self._conn() as conn:
            try:
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
            except sqlite3.IntegrityError as exc:
                if "FOREIGN KEY constraint failed" in str(exc):
                    raise ValueError(
                        f"no agent {record.agent_id!r} exists for this account. Create it "
                        "first, then insert its memory."
                    ) from exc
                raise
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM memory_record WHERE uuid=? AND user_id=?",
                (record.uuid, self._user_id),
            ).fetchone()
        return _row_to_record(row)

    def insert_shared(self, record: SharedRecord) -> SharedRecord:
        """Append a new fleet-shared item. Same idempotent UPSERT-on-``uuid`` contract as
        ``insert``, against the table that has no owner column.

        This is the one operation that genuinely needs a shared twin. Every other
        write addresses a record that already exists, so its uuid says which table to
        use; an insert is deciding *where the row goes*, and nothing in the arguments
        can imply that. ``record_type`` is enforced by the table's own CHECK — passing
        an episode is refused rather than silently accepted into a table that is only
        ever reasoning and knowledge.

        The schema stays the single enforcer of that rule — it is not restated here —
        but its rejection is translated into ``ValueError`` so both faces can report it
        the way they report every other bad input. An untranslated ``IntegrityError``
        reaches an agent as an opaque database string and an HTTP caller as a 500."""
        created = record.created_date or _now()
        modified = record.modified_date or created
        with self._conn() as conn:
            try:
                conn.execute(
                    f"""
                INSERT INTO shared_record
                    ({_SHARED_INSERT_COLUMNS})
                VALUES (:uuid, :user_id, :record_type, :project, :title,
                        :tags, :created_date, :modified_date, :archived_date,
                        :deleted_date, :full_content)
                ON CONFLICT(uuid) DO UPDATE SET
                    record_type=excluded.record_type,
                    project=excluded.project, title=excluded.title, tags=excluded.tags,
                    modified_date=excluded.modified_date, archived_date=excluded.archived_date,
                    deleted_date=excluded.deleted_date, full_content=excluded.full_content
                """,
                    {
                        "uuid": record.uuid,
                        "user_id": self._user_id,
                        "record_type": record.record_type.value,
                        "project": record.project,
                        "title": record.title,
                        "tags": json.dumps(record.tags or []),
                        "created_date": created,
                        "modified_date": modified,
                        "archived_date": record.archived_date,
                        "deleted_date": record.deleted_date,
                        "full_content": record.full_content,
                    },
                )
            except sqlite3.IntegrityError as exc:
                msg = str(exc)
                if "CHECK constraint failed" in msg:
                    raise ValueError(
                        f"fleet-shared memory cannot be {record.record_type.value!r}: "
                        f"it may only be {_SHARED_RECORD_TYPES}. Memory of any other kind "
                        "belongs to an agent — insert it with that agent's id instead."
                    ) from exc
                # The partial unique index on (user_id) WHERE record_type='user_profile'.
                # A uuid collision cannot reach here — ON CONFLICT(uuid) upserts it — so
                # this names the only UNIQUE the table can actually refuse. Left as an
                # IntegrityError it surfaced as an unhandled 500, which reads as a broken
                # server rather than what it is: a caller asking for a second profile.
                if "UNIQUE constraint failed: shared_record.user_id" in msg:
                    raise ValueError(
                        "this tenant already has a user profile: only one 'user_profile' "
                        "record may exist per user, because awaken answers \"has anyone "
                        "been asked yet\" with the presence of a row. Edit the existing "
                        "record instead of inserting a second one."
                    ) from exc
                raise
            row = conn.execute(
                f"SELECT {_SHARED_COLUMNS} FROM shared_record WHERE uuid=? AND user_id=?",
                (record.uuid, self._user_id),
            ).fetchone()
        return _row_to_shared(row)

    def edit(
        self,
        uuid: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> SharedRecord:
        """Edit-tool-parity content edit. Unique-replace by default (raises if the
        substring is absent or ambiguous); ``replace_all=True`` replaces every
        occurrence. Bumps ``modified_date``; FTS re-syncs via the AFTER UPDATE trigger.

        Raises ``LookupError`` if the record is missing/deleted, ``ValueError`` if
        ``old_string`` is not found or (without ``replace_all``) ambiguous."""
        return self._rewrite(
            uuid, lambda c: _apply_edit(c, old_string, new_string, replace_all, uuid)
        )

    def append(self, uuid: str, text: str) -> SharedRecord:
        """Add ``text`` verbatim to the END of the body (caller controls newlines).
        Bumps ``modified_date``; raises ``LookupError`` if missing/deleted."""
        return self._rewrite(uuid, lambda c: c + text)

    def prepend(self, uuid: str, text: str) -> SharedRecord:
        """Add ``text`` verbatim to the START of the body (caller controls newlines).
        Bumps ``modified_date``; raises ``LookupError`` if missing/deleted."""
        return self._rewrite(uuid, lambda c: text + c)

    def multi_edit(
        self, uuid: str, edits: Sequence[tuple[str, str, bool]]
    ) -> SharedRecord:
        """Apply the ``(old_string, new_string, replace_all)`` edits in order,
        atomically. Each edit sees the result of the previous; if any fails the whole
        rewrite aborts before the single UPDATE, so nothing is written.

        Raises ``LookupError`` if missing/deleted, ``ValueError`` if ``edits`` is empty
        or any edit's ``old_string`` is absent/ambiguous (message names the index)."""
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
        """Read-modify-write one record's ``full_content`` under a single connection.
        ``transform`` maps the current body to the new body and may raise ``ValueError``
        to abort with nothing written (the UPDATE runs only after it returns). Bumps
        ``modified_date``; FTS re-syncs via the AFTER UPDATE trigger. Raises
        ``LookupError`` if the record is missing/deleted."""
        with self._conn() as conn:
            table = self._locate(conn, uuid)
            if table is None:
                raise LookupError(f"record not found: {uuid}")
            row = conn.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=? AND user_id=?",
                (uuid, self._user_id),
            ).fetchone()
            new_content = transform(row["full_content"] or "")
            conn.execute(
                f"UPDATE {table} SET full_content=?, modified_date=? "
                "WHERE uuid=? AND user_id=?",
                (new_content, _now(), uuid, self._user_id),
            )
            updated = conn.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=? AND user_id=?",
                (uuid, self._user_id),
            ).fetchone()
        return _row_from(table, updated)

    def archive(self, uuid: str) -> None:
        """Set ``archived_date`` (idempotent — first timestamp preserved)."""
        self._set_lifecycle("archived_date", uuid)

    def soft_delete(self, uuid: str) -> None:
        """Set ``deleted_date`` tombstone (idempotent)."""
        self._set_lifecycle("deleted_date", uuid)

    def _set_lifecycle(self, column: str, uuid: str) -> None:
        # `column` is a literal constant from archive/soft_delete, never caller input;
        # `table` comes from the _TABLES whitelist. Neither can be parameterised in SQLite.
        # Already-deleted rows stay addressable so soft_delete keeps its idempotency.
        with self._conn() as conn:
            table = self._locate(conn, uuid, include_deleted=True)
            if table is None:
                raise LookupError(f"record not found: {uuid}")
            conn.execute(
                f"UPDATE {table} SET {column}=COALESCE({column}, ?) "
                "WHERE uuid=? AND user_id=?",
                (_now(), uuid, self._user_id),
            )

    # --- reads ---

    def get(self, uuid: str) -> SharedRecord | None:
        """Load one record by uuid from whichever memory table holds it. Returns a
        ``MemoryRecord`` for agent memory and a ``SharedRecord`` for fleet memory — the
        caller can tell them apart by the presence of ``agent_id``, so the result is
        self-labelling and needs no wrapper."""
        with self._conn() as conn:
            table = self._locate(conn, uuid)
            if table is None:
                return None
            row = conn.execute(
                f"SELECT {_TABLES[table]} FROM {table} WHERE uuid=? AND user_id=?",
                (uuid, self._user_id),
            ).fetchone()
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
        """Build the ``(sql, params)`` for a field-filtered read of one memory table.

        Shared by ``query`` and ``query_shared`` so the tenancy and lifecycle invariants
        are written once and cannot drift apart between the two tables. ``table`` comes
        from the ``_TABLES`` whitelist; ``agent_id`` is only ever passed for
        ``memory_record``, the only table that has the column."""
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
        """Filter memory by exact field values, returning whole records including bodies.

        Naming an ``agent_id`` reads that agent's memory alone. Leaving it out means "all
        memory this tenant can see", which now spans two tables, so the fleet-shared rows
        are read too and appended after the agent rows — each mapped by its own table's
        mapper, so the result stays self-labelling (a ``MemoryRecord`` carries
        ``agent_id``; a ``SharedRecord`` has no such attribute). The alternative, a SQL
        ``UNION`` selecting ``NULL AS agent_id``, would hand every shared row a fake owner
        — the exact sentinel shape this model exists to remove.

        Ordering is per table (insertion order within each), not global: the two ``id``
        sequences are independent, so interleaving them would imply a chronology neither
        column carries."""
        sql, params = self._filtered_sql(
            "memory_record",
            agent_id=agent_id,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )
        with self._conn() as conn:
            records: list[SharedRecord] = [
                _row_to_record(r) for r in conn.execute(sql, params).fetchall()
            ]
            if agent_id is None:
                shared_sql, shared_params = self._filtered_sql(
                    "shared_record",
                    agent_id=None,
                    record_type=record_type,
                    project=project,
                    include_archived=include_archived,
                )
                records += [
                    _row_to_shared(r)
                    for r in conn.execute(shared_sql, shared_params).fetchall()
                ]
        return records

    def query_shared(
        self,
        *,
        record_type: RecordType | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> Sequence[SharedRecord]:
        """Fleet-shared memory only, filtered by exact field values, bodies included.
        No ``agent_id`` parameter exists because the table has no such column — this
        memory belongs to the fleet, not to an agent."""
        sql, params = self._filtered_sql(
            "shared_record",
            agent_id=None,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_shared(r) for r in rows]

    def search(self, text: str, *, include_archived: bool = True) -> Sequence[MemoryRecord]:
        """Full-text search (FTS5) over agent memory's content + title + tags. Safe
        plain-text (see ``_to_fts_query``); ``user_id``-stamped; soft-deleted excluded;
        archived included by default (still searchable). Ranked most-relevant-first (bm25).

        Fleet memory is **not** included — it has its own index and its own method.
        FTS5 external-content binds one index to one content table, so the split is the
        schema's, not a choice made here; the caller merges the two groups."""
        rows = self._search_rows(
            "memory_record", "memory_fts", "m", _M_COLUMNS, text,
            include_archived=include_archived,
        )
        return [_row_to_record(r) for r in rows]

    def search_shared(
        self, text: str, *, include_archived: bool = True
    ) -> Sequence[SharedRecord]:
        """Full-text search over fleet-shared memory. Same contract as ``search`` against
        the other corpus. Note that bm25 ranks **per corpus**, so a score from here is not
        strictly comparable with one from ``search`` — accepted, because nothing reads the
        scores and the two groups are merged by the caller, not interleaved by rank."""
        rows = self._search_rows(
            "shared_record", "shared_fts", "s", _S_COLUMNS, text,
            include_archived=include_archived,
        )
        return [_row_to_shared(r) for r in rows]

    def _search_rows(
        self,
        table: str,
        index: str,
        alias: str,
        columns: str,
        text: str,
        *,
        include_archived: bool,
    ) -> list[sqlite3.Row]:
        """One FTS5 corpus search, returning raw rows for the caller to map — which is
        what keeps each result the type its own table implies. Table, index and alias are
        literal constants from the two callers above, never caller input, because SQLite
        cannot parameterise them."""
        match = _to_fts_query(text)
        if not match:
            return []
        where = [f"{index} MATCH ?", f"{alias}.user_id = ?", f"{alias}.deleted_date IS NULL"]
        params: list[object] = [match, self._user_id]
        if not include_archived:
            where.append(f"{alias}.archived_date IS NULL")
        sql = (
            f"SELECT {columns} FROM {index} "
            f"JOIN {table} {alias} ON {alias}.id = {index}.rowid "
            f"WHERE {' AND '.join(where)} ORDER BY {index}.rank"
        )
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    # --- addressing a record by uuid, across both memory tables ---

    def _locate(
        self, conn: sqlite3.Connection, uuid: str, *, include_deleted: bool = False
    ) -> str | None:
        """Which table holds this uuid, or ``None`` if neither does.

        A uuid identifies one row across both tables by construction — `stable_uuid`
        derives it from a scope token plus the record's key, so an agent record and a
        shared record can never collide. That is what lets the seven uuid-addressed
        operations keep a single signature instead of growing shared twins: the caller
        already carries enough information to find the row, so asking them which table
        it lives in would be asking for something the id contains."""
        tail = "" if include_deleted else " AND deleted_date IS NULL"
        for table in _TABLES:
            found = conn.execute(
                f"SELECT 1 FROM {table} WHERE uuid=? AND user_id=?{tail}",
                (uuid, self._user_id),
            ).fetchone()
            if found:
                return table
        return None

    # --- the agent entity ---

    def upsert_agent(self, agent: Agent) -> Agent:
        """Create or update one agent. Idempotent on ``(user_id, agent_id)`` so a
        re-import refreshes name/role/uuid without disturbing ``created_date``.
        ``user_id`` is stamped server-side and ignored on the passed entity."""
        created = agent.created_date or _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO agent (user_id, agent_id, name, role, uuid, created_date)
                VALUES (:user_id, :agent_id, :name, :role, :uuid, :created_date)
                ON CONFLICT(user_id, agent_id) DO UPDATE SET
                    name=excluded.name, role=excluded.role, uuid=excluded.uuid
                """,
                    {
                    "user_id": self._user_id,
                    "agent_id": validate_domain(agent.agent_id),
                    "name": agent.name,
                    "role": agent.role,
                    "uuid": agent.uuid,
                    "created_date": created,
                },
            )
            row = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=? AND agent_id=?",
                (self._user_id, agent.agent_id),
            ).fetchone()
        return _row_to_agent(row)

    def create_agent(self, agent: Agent) -> Agent:
        """Create one agent, refusing to touch an existing one.

        The strict twin of ``upsert_agent``, and the only one of the two that belongs on
        a served surface. Upsert refreshes name and role by design — which is right for a
        re-import replaying the markdown source, and wrong for an agent calling a tool,
        because it would let one agent silently rewrite another's identity with no error
        and nothing to audit. Creation should also be honestly non-idempotent: re-running
        it against an existing domain is a mistake worth hearing about, not a no-op to
        absorb. Raises ``ValueError`` if the domain is taken."""
        created = agent.created_date or _now()
        domain = validate_domain(agent.agent_id)
        with self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO agent (user_id, agent_id, name, role, uuid, created_date)
                    VALUES (:user_id, :agent_id, :name, :role, :uuid, :created_date)
                    """,
                    {
                        "user_id": self._user_id,
                        "agent_id": domain,
                        "name": agent.name,
                        "role": agent.role,
                        "uuid": agent.uuid,
                        "created_date": created,
                    },
                )
            except sqlite3.IntegrityError as exc:
                # Narrow deliberately. The primary key is the only constraint that can
                # fire here today, so a blanket catch would be right by luck — and would
                # start reporting some future column's violation as a duplicate.
                if "UNIQUE constraint failed" not in str(exc):
                    raise
                raise ValueError(f"agent already exists: {domain}") from exc
            row = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=? AND agent_id=?",
                (self._user_id, domain),
            ).fetchone()
        return _row_to_agent(row)

    def list_agents(self) -> Sequence[Agent]:
        """Every agent in this tenant, sorted by domain. Reads the entity table — an
        agent is listed because it has a row, never because memory happens to mention
        it, so a brand-new agent with no memory yet is still a real agent here."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {_AGENT_COLUMNS} FROM agent WHERE user_id=? ORDER BY agent_id",
                (self._user_id,),
            ).fetchall()
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
    """One Edit-tool-parity string replace over ``content``. Raises ``ValueError``
    (naming the edit ``index`` when part of a ``multi_edit``) if ``old_string`` is
    absent, or ambiguous without ``replace_all``."""
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


def _row_from(table: str, row: sqlite3.Row) -> SharedRecord:
    """Map a row to the type its table implies — the two are kept in step by `_TABLES`."""
    return _row_to_record(row) if table == "memory_record" else _row_to_shared(row)


def _row_to_shared(row: sqlite3.Row) -> SharedRecord:
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


def _row_to_agent(row: sqlite3.Row) -> Agent:
    return Agent(
        user_id=row["user_id"],
        agent_id=row["agent_id"],
        name=row["name"],
        role=row["role"],
        uuid=row["uuid"],
        created_date=row["created_date"],
    )


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
