# Quick Wizard Plan: Munnin landing + privacy + terms pages (launch-map step 6)

## Context

`GET /` on Munnin is a 404 today. Google's publish rule (read from Google's own pages, 2026-09-01) requires an external production app to link a **homepage, privacy policy, and terms of service** hosted on the app's own domain — so these three pages are the hard prerequisite of launch-map step 5 (consent screen → *In production*). This plan builds them as one small anonymous module in `agent-memory-server`.

## Inherited Context

**From the parent plan** (the Munnin Launch Map artifact + `shared-memory/agent-memory/context/munnin-launch-plan.md`)
- **Assigned scope**: launch-map step 6 — landing page at `/` plus `/privacy` and `/terms`, nothing else.
- **Inherited decisions** (all Settled):
  - Three routes exactly; privacy URL is `/privacy` with `/terms` beside it, not a root-page anchor → Google requires distinct links.
  - Landing content: what Munnin is, how to connect, the demo-wipe notice.
  - Step order 6 → deploy → 5; step 5 runs only after these pages are live on `munnin.lok.quest`.
  - Logo stays empty on the consent screen (brand-verification trigger) — not this plan's file, but constrains nothing here.
- **Contracts**: step 7's wipe cron must match whatever the pages promise (resolved below by promising no number).

**From pre-planning discussion** (this session, 2026-09-02)
- **Settled decisions**:
  - Wipe cadence → **no number yet**: pages say "wiped on a regular schedule"; N is decided at step 7 → his call, avoids committing the cron now.
  - Contact point → **GitHub issues** (`github.com/alvseek/agent-memory-server/issues`) → free, public, no personal email published.
  - Licence question raised and closed → **stays Apache-2.0** (GPL doesn't close the ASP loophole; AGPL would, but the goal is users + contributors in a permissive-licence lane).
- **Considered and rejected**: env knob for notice text (no second consumer yet — YAGNI); template files in a `pages/` dir (over-built for three static pages); stating a concrete wipe-day count (forces step 7's hand and a second edit of these pages).

## Objective

Serve three anonymous, instance-neutral HTML pages from a new `api_pages` box so Google's three *App domain* links exist, growing the route-coverage guard deliberately (open routes 1 → 4, operations 18 → 21).

## Confirmed Decisions

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | Module shape | New box `src/munnin/api_pages/pages.py`, `build_pages_router()` returning an open `APIRouter` | Matches the A-Boxed prefix convention (`api_http`, `api_mcp`); keeps `api_http`'s "guard declared once on the guarded router" story clean — pages never touch that router |
| 2 | Content mechanism | Inline HTML constants, shared `_page(title, body)` layout helper, version formatted in; zero new dependencies, zero config knobs | Smallest true version; instance-neutral wording means one text serves demo, laptop, and self-hoster alike, so there is no instance-specific case to encode |
| 3 | Wording stance | Instance-neutral ("This Munnin instance…"), never naming `munnin.lok.quest` | The repo is the product; a self-hoster's deployment must not serve claims about our demo |
| 4 | Schema visibility | Pages stay `include_in_schema=True` | The route-coverage guard enumerates `app.openapi()["paths"]` — hiding them would exempt them from the anonymous-surface audit forever |
| 5 | Both modes serve them | Pages served in local mode and token mode alike | Harmless, no branch to maintain; local mode's landing page is genuinely useful orientation |
| 6 | Deploy | Out of scope — commit + pin only, per the standing pin-only decision | The box is already five pins behind by decision; the deploy that carries all six is its own gate, and step 5 waits on it |

## Success Criteria

- [ ] `GET /`, `GET /privacy`, `GET /terms` answer 200 `text/html` with **no token** in token mode, and also in local mode
- [ ] Landing page carries: pitch, how-to-connect (both `claude mcp add` and connector paste), the wipe notice ("regular schedule", nothing private), repo + issues links
- [ ] `/privacy` states truthfully: what is stored (Google account identifiers `iss`/`sub`, email as a label, the memory content you write), no analytics/tracking cookies, wipe schedule, contact via GitHub issues
- [ ] `/terms` states: demo provided as-is, no warranty, may be wiped or discontinued, software under Apache-2.0
- [ ] Route-coverage test updated deliberately: `OPEN_ROUTES` +3, `EXPECTED_OPERATIONS` = 21; every other route still 401s anonymously
- [ ] Full suite green (446 + new), `ruff check` clean
- [ ] Unit tests written for every step with testable logic
- [ ] Static quality review completed (Step 7 — `/analyze-code-quality`)
- [ ] QA Handoff completed (Step 8 — checklist built or skipped with reason)

## Execution Steps

1. **Create `src/munnin/api_pages/`** (`__init__.py` + `pages.py`): `build_pages_router()` with the three GET handlers returning `HTMLResponse`; shared `_page()` layout (one small inline CSS block, no external assets — the pages must not fetch anything); content constants worded instance-neutrally; `__version__` stamped in the footer. → verify by import + ruff. *(crosses: nothing)*
2. **Wire into `build_app`** ([app.py](C:\Work\IM\munnin-deploy\agent-memory-server\src\munnin\app.py)): `app.include_router(build_pages_router())` beside the existing router; update the two comments that claim `/health` is the sole open route ([api.py](C:\Work\IM\munnin-deploy\agent-memory-server\src\munnin\api_http\api.py) docstring + route-coverage docstring) so the guard's story stays truthful. → verify by boot in a test app.
3. **Tests**: new `tests/api_http/test_pages.py` — anonymous 200 + `text/html` on all three in token mode; served in local mode; landing carries the wipe notice + connect line; privacy carries the stored-data claims + issues link; terms carries as-is/Apache lines. Update [test_route_coverage.py](C:\Work\IM\munnin-deploy\agent-memory-server\tests\api_http\test_route_coverage.py): `OPEN_ROUTES` gains the three pages, `EXPECTED_OPERATIONS` 18 → 21. → run the two files.
4. **Docs**: `docs/README.md` — add the three routes to the HTTP surface listing and one sentence in the deployment section (the three links Google's consent screen needs). No `.env.example` change (no new env). → re-read the touched sections.
5. **Full verification**: `uv run pytest` + `uv run ruff check` from the repo root. → all green.
6. **Commit + pin**: commit `agent-memory-server` (docs + code + tests, one commit), push; bump the pin in `munnin-deploy`, push. No deploy. → `git ls-remote` confirms both.

## Quality Review

- **Scope**: `src/munnin/api_pages/{__init__,pages}.py`, `src/munnin/app.py`, `src/munnin/api_http/api.py`, `tests/api_http/{test_pages,test_route_coverage}.py`, `docs/README.md` — reconciled against commit `8952cd8` (exact match, working tree clean)
- **Quality Standard**: not found (`**/quality-standard.md` glob came back empty) — freeform review
- **Findings**: 2 low — (1) `public_base_url` interpolated into HTML unescaped (operator config, cosmetic risk); (2) landing pitch duplicates the root README's pitch paragraph (below the DRY bar, different consumers)
- **Fixed**: finding 1 — `html.escape()` on the interpolated base URL (`c6bd790`); finding 2 skipped by default, accepted

## QA Handoff

- **Scope**: `api_pages` (new box), `app.py` wiring, route-coverage guard
- **QA instrument**: set up (`qa/qa-map.md` + built bench; bench's `start-server.sh` broken since 08-29 — known debt)
- **Integration coverage**: N/A — no step crosses a real boundary (all tests in-process ASGI)
- **Checklist**: `qa/checklists/landing-privacy-terms-pages.md` — 8 checks; automated column cites 9 named tests; 5 manual items of which 2 are UI-bound (browser rendering, network tab); includes the truthfulness gate that the promised wipe (step 7) must exist by the time step 5 publishes
- **Runtime verification**: **NOT DONE.** Next action: deploy ≥ `c6bd790`, then `/run-qa-test --checklist qa/checklists/landing-privacy-terms-pages.md`.
