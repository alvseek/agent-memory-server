# Permanent layer projection — QA Checklist

**Source**: `plans/2026-11-08-munnin-deploy-permanent-layer-projection.md` (agent-memory-server `5ca2394` plus `100ba7b`, agent-memory-system `d328b4c`)
**Purpose**: confirm the always-on block is derived per tenant from the reasoning lane, that nothing is omitted silently, and that no deployment-wide reasoning reaches a client.
**Apps under test**: `agent-memory-server` (the `permanent_layer` MCP tool, `MemoryService`, the content loader) and `agent-memory-system` (the core-memory starter file, the reasoning template, `add-reasoning`, `anchor-memory`). Deliberately **not** touched: the `awaken` payload, the HTTP API surface, the store schema, the RAS records.

## Terminology & state model (read first)

- **The block** is what `permanent_layer()` returns: the tenant's RAS triggers, then one entry per reasoning record, each as `### {stored title}` and the rule's capsule under it.
- **The capsule** is the text after `**Final Conclusion**:` in a reasoning record's body, collapsed to one line.
- **`skipped`** lists the rules left out for carrying no capsule. `None declared` is the template's opt-out and is not reported.

**Key invariants** (each is a thing to *disprove*):

- A block never contains reasoning from another tenant.
- No rule is missing from the block without appearing in `skipped`, except one that declares `None declared`.
- The block never reads the content tree, so deleting or editing `control-files/core-memory/3-core-reasoning-memory.md` cannot change it.

## Happy path — single end-to-end scenario (run this first)

1. Wake as any agent on this tenant and call `permanent_layer`. Expect the RAS entries first, then one entry per reasoning record, `skipped: []`. → **Section A**
2. Run `/anchor-memory`. Expect the local file's body hash to equal the served `hash`. → **Section D**
3. Edit one rule's capsule, then call the tool again. Expect the block text to change and `version` to move to today. → **Section B**
4. Compile the markdown path and read the compiled file. Expect the worked example and none of your rules. → **Section E**

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| The block is RAS first, then title-plus-capsule entries | `tests/business_services/test_permanent_layer.py::test_block_is_the_ras_triggers_then_title_and_conclusion` | — |
| A rule with no capsule is absent and named in `skipped` | `…::test_a_rule_without_a_conclusion_is_skipped_and_named` | the same behaviour through the MCP face: `test_content_tools.py::test_permanent_layer_projects_the_store_per_tenant` |
| `None declared` is excluded and not reported | `…::test_none_declared_is_excluded_without_being_reported` | — |
| Entries follow creation order, not insertion order | `…::test_entries_are_ordered_by_creation_not_insertion` | — |
| `version` is the newest included `modified_date` | `…::test_version_is_the_newest_modified_date_the_block_includes` | that an edit through `edit` moves it (Section B) |
| An empty store answers empty rather than raising | `…::test_an_empty_store_answers_empty_rather_than_raising` | — |
| The MCP face returns `skipped` and a twelve-character hash | `test_content_tools.py::test_permanent_layer_projects_the_store_per_tenant` | — |
| The compile folds the starter and strips the guidance comment | `control-files` suite, `41 passed` | reading the compiled output (Section E) |

## Checks

### A. The block's content

- [ ] `permanent_layer()` begins with the RAS triggers, in store order, before any rule.
- [ ] Every reasoning record with a capsule appears exactly once, under its stored title, verbatim including emoji.
- [ ] A record typed `coding_reasoning` never appears in the block, even though its capsule exists.
- [ ] A record with `archived_date` or `deleted_date` set is absent.
- [ ] With one rule deliberately stripped of its capsule, the call still answers, that rule is absent, and `skipped` names its title.
- [ ] With one rule carrying `None declared`, it is absent and `skipped` stays empty.

### B. Version and hash

- [ ] `version` is a date matching the newest `modified_date` among included records, not the old authored stamp `2026-11-07`.
- [ ] Editing any included rule through `edit` changes `version` to today and changes `hash`.
- [ ] `hash` is twelve lowercase hex characters and equals the first twelve of `sha256(content)`.
- [ ] Editing a rule *without* changing its capsule (e.g. its `Why`) still changes `hash`, because the block text is unchanged but the record's date moved. Confirm the expected direction: the hash must stay the same if the block text is identical. (If it moved, the projection is reading more than the capsule.)

### C. Tenant isolation

- [ ] A second tenant holding its own reasoning record gets a block without this tenant's rules. Provision it on the bench, not on the live store.
- [ ] The same tenant, opened by a guest with access, gets the owner's block, since the block belongs to the account.

### D. Anchoring

- [ ] `/anchor-memory` writes the file with the stamp line, one LF, then the body, and the body's SHA-256 prefix equals the served `hash`.
- [ ] The pointer appears exactly once in the harness's instruction file after a second run.
- [ ] The anchor report names anything in `skipped`, and says the block is complete when the list is empty.
- [ ] A stale local file (edit one character) is detected by the hash comparison on the next anchor.

### E. The markdown path

- [ ] `compile.sh` output contains the worked example and none of the tenant's rules.
- [ ] The guidance comment is stripped from the compiled output and remains readable in the source file.
- [ ] A reasoning insert declaring the old template stamp `2026-09-21-14-53` is refused; the new stamp `2026-11-08-00-30` is accepted.
- [ ] `read_procedure("anchor-memory")` and `read_resource("reasoning-pattern-template")` serve the updated text.

### F. Client surface

- [ ] A **freshly connected** client sees a `permanent_layer` description naming the per-tenant derivation and `skipped`. An already-connected client keeps the old text until it reconnects, which is the catalogue cache, not a failed deploy.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
