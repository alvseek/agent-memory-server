# Content summary input limit — QA Checklist

**Source**: Quick Wizard plan approved in conversation on 2026-11-14; changes in
`MemoryService.insert`, `MemoryService.edit_metadata`, both adapter descriptions,
and the summary-limit tests.
**Purpose**: Detect partial writes, accidental byte-counting, and broken access to
legacy summaries after introducing a write-time limit.
**Apps under test**: Munnin service, MCP and HTTP. No schema, importer, Hermod,
Helheim implementation, or existing stored summary was changed.

## Terminology & state model

- **Limit**: 1,000 Unicode code points (Python `len()`), not bytes, tokens, or
  displayed glyphs. Combining marks count separately; text is not normalized.
- **New input**: any non-null summary supplied to `insert` or `edit_metadata`,
  including an upsert of an existing UUID. The rule applies to either scope and
  every record type that supplies a summary.
- **Legacy**: a stored summary above the ceiling. Reads preserve it, and metadata
  edits that omit/null the summary do not revalidate it.
- **Rejection**: the entire operation fails before persistence. It does not
  truncate the text or update another supplied field.

**Key invariants to disprove**
- An invalid summary cannot partially update a title, body, or other metadata.
- UTF-8 size cannot make a valid 1,000-character summary fail.
- Enforcing input length cannot hide, truncate, or block an unrelated edit of a
  legacy record.

## Happy path — single end-to-end scenario

Use an isolated local stack or disposable tenant, never reset the production store.

1. Create a disposable agent through `create_agent`. Read the current knowledge
   template and use its exact `template_version` when inserting a knowledge record.
2. Insert a summary of exactly 1,000 characters and save its UUID and returned
   content. Read it back without shortening.
3. Submit 1,001 characters through `edit_metadata` together with a changed title.
   Expect rejection naming `1000` and `1001`; read back the original title and summary.
4. Replace the summary with a short description; expect success. Repeat the boundary
   through the other transport, then retire only the disposable records.

## Automated coverage

| Item | Automated test | Still manual |
|---|---|---|
| Exact limit counts Unicode rather than bytes | `test_summary_limit_accepts_exactly_1000_unicode_characters` | Deployed version |
| Rejected creation leaves no row | `test_oversized_insert_creates_nothing` | Deployed version |
| Rejected upsert/metadata edit changes nothing | `test_oversized_summary_rejects_the_entire_write` | Deployed version |
| Legacy reads, indexes, unrelated edits, shortening and clearing work | `test_legacy_summary_is_readable_and_unrelated_edits_still_work` | Existing deployed data |
| Optional summaries are bounded too | `test_limit_also_applies_to_optional_summaries` | Deployed version |
| HTTP/MCP surface the error and expose the documented ceiling | `test_summary_length_limit_over_http`, `test_summary_length_limit_over_mcp` | Proxy, real auth, and Helheim presentation |

Service tests live in
[test_summary_limit.py](../../tests/business_services/test_summary_limit.py), with
both real repository backends parameterized; PostgreSQL requires
`MUNNIN_PG_TEST_URL` pointing at a disposable database. The face tests live in
[test_write_faces.py](../../tests/api_http/test_write_faces.py) and
[test_write_tools.py](../../tests/api_mcp/test_write_tools.py), over in-process clients
and real temporary SQLite. None proves a running server was upgraded.

## Checks

- [x] **Automated**: Exactly 1,000 ASCII, CJK and emoji code points survive insertion;
  a 1,000-character replacement succeeds in both agent and shared scope.
- [x] **Automated**: A 1,001-character creation fails and query finds no row.
- [x] **Automated**: A rejected upsert or metadata edit leaves the previous summary,
  title and body unchanged in both scopes.
- [x] **Automated**: A 2,000-character legacy summary stays complete in `get` and the
  awakening index; changing its title works; explicitly shortening or clearing its
  summary still works.
- [x] **Automated**: An oversized optional summary on an identity record is refused.
- [x] **Automated**: HTTP returns 400, MCP raises a tool error, and both name the maximum
  and actual length. The API descriptions advertise the same ceiling; valid emoji
  replacements succeed.
- [x] **Manual**: Run the happy path through the running MCP and HTTP interfaces with
  the actual configured auth. Confirm errors do not become generic 500s through the
  deployed stack and accepted strings are not truncated.
- [x] **Manual**: Read a known pre-existing oversized summary before and after upgrade,
  without modifying it. Compare the full value, not just its displayed preview.
- [ ] **Manual, UI-bound**: In Helheim, inspect the refreshed `insert`/`edit_metadata`
  parameter descriptions, then submit an oversized summary on a disposable record.
  Confirm the error is readable, Send becomes usable again, and the prior value remains.

## Result

**Run**: 2026-11-14 · software-architect · Tactic C, deployed PostgreSQL/OAuth and Chrome
**Automated**: 6/6 green · **Manual**: 2/3 complete; UI row partially observed
**Sign-off**: NOT SIGNED OFF — Helheim error presentation and post-error Send recovery
remain unobserved; the browser target stopped responding before submission.

### Evidence
- Product `740de43`: CI run `43543209265` passed both jobs (Linux default suite:
  900 passed, 133 skipped; PostgreSQL subset: 111 passed, 922 deselected).
  Image build `43543209257` succeeded for the same full commit.
- Deploy run `43543348532` succeeded. Independently observed
  `munnin-web-740de43`, image `ghcr.io/alvseek/munnin:740de43`, healthy on the host;
  public `/health` answered 200.
- Using the existing real OAuth credential, exercised deployed HTTP and network MCP
  against the live PostgreSQL store. In both agent and shared scope, exactly 1,000
  emoji code points survived; 1,001-character upserts and metadata replacements
  were rejected with the maximum and submitted length. Reads confirmed unchanged
  title, body and summary, followed by successful short replacements.
- The pre-existing example's complete 14,238-character summary matched the
  pre-upgrade value byte-for-byte (same SHA-256 recorded below). No legacy summary
  was edited or truncated.
- Created only disposable records under the existing agent/shared scopes; no test
  agent or tenant was added. All four API-test records and the additional UI-test
  record were tombstoned in cleanup and confirmed to return 404. Tombstones remain
  in storage by the API's design; no claim of physical row removal is made.
- Chrome loaded Helheim's refreshed `edit_metadata` form, visibly including
  "Maximum 1000 Unicode characters; longer input is rejected, never truncated.
  Aim for 300-500 characters." Filling the disposable UUID succeeded, then filling
  the title timed out; a fresh snapshot also timed out and relay status marked the
  target `protectedUi`. Stopped rather than retrying or submitting through another
  route. No Send click ran; the disposable record remained unchanged before cleanup.
- Browser sessions created for this run were deleted. The user's Helheim process
  was left running; its existing local call history was not altered or purged.

### Findings
| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Deployed OAuth/PostgreSQL behavior and preservation of the legacy example are proven. | qa | Closed |
| 2 | Helheim's field description was visible, but browser control stopped before submitting an oversized value; error rendering and Send recovery are unobserved. | qa | Open — manual browser check remains |

**Run**: 2026-11-14 · software-architect · Tactic C, local socket verification
**Automated**: 6/6 green · **Manual**: 0/3 complete (running local interfaces exercised;
real issuer/deployed stack and UI await release)
**Sign-off**: NOT SIGNED OFF — live deployment, legacy comparison and UI remain.

### Evidence
- Full suite: 910 passed, 123 skipped. Targeted summary-limit cases: 17 passed,
  15 PostgreSQL cases skipped because no local test DSN was configured.
- Scoped ruff and `git diff --check` passed; static quality review found no issues.
- Booted through the bench ACT script on port 18200 using an isolated temporary
  SQLite database and explicit local auth. No production RESET or INJECT ran.
- Bench OBSERVE passed all five probes. The runbook's served-content sweep found
  no vocabulary leaks across 16 prompts.
- Real network MCP and HTTP each accepted 1,000 emoji code points in both scopes,
  rejected 1,001-character creation/upsert/metadata writes, preserved the previous
  title/body/summary, and accepted a short replacement.
- An isolated pre-limit 2,000-character row remained complete through a live GET
  and unrelated title edit. Live MCP descriptions advertised the 1,000-character cap.
- Finally stopped the owned server through the bench stop script, confirmed its
  port closed, and removed the temporary database with its temporary directory.
- Captured the deployed example `ac3b4476-dd15-552d-8e2e-69b189a934fe` read-only
  before release: 14,238 summary characters; SHA-256
  `42f1145c7a0eede7745546763adadfafa7cf8db85031e6d43e2c56d98b0ef74d`.

### Findings
| # | Finding | Owner | Status |
|---|---|---|---|
| 1 | Real issuer, deployed PostgreSQL and Helheim presentation are not proven by a local-mode socket test. | qa | Open — verify after release |
