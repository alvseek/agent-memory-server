"""The transport-agnostic memory-service core.

Both adapters (MCP + HTTP) call THIS; it calls the injected repository. No
transport concerns leak in here. Memory operations (awaken, update_episodic,
add_reasoning, ...) land in Phase 5; Phase 4 provides only liveness.
"""

from __future__ import annotations

import hashlib
import re
import uuid as _uuid
from typing import Any

from munnin import __version__
from munnin.business_services.archive_rule import partition_episodes
from munnin.data_entities.memory_record import (
    Agent,
    EpisodeMetadata,
    MemoryRecord,
    RecordType,
    SharedRecord,
    validate_domain,
)
from munnin.data_repositories.memory_repository import MemoryRepository

#: The record types a browse index reads a ``content_summary`` from: ``episodic_index`` and
#: ``knowledge_index``, the two the awakening hands back as metadata-only listings. Every
#: other type is loaded whole at awakening, and the markdown backend has no artifact to author
#: a one-liner into for them, so requiring one there would ask for data nothing reads.
_SUMMARY_REQUIRED = (RecordType.episode, RecordType.knowledge)


def _whole(r: SharedRecord) -> dict[str, Any]:
    """Always-load section item — full body included."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "content": r.full_content,
    }


def _episode(r: SharedRecord | None) -> dict[str, Any] | None:
    """The latest-episode item: the whole record plus its ``project``, so a caller can
    tell a project-matched episode from the fallback without a second field."""
    if r is None:
        return None
    return {**_whole(r), "project": r.project}


def _index(r: SharedRecord) -> dict[str, Any]:
    """Browse section item — metadata only, no body (fetched on demand). Carries
    ``project`` so a caller can pick the episode for a project without loading bodies,
    and ``content_summary`` so the reader can judge whether to fetch one at all."""
    return {
        "uuid": r.uuid,
        "title": r.title,
        "content_summary": r.content_summary,
        "tags": r.tags,
        "project": r.project,
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
        "content_summary": r.content_summary,
        "tags": r.tags,
        "created_date": r.created_date,
        "modified_date": r.modified_date,
        "archived_date": r.archived_date,
        "content": r.full_content,
    }


def _episode_metadata(m: EpisodeMetadata) -> dict[str, Any]:
    """The scan's item shape: what the rule decided on, and nothing it did not read."""
    return {
        "uuid": m.uuid,
        "project": m.project,
        "title": m.title,
        "content_summary": m.content_summary,
        "tags": m.tags,
        "created_date": m.created_date,
        "modified_date": m.modified_date,
    }


def _agent(a: Agent) -> dict[str, Any]:
    """The agent entity's public shape. Carries ``uuid`` where the roster does not: a
    creation response confirms what was actually stored, while the roster stays three
    short fields per agent because whole identities overrun the client's output cap."""
    return {"agent_id": a.agent_id, "name": a.name, "role": a.role, "uuid": a.uuid}


#: A reasoning pattern's compression-survival capsule: everything after its final marker,
#: to the end of the body. Anchored at the end on purpose — the template puts the marker
#: last, and text appended after it is not part of the capsule.
_FINAL_CONCLUSION = re.compile(r"\*\*Final Conclusion\*\*:\s*(.*)\Z", re.DOTALL)

#: The template's sanctioned opt-out. A rule declaring it says it has no capsule, which
#: is intent, not a defect, so it leaves the block without being reported.
_NONE_DECLARED = "none declared"


def _final_conclusion(body: str) -> str | None:
    """The one line the always-on block keeps for a rule, or ``None`` when it has none."""
    match = _FINAL_CONCLUSION.search(body or "")
    if not match:
        return None
    return " ".join(match.group(1).split()) or None


def _permanent_layer_projection(shared: list[SharedRecord]) -> tuple[str, str, list[str]]:
    """The permanent layer's block, derived from records: ``(content, version, skipped)``.

    The universal RAS triggers come first, in the store's insertion order, which preserves
    the order the source file authored them in. Then one entry per reasoning record, in
    authoring order: the stored title as a heading, and the rule's ``Final Conclusion`` as
    the paragraph under it. Nothing is selected and nothing is authored, so a new rule is
    always-on the moment it is written and no artifact can fall behind the corpus.

    A rule with no capsule is left out and named in ``skipped``: dropping it silently
    would remove it from the always-on layer with nothing to notice. ``None declared`` is
    the template's explicit opt-out and is left out without a report.

    ``version`` is the newest ``modified_date`` among the records the block includes, so it
    moves when a rule is edited instead of being typed by hand. ``hash`` stays over the
    assembled text, which is what tells a stale local copy from a current one."""
    ras = sorted(
        (r for r in shared if r.record_type is RecordType.ras), key=lambda r: r.id or 0
    )
    rules = sorted(
        (r for r in shared if r.record_type is RecordType.reasoning),
        key=lambda r: (r.created_date or "", r.id or 0),
    )

    parts: list[str] = []
    included: list[SharedRecord] = []
    skipped: list[str] = []

    for record in ras:
        body = (record.full_content or "").strip()
        if body:
            parts.append(body)
            included.append(record)

    for record in rules:
        conclusion = _final_conclusion(record.full_content or "")
        if conclusion is None:
            skipped.append(record.title or record.uuid)
            continue
        if conclusion.casefold().startswith(_NONE_DECLARED):
            continue
        parts.append(f"### {record.title or record.uuid}\n{conclusion}")
        included.append(record)

    version = max(
        (r.modified_date or r.created_date or "" for r in included), default=""
    )
    return "\n\n".join(parts), version[:10], skipped


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

    def awaken(
        self, domain: str, caller: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Assemble an agent's memory payload from the DB (4-layer model, C-2).

        Always-load whole: layer i (fleet-shared reasoning, knowledge, the universal RAS
        triggers and the user profile) + layer ii (domain identity/reasoning/emotional).
        Index-only: layer iii
        (domain episode/knowledge) + the latest episode body. All reads are hot-read
        filtered (deleted + archived excluded) by the repository.

        Project-blind by design: no project is accepted or resolved here. ``latest_episode``
        is the newest episode overall, and the whole ``episodic_index`` is still returned
        with ``project`` on every entry, so a caller selects the episode for its own project
        and fetches it by id. The returned record's own ``project`` is how a caller tells a
        match from a fallback. Identity, reasoning, emotional and knowledge carry no project
        and are unaffected.

        ``shared.user_profile`` is a single record or ``None`` — who the user is does not
        vary by agent, so it is fleet memory rather than anyone's identity. ``None`` is a
        real answer meaning nobody has been asked yet, and it is what tells the awakening
        protocol to run its first-run bootstrap; a blank *field* inside a present record
        is a deliberate blank and must not trigger it.

        Layer i now comes from ``query_shared`` rather than from an agent named
        ``__shared__``. The payload shape is unchanged — it always was fleet memory;
        only the place it is stored stopped pretending to be an agent."""
        domain = validate_domain(domain)

        shared = self._repo.query_shared()
        shared_reasoning = [r for r in shared if r.record_type is RecordType.reasoning]
        shared_knowledge = [r for r in shared if r.record_type is RecordType.knowledge]
        shared_ras = [r for r in shared if r.record_type is RecordType.ras]
        # Filtered from the same fetch rather than re-queried — layer i is one round trip.
        profile = next((r for r in shared if r.record_type is RecordType.user_profile), None)

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
            # Who is signed in, when the face knows. Omitted rather than nulled when it
            # does not, so a caller can tell "nobody told us" from "a guest".
            **({"caller": caller} if caller is not None else {}),
            # layer i - always-load for every agent
            "shared": {
                "reasoning": [_whole(r) for r in shared_reasoning],
                "knowledge": [_whole(r) for r in shared_knowledge],
                "ras": [_whole(r) for r in shared_ras],
                "user_profile": _whole(profile) if profile else None,
            },
            # layer ii — this agent's identity
            "identity": [_whole(r) for r in identity],
            "reasoning": [_whole(r) for r in reasoning],
            "emotional": [_whole(r) for r in emotional],
            # layer iii — index only (+ latest episode body)
            "knowledge_index": [_index(r) for r in knowledge_idx],
            "episodic_index": [_index(r) for r in episodes],
            "latest_episode": _episode(latest),
        }

    def permanent_layer(self) -> dict[str, Any]:
        """The always-on permanent layer a client writes into its system prompt.

        Derived, per tenant, from the store's own records: the universal RAS triggers and
        the reasoning lane, projected into one block. This is the slice that must survive
        context compaction, which is why it is assembled here rather than pulled from
        ``awaken`` — ``awaken`` returns the full, perishable layer, and a tool result is
        eaten by compaction.

        Nothing is stored for it and nothing is authored, so there is no second copy to
        drift from the rules, and one tenant's reasoning never reaches another's. ``version``
        and ``hash`` are both derived: the date from the newest record the block includes,
        the hash over the assembled text, so a client can tell a stale local copy from a
        current one. ``skipped`` names any rule left out for having no capsule."""
        content, version, skipped = _permanent_layer_projection(self._repo.query_shared())
        return {
            "version": version,
            "hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:12],
            "content": content,
            "skipped": skipped,
        }

    # --- reads (load by id / browse / full-text) ---

    def get(self, uuid: str) -> dict[str, Any] | None:
        """Load one record's full body by id. Excludes soft-deleted. ``None`` if absent."""
        r = self._repo.get(uuid)
        return _record(r) if r else None

    def coding_reasoning(self) -> list[dict[str, Any]]:
        """The coding-reasoning lane, loaded whole.

        Fleet memory like ``shared.reasoning``, but only ever on a deliberate ask: ``awaken``
        selects its universal layer by ``record_type is reasoning``, so this lane never
        reaches a chat agent. This reuses ``query_shared``'s type filter rather than adding a
        repository op, because the lane is one record type over a read that already exists."""
        return [
            _whole(r)
            for r in self._repo.query_shared(record_type=RecordType.coding_reasoning)
        ]

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
        content_summary: str | None = None,
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

        ``content_summary`` is required for the types a browse index reads - ``episode`` and
        ``knowledge``: one line saying what the record holds, shown beside its title wherever
        a listing is rendered. It is what a reader decides on before fetching a body, so it is
        authored rather than derived, and a blank one is refused instead of stored as an
        absent answer. Every other type is loaded whole at awakening, so a summary there would
        be data nothing reads. ``edit_metadata`` replaces it when the content it describes
        changes.

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
        if content_summary is not None and not content_summary.strip():
            raise ValueError(
                "blank content_summary is not a value: leave it off, or clear a stored one "
                "with edit_metadata's clearing."
            )
        if rtype in _SUMMARY_REQUIRED and not content_summary:
            raise ValueError(
                f"content_summary is required for a {rtype.value}: one line saying what the "
                "record holds, which a listing shows beside its title."
            )
        common: dict[str, Any] = {
            "uuid": uuid or _uuid.uuid4().hex,
            "user_id": "",  # repo stamps server-side
            "record_type": rtype,
            "full_content": content,
            "title": title,
            "content_summary": content_summary,
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
        self,
        uuid: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity). Raises
        ``LookupError`` if missing/deleted, ``ValueError`` if ``old_string`` is absent or
        (without ``replace_all``) ambiguous.

        The body only. Every metadata field is ``edit_metadata``'s business, so a body
        edit and the summary that describes it are two calls: the summary is a claim about
        the body, and the op that owns it is named for that."""
        return _record(
            self._repo.edit(uuid, old_string, new_string, replace_all)
        )

    def edit_metadata(
        self,
        uuid: str,
        *,
        title: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        content_summary: str | None = None,
        clearing: list[str] | None = None,
    ) -> dict[str, Any]:
        """Change a record's metadata, leaving its body alone.

        The one writer for the four fields a record owns besides its body — ``title``,
        ``tags``, ``project`` and ``content_summary`` — and the only writer of
        ``content_summary``, because a field with one owner cannot be updated two ways.

        A field that is not passed keeps its stored value, so this is not a replace and
        never reads the body first. ``clearing`` names fields to remove, written as SQL
        NULL, and it is the only way to unset one: omitting a field means "leave it", and
        for ``project`` a blank string would still read as a project row, because both
        engines filter the corpora on ``project IS NULL``.

        A blank ``title``, ``project`` or ``content_summary`` is refused, the same way a
        blank summary is refused at insert: clearing has a name of its own, so an empty
        value can only arrive by accident. ``tags=[]`` is a value rather than a blank, and
        empties the list.

        Raises ``LookupError`` for a missing or deleted record, and ``ValueError`` when
        nothing would change or ``clearing`` names something that is not one of the four.
        """
        for name, value in (
            ("title", title),
            ("project", project),
            ("content_summary", content_summary),
        ):
            if value is not None and not value.strip():
                raise ValueError(
                    f"blank {name} is not a value: name it in `clearing` to remove it"
                )
        return _record(
            self._repo.set_fields(
                uuid,
                title=title,
                tags=tags,
                project=project,
                content_summary=content_summary,
                clearing=tuple(clearing or ()),
            )
        )

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

    def archive_memories(
        self, agent_id: str, *, days: int = 30, apply: bool = False
    ) -> dict[str, Any]:
        """Scan one agent's live episodes for themes that may be archived.

        ``apply=False`` is a dry run and writes nothing: it returns the three sets the
        rule produced. ``apply=True`` archives exactly ``auto`` (tagged ``finished`` and
        unprotected) and returns the uuids it archived. ``ask`` is never written here,
        because deciding an aging theme is a per-record judgment, and ``protected`` is
        reported with the reason each row was spared.
        """
        if not 1 <= days <= 3650:
            raise ValueError("days must be between 1 and 3650")
        partition = partition_episodes(
            self._repo.query_episode_metadata(validate_domain(agent_id)), days=days
        )
        archived: list[str] = []
        if apply:
            for row in partition.auto:
                self._repo.archive(row.uuid)
                archived.append(row.uuid)
        return {
            "agent_id": agent_id,
            "days": days,
            "applied": apply,
            "archived": archived,
            "auto": [_episode_metadata(row) for row in partition.auto],
            "ask": [_episode_metadata(row) for row in partition.ask],
            "protected": [
                {**_episode_metadata(row.record), "reason": row.reason}
                for row in partition.protected
            ],
        }

    def unarchive(self, uuid: str) -> dict[str, str]:
        """Return an archived record to the hot index. Raises ``LookupError`` when the
        record is absent or soft-deleted."""
        self._repo.unarchive(uuid)
        return {"uuid": uuid, "status": "active"}
