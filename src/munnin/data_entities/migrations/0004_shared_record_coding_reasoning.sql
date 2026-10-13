-- 0004 — widen shared_record's CHECK to admit 'coding_reasoning' (the coding-reasoning lane).
--
-- SQLite cannot ALTER a CHECK, so the table is rebuilt, the same dance 0002 performed for
-- 'ras'. Dropping it also drops its indexes and its FTS triggers, so all of those are
-- recreated here, and the external-content FTS index is rebuilt from the new table. The
-- primary key `id` is carried across so the FTS rowid link survives the swap.
--
-- `content_summary` is carried too. It was added by 0003, after 0002's rebuild, so a copy
-- of 0002's column list verbatim would drop it — the rebuild must name every column the
-- table has *now*, not the ones it had when 0002 was written.

CREATE TABLE shared_record__new (
  id              INTEGER PRIMARY KEY,    -- internal rowid; storage + FTS5 link (never leaves the store)
  uuid            TEXT    NOT NULL UNIQUE,-- global/portable identity; the idempotency key
  user_id         TEXT    NOT NULL,
  record_type     TEXT    NOT NULL CHECK (record_type IN ('reasoning','coding_reasoning','knowledge','ras','user_profile')),
  project         TEXT,                   -- reserved for Hermod's project scope; unused by Munnin
  title           TEXT,
  tags            TEXT,                   -- JSON array (stored as text)
  created_date    TEXT    NOT NULL,
  modified_date   TEXT    NOT NULL,
  archived_date   TEXT,                   -- non-NULL = out of hot index, still searchable
  deleted_date    TEXT,                   -- non-NULL = tombstone, excluded from all reads
  full_content    TEXT,                   -- markdown item body
  content_summary TEXT                    -- authored one-line summary (added by 0003)
);

INSERT INTO shared_record__new
  (id, uuid, user_id, record_type, project, title, tags,
   created_date, modified_date, archived_date, deleted_date, full_content, content_summary)
SELECT
   id, uuid, user_id, record_type, project, title, tags,
   created_date, modified_date, archived_date, deleted_date, full_content, content_summary
FROM shared_record;

DROP TABLE shared_record;
ALTER TABLE shared_record__new RENAME TO shared_record;

CREATE INDEX IF NOT EXISTS idx_shared_browse
  ON shared_record (user_id, record_type, project, created_date);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_user_profile_per_tenant
  ON shared_record (user_id)
  WHERE record_type = 'user_profile' AND deleted_date IS NULL;

CREATE TRIGGER IF NOT EXISTS shared_record_ai AFTER INSERT ON shared_record BEGIN
  INSERT INTO shared_fts(rowid, full_content, title, tags)
  VALUES (new.id, new.full_content, new.title, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS shared_record_ad AFTER DELETE ON shared_record BEGIN
  INSERT INTO shared_fts(shared_fts, rowid, full_content, title, tags)
  VALUES ('delete', old.id, old.full_content, old.title, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS shared_record_au AFTER UPDATE ON shared_record BEGIN
  INSERT INTO shared_fts(shared_fts, rowid, full_content, title, tags)
  VALUES ('delete', old.id, old.full_content, old.title, old.tags);
  INSERT INTO shared_fts(rowid, full_content, title, tags)
  VALUES (new.id, new.full_content, new.title, new.tags);
END;

INSERT INTO shared_fts(shared_fts) VALUES('rebuild');
