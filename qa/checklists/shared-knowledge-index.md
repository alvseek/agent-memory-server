# Shared Knowledge Index — QA Checklist

**Source**: [Implementation plan](../../../plans/2026-11-13-munnin-shared-knowledge-index.md)
**Purpose**: Verify that removing knowledge bodies from awakening does not lose access, defeat layer selection or expose a different agent's memory.
**Apps under test**: Munnin MCP/HTTP and served instructions; universal-chat-agent consumer. Reasoning storage/loading and knowledge archival policy are deliberately unchanged.

## Terminology & state model
Shared knowledge is available fleet-wide but not loaded in full. Private knowledge belongs to an agent. The consumer's advertised IDs are an awakening snapshot; type, owner and archive status are checked again when fetching a body.

**Key invariants to disprove**:
- A smaller awakening must not be achieved by deleting records or suppressing discoverable entries.
- A knowledge reader must not become an unrestricted reader of a tenant's episodes, identity or another agent's knowledge.
- A layer excluded from the prompt must not remain reachable through the new tool.
- A body-fetch failure must not break external toolsets or leak bearer credentials.

## Happy path — run first
1. On a disposable tenant, seed shared/private knowledge and an unrelated agent's private knowledge.
2. Awaken over MCP and HTTP: compare the indexes; ensure no shared knowledge body or old shared.knowledge field arrives.
3. Read an indexed body directly; compare it to its pre-change bytes.
4. With the updated consumer, ask a question requiring the indexed material; observe the actual read_knowledge call and returned body.
5. Exclude the shared index and try the same UUID; verify the tool refuses it without an HTTP read.

## Automated coverage
| Item | Tests | Still manual |
|---|---|---|
| Metadata projection and deliberate body read | test_awaken.py; test_shared_knowledge_index.py | Deployed version and real credentials |
| Both adapter shapes and instruction composition | test_shared_knowledge_index.py | Fresh-client instruction processing |
| Read-only tool boundary, errors and partial metadata | consumer test_knowledge_tools.py | Real OAuth and production model invocation |
| Actual registry binding, reload and external tools retained | consumer test_main_bindings.py | Deployment's pinned consumer version |
| Old/new layer filters and summaries/UUID rendering | consumer test_knowledge_tools.py and test_awakening_domain.py | Real configured filters in deployed environment |

## Checks
- [ ] **Automated**: archived/deleted shared knowledge stays out of the index while get retains archived bodies.
- [ ] **Automated**: null-summary legacy entries remain discoverable; empty knowledge indexes do not erase identity or reasoning.
- [ ] **Automated**: wrong UUID/type/owner/project and newly archived records never disclose their body through the consumer tool.
- [ ] **Automated**: 401/403, missing records, malformed JSON/records and network failure return bounded errors with no credential text.
- [ ] **Automated**: record pagination metadata survives; no automatic additional fetch occurs.
- [ ] **Manual**: capture deployed before/after payloads for the same data; distinguish serialized bytes from actual tokenizer counts.
- [ ] **Manual**: verify the running consumer handles the new index, fetches relevant shared/private knowledge and retains unrelated configured tools.
- [ ] **Manual**: expire/refuse a real service credential and confirm the failure is visible without leaked tokens.
- [ ] **Manual, UI-bound**: in Helheim, inspect the new index and fetch one body; no whole-body alias is present.
- [ ] **Manual**: verify the deployed core/coding instructions describe index-only loading and do not reload all knowledge to complete awakening.
- [ ] **Manual**: record the product/deployment versions actually exercised; a standalone worktree does not update telegent's pinned brain.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
