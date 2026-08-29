"""Munnin configuration.

The tenant is a property of each request, not of the process: it is resolved from a
verified token's subject, so nothing here names whose memory the server serves.

``user_id`` survives for one narrower job — it names the tenant an **import** lands in.
The importer stamps records with it; the server no longer reads it to decide anything.

``logto_endpoint``, ``authkit_domain`` and ``public_base_url`` configure token
verification. None of them is a secret: a resource server verifies against a **public**
JWKS and holds no client credential, which is why these sit in plain config rather than
behind the deploy's secret handling.

Two issuers may be set at once, and that is not indecision — it is how one gets replaced
without locking anybody out. The newer issuer owns discovery, so fresh logins go to it,
while tokens the older one already minted keep verifying until they expire. With neither
set the server refuses to start, because a server that cannot check a token is a server
that serves everyone's memory to anyone.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Runtime settings. Env vars override defaults where present."""

    host: str = "127.0.0.1"
    port: int = 8200
    # The tenant an import lands in — stamped on records by the importer. NOT the
    # server's tenant, which comes from the caller's token.
    user_id: str = "alvi"
    # Valaskjalf/memory — gitignored runtime data (one writer: Munnin).
    db_path: Path = Path("data/valaskjalf-memory.db")
    # Served framework content (the control-files submodule).
    content_root: Path = Path("control-files")
    # Logto tenant endpoint, e.g. "https://xxxxxx.logto.app" (Console -> Settings ->
    # Domains). When set, Logto is the issuer clients are sent to; the OIDC paths beneath
    # it are fixed by Logto, so they are derived rather than configured.
    logto_endpoint: str = ""
    # AuthKit tenant, e.g. "https://munnin.authkit.app". The issuer when it is the only
    # one set, and a verify-only fallback once Logto is configured beside it.
    authkit_domain: str = ""
    # Overrides the audience Logto tokens are checked against. Normally left empty, since
    # the audience binds itself to the resource URL this server advertises. Set it only if
    # Logto stores the API Identifier in a different form than that URL — a token request's
    # `resource` parameter has to match the registered identifier character for character.
    logto_audience: str = ""
    # This server's own public URL. Tokens are bound to it as their audience, so it must
    # match the Resource Indicator registered with whichever issuer is in use.
    public_base_url: str = "https://munnin.lok.quest"
    # FastAPI's own /openapi.json, /docs and /redoc. They sit outside the router the auth
    # guard is attached to, so they cannot be protected — only present or absent. Off by
    # default: forgetting to disable them publishes the API's shape, whereas forgetting to
    # enable them costs a developer one environment variable.
    docs_enabled: bool = False


def load_config() -> Config:
    """Build config from defaults + optional env overrides (MUNNIN_*)."""
    return Config(
        host=os.getenv("MUNNIN_HOST", "127.0.0.1"),
        port=int(os.getenv("MUNNIN_PORT", "8200")),
        user_id=os.getenv("MUNNIN_USER_ID", "alvi"),
        db_path=Path(os.getenv("MUNNIN_DB_PATH", "data/valaskjalf-memory.db")),
        content_root=Path(os.getenv("MUNNIN_CONTENT_ROOT", "control-files")),
        logto_endpoint=os.getenv("MUNNIN_LOGTO_ENDPOINT", ""),
        authkit_domain=os.getenv("MUNNIN_AUTHKIT_DOMAIN", ""),
        logto_audience=os.getenv("MUNNIN_LOGTO_AUDIENCE", ""),
        public_base_url=os.getenv("MUNNIN_PUBLIC_BASE_URL", "https://munnin.lok.quest"),
        docs_enabled=os.getenv("MUNNIN_DOCS", "").lower() in {"1", "true", "yes"},
    )
