"""FastAPI adapter — the HTTP face.

Phase 4 exposes only ``/health``. The ``/api`` memory-operation surface (the full
memory surface, twin of the MCP face) lands in Phase 5.
"""

from __future__ import annotations

from fastapi import APIRouter

from munnin.core.service import MemoryService


def build_router(service: MemoryService) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return service.health()

    return router
