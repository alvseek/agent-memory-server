# Fixtures

A **fixture** cheaply reproduces the end-state of one flow stage ("as if the seed importer had run", "as if a wrap-up had appended an episode") so `/integration-test` **Tactic B** can reach a deep precondition without paying the full end-to-end cost for every upstream step. Built **per-flow, on demand** — not up front.

**Header convention** (each fixture carries):
```
# fixture: {stage} — produces: {end-state it reproduces} — fidelity: {reuse-snapshot | real-API-with-token | DB-seed-mirroring-writes}
```

**Fidelity rule**: a fixture must produce a state *equivalent* to what the real stage writes, or Tactic-B runs validate states the system could never reach. Prefer the highest-fidelity buildable form (reuse an existing snapshot > call the real stage > hand-rolled DB seed). `/integration-test` should periodically run the REAL stage and assert its output matches the fixture (drift check).

**Golden rule**: *fixture the preconditions; never fixture the step under test.*

> For Munnin most preconditions are cheap already (`reset-db.sh` + `seed-meta.sh` reach a full seeded DB in one step), so fixtures are rarely needed. Add one here only when a specific Tactic-B run needs a precondition the seed can't cheaply produce.
