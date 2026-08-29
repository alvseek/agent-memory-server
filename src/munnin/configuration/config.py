"""Munnin configuration.

The tenant is a property of each request, not of the process: it is resolved from a
verified token's subject, so nothing here names whose memory the server serves.

``user_id`` survives for one narrower job — it names the tenant an **import** lands in.
The importer stamps records with it; the server no longer reads it to decide anything.

``authkit_domain`` and ``public_base_url`` configure token verification. Neither is a
secret: a resource server verifies against a **public** JWKS and holds no client
credential, which is why these sit in plain config rather than behind the deploy's
secret handling.
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
    # AuthKit tenant issuing our tokens, e.g. "https://munnin.authkit.app". No default:
    # an unset issuer must stop the server, never quietly open it.
    authkit_domain: str = ""
    # This server's own public URL. Tokens are bound to it as their audience, so it must
    # match the Resource Indicator registered in the WorkOS dashboard.
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
        authkit_domain=os.getenv("MUNNIN_AUTHKIT_DOMAIN", ""),
        public_base_url=os.getenv("MUNNIN_PUBLIC_BASE_URL", "https://munnin.lok.quest"),
        docs_enabled=os.getenv("MUNNIN_DOCS", "").lower() in {"1", "true", "yes"},
    )
