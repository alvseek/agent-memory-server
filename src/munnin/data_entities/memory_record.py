"""The uniform memory record — one shape for every item (ADR-013 D5, arch §3).

One record = one *item* (one episode / reasoning pattern / emotional moment /
knowledge entry / identity doc). Metadata columns + a ``full_content`` markdown
blob. The index is a projection over the metadata (a SELECT), never a hand-edited
file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# The reserved sentinel for fleet-shared memory (always-load layer i). One constant,
# never a magic string. It is NOT a legal agent domain (underscores fail the kebab rule),
# so no real agent can collide with it and break fleet-shared isolation.
SHARED_AGENT_ID = "__shared__"

_DOMAIN_RE = re.compile(r"^[a-z0-9-]+$")
# Kebab-legal but semantically reserved names that must not be used as domains.
_RESERVED_DOMAINS = frozenset({"shared"})


def validate_domain(name: str) -> str:
    """Validate an agent domain name and return it. Kebab-case ``[a-z0-9-]+`` only
    (so the ``__shared__`` sentinel — which has underscores — can never be a domain),
    and not a reserved word. Raises ``ValueError`` otherwise."""
    if not _DOMAIN_RE.fullmatch(name) or name in _RESERVED_DOMAINS:
        raise ValueError(
            f"invalid agent domain {name!r}: must match [a-z0-9-]+ and not be reserved "
            f"({sorted(_RESERVED_DOMAINS)} or the '{SHARED_AGENT_ID}' sentinel)"
        )
    return name


def validate_write_agent(name: str) -> str:
    """Validate an ``agent_id`` for a WRITE. Like ``validate_domain`` but also accepts
    the reserved ``__shared__`` sentinel (fleet-shared reasoning/knowledge are written
    under it). Reads stay permissive — only writes decide ownership."""
    if name == SHARED_AGENT_ID:
        return name
    return validate_domain(name)


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
