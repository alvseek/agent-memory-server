# Prompt Arguments — QA Checklist

**Source**: Approved in-conversation Quick Wizard plan, 2026-11-13, “Munnin and Einherjar prompt arguments”; [Munnin loader change](../../src/munnin/content/loader.py) and [regression tests](../../tests/api_mcp/test_prompt_arguments.py).
**Purpose**: Ensure prompt declarations agree with their bodies and supplied text reaches the procedure, including when a new procedure has no compatibility-map entry.
**Apps under test**: Munnin prompt discovery, prompt reads and `read_procedure`. Einherjar has its own automated tests but no QA bench; this checklist does not claim its runtime verification.

## Terminology & state model (read first)

- `$ARGUMENTS` in a procedure's source declares one optional text input.
- Existing names such as `domain`, `mode` and `context` remain compatible; new procedures use `argument`.
- No placeholder means no slot, even if a stale compatibility-map entry exists.
- Fetching a procedure does not authorize executing it.

**Key invariants** (each is a thing to disprove):
- A placeholder-bearing procedure cannot be listed without an argument slot.
- A declared slot cannot accept and silently discard its text.
- A no-input procedure cannot advertise an inert argument.
- Omitted input cannot alter the authored body or accidentally execute its instructions.

## Happy path — single end-to-end scenario (run this first)

1. Use a disposable QA instance running the candidate code, with framework content available; follow the [bench](../README.md). Do not reset an existing store for this metadata-only check.
2. Run the automated checks below, including the synthetic new-procedure and stale-declaration cases.
3. Open a fresh authenticated MCP session against that candidate instance. Read `prompts/list`, then `prompts/get` for every returned name, using the actual declared name for each input.
4. Supply a distinctive marker containing spaces. Compare each filled body with the no-input body after literal `$ARGUMENTS` replacement. For parameterless prompts, compare the no-input body only.
5. Check an actual client's command expansion in a disposable session with execution disabled; inspect the expanded text rather than asking the model to run the procedure. Do not write memories, switch tenants or run shell commands from fetched instructions.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Every shipped prompt binds its optional input; omission preserves its body; native/tool reads agree | [test_prompt_arguments.py](../../tests/api_mcp/test_prompt_arguments.py)::test_every_served_prompt_preserves_its_arguments | Candidate endpoint and real client expansion. |
| New procedure works without a map edit | Same file::test_a_new_procedure_declares_and_binds_input_without_a_map_entry | The deployed image must actually include the candidate loader. |
| A stale named entry cannot advertise an inert slot | Same file::test_a_parameterless_source_does_not_advertise_a_stale_named_slot | Real endpoint discovery/cache refresh. |
| Existing argument names stay compatible | Same file::test_existing_named_slots_keep_their_names | A client's argument forwarding and cached metadata. |

## Checks

- [ ] **Automated — all current prompts:** Run `uv run pytest tests/api_mcp/test_prompt_arguments.py -q`; all per-procedure cases pass.
- [ ] **Automated — new procedures:** The synthetic new-procedure test above passes without adding its name to a map.
- [ ] **Automated — parameterless:** The stale named-slot test passes; `wait-options` also remains parameterless in the shipped-procedure cases.
- [ ] **Automated — compatibility:** The existing-name test passes; no formerly named slot is replaced by the generic name.
- [ ] **Manual — real transport:** On the candidate endpoint, every declared slot preserves the supplied marker, every placeholder has one slot, parameterless prompts have none, and `read_procedure(name, argument)` gives the same substituted text. Record endpoint and release revision.
- [ ] **Manual, UI-bound — client expansion:** Refresh the client's MCP discovery, expand an argument-bearing slash command with a distinctive marker without executing its instructions, and inspect the expanded prompt. The marker remains and literal `$ARGUMENTS` is gone. Record client/version and whether preview-only inspection is supported.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
