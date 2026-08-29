"""Tenant and identity storage — the one repository that has no tenant of its own.

Every other repository is constructed *for* a tenant and stamps it into each statement.
This one cannot be: it runs before the tenant is known, and answering "who is this?" is
precisely its job. That is why the lookup cannot live on ``SqliteMemoryRepository``,
whose whole design is that ``user_id`` is fixed at construction.

It opens its own connections and therefore sets ``PRAGMA foreign_keys`` itself. SQLite
defaults it OFF per connection, so inheriting the other repository's habit is not enough
— a declared-but-unenabled constraint on ``user_identity`` would let a mapping point at a
tenant that does not exist, which is a login into nothing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from munnin.data_entities.identity import Account, UserIdentity

_SCHEMA_SQL = (
    Path(__file__).resolve().parent.parent / "data_entities" / "schema.sql"
).read_text(encoding="utf-8")


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


class IdentityRepository:
    """Reads and writes ``account`` and ``user_identity``. Holds no tenant."""

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
            conn.executescript(_SCHEMA_SQL)
            self._ensured = True
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- reads ---

    def find_user_id(self, iss: str, sub: str) -> str | None:
        """The tenant this issuer-and-subject pair resolves to, or ``None``."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id FROM user_identity WHERE iss = ? AND sub = ?", (iss, sub)
            ).fetchone()
        return None if row is None else str(row["user_id"])

    def get_account(self, user_id: str) -> Account | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, display_name, email, created_date FROM account"
                " WHERE user_id = ?",
                (user_id,),
            ).fetchone()
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
        """Create the tenant if it is absent; leave an existing one untouched.

        Idempotent so the importer and the login path can both call it without either
        having to know whether the other ran first. It deliberately does **not** refresh
        ``display_name`` or ``email`` — an issuer's profile claims are not authoritative
        over a tenant that already exists."""
        created = account.created_date or _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO account (user_id, display_name, email, created_date)"
                " VALUES (?,?,?,?)",
                (account.user_id, account.display_name, account.email, created),
            )
        found = self.get_account(account.user_id)
        assert found is not None  # noqa: S101 — just inserted or already present
        return found

    def link_identity(self, identity: UserIdentity) -> UserIdentity:
        """Map an issuer-and-subject pair to a tenant. Idempotent on that pair.

        The foreign key means a mapping can never name a tenant that does not exist, so
        ``ensure_account`` has to have run first — which is what makes an unknown pair a
        two-step creation rather than one insert."""
        linked = identity.linked_date or _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_identity (iss, sub, user_id, linked_date)"
                " VALUES (?,?,?,?)",
                (identity.iss, identity.sub, identity.user_id, linked),
            )
        return UserIdentity(
            iss=identity.iss, sub=identity.sub, user_id=identity.user_id, linked_date=linked
        )
