-- A one-line summary of a record's content, authored by whoever wrote it.
--
-- Added for the project-keyed rows: a project-context entry's summary is what the context
-- index shows beside its theme, and Valaskjalf's `project` column is where those rows live.
-- Munnin's own records leave it NULL until one has a summary worth storing, which is why the
-- column is nullable and carries no default.
--
-- `ALTER TABLE ... ADD COLUMN` with no default is in-place, so neither table is rebuilt and
-- every existing row keeps NULL. That matters here: `0002` already had to rebuild a table for
-- a CHECK change, and a second rebuild for a column that is only ever read back would be a
-- copy of every row for no reason.

ALTER TABLE memory_record ADD COLUMN content_summary TEXT;
ALTER TABLE shared_record ADD COLUMN content_summary TEXT;
