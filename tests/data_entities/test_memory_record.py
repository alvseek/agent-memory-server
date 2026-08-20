"""Entity guards — domain validation.

The `__shared__` sentinel this file once guarded no longer exists: fleet memory lives in
its own table with no owner column, so there is nothing for a sentinel to stand in for.
Its rejection is still asserted below, alongside the other illegal domains — a name that
was reserved for years may well be typed again, and it must fail as a *domain*, not
because a constant happens to remember it.
"""

from __future__ import annotations

import pytest

from munnin.data_entities.memory_record import validate_domain


@pytest.mark.parametrize("name", ["meta", "backend-nestjs", "uiux-designer", "aquazone"])
def test_valid_domains(name: str) -> None:
    assert validate_domain(name) == name


@pytest.mark.parametrize("name", ["__shared__", "shared", "a_b", "Shared", "with space", ""])
def test_invalid_domains_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        validate_domain(name)
