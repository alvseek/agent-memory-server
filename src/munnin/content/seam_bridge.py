"""Bridge to the framework's canonical seam-substitution logic.

The substitution logic lives once, beside the seam contract, in the control-files
submodule (``procedures/memory/storage-backends/seam.py``) — Munnin-agnostic, so
the public framework tree can be verified without the server. Munnin keeps **no
copy**: it imports that module from the checked-out submodule at runtime through
this bridge. See ``ContentLoader`` (serving) and the markdown-fidelity gate.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType

_SEAM_REL = "procedures/memory/storage-backends/seam.py"


@lru_cache(maxsize=None)
def seam_compose(content_root: str) -> ModuleType:
    """Load + cache the canonical ``seam`` module from a control-files root.

    ``content_root`` is the submodule path (Munnin's configured content root).
    Raises ``FileNotFoundError`` if the submodule / file is absent.
    """
    path = Path(content_root) / _SEAM_REL
    if not path.exists():
        raise FileNotFoundError(f"canonical seam module not found: {path}")
    spec = importlib.util.spec_from_file_location("cf_seam_compose", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
