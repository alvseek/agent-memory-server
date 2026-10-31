"""Who the current caller is acting as.

One seam, and the adapters ask it nothing else — they never learn where the answer came
from, which is what let the tenant move from a process-wide constant to a verified token
claim without a single handler changing shape.

Two implementations live here, and the second is deliberately hard to reach. A tenant is
normally chosen only from a token that has already been verified; the temporary static
resolver that carried the refactor through its middle phases was deleted so that no
code path reached a tenant any other way. ``LocalTenantResolver`` reintroduces a fixed
tenant for exactly one situation — local mode, ``MUNNIN_AUTH=off`` on a loopback public
URL — and ``build_app`` selects it only when ``build_auth`` has returned no provider,
which is the one place that guard is enforced. The test suite keeps a double of its own,
which is visibly a double and never shipped.

``TokenTenantResolver`` trusts the verification completely and deliberately — by the time
a tool body runs, an invalid token has already been refused at the transport, so a
resolver that re-checked would duplicate the guard rather than add one.
"""

from __future__ import annotations

from typing import Protocol

from fastmcp.server.dependencies import get_access_token

from munnin.business_services.identity_service import IdentityService
from munnin.business_services.sharing_service import SharingService, TenantAccessRevoked
from munnin.data_repositories.sharing_repository import SharingRepository

#: Re-exported: the refusal is raised by the sharing service, but the resolver is where a
#: reader looks for it, and both faces import it from here.
__all__ = [
    "LocalTenantResolver",
    "MissingTokenError",
    "TenantAccessRevoked",
    "TenantResolver",
    "TokenTenantResolver",
]


class TenantResolver(Protocol):
    """Answers "whose memory is this request acting on?" for the call in progress."""

    def current_user_id(self) -> str: ...

    def current_home_user_id(self) -> str: ...


class MissingTokenError(RuntimeError):
    """Raised when a tenant is asked for on a call that carries no verified token.

    This should be unreachable: the auth layer rejects an unauthenticated request before
    any handler runs. It exists so that if a route is ever added outside the guard, it
    fails loudly on the first call rather than quietly serving somebody a tenant.
    """


class TokenTenantResolver:
    """The tenant named by the verified token of the call in progress."""

    def __init__(self, identity: IdentityService, sharing: SharingRepository) -> None:
        self._identity = identity
        self._sharing = sharing

    def _claims(self) -> tuple[str, str, dict]:
        token = get_access_token()
        if token is None:
            raise MissingTokenError(
                "no verified token on this call — a handler is running outside the "
                "authentication guard"
            )
        claims = token.claims
        iss, sub = claims.get("iss"), claims.get("sub")
        if not iss or not sub:
            # A token that verified but names no subject cannot be resolved to a tenant,
            # and guessing one would be the exact failure the (iss, sub) key exists to
            # prevent. Refuse rather than fall back to anything.
            raise MissingTokenError(
                "verified token carries no issuer/subject pair, so it names no tenant"
            )
        return str(iss), str(sub), claims

    def current_home_user_id(self) -> str:
        """The tenant the caller's login belongs to, before any selection is applied.

        The membership tools read this one: it is what keeps them reachable while a bad
        selection is refusing every memory operation.
        """
        iss, sub, claims = self._claims()
        return self._identity.resolve(
            iss,
            sub,
            email=claims.get("email"),
            display_name=claims.get("name"),
        )

    def current_user_id(self) -> str:
        """The tenant this request acts on: the caller's home, or a selection still permitted.

        The check itself lives in ``SharingService.resolved_user_id`` so both faces call one
        implementation rather than each re-deriving it.
        """
        home = self.current_home_user_id()
        return SharingService(
            self._sharing,
            home_user_id=home,
            selected_user_id=self._sharing.find_active(home),
        ).resolved_user_id()


class LocalTenantResolver:
    """One fixed tenant for every call — local mode only.

    Shipped, unlike the test double, because a laptop running Munnin with no identity
    provider still needs an answer to "whose memory is this". It is constructed only by
    ``build_app`` and only after ``build_auth`` has accepted ``MUNNIN_AUTH=off``, which it
    does solely for a loopback public URL — so a deployment cannot arrive here through a
    missing setting, only by choosing local mode on a machine nobody else can reach.

    There is nobody else to switch to and no grant to consult, so both answers are the same
    constant. That is a property of local mode, not a shortcut.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def current_user_id(self) -> str:
        return self._user_id

    def current_home_user_id(self) -> str:
        return self._user_id
