"""Access and invitations must survive everything that moves memory around.

Two different hazards, both silent. An **import** purges a tenant's records before writing
them back, so a purge that also swept grants would quietly end everyone's access on the
next import. A **backend migration** copies a fixed column list per table, so a table
missing from that list is simply not copied, and the target looks complete without it.
Neither failure raises anything a count of the memory tables would notice.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from munnin.data_entities.identity import Account
from munnin.data_entities.sharing import TenantInvite
from munnin.data_migrations.importer import _purge_tenant
from munnin.data_migrations.sqlite_to_postgres import _TABLES
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sharing_repository import SqliteSharingRepository

FUTURE = "2999-01-01T00:00:00+00:00"


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _seeded(db: Path) -> SqliteSharingRepository:
    identity = SqliteIdentityRepository(db)
    identity.ensure_account(Account(user_id="alvi", display_name="Alvi"))
    identity.ensure_account(Account(user_id="roy", display_name="Roy"))
    sharing = SqliteSharingRepository(db)
    sharing.grant("alvi", "roy")
    sharing.set_active("roy", "alvi")
    sharing.create_invite(
        TenantInvite(
            code="code-1",
            tenant_user_id="alvi",
            created_by="alvi",
            created_date=_now(),
            expires_date=FUTURE,
        )
    )
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO agent VALUES ('alvi','meta','Claude Meta','Meta','u1','d')")
    conn.execute(
        "INSERT INTO memory_record "
        "(uuid,user_id,agent_id,record_type,created_date,modified_date,full_content) "
        "VALUES ('r1','alvi','meta','episode','d','d','body')"
    )
    conn.commit()
    conn.close()
    return sharing


def test_purging_a_tenant_removes_its_memory_and_keeps_its_access(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    sharing = _seeded(db)

    removed = _purge_tenant(db, "alvi")

    assert removed == 2  # the agent and its record, and nothing else
    assert sharing.find_access("alvi", "roy") is not None
    assert sharing.find_invite("code-1") is not None
    assert sharing.find_active("roy") == "alvi"


def test_the_backend_migration_copies_access_and_the_selection() -> None:
    """A structural guard, not a behavioural one: the migration reads a typed column list,
    so a table or column left out of it is invisible at the target rather than an error."""
    tables = {name: cols for name, cols in _TABLES}
    assert {"tenant_access", "tenant_invite"} <= set(tables)
    assert "active_user_id" in tables["account"]
