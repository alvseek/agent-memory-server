# Landing, privacy and terms pages — QA Checklist

**Source**: Quick Wizard plan "Munnin landing + privacy + terms pages" (launch-map step 6), `agent-memory-server@8952cd8` + `@c6bd790`
**Purpose**: confirm the three anonymous HTML pages serve correctly on every shape (local, token, live behind the proxy), that the anonymous surface grew by exactly those three routes and nothing else, and that the pages' claims are true of the instance serving them.
**Apps under test**: `api_pages` (new), `app.py` wiring, route-coverage guard. Deliberately NOT touched: the guarded `/api` surface, the MCP face, auth, tenancy, the wipe itself (launch-map step 7 — see the invariant below).

## Key invariants (each is a thing to *disprove*)

- No route outside `{/health, /, /privacy, /terms, discovery}` answers anonymously — try to find one that does.
- The pages read nothing from the store — no page's content can differ per caller or per tenant.
- No page load makes the browser fetch a third-party resource — the privacy page's "no tracking" claim is structural.
- Nothing on any page names a specific deployment — a self-hoster's instance must serve text that is true for them.

## Happy path — single end-to-end scenario (run this first)

1. On the live box (after a deploy ≥ `c6bd790`): open `https://munnin.lok.quest/` in a browser → landing renders, styled, nav shows Munnin/Privacy/Terms.
2. The connect snippet shows `https://munnin.lok.quest/mcp` — the instance's own URL, not a baked-in one.
3. Click Privacy → policy renders; click Terms → terms render; both carry the GitHub issues contact link.
4. `curl -s -o /dev/null -w "%{http_code} %{content_type}" https://munnin.lok.quest/privacy` → `200 text/html; charset=utf-8`, no redirect hop.
5. `POST https://munnin.lok.quest/mcp` anonymously still answers **401** — the pages did not widen the guarded surface.

## Automated coverage

| Checklist item | Automated test | Still manual |
|---|---|---|
| Three pages answer 200 anonymously in token mode | `test_pages_answer_anonymously_in_token_mode` | live-proxy hop (test is in-process ASGI) |
| Pages serve in local mode | `test_pages_answer_in_local_mode` | — |
| Landing carries wipe notice + connect line + repo link | `test_landing_carries_the_demo_notice_and_connect_line` | visual rendering |
| Connect snippet uses the instance's own `public_base_url`; no `lok.quest` baked in | `test_landing_shows_this_instances_own_mcp_url` | — |
| Privacy states stored data + contact | `test_privacy_states_what_is_stored_and_the_contact` | truthfulness against the live system (below) |
| Terms state as-is + licence | `test_terms_state_as_is_and_the_licence` | — |
| No external fetches (`src=`, `<link`) | `test_pages_load_no_external_resources` | — |
| Every non-open route still 401s; surface is exactly 21 operations | `test_every_route_outside_the_open_set_rejects_an_absent_token`, `test_the_surface_is_the_size_we_think_it_is` | — |
| Open routes answer 200 | `test_the_open_routes_still_answer` | — |

## Checks

- [ ] **Live, post-deploy**: `GET /`, `/privacy`, `/terms` on `https://munnin.lok.quest` each answer `200 text/html` with no redirect (`curl -i`, look for no `Location`) — the in-process tests cannot see kamal-proxy or the `_NormalisePath` middleware interplay.
- [ ] **Live**: landing's connect snippet reads `https://munnin.lok.quest/mcp` (proves the box's `MUNNIN_PUBLIC_BASE_URL` flows through).
- [ ] **Live**: anonymous `GET /api/agents` still **401** and `POST /mcp` still **401** after the deploy that carries the pages.
- [ ] **Browser (UI-bound)**: all three pages legible on a phone-width viewport (the `<meta viewport>` + max-width CSS actually working); nav links navigate between the three.
- [ ] **Browser (UI-bound)**: browser devtools Network tab on each page shows requests to this host only (favicon 404 is acceptable).
- [ ] **Truthfulness gate for step 5 (publish)**: the pages promise "wiped on a regular schedule" — **the wipe (launch-map step 7) does not exist yet**. Before or promptly after the consent screen goes to production, step 7 must land, or the privacy policy overstates. Disprove: is there a cron/timer on the box wiping demo tenants? (Today: no — known, deliberate ordering.)
- [ ] **Google's own reader**: after step 5 pastes the three URLs under *Branding → App domain*, Google accepts them (its validator requires same-domain, reachable URLs).
- [ ] **Edge**: `GET /privacy/` (trailing slash) — Starlette's default redirect is acceptable here (only `/mcp*` must never 3xx); confirm the redirect it issues is not plaintext `http://` when reached via HTTPS through the proxy. If it is, that is the `FORWARDED_ALLOW_IPS` regression resurfacing on a new route — flag, don't ship.

## Result

*Not yet run. `/run-qa-test --checklist` writes this section — see its Run record.*
