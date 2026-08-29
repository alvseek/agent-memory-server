"""Who the current caller is acting as.

One seam, two implementations at different times. The adapters ask this and nothing else;
they never learn where the answer came from, which is what lets Phase 3 replace a
constant with a verified token claim without touching a single handler.

``StaticTenantResolver`` is **TEMPORARY** — it exists only so the suite stays green
between the tenancy refactor and the arrival of token verification, and it is deleted in
Step 3.4. It is the one path in this codebase by which a tenant can be chosen without a
token, and it must not outlive that step.
"""

from __future__ import annotations

from typing import Protocol


class TenantResolver(Protocol):
    """Answers "whose memory is this request acting on?" for the call in progress."""

    def current_user_id(self) -> str: ...


class StaticTenantResolver:
    """TEMPORARY (deleted in Step 3.4): always the configured tenant.

    Reproduces exactly the behaviour the server had before this refactor — one tenant for
    the whole process — so Phase 2 can move the *plumbing* without changing any
    observable behaviour, and the existing suite stays a valid check on that."""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def current_user_id(self) -> str:
        return self._user_id
