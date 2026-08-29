"""Build a memory service bound to one tenant.

The composition root used to construct a single ``MemoryService`` at boot, which meant
the answer to "whose memory is this?" was decided before the first request arrived. This
moves that decision to where it belongs: each caller names its own tenant, and gets a
service that can reach nothing else.

``MemoryService`` and ``SqliteMemoryRepository`` keep their existing constructors — the
tenant was always a constructor argument, it was simply only ever supplied once. That is
why nothing below the adapters had to change.

The content loader is deliberately **not** held here. Framework content is identical for
every tenant, so putting it in a per-tenant factory would imply a variation that does not
exist; the adapters take it directly, as they always have.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


class ServiceFactory:
    """Hands out per-tenant services over one database."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._services: dict[str, MemoryService] = {}

    def for_user(self, user_id: str) -> MemoryService:
        """The service acting as ``user_id``. Every query it runs is scoped to that tenant.

        Services are kept per tenant rather than rebuilt per request, for one concrete
        reason: the repository applies ``schema.sql`` on its first connection and then
        remembers, so a fresh instance per request would re-run five ``CREATE TABLE IF NOT
        EXISTS`` statements plus indexes and triggers on every single call. The cached
        objects hold a path and a string, so the cost of keeping one per tenant is
        nothing next to that."""
        service = self._services.get(user_id)
        if service is None:
            repo = SqliteMemoryRepository(self._db_path, user_id=user_id)
            service = MemoryService(repo, user_id=user_id)
            self._services[user_id] = service
        return service
