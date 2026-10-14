# ADR-002: `edit_metadata`, and one owner per field

**Date**: 2026-10-14

**Status**: Accepted

---

## Problem

Two gaps met at the same place. A record's metadata — `title`, `tags`, `project`, `content_summary` — had exactly one served writer, `insert`: nothing else could set them, so repairing a wrong tag, a misfiled `project` or a missing summary meant sending the whole record back through `insert`, which upserts and carries the lifecycle columns with it, so an archived row comes back hot. And `content_summary` was the one field with two homes: `edit` could replace it in the same write as a body change, while the three fields beside it had none.

The cost landed on the ordinary repair. The store's browse indexes list a `content_summary` next to every title, and rows are found missing one; the only served way to fill it was to hand the entry's whole body back, up to the line the store refuses beyond, to change a single line that is not in the body at all.

---

## Decision

**We decided to**: add `edit_metadata(uuid, title?, tags?, project?, content_summary?, clearing?)` as the only writer of those four fields, and remove `content_summary` from `edit`, leaving the body writers to the body.

The write is one `UPDATE` of the named columns plus `modified_date`, addressed to whichever table holds the uuid and scoped to the caller's tenant, with no read of `full_content` at all (`_set_fields` in each engine). An omitted field keeps its stored value, so the op is a targeted update rather than a replace. `clearing` names fields to set to SQL NULL, which is the only way to unset one. Both faces carry it — MCP tool and `POST /api/edit-metadata` — and it is annotated destructive, because it overwrites stored values and can remove them.

**Why we chose this:**

- **One owner per field.** A value reachable two ways is a value two rules can drift apart on, and the drift is invisible: whichever op you did not read looks like it behaves the same.
- **The metadata write never round-trips a body**, which is the failure it exists to remove. Handing a long document back to change one line risks the document, and nothing checked that what returned was what went in.
- **A named op is discoverable.** Tool definitions arrive at a client deferred, names first, so the tool *name* is what someone looking for "how do I change a tag" actually scans, and `edit` reads as the body.
- **The seam already had the right shape.** Every other write addresses an existing record by uuid and goes through a `_locate` that decides the table, so the new op needed no migration and no new identity.

---

## Alternatives Rejected

- **Widening `edit` with optional metadata parameters.** `old_string` and `new_string` would stop being required, and "required unless another parameter is present" is not expressible in a tool's parameter schema, so the refusal would move out of the schema and into a runtime check. It also keeps metadata behind a name that promises a body edit.
- **Keeping `content_summary` on `edit`** for the atomic body-and-summary write. The atomicity is real — the served `update-episodic` op relied on it — but the exception turned out to be positional rather than principled: `append`, the write most likely to invalidate a summary, could not carry one and had to fake a `prepend` through `edit` to reach it. The coupling now lives in the procedure as two named steps.
- **Treating a blank string as a clear.** A blank produced by a bug would silently wipe a stored value with no error, which is the failure class this change exists to remove.
- **Mirroring `insert`'s per-type blank rule.** It branches on a `record_type` the caller never passed, to give one useless input two different outcomes.

---

## Consequences

**Known limits, deliberately:**

- **Clearing needs the parameter.** For `project`, `title` and `content_summary`, an empty string is refused and `clearing` is the only route to NULL. `tags=[]` is a value rather than a blank and empties the list. The asymmetry is deliberate: NULL and `[]` are indistinguishable after decode, while an empty string against a nullable string column is not, and `project IS NULL` is exactly what decides which corpus a row belongs to.
- **A body edit and its summary are two calls**, so a failure between them leaves a summary describing the previous content until the next read. That is recoverable and visible, and it is the price of one owner per field.
- **`content_summary` stays an authored value.** Munnin refuses a blank one and requires one for the two types a browse index reads, but it cannot require a good one.

**What it moved**: `content_summary` off `edit`, and `edit`'s `content_summary` parameter out of the tool, the HTTP body, the service and the two `_rewrite` helpers. The served `db.md` op that used `edit`-as-prepend to carry a summary became a real `prepend` plus an `edit_metadata`.

**Full context**: the Munnin Quick Wizard session of 2026-10-14, whose steps this records the shape of.
