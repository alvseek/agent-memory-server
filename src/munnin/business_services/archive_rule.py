"""The archive rule: which episodes may be retired, which need a decision.

Pure: rows in, three lists out. No repository, no clock of its own, so every rule here
can be tested without a database and both transports share one implementation.

The rule reads only what the metadata projection carries: tags, dates and project. It
never reads a body, and it never guesses whether a theme is finished; the agent stamps
``finished`` when it closes a theme, and this decides what may be archived from that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

from munnin.data_entities.memory_record import EpisodeMetadata

#: The tag that marks a theme as closed. Written by the update-episodic procedure.
FINISHED_TAG = "finished"

#: What a protected row carries: the record plus why it was spared.
NEWEST_OF_PROJECT = "newest of project"
NEWEST_OVERALL = "newest overall"
UNDATED = "undated"


@dataclass(kw_only=True)
class ProtectedRow:
    """One row the rule refuses to touch, with the reason it does."""

    record: EpisodeMetadata
    reason: str


@dataclass(kw_only=True)
class Partition:
    """The three sets a scan produces.

    ``auto`` is what ``apply`` archives: tagged and unprotected. ``ask`` is what the
    procedure presents for a decision. ``protected`` is what the rule refuses, with a
    reason, and it is reported rather than acted on."""

    auto: list[EpisodeMetadata] = field(default_factory=list)
    ask: list[EpisodeMetadata] = field(default_factory=list)
    protected: list[ProtectedRow] = field(default_factory=list)


def _parse(value: str | None) -> datetime | None:
    """An authored or server-stamped date as an aware datetime, or ``None``.

    The store holds two shapes: date-only values from the importer and ISO timestamps
    from the service. Both parse; anything unparseable returns ``None`` rather than
    being compared as a string, because a lexical comparison across those two shapes
    silently orders them wrong."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _newest(rows: Sequence[EpisodeMetadata]) -> set[str]:
    """The uuids of every row tied at the newest ``created_date`` in its group.

    Grouping is by ``project``, with ``None`` as a group of its own, because the
    awakening selects one body per project and a single unprojected continuity record.
    A row with no parseable date is not treated as newest; it is protected separately
    by :func:`partition_episodes`."""
    by_project: dict[str | None, datetime] = {}
    for row in rows:
        created = _parse(row.created_date)
        if created is None:
            continue
        current = by_project.get(row.project)
        if current is None or created > current:
            by_project[row.project] = created
    return {
        row.uuid
        for row in rows
        if (created := _parse(row.created_date)) is not None
        and by_project.get(row.project) == created
    }


def partition_episodes(
    rows: Sequence[EpisodeMetadata],
    *,
    days: int = 30,
    now: datetime | None = None,
) -> Partition:
    """Split one agent's live episodes into archive, decide, and never-touch."""
    now = now or datetime.now(timezone.utc)
    newest = _newest(rows)
    newest_overall = max(
        (_parse(row.created_date) for row in rows if _parse(row.created_date) is not None),
        default=None,
    )
    cutoff = now - timedelta(days=days)

    result = Partition()
    for row in rows:
        created = _parse(row.created_date)
        modified = _parse(row.modified_date) or created

        if created is None or modified is None:
            result.protected.append(ProtectedRow(record=row, reason=UNDATED))
            continue
        if row.uuid in newest:
            # The newest per project is what a coding awakening loads for that project;
            # the newest overall is what a project-blind chat awakening loads. The
            # second is always a member of the first, and is named anyway so the reason
            # reported to a caller matches the load path it protects.
            reason = (
                NEWEST_OVERALL
                if newest_overall is not None and created == newest_overall
                else NEWEST_OF_PROJECT
            )
            result.protected.append(ProtectedRow(record=row, reason=reason))
            continue
        if FINISHED_TAG in row.tags:
            result.auto.append(row)
        elif modified < cutoff:
            result.ask.append(row)
    return result
