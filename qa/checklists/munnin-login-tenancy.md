# Munnin Login & Tenancy — QA Checklist

**Source**: [plans/2026-08-28-munnin-login-tenancy.md](../../plans/2026-08-28-munnin-login-tenancy.md) — Phases 1–4
**Purpose**: Confirm that a person reaches their own memory and nobody else's, that nothing answers without a token, and that the constraint protecting all of it actually exists in the deployed database.
**Apps under test**: `munnin` server — both faces (`api_mcp`, `api_http`), `business_services`, `data_repositories`, `data_entities/schema.sql`, `configuration`. **Not touched**: the memory operations themselves (insert/edit/query/search semantics), the content loader, `control-files`.

## Terminology & state model (read first)

- **Subject** — who the issuer says you are, as `(iss, sub)`. Meaningless outside that issuer.
- **Tenant** (`user_id`) — who *Munnin* says you are. Minted by us, permanent, never an issuer's subject. Alvi's is the literal string `alvi`; everyone else's is a `uuid4` hex.
- **`user_identity`** — the table mapping one to the other. This is the only thing that survives changing issuer, and it is the whole reason the store is portable.
- **Resource Indicator** — the URL a token's `aud` must equal: **`https://munnin.lok.quest/`**, with the trailing slash, *not* `/mcp`.

**Key invariants** (each is a thing to *disprove*):

- No request without a valid token reaches anything except `GET /health` and the two `/.well-known/` discovery documents.
- Two tenants cannot observe each other's records by **any** route on **either** face — including full-text search, which reaches rows by a different index than browsing.
- A returning subject resolves to the tenant it had before. Signing in twice never mints a second one.
- `alvi` still names the tenant holding the imported fleet memory, and only the identity mapped to it can read that memory.
- The `agent → account` foreign key **exists in the deployed database**. It is created by `CREATE TABLE IF NOT EXISTS`, so a database that already had the old `agent` table keeps it *without* the constraint — silently, with nothing reporting the difference.

## Happy path — single end-to-end scenario (run this first)

1. From a machine that has never authenticated, open the MCP endpoint in Inspector → you are challenged, and the login page appears. *(§ Discovery, § Login)*
2. Sign in with Google → land back at the client with a token. Decode it and read `aud`. *(§ Token)*
3. Call `awaken` for one of your agents → the full payload comes back. *(§ Tenancy)*
4. Sign in as the demo account in a second browser profile → `awaken` returns an **empty store**, not yours. *(§ Isolation)*
5. From the demo account, try to read a record uuid taken from step 3 → refused. *(§ Isolation)*

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Every `/api` route refuses an absent token | `test_route_coverage.py::test_every_route_except_health_rejects_an_absent_token` | Runs against an in-process app, so it cannot see a **proxy or CDN** in front of the deployed host serving a cached 200. |
| `/health` stays open | `test_route_coverage.py::test_the_open_route_still_answers` | Whether *Kamal's* health gate passes on the real host — a different caller with its own timeout. |
| No MCP tool is reachable unauthenticated | `test_mcp_auth.py::test_no_tool_is_reachable_unauthenticated` | — |
| Two subjects get two tenants; a returning one keeps its tenant | `test_mcp_auth.py::test_two_subjects_get_two_tenants`, `::test_a_returning_subject_keeps_its_tenant` | — |
| One tenant cannot read/edit/search another's record | `test_isolation.py` (10 tests, both faces) | Only proves it for tenants created **in that test**. It cannot prove the *imported* `alvi` rows are correctly owned, because the import has not run. |
| Audience is bound to the server's resource URL | `test_auth_provider.py::test_audience_binds_to_this_server_through_multiauth` | Asserts what *we* verify against. It cannot prove **AuthKit mints** that `aud` — that depends on the dashboard's Resource Indicator and is only knowable by decoding a real token. |
| Discovery is served where the challenge points | `test_route_coverage.py::test_oauth_discovery_is_served_where_the_challenge_says_it_is` | Behind kamal-proxy on the real host, where a path-rewrite would break it invisibly. |
| Schema routes absent unless `MUNNIN_DOCS` is set | `test_route_coverage.py::test_the_schema_routes_are_absent_by_default`, `test_config.py` | Whether the **deployed** environment actually leaves it unset. |
| The `agent → account` foreign key rejects an orphan | `test_foreign_keys.py` (asserts `__cause__` is an `IntegrityError`, so it proves the *database* refused) | Runs against a **freshly created** temp database, which always has the constraint. It cannot fail on a deployed volume that predates it — the single most important manual item below. |
| An unset issuer stops the server | `test_config.py::test_an_unset_issuer_stops_the_server` | — |

## Checks

### Deployment preconditions

- [ ] **The deployed volume was destroyed and recreated before this release.** Then, against the live database: `PRAGMA foreign_key_list(agent)` returns a row referencing `account`. 🚨 If the volume was reused, the table persists **without** the constraint and every isolation guarantee below rests on application code alone, with nothing reporting it. This is the one item that cannot be inferred from a green deploy.
- [ ] `MUNNIN_AUTHKIT_DOMAIN` is set on the host; the container is running (a missing value makes it refuse to start, so a running container is itself the evidence).
- [ ] `MUNNIN_DOCS` is **not** set: `GET https://munnin.lok.quest/openapi.json` → 404, and so do `/docs` and `/redoc`.
- [ ] `MUNNIN_USER_ID` is still `alvi` — it now names the **import target**, not the served tenant. Confirm nobody changed it expecting it to select whose memory is served.

### Discovery and login

- [ ] `POST /mcp/` with no token → **401**, and its `WWW-Authenticate` header names a `resource_metadata` URL.
- [ ] Fetching that exact URL returns 200 with an `authorization_servers` array. *(This pair broke once already — the header pointed at a 404.)*
- [ ] MCP Inspector completes the OAuth flow against the deployed host and returns a token.
- [ ] The login page offers Google.

### Token

- [ ] **Decode the real token and read `aud`** — it must be exactly `https://munnin.lok.quest/`, trailing slash included. A successful login proves nothing here; a mis-registered Resource Indicator still logs you in and then fails every call.
- [ ] The token's `iss` equals the configured AuthKit domain.
- [ ] A token whose `aud` is something else (or one hand-edited) → 401, not 200.
- [ ] An **expired** token → 401. *(Not covered automatically: the test verifier has no expiry.)*

### Tenancy

- [ ] After the import, `awaken` as Alvi returns the full fleet payload — agent count and record count matching the pre-import store, not merely "non-empty".
- [ ] A **first-ever** sign-in creates exactly one `account` row and one `user_identity` row, and emits the `new tenant created` WARNING in the container logs. Check the log — it is the only signal that admission happened.
- [ ] Signing out and back in does **not** create a second tenant (`SELECT count(*) FROM account` is unchanged).
- [ ] Two concurrent first sign-ins for the same subject settle on one tenant. *(Race; exercise only if you can trigger it.)*

### Isolation

- [ ] As the demo account: `awaken` for an agent name you know exists in Alvi's store → empty or "no such agent", never Alvi's payload.
- [ ] As the demo account: `GET /api/record/{uuid}` with a uuid copied from Alvi's store → **404**.
- [ ] As the demo account: `GET /api/search?text=<a phrase you know is in Alvi's memory>` → **empty array**. Search reaches rows through the FTS index rather than the browse query, so it is the likeliest place for a leak to survive.
- [ ] As the demo account: `GET /api/agents` → empty, not Alvi's roster.
- [ ] Repeat the previous three over the **MCP** face. The two faces resolve their tenant by different mechanisms and could hold the boundary differently.
- [ ] As the demo account, `POST /api/insert` naming one of Alvi's agents → **400** with a "no agent … exists for this account" message, **not 500**. *(This was a real defect: the constraint held but surfaced as an unhandled database error.)*

### Regressions to check deliberately

- [ ] 🚨 **`qa/scripts/smoke-check.sh` is now broken by this change** and will report `SMOKE FAILED`. It probes `/api/awaken`, `/api/prompts`, `/api/prompts/update-episodic` and `/api/resources` with **no Authorization header**; all four now answer 401 and only `/health` still passes. The script belongs to the bench, so it is named here rather than patched — fix via **`/build-qa-bench`**, giving it a token or scoping it to `/health` plus discovery.
- [ ] Local agent sessions in `munnin-deploy/.mcp.json` reconnect after re-authenticating. They break the moment this deploys, by design.
- [ ] Anything that scraped `/openapi.json` for the API shape now gets a 404 — confirm nothing in the deploy tooling did.
- [ ] The served content endpoints (`/api/prompts`, `/api/resources`) still return **byte-identical** markdown when called *with* a token — the guard should have changed who may read them, not what they say.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
