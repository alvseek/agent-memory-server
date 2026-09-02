"""The three anonymous HTML pages: ``/``, ``/privacy`` and ``/terms``.

These exist because a Google consent screen published to production must link a
homepage, a privacy policy and terms of service **hosted on the app's own domain** —
so the pages are served by the app itself rather than parked on some other site. They
are deliberately anonymous: a stranger reads them to decide whether to sign in, which
is before any token can exist.

The wording is instance-neutral on purpose. This repo is the product and anyone may
host it, so nothing here names a particular deployment — the pages describe what the
software stores and what a hosted demo of it behaves like, which is true wherever the
image runs. Instance-specific facts arrive as parameters (``public_base_url``), never
as text baked into the module.

The pages fetch nothing: no external CSS, fonts, scripts or images. A page whose only
job is to be linked from a consent screen should not make its readers' browsers call
third parties — that would also make the privacy policy's own "no tracking" claim
harder to keep honest.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from munnin import __version__

REPO_URL = "https://github.com/alvseek/agent-memory-server"
ISSUES_URL = f"{REPO_URL}/issues"
FRAMEWORK_URL = "https://github.com/alvseek/agent-memory-system"

# One small stylesheet, inlined into every page. Kept as a plain constant (not an
# f-string) because CSS is made of braces.
_STYLE = """
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         max-width: 42rem; margin: 0 auto; padding: 2rem 1.25rem 4rem;
         line-height: 1.6; color: #1a1a1a; background: #fdfdfd; }
  h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
  h2 { font-size: 1.15rem; margin-top: 2rem; }
  code, pre { background: #f0f0ee; border-radius: 4px; font-size: 0.9em; }
  code { padding: 0.1em 0.35em; }
  pre { padding: 0.75rem; overflow-x: auto; }
  a { color: #0b57d0; }
  nav { font-size: 0.9rem; margin-bottom: 2rem; }
  nav a { margin-right: 1rem; }
  footer { margin-top: 3rem; font-size: 0.85rem; color: #666;
           border-top: 1px solid #e0e0e0; padding-top: 1rem; }
  .notice { background: #fff8e1; border: 1px solid #e6d9a8; border-radius: 6px;
            padding: 0.75rem 1rem; }
"""


def _page(title: str, body: str) -> str:
    """Wrap ``body`` in the shared layout — nav, style, footer — as one HTML document."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<nav><a href="/">Munnin</a> <a href="/privacy">Privacy</a> <a href="/terms">Terms</a></nav>
{body}
<footer>munnin {__version__} · <a href="{REPO_URL}">source</a> (Apache-2.0)
· <a href="{ISSUES_URL}">contact / issues</a></footer>
</body>
</html>
"""


def _landing(public_base_url: str) -> str:
    base = public_base_url.rstrip("/")
    return _page(
        "Munnin — an agent identity server",
        f"""
<h1>Munnin — an agent identity server</h1>
<p>Munnin gives an AI agent a persistent self — identity, reasoning patterns, emotional
moments, episodic history, knowledge — and serves the <strong>procedures for tending that
memory</strong> beside the data, over MCP. It is the memory server of the
<a href="{FRAMEWORK_URL}">agent-memory framework</a>: an agent awakens from it as
<em>who it is</em>, not from a pile of recalled facts, and writes back through the same
discipline.</p>

<h2>Connect</h2>
<p>Point an MCP client at this instance's MCP endpoint:</p>
<pre>claude mcp add --transport http munnin {base}/mcp</pre>
<p>or paste <code>{base}/mcp</code> into claude.ai's custom connectors. Instances that
require sign-in will walk you through it; once connected, the <code>ping</code> tool
answers <code>pong</code> and <code>list_procedures</code> shows the memory discipline.</p>

<h2>Data &amp; demo notice</h2>
<div class="notice">
<p>Signing in stores only your account identifiers (the sign-in provider's issuer and
subject) and your email address as a label — plus whatever memory you and your agents
choose to write. Munnin instances offered as public demos are
<strong>wiped on a regular schedule</strong>: treat a demo as a playground, not a home,
and don't store anything private or irreplaceable. Details in the
<a href="/privacy">privacy policy</a>.</p>
</div>

<h2>Run your own</h2>
<p>Munnin is open source (Apache-2.0) and runs on a laptop in five minutes with no
identity provider — see the <a href="{REPO_URL}">repository</a> for the five-minute
run and the hosting guide.</p>
""",
    )


_PRIVACY = _page(
    "Privacy policy — Munnin",
    f"""
<h1>Privacy policy</h1>
<p>This policy describes what a hosted Munnin instance stores about you. Munnin is
open-source software; this page ships with it and describes what the software itself
does when operated as a service.</p>

<h2>What is stored</h2>
<ul>
<li><strong>Sign-in identity</strong> — when you sign in through an identity provider
(for example a Google account), this instance stores the provider's issuer and subject
identifiers, which name your account, and your email address, used only as a
human-readable label for your tenant. Munnin never sees your password.</li>
<li><strong>The memory you write</strong> — agent identity, reasoning, episodic and
knowledge records that you or your agents create. This content is yours; it is stored
so your agents can read it back.</li>
</ul>

<h2>What is not done</h2>
<ul>
<li>No analytics, no tracking, no advertising. Munnin itself sets no cookies.</li>
<li>Your data is not sold, shared or used for anything beyond serving it back to
you. Every read and write is scoped to your own tenant.</li>
<li>These pages load no third-party resources.</li>
</ul>

<h2>Retention</h2>
<p>Instances operated as public demos are <strong>wiped on a regular schedule</strong> —
stored memory is deleted, and signing in again simply creates a fresh tenant. Do not
keep anything on a demo you cannot afford to lose.</p>

<h2>Your data</h2>
<p>To ask a question about your data or request its deletion, open an issue at
<a href="{ISSUES_URL}">{ISSUES_URL}</a>.</p>
""",
)


_TERMS = _page(
    "Terms of service — Munnin",
    f"""
<h1>Terms of service</h1>
<p>By using a hosted Munnin instance you agree to the following.</p>

<h2>The service</h2>
<ul>
<li>The service is provided <strong>as is</strong>, with no warranty and no service-level
guarantee.</li>
<li>Instances operated as public demos may be wiped on a regular schedule, changed, or
discontinued at any time without notice.</li>
</ul>

<h2>Acceptable use</h2>
<ul>
<li>Store only content you have the right to store; nothing unlawful.</li>
<li>Do not attempt to access other tenants' data or to disrupt the service.</li>
</ul>

<h2>Your content</h2>
<p>The memory you write remains yours. The operator stores and processes it only to
serve it back to you, as described in the <a href="/privacy">privacy policy</a>.</p>

<h2>Software</h2>
<p>Munnin is open-source software under the
<a href="{REPO_URL}/blob/main/LICENSE">Apache License 2.0</a>; these terms cover the
hosted service, not the software, which you are free to run yourself.</p>

<h2>Contact</h2>
<p>Questions: <a href="{ISSUES_URL}">{ISSUES_URL}</a>.</p>
""",
)


def build_pages_router(public_base_url: str) -> APIRouter:
    """The anonymous pages face.

    ``public_base_url`` is received rather than read from config here, for the same
    reason the other faces take their collaborators as parameters: the composition root
    owns configuration, and a leaf module that reached for it would work in the app and
    lie in a test. It appears only in the landing page's connect snippet, so each
    instance shows its own address.

    The routes stay in the OpenAPI schema deliberately: ``test_route_coverage``
    enumerates the schema to audit the anonymous surface, and a page hidden from the
    schema would be exempt from that audit forever.
    """
    router = APIRouter()
    landing = _landing(public_base_url)

    @router.get("/", response_class=HTMLResponse)
    def landing_page() -> HTMLResponse:
        return HTMLResponse(landing)

    @router.get("/privacy", response_class=HTMLResponse)
    def privacy() -> HTMLResponse:
        return HTMLResponse(_PRIVACY)

    @router.get("/terms", response_class=HTMLResponse)
    def terms() -> HTMLResponse:
        return HTMLResponse(_TERMS)

    return router
