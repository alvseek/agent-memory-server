# Local mode and the Apache-2.0 licence — QA Checklist

**Source**: Quick Wizard plan *Licence + local mode (launch map steps 1–2)*, 2026-09-01 — `agent-memory-server@4e7f8e0` + review fixes `@f4c89d8`; `agent-memory-system@a88ab42`.
**Purpose**: confirm that a stranger can legally clone and run this server on a laptop with no identity provider, that local mode can never answer beyond that laptop, and that the hosted, token-verified deployment did not move by a byte.
**Apps under test**: `agent-memory-server` (configuration, `app.build_auth`/`build_app`, `api_http.build_router`, `tenant_resolver`, `compose.yaml`, `Dockerfile`, licence files) and the `control-files` submodule's licence. **Not touched**: Authentra, `munnin-deploy`'s Kamal config (only its pin moved), the served procedures' content, the store schema.

## Terminology & state model (read first)

Two **modes**, chosen by `MUNNIN_AUTH`:

| Mode | Value | Who is the caller | Requires |
|---|---|---|---|
| **token** | anything except the literal `off` (default; absent = token) | the `(iss, sub)` of a verified token | an issuer (`MUNNIN_LOGTO_ENDPOINT` or `MUNNIN_AUTHKIT_DOMAIN`) or the server refuses to start |
| **local** | `off` | the one constant tenant `MUNNIN_USER_ID` | `MUNNIN_PUBLIC_BASE_URL` on loopback **and** (`MUNNIN_HOST` on loopback **or** `MUNNIN_LOCAL_BIND_ALL=1`) — otherwise `LocalModeNotLoopbackError` |

`MUNNIN_LOCAL_BIND_ALL=1` is an *acknowledgement*, not a detection: it says "something in front of this process publishes the port on the host's loopback". `compose.yaml` sets it because its `ports:` line is `127.0.0.1:${MUNNIN_HOST_PORT}:8200`. The Docker image bakes `MUNNIN_HOST=0.0.0.0`, so a bare `docker run` in local mode without the flag must refuse.

**Key invariants** (each is a thing to *disprove*):
- A server started with no `MUNNIN_AUTH` behaves exactly as before 2026-09-01: no issuer → no boot; issuer → every `/api/*` and `/mcp` call needs a bearer.
- A local-mode server is reachable from `127.0.0.1` and from nowhere else — on any shape: process, compose, bare `docker run`.
- In local mode every write lands under `MUNNIN_USER_ID`, and the importer stamps the same tenant, so import → awaken round-trips.
- Local mode changes nothing about *what* is served: 13 procedures, 4 templates, byte-identical to the compiled commands.
- The default `public_base_url` moving to loopback changed no deployed audience: the hosted container still advertises `https://munnin.lok.quest/mcp`.
- Both repos read as Apache-2.0 to GitHub, to `uv build`, and to the image build.

## Happy path — single end-to-end scenario (run this first)

1. On a machine with Docker and no Munnin running: `git clone --recurse-submodules https://github.com/alvseek/agent-memory-server && cd agent-memory-server` → *Checks: Licence* (the clone's `LICENSE` and `control-files/LICENSE` both open with "Apache License").
2. `docker compose up -d --build` → within 30 s `curl http://127.0.0.1:8200/health` → `{"status":"ok",…}` → *Checks: Local — compose*.
3. `claude mcp add --transport http munnin-local http://127.0.0.1:8200/mcp` → in a Claude Code session `/mcp` shows it **Connected** with no sign-in → *Checks: Local — real client*.
4. In that session: `ping` → `pong`; `list_procedures` → 13; `create_agent("meta", …)` then `list_agents` → `meta` → *Checks: Local — tenant*.
5. `docker compose down` → `docker compose up -d` → `list_agents` still returns `meta` (the named volume survived) → *Checks: Local — compose*.
6. From the same machine: `curl http://<this machine's LAN IP>:8200/health` → **connection refused** → *Checks: Local — reachability*.
7. `docker compose down -v`.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| `MUNNIN_AUTH` parses: `off` → local, absent/anything else → token | `tests/configuration/test_config.py::test_auth_mode_defaults_to_token`, `::test_off_is_read_as_local_mode`, `::test_anything_else_keeps_token_mode` | — |
| `public_base_url` default is loopback | `test_config.py::test_public_base_url_defaults_to_loopback` | That the **deployed** container still carries `https://munnin.lok.quest` — env on the box, after the next deploy |
| local + non-loopback public URL refused | `tests/test_auth_provider.py::test_local_mode_is_refused_off_loopback` | — |
| local + non-loopback bind refused; waived only by the flag; flag never waives the URL check | `test_auth_provider.py::test_local_mode_is_refused_when_bound_beyond_loopback`, `::test_the_bind_guard_is_waived_only_by_the_explicit_flag` | The same refusal **inside the image** (`docker run` with the flag absent) — the tests construct `Config`, they do not run the image |
| token mode with no issuer still refuses to boot | `test_auth_provider.py::test_local_mode_needs_no_issuer_and_token_mode_still_does`, `test_config.py::test_no_issuer_at_all_stops_the_server` | — |
| HTTP router refuses neither/both modes | `tests/api_http/test_local_mode.py::test_router_refuses_neither_mode`, `::test_router_refuses_both_modes` | — |
| local mode: anonymous HTTP 200, anonymous MCP `pong`, writes land in the tenant, no discovery | `test_local_mode.py::test_http_face_answers_without_a_bearer`, `::test_mcp_face_answers_without_a_token`, `::test_writes_land_in_the_configured_tenant`, `::test_local_mode_serves_no_oauth_discovery` | Through a **real** Claude Code client over TCP — the tests drive the mounted app in process, so the transport's own handling of a missing `Authorization` header over the network is unproven by CI |
| token mode unchanged: anonymous call → 401 | `test_local_mode.py::test_token_mode_still_refuses_an_anonymous_call`, `tests/api_http/test_route_coverage.py` (whole surface) | On the **live** host after the next deploy |
| Importer's tenant stamp matches local mode's tenant | none | Entirely manual — import then awaken through local mode |
| Port published on host loopback only | none — a compose property | `curl` against the LAN IP |
| Licence detected / packaged / built | none — `gh api`, `uv build` and the CI *Build image* job are the checks | Read them, do not infer from a green badge |

## Checks

### Licence
- [ ] `gh api repos/alvseek/agent-memory-server --jq .license.spdx_id` → `Apache-2.0`; same for `agent-memory-system`. (Both read `Apache-2.0` on 2026-09-01 within minutes of the push — re-read, do not assume.)
- [ ] `uv build --wheel` → `METADATA` has `License-Expression: Apache-2.0` and **two** `License-File:` lines; the wheel's `dist-info/licenses/` holds `LICENSE` (11,358 B) and `NOTICE`.
- [ ] `sha256sum LICENSE control-files/LICENSE` → both `cfc7749b…` (the canonical Apache-2.0 text, byte-identical).
- [ ] `control-files/CONTRIBUTING.md` no longer names CC BY 4.0; `control-files/README.md` and `README.md` each end with a `## License` section.
- [ ] GitHub Actions on `agent-memory-server` for `f4c89d8`: **CI** and **Build image** both green — the image build is the only thing that exercises the Dockerfile's new `COPY README.md LICENSE NOTICE`.

### Local — compose
- [ ] Fresh clone → `docker compose up -d --build` → `/health` 200 within 30 s; no `LocalModeNotLoopbackError` in `docker compose logs`.
- [ ] `docker compose exec munnin env | grep MUNNIN_` → `MUNNIN_AUTH=off`, `MUNNIN_LOCAL_BIND_ALL=1`, `MUNNIN_PUBLIC_BASE_URL=http://127.0.0.1:8200`, `MUNNIN_HOST=0.0.0.0`.
- [ ] `docker compose port munnin 8200` → `127.0.0.1:8200` — never `0.0.0.0:8200`.
- [ ] `MUNNIN_HOST_PORT=8201 docker compose up -d` → `MUNNIN_PUBLIC_BASE_URL` inside is `http://127.0.0.1:8201` (the two move together).
- [ ] State survives `down` / `up` (step 5 of the happy path).

### Local — reachability (the guard, on every shape)
- [ ] `docker run --rm -e MUNNIN_AUTH=off -e MUNNIN_PUBLIC_BASE_URL=http://127.0.0.1:8200 munnin:0.1.0` (flag absent, port unpublished) → exits **1**, stderr names `LocalModeNotLoopbackError` and `MUNNIN_HOST='0.0.0.0'`.
- [ ] `MUNNIN_AUTH=off MUNNIN_PUBLIC_BASE_URL=https://munnin.lok.quest uv run python -m munnin` → exits 1, `LocalModeNotLoopbackError` naming the URL.
- [ ] `MUNNIN_AUTH=off MUNNIN_HOST=0.0.0.0 uv run python -m munnin` → exits 1; add `MUNNIN_LOCAL_BIND_ALL=1` → boots (and you have just done the thing the flag's comment warns against — stop it).
- [ ] `MUNNIN_AUTH=off uv run python -m munnin` (all defaults) → boots on `127.0.0.1:8200`; `curl http://<LAN IP>:8200/health` → connection refused.
- [ ] `MUNNIN_AUTH=Off`, `MUNNIN_AUTH=false`, `MUNNIN_AUTH=none` → each **boots in token mode** and, with no issuer set, refuses with `AuthNotConfiguredError` — never silently local.

### Local — real client
- [ ] `claude mcp add --transport http munnin-local http://127.0.0.1:8200/mcp` (no `--client-id`) → `/mcp` shows **Connected**; no browser opens, no sign-in prompt.
- [ ] From that session: `ping` → `pong`; `list_procedures` → 13 names; `read_procedure("awaken-agent", argument="meta")` returns the DB-composed text with `$ARGUMENTS` substituted.
- [ ] `POST /mcp` with no `Authorization` header from `curl` → **200/202**, never a `401` with `WWW-Authenticate`.
- [ ] `GET /.well-known/oauth-protected-resource/mcp` → **404**; `GET /.well-known/oauth-authorization-server` → 404.

### Local — tenant
- [ ] `create_agent("meta", …)` → `list_agents` → `[meta]`; `GET /api/agents` (no bearer) → the same list.
- [ ] `MUNNIN_AUTH=off MUNNIN_DB_PATH=<scratch> uv run python -m munnin.data_migrations.importer` (agent-meta) then `awaken("meta")` over local mode → identity + `shared.reasoning` + `shared.knowledge` populated — the importer's `MUNNIN_USER_ID` stamp and local mode's tenant are the same tenant.
- [ ] `insert(scope="shared", record_type="user_profile", …)` in local mode → `awaken` returns it under `shared.user_profile` (the first-run branch works with no login).

### Token mode — the hosted deploy did not move (after the next Kamal deploy of ≥ `f4c89d8`)
- [ ] On the box: `docker exec munnin-web-<sha> env | grep MUNNIN_` → **no** `MUNNIN_AUTH`, **no** `MUNNIN_LOCAL_BIND_ALL`, `MUNNIN_PUBLIC_BASE_URL=https://munnin.lok.quest`, `MUNNIN_LOGTO_ENDPOINT=https://auth.lok.quest`.
- [ ] Anonymous from outside: `GET /api/agents` → **401**; `POST /mcp` → **401** with `resource_metadata="https://munnin.lok.quest/.well-known/oauth-protected-resource/mcp"`; that document's `resource` is `https://munnin.lok.quest/mcp` (the default flip changed nothing advertised).
- [ ] A live authenticated session (Claude Code or claude.ai) still gets `pong` and `list_procedures` = 13.
- [ ] Logto `logs`: no new `Error` rows for `resource = https://munnin.lok.quest/mcp` after the deploy.

### Untouched surfaces (regression)
- [ ] `uv run pytest -q` → 446 passed (or more), `ruff check` clean.
- [ ] `read_procedure("wrap-up")` in **token** mode is byte-identical to before the change (served content is unaffected by the mode).

### Noted, not this checklist's to fix
- `qa/scripts/start-server.sh` boots with no environment and has failed on `AuthNotConfiguredError` since token verification landed on 2026-08-29; `MUNNIN_AUTH=off` is the obvious repair and belongs to `/build-qa-bench`.
- `README.md`, `docs/README.md` and `.env.example` still describe a token-less v1 and name `RackNerd`; launch-map step 3 rewrites them.
- `qa/checklists/qa-checklists-map.md` is a `/map-qa-instrument` scan artifact and does not list this checklist — `--rescan`, not a hand edit.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
