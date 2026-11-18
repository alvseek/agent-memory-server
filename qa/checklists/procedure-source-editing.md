# Procedure source editing & guarded memory saves — QA Checklist

**Source**: Deployment plan [`2026-11-16-munnin-deploy-procedure-source-editing.md`](../../../plans/2026-11-16-munnin-deploy-procedure-source-editing.md); [original file inventory](../../../plans/evidence/2026-11-17-procedure-source-editing-files.json), plus approved F1/H1–H4 review fixes. Implementation/review evidence in that plan is not execution of this checklist.
**Purpose**: Disprove backend contamination, wrong-source publication, stale/unauthorized writes, lossy full-body reconstruction and accidental private-history copies.
**Apps under test**: Munnin composer delivery and memory service through HTTP/MCP, SQLite and PostgreSQL. Framework/compiler and Helheim are cross-consumer dependencies, not additional benches. Hermod migration, production promotion, memory creation/deletion UI and arbitrary repository editing are deliberately out of scope.

## Terminology & state model (read first)

| Term | Meaning for this run |
|---|---|
| Authored source / composition | A declared section is writable; composed text is generated. Shared sections affect both backends. Source ID/path/hash and branch HEAD identify the edit, not its heading. |
| Draft / saved / deployed | Browser draft is unsaved; Git commit is saved to the workspace branch; draft PR is reviewable, not deployed. Unknown write outcome requires reconciliation; confirmed commit with failed PR step is partial success. |
| Edit context | Full UUID, resolved acting tenant and opaque complete-row state digest. It is not a timestamp or an event counter; returning to identical row state can return the same digest. |
| Exact baseline | All pages share context, metadata, body SHA-256 and Unicode-code-point length. Source-position segments reconstruct original order; display-page concatenation is not necessarily the body. |
| Independent saves | Body uses complete baseline as `old_string`; metadata uses only changed fields/explicit clearing. Success refreshes shared revision but does not save the other area's draft. |
| Session lifetime | Helheim holds at most 32 memory baselines, evicting the least-recently-used non-saving session; 30 minutes without a preview/save request expires one. Typing alone sends no heartbeat; preview/save refreshes the lifetime. Browser drafts can outlive the server baseline, not a browser restart. |
| Authorization boundary | Tenant selection and live grant are resolved on each call. Revocation affects subsequent calls, not cancellation of an already-authorized in-flight request. `expected_tenant` is a precondition, never an account selector. |

**Future-run prerequisites and safety**: Use the existing [Munnin runbook](../runbooks/munnin.md) with an isolated disposable database/tenant and explicitly designated disposable records. Prepare owner, invited guest and stranger identities through approved administration, not production users. Use a separate allowed Git test repository/branch and draft PR; record IDs for scoped cleanup. Never run blanket RESET/seed against production. Issuer login, PostgreSQL, deployed-version inspection and GitHub mutations require the runner's approved environment/authority; missing prerequisites are gaps, not passes. Do not install, start services or create fixtures merely by reading this checklist.

Munnin's [map](../qa-map.md), [README](../README.md) and existing scripts establish the bench opt-in. Coordinating root and Helheim have no QA map/built bench: their checklist generation is **SKIPPED**. Checks below requiring Helheim/browser/GitHub remain manual cross-consumer prerequisites; no Helheim bench is claimed. The existing checklist map is a dated audit, with no mandatory per-creation update contract; it is unchanged. Its completed directory contains only `.gitkeep`.

**Key invariants** (each is a thing to *disprove*):
- A DB delivery must not acquire Markdown file-writing mechanics through a legacy component or silently fall back after converted-source failure.
- Source saves must not overwrite another HEAD, write an undeclared path, discard prior section edits, or label a commit as deployed.
- No incomplete/mixed body may become a writable baseline; untouched Unicode/newline bytes must survive actual UI edits.
- A failed guard or subsequent revoked/changed-account call must not alter either tenant's record or disclose another body's contents.
- Body and metadata writers must not cross fields; private drafts/baselines must not enter generic inspector history or persist indefinitely as active server sessions.

## Happy path — single end-to-end scenario (run this first)
1. Record exact framework/composer/Munnin/Helheim revisions and tool capabilities in the isolated environment (M01). Open `wrap-up`, choose both backends, then Edit one shared section; verify canonical source badge and shared-impact warning (M02).
2. Preview a small reversible edit without writing, save to the disposable branch/draft PR, then edit a second section in the same workspace. Preview both accumulated changes and independently inspect the remote two-file diff. Served Munnin content must remain at its deployed revision (M02–M03).
3. Open the disposable multi-page episode containing preamble, non-adjacent equal timestamps, Unicode and mixed newlines. Compare the exact reconstructed baseline with its prepared body (M04).
4. Dirty body and metadata. Save body only, independently read the record over authenticated HTTP, then save metadata only with the new revision. Repeat in reverse order; neither save loses the other draft (M05).
5. Repeat a successful guarded save as the invited guest under the displayed owner tenant, then Close with confirmation and prove the old session cannot save. Inspect generic history for the unique private marker (M06, M10, M14). Clean up only the run's identified disposable resources under the runner's approved cleanup procedure.

## Automated coverage
| Checklist item | Automated test | Still manual |
|---|---|---|
| A01 Canonical loader output and dependency refusal | `tests/content/test_content_loader.py::test_converted_served_text_is_exactly_the_canonical_composition`; `test_converted_calls_cannot_silently_point_at_unserved_procedures` | Actual installed pins/container and served envelopes; same-provider equality alone does not prove installation or UI preview equality (M01–M03). |
| A02 Legacy content/arguments/resources | Same file: `test_seamless_procedure_is_served_as_its_own_core`, `test_arguments_substitute_only_when_supplied`, `test_lists_served_prompts`, `test_resources_include_block_templates`, `test_markdown_scaffold_excluded_from_resources` | Transport registration/envelopes and live caller compatibility (M16). |
| A03 Dual compiler regression F1 | Framework `tests/test_compile_procedures.py::test_dual_output_matches_single_backend_including_canonical_components`, `test_dual_intermediates_are_separate_and_match_each_backend` | Installed command and available overlay consumers; Munnin intentionally excludes `refresh-memory` (M16). |
| A04 Revision, independent fields, empty/lifecycle cases | `tests/data_repositories/test_edit_guards.py::test_revision_counts_every_entity_field_without_timestamp_resolution`, `test_guarded_body_and_metadata_writes_are_independent`, `test_lifecycle_and_empty_body_guards` | Parameterized engine tests only prove engines actually executed; deployed storage and missing/deleted cases (M09, M12). |
| A05 Transaction boundary and concurrent winner | Same file: `test_body_is_read_and_transformed_only_under_the_real_write_lock`, `test_failed_guard_never_runs_a_body_transform`, `test_two_writers_with_one_baseline_cannot_both_commit` | `_rewrite` lock probe is not an end-to-end sibling-writer test; live append/prepend/multi-edit and actual PostgreSQL execution (M09, M17). |
| A06 Service defaults/guards and exact segments | `tests/business_services/test_edit_context.py::test_opt_in_read_and_separate_guarded_saves`, `test_partial_precondition_pairs_are_refused`, `test_expected_tenant_never_selects_an_account_or_leaks_a_body`, `test_each_episode_page_reports_the_same_context_until_the_row_changes`, `test_editor_pages_reconstruct_nonadjacent_equal_timestamps_byte_exactly` | Reconstruction test joins segments itself, not through Helheim; real multi-page transport/UI and interrupted loads (M04, M08, M16). |
| A07 Authenticated API adapters | `tests/test_editor_contract.py::test_http_owner_guest_conflicts_and_revocation`, `test_mcp_schema_guards_and_guest_authorization` | Real adapters with disposable SQLite/synthetic verified actors, not real issuer/deployment; stranger, broader body-save revocation matrix and expiry remain M01, M06–M07. |
| A08 Helheim service/route boundaries | Helheim `tests/test_memory_editor.py::test_nonadjacent_source_positions_reconstruct_the_exact_body`, `test_incomplete_or_mixed_pages_never_enable_save`, `test_old_server_is_read_only_and_browse_does_not_fetch_bodies`, `test_separate_saves_preserve_the_other_baseline_and_refuse_duplicate_revision`, `test_capability_loss_or_transport_failure_never_advances_a_baseline`; `tests/test_editor_routes.py::test_memory_saves_are_guarded_and_not_written_to_history` | Fake remote service and in-process routes do not prove browser wiring, real issuer, all corruption shapes or disk/log privacy (M04–M11, M14). |
| A09 Helheim source outcomes H1/H2 | `tests/test_github.py::test_missing_write_response_is_uncertain`; `tests/test_workspaces.py::test_lost_response_retains_intent_after_remote_write`, `test_postcommit_pr_check_failure_returns_confirmed_save`, `test_commit_success_pr_failure_retries_only_the_pr`, `test_open_and_preview_do_not_write_and_two_saves_share_one_pr` | Fake GitHub/process responses; actual remote outcome and visible recovery controls (M03, M13). |
| A10 Browser-script fidelity/close H3/H4 and session cleanup | Helheim `tests/editors_newlines.test.cjs`: generated `mapper: CRLF edit`, `mapper: mixed edit`, source/memory `: exact baseline, preview/save, successive save ` cases, `memory: metadata saves preserve dirty body and its original separator baseline`, `memory close: dirty cancellation sends no POST and retains drafts`, `memory close: confirmed POST disables editor and navigates without another dirty prompt`; `tests/test_memory_editor.py::test_close_releases_only_the_owning_idle_editor`, `test_capacity_releases_least_recently_used_without_touching_busy_saves`, `test_idle_expiry_and_activity_refresh_are_deterministic`, `test_expiry_never_releases_a_save_in_flight_and_lazy_expiry_refuses_writes`, `test_abandoned_baseline_is_released_without_another_request` | Node VM models textarea/events; service tests use short/injected limits, not the actual browser and deployed 32-session/30-minute policy (M05, M10). |

## Checks

### Automated contracts — not results

Run from each named repository using its existing approved test environment; do not infer a pass from historical plan/review counts. A checkbox represents one coverage group, not one test invocation.

- [x] **Automated A01**: Execute the two A01 named tests; exact canonical DB bytes/metadata match and a missing declared call fails rather than falls back.
- [x] **Automated A02**: Execute the five A02 tests; legacy text, optional arguments, served exclusions and separate resources retain their contracts.
- [x] **Automated A03**: Execute both A03 tests for both backend parameters; dual/single outputs and backend-specific intermediates agree, including legacy `refresh-memory`.
- [x] **Automated A04**: Execute all A04 tests for SQLite/PostgreSQL and agent/shared parameters; stale body/metadata writes roll back, empty bodies work, lifecycle/row-state changes invalidate old tokens. Record skips separately.
- [x] **Automated A05**: Execute the three A05 tests on both engines; the lock probe holds during transformation, failed guards do not transform, and exactly one concurrent guarded writer wins.
- [x] **Automated A06**: Execute the five A06 tests; default response compatibility, paired guards, tenant mismatch and source-segment reconstruction are preserved.
- [x] **Automated A07**: Execute both A07 API tests; HTTP 409/403 and MCP actionable failures accompany no failed-precondition write or body leak.
- [x] **Automated A08**: Execute the six A08 named tests, including corruption parameters; fake-remote editor loading/saves and in-process history suppression hold without unguarded fallback.
- [x] **Automated A09**: Execute the five A09 tests with all parameters; missing write responses retain pending intent, known commits survive PR-step failure, PR retry does not recommit, and two edits share one draft PR.
- [x] **Automated A10**: Execute `node --test tests/editors_newlines.test.cjs` in Helheim and all five named Python cleanup tests; report Node and Python results separately. Exact-script tests are not native-browser proof.

### Manual — deployed boundaries and Helheim-dependent prerequisites

- [ ] **Manual M01 — issuer/deployment**: With approved real-issuer test identities, record running image/source/composer versions and Helheim's immutable dependency pin; inspect MCP `get`, `edit`, `edit_metadata` schemas and HTTP behavior. `include_edit_context` and both guards must be advertised/accepted before editing. Do not restart the user's unrelated instance or treat a review branch as deployed.
- [x] **Manual M02 — UI-bound source identity**: Open awakening/wrap-up in both backends. Each Edit opens the declared raw section with correct path/hash/HEAD; repeated appearances share one source and show derived dependents. Shared edits visibly warn of both-backend impact. Preview performs no Git or memory writes and shows safe diff/text, not editable generated output.
- [x] **Manual M03 — GitHub cross-consumer**: On the disposable workspace, save two different sections and independently inspect branch commits/PR diff. Both edits remain in one draft PR; preview combines saved edits with current draft for both backends. No merge/deploy occurs and Munnin's installed source is unchanged. Advance HEAD externally, then Save from the old UI: conflict, no forced write, draft retained. Closed/ready PR reuse and existing-branch collisions must refuse without reset.
- [ ] **Manual M04 — UI-bound exact paging**: Use an episode exceeding the configured body ceiling, with preamble, non-adjacent equal timestamps, CRLF/LF/CR, leading/trailing blank lines and Unicode. Inspect every page's context/hash/character length/source segments and compare reconstructed UTF-8 bytes with the prepared original. Metadata browsing must not fetch bodies; Save cannot enable before complete verified coverage. Display-order concatenation must not silently replace source order.
- [ ] **Manual M05 — UI-bound field/newline fidelity**: Dirty both areas; save each first in turn, then save the other using refreshed context. Independently read after each write: only named area changed, no automatic summary, other draft/dirty badge retained. In both source and memory editors change one line, split/join a line and insert/delete a line in CRLF and mixed-newline bodies; inspect submitted and persisted UTF-8, including untouched separators. Verify empty original/replacement and successive saves without global newline normalization.
- [x] **Manual M06 — tenant-change negative**: Guest opens a disposable owner record, then selects home or another allowed tenant in a second client. Submit old body and metadata saves separately. Subsequent calls must refuse account mismatch (HTTP 409/MCP actionable error), preserve browser draft, write neither tenant and expose neither tenant's current body. Reload under the displayed selected tenant to recover; expected tenant must not switch accounts.
- [ ] **Manual M07 — revocation/stranger negative**: Invite/select guest, load, then revoke through approved test administration before the next save. Both body and metadata attempts must fail authorization (HTTP 403/MCP permission failure), not write, and retain drafts without body-bearing errors. Stranger cannot read/save the owner UUID; expired/invalid token keeps authentication semantics. An already-authorized in-flight request is not required to be cancelled.
- [ ] **Manual M08 — mixed/incomplete-pages negative**: In the isolated test transport only, pause after page one, change row metadata/body or selected tenant, then resume. Separately interrupt transport, repeat a cursor, omit context, corrupt hash/length, introduce a segment gap/overlap or wrong UUID. Load must fail closed with reload guidance and no writable editor/save call; restoring transport requires a fresh complete baseline, not concatenating old/new pages.
- [x] **Manual M09 — stale old/new negative**: Open two editors at one revision. Save from one; attempt old-revision body and metadata writes from the other even if its `old_string` still matches. Both must conflict without overwrite. Load latest in a new tab, preserve old draft for comparison, deliberately reapply and save with the new context; it must succeed only if no intervening change. Repeat after archive/append/prepend/multi-edit via an existing client, and with two near-simultaneous saves.
- [x] **Manual M10 — UI-bound Close/expiry/cap**: Dirty both areas, cancel Close: no close request, no lost draft. Confirm Close: server baseline released, controls disabled/navigation succeeds, old session cannot write. With disposable sessions, open 33 editors: retained baselines never exceed 32 and a least-recently-used non-saving one ends. Leave an editor without server activity for 30 minutes, including typing locally: no heartbeat extends it; later Save gives ended/expired guidance, retains browser draft and requires opening latest in a new tab. An in-flight save is not evicted.
- [x] **Manual M11 — old-server/capability negative**: Connect only to an isolated legacy server lacking guard schemas or exact-body reconstruction. Browse remains available, editing refuses; no guard-dropping fallback. Remove capability/change transport after open: Save does not advance the local baseline or erase draft. For uncertain memory write outcome, independently reread latest before reapplying; do not blindly retry an old baseline.
- [x] **Manual M12 — validation/lifecycle**: On disposable agent/shared records through both faces, reject a missing guard partner, blank token, unknown edit field, blank title/project/summary, and a 1,001-code-point summary; accept valid 1,000-code-point Unicode summary and explicit clearing/empty tags. Body must remain byte-identical on metadata validation/clear. Missing/deleted records stay unavailable; no save revives lifecycle or edits owner/type. Check actual status/error, not just visible text.
- [ ] **Manual M13 — Git uncertainty/partial-success negatives H1/H2**: With approved disposable remote writes and controlled fault injection, lose the response after branch creation and after commit. UI reports uncertainty, blocks blind saves and retains pending intent; reconcile a confirmed commit without recommit, but never adopt/reset an ambiguous branch. Fail the PR-state read after a confirmed second commit: visible partial success includes commit/source revision; Retry PR changes no source commit. Closed/ready/wrong-head/base PR must not be silently reused.
- [x] **Manual M14 — privacy/security**: Put a unique harmless marker in the disposable body/draft; open/preview/save/fail/close using the editor. Inspect generic inspector history, its persisted local DB and accessible logs: no automatic memory-body/draft copy. Baseline release does not promise secure erasure of browser/process memory. Try HTML/script/unsafe-link payloads: literal safe text, no execution. Forged Origin, Host or missing/bad CSRF on every current POST route must fail before Git/Munnin authority; do not rely on loopback alone.
- [ ] **Manual M15 — UI-bound feedback/inspector regression**: Use native clicks/keyboard: labels, focus, acting account, source/backend/revision and saved-area confirmation remain readable. Duplicate Save/Close while pending causes no second write. Validation/conflict/network errors retain both drafts. Existing inspector Send/history/replay/token counts work unchanged; only deliberate generic inspector calls retain their established history behavior.
- [ ] **Manual M16 — content/default API compatibility**: Over actual HTTP and MCP, compare converted `awaken-agent`/`wrap-up` and called procedures with same-revision canonical DB output; no file-backed persistence/push instructions leak. Read legacy `wait-options`, separate templates/resources and prompt argument metadata; absent/empty arguments preserve placeholders, supplied argument substitutes. Default get/query/awaken must not gain `edit_context`/`edit_body`; legacy unguarded body edit stays body-bearing, metadata edit stays metadata-only, guarded success has fresh context/metadata without body. Verify installed Markdown commands and dual/single `refresh-memory` outputs; preserve available overlay seam imports without claiming Hermod migration or unavailable-consumer tests.
- [ ] **Manual M17 — engine/release evidence**: Read exact-revision CI evidence showing the guarded tests actually executed against PostgreSQL, not skipped/only collected; separately exercise approved isolated PostgreSQL runtime through authenticated faces. Record image build/runtime and deployed content/capabilities independently of SQLite/unit/wheel success. No schema/backfill/reset or production promotion is implied; unresolved issuer, native UI, container or consumer prerequisites remain explicit gaps.

## Result

**Run**: 2026-11-18 · software-architect · Tactic C continuation — live GitHub, default expiry, security and API matrices
**Automated**: 10/10 groups remain green; additional native-form repair suite 149 passed, one real-server integration test deselected.
**Manual**: 8/17 rows locally completed (M02, M03, M06, M09, M10, M11, M12, M14); 9 remain partial, bench-gated or staged after release.
**Sign-off**: NOT SIGNED OFF — no archive or production release approval.

### Actual source/GitHub verification

- Opened awakening and wrap-up in DB and Markdown through native selectors.
  Checked **64** source-edit targets against immutable `git show 6412c4d:<path>`
  bytes: ID, source path, full SHA-256, source text and displayed HEAD matched.
  All **21** shared source IDs stayed single-source across backend appearances.
  Shared-impact and dependent labels were shown. Evidence:
  `procedure-qa-source-identities.json` in the approved opencode temp directory.
- Created workspace `a164682e0c5c44a8be9acfa1c990f025` on the framework review
  base, not main. Native shared-source preview showed its unsaved marker in both
  backends while an independent remote-ref read confirmed no branch existed.
- Native first save committed only `wrap-up.text-004.md` as
  `d309a04cf52036c5cde90a845bbf244e5f52635c`. Controlled failure of the following
  PR step showed the correct saved-to-branch/PR-pending state. Native Retry PR
  created test PR #3 without changing that commit.
- Native second save changed `wrap-up.text-005.md` as
  `0a1680d7259a25193455e14a19b04321ee23690a`, reused PR #3 and preserved both
  edits. Combined previews contained the saved first edit and unsaved second
  draft in both backends. Native Tab/Enter navigation reached the declared
  canonical source, including when the large AX snapshot clipped lower links.
- A real outside writer advanced only this disposable branch to
  `30124943ae1c8d7cc50d1d4e304d190bdaa5d990`. Native stale Save refused and kept
  the draft. The test operator explicitly marked this disposable PR ready solely
  to test refusal; the application did not do it automatically. Ready and then
  closed PR saves both refused with the draft intact. App observed exactly two
  commits, plus the separate outside writer's third commit.
- Independently inspected PR metadata, commit list and two-file diff. Closed
  [test PR #3](https://github.com/alvseek/agent-memory-system/pull/3) without merge,
  then deleted only its owned `helheim/a164...` branch after checking exact HEAD.
- Created workspace `677658319b8f41afb58a43cb75b325d3`, then reserved its branch
  externally at the expected base. Native editor entry refused the existing
  branch rather than adopting/resetting it. Its HEAD stayed `6412c4d`; deleted
  only that owned collision branch afterward.
- Main stayed `7b4d204`; the framework review ref stayed `6412c4d`. No main merge,
  tag, image publication or production deployment. Evidence:
  `procedure-qa-live-pr3.json`, `procedure-qa-live-state.json`,
  `procedure-qa-live-external.json`, `procedure-qa-branch-collision.json`.

### Actual memory/state/security verification

- The live 33-editor HTTP/CSRF probe retained exactly 32 baselines, evicted only
  the oldest of its own 33, and closed all 32 retained sessions afterward.
  Evidence: `procedure-qa-capacity-result.json`.
- Waited the actual shipped **1,800-second** policy, not a shortened timer or
  fake clock. After 1,802 measured seconds the owned HTTP editor refused Save.
  Its earlier native browser sibling also refused after additional local typing,
  retained its draft/dirty state and left the independently observed stored
  revision unchanged. Evidence: `procedure-qa-real-idle-result.json`.
  Existing independent H4 suspended-save interleavings establish the separate
  in-flight-lock exception; no 30-minute network-blocked write is claimed.
- A guest's real selection change caused both native body/metadata saves to
  refuse without losing drafts. Separate HTTP calls returned 409 for both;
  owner revision stayed unchanged and guest home remained empty. Revoking that
  guest then produced native refusals and HTTP 403 for both areas. As an ungranted
  home caller, read/body/metadata requests returned 404. Missing, blank and
  invalid bearers returned 401. These use verified synthetic fixture actors;
  real-issuer expiry remains under M01/M07, not silently counted here.
- Native stale body and metadata writes both failed. The actual latest-record
  link opened a fresh tab, leaving the old drafts intact. Reapplied those drafts
  through native inputs, then saved with the new context successfully. A native
  double body-Save generated exactly one captured POST. Independent HTTP verified
  the recovered body/title; restored only the controlled record's original
  field values with revision/tenant guards afterward.
- The real HTTP matrix also covered append, prepend, multi-edit, archive and
  unarchive invalidating old body/metadata guards for agent/shared records.
  Near-simultaneous body/metadata writers produced exactly one 200 and one 409
  in each scope. Broader validation/default/clearing/deleted-record cases ran
  through actual HTTP and MCP, including 1,000/1,001-code-point Unicode limits
  and no owner/type mutation. Current SDK rejected the unsupported owner field.
- Exercised a stored private marker, closing-textarea/script payload, unsafe
  Markdown URL, preamble, Unicode and all LF/CRLF/CR forms. Native initial load,
  Preview, Save and stale failure rendered literal text: no injected script node,
  executable link or probe flag. No-change Preview kept exact raw body bytes;
  a subsequent native edit preserved untouched separators. Separate paged HTTP
  reconstruction verified length/hash/source order; the original body hash and
  title were restored after the probe.
- Before deliberate Inspector calls, generic history stayed empty and the marker
  was absent from its persisted database and all 15 inspected owned log/database
  files. Evidence: `procedure-qa-private-history-audit.json`.
- All nine product POST routes rejected 36 hostile-Origin/CSRF/Host probes
  without authority use. After the form repair below, repeated the live probe
  with explicit null Origin too: **45/45** refused, with Git counters and existing
  deliberate history unchanged. Evidence:
  `procedure-qa-live-write-guards.json` and
  `procedure-qa-live-write-guards-post-fix.json`.

### New runtime finding H5 — fixed, independently reviewed and review-published

Native Inspector Send initially returned 403 and created no history record.
Captured same-origin browser navigation headers showed `Origin: null`; the page
emitted `Referrer-Policy: no-referrer`. Replaced only that response policy with
`same-origin`: same-origin form origins are preserved and cross-origin referrers
remain suppressed. Strict Origin/Host/CSRF checks were not relaxed.

- Added three response-policy and nine null-Origin route regressions. Before
  repair: 3 failed / 9 passed. After repair: full Helheim suite **149 passed**,
  one real-server test deselected; full Ruff and diff checks clean. Evidence:
  `procedure-qa-native-form-red.xml`, `procedure-qa-native-form-green.xml`.
- Native Send then carried `Origin: http://127.0.0.1:18765`, returned 303 to a
  successful `pong` result and displayed 4 bytes/1 returned-text token. A native
  double click produced exactly one history call. Native Replay was read-only,
  retained the tool's POST action, and its Send created exactly the second
  deliberate call rather than a 405. Native History showed those two calls.
- Independent two-file security/privacy review found no new defect; its narrow
  tests passed 44 with four unrelated rendering cases deselected. Report:
  `procedure-review-native-form-fix.md`. Parent owns the native wire proof above.
- Published only the existing Helheim review branch:
  `4e903f20ef560e4b8c26c213ecb19a1d53d13f33`. No usual app upgrade/restart or
  production promotion. Helheim has no repository CI workflow; local proof is
  not presented as remote CI.

### Released-server compatibility and current recovery

Ran the already-released `699453f` image locally, identified by full revision and
digest `sha256:46d9a0e33ff892d62eda5fc05d9a32c81d486e677fc148a419b94ae31ce6a01a`,
on the owned QA backend port with a separate tmpfs/local-mode tenant. Existing
new-editor body and metadata saves both refused the now-missing capabilities,
retaining drafts and client revision. A same-UUID old-server sentinel, chosen
so an unsafe guard-dropping body fallback could have matched, stayed unchanged.
Metadata browsing worked; fresh Open refused before rendering writable controls.

After removing the owned old container, both areas also handled the offline
transport without advancing baselines or losing drafts. Restored only the
current QA backend and verified a fresh native load again exposes guarded editing
with the unchanged original context/body/title. This is actual old-release
capability and pre-write network-loss proof, not a committed-memory-write response
loss experiment. Evidence: `procedure-qa-legacy-container.json`.

### Content/API matrix and exact limitations

The indexed bench start/stop mechanisms ran a separate disposable loopback
instance. All seven converted procedure bytes matched local canonical DB output
over actual HTTP and MCP; prompt argument declarations/substitution, legacy
wait-options and separate resource delivery matched. Default get/query/awaken
did not gain editor fields; legacy edit/metadata and guarded result envelopes
kept their contracts. Agent/shared validation and sibling/concurrent writers
passed. Evidence: `procedure-qa-contract-jazdhshp/result.json` and its server log
(earlier run: `procedure-qa-contract-1jetd_ks/result.json`). Both temporary stores/
ports were removed and the pre-existing bench log restored.

The broad remaining rows are not marked complete:

| Rows | Outstanding boundary/coverage |
|---|---|
| M01, M17 | Actual released/deployed image and real-issuer/guest checks after separately authorized publication; local image/PG proof is already recorded |
| M04, M05 | Some full native browsing/progress and source-editor newline corner matrices; existing automated 42-case JS matrix and ordinary native flows are recorded, not relabelled as every manual case |
| M07 | Real issued-token expiry/identity matrix; local revoked/ungranted/invalid-token paths passed |
| M08, M13 | Full controlled transport-corruption and real GitHub branch/commit response-loss UI fixtures; automated cases plus actual partial-PR recovery passed |
| M15 | Rapid Close sometimes got ERR_EMPTY_RESPONSE: one fetch was observed, the session subsequently refused use, and drafts remained; ordinary single native Close and five persistent HTTP Close calls succeeded. No product cause was established. The separate minimal plain/ASGI response diagnostics all returned 200, so no universal path/JSON-body explanation is claimed |
| M16 | Global installed-command/deployment and unavailable-consumer portions; actual local HTTP/MCP content/default contracts passed |

Formal Helheim fixture-building gate: **Bench: not set up. Stack: unknown — no
indexed bench probe exists.** This does not negate the direct owned-runtime
checks above. The plan explicitly excludes building a new Helheim bench, so the
integration-test gate stops additional fixture scaffolding rather than inventing
a framework mid-run. No product code was changed to manufacture coverage.

### Teardown/retained inspection state

Test PR #3 is closed without merge; its branch and the separate owned collision
branch were verified deleted. The live-Git process and response diagnostic were
stopped. Legacy container/tmpfs and independent contract databases are removed.
The current memory QA services remain reachable for inspection, with original
fixture body/title/guest selection restored; revision dates legitimately changed.
Docker and the browser relay remain running, with no broad cache pruning. The
only deliberate generic history entries are the two harmless ping calls.
Production and the usual running Helheim were never restarted or deployed.

**Run**: 2026-11-18 · software-architect · Tactic C continuation — post-reboot native editor flow
**Automated**: Prior 10/10 groups retained; rebuilt Helheim environment rerun: 137 passed, one live-server test deselected.
**Manual**: Basic native memory-editor flow passed as detailed below; complete compound M04/M05/M10/M12/M15 matrices are not claimed.
**Sign-off**: NOT SIGNED OFF — remaining procedure/source, issuer/deployed and broader manual matrices still open.

### Environment repair and browser choice

- Laptop restart ended the temporary services/relay. Recreated only owned QA
  processes with saved PIDs and log files. Chrome reconnected, now with extension
  0.0.17 and relay 0.0.16, reporting compatible protocol 3. It still timed out on
  the record link; this is not claimed fixed by reboot.
- Chrome successfully read one concrete environment error on the metadata page:
  `ImportError: cannot import name 'exceptions' from 'jsonschema'`. Independent
  import probes confirmed the old temporary Helheim environment had an incomplete
  namespace-only jsonschema package; Munnin's repository environment imported it
  correctly. Why the temporary package files disappeared is not established.
- Created a fresh isolated `procedure-qa-postreboot-helheim` environment with
  `uv sync --locked`, verified `jsonschema.exceptions` and the exact composer Git
  SHA `6412c4dc47606f1d63807d33d4aa14cce013231d`, then gracefully replaced only
  the owned QA Helheim process. No product, lockfile, global package, user's
  usual Helheim instance or browser security configuration was changed.
- The OpenCode browser now captured screenshots and performed native controls.
  Used that working browser rather than continuing Chrome retry loops. Editor
  interactions below used browser click/key/fill tools (explicit Control+A
  before replacement), not page-evaluated setters or synthetic DOM clicks.
  Page evaluation was used only to observe state.

### Native flow actually exercised

1. Native Home → Memory → munnin → record navigation opened the editor with both
   areas and correct acting tenant. Screenshot capture now succeeded.
2. Changed a body word using keyboard/fill while preserving the original leading
   newline, Unicode, non-adjacent timestamp order and mixed newline conventions.
   Changed metadata too; both areas showed unsaved state.
3. Native Preview body showed the exact intended diff and reported no save.
   Independent authenticated HTTP reconstruction of both source-position pages
   verified original body hash/title unchanged before Save.
4. Native Save body reported success, reset only its dirty state and preserved
   the unsaved metadata draft. Separate HTTP reconstruction showed the exact
   expected CRLF/LF/Unicode body and original metadata.
5. Dirtied the body again, then native Save metadata succeeded with that new
   revision. The body draft stayed visible/unsaved; independent HTTP showed the
   persisted body hash unchanged and the intended metadata title updated.
6. Replaced metadata with invalid JSON and clicked native Save metadata. Clear
   validation feedback appeared, Save remained available, and both typed drafts
   remained. The actual rendered error/drafts were screenshot-verified.
7. Clicked native Close with dirty drafts. Inspected its exact confirm dialog;
   dismiss retained both drafts. Clicked Close anew, accepted the matching
   confirmation, then verified navigation to `/memory` without another dirty
   prompt. Tool-reported dialog interruptions were handled through the dialog
   API, not by repeating an unresolved click.
8. Generic inspector history remained empty after these editor interactions.
   Restored only this run's saved fixture body/title through guarded HTTP writes;
   independent paged HTTP reconstruction confirmed the original body hash
   `dd875932a52eeaa68bf3b81fb37d56d28adc2194e1a4160e88407f52c7840658`
   and title. The record revision/date legitimately changed during testing.

### Evidence and retained state

Native error/layout screenshot:
`C:/Users/alvia/AppData/Local/Temp/opencode-browser-5ZAAs2/0/screenshot.jpeg`.
Home screenshot:
`C:/Users/alvia/AppData/Local/Temp/opencode-browser-NaR11z/0/screenshot.jpeg`.
Rebuilt-environment JUnit:
`C:/Users/alvia/AppData/Local/Temp/opencode/procedure-qa-postreboot-helheim.xml`.
Read-only observer output:
`C:/Users/alvia/AppData/Local/Temp/opencode/procedure-qa-current-observation.json`.

Owned QA Helheim now runs from the repaired environment (PID 29300 at start);
the retained PID/start record is `owned-helheim-repaired.json` under the fixture
directory. QA services are intentionally kept running for follow-up, with their
fixture field values restored. No production/GitHub writes or release occurred.
The working OpenCode tab is on the Memory landing page. Chrome's failed owned
session remains a tooling limitation; no manual user help was needed for the
basic editor checks above.

**Run**: 2026-11-18 · software-architect · Tactic C continuation — server restored; browser diagnosis corrected
**Automated**: 10/10 groups retain prior unchanged-code proof.
**Manual**: No additional complete row; native driver reads remain unreliable.
**Sign-off**: NOT SIGNED OFF.

The user's screenshot showed `ERR_CONNECTION_REFUSED` at the metadata URL. That
current refusal was caused by this run's own earlier fixture shutdown, not proof
of a protected UI prompt. The driver had reported `protectedUi: true`, but no
visible popup was observed; the instruction to dismiss a known popup was
unsupported and is withdrawn.

Restarted both owned fixture processes from their existing scripts. Independent
HTTP reads now return 200 at `/` and `/memory/munnin`; actual Chrome Home rendered
and was captured again. Later native navigation/page reads still failed with
stale refs/body-read timeout while the metadata HTTP endpoint remained 200.
This remains a **qa** instrument issue of unestablished cause, not a verified
product defect or an identified Chrome popup.

A fresh owned `procedure-qa-flow` tab subsequently completed native Home →
Memory → munnin navigation, then timed out on the record-link click and its
screenshot. Independent HTTP retrieval of the exact record-editor URL returned
200 with the body editor present (4,201 bytes, 0.22 seconds). No editor save or
native editor pass was earned. No subagent was executing this QA; the coordinating
agent performed these calls directly.

Subsequently, the user supplied an actual Chrome screenshot of the record editor.
It visibly renders the fixture-owner account, original source-ordered body,
separate Metadata JSON area, both Preview controls, disabled unchanged-area Save
buttons, Close and the latest-record link. This verifies initial editor rendering
through the user's normal browser interaction; no popup is visible. It does not
verify save, conflict, keyboard, expiry or the complete M04/M15 matrices. The
automation driver remains a separate unresolved QA instrument issue.

The QA servers and owned Chrome session are intentionally left running for
immediate user inspection/follow-up, unlike the earlier teardown. Exact source
fixture directory: `C:/Users/alvia/AppData/Local/Temp/opencode/procedure-qa-chrome-20261118`.
Only disposable local data is served; production and the user's Helheim instance
remain untouched. Teardown is still required when this inspection ends.

**Run**: 2026-11-18 · software-architect · Tactic C continuation — quick Chrome connection repair
**Automated**: 10/10 groups remain green on unchanged product revisions; no suites rerun here.
**Manual**: Native home/navigation observation added; editor-specific rows remain incomplete.
**Sign-off**: NOT SIGNED OFF — Chrome protected UI prevented continuing the editor walk.

### Evidence and findings

- User requested Chrome and authorized whatever quick available repair would work.
  The detached relay had reported startup but was subsequently unreachable.
  Running the installed `browse serve` directly as a managed background shell
  made its HTTP endpoint reachable. The already-paired `chrome-spearhead` browser
  reconnected automatically with protocol 3 compatible; no installation, pairing
  reset, security switch, browser restart or browser settings change.
- Created only the owned `procedure-qa-chrome` session with exact loopback
  allowlist. Fresh byte-identical copies of the earlier verified fixture scripts
  used disposable SQLite data, synthetic verified actors and a fake Git adapter.
  A direct cross-site entry into the private record route was correctly refused;
  normal entry through Home → Memory → munnin worked via native Playwright clicks.
- Captured and visually inspected the actual Chrome home screenshot: header,
  Procedures/Memory/History navigation, server card and readable status were
  visible. Evidence:
  `C:/Users/alvia/AppData/Local/Temp/opencode-browser-files-47948-v3ED7U/procedure-qa-chrome-home.png`.
  This is actual Chrome visual proof for Home only, not the editor.
- Clicking the record link timed out; follow-up reads failed with destroyed
  execution contexts. Relay status then explicitly reported `protectedUi: true`
  on the owned tab. Stopped rather than retry-looping, resetting the page,
  synthesizing around the protected UI or changing security settings. The exact
  popup/prompt is not identified; the user must dismiss visible Chrome UI.
- Owner **qa**: browser setup is now connected, but protected-UI manual
  intervention remains open. No product defect or record-save outcome was
  established by the failed click. No GitHub/source or memory writes occurred.

### Teardown and retained state

Both fixture servers acknowledged shutdown and exited; owned ports 18200/18765
closed and exact temporary DB/WAL/SHM files were removed. The connected relay
remains running for follow-up. Its one owned Chrome tab/session is retained for
the user to dismiss the protected prompt, not reset to evade it. Production and
the user's Helheim instance remain untouched.

**Run**: 2026-11-18 · software-architect · Tactic C continuation — real local PostgreSQL and application image
**Automated**: 10/10 groups green, combining unchanged-revision evidence from the preceding run with the newly executed A04/A05 engine cases.
**Manual**: 0/17 fully passed; prior partial observations retained, with additional M01/M12/M16/M17 local-image evidence below.
**Sign-off**: NOT SIGNED OFF — native UI, real-issuer/deployed proof and unwalked/partial scenario matrices remain outstanding. No release or archive approval.

### Evidence and limits

- User said "proceed" after the prior partial result. Docker was still stopped;
  started it through its installed `docker desktop start --timeout 90` command.
  The engine answered Linux 28.5.1. No Docker update, production service restart,
  power-plan change, system configuration rewrite or production deployment.
- Created a uniquely named `postgres:17-alpine` container using the existing CI
  service shape: `pagination_qa_editors`, loopback-only dynamically assigned port
  and temporary data mount. Verified container ownership label, host binding and
  actual database identity before supplying the DSN to existing tests. No host
  directory, production DSN or shared database was mounted/passed to tests.
- Existing `tests/data_repositories/test_edit_guards.py`: **19 passed**, no skips,
  covering SQLite and actual PostgreSQL with agent/shared variants. Existing
  `pytest -m postgres`: **120 passed / 947 deselected**, no skipped cases. These
  suites overlap; their test counts are not added. The latter includes real
  PostgreSQL through authenticated HTTP/MCP adapter integration using synthetic
  verified actors and in-process ASGI, not a real issuer or remote deployed API.
  A04/A05 are now ticked; other automated groups retain prior unchanged-code proof.
- Evidence: approved temp directory, `munnin-qa-editors-768757a57639.json`,
  `.guards.xml` and `.postgres.xml`. Container
  `c2dc5b6ef3403995b068769295549a3239127c0e9713b3703fa6454080bb727e`
  was removed afterward; no test database or listening service was retained.
- Built the current Munnin Dockerfile locally with its pinned framework sources.
  It included/imported composer 0.1.0, booted as shipped and served all 16
  procedure bodies without runbook leak markers. The actual image accepted
  HTTP agent/identity creation in its temporary SQLite data mount; default reads
  omitted editor fields, opt-in reads returned the expected tenant/context,
  guarded body edits preserved mixed newlines and metadata, and stale revisions
  or wrong tenants returned HTTP 409 without overwriting stored state.
- The image run deliberately used explicit loopback-only local mode, not issuer
  authentication. It proves build/package/runtime/HTTP wiring; it does not prove
  deployed image identity, OAuth, guest authorization in the image or live
  PostgreSQL-backed container HTTP calls. M01/M12/M16/M17 remain partial.
  Successful image ID:
  `sha256:ede2ff9390e9009b57b9a69fcdf2b344507c9adc8aefec5d678b3f302d835459`.
  Evidence: `munnin-qa-image-b79781a76a94.json`, `.build.log`, `.runtime.log`.
- The first image driver attempted HTTP before app readiness and did not handle
  a transient `RemoteDisconnected`. It stopped early, retained evidence and
  removed its owned image/container. Fixed only the temporary QA driver's
  readiness handling and reran; the complete run above passed. No product-code
  repair was made or disguised as a passing first attempt. First-attempt evidence:
  `munnin-qa-image-b176c8d80ef4.json` and corresponding build/runtime logs.
- Rechecked browser capture on a new owned about:blank tab after focus: the
  desktop pane was still not visible, so screenshot capture refused. Closed that
  tab. Alternate browser relay was unreachable/stopped; no browser pairing,
  extension installation, security widening or settings change was attempted.
  Native interaction/layout sign-off still requires a visible desktop browser.

### Findings and teardown

| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Prior missing local PostgreSQL execution | qa | Closed for automated engine groups: actual local 19-case guard and 120-case PostgreSQL runs passed |
| 2 | Prior missing application-image build/runtime proof | qa | Local build and loopback HTTP checks passed; deployment/issuer/PG-backed image matrix still open |
| 3 | Native browser pane remains hidden; other manual matrices incomplete | qa | Open — visible pane and remaining approved runtime prerequisites required |
| 4 | Temporary image-driver readiness failure | qa | Fixed and rerun successfully; no product defect identified on exercised paths |

All three owned QA containers (PostgreSQL and two image attempts) were verified
absent afterward. Owned application-image tags were removed, their ephemeral
databases disappeared with their containers and the successful HTTP port closed.
Docker Desktop remains running; shared caches/base images were not pruned.
Production, GitHub refs and the user's Helheim instance remain unchanged.
QA record and coordinating-plan updates are local, not committed/pushed.

**Run**: 2026-11-18 · software-architect · Tactic C plus isolated Tactic A smoke
**Automated**: 8/10 groups green; A04/A05 partial locally (PostgreSQL cases skipped).
**Manual**: 12/17 rows partially exercised, 5/17 not walked; 0/17 fully passed.
**Sign-off**: NOT SIGNED OFF — native UI, full scenario matrices, real-issuer/nonproduction PostgreSQL runtime and deployed-image proof remain outstanding. No archive or release approval.

### Evidence and scope

- Revisions remained framework `6412c4d`, Munnin `fb7ab77`, Helheim `914b8bc`,
  coordinating plan `0a7f64a`; no product changes, release or user-instance restart.
- Munnin's five named test files (content loader/fidelity, edit context, guards and
  API contract): 58 passed, 9 PostgreSQL cases skipped. Framework compiler tests:
  30 passed. Helheim memory/routes/GitHub/workspaces/JavaScript-wrapper files:
  76 passed. Direct production-JS runner: 42 passed, none skipped/failed; these
  overlap the wrapper and are not added to the Python counts.
- The existing exact-SHA Munnin CI run
  [44110391384](https://github.com/alvseek/agent-memory-server/actions/runs/44110391384)
  was rechecked successful for `fb7ab77589fdcd689d1f62e71b6ae72586fa4c7d`,
  including its separate actual PostgreSQL job. Earlier observed 120 passing
  PostgreSQL tests remain CI evidence, not a new local runtime run. Local Docker
  reported no dockerDesktopLinuxEngine pipe, no PostgreSQL binary was found and
  no `MUNNIN_PG_TEST_URL` was configured. A04/A05 stay unchecked for this run.
- Existing runbook/table mechanisms resolved and ran unmodified, with explicit
  SQLite/loopback overrides and an owned temporary database at port 18201.
  RESET, INJECT (329 imported meta/shared records), ACT and OBSERVE all returned
  zero; smoke health/awaken/prompts/resource checks passed. The runbook's live
  no-leak sweep checked 16 prompt responses, all Markdown, with zero forbidden
  markers. This is local unauthenticated bench proof, not cloud/issuer proof.
- Reused the previously verified temporary Munnin/Helheim fixture scripts by
  byte-exact copy into a fresh owned directory. Munnin used real SQLite, HTTP,
  MCP, tenant resolver/sharing and `StaticTokenVerifier` owner/guest actors;
  Helheim used actual delivered browser JS and MCP transport. The Git adapter
  remained fake and received no calls in this run. No new fixture was improvised,
  no real issuer exchange or remote GitHub write is claimed.
- In the actual browser page, source-position pages loaded non-adjacent equal
  timestamps, a leading newline, Unicode and mixed CRLF/LF. A DOM-event body edit
  preserved the exact untouched delimiters; a separate authenticated HTTP reader
  fetched both pages, reconstructed by positions and verified complete length/hash.
  Initial comparison of just one page was invalid; it was corrected before any
  fidelity conclusion. Metadata remained unchanged after body save.
- Both dirty-area directions were exercised: body save retained metadata draft;
  metadata save retained body draft and left its persisted body hash unchanged.
  A 1,001-code-point summary was refused with both drafts retained and Save enabled.
  An outside HTTP metadata change caused the old browser body save to conflict,
  retaining both drafts rather than overwriting it.
- A guest successfully saved to the displayed owner tenant. An independent real
  HTTP tenant-selection change made the next browser body save refuse account
  mismatch. Restoring selection then revoking membership through the real HTTP
  administration route made the next metadata save refuse access. Browser drafts
  remained intact; independent owner HTTP reads showed no refused draft applied,
  and the guest's home listing stayed empty. These use synthetic verified actors,
  not real issuer identities, and do not cover the complete two-area matrix.
- Actual browser confirm dialogs were dismissed then accepted for Close. Cancel
  retained both drafts; accept navigated to `/memory`. The ended session's save
  returned 400 with reopen guidance; local inspector history remained empty.
  The 33-editor cap and 30-minute wall-clock path were not manually walked.
- The browser pane was not visible after focus, so screenshot capture refused.
  Its Fill tool appended instead of replacing text; that instrument behavior was
  detected and the field reset before Save. Subsequent interactions explicitly
  used DOM input/click events. They are functional browser checks, not native
  click/keyboard/focus/layout/pixel verification. One expected-heading wait used
  the wrong wording; direct page inspection confirmed successful Close navigation.
- Evidence: approved temporary root `C:/Users/alvia/AppData/Local/Temp/opencode/`,
  JUnit files `procedure-qa-20261118-{munnin,framework,helheim}.xml`,
  `procedure-qa-20261118-node.log`, smoke
  `procedure-qa-bench-rxo9a1ml/result.json`, and
  `procedure-qa-current-observation.json`. No full private import body was emitted
  as tool output; the disposable imported database was removed after smoke.

### Manual row accounting

| Rows | Status this run | Remaining proof |
|---|---|---|
| M01 | Partial: local revisions/capabilities exercised | Real issuer, running image and deployed pin inspection |
| M02, M03 | Not walked | Canonical source UI and actual disposable GitHub branch/PR workflow |
| M04 | Partial: two-page exact browser load and independent source-position/hash reconstruction | Broader load-progress/browsing observations and native UI |
| M05 | Partial: both save/draft directions, Unicode/mixed newline edit | Source editor, split/join/insert/delete/empty/successive matrix |
| M06 | Partial: selected-account body refusal | Metadata refusal and real-issuer matrix |
| M07 | Partial: revoked guest metadata refusal | Body refusal, stranger and invalid/expired real-token matrix |
| M08 | Not walked | Controlled interrupted/corrupted/mixed runtime-page fixture |
| M09 | Partial: outside-write stale body refusal | Metadata, reload/reapply, lifecycle/sibling writers and simultaneous runtime saves |
| M10 | Partial: Close cancel/accept and ended-session refusal | Actual 33-editor LRU, 30-minute idle expiry, in-flight runtime matrix |
| M11 | Not walked | Isolated legacy/capability-loss server and uncertain-write recovery |
| M12 | Partial: oversized summary refusal and unchanged data | Both-face/type/boundary/clearing/lifecycle matrix |
| M13 | Not walked | Actual controlled lost GitHub response/PR-check failure workflow |
| M14 | Partial: empty local history and refusal bodies | Persisted/log marker audit, runtime XSS and all sibling security cases |
| M15 | Partial: functional JS controls/messages | Native clicks/keyboard/focus/layout and inspector regression walk |
| M16 | Partial: real local HTTP content surface and no-leak sweep | Full HTTP/MCP defaults, installed commands and downstream consumer matrix |
| M17 | Partial: exact-revision PostgreSQL CI rechecked | Authenticated isolated PostgreSQL runtime and image/deployment evidence |

### Findings

| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Native UI observation unavailable: hidden pane; Fill semantics unreliable | qa | Open — show the desktop browser pane before native UI sign-off |
| 2 | No local disposable PostgreSQL runtime; current CI proof does not replace it | qa | Open — provision an approved isolated PostgreSQL test target or explicitly defer |
| 3 | Real-issuer/deployed-image and remaining runtime matrices are not verified | qa | Open — approved test identities/environment and remaining assets/scenarios required; missing fixture work belongs to integration-test, not improvised in this run |
| 4 | No product failure was observed on the paths exercised | product-defect | No defect identified; this is not full-checklist approval |

### Teardown

- Smoke server stopped using the indexed bench stop script; port 18201 closed,
  exact temporary DB/WAL/SHM removed, pre-existing bench log restored byte-for-byte.
- Both disposable browser-fixture servers acknowledged shutdown and exited; their
  owned ports 18200/18765 were checked closed. Both owned browser tabs closed.
  Exact owned Munnin/Helheim SQLite/WAL/SHM files were removed; scripts and bounded
  test evidence remain in the approved temporary directory. One browser cleanup
  fetch failed with an unknown outcome; no write was retried, and successful
  server shutdown/database teardown established final cleanup independently.
- Production, the user's Helheim instance, review/main GitHub refs, real account
  invitations/selections and Windows settings were not changed by this QA run.
