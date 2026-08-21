# `awaken-agent` as Served Prompt 12 — QA Checklist

**Source**: Quick Wizard sweep "Serve `awaken-agent` as Prompt 12" (2026-08-21) — closes the deferral that shipped the user-profile record without the instruction to ask for one.
**Purpose**: Confirm a DB-path client now receives the **awakening protocol**, that it arrives whole over a real server, and that adding it changed nothing for the eleven prompts and the markdown fleet that were already working.
**Apps under test**: Munnin's served-content surface (`ContentLoader`, both faces) + the `control-files` component the edit touched. **Not touched**: the DB schema, the importer, the `awaken` tool's payload, the data tools.

## Terminology & state model (read first)

Two things share the name and are **not** the same object:

| Thing | What it is | Who serves it |
|---|---|---|
| `awaken` | An MCP **tool**. Returns the agent's memory records. | `MemoryService.awaken` |
| `awaken-agent` | An MCP **Prompt** (new). Returns the *protocol* for processing that memory — phased load, load-integrity check, first-run profile ask. | `ContentLoader.get_prompt` |

The change exists because the first is data and the second is process, and a client that got only the first had the profile but no instruction to ask for one when it was `null`.

**A second distinction the served text must preserve** — inherited from the user-profile work and easy to flatten:

| State | Meaning | Required behaviour |
|---|---|---|
| `shared.user_profile` is `null` | Nobody has ever been asked | Ask once, then persist |
| Record exists, a field is empty | A deliberate blank | **Never** re-ask |

**Key invariants** (each written as a thing to *disprove*):

- The installed markdown `/awaken-agent` still tells an agent to Read the four files itself. The edit removed that sentence from the shared **component**; the markdown backend's own `§ load-agent-memory` is supposed to carry it. If both dropped it, 27 agents lose their load instruction and nothing errors.
- `/refresh-memory` — the component's **other** consumer — still reads correctly on both backends. It was edited by side effect, not by intent.
- Registering a Prompt named `awaken-agent` does not shadow, rename, or break the `awaken` **tool**.
- The other eleven prompts compose identically to before. `awaken-agent` is the first served procedure whose ops arrive through an **inlined component** rather than a `## {procedure}` backend section, and that path runs through shared, cached modules.
- The served text arrives **whole** over a live server. `awaken`'s payload is already known to exceed the MCP output cap and truncate silently — a 10,842-byte prompt should be nowhere near it, but "should" is what that finding disproved once already.

## Happy path — single end-to-end scenario (run this first)

1. RESET → INJECT → ACT (`qa/scripts/reset-db.sh`, `seed-meta.sh`, `start-server.sh`) — see [qa/README.md](../README.md).
2. `GET /api/prompts` → the list contains **12** names including `awaken-agent`. → *Registration*
3. `GET /api/prompts/awaken-agent` → HTTP 200, `content-type: text/markdown; charset=utf-8`, body **10,842 bytes**. → *Delivery*
4. Read the body: it names `awaken(`, both profile ops, and the `null`-vs-blank distinction; it contains no `## Storage Mechanics`, no `[STORAGE-BACKENDS-PATH]`, no `](components/`, no "Read tool". → *Composition*
5. Over MCP on the same running server, `prompts/list` returns the same 12 and `tools/list` still returns the 14 tools with `awaken` intact. → *No collision*
6. `GET /api/prompts/update-episodic` still returns its DB mechanics unchanged. → *No regression*

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| `awaken-agent` is in the served set; 12 total | `test_lists_served_prompts` · `test_prompts_list_get_404` · `test_prompt_list_parity` | Whether a **live uvicorn** serves it — every one of these uses an in-process transport (`ASGITransport` / FastMCP in-memory `Client`), so a routing or startup regression leaves them green |
| The served text stands alone — ops present, seam consumed, no dangling component link, no `Read tool` | `test_awaken_agent_prompt_stands_alone` | Whether the text is *usable by an agent* — every assertion is a substring check, so prose that is present but incoherent passes |
| Both faces return the same prompt names | `test_prompt_list_parity` | Whether both faces return the same **body** — parity is asserted on names only |
| Tool surface still 14, `awaken` intact | `test_tool_surface_is_the_documented_size` | Whether tool and prompt registration coexist **on one server instance** — the tests build them from separate fixtures (`_mcp` vs `_mcp_content`) |
| The other 11 prompts still compose | `test_prompt_composes_db_mechanics` · `test_orchestrator_prompt_composes_and_keeps_footer` | Only two of the eleven are actually asserted on |
| **The markdown-path component edit** | **none in this repo** — `control-files` runs its own CI | **All of it.** The compiled `/awaken-agent` and `/refresh-memory` markdown commands, and whether a real agent awakening still loads all four layers |
| **The prompt is not truncated in transit** | **none** | All of it — the MCP output cap applies at the client, and no test measures the delivered length |
| **The first-run ask actually fires for a DB client** | **none — unreachable by any test** | All of it. It needs a fresh agent session, on the DB backend, against a store with no profile record |

## Checks

### Registration & delivery

- [ ] `GET /api/prompts` returns exactly 12 names; `awaken-agent` among them.
- [ ] `GET /api/prompts/awaken-agent` → 200, `text/markdown; charset=utf-8`, **not** a JSON envelope.
- [ ] `curl -o out.md` writes a file that opens as clean markdown — no truncation mid-sentence at the tail.
- [ ] Body length matches what the loader composes in-process — compare **UTF-8 bytes to UTF-8 bytes**: `len(get_prompt("awaken-agent").encode("utf-8"))` against curl's `size_download`. A raw Python `len()` counts characters (10,731) and will look like 111 bytes of truncation that is not there.
- [ ] MCP `prompts/list` on the **same running server** returns the same 12, and `prompts/get` for `awaken-agent` returns the same bytes as the HTTP face.

### Composition correctness

- [ ] The body contains `awaken(`, `§ load-user-profile`, `§ persist-user-profile`.
- [ ] The body contains **no** `## Storage Mechanics`, `[STORAGE-BACKENDS-PATH]`, `](components/`, or `Read tool`.
- [ ] The `null`-vs-deliberate-blank distinction is present and legible — a reader can tell which state means "ask" and which means "never ask".
- [ ] The sub-agent prohibition survived the rewrite and still reads as a rule, not a fragment.
- [ ] Both inlined components are present in full; neither appears twice.

### Collision & regression

- [ ] `tools/list` still returns 14 tools including `awaken`; calling `awaken` on the content-registered server still works.
- [ ] Spot-check **three** other prompts (not just the two under test) against their pre-change bodies — e.g. `wrap-up`, `create-agent`, `load-episodic`.
- [ ] `GET /api/resources` still returns 4 templates.
- [ ] `qa/scripts/smoke-check.sh` exits 0. **Note**: it probes only `/api/prompts/update-episodic`, so it cannot catch a regression in the new prompt — see Known gaps.

### Markdown path — the fleet that already worked

- [ ] Compiled `control-files/procedures/output/awaken-agent.md` still instructs the agent to Read the four files (the backend's `§ load-agent-memory`), **and** carries the no-delegate rule.
- [ ] Compiled `refresh-memory.md` reads correctly end to end — it consumes the same edited component.
- [ ] Run **both installers as a pair**, then awaken a real agent and confirm all four layers load. The core installer alone drops the overlay's path definition.
- [ ] `control-files` CI is green on the component change.

### Boundaries

- [ ] With the `control-files` submodule absent, `/api/prompts` returns `[]` rather than erroring (`test_missing_submodule_is_graceful` covers in-process; confirm over the live face).
- [ ] `GET /api/prompts/awaken-agents` (typo'd) → 404, not a 500.
- [ ] Two rapid concurrent `GET /api/prompts/awaken-agent` calls both return the full body — the loader caches framework modules via `lru_cache`.

## Known gaps this checklist cannot close

- **`smoke-check.sh` does not probe `awaken-agent`.** OBSERVE will report `SMOKE OK` with the new prompt broken. Adding a probe is a `/build-qa-bench` change, not this checklist's.
- **The first-run ask remains unverifiable from inside a session** — carried from the user-profile checklist, and this change narrows it (the instruction now reaches the DB path) without closing it.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
