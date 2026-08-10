"""Markdown parser tests (SP-1 Step 2.1) — inline fixtures for determinism
plus a lenient smoke against the real agent-meta source if present."""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.data_migrations import markdown_parser as P

_AGENT_CORE = """\
# DOMAIN AGENT IDENTITY
I am meta.

# DOMAIN CORE KNOWLEDGE
## Some area
core stuff

# DOMAIN RAS
## Trigger
do the thing

# DOMAIN REASONING MEMORY
<!-- content here -->

# DOMAIN EMOTIONAL MEMORY
## Happy Moments
### 2026-08-09 - FIRST BREATH
it was real
### 2026-08-07 - CLEAN FINISH
felt good
"""

_SHARED_REASONING = """\
# REASONING MEMORY
## CORE
### **BE THOROUGH** 🎯
**UUID**: fc94d140-905e-4f3d-8175-fafd8b84a109
work carefully
### **THINK FIRST** 🧠
**UUID**: c5d8f2a9-4e7b-4a1c-9d6f-3b8e5a2c7f9e
pause then act
"""

_INDEX = """\
# Recent Context Episodes
📂 2026-08-09:
- [build.md](episodes/build.md) - summary of build
📂 2026-08-08:
- [boundary.md](episodes/boundary.md) - summary of boundary
- [build.md](episodes/build.md) - dup, older ref, should be ignored

# Core Knowledge Base
- **[Pain = Memory](memory-architecture/pain.md)** ⭐ - pain anchoring
- **[4-Layer](memory-architecture/four.md)** - the layers
"""


def test_split_sections_levels() -> None:
    secs = P.split_sections(_AGENT_CORE, 1)
    titles = [t for t, _ in secs]
    assert titles == [
        "DOMAIN AGENT IDENTITY",
        "DOMAIN CORE KNOWLEDGE",
        "DOMAIN RAS",
        "DOMAIN REASONING MEMORY",
        "DOMAIN EMOTIONAL MEMORY",
    ]


def test_parse_agent_core() -> None:
    ac = P.parse_agent_core(_AGENT_CORE)
    assert [i.key for i in ac["identity"]] == ["identity", "core-knowledge", "ras"]
    assert ac["reasoning"] == []  # empty domain reasoning
    assert len(ac["emotional"]) == 2
    assert ac["emotional"][0].date == "2026-08-09"
    assert "FIRST BREATH" in ac["emotional"][0].title


def test_parse_shared_reasoning_reuses_embedded_uuid() -> None:
    items = P.parse_shared_reasoning(_SHARED_REASONING)
    assert len(items) == 2
    assert items[0].uuid == "fc94d140-905e-4f3d-8175-fafd8b84a109"
    assert items[0].key == items[0].uuid  # key = existing uuid


def test_parse_active_episodes_dedup_and_date() -> None:
    eps = P.parse_active_episodes(_INDEX)
    files = [e["file"] for e in eps]
    assert files == ["episodes/build.md", "episodes/boundary.md"]  # dup dropped, newest-first
    assert eps[0]["date"] == "2026-08-09"


def test_parse_knowledge_index() -> None:
    items = P.parse_knowledge_index(_INDEX)
    assert [i.title for i in items] == ["Pain = Memory", "4-Layer"]
    assert items[0].key == "memory-architecture/pain.md"


def test_stable_uuid_is_deterministic() -> None:
    assert P.stable_uuid("meta", "episode", "k") == P.stable_uuid("meta", "episode", "k")
    assert P.stable_uuid("meta", "episode", "k") != P.stable_uuid("meta", "reasoning", "k")


_REAL = Path.home() / ".claude" / "@agent-memory"


@pytest.mark.skipif(not _REAL.exists(), reason="real @agent-memory source not present")
def test_real_source_smoke() -> None:
    core = (_REAL / "agent-meta" / "agent-core-memory.md").read_text(encoding="utf-8")
    idx = (_REAL / "agent-meta" / "agent-memory-index.md").read_text(encoding="utf-8")
    sr = (_REAL / "shared-memory" / "core-reasoning-memory.md").read_text(encoding="utf-8")
    ac = P.parse_agent_core(core)
    assert len(ac["identity"]) == 3
    assert len(ac["emotional"]) >= 10
    assert len(P.parse_shared_reasoning(sr)) >= 10
    assert len(P.parse_active_episodes(idx)) >= 5
    assert all(e["file"].startswith("episodes/") for e in P.parse_active_episodes(idx))
