"""Serves framework memory procedures/templates as data from the control-files submodule.

Procedures are served as MCP **Prompts** (the "how-to" an agent reads before calling
the data tools); templates as MCP **Resources**. Content is read **live** from the
submodule on each request — single source of truth, no re-import on edit.

Each served procedure is storage-agnostic (a semantic core + a ``## Storage Mechanics``
seam). ``get_prompt`` composes the core with the **db** backend section so a Munnin
client gets DB-tool mechanics; the native markdown mechanics never reach the wire.
``push``/``pull``/``refresh``-memory + ``awaken-agent`` are intentionally NOT served
(the DB write is durable; awaken is a tool).
"""

from __future__ import annotations

from pathlib import Path

from munnin.content.seam_bridge import seam_compose

# Served memory procedures: prompt name -> path under content_root.
_PROMPTS: dict[str, str] = {
    "update-episodic": "procedures/memory/update-episodic.md",
    "add-reasoning": "procedures/memory/add-reasoning.md",
    "update-emotional": "procedures/memory/update-emotional.md",
    "update-knowledge": "procedures/memory/update-knowledge.md",
    "load-episodic": "procedures/memory/load-episodic.md",
    "load-knowledge": "procedures/memory/load-knowledge.md",
    "archive-old-memories": "procedures/memory/archive-old-memories.md",
    "update-memory": "procedures/memory/update-memory.md",
    "wrap-up": "procedures/wrap-up.md",
}
_DB_BACKEND = "procedures/memory/storage-backends/db.md"
_TEMPLATES_DIR = "procedures/memory/resources"
# Markdown-only file/index scaffold — used by the markdown backend's create-episode `cp`,
# NOT a DB-world block template. Not served as a resource (a Munnin client never cp's a file).
_RESOURCE_EXCLUDE = {"episodic-memory-template"}


class ContentLoader:
    """Reads + composes served framework content from the control-files submodule."""

    def __init__(self, content_root: Path) -> None:
        self._root = content_root

    def available(self) -> bool:
        """True when the control-files submodule is present."""
        return self._root.exists()

    def root(self) -> Path:
        return self._root

    # --- prompts (memory procedures, composed with the db backend) ---

    def list_prompts(self) -> list[str]:
        """The served procedure names (only those present on disk)."""
        return sorted(name for name, rel in _PROMPTS.items() if (self._root / rel).exists())

    def get_prompt(self, name: str) -> str:
        """Return the procedure composed with its db storage-backend section.

        Falls back to the core verbatim if the procedure has no ``## Storage
        Mechanics`` marker or no db backend section. Raises ``KeyError`` for an
        unknown prompt name.
        """
        rel = _PROMPTS.get(name)
        if rel is None:
            raise KeyError(f"unknown prompt: {name}")
        core = (self._root / rel).read_text(encoding="utf-8")
        db_path = self._root / _DB_BACKEND
        if not db_path.exists():
            return core
        compose = seam_compose(str(self._root))
        try:
            section = compose.extract_section(db_path.read_text(encoding="utf-8"), name)
            return compose.substitute_storage_mechanics(core, section)
        except KeyError:
            # No db section for this procedure, or no marker to swap — serve the core.
            return core

    # --- resources (templates, verbatim) ---

    def list_resources(self) -> list[str]:
        """The served template names (file stems under ``procedures/memory/resources/``)."""
        d = self._root / _TEMPLATES_DIR
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.md") if p.stem not in _RESOURCE_EXCLUDE)

    def get_resource(self, name: str) -> str:
        """Return a template file verbatim. Raises ``KeyError`` if absent or excluded."""
        if name in _RESOURCE_EXCLUDE:
            raise KeyError(f"unknown resource: {name}")
        path = self._root / _TEMPLATES_DIR / f"{name}.md"
        if not path.exists():
            raise KeyError(f"unknown resource: {name}")
        return path.read_text(encoding="utf-8")
