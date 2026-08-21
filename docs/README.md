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

**Munnin** (Odin's memory raven) is the **memory MCP server** for the agent-memory framework. It owns the **`Valaskjalf/memory`** store — every agent's identity, reasoning, emotional, episodic, and knowledge records, plus the fleet-shared foundations — and serves them over two faces: **MCP** (for agents) and an **HTTP** operation API (for server-to-server callers). It is **project-blind** (project-scoped memory belongs to a separate overlay, *Hermod*).

It turns the framework's markdown-file memory into DB-backed software: an agent can `awaken` from a `SELECT` instead of reading files, and read/write memory through a small set of generic tools.

### Architecture

Two thin adapters over one transport-agnostic core, co-hosted on a single uvicorn app. The store sits behind a `MemoryRepository` Protocol (DI seam — SQLite today, swappable later). Structured in **A-Boxed L1 boxes** (one package per box):

```
              ┌───────── one uvicorn app (127.0.0.1:8200) ─────────┐
   MCP client │  /mcp   → api_mcp    (FastMCP streamable-HTTP)      │
  ────────────┤                        \                           │
  HTTP caller │  /api   → api_http    (FastAPI REST twin)          │
  ────────────┤           /health       \                          │
              │                    business_services               │
              │                    (MemoryService — the core)      │
              │                          |                         │
              │                    data_repositories  ── Protocol ─┼── SqliteMemoryRepository
              │                          |                         │        │
              │                    data_entities (MemoryRecord)    │   Valaskjalf/memory
              │                                                    │   (SQLite · WAL · FTS5)
              │  content ── serves control-files/ procedures as    │
              │             MCP Prompts + templates as Resources   │
              │  data_migrations ── markdown → DB importer         │
              └────────────────────────────────────────────────────┘
```

Both adapters call the **same** `MemoryService`; identical surface comes from the shared core, not from stacking MCP on HTTP. The awaken read path is documented in [flows/awaken-db.md](flows/awaken-db.md).

### Tech Stack

- **Runtime**: Python ≥ 3.12
- **MCP**: FastMCP ≥ 3.4.6 (streamable-HTTP transport)
- **HTTP**: FastAPI ≥ 0.141 + uvicorn (single worker)
- **Store**: SQLite — WAL mode + FTS5 full-text (no external DB)
- **Tooling**: `uv` (build backend + deps + runtime venv), `ruff` (lint/format), `pytest`
- **Served content**: the `control-files/` git submodule (framework procedures + templates)

---

## How Do I Set It Up?

### Prerequisites

- Python 3.12 (`python --version`)
- [`uv`](https://docs.astral.sh/uv/) (`uv --version`) — used for deps, the build, and the runtime venv
- `git` (the framework content is a submodule)

### Setup

1. Clone **with submodules** (the served `content/` lives in `control-files/`):
   ```sh
   git clone --recurse-submodules <repo-url>
   cd agent-memory-server
   ```
   (already cloned without `--recurse-submodules`? run `git submodule update --init --recursive`)

2. Install:
   ```sh
   uv sync
   ```

3. (Optional) Populate the DB from the markdown fleet — the store is empty until imported:
   ```sh
   uv run python -m munnin.data_migrations.importer --all   # flags: --source, --db (defaults to MUNNIN_DB_PATH)
   ```

4. Start:
   ```sh
   uv run python -m munnin      # boots on 127.0.0.1:8200
   ```

5. Verify it works:
   ```sh
   curl http://127.0.0.1:8200/health
   # Expected: {"status":"ok","service":"munnin","version":"0.1.0"}
   ```

### Environment Variables

All optional — defaults are local-first. Override with `MUNNIN_*`:

| Variable | Description | Default |
|----------|-------------|---------|
| `MUNNIN_HOST` | Bind address | `127.0.0.1` |
| `MUNNIN_PORT` | Bind port | `8200` |
| `MUNNIN_USER_ID` | Server-side tenant id (stamped on writes; never from caller) | `alvi` |
| `MUNNIN_DB_PATH` | Valaskjalf/memory SQLite file (gitignored runtime data) | `data/valaskjalf-memory.db` |
| `MUNNIN_CONTENT_ROOT` | Served framework content root | `control-files` |

---

## How Do I Use It?

### Commands

| Command | Description |
|---------|-------------|
| `uv run python -m munnin` | Start the server (MCP `/mcp` + HTTP `/api` + `/health`) |
| `uv run pytest` | Run the test suite (`tests/`) |
| `uv run pytest -q` | Quiet test run (CI form) |
| `uv run ruff check` | Lint (pycodestyle + pyflakes + isort) |

### MCP surface (agent face)

- **Tools** (14 — data primitives plus agent lifecycle): `ping`, `awaken`, `get`, `query`, `search`, `insert`, `edit`, `append`, `prepend`, `multi_edit`, `archive`, `soft_delete`, `create_agent`, `list_agents`
- **Prompts** (12 procedures, composed with the DB backend — the "how-to" before calling the tools): `update-episodic`, `add-reasoning`, `update-emotional`, `update-knowledge`, `load-episodic`, `load-knowledge`, `archive-old-memories`, `update-memory`, `wrap-up`, `create-agent`, `list-agents`, `awaken-agent` — the last carrying the awakening protocol itself, since `awaken` returns the memory but not the process for using it
- **Resources**: framework block-templates (`episodic-entry`, `reasoning-pattern`, `emotional-moment`, `knowledge-file`)

### HTTP API (REST twin)

Each HTTP endpoint is a REST twin of an MCP primitive over the **same** `MemoryService` core. The naming idiom differs by protocol: REST paths are **resource/noun**-style, MCP tools are **verb**-style — so `/api/record/{uuid}` is the same operation as the `get` tool (a naming asymmetry, not a missing tool).

| Method | Endpoint | MCP twin | Description |
|--------|----------|----------|-------------|
| GET | `/health` | `ping` tool | Liveness (`/health` returns a status object; the `ping` tool returns `"pong"`) |
| GET | `/api/awaken?agent_id=` | `awaken` tool | Assemble an agent's full 4-layer memory payload |
| GET | `/api/record/{uuid}` | `get` tool | Load one record's full body (HTTP `404` ↔ MCP `null` when absent) |
| GET | `/api/query` | `query` tool | Browse the index (filter by `agent_id`/`record_type`/`project`/`include_archived`) |
| GET | `/api/search?text=` | `search` tool | Full-text (FTS5) search over content + title + tags |
| POST | `/api/insert` | `insert` tool | Append a new item (record assembled server-side) |
| POST | `/api/edit` | `edit` tool | Targeted string replace in a record body (Edit-tool parity) |
| POST | `/api/append` | `append` tool | Add text verbatim to the end of a record body |
| POST | `/api/prepend` | `prepend` tool | Add text verbatim to the start of a record body |
| POST | `/api/multi-edit` | `multi_edit` tool | Apply a sequence of edits to one record atomically |
| POST | `/api/archive` | `archive` tool | Retire a record from the hot index (still searchable) |
| POST | `/api/soft-delete` | `soft_delete` tool | Tombstone a record (excluded from all reads) |
| GET | `/api/prompts` · `/api/prompts/{name}` | `prompts/list` · `prompts/get` | List names (JSON) / fetch a served procedure, DB-composed, as raw markdown |
| GET | `/api/resources` · `/api/resources/{name}` | `resources/list` · `resources/read` | List names (JSON) / fetch a served template verbatim, as raw markdown |

The `prompts/*` and `resources/*` rows twin MCP's **native prompt/resource primitives** (not tools); every other row twins a **tool**. Their response shape splits by what is being returned: a *list* of names is data and arrives as JSON, while a *single* procedure or template is a document and arrives as raw `text/markdown; charset=utf-8` — no enclosing object, so `curl -o update-episodic.md` writes exactly the bytes an installed slash command carries. Errors stay JSON throughout: `ValueError → 400`, `LookupError → 404`.

---

## How Does It Work Inside?

### Core Flow: Awaken

`awaken(domain)` assembles the 4-layer memory model from the DB (see [flows/awaken-db.md](flows/awaken-db.md) for the full trace):

1. **Adapter** (`api_mcp/server.py` tool · `api_http/api.py` `/api/awaken`) — delegates to the core.
2. **Service** (`business_services/memory_service.py`) — `validate_domain`, then queries the repo for: layer i `__shared__` reasoning + knowledge (whole), layer ii the agent's identity/reasoning/emotional (whole), layer iii knowledge + episode **indexes** (metadata only) + the **latest episode body**.
3. **Repository** (`data_repositories/sqlite_memory_repository.py`) — hot-read queries (soft-deleted + archived excluded).

Writes follow the same core → repo path with Edit-tool parity (`insert` / `edit` / `append` / `prepend` / `multi_edit` / `archive` / `soft_delete`). `append` / `prepend` add text verbatim to a body (caller controls newlines); `multi_edit` applies a sequence of edits to one record atomically (all-or-nothing).

### Data Model

One **uniform record** per item (`data_entities/schema.sql`, `memory_record.py`) — episode / knowledge / identity / reasoning / emotional all share one table:

```
memory_record(id PK, uuid UNIQUE, user_id, agent_id, record_type,
              project, title, tags(JSON), created_date, modified_date,
              archived_date, deleted_date, full_content)
  + idx_memory_browse (user_id, agent_id, record_type, project, created_date)
  + memory_fts  FTS5 external-content over (full_content, title, tags), trigger-synced
```

- `agent_id` = a kebab domain **or** the `__shared__` sentinel (fleet-shared reasoning/knowledge).
- `archived_date` non-NULL = out of the hot index but still searchable; `deleted_date` non-NULL = tombstone.
- `uuid` is the idempotency key (upsert on `uuid`).

### Served Content (component inlining + storage-backend seam)

The 9 served procedures are storage-agnostic: a semantic core + a `## Storage Mechanics` seam. `content/loader.py` composes them live from the submodule at serve time, in the framework's two stages — **components inlined** (shared fragments under `procedures/components/`, replaced at their reference point so the Prompt points at no file the client cannot reach), then **core + `db` backend** substituted in. Ops a component brings are defined once under the component's own backend section and composed in alongside the procedure's, so they resolve without being restated under every caller.

Both substitutions load through `content/seam_bridge.py` from their single homes in control-files (`components/inline.py`, `storage-backends/seam.py`) — Munnin keeps no copy of either, which is what makes a served Prompt byte-identical to the slash command `compile-procedures.py` installs. So a Munnin client is served DB-tool mechanics while the native markdown fleet reads the same core + the `markdown` backend. `push`/`pull`/`refresh`-memory and `awaken-agent` are **not** served (see Debts).

### Importer

`data_migrations/importer.py` migrates the markdown fleet → records (deterministic `uuid5`, idempotent upsert; archived = a file absent from the agent's index). `markdown_parser.py` extracts episode dates/headings across the fleet's header dialects.

---

## How Is It Deployed?

### Environments

| Environment | Host | Bind | Notes |
|-------------|------|------|-------|
| Local dev | your machine | `127.0.0.1:8200` | `uv run python -m munnin` |
| Production | RackNerd VPS | `127.0.0.1:8200` (loopback) | reached via **SSH tunnel** — no public exposure, no TLS (SSH is the auth boundary) |

### CI/CD

GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) on push + PR: checkout (recursive submodules) → `uv sync` → `uv run ruff check` → `uv run pytest -q`. Remote is `github.com/alvseek/agent-memory-server` (added 2026-08-14).

`pytest` collects `tests/` only, by design: **control-files runs its own CI** on `agent-memory-system` (lint, its 38 tool tests, a strict compile of every seam procedure, and the core-invariant guard). A submodule's tests are gated by the repo that owns them, not by this one. **No deploy automation** — deploy is manual via `deploy/deploy.sh`.

### Infrastructure

- **Runtime**: systemd unit ([deploy/munnin.service](../deploy/munnin.service)) — **systemd + uv, no Docker**; runs `.venv/bin/python -m munnin` directly (no uv needed at runtime), `Restart=on-failure`, **`MemoryMax=200M`** (hard ceiling protecting co-tenants on the 1 GB box).
- **Store**: SQLite file on local disk (`data/valaskjalf-memory.db`), WAL, **single writer** (one uvicorn worker per file).
- **Scale trigger**: sustained swap > 700–800 MB + rising restarts → move to a bigger box (RAM check 2026-08-09: 461 MB avail).

### Rollback

The markdown fleet remains authoritative; the markdown→DB awakening switch is enabled-but-not-activated, so rollback = keep awakening on markdown. `[TODO: document the service-level rollback (systemctl to a prior venv/commit) once a release flow exists]`.

---

## What Decisions Were Made?

The full ADRs live in the `@agent-memory` repo (`docs/adr/`). Key ones shaping this server:

### ADR-013: DB Persistence, Store Ownership & Transport Split (2026-08-08)

**Context**: The framework's memory was markdown + git; awakening meant reading files across the fleet.
**Decision**: Persist to a DB; Munnin owns `Valaskjalf/memory` (one writer); MCP for agent↔server, HTTP for server↔server; the HTTP face exposes the **full** memory surface; one uniform record + Edit-tool-parity writes; `user_id` token-passthrough tenancy; soft-delete + archive + FTS5.
**Trade-off**: A running server + a store to operate, vs. plain files — accepted for DB-backed recall (instant `awaken`, FTS search).

### ADR-012: Memory Core / Coding-Skill Decoupling (2026-08-06)

**Context**: Repo/coding procedures were entangled with memory primitives.
**Decision**: Split into a memory-primitives core (control-files, MCP-wrappable → this server) + a sibling coding overlay; one-way dependency.
**Trade-off**: More repos to coordinate, vs. a clean core an MCP server can wrap.

### In-repo design decisions

- **Two thin adapters over one core** (not MCP-over-HTTP) — identical surface from the shared `MemoryService`, no pointless localhost hop.
- **Constant `user_id`, no auth** (v1) — local-first / single-fleet; schema stays multi-tenant-ready.
- **Storage-backend seam for served procedures** — one semantic core, `markdown`/`db` backends composed at serve time (the prose-layer mirror of the `MemoryRepository` Protocol).
- **`awaken-agent` + push/pull/refresh not served** — on the reasoning "the DB write is durable; awaken is a tool." *This under-covered the awakening **process** — see Debts.*

---

## What's Broken / Known Debts?

### High Priority

- **Awakening process-instruction gap**: the `awaken` tool returns memory **data** only. The awakening **process** (Phase 1/2 flow, sub-agent-read prohibition, report format) lives only in `awaken-agent.md` + `core-instruction-control-files.md`, which are **not imported and not served** — so a pure-DB client gets the records but no process. Confirmed 2026-08-13; see [flows/awaken-db.md](flows/awaken-db.md).
  *Why*: `awaken-agent` was scoped out of SP-5's served set on "awaken is a tool," which only covered the data half.

### Medium Priority

- **Upsert does not update `created_date`**: a data-correcting re-import needs a **fresh DB rebuild** (delete + import), not an idempotent re-run.
  *Why*: idempotent upsert preserves the original creation timestamp by design; correction wasn't a modeled case.
- **markdown→DB switch enabled-but-not-activated (B′)**: awakening still runs on markdown in production; DB path is proven locally only.
  *Why*: the remote landed 2026-08-14, so the gate is now the RackNerd deploy itself plus the awakening process-instruction gap above.

### Low Priority

- **Metadata-only projection query** deferred (browse currently returns bodies).
- **`must-load-domain-knowledge`** mechanism unmodeled (future `always_load` flag on knowledge rows).
- **"Domain Ras" identity title cosmetic** — `.title()` lowercases the RAS acronym.
- **1 cp1252-mojibake source file + 1 dangling `backend-net-framework` index ref** to clean in the markdown fleet.
- **codex/antigravity installers + Hermod overlay MCP** deferred.

### Known Limitations

- **Single writer**: one uvicorn worker per SQLite file (WAL) — horizontal scaling needs the Postgres swap the `MemoryRepository` seam allows.
- **No auth / no TLS**: v1 relies on loopback binding + SSH tunnel as the security boundary.
- **Project-blind**: project-scoped memory is out of scope (belongs to the Hermod overlay).
