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


def test_parse_active_episodes_rich_date_headers() -> None:
    """Real fleet headers carry a time + parenthetical label after the date, and some use
    a different leading emoji (🔂) or none at all. The leading date must STILL be extracted
    — regression for the strict `📂 YYYY-MM-DD:` matcher that dropped these to date=''
    (breaking awaken's latest_episode chronology, found in P8)."""
    index = (
        "# Recent Context Episodes\n"
        "## 📅 Interactions List\n"
        "\n"
        "📂 2026-08-11 10.44 (AQUAZONE: QA ONTOLOGY FIXED — runbook vs playbook):\n"
        "- [aquazone-qa.md](episodes/aquazone-qa.md) - ontology fix\n"
        "\n"
        "📂 2026-08-10 07.40 (AGENT-MEMORY-SERVER: MUNNIN SCAFFOLD):\n"
        "- [arch.md](episodes/arch.md) - scaffold delta\n"
        "📂 2026-08-08 11.34 (AGENT-MEMORY: ARCHITECTURE DESIGNED):\n"
        "- [arch.md](episodes/arch.md) - dup, older ref, ignored\n"
        "🔂 2026-07-15 09:02 (BRYES: SHELL EFFECTOR):\n"
        "- [bryes.md](episodes/bryes.md) - effector channel\n"
        "2026-05-26:\n"
        "- [bare.md](episodes/bare.md) - bare header, no emoji\n"
        # a rolling episode file whose FILENAME is date-prefixed: the entry line must NOT
        # be mistaken for a date-group header just because a date sits after the `- [`.
        "📂 2026-04-10 09.00 (DATE-PREFIXED ROLLING FILE):\n"
        "- [2026-05-27-00.10-saas-pivot.md](episodes/2026-05-27-00.10-saas-pivot.md) - rolling\n"
    )
    by_file = {e["file"]: e["date"] for e in P.parse_active_episodes(index)}
    assert by_file["episodes/aquazone-qa.md"] == "2026-08-11"  # rich header: time + label
    assert by_file["episodes/arch.md"] == "2026-08-10"  # dedup: newest ref wins its date
    assert by_file["episodes/bryes.md"] == "2026-07-15"  # 🔂 emoji + HH:MM time
    assert by_file["episodes/bare.md"] == "2026-05-26"  # no emoji at all
    # date-PREFIXED entry stayed an episode (not swallowed as a header) + took the HEADER's
    # date (2026-04-10), NOT the 2026-05-27 embedded in its own filename
    assert by_file["episodes/2026-05-27-00.10-saas-pivot.md"] == "2026-04-10"
    # every active entry carries a REAL date — none empty
    assert all(e["date"] for e in P.parse_active_episodes(index))


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


# --- SP-4 helpers: first_heading + date_from_filename ---


def test_first_heading_various_levels() -> None:
    assert P.first_heading("no heading here\njust text") is None
    assert P.first_heading("## Second level\nbody") == "Second level"
    assert P.first_heading("intro\n\n#### Deep\nx") == "Deep"
    assert P.first_heading("# Top **bold**\n## Sub") == "Top **bold**"


def test_date_from_filename() -> None:
    assert P.date_from_filename("2025-09-07-4layer-system.md") == "2025-09-07"
    assert P.date_from_filename("2026-03-04-02.04-foo.md") == "2026-03-04"
    assert P.date_from_filename("agent-memory-mcp-server-build.md") is None
    assert P.date_from_filename("no-date.md") is None


_FENCED_CORE = """\
# DOMAIN AGENT IDENTITY
I am admiral.

# DOMAIN CORE KNOWLEDGE
Fleet orchestration runbook:

```bash
# 1. generate a session
ID=$(uuidgen)
# 2. awaken the agent
claude --resume $ID
```

CRITICAL: never resume a dead session.

# DOMAIN RAS
## Trigger
do the thing
"""

_SHARED_KNOWLEDGE = """\
# KNOWLEDGE MEMORY
## FUNDAMENTALS
### **Line Ending Rule**
always LF
### **Fenced Example**
```bash
# not a heading
echo hi
```
trailing prose after the fence
"""


def test_fenced_comments_are_not_section_boundaries() -> None:
    """A ``#`` comment inside a bash block is content, not a heading — otherwise the
    section is silently truncated at that line (agent-admiral, 2026-08-19)."""
    titles = [t for t, _ in P.split_sections(_FENCED_CORE, 1)]
    assert titles == ["DOMAIN AGENT IDENTITY", "DOMAIN CORE KNOWLEDGE", "DOMAIN RAS"]
    assert "1. generate a session" not in titles


def test_parse_agent_core_keeps_content_after_a_fenced_block() -> None:
    ac = P.parse_agent_core(_FENCED_CORE)
    assert len(ac["identity"]) == 3
    ck = next(i for i in ac["identity"] if i.key == "core-knowledge")
    # the whole block survives, comments included, and so does the prose below it
    assert "# 1. generate a session" in ck.body
    assert "CRITICAL: never resume a dead session." in ck.body


def test_parse_shared_knowledge_splits_entries_and_respects_fences() -> None:
    items = P.parse_shared_knowledge(_SHARED_KNOWLEDGE)
    assert [i.title for i in items] == ["**Line Ending Rule**", "**Fenced Example**"]
    assert "trailing prose after the fence" in items[1].body


# --- the agent entity: Name / Role read out of an identity body ---
IDENTITY = """# DOMAIN AGENT IDENTITY

## Agent Identity
**Name**: Claude Meta
**Role**: Meta Agent for Alvi
**Folder**: `claude-meta/`
"""


def test_identity_fields_reads_name_and_role() -> None:
    assert P.parse_identity_fields([IDENTITY]) == {
        "name": "Claude Meta",
        "role": "Meta Agent for Alvi",
        "uuid": None,
    }


def test_identity_fields_reads_the_agents_own_uuid() -> None:
    """The agent's "digital soul" id is content — a human maintains it on a markdown
    line — which is exactly why the table is keyed on (user_id, agent_id) instead."""
    body = IDENTITY + "**UUID**: `fbb2d630-ea37-4f18-93f7-69c241ad2c1d`\n"
    assert P.parse_identity_fields([body])["uuid"] == "fbb2d630-ea37-4f18-93f7-69c241ad2c1d"


def test_identity_fields_are_none_when_there_is_no_identity() -> None:
    """Never drop an agent silently — absent identity is a finding, not an absence.
    The importer stores these as NULL columns and the roster renders the agent anyway."""
    assert P.parse_identity_fields(["just an episode"]) == {
        "name": None, "role": None, "uuid": None,
    }


def test_identity_fields_do_not_depend_on_the_record_title() -> None:
    """create-agent titles its record "Agent Identity"; the importer titles it "Domain
    Agent Identity". Matching by line rather than title is what keeps both visible —
    the parser never sees a title at all, which is the point."""
    body = IDENTITY.replace("# DOMAIN AGENT IDENTITY", "# AGENT IDENTITY")
    assert P.parse_identity_fields([body])["name"] == "Claude Meta"


def test_main_purpose_is_the_role_fallback() -> None:
    body = "# DOMAIN AGENT IDENTITY\n**Name**: Claude Old\n**Main Purpose**: Legacy duty\n"
    assert P.parse_identity_fields([body])["role"] == "Legacy duty"


def test_role_wins_over_main_purpose_regardless_of_order() -> None:
    """Precedence must come from the rule, not from which line the file happens to put
    first — an alternation regex would return whichever appeared earlier."""
    body = (
        "# DOMAIN AGENT IDENTITY\n**Name**: Claude Odd\n"
        "**Main Purpose**: the long purpose paragraph\n**Role**: The Role\n"
    )
    assert P.parse_identity_fields([body])["role"] == "The Role"


def test_identity_searched_across_all_records() -> None:
    """An agent has three identity records; Name/Role live in only one of them."""
    ras = "# DOMAIN RAS\ntriggers"
    assert P.parse_identity_fields([ras, IDENTITY])["role"] == "Meta Agent for Alvi"
