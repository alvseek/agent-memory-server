"""Tenant access and invitations — the seam and its SQLite implementation.

Like ``IdentityRepository``, this repository holds no tenant of its own: it answers
"which tenant may this person act in" *before* one is chosen, which is why it cannot live
on the per-tenant memory repository.

Every rule that decides *whether* an access is legitimate (is the caller the owner, is
this label ambiguous, is the invite actually live) lives in the sharing service. What
lives here is the one operation that cannot be split without a race: ``redeem``. It
consumes the invite and writes the grant in a single transaction, so two people racing on
the same code cannot both win.

``SqliteSharingRepository`` opens its own connections and therefore sets
``PRAGMA foreign_keys`` itself — the same reason the identity repository does: SQLite
defaults it OFF per connection, and a grant naming a tenant that does not exist would be a
door into nothing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from munnin.data_entities.schema_migrations import apply_migrations
from munnin.data_entities.sharing import TenantAccess, TenantInvite

_UPSERT_ACCESS = """
INSERT INTO tenant_access (tenant_user_id, member_user_id, granted_date, revoked_date)
VALUES (?,?,?,NULL)
ON CONFLICT (tenant_user_id, member_user_id)
DO UPDATE SET granted_date = excluded.granted_date, revoked_date = NULL
"""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _access(row: sqlite3.Row) -> TenantAccess:
    return TenantAccess(
        tenant_user_id=str(row["tenant_user_id"]),
        member_user_id=str(row["member_user_id"]),
        granted_date=row["granted_date"],
        revoked_date=row["revoked_date"],
    )


def _invite(row: sqlite3.Row) -> TenantInvite:
    return TenantInvite(
        code=str(row["code"]),
        tenant_user_id=str(row["tenant_user_id"]),
        created_by=str(row["created_by"]),
        created_date=row["created_date"],
        expires_date=row["expires_date"],
        used_by=row["used_by"],
        used_date=row["used_date"],
        revoked_date=row["revoked_date"],
    )


class SharingRepository(Protocol):
    """The active selection, the grants, and the invitations."""

    # --- the remembered selection ---
    def find_active(self, user_id: str) -> str | None:
        """The tenant this person is acting in, or ``None`` for their own."""
        ...

    def set_active(self, user_id: str, tenant_user_id: str | None) -> None:
        """Remember the selection; ``None`` clears it back to their own tenant."""
        ...

    # --- grants ---
    def grants_for(self, member_user_id: str) -> list[TenantAccess]:
        """Every grant held by this person, live or revoked."""
        ...

    def members_of(self, tenant_user_id: str) -> list[TenantAccess]:
        """Every grant on this tenant, live or revoked."""
        ...

    def find_access(self, tenant_user_id: str, member_user_id: str) -> TenantAccess | None:
        """One grant row, or ``None``."""
        ...

    def grant(self, tenant_user_id: str, member_user_id: str) -> TenantAccess:
        """Grant access, reviving a revoked row rather than adding a second one."""
        ...

    def revoke(self, tenant_user_id: str, member_user_id: str) -> bool:
        """Revoke a live grant. ``False`` when there was none to revoke."""
        ...

    # --- invitations ---
    def create_invite(self, invite: TenantInvite) -> TenantInvite:
        """Store a new invitation."""
        ...

    def find_invite(self, code: str) -> TenantInvite | None:
        """One invitation by code, or ``None``."""
        ...

    def revoke_invite(self, code: str) -> bool:
        """Retire an unused invitation. ``False`` when it was absent or already settled."""
        ...

    def redeem(self, code: str, member_user_id: str) -> bool:
        """Consume a live invite and grant access, in one transaction.

        ``False`` when the invite is absent, used, revoked or expired, or when it names
        the member's own tenant. Nothing is written in that case.
        """
        ...

    # --- labels ---
    def account_label(self, user_id: str) -> str | None:
        """The human label for a tenant: its display name, else its email, else ``None``."""
        ...


class SqliteSharingRepository:
    """The SQLite implementation. Holds no tenant."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._ensured = False

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._ensured:
            apply_migrations(conn)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- the remembered selection ---

    def find_active(self, user_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT active_user_id FROM account WHERE user_id = ?", (user_id,)
            ).fetchone()
        return None if row is None else row["active_user_id"]

    def set_active(self, user_id: str, tenant_user_id: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE account SET active_user_id = ? WHERE user_id = ?",
                (tenant_user_id, user_id),
            )

    # --- grants ---

    def grants_for(self, member_user_id: str) -> list[TenantAccess]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_access WHERE member_user_id = ?"
                " ORDER BY granted_date",
                (member_user_id,),
            ).fetchall()
        return [_access(row) for row in rows]

    def members_of(self, tenant_user_id: str) -> list[TenantAccess]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_access WHERE tenant_user_id = ?"
                " ORDER BY granted_date",
                (tenant_user_id,),
            ).fetchall()
        return [_access(row) for row in rows]

    def find_access(self, tenant_user_id: str, member_user_id: str) -> TenantAccess | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_access WHERE tenant_user_id = ? AND member_user_id = ?",
                (tenant_user_id, member_user_id),
            ).fetchone()
        return None if row is None else _access(row)

    def grant(self, tenant_user_id: str, member_user_id: str) -> TenantAccess:
        now = _now()
        with self._conn() as conn:
            conn.execute(_UPSERT_ACCESS, (tenant_user_id, member_user_id, now))
        found = self.find_access(tenant_user_id, member_user_id)
        assert found is not None  # noqa: S101 — just written or already present
        return found

    def revoke(self, tenant_user_id: str, member_user_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tenant_access SET revoked_date = ?"
                " WHERE tenant_user_id = ? AND member_user_id = ? AND revoked_date IS NULL",
                (_now(), tenant_user_id, member_user_id),
            )
        return cur.rowcount > 0

    # --- invitations ---

    def create_invite(self, invite: TenantInvite) -> TenantInvite:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tenant_invite"
                " (code, tenant_user_id, created_by, created_date, expires_date,"
                "  used_by, used_date, revoked_date)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    invite.code,
                    invite.tenant_user_id,
                    invite.created_by,
                    invite.created_date,
                    invite.expires_date,
                    invite.used_by,
                    invite.used_date,
                    invite.revoked_date,
                ),
            )
        found = self.find_invite(invite.code)
        assert found is not None  # noqa: S101 — just inserted
        return found

    def find_invite(self, code: str) -> TenantInvite | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_invite WHERE code = ?", (code,)
            ).fetchone()
        return None if row is None else _invite(row)

    def revoke_invite(self, code: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tenant_invite SET revoked_date = ?"
                " WHERE code = ? AND used_by IS NULL AND revoked_date IS NULL",
                (_now(), code),
            )
        return cur.rowcount > 0

    def redeem(self, code: str, member_user_id: str) -> bool:
        now = _now()
        with self._conn() as conn:
            invite = conn.execute(
                "SELECT * FROM tenant_invite WHERE code = ?", (code,)
            ).fetchone()
            if invite is None or invite["tenant_user_id"] == member_user_id:
                return False
            cur = conn.execute(
                "UPDATE tenant_invite SET used_by = ?, used_date = ?"
                " WHERE code = ? AND used_by IS NULL AND revoked_date IS NULL"
                " AND expires_date > ?",
                (member_user_id, now, code, now),
            )
            if cur.rowcount != 1:
                return False
            conn.execute(_UPSERT_ACCESS, (invite["tenant_user_id"], member_user_id, now))
        return True

    # --- labels ---

    def account_label(self, user_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT display_name, email FROM account WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return row["display_name"] or row["email"]
