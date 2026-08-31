"""Bridge to the framework's canonical delivery logic.

Turning a procedure source into a self-contained Prompt takes two substitutions, and
knowing which files are procedures at all is a third definition. All three live once in
the control-files submodule, each beside its own contract — Munnin-agnostic, so the
public framework tree can be verified without the server:

- **seam substitution** — ``procedures/memory/storage-backends/seam.py``
- **component inlining** — ``procedures/components/inline.py``
- **the command set** — ``procedures/command_set.py``, which ``*.md`` files are commands

Munnin keeps **no copy** of any: it imports them from the checked-out submodule at
runtime through this bridge, exactly as the framework's own
``compile-procedures.py`` does. That is what makes an installed slash command and a
served Prompt compose identically. See ``ContentLoader`` (serving) and the
markdown-fidelity gate.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType

_SEAM_REL = "procedures/memory/storage-backends/seam.py"
_INLINE_REL = "procedures/components/inline.py"
_COMMAND_SET_REL = "procedures/command_set.py"


@lru_cache(maxsize=None)
def _load(module_name: str, rel: str, content_root: str) -> ModuleType:
    """Load + cache one framework module from a control-files root by file path.

    ``content_root`` is the submodule path (Munnin's configured content root).
    Raises ``FileNotFoundError`` if the submodule / file is absent — a stale or
    missing checkout must fail loud rather than serve a half-composed procedure.
    """
    path = Path(content_root) / rel
    if not path.exists():
        raise FileNotFoundError(f"canonical framework module not found: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seam_compose(content_root: str) -> ModuleType:
    """The canonical ``seam`` module — backend-section extraction + substitution."""
    return _load("cf_seam_compose", _SEAM_REL, content_root)


def component_inline(content_root: str) -> ModuleType:
    """The canonical ``inline`` module — component reference inlining."""
    return _load("cf_component_inline", _INLINE_REL, content_root)


def command_set(content_root: str) -> ModuleType:
    """The canonical ``command_set`` module — which ``*.md`` files are commands."""
    return _load("cf_command_set", _COMMAND_SET_REL, content_root)
