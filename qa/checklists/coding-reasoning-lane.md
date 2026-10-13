# Coding-Reasoning Lane — QA Checklist

**Source**: [High Wizard plan 2026-10-13 agent-memory-project coding-reasoning-lane](../../../hermod-deploy/hermod-server/agent-memory-project/plans/2026-10-13-agent-memory-project-coding-reasoning-lane.md) (ADR-028)
**Purpose**: Confirm the coding-reasoning lane exists in the store, is reachable by a coding awakening, and is **never** carried into a chat agent's `awaken` payload — including on a store that already held data before the migration.
**Apps under test**: Munnin (`agent-memory-server`: store type + schema, importer, read tool, both faces) and Hermod (`agent-memory-project`: `/add-coding-reasoning`, `§ load-coding-reasoning`). Deliberately **not** touched: the universal reasoning set, `awaken`'s output shape, the deployed store (the deploy path owns that migration).

## Terminology & state model (read first)

The lane is a `shared_record` row with `record_type = coding_reasoning` and `project = NULL`. There are two reasonings corpora and the boundary between them is the **type**:

- `reasoning` is the universal set. `awaken` loads it for every agent, chat agents included.
- `coding_reasoning` is the lane. `awaken` never selects it; only the `coding_reasoning()` read does.

**Key invariants** (each is a thing to *disprove*):
- A chat agent's `awaken` payload contains **zero** `coding_reasoning` uuids, even when the lane holds rows. The filter is `record_type is RecordType.reasoning`, not a project or a flag.
- The lane survives a re-import with the same uuids (no duplicates), because the uuid varies by record type.
- The SQLite `0004` rebuild carries **every** existing shared row and its `content_summary`, and rebuilds `shared_fts`.
- The corpus-boundary predicate `(record_type <> 'knowledge' OR project IS NULL)` does **not** hide the lane: it is not `knowledge`, so the lane's read sees it.

## Happy path — single end-to-end scenario (run this first)

1. On a store with data, apply migrations (SQLite `0004` / Postgres `0003`) and confirm every prior shared row plus its `content_summary` survived. → Checks 1, 2
2. Import the real `coding-reasoning-memory.md`; confirm the lane row count equals the file's pattern count. → Check 3
3. Call the coding read; confirm it returns the whole lane. Then call `awaken("meta")` and confirm zero lane uuids appear. → Checks 4, 5
4. Write a pattern through `/add-coding-reasoning`; confirm a `coding_reasoning` shared row lands and a chat `awaken` still excludes it. → Checks 6, 7
5. Re-import; confirm the lane row count is unchanged (idempotent). → Check 8

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| The enum and the SQL `CHECK` agree, and both admit `coding_reasoning` | `tests/data_entities/test_schema.py::test_the_declared_shared_types_match_the_schema_check`, `::test_shared_accepts_its_five_record_types[coding_reasoning]` | — |
| The `0004` rebuild preserves `content_summary` | `tests/data_entities/test_migrations.py::test_the_coding_reasoning_migration_preserves_content_summary` | Rows + `shared_fts` on a real pre-existing store (Check 1) |
| An existing DB picks up the new migrations | `tests/data_entities/test_migrations.py::test_an_existing_base_schema_gets_the_ras_migration` | The **Postgres** constraint swap on a real Postgres (Check 2) |
| A shared `coding_reasoning` insert is accepted | `tests/business_services/test_write_ops.py::test_insert_shared_scope_accepts_the_coding_reasoning_lane` | — |
| A chat `awaken` excludes the lane | `tests/business_services/test_write_ops.py::test_the_coding_lane_is_readable_but_absent_from_a_chat_awakening` | — |
| The lane imports from the real file and stays out of `awaken` | `tests/test_fidelity.py::test_the_coding_lane_imports_and_stays_out_of_a_chat_awakening` | — |
| The lane parser shares the pattern shape | `tests/data_migrations/test_markdown_parser.py::test_parse_coding_reasoning_shares_the_pattern_shape` | — |
| The tool/route/annotation registries count the new surface | `tests/test_twin_parity.py`, `tests/api_mcp/test_tool_annotations.py`, `tests/api_http/test_route_coverage.py` | — |
| Hermod compiles the new procedure for both backends | Hermod `tests/test_compile_procedures.py` (52 passed) | `/add-coding-reasoning` run by a live client (Check 6) |

## Checks

- [ ] Apply migrations on a **populated** store (SQLite and, separately, Postgres); assert the shared row count is unchanged, `content_summary` values are intact, and `shared_fts` answers a search that matched before. Expected: no row lost, no value nulled.
- [ ] On the deployed Postgres, run `0003`: `DROP CONSTRAINT shared_record_record_type_check` then `ADD`. Expected: succeeds; inserting a `coding_reasoning` row then succeeds; an `episode` into `shared_record` still fails the CHECK.
- [ ] Import `coding-reasoning-memory.md` (12 patterns at the time of writing). Expected: `shared/coding_reasoning == 12`, matching the file's level-3 pattern count.
- [ ] Call `coding_reasoning()`. Expected: the whole lane, each item carrying `uuid`, `title`, `content`.
- [ ] Call `awaken("<a chat agent>")` with the lane populated. Expected: `shared.reasoning` is unchanged, and no lane uuid appears anywhere in the payload. **This is the invariant; if it fails, the change is wrong, not the test.**
- [ ] Run `/add-coding-reasoning` end to end with a live client: draft a pattern, persist it. Expected: a `coding_reasoning` shared row appears, and a subsequent `awaken` still excludes it. A missing or stale `template_version` must be refused.
- [ ] Call the read when the lane is empty, and when `coding-reasoning-memory.md` is absent at import. Expected: an empty list and a clean skip; the store remains valid.
- [ ] Re-import over an existing lane. Expected: the same uuids, the same row count, no duplicates.
- [ ] `/awaken-coder` in a coding session loads the lane; the same session's core `awaken` does not. Expected: the coding layer is present for the coding path only.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
