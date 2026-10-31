"""PostgreSQL implementation of ``SharingRepository`` (grants, invites, the selection).

The twin of ``SqliteSharingRepository``. Holds no tenant. The dialect differences are
``ON CONFLICT ... DO UPDATE`` in place of SQLite's upsert clause, ``%s`` placeholders, and
``ensure_schema`` on the first connection in place of the SQLite migration runner.

The one transaction that must not be split stays one transaction here too: ``redeem``
claims the invite and writes the grant together, so a race on a code has exactly one
winner.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from munnin.data_entities.postgres_migrations import ensure_schema
from munnin.data_entities.sharing import TenantAccess, TenantInvite

_UPSERT_ACCESS = """
INSERT INTO tenant_access (tenant_user_id, member_user_id, granted_date, revoked_date)
VALUES (%s,%s,%s,NULL)
ON CONFLICT (tenant_user_id, member_user_id)
DO UPDATE SET granted_date = EXCLUDED.granted_date, revoked_date = NULL
"""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _access(row: dict) -> TenantAccess:
    return TenantAccess(
        tenant_user_id=str(row["tenant_user_id"]),
        member_user_id=str(row["member_user_id"]),
        granted_date=row["granted_date"],
        revoked_date=row["revoked_date"],
    )


def _invite(row: dict) -> TenantInvite:
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


class PostgresSharingRepository:
    """Implements ``SharingRepository`` over PostgreSQL. Holds no tenant."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ensured = False

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(self._dsn, row_factory=dict_row)
        if not self._ensured:
            ensure_schema(conn)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- the remembered selection ---

    def find_active(self, user_id: str) -> str | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT active_user_id FROM account WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
        return None if row is None else row["active_user_id"]

    def set_active(self, user_id: str, tenant_user_id: str | None) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE account SET active_user_id = %s WHERE user_id = %s",
                (tenant_user_id, user_id),
            )

    # --- grants ---

    def grants_for(self, member_user_id: str) -> list[TenantAccess]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenant_access WHERE member_user_id = %s"
                " ORDER BY granted_date",
                (member_user_id,),
            )
            rows = cur.fetchall()
        return [_access(row) for row in rows]

    def members_of(self, tenant_user_id: str) -> list[TenantAccess]:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenant_access WHERE tenant_user_id = %s"
                " ORDER BY granted_date",
                (tenant_user_id,),
            )
            rows = cur.fetchall()
        return [_access(row) for row in rows]

    def find_access(self, tenant_user_id: str, member_user_id: str) -> TenantAccess | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenant_access WHERE tenant_user_id = %s AND member_user_id = %s",
                (tenant_user_id, member_user_id),
            )
            row = cur.fetchone()
        return None if row is None else _access(row)

    def grant(self, tenant_user_id: str, member_user_id: str) -> TenantAccess:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(_UPSERT_ACCESS, (tenant_user_id, member_user_id, _now()))
        found = self.find_access(tenant_user_id, member_user_id)
        assert found is not None  # noqa: S101 — just written or already present
        return found

    def revoke(self, tenant_user_id: str, member_user_id: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tenant_access SET revoked_date = %s"
                " WHERE tenant_user_id = %s AND member_user_id = %s AND revoked_date IS NULL",
                (_now(), tenant_user_id, member_user_id),
            )
            changed = cur.rowcount
        return changed > 0

    # --- invitations ---

    def create_invite(self, invite: TenantInvite) -> TenantInvite:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenant_invite"
                " (code, tenant_user_id, created_by, created_date, expires_date,"
                "  used_by, used_date, revoked_date)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
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
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tenant_invite WHERE code = %s", (code,))
            row = cur.fetchone()
        return None if row is None else _invite(row)

    def revoke_invite(self, code: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE tenant_invite SET revoked_date = %s"
                " WHERE code = %s AND used_by IS NULL AND revoked_date IS NULL",
                (_now(), code),
            )
            changed = cur.rowcount
        return changed > 0

    def redeem(self, code: str, member_user_id: str) -> bool:
        now = _now()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tenant_user_id FROM tenant_invite WHERE code = %s", (code,)
            )
            row = cur.fetchone()
            if row is None or row["tenant_user_id"] == member_user_id:
                return False
            cur.execute(
                "UPDATE tenant_invite SET used_by = %s, used_date = %s"
                " WHERE code = %s AND used_by IS NULL AND revoked_date IS NULL"
                " AND expires_date > %s",
                (member_user_id, now, code, now),
            )
            if cur.rowcount != 1:
                return False
            cur.execute(_UPSERT_ACCESS, (row["tenant_user_id"], member_user_id, now))
        return True

    # --- labels ---

    def account_label(self, user_id: str) -> str | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT display_name, email FROM account WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return row["display_name"] or row["email"]
