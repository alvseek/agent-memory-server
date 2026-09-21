"""Template-version write gate — stamp parsing + per-type enforcement.

The four resource templates carry a ``template_version`` stamp; the loader reads it
live from the documents (no second registry), and ``check_template_version`` refuses
gated-type writes built against anything else. ``identity`` / ``user_profile`` have no
template and pass through.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from munnin.content.loader import TEMPLATE_BY_RECORD_TYPE, ContentLoader

REPO = Path(__file__).resolve().parents[2]
CF = REPO / "control-files"

_VERSION_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}$")


@pytest.fixture
def loader() -> ContentLoader:
    return ContentLoader(CF)


def test_all_four_live_templates_carry_a_version_shaped_stamp(
    loader: ContentLoader,
) -> None:
    versions = {
        rtype: loader.template_version(resource)
        for rtype, resource in TEMPLATE_BY_RECORD_TYPE.items()
    }
    assert set(versions) == {"episode", "reasoning", "emotional", "knowledge"}
    for rtype, version in versions.items():
        assert _VERSION_SHAPE.match(version), f"{rtype}: {version!r}"


def test_mapping_covers_exactly_the_four_gated_types() -> None:
    assert set(TEMPLATE_BY_RECORD_TYPE) == {
        "episode", "reasoning", "emotional", "knowledge",
    }


def _root_with(tmp_path: Path, name: str, body: str) -> ContentLoader:
    d = tmp_path / "procedures" / "memory" / "resources"
    d.mkdir(parents=True)
    (d / f"{name}.md").write_text(body, encoding="utf-8", newline="\n")
    return ContentLoader(tmp_path)


def test_missing_stamp_raises_value(tmp_path: Path) -> None:
    loader = _root_with(tmp_path, "episodic-entry-template", "# No Stamp Here\n")
    with pytest.raises(ValueError, match="no template_version stamp"):
        loader.template_version("episodic-entry-template")


def test_unknown_resource_raises_key(tmp_path: Path) -> None:
    loader = _root_with(tmp_path, "episodic-entry-template", "template_version: 1\n")
    with pytest.raises(KeyError):
        loader.template_version("does-not-exist")


def test_matching_version_passes(loader: ContentLoader) -> None:
    current = loader.template_version("episodic-entry-template")
    loader.check_template_version("episode", current)  # no raise


def test_missing_claim_is_refused(loader: ContentLoader) -> None:
    with pytest.raises(ValueError, match="template_version is required"):
        loader.check_template_version("episode", None)


def test_stale_claim_names_the_latest(loader: ContentLoader) -> None:
    latest = loader.template_version("reasoning-pattern-template")
    with pytest.raises(ValueError, match=f"latest is '{latest}'"):
        loader.check_template_version("reasoning", "2000-01-01-00-00")


def test_ungated_types_pass_through(loader: ContentLoader) -> None:
    loader.check_template_version("identity", None)  # no template, no claim needed
    loader.check_template_version("user_profile", None)


def test_unknown_record_type_passes_through_to_the_service(loader: ContentLoader) -> None:
    # the gate only knows templated types; an invalid type is the service's refusal,
    # not the gate's — so the gate must not fire first with a misleading message
    loader.check_template_version("bogus", None)
