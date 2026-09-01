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


def test_lists_served_prompts(loader: ContentLoader) -> None:
    names = loader.list_prompts()
    assert len(names) == 13
    assert "update-episodic" in names
    assert "wrap-up" in names
    assert "create-agent" in names
    assert "list-agents" in names
    # the awakening protocol is not a record, so it rides in a Prompt
    assert "awaken-agent" in names
    # a format reference with no storage seam: in the command set, so served — as-is
    assert "wait-options" in names
    # intentionally NOT served (the DB write is durable / markdown-recovery)
    assert "push-memory" not in names
    assert "pull-memory" not in names
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
    # db persistence op substituted in: a DB write is durable the moment it lands,
    # so the served prompt reports an outcome rather than performing a save
    assert "already durable" in text
    # markdown-only mechanics must NOT reach the wire — a Munnin client has no
    # git store to push, and the markdown backend resolves this op to /push-memory
    assert "/push-memory" not in text
    # the trailing footer note after the seam must survive the substitution
    assert "Working in a repo as well?" in text


def test_unknown_prompt_raises(loader: ContentLoader) -> None:
    with pytest.raises(KeyError):
        loader.get_prompt("does-not-exist")


def test_prompt_descriptions_are_distinct_and_read_from_the_procedures(
    loader: ContentLoader,
) -> None:
    described = {name: loader.describe_prompt(name) for name in loader.list_prompts()}
    assert len(described) == 13
    # a command menu is only readable if its rows differ — one templated sentence with
    # the name swapped in gives twelve entries that all say the same thing
    assert len(set(described.values())) == 13
    assert described["awaken-agent"] == "Load agent memory and activate a domain-specific agent."
    assert described["update-episodic"] == "Capture session context as rolling per-theme episodes."


def test_prompt_description_stops_before_the_storage_caveat(loader: ContentLoader) -> None:
    # every procedure names its storage backend in a *later* sentence, so this fails
    # loudly if the first-sentence cut ever stops working
    for name in loader.list_prompts():
        assert "storage backend" not in loader.describe_prompt(name)


def test_prompt_description_is_plain_text(loader: ContentLoader) -> None:
    # descriptions travel as a plain string, where `**bold**` arrives as literal asterisks
    for name in loader.list_prompts():
        description = loader.describe_prompt(name)
        assert "**" not in description
        assert "`" not in description
        assert "](" not in description
        assert "\n" not in description
        assert description == description.strip()


def test_describe_unknown_prompt_raises(loader: ContentLoader) -> None:
    with pytest.raises(KeyError):
        loader.describe_prompt("does-not-exist")


def test_prompt_with_no_prose_falls_back_to_naming_itself(tmp_path: Path) -> None:
    root = tmp_path / "control-files"
    proc = root / "procedures" / "memory"
    proc.mkdir(parents=True)
    _install_framework_modules(root)
    (proc / "update-episodic.md").write_text(
        "# Update Episodic\n", encoding="utf-8", newline="\n"
    )
    assert (
        ContentLoader(root).describe_prompt("update-episodic")
        == "Memory procedure 'update-episodic'."
    )


def test_every_prompt_has_a_title_from_its_own_heading(loader: ContentLoader) -> None:
    titles = {name: loader.title_prompt(name) for name in loader.list_prompts()}
    assert len(set(titles.values())) == 13
    assert titles["awaken-agent"] == "Awaken Agent"
    assert titles["wrap-up"] == "Wrap Up Session"
    # a title is a display name, never the slug it replaces
    for name, title in titles.items():
        assert title != name
        assert "**" not in title and "#" not in title


def test_every_procedure_declares_its_optional_argument(loader: ContentLoader) -> None:
    declared = {name: loader.argument_prompt(name) for name in loader.list_prompts()}
    # a format reference is read, never invoked with a subject — it takes nothing
    assert declared.pop("wait-options") is None
    for name, argument in declared.items():
        assert argument is not None, f"{name} declares no argument"
        arg_name, arg_help = argument
        # a parameter name has to be a legal python identifier or the signature won't build
        assert arg_name.isidentifier()
        assert arg_help


def test_arguments_substitute_only_when_supplied(loader: ContentLoader) -> None:
    bare = loader.get_prompt("awaken-agent")
    # the placeholder must survive an empty invocation, or a served prompt stops being
    # byte-identical to the command it mirrors
    assert "$ARGUMENTS" in bare
    assert loader.get_prompt("awaken-agent", None) == bare
    assert loader.get_prompt("awaken-agent", "") == bare

    filled = loader.get_prompt("awaken-agent", "software-architect")
    assert "$ARGUMENTS" not in filled
    assert "software-architect" in filled


def test_resource_titles_and_descriptions_come_from_the_templates(loader: ContentLoader) -> None:
    names = loader.list_resources()
    described = {n: loader.describe_resource(n) for n in names}
    titled = {n: loader.title_resource(n) for n in names}
    # the same defect the prompts had: one templated sentence per name tells a reader nothing
    assert len(set(described.values())) == len(names)
    assert described["knowledge-file-template"] == "The structure of a knowledge-base entry."
    assert titled["reasoning-pattern-template"] == "Reasoning Pattern Template"
    for n in names:
        assert "**" not in described[n] and "`" not in described[n]
        assert titled[n] != n


def test_describe_unknown_resource_raises(loader: ContentLoader) -> None:
    with pytest.raises(KeyError):
        loader.describe_resource("does-not-exist")
    with pytest.raises(KeyError):
        loader.title_resource("episodic-memory-template")  # excluded, not served


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


# --- discovery: the served set is the framework's command set, never a list kept here ---


def _install_framework_modules(root: Path) -> None:
    """The framework's own modules copied into a synthetic tree — imported, never stubbed,
    so a synthetic tree composes and discovers through the same single-homed logic."""
    proc = root / "procedures"
    backends = proc / "memory" / "storage-backends"
    comp = proc / "components"
    for d in (proc, backends, comp):
        d.mkdir(parents=True, exist_ok=True)
    shutil.copy(CF / "procedures" / "command_set.py", proc)
    shutil.copy(CF / "procedures" / "memory" / "storage-backends" / "seam.py", backends)
    shutil.copy(CF / "procedures" / "components" / "inline.py", comp)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_served_set_is_discovered_from_the_command_dirs(tmp_path: Path) -> None:
    """No name is listed anywhere: a file dropped into a command dir is served, one in the
    exclusion set is not, and one in a non-command dir (``components/``) never is."""
    root = tmp_path / "control-files"
    _install_framework_modules(root)
    proc = root / "procedures"
    _write(proc / "brand-new.md", "# Brand New\n\nA procedure nobody listed.\n")
    _write(proc / "memory" / "deeper-new.md", "# Deeper New\n\nAlso unlisted.\n")
    _write(proc / "push-memory.md", "# Push\n\nExcluded by policy.\n")
    _write(proc / "components" / "fragment.md", "# Fragment\n\nInlined, never served.\n")

    loader = ContentLoader(root)
    assert loader.list_prompts() == ["brand-new", "deeper-new"]
    assert loader.describe_prompt("brand-new") == "A procedure nobody listed."
    # no seam and no db backend in this tree: the core is served as-is
    assert loader.get_prompt("deeper-new") == "# Deeper New\n\nAlso unlisted.\n"
    with pytest.raises(KeyError):
        loader.get_prompt("push-memory")
    with pytest.raises(KeyError):
        loader.get_prompt("fragment")


def test_duplicate_command_stem_is_refused(tmp_path: Path) -> None:
    """A command is addressed by its stem alone, so two files sharing one could only be
    resolved by a precedence rule nobody stated — refuse rather than pick."""
    root = tmp_path / "control-files"
    _install_framework_modules(root)
    _write(root / "procedures" / "same.md", "# Same\n\nTop-level.\n")
    _write(root / "procedures" / "memory" / "same.md", "# Same\n\nNested.\n")
    with pytest.raises(ValueError, match="duplicate command stem"):
        ContentLoader(root).list_prompts()


def test_seamless_procedure_is_served_as_its_own_core(loader: ContentLoader) -> None:
    """``wait-options`` carries no ``## Storage Mechanics`` — a format reference with no
    storage dimension — so the served text is the file itself, on either backend."""
    served = loader.get_prompt("wait-options")
    source = (CF / "procedures" / "wait-options.md").read_text(encoding="utf-8")
    assert served == source
    assert "## Storage Mechanics" not in served


def test_lead_sentence_does_not_end_inside_a_parenthetical(loader: ContentLoader) -> None:
    # the WAIT Options reference opens with a question mark inside brackets; a sentence
    # boundary inside a parenthetical is not a sentence boundary
    described = loader.describe_prompt("wait-options")
    assert described.startswith(
        "Reusable format definition for WAIT Options (What Am I Thinking? Options)"
    )
    assert described.endswith("collecting an answer.")


def test_awaken_agent_prompt_stands_alone(loader: ContentLoader) -> None:
    """Prompt 12. ``awaken`` returns the memory; this Prompt carries the protocol for
    using it — so the served text has to work with no filesystem and no dangling links.

    Its ops arrive through an inlined component rather than a ``## awaken-agent`` backend
    section (the backend has none), which is the composition path no other served
    procedure takes.
    """
    text = loader.get_prompt("awaken-agent")
    # db mechanics arrived via the inlined component's own backend section
    assert "awaken(" in text
    assert "§ load-user-profile" in text
    assert "§ persist-user-profile" in text
    # seam scaffolding fully consumed
    assert "## Storage Mechanics" not in text
    assert "[STORAGE-BACKENDS-PATH]" not in text
    # components inlined, not pointed at — a served client cannot fetch control-files
    assert "](components/" not in text
    # markdown-path mechanics must not reach the wire: there are no files to Read here,
    # while the rule the sentence carries (never delegate the load) still must
    assert "Read tool" not in text
    assert "delegate it to a sub-agent" in text


# --- component inlining (the pre-seam stage) ---
#
# `awaken-agent` exercises this for real against the submodule (see the served-text test
# above); the synthetic tree here isolates the shape from that one procedure's content, so
# a change to the awakening protocol cannot quietly take the mechanism's only coverage
# with it. The framework modules are copied in and imported from the tree, never stubbed,
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
    _install_framework_modules(root)

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


def test_backend_preamble_reaches_every_seam_procedure() -> None:
    """The db backend opens every composed procedure with the one sentence none of them
    carried: what `<domain>` in its ops means. It arrives through the framework's own
    composer, so it reaches the served prompt, the tool and the HTTP face alike — and
    not `wait-options`, which has no seam to compose."""
    loader = ContentLoader(CF)
    marker = "`<domain>` in the ops below is the agent you are acting as"
    for name in ("update-episodic", "wrap-up", "awaken-agent"):
        text = loader.get_prompt(name)
        assert marker in text, name
        assert text.index(marker) < text.index("### §"), name  # ahead of the mechanics
    assert marker not in loader.get_prompt("wait-options")


def test_unresolvable_component_leaves_its_reference_visible(tmp_path: Path) -> None:
    """Nothing fails silently: an absent component keeps its link in the text rather
    than quietly dropping the step."""
    root = _synthetic_root(tmp_path)
    (root / "procedures" / "components" / "shared-fragment.md").unlink()

    text = ContentLoader(root).get_prompt("update-episodic")
    assert "components/shared-fragment.md" in text
    assert "insert(" in text  # the procedure's own section still substitutes
    assert "query(" not in text  # the component contributed nothing
