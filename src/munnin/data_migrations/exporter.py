"""memory store -> markdown-memory-tree exporter (the importer's inverse).

The importer only ever adds and updates, so a record the store holds and markdown lacks
survives an upsert but is **dropped by a ``--purge`` reimport**. This module finds those
records (:func:`compare`) and gives them a markdown home (:func:`export_db_only`), reading
each body from the store so nothing is retyped.

Scope: episodes and knowledge, which own files. The always-load layers (identity,
reasoning, emotional) live inside ``agent-core-memory.md`` and are not written here.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from pathlib import Path

from munnin.data_entities.identity import Account
from munnin.data_migrations.importer import import_fleet
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository

# The index's own glyphs, built from code points so this source stays ASCII: a day header
# opens with the calendar and the interactions-list marker is the open folder. They are
# cosmetic to the importer, which reads the index by link and date, not by glyph.
_CAL = "\U0001f4c5"
_FOLDER = "\U0001f4c2"

# A day-group header in the interactions list: the glyph, a date, a colon, nothing else.
_GROUP = re.compile(r"^\W*\d{4}-\d{2}-\d{2}:\s*$")

_FIELDS = (
    "uuid",
    "agent_id",
    "record_type",
    "title",
    "project",
    "tags",
    "archived_date",
    "created_date",
    "full_content",
)


# --- reading both sides ---


def _records(db: Path | str, user_id: str) -> dict[str, dict[str, str | None]]:
    """Every memory record for the tenant, keyed by uuid. Raw SQLite rather than the
    repository: the exporter is a migration tool reading a dump, not a service read."""
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            f"select {', '.join(_FIELDS)} from memory_record where user_id = ?", (user_id,)
        )
        return {row[0]: dict(zip(_FIELDS, row)) for row in rows}
    finally:
        conn.close()


def store_records(db: Path | str, *, user_id: str = "alvi") -> dict[str, dict[str, str | None]]:
    """Every record the store holds, keyed by uuid."""
    return _records(db, user_id)


def markdown_records(
    store: Path | str, *, user_id: str = "alvi", scratch_db: Path | str | None = None
) -> dict[str, dict[str, str | None]]:
    """What a ``--purge`` reimport of the markdown tree would produce, keyed by uuid.

    Built by running the real importer into a scratch database, so the comparison is
    against the importer's own reading of the tree, not a second interpretation of it."""
    scratch = (
        Path(scratch_db)
        if scratch_db
        else (Path(tempfile.mkdtemp(prefix="munnin-export-")) / "scratch.db")
    )
    if scratch.exists():
        scratch.unlink()
    SqliteIdentityRepository(scratch).ensure_account(Account(user_id=user_id))
    import_fleet(SqliteMemoryRepository(scratch, user_id=user_id), Path(store))
    return _records(scratch, user_id)


def compare(db: Path | str, store: Path | str, *, user_id: str = "alvi") -> tuple[dict, dict, dict]:
    """``(db_only, markdown_only, changed)``, each keyed by uuid.

    ``db_only`` is what a ``--purge`` reimport would drop; ``markdown_only`` is what it
    would add; ``changed`` is a record in both whose columns differ."""
    stored = store_records(db, user_id=user_id)
    derived = markdown_records(store, user_id=user_id)
    return (
        {u: stored[u] for u in stored.keys() - derived.keys()},
        {u: derived[u] for u in derived.keys() - stored.keys()},
        {
            u: (stored[u], derived[u])
            for u in stored.keys() & derived.keys()
            if stored[u] != derived[u]
        },
    )


# --- writing the markdown side ---


def _tags(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _frontmatter(project: str | None, tags: list[str], created: str | None = None) -> str:
    lines = ["---"]
    if project:
        lines.append(f'project: "{project}"')
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    if created:
        lines.append(f'created: "{created}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _read_raw(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write_raw(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _index_path(store: Path | str, agent_id: str) -> Path:
    return Path(store) / f"agent-{agent_id}" / "agent-memory-index.md"


def _insert_after(text: str, needle: str, block: list[str]) -> str:
    """Insert ``block`` right after the first line containing ``needle``. The file's own
    line ending is preserved, so an edit never re-encodes the whole index."""
    sep = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(sep)
    for i, line in enumerate(lines):
        if needle in line:
            lines[i + 1 : i + 1] = block
            return sep.join(lines)
    raise KeyError(f"index anchor not found: {needle!r}")


def _insert_day(text: str, day: str, block: list[str]) -> str:
    """Add bullets to ``day``'s group in the interactions list, creating the group above
    the newest existing one when absent (newest first is the store's order)."""
    sep = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(sep)
    header = f"{_FOLDER} {day}:"
    for i, line in enumerate(lines):
        if line.strip() == header:
            lines[i + 1 : i + 1] = block
            return sep.join(lines)
    for i, line in enumerate(lines):
        if _GROUP.match(line.strip()):
            lines[i:i] = [header, *block, ""]
            return sep.join(lines)
    raise KeyError("no interactions-list group to insert before")


def export_episode(
    store: Path | str,
    agent_id: str,
    title: str,
    *,
    body: str,
    project: str | None = None,
    tags: list[str] | None = None,
    day: str,
) -> Path:
    """Write one episode as its own file. The filename is the title (episode titles carry
    no date prefix) and the body is the stored content, so a reimport rebuilds the record."""
    path = Path(store) / f"agent-{agent_id}" / "episodes" / f"{title}.md"
    _write_raw(
        path,
        _frontmatter(project, tags or [])
        + f"# Agent {agent_id} - {title}\n\n## {_CAL} Interactions List\n{_FOLDER} {day}:\n\n"
        + body.rstrip()
        + "\n",
    )
    return path


def add_episode_index(
    store: Path | str, agent_id: str, *, filename: str, summary: str, day: str
) -> None:
    """Add ``- [filename](episodes/filename) - summary`` under ``day``. Indexed is active;
    an unindexed file would import archived, so this is what keeps the record hot."""
    index = _index_path(store, agent_id)
    text = _read_raw(index)
    bullet = f"- [{filename}](episodes/{filename}) - {summary}"
    _write_raw(index, _insert_day(text, day, [bullet]))


def export_knowledge(
    store: Path | str,
    agent_id: str,
    relpath: str,
    *,
    body: str,
    tags: list[str] | None = None,
    created: str | None = None,
) -> Path:
    """Write one knowledge file at ``knowledge-base/<relpath>``, the path the index links."""
    path = Path(store) / f"agent-{agent_id}" / "knowledge-base" / relpath
    _write_raw(path, _frontmatter(None, tags or [], created) + body.rstrip() + "\n")
    return path


def add_knowledge_index(
    store: Path | str, agent_id: str, *, title: str, relpath: str, summary: str, anchor: str
) -> None:
    """Add a knowledge bullet after the index line containing ``anchor`` (the last existing
    entry of the section it belongs to). The section is a judgment, so it is an argument."""
    index = _index_path(store, agent_id)
    text = _read_raw(index)
    bullet = f"- **[{title}]({relpath})** - {summary}"
    _write_raw(index, _insert_after(text, anchor, [bullet]))


def export_db_only(
    db: Path | str,
    store: Path | str,
    *,
    user_id: str = "alvi",
    knowledge_anchor: str | None = None,
    summary: dict[str, str] | None = None,
) -> list[Path]:
    """Materialise the episode and knowledge records the markdown tree lacks.

    Episodes are placed deterministically (file plus index group). Knowledge needs an
    ``knowledge_anchor`` because which index section a knowledge entry belongs to is a
    judgment no code can make, and ``summary`` may override the index one-liner per title.
    A record type with no file of its own raises, so a loss is never silent."""
    db_only, _markdown_only, _changed = compare(db, store, user_id=user_id)
    summary = summary or {}
    written: list[Path] = []
    ordered = sorted(
        db_only.values(),
        key=lambda r: (r["agent_id"] or "", r["record_type"] or "", r["title"] or ""),
    )
    for rec in ordered:
        agent_id, rtype, title = rec["agent_id"], rec["record_type"], rec["title"]
        created = (rec["created_date"] or "")[:10]
        if rtype == "episode":
            path = export_episode(
                store,
                agent_id,
                title,
                body=rec["full_content"],
                project=rec["project"],
                tags=_tags(rec["tags"]),
                day=created or "1970-01-01",
            )
            add_episode_index(
                store,
                agent_id,
                filename=f"{title}.md",
                summary=summary.get(title, title),
                day=created or "1970-01-01",
            )
        elif rtype == "knowledge":
            if not knowledge_anchor:
                raise ValueError(
                    "knowledge needs --knowledge-anchor: which section it belongs to is a judgment"
                )
            relpath = f"{title.lower().replace(' ', '-')}.md"
            path = export_knowledge(
                store,
                agent_id,
                relpath,
                body=rec["full_content"],
                tags=_tags(rec["tags"]),
                created=created,
            )
            add_knowledge_index(
                store,
                agent_id,
                title=title,
                relpath=relpath,
                summary=summary.get(title, title),
                anchor=knowledge_anchor,
            )
        else:
            raise ValueError(f"cannot export a {rtype!r} record: it has no file of its own")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Store -> markdown exporter (the importer's inverse)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("compare", "report what a --purge reimport would drop, add or change"),
        ("export", "materialise the records markdown lacks"),
    ):
        cmd = sub.add_parser(name, help=helptext)
        cmd.add_argument("--db", required=True)
        cmd.add_argument("--store", required=True)
        cmd.add_argument("--user-id", default="alvi")
        if name == "export":
            cmd.add_argument("--knowledge-anchor", default=None)
    args = parser.parse_args(argv)

    if args.command == "compare":
        db_only, markdown_only, changed = compare(args.db, args.store, user_id=args.user_id)
        print(
            f"db-only: {len(db_only)}  markdown-only: {len(markdown_only)}  changed: {len(changed)}"
        )
        for rec in sorted(
            db_only.values(), key=lambda r: (r["agent_id"] or "", r["record_type"] or "")
        ):
            print(f"  db-only  {rec['agent_id']} {rec['record_type']} :: {rec['title']}")
        for rec in sorted(
            markdown_only.values(), key=lambda r: (r["agent_id"] or "", r["record_type"] or "")
        ):
            print(f"  add      {rec['agent_id']} {rec['record_type']} :: {rec['title']}")
        return

    written = export_db_only(
        args.db, args.store, user_id=args.user_id, knowledge_anchor=args.knowledge_anchor
    )
    print(f"wrote {len(written)} file(s)")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()
