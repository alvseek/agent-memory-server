"""The archive rule, tested with no database around it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from munnin.business_services.archive_rule import (
    FINISHED_TAG,
    NEWEST_OF_PROJECT,
    NEWEST_OVERALL,
    UNDATED,
    partition_episodes,
)
from munnin.data_entities.memory_record import EpisodeMetadata

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def _ep(
    uuid: str,
    *,
    project: str | None = "proj",
    created: str | None = "2026-01-01",
    modified: str | None = None,
    tags: list[str] | None = None,
) -> EpisodeMetadata:
    return EpisodeMetadata(
        uuid=uuid,
        agent_id="meta",
        project=project,
        title=f"{project}-theme-{uuid}",
        created_date=created,
        modified_date=modified if modified is not None else created,
        tags=tags or [],
    )


def _uuids(rows: list[EpisodeMetadata]) -> list[str]:
    return [r.uuid for r in rows]


def test_tagged_and_superseded_is_auto() -> None:
    old = _ep("old", created="2026-01-01", tags=[FINISHED_TAG])
    new = _ep("new", created="2026-10-01")
    part = partition_episodes([new, old], now=NOW)
    assert _uuids(part.auto) == ["old"]
    assert _uuids(part.ask) == []
    assert [p.record.uuid for p in part.protected] == ["new"]


def test_untagged_and_stale_is_asked() -> None:
    stale = _ep("stale", created="2026-01-01", modified="2026-01-02")
    fresh = _ep("fresh", created="2026-10-20")
    part = partition_episodes([fresh, stale], now=NOW)
    assert _uuids(part.ask) == ["stale"]
    assert _uuids(part.auto) == []


def test_untagged_and_recent_is_neither() -> None:
    recent = _ep("recent", created="2026-10-01", modified="2026-11-01")
    newest = _ep("newest", created="2026-10-20")
    part = partition_episodes([newest, recent], now=NOW)
    assert _uuids(part.auto) == []
    assert _uuids(part.ask) == []
    assert [p.record.uuid for p in part.protected] == ["newest"]


def test_newest_per_project_and_overall_carry_a_reason() -> None:
    a_old = _ep("a-old", project="a", created="2026-01-01")
    a_new = _ep("a-new", project="a", created="2026-02-01")
    b_new = _ep("b-new", project="b", created="2026-03-01")
    part = partition_episodes([a_old, a_new, b_new], now=NOW)
    reasons = {p.record.uuid: p.reason for p in part.protected}
    assert reasons["a-new"] == NEWEST_OF_PROJECT
    assert reasons["b-new"] == NEWEST_OVERALL
    assert "a-old" not in reasons


def test_a_tagged_newest_row_is_protected_not_auto() -> None:
    """A finished theme that is still the newest of its project must not be archived:
    that record is the only carry-forward the project has."""
    only = _ep("only", created="2026-01-01", tags=[FINISHED_TAG])
    part = partition_episodes([only], now=NOW)
    assert _uuids(part.auto) == []
    assert [p.record.uuid for p in part.protected] == ["only"]


def test_every_row_tied_at_the_newest_date_is_protected() -> None:
    """The store orders by ``(created_date, id)``, and the API exposes no ``id``, so a
    caller cannot tell two same-date rows apart. Protecting the whole tie is the only
    answer that cannot pick the wrong one."""
    one = _ep("one", created="2026-05-01")
    two = _ep("two", created="2026-05-01")
    older = _ep("older", created="2026-04-01")
    part = partition_episodes([one, two, older], now=NOW)
    assert sorted(p.record.uuid for p in part.protected) == ["one", "two"]


def test_project_none_is_its_own_group() -> None:
    """An unprojected episode is the continuity record for project-less work. It must be
    judged inside its own group, not against a project's dates."""
    unprojected = _ep("none", project=None, created="2026-05-01")
    projected = _ep("proj", project="a", created="2026-06-01")
    part = partition_episodes([unprojected, projected], now=NOW)
    reasons = {p.record.uuid: p.reason for p in part.protected}
    assert reasons["none"] == NEWEST_OF_PROJECT
    assert reasons["proj"] == NEWEST_OVERALL


def test_undated_rows_are_protected() -> None:
    undated = _ep("undated", created=None, modified=None, tags=[FINISHED_TAG])
    part = partition_episodes([undated], now=NOW)
    assert _uuids(part.auto) == []
    assert [p.reason for p in part.protected] == [UNDATED]


def test_the_age_boundary_is_strict() -> None:
    just_over = _ep("over", created="2026-01-01", modified=(NOW - timedelta(days=31)).isoformat())
    just_under = _ep("under", created="2026-01-01", modified=(NOW - timedelta(days=29)).isoformat())
    newest = _ep("newest", created="2026-10-20")
    part = partition_episodes([newest, just_over, just_under], now=NOW)
    assert _uuids(part.ask) == ["over"]


def test_mixed_date_shapes_compare_chronologically() -> None:
    """The store holds date-only values from the importer and ISO timestamps from the
    service. A lexical comparison would order them wrong across a year boundary."""
    later = datetime(2027, 6, 1, tzinfo=timezone.utc)
    date_only = _ep("date-only", created="2026-12-31")
    iso = _ep("iso", created="2026-01-01T00:00:00+00:00")
    newest = _ep("newest", created="2027-01-01T00:00:00+00:00")
    part = partition_episodes([date_only, iso, newest], now=later)
    assert [p.record.uuid for p in part.protected] == ["newest"]
    assert _uuids(part.ask) == ["date-only", "iso"]
