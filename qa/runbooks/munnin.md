# Munnin — QA Runbook

> Tells the whole story of QA-ing the Munnin memory server. Read top-to-bottom first time; jump-to-section later. Single-app project — this runbook carries the whole story (no cross-module playbook).

## Goal
Bring Munnin up on a clean DB seeded with real memory, then confirm the data read path (awaken) and the served content surface (prompts/resources) work over the live HTTP face.

## Preconditions
- `uv` installed; deps synced (`uv sync`).
- The markdown memory tree present at `~/.claude/@agent-memory` (the importer's default source; override with `MUNNIN_IMPORT_SOURCE`).
- The `control-files` submodule checked out (served content lives there).
- No required secrets — every `MUNNIN_*` var is defaulted. See [qa/config/REQUIRED.md](../config/REQUIRED.md).

## Reset → Clean State
```
bash qa/scripts/reset-db.sh
```
Removes `data/valaskjalf-memory.db` (+ `-wal`/`-shm`).

## Inject → Realistic Data
Seed strategy: **importer, single agent** (the real production seed path).
```
bash qa/scripts/seed-meta.sh          # agent-meta + shared (fast)
bash qa/scripts/seed-meta.sh --all    # full fleet (~1284 records)
```

## Act → Exercise the System
```
bash qa/scripts/start-server.sh       # boots uvicorn in the background (pid -> qa/.munnin.pid)
```
Invariant smoke path: server answers `/health`, assembles `/api/awaken?agent_id=meta`, and serves the content surface (`/api/prompts`, `/api/resources`). MCP face is mounted at `/mcp` (streamable-HTTP).

## Observe → Confirm Result
```
bash qa/scripts/smoke-check.sh        # waits for health, asserts read path + content surface; exit 0 = pass
bash qa/scripts/stop-server.sh        # stop the backgrounded server
```
Full loop in one go:
```
bash qa/scripts/reset-db.sh && bash qa/scripts/seed-meta.sh && bash qa/scripts/start-server.sh && bash qa/scripts/smoke-check.sh; bash qa/scripts/stop-server.sh
```
Logs stream to `qa/.munnin.log`.

## Config Switching
All config is env-driven (`munnin.configuration.config`), defaulted for local:
`MUNNIN_HOST` `MUNNIN_PORT` `MUNNIN_USER_ID` `MUNNIN_DB_PATH` `MUNNIN_CONTENT_ROOT` `MUNNIN_IMPORT_SOURCE`.
Local template: [qa/config/.env.local.template](../config/.env.local.template). Deploy target = `deploy/munnin.env.example` (RackNerd, loopback `127.0.0.1:8200`, SSH tunnel).

## Troubleshooting
- **`/health` never comes up** → read `qa/.munnin.log`; commonly the port is taken (`MUNNIN_PORT`) or the DB dir is missing (`reset-db.sh` recreates it).
- **awaken returns empty** → the seed step didn't run or `MUNNIN_IMPORT_SOURCE` points at the wrong tree.
- **prompts/resources 404 or empty** → the `control-files` submodule isn't checked out (`git submodule update --init`).
- **stop doesn't kill uvicorn** → on Windows/git-bash use the provided `stop-server.sh` (uses `taskkill //T` to kill the child tree).

## Known Gotchas
- On Windows/git-bash, a bare `kill` may leave the uvicorn child alive — always stop via `stop-server.sh`.
- SQLite WAL leaves `-wal`/`-shm` sidecars; `reset-db.sh` removes all three.
- The importer is idempotent (deterministic uuid5), so re-seeding without a reset is safe but a reset gives a truly clean count.
