# High Wizard Plan

## **PROJECT INFO**
- **Project**: agent-memory-server (Munnin) + control-files
- **Date**: 2026-08-21
- **Agent**: Claude Meta
- **Theme**: The user profile as fleet memory — a sixth `RecordType` admitted to `shared_record`, a single markdown source of truth in the private store, and the strictly-first-run bootstrap that creates it when no source exists
- **Source Protocol**: `/high-wizard` — /high-wizard

*CRITICAL INSTRUCTION: To continue this plan: load the source protocol above, then inspect which sections below are filled vs unfilled to infer your current step.*

---

## **INHERITED CONTEXT**
*Filled at investigation step 0 when this plan was launched as a sub-plan — from the parent's handoff payload (or the parent `core-plan.md` beside this file). Write "None — standalone plan" if there is no parent.*
*These decisions are **not yours to reopen**. If one looks wrong, STOP and surface it to [USER-NAME] — do not silently re-decide it here or in Confirmed Decisions below.*

None — standalone plan.

Two earlier plans touched this ground and neither is a parent. A 2026-08-14 `/council-of-wizards` scoped the profile together with environment memory; environment was decided out of the DB entirely on 08-15, which left that plan over-scoped at Level 2, and [USER-NAME] abandoned it — its folder is deleted in this plan's first commit. The 2026-08-20 agent-entity plan deferred `user-profile` explicitly (*"same class of question, deliberately deferred and re-decided against whatever this lands"*), and this plan is that re-decision; it inherits that plan's **schema** as landed code, not as decisions to honour.

---

## **OBJECTIVES**

Make an agent awakening from the database know who the user is, by storing the user profile where it behaves like what it is — fleet memory, shared by every agent and owned by none.

Three documents already tell a DB-path agent that the profile *"is already in the agent's context… from `awaken`'s `user-profile` record"*. No such record type exists, and `awaken()` returns no such key, so the instruction describes something that never happens. This plan makes those sentences true rather than rewriting them.

A second objective rides along because it shares one artifact: the profile's real values are currently committed in the **public** framework repo, and [USER-NAME] asked on 2026-08-15 for both environment and profile to be decoupled from it. Environment's half was done; the profile's was not. The markdown file this plan creates is both the importer's source and that private home, which is why the two are one job rather than two.

### **Related Documents**
- [permanent-vs-perishable-memory.md](../../../.claude/@agent-memory/shared-memory/agent-memory/context/permanent-vs-perishable-memory.md) — the 2026-08-15 decision this plan implements: profile in the DB, scoped fleet-wide, first-run-only ask, field named "philosophy" not "mission"
- [2026-08-20-agent-memory-server-agent-identity-entity.md](2026-08-20-agent-memory-server-agent-identity-entity.md) — the landed three-table schema this plan builds on, and the plan that deferred this question
- [db.md](../control-files/procedures/memory/storage-backends/db.md) — the served DB backend carrying the untrue precondition sentence
- [memory-mcp-server.md](../../../.claude/@agent-memory/docs/architecture/memory-mcp-server.md) — §3 schema, to be amended for the sixth record type

### **SUCCESS CRITERIA**
- [ ] `RecordType` gains `user_profile`; `shared_record`'s CHECK admits it and still rejects `episode`, `identity`, `emotional` — proven by a rejection test, not a happy-path one
- [ ] `shared-memory/user-profile.md` exists in the private store and is the **single** source of truth — no second copy anywhere
- [ ] The public template `0-core-user-profile.md` carries placeholders only; `grep` for the real values in `control-files` returns nothing
- [ ] Importer creates exactly **one** `user_profile` row; `shared_record` goes 55 → **56** after re-import (55 measured from the live DB, not from the prior plan's criterion — see decision 12)
- [ ] `awaken()` payload carries the profile under its `shared` key; markdown awakening set stays at **4** files
- [ ] The strictly-first-run ask is specified in `core-instruction-control-files.md` and fires on **absence only** — never on a deliberately blank field
- [ ] `db.md`'s payload section lists `shared.user_profile`, and its *"not covered by the payload"* note no longer names the profile; `ARCHITECTURE.md`'s claim becomes true unedited; the compiled `awaken-agent.db.md` follows from `db.md`
- [ ] Full suite green against the 245-test baseline, ruff clean, control-files CI green (ruff · 38 tests · `--strict` compile · core invariant)
- [ ] Field test passes **on the markdown path**: the ask fires on a missing profile, stays silent when one exists, and stays silent on a deliberately blank field
- [ ] Static quality review completed (Step 16)
- [ ] QA Handoff completed (Step 17)

---

## **SCOPE**

### In Scope
- `RecordType.user_profile`; `shared_record` CHECK widened to three values
- `shared-memory/user-profile.md` in the private store — the single source of truth
- `0-core-user-profile.md` in the public repo reduced to placeholders
- `parse_shared_profile` + a third block in `import_shared`
- `awaken()` payload key for the profile
- The strictly-first-run bootstrap ask in `core-instruction-control-files.md` (component, two callers)
- `markdown.md` / `db.md` seam ops for reading the profile per backend
- Purge and re-import the local DB
- `db.md`'s payload list and its "not covered by the payload" note — the profile moves from the second to the first
- Arch-doc §3 amendment for the sixth record type
- `docs/flows/awaken-db.md` — the payload addition **and** the pre-existing `__shared__` staleness left by the agent-entity plan ([USER-NAME]'s call: fix the whole file rather than half of it)

### Out of Scope
- **The `user` table** — needed, and deferred to the login work by [USER-NAME]'s call. It holds Authentra auth identity; the profile is not auth data. See the decision table.
- **Foreign keys on `user_id`** — `agent.user_id` and `shared_record.user_id` still reference nothing. Real gap, belongs with the table that would anchor them.
- **Login / multi-tenant** — `user_id` stays a server-side constant.
- **A `user_id` format agreement** — none exists; it becomes decidable only once a token is producing the value.
- **B′ activation** — markdown stays authoritative; this does not switch the fleet to DB reads.
- **Profile editing through the write tools** — the markdown file and the first-run ask are the only writers this plan creates.
- **Serving `awaken-agent` as Prompt 12** — deferred (decision 16). Consequence stated plainly rather than implied: the first-run ask ships **markdown-path only**, and a DB client will receive the profile record but not the instruction to ask for one when it is missing.

---

## **CONFIRMED DECISIONS**
*Decisions made **by this plan** — both **asked-and-confirmed** by [USER-NAME] AND **written-through** (Zone A and B decisions made by the agent, recorded with their reasoning). The reasons serve as the analysis record.*
*Decisions inherited from a parent belong in [INHERITED CONTEXT](#inherited-context) above, not here — keeping them separate is what shows which decisions this plan actually owns.*

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | Where the profile lives in the DB | **Fleet memory** — a sixth `RecordType` admitted to `shared_record` | It is shared by every agent, owned by none, always-load at awakening, and sourced from a markdown file in `shared-memory/` — which is the definition `shared_record` carries in its own schema comment. [USER-NAME] raised this against an earlier recommendation of mine and was right: that recommendation had bundled *does `user_id` need a referent* with *where does profile content live*, and used the first to carry the second. |
| 2 | Whether the `user` table holds the profile | **No** — the table is needed for Authentra auth identity and is deferred to the login work; the profile stays memory | Different writers and different lifecycles: the `user` row is derived from verified token claims and rewritten on every login, the profile is authored by hand. They also hold different facts — Authentra supplies an account name (*Alviandi Widiasto*), the profile supplies what agents should call him (*Alvi*). Merging them makes one silently overwrite the other. Fleet memory also inherits FTS5 indexing, so *"what is my philosophy"* is searchable; a table column would not be. |
| 3 | The profile's markdown source of truth | `shared-memory/user-profile.md` in the private store | The importer needs a parseable file, and decoupling from the public repo needs a private home. One file satisfies both, and one file is the only arrangement that cannot drift. |
| 4 | The real values in the public repo | Reduced to placeholders in `0-core-user-profile.md` | Finishes the 2026-08-15 decoupling [USER-NAME] asked for, whose environment half shipped and whose profile half did not. The template keeps its role as a virgin-checkout seed. |
| 5 | Plan vehicle | Fresh standalone High Wizard; the 2026-08-14 CoW folder deleted | [USER-NAME]'s call. Environment leaving the scope on 08-15 left that plan over-scoped at Level 2 — one deliverable with no siblings is Level 1 by the ladder's own definition. |
| 6 | *(written through)* One record or three | **One** `user_profile` record holding the whole profile | A presence check for the first-run ask is then a single question — zero rows or one — where three records admit partial states with no rule for resolving them. The 08-15 decision also says "the record", singular, and locates blank-field handling *inside* it. |
| 7 | *(written through)* No new repository method | Reuse `insert_shared` / `query_shared` / `search_shared` | The agent-entity work already gave the repository a complete shared-memory surface. A sixth record type is data flowing through existing methods, not a new capability. |
| 8 | *(written through)* Markdown-path awakening | Unchanged — the profile stays a precondition already in context from the global instructions file | [USER-NAME] rewrote that section himself on 08-15 to say exactly this. Adding a fifth Read would reverse the 5 → 4 reduction earned when the awakening protocol became a component, and buy nothing: the value is already in the system prompt. |
| 9 | *(written through)* Branch | `user-profile-record`, cut from `agent-identity-entity` in both repos | That branch is committed and pushed but not merged to `main`, and this plan depends on its schema. Branching from it avoids both a collision and a rebase; a branch is free to redo if [USER-NAME] merges first. |
| 10 | Profile file format and its parser | Keep the bullet form (`- **[USER-NAME]** = Alvi`); write a small `parse_shared_profile` for it | The file has **two readers**: `user-profile-claude.sh` greps those literal markers, and the importer parses it. Reformatting to `###` headings would let `split_sections` be reused, but it rewrites a working shell pipeline *and* changes how the block appears in the compiled permanent layer — and the permanent layer is the one artifact that must not wobble. A six-line parser is the cheaper side of that trade. |
| 11 | How the profile script learns where the private store is | Reorder `user-config-claude.sh` to run **env first, profile second**; profile reads `[AGENT-MEMORY-PATH]` from the env output | [USER-NAME]'s call, and it corrects a proposal of mine that violated a boundary. I had suggested deriving the store root from `$SCRIPT_DIR/../../..`, which works only because control-files happens to be a submodule of the store — **a submodule must never know its parent**, and a standalone clone of the public repo would be reasoning about a directory that isn't there. `[AGENT-MEMORY-PATH]` exists exactly to inject that value from outside; the only obstacle was ordering, and ordering is one line. Verified the one-click path reaches it: `setup-claude-code.bat` → `setup-claude-code.sh` → `user-config-claude.sh`. Rejected alternatives: a `--store-path` argument (explicit, but hassle for a wizard `.bat`), and moving the configurator into the private repo (purest, but the installer would then reach *into* the parent — the same violation inverted). |
| 12 | *(written through)* The row-count baseline | **55** shared records, measured from the live DB — not the 61 in the prior plan's criterion | Final-review check caught this: I had taken 61 from the agent-entity plan's *success criteria*, which that plan itself recorded as **NOT met as written**. Its execution log explains why — the old DB carried **six ghost rows** for patterns that had moved to `coding-reasoning-memory.md`, surviving only because the importer never deletes. The purge removed them, and 55 (27 reasoning + 28 knowledge) matches the markdown source exactly. Reading a plan's criteria instead of its results is the adjacent-evidence trap (`0eb34b96`) in document form. |

---

| 13 | `uv.lock` in control-files | **Commit it** | The repo declares `ruff>=0.16.2` and `pytest>=9.1.1` — open-ended bounds, so a new ruff minor with new default rules can turn the framework's CI red on a day nobody touched the code. This repo has already lost a run to version drift once (`setup-uv@v10`, a floating tag that never existed). `uv sync` honours an existing lock, so committing pins CI with no workflow change. |
| 14 | Proving the first-run ask | **Field-test it in this plan** (new Phase 5) rather than handing it to a QA session | Unit tests can prove the prose exists, never that the behaviour is right. Three items are already carried as *never run* — `/create-agent`, REAQ's amendments, wizard altitude+handoff — and each was deferred for a reason as reasonable as "write the checklist and verify later". The store is right here; the test costs three awakenings. |
| 15 | When the `user` table and login happen | **When Authentra integration actually starts** | The claim shapes decide the columns. The one concrete thing already known — that Authentra's account name and the profile's name are different facts — came from reasoning about real claims; building the table against imagined ones would bake in guesses. |
| 16 | Whether `awaken-agent` becomes Prompt 12 here | **Defer** — this plan's bootstrap is delivered on the **markdown path only** | Verified that `core-instruction-control-files.md` reaches **no** served Prompt: its only consumers are `awaken-agent.md` and `refresh-memory.md`, neither of which is in `_PROMPTS`. So the first-run ask is undeliverable to an MCP client until `awaken-agent` is served. Deferred because the DB path has **no live clients** — B′ is not activated and markdown is authoritative — so nothing is broken today, and folding it in would be this plan's third scope addition. Logged as a `/quick-wizard`-sized follow-on: one map entry, three count assertions, and confirming the served text stands alone. |
## **SOLUTION**

### Architecture Overview

The profile becomes the third kind of thing that lives in `shared_record` — memory the fleet shares and no agent owns. Nothing new is invented to carry it: the repository already exposes `insert_shared` / `query_shared` / `search_shared`, `awaken()` already assembles a `shared` block, and the importer already has a place where fleet files are read. This plan adds a record type, a parser, and one file; the existing machinery carries the rest.

The one genuinely new behaviour is on the markdown side, and it is a *relocation* rather than a feature: the profile's real values stop living in the public framework repo and move into the private store, where a single file now feeds two consumers — compiled into the global instructions file for the markdown path, imported into `shared_record` for the DB path. One source, because two would drift.

### Component 1: The record type and its constraint

- **Purpose**: make `user_profile` a thing the store will accept, without loosening what it rejects.
- **Key Files**: `src/munnin/data_entities/memory_record.py`, `src/munnin/data_entities/schema.sql`

`RecordType` gains a sixth member. `shared_record`'s CHECK becomes `IN ('reasoning','knowledge','user_profile')` — still rejecting `episode`, `identity` and `emotional`, which is what that constraint was written to do.

`schema.sql` is applied with `CREATE TABLE IF NOT EXISTS`, so **an existing database keeps its old CHECK**. This is why purge-and-re-import is in scope rather than optional: without it the constraint silently stays two-valued and every profile insert fails.

### Component 2: The markdown source of truth

- **Purpose**: one file holding the real values, in the private store.
- **Key Files**: `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md` (new), `control-files/core-memory/0-core-user-profile.md` (reduced to placeholders)

Format is unchanged from today's bullet form, because `user-profile-claude.sh` greps those literal markers and the compiled permanent layer renders them.

### Component 3: The parser

- **Purpose**: one file to exactly one `ParsedItem`.
- **Key Files**: `src/munnin/data_migrations/markdown_parser.py`

`parse_shared_profile(text)` returns a single item whose body is the whole file, titled `User Profile` with a fixed key so `stable_uuid("shared", "user_profile", ...)` is idempotent across re-imports. It returns **empty** when the user-name marker is absent — a file carrying no marker is not a profile, and importing it as one would store noise under a name that promises meaning.

### Component 4: The importer block

- **Purpose**: create the row, and tolerate its legitimate absence.
- **Key Files**: `src/munnin/data_migrations/importer.py`

A third block in `import_shared`, alongside reasoning and knowledge. It differs from both in one way that matters: **the file may legitimately not exist** — a fresh store, or a user who has not run setup — so absence skips with a count of zero rather than raising. Reasoning and knowledge are framework invariants; a profile is a fact about a person who may not have told us yet.

### Component 5: The awaken payload

- **Purpose**: deliver it to a DB-path agent.
- **Key Files**: `src/munnin/business_services/memory_service.py`

`awaken()`'s `shared` dict gains `user_profile` — the whole record, or `None`. It sits with `reasoning` and `knowledge` because it *is* layer i: always-load, fleet-wide, agent-independent.

### Component 6: The seam and the first-run ask

- **Purpose**: tell each backend where the profile comes from, and what to do when there isn't one.
- **Key Files**: `control-files/procedures/memory/storage-backends/markdown.md`, `.../db.md`, `control-files/procedures/components/core-instruction-control-files.md`

A new `§ load-user-profile` op under `## core-instruction-control-files` in both backends. **Markdown**: no action — the profile is already in context from the global instructions file, which is what [USER-NAME] rewrote that section to say on 2026-08-15. **DB**: it arrived in the `awaken` payload under `shared.user_profile`.

The component gains the bootstrap: if the profile is **absent**, ask for the three fields once and write them. Absent means no record at all — a record with a blank field is a deliberate blank and must never be re-asked. This is the concession to AUTOMATIC FOR READ, EXPLICIT FOR WRITE (`7b3c5a9d`): an interactive first-run bootstrap is acceptable where a silent recurring write is not.

### Component 7: The configurator reorder

- **Purpose**: let the profile script learn the store path without a submodule reaching upward.
- **Key Files**: `control-files/core-memory/compile-scripts/user-config-claude.sh`, `.../user-profile-claude.sh`

The orchestrator runs **env first, profile second**. `user-profile-claude.sh` then reads `[AGENT-MEMORY-PATH]` from the env output file and writes to the store's `shared-memory/user-profile.md`. If the value is missing it says so and exits non-zero rather than guessing a location for private data.

### Component 8: Documentation

- **Purpose**: keep the architecture record true.
- **Key Files**: `control-files/procedures/memory/storage-backends/db.md`, `docs/architecture/memory-mcp-server.md` (section 3)

`db.md` needs a real edit, and self-review caught that I had claimed otherwise. Its payload note reads *"Not covered by the payload — and no longer needs to be"* and lists **two** things under it: the awakening instructions, which genuinely are not records, and the user profile, which is about to become one. Those must split — `shared.user_profile` joins the payload bullet list above, and the note keeps only the instructions. The compiled `awaken-agent.db.md` is generated from `db.md`, so it follows automatically; `ARCHITECTURE.md`'s line does become true unedited.

Section 3 of the architecture doc gains the sixth record type and the widened CHECK.

<!-- OPTIONAL SECTION A2 -->
### Cross-System Contract Impact (Blast-Radius Check)

**Change classification**: [x] enum value added · [x] new field (payload key) · [x] string format (the profile file's markers) · [ ] field type/nullability · [ ] semantics changed

| # | Consumer (system + path) | How it couples | Breaks how on this change? | Verified / mitigated |
|---|---|---|---|---|
| 1 | bash — `user-profile-claude.sh` | greps the profile markers by line | none — format deliberately unchanged (decision 10) | re-run the script and diff its output |
| 2 | bash — `compile.sh` to the global instructions file | reads the profile block, writes the permanent layer | a wrong source path blanks the profile in CLAUDE.md | compile and diff live `CLAUDE.md` before/after |
| 3 | python — `parse_shared_profile` | parses the same file the shell writes | a format change on either side silently yields zero items | round-trip test: shell-written file to parser to one item |
| 4 | SQLite — `shared_record` CHECK | any caller inserting a shared record | an un-migrated DB rejects every profile insert | purge and re-import; rejection test for the three still-invalid types |
| 5 | MCP/HTTP clients — `awaken()` payload | reads the `shared` block | additive key; an old client ignores it | twin-parity test across both faces |
| 6 | served `db.md` — any DB-path agent | reads the instruction as a precondition | already broken today; this fixes it | assert the served text names `shared.user_profile` |

- **Deploy ordering**: schema, then importer, then served content. The DB must accept the type before anything writes it, and the instruction must not promise a payload key that isn't there yet.
- **Existing data**: none — no profile row exists anywhere today, so there is no mixed-format case.

<!-- OPTIONAL SECTION C -->
### Technical Considerations

- **`CREATE TABLE IF NOT EXISTS` does not alter an existing table.** The widened CHECK reaches only a freshly created database. Purge-and-re-import is therefore load-bearing rather than hygiene — and the failure it prevents is a constraint violation on every insert, which is at least loud.
- **FTS5 triggers are type-blind and need no change.** The `shared_record` triggers fire on any row, so the profile becomes searchable with no extra work. That is a benefit of the fleet-memory decision which a `user` table column would not have had.
- **One file, two languages.** The bullet format is a contract between a bash `grep` and a Python parser with no shared schema. Row 3 of the blast-radius table is the only thing that would catch a drift, so that round-trip test is not optional.
- **`[AGENT-MEMORY-PATH]` becomes a hard dependency of profile setup.** It was already required by the framework at large; this makes it required *earlier*, which is why the orchestrator order changes rather than the profile script guessing.
- **The first-run ask cannot be proven by tests.** It is prose in a component inlined into two callers across two backends, and its correctness is *asks exactly once, never nags a deliberate blank*. Tests can confirm the text is present and the payload key exists; only a real awakening confirms the behaviour. This belongs in QA Handoff rather than being implied as covered.
- **A standalone public clone gets no profile setup.** With no private store there is nowhere private to write. That is correct, and it is the same precondition every other memory operation already has — but it should be said out loud rather than discovered.

---

## **IMPLEMENTATION PHASES**

### Phase 1: Schema

- [ ] **Step 1.1**: The sixth record type and its constraint
  - **Action**: add `user_profile` to `RecordType`; widen the `shared_record` CHECK to three values.
  - **Implementation**: enum member in `memory_record.py`; CHECK clause in `schema.sql`.
  - **Testing**: a **rejection** test — inserting `episode`, `identity`, `emotional` into `shared_record` still raises; inserting `user_profile` succeeds.
  - **Success Criteria**: both directions proven, so the constraint is narrower than "anything goes".

### Phase 2: Source, parser, importer

*Ordering note: the re-import that counts the profile row must come **after** the file and the parser exist, or it counts 61 and the criterion is unmeetable. Self-review caught this the other way round.*

- [ ] **Step 2.1**: Create the private profile file
  - **Action**: write `shared-memory/user-profile.md` with the real values.
  - **Implementation**: `cp` from the current template — copied, never retyped (`076a9843`).
  - **Testing**: byte-identical to its source; the private store shows it as a new file.
  - **Success Criteria**: the values exist in the private store.
  - **Ordering correction, found during implementation**: stripping the public template was originally bundled here and has **moved to Step 4.1**. `core-memory/output/` holds nothing but `.gitkeep` — there is no `output/0-core-user-profile.md` — so the tracked template is not a fallback, it is the **live source** the compile reads. Emptying it before the pipeline is retargeted would blank the profile in `CLAUDE.md` in the window between the two steps. It also explains *why* the real values were in the public repo: on this machine nothing else has ever written them.

- [ ] **Step 2.2**: Parser and importer block
  - **Action**: `parse_shared_profile`; third block in `import_shared`.
  - **Implementation**: single `ParsedItem`, fixed key for idempotency; a missing file skips with count 0.
  - **Testing**: one item from a real file; **zero** items from a file with no marker; a missing file imports cleanly; re-import idempotent (row count unchanged, `created_date` preserved).
  - **Success Criteria**: absence and malformity behave differently from success, and both are quiet rather than fatal.

- [ ] **Step 2.3**: Purge and re-import
  - **Action**: delete the local DB and re-import the fleet.
  - **Implementation**: remove `data/valaskjalf-memory.db`, then `importer --all`. Required rather than optional: `CREATE TABLE IF NOT EXISTS` leaves an existing DB on the old two-valued CHECK.
  - **Testing**: `shared_record` count 55 to 56; `agent` still 27; `memory_record` still 1,399 (all three measured from the live DB on 2026-08-21).
  - **Success Criteria**: exactly one `user_profile` row and no other count moves.
  - **Note**: back up before purging, then **delete the backup once counts verify**. `data/` already holds five unreferenced `.bak-*` files totalling ~76 MB, logged as debt by the prior plan; this step should not make it six.

### Phase 3: Delivery

- [ ] **Step 3.1**: The awaken payload
  - **Action**: add `shared.user_profile` to `awaken()`.
  - **Implementation**: `query_shared` filtered to the new type; whole record or `None`.
  - **Testing**: payload carries the profile; twin parity across MCP and HTTP; a store with no profile row returns `None` rather than raising.
  - **Success Criteria**: present when it exists, `None` when it doesn't, identical on both faces.

- [ ] **Step 3.2**: Seam ops and the first-run ask
  - **Action**: `§ load-user-profile` in both backends; bootstrap prose in `core-instruction-control-files.md`.
  - **Implementation**: markdown = no action (precondition); db = read `shared.user_profile`; the ask fires on absence only.
  - **Testing**: `--strict` compile; served `db.md` names `shared.user_profile`; core invariant guard green; awakening set still 4 files.
  - **Success Criteria**: both compiled callers carry the op and no seam header leaks.

### Phase 4: Configurator and docs

- [ ] **Step 4.1**: Reorder the orchestrator; retarget the profile script; strip the public template
  - **Action**: env first, profile second; profile reads `[AGENT-MEMORY-PATH]` and writes to the private store; **then** reduce `0-core-user-profile.md` to empty placeholders (moved here from Step 2.1 — see that step's ordering note).
  - **Implementation**: swap the two blocks in `user-config-claude.sh`; replace the output targeting in `user-profile-claude.sh`; exit non-zero when the path is unset. Template values are left **empty after `= `** rather than filled with descriptive placeholder text, because the script reads a current value with `sed 's/.*\*\* = //'` and would offer any placeholder back as a keep-this default; make that read robust so an unset value cannot survive as one.
  - **Testing (added)**: `grep` for the real values across `control-files` returns nothing.
  - **Testing**: run the orchestrator end to end; compile and **diff live `CLAUDE.md`** to prove the profile block is byte-identical; confirm the `.bat` chain reaches it.
  - **Success Criteria**: the permanent layer is unchanged while its source has moved.

- [ ] **Step 4.2**: Documentation
  - **Action**: move the profile from `db.md`'s "not covered by the payload" note into its payload list; amend arch-doc section 3 for the sixth type and the widened CHECK; bring `docs/flows/awaken-db.md` current on both counts.
  - **Implementation**: rewrite each region as one flow rather than a bolt-on note (`78ead9e5`); recompile so `awaken-agent.db.md` follows. In `awaken-db.md` that means the payload list in the sequence diagram (line ~36), step 3's `repo.query(agent_id="__shared__")` and the importer sentence in the notes — the last two are the agent-entity plan's leftovers, taken on by [USER-NAME]'s call rather than logged back.
  - **Testing**: read each back in context; `grep` for `__shared__` across the three docs returns nothing; no stale "five types" phrasing; the note no longer names the profile.
  - **Success Criteria**: all three documents describe the system as built, with no sentence surviving from either prior era.
  - **Out of scope, deliberately**: `awaken-db.md`'s own recorded open decision about the process-instruction gap. This plan updates the doc's *facts*, not its unresolved question.

---

### Phase 5: Field test

*Unit tests cannot reach this. Decision 14 puts it here rather than in a later QA session, because three prior "verify later" items are still unverified.*

- [ ] **Step 5.1**: Prove the first-run ask against a real awakening
  - **Action**: exercise all three branches of the bootstrap on the live store.
  - **Implementation**: (i) delete the `user_profile` row, awaken, observe the ask; answer it and confirm the row is written. (ii) awaken again, confirm silence. (iii) blank one field in the source, re-import, awaken, confirm it is **not** re-asked.
  - **Testing**: three awakenings, three observed behaviours, recorded verbatim in the log.
  - **Success Criteria**: asks on absence, silent on presence, silent on a deliberate blank. Any other combination is a defect, not a nuance.

---

## **EXECUTION LOG**
**Execution Protocol for AI**:
I have to use this document as my **ONLY** source of truth to execute and track the plan steps iteratively. I should **NOT** use additional tools like ToDos because it lacks the context of what should I do. Everytime I want to implement a step I have to check the reference to the original step plan above. Everytime a step has been finished I need to go back to this document to log what was done.
*In other words*:
- I have to make this document as the source of truth for the implementation phase on what I have worked on and what I will be working
- The original plan must be fully in my context, therefore, I have to make sure I loaded the **Plan File** before executing any task and read carefully the reference to the original step
- I have to do the implementation by doing it in order per step THEN, I ALWAYS have to fill the step log rightly after

**Definition of Done (applies to ALL steps)**:
- ✅ **Code Quality**: Code compiles/runs without errors
- ✅ **Testing**: Tests written and passing
- ✅ **Logged**: Implementation and testing logged below
- 🚫 **Blocked**: Get input from [USER-NAME] before assuming

### Phase 1:
- [x] **Step 1.1**: [The sixth record type and its constraint](#phase-1-schema)
  - **Implementation Log**: `RecordType` gained `user_profile`, and its docstring was rewritten rather than appended to — it now states that the profile is loaded whole at awaken like identity/reasoning/emotional, that it is *fleet* memory because who the user is does not vary by agent, and that it is deliberately not the auth identity (that belongs to a future `user` table fed by verified claims; the two hold different facts). `schema.sql`'s `shared_record` CHECK went from `('reasoning','knowledge')` to `('reasoning','knowledge','user_profile')`, with the comment above it rewritten to say what the constraint now guards: never an episode, identity or emotional moment, all of which belong to some particular agent.
  - **Testing Log**: `tests/data_entities/test_schema.py` — the accept case is now parametrized over three types instead of two, and the reject case is unchanged in behaviour but its docstring explains why widening did not loosen it. **22 passed** in that module. Full suite **246 passed in 41.14s** against the 245 baseline — the single addition is the new `[user_profile]` parametrize case, so nothing else moved. `ruff check` clean.
    - **Mutation-proved rather than assumed.** Reverted the CHECK to two values and ran the accept test: `test_shared_accepts_its_three_record_types[user_profile]` **failed** with `IntegrityError`, the other two passed. Restored → 3 passed. The assertion detects the schema change specifically, not merely the code's presence — which is the check I have repeatedly written and repeatedly failed to prove bites.
  - **Success Criteria**: **Pass.** Both directions proven: `user_profile` is admitted, and `episode` / `identity` / `emotional` are still rejected with `CHECK constraint failed`. The constraint is narrower than "anything goes".
  - **Tech Debts**: None.
  - **Result**: Met. `shared_record` accepts exactly three record types and the widening is proven to be what the test sees.

### Phase 2:
- [x] **Step 2.1**: [Create the private profile file](#phase-2-source-parser-importer)
  - **Implementation Log**: `cp` of `control-files/core-memory/0-core-user-profile.md` to `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md` — copied rather than retyped, so the bullet markers the shell greps and the `## AI Agent - User Profile` heading the compile emits are preserved exactly. 422 bytes.
  - **Testing Log**: `diff` against its source is **empty** — byte-identical. `git status` in the private store shows it as `?? shared-memory/user-profile.md`, i.e. genuinely new rather than overwriting something.
  - **Success Criteria**: **Pass** for this step as re-scoped. The "one copy only" half moved to Step 4.1 with the template strip.
  - **Tech Debts**: None. The temporary two-copy state is deliberate and closes in Step 4.1.
  - **Result**: Met. **Scope correction found here rather than assumed**: `core-memory/output/` contains only `.gitkeep` in *this* checkout, so the strip moved to Step 4.1 to land with the retarget.
  - **Correction, made during Step 4.1 and recorded here where the wrong claim was written**: the sentence above originally continued *"…so the tracked public template is the live source the compile reads on this machine"*. **That was wrong.** There are **four** `control-files` checkouts, and the one that owns the live `CLAUDE.md` is the store's own — `[AGENT-MEMORY-PATH]/control-files` — which is on `main` at `a8f3cc6` with a **populated** `core-memory/output/` holding the real profile and the correct `[AGENT-MEMORY-PATH]`. Munnin's checkout has an empty `output/` and has never compiled the permanent layer. I read one checkout's state and drew a conclusion about "this machine" — the adjacent-evidence trap (`0eb34b96`) with a directory standing in for a fact. Two consequences: stripping the template is **safer** than I said, since the authoritative checkout compiles from its own `output/`; and the reason the real values sit in the public repo is not "nothing ever wrote them elsewhere" — something did, in a different checkout, into a gitignored file.

- [x] **Step 2.2**: [Parser and importer block](#phase-2-source-parser-importer)
  - **Implementation Log**: `parse_shared_profile` added beside the other two shared parsers, returning **one** `ParsedItem` carrying the whole file, titled `User Profile` with the fixed key `user-profile` so `stable_uuid` is stable across re-imports. It returns `[]` when the `[USER-NAME]` marker is absent. The marker is a module constant with a comment naming what it actually is — a contract between bash and Python with no schema to enforce it. `import_shared` gained a third block, guarded by `profile_path.exists()` because `_read` calls `read_bytes()` and would raise on a missing file; the else branch logs that the first-run ask owns that record. Its docstring was rewritten rather than appended to, and now states *why* the third block is guarded while the first two are not: reasoning and knowledge are framework invariants whose absence means a broken store, a profile is a fact about a person who may not have been asked yet.
  - **Testing Log**: 8 new tests — 4 on the parser, 4 on the importer. `tests/data_migrations` **40 passed**; full suite **254 passed in 36.89s** (246 → 254); `ruff check` clean.
    - **The round-trip contract is tested with a literal, not a fixture.** The parser test embeds the exact bullet form the shell writes, written out by hand rather than generated, because a fixture derived from the parser's own assumptions would agree with itself and catch nothing. This is blast-radius row 3.
    - Covered: one item from a real file · the fixed key surviving a content edit · a **blank** field parsing and staying blank (so the bootstrap can tell *told us nothing* from *never asked*) · zero items with no marker · one row created on import · a **missing** file importing quietly while the rest of the layer still lands · a marker-less file importing nothing · re-import updating rather than duplicating (same uuid, new content, still one row).
    - **Mutation-proved.** Removing the importer block failed exactly the two positive tests and left the two absence tests passing — which is the correct discrimination, since absence behaves identically whether the block exists or not. Restored → 4 passed.
  - **Success Criteria**: **Pass.** Absence, malformity and success are three distinguishable outcomes, and the two failure modes are quiet rather than fatal.
  - **Tech Debts**: None.
  - **Result**: Met. Note the existing fleet fixture ships no `user-profile.md`, so every pre-existing importer test now also exercises the tolerant-absence path and still passes unchanged.

- [x] **Step 2.3**: [Purge and re-import](#phase-2-source-parser-importer)
  - **Implementation Log**: Measured before destroying — 27 agents / 55 shared / 1,399 memory, shared split 27 reasoning + 28 knowledge. Copied to `data/valaskjalf-memory.db.bak-preuserprofile`, removed the db plus its `-wal`/`-shm`, ran `uv run python -m munnin.data_migrations.importer --all`. Backup deleted once the counts were explained, so `data/` still holds the same five pre-existing `.bak-*` files rather than six.
  - **Testing Log**: `agent` **27** (expected 27, OK) · `shared_record` **56** (expected 56, OK) · `memory_record` **1400** (expected 1,399 — investigated below). Shared split is now `knowledge 28, reasoning 27, user_profile 1`. Exactly **one** profile row, uuid `c3b1d18c-ad52-59ba-a6f0-dc1a94511d01`, title `User Profile`, all three markers present in the body. Full suite **254 passed** against the rebuilt database.
    - **The body is 421 bytes against a 422-byte file** — the parser calls `.strip()`, so the trailing newline is not stored. Expected, and checked rather than assumed.
    - **The +1 was traced to a cause, not waved through.** Diffed the rebuilt DB against the pre-purge backup by uuid: **1 added, 0 removed**. The addition is `meta` / `knowledge` / *"Compile Output Filename Schemes"*, and its body file exists on disk at 2,697 bytes with mtime **2026-08-20 20:32** — written by another session *after* the 17:26 import that produced the 1,399 baseline. Real memory arriving, not a defect in this change.
  - **Success Criteria**: **Met in substance.** "No other count moves" holds for everything this plan touches; the one movement is source drift with a named record, a real file and a timestamp that explains it. The criterion was written against a measurement taken hours earlier — the same shape of staleness decision 12 already records, now demonstrated a second time in one plan.
  - **Tech Debts**: None new. The five pre-existing backups (~76 MB) remain the prior plan's logged debt, deliberately untouched rather than swept up here.
  - **Result**: Met. The store now carries the user profile as fleet memory, and every count is either expected or explained.

### Phase 3:
- [x] **Step 3.1**: [The awaken payload](#phase-3-delivery)
  - **Implementation Log**: `awaken()`'s `shared` block gained `user_profile` — the whole record or `None`. Filtered out of the **existing** `query_shared()` fetch with a `next(...)` rather than issuing a second query, so layer i stays one round trip. Docstring rewritten rather than appended: it now names the profile as layer i's third member and states that `None` is a real answer meaning nobody has been asked, which is what triggers the bootstrap, while a blank *field* inside a present record is deliberate and must not.
  - **Testing Log**: 4 new tests. Full suite **258 passed in 52.26s** (254 → 258); `ruff check` clean.
    - `None` when no profile exists · the whole record with its body when one does · **the profile must not leak into `reasoning` or `knowledge`** (three types now share one table and one fetch, so a leak would deliver the profile as a pattern to obey) · **twin parity** across HTTP and MCP, asserting the two payloads are equal rather than each merely non-empty.
    - **Mutation-proved.** Removing the single payload line failed all four, including the parity test on both faces. Restored → 12 profile-named tests pass across the three steps so far.
    - **The additive key broke nothing**, which is blast-radius row 5 confirmed rather than predicted: the suite was green before the new tests were written, so no existing client asserted an exact `shared` shape.
  - **Success Criteria**: **Pass.** Present when it exists, `None` when it doesn't, identical on both faces.
  - **Tech Debts**: None.
  - **Result**: Met. A DB-path client now receives the profile; what it still lacks is the *instruction* to ask for one when it is `None` — that is decision 16's deferral, and Step 3.2 writes the instruction for the markdown path.

- [x] **Step 3.2**: [Seam ops and the first-run ask](#phase-3-delivery)
  - **Implementation Log**: **Two** ops rather than the planned one — `§ load-user-profile` **and** `§ persist-user-profile`. The bootstrap has to write, and writing differs by backend (a markdown file vs a shared insert), so an instruction with only a read op could not say how to store the answer. Markdown: load is *"No action"* (the profile is already in context from the global instructions file), persist writes the bullet form to `shared-memory/user-profile.md` and tells [USER-NAME] the compiled copy is downstream. DB: load reads `shared.user_profile` from the payload, persist is `insert(scope="shared", record_type="user_profile", …)` with no `agent_id`. Component Phase 1 item 2 was **rewritten** to load the profile through the op, with the first-run branch as a blockquote matching the section's existing two — it fires on a missing *record*, never on a missing *value* inside a present one, and names `7b3c5a9d` for why one interactive write is allowed in a read flow. The `# USER PROFILE` section gained two clauses saying the profile is fleet memory and that Phase 1 collects it on the one occasion it does not exist.
    - **Fixed a defect this plan created, rather than logging it.** Widening the CHECK made the `insert` **tool docstring** wrong — it enumerated five record types and said fleet memory "may only be reasoning or knowledge". That string is an MCP tool description, which ships inside a client's system prompt, so a stale one actively misleads. Corrected in `api_mcp/server.py`; `grep` confirmed it was the only place the list is written out. The service layer needed nothing: it deliberately delegates shared-type validation to the schema CHECK, so it composed with the widening for free.
  - **Testing Log**: `--strict` compile clean · control-files **38 passed**, ruff clean · core invariant guard **green** (*"the memory core references no add-on procedure by name"*).
    - All **four** compiled variants (`awaken-agent` and `refresh-memory` × `markdown`/`db`) carry both ops and exactly one first-run branch, with **zero** `## Storage Mechanics` header leaks.
    - Backend separation verified by reading, not counting: the db variant names `shared.user_profile` twice (description + op), the markdown variant once — and that once is the shared *"should already exist"* description that names both paths, while its own op correctly reads **"No action."**
    - Awakening set still **4** files — the 5→4 reduction earned when the protocol became a component is intact.
  - **Success Criteria**: **Pass.** Both compiled callers carry the ops on both backends and no seam header leaked.
  - **Tech Debts**: None of mine. **Found**: `procedures/output/awaken-agent.md` was **not** regenerated by this compile (still Aug 20, 8,607 B) while the `.markdown.md`/`.db.md` pair refreshed — the default dual preview and `--backend db` write different filenames into the same directory. Pre-existing and harmless here because Munnin's `ContentLoader` reads live from source, never from `output/`. It is exactly the trap agent-meta banked as knowledge at 02:48 today, and checking mtimes instead of the exit code is what surfaced it.
  - **Result**: Met, with the op count corrected from one to two for a reason found in implementation rather than assumed in planning.

### Phase 4:
- [x] **Step 4.1**: [Reorder the orchestrator; retarget the profile script; strip the public template](#phase-4-configurator-and-docs)
  - **Implementation Log**: `user-config-claude.sh` now runs **environment first, profile second**, with the reason written where the order lives: the profile is stored privately and learns *where* privately is from the file the first script writes. `user-profile-claude.sh` reads `[AGENT-MEMORY-PATH]` out of the env output with a `sed -n …p` (prints only on a match), converts it via `cygpath` when present, and refuses with a non-zero exit if the value is unset or the target has no `shared-memory/` — it will not guess a location for private values. Its source of truth is `[AGENT-MEMORY-PATH]/shared-memory/user-profile.md`; it then **materializes** `core-memory/output/0-core-user-profile.md` from it, which is [USER-NAME]'s decision A: `output/` is gitignored and already understood as derived runtime state, so `compile.sh` needs no change and the values stay out of the tracked tree. The current-value reads were rewritten from `grep | sed 's///'` to `sed -n 's///p'` — the old form **echoed the whole line back when it failed to match**, which would have offered an unmatched line as a keep-this default. `0-core-user-profile.md` reduced to empty placeholders with a comment saying where the real values live.
  - **Testing Log**: Ran the retargeted script with all three prompts left blank — it read the existing values from the private store, showed them as defaults, wrote the private file, and refreshed the derived copy **byte-identical** (`diff -q` clean, 422 B).
    - **The live check ran, and passed.** `compile.sh` produced `core-memory-compiled.md` (11,738 B) against the live `CLAUDE.md` (11,886 B), and the **full diff is exactly two lines** — both the overlay's own `[path-to-agent-memory-coding-skill]` definition, which the core compile has never owned. The profile block and every other byte match. The permanent layer does not move while its source has.
    - `CLAUDE.md` verified **unchanged** by md5 before and after: `e40f053f864acadf3ddb9c314238bf39`, 11,886 B both times.
  - **Success Criteria**: **Pass.** Source moved, permanent layer identical.
  - **Tech Debts**: The tracked env template still carries `C:\Work\research\agent-memory\`, which resolves to nothing on this machine (PowerShell: `C:\Work\research` absent; the real store is `C:\Work\IM\@agent-memory`, with `.claude\@agent-memory` a **Junction** to it). Fixed *for this checkout* by copying the working `output/1-core-environment-memory.md` across, at [USER-NAME]'s request. The public template is untouched and remains env's problem, not this plan's.
  - **Result**: Met — plus a hazard found by accident. `compile-write-to-claude.sh` **hung** on `write-to-claude.sh`'s own prompt after compiling, so nothing was written. That was lucky: writing the core-compiled output alone would have **dropped the overlay's path definition**, which 38 installed overlay commands resolve through. The core and overlay installers have to run as a pair; running the core's write step alone leaves the overlay broken until the other follows.

- [x] **Step 4.2**: [Documentation](#phase-4-configurator-and-docs)
  - **Implementation Log**: **`db.md`** — `shared.user_profile` joined the payload list with its `null`-means-first-run semantics, and the *"not covered by the payload"* note now holds only the awakening instructions, saying outright that the profile used to be listed there and is now a record like any other. **`awaken-db.md`** — six regions: the sequence diagram's `query(agent_id="__shared__")` → `query_shared()`, the reply arrow, the payload braces, step 3 rewritten whole, the `validate_domain` note, and the importer sentence. The only surviving `__shared__` is the sentence stating the sentinel is gone. **Arch doc §3.2** — rewritten under [USER-NAME]'s call (option B): retitled *"Three tables: one entity, two kinds of memory"*, carrying all three DDLs, the composite FK, the `PRAGMA foreign_keys = ON` hazard and why the schema and repository tests are kept apart, two browse indexes, two FTS indexes with the per-corpus bm25 cost, the three-value CHECK, and a paragraph on `user_profile` including why it is not auth identity. The *"Blobs in SQLite"* paragraph was corrected too — it argued "one table stays fast", which now reads as a claim about the entity split; it is about blob separation and now says so.
  - **Testing Log**: `shared_record` mentions in the arch doc **0 → 5**; `user_profile` **0 → 4**; the stale `agent_id … | 'shared'` comment **gone**; heading structure intact (`3.1`, `3.2`, then the four `####` subsections unchanged). `grep` for `__shared__` across all three documents returns only the deliberate "it is gone" sentence.
  - **Success Criteria**: **Pass.** All three describe the system as built, with no sentence surviving from either prior era.
  - **Tech Debts**: None new.
  - **Result**: Met — and larger than planned. The step was written as "amend §3 for the sixth type and the widened CHECK", which turned out to be impossible: §3 contained no `shared_record` and no CHECK, because the agent-entity plan's Step 5.2 scoped the **caller-path table**, not the schema section. Surfaced rather than papered over, and [USER-NAME] chose the full rewrite for the same reason he chose it for `awaken-db.md`.

---

### Phase 5:
- [~] **Step 5.1**: [Prove the first-run ask against a real awakening](#phase-5-field-test) — **PARTIAL, and the remainder is not mine to run**
  - **Implementation Log**: Exercised the three payload states against the **live** store rather than a fixture: read the profile, soft-deleted the record, read again, re-imported from markdown, read again.
  - **Testing Log**: baseline **PRESENT (421 B)** → after removal **None** → after re-import **PRESENT (421 B)**, **same uuid**, `query_shared` count still exactly **1**. So absence yields `None` rather than a raise or a missing key, restoration is idempotent, and no duplicate row appears.
  - **Success Criteria**: **Partial.** The *data* condition the bootstrap keys off is proven in all three states. The *behaviour* — asks once on absence, silent on presence, silent on a deliberate blank — is **not** proven and cannot be from here.
  - **Why not, plainly**: the instruction lives in a compiled command that has not been installed, and my own awakening protocol was loaded at session start, before these edits existed. "Awaken and observe whether it asks" requires a **fresh session reading the installed instruction** — which is something [USER-NAME] starts, not something a running agent can do to itself. Installing the core alone is also unsafe until the overlay installer runs beside it (Step 4.1's result explains why).
  - **Tech Debts**: **The behavioural field test is outstanding**, and decision 14 exists precisely so this is not quietly filed as done. It is not a fourth "never run" item by default — it has a named, ordered path: commit both repos → run the core **and** overlay installers as a pair → open a fresh session → `/awaken-coder meta` with the profile record removed → observe one ask, answer it, awaken again, observe silence.
  - **Result**: Honest partial. The half a running session can prove is proven against real data; the half it cannot is stated as outstanding with the exact steps to close it, rather than substituted with a test that would have passed without meaning anything.

---

## **QUALITY REVIEW**
*Filled by procedure Step 16 (delegated to `/analyze-code-quality` in embedded mode) after all execution phases are complete. **Static** review — answers "is the code clean?".*

- **Scope**: 20 files across three trees — Munnin (6 source, 5 test, 1 flow doc), control-files (6), the private store (2). **Reconciled against `git diff`**: the only extras on disk are the `control-files` submodule gitlink and the staged deletion of the abandoned 08-14 plan, neither of which is reviewable content; the store also carries `agent-mentor/knowledge-base/coding-test-syntax-cheatsheet.md`, which belongs to another session and is out of scope. Nothing in the Execution Log is missing from the diff — `shared-memory/user-profile.md` shows as untracked-new because it is new.
- **Quality Standard**: none found (`quality-standard.md` absent from both repos) — freeform analysis, Dimension 8 skipped. Dimensions 2 and 3 (UI state / UX flows) do not apply to this scope.
- **Findings**: 2 Medium, 2 Low.

| # | Severity | File:Line | Issue | Fix Options |
|---|----------|-----------|-------|-------------|
| 1 | Medium | `schema.sql` (shared_record) + `memory_service.py:awaken` | **Nothing prevents two `user_profile` rows.** Proven, not theorised: inserting a second row leaves both in place, and `awaken`'s `next(...)` silently returns the first. Decision 6 justifies one record on the grounds that *"presence is answered by a row count"* — but if the count can exceed 1, the first-run check is satisfied by whichever profile happens to sort first, and a wrong one persists invisibly. The importer cannot cause this (its uuid is derived from a fixed key); a manual `insert(scope="shared", record_type="user_profile")` can. | A) Partial unique index: `CREATE UNIQUE INDEX … ON shared_record(user_id) WHERE record_type='user_profile' AND deleted_date IS NULL` — the schema is already this codebase's stated single enforcer of what fleet memory may contain B) Reject the second insert in `MemoryService.insert` C) Have `awaken` raise on >1 |
| 2 | Medium | `user-profile-claude.sh:7-8` | **The header comment contradicts the body.** It still reads *"Writes core-memory/output/0-core-user-profile.md (the runtime file compile.sh prefers over the template)"* — which is now only the derived half. The file's whole point is that the private store is the source of truth, and the first thing a reader sees says otherwise. | A) Rewrite the header to describe both writes and name the private store as the source B) Leave it |
| 3 | Low | `user-profile-claude.sh` (write block) | **A failed write still reports success.** Neither `cat > "$USER_PROFILE_FILE"` nor the follow-up `cp` is checked, and the script has no `set -e`, so a permission or disk failure still prints `✓ User profile saved`. Low because the paths are validated first, but this is the one place the script can lie. | A) Check both writes and exit non-zero with the failing path B) Leave it |
| 4 | Low | `markdown_parser.py:parse_shared_profile` | Body is stored as `text.strip()`, so the record is 421 B against the file's 422 B. Harmless and deliberate, but it means any future byte-comparison of store-vs-file needs the same strip, and nothing says so. | A) Note it in the docstring B) Leave it |

- **Fixed**: all four, defaults accepted.
  1. **Partial unique index** `idx_one_user_profile_per_tenant ON shared_record(user_id) WHERE record_type='user_profile' AND deleted_date IS NULL`. Verified three ways: a second profile now raises `UNIQUE constraint failed`; reasoning and knowledge still accept many rows (it is partial, not blanket); and a second *tenant* may still have their own. **Three tests added and mutation-proved** — removing the index fails exactly `test_only_one_user_profile_per_tenant` and leaves the other fourteen passing, which is the right discrimination since those assert what remains *allowed*.
  2. **Script header rewritten** to name both writes and mark the private store as the source and `output/` as derived — plus why `[AGENT-MEMORY-PATH]` is read rather than derived.
  3. **Both writes now checked**; a failed `cat >` or `cp` exits non-zero naming the path, and the `cp` failure message says the global instructions file still carries the previous values.
  4. **`parse_shared_profile` docstring** records the `strip()` and warns that a store-vs-file byte comparison needs the same strip on both sides.
- **Verification after fixes**: full suite **261 passed** (258 → 261), `ruff check` clean, and the configurator re-run end to end with the derived copy still byte-identical to its source.
- **Worth keeping — my verification was wrong before the code was.** I first reported the index as absent from the live database. It wasn't: `_conn()` applies the schema on the first **connection**, and merely constructing a repository opens none, so my probe tested nothing. Re-checked through a real operation and the index was there. Eighth check of this lineage to test for something the artifact never contained.

---

## **QA HANDOFF**
*Filled by procedure Step 17 after Quality Review is resolved. This plan is **not** runtime-verified — this section records the plan for that verification, which happens in a QA session with the stack up.*

- **Scope**: the store schema and its constraints · the shared-memory parser and importer block · `awaken`'s layer-i assembly and both faces · the awakening component's first-run bootstrap and its four seam ops · the configurator pair and the compile pipeline's profile input.
- **QA instrument**: **NOT SET UP — auto-skipped.** `qa/` exists with its P6 structure (`checklists/`, `config/`, `fixtures/`, `runbooks/`, `scripts/`) but there is **no `qa/qa-map.md`** and no built bench. I verified this precondition directly rather than delegating to a command whose documented behaviour on a missing map is to notify and skip; the outcome is the same and the check is visible here.
- **Checklist**: none — skipped for the reason above. Setting the instrument up is `/map-qa-instrument create` → `/build-qa-bench`, and that is a separate job from this plan.
- **Coverage split**: **19 automated** across five modules — 5 schema/constraint (3 of them the new profile-limit tests), 4 parser, 4 importer, 4 awaken/service, 1 twin-parity, plus the two pre-existing shared-type guards that now also cover the widened CHECK. **1 manual, and it is the important one**: the first-run bootstrap. None are UI-bound.
- **Runtime verification**: **NOT DONE.** The one manual item cannot be automated *or* run from inside a session — it needs a fresh agent reading the installed instruction. Next action, in order: commit all three trees → run the core **and** overlay installers as a pair (never the core alone, per Step 4.1's result) → open a fresh session → remove the `user_profile` row → `/awaken-coder meta` → expect exactly one ask, answer it, awaken again, expect silence, then blank a field and confirm it is not re-asked.

> Do not read a filled checklist as a passed one. This section says a verification *plan* exists, nothing more.

---

## **POST-COMPLETION**
After all phases are executed, logged, and both **Quality Review** + **QA Handoff** are filled, move this plan to `plans/completed/`:
`mkdir -p ./plans/completed && mv ./plans/[this-file].md ./plans/completed/[this-file].md`
