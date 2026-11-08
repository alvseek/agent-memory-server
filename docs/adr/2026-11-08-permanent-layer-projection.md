# ADR-004: The permanent layer is derived, per tenant

**Date**: 2026-11-08

**Status**: Accepted

---

## Problem

`permanent_layer()` assembles the always-on block from two halves with two different scopes. The RAS triggers come from `shared_record` under the caller's tenant. The "compacted reasoning digest" comes from `core-memory/3-core-reasoning-memory.md`, a file baked into the image. One half belongs to the person; the other belongs to the deployment.

That mismatch produced three faults. Any second tenant is served the first tenant's reasoning as its own always-on memory. The file is public: it ships in `agent-memory-system`, is pinned as a submodule in `agent-memory-server`, and is baked into a publicly pullable image, so the text is readable without deploying anything. And because the file is authored by hand, nothing detects it falling behind. It held 11 of the 34 rules with no recorded selection rule, and the one rule with no `Final Conclusion` was never noticed at all.

---

## Decision

**We decided to**: derive the reasoning half from the shared reasoning lane instead of storing it.

`MemoryService.permanent_layer()` reads the tenant's shared records once and emits the RAS entries, then one entry per non-deleted, non-archived `reasoning` record: `### {stored title}` followed by the text after that record's `**Final Conclusion**:` marker, collapsed to a single line. Order is `created_date` then `id`. `version` is the newest `modified_date` among the records the block includes, cut to its date part. `hash` stays `sha256(content)[:12]`. A record with no marker is skipped and named in a `skipped` list; a conclusion reading `None declared` is skipped without a report.

The markdown backend keeps its own authored file. `core-memory/3-core-reasoning-memory.md` stops carrying one person's rules and becomes a starter: one neutral worked example under an HTML comment that explains the shape, says a server-backed install ignores the file, and tells the reader to replace the example. The private store is retired as a memory source; the markdown path never read it.

**Why we chose this:**

- **The selection rule disappears rather than moving.** Everything in the lane is always-on, and the whole lane measured 5,627 characters against 6,109 for the hand-picked 11. The debt closed itself.
- **One home per fact.** The rule is the record and the block is a view of it, so editing a rule changes the block and no second copy can disagree.
- **The block's scope becomes the tenant's**, matching how `awaken` already works, and no deployment-wide artifact carries one person's reasoning.
- **A new rule is always-on the moment it is written**, with no second edit, so the artifact cannot fall behind the corpus.

---

## What to Build (Requirements)

**Core Requirements:**

- `permanent_layer()` projects from records, takes no digest or version parameter, and returns `skipped`.
- `permanent_layer_source()`, `_PERMANENT_LAYER_DIGEST` and the stamp regex are deleted, and no code reads a digest file.
- The tracked `3-core-reasoning-memory.md` becomes a starter carrying one neutral worked example and the guidance comment, and nothing personal.
- The served `reasoning-pattern-template` and `add-reasoning` state that the conclusion is the always-on form and ask for a single sentence under 240 characters.
- `/anchor-memory`'s report names anything in `skipped`.
- REAQ gains a `Final Conclusion` in the live store and in the private store file.
- Tests cover assembly, order, version, hash, and skip-and-report; the three loader tests and the pinned-stamp assertion go.

**Success Criteria:**

- The live tool serves 34 entries for this tenant, RAS first, no skips.
- This machine's `~/.munnin/permanent-layer.md` hashes to the served value after re-anchoring.
- The generator's output and the server's projection are identical on the same corpus.
- No new record type, no migration, no importer change.

---

## Alternatives Rejected

- **An authored digest as a per-tenant record.** Needs a record type, two migrations, an importer seed and a partial unique index, and leaves two places holding the same facts, which is how the current digest went stale.
- **Model-generated digest.** Non-deterministic, nothing to diff, and a bad line reads exactly like a good one.
- **A curated subset marked by tag.** Keeps the selection rule and adds a tag to police, so the hand-kept artifact survives under a new name.
- **Fixing the public repository only.** The server keeps serving one person's reasoning to every tenant, so the defect stays.

---

## Consequences

**Known limits, deliberately:**

- **The block is about a third larger.** The 33 rules that carry a conclusion today measure 8,490 characters with their titles, about 8,700 once REAQ has one; with the RAS half the block lands near 10 KB against 7.5 KB today.
- **A tenant with no reasoning lane gets no always-on reasoning.** That is the honest result of the block becoming personal, and the stub says so at install time.
- **A record written off-template loses its always-on line** until it is fixed. The `skipped` list is what makes that visible instead of silent, and REAQ is the one record that needed fixing.
- **A markdown install carries one example rule, not the corpus.** That is the honest state: the always-on block is personal, and the file says how to populate it.
- **The presence validator the reasoning template claims to have still does not exist.** Only `template_version` is checked. That is its own plan, across four record types.

**What it moved**: the reasoning half of the permanent layer from an authored, deployment-wide file to a per-tenant projection of the reasoning lane; the digest file from content to a stub; and the version from a typed stamp to a derived date.

**Full context**: [High Wizard plan](../../../plans/2026-11-08-munnin-deploy-permanent-layer-projection.md)
