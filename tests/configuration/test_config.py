"""The settings this work added, and what happens when they are absent.

Most decide security outcomes rather than behaviour: the two issuer names
(``MUNNIN_LOGTO_ENDPOINT`` and ``MUNNIN_AUTHKIT_DOMAIN``) decide *together* whether the
server starts at all, and ``MUNNIN_DOCS`` decides whether the API's shape is published to
anyone who asks. All fail safe when mistyped — no boot, and docs off — which is the
property worth pinning, because it is the reason a typo here is an inconvenience rather
than an exposure.

The issuer names are tested as a pair. Either one alone is enough to boot, so a test that
cleared only one would go on passing while describing a rule that no longer exists.

Only the new settings are covered. The four that predate this work have shipped unbroken
since P4, and testing them is a different job from this one.
"""

from __future__ import annotations

import pytest

from munnin.app import AuthNotConfiguredError, build_auth
from munnin.configuration.config import Config, load_config


def test_neither_issuer_is_invented_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No default is invented for either issuer — an absent one must stay absent."""
    monkeypatch.delenv("MUNNIN_LOGTO_ENDPOINT", raising=False)
    monkeypatch.delenv("MUNNIN_AUTHKIT_DOMAIN", raising=False)
    config = load_config()
    assert config.logto_endpoint == ""
    assert config.authkit_domain == ""


def test_no_issuer_at_all_stops_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pair that matters: absent config plus a refusal to start.

    Asserted together because either alone is harmless — an empty string is only
    dangerous if something downstream shrugs and carries on.
    """
    monkeypatch.delenv("MUNNIN_LOGTO_ENDPOINT", raising=False)
    monkeypatch.delenv("MUNNIN_AUTHKIT_DOMAIN", raising=False)
    with pytest.raises(AuthNotConfiguredError):
        build_auth(load_config())


@pytest.mark.parametrize("name", ["MUNNIN_LOGTO_ENDPOINT", "MUNNIN_AUTHKIT_DOMAIN"])
def test_either_issuer_alone_is_enough_to_boot(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """The swap's two ends: before Logto is added, and after AuthKit is dropped.

    Neither end is a degraded state, which is why both are asserted — the refusal above
    is about having *no* issuer, never about having only one.
    """
    monkeypatch.delenv("MUNNIN_LOGTO_ENDPOINT", raising=False)
    monkeypatch.delenv("MUNNIN_AUTHKIT_DOMAIN", raising=False)
    monkeypatch.setenv(name, "https://example.test")
    assert build_auth(load_config()) is not None


def test_the_issuers_and_base_url_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUNNIN_LOGTO_ENDPOINT", "https://example.logto.app")
    monkeypatch.setenv("MUNNIN_AUTHKIT_DOMAIN", "https://example.authkit.app")
    monkeypatch.setenv("MUNNIN_LOGTO_AUDIENCE", "https://example.test/api")
    monkeypatch.setenv("MUNNIN_PUBLIC_BASE_URL", "https://munnin.example.test")
    config = load_config()
    assert config.logto_endpoint == "https://example.logto.app"
    assert config.authkit_domain == "https://example.authkit.app"
    assert config.logto_audience == ("https://example.test/api",)
    assert config.public_base_url == "https://munnin.example.test"


def test_the_pinned_audience_is_empty_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty means "derive it from the resource URL", which is the normal case.

    A value here is only correct when Logto holds the API Identifier in some other form,
    so the default has to be the derived one rather than a guess at what was registered.
    """
    monkeypatch.delenv("MUNNIN_LOGTO_AUDIENCE", raising=False)
    assert load_config().logto_audience == ()


def test_more_than_one_audience_can_be_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Several identifiers have to be trusted together while the canonical one changes.

    A refresh token is frozen to its resource at issuance, so when the advertised
    identifier moves — as it did from the root, to ``/mcp/``, to ``/mcp`` — tokens minted
    against the earlier spellings stay alive until each client signs in again. The list
    is what lets the server accept all of them in the meantime; a single value would
    refuse every session that had not yet re-authenticated.
    """
    monkeypatch.setenv(
        "MUNNIN_LOGTO_AUDIENCE",
        "https://munnin.example.test/mcp, https://munnin.example.test/mcp/, "
        "https://munnin.example.test/",
    )
    assert load_config().logto_audience == (
        "https://munnin.example.test/mcp",
        "https://munnin.example.test/mcp/",
        "https://munnin.example.test/",
    )


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


# --- local mode ---------------------------------------------------------------------------


def test_auth_mode_defaults_to_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent means token — the deployed case, where nothing sets it, keeps auth on."""
    monkeypatch.delenv("MUNNIN_AUTH", raising=False)
    assert load_config().auth_mode == "token"
    assert Config().auth_mode == "token"


@pytest.mark.parametrize("value", ["off", "OFF", " off "])
def test_off_is_read_as_local_mode(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MUNNIN_AUTH", value)
    assert load_config().auth_mode == "off"


@pytest.mark.parametrize("value", ["", "on", "token", "false", "0", "of", "disabled", "none"])
def test_anything_else_keeps_token_mode(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A typo turns authentication on, never off — the same fail-safe as ``MUNNIN_DOCS``.

    ``of`` and ``none`` are the near-misses worth pinning: both look like an attempt to
    switch auth off, and both must leave it on.
    """
    monkeypatch.setenv("MUNNIN_AUTH", value)
    assert load_config().auth_mode == "token"


def test_public_base_url_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A public repo must not default to one deployment's hostname.

    Loopback is the only value local mode accepts, and the hosted config sets its own URL
    explicitly, so nothing deployed depends on this default.
    """
    monkeypatch.delenv("MUNNIN_PUBLIC_BASE_URL", raising=False)
    assert load_config().public_base_url == "http://127.0.0.1:8200"
    assert Config().public_base_url == "http://127.0.0.1:8200"
