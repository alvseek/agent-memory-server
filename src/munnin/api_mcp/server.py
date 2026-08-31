"""FastMCP adapter — the agent-facing MCP face (streamable-HTTP transport).

Exposes the full memory data-primitive surface as tools (twin of the HTTP face)
over the shared MemoryService core. The 1:1 memory *procedures* (update_episodic,
add_reasoning, ...) are served separately as MCP Prompts/Resources in SP-5 — these
tools are the data operations those procedures instruct the agent to call.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider

from munnin.business_services.memory_service import MemoryService
from munnin.business_services.service_factory import ServiceFactory
from munnin.business_services.tenant_resolver import TenantResolver
from munnin.content.loader import ContentLoader


def build_mcp(
    factory: ServiceFactory,
    resolver: TenantResolver,
    content: ContentLoader | None = None,
    auth: AuthProvider | None = None,
) -> FastMCP:
    """The MCP face.

    ``auth`` guards every tool at the transport layer: FastMCP refuses an unverified
    request before any tool body runs, which is why the resolver below can trust the
    token it finds rather than re-checking it.
    """
    mcp: FastMCP = FastMCP("munnin", auth=auth)

    def _svc() -> MemoryService:
        """The service for whoever is calling right now.

        Called inside each tool body rather than captured when the tool is registered:
        registration happens once at boot, and the caller is not known until the call."""
        return factory.for_user(resolver.current_user_id())

    @mcp.tool
    def ping() -> str:
        """Liveness check — returns 'pong'."""
        return "pong"

    @mcp.tool
    def awaken(domain: str) -> dict[str, Any]:
        """Assemble and return an agent's full memory payload from the DB.

        Loads the shared always-load layer + the agent's identity whole, plus the
        episodic/knowledge index and the latest episode body."""
        return _svc().awaken(domain)

    # --- reads ---

    @mcp.tool
    def get(uuid: str) -> dict[str, Any] | None:
        """Load one record's full body by id (None if absent/deleted)."""
        return _svc().get(uuid)

    @mcp.tool
    def query(
        agent_id: str | None = None,
        record_type: str | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Filter memory by exact field values, returning whole records with bodies.
        Naming an ``agent_id`` reads that agent alone; omitting it also returns
        fleet-shared memory, whose rows carry no ``agent_id``."""
        return _svc().query(
            agent_id=agent_id,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )

    @mcp.tool
    def search(text: str, include_archived: bool = True) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search over content + title + tags."""
        return _svc().search(text, include_archived=include_archived)

    @mcp.tool
    def list_agents() -> list[dict[str, Any]]:
        """List every agent in the fleet: ``agent_id`` + display name + one-line role.
        Metadata only, no bodies. An agent with no identity recorded comes back with
        ``name``/``role`` of ``null`` rather than being omitted."""
        return _svc().list_agents()

    @mcp.tool
    def create_agent(
        agent_id: str,
        name: str | None = None,
        role: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Create a new agent. ``agent_id`` is a kebab domain and must not already exist —
        creating over a live agent raises rather than overwriting its identity. Call this
        **before** inserting any of the agent's memory: memory names an owner the store
        checks, so an insert for an agent with no row is refused. ``uuid`` is the agent's
        own "digital soul" id from its identity document."""
        return _svc().create_agent(agent_id=agent_id, name=name, role=role, uuid=uuid)

    # --- writes (Edit-tool parity; record assembled server-side) ---

    @mcp.tool
    def insert(
        record_type: str,
        content: str,
        agent_id: str | None = None,
        scope: str = "agent",
        title: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Append a new memory item. ``scope="agent"`` (the default) writes memory owned
        by ``agent_id``, which must be an existing kebab domain; ``scope="shared"`` writes
        fleet-wide memory owned by nobody and takes no ``agent_id``. ``record_type`` ∈
        episode|knowledge|identity|reasoning|emotional|user_profile, and fleet memory may
        only be reasoning, knowledge or user_profile — the profile is fleet-wide because
        who the user is does not vary by agent."""
        return _svc().insert(
            agent_id=agent_id,
            scope=scope,
            record_type=record_type,
            content=content,
            title=title,
            tags=tags,
            project=project,
            uuid=uuid,
        )

    @mcp.tool
    def edit(
        uuid: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity)."""
        return _svc().edit(uuid, old_string, new_string, replace_all)

    @mcp.tool
    def append(uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` to the END of a record's body. Verbatim — include your own
        leading newline(s) for spacing (e.g. a new sub-episode under a date header)."""
        return _svc().append(uuid, text)

    @mcp.tool
    def prepend(uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` to the START of a record's body. Verbatim — include your own
        trailing newline(s) for spacing."""
        return _svc().prepend(uuid, text)

    @mcp.tool
    def multi_edit(uuid: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply a sequence of string edits to one record atomically (all-or-nothing).

        Each edit is a dict with ``old_string`` + ``new_string`` (+ optional
        ``replace_all``). Edits apply in order, each to the result of the previous; if
        any fails, nothing is written."""
        return _svc().multi_edit(uuid, edits)

    @mcp.tool
    def archive(uuid: str) -> dict[str, str]:
        """Retire a record from the hot index (still searchable on demand)."""
        return _svc().archive(uuid)

    @mcp.tool
    def soft_delete(uuid: str) -> dict[str, str]:
        """Tombstone a record (excluded from all reads)."""
        return _svc().soft_delete(uuid)

    if content is not None and content.available():
        _register_content(mcp, content)

    return mcp


def _register_content(mcp: FastMCP, content: ContentLoader) -> None:
    """Register served memory procedures as Prompts + templates as Resources.

    Both are read live from the control-files submodule; procedures are composed
    with the db storage backend so the served text speaks DB tools, not markdown
    files. The twin of these is the FastAPI ``/api/prompts`` + ``/api/resources``.
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
            return fn
        arg_name, arg_help = argument
        fn.__doc__ = f"{procedure}\n\nArgs:\n    {arg_name}: {arg_help}\n"
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

    def _make_resource(template: str):
        # Zero-arg so FastMCP registers a static resource, not a URI template.
        def fn() -> str:
            return content.get_resource(template)

        fn.__name__ = f"resource_{template.replace('-', '_')}"
        return fn

    for name in content.list_resources():
        mcp.resource(
            f"resource://templates/{name}",
            name=name,
            title=content.title_resource(name),
            description=content.describe_resource(name),
            mime_type="text/markdown",
            # A fill-in template is written by an agent and read by nobody else, hence the
            # assistant audience. The priority is near the floor because `priority` scores
            # whether a client should pull something into context unasked, and a template
            # earns its place only at the moment that memory layer is being written —
            # deliberately fetched, never speculatively included. Not 0.0: that is the
            # spec's "entirely optional", and a client could reasonably read it as "hide",
            # which would take these out of a picker where they do belong.
            annotations={"audience": ["assistant"], "priority": 0.1},
        )(_make_resource(name))
