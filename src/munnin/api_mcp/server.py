"""FastMCP adapter — the agent-facing MCP face (streamable-HTTP transport).

Exposes the full memory data-primitive surface as tools (twin of the HTTP face)
over the shared MemoryService core. The 1:1 memory *procedures* (update_episodic,
add_reasoning, ...) are served separately as MCP Prompts/Resources in SP-5 — these
tools are the data operations those procedures instruct the agent to call.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from munnin.business_services.memory_service import MemoryService
from munnin.content.loader import ContentLoader


def build_mcp(service: MemoryService, content: ContentLoader | None = None) -> FastMCP:
    mcp: FastMCP = FastMCP("munnin")

    @mcp.tool
    def ping() -> str:
        """Liveness check — returns 'pong'."""
        return "pong"

    @mcp.tool
    def awaken(domain: str) -> dict[str, Any]:
        """Assemble and return an agent's full memory payload from the DB.

        Loads the shared always-load layer + the agent's identity whole, plus the
        episodic/knowledge index and the latest episode body."""
        return service.awaken(domain)

    # --- reads ---

    @mcp.tool
    def get(uuid: str) -> dict[str, Any] | None:
        """Load one record's full body by id (None if absent/deleted)."""
        return service.get(uuid)

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
        return service.query(
            agent_id=agent_id,
            record_type=record_type,
            project=project,
            include_archived=include_archived,
        )

    @mcp.tool
    def search(text: str, include_archived: bool = True) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search over content + title + tags."""
        return service.search(text, include_archived=include_archived)

    @mcp.tool
    def list_agents() -> list[dict[str, Any]]:
        """List every agent in the fleet: ``agent_id`` + display name + one-line role.
        Metadata only, no bodies. An agent with no identity recorded comes back with
        ``name``/``role`` of ``null`` rather than being omitted."""
        return service.list_agents()

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
        return service.create_agent(agent_id=agent_id, name=name, role=role, uuid=uuid)

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
        episode|knowledge|identity|reasoning|emotional, and fleet memory may only be
        reasoning or knowledge."""
        return service.insert(
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
        return service.edit(uuid, old_string, new_string, replace_all)

    @mcp.tool
    def append(uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` to the END of a record's body. Verbatim — include your own
        leading newline(s) for spacing (e.g. a new sub-episode under a date header)."""
        return service.append(uuid, text)

    @mcp.tool
    def prepend(uuid: str, text: str) -> dict[str, Any]:
        """Add ``text`` to the START of a record's body. Verbatim — include your own
        trailing newline(s) for spacing."""
        return service.prepend(uuid, text)

    @mcp.tool
    def multi_edit(uuid: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply a sequence of string edits to one record atomically (all-or-nothing).

        Each edit is a dict with ``old_string`` + ``new_string`` (+ optional
        ``replace_all``). Edits apply in order, each to the result of the previous; if
        any fails, nothing is written."""
        return service.multi_edit(uuid, edits)

    @mcp.tool
    def archive(uuid: str) -> dict[str, str]:
        """Retire a record from the hot index (still searchable on demand)."""
        return service.archive(uuid)

    @mcp.tool
    def soft_delete(uuid: str) -> dict[str, str]:
        """Tombstone a record (excluded from all reads)."""
        return service.soft_delete(uuid)

    if content is not None and content.available():
        _register_content(mcp, content)

    return mcp


def _register_content(mcp: FastMCP, content: ContentLoader) -> None:
    """Register served memory procedures as Prompts + templates as Resources.

    Both are read live from the control-files submodule; procedures are composed
    with the db storage backend so the served text speaks DB tools, not markdown
    files. The twin of these is the FastAPI ``/api/prompts`` + ``/api/resources``.
    """
    def _make_prompt(procedure: str):
        # Zero-arg so FastMCP registers a plain prompt (a parameter would make it
        # a prompt-with-arguments); the name is bound via the factory closure.
        def fn() -> str:
            return content.get_prompt(procedure)

        fn.__name__ = procedure.replace("-", "_")
        return fn

    for name in content.list_prompts():
        mcp.prompt(
            name=name,
            description=f"Memory procedure '{name}' — how-to for the DB-backed memory tools.",
        )(_make_prompt(name))

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
            description=f"Framework template '{name}'.",
            mime_type="text/markdown",
        )(_make_resource(name))
