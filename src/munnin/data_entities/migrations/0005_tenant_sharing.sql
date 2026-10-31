-- Tenant sharing: a grant, an invitation, and the selection a person is acting in.
--
-- Numbered 0005 here and 0004 in the Postgres set: each backend numbers its own history,
-- and Postgres reached its final base shape in one file (`ras` was part of 0001 rather
-- than a table rebuild), so it runs one migration behind. The two files are twins of
-- purpose, not of number.
--
-- `active_user_id` carries no foreign key on purpose. The grant is consulted on every
-- call anyway, so a stale id already has a safe answer (act as yourself), and SQLite
-- cannot add a constraint through ALTER TABLE. A nullable column is the one shape both
-- backends add in place, with no table rebuild.

ALTER TABLE account ADD COLUMN active_user_id TEXT;

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
