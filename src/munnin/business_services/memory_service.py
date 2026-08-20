"""The transport-agnostic memory-service core.

Both adapters (MCP + HTTP) call THIS; it calls the injected repository. No
transport concerns leak in here. Memory operations (awaken, update_episodic,
add_reasoning, ...) land in Phase 5; Phase 4 provides only liveness.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from munnin import __version__
from munnin.data_entities.memory_record import (
    Agent,
    MemoryRecord,
    RecordType,
    SharedRecord,
    validate_domain,
)
from munnin.data_repositories.memory_repository import MemoryRepository


def _whole(r: SharedRecord) -> dict[str, Any]:
    """Always-load section item — full body included."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "content": r.full_content,
    }


def _index(r: SharedRecord) -> dict[str, Any]:
    """Browse section item — metadata only, no body (fetched on demand)."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "tags": r.tags,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
    }


def _record(r: SharedRecord) -> dict[str, Any]:
    """Full public record projection — the whole item including body. Omits the
    internal ``id`` (never leaves the store) and ``user_id`` (tenancy-internal).

    ``agent_id`` appears only on agent-owned memory, because only ``MemoryRecord``
    has one. That is what makes a merged result **self-labelling**: a caller reading
    a mixed list can tell fleet memory from an agent's by the field's presence,
    without an envelope to unpack or a sentinel value to recognise."""
    return {
        "uuid": r.uuid,
        **({"agent_id": r.agent_id} if isinstance(r, MemoryRecord) else {}),
        "record_type": r.record_type.value,
        "project": r.project,
        "title": r.title,
        "tags": r.tags,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "archived_date": r.archived_date,
        "content": r.full_content,
    }


def _agent(a: Agent) -> dict[str, Any]:
    """The agent entity's public shape. Carries ``uuid`` where the roster does not: a
    creation response confirms what was actually stored, while the roster stays three
    short fields per agent because whole identities overrun the client's output cap."""
    return {"agent_id": a.agent_id, "name": a.name, "role": a.role, "uuid": a.uuid}


class MemoryService:
    """Assembly + writes over the store. Constructed with a repository (DI) and the
    server-side ``user_id`` (v1: a constant, never from agent input)."""

    def __init__(self, repo: MemoryRepository, *, user_id: str) -> None:
        self._repo = repo
        self._user_id = user_id

    def health(self) -> dict[str, str]:
        return {"status": "ok", "service": "munnin", "version": __version__}

    def version(self) -> str:
        return __version__

    def awaken(self, domain: str) -> dict[str, Any]:
        """Assemble an agent's memory payload from the DB (4-layer model, C-2).

        Always-load whole: layer i (fleet-shared reasoning + knowledge) + layer ii
        (domain identity/reasoning/emotional). Index-only: layer iii (domain
        episode/knowledge) + the latest episode body. All reads are hot-read filtered
        (deleted + archived excluded) by the repository.

        Layer i now comes from ``query_shared`` rather than from an agent named
        ``__shared__``. The payload shape is unchanged — it always was fleet memory;
        only the place it is stored stopped pretending to be an agent."""
        domain = validate_domain(domain)

        shared = self._repo.query_shared()
        shared_reasoning = [r for r in shared if r.record_type is RecordType.reasoning]
        shared_knowledge = [r for r in shared if r.record_type is RecordType.knowledge]

        identity = self._repo.query(agent_id=domain, record_type=RecordType.identity)
        reasoning = self._repo.query(agent_id=domain, record_type=RecordType.reasoning)
        emotional = self._repo.query(agent_id=domain, record_type=RecordType.emotional)

        knowledge_idx = self._repo.query(agent_id=domain, record_type=RecordType.knowledge)
        episodes = sorted(
            self._repo.query(agent_id=domain, record_type=RecordType.episode),
            key=lambda r: (r.created_date or "", r.id or 0),
            reverse=True,
        )
        latest = episodes[0] if episodes else None

        return {
            "agent_id": domain,
            # layer i — always-load for every agent
            "shared": {
                "reasoning": [_whole(r) for r in shared_reasoning],
                "knowledge": [_whole(r) for r in shared_knowledge],
            },
            # layer ii — this agent's identity
            "identity": [_whole(r) for r in identity],
            "reasoning": [_whole(r) for r in reasoning],
            "emotional": [_whole(r) for r in emotional],
            # layer iii — index only (+ latest episode body)
            "knowledge_index": [_index(r) for r in knowledge_idx],
            "episodic_index": [_index(r) for r in episodes],
            "latest_episode": _whole(latest) if latest else None,
        }

    # --- reads (load by id / browse / full-text) ---

    def get(self, uuid: str) -> dict[str, Any] | None:
        """Load one record's full body by id. Excludes soft-deleted. ``None`` if absent."""
        r = self._repo.get(uuid)
        return _record(r) if r else None

    def query(
        self,
        *,
        agent_id: str | None = None,
        record_type: str | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Filter memory by exact field values, whole records including bodies.
        ``record_type`` is a string coerced to the enum (invalid → ``ValueError``).
        Naming an ``agent_id`` reads that agent alone; omitting it also returns
        fleet-shared memory, and those rows carry no ``agent_id`` key."""
        rtype = RecordType(record_type) if record_type else None
        rows = self._repo.query(
            agent_id=agent_id,
            record_type=rtype,
            project=project,
            include_archived=include_archived,
        )
        return [_record(r) for r in rows]

    def search(self, text: str, *, include_archived: bool = True) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search over content + title + tags, across **both**
        corpora. Archived rows are searchable by default; soft-deleted never surface.

        The two groups arrive from two indexes because FTS5 external-content binds one
        index to one table, and they are concatenated rather than interleaved by score:
        bm25 ranks per corpus, so the numbers are not comparable across the join. Within
        each group the ranking is the real one. Agent hits carry ``agent_id``; fleet hits
        do not, which is the whole labelling the caller needs."""
        return [
            _record(r)
            for r in (
                *self._repo.search(text, include_archived=include_archived),
                *self._repo.search_shared(text, include_archived=include_archived),
            )
        ]

    def create_agent(
        self,
        *,
        agent_id: str,
        name: str | None = None,
        role: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Bring a new agent into being — the row its memory will point at.

        An agent has to exist before anything can be written for it, so this is the first
        call in creating one, not an optional registration step. Refuses an existing
        domain with ``ValueError`` rather than refreshing it: re-running creation against
        a live agent is a mistake, and overwriting its name silently would be a worse
        answer than an error. ``uuid`` is the agent's own "digital soul" id from its
        identity document — content, not a key."""
        return _agent(
            self._repo.create_agent(
                Agent(
                    user_id="",  # repo stamps server-side
                    agent_id=validate_domain(agent_id),
                    name=name,
                    role=role,
                    uuid=uuid,
                )
            )
        )

    def list_agents(self) -> list[dict[str, Any]]:
        """The fleet roster: every agent domain plus its display name and one-line role.

        A plain column read. Name and role are parsed once, at import, and stored on the
        agent row — so this no longer pulls identity bodies through the service to regex
        them on every request, and no longer runs past the MCP output cap that truncates
        silently. An agent is listed because it has a row, which also means a newly
        created agent with no memory yet appears immediately.

        An agent with no readable identity keeps ``name``/``role`` of ``None`` — the
        caller renders it, never drops it, because absent identity is a finding."""
        return [
            {"agent_id": a.agent_id, "name": a.name, "role": a.role}
            for a in self._repo.list_agents()
        ]

    # --- writes (Edit-tool parity; record assembled server-side) ---

    def insert(
        self,
        *,
        record_type: str,
        content: str,
        agent_id: str | None = None,
        scope: str = "agent",
        title: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Append a new item. Assembles the record server-side (the repo stamps
        ``user_id`` + defaults dates); generates a ``uuid`` if absent. Idempotent upsert
        on ``uuid``.

        ``scope`` decides which table the row goes to, and it has to be explicit: an
        insert is the one write that chooses *where* — every other write addresses a
        record that already exists, so its uuid answers the question. ``scope="agent"``
        (the default) requires a real kebab ``agent_id``; ``scope="shared"`` forbids one,
        because fleet memory has no owner. Both contradictions raise ``ValueError`` rather
        than guessing, since either guess would put the row in a table the caller did not
        mean. An unknown ``scope``, an invalid domain, or an invalid ``record_type`` also
        raise ``ValueError``.

        A ``scope="shared"`` insert of an agent-only ``record_type`` (an episode, say) is
        refused by the shared table's own CHECK. That check is deliberately not duplicated
        here: the schema is the single enforcer of what fleet memory may contain."""
        if scope not in ("agent", "shared"):
            raise ValueError(f"invalid scope {scope!r}: expected 'agent' or 'shared'")
        rtype = RecordType(record_type)
        common: dict[str, Any] = {
            "uuid": uuid or _uuid.uuid4().hex,
            "user_id": "",  # repo stamps server-side
            "record_type": rtype,
            "full_content": content,
            "title": title,
            "tags": tags or [],
            "project": project,
        }
        if scope == "shared":
            if agent_id is not None:
                raise ValueError(
                    "scope='shared' takes no agent_id: fleet memory has no owner"
                )
            return _record(self._repo.insert_shared(SharedRecord(**common)))
        if agent_id is None:
            raise ValueError("scope='agent' requires an agent_id")
        return _record(
            self._repo.insert(
                MemoryRecord(agent_id=validate_domain(agent_id), **common)
            )
        )

    def edit(
        self, uuid: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity). Raises
        ``LookupError`` if missing/deleted, ``ValueError`` if ``old_string`` is absent or
        (without ``replace_all``) ambiguous."""
        return _record(self._repo.edit(uuid, old_string, new_string, replace_all))

    def append(self, uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` verbatim to the end of a record's body (caller controls
        newlines). Raises ``LookupError`` if missing/deleted."""
        return _record(self._repo.append(uuid, text))

    def prepend(self, uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` verbatim to the start of a record's body (caller controls
        newlines). Raises ``LookupError`` if missing/deleted."""
        return _record(self._repo.prepend(uuid, text))

    def multi_edit(self, uuid: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply a sequence of edits to one record atomically. Each edit is a dict with
        ``old_string`` + ``new_string`` (+ optional ``replace_all``); they apply in order,
        all-or-nothing. Raises ``LookupError`` if missing/deleted, ``ValueError`` if the
        list is empty, an edit is malformed, or an ``old_string`` is absent/ambiguous."""
        try:
            specs = [
                (e["old_string"], e["new_string"], bool(e.get("replace_all", False)))
                for e in edits
            ]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                "each edit needs 'old_string' and 'new_string'"
            ) from exc
        return _record(self._repo.multi_edit(uuid, specs))

    def archive(self, uuid: str) -> dict[str, str]:
        """Retire a record from the hot index (still searchable). Raises ``LookupError`` if
        absent."""
        self._repo.archive(uuid)
        return {"uuid": uuid, "status": "archived"}

    def soft_delete(self, uuid: str) -> dict[str, str]:
        """Tombstone a record (excluded from all reads). Raises ``LookupError`` if absent."""
        self._repo.soft_delete(uuid)
        return {"uuid": uuid, "status": "deleted"}
