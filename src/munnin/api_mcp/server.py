"""FastMCP adapter — the agent-facing MCP face (streamable-HTTP transport).

Phase 4 exposes only a ``ping`` tool to prove the MCP face initializes. The full
memory tool surface (awaken, load/update-episodic, add-reasoning, ...) + served
prompts/resources land in Phase 5.
"""

from __future__ import annotations

from fastmcp import FastMCP

from munnin.business_services.memory_service import MemoryService


def build_mcp(service: MemoryService) -> FastMCP:
    mcp: FastMCP = FastMCP("munnin")

    @mcp.tool
    def ping() -> str:
        """Liveness check — returns 'pong'."""
        return "pong"

    return mcp
