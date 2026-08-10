"""Entity guards — the shared sentinel + domain validation (SP-1 Step 1.1)."""

from __future__ import annotations

import pytest

from munnin.data_entities.memory_record import (
    SHARED_AGENT_ID,
    validate_domain,
)


def test_shared_sentinel_is_not_a_legal_domain() -> None:
    # underscores fail the kebab rule, so no agent can ever collide with it
    assert SHARED_AGENT_ID == "__shared__"
    with pytest.raises(ValueError):
        validate_domain(SHARED_AGENT_ID)


@pytest.mark.parametrize("name", ["meta", "backend-nestjs", "uiux-designer", "aquazone"])
def test_valid_domains(name: str) -> None:
    assert validate_domain(name) == name


@pytest.mark.parametrize("name", ["__shared__", "shared", "a_b", "Shared", "with space", ""])
def test_invalid_domains_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        validate_domain(name)
