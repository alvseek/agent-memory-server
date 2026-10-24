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


def test_parse_coding_reasoning_shares_the_pattern_shape() -> None:
    """The lane is the same level-3 shape as the universal set; only the caller's record
    type differs, so the parser reuses the one implementation."""
    items = P.parse_coding_reasoning(_SHARED_REASONING)
    assert len(items) == 2
    assert items[0].uuid == "fc94d140-905e-4f3d-8175-fafd8b84a109"
    assert items[0].key == items[0].uuid


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
    # the text past the link is the browse summary; the separator before it is markup
    # and drops, while a leading badge is not markup and stays
    assert items[1].content_summary == "the layers"
    assert items[0].content_summary == "⭐ - pain anchoring"


def test_parse_active_episodes_carries_the_index_summary() -> None:
    """The one-liner after the link is the episode's browse summary, deduped with the
    entry itself: the newer ref wins the whole reference, not just the date."""
    refs = P.parse_active_episodes(_INDEX)
    assert [r["file"] for r in refs] == ["episodes/build.md", "episodes/boundary.md"]
    assert [r["summary"] for r in refs] == ["summary of build", "summary of boundary"]


# --- the index shapes the fleet actually writes (2026-10-24) ---
#
# Every block below is a VERBATIM line (or header + line) out of one agent's real
# `agent-memory-index.md`, cut at the point where its prose runs on. The parser used to
# accept only the first of them — a dash bullet whose link starts the line — and returned
# ZERO active episodes for the eight agents that write any of the others. Since
# `archived_date IS NULL` is what every read path filters on, that meant every episode of
# those agents was stored archived and invisible. One case per shape, so a shape that stops
# parsing fails its own named test rather than moving a total.

_EPISODE_SHAPES = [
    (
        "meta/unity/admiral: dash bullet under a date header",
        "📂 2026-10-08:\n"
        "- [agent-memory-store-db-reconciliation.md]"
        "(episodes/agent-memory-store-db-reconciliation.md)"
        " - reconciled the store against the database, reversed the importer's archive rule",
        "episodes/agent-memory-store-db-reconciliation.md",
        "2026-10-08",
        "reconciled the store",
    ),
    (
        "aquazone: folder emoji + date + parenthetical, link mid-line",
        "📂 2026-10-06 (**October invoice scaled against the recorded work times; the billing"
        " columns appended**): [aquazone-invoice-generation]"
        "(episodes/2026-06-04-16.19-aquazone-invoice-generation.md) (new sub-episode) — window"
        " **1-Sep → 5-Oct**; 58 rows / 15 columns.",
        "episodes/2026-06-04-16.19-aquazone-invoice-generation.md",
        "2026-10-06",
        "(new sub-episode)",
    ),
    (
        "python: folder emoji + date, colon, then the link",
        "📂 2026-07-08: [OCX-1423 — Move Price DB-Writes to 3–6 AM WIB (Least-DB-Access"
        " Window), Shipped+Deployed+Verified](episodes/ocx-data-pipeline-scheduling.md) - Alvi"
        " picked Linear OCX-1423",
        "episodes/ocx-data-pipeline-scheduling.md",
        "2026-07-08",
        "Alvi picked Linear OCX-1423",
    ),
    (
        "invintiry: pin emoji, the date IS the link text",
        "📌 [2026-10-01 14.23](episodes/invintiry-council-closeout.md): Item Images council"
        " **archived** at [USER-NAME]'s sign-off.",
        "episodes/invintiry-council-closeout.md",
        "2026-10-01",
        "Item Images council",
    ),
    (
        "frontend-react: level-3 heading, ./episodes/ path, prose below",
        "📂 2026-05-25 15.18:\n"
        "\n"
        "### [2026-05-25-15.18-ocx-platform-pricechart-date-filter.md]"
        "(./episodes/2026-05-25-15.18-ocx-platform-pricechart-date-filter.md)\n"
        "PriceChart date-range pills redesign (`feat/ocx-prices-precomputed` branch).",
        "episodes/2026-05-25-15.18-ocx-platform-pricechart-date-filter.md",
        "2026-05-25",
        "",
    ),
    (
        "truth-seeker: bold date before the link, under no header",
        "- **2026-02-26** — [Compilation Split, Foreword & Tone Refinement]"
        "(episodes/2026-02-22-00.05-personal-journey-bahai-consultation.md) — Recovered"
        " crashed session.",
        "episodes/2026-02-22-00.05-personal-journey-bahai-consultation.md",
        "2026-02-26",
        "Recovered crashed session.",
    ),
    (
        "uiux-designer: bullet + emoji, date inside the link text",
        "- 📂 [2026-04-15 02.23 — Invintiry M6.5 Design]"
        "(episodes/2026-04-15-02.23-invintiry-m6.5-design.md): First session. Created M6.5"
        " design handoff",
        "episodes/2026-04-15-02.23-invintiry-m6.5-design.md",
        "2026-04-15",
        "First session.",
    ),
    (
        "ai-researcher: no bullet at all",
        "📂 2026-09-24:\n"
        "[The Aqdas Retrieval Agent](episodes/aqdas-rag-retrieval-agent.md) — built a"
        " structure-aware RAG agent over the Kitáb-i-Aqdas (aqdas-rag)",
        "episodes/aqdas-rag-retrieval-agent.md",
        "2026-09-24",
        "built a structure-aware RAG agent",
    ),
    (
        "trader: the link carries a #anchor into a sub-episode",
        "2025-11-04:\n"
        "- [Multi-Instrument Scanning Infrastructure Setup]"
        "(episodes/2025-11-03-02.32-trading-edge-breakthrough-discussion.md"
        "#2025-11-04-0224---multi-instrument-scanning-infrastructure-setup) - Implemented"
        ' "hunt for trends" strategy infrastructure.',
        "episodes/2025-11-03-02.32-trading-edge-breakthrough-discussion.md",
        "2025-11-04",
        "Implemented",
    ),
    (
        "frontend-nextjs: bare date-time prefix, no emoji",
        '2026-05-20 01.13: [Invintiry FE - Login "Checking session" Animated Dots + Auth Flow'
        " Investigation](episodes/2026-04-12-01.31-invintiry-fe-m6-sp1-unit-tracking.md) -"
        " Investigated BFF auth proxy",
        "episodes/2026-04-12-01.31-invintiry-fe-m6-sp1-unit-tracking.md",
        "2026-05-20",
        "Investigated BFF auth proxy",
    ),
]


@pytest.mark.parametrize(
    ("block", "expected_file", "expected_date", "expected_summary"),
    [(b, f, d, s) for _label, b, f, d, s in _EPISODE_SHAPES],
    ids=[label for label, *_ in _EPISODE_SHAPES],
)
def test_every_index_episode_shape_is_active(
    block: str, expected_file: str, expected_date: str, expected_summary: str
) -> None:
    """One shape per real agent. The date is the index's, not the filename's — the entry
    is when the session happened, and an inline-date line states it before the link."""
    index = "# Recent Context Episodes\n## Interactions List\n" + block + "\n"
    refs = P.parse_active_episodes(index)
    assert len(refs) == 1, refs
    assert refs[0]["file"] == expected_file
    assert refs[0]["date"] == expected_date
    if expected_summary:
        assert refs[0]["summary"].startswith(expected_summary)
    else:
        assert refs[0]["summary"] == ""


def test_an_episode_listed_in_any_shape_is_one_entry_not_two() -> None:
    """The same file referenced twice (newest first) stays one entry — the older
    reference is dropped whole, which is what keeps a re-import from archiving a file
    whose only difference is which of two bullets names it."""
    index = (
        "# Recent Context Episodes\n"
        "📂 2026-10-06: [a](episodes/a.md) — newest\n"
        "📌 [2026-01-01 09.00](episodes/a.md): oldest\n"
        "- **2026-02-02** — [a](episodes/a.md#sub) — middle\n"
    )
    refs = P.parse_active_episodes(index)
    assert len(refs) == 1
    assert refs[0]["date"] == "2026-10-06"
    assert refs[0]["summary"] == "newest"


def test_a_fenced_link_is_a_drawing_not_an_entry() -> None:
    """An index documents its own layout, and a ``` block is a picture of it."""
    index = (
        "# Recent Context Episodes\n"
        "```\n"
        "- [example.md](episodes/example.md) - how an entry looks\n"
        "```\n"
        "📂 2026-10-08:\n"
        "- [real.md](episodes/real.md) - the entry itself\n"
    )
    assert [r["file"] for r in P.parse_active_episodes(index)] == ["episodes/real.md"]


def test_a_long_inline_entry_summary_is_capped() -> None:
    """aquazone copies the episode's whole prose onto its entry line (8-10 KB on the real
    file). The summary is the one line a browse index shows, so it is capped rather than
    replayed whole."""
    body = "detail " * 400
    index = f"📂 2026-10-06: [t](episodes/t.md) - {body}\n"
    summary = P.parse_active_episodes(index)[0]["summary"]
    assert len(summary) <= P._SUMMARY_MAX + 1
    assert summary.endswith("…")


def test_inline_parenthetical_is_the_summary_when_nothing_follows_the_link() -> None:
    index = "📂 2026-06-04 (**Billing columns appended**): [t](episodes/t.md)\n"
    assert P.parse_active_episodes(index)[0]["summary"] == "**Billing columns appended**"


_KNOWLEDGE_SHAPES = (
    "# Recent Context Episodes\n"
    "📂 2026-10-08:\n"
    "- [ep.md](episodes/ep.md) - an episode, not a knowledge entry\n"
    "\n"
    "# Core Knowledge Base 📚\n"
    "## 📋 **KNOWLEDGE DIRECTORY & TABLE OF CONTENTS**\n"
    "### 🧠 **Memory Architecture Knowledge**\n"
    "- **[Pain = Memory Fundamentals](memory-architecture/pain-memory-fundamentals.md)**"
    " ⭐ - pain anchoring\n"
    "### **Research / Tooling:**\n"
    "- [2026-09-03-artifact-republish-view-gate.md]"
    "(knowledge-base/research/2026-09-03-artifact-republish-view-gate.md)"
    " — Why updating a published Artifact gets refused\n"
    "- [2026-09-18-rag-evaluation-mechanics.md]"
    "(knowledge-base/2026-09-18-rag-evaluation-mechanics.md)"
    " — How to evaluate a RAG pipeline\n"
    "### **Project Context Files:**\n"
    "- **invintiry**: [context-index.md](knowledge-base/invintiry/context-index.md)"
    " — architecture, tech-stack\n"
    "- [Absolute link](/control-files/procedures/memory/update-knowledge.md)"
    " — a procedure, not knowledge\n"
)


def test_every_index_knowledge_shape_is_active() -> None:
    """The bold wrapper is one agent's style, not the rule: aquazone, invintiry,
    ai-researcher, outreach-writer, telegent and gdevelop write a plain bullet, and the
    bold-only matcher filed every file they named as an unindexed (archived) one."""
    items = P.parse_knowledge_index(_KNOWLEDGE_SHAPES)
    assert [i.key for i in items] == [
        "memory-architecture/pain-memory-fundamentals.md",
        "knowledge-base/research/2026-09-03-artifact-republish-view-gate.md",
        "knowledge-base/2026-09-18-rag-evaluation-mechanics.md",
    ]
    assert items[0].content_summary == "⭐ - pain anchoring"
    assert items[1].content_summary == "Why updating a published Artifact gets refused"


def test_knowledge_keys_are_not_rewritten() -> None:
    """A path is stored as the index writes it (`knowledge-base/…` kept), because the
    record's uuid derives from it and rows already stored under that spelling must keep
    theirs. `./` is the one spelling normalised away — it names the same file."""
    items = P.parse_knowledge_index(
        "# Core Knowledge Base\n- [a](./knowledge-base/research/a.md) - A\n"
    )
    assert items[0].key == "knowledge-base/research/a.md"


def test_the_episode_list_is_never_read_as_knowledge() -> None:
    """meta, unity, admiral, infra and trader write episodes as `- [file](episodes/…)`,
    which is exactly the shape a knowledge bullet takes. Without section scoping every one
    of their episodes would be filed as knowledge."""
    items = P.parse_knowledge_index(_KNOWLEDGE_SHAPES)
    assert all("episodes/" not in i.key for i in items)
    assert all(i.key != "context-index.md" for i in items)


def test_one_path_listed_twice_is_one_knowledge_entry() -> None:
    """software-architect lists its design-patterns index twice; both bullets derive the
    same uuid, so reporting two entries would promise a row the store cannot hold."""
    items = P.parse_knowledge_index(
        "# Core Knowledge Base\n"
        "- **[Design Patterns](research/design-patterns/00-index.md)** - master index\n"
        "- [Design Patterns](research/design-patterns/00-index.md) - the same file again\n"
    )
    assert len(items) == 1


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


# --- the user profile (layer i, one record) ---

# The exact bullet form `user-profile-claude.sh` writes and greps. Written out here
# rather than imported from a fixture on purpose: this literal IS the contract between
# the shell and the parser, so a test that generated it from the parser's own assumptions
# would agree with itself and catch nothing.
_REAL_PROFILE = (
    "## AI Agent - User Profile\n"
    "\n"
    "- **[USER-NAME]** = Alvi\n"
    '- **[USER-PHILOSOPHY]** = "Success feeling first" - always start with working product.\n'
    "- **[USER-AGENT-VISION]** = Building a legendary ecosystem of specialized AI agents!\n"
)


def test_profile_parses_to_exactly_one_item() -> None:
    """One record, not one per field — presence is answerable by a row count."""
    items = P.parse_shared_profile(_REAL_PROFILE)
    assert len(items) == 1
    assert items[0].title == "User Profile"
    assert items[0].key == "user-profile"
    # the whole file is the body, so no field is dropped on the way in
    for marker in ("[USER-NAME]", "[USER-PHILOSOPHY]", "[USER-AGENT-VISION]"):
        assert marker in items[0].body


def test_profile_key_is_fixed_so_reimport_is_idempotent() -> None:
    """The key feeds `stable_uuid`; if it varied with content, every edit would insert
    a second row instead of updating the first."""
    edited = _REAL_PROFILE.replace("Alvi", "Someone Else")
    assert P.parse_shared_profile(edited)[0].key == P.parse_shared_profile(_REAL_PROFILE)[0].key


def test_a_blank_field_still_parses_and_stays_blank() -> None:
    """A deliberately empty field is data, not damage — the bootstrap must be able to
    tell 'told us nothing' from 'never asked'."""
    blanked = _REAL_PROFILE.replace(
        "- **[USER-AGENT-VISION]** = Building a legendary ecosystem of specialized AI agents!\n",
        "- **[USER-AGENT-VISION]** = \n",
    )
    items = P.parse_shared_profile(blanked)
    assert len(items) == 1
    assert "[USER-AGENT-VISION]" in items[0].body


def test_a_file_without_the_marker_is_not_a_profile() -> None:
    """Zero items, not one empty one — importing noise under a meaningful name is worse
    than importing nothing."""
    assert P.parse_shared_profile("# Some other document\n\nnothing to see here\n") == []
    assert P.parse_shared_profile("") == []


_ARCHIVE_MOMENTS = """\
# Agent meta - Archived Emotional Moments 2026

> **ARCHIVED MOMENTS**: kept verbatim below, newest-first.

## 📅 Archiving Rationale (2026-09-04 pass)

- **[2026-09-01 15.12]** — *[full-archive]*: redundant with a kept sibling
- **[2026-08-25 07.01]** — *[shortened]*: its lesson moved into a reasoning UUID

## 📅 Archived Moments (2026-09-04 pass)

### [2026-09-01 15.12] - "LOL, SO MANY GAPS" - THE REVIEW THAT CAUGHT IT
first moment body

### [2026-08-25 07.01] - THE SKILL I WROTE YESTERDAY RAN CLEAN TODAY
second moment body
"""


def test_archived_moments_parse_only_the_bracketed_blocks() -> None:
    """The rationale list sits at the same depth as the moments, so the bracketed date in
    the title is the only thing that separates them."""
    items = P.parse_archived_moments(_ARCHIVE_MOMENTS)
    assert [i.title for i in items] == [
        '[2026-09-01 15.12] - "LOL, SO MANY GAPS" - THE REVIEW THAT CAUGHT IT',
        "[2026-08-25 07.01] - THE SKILL I WROTE YESTERDAY RAN CLEAN TODAY",
    ]
    assert items[0].date == "2026-09-01"
    assert items[0].body.startswith("### [2026-09-01 15.12]")


def test_archived_moments_ignore_structural_headings() -> None:
    """`### Archiving Reasons` and `### Archived Content` are structure, not moments."""
    text = (
        "## Archived Happy Moments\n"
        "### Archiving Reasons\n"
        "### Archived Content\n"
        "### [2025-11-14 10:42] - A REAL MOMENT\nbody\n"
    )
    items = P.parse_archived_moments(text)
    assert [i.title for i in items] == ["[2025-11-14 10:42] - A REAL MOMENT"]


def test_overlapping_archive_forms_share_a_key() -> None:
    """The older single-file form and a year archive carry some of the same moments, and a
    shared key is what keeps that one record instead of two."""
    older = "## Emotional Moments\n### [2025-11-14 10:42] - SAME MOMENT\nbody A\n"
    year = "## Archived Moments (2026 pass)\n### [2025-11-14 10:42] - SAME MOMENT\nbody B\n"
    assert P.parse_archived_moments(older)[0].key == P.parse_archived_moments(year)[0].key
