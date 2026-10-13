-- A one-line summary of a record's content, authored by whoever wrote it.
--
-- The Postgres twin of `migrations/0003_record_content_summary.sql`: same column, same
-- nullable-and-no-default reasoning, on both record tables.
--
-- `ADD COLUMN IF NOT EXISTS` because a Postgres migration is applied whole and this file could
-- be re-run against a database that already carries the column after a partial failure; the
-- SQLite twin cannot say that, since SQLite has no such clause.

ALTER TABLE IF EXISTS memory_record ADD COLUMN IF NOT EXISTS content_summary TEXT;
ALTER TABLE IF EXISTS shared_record ADD COLUMN IF NOT EXISTS content_summary TEXT;
