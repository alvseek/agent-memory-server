"""FastAPI adapter — the HTTP face (REST twin of the MCP surface).

Exposes the full memory data-primitive surface over the shared MemoryService core:
``/health`` + ``/api/awaken`` + the generic read/write ops. ``ValueError`` → 400,
``LookupError`` → 404.

Every ``/api`` route sits behind a token. The guard is declared **once**, on the router
that carries them all, rather than per handler — a per-handler guard is a list you can
forget to add to, and forgetting is silent. Adding a route to this file therefore guards
it by construction, and ``test_route_coverage`` fails if one is ever hung on the open
router by mistake.

The tenant arrives the same way: a dependency verifies the caller, resolves them to a
tenant and hands the handler a service already bound to it. Nothing is stashed in ambient
per-request state, deliberately — the handlers here are synchronous and FastAPI runs them
in a threadpool, so a context variable would be one thread-reuse bug away from serving a
caller somebody else's rows, and it would fail by returning data rather than by raising.

``/health`` is the sole open route, and deliberately so — the deploy's health gate calls
it without a credential, so guarding it would fail the cutover. It reads nothing from the
store, so there is nothing to scope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastmcp.server.auth import AuthProvider
from pydantic import BaseModel

from munnin import __version__
from munnin.business_services.identity_service import IdentityService
from munnin.business_services.memory_service import MemoryService
from munnin.business_services.service_factory import ServiceFactory
from munnin.content.loader import ContentLoader

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


class MarkdownResponse(PlainTextResponse):
    """A served document, delivered as its own bytes rather than a JSON field.

    Starlette appends ``; charset=utf-8`` for any ``text/*`` media type.
    """

    media_type = "text/markdown"


class CreateAgentBody(BaseModel):
    agent_id: str
    name: str | None = None
    role: str | None = None
    uuid: str | None = None


class InsertBody(BaseModel):
    record_type: str
    content: str
    agent_id: str | None = None
    scope: str = "agent"
    title: str | None = None
    tags: list[str] | None = None
    project: str | None = None
    uuid: str | None = None


class EditBody(BaseModel):
    uuid: str
    old_string: str
    new_string: str
    replace_all: bool = False


class AppendBody(BaseModel):
    uuid: str
    text: str


class EditOp(BaseModel):
    old_string: str
    new_string: str
    replace_all: bool = False


class MultiEditBody(BaseModel):
    uuid: str
    edits: list[EditOp]


class UuidBody(BaseModel):
    uuid: str


def build_router(
    factory: ServiceFactory,
    content: ContentLoader | None = None,
    *,
    auth: AuthProvider,
    identity: IdentityService,
) -> APIRouter:
    """The HTTP face.

    ``auth`` and ``identity`` are required rather than optional: an unauthenticated HTTP
    face is not a configuration this server has, and a default of ``None`` would make one
    reachable by omission.
    """

    async def _caller(request: Request) -> str:
        """The tenant behind this request, or 401.

        Uses the **same** provider object the MCP face was given. Two independently
        configured verifiers would have to agree with each other forever, with nothing
        reporting the moment they stopped.
        """
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "missing bearer token", headers=_UNAUTHENTICATED)
        access = await auth.verify_token(token)
        if access is None:
            raise HTTPException(401, "invalid token", headers=_UNAUTHENTICATED)
        iss, sub = access.claims.get("iss"), access.claims.get("sub")
        if not iss or not sub:
            # Verified, but it names nobody. Choosing a tenant here would be guessing at
            # an identity, which is the failure the (iss, sub) key exists to prevent.
            raise HTTPException(401, "token names no subject", headers=_UNAUTHENTICATED)
        return identity.resolve(
            str(iss),
            str(sub),
            email=access.claims.get("email"),
            display_name=access.claims.get("name"),
        )

    def _tenant_service(user_id: str = Depends(_caller)) -> MemoryService:
        """A service that can reach this caller's records and no others."""
        return factory.for_user(user_id)

    router = APIRouter()
    # Every route below this line is guarded, including the served-content ones: one rule
    # with no exceptions is checkable, and an unauthenticated exception is what produced
    # the hole this work closes.
    api = APIRouter(dependencies=[Depends(_caller)])

    @router.get("/health")
    def health() -> dict[str, str]:
        # Deliberately tenant-free and deliberately open (decision 17): the deploy's
        # health gate reaches this without a credential, so resolving a caller here would
        # fail the cutover. It reads nothing from the store, so there is nothing to scope.
        return {"status": "ok", "service": "munnin", "version": __version__}

    @api.get("/api/awaken")
    def awaken(agent_id: str, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Assemble + return an agent's full memory payload from the DB (M0)."""
        try:
            return svc.awaken(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- reads ---

    @api.get("/api/record/{uuid}")
    def get_record(uuid: str, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Load one record's full body by id."""
        record = svc.get(uuid)
        if record is None:
            raise HTTPException(status_code=404, detail=f"record not found: {uuid}")
        return record

    @api.get("/api/query")
    def query(
        agent_id: str | None = None,
        record_type: str | None = None,
        project: str | None = None,
        include_archived: bool = False,
        svc: MemoryService = Depends(_tenant_service),
    ) -> list[dict[str, Any]]:
        """Filter memory by exact field values (bodies included). Omitting ``agent_id``
        also returns fleet-shared memory, whose rows carry no ``agent_id``."""
        try:
            return svc.query(
                agent_id=agent_id,
                record_type=record_type,
                project=project,
                include_archived=include_archived,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.get("/api/search")
    def search(
        text: str, include_archived: bool = True, svc: MemoryService = Depends(_tenant_service)
    ) -> list[dict[str, Any]]:
        """Full-text (FTS5) keyword search."""
        return svc.search(text, include_archived=include_archived)

    @api.get("/api/agents")
    def list_agents(svc: MemoryService = Depends(_tenant_service)) -> list[dict[str, Any]]:
        """The fleet roster — ``agent_id`` + name + role, metadata only."""
        return svc.list_agents()

    # --- writes ---

    @api.post("/api/agents")
    def create_agent(
        body: CreateAgentBody, svc: MemoryService = Depends(_tenant_service)
    ) -> dict[str, Any]:
        """Create a new agent. 400 if the domain is invalid or already taken — creation
        never overwrites a live agent's identity."""
        try:
            return svc.create_agent(
                agent_id=body.agent_id, name=body.name, role=body.role, uuid=body.uuid
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/insert")
    def insert(body: InsertBody, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Append a new item (record assembled server-side). ``scope="agent"`` (default)
        needs an ``agent_id`` that already exists; ``scope="shared"`` takes none."""
        try:
            return svc.insert(
                agent_id=body.agent_id,
                scope=body.scope,
                record_type=body.record_type,
                content=body.content,
                title=body.title,
                tags=body.tags,
                project=body.project,
                uuid=body.uuid,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/edit")
    def edit(body: EditBody, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Targeted string replace inside a record's body (Edit-tool parity)."""
        try:
            return svc.edit(body.uuid, body.old_string, body.new_string, body.replace_all)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/append")
    def append(body: AppendBody, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Add text verbatim to the end of a record's body."""
        try:
            return svc.append(body.uuid, body.text)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/api/prepend")
    def prepend(body: AppendBody, svc: MemoryService = Depends(_tenant_service)) -> dict[str, Any]:
        """Add text verbatim to the start of a record's body."""
        try:
            return svc.prepend(body.uuid, body.text)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/api/multi-edit")
    def multi_edit(
        body: MultiEditBody, svc: MemoryService = Depends(_tenant_service)
    ) -> dict[str, Any]:
        """Apply a sequence of edits to one record atomically (all-or-nothing)."""
        try:
            return svc.multi_edit(body.uuid, [op.model_dump() for op in body.edits])
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.post("/api/archive")
    def archive(body: UuidBody, svc: MemoryService = Depends(_tenant_service)) -> dict[str, str]:
        """Retire a record from the hot index (still searchable)."""
        try:
            return svc.archive(body.uuid)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/api/soft-delete")
    def soft_delete(
        body: UuidBody, svc: MemoryService = Depends(_tenant_service)
    ) -> dict[str, str]:
        """Tombstone a record (excluded from all reads)."""
        try:
            return svc.soft_delete(body.uuid)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # --- served content (twin of the MCP Prompts/Resources) ---
    # The two list endpoints answer with JSON, since a list of names is data. A single
    # prompt or template is a document, so it is returned as raw markdown: an installed
    # slash command and a served Prompt are byte-identical, and that only holds if the
    # bytes reach the caller unwrapped. Errors stay JSON — FastAPI's HTTPException shape.
    #
    # These take no service: framework content is identical for every tenant. They are
    # still guarded, by the router, because who may *read* the framework is a separate
    # question from whose memory it is (decision 13).

    @api.get("/api/prompts")
    def list_prompts() -> dict[str, list[str]]:
        """List the served memory-procedure prompt names."""
        names = content.list_prompts() if content is not None else []
        return {"prompts": names}

    @api.get("/api/prompts/{name}", response_class=MarkdownResponse)
    def get_prompt(name: str) -> MarkdownResponse:
        """Return a memory procedure composed with the DB storage backend."""
        if content is None:
            raise HTTPException(status_code=404, detail="content not available")
        try:
            return MarkdownResponse(content.get_prompt(name))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.get("/api/resources")
    def list_resources() -> dict[str, list[str]]:
        """List the served template resource names."""
        names = content.list_resources() if content is not None else []
        return {"resources": names}

    @api.get("/api/resources/{name}", response_class=MarkdownResponse)
    def get_resource(name: str) -> MarkdownResponse:
        """Return a framework template verbatim."""
        if content is None:
            raise HTTPException(status_code=404, detail="content not available")
        try:
            return MarkdownResponse(content.get_resource(name))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    router.include_router(api)
    return router
