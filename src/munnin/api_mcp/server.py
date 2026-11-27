"""FastMCP adapter — the agent-facing MCP face (streamable-HTTP transport).

Exposes the full memory data-primitive surface as tools (twin of the HTTP face)
over the shared MemoryService core. The memory *procedures* (update-episodic,
update-reasoning, ...) are served as MCP Prompts and the templates as Resources — and both
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

from munnin.business_services.memory_service import (
    CONTENT_SUMMARY_MAX_CHARACTERS,
    MemoryService,
)
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.sharing_service import (
    SharingError,
    SharingService,
    TenantAccessRevoked,
)
from munnin.business_services.tenant_resolver import TenantResolver
from munnin.content.discovery import catalog_rows
from munnin.content.loader import ContentLoader
from munnin.data_entities.edit_context import EditConflict

#: What a client is told at ``initialize``. claude.ai and Claude Code inject it into the
#: system prompt, so keep it brief. ``help`` returns the same text for other clients.
INSTRUCTIONS = (
    "Munnin holds agent identity — an agent's memory of reasoning patterns, emotional "
    "moments, episodes and knowledge — and serves the procedures for tending it.\n\n"
    "Returning agent: the user may supply the awaken-agent procedure directly as the prompt "
    "or ask you to invoke /munnin:awaken-agent.\n\n"
    "- Procedure supplied as the prompt: follow the instructions in the prompt.\n"
    '- Request to invoke the procedure: call read_procedure("awaken-agent", argument="<domain>"), '
    "then follow the returned instructions. For example, for the meta agent, call "
    'read_procedure("awaken-agent", argument="meta").\n\n'
    'New here: if you have no stored agent yet, call read_procedure("create-agent") and follow '
    "its instructions to create one. Once created, awaken that agent using the "
    "awaken-agent procedure."
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
        "characters, from list_memories or search_memories. "
        "UUID matching ignores case and hyphens; "
        "ambiguous prefixes are refused. Not an agent domain or project name."
    ),
]
ExistingAgent = Annotated[
    str, Field(description="Existing agent's kebab-case domain from list_agents, e.g. meta.")
]
EntryTitle = Annotated[
    str, Field(description="Subject, e.g. 'Catalog released'; omit the date and heading prefix.")
]
EntryBody = Annotated[
    str, Field(description="Filled episodic-entry-template rows, without the heading or separator.")
]
EpisodeVersion = Annotated[
    str | None,
    Field(
        description="Copy template_version from "
        "read_resource('episodic-entry-template') when served."
    ),
]
OptionalAgent = Annotated[
    str | None,
    Field(
        description="Agent domain from list_agents, e.g. "
        "'software-architect'. Omit/null for all agents plus "
        "fleet-shared records; naming an agent excludes fleet-shared records."
    ),
]
OptionalProject = Annotated[
    str | None,
    Field(
        description="Exact repository name, e.g. 'invintiry'. Omit or pass null for all projects."
    ),
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
        description="Copy exact text from get_memory, including whitespace. Must occur once "
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
ExpectedRevision = Annotated[
    str | None,
    Field(
        description="Opaque revision from get_memory(include_edit_context=true). Supply together "
        "with expected_tenant; stale saves are refused without changes."
    ),
]
ExpectedTenant = Annotated[
    str | None,
    Field(
        description="Copy edit_context.tenant from that same read, a "
        "precondition not a selector. "
        "Supply together with expected_revision."
    ),
]


CatalogQuery = Annotated[
    str,
    Field(
        description="Name or title phrase, e.g. 'update memory'. Case is ignored; "
        "spaces, hyphens and underscores are equivalent."
    ),
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
        try:
            return factory.for_user(resolver.current_home_user_id())
        except TenantAccessRevoked as exc:
            raise ToolError(str(exc)) from exc

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
        """Return 'pong' if the MCP handler responds; does not test storage."""
        return "pong"

    # Registered whether or not framework content is available: it is the fallback for a
    # client that never shows ``instructions``, so it has to exist in every configuration.
    @mcp.tool(name="help", title="What Munnin is and where to start", annotations=_READ)
    def help_() -> dict[str, Any]:
        """Read server instructions, the procedure menu and endpoint. The menu is empty when
        framework content is unavailable."""
        # ``access`` is constant because this face only exists as served procedures: a
        # client calling it has already reached the core this way, so there is no second
        # answer to give. ``register-core-access`` reads both values and writes them into
        # the client's instruction file.
        return {
            "instructions": INSTRUCTIONS,
            "procedures": catalog_rows(content, "procedures"),
            "access": "mcp",
            "endpoint": endpoint,
        }

    @mcp.tool(title="Awaken an agent", annotations=_READ)
    def awaken(domain: ExistingAgent) -> dict[str, Any]:
        """Load an existing agent's identity, reasoning, emotional memory, knowledge and episode
        indexes, and newest episode page across projects. Read-only."""
        return _svc().awaken(domain, caller=_sharing().caller_block())

    @mcp.tool(title="Read the coding-reasoning lane", annotations=_READ)
    def coding_reasoning() -> list[dict[str, Any]]:
        """Read the shared coding-only reasoning patterns omitted from awaken."""
        return _svc().coding_reasoning()

    # --- reads ---

    @mcp.tool(title="Read one record", annotations=_READ)
    def get_memory(
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
        include_edit_context: Annotated[
            bool,
            Field(
                description="True adds full UUID, acting tenant and opaque full-row revision "
                "for conflict-safe editing. Compare every page's context before enabling Save."
            ),
        ] = False,
    ) -> dict[str, Any] | None:
        """Read a memory record by ID, including archived records. For paged reads, limit counts
        timestamp groups; continue with next_cursor on the same record until null. For edits
        across pages, require matching edit_context on every page and use edit_body source
        positions and digest to reconstruct the original text."""
        try:
            return _svc().get(
                uuid, cursor=cursor, limit=limit, include_edit_context=include_edit_context
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(title="Browse records by field", annotations=_READ)
    def list_memories(
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
        """List memory records matching all supplied filters. Results include UUID, type, title,
        summary and tags. Read a body with get_memory."""
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
    def search_memories(
        text: Annotated[
            str,
            Field(
                description="Words to find in memory, e.g. 'catalog release'; not a UUID lookup."
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
        """Search titles, bodies and tags across agent and shared memory. Hits contain snippets;
        use get_memory for bodies. Includes archived records by default, never deleted ones. Ranking
        is separate per corpus."""
        return _svc().search(text, include_archived=include_archived)

    @mcp.tool(title="List the agents", annotations=_READ)
    def list_agents() -> list[dict[str, Any]]:
        """List registered agent domains, names and roles in the selected tenant, including
        agents without identity records."""
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
        """List your own and granted tenants. active marks the current selection; a revoked
        selection can be left but not re-entered."""
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
        """Select the tenant for subsequent reads and writes. The choice persists across restarts
        and applies to every client you sign in with. Pass null to return home."""
        try:
            ref = _sharing().use_tenant(tenant)
        except SharingError as exc:
            raise ToolError(str(exc)) from exc
        return {"user_id": ref.user_id, "role": ref.role, "label": ref.label, "active": True}

    @mcp.tool(title="List who has access to this tenant", annotations=_READ)
    def list_members() -> list[dict[str, Any]]:
        """List the selected tenant's owner and current guests, excluding pending invitations."""
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
        """Owner only: create a single-use invitation granting whole-tenant access. Share the
        code privately; revoke_invite cancels it before redemption."""
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
        """Owner only: invalidate an unused invitation. For a redeemed invitation, use
        revoke_member instead."""
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
        """Consume an invitation to join its tenant as a guest. Call use_tenant separately to
        switch there."""
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
        """Owner only: revoke a guest's access from their next call onward. Their records remain
        intact."""
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
            str | None,
            Field(
                description="Display name, e.g. 'Software Architect'; omit/null if "
                "not yet assigned."
            ),
        ] = None,
        role: Annotated[
            str | None,
            Field(
                description="Specialty, e.g. 'Reviews system designs'; omit/null if "
                "not yet assigned."
            ),
        ] = None,
        uuid: Annotated[
            str | None,
            Field(
                description="Optional identity-document UUID for the agent, "
                "not a memory-record reference."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Register a new agent before inserting its memory. For the full identity setup, follow
        the create-agent procedure."""
        return _svc().create_agent(agent_id=agent_id, name=name, role=role, uuid=uuid)

    # --- writes (Edit-tool parity; record assembled server-side) ---

    @mcp.tool(title="Insert a memory record", annotations=_ADDITIVE)
    def insert_memory(
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
                "and knowledge; omit/null otherwise. "
                f"Maximum {CONTENT_SUMMARY_MAX_CHARACTERS} Unicode characters; "
                "longer input is rejected, never truncated. Aim for 300-500 characters."
            ),
        ] = None,
        agent_id: Annotated[
            str | None,
            Field(
                description="Owner domain from list_agents, e.g. 'meta', required for scope=agent; "
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
            Field(description="Title, e.g. 'Release checks'; omit/null if not supplied."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Tag strings, e.g. ['release', 'qa']; omit/null for an empty list."),
        ] = None,
        project: Annotated[
            str | None,
            Field(
                description="Repository name, e.g. 'invintiry'; "
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
        """Store an agent or shared memory record. A supplied UUID is an upsert key and may
        update an existing
        row. Shared records can be reasoning, coding_reasoning, knowledge, ras or
        user_profile."""
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

    @mcp.tool(title="Create an episode with its first entry", annotations=_ADDITIVE)
    def create_episode(
        agent_id: ExistingAgent,
        title: Annotated[str, Field(description="Episode name, e.g. 'invintiry-auth'.")],
        entry_title: EntryTitle,
        body: EntryBody,
        content_summary: Annotated[str, Field(description="The entry's authored Summary row.")],
        project: Annotated[
            str | None,
            Field(description="Repository name, e.g. 'invintiry'; omit/null if unassigned."),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Episode tags, e.g. ['release']; omit/null for none."),
        ] = None,
        template_version: EpisodeVersion = None,
    ) -> dict[str, Any]:
        """Create a rolling episode with its first entry. Munnin adds the dated heading and saves
        the entry summary for listings."""
        _check_template("episode", template_version)
        return _svc().create_episode(
            agent_id=agent_id,
            title=title,
            entry_title=entry_title,
            body=body,
            content_summary=content_summary,
            project=project,
            tags=tags,
        )

    @mcp.tool(title="Add a dated entry to an episode", annotations=_ADDITIVE)
    def prepend_episode_entry(
        uuid: RecordRef,
        entry_title: EntryTitle,
        body: EntryBody,
        content_summary: Annotated[str, Field(description="The new entry's authored Summary row.")],
        template_version: EpisodeVersion = None,
    ) -> dict[str, Any]:
        """Prepend a dated entry and update the episode summary together. Retrying adds a
        duplicate entry."""
        _check_template("episode", template_version)
        return _svc().prepend_episode_entry(uuid, entry_title, body, content_summary)

    @mcp.tool(title="Edit a record's body", annotations=_DESTRUCTIVE)
    def edit_memory_body(
        uuid: RecordRef,
        old_string: OldString,
        new_string: NewString,
        replace_all: ReplaceAll = False,
        expected_revision: ExpectedRevision = None,
        expected_tenant: ExpectedTenant = None,
    ) -> dict[str, Any]:
        """Replace matching text in a memory body; its title, summary and tags stay unchanged.
        Returns the updated record. For
        conflict-safe edits supply both expected_revision and expected_tenant; success returns
        metadata and fresh edit_context instead."""
        try:
            return _svc().edit(
                uuid,
                old_string,
                new_string,
                replace_all,
                expected_revision=expected_revision,
                expected_tenant=expected_tenant,
            )
        except EditConflict as exc:
            raise ToolError(f"edit conflict: {exc}") from exc

    @mcp.tool(title="Append to a record", annotations=_ADDITIVE)
    def append_memory_body(
        uuid: RecordRef,
        text: Annotated[
            str,
            Field(description="Text to append verbatim; include leading newlines for separation."),
        ],
    ) -> dict[str, Any]:
        """Append text verbatim without updating the summary. Retrying duplicates the text."""
        return _svc().append(uuid, text)

    @mcp.tool(title="Prepend to a record", annotations=_ADDITIVE)
    def prepend_memory_body(
        uuid: RecordRef,
        text: Annotated[
            str,
            Field(
                description="Text to prepend verbatim; include trailing newlines for separation."
            ),
        ],
    ) -> dict[str, Any]:
        """Prepend text verbatim without updating the summary. Retrying duplicates the text."""
        return _svc().prepend(uuid, text)

    @mcp.tool(title="Apply several edits atomically", annotations=_DESTRUCTIVE)
    def multi_edit_memory_body(
        uuid: RecordRef,
        edits: Annotated[
            list[dict[str, Any]],
            Field(
                description="Ordered replacements, e.g. [{'old_string': 'draft', "
                "'new_string': 'ready'}]. Use "
                "optional replace_all for repeated matches. Each matches the "
                "body resulting from the previous edit; all edits succeed or none are written."
            ),
        ],
    ) -> dict[str, Any]:
        """Apply ordered body replacements to one record atomically. If any fails, none are
        saved. Update the summary separately with edit_memory_metadata."""
        return _svc().multi_edit(uuid, edits)

    @mcp.tool(title="Edit a record's metadata", annotations=_DESTRUCTIVE)
    def edit_memory_metadata(
        uuid: RecordRef,
        title: Annotated[
            str | None,
            Field(
                description="New title, e.g. 'Release checks'; omit/null to keep it. "
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
                description="Repository name, e.g. 'invintiry'; omit/null to keep it. "
                "Use clearing to remove it."
            ),
        ] = None,
        content_summary: Annotated[
            str | None,
            Field(
                description="New nonblank authored summary; omit/null to keep it. "
                "Use clearing to remove it. "
                f"Maximum {CONTENT_SUMMARY_MAX_CHARACTERS} Unicode characters; "
                "longer input is rejected, never truncated. Aim for 300-500 characters."
            ),
        ] = None,
        clearing: Annotated[
            list[str] | None,
            Field(
                description="Fields to set to null: title, tags, project and/or content_summary. "
                "Omit/null to clear nothing; do not also supply a replacement for a cleared field."
            ),
        ] = None,
        expected_revision: ExpectedRevision = None,
        expected_tenant: ExpectedTenant = None,
    ) -> dict[str, Any]:
        """Change a memory record's title, summary, tags or project without changing its body.
        Omitted fields are kept; use clearing to
        remove them. Returns metadata only. Supply both expected_revision and expected_tenant
        for a guarded save and fresh edit_context."""
        try:
            return _svc().edit_metadata(
                uuid,
                title=title,
                tags=tags,
                project=project,
                content_summary=content_summary,
                clearing=clearing,
                expected_revision=expected_revision,
                expected_tenant=expected_tenant,
            )
        except EditConflict as exc:
            raise ToolError(f"edit conflict: {exc}") from exc

    @mcp.tool(title="Archive a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def archive_memory(uuid: RecordRef) -> dict[str, str]:
        """Hide a record from awakening and default queries. It remains readable by ID and
        searchable; use unarchive_memory to restore it."""
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
        """Preview one agent's finished, stale and protected episodes. apply=True archives only
        unprotected finished episodes (auto); ask and protected entries are never changed."""
        return _svc().archive_memories(agent_id, days=days, apply=apply)

    @mcp.tool(title="Unarchive a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def unarchive_memory(uuid: RecordRef) -> dict[str, str]:
        """Restore an archived record to awakening and default queries. Cannot restore deleted
        records."""
        return _svc().unarchive(uuid)

    @mcp.tool(title="Soft-delete a record", annotations=_DESTRUCTIVE_IDEMPOTENT)
    def soft_delete_memory(uuid: RecordRef) -> dict[str, str]:
        """Hide a memory from reads, listings, searches and awakening without physically erasing it.
        There is no undelete tool."""
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

    metadata = content.metadata_snapshot()
    for name in metadata.list_prompts():
        mcp.prompt(
            name=name,
            title=metadata.title_prompt(name),
            description=metadata.describe_prompt(name),
        )(_make_prompt(name, metadata.argument_prompt(name)))

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
        """List served procedures with names, titles and descriptions. Use read_procedure for
        instructions."""
        return catalog_rows(content, "procedures")

    @mcp.tool(title="Search served procedures", annotations=_READ)
    def search_procedure(query: CatalogQuery) -> list[dict[str, str]]:
        """Find served procedures by name or title. Use a returned name with read_procedure."""
        return catalog_rows(content, "procedures", query)

    @mcp.tool(title="Read a served procedure", annotations=_READ)
    def read_procedure(
        name: Annotated[
            str,
            Field(description="Name from list_procedures, e.g. 'awaken-agent', without / or .md."),
        ],
        argument: Annotated[
            str | None,
            Field(
                description="Optional text for $ARGUMENTS, using the procedure's documented "
                "format (e.g. 'meta' for awaken-agent). Omit/null/empty leaves authored text."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Fetch instructions for a named procedure and follow them. Fetching does not run the
        procedure. Returns served=false for an unknown name."""
        try:
            text = content.get_prompt(name, argument)
        except KeyError:
            return _not_served("procedure", name, "list_procedures()")
        return {"served": True, "name": name, "content": text}

    @mcp.tool(title="List served resources", annotations=_READ)
    def list_resources() -> list[dict[str, str]]:
        """List served templates and scripts with names, titles and descriptions. Use
        read_resource for contents."""
        return catalog_rows(content, "resources")

    @mcp.tool(title="Search served resources", annotations=_READ)
    def search_resources(query: CatalogQuery) -> list[dict[str, str]]:
        """Find served templates and scripts by name or title. Use a returned name with
        read_resource."""
        return catalog_rows(content, "resources", query)

    @mcp.tool(title="Read a served resource", annotations=_READ)
    def read_resource(
        name: Annotated[
            str,
            Field(
                description="Name from list_resources, e.g. 'copy-lines', "
                "without directory, extension or resource URI."
            ),
        ],
    ) -> dict[str, Any]:
        """Read a template or script verbatim without executing it. Returns served=false for an
        unknown name. Pass template stamps separately on writes."""
        try:
            text = content.get_resource(name)
        except KeyError:
            return _not_served("resource", name, "list_resources()")
        return {"served": True, "name": name, "content": text}

    # --- the permanent layer: the slice a client pushes into its system prompt ---

    @mcp.tool(title="Read the permanent layer", annotations=_READ)
    def permanent_layer() -> dict[str, Any]:
        """Read the selected tenant's always-on instructions, version, hash and skipped rules. To
        install the instructions in a client, follow the anchor-memory procedure."""
        return svc().permanent_layer()
