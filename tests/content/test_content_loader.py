"""ContentLoader — composes memory procedures with the db backend + serves templates."""

from __future__ import annotations

import shutil
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
    assert "Append Sub-Episode" in text
    # the entry-block template is served as a separate Resource, NOT inlined in the prompt
    # (§ template seam) — its body must not leak onto the wire
    assert "Detailed Entry Template" not in text


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


def test_markdown_scaffold_excluded_from_resources(loader: ContentLoader) -> None:
    # the markdown file/index scaffold is markdown-backend-only, not a DB-world block template
    res = loader.list_resources()
    assert "episodic-memory-template" not in res
    assert len(res) == 4
    with pytest.raises(KeyError):
        loader.get_resource("episodic-memory-template")


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


# --- component inlining (the pre-seam stage) ---
#
# No procedure in the served set references a component today — only `awaken-agent` and
# `refresh-memory` do, and neither is served. So the shape is exercised on a synthetic
# control-files tree, which is what would break the day `awaken-agent` becomes the 10th
# Prompt. Both framework modules are copied in and imported from the tree, never stubbed,
# so this composes through the same single-homed logic the real submodule serves.


def _synthetic_root(tmp_path: Path) -> Path:
    """A minimal control-files tree whose served procedure inlines a component that
    brings a storage op of its own."""
    root = tmp_path / "control-files"
    proc = root / "procedures" / "memory"
    comp = root / "procedures" / "components"
    backends = proc / "storage-backends"
    for d in (proc, comp, backends):
        d.mkdir(parents=True, exist_ok=True)
    shutil.copy(CF / "procedures" / "memory" / "storage-backends" / "seam.py", backends)
    shutil.copy(CF / "procedures" / "components" / "inline.py", comp)

    (comp / "shared-fragment.md").write_text(
        "# Shared Fragment\n\nA component, not a standalone skill.\n\n---\n\n"
        "Do the shared thing (**§ shared-op**).\n",
        encoding="utf-8",
        newline="\n",
    )
    (proc / "update-episodic.md").write_text(
        "# Update Episodic\n\n"
        "Step 1 — [**Shared step**](components/shared-fragment.md)\n\n"
        "Step 2 — write it (**§ own-op**).\n\n"
        "## Storage Mechanics\n\nunsubstituted-placeholder\n",
        encoding="utf-8",
        newline="\n",
    )
    (backends / "db.md").write_text(
        "# DB backend\n\n"
        "## update-episodic\n\n### § own-op\n\nCall `insert(...)`.\n\n"
        "## shared-fragment\n\n### § shared-op\n\nCall `query(...)`.\n",
        encoding="utf-8",
        newline="\n",
    )
    return root


def test_component_is_inlined_and_brings_its_own_backend_ops(tmp_path: Path) -> None:
    text = ContentLoader(_synthetic_root(tmp_path)).get_prompt("update-episodic")

    # inlined at its reference point, link replaced by its label — the served Prompt is
    # self-contained and points at no file the client cannot reach
    assert "Do the shared thing" in text
    assert "components/shared-fragment.md" not in text
    assert "**Shared step**" in text

    # the substituted body is the procedure's own section PLUS its component's, so an op
    # arriving via the component resolves without being restated under the caller
    assert "insert(" in text  # ## update-episodic
    assert "query(" in text  # ## shared-fragment — absent under plain extract_section
    assert "unsubstituted-placeholder" not in text


def test_unresolvable_component_leaves_its_reference_visible(tmp_path: Path) -> None:
    """Nothing fails silently: an absent component keeps its link in the text rather
    than quietly dropping the step."""
    root = _synthetic_root(tmp_path)
    (root / "procedures" / "components" / "shared-fragment.md").unlink()

    text = ContentLoader(root).get_prompt("update-episodic")
    assert "components/shared-fragment.md" in text
    assert "insert(" in text  # the procedure's own section still substitutes
    assert "query(" not in text  # the component contributed nothing
