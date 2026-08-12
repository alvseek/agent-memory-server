"""ContentLoader — composes memory procedures with the db backend + serves templates."""

from __future__ import annotations

from pathlib import Path

import pytest

from munnin.content.loader import ContentLoader

REPO = Path(__file__).resolve().parents[2]
CF = REPO / "control-files"


@pytest.fixture
def loader() -> ContentLoader:
    return ContentLoader(CF)


def test_lists_nine_prompts(loader: ContentLoader) -> None:
    names = loader.list_prompts()
    assert len(names) == 9
    assert "update-episodic" in names
    assert "wrap-up" in names
    # intentionally NOT served (git-era / already a tool)
    assert "awaken-agent" not in names
    assert "push-memory" not in names
    assert "refresh-memory" not in names


def test_prompt_composes_db_mechanics(loader: ContentLoader) -> None:
    text = loader.get_prompt("update-episodic")
    # db tools present (from the substituted db backend section)
    assert "insert(" in text
    assert "query(" in text
    # markdown-only mechanics must NOT reach the wire
    assert "MOVE-TO-TODAY" not in text
    assert "episodic-memory-template.md" not in text
    assert "date '+%Y-%m-%d %H:%M'" not in text
    # semantic core retained
    assert "carry-forward" in text.lower()
    assert "Detailed Entry Template" in text


def test_orchestrator_prompt_composes_and_keeps_footer(loader: ContentLoader) -> None:
    text = loader.get_prompt("wrap-up")
    assert "query(" in text  # db read op substituted in
    # the trailing footer note after the seam must survive the substitution
    assert "Saving work to git too?" in text


def test_unknown_prompt_raises(loader: ContentLoader) -> None:
    with pytest.raises(KeyError):
        loader.get_prompt("does-not-exist")


def test_resources_include_block_templates(loader: ContentLoader) -> None:
    res = loader.list_resources()
    for stem in (
        "episodic-entry-template",
        "reasoning-pattern-template",
        "emotional-moment-template",
        "knowledge-file-template",
    ):
        assert stem in res


def test_get_resource_returns_body(loader: ContentLoader) -> None:
    body = loader.get_resource("episodic-entry-template")
    assert "Detailed Entry Template" in body


def test_unknown_resource_raises(loader: ContentLoader) -> None:
    with pytest.raises(KeyError):
        loader.get_resource("nope")


def test_missing_submodule_is_graceful() -> None:
    loader = ContentLoader(Path("does/not/exist"))
    assert loader.available() is False
    assert loader.list_prompts() == []
    assert loader.list_resources() == []
