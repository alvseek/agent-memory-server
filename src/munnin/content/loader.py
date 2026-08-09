"""Serves framework procedures/templates as data from the control-files submodule.

STUB (Phase 4). The real content-serving (resolving/returning specific procedures
+ templates for MCP prompts/resources) lands in Phase 5. This establishes the
path seam so the content root is configurable, not hardcoded.
"""

from __future__ import annotations

from pathlib import Path


class ContentLoader:
    """Reads served framework content from the control-files submodule."""

    def __init__(self, content_root: Path) -> None:
        self._root = content_root

    def available(self) -> bool:
        """True when the control-files submodule is present."""
        return self._root.exists()

    def root(self) -> Path:
        return self._root
