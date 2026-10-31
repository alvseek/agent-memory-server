# Account sharing by tenant selection — QA Checklist

**Source**: High Wizard session 2026-10-28 → 2026-10-31 (`agent-memory-server`, uncommitted at the time of writing)
**Purpose**: confirm that a second person can work inside an account with their own login, that switching is explicit and remembered, that revocation takes effect on the next call, and that nothing about record scoping moved.
**Apps under test**: Munnin (schema, sharing repository and service, resolver, MCP face, HTTP face, pages) and the served procedure. **Not touched**: Hermod's store, the markdown backend's mechanics, the importer's markdown parsing.

## Terminology & state model (read first)

- **home tenant** = the account a login resolves to. Always exactly one, unchanged by this feature.
- **selection** = `account.active_user_id`: the tenant a person is acting in. `NULL` means "their own", and that is the only representation of "at home".
- **grant** = a `tenant_access` row: owner's tenant, member's tenant, `granted_date`, nullable `revoked_date`. Your own tenant never needs one.
- **invite** = a `tenant_invite` row: a single-use, expiring code naming the tenant it admits to.
- **caller block** = `awaken`'s top-level `caller`: who is signed in, and whether they are a guest in the account being read.

**Key invariants** (each is a thing to *disprove*):
- Every memory query still belongs to exactly one `user_id`. Nothing unions two tenants.
- A revoked selection makes memory calls refuse **by name**, never fall back to the caller's own tenant.
- The membership tools answer while every memory tool refuses, because they resolve the home tenant only.
- Joining or leaving never moves a record, and never touches the joiner's own account.
- An authored `user_profile` is never overwritten by the seed, and a login with no name writes nothing.

## Happy path — single end-to-end scenario (run this first)

1. As Alvi in Helheim, `create_invite()` → a code and an expiry. *(A)*
2. As Roy, in a real client signed in with his own account, `redeem_invite(code)` → `{"tenant_user_id": "<alvi>", "role": "guest"}`. His own tenant is untouched. *(A, B)*
3. Roy calls `list_tenants()` → his own first (`owner`, `active: true`), Alvi's second (`guest`). *(B)*
4. Roy calls `use_tenant("<alvi>")`, then `awaken("<alvi's agent>")` → Alvi's fleet, and `caller` names Roy with `is_guest: true`. *(C)*
5. Alvi calls `revoke_member("<roy>")`, then Roy calls any memory tool → refused, naming the tenant; `use_tenant(null)` returns him home and memory works again. *(D)*
6. Alvi calls `create_invite()` again, Roy redeems, and `list_tenants()` shows Alvi once, not twice. *(E)*
7. Re-run steps 4 and 5 against the live box (Postgres) rather than a local SQLite store. *(F)*

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| The schema carries the two tables and the column; both backends; existing rows untouched | `test_sharing_schema.py` (5), `test_the_sharing_migration_upgrades_an_existing_store_without_touching_its_rows` | The live box's `0004_tenant_sharing` migration (F) |
| Selection round trip, idempotent grant, revoke/re-grant as one row, single-use redeem, expired/revoked/unknown refused | `test_sharing_repository.py` (12, both engines) | — |
| An import or backend migration cannot drop access | `test_sharing_survives_data_movement.py` (2) | A real `--all` import against the live store (F) |
| Every rule and every refusal message | `test_sharing_service.py` (16) | — |
| A live selection is used; a revoked or never-granted one refuses; the way home still answers | `test_tenant_resolver.py` (4 new) | A real token from the real issuer (B, D) |
| The seven tools are served, dispatched, and refuse correctly | `test_sharing_tools.py` (4) | Helheim's own forms (A, G) |
| The same seven on HTTP, including 403 and switching back afterwards | `test_sharing_routes.py` (3) | A real client over TLS (B) |
| The profile seed: once, only with a name, never over an authored profile | `test_profile_seed.py` (6) | A real first login (B) |
| Surface size and hints | `test_tool_annotations.py`, `test_twin_parity.py::test_tool_surface_is_the_documented_size`, `test_route_coverage.py` | Client-side confirmation prompts |
| The Postgres engine behaves identically | the `postgres` parameter of `test_sharing_repository.py`, `-m postgres` in CI | — |

## Checks

### A The owner side
- [ ] `create_invite()` returns a code, a `tenant_user_id` equal to the caller's own, and an expiry about seven days out.
- [ ] `list_members()` lists the owner first with `role: "owner"`, then every live guest.
- [ ] `revoke_invite(code)` before use → a later redeem says the invitation was revoked. **Disprove**: a revoked code still admitting somebody.

### B Joining, and what it does not touch
- [ ] Roy's first login creates his own empty tenant (warning in the log: `new tenant created`), and it carries a seeded profile naming him if the provider sent a name.
- [ ] Redeem joins but does **not** switch: `list_tenants()` still shows his own as `active`.
- [ ] His own tenant's records, if he had any, are exactly as they were.
- [ ] A second redeem of the same code is refused with "already been used".
- [ ] Redeeming a code for his own tenant is refused with "you already own".

### C Working inside somebody else's account
- [ ] `awaken` returns the account's fleet and user profile, with `caller.user_id` naming Roy and `is_guest: true`.
- [ ] A write from inside that account lands in **that** account: read it back as Alvi and it is there.
- [ ] Switch back with `use_tenant(null)`: `caller` becomes `is_guest: false`, and Alvi's records are no longer reachable.
- [ ] **Disprove**: any call that returns data from both accounts at once.

### D Revocation, at the point of use
- [ ] Revoke while Roy is sitting in the account: his very next memory call answers 403 / a tool error saying access was revoked, naming the tenant.
- [ ] `list_tenants` and `use_tenant(null)` still work, and after switching home every memory call succeeds.
- [ ] **Disprove**: any fallback that silently serves Roy's own tenant while his selection still names Alvi's.
- [ ] Nothing Alvi wrote is deleted, and nothing Roy wrote is deleted.

### E One row per pair
- [ ] Revoke, then re-invite and redeem: `list_members` shows the pair once, and `granted_date` has moved.

### F On the live box
- [ ] The `0004_tenant_sharing` migration applied to the deployed Postgres schema, and `account.active_user_id` exists there.
- [ ] A real import (`importer --all`) leaves grants and invites intact.
- [ ] `deploy/link-identity.py` with `MUNNIN_DB_BACKEND=postgres` links a machine identity and reads back as intended.
- [ ] A revoked selection on the live box answers 403 through the deployed proxy, not a 500.

### G Helheim, unchanged
- [ ] The server page lists the seven membership tools with their titles.
- [ ] `create_invite` and `list_members` run from the generated forms, and the call history records them.
- [ ] No Helheim code was changed to make this work.

## Result

**Runs**: 2026-10-31 · software-architect. Two, because one could not reach the feature's core.

1. **Local mode** (`MUNNIN_AUTH=off`, scratch SQLite), through the bench's own ACT and OBSERVE scripts. Reaches the owner side only: one tenant means no second person.
2. **Token mode** on a scratch store, port 8201, with two stand-in identities — a static verifier in place of Logto, everything else the shipped app. This is where B, C, D and E were walked: tenant creation on first contact, the profile seed, invitations, switching, a write landing in the other account, and revocation taking effect on the next call.

**Bench defects found by running, and fixed**: `start-server.sh` could not boot the server at all, because auth defaults to `token` and the script set nothing, so it died at `AuthNotConfiguredError`; it never exported `MUNNIN_HOST`/`MUNNIN_PORT`; and it recorded the pid of a `uv` wrapper instead of the server. `stop-server.sh` then handed that POSIX pid to `taskkill`, which reported success while uvicorn kept serving. All three are fixed and re-proven: start → health 200, stop → port closed.

**Finding from run 2, fixed in the same session**: while a person's selection named a tenant they had just lost access to, `list_tenants` returned their own tenant with **nothing active** — the state was unreportable, so a refusal had no visible cause and the caller could not see where they were standing. `TenantRef` gained `revoked`, the dead selection is now listed as `active` and marked, and `use_tenant` refuses to re-enter it. Covered by `test_a_selection_that_lost_access_is_still_shown_and_still_active`.

**Walked: 18 of 24**

| Row | Result |
|---|---|
| A1 invite shape | pass (run 1) |
| A2 members, owner first | pass (run 2, with a guest present) |
| A3 revoke before use | pass (run 1, both calls behave); the **revoked** wording on a third-party code is proven by `test_a_revoked_expired_or_unknown_code_says_which`, not by HTTP |
| B1 first contact creates the tenant | pass, both people, with `new tenant created` in the log |
| B2 the seed names the person | pass: both awaken payloads carry their own profile |
| B3 redeem joins without switching | pass: his own tenant stayed `active` |
| B4 a second redeem is refused | **not walked** |
| B5 own tenant needs no invitation | pass (run 1) |
| C1 caller says Roy, profile says Alvi | pass |
| C2 a write inside lands in that account | pass: Alvi reads it, Roy does not at home |
| C3 switch home puts it out of reach | pass |
| C4 no call returns both accounts | pass, as observed across the run |
| D1 revoke while inside refuses the next call | pass: 403 naming the tenant |
| D2 the membership calls still answer | pass after the fix: the dead selection shows `active: true, revoked: true` |
| D3 switching home restores memory | pass: 200 again |
| D4 nothing is deleted | pass: the row Roy wrote is still Alvi's |
| E one row per pair | pass: revoke, re-invite, redeem → one row for Roy |
| F1 the migration on the deployed Postgres | pass (run 3): `0004_tenant_sharing` applied to a live store at `0003`, both tables and `account.active_user_id` present |
| F3 the operator script against Postgres | pass (run 3): refused an unknown tenant, then linked onto a scratch database and read back |

**Not walked: 6 rows** — B4 (a double redeem, covered by `test_a_code_works_exactly_once`), F2 (a live import would purge a tenant's memory from the production store to prove a path the suite already covers), F4 (needs a token to call the deployed proxy), G1–G3 (Helheim holding a real login).

**Run 3, the deployed box** (`munnin-web-b9f7a0e`, deployed 2026-10-31 16:08Z by the deploy workflow, after a fresh `pg_dump` at 16:07Z): health answered 200 through the proxy; the store is the `munnin` database, **not** `valaskjalf`; the migration applied to an existing store at `0003` with data already in it; `accounts=2 grants=0 invites=0`.

**Operational finding from run 3**: the container came up healthy with the **unmigrated** schema still in place. Migrations run lazily on the first store connection, and `/health` deliberately reads nothing, so a green healthcheck says nothing about the schema. The migration was applied deliberately with an empty-store-connection probe, and a first request from a real client would have done the same at whatever moment that client arrived. `docker ps` showing the new tag is therefore not evidence of a migrated store; reading `migration_history` is.

**Verdict**: the two-person path works end to end over real HTTP with real bearer tokens and per-request tenant resolution, and a revoked person is refused, told why, and shown where they are. What remains unproven is a **real issuer** (Logto and Google) and the **deployed Postgres box**, which are F and G.
