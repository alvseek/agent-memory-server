"""Entry point — ``python -m munnin`` / the ``munnin`` console script.

Boots the co-hosted app under uvicorn (single worker; one writer per SQLite file).
"""

from __future__ import annotations

import uvicorn

from munnin.app import build_app
from munnin.config import load_config


def main() -> None:
    config = load_config()
    uvicorn.run(build_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
