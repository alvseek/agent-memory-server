"""Entry point — ``python -m munnin`` / the ``munnin`` console script.

Boots the co-hosted app under uvicorn (single worker; one writer per SQLite file).
"""

from __future__ import annotations

import uvicorn

from munnin.app import build_app
from munnin.configuration.config import load_config
from munnin.logger.logger import get_logger


def main() -> None:
    config = load_config()
    get_logger("boot").info("munnin starting on %s:%s", config.host, config.port)
    uvicorn.run(build_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
