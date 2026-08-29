"""Turn a verified token into the tenant it acts as.

The whole of Munnin's multi-tenancy rests on one function here. Everything upstream has
already established *that* the caller is who they say — this decides *whose memory* that
makes them, and it is the only place a tenant is ever chosen.

An unmapped pair creates a tenant rather than refusing one, because admission is owned by
the authorization server: its sign-up setting decides who may authenticate at all, and a
second gate here would have to agree with a dashboard forever with nothing reporting
divergence. Creation is logged loudly instead — a flag prevents a door you already
control, whereas a log tells you when it opened unexpectedly.
"""

from __future__ import annotations

from uuid import uuid4

from munnin.data_entities.identity import Account, UserIdentity
from munnin.data_repositories.identity_repository import IdentityRepository
from munnin.logger.logger import get_logger

_log = get_logger("identity")


class IdentityService:
    """Resolves ``(iss, sub)`` to an internal ``user_id``, creating the tenant on a miss."""

    def __init__(self, repo: IdentityRepository) -> None:
        self._repo = repo

    def resolve(
        self,
        iss: str,
        sub: str,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> str:
        """The tenant for this issuer-and-subject pair, created if it is new.

        ``email`` and ``display_name`` are stored on a *newly created* tenant only, as
        labels. They are never used to find one: an issuer may reassign an address to a
        different person, so matching on email could hand over somebody's memory."""
        existing = self._repo.find_user_id(iss, sub)
        if existing is not None:
            return existing

        user_id = uuid4().hex
        self._repo.ensure_account(
            Account(user_id=user_id, email=email, display_name=display_name)
        )
        self._repo.link_identity(UserIdentity(iss=iss, sub=sub, user_id=user_id))

        # Re-read rather than returning what we minted: two simultaneous first logins for
        # the same pair both reach here, and only one of their identity rows survives the
        # idempotent insert. The stored answer is the true one.
        settled = self._repo.find_user_id(iss, sub)
        resolved = settled if settled is not None else user_id

        # WARNING, not INFO: a tenant appearing is the event you would want to see even
        # on a server whose log level has been raised, because while sign-up is
        # invitation-only it should happen only when you invited somebody.
        _log.warning("new tenant created: user_id=%s iss=%s sub=%s", resolved, iss, sub)
        return resolved
