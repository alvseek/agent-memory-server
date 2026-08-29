"""Who the current caller is acting as.

One seam, and the adapters ask it nothing else — they never learn where the answer came
from, which is what let the tenant move from a process-wide constant to a verified token
claim without a single handler changing shape.

There is exactly one implementation here, and that is the point: a tenant can be chosen
only from a token that has already been verified. The temporary static resolver that
carried the refactor through its middle phases has been deleted, so no code path in this
server reaches a tenant any other way. The test suite keeps a double of its own, which is
visibly a double and never shipped.

``TokenTenantResolver`` trusts the verification completely and deliberately — by the time
a tool body runs, an invalid token has already been refused at the transport, so a
resolver that re-checked would duplicate the guard rather than add one.
"""

from __future__ import annotations

from typing import Protocol

from fastmcp.server.dependencies import get_access_token

from munnin.business_services.identity_service import IdentityService


class TenantResolver(Protocol):
    """Answers "whose memory is this request acting on?" for the call in progress."""

    def current_user_id(self) -> str: ...


class MissingTokenError(RuntimeError):
    """Raised when a tenant is asked for on a call that carries no verified token.

    This should be unreachable: the auth layer rejects an unauthenticated request before
    any handler runs. It exists so that if a route is ever added outside the guard, it
    fails loudly on the first call rather than quietly serving somebody a tenant.
    """


class TokenTenantResolver:
    """The tenant named by the verified token of the call in progress."""

    def __init__(self, identity: IdentityService) -> None:
        self._identity = identity

    def current_user_id(self) -> str:
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
        return self._identity.resolve(
            str(iss),
            str(sub),
            email=claims.get("email"),
            display_name=claims.get("name"),
        )
