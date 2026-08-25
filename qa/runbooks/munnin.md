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

## Daily Loop / Quick Start
Boot the server, prove it healthy, stop it. This is the path to bring Munnin up and actually use it, and it is what a Tactic-A run follows.
```
bash qa/scripts/start-server.sh       # boots uvicorn in the background (pid -> qa/.munnin.pid)
bash qa/scripts/smoke-check.sh        # waits for health, asserts read path + content surface; exit 0 = pass
bash qa/scripts/stop-server.sh        # stop the backgrounded server
```
Full loop in one go:
```
bash qa/scripts/reset-db.sh && bash qa/scripts/seed-meta.sh && bash qa/scripts/start-server.sh && bash qa/scripts/smoke-check.sh; bash qa/scripts/stop-server.sh
```
The smoke path covers: `/health` answers, `/api/awaken?agent_id=meta` assembles, and the content surface (`/api/prompts`, `/api/resources`) responds. The MCP face is mounted at `/mcp` (streamable-HTTP). Logs stream to `qa/.munnin.log`.

## Act → Exercise the System
One scenario, and it is the module's standing invariant rather than any single feature's check: **no served prompt may carry markdown-path vocabulary or unconsumed seam scaffolding.**

Every prompt is composed in two stages — components inlined, then the `## Storage Mechanics` section replaced by the db backend's ops. A failure in either stage produces perfectly valid markdown that simply says the wrong thing to a DB client, and nothing raises. The bench's smoke check asserts one prompt contains `insert(`; it says nothing about the rest and nothing about leaks.

Earned 2026-08-21: a shared component instructed every reader to *"Use the Read tool directly"* — true on the markdown backend, meaningless to a client that has no files to read. It was caught by reading composed output, not by any test or probe.

With the server up (Daily Loop above):
```bash
BASE=http://127.0.0.1:8200
NAMES=$(curl -s $BASE/api/prompts | python -c "import sys,json;print(' '.join(json.load(sys.stdin)['prompts']))")
echo "served: $(echo $NAMES | wc -w) prompts"
for n in $NAMES; do
  BODY=$(curl -s "$BASE/api/prompts/$n")
  for bad in '## Storage Mechanics' '[STORAGE-BACKENDS-PATH]' '](components/' 'Read tool' 'MOVE-TO-TODAY'; do
    printf '%s' "$BODY" | grep -qF -- "$bad" && echo "LEAK $n <- $bad"
  done
done
```

## Observe → Confirm Result
- The loop prints **no `LEAK` lines**. Any output names the offending prompt and the exact string that leaked — that pair is the whole diagnosis.
- The served count printed by the loop is **12** as of 2026-08-21. A lower number means the running process predates a registration, not that content is missing — see Known Gotchas before investigating.
- Each `GET /api/prompts/{name}` answers `200` with `content-type: text/markdown; charset=utf-8`. A JSON envelope here means the raw-markdown response split regressed; the two *list* endpoints are the only content routes that legitimately answer JSON.

Last run 2026-08-21 — 12 prompts swept, zero leaks.

## Config Switching
All config is env-driven (`munnin.configuration.config`), defaulted for local:
`MUNNIN_HOST` `MUNNIN_PORT` `MUNNIN_USER_ID` `MUNNIN_DB_PATH` `MUNNIN_CONTENT_ROOT` `MUNNIN_IMPORT_SOURCE`.
Local template: [qa/config/.env.local.template](../config/.env.local.template). Committed config shape = [`.env.example`](../../.env.example) at the repo root; a real deployment supplies its own values.

## Troubleshooting
- **`/health` never comes up** → read `qa/.munnin.log`; commonly the port is taken (`MUNNIN_PORT`) or the DB dir is missing (`reset-db.sh` recreates it).
- **awaken returns empty** → the seed step didn't run or `MUNNIN_IMPORT_SOURCE` points at the wrong tree.
- **prompts/resources 404 or empty** → the `control-files` submodule isn't checked out (`git submodule update --init`).
- **a prompt you just registered 404s** → the running server predates the registration. Restart it; content edits need no restart, set changes do.
- **port 8200 is listening but no `qa/.munnin.pid` exists** → another session started a server outside the bench scripts. `stop-server.sh` will not find it, and starting your own will collide. Boot on `MUNNIN_PORT=8201` with your own `MUNNIN_DB_PATH` instead of killing theirs.
- **stop doesn't kill uvicorn** → on Windows/git-bash use the provided `stop-server.sh` (uses `taskkill //T` to kill the child tree).

## Known Gotchas
- On Windows/git-bash, a bare `kill` may leave the uvicorn child alive — always stop via `stop-server.sh`.
- SQLite WAL leaves `-wal`/`-shm` sidecars; `reset-db.sh` removes all three.
- The importer is idempotent (deterministic uuid5), so re-seeding without a reset is safe but a reset gives a truly clean count.
- **The served prompt *set* is fixed at process start; prompt *content* is not.** `_PROMPTS` is a module constant read at import, while bodies are read from `control-files` on every request. Editing a procedure's markdown shows up immediately; *adding* one needs a restart. Observed 2026-08-21: a server booted before a registration served 11 prompts and 404'd the 12th while its source file sat right there on disk.
- **Never compare a Python `len()` against curl's `size_download`.** `len(text)` counts characters; the wire carries UTF-8 bytes. `awaken-agent` is 10,731 characters and **10,842 bytes** — a 111-byte gap from 60 non-ASCII characters (`§`, `—`, `→`). Compared naively this reads as truncation. Use `len(text.encode("utf-8"))`.
- **Serving prompts never opens the database.** Verified 2026-08-21 against a `MUNNIN_DB_PATH` that was never created: `/api/prompts/*` answered 200 with full bodies and no file appeared. So RESET and INJECT are *not* preconditions for a content-surface check — useful for isolating whether a failure is content or data.
