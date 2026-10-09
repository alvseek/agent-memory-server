# ADR-001: PostgreSQL Store for Valaskjalf

**Date**: 2026-10-09

**Status**: Accepted

---

## Problem

Munnin's store (Valaskjalf) runs on SQLite: a single file in WAL mode, one writer, enforced by a single uvicorn worker. That is fine for a demo, but the store now holds important data used daily, and two things force a change. First, the writer: any move to more than one worker or instance, or Hermod as a second writer, is blocked by SQLite's single-writer-per-file model. Second, schema evolution: the current foreign-key chain works only because the deployed volume is deleted and recreated on change, because SQLite cannot `ALTER` in a constraint; that trick stops being available the moment the store holds data that cannot be lost.

---

## Decision

**We decided to**: Move the deployed store to PostgreSQL as a **dual-backend** design behind the existing `MemoryRepository` seam, keeping SQLite for tests and local use.

A `PostgresMemoryRepository` implements the existing `MemoryRepository` Protocol, and the concrete `IdentityRepository` becomes a Protocol with a Postgres implementation. A separate `PostgresMigrationRunner` applies a Postgres schema (a generated `tsvector` column with a GIN index replaces FTS5). The cutover is a cold window with a verified SQLite-to-Postgres data migration, and the SQLite file is retained as the rollback. The offline tooling (markdown importer/exporter, `migrate.py`) stays SQLite-only.

**Why we chose this:**
- The seam already exists, so the change is bounded and reversible rather than a rewrite.
- SQLite still earns its place: a fast, service-free path for tests and local development.
- Postgres is the engine the next step (Hermod, and any multi-writer or multi-instance future) requires.

---

## What to Build (Requirements)

Implement the Postgres backend behind the seam, a verified data migration, and the cutover, without losing a record and without changing anything above the repository.

**Core Requirements:**
- `PostgresMemoryRepository` implementing the full `MemoryRepository` Protocol.
- `IdentityRepository` Protocol + `PostgresIdentityRepository`.
- `PostgresMigrationRunner` + `migrations_postgres/` (seeded by `0001_init.sql`).
- Config `MUNNIN_DB_BACKEND` (default `sqlite`) and `MUNNIN_DB_URL`; wiring in `ServiceFactory` and `app.py`.
- A one-shot, verified SQLite-to-Postgres data-migration tool preserving `id` and date strings.
- Dual-backend tests: the full SQLite suite plus a Postgres-marked subset in CI.

**Success Criteria:**
- The Postgres repository passes the same behavioural tests as SQLite.
- The migration copies all five tables and a verification asserts per-table and per-tenant counts plus the `(iss, sub)` mapping.
- Search parity is verified against a fixture of real queries before cutover.

---

## Alternatives Rejected

- **Replace SQLite entirely**: loses the fast, service-free local/test path that the dual-backend choice exists to keep.
- **Postgres via an ORM (SQLAlchemy/Alembic)**: a rewrite of a working data layer for portability the project does not need.
- **SQL-level streaming (pgloader)**: bypasses the schema's constraints and is hard to verify per tenant, which is the property that must not be got wrong.
- **Managed Postgres (Neon)**: metered egress penalises large read payloads, the free tier is not a backup story, and it reverses the self-hosting posture Authentra established.

---

**Full context**: [High Wizard plan (2026-10-09)](../../../plans/2026-10-09-munnin-deploy-postgres-migration.md)

---

**ADR Template for Architecture Decision Records**

*This document serves as a SPECIFICATION that tells implementation agents WHAT to build. The implementation protocol (High Wizard/Quick Wizard) will figure out HOW to build it.*
