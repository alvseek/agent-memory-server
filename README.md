# agent-memory-server (Munnin)

The **memory MCP server** for the agent-memory framework — Python · FastMCP · FastAPI · SQLite.

Codename **Munnin** (Odin's memory raven). Owns the **`Valaskjalf/memory`** store (identity, episodic, knowledge, shared foundations) and serves memory primitives over **MCP** (agents) + an **HTTP** operation API. Project-blind.

Design of record: `docs/architecture/memory-mcp-server.md` + ADR-013 (in the `@agent-memory` repo).

## Clone

```bash
git clone --recurse-submodules <url>   # control-files is a git submodule
```

The framework procedures/templates served as `content/` live in the **`control-files/`** submodule (`agent-memory-system`).

## Dev

```bash
uv sync
uv run python -m munnin      # boots on 127.0.0.1:8200 → /mcp (MCP) + /api + /health
uv run pytest
uv run ruff check
```

## Deploy

Two supported shapes, both driven by the same `MUNNIN_*` settings ([.env.example](.env.example)):

- **Container** — [Dockerfile](Dockerfile) + [compose.yaml](compose.yaml). One unit, non-root, SQLite on a named volume mounted at the data *directory*.
- **Process** — `.venv/bin/python -m munnin` under any supervisor; no uv needed at runtime.

Both bind loopback by default and expect a reverse proxy or tunnel in front. Host-specific configuration and release orchestration live outside this repo.

## Status

Working locally. The full surface is in place on both faces — **11 data tools** (`awaken`, `get`, `query`, `search`, `insert`, `edit`, `append`, `prepend`, `multi_edit`, `archive`, `soft_delete`) over a SQLite + FTS5 store, plus **12 procedures served as MCP Prompts** and **4 templates as Resources**, and a lossless markdown→DB importer.

**Not yet deployed** — the fleet still awakens from markdown; the RackNerd rollout is the remaining step. Full architecture, surface reference, and known debts: [docs/README.md](docs/README.md).
