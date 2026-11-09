# QA Scripts Map — agent-memory-server

> Navigation audit; last scan 2026-11-09. Materials stay in place. Prior Notes are copied verbatim and describe the earlier scan, not a new runtime claim.

**Category status**: exists-documented
**Owner**: /build-qa-bench

## Found

| Material | Location | Grade | Notes (prior annotations retained verbatim where present) |
|---|---|---|---|
| qa/scripts/reset-db.sh | [reset-db.sh](reset-db.sh) | exists-documented | Linked from the `qa/README.md` R/I/A/O table 2026-08-21; verified running |
| qa/scripts/seed-meta.sh | [seed-meta.sh](seed-meta.sh) | exists-documented | Linked and verified running |
| qa/scripts/smoke-check.sh | [smoke-check.sh](smoke-check.sh) | exists-documented | Linked and verified running |
| qa/scripts/start-server.sh | [start-server.sh](start-server.sh) | exists-documented | Linked and verified running |
| qa/scripts/stop-server.sh | [stop-server.sh](stop-server.sh) | exists-documented | Paired with start-server; linked and verified |
| src/munnin/data_migrations/exporter.py | [../../src/munnin/data_migrations/exporter.py](../../src/munnin/data_migrations/exporter.py) | exists-tribal |  |
| src/munnin/data_migrations/importer.py | [../../src/munnin/data_migrations/importer.py](../../src/munnin/data_migrations/importer.py) | exists-tribal |  |
| src/munnin/data_migrations/sqlite_to_postgres.py | [../../src/munnin/data_migrations/sqlite_to_postgres.py](../../src/munnin/data_migrations/sqlite_to_postgres.py) | exists-tribal |  |

## Gaps

No new material built by this audit. Discovery/link resolution is not runtime verification. The four bench phases remain linked and documented.
