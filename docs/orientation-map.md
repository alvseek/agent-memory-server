---
project: "agent-memory-server"
description: "Orientation map for the Munnin memory-server repo — the project 7Q README, the awaken flow doc, deploy + QA runbooks, and the control-files framework submodule sub-map."
created: "2026-08-13"
last_full_scan: "2026-08-13"
---

# Orientation Map — agent-memory-server (Munnin)

Index of orientation artifacts in this repo. Used by agents at awakening (load into session context) and wrap-up (refresh entries the session touched) via the `/map-orientation` skill. This map is **self-contained to `agent-memory-server`** — it indexes only this repo's own docs (plus its `control-files` submodule sub-map) and stands on its own.

## Status Legend

- **useful** — current, accurate, future tasks will rely on it. Update when scope changes.
- **stale-but-valuable** — could be useful if updated. Repair on demand when next task hits its scope.
- **obsolete** — neither current nor valuable. Ignore. Optional: archive or delete.
- **unverified** — mtime changed since `last_verified`, or never verified. Next task touching its scope verifies and updates status.

## Scope Legend

- **shared** — relevant to every role on this project. Always loaded.
- **role-private** — relevant only to roles listed in `roles`. Other roles skip.
- **cross-readable** — relevant to roles listed in `roles`, PLUS Architect and QA always.

*(agent-memory-server is a single-role project — all entries are `scope: shared, roles: []`; the role filter is a no-op.)*

## Type Legend

- **7q-readme** — 7 Questions Framework README (any scope: root, module, sub-component)
- **flow-diagram** — a flow deep-dive (`doc_type: flow`, under `docs/flows/`)
- **orientation-map-link** — pointer to a child orientation map for a sub-project. The `child_map` field names the sub-map file.
- **other** — orientation artifact that doesn't fit above (deploy guide, runbook, non-7Q README, etc.)

---

## Entries

### `README.md`

- **type**: other
- **scope**: shared
- **roles**: []
- **status**: useful
- **tags**: [overview, entry-point, non-7q, pointer]
- **last_verified**: "2026-08-21"
- **verified_by**: "meta / awaken-agent served-prompt session"
- **update_trigger**: "when setup/deploy invocation or the served surface changes; slim to a thin pointer to docs/README.md per the placement contract"
- **notes**: "Root README (non-7Q). Status line corrected 2026-08-15 — it had claimed an empty Phase 4 scaffold 'boots + health only', ~5 phases stale; now states the real surface (11 data tools, 12 Prompts, 4 Resources, importer) with deployment named as the open step, verified by introspection rather than recall. Content is accurate; the structural decision to slim it to a thin pointer at docs/README.md is still pending (A/B/C)."

### `docs/README.md`

- **type**: 7q-readme
- **scope**: shared
- **roles**: []
- **status**: useful
- **tags**: [readme, 7q, project-entry-point, munnin, mcp-server]
- **last_verified**: "2026-08-21"
- **verified_by**: "meta / awaken-agent served-prompt session"
- **update_trigger**: "when tech stack, the tool/endpoint surface, the data model, deploy topology, or known debts change"
- **notes**: "Full project 7Q README for Munnin — two-adapters-over-one-core architecture, full MCP+HTTP surface, uniform-record data model, RackNerd deploy, ADR-012/013, and the awaken process-instruction gap. Generated 2026-08-13 from code. 2026-08-15: Served Content section now describes the **two-stage** delivery (component inlining then seam substitution); the closed no-remote debt (D3) retired from Debts, CI/CD, and Rollback; recorded that control-files runs its own CI so this repo's testpaths stays scoped to tests/. 2026-08-17: the HTTP API table + the paragraph under it now state the served-content response split — the two list endpoints answer JSON, a single prompt or template answers raw `text/markdown`."

### `docs/flows/awaken-db.md`

- **type**: flow-diagram
- **scope**: shared
- **roles**: []
- **status**: useful
- **tags**: [flow, awaken, db-payload, 4-layer, process-gap, doc_type-flow]
- **last_verified**: "2026-08-13"
- **verified_by**: "meta / generate-flow-docs session"
- **update_trigger**: "when the awaken payload/assembly changes, or when the awakening process-instruction gap is resolved (e.g. awaken-agent served as a Prompt)"
- **notes**: "The DB-world awaken flow (MCP tool / HTTP /api/awaken → MemoryService.awaken → repo → payload). Traces the 4-layer assembly and flags that the awakening PROCESS (Phase 1/2, sub-agent rule, report format) is not in the payload and not served — the gap under review with software-architect."

### `deploy/README.md`

- **type**: other
- **scope**: shared
- **roles**: []
- **status**: unverified
- **tags**: [deploy, systemd, uv, racknerd, ssh-tunnel]
- **last_verified**: ""
- **verified_by**: ""
- **update_trigger**: "when the deploy topology (host, systemd unit, scripts, tunnel) or the deploy/ file set changes"
- **notes**: "Deployment guide — systemd + uv, no Docker; loopback 127.0.0.1:8200 + SSH tunnel; MemoryMax=200M. Lists the deploy/ file set (munnin.service, deploy.sh, restart.sh, *.env.example, mcp.json.example)."

### `qa/runbooks/munnin.md`

- **type**: other
- **scope**: shared
- **roles**: []
- **status**: unverified
- **tags**: [qa, runbook, awaken, served-content, http-face]
- **last_verified**: "2026-08-21"
- **verified_by**: "meta / awaken-agent served-prompt session"
- **update_trigger**: "when the QA flow or the qa/ instrument changes"
- **notes**: "QA runbook — bring Munnin up on a clean seeded DB, then verify the data read path (awaken) and the served content surface (prompts/resources) over the live HTTP face. Single-app project — carries the whole QA story (qa/checklists, qa/fixtures, qa/config are instrument-internal scaffolding, not indexed)."

### `control-files/` (submodule)

- **type**: orientation-map-link
- **scope**: shared
- **roles**: []
- **status**: useful
- **child_map**: ../control-files/docs/orientation-map.md
- **tags**: [submodule, framework, memory-core, muninn, served-content, public]
- **last_verified**: "2026-08-13"
- **verified_by**: "meta / map-orientation create"
- **update_trigger**: "when the control-files submodule gains/loses orientation docs"
- **notes**: "Public agent-memory-system framework (the memory core / Muninn) — git submodule at control-files/. Supplies the served content/ (memory procedures → MCP Prompts, templates → Resources). Has its own orientation map (linked). Load when working on the served procedures/templates or the storage-backend seam."

---

## How to Use This File

**Agents at awakening**: Loaded into session context by `/map-orientation` (bare call) when working in this repo. Reference entries by `path`. Single-role project → all entries load (filter is a no-op). For the `control-files/` `orientation-map-link`: also load its child map when working on served content.

**Agents at wrap-up**: If your session touched any indexed doc, `/map-orientation --session-touched [paths]` refreshes its `last_verified` + status. If you DISCOVERED an entry's status is wrong, fix it directly via `/update-project-context`.

**Scope**: this map covers `agent-memory-server` only. The `control-files/` entry links the framework submodule's own map; nothing here references or depends on any parent map.
