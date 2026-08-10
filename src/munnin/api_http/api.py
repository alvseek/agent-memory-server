"""FastAPI adapter — the HTTP face.

Phase 4 exposes only ``/health``. The ``/api`` memory-operation surface (the full
memory surface, twin of the MCP face) lands in Phase 5.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from munnin.business_services.memory_service import MemoryService


def build_router(service: MemoryService) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return service.health()

    @router.get("/api/awaken")
    def awaken(agent_id: str) -> dict[str, Any]:
        """Assemble + return an agent's full memory payload from the DB (M0)."""
        try:
            return service.awaken(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
