"""Who may act in which tenant, and the invitation that gets them there.

Three records, and one rule underneath them: a person's own tenant is theirs by
construction, so only access to somebody else's is ever stored. That is why
``TenantAccess`` describes a guest and why there is no role column in this module at
all. "Owner" is a fact about whose account it is, not a permission that can be granted
away, and keeping it structural is what makes a lockout impossible rather than merely
unlikely.

Dates are ISO-8601 strings with an explicit UTC offset, matching every other date in
this schema, so two of them compare correctly as plain strings.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The role a tenant reference carries. Only two exist, and neither is stored.
OWNER = "owner"
GUEST = "guest"


@dataclass(kw_only=True)
class TenantAccess:
    """One person's live or revoked access to somebody else's tenant.

    ``revoked_date`` rather than a deleted row, so a refusal can say *access was revoked*
    instead of *no such tenant*, and so re-granting revives the row that already exists
    instead of starting a history from zero.
    """

    tenant_user_id: str
    member_user_id: str
    granted_date: str
    revoked_date: str | None = None

    @property
    def live(self) -> bool:
        """Whether this grant is currently in force."""
        return self.revoked_date is None


@dataclass(kw_only=True)
class TenantInvite:
    """A bearer code that admits whoever redeems it to one tenant, once, until it expires."""

    code: str
    tenant_user_id: str
    created_by: str
    created_date: str
    expires_date: str
    used_by: str | None = None
    used_date: str | None = None
    revoked_date: str | None = None

    def is_live(self, now: str) -> bool:
        """Usable at ``now``: not used, not revoked, and not yet expired.

        All three are compared as strings, which is exact because every date here is the
        same ISO-8601 shape.
        """
        return (
            self.used_by is None
            and self.revoked_date is None
            and self.expires_date > now
        )


@dataclass(kw_only=True)
class TenantRef:
    """One entry in the list a caller may act in: their own tenant, or a granted one."""

    user_id: str
    role: str
    label: str | None = None
    active: bool = False
    #: True for a tenant the caller is still selecting but may no longer enter. It is
    #: reported rather than hidden, because a person whose access just ended should be able
    #: to see that the reason every call refuses is their current position, not a bug.
    revoked: bool = False

    @property
    def is_owner(self) -> bool:
        """Whether this is the caller's own tenant."""
        return self.role == OWNER
