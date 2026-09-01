# Server instructions, `help`, tool annotations, and the `<domain>` preamble — QA Checklist

**Source**: Quick Wizard plan *Server instructions, `help`, tool annotations, and the `<domain>` sentence (launch-map step 4)*, 2026-09-01 — `agent-memory-server` (this commit) pinning `agent-memory-system@475c3be` (`28a5a34` + a review fix).
**Purpose**: confirm that a stranger who connects to Munnin is told what it is and what to call first *by the client they actually use*, that the client treats each tool the way its hints say, and that the one sentence now opening every served procedure reaches every door without moving a byte of the installed markdown commands or of anything the hosted deploy already serves.
**Apps under test**: the MCP face (`initialize`, `tools/list`, the `help` tool, `read_procedure`), the framework's seam composer (`seam.py`) and the `db` backend. **Not touched**: the data tools' behaviour, the HTTP `/api` routes, tenancy, auth, the store schema, the markdown backend, the hosted box (pin only — it still runs `e52dd8d`).

## Terminology & state model (read first)

Three new things, three different carriers:

| Thing | Carrier | Who sees it | When |
|---|---|---|---|
| **instructions** (4 sentences, 466 chars) | the `initialize` result | a client that injects it into the system prompt (Claude Code, claude.ai) | once per session, then re-sent on every call as part of the prompt |
| **`help` tool** | `tools/list` + `tools/call` | every client, including ones that show no instructions | on demand |
| **title + hints** (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | `tools/list` | the client, before it lets a tool run | on demand (tool definitions arrive deferred — names first, schemas on demand) |
| **`<domain>` preamble** | the body of every seam procedure, ahead of its `### §` ops | whoever reads a procedure: `read_procedure`, the MCP prompt, HTTP `/api/prompts/{name}` | composed live at serve time |

The preamble is a **backend-level** section (`## all-procedures` in `db.md`): it is prepended only when a procedure is already covered by the backend, and `markdown.md` defines none.

**Key invariants** (each is a thing to *disprove*):
- The installed markdown command set is byte-identical to before — `update-episodic.md` installed under `~/.claude/commands/` shows no `<domain>` note after a reinstall.
- Every procedure that reaches the wire (13) carries the preamble exactly once, ahead of its first `### §` op; `wait-options` (no seam) carries none.
- The preamble never *creates* a served procedure: the served set is still 13 and `push`/`pull`/`refresh`-memory are still absent.
- `tools/list` has 19 entries, each with a title and `readOnlyHint`; every non-read-only tool states `destructiveHint` explicitly; nothing claims `openWorldHint=true`.
- The destructive set is exactly `{edit, multi_edit, archive, soft_delete}` — an additive write (`insert`, `create_agent`, `append`, `prepend`) is never shown to a person as destructive.
- In token mode `help` needs a bearer like every other tool; in local mode it answers without one. `help` exists with no served content and then lists no procedures.
- The hosted box is unchanged by this commit (pin only): anonymous `POST /mcp` still **401**, and its `initialize` result still carries **no** `instructions` until the next deploy.

## Happy path — single end-to-end scenario (run this first)

1. `MUNNIN_AUTH=off uv run python -m munnin` (or `docker compose up -d --build`), then `claude mcp add --transport http munnin-local http://127.0.0.1:8200/mcp` → *Checks: Client sees the instructions*.
2. Start a **fresh** Claude Code session, do nothing but ask *"what is this munnin server and what should I do first?"* → the answer names agent identity, `list_agents()`, and `read_procedure("create-agent")` **without any tool call having been made yet** → *Checks: Client sees the instructions*.
3. `/mcp` → `munnin-local` → tool list: entries show their **titles** ("Awaken an agent", "Soft-delete a record"…), not only names → *Checks: Titles and hints reach the client*.
4. Have the agent `create_agent("qa-scratch")` then `insert(agent_id="qa-scratch", record_type="knowledge", content="x", uuid="qa-1")` → no confirmation prompt for either (additive) → *Checks: Titles and hints reach the client*.
5. Have the agent `soft_delete("qa-1")` → the client asks before running it (destructive) → *Checks: Titles and hints reach the client*.
6. Have the agent `read_procedure("update-episodic")` → the returned text opens (after the procedure's own heading and intro) with the blockquote *"`<domain>` in the ops below is the agent you are acting as…"* **before** the first `### §` → *Checks: Preamble*.
7. Have the agent call `help` → instructions text + 13 rows, identical to `list_procedures` → *Checks: help*.
8. `soft_delete` is tombstoned; `claude mcp remove munnin-local`; stop the server.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| `initialize` carries `instructions` == the constant, ≤ 600 chars | `tests/api_mcp/test_content_tools.py::test_initialize_carries_the_instructions` | That a **client injects it** — the test reads the wire, it cannot see a system prompt; step 2 above |
| `help` == instructions + the same rows as `list_procedures`; with no content, `[]` | `test_content_tools.py::test_help_is_the_instructions_plus_the_menu`, `::test_help_answers_without_served_content` | — |
| `help` present with and without content; surface 15 bare / 19 full | `test_content_tools.py::test_content_tools_present_only_with_content`, `tests/test_twin_parity.py::test_tool_surface_is_the_documented_size` | — |
| Every tool titled and hinted; destructive set exact; idempotent on archive/soft_delete; `openWorldHint=false` | `tests/api_mcp/test_tool_annotations.py` (three tests) | That a **client honours** the hints — confirmation on destructive, none on additive; steps 4–5 |
| `help` guarded in token mode | `tests/api_mcp/test_mcp_auth.py` (whole MCP face rejects an absent token at the transport) | An explicit `tools/call help` with no bearer against the **live** box after the next deploy → 401 |
| Preamble in `update-episodic`, `wrap-up`, `awaken-agent`; absent from `wait-options`; ahead of `### §` | `tests/content/test_content_loader.py::test_backend_preamble_reaches_every_seam_procedure`; framework `tests/test_compile_procedures.py::test_db_preamble_opens_every_composed_procedure` | The remaining 9 served procedures are covered by the mechanism, not enumerated — spot-check two (`add-reasoning`, `create-agent`) |
| Preamble reaches all three doors identically (tool, prompt, HTTP) | `tests/test_twin_parity.py::test_read_procedure_tool_parity`, `::test_prompt_parity` (same loader behind all three) | — |
| Preamble never wires a procedure; served set still 13 | framework `test_compile_procedures.py::test_preamble_rides_along_but_never_wires_a_procedure`; `test_twin_parity.py::test_prompt_list_parity` (13) | — |
| Markdown command set unchanged | framework `test_compile_procedures.py::test_markdown_defines_no_preamble_and_is_unchanged_by_it` (asserts absence of the marker); `tests/content/test_markdown_fidelity.py` | **Byte identity** was proven once by diffing 16 compiled files before/after (2026-09-01), not by a test that keeps a baseline — re-run the installer and `cmp` the installed `update-episodic.md` against the one installed today |
| Hosted box unchanged | none — pin only | Anonymous `POST /mcp` on `munnin.lok.quest` → 401; its `initialize` (authenticated) shows no `instructions` until the deploy |

## Checks

### Client sees the instructions
- [ ] Fresh Claude Code session, no prior tool call: asking what the server is yields agent identity + `list_agents()` + `read_procedure("create-agent")` (step 2). If the agent instead calls `help` first, note it — that is the fallback working, not the instructions.
- [ ] claude.ai (hosted, **after the next deploy**): a new conversation with the connector enabled answers the same question the same way.
- [ ] `initialize` result over raw HTTP (`curl` with the JSON-RPC `initialize` body) carries `"instructions"` whose length is 466 and whose first word is `Munnin`.

### Titles and hints reach the client
- [ ] Claude Code's `/mcp` tool listing shows titles for all 19 tools; no entry falls back to the bare name.
- [ ] `soft_delete`, `archive`, `edit`, `multi_edit` each prompt for confirmation before running; `insert`, `create_agent`, `append`, `prepend` do not (steps 4–5). Record which client and version — this is the client's behaviour, and clients differ.
- [ ] `tools/list` over raw HTTP: `jq '.result.tools | map(select(.annotations.readOnlyHint == null or .title == null)) | length'` → `0`; `map(select(.annotations.destructiveHint == true) | .name)` → exactly the four.

### help
- [ ] Local mode: `help` with no `Authorization` header → 200 with `instructions` + 13 `procedures`.
- [ ] `MUNNIN_CONTENT_ROOT=/nonexistent MUNNIN_AUTH=off uv run python -m munnin` → server boots, `help` → `{"instructions": …, "procedures": []}`, `list_procedures` absent from `tools/list`, tool count 15.
- [ ] Token mode (live box, after deploy): `tools/call help` with no bearer → 401 with the `WWW-Authenticate` challenge, same as any data tool.

### Preamble
- [ ] `read_procedure("update-episodic")` opens the mechanics with the blockquote, once, before the first `### §` (step 6).
- [ ] Spot-check `read_procedure("add-reasoning")` and `read_procedure("create-agent")`: same sentence, same position, once each.
- [ ] `read_procedure("wait-options")` carries no `<domain>` sentence (no seam, nothing composed).
- [ ] `GET /api/prompts/update-episodic` (bearer in token mode; none in local) returns the same bytes `read_procedure` returned.
- [ ] `list_procedures` → 13; `push-memory`, `pull-memory`, `refresh-memory` absent.
- [ ] After `bash control-files/setup-scripts/setup-all-claude-code.sh` on a machine with the fleet installed: `cmp ~/.claude/commands/update-episodic.md <copy saved before the reinstall>` → identical; `grep -c '<domain>` in the ops below' ~/.claude/commands/*.md` → 0 everywhere.

### Hosted deploy did not move (pin only)
- [ ] `docker ps` on the box still names `munnin-web-e52dd8d`.
- [ ] Anonymous `POST https://munnin.lok.quest/mcp` → **401**; an authenticated session's `initialize` result carries no `instructions` and `tools/list` shows 18 tools — the pre-step-4 surface, until the deploy that lands `≥` this commit.

### Untouched surfaces (regression)
- [ ] `uv run pytest -q` → 453 passed (or more), `ruff check` clean; framework `uv run pytest -q` → 41 passed, strict compile exit 0, core invariant holds.
- [ ] `list_prompts` → 13 and `list_resources` → 4, unchanged; `read_resource("episodic-entry-template")` byte-identical to before (templates are not composed, so the preamble cannot reach them).

### Noted, not this checklist's to fix
- A future procedure named `all-procedures` would collide with the preamble section name; `command_set` would then try to serve it. Unlikely, recorded.
- Tool descriptions and titles are deferred by clients (names first), so a title is visible only in a picker, never in the model's always-on context — the tool **name** remains the discovery surface (recorded 2026-08-30).
- `qa/checklists/qa-checklists-map.md` does not list this checklist — `/map-qa-instrument --rescan`, not a hand edit.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
