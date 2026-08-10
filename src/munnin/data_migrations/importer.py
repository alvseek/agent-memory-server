"""One-time markdown-memory-tree → Valaskjalf/memory importer (SP-1 subset).

SP-1 imports a single agent's **active** memory (archived_date = NULL) — enough to
awaken it from the DB. Full-fleet + archived-episode import + the archived-detection
rule land in SP-4. Idempotent: deterministic uuids mean a re-run upserts, never dups.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from pathlib import Path

from munnin.configuration.config import load_config
from munnin.data_entities.memory_record import SHARED_AGENT_ID, MemoryRecord, RecordType
from munnin.data_migrations import markdown_parser as P
from munnin.data_repositories.memory_repository import MemoryRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository
from munnin.logger.logger import get_logger

_log = get_logger("importer")


def _to_record(item: P.ParsedItem, agent_id: str, record_type: RecordType) -> MemoryRecord:
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
    )


def import_agent(repo: MemoryRepository, source_root: Path | str, agent_id: str) -> dict[str, int]:
    """Import ``agent_id``'s active memory + the shared always-load layer. Returns
    a count map keyed ``"<agent_id>/<record_type>"``."""
    root = Path(source_root)
    agent_dir = root / f"agent-{agent_id}"
    counts: Counter[str] = Counter()

    def add(item: P.ParsedItem, aid: str, rtype: RecordType) -> None:
        repo.insert(_to_record(item, aid, rtype))
        counts[f"{aid}/{rtype.value}"] += 1

    # layer ii — agent identity (agent-core-memory.md)
    core = (agent_dir / "agent-core-memory.md").read_text(encoding="utf-8")
    ac = P.parse_agent_core(core)
    for it in ac["identity"]:
        add(it, agent_id, RecordType.identity)
    for it in ac["reasoning"]:
        add(it, agent_id, RecordType.reasoning)
    for it in ac["emotional"]:
        add(it, agent_id, RecordType.emotional)

    # layer i — shared always-load (loaded by every agent)
    sr = (root / "shared-memory" / "core-reasoning-memory.md").read_text(encoding="utf-8")
    for it in P.parse_shared_reasoning(sr):
        add(it, SHARED_AGENT_ID, RecordType.reasoning)
    sk = (root / "shared-memory" / "core-knowledge-memory.md").read_text(encoding="utf-8")
    for it in P.parse_shared_knowledge(sk):
        add(it, SHARED_AGENT_ID, RecordType.knowledge)

    # layer iii — domain knowledge index + active episodes
    index = (agent_dir / "agent-memory-index.md").read_text(encoding="utf-8")
    for it in P.parse_knowledge_index(index):
        add(it, agent_id, RecordType.knowledge)
    for ep in P.parse_active_episodes(index):
        ep_path = agent_dir / ep["file"]
        if not ep_path.exists():
            _log.warning("active episode missing, skipping: %s", ep_path)
            continue
        body = ep_path.read_text(encoding="utf-8")
        item = P.ParsedItem(
            title=Path(ep["file"]).stem,
            body=body,
            key=ep["file"],
            date=ep["date"] or None,
        )
        add(item, agent_id, RecordType.episode)

    _log.info("import complete for %s: %s", agent_id, dict(counts))
    return dict(counts)


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description="Import an agent's markdown memory into the DB.")
    default_source = os.getenv(
        "MUNNIN_IMPORT_SOURCE", str(Path.home() / ".claude" / "@agent-memory")
    )
    parser.add_argument(
        "--source",
        default=default_source,
        help="root of the @agent-memory markdown tree",
    )
    parser.add_argument("--agent", default="meta", help="agent domain to import")
    parser.add_argument("--db", default=str(config.db_path), help="target SQLite db path")
    args = parser.parse_args()

    repo = SqliteMemoryRepository(Path(args.db), user_id=config.user_id)
    counts = import_agent(repo, args.source, args.agent)
    total = sum(counts.values())
    print(f"imported {total} records for '{args.agent}' from {args.source}")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")


if __name__ == "__main__":
    main()
