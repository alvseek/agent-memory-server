# High Wizard Plan

## **PROJECT INFO**
- **Project**: agent-memory-server (Munnin)
- **Date**: 2026-08-28
- **Agent**: software-architect
- **Theme**: Give Munnin a real tenant per request and a login, with the token issuer kept swappable
- **Source Protocol**: `/high-wizard` — /high-wizard

*CRITICAL INSTRUCTION: To continue this plan: load the source protocol above, then inspect which sections below are filled vs unfilled to infer your current step.*

---

## **INHERITED CONTEXT**
*Filled at investigation step 0 with whatever was settled before this plan existed. The two sources are recorded separately and never merged — write "None" under a part that does not apply.*
*These decisions are **not yours to reopen**. If one looks wrong, STOP and surface it to [USER-NAME] — do not silently re-decide it here or in Confirmed Decisions below.*

### From the Parent Plan
- **Parent plan**: None — not a sub-plan.
- **Assigned scope**: N/A
- **Integration contracts**: None
- **Pushed-down open items**: None

### From Pre-Planning Discussion
- **Discussion**: Pre-planning discussion with Alvi, 2026-08-28 (this session), building on the WorkOS decision recorded 2026-08-23.
- **Agreed scope**: Make the tenant a property of the request rather than of the process, add an internal user identity that survives changing issuers, and delegate token verification to a provider that can be swapped.

| # | Settled decision | Chosen | His reason | Status |
|---|------------------|--------|------------|--------|
| 1 | Who issues user tokens | Buy it — WorkOS AuthKit | Nobody buys Munnin because its login is good, and a defect there breaches every user's memory at once. Free to 1M monthly users. | Settled 2026-08-23 |
| 2 | Whether the issuer must be replaceable | Yes — a later move to Supabase must be setup only | *"I want the WorkOS is actually swappable (modular), so if someday I want to change to supabase everything goes easy (only need to setup the supabase)"* | Settled |
| 3 | What identifies a tenant in the store | An internal id we mint, never the issuer's subject | A subject is meaningless outside the issuer that minted it, so storing it would orphan every record on a swap. His response: *"exactly"* | Settled |
| 4 | Where the issuer-to-tenant mapping lives | Two new tables in Munnin's own schema | The mapping exists precisely so the issuer can change; storing it inside an issuer would destroy it on the swap it was built for | Settled |
| 5 | Whether Authentra is involved | No | Authentra is a token issuer for machine-to-machine calls with no human in it; it is neither an authenticator nor an authorizer, and this work needs neither of those from it | Settled |
| 6 | Order of work | Tenancy first, then the issuer wiring | Auth on top of a process-wide tenant is decoration — it would authenticate people into one shared mailbox | Settled |

- **Considered and rejected**:
  - *Store the issuer's `sub` directly as `user_id`* → a later issuer change orphans the entire memory store, and no abstraction layer can prevent it.
  - *Put the identity mapping inside Authentra* → self-defeating: the mapping's whole purpose is surviving an issuer change.
  - *Build our own pluggable-auth-provider abstraction* → FastMCP already ships one; a second abstraction over the first buys nothing.
  - *Build Authentra out into the authorization server* → deferred unless Authentra becomes a product to sell; that condition was set on 2026-08-23 and has not changed.
  - *Use Google directly as the authorization server* → it can never mint a token whose audience is Munnin.

- **Left open at the time, and both closed during this plan's rounds** (kept here as the record of what was still undecided when planning began):
  - What happens when a token arrives whose issuer-and-subject pair is not mapped → **closed by Confirmed Decision 5**: the tenant is created, unconditionally and logged, because WorkOS owns admission through its sign-up toggle. My earlier recommendation of a flat refusal was withdrawn once that became clear.
  - Whether the `user` table lands in this work or only `user_identity` → **closed by Confirmed Decisions 12 and 15**: both tables land, and `agent` joins the same referential chain.

---

## **OBJECTIVES**

Munnin currently decides whose memory it serves once, at process start, and serves it to anyone who can reach the host. This plan makes the tenant a property of each request, puts both served faces behind a verified token, and gives every person an internal identity that survives changing token issuers.

It exists because the deployed server is live and unauthenticated, and the memory import is deliberately blocked until this lands.

### **Related Documents**
- [MCP Remote Server Authorization + the Authentra Build-vs-Buy Decision](../../../../Users/alvia/.claude/@agent-memory/agent-software-architect/knowledge-base/research/2026-08-23-mcp-remote-server-authorization.md) — what the MCP spec demands of a resource server, why claude.ai needs public HTTPS, and the WorkOS decision this builds on.
- [memory-server-containerization-and-delivery.md](../../../../Users/alvia/.claude/@agent-memory/shared-memory/agent-memory/context/memory-server-containerization-and-delivery.md) — the live delivery pipeline this deploys through.
- Episode `2026-08-28 08.10` in [agent-memory-mcp-server-architecture.md](../../../../Users/alvia/.claude/@agent-memory/agent-software-architect/episodes/agent-memory-mcp-server-architecture.md) — the sibling session that put the server live and recorded the unauthenticated surface as a debt.

### **SUCCESS CRITERIA**
- [x] Two identities writing through the same running server cannot read each other's records — proved by a test, not by inspection.
- [x] Every route on both faces rejects an absent, expired, wrong-issuer or wrong-audience token; no endpoint is reachable unauthenticated. *(23 operations measured: 18 API + 4 FastAPI built-ins + the MCP mount. Only `GET /health` answers, by design.)*
- [x] A person who has never signed in before gets a tenant created on first arrival, and that creation is logged.
- [x] The existing suite still passes, with the app-level tests authenticating rather than being exempted. *(324 tests.)*
- [ ] A real token from the live issuer is accepted by the deployed server, and its audience is confirmed by decoding the token — not by observing that login worked.
- [ ] `alvi` remains the internal identifier, and the reimported memory is reachable only by the identity mapped to it.

---

## **SCOPE**

### In Scope
- Two new tables — `user` and `user_identity` — with the mapping keyed on issuer plus subject, and the existing `agent` table brought into the same referential chain.
- The tenant resolved per request from the verified token's subject, replacing the process-wide constant.
- Token verification on **both** faces: the MCP app and every `/api/*` route, including the content endpoints, through one shared provider object.
- A `MultiAuth` composition wired with WorkOS as its only current member, so a second issuer is a list entry rather than a restructure.
- Tenant creation on first arrival for an identity that authenticated but has no mapping, logged when it happens.
- Application-level tests authenticating through a debug verifier, plus an isolation test that writes as one subject and proves another cannot read it.
- Verification against the live issuer on the deployed server, including decoding a real token to confirm its audience.

### Out of Scope
- **Per-user storage quotas, rate limiting, backup handling for other people's data, and account deletion.** Deferred deliberately. **Gate: WorkOS's own sign-up toggle must not be switched to public until these exist** — until then admission is by invitation and volume stays in single digits.
- **A machine-to-machine credential path.** Claude Code performs the interactive flow and caches the token, so nothing needs it yet. It becomes necessary when telegent connects, and lands as one verifier added to the `MultiAuth` list.
- **Seeding the fictional demo fleet.** Deferred until everything is up, by decision.
- **Migrating an existing populated database.** The deployed volume is recreated, so no data migration is written; a live-data path would need a migration framework this repo does not have.
- **Moving to Postgres.** Planned after Hermod, and nothing added here is SQLite-specific beyond the existing foreign-key pragma.
- **The sibling session's served-surface debts** — prompt and resource descriptions, tool parameter descriptions, the `serverInfo` version. Same repo, different lane.
- **Retiring the in-process Authentra seed.** Untouched; it solves machine-to-machine, which is a different problem.

---

## **CONFIRMED DECISIONS**
*Decisions made **by this plan** — both **asked-and-confirmed** by [USER-NAME] AND **written-through** (Zone A and B decisions made by the agent, recorded with their reasoning). The reasons serve as the analysis record.*
*Decisions settled before this plan existed — by a parent, or in a pre-planning discussion — belong in [INHERITED CONTEXT](#inherited-context) above, not here. Keeping them separate is what shows which decisions this plan actually owns.*

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | Which surfaces sit behind the token | Both the MCP app and every `/api/*` route | The live server was measured answering `/api/agents` to an anonymous request; the sibling session's audit counts 17 routes of which 7 write. Binding the HTTP face to loopback would put the protection in deploy config that no test can reach. |
| 2 | Multi-user concerns not in this plan | Quotas, rate limits, backup handling and deletion all deferred, with a written gate | Admission is by invitation while WorkOS's sign-up toggle is off, so volume stays tiny. The gate is recorded because an unrecorded "we'll do it before launch" is how the current exposure happened. |
| 3 | Alvi's internal identifier | `alvi`, permanently | It is already stamped on ~1,289 records. Changing it is a full-store rewrite to make a column prettier, and the column is `TEXT` so no UUID is required. |
| 4 | Whether interviewers reach the instance holding real memory | Yes — one instance, tenancy isolates, demo account created inside it | Alvi's call. A second demo instance would keep his own agents off the deployed server, which was the point of deploying it. Consequence accepted: isolation is load-bearing on day one, so it gets a dedicated test rather than an assumption. |
| 5 | An authenticated identity with no mapping | Create the tenant, unconditionally, and log it loudly | WorkOS owns admission through its sign-up toggle and invitations. A second flag in Munnin would have to be kept in agreement with a third-party dashboard setting forever, with nothing reporting divergence. Logging gives detection without a second source of truth. |
| 6 | How the tenant stops being process-wide | Per-request service, resolved explicitly at each handler | A service object *is* a tenant, so no ambient state is involved and a reviewer sees the tenant at each call site. The repository holds only a path and a tenant and opens connections per call, so per-request construction is free. Rejected a context variable: smaller diff, but an unset value fails by reading someone else's rows. |
| 7 | How `/api/*` is guarded | A FastAPI dependency calling the same provider object | Two independently configured verifiers would have to agree forever with nothing reporting when they stop — the drift `test_twin_parity` exists to prevent. |
| 8 | Whether `MultiAuth` is wired now | Yes, with WorkOS as its only member | `MultiAuth(server=provider)` with an empty verifier list behaves identically to the provider alone, so the skeleton is free, and it has a named future occupant in telegent's machine token. |
| 9 | How an account is admitted before sign-up opens | Nothing built — invitation from the WorkOS dashboard | WorkOS ships a per-environment sign-up toggle and an invitation flow. Building a CLI or an admin endpoint would be a second door beside an existing one. |
| 10 | How Alvi's own agent sessions authenticate | Claude Code's built-in OAuth | It runs the flow once, caches the token in the system keychain and refreshes automatically. No machine credential is needed until an unattended consumer appears. |
| 11 | How application-level tests authenticate | FastMCP's `DebugTokenVerifier`, each test presenting a chosen subject | Lets the isolation test be written at all. Rejected disabling auth under test: the tested path would stop being the shipped path, on the most security-sensitive change in the plan. |
| 12 | Referential integrity for `agent` | Full chain — `agent` references `user` | Alvi's call, taken knowing SQLite cannot add a foreign key to an existing table. Viable only because the deployed volume is deleted and recreated, so the constraint exists from birth rather than being retrofitted. Also inherited cleanly by the later Postgres move. |
| 13 | The content endpoints | Behind the token like everything else | One rule with no exceptions is checkable. An unauthenticated exception is what produced the current hole. |
| 14 | `MUNNIN_USER_ID` in the deploy config | Retargeted, not removed | Still read by the importer to stamp records. It stops configuring the server's tenant and keeps configuring the import target — a comment change in a file the sibling session owns. |
| 15 | The provider class | `AuthKitProvider` | Written through, not asked: it is the only real candidate. It builds a `JWTVerifier` against AuthKit's JWKS so verification is local with no per-request outbound call, and it auto-binds the audience to the server's own URL, which turns a misconfigured resource indicator into a loud 401 rather than a silent hole. |
| 16 | Whether this plan introduces a secret | No | Written through: a resource server verifies against a **public** JWKS and holds no client credential. The sibling session's `docker`-group boundary debt is therefore not triggered by this work. |
| 17 | `/health` | Stays unauthenticated — the single exception to decision 13 | Written through: the Kamal configuration sets `healthcheck.path: /health`, so guarding it fails the deploy's health gate and the cutover never happens. It discloses status, service name and version only. Recorded as an exception with its reason so it does not read as an oversight later. |
| 18 | An unset `MUNNIN_AUTHKIT_DOMAIN` | Refuse to build the app | Asked 2026-08-29, during Phase 3. A config-absent escape hatch is decision 11's refusal to disable auth under test, undone one layer down at deploy level — a missing environment variable would silently produce exactly the world-writable server this plan exists to close. Rejected defaulting to a placeholder domain (safe, since a bogus JWKS rejects every token, but it surfaces as "nobody can log in" rather than "you forgot a variable"). |
| 20 | FastAPI's own `/openapi.json`, `/docs` and `/redoc` | Absent by default, enabled locally with `MUNNIN_DOCS` | Asked 2026-08-29. Measured answering **200 anonymously** after Step 3.3 — they are added to the app rather than to a router, so the guard cannot reach them and they can only be present or absent, never protected (a browser cannot attach a bearer token to its own page load). They disclose the API's shape rather than any memory, but Success Criterion 2 says *no endpoint is reachable unauthenticated*, and reading `/openapi.json` is exactly how the live server's original hole was found. Off by default because forgetting to disable them publishes the schema, whereas forgetting to enable them costs a developer one environment variable. |
| 19 | Where the test-auth harness lands | Folded into Step 3.1, before enforcement is switched on | Asked 2026-08-29. As originally ordered, Steps 3.2 and 3.3 turn on rejection while Step 3.5 teaches the tests to authenticate — leaving three consecutive steps closing red against the plan's own per-step Definition of Done, on its most security-sensitive change. Building the instrument after the thing it measures means the one step that could catch a mistake runs last. Pure reordering: same work, same files, no scope change. |

---

## **SOLUTION**

### Architecture Overview

Three seams, in the order a request meets them.

**Verification.** `build_app` constructs one `MultiAuth(server=AuthKitProvider(...))`. That single object is handed to `FastMCP(auth=...)` and reused by a FastAPI dependency, so both faces verify identically by construction rather than by agreement.

**Identity.** A verified token yields an issuer and a subject. A tenant-free `IdentityRepository` looks that pair up in `user_identity`; on a miss it creates a `user` and a `user_identity` row and logs the creation. It returns the internal `user_id`. This repository deliberately holds no tenant, because it runs *before* a tenant is known — the existing tenant-bound repository cannot serve this lookup.

**Tenancy.** A `ServiceFactory` holds the database path and the content loader. `factory.for_user(user_id)` returns a `MemoryService` bound to that one tenant. Handlers call it; nothing else changes. `MemoryService` and `SqliteMemoryRepository` keep their existing constructors, which is why every service- and repository-level test survives untouched.

The old composition root built one service for the process. The new one builds a factory and lets each request name its own tenant.

### Component 1: Identity tables and resolver
- **Purpose**: Give every person an internal identifier that outlives whichever issuer authenticated them, and resolve a token to it.
- **Key Files**: `src/munnin/data_entities/schema.sql` (two new tables, `agent` gains its foreign key), `src/munnin/data_entities/user.py` (new), `src/munnin/data_repositories/identity_repository.py` (new, tenant-free), `src/munnin/business_services/identity_service.py` (new).

### Component 2: Per-request tenancy
- **Purpose**: Replace the process-wide constant with a tenant resolved per request, without changing the service or repository constructors.
- **Key Files**: `src/munnin/business_services/service_factory.py` (new), `src/munnin/app.py`, `src/munnin/api_http/api.py`, `src/munnin/api_mcp/server.py`.

### Component 3: Token verification on both faces
- **Purpose**: Ensure no route on either face is reachable without a token whose signature, issuer and audience all check out.
- **Key Files**: `src/munnin/configuration/config.py` (issuer domain and public base URL), `src/munnin/app.py` (the shared provider), `src/munnin/api_http/api.py` (the dependency), `src/munnin/api_mcp/server.py` (`auth=` on the server).

### Integration Architecture

| Component | Integrates with | Data flow | Depends on |
|---|---|---|---|
| `MultiAuth` + `AuthKitProvider` | `FastMCP(auth=)`, the FastAPI dependency | bearer token → signature, issuer and audience checked against AuthKit's JWKS → `AccessToken` with claims | AuthKit's public JWKS; **no secret** |
| `IdentityService` | both adapters, `IdentityRepository` | `(iss, sub)` → existing mapping, or a created `user` + `user_identity` pair → internal `user_id` | the two new tables |
| `ServiceFactory` | both adapters | `user_id` → a `MemoryService` bound to that tenant | `MemoryService`, `SqliteMemoryRepository` (constructors unchanged) |
| `api_http` dependency | `MultiAuth`, `IdentityService`, `ServiceFactory` | request → verified token → tenant → service, injected per route | all three above |
| `api_mcp` tools | the same three, via `get_access_token()` | identical chain, resolved inside each tool body | all three above |
| Importer | `IdentityRepository` | ensures the `user` row exists before upserting agents, because `agent` now references it | `MUNNIN_USER_ID`, retargeted to mean the import target |

### System Flow Diagrams

**Current State** — the tenant is decided once, before any request exists:

```mermaid
sequenceDiagram
    participant C as Any caller
    participant A as FastAPI / FastMCP
    participant S as MemoryService (one, built at boot)
    participant R as SqliteMemoryRepository (user_id="alvi")
    Note over S,R: constructed in build_app, captured by both adapters
    C->>A: request (no credential of any kind)
    A->>S: call the captured instance
    S->>R: operation
    R->>R: WHERE user_id = 'alvi'
    R-->>C: Alvi's records
```

**End Result** — every request names its own tenant:

```mermaid
sequenceDiagram
    participant C as Caller
    participant A as FastAPI / FastMCP
    participant V as MultiAuth + AuthKitProvider
    participant I as IdentityService
    participant F as ServiceFactory
    participant R as SqliteMemoryRepository (per request)
    C->>A: request + bearer token
    A->>V: verify signature, iss, aud (JWKS, no network per call)
    alt token invalid or absent
        V-->>C: 401
    else verified
        V-->>A: claims (iss, sub)
        A->>I: resolve(iss, sub)
        alt mapping exists
            I-->>A: user_id
        else first arrival
            I->>I: create user + user_identity, log it
            I-->>A: new user_id
        end
        A->>F: for_user(user_id)
        F-->>A: MemoryService bound to that tenant
        A->>R: operation
        R->>R: WHERE user_id = <this caller>
        R-->>C: only that tenant's records
    end
```

### Technical Considerations

- **SQLite cannot add a foreign key to an existing table.** `ALTER TABLE` does renames, add-column and drop-column only; a table-level constraint needs a full rebuild. Because the schema is applied with `CREATE TABLE IF NOT EXISTS`, writing the constraint into the file would apply it to **fresh databases only**, silently — new ones constrained, existing ones not, with nothing reporting the difference.
  - This is survivable solely because the deployed volume is deleted and recreated. That precondition is part of decision 12, not an implementation detail.
  - The local development store should be rebuilt the same way, or knowingly left without the constraint.
- **Foreign keys are off by default and enabled per connection.** The schema header already notes this and the repository sets the pragma in `_conn()`. The new `IdentityRepository` opens its own connections and must set it too, or its constraint is decorative. A test should prove rejection rather than assume the declaration works.
- **`/health` must stay unauthenticated.** The Kamal configuration sets `healthcheck.path: /health`, so guarding it would fail the deploy's health gate and the cutover would never happen. It exposes only status, service name and version.
- **The audience is bound automatically, which changes the failure mode in our favour.** `AuthKitProvider` creates its verifier with the audience bound to the server's own resource URL. A resource indicator that was never registered at WorkOS therefore produces tokens the server *rejects* — a loud 401 — rather than tokens it accepts unprotected. Verification is still by decoding a real token and reading the audience, never by observing that login worked.
- **Verification is local.** The provider builds a `JWTVerifier` against AuthKit's JWKS, so no outbound request happens per call. The `WorkOSTokenVerifier` class in the same module does call a userinfo endpoint per request — it belongs to a different provider and must not be used here.
- **Postgres is coming after Hermod.** Nothing added here is SQLite-specific: two tables of `TEXT` columns with a primary key and a foreign key port directly. The pragma and the FTS5 tables are pre-existing concerns, not new ones.
- **A temporary component exists between phases and must not survive.** Phase 2 introduces a static resolver so the suite stays green before verification is wired; phase 3 replaces it and deletes it. It is temporary by construction and named so.


---

## **IMPLEMENTATION PHASES**

### Phase 1: Identity tables and the resolver
*No authentication yet. Everything here is provable on its own.*

- [x] **Step 1.1**: The two tables, and `agent` joins the chain
  - **Action**: Add `user` and `user_identity` to the schema; add the foreign key from `agent` to `user`.
  - **Implementation**: `user` holds the internal id, an optional display name and email (a **label and a matching hint, never a key**), and a creation date. `user_identity` is keyed on `(iss, sub)` and references `user`. `agent` gains its reference in the same file. Because SQLite cannot retrofit a constraint, this applies to a database created fresh — the deployed volume is deleted at Phase 4.
  - **Testing**: Extend `tests/data_entities/test_schema.py` for both tables; extend `tests/data_repositories/test_foreign_keys.py` to prove an unknown `user_id` is **rejected**, not silently accepted.
  - **Success Criteria**: A fresh database has both tables, and an orphan insert raises.

- [x] **Step 1.2**: The tenant-free identity repository and service
  - **Action**: Add `IdentityRepository` and `IdentityService.resolve(iss, sub) -> user_id`.
  - **Implementation**: The repository takes only a database path — **no tenant**, because it runs before a tenant is known, which is why it cannot live on `SqliteMemoryRepository`. It must set the foreign-key pragma on its own connections. The service returns an existing mapping, or creates a `user` plus a `user_identity` row and logs the creation through the existing `logger/` box, at a level that survives production settings.
  - **Testing**: New unit tests — known pair resolves; unknown pair creates exactly one user and one identity; the same unknown pair twice is idempotent; two different subjects get two different users; a creation emits a log record.
  - **Success Criteria**: All pass, and the pragma is proved on this repository's own connection rather than inherited by assumption.

- [x] **Step 1.3**: The importer ensures its user exists
  - **Action**: Make the importer create the `user` row before upserting agents.
  - **Implementation**: `importer.py` already reads `config.user_id`; that value now names the import target. Ensure the row, then proceed unchanged.
  - **Testing**: Extend `tests/data_migrations/test_importer.py` — importing into an empty database succeeds and leaves exactly one user; importing twice stays idempotent.
  - **Success Criteria**: A clean import into a fresh database passes with the new constraint in force.

### Phase 2: Per-request tenancy
*Still no authentication. The tenant becomes a parameter before it becomes a claim.*

- [x] **Step 2.1**: The service factory
  - **Action**: Add `ServiceFactory` and stop building a service in `build_app`.
  - **Implementation**: The factory holds the database path and the content loader; `for_user(user_id)` returns a `MemoryService` bound to that tenant. `MemoryService` and `SqliteMemoryRepository` constructors are **unchanged**, which is what keeps the service- and repository-level tests untouched.
  - **Testing**: A factory test proving two calls with different ids yield services that cannot see each other's writes — the first form of the isolation proof.
  - **Success Criteria**: Every existing `business_services` and `data_repositories` test still passes with no edits.

- [x] **Step 2.2**: Both adapters resolve per call
  - **Action**: Replace the captured service with a per-call resolution in all routes and all tools.
  - **Implementation**: `api_http` gains a dependency injecting the service per route; `api_mcp` tools open with one resolution line. Identity comes from a `StaticResolver(config.user_id)` — **temporary, marked temporary, deleted in Step 3.4** — so the suite stays green before verification exists.
  - **Testing**: The whole existing suite, unchanged, still green.
  - **Success Criteria**: No handler references a module-level service; behaviour is identical to before.

### Phase 3: Verification on both faces

- [x] **Step 3.1**: The shared provider, and the harness that will prove it
  - **Action**: Build `MultiAuth(server=AuthKitProvider(...))` once in `build_app`, and give the app-driving tests a way to authenticate *before* anything starts rejecting.
  - **Implementation**: Config gains the AuthKit domain and the public base URL — no secret. Use `AuthKitProvider`, **not** `WorkOSTokenVerifier`, which calls a userinfo endpoint per request. An unset domain raises (decision 18). `build_app` takes an `auth` override that swaps *which issuer is trusted* and never *whether* a token is checked. Per decision 19 the test harness lands here rather than at 3.5, so each later step closes green and a real regression stays visible among the expected 401s.
  - **Testing**: The provider's verifier is JWKS-based; its audience is unbound until the mount path is known and then binds to the configured base URL **through `MultiAuth`**, which is the forwarding decision 8 rests on; an unset issuer refuses to build.
  - **Success Criteria**: One provider object exists, is reachable by both adapters, and every app-driving test already authenticates.

- [x] **Step 3.2**: The MCP face
  - **Action**: Pass the provider as `auth=` to `FastMCP`; resolve identity from the verified token.
  - **Implementation**: Tools take issuer and subject from `get_access_token()` and pass them to `IdentityService`.
  - **Testing**: An unauthenticated tool call is rejected; an authenticated one reaches the right tenant.
  - **Success Criteria**: No tool is reachable without a valid token.

- [x] **Step 3.3**: The HTTP face, with the one exception
  - **Action**: Guard every `/api/*` route, content endpoints included, through the same provider object.
  - **Implementation**: A FastAPI dependency reusing the provider's verifier — not a second verifier. **`/health` stays open** (decision 17): the Kamal health gate depends on it.
  - **Testing**: A test enumerating the app's routes and asserting every one except `/health` rejects an absent token — a route-count guard, so a future route added without a guard fails the suite.
  - **Success Criteria**: The enumeration passes and `/health` still answers unauthenticated.

- [x] **Step 3.4**: Delete the temporary resolver
  - **Action**: Remove `StaticResolver` and every reference to it.
  - **Implementation**: Identity now comes only from a verified token.
  - **Testing**: A grep for the symbol returns nothing; the suite is green.
  - **Success Criteria**: No path exists by which a tenant is chosen without a token.

- [x] **Step 3.5**: Confirm nothing authenticates by accident
  - **Action**: Sweep the suite now that enforcement is real. The migration this step used to carry happened at 3.1 (decision 19); what remains is checking that it actually bites.
  - **Implementation**: Auth is **never** disabled under test — the tested path stays the shipped path — so the thing to verify is that removing a test's token makes it fail. A harness that silently passes unauthenticated would have hidden every guard in this phase.
  - **Testing**: A test presenting no token, and one presenting an unknown token, are both rejected by each face.
  - **Success Criteria**: The full suite is green with verification enforced throughout, and proven capable of going red.

### Phase 4: Prove it, then ship it

- [x] **Step 4.1**: The isolation proof
  - **Action**: Write the test the whole plan exists to make possible.
  - **Implementation**: Through the running app, authenticate as one subject and write a record; authenticate as a second subject and attempt to read, query, search and edit it. Every attempt must fail or return nothing — including full-text search, which reaches the records by a different path than `query` and is the likeliest place for a leak to hide.
  - **Testing**: Is the test.
  - **Success Criteria**: The second subject cannot observe the first's record by any route on either face.

- [ ] **Step 4.2**: Configure the issuer
  - **Action**: WorkOS dashboard — Google as a social connection, CIMD on, **the server URL registered as a resource indicator**, sign-up left invitation-only.
  - **Implementation**: Roughly ten minutes of dashboard entries; note the issuer URL for config.
  - **Testing**: MCP Inspector completes the flow locally against the deployed server.
  - **Success Criteria**: A real token is obtained outside claude.ai.

- [ ] **Step 4.3**: Deploy onto a recreated volume, and decode the token
  - **Action**: Delete the deployed volume so the schema is created with the constraint, deploy, then verify.
  - **Implementation**: Coordinate with the sibling session on `MUNNIN_USER_ID`'s changed meaning (decision 14). Deploy through the existing Kamal path.
  - **Testing**: `/health` answers; every other route rejects an anonymous request — re-run the exact probe that found the hole and confirm it now fails. **Decode a real token and read its audience**; a green login proves nothing.
  - **Success Criteria**: The audience is the server's own URL, and the previously-open probe returns 401.

- [ ] **Step 4.4**: Import the memory
  - **Action**: Run the import that has been deliberately blocked.
  - **Implementation**: Import as `alvi`; seed your `user_identity` row mapping your WorkOS subject to it.
  - **Testing**: Awaken through the deployed server as yourself and get the full payload; attempt the same as a second identity and get an empty store.
  - **Success Criteria**: Your fleet memory is reachable by you and by nobody else.

- [ ] **Step 4.5**: Re-authenticate the local agent sessions
  - **Action**: Reconnect this repository's Claude Code sessions to the now-guarded server.
  - **Implementation**: The sibling session pointed `.mcp.json` at the deployed server, so those sessions break the moment Step 4.3 lands. Claude Code runs the OAuth flow once and caches the token in the system keychain; it refreshes silently afterwards.
  - **Testing**: Start a session and call a Munnin tool; confirm it reaches your tenant.
  - **Success Criteria**: Local sessions work again without a machine credential, confirming decision 10 in practice rather than in principle.

> **Known consequence, not a gap**: a newly created tenant has no agents, so an interviewer's first `awaken` finds an empty store. That is what the deferred demo seed (OQ2) exists to fix, and it is deliberately not fixed here.

---

## **EXECUTION LOG**
**Execution Protocol for AI**:
I have to use this document as my **ONLY** source of truth to execute and track the plan steps iteratively. I should **NOT** use additional tools like ToDos because it lacks the context of what should I do. Everytime I want to implement a step I have to check the reference to the original step plan above. Everytime a step has been finished I need to go back to this document to log what was done.
*In other words*:
- I have to make this document as the source of truth for the implementation phase on what I have worked on and what I will be working
- The original plan must be fully in my context, therefore, I have to make sure I loaded the **Plan File** before executing any task and read carefully the reference to the original step
- I have to do the implementation by doing it in order per step THEN, I ALWAYS have to fill the step log rightly after

**Definition of Done (applies to ALL steps)**:
- ✅ **Code Quality**: Code compiles/runs without errors
- ✅ **Testing**: Tests written and passing
- ✅ **Logged**: Implementation and testing logged below
- 🚫 **Blocked**: Get input from [USER-NAME] before assuming

*Each entry below mirrors a step in Implementation Phases. Fill it immediately after the step, never in a batch at the end.*

### Phase 1: Identity tables and the resolver
- [x] **Step 1.1**: The two tables, and `agent` joins the chain
  - **Implementation Log**: Added `account` and `user_identity` to `schema.sql`, and the foreign key from `agent` to `account`. Rewrote the file header so it describes five tables as one list rather than carrying an appended note. **Two deviations from the plan text, both approved in conversation first**: the table is `account`, not `user` — `USER` is reserved in Postgres, which is the next database, so `CREATE TABLE user` would be a syntax error there and every later query would need quoting; and its primary key column keeps the name `user_id`, because `agent`, `shared_record` and `memory_record` already use it and not rewriting them is the entire point of the design. `email` is on `account` as a label and matching hint, commented as never a key.
  - **Testing Log**: The constraint's blast radius was **7 test files**, matching the estimate given before the decision. `conftest.py` gained `seed_account`, and `AutoAgentRepository` plus `seed_agent` now ensure the tenant — one change covering the ten files that use the double. The six deliberately double-free files got one explicit seeding line each, preserving the stated intent of `test_agents.py` and `test_foreign_keys.py`. **One implementation error, caught by running rather than by reading**: `seed_account` first opened a raw `sqlite3` connection, which failed with `no such table: account` because the schema is applied on the repository's first `_conn()`, not in `__init__`; rewritten to use `repo._conn()`, which is also what enables the foreign keys. Six new tests added — three in `test_schema.py` (one person holding two identities, the same subject string under two issuers being two identities, the same pair rejected twice) and three in `test_foreign_keys.py` (an agent naming an unknown tenant rejected, a known one accepted, and an identity mapping to an unknown tenant rejected). **270 passed**, up from 264; `ruff check` clean.
  - **Success Criteria**: **Pass.** A fresh database has both tables, and an orphan insert raises on both new links.
  - **Tech Debts**: `account` and `user_identity` are asymmetrically named — the first was renamed for Postgres, the second never needed it. Cosmetic, flagged rather than churned.
  - **Result**: Met. The chain is `account ← agent ← memory_record`, with `user_identity → account` alongside, and every link proved by a rejection rather than assumed from the declaration.
- [x] **Step 1.2**: The tenant-free identity repository and service
  - **Implementation Log**: Three new files. `data_entities/identity.py` holds `Account` and `UserIdentity` (named for the concern rather than the plan's `user.py`, which stopped fitting once the table became `account`). `data_repositories/identity_repository.py` takes only a path, opens its own connections and sets `PRAGMA foreign_keys` itself — copied deliberately from `SqliteMemoryRepository._conn` rather than shared, since the two have different lifetimes and the pragma is the thing most dangerous to inherit by assumption. `business_services/identity_service.py` resolves a pair, mints a `uuid4` tenant on a miss, and logs at **WARNING** rather than INFO so the event survives a raised log level — a new tenant should only appear when you invited somebody. Two design details worth naming: `ensure_account` deliberately does **not** refresh `display_name` or `email` on an existing tenant, because an issuer's profile claims are not authoritative over an account that already exists; and `resolve` re-reads after linking rather than returning what it minted, so two simultaneous first logins for one pair settle on whichever row the idempotent insert kept.
  - **Testing Log**: `tests/business_services/test_identity.py`, 11 tests, all green on the first run. Beyond the five the plan named: the same subject string under two issuers resolves to two tenants; two issuers may map to one tenant (the swap path); a known pair logs *nothing*, because a warning on every ordinary request would train the reader to ignore it; email is stored but proved not to be used for resolution; the pragma is proved on this repository's own connection; and a mapping naming an absent tenant is rejected.
  - **Success Criteria**: **Pass**, including the pragma proved rather than inherited.
  - **Tech Debts**: `_now()` is defined locally instead of shared with `sqlite_memory_repository`'s private one — a two-line duplication rather than reaching into another module's privates.
  - **Result**: Met. A verified token can now be turned into a tenant, and nothing else in the system knows how.

- [x] **Step 1.3**: The importer ensures its user exists
  - **Implementation Log**: `main()` now calls `IdentityRepository.ensure_account(Account(user_id=config.user_id))` before constructing the memory repository, with a comment recording that `MUNNIN_USER_ID` has changed meaning — it names which tenant an import lands in, not which tenant the server serves. Placed in `main()` rather than in `import_fleet` so the production entrypoint owns it and no function signature changes; the tests that call `import_fleet` directly go through `AutoAgentRepository`, which seeds the tenant already.
  - **Testing Log**: Two tests appended to `test_importer.py`, both driving the **real** `main()` through patched `argv` against the fake source tree — the honest test, since `main` builds the real repository and without the account row the first agent write would fail on the foreign key. One asserts the tenant exists with a stamped date; the other runs the import twice and asserts exactly one account, because re-importing is how this store is normally refreshed. **283 passed**; `ruff check` clean after fixing one line length and one import order.
  - **Success Criteria**: **Pass.** A clean import into a fresh database works with the constraint in force.
  - **Tech Debts**: None.
  - **Result**: Met.

### Phase 2: Per-request tenancy
- [x] **Step 2.1**: The service factory
  - **Implementation Log**: `business_services/service_factory.py` — `ServiceFactory(db_path).for_user(user_id)` returns a `MemoryService` bound to that tenant, with both existing constructors untouched. **Two deviations from the plan text, both improvements**: the factory does **not** hold the content loader, because framework content is identical for every tenant and putting it in a per-tenant object would imply a variation that does not exist — the adapters take it directly, as before. And services are **cached per tenant** rather than rebuilt per request, for a concrete reason found while writing it: the repository applies `schema.sql` on its first connection and then remembers, so a fresh instance per request would re-run five `CREATE TABLE IF NOT EXISTS` statements plus indexes and triggers on *every call*. The cached objects hold a path and a string.
  - **Testing Log**: `tests/business_services/test_service_factory.py`, 6 tests, green first run. The important three are the first form of the isolation proof: a second tenant cannot reach a record by `get`, by `query`, or by `search` — search tested separately because it reaches records through the full-text index rather than the browse query, which is a different path and the likeliest place for a leak.
  - **Success Criteria**: **Pass.** Every existing `business_services` and `data_repositories` test passed with no edits.
  - **Tech Debts**: The per-tenant cache is unbounded. Bounded in practice by the number of distinct tenants a process sees, and each entry is two fields, so it is a deliberate choice rather than a leak — but it is worth revisiting if signup ever opens to the public.
  - **Result**: Met.

- [x] **Step 2.2**: Both adapters resolve per call
  - **Implementation Log**: Added `business_services/tenant_resolver.py` — a `TenantResolver` protocol with one method, plus `StaticTenantResolver`, marked **TEMPORARY** in its own docstring and at its construction site in `build_app`, to be deleted in Step 3.4. Both adapters gained a nested `_svc()` helper and now take `(factory, resolver, content)`; all **26** call sites (13 per face) were transformed mechanically with `sed`, having first checked that every `service.` occurrence was a real call rather than prose, and that both files were already LF so `-i` would not rewrite their line endings. `build_app` builds the factory and the temporary resolver instead of a single service.
  - **Testing Log**: **289 passed**, `ruff check` clean. 🚨 **The plan's success criterion for this step was wrong and I wrote it**: it said the whole existing suite would stay green *unchanged*, reasoning that the service and repository constructors were untouched. They were — but `build_mcp` and `build_router` are constructors too, and four test files call them directly. Those needed a real change, not none. Added `mcp_for()` to `conftest.py` so face tests build the MCP surface the way `build_app` does, over a factory; `test_write_tools.py` now seeds its agent explicitly, because the face runs the real repository where the auto-creating double used to invent one. `test_smoke.py`'s ping test deliberately does **not** seed, since it runs against the *configured* database path and `ping` touches no store — seeding there would write rows into a real developer store for nothing.
  - **Success Criteria**: **Partial as written, met in substance.** Behaviour is identical and no handler references a module-level service; but four test files changed, where the criterion promised none.
  - **Tech Debts**: `/health` is now the one route that resolves no tenant. Correct and recorded as decision 17, but it is also the only asymmetry between the two faces, so it is the thing to check first if twin parity ever drifts.
  - **Result**: Met, with the success criterion corrected rather than quietly satisfied.

### Phase 3: Verification on both faces
- [x] **Step 3.1**: The shared provider, and the harness that will prove it
  - **Implementation Log**: `config.py` gained `authkit_domain` (no default) and `public_base_url`, and its docstring was rewritten rather than appended to — it still claimed "there is no auth and no login", which stopped being true two phases ago. `app.py` gained `build_auth(config)`, raising `AuthNotConfiguredError` when the domain is unset (decision 18), plus an `auth` override on `build_app` for tests. **Three facts read out of the installed `fastmcp 3.4.6` rather than its docs, each of which would have produced a wrong test if assumed**: `AuthKitProvider` binds the token audience in `set_mcp_path()`, **not** in `__init__`, so a freshly built provider legitimately has `audience is None` and a naive assertion would have tested the wrong moment; `MultiAuth.set_mcp_path` explicitly forwards to `self.server`, which is the mechanical reason decision 8's "free skeleton" claim holds; and `JWTVerifier` puts the whole decoded payload in `AccessToken.claims`, so `iss`/`sub` arrive there. **One deviation from the plan text**: decision 11 named `DebugTokenVerifier`, but it returns `claims={"token": token}` — no subject at all — so it cannot express "each test presenting a chosen subject". Used its sibling `StaticTokenVerifier` from the same package, which maps a token string to a claims dict natively. Same intent, same refusal to disable auth; the class named in the decision simply could not do what the decision asked for.
  - **Testing Log**: New `tests/test_auth_provider.py`, 5 tests: the unset issuer refuses to build; the verifier is a `JWTVerifier` against `{domain}/oauth2/jwks` with `RS256` (the guard against reaching for `WorkOSTokenVerifier`, which sits in the same module under a more obvious name); the audience is unbound before the mount path is known; it binds to `{base_url}/mcp` **asserted through the `MultiAuth` wrapper**, since forwarding is the thing that could silently break; and no attribute holding a secret exists (decision 16). `conftest.py` gained `auth_for()` / `token_for()`, and all **7 `build_app` call sites across 5 files** now authenticate. **294 passed** (up from 289), `ruff check` clean. Two self-caught defects: my first `auth_for` import order failed `ruff check` (fixed), and the secret test contained redundant logic — `"client_secret" in name` can never be true when `"secret" in name` is false.
  - **Success Criteria**: **Pass.** One provider object exists, is held on `app.state.auth`, and every app-driving test already authenticates — so Steps 3.2 and 3.3 are now pure wiring against a green suite.
  - **Tech Debts**: `public_base_url` defaults to the live host, so a developer running locally verifies against a production audience unless they override it — harmless today because no local token is minted, and it will bite the moment one is. `ruff format` disagrees with 33 files repo-wide including 4 I touched; **verified pre-existing** by format-checking the `HEAD` blobs, and CI runs `ruff check` + `pytest` only, so reformatting was left alone rather than churning files this plan never needed.
  - **Result**: Met, with the step widened by decision 19 and the verifier class corrected to one that can carry a subject.
- [x] **Step 3.2**: The MCP face
  - **Implementation Log**: `build_mcp` gained an `auth` parameter passed straight to `FastMCP(auth=...)`, so the guard sits at the transport and no tool body can be reached without a verified token. `tenant_resolver.py` gained `TokenTenantResolver`, which reads `get_access_token()`, takes `iss` and `sub` from its claims and hands them to `IdentityService.resolve`; its module docstring was rewritten as one description of the seam rather than having a second class appended to it. It **refuses** rather than falling back when a token carries no issuer-and-subject pair — a fallback there would pick a tenant for someone whose identity is unknown, which is the precise failure the `(iss, sub)` key exists to prevent. `build_app` now wires `TokenTenantResolver` into the MCP face while the HTTP face stays on `StaticTenantResolver` until Step 3.3, and the TEMPORARY comment moved with it so it still marks the one remaining tokenless path. **A design fact found by reading rather than assuming**: `get_access_token()` resolves through FastMCP's own request context, so it returns `None` inside a plain FastAPI route — which is why decision 7's separate HTTP dependency is a necessity rather than a stylistic choice, and why this step is MCP-only.
  - **Testing Log**: New `tests/api_mcp/test_mcp_auth.py`, 9 tests. These drive the **mounted** app over streamable-HTTP rather than an in-memory `FastMCP`, because auth is enforced at the transport and an in-memory client sails straight past it — a test that cannot observe the guard cannot prove it. Two traps found by running: `ASGITransport` never fires lifespan events, so the MCP session manager stayed uninitialised and failed with a task-group error that looks nothing like an auth problem (fixed by entering `app.router.lifespan_context`); and a stray third-party `tests` package in site-packages shadows the repo's, which only bites standalone scripts since pytest puts the repo root first. 🚨 **A negative control was added and matters more than the rest**: every other assertion here is that something is *refused*, and a malformed request would be refused too — so an unguarded face is built and the identical call made against it, asserting it is **not** 401. Without that, all eight passing tests would have been compatible with a server that rejects everything for unrelated reasons. The tenant assertions read the **store**, not the tool's reply, because the reply would look identical if the resolver had quietly fallen back to the configured tenant. **303 passed** (up from 294), `ruff check` clean.
  - **Success Criteria**: **Pass.** No tool is reachable without a valid token — proven on `ping` too, which touches no store and is the likeliest thing to be waved through — and an authenticated call lands in a tenant that is demonstrably not the configured one.
  - **Tech Debts**: `TokenTenantResolver` resolves identity on **every** tool call, so a session doing twenty calls does twenty `user_identity` lookups. Each is an indexed read on a local SQLite file and the correctness argument is simply that resolution is not cached where a token could change under it — but it is the obvious thing to measure if latency ever matters.
  - **Result**: Met. The MCP face now serves whoever holds the token and nobody else.
- [x] **Step 3.3**: The HTTP face, with the one exception
  - **Implementation Log**: `build_router` now takes `auth` and `identity` as **required** keyword arguments and no resolver — an unauthenticated HTTP face is not a configuration this server has, and an optional `None` would make one reachable by omission. Inside it, `_caller` verifies the bearer through **the same provider object** the MCP face holds and resolves the pair to a tenant; `_tenant_service` turns that into a `MemoryService` bound to the caller. Routes moved onto a second `APIRouter(dependencies=[Depends(_caller)])`, so the guard is declared **once** for all sixteen rather than sixteen times — a per-handler list is a thing you can forget to add to, and forgetting is silent. Paths are unchanged; `/health` stays on the open router. **Decision 6 was nearly violated and the plan caught me**: the small-diff way to keep `_svc()` working was a request-scoped context variable, and I had started designing one before re-reading that decision, which had already rejected exactly that — *"an unset value fails by reading someone else's rows."* It would have been worse than the plan knew, because all 19 handlers are **synchronous**, so FastAPI runs them in a threadpool and a leaked context variable would serve one caller another's rows while raising nothing.
  - **Testing Log**: 🚨 **Two false-green traps found by measuring instead of assuming.** First, the handlers took `svc: Svc` where `Svc` was a local `Annotated[...]` alias — with `from __future__ import annotations` the annotation is the *string* `"Svc"`, which `get_type_hints` cannot resolve to a local, so FastAPI silently treated `svc` as a **query parameter** and every route answered 422. Fixed by the default-value form (`svc: MemoryService = Depends(_tenant_service)`), which is evaluated at definition time and needs no annotation lookup. Second, the route-coverage guard: walking `app.routes` finds **four** built-in routes and no real ones, because FastAPI keeps an included router as one opaque `_IncludedRouter` with neither `path` nor `routes` — the naive guard would have passed while checking nothing. Rewritten to read the **OpenAPI schema**, which is both public API and the authoritative surface: **17 paths / 18 operations**, matching the sibling session's audit exactly. New `tests/api_http/test_route_coverage.py` (5 tests) asserts every operation but `/health` returns 401, that `/health` still answers, a size tripwire, and a negative control on one read and one write so the file cannot pass by everything being broken. **308 passed** (up from 303), `ruff check` clean. Also completed the Step 3.1 harness, which was half-built: it made the app trust a known verifier but never made the clients *present* a token, so this step's first run was 27 red. Added `bearer()` and `seed_login()` and wired six client sites.
  - **Success Criteria**: **Pass.** The enumeration passes and `/health` still answers unauthenticated.
  - **Tech Debts**: 🚨 **`/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` answer 200 to an anonymous request.** They are FastAPI built-ins, so they sit outside the `/api` router the guard is attached to, and outside decision 1's wording — but Success Criterion 2 says *no endpoint is reachable unauthenticated*, so as written this plan does not yet meet it. Not data, but the complete shape of the API, and reading `/openapi.json` is exactly how the sibling session found the original hole. **Raised for decision rather than settled.** Also: `identity.resolve` runs synchronous SQLite inside an async dependency, briefly blocking the event loop — invisible on a local file, worth revisiting under Postgres.
  - **Result**: Met for the surface the plan scoped; the built-in documentation routes are outside it and are now the only open HTTP endpoints besides `/health`.
- [x] **Step 3.4**: Delete the temporary resolver
  - **Implementation Log**: `StaticTenantResolver` deleted from `src/`. Production had already stopped using it at Step 3.3, so the only four references left were tests. Rather than delete those tests' ability to build a face directly, the class moved into `tests/conftest.py` as `FixedTenantResolver`, documented as a test double that is **deliberately not importable from `munnin`** — if it ever appears in the server's own dependency graph again, that is the bug it now exists to make visible. `tenant_resolver.py`'s docstring was rewritten to say there is exactly one implementation and why that is the point, rather than leaving a paragraph describing a class that no longer exists.
  - **Testing Log**: The grep the plan asks for: `grep -rn "StaticTenantResolver" --include=*.py .` returns **nothing anywhere in the repo**, and `src/` alone likewise. **308 passed**, `ruff check` clean.
  - **Success Criteria**: **Pass.** No path exists in the shipped server by which a tenant is chosen without a token — the resolver protocol now has one implementation and it reads a verified token.
  - **Tech Debts**: None.
  - **Result**: Met.
- [x] **Step 3.5**: Confirm nothing authenticates by accident
  - **Implementation Log**: No production code. The migration this step originally carried happened at 3.1 under decision 19, so what was left was checking the guard actually bites rather than assuming it from a green suite.
  - **Testing Log**: Added the two HTTP rejection paths that had only been shown on the MCP face — an **unknown** token (presenting *a* token is not presenting a *valid* one), and the sharper one, a token that **verifies but names no subject**. That second branch is the one it would be tempting to paper over with a default, because the signature checks out and the caller looks legitimate while nothing says who they are; resolving it to any tenant would be guessing at an identity. Both 401. Together with the negative controls already in `test_mcp_auth.py` and `test_route_coverage.py`, every rejection assertion in this phase is now paired with a demonstration that the same call succeeds when the guard is removed or a real token is presented — so none of them can be passing for an unrelated reason. **310 passed**, `ruff check` clean.
  - **Success Criteria**: **Pass.** The suite is green with verification enforced throughout, and proven capable of going red.
  - **Tech Debts**: The subjectless-token test builds its own verifier inline rather than through `auth_for`, since `auth_for` always supplies a subject. Two lines, and making the helper able to omit a subject would give every future test a way to build a caller who is nobody.
  - **Result**: Met. Phase 3 complete.

### Phase 4: Prove it, then ship it
- [x] **Step 4.1**: The isolation proof
  - **Implementation Log**: No production code was planned for this step, and one change was needed anyway — see the finding below. Also lifted `running()` and `mcp_client_for()` out of `test_mcp_auth.py` into `conftest.py`, since a second file now needs them and they are fiddly enough (lifespan plus an injected httpx factory) that two copies would drift.
  - **Testing Log**: New `tests/test_isolation.py`, 10 tests, both faces, everything through routes a real caller has rather than by reaching into the store. Alice creates her own agent and writes a record; Bob is then **handed its uuid** — the strongest form, since it removes discovery from the question and asks only whether the tenant check holds. Bob gets 404 on `get`, `edit`, `append`, `prepend`, `archive` and `soft_delete`, empty on `query`, `search` and `list_agents`, and the same over MCP. `search` is asserted separately from `query` throughout because it reaches records through the FTS5 index rather than the browse query — a different WHERE clause, and the likeliest place for a leak to survive a change that looked safe. The negative control is first in the file: Alice can read her own record, because an absence is also what a completely broken write path produces.
  - 🚨 **The finding**: Bob naming Alice's agent `meta` was **correctly refused by the composite foreign key** — no leak — but it escaped as an unhandled `sqlite3.IntegrityError`, so the caller got a **500 instead of the 400** the API promises. This path is newly reachable *because of this plan*: before per-request tenancy every caller was the same tenant, so naming an existing agent always succeeded. Fixed in `SqliteMemoryRepository.insert` by translating the foreign-key violation into `ValueError`, following the pattern the shared-table insert already established a few lines below — whose own comment says *"an untranslated IntegrityError reaches an agent as an opaque database string and an HTTP caller as a 500."* Four existing tests asserted the raw `IntegrityError` and were updated; two of them now also assert `__cause__` is an `IntegrityError`, so they still prove the **database** refused rather than a Python pre-check — a pre-check would pass those tests with foreign keys switched off.
  - **Success Criteria**: **Pass.** The second subject cannot observe the first's record by any route on either face. **324 passed**, `ruff check` clean.
  - **Tech Debts**: The proof runs against an in-process ASGI app, not a server started by `qa/scripts/start-server.sh`, so it is integration-by-substitution rather than the QA bench's own RESET → INJECT → ACT cycle. Worth re-running there once the stack is up, though the boundary it exercises — two verified identities through the mounted app — is the real one.
  - 🚨 **A second finding, while preparing Step 4.2 — this one would have blocked login entirely.** The 401 challenge answers `WWW-Authenticate: Bearer resource_metadata="https://munnin.lok.quest/.well-known/oauth-protected-resource"`, and **that URL returned 404**. FastMCP builds its app believing it sits at `/`, so it advertises root-level metadata and keeps its own copies of the discovery routes *inside* the sub-app — which FastAPI then mounts under `/mcp`, leaving the advertised URL nowhere. A client following the standard flow (claude.ai, MCP Inspector) would fail discovery and never reach a login screen, while every test in this plan still passed and the server looked healthy. Fixed by serving `auth.get_well_known_routes()` from the FastAPI root; both URLs now agree, asserted **together** because their agreeing is the property rather than either existing. Two consequences recorded rather than left to be rediscovered: OAuth discovery is a **third deliberately open endpoint** beside `/health` (a client reads it to learn how to get a token, so requiring one would be circular — RFC 9728), and `/.well-known/oauth-authorization-server` is a **forwarder** that fetches AuthKit's metadata over the network per request, so discovery stops working if AuthKit is unreachable.
  - 📌 **Measured for Step 4.2**: the audience Munnin binds is **`https://munnin.lok.quest/`** — with a trailing slash, and *not* `/mcp`, because `http_app(path="/")` leaves FastMCP unaware of the FastAPI mount. That exact string is what must be registered as the Resource Indicator, or every token is refused with a loud 401.
  - **Result**: Met, and it earned its place twice over — the isolation proof found a 500-where-400 defect, and preparing the dashboard step found a discovery break that no test in the plan would have caught.
- [ ] **Step 4.2**: Configure the issuer
  - **Implementation Log**: · **Testing Log**: · **Success Criteria**: · **Tech Debts**: · **Result**:
- [ ] **Step 4.3**: Deploy onto a recreated volume, and decode the token
  - **Implementation Log**: · **Testing Log**: · **Success Criteria**: · **Tech Debts**: · **Result**:
- [ ] **Step 4.4**: Import the memory
  - **Implementation Log**: · **Testing Log**: · **Success Criteria**: · **Tech Debts**: · **Result**:
- [ ] **Step 4.5**: Re-authenticate the local agent sessions
  - **Implementation Log**: · **Testing Log**: · **Success Criteria**: · **Tech Debts**: · **Result**:

---

## **QUALITY REVIEW**
*Filled by procedure Step 16 (delegated to `/analyze-code-quality` in embedded mode) after all execution phases are complete. **Static** review — answers "is the code clean?".*

- **Scope**: 19 files — 6 production (`app.py`, `api_http/api.py`, `api_mcp/server.py`, `business_services/tenant_resolver.py`, `configuration/config.py`, `data_repositories/sqlite_memory_repository.py`), 12 test, 1 plan. Reconciled against ground truth: `git diff --name-only` lists 15 and `git ls-files --others` the 4 new test files, which together match the Execution Log exactly — the four missing from the diff are new files, which `git diff` never shows, proven rather than assumed.
- **Quality Standard**: **Not found** — no `quality-standard.md` exists in this repo, so the review is freeform and Dimension 8 (project standard compliance) is skipped. Worth noting the repo has one enforced standard regardless: `ruff check` runs in CI, and it is clean.
- **Findings**: 4 — 0 critical, 2 medium, 2 low.

  | # | Severity | Location | Issue |
  |---|---|---|---|
  | 1 | Medium | `app.py:99` | `app.state.auth = auth` is written and **never read**. It was load-bearing at Step 3.1, when the provider had to be "reachable by both adapters" before either consumed it; both now receive it as an explicit argument. Dead state that advertises a coupling which no longer exists, and would be the wrong place for a future reader to reach for it. |
  | 2 | Medium | `configuration/config.py:50-59` | **No test covers `load_config()` at all** — a pre-existing gap this plan made sharper by adding three env-driven settings, two of them security-relevant: `MUNNIN_AUTHKIT_DOMAIN` decides whether the server boots, and `MUNNIN_DOCS` decides whether the API schema is public. All three fail safe under a typo (no boot, wrong audience → loud 401, docs off), which is why this is Medium rather than Critical, but the truth-table for `MUNNIN_DOCS` (`1`/`true`/`yes`) is asserted nowhere. |
  | 3 | Low | `tenant_resolver.py:33-64` | `MissingTokenError` is raised on two branches and **caught nowhere, tested nowhere**. It exists to fail loudly if a handler is ever added outside the guard — but an unproven guard is a guard nobody knows works, and its first execution would be in production. |
  | 4 | Low | `app.py:88-92` | The comment *"Propagate the MCP app's lifespan to the parent app."* now sits immediately above the block explaining the schema routes, so it reads as describing them. Two edits collided; the sentence lost the statement it belonged to. |

  Deliberately **not** raised: `_UNAUTHENTICATED` being a module-level dict shared across three `HTTPException` raises looked like a shared-mutable risk, but Starlette copies headers into the response rather than retaining the mapping, so it is safe as written and changing it would be motion without a defect.
- **Fixed**: All four, on [USER-NAME]'s *"proceed"* (defaults accepted). **349 passed** (up from 326), `ruff check` clean.
  1. `app.state.auth` deleted.
  2. New `tests/configuration/test_config.py` (16 tests) — the issuer stays empty when unset *and* an unset issuer stops the server, asserted together because an empty string is only dangerous if something downstream shrugs; plus the full `MUNNIN_DOCS` truth-table including the near-misses `off`, `maybe` and `" true"`, that last one being what a typo in a compose file looks like and the one that must not read as enabled.
  3. New `tests/business_services/test_tenant_resolver.py` (7 tests) — both `MissingTokenError` branches, parametrised over five shapes of incomplete token. **Empty strings are included deliberately**: `{"iss": "", "sub": "x"}` is what a claim stripped by a misconfigured issuer looks like — falsy but present, which an `in claims` check would wave straight through, and the current truthiness check correctly refuses. A negative control proves a complete token still resolves, and resolves *stably* on a second call.
  4. The lifespan comment reunited with the line it describes.

---

## **QA HANDOFF**
*Filled by procedure Step 17 after Quality Review is resolved. This plan is **not** runtime-verified — this section records the plan for that verification, which happens in a QA session with the stack up.*

- **Scope**: [Modules touched — mapped from Execution Log scope]
- **QA instrument**: [Set up (map + bench) / NOT SET UP — auto-skipped]
- **Integration coverage**: **In scope** — bench built (all four R/I/A/O phases `documented`) and a server answers on `127.0.0.1:8200` (`/health` → HTTP 200, checked 2026-08-28). **Phase 4 Step 4.1 carries an `/integration-test` run**: the isolation proof authenticates as two subjects against a *started* server, which is integration by the substitution rule — the server is started, not constructed. Phases 1–3 do not: their boundaries are a temp SQLite the test constructs itself and a doubled token verifier, neither of which is a started system. Steps 4.3–4.5 are **live-system verification against the deployed host**, which sits above `/integration-test` and is recorded here so its absence from the integration count is not read as a gap.
  - ⚠️ **Caveat on the probe**: what answered on 8200 is most likely the long-running local instance left up since 2026-08-21, not a server started by `qa/scripts/start-server.sh`. Its database is therefore not the QA seed. Before Step 4.1, run the bench's own RESET → INJECT → ACT cycle so the isolation test starts from a known state rather than from whatever that instance holds.
- **Checklist**: [qa/checklists/munnin-login-tenancy.md](../qa/checklists/munnin-login-tenancy.md) — built 2026-08-29. Instrument gate passed (`qa/qa-map.md` + a built bench both present). 🚨 It carries a regression the change caused rather than found: **`qa/scripts/smoke-check.sh` will now report `SMOKE FAILED`**, because it probes `/api/awaken`, `/api/prompts`, `/api/prompts/update-episodic` and `/api/resources` with no Authorization header and all four now answer 401. Named rather than patched — the scripts belong to `/build-qa-bench`. The sharpest manual item is one no automated test can reach: **`PRAGMA foreign_key_list(agent)` against the deployed database**, because `CREATE TABLE IF NOT EXISTS` leaves a reused volume's `agent` table without the constraint, silently, and every isolation guarantee would then rest on application code alone.
- **Coverage split**: 10 automated rows (each naming its test) / 26 manual checks. **Four of the automated rows carry an explicit gap in the Still-manual column** rather than an em-dash — the audience row is the one to read: our tests prove what Munnin *verifies against*, and nothing offline can prove what AuthKit actually *mints*. That is only knowable by decoding a real token, which is why it is a manual check and not a green tick. None are UI-bound in the usual sense; the login page is the only screen involved.
- **Runtime verification**: **NOT DONE.** Next action: `/run-qa-test --checklist qa/checklists/munnin-login-tenancy.md` once Phase 4 has deployed and the stack is up. Note the ordering: most of this checklist cannot be walked until Steps 4.2–4.4 are complete, because it verifies a live issuer, a recreated volume and an imported store — none of which exist yet.

> Do not read a filled checklist as a passed one. This section says a verification *plan* exists, nothing more.

---

## **POST-COMPLETION**
After all phases are executed, logged, and both **Quality Review** + **QA Handoff** are filled, move this plan to `plans/completed/`:
`mkdir -p ./plans/completed && mv ./plans/[this-file].md ./plans/completed/[this-file].md`
