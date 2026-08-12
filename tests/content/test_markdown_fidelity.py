"""Markdown-fidelity gate — the markdown pathway must carry every storage mechanic.

Originally a one-time migration guard that diffed the refactored procedures against
their pre-refactor ``git HEAD`` version. Once the seam refactor was committed, HEAD
*became* the refactored core, so that comparison is moot. This is the durable
forward form: compose ``core + markdown.md §proc + referenced templates`` and assert
every curated mechanic token is present. If a future edit drops a mechanic from the
markdown backend, the fleet's markdown pathway would silently change — this fails loud.

Byte-identity with the old procedures is intentionally NOT required (the seam relocates
text); behavioral preservation via mechanic-token presence is the property that matters.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.content.compose import extract_section, substitute_storage_mechanics

REPO = Path(__file__).resolve().parents[2]
CF = REPO / "control-files"
PROC_DIR = CF / "procedures" / "memory"
BACKEND = PROC_DIR / "storage-backends"

# procedure -> referenced templates + the storage mechanics (commands, paths, index rules,
# thresholds) a markdown-era agent must still be told to do. The markdown composition MUST
# carry all of these.
CASES: dict[str, dict] = {
    "update-episodic": {
        "templates": ["templates/episodic-entry-template.md"],
        "tokens": [
            "date '+%Y-%m-%d %H:%M'",
            "agent-memory-index.md",
            "# Recent Context Episodes",
            "MOVE-TO-TODAY",
            "episodic-memory-template.md",
            "1000",
            "500",
            "lazy",
            "archive/",
            "episodes/",
        ],
    },
    "add-reasoning": {
        "templates": ["templates/reasoning-pattern-template.md"],
        "tokens": ["agent-core-memory.md", "uuidgen", "/proc/sys/kernel/random/uuid", "NewGuid"],
    },
    "update-emotional": {
        "templates": ["templates/emotional-moment-template.md"],
        "tokens": [
            "date '+%Y-%m-%d %H:%M'",
            "agent-core-memory.md",
            "DOMAIN EMOTIONAL MEMORY",
            "NEWEST FIRST",
        ],
    },
    "update-knowledge": {
        "templates": ["templates/knowledge-file-template.md"],
        "tokens": [
            "knowledge-base/research/",
            "agent-memory-index.md",
            "2025-09-11-nestjs-patterns.md",
            "typescript-best-practices.md",
        ],
    },
    "load-episodic": {
        "templates": [],
        "tokens": ["agent-memory-index.md", "# Recent Context Episodes", "episodes/"],
    },
    "load-knowledge": {
        "templates": [],
        "tokens": ["agent-memory-index.md", "# Core Knowledge Base", "knowledge-base/"],
    },
    "archive-old-memories": {
        "templates": [],
        "tokens": [
            "date '+%Y-%m-%d %H:%M'",
            "archive/[YYYY]-archived-context.md",
            "archive/[YYYY]-archived-moments.md",
            "copy-lines.sh",
            "agent-core-memory.md",
            "agent-memory-index.md",
        ],
    },
    "update-memory": {
        "templates": [],
        "tokens": ["agent-memory-index.md", "shared-memory/", "core-reasoning-memory.md",
                   "knowledge-base/"],
    },
}


def _composed_markdown(name: str, case: dict) -> str:
    core = (PROC_DIR / f"{name}.md").read_text(encoding="utf-8")
    backend = extract_section((BACKEND / "markdown.md").read_text(encoding="utf-8"), name)
    composed = substitute_storage_mechanics(core, backend)
    templates = "\n".join((CF / t).read_text(encoding="utf-8") for t in case["templates"])
    return composed + "\n" + templates


@pytest.mark.parametrize("name", list(CASES))
def test_mechanics_present_in_markdown_pathway(name: str) -> None:
    case = CASES[name]
    composed = _composed_markdown(name, case)
    missing = [t for t in case["tokens"] if t not in composed]
    assert not missing, f"{name}: mechanics missing from the markdown pathway: {missing}"


def test_harness_detects_a_dropped_mechanic() -> None:
    """The gate must BITE: if the markdown backend loses its mechanics, tokens go missing."""
    name = "update-episodic"
    case = CASES[name]
    core = (PROC_DIR / f"{name}.md").read_text(encoding="utf-8")
    broken = substitute_storage_mechanics(core, "")  # empty backend = mechanics dropped
    missing = [t for t in case["tokens"] if t not in broken]
    assert missing, "regression check failed: empty backend should drop mechanics"
