"""Pure markdown parsers for the migration importer (SP-1 Step 2.1).

Text in, structured items out — no file I/O (the importer reads files and builds
MemoryRecords). Deterministic ``uuid5`` so re-import upserts instead of duplicating.
"""

from __future__ import annotations

import re
import uuid as _uuidlib
from dataclasses import dataclass, field

# Fixed namespace for deterministic record UUIDs (never regenerate).
_NS = _uuidlib.UUID("6f8d2c1a-0000-5000-a000-a6e6d0000001")

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_UUID_IN_BODY = re.compile(r"\*\*UUID\*\*:\s*`?([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})`?")
# A date-group header: an optional leading marker (📂 / 🔂 / none) then a YYYY-MM-DD.
# Tolerant of a trailing time + parenthetical label (`📂 2026-08-11 10.44 (LABEL…):`).
# The leading `(?![-*+>])` rejects list/quote markers so a `- [YYYY-MM-DD…](…)` episode
# entry (date-PREFIXED filename) is NEVER mistaken for a header; `[^\w\n]*` then eats
# emoji/space up to the leading date.
_DATE_GROUP = re.compile(r"^(?![-*+>])[^\w\n]*(\d{4}-\d{2}-\d{2})\b")
_EPISODE_ENTRY = re.compile(r"^-\s+\[([^\]]+)\]\((episodes/[^)]+)\)\s*-?\s*(.*)$")
_KNOWLEDGE_ENTRY = re.compile(r"^-\s+\*\*\[([^\]]+)\]\(([^)]+)\)\*\*\s*(.*)$")
_LEADING_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def stable_uuid(agent_id: str, record_type: str, key: str) -> str:
    """Deterministic record uuid from stable identity — re-import is idempotent."""
    return str(_uuidlib.uuid5(_NS, f"{agent_id}|{record_type}|{key}"))


@dataclass
class ParsedItem:
    title: str
    body: str
    key: str  # stable key for uuid derivation
    uuid: str | None = None  # pre-existing UUID to reuse (reasoning patterns)
    date: str | None = None
    tags: list[str] = field(default_factory=list)


def split_sections(text: str, level: int) -> list[tuple[str, str]]:
    """Return ``[(title, body)]`` for headings at exactly ``level``. A higher-level
    heading (fewer ``#``) closes the current section; deeper headings are body."""
    out: list[tuple[str, str]] = []
    title: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            hlevel = len(m.group(1))
            if hlevel == level:
                if title is not None:
                    out.append((title, "\n".join(buf).strip()))
                title, buf = m.group(2).strip(), []
                continue
            if hlevel < level:
                if title is not None:
                    out.append((title, "\n".join(buf).strip()))
                    title, buf = None, []
                continue
        if title is not None:
            buf.append(line)
    if title is not None:
        out.append((title, "\n".join(buf).strip()))
    return out


# --- agent-core-memory.md (layer ii: identity / reasoning / emotional) ---

_CORE_IDENTITY_SECTIONS = {
    "DOMAIN AGENT IDENTITY": "identity",
    "DOMAIN CORE KNOWLEDGE": "core-knowledge",
    "DOMAIN RAS": "ras",
}


def parse_agent_core(text: str) -> dict[str, list[ParsedItem]]:
    """Split agent-core-memory.md into identity (whole-section rows), reasoning
    (per-pattern), and emotional (per-moment)."""
    result: dict[str, list[ParsedItem]] = {"identity": [], "reasoning": [], "emotional": []}
    for title, body in split_sections(text, 1):
        name = title.strip()
        if name in _CORE_IDENTITY_SECTIONS:
            key = _CORE_IDENTITY_SECTIONS[name]
            result["identity"].append(ParsedItem(title=name.title(), body=body, key=key))
        elif name == "DOMAIN REASONING MEMORY":
            result["reasoning"].extend(_patterns(body, "reasoning"))
        elif name == "DOMAIN EMOTIONAL MEMORY":
            for mtitle, mbody in split_sections(body, 3):
                date = _first_date(mtitle)
                body_md = f"### {mtitle}\n{mbody}".strip()
                result["emotional"].append(
                    ParsedItem(title=mtitle, body=body_md, key=mtitle, date=date)
                )
    return result


def _patterns(text: str, record_type: str) -> list[ParsedItem]:
    """Level-3 items that may carry an embedded **UUID** to reuse."""
    items: list[ParsedItem] = []
    for title, body in split_sections(text, 3):
        full = f"### {title}\n{body}".strip()
        m = _UUID_IN_BODY.search(body)
        existing = m.group(1) if m else None
        items.append(ParsedItem(title=title, body=full, key=existing or title, uuid=existing))
    return items


# --- shared-memory (layer i) ---


def parse_shared_reasoning(text: str) -> list[ParsedItem]:
    return _patterns(text, "reasoning")


def parse_shared_knowledge(text: str) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    for title, body in split_sections(text, 3):
        items.append(ParsedItem(title=title, body=f"### {title}\n{body}".strip(), key=title))
    return items


# --- agent-memory-index.md (layer iii: knowledge index + active episodes) ---


def parse_knowledge_index(index_text: str) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    for line in index_text.splitlines():
        m = _KNOWLEDGE_ENTRY.match(line.strip())
        if m:
            title, path, desc = m.group(1), m.group(2), m.group(3).strip()
            items.append(ParsedItem(title=title, body=desc or title, key=path))
    return items


def parse_active_episodes(index_text: str) -> list[dict[str, str]]:
    """Active episode refs from the index (Recent Context Episodes), deduped by file,
    newest-first (first occurrence wins). Each: {date, summary, file}."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    cur_date = ""
    for raw in index_text.splitlines():
        line = raw.strip()
        dm = _DATE_GROUP.match(line)
        if dm:
            cur_date = dm.group(1)
            continue
        em = _EPISODE_ENTRY.match(line)
        if em:
            file = em.group(2)
            if file in seen:
                continue
            seen.add(file)
            out.append({"date": cur_date, "summary": em.group(3).strip(), "file": file})
    return out


def _first_date(text: str) -> str | None:
    m = _LEADING_DATE.search(text)
    return m.group(1) if m else None


_FILENAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def first_heading(text: str) -> str | None:
    """The first markdown heading's text (any level), or ``None``. Used to title an
    archived item that has no index line to describe it."""
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            return m.group(2).strip()
    return None


def date_from_filename(name: str) -> str | None:
    """The leading ``YYYY-MM-DD`` in a filename, or ``None`` for rolling/undated files.
    Legacy archived episodes carry this prefix; rolling files (no prefix) don't."""
    m = _FILENAME_DATE.match(name)
    return m.group(1) if m else None
