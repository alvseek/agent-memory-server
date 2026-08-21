"""markdown-memory-tree → Valaskjalf/memory importer.

Two passes: the ``agent`` rows first, then the memory that points at them — the foreign
key makes that order mandatory, not stylistic. Full-fleet, all 5 record types, the
fleet-shared layer imported **once** into its own table, and BOTH **active** +
**archived** episodes/knowledge — where *archived* = a file **absent from the agent
index** (``archived_date`` set; excluded from awaken's hot index, still searchable).
Real file bodies. Idempotent: deterministic ``uuid5`` → re-run upserts, never dups.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from pathlib import Path

from munnin.configuration.config import load_config
from munnin.data_entities.memory_record import Agent, MemoryRecord, RecordType, SharedRecord
from munnin.data_migrations import markdown_parser as P
from munnin.data_repositories.memory_repository import MemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from munnin.logger.logger import get_logger

_log = get_logger("importer")

# Namespace token for fleet-shared record uuids. A fixed word rather than an agent id,
# because these records have no agent — and `shared` is a reserved domain, so it can
# never collide with a real one.
_SHARED_UUID_SCOPE = "shared"


class ImportAborted(RuntimeError):
    """Pass 1 found an agent folder whose identity will not parse.

    Raised **before anything is written**, so a run either imports the whole fleet or
    leaves the database exactly as it found it. The alternative — skipping the bad
    folder and carrying on — is what let five agents import as hollow shells for months
    while every run reported success."""


# Non-null sentinel for an archived file with no parseable date (rare — nearly all
# archived episodes carry a YYYY-MM-DD filename prefix). The value only needs to be
# non-null so the row drops out of the hot awaken index.
_ARCHIVED_FALLBACK = "1970-01-01"


def _read(path: Path) -> str:
    """Read markdown tolerant of legacy encodings — utf-8, then cp1252 (Windows smart
    quotes etc.), never crashing on a stray byte. One known cp1252 file exists in the
    real fleet (a mojibake artifact tracked as a separate source-repair tech debt)."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _to_record(
    item: P.ParsedItem,
    agent_id: str,
    record_type: RecordType,
    *,
    archived_date: str | None = None,
) -> MemoryRecord:
    uid = item.uuid or P.stable_uuid(agent_id, record_type.value, item.key)
    return MemoryRecord(
        uuid=uid,
        user_id="",  # repo stamps server-side
        agent_id=agent_id,
        record_type=record_type,
        full_content=item.body,
        title=item.title,
        tags=item.tags,
        created_date=item.date,  # None → repo defaults (undated identity/knowledge)
        archived_date=archived_date,
    )


def _to_shared_record(item: P.ParsedItem, record_type: RecordType) -> SharedRecord:
    """The fleet twin of ``_to_record`` — same mapping, no owner."""
    uid = item.uuid or P.stable_uuid(_SHARED_UUID_SCOPE, record_type.value, item.key)
    return SharedRecord(
        uuid=uid,
        user_id="",  # repo stamps server-side
        record_type=record_type,
        full_content=item.body,
        title=item.title,
        tags=item.tags,
        created_date=item.date,
    )


def _parse_agent_entity(agent_dir: Path, agent_id: str) -> Agent | str:
    """One folder → an ``Agent``, or a one-line reason it cannot be read.

    Returning the reason rather than raising is what lets pass 1 report **every** bad
    folder in one go; a raise would surface the first and hide the rest."""
    core_path = agent_dir / "agent-core-memory.md"
    if not core_path.is_file():
        return f"{agent_id}: no agent-core-memory.md"
    identity = P.parse_agent_core(_read(core_path))["identity"]
    if not identity:
        return f"{agent_id}: no identity section parsed from agent-core-memory.md"
    fields = P.parse_identity_fields([it.body for it in identity])
    if not fields["name"]:
        return f"{agent_id}: identity has no **Name** line"
    return Agent(
        user_id="",  # repo stamps server-side
        agent_id=agent_id,
        name=fields["name"],
        role=fields["role"],
        uuid=fields["uuid"],
    )


def parse_agent(source_root: Path | str, agent_id: str) -> Agent:
    """Read one agent's entity, raising ``ImportAborted`` if its identity is unusable."""
    result = _parse_agent_entity(Path(source_root) / f"agent-{agent_id}", agent_id)
    if isinstance(result, str):
        raise ImportAborted(f"nothing was imported — {result}")
    return result


def parse_fleet_agents(source_root: Path | str) -> list[Agent]:
    """**Pass 1** — read every ``agent-*/`` folder into an ``Agent``, or raise.

    Nothing is written here and nothing is written by the caller until this returns, so
    a fleet with one unreadable identity fails **up front** rather than half-way through.
    Every problem found is reported together: reporting them one run at a time would be a
    poor trade for a check that costs one pass over a few dozen small files."""
    root = Path(source_root)
    agents: list[Agent] = []
    problems: list[str] = []
    for agent_dir in sorted(root.glob("agent-*")):
        if not agent_dir.is_dir():
            continue
        result = _parse_agent_entity(agent_dir, agent_dir.name[len("agent-") :])
        if isinstance(result, str):
            problems.append(result)
        else:
            agents.append(result)
    if problems:
        raise ImportAborted(
            f"{len(problems)} agent folder(s) have no usable identity; nothing was imported:\n  "
            + "\n  ".join(problems)
        )
    _log.info("pass 1: %d agents parsed", len(agents))
    return agents


def import_shared(repo: MemoryRepository, source_root: Path | str) -> dict[str, int]:
    """Import the fleet-shared always-load layer (core-reasoning, core-knowledge, and the
    user profile) into ``shared_record``. Call **once** per DB — ``import_fleet`` does.
    Returns a count map.

    Needs no agent to exist: this memory belongs to the fleet, which is the whole reason
    it stopped living under a sentinel owner.

    Reasoning and knowledge are framework invariants and their absence is a broken store,
    so they are read unguarded. The profile is not: it is a fact about a person who may
    simply not have been asked yet, so a missing file skips quietly and leaves that record
    to the first-run bootstrap at awakening."""
    root = Path(source_root)
    counts: Counter[str] = Counter()
    sr = _read(root / "shared-memory" / "core-reasoning-memory.md")
    for it in P.parse_shared_reasoning(sr):
        repo.insert_shared(_to_shared_record(it, RecordType.reasoning))
        counts[f"{_SHARED_UUID_SCOPE}/reasoning"] += 1
    sk = _read(root / "shared-memory" / "core-knowledge-memory.md")
    for it in P.parse_shared_knowledge(sk):
        repo.insert_shared(_to_shared_record(it, RecordType.knowledge))
        counts[f"{_SHARED_UUID_SCOPE}/knowledge"] += 1
    profile_path = root / "shared-memory" / "user-profile.md"
    if profile_path.exists():
        for it in P.parse_shared_profile(_read(profile_path)):
            repo.insert_shared(_to_shared_record(it, RecordType.user_profile))
            counts[f"{_SHARED_UUID_SCOPE}/user_profile"] += 1
    else:
        _log.info("import shared: no user-profile.md — the first-run ask owns that record")
    _log.info("import shared: %s", dict(counts))
    return dict(counts)


def _import_episodes(
    repo: MemoryRepository, agent_dir: Path, agent_id: str, counts: Counter[str]
) -> None:
    """Every ``episodes/*.md`` → a record. In the index = active (archived_date NULL);
    absent from the index = archived (archived_date set). Body = the real file."""
    ep_dir = agent_dir / "episodes"
    if not ep_dir.is_dir():
        return
    index_path = agent_dir / "agent-memory-index.md"
    index = _read(index_path) if index_path.exists() else ""
    active = {ep["file"]: ep["date"] for ep in P.parse_active_episodes(index)}
    for ep_path in sorted(ep_dir.glob("*.md")):
        rel = f"episodes/{ep_path.name}"
        body = _read(ep_path)
        if rel in active:
            date = active[rel] or P.date_from_filename(ep_path.name)
            archived = None
        else:
            date = P.date_from_filename(ep_path.name)
            archived = date or _ARCHIVED_FALLBACK
        item = P.ParsedItem(title=ep_path.stem, body=body, key=rel, date=date)
        repo.insert(_to_record(item, agent_id, RecordType.episode, archived_date=archived))
        counts[f"{agent_id}/episode"] += 1


def _import_knowledge(
    repo: MemoryRepository, agent_dir: Path, agent_id: str, counts: Counter[str]
) -> None:
    """Indexed knowledge = active, imported with its **real file body** (fallback to the
    index description if the file is missing). Unindexed non-project files = archived.
    ``knowledge-base/`` subdirs holding a ``context-index.md`` are project-scoped → Hermod,
    skipped."""
    index_path = agent_dir / "agent-memory-index.md"
    index = _read(index_path) if index_path.exists() else ""
    active_items = P.parse_knowledge_index(index)
    active_paths = {it.key for it in active_items}
    kb = agent_dir / "knowledge-base"

    # active — indexed, real body (fallback to the index description)
    for it in active_items:
        fpath = kb / it.key
        body = _read(fpath) if fpath.is_file() else it.body
        item = P.ParsedItem(title=it.title, body=body, key=it.key, tags=it.tags)
        repo.insert(_to_record(item, agent_id, RecordType.knowledge))
        counts[f"{agent_id}/knowledge"] += 1

    if not kb.is_dir():
        return
    # archived — unindexed, non-project files
    project_dirs = {d for d in kb.iterdir() if d.is_dir() and (d / "context-index.md").is_file()}
    for f in sorted(kb.rglob("*.md")):
        if f.name == "context-index.md":
            continue
        if any(pd in f.parents for pd in project_dirs):
            continue  # project-scoped → Hermod / Valaskjalf/project
        rel = f.relative_to(kb).as_posix()
        if rel in active_paths:
            continue  # already imported as active
        body = _read(f)
        date = P.date_from_filename(f.name)
        item = P.ParsedItem(title=P.first_heading(body) or f.stem, body=body, key=rel, date=date)
        archived = date or _ARCHIVED_FALLBACK
        repo.insert(_to_record(item, agent_id, RecordType.knowledge, archived_date=archived))
        counts[f"{agent_id}/knowledge"] += 1


def import_agent(repo: MemoryRepository, source_root: Path | str, agent_id: str) -> dict[str, int]:
    """Import ONE agent's own memory — identity/reasoning/emotional (whole) + knowledge +
    episodes (active AND archived). Does **not** import the shared layer (see
    ``import_shared``). Returns a count map keyed ``"<agent_id>/<record_type>"``."""
    root = Path(source_root)
    agent_dir = root / f"agent-{agent_id}"
    counts: Counter[str] = Counter()

    core_path = agent_dir / "agent-core-memory.md"
    if core_path.is_file():
        ac = P.parse_agent_core(_read(core_path))
        for rtype in (RecordType.identity, RecordType.reasoning, RecordType.emotional):
            for it in ac[rtype.value]:
                repo.insert(_to_record(it, agent_id, rtype))
                counts[f"{agent_id}/{rtype.value}"] += 1

    _import_knowledge(repo, agent_dir, agent_id, counts)
    _import_episodes(repo, agent_dir, agent_id, counts)
    _log.info("import complete for %s: %s", agent_id, dict(counts))
    return dict(counts)


def import_fleet(repo: MemoryRepository, source_root: Path | str) -> dict[str, int]:
    """Import the whole fleet in two passes.

    **Pass 1** parses every agent's identity and writes the ``agent`` rows; **pass 2**
    imports the memory that points at them. The order is not a preference — the foreign
    key means no memory can be written until its owner exists, so an import that tried
    to do both at once would fail on its first record.

    Pass 1 raises ``ImportAborted`` before writing anything if any folder's identity is
    unreadable, so the database is never left holding a partial fleet."""
    root = Path(source_root)
    agents = parse_fleet_agents(root)  # pass 1 — may raise, writes nothing
    for agent in agents:
        repo.upsert_agent(agent)

    totals: Counter[str] = Counter()
    totals.update(import_shared(repo, root))  # pass 2
    for agent in agents:
        totals.update(import_agent(repo, root, agent.agent_id))
    _log.info(
        "fleet import complete: %d agents, %d records", len(agents), sum(totals.values())
    )
    return dict(totals)


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description="Import markdown memory into the DB.")
    default_source = os.getenv(
        "MUNNIN_IMPORT_SOURCE", str(Path.home() / ".claude" / "@agent-memory")
    )
    parser.add_argument("--source", default=default_source, help="root of the markdown tree")
    parser.add_argument(
        "--agent", default=None, help="import a single agent domain (default: the whole fleet)"
    )
    parser.add_argument(
        "--all", action="store_true", help="import the whole fleet (the default)"
    )
    parser.add_argument("--db", default=str(config.db_path), help="target SQLite db path")
    args = parser.parse_args()

    repo = SqliteMemoryRepository(Path(args.db), user_id=config.user_id)
    if args.agent and not args.all:
        # Pass 1 for this one agent only — a sibling folder being unreadable is not a
        # reason to refuse an import that never touches it.
        repo.upsert_agent(parse_agent(args.source, args.agent))
        counts = dict(import_shared(repo, args.source))
        counts.update(import_agent(repo, args.source, args.agent))
        label = args.agent
    else:
        counts = import_fleet(repo, args.source)
        label = "fleet"

    total = sum(counts.values())
    print(f"imported {total} records ({label}) from {args.source}")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")


if __name__ == "__main__":
    main()
