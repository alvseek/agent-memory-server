# QA Instrument Map — agent-memory-server (Munnin)

> Navigation audit; last scan 2026-11-09. Whole-project scan includes tracked/untracked files and the control-files content submodule. Maps link existing material; this refresh builds no bench scripts or fixtures.

## R/I/A/O loop maturity

| Phase | Grade | Backed by |
|---|---|---|
| RESET | exists-documented | [scripts/reset-db.sh](scripts/reset-db.sh) |
| INJECT | exists-documented | [scripts/seed-meta.sh](scripts/seed-meta.sh) |
| ACT | exists-documented | [scripts/start-server.sh](scripts/start-server.sh) · [scripts/stop-server.sh](scripts/stop-server.sh) |
| OBSERVE | exists-documented | [scripts/smoke-check.sh](scripts/smoke-check.sh) |

## Index integrity — qa/README.md R/I/A/O table

All four phase rows resolve to existing mechanisms and agree with the scripts' actual roles. RESET/INJECT/ACT were inspected, not executed against the dev store. OBSERVE was run read-only on 2026-11-09: SMOKE OK. This proves existing stack liveness, not the new feature.

## Category maps

| Category | Owner | Map |
|---|---|---|
| Runbooks | /build-qa-bench | [runbooks/qa-runbooks-map.md](runbooks/qa-runbooks-map.md) |
| Playbook | /build-qa-bench | [qa-playbook-map.md](qa-playbook-map.md) |
| Checklists | /generate-qa-checklist | [checklists/qa-checklists-map.md](checklists/qa-checklists-map.md) |
| Fixtures | /integration-test | [fixtures/qa-fixtures-map.md](fixtures/qa-fixtures-map.md) |
| Config | /build-qa-bench | [config/qa-config-map.md](config/qa-config-map.md) |
| Scripts | /build-qa-bench | [scripts/qa-scripts-map.md](scripts/qa-scripts-map.md) |
| Seeds | /build-qa-bench | [seeds/qa-seeds-map.md](seeds/qa-seeds-map.md) |

## Prefix addressing coverage

- [Repository contract](../tests/data_repositories/test_record_prefix.py): both real engines via memory_repo; PostgreSQL needs the CI service.
- [Service integration](../tests/business_services/test_record_prefix_integration.py): real-entry-point preconditions, red under an in-process resolution mutation, green after restoration and on a fresh run.
- [HTTP/MCP contracts](../tests/api_http/test_record_prefix_faces.py): in-process adapters over real SQLite; not deployed-system proof.
- [Feature checklist](checklists/short-uuid.md): written, not walked; real OAuth/Helheim and concurrency scenarios stay separate.

## Verdict

The bench remains wired and documented. The rescan makes current fixtures, tests and checklists discoverable while retaining prior material annotations. No live-store reset occurred. No new fidelity-pending fixture was introduced. PostgreSQL execution, deployed-system behavior and UI verification must be reported from their own evidence.
