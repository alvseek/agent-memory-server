# edit_metadata & the content_summary removal — QA Checklist

**Source**: Quick Wizard session 2026-10-14 (`agent-memory-server` `fd827ec` + `7a93abf` + `eccd16a`, deployed as `munnin-web-eccd16a`)
**Purpose**: confirm a record's metadata can be changed without its body, that every field has exactly one writer, and that nothing which read the old shape broke.
**Apps under test**: Munnin (store seam, service, MCP face, HTTP face) and the served storage mechanics. **Not touched**: Hermod's store (it writes the same tables through its own repository, so a Hermod-side metadata op is future work), the markdown backend's mechanics, and the importer.

## Terminology & state model (read first)

- **metadata** = `title`, `tags`, `project`, `content_summary`. **body** = `full_content`. They are now written by different ops.
- **`clearing`** = the only way to unset a field. Omitted means untouched; a blank string is refused, because `project IS NULL` (not `= ''`) is what decides which corpus a row belongs to.
- **Two writers, one field**: `edit` and its siblings write the body; `edit_metadata` writes the metadata. `content_summary` is metadata-only now.

**Key invariants** (each is a thing to *disprove*):
- A metadata write never alters `full_content`, and a body write never alters metadata.
- A field not named in a call keeps its stored value.
- Clearing writes SQL NULL, and a cleared `project` returns the row to Munnin's own knowledge reads.
- Nothing revives an archived or tombstoned row: `archive`/`soft_delete` remain the only lifecycle writers.

## Happy path — single end-to-end scenario (run this first)

1. Create a throwaway agent and insert a `knowledge` record with `title`, `tags`, `project` and `content_summary` set (use the agent's own domain, and the real `knowledge-file-template` stamp if the box is serving content).
2. `edit_metadata(uuid, content_summary="second")` → 200. Read it back: summary moved, body byte-identical, `title`/`tags`/`project` untouched. *(§A)*
3. `edit_metadata(uuid, clearing=["project"], tags=[])` → 200. `project` is now null, `tags` is `[]`, the summary still stands. *(§B)*
4. Confirm the row is back inside Munnin's own knowledge reads, and that a cleared project did **not** leave an empty-string column. *(§B, §C)*
5. `edit(uuid, old_string=…, new_string=…)` → 200. Body changes; all four metadata fields are exactly as step 3 left them. *(§D)*
6. Change `title` to a unique token, then `search(token)` → the record is found, on SQLite and on the live Postgres box. *(§C)*
7. Sweep the served text and the tool list for the old contract. *(§F)*

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Metadata writes leave the body alone; omitted fields keep their values | `test_set_fields_touches_only_the_fields_it_is_given` (both engines), `test_edit_metadata_changes_a_field_without_the_body` | The live box's own rows (§A) |
| Clearing writes NULL; `tags=[]` empties; a field in both value and `clearing` is refused | `test_set_fields_clears_to_null_empties_tags_and_refuses_an_empty_change` (both engines), `test_edit_metadata_clears_and_empties` | That the corpus reads act on it against the live store (§B) |
| A shared-table record is reachable too | `test_set_fields_reaches_a_shared_record` | — |
| A changed `title`/`tags` is findable without extra work | `test_set_fields_reindexes_a_changed_title` (SQLite trigger + Postgres generated column) | Search on the live box (§C) |
| Blank values refused; nothing-to-change refused; missing record is `LookupError` | `test_edit_metadata_refuses_blank_values_and_empty_changes`, `test_insert_with_a_blank_summary_is_refused`, `test_insert_without_a_summary_for_an_index_type_is_refused` | — |
| A body edit leaves the summary alone (two calls, by design) | `test_a_rolling_record_moves_its_summary_in_a_second_call` | An agent actually following both steps (§E) |
| Both faces carry the op, with the same refusals and status codes | `test_edit_metadata_omits_clears_and_empties` (MCP), `test_edit_metadata_over_the_http_face` | The live box, which needs a token (§D) |
| Tenant isolation on the new write route | `test_bob_cannot_touch_alices_record_by_uuid[/api/edit-metadata]` | — |
| An unknown field in a write body is refused, not dropped | `test_a_write_body_refuses_a_field_it_does_not_take` | The MCP face, which cannot refuse it (§F) |
| Surface size, titles, hints, destructive set | `test_the_surface_is_the_documented_size`, `test_the_surface_is_the_size_we_think_it_is`, `test_tool_annotations.py` (three tests) | Client-side confirmation prompts (§F) |
| The Postgres engine behaves identically | CI `postgres` job, `-m postgres` | The live box's own database (§A–§D) |

## Checks

### §A A metadata write leaves the body alone
- [ ] Insert a record with a distinctive body, then `edit_metadata` all four fields at once → the record read back has a **byte-identical** body and all four fields changed.
- [ ] `modified_date` moved; `created_date`, `archived_date` and `deleted_date` did not.
- [ ] On the live box (Postgres + the real store): the same call on a real record → body unchanged in the returned payload.

### §B Clearing, emptying, and the corpus boundary
- [ ] `clearing=["project"]` on a `knowledge` row that had one → the column is **NULL**, not `""` (read it raw, not through the API).
- [ ] The same row now appears in Munnin's own knowledge reads (`query(record_type="knowledge")` / `query_shared`), which it did not while it carried a project.
- [ ] Setting `project` again takes it back out. **Disprove**: a row that is visible in both corpora, or in neither.
- [ ] `tags=[]` empties the list and reads back as `[]`; `clearing=["tags"]` also reads back as `[]`.
- [ ] `title=""`, `project="   "`, `content_summary=""` → each refused with a message naming the field; a blank on `insert` → refused for **every** record type, with `content_summary is required` still the message for a *missing* one on episode/knowledge.

### §C Index and search
- [ ] Change `title` to a one-off token, then `search(token)` finds the record — on SQLite and on the live box.
- [ ] Change `tags` to a one-off token, then `search(token)` finds it.
- [ ] `content_summary` and `project` changes do **not** need to be searchable (they are not indexed) — confirm a summary-only change still leaves search results for the old title intact.

### §D One owner per field
- [ ] `edit`, `append`, `prepend` and `multi_edit` on a record with a summary → the summary is unchanged afterwards in every case.
- [ ] MCP `edit` called **with** a `content_summary` argument → call succeeds (the transport ignores undeclared arguments) and the summary is **unchanged**. This is the documented tolerance, not a bug: it is why the served text moved in the same change.
- [ ] HTTP `POST /api/edit` with `content_summary` in the body → **422**, and the summary is unchanged.
- [ ] HTTP `POST /api/edit-metadata` with a misspelled field → 422.

### §E The append flow the served text now describes
- [ ] On a scratch episode: `prepend` a new H3 block with `\n\n---\n\n`, then `edit_metadata(content_summary=…)` → the body is newest-first with exactly one separator between blocks, and the summary describes the new top block.
- [ ] Skip the second call → the summary still describes the previous block (the documented cost of two writes); it is visible on the next read and recoverable by doing step 2 then.
- [ ] A real agent session running `/update-episodic` against this store performs both steps. *(No test drives an agent.)*

### §F Surface, text, and lifecycle
- [ ] `tools/list` → 22 tools, every one titled with a hint, and the destructive set exactly `{edit, edit_metadata, multi_edit, archive, soft_delete}`.
- [ ] A client prompts for confirmation on `edit_metadata` (record client + version; clients differ).
- [ ] No served procedure still sends `content_summary` to `edit`; the composed `update-episodic` shows `prepend(` and `edit_metadata(`.
- [ ] `archive(uuid)` then `edit_metadata` → works (archived rows stay addressable, as they do for `edit`/`append`); `soft_delete(uuid)` then `edit_metadata` → `record not found`. **Disprove**: a metadata write reviving a tombstoned or archived record, or clearing a lifecycle date.
- [ ] The migration/DDL surface is untouched: no new migration, and `python -m munnin.migrate status` reports nothing pending on the live box.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
