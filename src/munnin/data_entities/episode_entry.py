"""Format a new episode entry; previously stored headings are never restamped."""

from datetime import datetime, timezone

from munnin.data_entities.memory_record import MemoryRecord, RecordType, SharedRecord


def stamped_entry(agent_id: str, entry_title: str, body: str) -> str:
    title = entry_title.strip()
    if not title or entry_title.splitlines() != [entry_title]:
        raise ValueError("entry_title must be a nonblank single line")
    if not body.strip():
        raise ValueError("episode entry body must not be blank")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H.%M UTC")
    return f"### {stamp} - {title} (agent: {agent_id})\n\n{body}"


def prepend_entry(record: SharedRecord, entry_title: str, body: str) -> str:
    if not isinstance(record, MemoryRecord) or record.record_type != RecordType.episode:
        raise ValueError("entry target must be an agent-owned episode")
    entry = stamped_entry(record.agent_id, entry_title, body)
    return f"{entry}\n\n---\n\n{record.full_content}" if record.full_content else entry
