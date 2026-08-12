"""Markdown-fidelity gate — the seam refactor must not change fleet behavior.

For each refactored procedure, assert every storage MECHANIC present in the
pre-refactor version (``git HEAD`` of the control-files submodule) still appears
in the composed markdown pathway: refactored core + markdown backend section +
referenced templates. A dropped mechanic fails loud.

This is the SP5-5 guardrail: byte-identity is impossible (the seam relocates
text), so we enforce *behavioral* preservation via strict mechanic-token
accounting derived from the HEAD source.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from munnin.content.compose import extract_section, substitute_storage_mechanics

REPO = Path(__file__).resolve().parents[2]
CF = REPO / "control-files"
PROC_DIR = CF / "procedures" / "memory"
BACKEND = PROC_DIR / "storage-backends"

# procedure -> HEAD path (under control-files), referenced templates, must-survive mechanic tokens.
# Tokens are the concrete storage mechanics (commands, paths, index rules, thresholds) that a
# markdown-era agent must still be told to do. Extended per procedure as the refactor proceeds.
CASES: dict[str, dict] = {
    "update-episodic": {
        "proc": "procedures/memory/update-episodic.md",
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
        "proc": "procedures/memory/add-reasoning.md",
        "templates": ["templates/reasoning-pattern-template.md"],
        "tokens": [
            "agent-core-memory.md",
            "uuidgen",
            "/proc/sys/kernel/random/uuid",
            "NewGuid",
        ],
    },
    "update-emotional": {
        "proc": "procedures/memory/update-emotional.md",
        "templates": ["templates/emotional-moment-template.md"],
        "tokens": [
            "date '+%Y-%m-%d %H:%M'",
            "agent-core-memory.md",
            "DOMAIN EMOTIONAL MEMORY",
            "NEWEST FIRST",
        ],
    },
    "update-knowledge": {
        "proc": "procedures/memory/update-knowledge.md",
        "templates": ["templates/knowledge-file-template.md"],
        "tokens": [
            "knowledge-base/research/",
            "agent-memory-index.md",
            "2025-09-11-nestjs-patterns.md",
            "typescript-best-practices.md",
        ],
    },
    "load-episodic": {
        "proc": "procedures/memory/load-episodic.md",
        "templates": [],
        "tokens": [
            "agent-memory-index.md",
            "# Recent Context Episodes",
            "episodes/",
        ],
    },
    "load-knowledge": {
        "proc": "procedures/memory/load-knowledge.md",
        "templates": [],
        "tokens": [
            "agent-memory-index.md",
            "# Core Knowledge Base",
            "knowledge-base/",
        ],
    },
    "archive-old-memories": {
        "proc": "procedures/memory/archive-old-memories.md",
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
        "proc": "procedures/memory/update-memory.md",
        "templates": [],
        "tokens": [
            "agent-memory-index.md",
            "shared-memory/",
            "core-reasoning-memory.md",
            "knowledge-base/",
        ],
    },
}


def _head(path_in_cf: str) -> str:
    return subprocess.run(
        ["git", "-C", str(CF), "show", f"HEAD:{path_in_cf}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def _composed_markdown(name: str, case: dict) -> str:
    core = (PROC_DIR / f"{name}.md").read_text(encoding="utf-8")
    backend = extract_section((BACKEND / "markdown.md").read_text(encoding="utf-8"), name)
    composed = substitute_storage_mechanics(core, backend)
    templates = "\n".join((CF / t).read_text(encoding="utf-8") for t in case["templates"])
    return composed + "\n" + templates


@pytest.mark.parametrize("name", list(CASES))
def test_mechanics_preserved(name: str) -> None:
    case = CASES[name]
    head = _head(case["proc"])
    composed = _composed_markdown(name, case)
    # Only assert on tokens that were actually mechanics in HEAD (guards against typos in the list).
    expected = [t for t in case["tokens"] if t in head]
    assert expected, f"{name}: no known mechanic tokens found in HEAD — check the token list"
    missing = [t for t in expected if t not in composed]
    assert not missing, f"{name}: mechanics dropped from the markdown pathway: {missing}"


def test_harness_detects_a_dropped_mechanic() -> None:
    """The gate must BITE: if the markdown backend loses a mechanic, the check fails."""
    name = "update-episodic"
    case = CASES[name]
    head = _head(case["proc"])
    core = (PROC_DIR / f"{name}.md").read_text(encoding="utf-8")
    # Compose with an EMPTY backend — simulates a refactor that dropped all mechanics.
    broken = substitute_storage_mechanics(core, "")
    expected = [t for t in case["tokens"] if t in head]
    missing = [t for t in expected if t not in broken]
    assert missing, "regression check failed: empty backend should drop mechanics"
