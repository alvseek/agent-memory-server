"""Episodic body pagination — bounded pages of timestamp groups.

An episode is a rolling document: every ``/update-episodic`` prepends a new sub-episode
block at the top, so the body grows without bound and an awakening can no longer carry it
whole. This module turns that one body into pages without touching storage and without
inventing anything: the page unit is the **timestamp group**, the cursor is the group's own
``###`` timestamp, and nothing here writes, migrates or persists a block id.

Why the timestamp and not an ordinal: every append prepends, so ordinal ``0`` names a
different block tomorrow. A timestamp survives an unrelated prepend because it names a
moment in the record, and it needs no new column.

Why a *group* and not a single block: two sub-episodes can share a timestamp. They are one
pagination unit — ``blocks_returned``/``blocks_total`` and ``limit`` all count groups — so a
collision needs neither a fingerprint nor a persisted id, and no group is ever split.

The parser is deliberately small and literal:

* a boundary is an H3 heading whose text *opens* with a timestamp — the template's
  ``### YYYY-MM-DD HH.MM - TITLE`` and the historical ``### [YYYY-MM-DD HH.MM] - TITLE``
  (colon minutes accepted too). Equivalent date/hour/minute values group together even
  when their spellings differ, and the stored header is never rewritten;
* an H3 heading inside a fenced code block is not a boundary, and an ordinary H3 heading
  inside a sub-episode ("### Discussion") is not one either — it has no leading timestamp;
* a body with no usable timestamp header is **one atomic group**, empty bodies included.
  Inventing an offset would contradict the cursor mechanism, and dropping the text would
  destroy content, so neither happens.

Delivery is bounded by a byte budget as well as a page size: the first selected group is
always emitted intact (a group is indivisible even above the ceiling), then groups are
added only while the UTF-8 content stays within the ceiling. The budget is a *content*
budget — the caller's JSON envelope still sits on top of it — and it never splits a block.

A full uncapped read returns the stored body byte for byte. Grouping can reorder
non-adjacent equal timestamps, which is only acceptable on a partial page; when every
group is emitted from the first one, the original text is what comes back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The default content ceiling for one page, in UTF-8 bytes.
#:
#: Derived on 2026-11-10 rather than picked, because a transport fact cannot be a taste:
#:
#: * the tightest client cap this fleet actually records is **10,000 tokens** — the low
#:   default of Claude Code's Read-tool cap (``control-files/SETUP.md``, "default may be as
#:   low as 10K"); the MCP tool-result cap was measured at 25,000 tokens and Codex's
#:   ``tool_output_token_limit`` is recommended at 64,000, so 10,000 is the binding one;
#: * the store's own counter converts at 4 characters per token
#:   (``control-files/procedures/setup-scripts/token-counter.py``'s fallback), so that cap is
#:   ~40,000 ASCII bytes of content;
#: * a measured single-record response on the isolated rig added **338 bytes** around a
#:   304-byte body (``GET /api/record/{uuid}``: 642 JSON bytes total), plus ~1 byte per line
#:   for JSON newline escaping.
#:
#: 32,000 is 80% of the 40,000-byte cap, which leaves room for that envelope, the escaping,
#: and the chars/4 heuristic being an *under*count of emoji-dense text. It is a content
#: budget for one record's body, not a promise that the whole tool response fits: other
#: waking layers and the client's JSON structure are not paged by this plan.
DEFAULT_MAX_BODY_BYTES = 32_000

#: An ATX H3 heading, allowing up to three leading spaces as CommonMark does. Only the first
#: three hashes open a heading, so ``####`` does not match.
_H3 = re.compile(r"^ {0,3}###[ \t]+(?P<text>.*?)[ \t]*$")

#: A sub-episode boundary: the heading text opens with a timestamp. The ``stamp`` group is
#: kept verbatim — colon or dot minutes, and the whitespace between date and time — because
#: it is what a cursor returns and what the caller sends back. The lookahead requires the
#: timestamp to end the heading or be followed by whitespace, so ``2026-11-10 10.05-x`` is
#: not silently accepted as a boundary.
_LEADING_STAMP = re.compile(
    r"^\[?(?P<stamp>"
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[ \t]+"
    r"(?P<hour>\d{2})[.:](?P<minute>\d{2})"
    r")\]?(?=\s|$)"
)

#: A cursor, which is the same stamp possibly written with the historical brackets. It is
#: matched whole rather than as a prefix: a cursor names one moment and nothing else.
_CURSOR_STAMP = re.compile(
    r"^\[?(?:"
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[ \t]+"
    r"(?P<hour>\d{2})[.:](?P<minute>\d{2})"
    r")\]?$"
)

#: An opening or closing fenced-code marker. A boundary-looking line inside a fence is code.
_FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")


@dataclass(frozen=True)
class PageBody:
    """One page of a record body, plus the two facts a caller needs to continue.

    ``blocks_returned`` and ``blocks_total`` describe *this page versus the whole record*;
    ``next_cursor`` alone answers "is more content left?", because a final page can return
    fewer than the total without anything remaining."""

    content: str
    blocks_returned: int
    blocks_total: int
    next_cursor: str | None

    def fields(self) -> dict[str, object]:
        """The page fields as they appear beside ``content`` in a public response."""
        return {
            "blocks_returned": self.blocks_returned,
            "blocks_total": self.blocks_total,
            "next_cursor": self.next_cursor,
        }


_Key = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _Group:
    """One timestamp group: every sub-episode block sharing a moment, in source order.

    ``key`` is the parsed moment the group is anchored on, kept beside the verbatim
    ``cursor`` so grouping and continuation always answer from the same parse."""

    cursor: str | None
    key: _Key | None
    text: str


def _stamp_key(match: re.Match[str]) -> tuple[int, int, int, int, int] | None:
    """The ``(year, month, day, hour, minute)`` a matched stamp names, or ``None`` when the
    numbers do not describe a real moment.

    Range checking matters more than it looks: a heading like ``### 2026-13-45 99.99`` is
    prose, not a boundary, and treating it as one would make a cursor that can never be
    matched again.
    """
    year, month, day = int(match["year"]), int(match["month"]), int(match["day"])
    hour, minute = int(match["hour"]), int(match["minute"])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    # Reject a day the month does not have (2026-02-30), which the ranges above allow.
    days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        days = 29
    if day > days:
        return None
    return (year, month, day, hour, minute)


def _heading_stamp(text: str) -> tuple[tuple[int, int, int, int, int], str] | None:
    """The moment a heading opens with, and its verbatim stamp text, or ``None``."""
    match = _LEADING_STAMP.match(text)
    if match is None:
        return None
    key = _stamp_key(match)
    if key is None:
        return None
    return key, match["stamp"]


def _cursor_key(cursor: str) -> tuple[int, int, int, int, int]:
    """Parse one caller-supplied cursor. Raises ``ValueError`` rather than guessing."""
    match = _CURSOR_STAMP.match(cursor.strip())
    if match is None:
        raise ValueError(
            f"invalid cursor {cursor!r}: expected a block timestamp from the record, "
            "such as '2026-11-10 10.05'"
        )
    key = _stamp_key(match)
    if key is None:
        raise ValueError(f"invalid cursor {cursor!r}: that is not a real date and time")
    return key


def _groups(content: str, *, splittable: bool) -> list[_Group]:
    """Split one body into timestamp groups, in first-occurrence order.

    Slices are taken from the original text and joined back without manufactured headings,
    so a group's bytes are the stored bytes. The preamble — everything before the first
    boundary — belongs to the first group: it is the record's own introduction and has
    nowhere else to go.
    """
    if not splittable:
        return [_Group(cursor=None, key=None, text=content)]

    lines = content.splitlines(keepends=True)
    # (line index, key, verbatim stamp) for every boundary outside a fence.
    boundaries: list[tuple[int, _Key, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        bare = line.rstrip("\r\n")
        marker = _FENCE.match(bare)
        if fence is None:
            if marker is not None:
                fence = marker["fence"]
                continue
            heading = _H3.match(bare)
            if heading is None:
                continue
            found = _heading_stamp(heading["text"].strip())
            if found is not None:
                key, stamp = found
                boundaries.append((index, key, stamp))
        elif marker is not None:
            # Only a fence of the same character, at least as long, closes it.
            run = marker["fence"]
            if run[0] == fence[0] and len(run) >= len(fence):
                fence = None

    if not boundaries:
        return [_Group(cursor=None, key=None, text=content)]

    # Block slices: each boundary owns its lines up to the next boundary. The first boundary
    # also carries the preamble, which is why the slice starts at 0 rather than at its line.
    slices: list[tuple[_Key, str, int, int]] = []
    for position, (line_index, key, stamp) in enumerate(boundaries):
        start = 0 if position == 0 else line_index
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(lines)
        slices.append((key, stamp, start, end))

    # Group by moment, preserving first-occurrence order and source order inside a group.
    order: list[_Key] = []
    parts: dict[_Key, list[str]] = {}
    stamps: dict[_Key, str] = {}
    for key, stamp, start, end in slices:
        if key not in parts:
            order.append(key)
            parts[key] = []
            stamps[key] = stamp
        parts[key].append("".join(lines[start:end]))
    return [
        _Group(cursor=stamps[key], key=key, text="".join(parts[key])) for key in order
    ]


def count_groups(content: str, *, splittable: bool = True) -> int:
    """How many pagination units a body holds — what ``blocks_total`` reports.

    A browse listing wants the number without the page, and deriving it from the same
    splitter is what keeps the listing and the page from disagreeing."""
    return len(_groups(content or "", splittable=splittable))


def page_body(
    content: str,
    *,
    cursor: str | None = None,
    limit: int | None = None,
    max_body_bytes: int | None = None,
    splittable: bool = True,
) -> PageBody:
    """One page of ``content``: whole by default, bounded by ``limit`` and the byte ceiling.

    ``cursor`` resumes *at* the group whose timestamp it names (inclusive), so a caller feeds
    a previous page's ``next_cursor`` straight back. An unknown or malformed cursor, or a
    nonpositive ``limit``, raises ``ValueError``: answering with page one would hide a
    continuation that failed, and no ordinal fallback exists.

    ``max_body_bytes`` caps the page's UTF-8 content, not the caller's serialized response.
    The first selected group is always emitted whole — a group is indivisible — and groups
    are added only while they fit, so the ceiling can be exceeded by at most one group.

    ``splittable=False`` is for a record type whose body is not an episode: the whole text is
    one atomic group even when it happens to contain H3 headings.
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError(f"invalid limit {limit!r}: expected a positive whole number of blocks")
    if max_body_bytes is not None and (
        isinstance(max_body_bytes, bool)
        or not isinstance(max_body_bytes, int)
        or max_body_bytes < 1
    ):
        raise ValueError(f"invalid max_body_bytes {max_body_bytes!r}: expected a positive number")

    groups = _groups(content or "", splittable=splittable)
    start = 0
    if cursor is not None:
        wanted = _cursor_key(cursor)
        start = next(
            (index for index, group in enumerate(groups) if group.key == wanted),
            -1,
        )
        if start < 0:
            raise ValueError(
                f"cursor {cursor!r} does not match any timestamp block in this record"
            )

    remaining = groups[start:]
    if limit is not None:
        remaining = remaining[:limit]

    emitted: list[_Group] = []
    used = 0
    for index, group in enumerate(remaining):
        size = len(group.text.encode("utf-8"))
        if index > 0 and max_body_bytes is not None and used + size > max_body_bytes:
            break
        emitted.append(group)
        used += size

    whole = start == 0 and len(emitted) == len(groups)
    following = groups[start + len(emitted)] if start + len(emitted) < len(groups) else None
    if whole:
        # A complete read is the stored body, byte for byte — grouping can move non-adjacent
        # equal timestamps next to each other, which is only acceptable on a partial page.
        page = content or ""
    else:
        page = "".join(group.text for group in emitted)
    return PageBody(
        content=page,
        blocks_returned=len(emitted),
        blocks_total=len(groups),
        next_cursor=following.cursor if following is not None else None,
    )
