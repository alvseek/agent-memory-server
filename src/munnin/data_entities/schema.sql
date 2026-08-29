-- Valaskjalf/memory schema — five tables (arch §3; amends ADR-013 D5 for entities).
--
--   account        the tenant. A person exists here because they have a row.
--   user_identity  which issuer-and-subject pair resolves to which tenant.
--   agent          the entity. An agent exists because it has a row.
--   shared_record  fleet memory, owned by no agent.
--   memory_record  shared_record + agent_id, with the owner enforced by a foreign key.
--
-- Applied on repository init (idempotent). FTS5 external-content indexes each memory
-- table without duplicating its blob; a browse index serves the metadata reads.
-- NOTE: every foreign key below only fires when `PRAGMA foreign_keys = ON` is set on the
-- connection — SQLite defaults it OFF, so each repository sets it per connection.

-- The tenant. `user_id` is ours forever and is never an issuer's subject: a subject is
-- only unique within the issuer that minted it, so storing one here would orphan every
-- record the day the issuer changes. The column keeps the name `user_id` because three
-- tables below already use it and not rewriting them is the entire point of this design.
-- `email` is a label and a matching hint, never a key — OpenID Connect permits an issuer
-- to reassign an address to a different person, so matching on it can hand one person's
-- memory to another.
CREATE TABLE IF NOT EXISTS account (
  user_id      TEXT PRIMARY KEY,
  display_name TEXT,
  email        TEXT,
  created_date TEXT NOT NULL
);

-- Issuer-to-tenant mapping, keyed on the pair OpenID Connect guarantees to be stable.
-- Two issuers may map to one person at the same time, which is what makes changing
-- issuers an insert here rather than a rewrite of every memory record.
CREATE TABLE IF NOT EXISTS user_identity (
  iss         TEXT NOT NULL,            -- the authorization server that minted the token
  sub         TEXT NOT NULL,            -- its identifier for the person; meaningless elsewhere
  user_id     TEXT NOT NULL,
  linked_date TEXT NOT NULL,
  PRIMARY KEY (iss, sub),
  FOREIGN KEY (user_id) REFERENCES account(user_id)
);

-- The agent entity. No lifecycle columns: nothing in the system retires an agent.
CREATE TABLE IF NOT EXISTS agent (
  user_id      TEXT NOT NULL,           -- tenant; stamped server-side, never from caller
  agent_id     TEXT NOT NULL,           -- kebab domain; equals the agent-[domain]/ folder name
  name         TEXT,                    -- **Name** from the identity document
  role         TEXT,                    -- **Role**, falling back to **Main Purpose**
  uuid         TEXT,                    -- the agent's own "digital soul" id — content, never a key
  created_date TEXT NOT NULL,
  PRIMARY KEY (user_id, agent_id),
  FOREIGN KEY (user_id) REFERENCES account(user_id)
);

-- Fleet-shared memory. No agent_id at all — this memory has no owner, which is why it
-- cannot live in memory_record without weakening that table's foreign key. The CHECK
-- enforces what used to be convention only: shared memory is reasoning, knowledge, and
-- the user profile — never an episode, an identity or an emotional moment, all of which
-- belong to some particular agent.
CREATE TABLE IF NOT EXISTS shared_record (
  id            INTEGER PRIMARY KEY,    -- internal rowid; storage + FTS5 link (never leaves the store)
  uuid          TEXT    NOT NULL UNIQUE,-- global/portable identity; the idempotency key
  user_id       TEXT    NOT NULL,
  record_type   TEXT    NOT NULL CHECK (record_type IN ('reasoning','knowledge','user_profile')),
  project       TEXT,                   -- reserved for Hermod's project scope; unused by Munnin
  title         TEXT,
  tags          TEXT,                   -- JSON array (stored as text)
  created_date  TEXT    NOT NULL,
  modified_date TEXT    NOT NULL,
  archived_date TEXT,                   -- non-NULL = out of hot index, still searchable
  deleted_date  TEXT,                   -- non-NULL = tombstone, excluded from all reads
  full_content  TEXT                    -- markdown item body; last column (overflow-friendly)
);

-- Agent-scoped memory = shared_record + agent_id. The composite foreign key means a
-- memory item can never name an owner that does not exist, and cannot reach across tenants.
CREATE TABLE IF NOT EXISTS memory_record (
  id            INTEGER PRIMARY KEY,
  uuid          TEXT    NOT NULL UNIQUE,
  user_id       TEXT    NOT NULL,
  agent_id      TEXT    NOT NULL,       -- always a real agent; no sentinel value exists
  record_type   TEXT    NOT NULL,       -- episode | knowledge | identity | reasoning | emotional
  project       TEXT,
  title         TEXT,
  tags          TEXT,
  created_date  TEXT    NOT NULL,
  modified_date TEXT    NOT NULL,
  archived_date TEXT,
  deleted_date  TEXT,
  full_content  TEXT,
  FOREIGN KEY (user_id, agent_id) REFERENCES agent(user_id, agent_id)
);

-- Browse/metadata indexes (the awakening + load reads).
CREATE INDEX IF NOT EXISTS idx_memory_browse
  ON memory_record (user_id, agent_id, record_type, project, created_date);
CREATE INDEX IF NOT EXISTS idx_shared_browse
  ON shared_record (user_id, record_type, project, created_date);

-- Exactly one user profile per tenant. The CHECK above says a profile MAY live in this
-- table; this says only one may. `awaken` answers "has anyone been asked yet" with the
-- presence of a row, so a second profile would satisfy that question with whichever row
-- came first and leave the other invisible — the wrong answer, arrived at silently.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_user_profile_per_tenant
  ON shared_record (user_id)
  WHERE record_type = 'user_profile' AND deleted_date IS NULL;

-- Full-text indexes (external-content) over body + title + tags — one per memory table.
-- External-content mode indexes without duplicating; search never scans the blobs.
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  full_content,
  title,
  tags,
  content='memory_record',
  content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS shared_fts USING fts5(
  full_content,
  title,
  tags,
  content='shared_record',
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

-- The same three, for shared_record / shared_fts.
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
