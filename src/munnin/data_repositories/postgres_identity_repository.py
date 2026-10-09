"""PostgreSQL implementation of ``IdentityRepository`` (the tenant/identity store).

The twin of ``SqliteIdentityRepository``. Holds no tenant: it resolves a login to one, and
creates the tenant and its ``(iss, sub)`` mapping. The only dialect differences are
``ON CONFLICT DO NOTHING`` in place of ``INSERT OR IGNORE`` and ``%s`` placeholders.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_entities.postgres_migrations import ensure_schema


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


class PostgresIdentityRepository:
    """Implements ``IdentityRepository`` over PostgreSQL. Holds no tenant."""

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

    # --- reads ---

    def find_user_id(self, iss: str, sub: str) -> str | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM user_identity WHERE iss = %s AND sub = %s", (iss, sub)
            )
            row = cur.fetchone()
        return None if row is None else str(row["user_id"])

    def get_account(self, user_id: str) -> Account | None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, display_name, email, created_date FROM account"
                " WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return Account(
            user_id=str(row["user_id"]),
            display_name=row["display_name"],
            email=row["email"],
            created_date=row["created_date"],
        )

    # --- writes ---

    def ensure_account(self, account: Account) -> Account:
        """Create the tenant if it is absent; leave an existing one untouched (idempotent)."""
        created = account.created_date or _now()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO account (user_id, display_name, email, created_date)"
                " VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING",
                (account.user_id, account.display_name, account.email, created),
            )
        found = self.get_account(account.user_id)
        assert found is not None  # noqa: S101 — just inserted or already present
        return found

    def link_identity(self, identity: UserIdentity) -> UserIdentity:
        """Map an issuer-and-subject pair to a tenant. Idempotent on that pair."""
        linked = identity.linked_date or _now()
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_identity (iss, sub, user_id, linked_date)"
                " VALUES (%s,%s,%s,%s) ON CONFLICT (iss, sub) DO NOTHING",
                (identity.iss, identity.sub, identity.user_id, linked),
            )
        return UserIdentity(
            iss=identity.iss, sub=identity.sub, user_id=identity.user_id, linked_date=linked
        )
