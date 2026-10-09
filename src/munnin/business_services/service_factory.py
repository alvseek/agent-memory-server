"""Build a memory service bound to one tenant and one backend.

The composition root used to construct a single ``MemoryService`` at boot, which meant the
answer to "whose memory is this?" was decided before the first request arrived. This moves
that decision to where it belongs: each caller names its own tenant, and gets a service
that can reach nothing else.

``MemoryService`` keeps its existing constructor — the tenant was always a constructor
argument, it was simply only ever supplied once. Below the repository, the backend is
chosen here: SQLite (the default) or PostgreSQL (the deployed store), both satisfying the
same ``MemoryRepository`` Protocol.

The content loader is deliberately **not** held here. Framework content is identical for
every tenant, so putting it in a per-tenant factory would imply a variation that does not
exist; the adapters take it directly, as they always have.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_repositories.memory_repository import MemoryRepository
from munnin.data_repositories.postgres_memory_repository import PostgresMemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


class ServiceFactory:
    """Hands out per-tenant services over one store (SQLite or PostgreSQL)."""

    def __init__(
        self,
        db_path: Path,
        *,
        backend: str = "sqlite",
        db_url: str | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._backend = backend
        self._db_url = db_url
        self._services: dict[str, MemoryService] = {}

    def _repository(self, user_id: str) -> MemoryRepository:
        if self._backend == "postgres":
            if not self._db_url:
                raise ValueError("the postgres backend needs a db_url (MUNNIN_DB_URL)")
            return PostgresMemoryRepository(self._db_url, user_id=user_id)
        return SqliteMemoryRepository(self._db_path, user_id=user_id)

    def for_user(self, user_id: str) -> MemoryService:
        """The service acting as ``user_id``. Every query it runs is scoped to that tenant.

        Services are kept per tenant rather than rebuilt per request, for one concrete
        reason: the repository runs the schema migrations on its first connection and then
        remembers, so a fresh instance per request would re-check the migration history on
        every single call. The cached objects hold a path/dsn and a string, so the cost of
        keeping one per tenant is nothing next to that."""
        service = self._services.get(user_id)
        if service is None:
            service = MemoryService(self._repository(user_id), user_id=user_id)
            self._services[user_id] = service
        return service
