"""Munnin configuration.

v1 is local-first / single-fleet: there is no auth and no login. ``user_id`` is a
server-side constant (never read from agent/tool input) so the tenancy rule holds
trivially and the schema stays ready for real multi-tenant auth later.
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
    # v1: single constant tenant, stamped server-side — never from agent input.
    user_id: str = "alvi"
    # Valaskjalf/memory — gitignored runtime data (one writer: Munnin).
    db_path: Path = Path("data/valaskjalf-memory.db")
    # Served framework content (the control-files submodule).
    content_root: Path = Path("control-files")


def load_config() -> Config:
    """Build config from defaults + optional env overrides (MUNNIN_*)."""
    return Config(
        host=os.getenv("MUNNIN_HOST", "127.0.0.1"),
        port=int(os.getenv("MUNNIN_PORT", "8200")),
        user_id=os.getenv("MUNNIN_USER_ID", "alvi"),
        db_path=Path(os.getenv("MUNNIN_DB_PATH", "data/valaskjalf-memory.db")),
        content_root=Path(os.getenv("MUNNIN_CONTENT_ROOT", "control-files")),
    )
