"""FastMCP adapter — the agent-facing MCP face (streamable-HTTP transport).

Exposes the full memory data-primitive surface as tools (twin of the HTTP face)
over the shared MemoryService core. The memory *procedures* (update-episodic,
add-reasoning, ...) are served as MCP Prompts and the templates as Resources — and both
again as tools (``read_procedure`` / ``read_resource``), because a Prompt is user-invoked
and a Resource client-attached, while a tool is the one primitive the protocol lets the
agent itself call. The data tools are the operations those procedures instruct the agent
to call.

A stranger who connects meets this surface cold, so the server also says what it is:
``INSTRUCTIONS`` goes out in the ``initialize`` result (clients inject it into the system
prompt), ``help`` returns the same text for clients that show no instructions, and every
tool carries a title and the read-only / destructive hints a client shows before it
lets a tool run.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from pydantic import Field

from munnin.business_services.memory_service import MemoryService
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.sharing_service import SharingError, SharingService
from munnin.business_services.tenant_resolver import TenantResolver
from munnin.content.loader import ContentLoader

#: What a client is told at ``initialize``. claude.ai and Claude Code inject it into the
#: system prompt, so it is re-sent on every call of every session — which is why it is
#: four sentences and not a manual: enough to act on with no other reading, and nothing
#: the tool list already says. ``help`` returns the same text for clients that ignore it.
INSTRUCTIONS = (
    "Munnin holds agent identity — an agent's memory of reasoning patterns, emotional "
    "moments, episodes and knowledge — and serves the procedures for tending it.\n"
    'New here: call list_agents(); if it is empty, read_procedure("create-agent") and '
    "follow it.\n"
    'Returning: read_procedure("awaken-agent", argument="<domain>") and follow it — '
    '<domain> is the agent you are being, e.g. "meta".\n'
    "Procedures come from read_procedure(name), never from slash commands; help() lists them."
)

# Tool annotations, by what a tool does to the store. Clients read these before letting a
# tool run: a read-only tool needs no confirmation, a destructive one earns a prompt. The
# spec's ``destructiveHint`` defaults to *true* and is meaningful only when a tool is not
# read-only, so the additive writes must say ``False`` explicitly or they read as
# destructive. ``openWorldHint`` is false throughout: nothing here reaches past the store.
_READ = {"readOnlyHint": True, "openWorldHint": False}
_ADDITIVE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
_DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}
# Archiving or tombstoning a record twice leaves it archived or tombstoned — a retry is safe.
_DESTRUCTIVE_IDEMPOTENT = {**_DESTRUCTIVE, "idempotentHint": True}

# Shared parameter semantics, not additional validation: defaults and wire types stay unchanged.
RecordRef = Annotated[
    str,
    Field(
        description="Existing record's full ID or unique UUID prefix of at least 6 hex "
        "characters, from query/search/get. UUID matching ignores case and hyphens; "
        "ambiguous prefixes are refused. Not an agent domain or project name."
    ),
]
ExistingAgent = Annotated[
    str, Field(description="Existing agent's kebab-case domain from list_agents, e.g. meta.")
]
OptionalAgent = Annotated[
    str | None,
    Field(
        description="Agent domain to filter by. Omit or pass null for all agents plus "
        "fleet-shared records; naming an agent excludes fleet-shared records."
    ),
]
OptionalProject = Annotated[
    str | None,
    Field(description="Exact project name filter. Omit or pass null for all projects."),
]
RecordKind = Annotated[
    str,
    Field(
        description="Memory type: episode, knowledge, identity, reasoning, emotional, "
        "user_profile, ras or coding_reasoning. Shared scope only permits reasoning, "
        "coding_reasoning, knowledge, ras and user_profile."
    ),
]
OldString = Annotated[
    str,
    Field(
        description="Exact body text to replace, including whitespace. Must occur once "
        "unless replace_all is true; absent or ambiguous matches are refused."
    ),
]
NewString = Annotated[
    str,
    Field(description="Replacement body text, verbatim. Use an empty string to remove the match."),
]
ReplaceAll = Annotated[
    bool, Field(description="False requires a unique match; true replaces every exact occurrence.")
]


def _procedure_rows(content: ContentLoader | None) -> list[dict[str, str]]:
    """Name, title and one-line purpose of every served procedure — the menu ``help`` and
    ``list_procedures`` both show, empty when no framework content is available."""
    if content is None or not content.available():
        return []
    return [
        {
            "name": name,
            "title": content.title_prompt(name),
            "description": content.describe_prompt(name),
        }
        for name in content.list_prompts()
    ]


def build_mcp(
    factory: ServiceFactory,
    resolver: TenantResolver,
    content: ContentLoader | None = None,
    auth: AuthProvider | None = None,
    endpoint: str | None = None,
) -> FastMCP:
    """The MCP face.

    ``auth`` guards every tool at the transport layer: FastMCP refuses an unverified
    request before any tool body runs, which is why the resolver below can trust the
    token it finds rather than re-checking it.

    ``endpoint`` is the address this face is served at, computed by the caller from the
    instance's public base URL (``app.mcp_resource_url``) — passed in rather than derived
    here because ``app`` imports this module, so the dependency only runs one way.
    """
    mcp: FastMCP = FastMCP("munnin", instructions=INSTRUCTIONS, auth=auth)

    def _svc() -> MemoryService:
        """The service for whoever is calling right now.

        Called inside each tool body rather than captured when the tool is registered:
        registration happens once at boot, and the caller is not known until the call."""
        return factory.for_user(resolver.current_user_id())

    def _check_template(record_type: str, declared: str | None) -> None:
        """The template-version write gate, closed over the build-time loader.

        A separate closure (rather than using ``content`` in the tool body) because
        ``insert`` takes its own ``content`` — the record body — which would shadow
        the loader. Skipped when no framework content is available: with nothing to
        check against, there is no check, the same way an absent submodule yields no
        procedures rather than failing the boot.
        """
        if content is not None and content.available():
            content.check_template_version(record_type, declared)

    @mcp.tool(title="Liveness check", annotations=_READ)
    def ping() -> str:
        """Check that the MCP handler responds; returns the string 'pong'.

        Takes no parameters and changes nothing. Does not test the database, content checkout,
        agent identity or completeness of stored memory.
        """
        return "pong"

    # Registered whether or not framework content is available: it is the fallback for a
    # client that never shows ``instructions``, so it has to exist in every configuration.
    @mcp.tool(name="help", title="What Munnin is and where to start", annotations=_READ)
    def help_() -> dict[str, Any]:
        """Start here to understand Munnin and choose the next memory procedure.

        Takes no parameters. Returns initialize instructions, the served procedure menu
        (name/title/description), access='mcp' and the configured endpoint, which may be null.
        Available without framework content; its procedure menu is then empty. Read-only:
        use read_procedure to fetch instructions, then follow them with the data tools.
        """
        # ``access`` is constant because this face only exists as served procedures: a
        # client calling it has already reached the core this way, so there is no second
        # answer to give. ``register-core-access`` reads both values and writes them into
        # the client's instruction file.
        return {
            "instructions": INSTRUCTIONS,
            "procedures": _procedure_rows(content),
            "access": "mcp",
            "endpoint": endpoint,
        }

    @mcp.tool(title="Awaken an agent", annotations=_READ)
    def awaken(domain: ExistingAgent) -> dict[str, Any]:
        """Assemble and return an agent's full memory payload from the DB.

        Loads the shared always-load layer + the agent's identity whole, plus the
        episodic/knowledge index and a page of the latest episode body. Project-blind: no
        project is accepted or resolved, ``latest_episode`` is the newest episode overall,
        and the whole index is returned with ``project`` on every entry so a caller selects.

        ``latest_episode`` is a page of up to three timestamp groups, never the whole rolling
        body: ``blocks_returned``/``blocks_total`` count groups and a non-null ``next_cursor``
        means more remain — continue with ``get(latest_episode.uuid, cursor=…)``. Every fixed
        layer above (identity, reasoning, emotional, knowledge, the shared layers) is whole.
        Read-only; follow read_procedure("awaken-agent", argument=domain) for the processing
        protocol. This returns data, not an automatically activated or newly created agent.
        """
        return _svc().awaken(domain, caller=_sharing().caller_block())

    @mcp.tool(title="Read the coding-reasoning lane", annotations=_READ)
    def coding_reasoning() -> list[dict[str, Any]]:
        """The coding-reasoning lane, loaded whole: the fleet's coding-only reasoning
        patterns. Kept out of ``awaken`` on purpose, so a chat agent never receives it; a
        coding awakening normally receives it through Hermod's awaken_coder payload.
        Takes no parameters. Returns full live shared coding-reasoning records, or an empty
        list when none are stored; this read does not create the lane.
        """
        return _svc().coding_reasoning()

    # --- reads ---

    @mcp.tool(title="Read one record", annotations=_READ)
    def get(
        uuid: RecordRef,
        cursor: Annotated[
            str | None,
            Field(
                description="Opaque next_cursor returned for this same record. Omit or pass "
                "null to start at the beginning; an unknown cursor is refused."
            ),
        ] = None,
        limit: Annotated[
            int | None,
            Field(
                description="Positive maximum timestamp groups per page, not lines or bytes. "
                "Omit or pass null to read up to the configured body-size ceiling."
            ),
        ] = None,
    ) -> dict[str, Any] | None:
        """Load one record by full ID or unique UUID prefix (at least 6 hex characters).
        Case and hyphens are ignored for UUID matching. Ambiguity errors list full IDs
        and titles; absent/deleted records return None. Existing-record writes accept
        the same references and refuse ambiguous prefixes before changing anything.

        The body comes back whole by default, still capped by the configured content
        ceiling. Pass ``cursor`` (a ``next_cursor`` from an earlier read) and/or ``limit``
        to read one page instead: limit counts timestamp groups and cursor resumes at the
        named group. Blocks sharing one ``###`` timestamp form an indivisible group.
        ``blocks_total`` counts the whole record; ``next_cursor`` is null only when nothing
        remains, so a final page may return fewer than ``blocks_total``. An unknown cursor or a
        nonpositive limit is an error, never a quiet fall back to the first page.
        Returns metadata, content, blocks_returned, blocks_total and next_cursor.
        Archived records remain readable by ID. Read-only; non-episode bodies are atomic.
        """
        try:
            return _svc().get(uuid, cursor=cursor, limit=limit)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Browse records by field", annotations=_READ)
    def query(
        agent_id: OptionalAgent = None,
        record_type: Annotated[
            str | None,
            Field(
                description="Exact memory type: episode, knowledge, identity, reasoning, "
                "emotional, user_profile, ras or coding_reasoning. Omit/null for all types."
            ),
        ] = None,
        project: OptionalProject = None,
        include_archived: Annotated[
            bool,
            Field(description="Include archived records when true; deleted records never appear."),
        ] = False,
    ) -> list[dict[str, Any]]:
        """Filter memory by exact field values — metadata only, never bodies: a browse
        answers what matches, ``blocks_total`` says how many timestamp groups its body
        holds, and the body itself is one ``get`` by uuid away. Naming an ``agent_id``
        reads that agent alone; omitting it also returns fleet-shared memory, whose rows
        carry no ``agent_id``. Filters combine with AND. Returns an empty list for no matches;
        invalid record types are refused. Reads only the selected tenant and changes nothing.
        """
        try:
            return _svc().query(
                agent_id=agent_id,
                record_type=record_type,
                project=project,
                include_archived=include_archived,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Full-text search", annotations=_READ)
    def search(
        text: Annotated[
            str,
            Field(
                description="Full-text keyword query across titles, bodies and tags; "
                "not a UUID lookup."
            ),
        ],
        include_archived: Annotated[
            bool,
            Field(
                description="True includes archived matches (the default); "
                "false searches live records only."
            ),
        ] = True,
    ) -> list[dict[str, Any]]:
        """Full-text keyword search over content + title + tags, both corpora.

        Each hit is metadata plus a plain-text ``snippet`` of the match — **not** a body;
        read one with ``get`` when it is worth opening. Archived records are searchable by
        default, soft-deleted never are, and a title-only or tag-only match still yields an
        excerpt. Agent hits carry ``agent_id``; fleet hits do not. Searches the selected tenant
        only, returns an empty list for no matches and changes nothing. Ranking is per corpus,
        not one global relevance score across agent and shared results.
        """
        return _svc().search(text, include_archived=include_archived)

    @mcp.tool(title="List the agents", annotations=_READ)
    def list_agents() -> list[dict[str, Any]]:
        """List every agent in the fleet: ``agent_id`` + display name + one-line role.
        Metadata only, no bodies. Stored ``name``/``role`` may be null when unset; agents
        without identity records are still listed. Takes no parameters and reads
        the selected tenant. An empty list means no agents are registered there; follow
        read_procedure("create-agent") to create one rather than inventing a domain.
        """
        return _svc().list_agents()

    # --- sharing: which tenant you act in, and who may enter yours ---
    #
    # These read the caller's *home* tenant, never the resolved one. That is what keeps
    # them reachable while every memory tool is refusing because the selection names a
    # tenant whose access was revoked: the way out must not be behind the door.

    def _sharing() -> SharingService:
        """The sharing rules for whoever is calling right now."""
        return factory.sharing_for(resolver.current_home_user_id())

    @mcp.tool(title="List the tenants you may act in", annotations=_READ)
    def list_tenants() -> list[dict[str, Any]]:
        """Every tenant open to you: your own first, then the ones you were granted.
        ``role`` is ``owner`` for your own tenant and ``guest`` for a granted one, and
        ``active`` marks the one your calls are currently acting in. Access is whole
        tenant, so this list is the whole choice; there is nothing per agent or project.
        Takes no parameters. Each row has user_id, role, label, active and revoked. A selected
        tenant whose grant ended is also listed, marked revoked; it is not permission to enter.
        Use use_tenant to select one or return home. Read-only.
        """
        return [
            {
                "user_id": ref.user_id,
                "role": ref.role,
                "label": ref.label,
                "active": ref.active,
                "revoked": ref.revoked,
            }
            for ref in _sharing().list_tenants()
        ]

    @mcp.tool(title="Act in one of your tenants", annotations=_ADDITIVE)
    def use_tenant(
        tenant: Annotated[
            str | None,
            Field(
                description="Tenant user_id from list_tenants, or an exact uniquely matching "
                "label. Omit, pass null or an empty string to return to your own tenant."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Switch which tenant your calls act in; ``None`` returns to your own.
        ``tenant`` is an id from ``list_tenants``, or its label when that label names
        exactly one tenant you may enter. The choice is remembered per person, so it
        survives a restart and applies to every client you sign in with. A tenant whose
        access was revoked is refused by name, and is always switchable away from.
        Changes a persistent selection, not just this session; subsequent memory reads and writes
        from your clients use it. Returns user_id, role, label and active=true for the selection.
        Does not move, copy or delete memory, or grant access to an unpermitted tenant.
        """
        try:
            ref = _sharing().use_tenant(tenant)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc
        return {"user_id": ref.user_id, "role": ref.role, "label": ref.label, "active": True}

    @mcp.tool(title="List who has access to this tenant", annotations=_READ)
    def list_members() -> list[dict[str, Any]]:
        """List current members of the selected tenant, including its owner.

        Takes no parameters. Returns user_id, role, label and granted_date for each member;
        revoked grants are excluded. Use a guest's user_id with revoke_member if you own the
        tenant. Read-only; this does not list outstanding invitations.
        """
        try:
            return _sharing().list_members()
        except SharingError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Invite somebody to this tenant", annotations=_ADDITIVE)
    def create_invite(
        days: Annotated[
            int, Field(description="Invitation lifetime in days from creation; defaults to 7.")
        ] = 7,
    ) -> dict[str, Any]:
        """Mint a single-use code that admits whoever redeems it to this tenant.
        Only the owner of the tenant you are acting in may call this. The code expires in
        ``days`` days, works once, and can be revoked before use with ``revoke_invite``.
        Send it to the person out of band; they redeem it with ``redeem_invite``.
        Returns code, tenant_user_id, created_date and expires_date. Treat the code as a
        credential: redemption grants whole-tenant access, not read-only or per-agent access.
        """
        try:
            invite = _sharing().create_invite(days)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc
        return {
            "code": invite.code,
            "tenant_user_id": invite.tenant_user_id,
            "created_date": invite.created_date,
            "expires_date": invite.expires_date,
        }

    @mcp.tool(title="Revoke an unused invitation", annotations=_DESTRUCTIVE)
    def revoke_invite(
        code: Annotated[
            str, Field(description="Exact unused invitation code returned by create_invite.")
        ],
    ) -> dict[str, Any]:
        """Revoke an unused invitation to your selected tenant; owner-only.

        Returns code and revoked=true. Unknown, already used or already revoked codes are
        refused. Does not remove a redeemed membership; use revoke_member for that.
        """
        try:
            _sharing().revoke_invite(code)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc
        return {"code": code, "revoked": True}

    @mcp.tool(title="Join a tenant with an invitation", annotations=_ADDITIVE)
    def redeem_invite(
        code: Annotated[
            str, Field(description="Single-use invitation code received from the tenant owner.")
        ],
    ) -> dict[str, Any]:
        """Join the tenant an invitation names, as a guest. Does not switch you into it.
        Redeem first, then call ``use_tenant`` when you want to work there; your own
        tenant and everything in it are untouched by joining. Returns tenant_user_id and label
        with role='guest'. Unknown, expired, revoked, used or own-tenant invitations are refused.
        Consumes the invitation and grants whole-tenant access.
        """
        try:
            return _sharing().redeem(code)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Revoke somebody's access", annotations=_DESTRUCTIVE)
    def revoke_member(
        member: Annotated[
            str,
            Field(
                description="Guest's exact user_id from list_members, "
                "not their label or an agent domain."
            ),
        ],
    ) -> dict[str, Any]:
        """End a person's access to the tenant you are acting in, which you must own.
        ``member`` is the ``user_id`` from ``list_members``. Their access ends on their
        next call, immediately, and nothing they wrote is deleted. Returns member and revoked=true.
        Cannot revoke your own ownership; an unknown or already revoked membership is refused.
        """
        try:
            _sharing().revoke_member(member)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc
        return {"member": member, "revoked": True}

    @mcp.tool(title="Create an agent", annotations=_ADDITIVE)
    def create_agent(
        agent_id: Annotated[
            str,
            Field(
                description="New kebab-case agent domain, e.g. backend-python; "
                "must not already exist."
            ),
        ],
        name: Annotated[
            str | None, Field(description="Agent's display name; omit/null if not yet assigned.")
        ] = None,
        role: Annotated[
            str | None,
            Field(description="One-line specialty for list_agents; omit/null if not yet assigned."),
        ] = None,
        uuid: Annotated[
            str | None,
            Field(
                description="Optional identity-document UUID for the agent, "
                "not a memory-record reference."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a new agent. ``agent_id`` is a kebab domain and must not already exist —
        creating over a live agent raises rather than overwriting its identity. Call this
        **before** inserting any of the agent's memory: memory names an owner the store
        checks, so an insert for an agent with no row is refused. ``uuid`` is the agent's
        own "digital soul" id from its identity document. Returns agent_id, name, role and uuid.
        Creates only the agent registration in the selected tenant, not its identity or memories;
        follow read_procedure("create-agent") for the full creation workflow.
        """
        return _svc().create_agent(agent_id=agent_id, name=name, role=role, uuid=uuid)

    # --- writes (Edit-tool parity; record assembled server-side) ---

    @mcp.tool(title="Insert a memory record", annotations=_ADDITIVE)
    def insert(
        record_type: RecordKind,
        content: Annotated[
            str,
            Field(
                description="Complete authored record body, following its current template; "
                "no template_version stamp."
            ),
        ],
        content_summary: Annotated[
            str | None,
            Field(
                description="Authored nonblank one-line summary, required for episode "
                "and knowledge; omit/null otherwise."
            ),
        ] = None,
        agent_id: Annotated[
            str | None,
            Field(
                description="Existing owner domain, required for scope=agent; "
                "must be omitted/null for scope=shared."
            ),
        ] = None,
        scope: Annotated[
            str,
            Field(
                description="agent (default) for one owner's memory; "
                "shared for fleet-wide memory without an owner."
            ),
        ] = "agent",
        title: Annotated[
            str | None,
            Field(description="Display title for this record; omit/null if not supplied."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Searchable tag strings; omit/null for an empty list."),
        ] = None,
        project: Annotated[
            str | None,
            Field(
                description="Project to file the record under; "
                "omit/null for memory without a project."
            ),
        ] = None,
        uuid: Annotated[
            str | None,
            Field(
                description="Optional full record ID for idempotent insertion/upsert, never a "
                "short prefix. Omit/null to generate a new UUID; reuse may update an existing row."
            ),
        ] = None,
        template_version: Annotated[
            str | None,
            Field(
                description="Exact current stamp from read_resource for this type's template. "
                "Required for episode, reasoning, emotional, knowledge and coding_reasoning "
                "when framework content is available. Pass separately, not in the body."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Append a new memory item. ``scope="agent"`` (the default) writes memory owned
        by ``agent_id``, which must be an existing kebab domain; ``scope="shared"`` writes
        fleet-wide memory owned by nobody and takes no ``agent_id``. ``record_type`` ∈
        episode|knowledge|identity|reasoning|emotional|user_profile|ras|coding_reasoning,
        and fleet memory may only be reasoning, coding_reasoning, knowledge, ras or
        user_profile — ras is the universal RAS triggers, coding_reasoning is the coding
        layer's own lane, and the profile is fleet-wide because who the user is does not
        vary by agent. ``template_version`` declares which version of the record type's
        template the content was built against (read it with read_resource first); the
        gated types (episode|reasoning|emotional|knowledge|coding_reasoning) are refused
        without a matching one. ``content_summary`` is required for the types a browse index
        reads (``episode``, ``knowledge``): one line saying what the record holds, which a
        listing shows beside its title and a reader decides on before fetching the body.
        Author it; a blank one is refused. Other types do not require one.
        Writes to the selected tenant and returns the stored record with body and metadata.
        A supplied UUID is an upsert key: this is not guaranteed to create a new row on replay.
        """
        _check_template(record_type, template_version)
        return _svc().insert(
            agent_id=agent_id,
            scope=scope,
            record_type=record_type,
            content=content,
            content_summary=content_summary,
            title=title,
            tags=tags,
            project=project,
            uuid=uuid,
        )

    @mcp.tool(title="Edit a record's body", annotations=_DESTRUCTIVE)
    def edit(
        uuid: RecordRef,
        old_string: OldString,
        new_string: NewString,
        replace_all: ReplaceAll = False,
    ) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity). The body
        only: metadata, `content_summary` included, is `edit_metadata`'s business, so a
        body edit and the summary describing it are two calls on two named tools.
        Returns the updated record. Missing/deleted targets or absent/ambiguous matches fail
        without an edit; use get to obtain the exact text before replacing it.
        """
        return _svc().edit(uuid, old_string, new_string, replace_all)

    @mcp.tool(title="Append to a record", annotations=_ADDITIVE)
    def append(
        uuid: RecordRef,
        text: Annotated[
            str,
            Field(description="Text to append verbatim; include leading newlines for separation."),
        ],
    ) -> dict[str, Any]:
        """Add ``text`` to the END of a record's body. Verbatim — include your own
        leading newline(s) for spacing (e.g. a new sub-episode under a date header).
        Returns the updated record; missing/deleted targets are refused. Does not update metadata
        or its summary. Retrying duplicates the appended text.
        """
        return _svc().append(uuid, text)

    @mcp.tool(title="Prepend to a record", annotations=_ADDITIVE)
    def prepend(
        uuid: RecordRef,
        text: Annotated[
            str,
            Field(
                description="Text to prepend verbatim; include trailing newlines for separation."
            ),
        ],
    ) -> dict[str, Any]:
        """Add ``text`` to the START of a record's body. Verbatim — include your own
        trailing newline(s) for spacing. Returns the updated record; missing/deleted targets
        are refused. Does not update metadata or its summary. Retrying duplicates the text.
        """
        return _svc().prepend(uuid, text)

    @mcp.tool(title="Apply several edits atomically", annotations=_DESTRUCTIVE)
    def multi_edit(
        uuid: RecordRef,
        edits: Annotated[
            list[dict[str, Any]],
            Field(
                description="Nonempty ordered list of objects with old_string and new_string "
                "string values, plus optional replace_all (default false). Each matches the "
                "body resulting from the previous edit; all edits succeed or none are written."
            ),
        ],
    ) -> dict[str, Any]:
        """Apply a sequence of string edits to one record atomically (all-or-nothing).

        Each edit is a dict with ``old_string`` + ``new_string`` (+ optional
        ``replace_all``). Edits apply in order, each to the result of the previous; if
        any fails, nothing is written. Returns the updated record; missing/deleted targets and
        malformed or empty edits are refused. Body only; update its summary with edit_metadata.
        """
        return _svc().multi_edit(uuid, edits)

    @mcp.tool(title="Edit a record's metadata", annotations=_DESTRUCTIVE)
    def edit_metadata(
        uuid: RecordRef,
        title: Annotated[
            str | None,
            Field(
                description="New nonblank display title; omit/null to keep it. "
                "Use clearing to remove it."
            ),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(
                description="Replacement tag list; [] empties it. Omit/null to keep existing tags."
            ),
        ] = None,
        project: Annotated[
            str | None,
            Field(
                description="New nonblank project name; omit/null to keep it. "
                "Use clearing to remove it."
            ),
        ] = None,
        content_summary: Annotated[
            str | None,
            Field(
                description="New nonblank authored summary; omit/null to keep it. "
                "Use clearing to remove it."
            ),
        ] = None,
        clearing: Annotated[
            list[str] | None,
            Field(
                description="Fields to set to null: title, tags, project and/or content_summary. "
                "Omit/null to clear nothing; do not also supply a replacement for a cleared field."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Change a record's metadata, leaving its body alone.

        `title`, `tags`, `project` and `content_summary` are the fields a record owns
        beside its body. Use this to update an existing record's summary; body-edit tools
        do not update it. A field you leave out keeps its stored
        value, so this is not a replace: omit `title` and the title stands. Name fields in
        `clearing` to remove them, which is the only way, because a blank string is refused
        rather than stored (for `project`, an empty value still reads as a project row).
        `tags=[]` is a real value and empties the list. Refuses a call that would change
        nothing.
        Returns the updated record. Missing/deleted targets, unsupported clearing fields and
        calls with no effective change are refused.
        """
        return _svc().edit_metadata(
            uuid,
            title=title,
            tags=tags,
            project=project,
            content_summary=content_summary,
            clearing=clearing,
        )

    @mcp.tool(title="Archive a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def archive(uuid: RecordRef) -> dict[str, str]:
        """Archive a record without deleting its body; returns uuid and status='archived'.

        Removes it from awakening and default query results. Search includes archived records
        by default, and get still reads it by ID. Use unarchive to restore it. Repeating is safe;
        a missing/deleted target is refused.
        """
        return _svc().archive(uuid)

    @mcp.tool(title="Scan for archivable episodes", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def archive_memories(
        agent_id: ExistingAgent,
        days: Annotated[
            int,
            Field(
                description="Age in days for the ask set, based on last modification; "
                "1–3650, default 30."
            ),
        ] = 30,
        apply: Annotated[
            bool,
            Field(
                description="False previews only. True archives auto candidates, "
                "never ask or protected rows."
            ),
        ] = False,
    ) -> dict[str, Any]:
        """Scan one agent's episodes and report what may be archived.

        ``auto`` is tagged ``finished`` and unprotected; ``apply=True`` archives exactly
        that set. ``ask`` is untagged and not modified within ``days``, and is never
        written here because deciding it is a per-record judgment. ``protected`` names
        the rows the rule refuses, with the reason. The default ``apply=False`` writes
        nothing. Returns agent_id, days, applied, archived UUIDs and the auto/ask/protected
        candidate lists, including protection reasons. Refuses an unknown agent or invalid days.
        """
        return _svc().archive_memories(agent_id, days=days, apply=apply)

    @mcp.tool(title="Unarchive a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def unarchive(uuid: RecordRef) -> dict[str, str]:
        """Restore an archived record to awakening and normal query results.

        Returns uuid and status='active'. Repeating is safe. Does not undo soft deletion;
        a missing/deleted target is refused. The body and other metadata remain intact.
        """
        return _svc().unarchive(uuid)

    @mcp.tool(title="Soft-delete a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def soft_delete(uuid: RecordRef) -> dict[str, str]:
        """Tombstone a record, hiding it from get, query, search and awakening.

        Returns uuid and status='deleted'. This is not an archive: unarchive does not restore
        deleted records, and no undelete tool is exposed. Repeating is safe; unknown IDs fail.
        Does not physically erase the stored row.
        """
        return _svc().soft_delete(uuid)

    if content is not None and content.available():
        _register_content(mcp, content, _svc)

    return mcp


def _register_content(
    mcp: FastMCP, content: ContentLoader, svc: Callable[[], MemoryService]
) -> None:
    """Register served procedures as Prompts, templates as Resources — and both as tools.

    All read live from the control-files submodule; procedures are composed with the db
    storage backend so the served text speaks DB tools, not markdown files. The twin of
    these is the FastAPI ``/api/prompts`` + ``/api/resources``.

    The tools are the same content through a door the agent can open itself. A served
    procedure that says "execute ``/wrap-up``" is addressed to an agent with no picker to
    run it from; ``read_procedure("wrap-up")`` is what that instruction resolves to on
    this backend (the rule rides in the awakening procedure's db mechanics).
    """

    def _make_prompt(procedure: str, argument: tuple[str, str] | None):
        # FastMCP derives a prompt's arguments from the function signature, so a procedure
        # that takes one needs a real parameter carrying its name. The parameter is built
        # dynamically because each procedure names its argument differently, and both
        # ``__signature__`` and ``__annotations__`` must be set — pydantic reads the second
        # and raises on the first alone. A plain ``str`` annotation is deliberate: an
        # ``Annotated[str, Field(...)]`` makes FastMCP append a JSON-schema instruction to
        # the description, which reads as noise in a command menu.
        def fn(**kwargs: str) -> str:
            return content.get_prompt(procedure, kwargs.get(argument[0]) if argument else None)

        fn.__name__ = procedure.replace("-", "_")
        if argument is None:
            # A bare signature, or FastMCP sees the raw ``**kwargs`` and refuses the prompt.
            # This branch was never reached until the first argument-less procedure was
            # served (``wait-options``, a format reference that takes nothing).
            fn.__annotations__ = {"return": str}
            fn.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                [], return_annotation=str
            )
            return fn
        arg_name, arg_help = argument
        fn.__doc__ = (
            f"{procedure}\n\nArgs:\n    {arg_name}: {arg_help}. "
            "Optional text substituted into $ARGUMENTS; fetching does not execute the procedure.\n"
        )
        fn.__annotations__ = {arg_name: str, "return": str}
        parameter = inspect.Parameter(
            arg_name, inspect.Parameter.KEYWORD_ONLY, default="", annotation=str
        )
        fn.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            [parameter], return_annotation=str
        )
        return fn

    for name in content.list_prompts():
        mcp.prompt(
            name=name,
            title=content.title_prompt(name),
            description=content.describe_prompt(name),
        )(_make_prompt(name, content.argument_prompt(name)))

    def _make_resource(resource: str):
        # Zero-arg so FastMCP registers a static resource, not a URI template.
        def fn() -> str:
            return content.get_resource(resource)

        fn.__name__ = f"resource_{resource.replace('-', '_')}"
        return fn

    for name in content.list_resources():
        script = content.is_script(name)
        mcp.resource(
            f"resource://{'scripts' if script else 'templates'}/{name}",
            name=name,
            title=content.title_resource(name),
            description=content.describe_resource(name),
            mime_type="text/x-shellscript" if script else "text/markdown",
            # A fill-in template is written by an agent and read by nobody else, and a
            # script is run by one; either way the audience is the assistant. The priority
            # is near the floor because `priority` scores whether a client should pull
            # something into context unasked, and both earn their place only when
            # deliberately fetched. Not 0.0: that is the spec's "entirely optional", and a
            # client could reasonably read it as "hide", which would take these out of a
            # picker where they do belong.
            annotations={"audience": ["assistant"], "priority": 0.1},
        )(_make_resource(name))

    # --- the same content as tools: the one primitive the agent may invoke itself ---

    def _not_served(kind: str, name: str, listing: str) -> dict[str, Any]:
        # A tool's caller is an agent typing whatever a procedure told it to type, so an
        # unknown name is an answer to give, not an error to raise — the raise is right
        # for the Prompt surface, where a client can only ask for a registered name.
        return {
            "served": False,
            "name": name,
            "note": f"no served {kind} named {name!r}; call {listing} to see what is",
        }

    @mcp.tool(title="List served procedures", annotations=_READ)
    def list_procedures() -> list[dict[str, str]]:
        """List the framework procedures this server serves — name, title, one-line purpose.

        Takes no parameters. A procedure is the how-to an agent follows before calling data
        tools. Pass a returned name to read_procedure. Read-only discovery: does not execute
        instructions or load an agent's memory.
        """
        return _procedure_rows(content)

    @mcp.tool(title="Read a served procedure", annotations=_READ)
    def read_procedure(
        name: Annotated[
            str, Field(description="Exact procedure name from list_procedures, without / or .md.")
        ],
        argument: Annotated[
            str | None,
            Field(
                description="Optional text for $ARGUMENTS, using the procedure's documented "
                "format (e.g. a domain for awaken-agent). Omit/null/empty leaves authored text."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Read a served framework procedure, composed for this server's storage backend.

        Use this whenever a procedure or instruction tells you to execute, invoke or run a
        slash command such as `/wrap-up`: call read_procedure("wrap-up") instead of the
        slash command and follow what it returns. `argument` fills the procedure's
        $ARGUMENTS slot (the domain for awaken-agent, a mode for wrap-up). A name that is
        not served returns served=false rather than an error. Success returns served=true,
        name and content; a miss returns name and a discovery note. Read-only: fetching does
        not run the procedure or perform any memory writes it describes.
        """
        try:
            text = content.get_prompt(name, argument)
        except KeyError:
            return _not_served("procedure", name, "list_procedures()")
        return {"served": True, "name": name, "content": text}

    @mcp.tool(title="List served resources", annotations=_READ)
    def list_resources() -> list[dict[str, str]]:
        """List the framework resources this server serves — name, title, one-line purpose.

        Takes no parameters. A resource is a template (the format filled in when one memory
        entry is written) or an agent-facing script (a helper you fetch and run). Read one with
        read_resource(name). Read-only discovery: does not write a file or run a script.
        """
        return [
            {
                "name": name,
                "title": content.title_resource(name),
                "description": content.describe_resource(name),
            }
            for name in content.list_resources()
        ]

    @mcp.tool(title="Read a served resource", annotations=_READ)
    def read_resource(
        name: Annotated[
            str,
            Field(
                description="Exact resource stem from list_resources, "
                "without directory, extension or resource URI."
            ),
        ],
    ) -> dict[str, Any]:
        """Read a served framework resource verbatim — a template or a script.

        Use this when a served instruction points at a file by relative path: a reference
        to `resources/episodic-entry-template.md` or `scripts/copy-lines.sh` is
        read_resource("episodic-entry-template") / read_resource("copy-lines"). A name that
        is not served returns served=false rather than an error. Success returns served=true,
        name and content; a miss includes a discovery note. Does not execute scripts or save
        files. For template-gated writes, read the template's stamp and pass it separately.
        """
        try:
            text = content.get_resource(name)
        except KeyError:
            return _not_served("resource", name, "list_resources()")
        return {"served": True, "name": name, "content": text}

    # --- the permanent layer: the slice a client pushes into its system prompt ---

    @mcp.tool(title="Read the permanent layer", annotations=_READ)
    def permanent_layer() -> dict[str, Any]:
        """The always-on memory a client writes into its system-prompt file: the
        universal RAS triggers plus one entry per reasoning rule, with a content hash.

        Both halves come from this tenant's own records, so one account's reasoning is
        never served to another's, and nothing is authored or stored for the block.
        ``skipped`` names any rule left out for carrying no ``Final Conclusion``; a
        rule explicitly opting out with 'None declared' is omitted without being listed.

        This is the slice that must survive context compaction, which is why it is
        pushed into the harness's instruction file rather than pulled per session — a
        tool result is conversation history and compaction eats it. The hash tells a
        stale local copy from a current one. Follow read_procedure("anchor-memory") to
        install it. Takes no parameters. Returns version, hash, content and skipped; this
        read does not install or update the client's local instruction file.
        """
        return svc().permanent_layer()
