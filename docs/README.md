---
doc_type: 7q-readme
---

# agent-memory-server (Munnin)

## Table of Contents

- [What Is This?](#what-is-this)
- [How Do I Set It Up?](#how-do-i-set-it-up)
- [How Do I Use It?](#how-do-i-use-it)
- [How Does It Work Inside?](#how-does-it-work-inside)
- [How Is It Deployed?](#how-is-it-deployed)
- [What Decisions Were Made?](#what-decisions-were-made)
- [What's Broken / Known Debts?](#whats-broken--known-debts)

---

## What Is This?

**Munnin** (Odin's memory raven) is an **agent identity server**. It holds an AI agent's persistent self — identity, reasoning patterns, emotional moments, episodic history, knowledge, plus the foundations a whole fleet of agents shares — and serves the *procedures for tending that memory* beside the data, so an agent that connects can awaken as who it is and write back through the same discipline. It is the memory server of the [agent-memory framework](https://github.com/alvseek/agent-memory-system), whose markdown-file memory it turns into DB-backed software: `awaken` is a query, not a walk through files.

It speaks **MCP** to agents and offers the same operations over **HTTP** to server-to-server callers. It is project-blind — project-scoped memory belongs to a separate overlay (*Hermod*, not built).

It runs in one of two shapes, chosen by `MUNNIN_AUTH`; everything else in this document applies to both unless it says otherwise.

| | **Local** — `MUNNIN_AUTH=off` | **Hosted** — token mode (the default) |
|---|---|---|
| Who is calling | one constant tenant, `MUNNIN_USER_ID` | whoever a verified token says: its `(iss, sub)` pair resolves to a tenant |
| Sign-in | none | an OIDC issuer; each person gets their own tenant on first login |
| Reachable from | this machine only — the server refuses to start otherwise | a public HTTPS URL behind a TLS-terminating proxy |
| Typical run | `docker compose up` on a laptop | the prebuilt image under a deploy tool |

### Architecture

Two thin adapters over one transport-agnostic core, co-hosted on a single uvicorn app. Both faces share **one** token verifier and **one** tenant resolver, so there is no seam where they could drift apart. The store sits behind a `MemoryRepository` Protocol (SQLite today, swappable). Structured in **A-Boxed L1 boxes** — one package per box:

```
                ┌────────────── one uvicorn app ───────────────────────────────┐
   MCP client   │  /mcp    → api_mcp   (FastMCP streamable-HTTP)               │
  ──────────────┤              \                                              │
   HTTP caller  │  /api    → api_http  (FastAPI REST twin)   /health (open)    │
  ──────────────┤              \        /                                     │
                │          auth (token mode: one verifier — JWKS, aud = /mcp) │
                │          tenant resolver (token → account · local: constant)│
                │                        |                                    │
                │               business_services  (MemoryService, per tenant)│
                │                        |                                    │
                │               data_repositories ── Protocol ── SQLite       │
                │                        |                        Valaskjalf  │
                │               data_entities (five tables)      WAL · FTS5   │
                │                                                             │
                │  content ── serves control-files/ procedures + templates    │
                │             as MCP prompts, resources, and tools            │
                │  data_migrations ── markdown → DB importer                  │
                └─────────────────────────────────────────────────────────────┘
```

Both adapters call the same `MemoryService`; identical surface comes from the shared core, not from stacking MCP on HTTP. The awaken read path is traced in [flows/awaken-db.md](flows/awaken-db.md).

### Tech Stack

- **Runtime**: Python ≥ 3.12
- **MCP**: FastMCP ≥ 3.4.6 (streamable-HTTP; protocol revision 2025-11-25)
- **HTTP**: FastAPI ≥ 0.141 + uvicorn, single worker
- **Auth**: FastMCP's `RemoteAuthProvider` + `JWTVerifier` — Munnin is a *resource server*, verifying RS256 tokens against the issuer's public JWKS; it never holds a client secret
- **Store**: SQLite — WAL mode, FTS5 full-text, no external database
- **Tooling**: `uv` (build backend, deps, runtime venv), `ruff`, `pytest`
- **Served content**: the `control-files/` git submodule (the framework's procedures and templates)

---

## How Do I Set It Up?

### Prerequisites

- `git` — the served content is a submodule, so clone with `--recurse-submodules`
- **Either** Docker (the compose shape) **or** Python 3.12 + [`uv`](https://docs.astral.sh/uv/) (the process shape)

### Local mode

Local mode is the laptop shape: no identity provider, every call acts as the one tenant `MUNNIN_USER_ID`, and the server is reachable from this machine only. That last property is not a convention — `build_auth` **refuses to start** unless both hold:

1. `MUNNIN_PUBLIC_BASE_URL` names this machine (`127.0.0.1`, `localhost` or `::1`) — the default already does;
2. `MUNNIN_HOST` is a loopback address, **or** `MUNNIN_LOCAL_BIND_ALL=1` states that something in front of the process publishes the port on the host's loopback. The flag is an acknowledgement, never a detection: the server cannot see what publishes its port, so it asks to be told. `compose.yaml` sets it because its `ports:` line is `127.0.0.1:${MUNNIN_HOST_PORT}:8200`; a bare `docker run -e MUNNIN_AUTH=off` without the flag exits 1 naming `LocalModeNotLoopbackError`, because the image binds `0.0.0.0`.

Anything other than the literal `off` in `MUNNIN_AUTH` is token mode — a typo keeps authentication on, never off.

**Compose:**

```sh
git clone --recurse-submodules https://github.com/alvseek/agent-memory-server
cd agent-memory-server
docker compose up -d --build
curl http://127.0.0.1:8200/health      # {"status":"ok","service":"munnin","version":"0.1.0"}
```

State lives on the named volume `munnin-data`; `docker compose down` keeps it, `down -v` deletes it. Port 8200 already taken on the host? `MUNNIN_HOST_PORT=8201 docker compose up -d` — the published port and `MUNNIN_PUBLIC_BASE_URL` move together.

**Process:**

```sh
uv sync
MUNNIN_AUTH=off uv run python -m munnin     # 127.0.0.1:8200 → /mcp, /api, /health
```

Then [connect a client](#connecting-a-client).

### Import an existing markdown fleet (optional)

The store starts empty. If you already run the framework on markdown, the importer migrates it — deterministic `uuid5` per item, idempotent upsert, archived = a file absent from the agent's index:

```sh
uv run python -m munnin.data_migrations.importer --all          # the whole fleet
uv run python -m munnin.data_migrations.importer --agent meta   # one agent
# --source <markdown root>   --db <sqlite path>   (defaults: the framework store, MUNNIN_DB_PATH)
```

Records land in the tenant `MUNNIN_USER_ID`. In local mode that is the tenant every call reads, so import → `awaken` round-trips; in token mode the account row has to exist first and the tenant is whichever `(iss, sub)` you have mapped to it.

### Environment variables

All `MUNNIN_*`, all optional. Defaults describe a bare process on a laptop; the compose file and the image pin the container-specific ones.

| Variable | What it does | Default |
|---|---|---|
| `MUNNIN_AUTH` | `off` = local mode; anything else = token mode | token mode |
| `MUNNIN_HOST` | Bind address. Must be `0.0.0.0` inside a container (the image bakes it) | `127.0.0.1` |
| `MUNNIN_PORT` | Bind port | `8200` |
| `MUNNIN_PUBLIC_BASE_URL` | Where this server is addressed. Tokens are bound to `<this>/mcp`; local mode requires it to be loopback | `http://127.0.0.1:8200` |
| `MUNNIN_LOCAL_BIND_ALL` | `1` waives local mode's bind check — only when the port is published on the host's loopback | unset |
| `MUNNIN_USER_ID` | Local mode's tenant, and the tenant the importer stamps. Not read in token mode | `alvi` |
| `MUNNIN_DB_PATH` | Valaskjalf/memory SQLite file (runtime data, gitignored) | `data/valaskjalf-memory.db` |
| `MUNNIN_CONTENT_ROOT` | Served framework content root | `control-files` |
| `MUNNIN_LOGTO_ENDPOINT` | Token mode: the Logto tenant endpoint. OIDC paths are derived from it | unset |
| `MUNNIN_LOGTO_AUDIENCE` | Token mode: override the audience Logto tokens are checked against — comma-separated, for a rename window. Normally empty; it binds itself to `<public URL>/mcp` | unset |
| `MUNNIN_AUTHKIT_DOMAIN` | Token mode: a WorkOS AuthKit tenant — the issuer when set alone, a verify-only fallback beside Logto (how an issuer is replaced without locking anyone out) | unset |
| `MUNNIN_DOCS` | `1` enables FastAPI's `/openapi.json`, `/docs`, `/redoc`. They sit outside the auth guard — present or absent, never protected | off |

[.env.example](../.env.example) carries the same list with the local-mode values compose uses.

### Hosted (token mode)

Token mode is the default and needs an issuer, or the server refuses to start with `AuthNotConfiguredError`. What the issuer must be able to do, and what to set:

1. **An OIDC authorization server that binds tokens to a resource** — RFC 8707 resource indicators, so a token's `aud` can be this server and nothing else. Logto is the proven issuer: self-hosted Logto OSS 1.43+ with **CIMD** enabled (that is how claude.ai and Claude Code register themselves as clients; there is no client secret to hand out). Logto Cloud's free tier cannot serve this role — API resources are a paid feature there.
2. **Register the resource** on the issuer as an API resource whose identifier is exactly `https://<your-host>/mcp` — no trailing slash. That string is what a client sends as `resource` when it authorizes *and* when it refreshes, and the issuer matches it character for character; a refresh token is stamped with its resource when minted, so changing the identifier later means every client signs in again.
3. **Configure Munnin**: `MUNNIN_PUBLIC_BASE_URL=https://<your-host>`, `MUNNIN_LOGTO_ENDPOINT=https://<your-issuer>`, no `MUNNIN_AUTH`, no `MUNNIN_LOCAL_BIND_ALL`. Nothing here is a secret — it is a public URL and a public JWKS.
4. **Put it behind TLS.** Publish no port directly; the proxy in front terminates TLS and forwards `X-Forwarded-Proto`. The container binds `0.0.0.0` on the network the proxy shares with it.
5. **Verify from outside before connecting anything**: `GET /api/agents` and `POST /mcp` both answer **401** anonymously, the `WWW-Authenticate` challenge names `…/.well-known/oauth-protected-resource/mcp`, and that document's `resource` reads `https://<your-host>/mcp`. Only `GET /health` and the discovery documents answer without a token.

Then paste `https://<your-host>/mcp` into claude.ai's connector settings (claude.ai connects from Anthropic's servers, so a public HTTPS URL is a hard requirement — it can never reach a laptop) or `claude mcp add --transport http munnin https://<your-host>/mcp`. The first sign-in creates the person's tenant; there is no admission switch in Munnin — that belongs to the issuer's own sign-up settings.

Host provisioning, DNS and release orchestration are deliberately not in this repository — see [How Is It Deployed](#how-is-it-deployed).

---

## How Do I Use It?

### Commands

| Command | Description |
|---|---|
| `uv run python -m munnin` | Start the server (`/mcp` + `/api` + `/health`) |
| `docker compose up -d --build` | Same, as a container in local mode |
| `uv run pytest -q` | The test suite (446 tests) |
| `uv run ruff check` | Lint (pycodestyle, pyflakes, isort) |
| `uv run python -m munnin.data_migrations.importer --all` | Import a markdown fleet |

### Connecting a client

Munnin's MCP face is streamable-HTTP at `<public URL>/mcp` — both `/mcp` and `/mcp/` reach it, with no redirect between them.

- **Claude Code**: `claude mcp add --transport http munnin http://127.0.0.1:8200/mcp` (local) — token mode opens the browser for sign-in on first use.
- **A project `.mcp.json`**: `{ "mcpServers": { "munnin": { "type": "http", "url": "http://127.0.0.1:8200/mcp" } } }`
- **claude.ai**: paste the public `https://<host>/mcp` under connectors — hosted shape only.
- **Anything else**: any MCP client that speaks streamable-HTTP; in token mode it must handle the OAuth flow the 401 challenge advertises.

In a session, `ping` → `pong` is the connectivity check; `list_procedures` shows the 13 procedures; `read_procedure("create-agent")` is where a new tenant starts, and `read_procedure("awaken-agent", argument="<domain>")` is how a returning agent loads itself.

### MCP surface (agent face)

At `initialize` the server returns four sentences of **instructions** — what Munnin is, what to call first whether you are new or returning, and that procedures come from `read_procedure`, never slash commands; clients that show instructions inject them into the system prompt. Every tool carries a **title** and the MCP hints a client reads before letting it run: `readOnlyHint` on all, `destructiveHint` explicit on every write (additive: `insert`, `create_agent`, `append`, `prepend`; destructive: `edit`, `multi_edit`, `archive`, `soft_delete`), `openWorldHint=false` throughout.

**19 tools**, in four groups:

- *Orientation* — `help`: the same instructions text plus the served procedure list, for clients that never show instructions. Always present, even with no served content.
- *Data* — `awaken`, `get`, `query`, `search`, `insert`, `edit`, `append`, `prepend`, `multi_edit`, `archive`, `soft_delete`, plus `ping`. Writes have Edit-tool parity: `edit` is a targeted string replace, `append`/`prepend` add text verbatim, `multi_edit` applies a sequence atomically.
- *Agent lifecycle* — `create_agent`, `list_agents`. An agent exists when it has a row; every memory record names one under a foreign key, so `create_agent` is the strict twin of the first write.
- *Served content* — `list_procedures`, `read_procedure(name, argument?)`, `list_resources`, `read_resource(name)`. The same procedures and templates are also served as MCP **prompts** and **resources**, but a prompt is user-invoked and a resource client-attached; a tool is the one primitive the agent may call itself, which is what lets a served procedure that says *execute `/wrap-up`* resolve to `read_procedure("wrap-up")`.

**13 prompts** — the framework's command set, discovered from `control-files` at serve time (never a list kept in the server) minus `push`/`pull`/`refresh`-memory, which have no meaning against a database: `update-episodic`, `add-reasoning`, `update-emotional`, `update-knowledge`, `load-episodic`, `load-knowledge`, `archive-old-memories`, `update-memory`, `wrap-up`, `create-agent`, `list-agents`, `awaken-agent` (the awakening *process* — `awaken` returns the data, this says what to do with it), `wait-options`. Each carries its title and, where the procedure takes one, its argument.

**4 resources** — the framework's block templates, served as `resource://templates/<name>` and by the same name to `read_resource`: `episodic-entry-template`, `reasoning-pattern-template`, `emotional-moment-template`, `knowledge-file-template`.

### HTTP API (REST twin)

Every endpoint is a REST twin of an MCP primitive over the same core; only the naming idiom differs (REST nouns, MCP verbs — `/api/record/{uuid}` *is* the `get` tool). In token mode every `/api/*` route needs `Authorization: Bearer <token>`; in local mode none does.

| Method | Endpoint | MCP twin | Description |
|---|---|---|---|
| GET | `/health` | `ping` | Liveness — open in both modes (`{"status":"ok",…}`; the tool answers `"pong"`) |
| GET | `/api/awaken?agent_id=` | `awaken` | The agent's full 4-layer memory payload |
| GET | `/api/record/{uuid}` | `get` | One record's full body (`404` ↔ MCP `null`) |
| GET | `/api/query` | `query` | Browse the index — `agent_id`, `record_type`, `project`, `include_archived` |
| GET | `/api/search?text=` | `search` | FTS5 search over body + title + tags |
| GET · POST | `/api/agents` | `list_agents` · `create_agent` | The tenant's agents / create one |
| POST | `/api/insert` | `insert` | New item, record assembled server-side |
| POST | `/api/edit` · `/api/append` · `/api/prepend` · `/api/multi-edit` | the same names | Body edits with Edit-tool parity |
| POST | `/api/archive` · `/api/soft-delete` | `archive` · `soft_delete` | Out of the hot index but searchable · tombstoned |
| GET | `/api/prompts` · `/api/prompts/{name}` | `list_procedures` · `read_procedure` | Names as JSON · one procedure as raw `text/markdown` |
| GET | `/api/resources` · `/api/resources/{name}` | `list_resources` · `read_resource` | Names as JSON · one template as raw `text/markdown` |

A *list* is data and arrives as JSON; a *single* procedure or template is a document and arrives as raw markdown with no enclosing object, so `curl -o wrap-up.md` writes exactly the bytes an installed slash command carries. Errors stay JSON: `ValueError → 400`, `LookupError → 404`, and in token mode a missing or invalid token → `401` with a `WWW-Authenticate` challenge.

---

## How Does It Work Inside?

### Auth and tenancy

Three roles, and Munnin plays exactly one. The **identity provider** proves who the human is (Google, behind the issuer). The **authorization server** issues a token stamped for Munnin — `aud = https://<host>/mcp`. **Munnin** is the resource server: it verifies the token's signature against the issuer's JWKS, its issuer, and its audience, then decides what may be read. It never holds a client secret and never proxies OAuth; `build_auth` in `app.py` builds one `MultiAuth` that both faces share.

The tenant is a property of each **request**, not of the process. In token mode `TokenTenantResolver` maps the token's `(iss, sub)` — the only pair OpenID Connect guarantees stable — to an `account` row through `user_identity`, creating both on first sight. Email is a label, never a key: the OIDC spec lets an issuer reassign an address to a different person, and for a memory server that would hand one person's memory to another. Swapping issuers is therefore an insert in `user_identity`, not a rewrite of every record, and two issuers may verify at once while one replaces the other. In local mode `LocalTenantResolver` returns `MUNNIN_USER_ID` and `build_app` ensures its account row exists.

One identifier names the MCP face — `<public URL>/mcp`, no trailing slash — pinned in one place (`MCP_MOUNT_PATH`) and used by the 401 challenge, the metadata document, and the verifier's audience alike. A path-normalising middleware serves `/mcp` and `/mcp/` from one handler with no redirect, because a redirect built from the scheme uvicorn saw points at plaintext behind a TLS proxy.

### Core flow: awaken

`awaken(domain)` assembles the 4-layer memory model ([flows/awaken-db.md](flows/awaken-db.md)):

1. **Adapter** (`api_mcp/server.py` tool · `api_http/api.py` `/api/awaken`) delegates to the tenant's `MemoryService`.
2. **Service** (`business_services/memory_service.py`) validates the domain, then reads: the fleet-shared reasoning, knowledge and user profile (whole); the agent's identity, reasoning and emotional records (whole); the knowledge and episode **indexes** (metadata only) plus the **latest episode body**.
3. **Repository** (`data_repositories/sqlite_memory_repository.py`) — hot reads, soft-deleted and archived excluded.

The payload is data. The awakening *process* — what to do with it, the first-run profile question, the report — is the served `awaken-agent` procedure, which is why both are needed.

### Data model

Five tables (`data_entities/schema.sql`), all foreign keys live because each repository sets `PRAGMA foreign_keys = ON` per connection (SQLite defaults it off):

```
account        (user_id PK, display_name, email, created_date)          — the tenant
user_identity  (iss, sub) PK → account                                  — which issuer+subject is whom
agent          (user_id, agent_id) PK → account, name, role, uuid       — an agent exists because it has a row
shared_record  (id, uuid UNIQUE, user_id, record_type ∈ {reasoning, knowledge, user_profile},
                project, title, tags JSON, created/modified/archived/deleted_date, full_content)
memory_record  = shared_record + agent_id, record_type ∈ {episode, knowledge, identity, reasoning, emotional},
                FK (user_id, agent_id) → agent
```

- Fleet-shared memory has no owner, so it cannot live in `memory_record` without weakening that table's foreign key; the `CHECK` keeps episodes, identities and emotional moments — which always belong to some agent — out of it. There is no sentinel agent.
- Exactly one `user_profile` per tenant, by partial unique index: `awaken` answers *has anyone been asked yet* with the presence of a row.
- `archived_date` set = out of the hot index but still searchable; `deleted_date` set = tombstone. `uuid` is the idempotency key.
- Two FTS5 external-content indexes (`memory_fts`, `shared_fts`), trigger-synced; browse indexes serve the metadata reads.

### Served content

The procedures are storage-agnostic: a semantic core plus a `## Storage Mechanics` seam. `content/loader.py` composes them live from the submodule in the framework's two stages — shared **components** inlined at their reference point, then the core and the `db` backend substituted in — through `content/seam_bridge.py`, which imports `components/inline.py` and `storage-backends/seam.py` from their single homes in `control-files`. Munnin keeps no copy of either, which is what makes a served procedure byte-identical to the slash command the framework installs. The served *set* is the framework's own `command_set` minus the three memory-sync commands; add a procedure to `control-files` and it is served on the next request. The `db` backend also opens every composed procedure with its `## all-procedures` section — one sentence saying what `<domain>` in the ops means (the agent you awakened as, or the one `create-agent` made; `list_agents()` when there was no awakening) — so no served procedure leaves that placeholder to be guessed, and the markdown commands, whose backend defines no such section, are untouched.

### Importer

`data_migrations/importer.py` migrates a markdown fleet into records: two passes, aborting before any write if an agent's identity will not parse; deterministic `uuid5`; idempotent upsert on `uuid`; `markdown_parser.py` reads the fleet's several header dialects for episode dates and titles.

---

## How Is It Deployed?

### Environments

| Environment | Shape | Mode | Reached at |
|---|---|---|---|
| Laptop | `docker compose up` or `uv run python -m munnin` | local | `http://127.0.0.1:8200` |
| Hosted | the CI-built image under a deploy tool, behind a TLS proxy | token | `https://<host>/mcp`, one tenant per sign-in |

This repository is the **product**: source, image, tests. The private half of any real deployment — host, DNS, proxy config, release orchestration, the issuer's own deployment — lives outside it on purpose, because a deploy workflow in a public repo publishes host, user and paths with every secret masked. What the hosted shape *requires* is fully described under [Hosted (token mode)](#hosted-token-mode); how one particular box satisfies it is not this repo's business.

### CI/CD

Two GitHub Actions workflows:

- **CI** ([ci.yml](../.github/workflows/ci.yml)) — every push and PR: recursive checkout → `uv sync` → `ruff check` → `pytest -q`. `pytest` collects `tests/` only; the `control-files` submodule runs its own CI in its own repo.
- **Build image** ([build-image.yml](../.github/workflows/build-image.yml)) — `main` and `v*` tags: builds the [Dockerfile](../Dockerfile) with submodules and publishes **`ghcr.io/alvseek/munnin`**, tagged with the short commit SHA (immutable — this is what deploys and rollbacks name), the git tag when there is one, and a moving `latest` for ad-hoc runs. amd64 only. The package is public, so `docker pull ghcr.io/alvseek/munnin:latest` needs no login.

### Infrastructure

- **Image**: multi-stage on `python:3.12-slim`; uv pinned to the lockfile's revision; the venv and `src/` copied at the same paths, `control-files` copied in as read-only content; non-root `munnin` (uid 10001) with `/app/data` pre-owned so a fresh volume inherits it; `HEALTHCHECK` against `/health` in plain Python (slim has no curl); `ENTRYPOINT` is the venv interpreter directly so signals reach uvicorn.
- **Store**: one SQLite file, WAL mode, **single writer** — one uvicorn worker per database file. The volume mounts the data *directory*, never the `.db`, because WAL keeps `-wal`/`-shm` sidecars beside it; local driver only, since advisory locking over a network filesystem is a corruption path.
- **Scale**: the single-writer rule caps a database at one process, so scaling is a bigger box or the Postgres swap the `MemoryRepository` seam allows — not more workers.

### Rollback

Image tags are per-commit and never rebuilt in place, so rolling the application back is redeploying the previous SHA. The state is the volume, which the image never touches; a schema change applies lazily on first connection with `CREATE … IF NOT EXISTS`, so an older image runs against a newer schema as long as the columns it reads still exist. A markdown fleet, where one exists, stays importable at any time.

---

## What Decisions Were Made?

The framework's ADRs live in the private `@agent-memory` repo; the ones that shape this server:

- **ADR-013 — DB persistence, store ownership, transport split (2026-08-08).** Munnin owns `Valaskjalf/memory` with one writer; MCP for agent↔server, HTTP for server↔server, the HTTP face exposing the **full** surface; one uniform record with Edit-tool-parity writes; soft-delete + archive + FTS5. *Trade-off*: a server and a store to operate, for instant `awaken` and real search.
- **ADR-012 — memory core / coding-skill decoupling (2026-08-06).** The framework split into a memory-primitives core (`control-files`, wrapped by this server) and a sibling coding overlay, one-way dependency. *Trade-off*: more repos, for a core an MCP server can serve whole.
- **ADR-015 — agent identity as a first-class entity (2026-08-20).** One table became three (`agent`, `shared_record`, `memory_record`) with the owner enforced by a foreign key, killing the sentinel agent id. *Trade-off*: `create_agent` before the first write, for records that can never name an owner that does not exist.

In-repo decisions:

- **Two thin adapters over one core**, not MCP-over-HTTP — identical surface from the shared service, no localhost hop.
- **Token mode by default; local mode guarded.** A server that cannot check a token refuses to start; `off` is accepted only while the public URL is loopback and the bind is loopback or acknowledged. The guard lives in `build_auth`, so it fires the same whether config came from the environment or was constructed in a test.
- **Resource server, never proxy.** Verification is local against a public JWKS; no vendor is called per request and no client secret sits on the box. Two issuers may be configured at once so one can replace the other without a lockout window.
- **`(iss, sub)` → tenant, in a table we own.** Portability across issuers is an insert, not a migration of every record; email is never a key.
- **One resource identifier, no trailing slash**, pinned in one place and served under both spellings with no redirect — because the MCP specification says clients should use the no-slash form and claude.ai normalises to it, and a refresh token is frozen to whichever form it was minted for.
- **Served set discovered, not listed.** The procedures Munnin serves are the framework's own command set read at serve time; a hand-kept list in the server was the defect this replaced.
- **Storage-backend seam for served procedures** — one semantic core, `markdown` and `db` backends composed at serve time: the prose-layer mirror of the `MemoryRepository` Protocol.

---

## What's Broken / Known Debts?

### Planned before the hosted demo is promoted

- **`GET /` is a 404.** A landing page — what this is, how to connect, the demo's wipe notice and privacy line — is the next piece of the HTTP face.
- **Registration is open and nothing bounds a tenant.** No per-tenant record or body cap, no scheduled wipe of demo tenants.

### Known defects

- **`awaken` on an unknown agent returns the same empty payload as an existing agent with no records**, and its `user_profile: null` trips the first-run profile question. A missing agent should be told apart.
- **Upsert preserves `created_date`**, so a data-correcting re-import needs a fresh database, not an idempotent re-run.
- **`qa/scripts/start-server.sh` boots with no environment** and has failed on `AuthNotConfiguredError` since token mode landed; `MUNNIN_AUTH=off` is its repair.
- **[flows/awaken-db.md](flows/awaken-db.md) still flags the "awakening process gap" as open.** It closed on 2026-08-21 when `awaken-agent` became a served procedure; the flow doc has not been re-drawn.

### Deferred

- Metadata-only projection for browse (bodies are returned today); an `always_load` flag for must-load knowledge.
- The AuthKit issuer path is retained as a verify-only fallback for issuer migration but is not exercised by any deployment.
- MCP protocol revision **2025-11-25**: caching hints, `resource_link` and the vary-by-authorization rule from 2026-07-28 wait on FastMCP.

### Limitations by design

- **Single writer** per SQLite file — scale by box or by the Postgres swap, never by workers.
- **Project-blind** — project-scoped memory is Hermod's.
- **No rate limiting** at the application layer; put it in the proxy.
