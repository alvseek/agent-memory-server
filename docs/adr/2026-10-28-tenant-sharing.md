# ADR-003: Account Sharing by Tenant Selection

**Date**: 2026-10-28

**Status**: Accepted

---

## Problem

Munnin's tenancy answers "whose memory is this?" from the login: one issuer-and-subject pair resolves to one tenant and every record is scoped to it. That holds while a person is the only one who needs their memory, and fails the moment a second person must work inside an account. The only route today is handing over the owner's login, which is not acceptable, and the nearest shortcut, rebinding the joiner's identity to the owner's account, erases the joiner's own tenant and turns revocation into a loss of access rather than the end of a grant.

---

## Decision

**We decided to**: treat access to a tenant as a grant, and let a person act in any tenant they may enter, chosen explicitly and remembered per person.

A person's `(iss, sub)` still resolves to their own tenant, unchanged. `tenant_access` records that another person's tenant is open to them, with a `revoked_date` rather than a delete. `account.active_user_id` remembers which tenant they are acting in, defaulting to their own. The resolver chooses the active tenant on every call and consults the grant there, so a revocation is refused at the point of use rather than only at the moment of switching. Joining runs through a single-use, expiring invite row, so access can be revoked before it is used and the account keeps a record of who came in.

**Why we chose this:**
- The read path is untouched: every query stays scoped to one `user_id`, so no repository filter changes and the composite foreign keys keep their meaning.
- Ownership becomes structural rather than a role, because your own tenant needs no grant and therefore cannot be revoked from you.
- Nothing a person wrote before joining becomes unreachable, because joining moves neither their identity nor their records.

---

## What to Build (Requirements)

**Core Requirements:**
- `tenant_access`, `tenant_invite` and `account.active_user_id`, in both migration sets.
- A sharing repository and a sharing service that own the grant rules and the owner check.
- One resolver step that returns the active tenant and refuses a revoked one with a message naming it.
- Membership tools on both faces: list tenants, switch tenant, list members, create an invite, revoke an invite, redeem an invite, revoke a member.
- A `caller` block in the `awaken` payload, and a profile seeded from the provider's name claim when a tenant is created.

**Success Criteria:**
- A token resolves to its own tenant until somebody switches, and to a granted tenant only while the grant is live.
- Revoking a grant refuses the next read or write, while the person's own tenant stays readable.
- An invite is single-use and expires, and redeeming it records who used it.
- The existing memory suite, the isolation tests and the twin-migration parity tests pass, with the new cases added rather than old ones relaxed.

---

## Alternatives Rejected

- **A second login bound to the owner's account (the swap)**: erases the joiner's own tenant and turns revocation into a loss of access instead of the end of a grant.
- **Per-agent and per-project grants**: deferred at the owner's word; whole-account sharing answers the actual need first.
- **A `tenant` argument on every tool**: no state to store, but it adds an argument to every operation and invites a wrong value on each call.
- **A signed invite token with no row**: cannot be revoked before use and leaves no record of who came in.
- **A generic config table for the selection**: one per-person value does not earn a table, and it becomes a second unowned home for facts.

---

**Full context**: [High Wizard plan (2026-10-28)](../../plans/2026-10-28-agent-memory-server-account-sharing.md)

---

**ADR Template for Architecture Decision Records**

*This document serves as a SPECIFICATION that tells implementation agents WHAT to build. The implementation protocol (High Wizard/Quick Wizard) will figure out HOW to build it.*
