# UUID Prefixes — QA Checklist

**Source**: High Wizard short-UUID plan, 2026-11-09, in the deployment repository.
**Purpose**: Catch wrong-record writes, hidden cross-tenant matches and transport differences when abbreviated IDs reach Munnin.
**Apps under test**: Munnin repository/service and MCP/HTTP faces. Helheim is a caller, not modified by this change; Hermod-specific tools are outside scope.

## Terminology & state model
An exact stored identifier wins. Otherwise, at least six hexadecimal characters identify a UUID prefix; case and hyphens do not matter. Candidates are counted only inside the selected tenant and the operation's existing lifecycle visibility. Reads and unarchive exclude tombstones; archive/delete preserve their pre-existing idempotent access to tombstones.

**Key invariants to try to disprove:**
- A second matching record cannot turn a write into a first-match guess or a multi-row update.
- A record in another tenant cannot affect the result or appear in a candidate list.
- The full stored ID and its spelling do not change when an abbreviation is used.
- Creating a record with an explicit ID cannot overwrite a prefix-matched neighbour.

## Happy path — run first
1. On a disposable local/test tenant, create two knowledge records with distinct eight-character starts but the same first six characters; save their full IDs.
2. Read the first by an uppercase, hyphen-varied eight-character prefix over MCP and HTTP; both must return its original full UUID.
3. Append through that prefix; reread both full IDs and verify only the first changed.
4. Repeat with the shared six-character prefix: both faces must report ambiguity and neither record may change.
5. Repeat the safe read against the deployed server and inspect the result in Helheim. Clean up only the disposable records by full ID.

## Automated coverage
| Item | Automated tests | Still manual / environment-specific |
|---|---|---|
| Unique prefixes target one record for every operation | `test_unique_prefix_for_every_operation`, `test_unique_prefix_success` | Deployed image and real OAuth callers |
| Ambiguous reads/writes return choices without any change | `test_cross_table_ambiguity_never_writes`, `test_ambiguity_error_and_no_write` | Helheim's visual presentation |
| Six hex minimum; case/hyphens; invalid patterns refused | `test_normalized_prefix_read`, `test_invalid_prefix_is_refused`, `test_invalid_prefix_is_http_400_not_500` | None for repository/adapter contract |
| Cross-tenant rows cannot match or create ambiguity | `test_other_tenant_does_not_match_or_cause_ambiguity`, existing sharing/isolation tests | Selection via real shared-account OAuth session |
| Lifecycle and exact legacy ID compatibility | `test_lifecycle_visibility_is_preserved`, `test_exact_legacy_ids_take_precedence`, `test_exact_deleted_legacy_id_is_not_reinterpreted_as_a_prefix` | None for tested database behavior |
| Normalized and exact collisions are not first-match wins | `test_normalization_collision_is_ambiguous_but_exact_id_wins`, `test_same_exact_uuid_in_both_tables_is_never_arbitrarily_selected` | None for tested database behavior |
| Service call really reaches resolution and returns canonical IDs | `test_service_prefix_targets_one_record_and_refuses_ambiguous_write` | Separate deployed artifact proof |
| Creation still uses literal IDs | Existing insert/upsert tests, plus `test_exact_legacy_ids_take_precedence` creates a literal six-character ID alongside a longer UUID | Deployed caller behavior |

## Checks
- [ ] **Automated**: Run repository/service prefix tests against SQLite and PostgreSQL; both must execute, not merely collect or skip.
- [ ] **Automated**: Run both adapter test variants; unique results retain full UUIDs, ambiguity is HTTP 409 or an actionable MCP error, and bodies/metadata/lifecycle are unchanged after refusal.
- [ ] **Automated**: Run the full suite and lint to detect regressions in import, sharing, archival, soft-delete and legacy exact identifiers.
- [ ] **Manual**: After deployment, compare one existing record read by full ID, six-character prefix and case/hyphen-varied prefix through real authenticated MCP and HTTP.
- [ ] **Manual**: Use disposable records to verify real deployed ambiguity/no-write and unique-prefix append; clean up by their recorded full IDs only.
- [ ] **Manual, UI-bound**: In Helheim, a successful short-ID call shows the full UUID; an ambiguous call visibly presents both IDs/titles rather than a blank result.
- [ ] **Manual**: In a real shared-account session, switch tenant and confirm prefixes resolve within that selection, not the home account or another tenant.
- [ ] **Manual**: In an isolated environment, interleave an insertion with a prefix write; it must either target the one resolved full UUID or fail, never update several records. A short prefix is not a durable reservation across requests.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
