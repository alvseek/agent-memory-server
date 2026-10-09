# Postgres Search-Parity Fixture

Recorded 2026-10-09 while moving Valaskjalf from SQLite to PostgreSQL. This answers one
question: **does Postgres full-text search find what SQLite FTS5 found?**

## The invariant

For any query, `PostgresMemoryRepository.search(q)` returns the **same set** of records as
`SqliteMemoryRepository.search(q)` over the same data. Ranking may differ (`bm25` in FTS5
versus `ts_rank` in Postgres); **membership must not**.

## The finding (fixed before cutover)

The first pass **regressed recall**: Postgres was a strict subset of FTS5 — 0 extra, **100
missing** across the 20 queries below.

- **Cause**: FTS5's `unicode61` tokeniser splits on `-`, so `memory` matched `agent-memory`
  and `shared-memory`. Postgres's default parser keeps a hyphenated word **whole**
  (`shared-memory` is one token), so those rows were invisible to a `memory` search.
- **Fix**: the generated `search_tsv` column now flattens non-alphanumerics before
  tokenising — `regexp_replace(text, '[^[:alnum:]]+', ' ', 'g')` — reproducing FTS5's
  "letters and digits are tokens, everything else is a separator" rule.
- **After the fix**: 0 missing, 0 extra, every query.

This is why the fixture exists: a migration that only checked "does search return
something" would have shipped the regression.

## The 20 recorded queries

Run against the live snapshot (1,730 `memory_record`s under the `alvi` tenant), comparing
`SqliteMemoryRepository.search` to `PostgresMemoryRepository.search`.

| # | query | records matched (both engines) |
|---|---|---|
| 1 | postgres | 60 |
| 2 | sqlite | 26 |
| 3 | migration | 318 |
| 4 | awaken | 135 |
| 5 | deployment | 238 |
| 6 | lint | 20 |
| 7 | invintiry | 122 |
| 8 | telegent | 48 |
| 9 | whatsapp | 33 |
| 10 | linking | 54 |
| 11 | embedding | 30 |
| 12 | logto | 24 |
| 13 | cimd | 14 |
| 14 | authentra | 29 |
| 15 | heimdall | 17 |
| 16 | pagination | 65 |
| 17 | importer | 20 |
| 18 | quarantine | 27 |
| 19 | memory | 1003 |
| 20 | agent | 1102 |

## Coverage

The terms are chosen so hits fall across **content, title and tags**, and include
hyphenated tokens (`agent-memory`), underscored identifiers (`memory_record`), and plain
words — the classes where FTS5 and Postgres tokenise differently.

## Automated guard

`tests/test_search_parity.py` builds a synthetic store whose records carry hyphenated and
underscored tokens, migrates it into a fresh Postgres, and asserts **set-equality** across
the two engines for a batch of queries. Each query is asserted **non-empty**, so a fixture
that matched nothing on either side fails rather than passing vacuously.
