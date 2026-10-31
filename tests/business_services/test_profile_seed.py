"""The profile seed: what a first login writes, and what it must never write.

The claim under test is narrow and easy to get subtly wrong. A tenant born from a login
gets a profile carrying the provider's name, exactly once, and only when the provider
actually supplied a name — because a profile that exists with a blank name tells every
later agent that this person was asked and declined.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.identity_service import IdentityService
from munnin.business_services.memory_service import MemoryService
from munnin.business_services.profile_seed import USER_PROFILE_TEMPLATE, seed_profile
from munnin.data_repositories.identity_repository import SqliteIdentityRepository
from munnin.data_repositories.sqlite_memory_repository import SqliteMemoryRepository


def _memory(tmp_path: Path) -> MemoryService:
    db = tmp_path / "m.db"
    SqliteIdentityRepository(db).ensure_account(_account("alvi"))
    return MemoryService(SqliteMemoryRepository(db, user_id="alvi"), user_id="alvi")


def _account(user_id: str):
    from munnin.data_entities.identity import Account

    return Account(user_id=user_id)


def _service(tmp_path: Path, calls: list[tuple[str, str | None]]) -> IdentityService:
    def on_created(user_id: str, display_name: str | None) -> None:
        calls.append((user_id, display_name))

    return IdentityService(
        SqliteIdentityRepository(tmp_path / "m.db"), on_created=on_created
    )


# --- when the hook fires ---


def test_the_hook_fires_once_for_a_new_tenant_and_never_again(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []
    service = _service(tmp_path, calls)

    first = service.resolve("https://issuer.test", "roy", display_name="Roy")
    second = service.resolve("https://issuer.test", "roy", display_name="Roy")

    assert first == second
    assert calls == [(first, "Roy")]


def test_a_failing_hook_does_not_fail_the_login(tmp_path: Path) -> None:
    def boom(user_id: str, display_name: str | None) -> None:
        raise RuntimeError("the seed is broken")

    service = IdentityService(SqliteIdentityRepository(tmp_path / "m.db"), on_created=boom)
    assert service.resolve("https://issuer.test", "roy", display_name="Roy")


# --- what the seed writes ---


def test_the_seed_writes_the_three_line_profile(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    assert seed_profile(memory, "Roy") is True

    rows = memory.query(record_type="user_profile")
    assert len(rows) == 1
    body = rows[0]["content"]
    assert body == USER_PROFILE_TEMPLATE.format(name="Roy")
    assert "[USER-NAME]** = Roy" in body
    assert "[USER-PHILOSOPHY]** =" in body and "[USER-AGENT-VISION]** =" in body


def test_the_seed_writes_nothing_without_a_name(tmp_path: Path) -> None:
    """A profile with a blank name is a claim that this person was asked, and they were
    not. Leaving the profile absent keeps the first-run bootstrap alive."""
    memory = _memory(tmp_path)
    assert seed_profile(memory, None) is False
    assert memory.query(record_type="user_profile") == []


def test_the_seed_never_touches_an_authored_profile(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    memory.insert(
        scope="shared",
        record_type="user_profile",
        content="- **[USER-NAME]** = Alvi\n- **[USER-PHILOSOPHY]** = success feeling first\n",
        title="User Profile",
    )

    assert seed_profile(memory, "Somebody else") is False
    rows = memory.query(record_type="user_profile")
    assert len(rows) == 1
    assert "Alvi" in rows[0]["content"]
    assert "Somebody else" not in rows[0]["content"]


def test_a_seeded_profile_is_what_awakening_returns(tmp_path: Path) -> None:
    """The end the seed exists for: a brand-new tenant awakens with a name in hand."""
    memory = _memory(tmp_path)
    seed_profile(memory, "Roy")

    payload = memory.awaken("meta")
    profile = payload["shared"]["user_profile"]
    assert profile is not None
    assert "[USER-NAME]** = Roy" in profile["content"]
