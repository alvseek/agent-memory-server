# Canonical `/mcp` identifier — QA Checklist

**Source**: Quick Wizard plan *"Canonical `/mcp` — no trailing slash, no redirect"*, 2026-09-01 — `agent-memory-server@e52dd8d` (+ `c360177`, comments and a test docstring only), `munnin-deploy@49c1d10`, `authentra@951b38f`/`cc2f0ad`.
**Purpose**: confirm that a client which strips the trailing slash from the MCP URL reaches the login and mints a token Munnin accepts — and that nothing which previously worked (existing tokens, the HTTP face, the health gate) changed underneath it.
**Apps under test**: the MCP face at `/mcp` and its discovery document; the deploy env on the Munnin box; the API resources on the Authentra tenant. **Not touched**: the data tools, the HTTP `/api` routes, tenancy resolution, the importer, kamal-proxy's own config.

## Terminology & state model (read first)

- **Resource identifier** — the string a client sends as `resource` on the authorization and refresh requests, and the audience stamped into the token. Now `https://munnin.lok.quest/mcp` (no slash). The two earlier spellings, `…/mcp/` and `…/`, are still registered in Logto and still accepted by Munnin (`MUNNIN_LOGTO_AUDIENCE`, canonical first) only so that tokens minted against them keep working until each client has logged in again.
- **Stamped at issuance** — a refresh token carries its resource from the moment it is minted; registering or accepting a new spelling afterwards cannot reach an existing token. Only a fresh login mints one for `/mcp`.
- **Normaliser** — a middleware in front of routing that maps `/mcp` → `/mcp/` (the mount) and `/.well-known/oauth-protected-resource/mcp/` → `…/mcp` (the SDK's route), so both spellings hit one handler and no redirect is ever emitted.
- **Forwarded scheme** — uvicorn now trusts `X-Forwarded-Proto` from any peer (`FORWARDED_ALLOW_IPS=*`), so any redirect the app still emits elsewhere is built as `https://`. Safe only because the container publishes no port; kamal-proxy is its sole peer.

**Key invariants** (each is a thing to *disprove*):
- No request to `/mcp` or `/mcp/`, by any method, answers a 3xx — on the live host, through kamal-proxy, not only in-process.
- The 401 challenge, the metadata route and the metadata document all name the same string, `https://munnin.lok.quest/mcp`.
- Widening the audience list did **not** turn the audience check off: a token minted for an unregistered audience is still refused.
- Tokens minted before this change (audience `…/mcp/` or `…/`) still work; tokens minted after it carry `…/mcp`.
- The normaliser rewrites exactly two paths; every other path behaves as before.

## Happy path — single end-to-end scenario (run this first)

1. Anonymous `POST https://munnin.lok.quest/mcp` and `…/mcp/` → both **401**, identical `WWW-Authenticate`, `resource_metadata` ending in `/mcp` (no slash) → *Checks: Wire*.
2. `GET` the advertised document → `resource` is `https://munnin.lok.quest/mcp`; the slashed spelling of the document URL answers the same body → *Checks: Wire*.
3. In claude.ai, remove the Munnin connector and re-add it with `https://munnin.lok.quest/mcp`; complete the Google login → the connector lists Munnin's tools → *Checks: Clients*.
4. In Claude Code, reconnect Munnin and re-authenticate; call `list_procedures` → 13 procedures → *Checks: Clients*.
5. On the Authentra box, query Logto's `logs` for `resource = https://munnin.lok.quest/mcp` → at least one `Success` row newer than the deploy, and no new `Error` rows for that resource → *Checks: Issuer*.
6. A session that has **not** re-logged in (old token) still gets `pong` → *Checks: Transition*.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Both spellings answer the same 401 naming `…/mcp` | `tests/api_http/test_mcp_path_forms.py::test_both_slash_forms_answer_the_same_challenge` | The same through kamal-proxy on the live host — the in-process client never sees TLS termination or the proxy's forwarded headers |
| No method on `/mcp*` answers 3xx | `test_mcp_path_forms.py::test_nothing_on_the_mcp_path_redirects` (GET/POST/DELETE × both paths) | The `Location` *scheme* on any redirect the app still emits elsewhere (`/api/...` with a stray slash) — only observable behind the proxy |
| Metadata document served under both spellings, `resource` = `…/mcp` | `test_mcp_path_forms.py::test_metadata_document_is_served_under_both_forms` | — |
| The normaliser is what removes the redirect (negative control) | `test_mcp_path_forms.py::test_without_the_normaliser_the_bare_path_redirects` | — |
| Outer `MultiAuth` and inner provider agree on the identifier | `tests/test_auth_provider.py::test_advertised_resource_is_the_mcp_url_whatever_the_mount_reports` | — |
| Verifier audience bound to `…/mcp` | `test_auth_provider.py::test_logto_audience_binds_to_this_server` | Against a **real** Logto token: every test verifies through a debug verifier, so acceptance of a live `/mcp`-stamped token and refusal of a foreign-audience token are unproven by CI |
| Audience list parses canonical-first | `tests/configuration/test_config.py::test_more_than_one_audience_can_be_pinned` | That the deployed container carries the list (env on the box) |
| Every MCP-face test drives the no-slash URL | `tests/conftest.py` client (`http://test/mcp`) — indirectly, the whole `tests/api_mcp/` suite | — |
| Logto holds all three resources with distinct names | none — `deploy/register-resources.py` prints the set when run | Run it, or read `resources` on the box |
| claude.ai / Claude Code login over the new identifier | none | Entirely manual, UI-bound |

## Checks

### Wire (anonymous, from outside the network)
- [ ] `POST /mcp` with `Accept: application/json, text/event-stream` and an empty JSON body → **401**, `WWW-Authenticate: Bearer resource_metadata="https://munnin.lok.quest/.well-known/oauth-protected-resource/mcp"`.
- [ ] `POST /mcp/` → byte-identical status and `WWW-Authenticate` to the line above.
- [ ] `GET /mcp` (SSE accept) and `DELETE /mcp` → **401**, never 3xx; `curl -w '%{redirect_url}'` prints nothing.
- [ ] `GET /.well-known/oauth-protected-resource/mcp` → **200**, `resource` is exactly `https://munnin.lok.quest/mcp`; `GET …/mcp/` → **200**, same body.
- [ ] `GET /.well-known/oauth-protected-resource` (the root document the previous design used) → **404** — the old identifier is no longer advertised anywhere.
- [ ] `GET /health` → **200** (Kamal's health gate; the deploy would not have completed otherwise, so re-confirm after any restart).
- [ ] `GET /api/agents` anonymous → **401**; `POST /mcp` with a garbage bearer → **401** — the guard on the mounted face did not loosen when the path was rewritten.

### Redirect scheme (the proxy half — cannot be tested in-process)
- [ ] Find one path that still legitimately redirects (`GET /api/agents/` with a trailing slash, or any FastAPI slash-redirect) → the `Location` starts with **`https://`**, not `http://`. If none redirects any more, note it and mark passed.
- [ ] On the box, `docker port munnin-web-<sha>` prints nothing and the container sits only on the `kamal` network — the precondition for trusting every forwarded peer.

### Issuer (on the Authentra box)
- [ ] `select name, indicator from resources` lists `https://munnin.lok.quest/mcp` ("Munnin MCP"), `…/mcp/` ("… trailing slash, legacy") and `…/` ("… root, legacy").
- [ ] After step 4 of the happy path, `logs` shows `payload->'params'->>'resource' = 'https://munnin.lok.quest/mcp'` with `result = Success` and `created_at` after the deploy.
- [ ] The count of `Error` rows for `…/mcp` does not grow after the deploy (baseline before: **1**, dated 2026-08-31 05:12).

### Transition (old tokens keep working; audience check still real)
- [ ] A session holding a token minted before the deploy (audience `…/mcp/` or `…/`) still gets `pong` from `ping` without re-authenticating.
- [ ] Present a token minted for a **different** registered resource (`https://default.logto.app/api`, the Management API — obtainable on the Authentra box via `configure-tenant.py`'s `token()`) to `POST /mcp` → **401**. This is the check that the widened list is a list, not a wildcard.
- [ ] After every client has re-logged in: `logs` shows no `Success` for `…/mcp/` or `…/` newer than the last re-login — the signal that the two legacy audiences can be dropped from `MUNNIN_LOGTO_AUDIENCE` and deleted in Logto.

### Clients (UI-bound)
- [ ] claude.ai connector re-added with `https://munnin.lok.quest/mcp` connects and lists tools — no 502 from claude.ai's proxy.
- [ ] Claude Code (`.mcp.json` now `…/mcp`) reconnects; `list_procedures` returns 13; `read_procedure("wrap-up")` returns the procedure body.
- [ ] VS Code: Munnin's prompts appear in the slash-command picker on a fresh window — the failed-refresh round trips that pushed the connect past the picker's snapshot are gone. (Known client-side snapshot behaviour; a miss here is not necessarily this change.)

### Untouched surfaces (regression)
- [ ] `awaken("software-architect")` from an authenticated session returns the full payload — the mounted app's lifespan still starts under the new outermost middleware.
- [ ] `GET /api/prompts` with a valid token → the 13 served procedures; `/api/prompts` anonymous → 401.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
