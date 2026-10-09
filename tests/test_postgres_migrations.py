"""Postgres schema/migration-runner tests (marked ``postgres``).

These need a running PostgreSQL; they are skipped unless ``MUNNIN_PG_TEST_URL`` is set,
so the default local suite stays SQLite-only and fast (high-wizard decision 5).
"""

from __future__ import annotations

import os

import psycopg
import pytest

from munnin.data_entities import postgres_migrations as pgm

URL = os.getenv("MUNNIN_PG_TEST_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="MUNNIN_PG_TEST_URL not set"),
]


def _fresh_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()


def test_ensure_schema_creates_tables_indexes_and_fts_column() -> None:
    with psycopg.connect(URL) as conn:
        _fresh_schema(conn)
        ran = pgm.ensure_schema(conn)
        assert ran == ["0001_init"]
        with conn.cursor() as cur:
            cur.execute(
                "select tablename from pg_tables where schemaname='public' order by 1"
            )
            tables = {r[0] for r in cur.fetchall()}
            assert {
                "account",
                "user_identity",
                "agent",
                "shared_record",
                "memory_record",
                "migration_history",
            } <= tables
            cur.execute(
                "select data_type from information_schema.columns "
                "where table_name='memory_record' and column_name='search_tsv'"
            )
            assert cur.fetchone() == ("tsvector",)
            cur.execute(
                "select indexname from pg_indexes "
                "where tablename in ('memory_record','shared_record')"
            )
            indexes = {r[0] for r in cur.fetchall()}
            assert {"idx_memory_search", "idx_shared_search"} <= indexes


def test_ensure_schema_is_idempotent() -> None:
    with psycopg.connect(URL) as conn:
        _fresh_schema(conn)
        assert pgm.ensure_schema(conn) == ["0001_init"]
        assert pgm.ensure_schema(conn) == []
        assert {m.version: s for m, s in pgm.status(conn)} == {"0001": "applied"}


def test_generated_tsvector_populates_and_searches() -> None:
    with psycopg.connect(URL) as conn:
        _fresh_schema(conn)
        pgm.ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                "insert into account(user_id, created_date) values ('u','2026-01-01')"
            )
            cur.execute(
                "insert into agent(user_id, agent_id, created_date) "
                "values ('u','meta','2026-01-01')"
            )
            cur.execute(
                "insert into memory_record"
                "(uuid, user_id, agent_id, record_type, created_date, modified_date,"
                " title, full_content) "
                "values ('x','u','meta','episode','2026-01-01','2026-01-01',"
                " 'Memory note','the store moved to postgres')"
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "select uuid from memory_record "
                "where search_tsv @@ plainto_tsquery('simple', %s)",
                ("postgres",),
            )
            assert cur.fetchone() == ("x",)
