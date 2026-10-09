# QA Checklist — Postgres Migration

Feature: Munnin's store moved from SQLite to PostgreSQL (high-wizard plan
`plans/completed/2026-10-09-munnin-deploy-postgres-migration.md`). Cut over live on
`serverhost-1` on 2026-10-09.

## Automated (CI, `-m postgres`)

- [x] Schema + migration runner: the five tables, the generated `search_tsv` column, the GIN indexes; idempotent re-run.
- [x] Repository contract on **both** engines (the parametrized `memory_repo` fixture).
- [x] Identity repository: idempotent account creation, `(iss, sub)` mapping, FK refusal on a missing account.
- [x] Migration tool: copies all five tables preserving `id`; refuses a non-empty target; verification fails on a dropped row.
- [x] Search parity: set-equality between FTS5 and Postgres over a synthetic token corpus (hyphens, underscores).
- [x] Backend selection: config + factory + `build_app` boot on the postgres backend.

## Manual (stack up)

- [ ] An authenticated `awaken` returns the full payload from Postgres. *(Verified live 2026-10-09: identity `48b8245b`, 17 knowledge, 16 episodes, 32 shared reasoning.)*
- [ ] A `search` over the fixture's 20 real queries returns the expected records against the migrated store.
- [ ] Tenant isolation: a second account sees only its own memory.
- [ ] Writes land in Postgres and survive a container restart.
- [ ] The rollback (backend `sqlite` + redeploy) serves from the SQLite file. *(Verified live 2026-10-09.)*
