"""The uniform memory record — one shape for every item (ADR-013 D5, arch §3).

One record = one *item* (one episode / reasoning pattern / emotional moment /
knowledge entry / identity doc). Metadata columns + a ``full_content`` markdown
blob. The index is a projection over the metadata (a SELECT), never a hand-edited
file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RecordType(str, Enum):
    """Drives the two read patterns: identity/reasoning/emotional are loaded whole
    at awaken; episode/knowledge are browsed via the index, bodies on demand."""

    episode = "episode"
    knowledge = "knowledge"
    identity = "identity"
    reasoning = "reasoning"
    emotional = "emotional"


@dataclass
class MemoryRecord:
    """A single memory item. ``id`` is the internal rowid (assigned by the store);
    ``uuid`` is the global/portable identity used across stores and for idempotency."""

    uuid: str
    user_id: str
    agent_id: str  # the agent's domain, or "shared"
    record_type: RecordType
    full_content: str
    id: int | None = None
    project: str | None = None
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    created_date: str | None = None
    modified_date: str | None = None
    archived_date: str | None = None  # non-NULL = archived (out of hot index, still searchable)
    deleted_date: str | None = None  # non-NULL = soft-deleted tombstone (never surfaced)
