"""The transport-agnostic memory-service core.

Both adapters (MCP + HTTP) call THIS; it calls the injected repository. No
transport concerns leak in here. Memory operations (awaken, update_episodic,
add_reasoning, ...) land in Phase 5; Phase 4 provides only liveness.
"""

from __future__ import annotations

from munnin import __version__
from munnin.data_repositories.memory_repository import MemoryRepository


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
