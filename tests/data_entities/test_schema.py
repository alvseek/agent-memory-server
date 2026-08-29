"""The three-table schema — structure, idempotency, and the two constraints it adds.

These tests exercise the DDL directly against a bare sqlite3 connection, deliberately
not through the repository: they answer "does the schema declare the constraint", while
`tests/data_repositories/test_foreign_keys.py` answers the separate question "does the
repository turn it on". A constraint that is declared but never enabled passes one and
fails the other, which is exactly the failure mode worth keeping apart.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_DDL = (
    Path(__file__).resolve().parents[2]
    / "src" / "munnin" / "data_entities" / "schema.sql"
).read_text(encoding="utf-8")

_INSERT_SHARED = (
    "INSERT INTO shared_record (uuid,user_id,record_type,created_date,modified_date,full_content)"
    " VALUES (?,?,?,'d','d','body')"
)
_INSERT_MEMORY = (
    "INSERT INTO memory_record (uuid,user_id,agent_id,record_type,created_date,modified_date,"
    "full_content) VALUES (?,?,?,?,'d','d','body')"
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.execute("PRAGMA foreign_keys = ON")
    # The tenant first: an agent references it, so the chain has to be built downwards.
    conn.execute("INSERT INTO account (user_id, created_date) VALUES ('alvi','2026-08-28')")
    conn.execute(
        "INSERT INTO agent VALUES ('alvi','meta','Claude Meta','Meta Agent','u1','2026-08-20')"
    )
    return conn


def _names(conn: sqlite3.Connection, kind: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))}


_TABLES = {"account", "user_identity", "agent", "shared_record", "memory_record"}


def test_five_tables_and_two_fts_indexes() -> None:
    conn = _db()
    tables = _names(conn, "table")
    assert _TABLES <= tables
    assert {"memory_fts", "shared_fts"} <= tables
    assert {"idx_memory_browse", "idx_shared_browse"} <= _names(conn, "index")
    # one insert/delete/update trigger per memory table
    assert len({t for t in _names(conn, "trigger") if t.endswith(("_ai", "_ad", "_au"))}) == 6


def test_schema_is_idempotent() -> None:
    """Applied on every repository init, so a second run must be a no-op, not an error."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    conn.executescript(_DDL)
    assert _TABLES <= _names(conn, "table")


# --- the identity pair: a tenant, and which issuer-and-subject resolves to it ---


def test_one_person_may_hold_several_identities() -> None:
    """Two issuers mapping to one tenant at the same time is what makes changing
    issuers an insert here rather than a rewrite of every memory record."""
    conn = _db()
    conn.execute(
        "INSERT INTO user_identity VALUES ('https://a.authkit.app','sub_a','alvi','d')"
    )
    conn.execute(
        "INSERT INTO user_identity VALUES ('https://b.supabase.co/auth/v1','uuid-b','alvi','d')"
    )
    rows = conn.execute(
        "SELECT user_id FROM user_identity ORDER BY iss"
    ).fetchall()
    assert [r[0] for r in rows] == ["alvi", "alvi"]


def test_the_same_subject_string_under_two_issuers_is_two_identities() -> None:
    """Keyed on the pair, never on the subject alone — a subject is only unique within
    the issuer that minted it, so two issuers may legitimately emit the same string."""
    conn = _db()
    conn.execute("INSERT INTO account (user_id, created_date) VALUES ('other','d')")
    conn.execute("INSERT INTO user_identity VALUES ('https://a.example','same','alvi','d')")
    conn.execute("INSERT INTO user_identity VALUES ('https://b.example','same','other','d')")
    assert conn.execute("SELECT COUNT(*) FROM user_identity").fetchone()[0] == 2


def test_the_same_pair_cannot_map_twice() -> None:
    conn = _db()
    conn.execute("INSERT INTO user_identity VALUES ('https://a.example','sub_a','alvi','d')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO user_identity VALUES ('https://a.example','sub_a','alvi','d')")


@pytest.mark.parametrize("rtype", ["reasoning", "knowledge", "user_profile"])
def test_shared_accepts_its_three_record_types(rtype: str) -> None:
    """Fleet memory is two kinds of shared thinking plus one fact about the user."""
    _db().execute(_INSERT_SHARED, (f"s-{rtype}", "alvi", rtype))


@pytest.mark.parametrize("rtype", ["episode", "identity", "emotional"])
def test_shared_rejects_agent_only_record_types(rtype: str) -> None:
    """Admitting the user profile widened the CHECK without loosening what it guards:
    these three each belong to some particular agent, so an ownerless table still
    refuses them. A constraint that accepts everything would pass the test above and
    mean nothing."""
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        _db().execute(_INSERT_SHARED, (f"s-{rtype}", "alvi", rtype))


def test_only_one_user_profile_per_tenant() -> None:
    """`awaken` answers "has anyone been asked yet" with the presence of a row, so a second
    profile would answer it with whichever came first and hide the other — the wrong answer,
    arrived at silently. The CHECK says a profile *may* live here; this says only one may."""
    conn = _db()
    conn.execute(_INSERT_SHARED, ("s-up1", "alvi", "user_profile"))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
        conn.execute(_INSERT_SHARED, ("s-up2", "alvi", "user_profile"))


def test_the_declared_shared_types_match_the_schema_check() -> None:
    """`SHARED_RECORD_TYPES` exists so a refusal can name the legal values. That is only
    safe while it agrees with the CHECK, and nothing else would notice if it stopped —
    the drift is invisible until a caller reads a message listing the wrong set."""
    from munnin.data_entities.memory_record import SHARED_RECORD_TYPES

    check = _DDL.split("record_type   TEXT    NOT NULL CHECK (record_type IN (")[1]
    declared_in_schema = [v.strip().strip("'") for v in check.split("))")[0].split(",")]
    assert [t.value for t in SHARED_RECORD_TYPES] == declared_in_schema


def test_the_profile_limit_does_not_constrain_the_other_shared_types() -> None:
    """A partial index, not a blanket one: fleet reasoning and knowledge are many-per-tenant
    and must stay that way."""
    conn = _db()
    for i in range(3):
        conn.execute(_INSERT_SHARED, (f"s-r{i}", "alvi", "reasoning"))
        conn.execute(_INSERT_SHARED, (f"s-k{i}", "alvi", "knowledge"))


def test_a_second_tenant_may_have_their_own_profile() -> None:
    """The index is keyed on user_id, so the limit is per tenant — not one profile globally."""
    conn = _db()
    conn.execute(_INSERT_SHARED, ("s-up-a", "alvi", "user_profile"))
    conn.execute(_INSERT_SHARED, ("s-up-b", "someone-else", "user_profile"))


def test_memory_accepts_a_record_for_a_known_agent() -> None:
    _db().execute(_INSERT_MEMORY, ("m1", "alvi", "meta", "episode"))


def test_memory_rejects_a_record_for_an_unknown_agent() -> None:
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        _db().execute(_INSERT_MEMORY, ("m2", "alvi", "ghost", "episode"))


def test_memory_rejects_a_known_agent_under_another_tenant() -> None:
    """The composite key means the FK enforces tenancy, not just existence."""
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        _db().execute(_INSERT_MEMORY, ("m3", "someone-else", "meta", "episode"))


def test_each_fts_index_tracks_only_its_own_table() -> None:
    conn = _db()
    conn.execute(_INSERT_SHARED, ("s1", "alvi", "reasoning"))
    conn.execute(_INSERT_MEMORY, ("m1", "alvi", "meta", "episode"))
    hits = lambda t: conn.execute(f"SELECT rowid FROM {t} WHERE {t} MATCH 'body'").fetchall()  # noqa: E731
    assert len(hits("shared_fts")) == 1
    assert len(hits("memory_fts")) == 1
