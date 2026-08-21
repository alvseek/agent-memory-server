# User Profile as Fleet Memory — QA Checklist

**Source**: [plans/2026-08-21-agent-memory-server-user-profile-record.md](../../plans/2026-08-21-agent-memory-server-user-profile-record.md)
**Purpose**: confirm an agent awakening from the database learns who the user is — and, more importantly, that nothing which already worked stopped working when a sixth record type was admitted to a shared table.
**Apps under test**: Munnin (`data_entities`, `data_migrations`, `business_services`, `api_mcp`) · `control-files` (both storage backends, the awakening component, the two configurator scripts, the profile template).
**Deliberately NOT touched**: the `user` table / Authentra auth · login and multi-tenant `user_id` · B′ activation · agent-scoped record paths · the `edit`/`append`/`archive`/`soft_delete` write ops.

## Terminology & state model (read first)

Three states look similar and behave differently. Most items below turn on telling them apart:

| State | What it means | What the agent must do |
|---|---|---|
| **No record** | `shared.user_profile` is `null` — nobody has ever been asked | **Ask once**, then store |
| **Record with a blank field** | The record exists; one value is empty because the user left it empty | **Never ask.** A deliberate blank is an answer |
| **Record present and full** | Normal steady state | Silent |

Also: the profile has **one authored home** (`[AGENT-MEMORY-PATH]/shared-memory/user-profile.md`) and **one derived copy** (`core-memory/output/0-core-user-profile.md`, gitignored). The derived copy is what `compile.sh` reads into the global instructions file. Editing the derived copy is always wrong.

**Key invariants** (each is a thing to *disprove*):
- A second `user_profile` row cannot exist for one tenant — and the constraint that prevents it must not also constrain reasoning or knowledge.
- The profile must never surface as `shared.reasoning` or `shared.knowledge`; three types now share one table and one fetch.
- A blank field must never be re-asked.
- The public repo must never contain the real values again.
- `CLAUDE.md`'s profile block must be byte-identical after the source moved.

## Happy path — single end-to-end scenario (run this first)

1. `bash qa/scripts/reset-db.sh` then `bash qa/scripts/seed-meta.sh --all` — the store rebuilds from markdown (§ *Import & store*).
2. `bash qa/scripts/start-server.sh` then `bash qa/scripts/smoke-check.sh` — expect `SMOKE OK` (§ *Payload*).
3. `curl "http://127.0.0.1:8200/api/awaken?agent_id=meta"` — inspect `shared.user_profile` (§ *Payload*).
4. Delete the profile row, awaken as a **fresh agent session**, and watch what it asks (§ *First-run bootstrap* — the part no test reaches).
5. Re-run the configurator and recompile; diff `CLAUDE.md` (§ *Pipeline*).

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| A second profile is rejected | `test_only_one_user_profile_per_tenant` | Behaviour on a DB that **already** had two before the index existed — no test starts from that state |
| The limit doesn't constrain other shared types | `test_the_profile_limit_does_not_constrain_the_other_shared_types` · `test_a_second_tenant_may_have_their_own_profile` | — |
| Agent-only types still rejected from `shared_record` | `test_shared_rejects_agent_only_record_types` | — |
| Parser: one item, fixed key, blank field survives, no marker → none | 4 tests in `test_markdown_parser.py` | A file that exists but is unreadable (a directory, a permission error) — `.exists()` is true and `_read` would raise |
| Importer: creates one row, tolerates absence, ignores markerless, idempotent | 4 tests in `test_importer.py` | — |
| `awaken` returns the profile / `None`, and it doesn't leak into reasoning or knowledge | 3 tests in `test_awaken.py` | — |
| Both faces return the same profile | `test_both_faces_carry_the_same_user_profile` | — |
| **The first-run bootstrap asks exactly once** | **none — unreachable by any test** | **All of it.** The instruction lives in a compiled command; only a fresh agent session reading it can be observed |
| **`search` results now include a profile** | **none** | Whether a caller merging the two labelled groups mislabels or leaks the profile |
| **The configurator pair and the compile pipeline** | **none — shell, outside pytest** | All of it: ordering, the private write, the derived copy, and `CLAUDE.md`'s bytes |
| **The public template holds no real values** | **none** | A `grep` over `control-files` |

## Checks

### Import & store
- [ ] After `reset-db.sh` + `seed-meta.sh --all`: `agent` = 27, `shared_record` = 56, exactly **one** row with `record_type='user_profile'`.
- [ ] Re-run `seed-meta.sh --all` **without** resetting: the profile row count is still 1 and its `uuid` is unchanged — a re-import updates, never duplicates.
- [ ] Delete `shared-memory/user-profile.md`, reset, re-import: the import **succeeds** with 55 shared rows and no profile. Absence is not an error.
- [ ] Put a file with no `[USER-NAME]` marker at that path, reset, re-import: still succeeds, still no profile row. Nothing is stored under a name that promises meaning.
- [ ] Attempt `insert(scope="shared", record_type="episode", …)` via the API — expect a `CHECK constraint failed`, not a stored row.

### Payload
- [ ] `GET /api/awaken?agent_id=meta` → `shared.user_profile` is an object with a `content` carrying all three markers, **not** an index projection (it has a body).
- [ ] The same call over MCP returns an identical `shared.user_profile`.
- [ ] `shared.reasoning` and `shared.knowledge` contain **no** profile record — check by uuid, not by eyeballing counts.
- [ ] With the profile row deleted: `shared.user_profile` is `null` and the call still returns **200**. It must not raise or omit the key.
- [ ] `search` for a word that appears only in the philosophy text: the hit comes back, and it is labelled as shared rather than attributed to an agent.

### First-run bootstrap — *the reason this checklist exists*
> Requires a **fresh agent session** reading the installed instruction. Cannot be done from inside a running session, and no automated test reaches it.
- [ ] With **no** profile row and no `shared-memory/user-profile.md`: awaken an agent. It asks for name, philosophy and vision — **exactly once**, and only these three.
- [ ] Answer the ask. The values are written to `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md` — the private store, *not* the public template.
- [ ] Awaken again. It is **silent** — no re-ask.
- [ ] Blank the vision line in the source, re-import, awaken. It is **silent**. A deliberate blank is never re-asked. *(This is the item most likely to fail: "empty value" and "no record" are easy to conflate in prose.)*
- [ ] On the **markdown** path the awakening set is still **4** files — the profile is not a fifth Read.

### Pipeline & repo hygiene
- [ ] `grep -ri "success feeling first" control-files/` returns **nothing**. The real values are gone from the public repo.
- [ ] `control-files/core-memory/0-core-user-profile.md` has all three markers with empty values.
- [ ] Run `user-config-claude.sh`: **environment is Part 1/2, profile is Part 2/2**. The order is load-bearing.
- [ ] Run `user-profile-claude.sh` with `[AGENT-MEMORY-PATH]` unset in `output/1-core-environment-memory.md`: it **exits non-zero** with a message, and writes nothing. It must not guess a location for private values.
- [ ] Run it normally, keep all three values: the private file and `output/0-core-user-profile.md` are byte-identical afterwards.
- [ ] Compile and compare the output's profile block against live `CLAUDE.md` — **byte-identical**. The source moved; the permanent layer must not.
- [ ] ⚠️ Do **not** run the core's write step alone. It overwrites `CLAUDE.md` with core-compiled output and drops the overlay's `[path-to-agent-memory-coding-skill]` definition, which 38 overlay commands resolve through. Run both installers as a pair.

### Regression surface
- [ ] Full suite green (`uv run pytest -q`) and `ruff check` clean.
- [ ] `/create-agent` on the DB backend still inserts three `identity` records — the shared-table change must not have touched agent-scoped writes.
- [ ] `list-agents` still returns 27 with names and roles read from columns.
- [ ] The `awaken` payload has not crossed the 25,000-token MCP output cap — the profile adds roughly 421 bytes, but the cap truncates silently, so confirm rather than assume.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
