"""Pure markdown parsers for the migration importer (SP-1 Step 2.1).

Text in, structured items out — no file I/O (the importer reads files and builds
MemoryRecords). Deterministic ``uuid5`` so re-import upserts instead of duplicating.
"""

from __future__ import annotations

import re
import uuid as _uuidlib
from collections.abc import Iterator
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
# Every index in the fleet puts an episode's file in a markdown link, and that target is
# the ONLY thing the shapes share — so it is what this matches. The line prefixes vary per
# agent and per index generation, and none of them is load-bearing:
#
#   - [title](episodes/f.md) - desc              the bullet form (meta, unity, admiral, infra)
#   - [title](episodes/f.md#anchor) - desc       a sub-episode inside one file (trader)
#   - 📂 2026-10-06 (summary): [title](episodes/f.md) …   date and entry on ONE line (aquazone)
#   - 📂 2026-07-08: [title](episodes/f.md) - desc         same, no parenthetical (python)
#   - 2026-05-20 01.13: [title](episodes/f.md) - desc      a bare date-time prefix (frontend-nextjs)
#   - 📌 [2026-10-01 14.23](episodes/f.md): desc           the date IS the link text (invintiry)
#   - - 📂 [2026-04-15 …](episodes/f.md): desc        bullet + emoji before the link (uiux-designer)
#   - - **2026-02-26** — [title](episodes/f.md) — desc  a bold date before the link (truth-seeker)
#   - [title](episodes/f.md) — desc                        no bullet at all (ai-researcher)
#   - ### [f.md](./episodes/f.md)                          a heading link (frontend-react)
#
# `./episodes/…` is the same path spelled from the agent folder, and `#anchor` names a
# sub-episode inside the file rather than another file.
_EPISODE_LINK = re.compile(
    r"\[([^\]]*)\]\(\s*(?:\./)?((?:[^()\s#]*/)?episodes/[^()\s#]+\.md)(?:#[^()\s]*)?\s*\)"
)
# A date carried by an entry that sits under no date header: truth-seeker writes
# `- **2026-02-26** — [..](episodes/..)`. Kept separate from `_DATE_GROUP`, which rejects
# bullet lines on purpose so a bullet's own leading date is never read as a section header.
_ENTRY_LEADING_DATE = re.compile(r"^[-*+]\s+(?:\*\*|__)?(\d{4}-\d{2}-\d{2})\b")
# An inline-date entry can carry its one-liner as a parenthetical between the date and the
# link: `📂 2026-10-06 (**October invoice scaled …**): [title](episodes/..)`.
_PAREN_AFTER_DATE = re.compile(r"^\s*\((.+?)\)\s*:")
# A knowledge entry is a bullet whose link points at a knowledge file. The bold wrapper
# (`- **[title](path)**`) is one agent's style, not the rule: aquazone, invintiry,
# ai-researcher, outreach-writer, telegent and gdevelop write a plain `- [title](path)`.
_KNOWLEDGE_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^()\s]+?\.md)\s*\)")
_BULLET = re.compile(r"^[-*+]\s+")
_LEADING_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
# The separator(s) an index writes between a link and its text, and a leading `**` from the
# bold wrapper. Markup, so it drops from a summary; a badge is not markup and stays.
_ENTRY_SEPARATORS = " \t-–—:,*"
# A summary is one line by contract. Several inline-date indexes copy the episode's whole
# prose onto its entry line (aquazone's run to 8-10 KB), which would then be replayed into
# every browse listing, so the summary is capped rather than stored whole.
_SUMMARY_MAX = 400


def stable_uuid(agent_id: str, record_type: str, key: str) -> str:
    """Deterministic record uuid from stable identity — re-import is idempotent."""
    return str(_uuidlib.uuid5(_NS, f"{agent_id}|{record_type}|{key}"))


# --- frontmatter: the authored metadata a document carries above its body ---

_FRONTMATTER_DELIM = "---"


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, object]:
    """A deliberate subset of YAML, not a general parser. The store authors a fixed
    shape — scalars and inline lists — so `project: x` and `tags: [a, b]` are all that
    must parse. Anything else is skipped rather than guessed at, because a wrong value
    (a project that is not the project) is worse than a missing one."""
    meta: dict[str, object] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip("\"'") for v in value[1:-1].split(",")]
            meta[key] = [v for v in items if v]
        else:
            meta[key] = value.strip("\"'")
    return meta


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a leading ``---`` frontmatter block from the body: ``(meta, body)``.

    No frontmatter (or an unterminated one) returns ``({}, text)`` unchanged, so a file
    without metadata is imported exactly as before. The returned body has the metadata
    block removed, so ``full_content`` carries the document, not a copy of its columns."""
    lines = text.lstrip("\ufeff").split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        return {}, text
    close = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == _FRONTMATTER_DELIM), None
    )
    if close is None:
        return {}, text
    return _parse_frontmatter_lines(lines[1:close]), "\n".join(lines[close + 1 :])


def meta_str(meta: dict[str, object], key: str) -> str | None:
    """A scalar frontmatter value, or ``None`` when absent/blank. A blank is absent."""
    value = meta.get(key)
    return value if isinstance(value, str) and value else None


def meta_tags(meta: dict[str, object]) -> list[str]:
    """The ``tags`` frontmatter value as a string list; ``[]`` when absent or malformed."""
    value = meta.get("tags")
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    if isinstance(value, str) and value:
        return [value]
    return []


@dataclass
class ParsedItem:
    title: str
    body: str
    key: str  # stable key for uuid derivation
    uuid: str | None = None  # pre-existing UUID to reuse (reasoning patterns)
    date: str | None = None
    tags: list[str] = field(default_factory=list)
    # The index line's one-line description of this item, when the index carries one.
    content_summary: str | None = None


def split_sections(text: str, level: int) -> list[tuple[str, str]]:
    """Return ``[(title, body)]`` for headings at exactly ``level``. A higher-level
    heading (fewer ``#``) closes the current section; deeper headings are body.

    Lines inside a fenced code block are never headings: a shell comment in a bash
    block starts with ``#`` too, and treating it as a boundary silently truncates
    the section at that line."""
    out: list[tuple[str, str]] = []
    title: str | None = None
    buf: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        m = None if fenced else _HEADING.match(line)
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
            result["reasoning"].extend(_patterns(body))
        elif name == "DOMAIN EMOTIONAL MEMORY":
            for mtitle, mbody in split_sections(body, 3):
                date = _first_date(mtitle)
                body_md = f"### {mtitle}\n{mbody}".strip()
                result["emotional"].append(
                    ParsedItem(title=mtitle, body=body_md, key=mtitle, date=date)
                )
    return result


# --- archived emotional moments (agent-<domain>/archive/…) ---

# A moment block's title opens with a date: `### 2026-08-13 17.15 - TITLE` (what the
# archive files actually author) or the bracketed `### [2026-09-01 15.12] - TITLE` (an
# older template). Both forms are accepted; the date prefix is what separates a moment
# from the other level-3 headings an archive file carries at the same depth
# (`### Archived Content`, `### Archiving Reasons`), which are structure, not moments.
_MOMENT_TITLE = re.compile(
    r"^(?:\[\d{4}-\d{2}-\d{2}[^\]]*\]|\d{4}-\d{2}-\d{2}(?:\s+\d{2}\.\d{2})?)\s*-\s*\S"
)


def parse_archived_moments(text: str) -> list[ParsedItem]:
    """Emotional moments out of an archive file: level-3 blocks whose title opens with a
    bracketed date.

    Archiving *removes* a moment from the live core memory and keeps it in
    ``archive/<year>-archived-moments.md`` (one pass per archiving run) or the older
    ``archive/moments/emotional-key-moments.md``. The importer reads the live file, so
    without this the archived moments are invisible to a fresh import while the rows an
    *earlier* import wrote stay active in the store.

    A moment's key is its title, which is what makes the two archive forms safe to read
    together: they overlap (a 2025 moment appears in both the older file and the year
    archive) and a shared key upserts to one record instead of two.
    """
    items: list[ParsedItem] = []
    for title, body in split_sections(text, 3):
        t = title.strip()
        if not _MOMENT_TITLE.match(t):
            continue
        items.append(
            ParsedItem(title=t, body=f"### {t}\n{body}".strip(), key=t, date=_first_date(t))
        )
    return items


def _patterns(text: str) -> list[ParsedItem]:
    """Level-3 items that may carry an embedded **UUID** to reuse."""
    items: list[ParsedItem] = []
    for title, body in split_sections(text, 3):
        full = f"### {title}\n{body}".strip()
        m = _UUID_IN_BODY.search(body)
        existing = m.group(1) if m else None
        items.append(ParsedItem(title=title, body=full, key=existing or title, uuid=existing))
    return items


# --- the agent entity's own fields (read here, stored as columns) ---

# Roster fields, read out of an agent's identity body. Matched by line rather than by
# record title on purpose: a markdown-born agent's identity is titled "Domain Agent
# Identity" (the importer's `.title()` of the H1) while a DB-born one is titled "Agent
# Identity" (create-agent's `persist-identity`), so title-matching would see only half
# the fleet.
_NAME_RE = re.compile(r"^\*\*Name\*\*:\s*(.+?)\s*$", re.M)
_ROLE_RE = re.compile(r"^\*\*Role\*\*:\s*(.+?)\s*$", re.M)
# Fallback for agents predating the `Role` line. Kept as a separate pattern rather than
# an alternation so precedence is explicit: an alternation would resolve to whichever
# line appears first in the file, making the answer depend on template ordering.
_PURPOSE_RE = re.compile(r"^\*\*Main Purpose\*\*:\s*(.+?)\s*$", re.M)


def parse_identity_fields(bodies: list[str]) -> dict[str, str | None]:
    """The agent entity's three content fields, read across its identity records:
    first ``**Name**``, first ``**Role**`` (falling back to ``**Main Purpose**``), and
    the agent's own ``**UUID**`` — its "digital soul" id, which is content rather than
    a key, so it is read here like any other field. All ``None`` when the agent has no
    identity — a real state the caller surfaces as "(no identity recorded)", never as a
    missing row.

    Translating markdown into stored values is this module's job, not the service's.
    The roster is now a plain column read, so this runs **once at import** to fill
    ``agent.name`` / ``agent.role`` / ``agent.uuid`` instead of on every request."""
    def first(pattern: re.Pattern[str]) -> str | None:
        for body in bodies:
            m = pattern.search(body)
            if m:
                return m.group(1)
        return None

    return {
        "name": first(_NAME_RE),
        "role": first(_ROLE_RE) or first(_PURPOSE_RE),
        "uuid": first(_UUID_IN_BODY),
    }


# --- shared-memory (layer i) ---


def parse_shared_reasoning(text: str) -> list[ParsedItem]:
    return _patterns(text)


def parse_coding_reasoning(text: str) -> list[ParsedItem]:
    """The coding-reasoning lane: the same level-3 pattern shape as the universal reasoning
    set, in its own corpus. Its records are typed ``coding_reasoning``, so ``awaken`` never
    returns them to a chat agent; the coding awakening reads the lane through its own call.
    The title is the key unless the block carries an embedded ``**UUID**``, exactly as the
    universal set does."""
    return _patterns(text)


def parse_shared_knowledge(text: str) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    for title, body in split_sections(text, 3):
        items.append(ParsedItem(title=title, body=f"### {title}\n{body}".strip(), key=title))
    return items


def parse_shared_ras(text: str) -> list[ParsedItem]:
    """The universal RAS triggers — level-3 blocks, each carrying a ``**UUID**`` to reuse.

    A trigger is a titled protocol with a stable identity, which is the same shape as a
    reasoning pattern; only the record type differs, so the shared pattern parser serves
    both."""
    return _patterns(text)


# The line marker the profile is recognized by. It is also what `user-profile-claude.sh`
# greps, which makes this string a contract between bash and Python with no shared
# schema to enforce it — hence the round-trip test rather than trust.
_PROFILE_MARKER = "[USER-NAME]"


def parse_shared_profile(text: str) -> list[ParsedItem]:
    """The user profile — **one** item carrying the whole file, not one per field.

    Presence is the only question the first-run bootstrap asks, and one record answers it
    with a row count; three would admit partial states with no rule for resolving them. A
    field the user deliberately left blank stays blank *inside* the body, which is what
    lets the bootstrap distinguish "never told us" from "told us nothing".

    Returns **empty** when the file carries no ``[USER-NAME]`` marker. A file without it is
    not a profile, and importing it anyway would store noise under a name that promises
    meaning — the same reasoning that makes the fleet importer refuse an unparseable
    identity rather than write a half-agent.

    The body is ``strip()``ed, so the stored record is a trailing newline shorter than the
    file it came from. Deliberate, but it means a byte comparison of store against file
    needs the same strip on both sides or it will report a difference that is not one.
    """
    if _PROFILE_MARKER not in text:
        return []
    return [ParsedItem(title="User Profile", body=text.strip(), key="user-profile")]


# --- agent-memory-index.md (layer iii: knowledge index + active episodes) ---


def _unfenced_lines(text: str) -> Iterator[str]:
    """Lines outside fenced code blocks, in order.

    Both index sections document themselves: a knowledge index may hold a ```tree``` of
    the knowledge-base layout, and a procedure line may quote a link. A fence is a
    drawing of the shape, never the shape, so its lines are not entries."""
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def _kb_section(index_text: str) -> list[str]:
    """The lines under the first level-1 heading that names knowledge.

    Scoped rather than whole-document because this same index also carries the episode
    list, whose entries are links too (`- [file](episodes/…)` in meta, unity, admiral,
    infra, trader). Scanning everything would file every episode as knowledge. The level-1
    heading is the layer boundary in the agent template, and its block ends at the next
    level-1 heading — which is where the episodes begin.

    Falls back to the whole document when no such heading exists, so an index written
    against a template this parser has not seen keeps behaving as it did.
    """
    out: list[str] = []
    found = False
    inside = False
    for line in _unfenced_lines(index_text):
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            inside = "knowledge" in m.group(2).lower()
            found = found or inside
            continue
        if inside:
            out.append(line)
    return out if found else list(_unfenced_lines(index_text))


def parse_knowledge_index(index_text: str) -> list[ParsedItem]:
    """Active knowledge entries from the index's knowledge directory.

    ``body`` is the index description, which stands in for the whole body only when the
    file itself is missing (the importer prefers the real file). The same string is
    carried as ``content_summary`` in every case, because that one line is what a browse
    index shows beside the title.

    A bullet is accepted whatever wraps its link, because the fleet writes both
    ``- **[title](path)** desc`` and a plain ``- [title](path) desc``; requiring the bold
    wrapper read the plain form as "not in the index" and archived every file it named.
    Two targets are not knowledge entries: an absolute path (a procedure link), and
    ``context-index.md``, which is the project-context pointer Hermod owns — importing it
    here would file a project's index as one of Munnin's knowledge records.
    """
    items: list[ParsedItem] = []
    seen: set[str] = set()
    for line in _kb_section(index_text):
        raw = line.strip()
        if not _BULLET.match(raw):
            continue
        m = _KNOWLEDGE_LINK.search(raw)
        if not m:
            continue
        title, path = m.group(1).strip(), m.group(2).strip()
        if path.startswith(("/", "http://", "https://")):
            continue
        if path.rsplit("/", 1)[-1] == "context-index.md":
            continue
        if "/episodes/" in f"/{path}":
            continue
        # `./` is a spelling of the same path, so it is dropped from the key that the
        # record's uuid is derived from. A leading `knowledge-base/` is kept: rows
        # already stored under that spelling must keep their uuid.
        key = _strip_dot_slash(path)
        if key in seen:
            # One path, two bullets is still one file. Without this an index that lists a
            # ported file twice (software-architect's design-patterns index) reports one
            # more entry than the store can hold, since both map to the same uuid.
            continue
        seen.add(key)
        desc = raw[m.end() :].lstrip(_ENTRY_SEPARATORS).strip()
        items.append(
            ParsedItem(
                title=title,
                body=desc or title,
                key=key,
                # The separator the index writes before the text is markup, not
                # content, so the summary drops it; a leading badge is not markup and
                # stays. Only the summary is cleaned — ``body`` stays verbatim, since
                # it can stand in for a missing file.
                content_summary=_cap(desc) or None,
            )
        )
    return items


def _strip_dot_slash(path: str) -> str:
    """`./episodes/x.md` and `episodes/x.md` are one path; the key is the second."""
    return path[2:] if path.startswith("./") else path


def _cap(text: str) -> str:
    """A summary is one line: cap it rather than replay an entry's whole prose."""
    if len(text) <= _SUMMARY_MAX:
        return text
    return text[:_SUMMARY_MAX].rstrip() + "…"


def _entry_summary(line: str, link_end: int, date_end: int | None) -> str:
    """The one-liner an entry line carries after its link.

    When nothing follows the link and the line opened with an inline date, the summary is
    the parenthetical between that date and the link — the only descriptive text the entry
    has. A heading entry (`### [file](./episodes/f.md)`) has neither, so its summary is
    empty rather than borrowed from the paragraph below it: that paragraph is the episode's
    own prose, and guessing at it is how a summary stops describing the entry.
    """
    rest = line[link_end:].lstrip(_ENTRY_SEPARATORS).strip()
    if not rest and date_end is not None:
        m = _PAREN_AFTER_DATE.match(line[date_end:])
        if m:
            rest = m.group(1).strip()
    return _cap(rest)


def parse_active_episodes(index_text: str) -> list[dict[str, str]]:
    """Active episode refs from the index (Recent Context Episodes), deduped by file,
    newest-first (first occurrence wins). Each: {date, summary, file}.

    A line is an entry when it links to an episode file, whatever precedes or wraps that
    link (see ``_EPISODE_LINK`` for the ten shapes the fleet actually writes). The date
    comes from, in order: the date this same line opens with, a bold date at the head of a
    bullet, the date section above it, and lastly the link text — `📌 [2026-10-01
    14.23](episodes/…)` states its date as the link itself.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    cur_date = ""
    for raw in _unfenced_lines(index_text):
        line = raw.strip()
        dm = _DATE_GROUP.match(line)
        if dm:
            cur_date = dm.group(1)
        date_end = dm.end() if dm else None
        lead = _ENTRY_LEADING_DATE.match(line)
        for m in _EPISODE_LINK.finditer(line):
            file = m.group(2)
            if file in seen:
                continue
            seen.add(file)
            date = (lead.group(1) if lead else "") or cur_date or _first_date(m.group(1)) or ""
            out.append(
                {
                    "date": date,
                    "summary": _entry_summary(line, m.end(), date_end),
                    "file": file,
                }
            )
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


# A legacy filename's leading date and optional time, with its separator: `2025-09-07-`
# or `2026-05-26-23.36-`. Stripped so the title is the name, not the name plus a date.
_FILENAME_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}(?:-\d{2}\.\d{2})?[-_]?")


def title_from_filename(name: str) -> str:
    """The record title for an episode file: the filename without its date prefix, so a
    legacy `2026-05-26-23.36-agent-memory-task-system.md` titles as
    `agent-memory-task-system` and a rolling file is already clean. Falls back to the
    date-stripped stem if stripping would leave nothing."""
    stem = name[:-3] if name.endswith(".md") else name
    stripped = _FILENAME_DATE_PREFIX.sub("", stem)
    return stripped or stem
