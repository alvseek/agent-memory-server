-- Valaskjalf/memory schema — one uniform record per item (ADR-013 D5, arch §3).
-- Applied on repository init (idempotent). FTS5 external-content keeps the index
-- without duplicating the blob; browse index serves the metadata reads.

CREATE TABLE IF NOT EXISTS memory_record (
  id            INTEGER PRIMARY KEY,            -- internal rowid; storage + FTS5 link (never leaves the store)
  uuid          TEXT    NOT NULL UNIQUE,        -- global/portable identity; the idempotency key
  user_id       TEXT    NOT NULL,               -- tenant; stamped server-side, never from caller
  agent_id      TEXT    NOT NULL,               -- agent domain (kebab) OR the '__shared__' sentinel
  record_type   TEXT    NOT NULL,               -- episode | knowledge | identity | reasoning | emotional
  project       TEXT,                           -- nullable; set on project-scoped items
  title         TEXT,                           -- index line: summary / topic / doc-name
  tags          TEXT,                           -- JSON array (stored as text)
  created_date  TEXT    NOT NULL,
  modified_date TEXT    NOT NULL,               -- = created on insert; bumped on edit (staleness signal)
  archived_date TEXT,                           -- non-NULL = out of hot index, still searchable
  deleted_date  TEXT,                           -- non-NULL = tombstone, excluded from all reads
  full_content  TEXT                            -- markdown item body; last column (overflow-friendly)
);

-- Browse/metadata index (the awakening + load reads).
CREATE INDEX IF NOT EXISTS idx_memory_browse
  ON memory_record (user_id, agent_id, record_type, project, created_date);

-- Full-text index (external-content) over body + title + tags. Replaces cross-repo grep.
-- External-content mode indexes without duplicating; search never scans the blobs.
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  full_content,
  title,
  tags,
  content='memory_record',
  content_rowid='id'
);

-- Triggers keep memory_fts in sync with memory_record.
CREATE TRIGGER IF NOT EXISTS memory_record_ai AFTER INSERT ON memory_record BEGIN
  INSERT INTO memory_fts(rowid, full_content, title, tags)
  VALUES (new.id, new.full_content, new.title, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memory_record_ad AFTER DELETE ON memory_record BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, full_content, title, tags)
  VALUES ('delete', old.id, old.full_content, old.title, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memory_record_au AFTER UPDATE ON memory_record BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, full_content, title, tags)
  VALUES ('delete', old.id, old.full_content, old.title, old.tags);
  INSERT INTO memory_fts(rowid, full_content, title, tags)
  VALUES (new.id, new.full_content, new.title, new.tags);
END;
