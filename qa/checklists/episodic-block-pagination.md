# Episodic Block Pagination — QA Checklist

**Source**: High Wizard plan `plans/2026-11-09-munnin-episodic-block-pagination.md` in the deployment repository, executed 2026-11-10.
**Purpose**: Catch a page that silently drops, splits or miscounts a block — on Munnin's two engines, on Hermod's independent pager, and in the consumer's rendering — and prove the byte ceiling never cuts a timestamp group in half.
**Apps under test**: Munnin over MCP and HTTP against SQLite and PostgreSQL; Hermod's direct-store awakening; universal-chat-agent's prompt renderer; the served `db.md` / `load-episodic.md` / `awaken-coder.md` text.

## Terminology & state model
A **block** is one sub-episode: a `### ` heading whose text carries an H3 timestamp, plus everything under it until the next such heading. A **group** is every block sharing one timestamp. Pagination counts **groups, not blocks**: `limit` is a group budget, `blocks_returned` and `blocks_total` are group counts, and the **cursor** is the H3 timestamp of the first group not returned.

The ceiling (`MUNNIN_MAX_BODY_BYTES`, `HERMOD_MAX_BODY_BYTES`, both default `32_000`) shrinks a page; it never splits a block and never drops the first one, so a single group larger than the ceiling is still emitted whole.

**Key invariants to try to disprove:**
- A page never splits a timestamp group, even when that group alone exceeds the ceiling.
- `blocks_returned` matches the groups actually present in `content`; a terminal page reports fewer than `blocks_total` with `next_cursor` absent.
- `next_cursor` names the first group **not** returned, and resuming from it re-reads exactly there after a new block is prepended — it is keyset, not an offset.
- `get(uuid)` with no cursor returns the whole record, unchanged from before this feature; `awaken` pages the newest episode only.
- Search returns hits with a bounded snippet and no bodies; query returns a projection carrying `blocks_total`.
- An ordinary single-page record renders byte-for-byte as it did before.

## Happy path — run first
1. On a disposable database, create one episode with thirty timestamp groups in which two adjacent groups share a timestamp; record its uuid.
2. Call `awaken` as that agent. The newest episode must carry `content`, `blocks_returned` (3 by default), `blocks_total` (30) and `next_cursor` equal to the fourth group's timestamp.
3. Pass `next_cursor` to `get` with a `limit` that lands a boundary inside the equal-timestamp pair. Both blocks of that pair must arrive in the same page.
4. Prepend a new block to the record, then resume from the earlier cursor. The same groups must come back — proof the cursor is a timestamp, not a position.
5. Repeat steps 2–4 over HTTP, then repeat the whole sequence against a real PostgreSQL database rather than SQLite alone.

## Automated coverage
| Item | Automated tests | Still manual / environment-specific |
|---|---|---|
| Both pagers agree on all 40 shared vectors | Munnin `test_episode_page.py` (`test_vector`, `test_error_vector`, sha pinned); Hermod `test_episode_page.py` (same file, sha `cbaeac95…b588a4a` pinned) | Nothing — this is the parity contract |
| Ceiling never splits a group; an oversized first group still emits | `ceiling-never-splits-a-group`, `ceiling-stops-before-exceeding`, `ceiling-oversized-first-group-still-emitted`, `ceiling-counts-utf8-bytes-not-characters`; `test_ceiling_never_splits_a_group` | Real memory pressure at the deployed ceiling value |
| Equal timestamps are one indivisible group | `equal-timestamps-adjacent-*`, `equal-timestamps-nonadjacent-*`; `test_nonadjacent_grouping_reconciles_every_slice_once` | A record that grows mid-read (see step 4) |
| Cursor is the first group not returned and survives a prepend | `many-units-page-1/2/terminal`, `legacy-cursor-colon-resolves-dot`, `legacy-cursor-bracketed-resolves`; `test_get_pages_on_request_and_resumes_inclusively` | Deployed resume after a real write |
| Counts measure groups and agree between page and total | `test_count_groups_agrees_with_the_page`, `test_the_group_total_matches_the_page_engine_for_every_shape` | Deployed payload inspection |
| `awaken` pages the newest episode and leaves other layers whole | `test_awaken_pages_the_latest_episode_and_keeps_every_other_layer_whole` | Deployed `awaken` for a real 250K-char record |
| `get` bounded by the ceiling, paged on request, both engines | `test_get_pages_on_request_and_resumes_inclusively`, `test_a_final_page_can_return_fewer_than_total_with_nothing_left`, `test_the_page_contract_holds_on_both_engines` | Deployed `get` over real OAuth; a record larger than the ceiling |
| Search snippets carry no bodies; query carries `blocks_total` | `test_a_search_hit_carries_a_snippet_and_no_body`, `test_search_snippets.py` (6 cases), `test_search_over_postgres.py` | Deployed search in Helheim |
| Ceiling is configured and validated, not hard-coded | `test_the_page_ceiling_has_one_documented_default`, `test_the_page_ceiling_is_read_from_the_environment`, `test_a_bad_page_ceiling_refuses_to_load` | The deployed container's env value |
| Hermod pages its own store independently | `test_awakening_pagination.py` (5 cases), `test_episode_page.py` | Cross-server resume over TCP against a deployed Hermod |
| The consumer renders counts, uuid and cursor without extra requests | `test_a_partial_page_in_a_single_record_layer_keeps_its_notice`, `test_a_partial_page_in_a_list_layer_keeps_its_notice_under_a_nonstandard_name`, `test_an_ordinary_record_renders_byte_for_byte_as_before`, `test_a_complete_final_page_carries_no_notice`, `test_unusable_page_metadata_is_ignored_rather_than_half_reported` | A real chat turn against the deployed Munnin |

## Checks
- [ ] **Automated**: Run both pagers' vector suites and confirm the sha256 pin matches on both sides — a drift in one file must fail, not pass silently.
- [ ] **Automated**: Run the Munnin read, projection and search suites against SQLite **and** `-m postgres`; both must execute, not merely collect.
- [ ] **Automated**: Run Hermod's full suite.
- [ ] **Automated**: Run the consumer's renderer suite and confirm the ordinary-record case is byte-for-byte unchanged.
- [ ] **Automated**: Confirm `MUNNIN_MAX_BODY_BYTES` and `HERMOD_MAX_BODY_BYTES` default to `32_000` and that a non-positive value refuses to load.
- [ ] **Manual**: After deploy, `awaken` the `lsgi-unreal` agent and confirm the newest episode reports `blocks_returned` < `blocks_total` with a `next_cursor` present.
- [ ] **Manual**: Resume that record from its `next_cursor` and confirm the first block returned is the one the cursor named.
- [ ] **Manual**: `read_procedure` for `db.md` and `load-episodic.md` returns the updated text that documents groups, counts and the cursor rule.
- [ ] **Manual**: `get(uuid)` with no cursor returns as much as the ceiling allows — the whole body for a small record, one page with a `next_cursor` for a record larger than the ceiling — and `get` with a cursor resumes at the group that cursor names; checked over both MCP and HTTP.
- [ ] **Manual, UI-bound**: In a real chat turn, a partial record visibly shows the counts, the record uuid and the next cursor, and the transcript makes no second memory request to fetch the rest.
- [ ] **Manual**: Confirm the `search` result a caller sees carries a snippet and no full body, and that `query` returns `blocks_total`.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
