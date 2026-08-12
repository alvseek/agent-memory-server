"""FastAPI adapter — the HTTP face (REST twin of the MCP surface).

Exposes the full memory data-primitive surface over the shared MemoryService core:
``/health`` + ``/api/awaken`` + the generic read/write ops. ``user_id`` is stamped
server-side (never a request field). ``ValueError`` → 400, ``LookupError`` → 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from munnin.business_services.memory_service import MemoryService
from munnin.content.loader import ContentLoader


class InsertBody(BaseModel):
    agent_id: str
    record_type: str
    content: str
    title: str | None = None
    tags: list[str] | None = None
    project: str | None = None
    uuid: str | None = None


class EditBody(BaseModel):
    uuid: str
    old_string: str
    new_string: str
    replace_all: bool = False


class UuidBody(BaseModel):
    uuid: str


def build_router(service: MemoryService, content: ContentLoader | None = None) -> APIRouter:
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

    # --- reads ---

    @router.get("/api/record/{uuid}")
    def get_record(uuid: str) -> dict[str, Any]:
        """Load one record's full body by id."""
        record = service.get(uuid)
        if record is None:
            raise HTTPException(status_code=404, detail=f"record not found: {uuid}")
        return record

    @router.get("/api/query")
    def query(
        agent_id: str | None = None,
        record_type: str | None = None,
        project: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """Browse the index projection on demand."""
        try:
            return service.query(
                agent_id=agent_id,
                record_type=record_type,
                project=project,
                include_archived=include_archived,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/search")
    def search(text: str, include_archived: bool = True) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search."""
        return service.search(text, include_archived=include_archived)

    # --- writes ---

    @router.post("/api/insert")
    def insert(body: InsertBody) -> dict[str, Any]:
        """Append a new item (record assembled server-side)."""
        try:
            return service.insert(
                agent_id=body.agent_id,
                record_type=body.record_type,
                content=body.content,
                title=body.title,
                tags=body.tags,
                project=body.project,
                uuid=body.uuid,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/edit")
    def edit(body: EditBody) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity)."""
        try:
            return service.edit(body.uuid, body.old_string, body.new_string, body.replace_all)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/archive")
    def archive(body: UuidBody) -> dict[str, str]:
        """Retire a record from the hot index (still searchable)."""
        try:
            return service.archive(body.uuid)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/soft-delete")
    def soft_delete(body: UuidBody) -> dict[str, str]:
        """Tombstone a record (excluded from all reads)."""
        try:
            return service.soft_delete(body.uuid)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # --- served content (twin of the MCP Prompts/Resources) ---

    @router.get("/api/prompts")
    def list_prompts() -> dict[str, list[str]]:
        """List the served memory-procedure prompt names."""
        names = content.list_prompts() if content is not None else []
        return {"prompts": names}

    @router.get("/api/prompts/{name}")
    def get_prompt(name: str) -> dict[str, str]:
        """Return a memory procedure composed with the DB storage backend."""
        if content is None:
            raise HTTPException(status_code=404, detail="content not available")
        try:
            return {"name": name, "content": content.get_prompt(name)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/resources")
    def list_resources() -> dict[str, list[str]]:
        """List the served template resource names."""
        names = content.list_resources() if content is not None else []
        return {"resources": names}

    @router.get("/api/resources/{name}")
    def get_resource(name: str) -> dict[str, str]:
        """Return a framework template verbatim."""
        if content is None:
            raise HTTPException(status_code=404, detail="content not available")
        try:
            return {"name": name, "content": content.get_resource(name)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
