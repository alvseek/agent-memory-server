"""The three settings this work added, and what happens when they are absent.

Two of them decide security outcomes rather than behaviour: ``MUNNIN_AUTHKIT_DOMAIN``
decides whether the server starts at all, and ``MUNNIN_DOCS`` decides whether the API's
shape is published to anyone who asks. Both fail safe when mistyped — no boot, and docs
off — which is the property worth pinning, because it is the reason a typo here is an
inconvenience rather than an exposure.

Only the new settings are covered. The four that predate this work have shipped unbroken
since P4, and testing them is a different job from this one.
"""

from __future__ import annotations

import pytest

from munnin.app import AuthNotConfiguredError, build_auth
from munnin.configuration.config import Config, load_config


def test_the_issuer_is_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No default is invented for the issuer — an absent one must stay absent."""
    monkeypatch.delenv("MUNNIN_AUTHKIT_DOMAIN", raising=False)
    assert load_config().authkit_domain == ""


def test_an_unset_issuer_stops_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pair that matters: absent config plus a refusal to start.

    Asserted together because either alone is harmless — an empty string is only
    dangerous if something downstream shrugs and carries on.
    """
    monkeypatch.delenv("MUNNIN_AUTHKIT_DOMAIN", raising=False)
    with pytest.raises(AuthNotConfiguredError):
        build_auth(load_config())


def test_the_issuer_and_base_url_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUNNIN_AUTHKIT_DOMAIN", "https://example.authkit.app")
    monkeypatch.setenv("MUNNIN_PUBLIC_BASE_URL", "https://munnin.example.test")
    config = load_config()
    assert config.authkit_domain == "https://example.authkit.app"
    assert config.public_base_url == "https://munnin.example.test"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
def test_docs_can_be_turned_on(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MUNNIN_DOCS", value)
    assert load_config().docs_enabled is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", " true"])
def test_anything_else_leaves_docs_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Including the near-misses.

    ``off`` and ``maybe`` are the honest cases — neither is in the accepted set, so both
    mean off. `` true`` with a leading space is the one worth pinning: it is what a typo
    in a compose file looks like, and it must not read as enabled.
    """
    monkeypatch.setenv("MUNNIN_DOCS", value)
    assert load_config().docs_enabled is False


def test_docs_are_off_when_the_variable_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployed case: nothing sets it, so the schema stays private by omission."""
    monkeypatch.delenv("MUNNIN_DOCS", raising=False)
    assert load_config().docs_enabled is False
    assert Config().docs_enabled is False
