"""The one profile row a tenant born from a first login starts with.

The store already distinguishes an *absent* profile from a *blank* one, and that
distinction is load-bearing: ``awaken`` returns ``None`` to mean "nobody has been asked
yet", which is what tells the awakening protocol to run its first-run bootstrap, while a
field left blank inside a present record means "asked, and deliberately blank". Seeding a
profile therefore makes a claim, so this writes one only when the login provider actually
supplied a name — with nothing to say, the honest state is still "nobody has been asked".

The rest of the record stays blank on purpose: the name comes from the provider, and the
philosophy and vision are things a person answers, not things a server infers.
"""

from __future__ import annotations

from munnin.business_services.memory_service import MemoryService

#: The three lines the framework's own profile template carries. Kept as one string so the
#: shape the seed produces and the shape a person edits cannot drift apart by accident.
USER_PROFILE_TEMPLATE = (
    "## AI Agent - User Profile\n\n"
    "- **[USER-NAME]** = {name}\n"
    "- **[USER-PHILOSOPHY]** =\n"
    "- **[USER-AGENT-VISION]** =\n"
)


def seed_profile(
    memory: MemoryService, display_name: str | None, *, title: str = "User Profile"
) -> bool:
    """Write the starting profile for a new tenant, unless there is nothing honest to write.

    Returns whether a row was written. An existing profile is never touched: the caller has
    authored it, and an issuer's claim is not authoritative over that. The check and the
    write are two steps rather than one transaction, so two simultaneous first logins can
    race — the loser's insert fails on the one-profile-per-tenant index and is caught by the
    caller, which is the same outcome a transaction would produce with less machinery.
    """
    if not display_name:
        return False
    if memory.query(record_type="user_profile"):
        return False
    memory.insert(
        scope="shared",
        record_type="user_profile",
        content=USER_PROFILE_TEMPLATE.format(name=display_name),
        title=title,
    )
    return True
