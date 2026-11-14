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
- [x] **Automated**: archived/deleted shared knowledge stays out of the index while get retains archived bodies.
- [x] **Automated**: null-summary legacy entries remain discoverable; empty knowledge indexes do not erase identity or reasoning.
- [x] **Automated**: wrong UUID/type/owner/project and newly archived records never disclose their body through the consumer tool.
- [x] **Automated**: 401/403, missing records, malformed JSON/records and network failure return bounded errors with no credential text.
- [x] **Automated**: record pagination metadata survives; no automatic additional fetch occurs.
- [x] **Manual**: capture deployed before/after payloads for the same data; distinguish serialized bytes from actual tokenizer counts.
- [x] **Manual**: verify the running consumer handles the new index, fetches relevant shared/private knowledge and retains unrelated configured tools.
- [x] **Manual**: expire/refuse a real service credential and confirm the failure is visible without leaked tokens.
- [ ] **Manual, UI-bound**: in Helheim, inspect the new index and fetch one body; no whole-body alias is present.
- [x] **Manual**: verify the deployed core/coding instructions describe index-only loading and do not reload all knowledge to complete awakening.
- [x] **Manual**: record the product/deployment versions actually exercised; a standalone worktree does not update telegent's pinned brain.

## Result

**Run**: 2026-11-14 · software-architect · Tactic C, Chrome UI continuation
**Automated**: Prior 5/5 green retained · **Manual**: 5/6 completed; UI row partially observed
**Sign-off**: NOT SIGNED OFF — Chrome verified index rendering; body-fetch UI remains outstanding.

### Evidence
- Used Alvi's real Chrome through the connected extension. Helheim connected to Munnin with the existing sign-in; no new Google login was needed.
- Helheim call 56 (`awaken`, software-architect) rendered `shared` with exactly `reasoning`, `knowledge_index`, `ras` and `user_profile`. Expanded the 32-entry knowledge index and its first entry: UUID, title, authored summary, tags, project and dates were visible, with no body.
- Opened the `get` form and attempted the first indexed UUID. The Send action timed out; subsequent inspection also timed out. Relay status still reported Chrome connected but marked this target `protectedUi: true`. No successful body-fetch call or result was observed, and no repeated submission was attempted.

### Findings
| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Existing sign-in and index rendering now verified in Chrome. The get-form interaction stopped responding; the body-result UI is unverified. | qa | Open — inspect the Chrome tab before resuming |

**Run**: 2026-11-14 · software-architect · Tactic C
**Automated**: 5/5 green · **Manual**: 5/6 completed
**Sign-off**: NOT SIGNED OFF — Helheim's browser verification requires a fresh user login.

### Evidence
- Consumer `f4e892e`: full suite, 182 passed. Producer projection/API/content selection: 53 passed. Existing producer CI `43469062755` passed both `test` and `postgres`; image build `43469062769` passed for this exact commit.
- Released consumer first: universal-chat-agent main `f4e892e`, telegent `49ce3e5`, private deploy pin `43669dc`. The running VPS brain was restarted to `f4e892e` and its health endpoint answered successfully.
- Munnin `654bfa6`: deploy run `43529037189` succeeded. Hermod `ee6637a`: deploy run `43529232055` succeeded. Both image tags were independently observed in healthy running containers.
- Real OAuth/HTTP before and after: the same 32 shared IDs and 38 private index entries; full serialized awakening 370,266 → 302,065 UTF-8 bytes, a 68,201-byte reduction (not tokens). Shared reasoning/RAS/profile and agent identity/reasoning/emotional/private index compared equal; one shared and one private body hash were unchanged.
- Fresh MCP awakening confirms `shared.knowledge_index`, no old key, 32 metadata-only rows. Live Munnin and Hermod procedures explicitly instruct relevant-body reads rather than reloading the directory.
- The deployment intentionally excludes `shared.knowledge` and `shared.reasoning`. Configuration was not changed. Real HTTP-backed tool invocations proved private access, shared exclusion before any HTTP request, and shared access in an isolated tool instance without that exclusion. An intentionally invalid bearer against the real server produced only `knowledge_auth_failed`; no production credential was revoked.
- A registry-built agent using the production model `deepseek/deepseek-v4.1-flash` made one observed `read_knowledge` call and received the exact private body. The deployed daemon's `/chat` path also returned the body's exact first nonempty line; Munnin logged its body GET at `2026-11-13T23:56:51.760Z`, after chat started at `23:56:50.146Z`. The two temporary conversation rows were removed in `finally`, with zero matching rows remaining.
- Both running-agent reload endpoints succeeded. The production-configured invintiry operator retained `invintiry-reads`, `invintiry-writes` and `memory-knowledge` toolsets in a real registry build; no business write tool was invoked.
- The checklist's full disposable-tenant happy-path scenario was not separately seeded. Unit/service tests cover disposable-store isolation; live probes used read-only existing records and scoped temporary chat history. No RESET or INJECT was run against production.

### Findings
| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Helheim's saved connection is expired; browser reached the Logto sign-in page but no user login was completed. Index rendering and body fetch remain unobserved in this UI. | qa | Open — user login needed |
