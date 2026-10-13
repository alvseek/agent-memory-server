# Quick Wizard Plan: Awaken Goes Project-Blind

## Inherited Context
*Settled before this plan existed; not mine to reopen.*

**From the parent plan**
- **Parent plan**: None — not a sub-plan. Sibling to [2026-10-13-agent-memory-server-awaken-time.md](2026-10-13-agent-memory-server-awaken-time.md), which records this piece as agreed first and whose technical-core round this overtakes.

**From pre-planning discussion**
- **Discussion**: Pre-planning discussion with Alvi, 2026-10-13, same session.
- **Agreed scope**: `awaken` stops accepting a project at all.

| # | Settled decision | Chosen | His reason | Status |
|---|------------------|--------|------------|--------|
| 1 | The `project` parameter | Removed outright | *"the very first thing to do is to remove that project parameters from Munnin"* |
| 2 | Scope | The Munnin tree: src, tests, comments, and the served text in `control-files` | Chosen as option A after the served sentence was located |
| 3 | `latest_episode` | Kept, now the newest overall | Technical-core round, option A |
| 4 | Deploy | In this plan, verified live | Integration round, option A |
| 5 | Harness cleanup (uninstall the installed copies) | Out — its own piece | *"we should even uninstall it no?"* / scope round, option B |

- **Considered and rejected**: recompiling and reinstalling the installed commands (perpetuates the markdown copies); an accept-and-ignore tombstone for `project` (an undeclared argument is already ignored, probed 2026-10-13); dropping `latest_episode` from the payload (adds a `get(uuid)` to a design whose purpose is fewer calls); changing the overlay (it already selects from the index and already calls the core project-blind).

## Objective
Make `awaken` project-blind: the tool takes a domain and returns the memory set, and the caller selects the episode. The change is a deletion that makes the code agree with its own flow doc and with `ARCHITECTURE.md:283` (*"Project is a coding concept; a chat agent using the core alone is project-blind"*).

## Confirmed Decisions

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | The parameter | Removed from the service, the MCP tool and the HTTP route | An undeclared argument is already ignored on this call path (probed), so a tombstone buys nothing; code and text change in one commit |
| 2 | `latest_episode` | Kept, now the newest overall | Its own `project` field still tells a caller whether it is the one wanted; dropping it would cost a round trip |
| 3 | `_episode()` projection | Unchanged | It is what lets a caller tell a matched episode from the fallback |
| 4 | The repository `project` filter and the corpus boundary | Untouched | Other reads and the boundary depend on them; only `awaken`'s parameter goes |
| 5 | Served text | `storage-backends/db.md` § load-agent-memory, same pass | A stale instruction fails silently on the carry-forward, the one thing an awakening is for |
| 6 | The overlay | Not touched | `awaken-coder.md:38` already selects from the returned index and already calls the core project-blind |
| 7 | Plan location | `plans/` in `agent-memory-server` | The cwd is `hermod-deploy`; the work lands in the memory server, and the wrap-up files it there |

## Success Criteria
- [x] `awaken` declares no project on the service, the MCP tool or the HTTP route; `_select_latest` is gone — verified in the diff and live (`awaken(domain: string)` is what the served schema now shows)
- [x] A test asserts `latest_episode` is the newest episode overall regardless of its `project` — `test_awaken_latest_episode_is_the_newest_overall`, green
- [x] The whole suite is green — 531 passed, 24 skipped
- [x] The served `§ load-agent-memory` no longer instructs passing a project — read back live after the deploy, both `awaken(domain, project)` and `&project=` absent
- [x] Deployed, and verified live — deploy run `38395324661` succeeded; one `awaken` call returned `latest_episode` = `b855f155…`
- [x] `qa/checklists/awaken-project-blind.md` built

**Not met, and recorded rather than hidden**: main's CI is red for an unrelated stale expectation (`tests/test_postgres_migrations.py` still lists two migrations where the repo has three), and this plan's runtime verification is a written checklist that has not been run.

## Execution Steps
1. **Service** — `src/munnin/business_services/memory_service.py`: `def awaken(self, domain: str)`; delete `_select_latest` (57-70); `latest = episodes[0] if episodes else None`; rewrite the docstring paragraph at 138-143 to say the newest episode overall is returned and the caller selects. → verify: `pytest tests/business_services/test_awaken.py` (crosses: DB — the suite's repository fixture)
2. **Faces** — `src/munnin/api_mcp/server.py:120-129` and `src/munnin/api_http/api.py:175-186`: drop the parameter and the docstring sentence that promises scoping. → verify: `pytest tests/api_http/test_awaken_faces.py` (crosses: DB)
3. **Tests** — delete `test_awaken_scopes_latest_episode_to_project` (`tests/business_services/test_awaken.py:157-178`); add an assertion that the newest overall wins with episodes from several projects present; restate the reasons that cite `awaken`'s selection at `tests/data_repositories/test_repository_contract.py:141-144` and `src/munnin/data_repositories/sqlite_memory_repository.py:377-381`. → verify: full `pytest`
4. **Served text** — `control-files/procedures/memory/storage-backends/db.md:161-163`: drop *"Pass the current project so `latest_episode` is scoped to it"* and the `&project=` from the HTTP signature; state that the caller selects from the returned index by `project` and fetches by uuid when the newest overall is not the one wanted. → verify: `control-files/tests/test_compile_procedures.py`, then read the file back
5. **Commits** — commit inside the `control-files` submodule (`agent-memory-system`), bump the gitlink in the product, commit the product. → verify: `git status -sb` clean, `git submodule status` shows the new pointer
6. **Deploy and verify live** — dispatch the Munnin release from `munnin-deploy`, then read `§ load-agent-memory` back over `read_procedure` and call `awaken` once, checking `latest_episode` is the newest overall. → verify: both reads above (crosses: production HTTP)
7. **QA handoff** — build `qa/checklists/awaken-project-blind.md` with `/generate-qa-checklist`; the instrument exists (`qa/qa-map.md`, `qa/runbooks/munnin.md`, `qa/scripts/start-server.sh`).

## Execution Log
*2026-10-13, one session, in order.*

- **Steps 1-3** — 10 edits applied through a script with a per-edit match assertion and a guard that refuses if `_select_latest` is referenced anywhere else (`all edits applied`, every file `compiles`). Focused tests 25 passed / 12 skipped; **full suite 531 passed, 24 skipped**.
- **Step 4** — `storage-backends/db.md`: two lines changed (the call + the HTTP signature, and the `latest_episode` bullet). `control-files` compile test: 25 passed.
- **Step 5** — `control-files`: commit `0acc6b8`, push **rejected** (upstream had moved), rebased onto `29e4212` (a Codex uninstaller landing in the same submodule) and pushed as `5bb5185`. Product: `605db45` (code, tests, gitlink), then `e0e3a8a` (gitlink bumped to `5bb5185`, plus both plan files).
- **Failure found and fixed in this step** — the first push pointed the gitlink at `0acc6b8`, which the rebase had replaced and which was never on the remote, so the image build died at `actions/checkout` with *"remote error: upload-pack: not our ref 0acc6b8…"*. Fixed by the rebase and the bump; the `e0e3a8a` build succeeded (run `38395132492`).
- **CI on `e0e3a8a` failed, and not from this change** — `tests/test_postgres_migrations.py:33` still expects `["0001_init", "0002_record_content_summary"]` while the repo now carries `0003_shared_record_coding_reasoning`. That expectation belongs to the coding-reasoning lane's piece; left untouched and recorded here.
- **Step 6** — deploy dispatched `version=e0e3a8a command=deploy`, run `38395324661`, **success**. Verified live: the served `awaken-agent` no longer contains `awaken(domain, project)` nor `&project=`; the live tool schema reads `awaken(domain: string)`; a call returns the same eight keys with `latest_episode` = `b855f155…` (project `agent-memory-project`, the newest overall); and passing `project="hermod-deploy"` is ignored, returning that same episode.

## Quality Review
*Step 7, `/analyze-code-quality` in embedded mode. **Static** review: "is the code clean?"*

- **Scope**: `src/munnin/business_services/memory_service.py`, `src/munnin/api_mcp/server.py`, `src/munnin/api_http/api.py`, `src/munnin/data_repositories/sqlite_memory_repository.py`, `tests/business_services/test_awaken.py`, `tests/data_repositories/test_repository_contract.py`, `control-files/procedures/memory/storage-backends/db.md`. Reconciled against the range `984e09d..HEAD`: the diff adds only the submodule gitlink and the two plan documents, both recorded in the Execution Log, and nothing logged is missing.
- **Quality Standard**: not found — no `quality-standard.md` in this repo (globbed 2026-10-13); dimension review freeform, Dimension 8 skipped.
- **Checks that ran**: `ruff check` clean on all six Python files; no leftover reference to `_select_latest` or to an `awaken(..., project...)` call anywhere in `src` or `tests`; `ruff format --check` flags 4 of the 6 files, but every flagged line is pre-existing and outside this change (42 of 85 files repo-wide are unformatted), so formatting is not a gate here and nothing was changed for it.
- **Findings**: two, both Low.

| # | Severity | File:Line | Issue | Fix Options |
|---|----------|-----------|-------|-------------|
| 1 | Low | `control-files/procedures/output/awaken-agent.db.md:115`, `output/refresh-memory.db.md:118` | The local compiled previews still show `awaken(domain, project)`. Gitignored, not shipped, and the live server does not read them (verified after the deploy). | A) Refresh them by running `compile-procedures.py`. B) Leave them; they are generated and ignored. |
| 2 | Low | `control-files/docs/flows/awaken-db.md` | Entry-point references are stale: it cites `server.py:27` and `api.py:47` where the tool is at `server.py:120` and the route at `api.py:175`. The same doc also says `awaken-agent` is not served, which reads false beside the `read_procedure` that serves it, though I did not verify which sense of "served Prompts" it means. | A) Correct the two references and that sentence. B) Leave it; pre-existing and outside this change. |

- **Fixed**: both Low findings, in one pass. (1) The compiled previews were refreshed by running `procedures/setup-scripts/compile-procedures.py`; no `awaken(domain, project)` remains in `procedures/output/` or `procedures/output-inline/`, and `awaken(domain)` is present at `output/awaken-agent.db.md:115`. (2) `docs/flows/awaken-db.md`: the Entry references corrected to `server.py:120` and `api.py:175`, the Validate reference corrected to `memory_service.py:110` (the same defect, one line below, fixed with it and disclosed), and the "not served" sentence replaced with what is true: the process is served as a procedure and the instruction component is inlined into it.
- **Recorded decisions, not findings**: an extra `project` argument is silently ignored (technical-core round, option A, known when taken, and the served text was corrected in the same pass); `latest_episode` staying as the newest overall (technical-core round, option A).

## QA Handoff
- **Scope**: `memory_service.awaken`, both adapter faces, `control-files` served text
- **QA instrument**: Set up — `qa/qa-map.md` present and the bench built (all four R/I/A/O phases documented and promoted 2026-08-21)
- **Integration coverage**: steps 1-3 cross the DB and are covered by the unit suite through the repository fixture (531 passed); step 6 crosses production HTTP and was verified live against the deployed server
- **Checklist**: [qa/checklists/awaken-project-blind.md](../../qa/checklists/awaken-project-blind.md) — 19 checks: 5 backed by named automated tests, 14 manual, none UI-bound (a server API has no UI binding). It is written and **not yet run**.
- **Runtime verification**: **NOT DONE** as a bench run. Next action: `/run-qa-test --checklist qa/checklists/awaken-project-blind.md` with the stack up, started by `qa/scripts/start-server.sh` after `reset-db.sh` + `seed-meta.sh`.
- **Known gap found while building this**: `qa/checklists/qa-checklists-map.md` is stale — last scanned 2026-08-21, it lists one checklist where ten now exist. That map belongs to `/build-qa-test`, and a one-row patch would imply the rest is current, so it was left for a rescan rather than edited here.
