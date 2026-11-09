# QA Seeds Map — agent-memory-server

> Navigation audit; last scan 2026-11-09. Materials stay in place. Prior Notes are copied verbatim and describe the earlier scan, not a new runtime claim.

**Category status**: exists-tribal
**Owner**: /build-qa-bench

## Found

| Material | Location | Grade | Notes (prior annotations retained verbatim where present) |
|---|---|---|---|
| The markdown memory store (the real seed source) | `[AGENT-MEMORY-PATH]` — consumed by `munnin.data_migrations.importer --all` | historical / unresolved | This is the project's actual INJECT source and it is **strategy B-shaped**: the store is authoritative and the DB is a rebuildable projection, so there is no dummy-fixture burden. Nothing under `qa/` says so |
| Point-in-time DB snapshots | [../../data/](../../data/) — five `valaskjalf-memory.db.bak-*` files | historical / unresolved | ~76 MB, unreferenced by anything, kept as pre-change rollbacks. Logged as debt by the agent-entity plan (2026-08-20) |

## Gaps

The bench imports an external markdown store via MUNNIN_IMPORT_SOURCE. External placeholder locations and old snapshots above are historical annotations, not verified seed availability or production restore advice. The SQL files under qa/repairs are historical repairs, not seeds; their existence does not make a reset/import source available.
