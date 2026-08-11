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
    SHARED_AGENT_ID,
    MemoryRecord,
    RecordType,
    validate_domain,
    validate_write_agent,
)
from munnin.data_repositories.memory_repository import MemoryRepository


def _whole(r: MemoryRecord) -> dict[str, Any]:
    """Always-load section item — full body included."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "content": r.full_content,
    }


def _index(r: MemoryRecord) -> dict[str, Any]:
    """Browse section item — metadata only, no body (fetched on demand)."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "tags": r.tags,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
    }


def _record(r: MemoryRecord) -> dict[str, Any]:
    """Full public record projection — the whole item including body. Omits the
    internal ``id`` (never leaves the store) and ``user_id`` (tenancy-internal)."""
    return {
        "uuid": r.uuid,
        "agent_id": r.agent_id,
        "record_type": r.record_type.value,
        "project": r.project,
        "title": r.title,
        "tags": r.tags,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "archived_date": r.archived_date,
        "content": r.full_content,
    }


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

        Always-load whole: layer i (``__shared__`` reasoning + knowledge) + layer ii
        (domain identity/reasoning/emotional). Index-only: layer iii (domain
        episode/knowledge) + the latest episode body. All reads are hot-read filtered
        (deleted + archived excluded) by the repository."""
        domain = validate_domain(domain)

        shared = self._repo.query(agent_id=SHARED_AGENT_ID)
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
        """Browse the index projection on demand (bodies included). ``record_type`` is a
        string coerced to the enum (invalid → ``ValueError``)."""
        rtype = RecordType(record_type) if record_type else None
        rows = self._repo.query(
            agent_id=agent_id,
            record_type=rtype,
            project=project,
            include_archived=include_archived,
        )
        return [_record(r) for r in rows]

    def search(self, text: str, *, include_archived: bool = True) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search over content + title + tags. Archived rows are
        searchable by default; soft-deleted never surface."""
        return [_record(r) for r in self._repo.search(text, include_archived=include_archived)]

    # --- writes (Edit-tool parity; record assembled server-side) ---

    def insert(
        self,
        *,
        agent_id: str,
        record_type: str,
        content: str,
        title: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Append a new item. Assembles the ``MemoryRecord`` server-side (the repo stamps
        ``user_id`` + defaults dates); generates a ``uuid`` if absent. Idempotent upsert on
        ``uuid``. ``agent_id`` accepts a kebab domain or ``__shared__``; invalid
        ``agent_id``/``record_type`` raise ``ValueError``."""
        agent = validate_write_agent(agent_id)
        rtype = RecordType(record_type)
        record = MemoryRecord(
            uuid=uuid or _uuid.uuid4().hex,
            user_id="",  # repo stamps server-side
            agent_id=agent,
            record_type=rtype,
            full_content=content,
            title=title,
            tags=tags or [],
            project=project,
        )
        return _record(self._repo.insert(record))

    def edit(
        self, uuid: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity). Raises
        ``LookupError`` if missing/deleted, ``ValueError`` if ``old_string`` is absent or
        (without ``replace_all``) ambiguous."""
        return _record(self._repo.edit(uuid, old_string, new_string, replace_all))

    def archive(self, uuid: str) -> dict[str, str]:
        """Retire a record from the hot index (still searchable). Raises ``LookupError`` if
        absent."""
        self._repo.archive(uuid)
        return {"uuid": uuid, "status": "archived"}

    def soft_delete(self, uuid: str) -> dict[str, str]:
        """Tombstone a record (excluded from all reads). Raises ``LookupError`` if absent."""
        self._repo.soft_delete(uuid)
        return {"uuid": uuid, "status": "deleted"}
