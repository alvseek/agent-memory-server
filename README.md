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

RackNerd VPS, **systemd + uv, no Docker**. See `deploy/` (`munnin.service`, `deploy.sh`). Bind loopback `127.0.0.1:8200`; reach it via SSH tunnel. `MemoryMax=200M`.

## Status

Scaffold (Phase 4 of the Rite of Creation). Empty skeleton — boots + health only; memory logic lands in Phase 5 (Core Dev).
