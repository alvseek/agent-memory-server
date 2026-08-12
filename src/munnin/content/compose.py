"""Compose a memory procedure with a storage backend.

The seam: each memory procedure carries one ``## Storage Mechanics`` section.
Serving swaps that section's body for a backend's ``## [procedure]`` section —
markdown mechanics for the native fleet, DB tools for Munnin. Pure text ops,
reused by the markdown-fidelity test (markdown backend) and ``ContentLoader``
(db backend), so the substitution logic lives exactly once.
"""

from __future__ import annotations

STORAGE_MARKER = "## Storage Mechanics"


def extract_section(doc: str, title: str) -> str:
    """Return the body under ``## {title}`` up to the next ``## `` header or EOF.

    Matches the level-2 header exactly. Raises ``KeyError`` if absent.
    """
    lines = doc.splitlines(keepends=True)
    header = f"## {title}"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
            break
    if start is None:
        raise KeyError(f"section not found: {header}")
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "".join(lines[start:end]).strip("\n")


def substitute_storage_mechanics(core: str, backend_section: str) -> str:
    """Replace the body of the core's ``## Storage Mechanics`` with ``backend_section``.

    Keeps the marker header; replaces everything after it up to the next ``## ``
    header (or EOF). Raises ``KeyError`` if the marker is absent.
    """
    lines = core.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.strip() == STORAGE_MARKER:
            start = i
            break
    if start is None:
        raise KeyError("no '## Storage Mechanics' marker in procedure")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # The mechanics body ends at the next section header or a standalone rule,
        # so trailing content (e.g. a footer note after the section) is preserved.
        if lines[j].startswith("## ") or lines[j].strip() == "---":
            end = j
            break
    head = "".join(lines[: start + 1])
    tail = "".join(lines[end:])
    return f"{head}\n{backend_section.strip(chr(10))}\n\n{tail}"
