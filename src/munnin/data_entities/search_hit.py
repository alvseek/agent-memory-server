"""A search hit: the record's metadata plus the excerpt that matched — never its body.

``search`` used to return whole ``MemoryRecord`` entities, which meant a keyword lookup
transported every full body it matched. The match is what the caller asked for, so this is
the projection that answers it: the same identity/owner/lifecycle fields a browse entry
carries, plus a backend-generated ``snippet``.

It is deliberately **not** a ``MemoryRecord``. Pretending a truncated excerpt is a record
would let any later caller read ``full_content`` and believe it had the document, so the
type says what it holds instead of relying on a convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from munnin.data_entities.memory_record import RecordType


@dataclass(kw_only=True)
class SearchHit:
    """One match: where it is, what it is, and the plain-text window that matched.

    ``agent_id`` is absent (``None``) for fleet-shared memory, which is the same
    self-labelling rule every other merged read uses: presence means an agent owns it.
    ``snippet`` is plain text — no markup, no HTML — because a backend highlight is a
    rendering hint this server does not get to trust into a client's prompt.
    """

    uuid: str
    record_type: RecordType
    snippet: str
    agent_id: str | None = None
    project: str | None = None
    title: str | None = None
    content_summary: str | None = None
    tags: list[str] = field(default_factory=list)
    created_date: str | None = None
    modified_date: str | None = None
    archived_date: str | None = None
