# Quick Wizard Plan: Server instructions, `help`, tool annotations, and the `<domain>` sentence (launch-map step 4)

## Inherited Context

**From the parent plan**
- **Parent plan**: None — not a sub-plan. The governing document is the Munnin Launch Map (artifact `5a8f647a`), step 4, and `shared-memory/agent-memory/context/munnin-launch-plan.md`.
- **Assigned scope**: N/A
- **Inherited decisions**: N/A
- **Contracts / pushed-down items**: None

**From pre-planning discussion**
- **Discussion**: Pre-planning discussion, 2026-09-01 (the launch-map audit and this session's step-3 close).
- **Agreed scope**: (1) `FastMCP(..., instructions=…)` returned at `initialize`; (2) a read-only `help()` tool returning the same text plus `list_procedures()`; (3) `title` + `readOnlyHint`/`destructiveHint` on every tool; (4) one sentence in `db.md` saying what `<domain>` is. Done when a real client's `initialize` result carries the instructions, `tools/list` shows a title and hints on every tool, and `read_procedure("update-episodic")` carries the sentence.
- **Settled decisions**:
  - `instructions` stays short → Settled (permanent-layer text, re-sent every call of every session).
  - `help` is read-only and returns the instructions plus the procedure list → Settled.
  - `soft_delete`, `archive` and the edits are destructive → Settled.
  - The `<domain>` sentence is the answer to the `select_agent` idea: the domain lives in the agent's context, not in server state → Settled.
- **Considered and rejected**: a `select_agent` tool (server-side session state) — MCP calls are stateless and every write already names `agent_id`.

## Objective

Give a stranger who connects to Munnin something to act on before they have read anything: the server says what it is and what to call first, every tool declares what it does to the store, and every served procedure says what `<domain>` means.

## Confirmed Decisions

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | Where the `<domain>` sentence lives | A backend **preamble section** `## all-procedures` in `db.md`, prepended by `compose_backend_section` for every procedure when the backend defines it | `db.md` has no section every procedure gets; the requirement is "every procedure", which is a mechanism by definition (`2d6234a4`). The composer already has this shape for components. `markdown.md` defines no such section, so installed commands stay byte-identical. |
| 2 | The sentence's wording | *"`<domain>` in the ops below is the agent you are acting as — the domain you passed to `awaken`, or the one `create-agent` made. With no awakening, `list_agents()` shows what exists; never guess one."* | The artifact's "pass it as `argument`" is true for only 2 of 12 procedures (`loader.py:76`); for the rest `argument` is a mode or keyword. Surfaced as an inherited wording that looked wrong; [USER-NAME] accepted the correction. |
| 3 | The `instructions` text | [USER-NAME]'s wording, verbatim (see Step 1) | His edit: "agent identity — an agent's memory of reasoning patterns, emotional moments, episodes and knowledge". ~90 words, ~120 tokens per call. |
| 4 | Deploy after landing | **Pin only, no deploy** | Same as the last three pins; the done-when is provable locally against a real client; a production change becomes its own step before the blank-tenant walk. |
| 5 | `help` gets no HTTP twin | No | The HTTP face has no `initialize` and its callers are servers reading the README; a 19th `/api` operation would be size with no reader. `EXPECTED_OPERATIONS` stays 18. |
| 6 | `help` registered without served content | Yes — always registered; lists procedures only when content is available | It is the fallback for clients that ignore `instructions`, so it must exist in every configuration. Bare surface 14 → 15, full 18 → 19; the two pins move with a reason, which their docstrings ask for. |
| 7 | Where `INSTRUCTIONS` lives | A module constant in `api_mcp/server.py`, read by `FastMCP(...)` and by `help` | One home, two readers, both in the MCP face; nothing else needs it. |
| 8 | Annotation set | read-only: `ping`, `awaken`, `get`, `query`, `search`, `list_agents`, `list_procedures`, `read_procedure`, `list_resources`, `read_resource`, `help` · additive (`readOnlyHint=false, destructiveHint=false`): `insert`, `create_agent`, `append`, `prepend` · destructive: `edit`, `multi_edit`, `archive`, `soft_delete` (the last two also `idempotentHint=true`) · `openWorldHint=false` on all | The spec's semantics: `destructiveHint` is meaningful only when not read-only and defaults to true, so the additive writes must say false explicitly. The store is closed, so `openWorldHint` is false everywhere. |
| 9 | Titles | Human names per tool (e.g. "Awaken an agent", "Soft-delete a record"), authored beside each registration | A title is what a picker shows; the name is what an agent types. Both stay. |

## Success Criteria
- [ ] A real client's `initialize` result carries `instructions` equal to the constant, byte for byte
- [ ] `tools/list` shows a `title` and `readOnlyHint` on all 19 tools, `destructiveHint` explicitly on every non-read-only one, and `openWorldHint=false` on all
- [ ] `help()` returns the instructions plus the 13 procedure rows; with no served content it returns the instructions plus an empty list
- [ ] `read_procedure("update-episodic")` — and every other seam procedure — carries the `<domain>` sentence; `wait-options` (no seam) does not
- [ ] Installed **markdown** commands are byte-identical before and after (the framework's own compile test + Munnin's markdown fidelity test)
- [ ] Unit tests written and passing for every step with testable logic (or the step says why it has none)
- [ ] Static quality review completed (Step 7 — delegated to `/analyze-code-quality`)
- [ ] QA Handoff completed (Step 8 — checklist built, or auto-skipped with reason recorded)

## Execution Steps

1. **Framework: the preamble mechanism** (`control-files`, on a branch from `origin/main`): in `procedures/memory/storage-backends/seam.py`, `compose_backend_section` prepends `extract_section(doc, "all-procedures")` when the backend defines it, ahead of the procedure's own section; the docstring says why. Add `## all-procedures` to `db.md` with the sentence from decision 2, before `## update-episodic`. Test in `tests/test_compile_procedures.py`: a backend with the section yields it first for two different procedures; a backend without it (the markdown one) compiles unchanged — assert on the real `markdown.md` output of `update-episodic` against its pre-change bytes. → `uv run pytest` in `control-files` green; `python procedures/setup-scripts/compile-procedures.py` strict compile green; commit, push, note the SHA.

2. **Munnin: pin the framework** — `git -C control-files checkout <sha>`, run Munnin's suite: `tests/content/test_markdown_fidelity.py` must still pass untouched (markdown side unchanged), and a new test in `tests/content/test_content_loader.py` asserts the sentence in `get_prompt("update-episodic")` and in `get_prompt("wrap-up")`, and its absence from `get_prompt("wait-options")`. → both assertions green.

3. **`instructions` + `help`** (`src/munnin/api_mcp/server.py`): `INSTRUCTIONS` constant with decision 3's text; `FastMCP("munnin", instructions=INSTRUCTIONS, auth=auth)`; a `help` tool registered in `build_mcp` (not in `_register_content`) returning `{"instructions": INSTRUCTIONS, "procedures": [...]}` — rows from `content.list_prompts()` when content is available, else `[]`. Tests in `tests/api_mcp/test_content_tools.py`: `initialize` result's `instructions` equals the constant (FastMCP `Client` exposes `client.initialize_result`); `help` with and without content. Move the 14/18 pins in `test_twin_parity.py::test_tool_surface_is_the_documented_size` and the bare/full sets in `test_content_tools_present_only_with_content` to 15/19 with `help` in the bare set. → green.

4. **Annotations on every tool** (`server.py`): `annotations={...}` per decision 8 and `title=` per decision 9 on each `@mcp.tool(...)` (the decorator takes both — verified against `FastMCP.tool`'s signature in the installed 3.4.6). New test `tests/api_mcp/test_tool_annotations.py`: every tool in `tools/list` has a non-empty `title` and a non-`None` `readOnlyHint`; every tool with `readOnlyHint=False` has an explicit `destructiveHint`; the destructive set equals `{edit, multi_edit, archive, soft_delete}`; `openWorldHint is False` for all. → green; `ruff check` clean.

5. **Prove it on a real client, locally** — `MUNNIN_AUTH=off uv run python -m munnin` on 8201, then a FastMCP `Client` over TCP: read `initialize_result.instructions`, `list_tools()` titles/hints, `help()`, `read_procedure("update-episodic")` for the sentence. → the four done-when facts read off the wire, then stop the process.

6. **Docs** — `docs/README.md`: "18 tools" → 19 in the two places it appears, `help` added to the served-content group, the *Planned before the hosted demo* debts list loses its `instructions`/`help`/annotations item, `db.md`'s sentence mentioned under Served content. `README.md`: "18 tools" does not appear — no change. → grep for `18 tools` returns nothing.

7. **Commit and pin** — Munnin commit with a pathspec (server, tests, docs, plan, the submodule pointer); push; `munnin-deploy` pin bump "(no redeploy)"; push; verify both with `git ls-remote`. Move this plan to `plans/completed/`. → remote heads equal local.

No step crosses a boundary the unit tests would have to double: the store is SQLite in `tmp_path`, the served content is the checked-out submodule, and the MCP client runs in-process. Step 5 uses TCP deliberately, as proof rather than as a test.

## Quality Review
*Filled by Step 7 (delegated to `/analyze-code-quality` in embedded mode). **Static** review — answers "is the code clean?".*

- **Scope**: reconciled against `git diff --name-only` with no discrepancy — Munnin: `src/munnin/api_mcp/server.py`, `tests/api_mcp/test_content_tools.py`, `tests/api_mcp/test_tool_annotations.py` (new), `tests/test_twin_parity.py`, `tests/content/test_content_loader.py`, `docs/README.md`, this plan, the `control-files` pointer; framework (`agent-memory-system@28a5a34`): `seam.py`, `db.md`, the seam contract `README.md`, `compile-procedures.py`, `tests/test_compile_procedures.py`.
- **Quality Standard**: none found (`**/quality-standard.md`) — freeform; UI dimensions not applicable.
- **Findings**: 0 critical · 0 medium · 2 low. (1) `test_initialize_carries_the_instructions` pinned the text's newline count rather than the property that matters (a permanent-layer size budget). (2) `compose_backend_section` resolved the preamble with `defines_section` + a second scan while the loop above it uses `try/except KeyError`. Two claims were checked rather than assumed: `archive`/`soft_delete` are idempotent by construction (`COALESCE` on the lifecycle column, lookup with `include_deleted=True`), so `idempotentHint=true` is true; FastMCP builds a fresh `ToolAnnotations(**dict)` per tool, so the shared annotation dicts are safe.
- **Fixed**: both. (1) → `assert len(result.instructions) <= 600` with the reason in a comment. (2) → `try: parts.insert(0, extract_section(doc, PREAMBLE_SECTION)) except KeyError: pass`, committed as a second framework commit with the compiled output of both backends proven byte-identical to the reviewed build.

## QA Handoff
*Filled by Step 8 after Quality Review is resolved. This plan is **not** runtime-verified in the sense the checklist means — a human, a real client, and the hosted box after its next deploy.*

- **Scope**: `api_mcp/server.py` (instructions, `help`, titles + annotations); the framework's `seam.py` + `db.md` preamble; `docs/README.md`.
- **QA instrument**: set up — `qa/qa-map.md` (2026-08-21) + built bench (`qa/scripts/`, `qa/runbooks/munnin.md`).
- **Integration coverage**: N/A — no step crosses a real boundary the unit tests double (SQLite in `tmp_path`, submodule content, in-process client). Step 5's TCP walk against a live local-mode process was run as proof and passed on all seven facts; it is a proof, not a test.
- **Checklist**: `qa/checklists/server-instructions-help-annotations.md`
- **Coverage split**: 9 automated rows (13 named tests across Munnin and the framework) / 17 manual checks — of which 6 are **client-behaviour-bound** (whether a client injects instructions, shows titles, and asks before a destructive tool) and 4 wait on the **next hosted deploy**.
- **Runtime verification**: **NOT DONE.** Next action: `/run-qa-test --checklist qa/checklists/server-instructions-help-annotations.md` — the local sections now with a fresh Claude Code session; the hosted sections after the deploy that lands this commit.
