# Archive memories — QA Checklist

**Source**: `agent-memory-server` `2fc8792` (plus the review fix `9c1d5af`) and `agent-memory-system` `5e0890f`
**Purpose**: confirm the episodic archive scan partitions themes correctly, that `apply` writes only what carries the marker, that protection really protects, and that a mistaken archive is reversible.
**Apps under test**: `agent-memory-server` (the two MCP tools, the two routes, `MemoryService`, the rule, both repository backends) and `agent-memory-system` (`update-episodic`, `archive-old-memories`, the episode template, both storage backends). Deliberately **not** touched: the awakening payload, the store schema, the emotional curation, and the markdown archive mechanics (which stay manual).

## Terminology & state model (read first)

- **theme** is one episode record (rolling body of newest-first sub-episodes).
- **`finished`** is a tag on the record: the agent stamps it when a block closes the theme, and clears it while the theme is still live.
- **auto** = tagged `finished` and unprotected. **ask** = untagged and not modified within `days`. **protected** = newest per project, newest overall, undated.

**Key invariants** (each is a thing to *disprove*):

- No protected row ever appears in `auto` or `ask`.
- `apply` archives exactly the dry run's `auto` set, and a second apply writes nothing.
- An agent this account does not have is refused, never answered with three empty lists.
- `unarchive` returns a record to the index and refuses a soft-deleted one.
- The scan ships no bodies.
- The markdown backend never instructs a tool call, and carries the marker in frontmatter only.

## Happy path — single end-to-end scenario (run this first)

1. Close a theme in a real session so `update-episodic` stamps `finished`. Expect the record's tags to contain it and its newest block to say so. → **Section B**
2. Call `archive_memories(agent_id, apply=False)`. Expect that record in `auto`, nothing written. → **Section A**
3. Call it again with `apply=True`. Expect the uuid in `archived`, and the record gone from `episodic_index` while `search` still finds it. → **Section A**
4. Call `unarchive(uuid)`. Expect it back in the index and selectable as newest again. → **Section C**

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Tagged and superseded goes to `auto`; stale untagged goes to `ask` | `tests/business_services/test_archive_rule.py::test_tagged_and_superseded_is_auto`, `::test_untagged_and_stale_is_asked` | — |
| The newest per project, the newest overall, and every tie are protected | `::test_newest_per_project_and_overall_carry_a_reason`, `::test_every_row_tied_at_the_newest_date_is_protected` | — |
| A tagged newest row is protected, not auto | `::test_a_tagged_newest_row_is_protected_not_auto` | — |
| An undated row is protected | `::test_undated_rows_are_protected` | — |
| Mixed date shapes compare chronologically | `::test_mixed_date_shapes_compare_chronologically` | — |
| A dry run writes nothing; apply writes exactly `auto`; a second apply is a no-op | `test_archive_memories.py::test_a_dry_run_writes_nothing`, `::test_apply_archives_exactly_the_auto_set`, `::test_a_second_apply_is_a_no_op` | — |
| An unknown agent is refused | `::test_an_unknown_agent_is_refused` | the MCP and REST faces returning an error: part of the route cycle below |
| `unarchive` restores and refuses a tombstone | `::test_unarchive_returns_the_record_and_refuses_a_tombstone` | — |
| The scan ships no bodies | `::test_the_scan_reads_no_body`, `tests/data_repositories/test_repository_contract.py::test_episode_metadata_projection_carries_no_body` | — |
| The route cycle works over HTTP, with 400 and 404 paths | `tests/api_http/test_write_faces.py::test_archive_memories_scans_then_applies_then_unarchives`, `::test_archive_memories_rejects_a_bad_window`, `::test_unarchive_of_a_missing_record_is_404` | — |
| The tool's default is a dry run | `tests/api_mcp/test_write_tools.py::test_archive_memories_defaults_to_a_dry_run` | — |
| Both new routes are enumerated and token-guarded | `tests/api_http/test_route_coverage.py` | — |
| Every wired op resolves on both backends; procedures compose | `control-files` suite: `41 passed`, compile module `25 passed` | reading the composed markdown output (Section D) |

## Checks

### A. The scan and the apply on the live store

- [ ] `archive_memories(agent_id="software-architect", apply=False)` returns `auto`, `ask`, `protected` and the protected reasons name `newest of project` / `newest overall`.
- [ ] The counts reconcile: `auto + ask + protected` is at most the agent's live episode count, and the remainder are recent untagged records. Record the numbers you see.
- [ ] `archive_memories(agent_id="no-such-agent")` errors rather than returning empty lists.
- [ ] `apply=True` lists exactly the dry run's `auto` uuids.
- [ ] An archived record is absent from `episodic_index` and still returned by `search`.

### B. The marker

- [ ] After a theme closes, the record carries `finished` and the tag list still holds whatever was there before.
- [ ] While a theme is live, a resumed append leaves no `finished` tag behind.
- [ ] Reopening an archived theme clears the marker *and* unarchives, in that order; the next scan does not re-archive it.
- [ ] On the markdown backend, the marker lives in the file's frontmatter `tags:` line, not in the index line.

### C. Reversal

- [ ] `unarchive(uuid)` on an archived record returns `{uuid, status: "active"}` and the record is selectable as newest again when its date says so.
- [ ] `unarchive` on a soft-deleted record is refused (`LookupError` / 404).

### D. Content composition

- [ ] The composed `archive-old-memories.db.md` names `archive_memories`, `unarchive`, the scan, the apply, the per-record archive and the recovery.
- [ ] The composed `archive-old-memories.markdown.md` says "no tool on this backend" for both candidate ops and describes the index move instead.
- [ ] The composed `update-episodic.db.md` carries the theme-state step in both branches and the reopen note in the scan step.

### E. Surface

- [ ] `docs/README.md` states 31 tools, matching `grep -c "@mcp.tool" src/munnin/api_mcp/server.py`.
- [ ] Both tools carry `destructiveHint` and `idempotentHint`.
- [ ] Both `/api/archive-memories` and `/api/unarchive` answer 401 unauthenticated.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
