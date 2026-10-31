-- Tenant sharing: a grant, an invitation, and the selection a person is acting in.
--
-- The Postgres twin of `migrations/0005_tenant_sharing.sql`. Numbered 0004 because this
-- set is one migration behind on purpose: 0001 here was written at the final base shape
-- rather than replaying SQLite's table rebuilds, and `ras` was part of its CHECK from the
-- first day.
--
-- Dates stay TEXT (ISO-8601) to match the entity mapping and every other date column in
-- this schema, rather than introducing a timestamptz conversion on one table.

ALTER TABLE IF EXISTS account ADD COLUMN IF NOT EXISTS active_user_id TEXT;

-- Access to a tenant that is not your own. Your own tenant needs no row: ownership is
-- structural, so it cannot be revoked from you and needs no role column.
CREATE TABLE IF NOT EXISTS tenant_access (
  tenant_user_id TEXT NOT NULL,
  member_user_id TEXT NOT NULL,
  granted_date   TEXT NOT NULL,
  revoked_date   TEXT,
  PRIMARY KEY (tenant_user_id, member_user_id),
  FOREIGN KEY (tenant_user_id) REFERENCES account(user_id),
  FOREIGN KEY (member_user_id) REFERENCES account(user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_access_member
  ON tenant_access (member_user_id);

-- An invitation to join a tenant. The code is the key; the row is what makes an unused
-- invite revocable and what records who came in with it.
CREATE TABLE IF NOT EXISTS tenant_invite (
  code           TEXT PRIMARY KEY,
  tenant_user_id TEXT NOT NULL,
  created_by     TEXT NOT NULL,
  created_date   TEXT NOT NULL,
  expires_date   TEXT NOT NULL,
  used_by        TEXT,
  used_date      TEXT,
  revoked_date   TEXT,
  FOREIGN KEY (tenant_user_id) REFERENCES account(user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_invite_tenant
  ON tenant_invite (tenant_user_id);
