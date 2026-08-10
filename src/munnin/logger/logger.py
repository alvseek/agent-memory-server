"""Structured logging for Munnin (the L1 observability box).

A thin factory over stdlib ``logging`` with one consistent format. P5 wires it
into the service + adapters, and performance metrics land here when there is
something to measure. Kept minimal on purpose — observability from day 1 without
pulling a dependency.
"""

from __future__ import annotations

import logging
import sys

_ROOT_NAME = "munnin"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger(_ROOT_NAME)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the ``munnin`` root."""
    _configure()
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
