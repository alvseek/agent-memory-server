# Council of Wizards — Profile + Environment as Shared Memory → Munnin

## **FEATURE INFO**
- **Project**: agent-memory (framework) + agent-memory-server (Munnin)
- **Date**: 2026-08-14
- **Agent**: meta
- **Feature**: Separate the **user profile** and **environment memory** out of the public `control-files/core-memory/` (CLAUDE.md-only channel) into first-class **shared memory** markdown (mirroring `shared-memory/core-reasoning-memory.md` + `core-knowledge-memory.md`), then **migrate both into the Munnin DB** (`__shared__` records surfaced by `awaken()`), so a DB-only client awakens knowing who the user is.
- **Source Protocol**: `/council-of-wizards`

*CRITICAL INSTRUCTION: To continue this plan: load the source protocol above, then inspect which sections below are filled vs unfilled to infer your current step.*

---

## **REQUIREMENTS BREAKDOWN**
*Filled AFTER [USER-NAME] confirms the WAIT Options (Step 6).*

| # | Requirement | Description |
|---|-------------|-------------|
| _pending confirmation_ | | |

---

## **SCOPE GATE**
*Pending — filled after requirements confirmed.*

---

## **CONFIRMED DECISIONS**

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| _pending_ | | | |

---

## **SUB-PLANS TABLE**

| ID | Sub-Plan Name | Description | Requirements | Protocol | Plan File | Status |
|----|--------------|-------------|--------------|----------|-----------|--------|
| _pending_ | | | | | | |

---

## **INTEGRATION CONTRACTS**

| Contract ID | Between | Format | File Path | Verified |
|------------|---------|--------|-----------|----------|
| _pending_ | | | | |

---

## **DEPENDENCY GRAPH**

_pending_

---

## **EXECUTION LOG**

| Sub-Plan | Status | Started | Completed | Agent/Session | Notes |
|----------|--------|---------|-----------|---------------|-------|
| _pending_ | | | | | |

---

## **FEATURE COMPLETION CHECKLIST**

- [ ] All sub-plans have status DONE
- [ ] All integration contracts verified
- [ ] Markdown backend awakens with profile + env (both faces)
- [ ] DB backend awakens with profile + env (`awaken()` payload)
- [ ] Fidelity gate re-baselined + green
- [ ] [USER-NAME] confirms feature complete

---

## **INVESTIGATION NOTES (pre-requirements)**

**Current state (verified in code):**
- **Shared-memory markdown pattern (channel 1, awakening-loaded, private):** `shared-memory/core-reasoning-memory.md` + `core-knowledge-memory.md`, read at awaken (markdown backend `§ load-agent-memory`), imported to `__shared__/reasoning` + `__shared__/knowledge` by `importer.import_shared`.
- **Profile + env today (channel 2, CLAUDE.md-only, public):** live in `control-files/core-memory/0-core-user-profile.md` + `1-core-environment-memory.md`. `user-config.sh` writes real per-machine values into gitignored `output/`; `compile.sh` prefers `output/` over the committed template → `write-to-claude.sh` → global CLAUDE.md. **Never in shared-memory. Never in the DB.** `awaken()` payload has no profile/env.
- **DB model:** `RecordType = episode|knowledge|identity|reasoning|emotional` (schema stores it as free TEXT — additive). `awaken()` layer i loads every `__shared__` record for all agents.
- **Env is already machine-specific by design:** `user-config.sh` sets OS block + `[AGENT-MEMORY-PATH]` per machine into gitignored `output/`. A central portable DB serving one machine's paths to all clients is the core env tension.
