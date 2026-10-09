# Postgres Cutover Runbook — serverhost-1

High-wizard Phase 5. Moves Valaskjalf from SQLite to PostgreSQL on the live box in a cold
window, with the SQLite file kept untouched as the rollback. One writer and near-zero
concurrency make the window seconds.

## Facts

- **Box**: `serverhost-1` (`198.44.26.137`), `ssh munnin-vps` (user `agent`, in the docker group).
- **Munnin**: Kamal-managed container `munnin-web-<tag>`, image `ghcr.io/alvseek/munnin:<tag>`,
  volume `munnin-data:/app/data`, SQLite at `/app/data/valaskjalf-memory.db`.
- **Postgres**: container `munnin-postgres` on the `kamal` network, database `munnin`, PG 17.11,
  volume `munnin-pgdata`. DSN lives in `/home/agent/munnin-postgres/dsn.txt` (the munnin
  container resolves `munnin-postgres` on the shared `kamal` network).
- **Deploy**: `munnin-deploy` workflow_dispatch `deploy.yml` (`version=<short-sha>`,
  `command=deploy`). The image is built by the product repo's `build-image.yml` on push to `main`.
- **Migration tool**: `python -m munnin.data_migrations.sqlite_to_postgres --sqlite <path> --dsn <dsn>`
  (refuses a non-empty target; verifies per-table/per-tenant counts and the `(iss, sub)` mapping).

## Preconditions

- [x] Image for the target commit published — Build image run for `1ac96e3` succeeded.
- [x] Postgres reachable, DB `munnin` fresh.
- [x] Off-box R2 backup proven (agent-infra).
- [ ] **The box can pull the image** — `ghcr.io/alvseek/munnin` is a **private** package and the
      box is not logged in, so `docker run` is denied. Resolve before executing (options below).

## Image-pull options

- **A. Make the package public** — `gh api -X PATCH /user/packages/container/munnin -f visibility=public`.
  Simplest; the product source and `control-files` are already public. Changes package visibility.
- **B. Log the box into ghcr** with a token carrying `read:packages`. Adds a credential on the box.
- **C. Deploy-first-to-pull (recommended).** Run `deploy.yml version=1ac96e3 command=deploy` while
  the backend is still SQLite (the new code defaults to `sqlite`, so behaviour is unchanged); Kamal
  logs in and pulls the image. Then migrate with the now-local image, then deploy again with the
  Postgres env. No visibility change, no new long-lived token.

## Steps

1. **Pre-migrate (dry run)** — with the image present, migrate the box snapshot into Postgres and
   verify. Reset the schema afterwards so the real cutover starts clean.
2. **Freeze** — `kamal app stop` (or `docker stop munnin-web-<tag>`) so the store stops changing.
3. **Snapshot** — `VACUUM INTO` the SQLite file into `/home/agent/munnin-backups/`.
4. **Reset the target** (if the dry run left rows) — `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`.
5. **Migrate** — run the tool against the frozen snapshot; require a green verification.
6. **Cut over** — set `MUNNIN_DB_BACKEND=postgres` and `MUNNIN_DB_URL` (as a Kamal secret) in
   `munnin-deploy`, then `deploy.yml version=1ac96e3 command=deploy`.
7. **Smoke test** — `curl https://munnin.lok.quest/health`; an authenticated `awaken`; a `search`.
8. **Rollback (if needed)** — set `MUNNIN_DB_BACKEND=sqlite` and redeploy; the SQLite file is intact.

## Rollback

One config value. The cutover never deletes the SQLite file, so the rollback is a redeploy with
`MUNNIN_DB_BACKEND=sqlite`.

## Sources

Session 2026-10-09 (software-architect), high-wizard Phase 5.
