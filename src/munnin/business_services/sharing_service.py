"""The rules of account sharing: who may enter which tenant, and who may invite whom.

One service, holding every rule, so that no adapter has to know any of them. The two
three-way decisions worth stating out loud:

**Ownership is structural.** You own your own tenant and nothing else. There is no role
column to check, because access to somebody else's tenant *is* the grant — so "am I the
owner of the tenant I am acting on" is the question "is this my own tenant", and the
answer cannot be revoked from you.

**The selection is not the permission.** A person may sit in a tenant whose access has
since been revoked; what stops them reading it is the resolver's check on every call, not
this service. That is deliberate: it keeps the way *out* of a bad selection (``use_tenant``)
reachable while every memory operation is refusing.

Refusals are typed so the adapters can map them to a status without parsing prose: a
missing or revoked permission is 403, a bad or ambiguous invitation is 400.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from munnin.data_entities.sharing import GUEST, OWNER, TenantInvite, TenantRef
from munnin.data_repositories.sharing_repository import SharingRepository

#: How long an invitation stays usable. Long enough to survive a message sitting unread
#: over a weekend, short enough that a leaked code is not a standing key.
INVITE_DAYS = 7


class SharingError(RuntimeError):
    """Base class for a refusal a caller can act on."""


class NotOwner(SharingError):
    """The caller is not acting in a tenant they own."""


class NotPermitted(SharingError):
    """The caller has no live access to the tenant they named."""


class BadInvite(SharingError):
    """The invitation is unknown, used, revoked, expired, or names the caller's own tenant."""


class TenantAccessRevoked(NotPermitted):
    """The remembered selection names a tenant this caller may no longer enter.

    Deliberately loud rather than a quiet fallback to the caller's own tenant. Falling back
    would serve the wrong memory while looking like a successful call, and the mistake would
    be invisible in exactly the session where it matters: the one after somebody's access
    ends. Subclasses ``NotPermitted`` so every adapter maps it with one rule, and the
    message names the tenant and the way out, which stays reachable because the membership
    tools resolve the home tenant instead of this one.
    """

    def __init__(self, tenant_user_id: str, label: str | None) -> None:
        self.tenant_user_id = tenant_user_id
        self.label = label
        named = f"{label!r} ({tenant_user_id})" if label else repr(tenant_user_id)
        super().__init__(
            f"access to {named} was revoked, so this call cannot reach it; call use_tenant "
            "to return to your own account"
        )


class AmbiguousLabel(SharingError):
    """A label matched more than one tenant, so it names nothing."""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _until(days: int) -> str:
    return (datetime.now(tz=UTC) + timedelta(days=days)).isoformat(timespec="seconds")


class SharingService:
    """One caller's view of the sharing rules.

    ``home_user_id`` is the tenant their login resolves to. ``selected_user_id`` is what the
    store remembers they chose, which may name a tenant they can no longer enter; this
    service reports that honestly rather than hiding it.
    """

    def __init__(
        self,
        repo: SharingRepository,
        *,
        home_user_id: str,
        selected_user_id: str | None = None,
    ) -> None:
        self._repo = repo
        self._home = home_user_id
        self._selected = selected_user_id

    # --- where am I ---

    @property
    def home_user_id(self) -> str:
        return self._home

    @property
    def acting_user_id(self) -> str:
        """The tenant the caller is acting in, which is the one every rule reads."""
        return self._selected or self._home

    def caller_block(self) -> dict[str, object]:
        """Who is signed in, for the ``awaken`` payload.

        Deliberately the *home* tenant rather than the acting one: the memory belongs to
        the account being read, and the human reading it is somebody else. Both facts are
        true at once, and a payload that reported only one of them would be lying about
        the other.
        """
        return {
            "user_id": self._home,
            "display_name": self._label(self._home),
            "is_guest": self.acting_user_id != self._home,
        }

    def _label(self, user_id: str) -> str | None:
        return self._repo.account_label(user_id)

    def list_tenants(self) -> list[TenantRef]:
        """The caller's own tenant first, then every tenant they may still enter.

        A selection that is no longer permitted is listed too, marked ``revoked`` and
        ``active``: the caller is genuinely still standing there, and hiding it leaves a
        person whose access just ended with no visible reason for the refusals and no
        statement of where they are.
        """
        refs = [
            TenantRef(
                user_id=self._home,
                role=OWNER,
                label=self._label(self._home),
                active=self.acting_user_id == self._home,
            )
        ]
        for access in self._repo.grants_for(self._home):
            if not access.live:
                continue
            refs.append(
                TenantRef(
                    user_id=access.tenant_user_id,
                    role=GUEST,
                    label=self._label(access.tenant_user_id),
                    active=self.acting_user_id == access.tenant_user_id,
                )
            )
        if self._selected and self._selected != self._home:
            live = {ref.user_id for ref in refs}
            if self._selected not in live:
                refs.append(
                    TenantRef(
                        user_id=self._selected,
                        role=GUEST,
                        label=self._label(self._selected),
                        active=True,
                        revoked=True,
                    )
                )
        return refs

    def use_tenant(self, tenant: str | None) -> TenantRef:
        """Select the tenant to act in. ``None`` or one's own tenant returns to the default."""
        if tenant is None or tenant == "" or tenant == self._home:
            self._repo.set_active(self._home, None)
            self._selected = None
            return TenantRef(
                user_id=self._home, role=OWNER, label=self._label(self._home), active=True
            )

        permitted = {
            ref.user_id: ref for ref in self.list_tenants() if not ref.revoked
        }

        chosen = permitted.get(tenant)
        if chosen is None:
            by_label = [ref for ref in permitted.values() if ref.label == tenant]
            if len(by_label) > 1:
                labels = ", ".join(sorted(ref.user_id for ref in by_label))
                raise AmbiguousLabel(
                    f"the label {tenant!r} names more than one tenant ({labels}); pass the id"
                )
            chosen = by_label[0] if by_label else None

        if chosen is None:
            raise NotPermitted(self._refusal(tenant))

        if chosen.user_id == self._home:
            # "Act as yourself" is the absence of a selection, not a selection naming
            # yourself: one representation, so nothing downstream has two cases to handle.
            self._repo.set_active(self._home, None)
            self._selected = None
            return TenantRef(
                user_id=self._home, role=OWNER, label=self._label(self._home), active=True
            )

        self._repo.set_active(self._home, chosen.user_id)
        self._selected = chosen.user_id
        return TenantRef(
            user_id=chosen.user_id, role=chosen.role, label=chosen.label, active=True
        )

    def _refusal(self, tenant: str) -> str:
        """Say which kind of no this is: revoked access reads very differently from a typo."""
        for access in self._repo.grants_for(self._home):
            if tenant in (access.tenant_user_id, self._label(access.tenant_user_id)):
                if not access.live:
                    return (
                        f"access to {tenant!r} was revoked; call use_tenant to go back to "
                        "your own account"
                    )
        return f"no tenant called {tenant!r} is open to you"

    def resolved_user_id(self) -> str:
        """The tenant a memory call may act on: the home tenant, or a selection still permitted.

        One implementation, called by both faces, so the MCP and HTTP answers cannot drift.
        It refuses rather than falling back, and the refusal subclasses ``NotPermitted`` so
        every adapter maps it with the same rule.
        """
        if not self._selected or self._selected == self._home:
            return self._home
        access = self._repo.find_access(self._selected, self._home)
        if access is None or not access.live:
            raise TenantAccessRevoked(self._selected, self._label(self._selected))
        return self._selected

    # --- who may grant ---

    def _require_owner(self) -> str:
        acting = self.acting_user_id
        if acting != self._home:
            raise NotOwner(
                "only the owner of a tenant may change who has access to it, and you are "
                "acting in somebody else's; call use_tenant to return to your own first"
            )
        return acting

    def list_members(self) -> list[dict[str, object]]:
        """Everyone with access to the tenant being acted on, the owner included."""
        tenant = self.acting_user_id
        rows: list[dict[str, object]] = [
            {
                "user_id": tenant,
                "role": OWNER,
                "label": self._label(tenant),
                "granted_date": None,
            }
        ]
        for access in self._repo.members_of(tenant):
            if not access.live:
                continue
            rows.append(
                {
                    "user_id": access.member_user_id,
                    "role": GUEST,
                    "label": self._label(access.member_user_id),
                    "granted_date": access.granted_date,
                }
            )
        return rows

    def create_invite(self, days: int = INVITE_DAYS) -> TenantInvite:
        """Mint a single-use code for the tenant being acted on, which must be the caller's."""
        tenant = self._require_owner()
        return self._repo.create_invite(
            TenantInvite(
                code=secrets.token_urlsafe(12),
                tenant_user_id=tenant,
                created_by=self._home,
                created_date=_now(),
                expires_date=_until(days),
            )
        )

    def revoke_invite(self, code: str) -> None:
        """Retire an unused code before it is redeemed."""
        self._require_owner()
        if not self._repo.revoke_invite(code):
            raise BadInvite(
                "that invitation does not exist, was already used, or was already revoked"
            )

    def revoke_member(self, member_user_id: str) -> None:
        """End somebody's access to the tenant being acted on."""
        tenant = self._require_owner()
        if member_user_id == tenant:
            raise BadInvite("that is your own account; it needs no access and cannot be revoked")
        if not self._repo.revoke(tenant, member_user_id):
            raise NotPermitted(f"{member_user_id!r} has no live access to this account")

    # --- joining ---

    def redeem(self, code: str) -> dict[str, object]:
        """Join the tenant an invitation names. Does not switch the caller into it."""
        if not self._repo.redeem(code, self._home):
            invite = self._repo.find_invite(code)
            if invite is None:
                raise BadInvite("that invitation does not exist")
            if invite.tenant_user_id == self._home:
                raise BadInvite("that invitation is for the account you already own")
            if invite.used_by is not None:
                raise BadInvite("that invitation has already been used")
            if invite.revoked_date is not None:
                raise BadInvite("that invitation was revoked")
            raise BadInvite("that invitation has expired")

        invite = self._repo.find_invite(code)
        assert invite is not None  # noqa: S101 — just redeemed
        return {
            "tenant_user_id": invite.tenant_user_id,
            "label": self._label(invite.tenant_user_id),
            "role": GUEST,
        }
