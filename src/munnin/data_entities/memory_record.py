"""The store's entities: an agent, and the memory that belongs to it.

One memory record = one *item* (one episode / reasoning pattern / emotional moment /
knowledge entry / identity doc) — metadata columns plus a ``full_content`` markdown
blob. The index is a projection over that metadata (a SELECT), never a hand-edited file.
Every item still has one uniform shape; what changed is that an **agent** is no longer
one of the items. It is an entity with a row of its own, so ``MemoryRecord`` extends
``SharedRecord`` by exactly the field the two tables differ by — the owner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_DOMAIN_RE = re.compile(r"^[a-z0-9-]+$")
# Kebab-legal but semantically reserved names that must not be used as domains.
# `shared` is reserved because it names the fleet's own memory scope; the older
# `__shared__` sentinel is gone entirely, and the kebab rule rejects it anyway.
_RESERVED_DOMAINS = frozenset({"shared"})


def validate_domain(name: str) -> str:
    """Validate an agent domain name and return it. Kebab-case ``[a-z0-9-]+`` only, and
    not a reserved word. Raises ``ValueError`` otherwise.

    There is no longer a write-permissive variant: fleet-shared memory lives in its own
    table with no ``agent_id`` at all, so every ``agent_id`` reaching the store is a real
    domain and validates the same way on reads and writes."""
    if not _DOMAIN_RE.fullmatch(name) or name in _RESERVED_DOMAINS:
        raise ValueError(
            f"invalid agent domain {name!r}: must match [a-z0-9-]+ and not be reserved "
            f"({sorted(_RESERVED_DOMAINS)})"
        )
    return name


class RecordType(str, Enum):
    """Drives the two read patterns: identity/reasoning/emotional — and the fleet's
    ``user_profile`` — are loaded whole at awaken; episode/knowledge are browsed via
    the index, bodies on demand.

    ``user_profile`` is fleet memory rather than an agent's: who the user is does not
    vary by agent, so it lives in ``shared_record`` alongside reasoning and knowledge.
    It is deliberately *not* the auth identity — that belongs to a future ``user`` table
    fed by verified token claims, and the two hold different facts (an account name vs
    what the user wants agents to call them)."""

    episode = "episode"
    knowledge = "knowledge"
    identity = "identity"
    reasoning = "reasoning"
    emotional = "emotional"
    user_profile = "user_profile"


@dataclass(kw_only=True)
class Agent:
    """An agent — the entity memory belongs to, not a memory item.

    ``uuid`` here is the agent's own "digital soul" id carried in its identity document.
    It is *content*, not a key: a human edits it in a markdown line, so the table is keyed
    on ``(user_id, agent_id)`` instead. There are no lifecycle fields because no operation
    in the system retires an agent."""

    user_id: str
    agent_id: str
    name: str | None = None
    role: str | None = None
    uuid: str | None = None
    created_date: str | None = None


@dataclass(kw_only=True)
class SharedRecord:
    """A fleet-shared memory item — reasoning or knowledge that belongs to no agent.

    ``id`` is the internal rowid (assigned by the store); ``uuid`` is the global/portable
    identity used across stores and for idempotency. ``kw_only`` is required rather than
    stylistic: ``MemoryRecord`` extends this with a mandatory field, which a positional
    dataclass forbids after defaulted ones."""

    uuid: str
    user_id: str
    record_type: RecordType
    full_content: str
    id: int | None = None
    project: str | None = None  # reserved for Hermod's project scope; unused by Munnin
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    created_date: str | None = None
    modified_date: str | None = None
    archived_date: str | None = None  # non-NULL = archived (out of hot index, still searchable)
    deleted_date: str | None = None  # non-NULL = soft-deleted tombstone (never surfaced)


@dataclass(kw_only=True)
class MemoryRecord(SharedRecord):
    """An agent-scoped memory item: a ``SharedRecord`` plus the agent that owns it.

    The extension is the point — it is exactly the difference between the two tables, so
    the type says what the schema says. ``agent_id`` is always a real agent; the store
    enforces it with a foreign key, and no sentinel value exists."""

    agent_id: str
