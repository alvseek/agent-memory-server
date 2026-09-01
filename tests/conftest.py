"""Shared test infrastructure.

The store enforces a chain of ownership: a memory record names an agent, and an agent
names a tenant. Both links are foreign keys, so an insert needs its agent to exist, and
an agent needs its `account` row to exist. Both are real and wanted constraints, and
neither is what most tests are about — a test for `append` or for FTS ranking should not
have to restate two unrelated preconditions on every fixture.

`seed_account` and `AutoAgentRepository` supply them. Both are **test doubles only**: the
foreign keys themselves are exercised against the real `SqliteMemoryRepository` in
`tests/data_repositories/test_foreign_keys.py`, and the importer's own tenant and agent
creation is exercised against the real class in `tests/data_migrations/`. Anything
asserting *who creates account or agent rows* must use the real class, or it proves
nothing.

`seed_account` writes raw SQL rather than going through a repository, for the same reason
`test_foreign_keys.py` does: a helper that leans on the production write path stops being
able to set up a test *of* that path.

`auth_for` supplies the third precondition, once the faces are guarded: a caller. It hands
back a real verifier holding real claims, so a test authenticates rather than skips
authenticating — the tested path stays the shipped path on the one change where the
difference is a security boundary. What it substitutes is *which issuer is trusted*, never
whether a token is checked, and there is no helper here that turns verification off.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth import MultiAuth
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from httpx import ASGITransport

from munnin.api_mcp.server import build_mcp
from munnin.business_services.service_factory import ServiceFactory
from munnin.content.loader import ContentLoader
from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_entities.memory_record import Agent, MemoryRecord
from munnin.data_repositories.identity_repository import IdentityRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

TEST_ISSUER = "https://munnin-tests.authkit.invalid"


class FixedTenantResolver:
    """A resolver that always answers with one tenant. **Test double — never shipped.**

    The production resolver reaches a tenant only through a verified token, which is the
    property Step 3.4 deleted the old static resolver to guarantee. Face tests that build
    an adapter directly still need *some* tenant without standing up a token, so the
    double lives here, where its being a double is obvious. It is deliberately not
    importable from `munnin`: if this class ever appears in the server's own dependency
    graph, that is the bug it exists to make visible.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def current_user_id(self) -> str:
        return self._user_id


def token_for(subject: str) -> str:
    """The bearer string a test presents to act as ``subject``."""
    return f"test-token-{subject}"


def bearer(subject: str = "alvi") -> dict[str, str]:
    """The header a test client sends to act as ``subject``."""
    return {"Authorization": f"Bearer {token_for(subject)}"}


def seed_login(db: Path, user_id: str = "alvi") -> None:
    """Map the test subject ``user_id`` to the tenant of the same name.

    Tests seed their rows under a readable tenant id and authenticate as a subject with
    the same string, which only lines up because of this mapping. Without it the resolver
    would mint a fresh tenant on first contact and every seeded row would be invisible —
    which is correct behaviour, and precisely what the isolation proof depends on, but it
    would look here like the face had broken.
    """
    repo = IdentityRepository(db)
    repo.ensure_account(Account(user_id=user_id))
    repo.link_identity(UserIdentity(iss=TEST_ISSUER, sub=user_id, user_id=user_id))


def auth_for(*subjects: str) -> MultiAuth:
    """A verifier accepting exactly these subjects, each with its own token.

    The claims carry ``iss`` and ``sub`` because that pair is what identity resolution
    keys on — the same two values a real AuthKit token supplies, arriving by the same
    route. A verifier that returned no subject would let the faces be tested while the
    thing they resolve stayed unexercised.
    """
    return MultiAuth(
        verifiers=[
            StaticTokenVerifier(
                {
                    token_for(subject): {
                        "client_id": "munnin-tests",
                        "iss": TEST_ISSUER,
                        "sub": subject,
                    }
                    for subject in subjects
                }
            )
        ]
    )


@asynccontextmanager
async def running(app: Any) -> AsyncIterator[None]:
    """Start an app's lifespan.

    ``ASGITransport`` delivers requests but never fires lifespan events, so without this
    the mounted MCP app's session manager is never initialised and every session-opening
    call fails with a task-group error that looks nothing like an auth problem. Requests
    that are rejected at the transport do not need it, because they never reach the
    session manager — which is itself worth knowing.
    """
    async with app.router.lifespan_context(app):
        yield


def mcp_client_for(app: Any, token: str) -> Client:
    """A real MCP client speaking streamable-HTTP to a mounted app, in process.

    Drives the **mounted** app rather than an in-memory ``FastMCP`` deliberately:
    authentication is enforced at the transport, so an in-memory client sails straight
    past it and would report success against a server that is wide open.
    """

    def factory(headers=None, auth=None, follow_redirects=True, **_: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    return Client(
        StreamableHttpTransport(
            # The no-slash form, which is what a spec-following client sends: every
            # test that drives the MCP face through this client therefore also proves
            # the path normaliser, since without it this URL answers a redirect.
            url="http://test/mcp",
            auth=token,
            httpx_client_factory=factory,
        )
    )


def mcp_for(
    db: Path, *, user_id: str = "alvi", content: ContentLoader | None = None
) -> FastMCP:
    """Build the MCP face the way ``build_app`` does — over a per-tenant factory.

    Tests used to hand ``build_mcp`` a service they had constructed, which stopped being
    possible when the tenant moved from the process to the request. Going through the
    factory here keeps every face test on the same wiring the server actually runs."""
    seed_account(db, user_id)
    return build_mcp(ServiceFactory(db), FixedTenantResolver(user_id), content)


def seed_account(db: Path, user_id: str = "alvi") -> None:
    """Create the tenant row ``user_id`` in ``db``, so an agent may reference it.

    Idempotent, and safe against an empty path: the schema is applied by the repository's
    own connection helper, which is also what enables the foreign keys."""
    repo = SqliteMemoryRepository(db, user_id=user_id)
    with repo._conn() as conn:  # noqa: SLF001 — deliberately bypassing the write path
        conn.execute(
            "INSERT OR IGNORE INTO account (user_id, created_date) VALUES (?, '2026-08-28')",
            (user_id,),
        )


def seed_agent(
    db: Path, agent_id: str = "meta", *, user_id: str = "alvi", **fields: str
) -> None:
    """Create an agent row directly in ``db``, for tests that reach the store through a
    face rather than through a repository they constructed.

    ``build_app`` wires the **real** repository, so an API-level test cannot use the
    auto-creating double — and it should not want to: "the agent must exist first" is the
    precondition under test everywhere else, and a face test that quietly invented one
    would be asserting against a store no deployment can produce."""
    seed_account(db, user_id)
    SqliteMemoryRepository(db, user_id=user_id).upsert_agent(
        Agent(user_id="", agent_id=agent_id, **fields)
    )


class AutoAgentRepository(SqliteMemoryRepository):
    """A repository that creates an agent row on demand before inserting its memory.

    It fills the gap **only when nothing else has**. `upsert_agent` refreshes name and
    role by design, so an unconditional call here would silently overwrite whatever a
    real pass-1 import had just written with a placeholder — the double would then be
    destroying the very fields the test is about.

    It also ensures the tenant row the agent will reference, since an agent cannot exist
    without one. Same rule: supplied once, and only because it is a precondition rather
    than a subject."""

    def __init__(self, db_path: Path, *, user_id: str) -> None:
        super().__init__(db_path, user_id=user_id)
        seed_account(db_path, user_id)
        self._seen: set[str] = set()

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        seen = self._seen
        if record.agent_id not in seen:
            # Checked once per distinct domain, not once per record: a fleet import
            # writes thousands of rows and this repository opens a connection per call.
            if not any(a.agent_id == record.agent_id for a in self.list_agents()):
                self.upsert_agent(
                    Agent(
                        user_id=self._user_id,
                        agent_id=record.agent_id,
                        name=f"Agent {record.agent_id}",
                        role=f"{record.agent_id} agent",
                    )
                )
            seen.add(record.agent_id)
        return super().insert(record)
