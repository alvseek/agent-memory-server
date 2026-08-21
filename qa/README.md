---
doc_type: qa-riao-readme
---

# Munnin (agent-memory-server) — QA Instrument

> **What this is**: the QA instrument for **Munnin**, the memory MCP server — how to reset, seed, run, and observe it locally, and where every QA artifact lives.

---

## The R/I/A/O Loop

Every QA cycle here is one turn of **RESET → INJECT → ACT → OBSERVE**:

| Phase | What it means in Munnin | Mechanism | Status |
|---|---|---|---|
| **RESET** — back to known-clean | Delete the SQLite store plus its `-wal`/`-shm` so the next connection rebuilds it from `schema.sql`. Safe by design: the DB is a **rebuildable projection** of the markdown store, never a source of record — losing it costs one re-import. | [`scripts/reset-db.sh`](scripts/reset-db.sh) | documented |
| **INJECT** — realistic data in | Import from the **authoritative markdown store** via the production importer CLI — bare runs agent-meta plus the fleet-shared layer, `--all` does all 27 agents. Snapshot-shaped rather than dummy: the source is real, so a re-import cannot drift from it. | [`scripts/seed-meta.sh`](scripts/seed-meta.sh) · [seeds](seeds/) | documented |
| **ACT** — exercise the system | Boot the co-hosted uvicorn app in the background — MCP at `/mcp`, HTTP at `/api`, `/health` — on `127.0.0.1:8200`. PID and log land under `qa/`. | [`scripts/start-server.sh`](scripts/start-server.sh) · [`scripts/stop-server.sh`](scripts/stop-server.sh) | documented |
| **OBSERVE** — see what happened | Probe the live server end to end: wait for `/health`, then assert the **data read path** (`awaken`) and the **content surface** (prompts + resources). Non-zero exit on any failure. | [`scripts/smoke-check.sh`](scripts/smoke-check.sh) | documented |

*All four were graded `tribal` by the map on 2026-08-21 — working mechanisms that no index pointed at. The links above are the promotion; no script was renamed, moved or rewritten. Status became `documented` only after the loop was run end to end (below).*

---

## First-Time Setup

**Prerequisites**: Python ≥ 3.12 · [uv](https://docs.astral.sh/uv/) · a populated markdown memory store at `~/.claude/@agent-memory` (the INJECT source) · `curl` for the smoke check.

1. `uv sync` — install dependencies.
2. `bash qa/scripts/reset-db.sh` — start from a clean store.
3. `bash qa/scripts/seed-meta.sh --all` — import the whole fleet. Omit `--all` for agent-meta only, which is faster and enough for most work.
4. `bash qa/scripts/start-server.sh` then `bash qa/scripts/smoke-check.sh` — expect `SMOKE OK` and exit 0. That green is the instrument working.

No config acquisition is needed: `configuration/config.py`'s defaults *are* the local config. See [config/REQUIRED.md](config/REQUIRED.md).

---

## Daily Loop

```sh
bash qa/scripts/reset-db.sh          # RESET   — only when you need a clean slate
bash qa/scripts/seed-meta.sh --all   # INJECT  — first run / after a reset
bash qa/scripts/start-server.sh      # ACT     — boots on 127.0.0.1:8200, backgrounded
bash qa/scripts/smoke-check.sh       # OBSERVE — expect SMOKE OK, exit 0
# ... run the feature under test ...
bash qa/scripts/stop-server.sh       # done
```

Every script honours `MUNNIN_DB_PATH`, `MUNNIN_IMPORT_SOURCE`, `MUNNIN_HOST` and `MUNNIN_PORT`, so a second instance can run beside a live one without collision.

---

## Where Everything Lives

| Layer | What | Where | Built by |
|---|---|---|---|
| Per-module "how to run" | Runbook | [runbooks/munnin.md](runbooks/munnin.md) | /build-qa-test |
| Per-feature verification | Checklists | [checklists/](checklists/) — 1 active | /build-qa-test |
| Per-stage test preconditions | Fixtures | [fixtures/](fixtures/) | /build-qa-test |
| R/I/A/O scripts | Scripts | [scripts/](scripts/) | /build-qa-bench |
| Required config + templates | Config | [config/](config/) | /build-qa-bench |
| Test-data sources | Seeds | [seeds/](seeds/) | /build-qa-bench |
| What exists + maturity audit | Map | [qa-map.md](qa-map.md) | /map-qa-instrument |

*No cross-module playbook: Munnin is one app, and `control-files` is a submodule of served content rather than a second running service. See [qa-playbook-map.md](qa-playbook-map.md) for what a playbook here would actually be about.*

---

## Config Switching

There is almost nothing to switch, and that is deliberate: `configuration/config.py` ships working local defaults (`127.0.0.1:8200`, `data/valaskjalf-memory.db`, `content_root=control-files`, `user_id=alvi`), so a fresh clone runs without any config step.

- **Local override**: set `MUNNIN_*` environment variables for the run. Nothing is written to disk, so nothing can be committed by accident.
- **Deploy target**: [`deploy/munnin.env.example`](../deploy/munnin.env.example) is the committed shape for a real deployment; the real `.env` never enters git.
- **Invariant**: committed config = deploy target; local overrides are environment-only.

---

## Known Gaps / Debts

**Rig** (→ `/build-qa-bench`):
- **`qa/seeds/` holds no seed source**, only its map. The real INJECT source is the markdown store itself, which lives outside this repo by design — worth stating rather than materialising. The five unreferenced `data/valaskjalf-memory.db.bak-*` snapshots (~76 MB) have no retention policy.

**Test layer** (→ `/build-qa-test`):
- **One checklist now exists** — [checklists/user-profile.md](checklists/user-profile.md), built 2026-08-21. It is **not yet run**: its first-run-bootstrap items need a fresh agent session reading the installed instruction, and its pipeline items need the configurator run for real. Every other shipped change in this repo still has no checklist.
- **Fixtures are inlined in the test suite** (`_fake_source`, `_seed`, `_db`) rather than extracted to `qa/fixtures/`, so nothing is composable and `/run-qa-test` Tactic B cannot reach them.
- The runbook predates the three-table store and the `user_profile` record type; its content has not been re-checked against them.

**Not a gap**: the retired `# R/I/A/O category:` headers still present in all five scripts. They are inert — this table is the contract now — and rewriting working scripts to remove them would be churn.

---

## Where To Go Next

- Run **the module** → its [runbook](runbooks/munnin.md).
- See **what exists + how mature** → [qa-map.md](qa-map.md).
- **Build** a missing piece → `/build-qa-bench` (rig) or `/build-qa-test` (tests).
- **Run** the verification → `/run-qa-test`.
