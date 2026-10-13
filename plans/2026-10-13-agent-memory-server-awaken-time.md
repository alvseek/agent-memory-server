# High Wizard Plan

## **PROJECT INFO**
- **Project**: agent-memory-server (Munnin — the memory MCP server)
- **Date**: 2026-10-13
- **Agent**: meta
- **Theme**: Reduce the awaken payload so a coding awakening costs less time (baseline measured at 157s across 14 steps)
- **Source Protocol**: `/high-wizard` — /high-wizard

*CRITICAL INSTRUCTION: To continue this plan: load the source protocol above, then inspect which sections below are filled vs unfilled to infer your current step.*

---

## **INHERITED CONTEXT**
*Filled at investigation step 0 with whatever was settled before this plan existed. The two sources are recorded separately and never merged — write "None" under a part that does not apply.*
*These decisions are **not yours to reopen**. If one looks wrong, STOP and surface it to [USER-NAME] — do not silently re-decide it here or in Confirmed Decisions below.*

### From the Parent Plan
- **Parent plan**: None — not a sub-plan. This plan was escalated from `/quick-wizard`, whose Step 2 scope gate fired on four counts: a production deploy to serverhost-1, an architecture decision record, more than one repository, and a session with no room left to implement.
- **Assigned scope**: Not handed down. What this plan owns is stated in the Scope section, once the rounds below are confirmed.

| # | Inherited decision | Chosen | Parent's reason | Status |
|---|--------------------|--------|-----------------|--------|
| 1 | None | — | — | — |

- **Integration contracts**: None inherited.
- **Pushed-down open items**: None inherited.

### From Pre-Planning Discussion
- **Discussion**: Pre-planning discussion with Alvi, 2026-10-13, in the session that measured the awakening
- **Agreed scope**: improve the awakening time, with the diagnosis measured rather than assumed (157s across 14 steps, and the payload identified as the dominant cost)

| # | Settled decision | Chosen | His reason | Status |
|---|------------------|--------|------------|--------|
| 1 | What is being fixed | Cut the awakening time | *"I'm still want to improve the awaken time"* and *"What matters and what I want to fix is the awaken time"* | Settled |
| 2 | The shape of the fix | One complete call that returns the whole awakening set (episodic, knowledge, reasoning, map-orientation, private, shared), so the agent makes fewer tool calls. Not a smaller payload | *"isn't it supposed to be return more, but less tool call? ideally, it's already complete in a single query (episodic, knowledge, reasoning, map-orientation, private, shared). so content doesn't change at all"* | Settled |
| 3 | What the store holds | Nothing changes. No layer is trimmed, no record is written or relocated | *"so content doesn't change at all"* | Settled |
| 4 | Which face carries the complete call | Munnin's `awaken`, and this plan's scope is Munnin only (agent-memory-server) | *"we need to fix Munnin awakening first, correct? let's change the scope limited to munnin then"* | Settled |

- **Considered and rejected**: returning less (a smaller payload, by indexing a layer or relocating the trap notes out of the always-load shared layer) — lost on his call: the content is not the thing to change, the retrieval is. The measured reason it was ever on the table still stands as a fact: the payload's size taxes every step that follows it (5.0s per step before it, 14.2s per step after). Also rejected by decision 4: the Hermod-side alternatives (a coding-awakening call on Hermod, or Hermod reading the database itself).
- **Left open**: nothing from the discussion. Two notes carried into the plan: the cwd is `hermod-deploy` rather than the memory server, so the wrap-up files this work under `agent-memory-server`; and the plan file already lives in that repo at `plans/2026-10-13-agent-memory-server-awaken-time.md`.
- **Next piece, agreed 2026-10-13 (later in the same session): the project parameter comes out of `awaken` first**, as its own small plan run through `/quick-wizard`. Munnin stops accepting a project at all, so the code matches its own flow doc (`awaken-db.md` already documents `awaken(domain)`) and `ARCHITECTURE.md:283` (*"Project is a coding concept; a chat agent using the core alone is project-blind"*). This plan's technical-core round is therefore overtaken for episode selection: the set selection stays caller-side, which is where it already happens. Known cost, to be settled in that plan: `latest_episode` becomes the newest overall, so a project whose own episode is not the newest overall costs the caller one `get(uuid)`.

---

## **OBJECTIVES**
[Clear, concise statement of what we want to achieve]

### **Related Documents**
[Link to related documentation, requirements, or design files if they exist, or write "None"]
- [Document 1](path/to/document1.md) - Brief description

### **SUCCESS CRITERIA**
- [ ] [Primary goal achieved]
- [ ] [Quality/testing requirements met]
- [ ] [Integration requirements met]
- [ ] [Documentation updated if needed]

---

## **SCOPE**

### In Scope
- [Specific deliverable or feature]
- [Specific deliverable or feature]

### Out of Scope
- [Explicitly excluded item and why]
- [Future consideration for later]

---

## **CONFIRMED DECISIONS**
*Decisions made **by this plan** — both **asked-and-confirmed** by [USER-NAME] AND **written-through** (Zone A and B decisions made by the agent, recorded with their reasoning). The reasons serve as the analysis record.*
*Decisions settled before this plan existed — by a parent, or in a pre-planning discussion — belong in [INHERITED CONTEXT](#inherited-context) above, not here. Keeping them separate is what shows which decisions this plan actually owns.*

| # | Decision | Chosen | Reason |
|---|----------|--------|--------|
| 1 | [Decision topic] | [Chosen option] | [Evidence-based reason] |
| 2 | [Decision topic] | [Chosen option] | [Evidence-based reason] |

---

## **SOLUTION**

### Architecture Overview
[High-level system design and component interaction, built from confirmed decisions]

### Component 1: [Name]
- **Purpose**: [What problem it solves]
- **Key Files**: [Files to create/modify]

### Component 2: [Name]
- **Purpose**: [What problem it solves]
- **Key Files**: [Files to create/modify]

<!-- OPTIONAL SECTION A: Include when multi-system changes, multiple components interacting -->
### Integration Architecture
[Table or diagram showing how all components integrate together]

| Component | Integrates With | Data Flow | Dependencies |
|-----------|----------------|-----------|--------------|
| [Component 1] | [Other components] | [Input → Processing → Output] | [Required components] |
| [Component 2] | [Other components] | [Input → Processing → Output] | [Required components] |

<!-- OPTIONAL SECTION A2: Include when a change alters a data shape/format/contract that CROSSES a system, service, or process boundary (a field's type/nullability, a string format, an enum value, a serialized payload, a DB column another app reads). Skip for single-system internal changes. -->
### Cross-System Contract Impact (Blast-Radius Check)

*A producer-side change to shared data silently breaks consumers that nobody updated in the same pass. Enumerate EVERY consumer of the changed shape and how each is verified BEFORE shipping. Producer and consumers are usually separate deploys.*

**Change classification** (check all that apply): ☐ field type/nullability ☐ string/ID format ☐ enum value added/changed ☐ new/removed field ☐ semantics changed (same shape, new meaning)

| # | Consumer (system + path) | How it couples (deserialize / string-parse / DB-read / migrate / display) | Breaks how on this change? | Verified / mitigated |
|---|---|---|---|---|
| 1 | [System → file] | [coupling] | [crash / silent-wrong / leak / none] | [what was checked] |
| 2 | [System → file] | [coupling] | [crash / silent-wrong / leak / none] | [what was checked] |

- **Deploy ordering**: [which ends deploy, in what order — a producer-only deploy with a stale consumer is the classic break]
- **Existing data**: [is historical data mixed-format / un-migrated? parsers must handle both]
- **Project registry**: [link to the project's cross-system consumer registry if one exists]

<!-- OPTIONAL SECTION B: Include when changing data/process flow, API changes -->
### System Flow Diagrams

**Current State:**
```mermaid
[Sequence diagram showing current system flow and component interactions]
```

**End Result:**
```mermaid
[Sequence diagram showing system flow after changes are applied]
```

<!-- OPTIONAL SECTION C: Include when significant technical constraints exist -->
### Technical Considerations
[Constraints, limitations, dependencies, and technical challenges]

- **Consideration 1**: [Description]
  - [Sub-detail]
  - [Sub-detail]
- **Consideration 2**: [Description]
  - [Sub-detail]

<!-- OPTIONAL SECTION D: Include for investigation/analysis-focused tasks -->
### Detailed Analysis

#### Objective Analysis
[What does the objective really want? Break down requirements and specifications]

- **Requirement 1**: [Analysis]
- **Requirement 2**: [Analysis]

#### Current State Analysis
[What is our current state? Existing code, systems, capabilities, constraints]

- **Existing Systems**: [Current technology stack and architecture]
- **Current Capabilities**: [What we can do now]
- **Known Limitations**: [Current constraints and bottlenecks]

<!-- OPTIONAL SECTION E: Include for bug investigation/fix tasks -->
### Bug Investigation

#### Bug Information
- **Bug Report**: [What was reported / what's the symptom]
- **Context**: [When does it occur? What conditions trigger it?]
- **Severity**: [Impact on users/system]

#### Scaffolding Check
- **Existing Tests**: [What test coverage exists around the bug area?]
- **Debugging Tools**: [What logging/debugging infrastructure is available?]
- **Reproduction**: [Can the bug be reliably reproduced? Steps to reproduce.]

#### Bug Location
- **Suspected Area**: [Files/modules/functions where the bug likely lives]
- **Evidence**: [What points to this location?]

#### Hypothesis Testing
*Test hypotheses sequentially. Each must be tested before moving to the next.*

| # | Hypothesis | Test | Result | Confirmed? |
|---|-----------|------|--------|------------|
| 1 | [What might be causing the bug] | [How to verify] | [What happened] | Yes/No |
| 2 | [Next hypothesis if #1 rejected] | [How to verify] | [What happened] | Yes/No |
| 3 | [Next hypothesis if #2 rejected] | [How to verify] | [What happened] | Yes/No |

#### Root Cause
- **Confirmed Cause**: [The verified root cause of the bug]
- **Evidence**: [What test/evidence confirmed this?]

<!-- OPTIONAL SECTION F: Include for brainstorming/decision tasks, multiple viable approaches -->
### Solution Options & Evaluation

#### Solution Options
*List 5-8 potential solutions. Brief description for each.*

| # | Solution | Description |
|---|----------|-------------|
| 1 | [Name] | [Brief description of approach] |
| 2 | [Name] | [Brief description of approach] |
| 3 | [Name] | [Brief description of approach] |
| 4 | [Name] | [Brief description of approach] |
| 5 | [Name] | [Brief description of approach] |

#### Evaluation
*Evaluate top candidates with pros/cons.*

| Solution | Pros | Cons |
|----------|------|------|
| [Name] | [Advantages] | [Disadvantages] |
| [Name] | [Advantages] | [Disadvantages] |
| [Name] | [Advantages] | [Disadvantages] |

#### Selected Approach
- **Chosen**: [Solution name]
- **Rationale**: [Why this solution wins — connects evidence from evaluation]

<!-- OPTIONAL SECTION G: Include when task produces an architecture decision record -->
### ADR Output
*When this section is confirmed, the procedure creates a separate ADR file using the [ADR Template]([path-to-agent-memory-wizards]/templates/adr-template.md).*

- **ADR File**: [Path to created ADR file, filled by procedure Step 12]
- **Decision Summary**: [1-sentence summary of the decision made in section F]

---

## **IMPLEMENTATION PHASES**

### Phase 1: [Name]
- [ ] **Step 1.1**: [Overview]
  - **Action**: [What to do]
  - **Implementation**: [How to do it]
  - **Testing**: [How to verify]
  - **Success Criteria**: [When it's done]

- [ ] **Step 1.2**: [Overview]
  - **Action**: [What to do]
  - **Implementation**: [How to do it]
  - **Testing**: [How to verify]
  - **Success Criteria**: [When it's done]

### Phase 2: [Name]
- [ ] **Step 2.1**: [Overview]
  - **Action**: [What to do]
  - **Implementation**: [How to do it]
  - **Testing**: [How to verify]
  - **Success Criteria**: [When it's done]

...{next phases and steps as needed}...

---

## **EXECUTION LOG**
**Execution Protocol for AI**:
I have to use this document as my **ONLY** source of truth to execute and track the plan steps iteratively. I should **NOT** use additional tools like ToDos because it lacks the context of what should I do. Everytime I want to implement a step I have to check the reference to the original step plan above. Everytime a step has been finished I need to go back to this document to log what was done.
*In other words*:
- I have to make this document as the source of truth for the implementation phase on what I have worked on and what I will be working
- The original plan must be fully in my context, therefore, I have to make sure I loaded the **Plan File** before executing any task and read carefully the reference to the original step
- I have to do the implementation by doing it in order per step THEN, I ALWAYS have to fill the step log rightly after

**Definition of Done (applies to ALL steps)**:
- ✅ **Code Quality**: Code compiles/runs without errors
- ✅ **Testing**: Tests written and passing
- ✅ **Logged**: Implementation and testing logged below
- 🚫 **Blocked**: Get input from [USER-NAME] before assuming

### Phase 1:
- [ ] **Step 1.1**: [link to step above]
  - **Implementation Log**: [What was done]
  - **Testing Log**: [What was tested and results]
  - **Success Criteria**: [Pass/Fail against step's success criteria]
  - **Tech Debts**: [Optional - any shortcuts, TODOs, or future improvements noted]
  - **Result**: [Outcome compared to success criteria]

- [ ] **Step 1.2**: [link to step above]
  - **Implementation Log**: [What was done]
  - **Testing Log**: [What was tested and results]
  - **Success Criteria**: [Pass/Fail against step's success criteria]
  - **Tech Debts**: [Optional - any shortcuts, TODOs, or future improvements noted]
  - **Result**: [Outcome compared to success criteria]

### Phase 2:
- [ ] **Step 2.1**: [link to step above]
  - **Implementation Log**: [What was done]
  - **Testing Log**: [What was tested and results]
  - **Success Criteria**: [Pass/Fail against step's success criteria]
  - **Tech Debts**: [Optional - any shortcuts, TODOs, or future improvements noted]
  - **Result**: [Outcome compared to success criteria]

...{next phases as needed}...

---

## **QUALITY REVIEW**
*Filled by procedure Step 16 (delegated to `/analyze-code-quality` in embedded mode) after all execution phases are complete. **Static** review — answers "is the code clean?".*

- **Scope**: [Files reviewed — from Execution Log, reconciled against `git diff --name-only`]
- **Quality Standard**: [quality-standard.md found / not found — dimensions applied]
- **Findings**: [Issues found, or "No findings — implementation meets quality dimensions"]
- **Fixed**: [What was fixed from approved findings, or "N/A"]

---

## **QA HANDOFF**
*Filled by procedure Step 17 after Quality Review is resolved. This plan is **not** runtime-verified — this section records the plan for that verification, which happens in a QA session with the stack up.*

- **Scope**: [Modules touched — mapped from Execution Log scope]
- **QA instrument**: [Set up (map + bench) / NOT SET UP — auto-skipped]
- **Integration coverage**: [Filled at Step 14 from `/qa-status`. Either: "in scope — bench built, stack up; phases N, M carry integration tests" or "NONE — [which check failed], confirmed with [USER-NAME] before implementation"]
- **Checklist**: [`qa/checklists/{feature}.md`, or "none — skipped, reason"]
- **Coverage split**: [N automated (named tests) / N manual — of which N are UI-bound]
- **Runtime verification**: **NOT DONE.** Next action: [`/run-qa-test --checklist qa/checklists/{feature}.md` once the stack is up | set up the instrument first: `/map-qa-instrument create` → `/build-qa-bench`]

> Do not read a filled checklist as a passed one. This section says a verification *plan* exists, nothing more.

---

## **POST-COMPLETION**
After all phases are executed, logged, and both **Quality Review** + **QA Handoff** are filled, move this plan to `plans/completed/`:
`mkdir -p ./plans/completed && mv ./plans/[this-file].md ./plans/completed/[this-file].md`
