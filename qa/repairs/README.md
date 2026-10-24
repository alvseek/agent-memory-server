# Repairs — data already in the store

A repair here fixes **records that are already stored**, as opposed to the importer that
writes them. Each one is a guarded SQL file plus its rollback, kept because the change
happened against the live store and the evidence of what it touched has to live somewhere
durable: the dry-run count, the row count it asserted, and the exact `uuid`s it flipped.

Repairs are the exception, not the instrument. A defect that keeps producing bad rows is
fixed in the code first — the SQL here only repairs what the code already wrote, and it is
worth nothing without the code fix beside it.

---

## 2026-10-24 — episode and knowledge records stored archived

| | |
|---|---|
| Files | [repair](2026-10-24-episode-archive-repair.sql) · [rollback](2026-10-24-episode-archive-repair-rollback.sql) |
| Rows | 160 (137 episodes, 23 knowledge), 13 agents |
| Column touched | `memory_record.archived_date`, and nothing else |
| Result | `UPDATE 160`; aquazone 0 → 21 active episodes, python 0 → 63, invintiry 0 → 28, frontend-react 0 → 18 |

**Why the rows were wrong.** `parse_active_episodes` matched one line shape — a dash bullet
whose link starts the line — while the fleet writes ten, so eight agents' indexes parsed to
**zero** entries and `_import_episodes` filed every episode they had as *absent from the
index*, which means archived. `parse_knowledge_index` accepted only the bold-wrapped bullet,
so the plain `- [file](path) — text` form was filed the same way. Because every read path
filters on `archived_date IS NULL`, those records were invisible to `awaken` and to
`query … include_archived=false`.

**Why this and not a re-import.** The importer CLI only builds SQLite repositories, so no
command can import into the deployed Postgres; the SQLite→Postgres copy would overwrite the
live store with a staler file (163 meta episodes live against 145 in the dump). A full
re-import also rewrites `full_content`, `title`, `tags` and `content_summary` for every row
from markdown, reverting whatever agents have written through the store since. The defect
localises to one column on rows that can be named exactly, so one guarded `UPDATE` is the
smaller and reversible change.

**Re-running or verifying it.** The repair file is idempotent in the sense that matters: its
first query must return `160` before the `BEGIN` block, the block aborts unless it updates
exactly that many rows, and its last query prints the per-agent counts the repair exists to
change. Run it with `psql -f`; `\set ON_ERROR_STOP on` is inside the file. The rollback
restores the captured values and refuses if a row has been changed since.

**What it does not fix.** Files listed in an index that have no row at all (eight, mostly
legacy `recent-context.md`), and 66 index entries whose file is stored twice under two key
spellings — one visible, one archived. Both are recorded in the episode that shipped this
work; neither hides a record the index advertises.
