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

That authored home is also why the states below are reached through [`qa/fixtures/profile-source.sh`](../fixtures/profile-source.sh) rather than by hand. It assembles a throwaway source root — real `agent-meta/` and shared layer, copied verbatim — with the profile file `present`, `absent`, `markerless` or `blank-vision`, and prints the path to feed `MUNNIN_IMPORT_SOURCE`. The database is a rebuildable projection and losing it costs one re-import; the authored file is not, so no item here asks you to edit or delete it.

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
4. Re-seed from the `absent` fixture, then awaken as a **fresh agent session** and watch what it asks (§ *First-run bootstrap* — the part no test reaches).
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

Nothing in that right-hand column became automated when the fixture arrived — a precondition builder is not a test, and the manual items are still manual. What changed is that five check items below — two under *Import & store*, one under *Payload*, two under *First-run bootstrap* — are now reachable without editing the authored profile, because `absent`, `markerless` and `blank-vision` produce those states in a throwaway source root instead.

## Checks

### Import & store
- [x] After `reset-db.sh` + `seed-meta.sh --all`: `agent` = 27, `shared_record` = 56, exactly **one** row with `record_type='user_profile'`.
- [x] Re-run `seed-meta.sh --all` **without** resetting: the profile row count is still 1 and its `uuid` is unchanged — a re-import updates, never duplicates.
- [x] Seed from the `absent` fixture: the import **succeeds** with 55 shared rows and no profile. Absence is not an error.
- [x] Seed from the `markerless` fixture: still succeeds, still 55 rows, still no profile row. Nothing is stored under a name that promises meaning.
- [x] Attempt `insert(scope="shared", record_type="episode", …)` via the API — expect a `CHECK constraint failed`, not a stored row.

### Payload
- [x] `GET /api/awaken?agent_id=meta` → `shared.user_profile` is an object with a `content` carrying all three markers, **not** an index projection (it has a body).
- [ ] The same call over MCP returns an identical `shared.user_profile`.
- [x] `shared.reasoning` and `shared.knowledge` contain **no** profile record — check by uuid, not by eyeballing counts.
- [x] Seeded from the `absent` fixture: `shared.user_profile` is `null` and the call still returns **200**. It must not raise or omit the key.
- [x] `search` for a word that appears only in the philosophy text: the hit comes back, and it is labelled as shared rather than attributed to an agent.

### First-run bootstrap — *the reason this checklist exists*
> Requires a **fresh agent session** reading the installed instruction. Cannot be done from inside a running session, and no automated test reaches it.
- [ ] Seeded from the `absent` fixture, so there is no profile row and no profile file at the source root: awaken an agent. It asks for name, philosophy and vision — **exactly once**, and only these three.
- [ ] Answer the ask. The values are written to `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md` — the private store, *not* the public template.
- [ ] Awaken again. It is **silent** — no re-ask.
- [ ] Seed from the `blank-vision` fixture and awaken. It is **silent**. A deliberate blank is never re-asked. *(This is the item most likely to fail: "empty value" and "no record" are easy to conflate in prose. The fixture makes the two states one word apart, which is the point.)*
- [x] On the **markdown** path the awakening set is still **4** files — the profile is not a fifth Read.

### Pipeline & repo hygiene
- [x] `cd control-files && git grep -i "success feeling first"` returns **nothing**, and the same for `"legendary ecosystem"`. The claim is about the *repo*, so the check has to ask git — a plain `grep -ri control-files/` walks the working tree and hits `core-memory/output/`, which is gitignored and is *supposed* to hold the real values as the compile input.
- [x] `control-files/core-memory/0-core-user-profile.md` has all three markers with empty values.
- [x] Run `user-config-claude.sh`: **environment is Part 1/2, profile is Part 2/2**. The order is load-bearing.
- [x] Run `user-profile-claude.sh` with `[AGENT-MEMORY-PATH]` unset in `output/1-core-environment-memory.md`: it **exits non-zero** with a message, and writes nothing. It must not guess a location for private values.
- [x] Run it normally, keep all three values: the private file and `output/0-core-user-profile.md` are byte-identical afterwards. *(2026-08-21 — verified as **currently true** in both checkouts by `cmp`, and the copy step was exercised sandboxed; the script was not re-run against the real store.)*
- [x] Compile and compare the output's profile block against live `CLAUDE.md` — **byte-identical**. The source moved; the permanent layer must not. *(2026-08-21 — all three markers in live `CLAUDE.md` match the authored private source exactly, and the overlay's `[path-to-agent-memory-coding-skill]` line is present at line 107. Observed, not re-compiled: a fresh compile would **make** them match, whereas finding them already matching is what the invariant actually claims.)*
- [ ] ⚠️ Do **not** run the core's write step alone. It overwrites `CLAUDE.md` with core-compiled output and drops the overlay's `[path-to-agent-memory-coding-skill]` definition, which 38 overlay commands resolve through. Run both installers as a pair.

### Regression surface
- [x] Full suite green (`uv run pytest -q`) and `ruff check` clean.
- [x] `/create-agent` on the DB backend still inserts three `identity` records — the shared-table change must not have touched agent-scoped writes.
- [x] `list-agents` still returns 27 with names and roles read from columns.
- [ ] ❌ **FAILED** — The `awaken` payload has not crossed the 25,000-token MCP output cap — the profile adds roughly 421 bytes, but the cap truncates silently, so confirm rather than assume.

## Result

**Run**: 2026-08-21 · agent-meta · Tactic C (guided checklist pass), on the live HTTP face with the full-fleet store
**Automated**: 18/18 green — plus the whole suite at 261 passed and `ruff check` clean
**Manual**: 20/25 walked — 19 passed, **1 failed**, 5 not run
**Sign-off**: **NOT SIGNED OFF** — the payload-cap row failed, and five rows were never reached: the four first-run-bootstrap behaviours need a fresh agent session, and the MCP-face comparison was not walked live (its automated twin is green). The two pipeline rows were closed by observation rather than by re-running the installers — see finding 7 for why re-running is not currently a mechanical step.

The three-state model at the centre of this checklist was proved end to end over the real face: `absent` returns `user_profile: null` with HTTP 200 and the key still present; `blank-vision` returns a **record** whose vision value is `''`; `present` returns the full body. "Told us nothing" and "never asked" are distinguishable in the payload, which is what the bootstrap depends on.

### Findings
| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | **`awaken` is 2.2× over the MCP output cap.** `GET /api/awaken?agent_id=meta` returns 223,500 chars ≈ **55,875 tokens** against the 25,000-token hard cap, which truncates **silently** at the client. `shared` alone is ≈25,486 and `emotional` ≈19,617. The profile contributes ~105 tokens, so this change did not cause it — but the row asked for confirmation rather than assumption, and it is confirmed over. Counted with `control-files/procedures/setup-scripts/token-counter.py`, which fell back to its chars/4 heuristic (no tiktoken installed) and therefore **under**counts emoji-dense text. | dev | **deferred** 2026-08-21 by Alvi — *"I'll check this later"* |
| 2 | **A second profile is refused with HTTP 500, not 400.** The one-per-tenant invariant holds — the row was rejected, the store stayed at 56 with one profile and no impostor row — but `insert_shared` only converts `sqlite3.IntegrityError` to a `ValueError` when the message contains `CHECK constraint failed`; a `UNIQUE constraint failed: shared_record.user_id` re-raises and surfaces as an unhandled 500. A caller-caused constraint violation should be a 400 with a message, exactly as the CHECK case already is. | dev | **fixed** 2026-08-21 — the handler now converts the partial-index violation too; verified live (was 500, now 400 naming the one-per-tenant rule) and mutation-proved. |
| 3 | **The shared-scope rejection message omits `user_profile`.** `_SHARED_RECORD_TYPES` in `sqlite_memory_repository.py` is the hardcoded string `"'reasoning' or 'knowledge'"`, so a refused insert tells the caller shared memory "may only be 'reasoning' or 'knowledge'" — two of the three types the CHECK actually allows. Behaviour is correct; the message under-reports the allowed set. **A test was holding it there** — `test_shared_type_rejection_names_what_is_allowed` asserted the literal `"'reasoning' or 'knowledge'"`, so the message could not be corrected without the test objecting. | dev | **fixed** 2026-08-21 — `SHARED_RECORD_TYPES` now declared once beside the enum and the message derived from it; the test asserts the declared set, and a new schema test pins that set against the CHECK so the two cannot drift. |
| 4 | **This checklist instructed deleting the authored profile.** Five rows told the tester to edit or delete `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md` — the single authored home for the real values, and not a rebuildable artifact. They now route through `qa/fixtures/profile-source.sh`. | qa | fixed 2026-08-21 |
| 5 | **The repo-hygiene row asked git's question with the filesystem's command.** `grep -ri "success feeling first" control-files/` walks the working tree and hits `core-memory/output/`, which is gitignored and is *supposed* to hold the real values as the compile input. The claim is about the repo, so the check now uses `git grep`, which returns nothing — the invariant holds and always did. | qa | fixed 2026-08-21 |
| 6 | ~~`search` marks a shared hit by an absent key~~ — **withdrawn**. Investigated on Alvi's question: the conditional key is deliberate and documented in three places (`memory_service.py` lines 50, 56, 162, 179). A stated contract, not drift. | — | withdrawn |

| 7 | **The two `control-files` checkouts have diverged, so "run both installers" is not a mechanical step.** The store's checkout (`~/.claude/@agent-memory/control-files`, a Junction onto `C:/Work/IM/@agent-memory/control-files` — same inode, so there are **two** real checkouts, not three) sits on `main` at `a8f3cc6`; Munnin's sits on `user-profile-record` at `cd6de63`. **Neither is an ancestor of the other**, and the store's checkout has never fetched the branch. The live `CLAUDE.md` (11,886 B, written 2026-08-20 08:48) came from the store's `main`-era code. Compiling from `main` would use code predating the profile work; compiling from the feature branch would make an unmerged branch the writer of the machine-wide permanent layer, which has only ever had one writer. Recorded rather than resolved. | dev | open — needs a merge decision |

### Not run, and why
- **The four first-run-bootstrap behaviours** — the ask, the private write, the silence on re-awaken, and the silence on a blank field. Each needs a fresh agent session reading the installed instruction; none is reachable from inside a running session, and no automated test reaches them. The *data* preconditions for all four are now one fixture invocation away.
- **The MCP-face comparison** — covered automatically by `test_both_faces_carry_the_same_user_profile` (green), but not walked live against the running server.
- **The installers were deliberately not run** — see finding 7. Both pipeline rows were instead closed by observing the invariant they assert: the authored private source, the derived `output/0-core-user-profile.md` in **both** checkouts, and the profile block in live `CLAUDE.md` all carry identical values, and the overlay's `[path-to-agent-memory-coding-skill]` definition is present at line 107. That is stronger evidence for a *"the permanent layer must not move"* claim than a fresh compile, which would have **made** them agree rather than found them agreeing.
