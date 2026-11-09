# QA Fixtures Map — agent-memory-server

> Navigation audit; last scan 2026-11-09. Materials stay in place. Prior Notes are copied verbatim and describe the earlier scan, not a new runtime claim.

**Category status**: exists-documented
**Owner**: /integration-test

## Found

| Material | Location | Grade | Notes (prior annotations retained verbatim where present) |
|---|---|---|---|
| qa/fixtures/README.md | [README.md](README.md) | exists-documented | Header convention + the fidelity rule. As of today one fixture exists that follows them |
| qa/fixtures/postgres-search-parity.md | [postgres-search-parity.md](postgres-search-parity.md) | exists-documented |  |
| qa/fixtures/profile-source.sh | [profile-source.sh](profile-source.sh) | exists-documented | Built 2026-08-21 by /build-qa-test. Four modes (`present`/`absent`/`markerless`/`blank-vision`) assembling a throwaway import source root; composes with `seed-meta.sh` via `MUNNIN_IMPORT_SOURCE`. Chain-run, fidelity-checked against the real authoring script, teardown-clean. The category's first real fixture |
| tests/api_http/test_awaken_faces.py | [../../tests/api_http/test_awaken_faces.py](../../tests/api_http/test_awaken_faces.py) | exists-tribal | Same shape: reusable end-state builders that only one module can reach. Unchanged |
| tests/api_http/test_record_prefix_faces.py | [../../tests/api_http/test_record_prefix_faces.py](../../tests/api_http/test_record_prefix_faces.py) | exists-documented | Prefix addressing contract; temporary real-engine data, no extra upstream fixture. Linked from QA README/root map. |
| tests/business_services/test_awaken.py | [../../tests/business_services/test_awaken.py](../../tests/business_services/test_awaken.py) | exists-tribal | Same shape: reusable end-state builders that only one module can reach. Unchanged |
| tests/business_services/test_record_prefix_integration.py | [../../tests/business_services/test_record_prefix_integration.py](../../tests/business_services/test_record_prefix_integration.py) | exists-documented | Prefix addressing contract; temporary real-engine data, no extra upstream fixture. Linked from QA README/root map. |
| tests/conftest.py | [../../tests/conftest.py](../../tests/conftest.py) | exists-tribal |  |
| tests/data_entities/test_schema.py | [../../tests/data_entities/test_schema.py](../../tests/data_entities/test_schema.py) | exists-tribal | Applies the DDL and seeds one agent so FK-bearing inserts are legal. Unchanged |
| tests/data_migrations/test_importer.py | [../../tests/data_migrations/test_importer.py](../../tests/data_migrations/test_importer.py) | exists-tribal | Builds a complete markdown store — agents, episodes, knowledge index, shared layer. A genuine precondition-builder **inlined in a test suite**, the tribal home this category exists to surface. Unchanged |
| tests/data_repositories/test_record_prefix.py | [../../tests/data_repositories/test_record_prefix.py](../../tests/data_repositories/test_record_prefix.py) | exists-documented | Prefix addressing contract; temporary real-engine data, no extra upstream fixture. Linked from QA README/root map. |

## Gaps

Prefix preconditions are cheap real-entry-point inserts, not synthetic upstream output. Existing inlined import/awakening builders remain; this change does not extract them. No new PENDING fidelity fixture. PostgreSQL coverage runs in CI; production OAuth and UI are separate.
