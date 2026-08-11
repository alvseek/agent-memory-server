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


def build_mcp(service: MemoryService) -> FastMCP:
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
        """Browse the index projection on demand (filter by agent/type/project)."""
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

    # --- writes (Edit-tool parity; record assembled server-side) ---

    @mcp.tool
    def insert(
        agent_id: str,
        record_type: str,
        content: str,
        title: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        uuid: str | None = None,
    ) -> dict[str, Any]:
        """Append a new memory item. ``agent_id`` = a kebab domain or ``__shared__``;
        ``record_type`` ∈ episode|knowledge|identity|reasoning|emotional."""
        return service.insert(
            agent_id=agent_id,
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
    def archive(uuid: str) -> dict[str, str]:
        """Retire a record from the hot index (still searchable on demand)."""
        return service.archive(uuid)

    @mcp.tool
    def soft_delete(uuid: str) -> dict[str, str]:
        """Tombstone a record (excluded from all reads)."""
        return service.soft_delete(uuid)

    return mcp
