-- 0003 — widen shared_record's CHECK to admit 'coding_reasoning' (the coding-reasoning lane).
--
-- Postgres can ALTER a constraint in place, so unlike the SQLite twin (0004) there is no
-- table rebuild and no column list to carry. The CHECK is dropped and re-added with the new
-- value. The constraint's auto-generated name is the one 0001_init created, so a rename
-- there would fail this loudly rather than silently leave the old CHECK in place.

ALTER TABLE shared_record DROP CONSTRAINT shared_record_record_type_check;
ALTER TABLE shared_record ADD CONSTRAINT shared_record_record_type_check
  CHECK (record_type IN ('reasoning','coding_reasoning','knowledge','ras','user_profile'));
