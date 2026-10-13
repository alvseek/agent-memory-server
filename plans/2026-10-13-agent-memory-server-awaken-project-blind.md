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
- [ ] `awaken` declares no project on the service, the MCP tool or the HTTP route; `_select_latest` is gone
- [ ] A test asserts `latest_episode` is the newest episode overall regardless of its `project`
- [ ] The whole suite is green (`pytest`), including the faces test and the repository contract test
- [ ] The served `§ load-agent-memory` no longer instructs passing a project
- [ ] Deployed, and verified live: the served text read back and one `awaken` call returning the newest episode overall
- [ ] `qa/checklists/awaken-project-blind.md` built

## Execution Steps
1. **Service** — `src/munnin/business_services/memory_service.py`: `def awaken(self, domain: str)`; delete `_select_latest` (57-70); `latest = episodes[0] if episodes else None`; rewrite the docstring paragraph at 138-143 to say the newest episode overall is returned and the caller selects. → verify: `pytest tests/business_services/test_awaken.py` (crosses: DB — the suite's repository fixture)
2. **Faces** — `src/munnin/api_mcp/server.py:120-129` and `src/munnin/api_http/api.py:175-186`: drop the parameter and the docstring sentence that promises scoping. → verify: `pytest tests/api_http/test_awaken_faces.py` (crosses: DB)
3. **Tests** — delete `test_awaken_scopes_latest_episode_to_project` (`tests/business_services/test_awaken.py:157-178`); add an assertion that the newest overall wins with episodes from several projects present; restate the reasons that cite `awaken`'s selection at `tests/data_repositories/test_repository_contract.py:141-144` and `src/munnin/data_repositories/sqlite_memory_repository.py:377-381`. → verify: full `pytest`
4. **Served text** — `control-files/procedures/memory/storage-backends/db.md:161-163`: drop *"Pass the current project so `latest_episode` is scoped to it"* and the `&project=` from the HTTP signature; state that the caller selects from the returned index by `project` and fetches by uuid when the newest overall is not the one wanted. → verify: `control-files/tests/test_compile_procedures.py`, then read the file back
5. **Commits** — commit inside the `control-files` submodule (`agent-memory-system`), bump the gitlink in the product, commit the product. → verify: `git status -sb` clean, `git submodule status` shows the new pointer
6. **Deploy and verify live** — dispatch the Munnin release from `munnin-deploy`, then read `§ load-agent-memory` back over `read_procedure` and call `awaken` once, checking `latest_episode` is the newest overall. → verify: both reads above (crosses: production HTTP)
7. **QA handoff** — build `qa/checklists/awaken-project-blind.md` with `/generate-qa-checklist`; the instrument exists (`qa/qa-map.md`, `qa/runbooks/munnin.md`, `qa/scripts/start-server.sh`).

## Quality Review
- **Scope**: [filled by Step 7]
- **Quality Standard**: not found — no `quality-standard.md` in this repo (globbed 2026-10-13); dimension review is freeform
- **Findings**: [pending]
- **Fixed**: [pending]

## QA Handoff
- **Scope**: `memory_service.awaken`, both adapter faces, `control-files` served text
- **QA instrument**: Set up — `qa/qa-map.md` + runbooks + scripts are present. Stack state to be read with `/qa-status` at the top of execution.
- **Integration coverage**: steps 1-3 cross the DB (unit-tested through the repository fixture); step 6 crosses production HTTP (verified live). If the local stack is down, steps 1-3 ship with unit coverage only — to be confirmed before execution.
- **Checklist**: [pending Step 7]
- **Runtime verification**: **NOT DONE.** Next action: `/run-qa-test --checklist qa/checklists/awaken-project-blind.md` once the stack is up.
