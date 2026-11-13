# MCP Descriptions — QA Checklist

**Source**: Approved in-conversation Quick Wizard plan, 2026-11-13, “Munnin and Hermod MCP descriptions”; Munnin changes in [MCP registration](../../src/munnin/api_mcp/server.py), [content loader](../../src/munnin/content/loader.py) and their tests.
**Purpose**: Verify that usable, accurate descriptions reach a real MCP client without changing tool contracts, granting access or executing the instructions being fetched.
**Apps under test**: Munnin's MCP discovery and content reads. Hermod has separate automated tests and no QA bench; it is not covered by this checklist. No database migration, authentication change or deployment is part of this change.

## Terminology & state model (read first)

| Surface | Meaning |
|---|---|
| Tool description | What an operation does, returns and changes. |
| Parameter description | Meaning, accepted inputs and omission/default behavior; description text does not add validation. |
| Procedure/prompt | Instructions to follow; fetching them does not perform their steps. |
| Resource | Template or script content; reading does not install, save or execute it. |

**Key invariants** (each is a thing to disprove):
- Description edits do not change tool names, input types, required fields, defaults, output schemas or safety hints.
- Native prompts/resources and tool-based listings describe the same content.
- Procedure substitution and template/script bodies remain unchanged.
- A client does not mistake a search snippet for a full record, an archive for deletion, or a persistent tenant selection for a session-only setting.

## Happy path — single end-to-end scenario (run this first)

1. Use an explicitly identified disposable local QA instance running the candidate code, with framework content available. Follow the [bench](../README.md) but do not reset or seed an existing store just to test descriptions. Do not use a live tenant to exercise writes or invitations.
2. Reconnect a real MCP client to refresh its discovery metadata. Record the client/version, endpoint and code revision.
3. Run `tools/list`, native prompt/resource listings, and the `list_procedures`/`list_resources` tools. Check the automated coverage below, then inspect the real transport output and client display.
4. Read `awaken-agent`, `reasoning-pattern-template` and `copy-lines`; compare the content against the candidate's loader/source. Do not run the fetched script or follow write instructions.
5. Perform the read-only guidance checks below and record results. Disconnect the test client and stop only the instance this run started.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Tool and parameter descriptions exist; important defaults and safety distinctions are explained | [test_tool_annotations.py](../../tests/api_mcp/test_tool_annotations.py)::test_every_tool_and_parameter_explains_its_contract | Real transport and client visibility; the test cannot judge every sentence's meaning. |
| Native and tool-based discovery share descriptions and prompt arguments remain optional | [test_content_tools.py](../../tests/api_mcp/test_content_tools.py)::test_native_and_tool_discovery_share_descriptions | Actual client caching, truncation and display. |
| Procedure bodies, argument substitution, resource reads and missing-name responses retain their contracts | [test_content_tools.py](../../tests/api_mcp/test_content_tools.py)::test_read_procedure_composes_for_the_db_backend, ::test_read_procedure_fills_the_argument, ::test_resources_as_tools; [test_markdown_fidelity.py](../../tests/content/test_markdown_fidelity.py) | Real endpoint runs the intended revision and serves its content. |
| Tool safety annotations remain assigned to the same read/write operations | [test_tool_annotations.py](../../tests/api_mcp/test_tool_annotations.py)::test_the_hints_say_what_each_tool_does | A client's confirmation policy is separate from these server hints. |

## Checks

- [ ] **Automated — descriptions/defaults:** Run `uv run pytest tests/api_mcp/test_tool_annotations.py -q`; the description/default assertions above pass.
- [ ] **Automated — discovery parity:** Run the native/tool discovery test above; names, descriptions and optional prompt arguments agree.
- [ ] **Automated — content regression:** Run `uv run pytest tests/api_mcp/test_content_tools.py tests/content -q`; existing content, substitution and missing-name checks pass.
- [ ] **Automated — safety hints:** The annotations test above passes without changing the read-only, destructive or idempotent classifications.
- [ ] **Manual — transport:** Capture fresh discovery from the candidate endpoint. Every returned tool and parameter has a nonblank description, existing schema fields/defaults/hints match the pre-change revision after ignoring descriptions, and native prompt/resource descriptions match the corresponding tool listings. Read-only content requests match the candidate's expected bodies.
- [ ] **Manual, UI-bound — display:** In the real client's tool/prompt/resource inspector, open the full descriptions. Check that parameter guidance is accessible, not only tool titles, and that any shortened preview can be expanded. Record client limitations rather than claiming missing server metadata.
- [ ] **Manual — guidance:** In a fresh client session, ask how to read a complete search hit, preview archiving, return to the home tenant and obtain the copy-lines helper. Expected guidance: `get` rather than treating a snippet as the body; `archive_memories` with `apply=false`; `use_tenant` with omitted/null tenant and a warning that selection persists across clients; `read_resource("copy-lines")` without executing it. Do not authorize or run tenant switching, invitations, writes, archiving or scripts for this check.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
