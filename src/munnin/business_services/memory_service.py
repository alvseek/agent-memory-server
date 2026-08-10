"""The transport-agnostic memory-service core.

Both adapters (MCP + HTTP) call THIS; it calls the injected repository. No
transport concerns leak in here. Memory operations (awaken, update_episodic,
add_reasoning, ...) land in Phase 5; Phase 4 provides only liveness.
"""

from __future__ import annotations

from typing import Any

from munnin import __version__
from munnin.data_entities.memory_record import (
    SHARED_AGENT_ID,
    MemoryRecord,
    RecordType,
    validate_domain,
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
