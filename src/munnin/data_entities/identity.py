"""Who a tenant is, and which login resolves to them.

Two entities, deliberately separate. ``Account`` is the tenant every memory record
ultimately belongs to; ``UserIdentity`` records that a particular authorization server
called them a particular name. Keeping them apart is what lets the issuer change without
touching a single memory record — a swap inserts a row here and rewrites nothing.

``Account.user_id`` keeps that column name rather than becoming ``account_id`` because
``agent``, ``shared_record`` and ``memory_record`` already carry ``user_id``, and not
rewriting them is the whole point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(kw_only=True)
class Account:
    """A tenant.

    ``email`` is a **label and a matching hint, never a key**. OpenID Connect permits an
    issuer to reassign an address to a different person over time, so resolving a tenant
    by email could hand one person's memory to another. Resolution goes through
    ``UserIdentity`` only."""

    user_id: str
    display_name: str | None = None
    email: str | None = None
    created_date: str | None = None


@dataclass(kw_only=True)
class UserIdentity:
    """One issuer's name for one person.

    Keyed on ``(iss, sub)`` because that pair is the only stable identifier OpenID
    Connect guarantees — a subject is unique only within the issuer that minted it, so
    two issuers may legitimately emit the same string for different people."""

    iss: str
    sub: str
    user_id: str
    linked_date: str | None = None
