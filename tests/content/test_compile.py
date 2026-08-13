"""compile — self-contained previews of every seam procedure x both backends.

The tool is a standalone script inside the control-files submodule (Munnin-agnostic),
so it is loaded here by file path rather than imported as a package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CF = REPO / "control-files"
_SCRIPT = CF / "procedures" / "setup-scripts" / "compile.py"

_spec = importlib.util.spec_from_file_location("cf_compile", _SCRIPT)
cc = importlib.util.module_from_spec(_spec)
sys.modules["cf_compile"] = cc  # dataclass field resolution needs the module registered
_spec.loader.exec_module(cc)


def test_discovers_only_real_seam_procedures() -> None:
    procs = {p.stem for p in cc._seam_procedures(CF / "procedures")}
    # the 10 seam-bearing procedures
    assert "add-reasoning" in procs
    assert "awaken-agent" in procs
    assert "wrap-up" in procs
    assert len(procs) == 10
    # the seam's own machinery must be excluded, even though it names the marker in prose
    assert "README" not in procs
    assert "markdown" not in procs
    assert "db" not in procs


def test_compiles_all_procedures_for_both_backends(tmp_path: Path) -> None:
    reports = cc.compile_all(CF, tmp_path)
    assert len(reports) == 20  # 10 procedures x 2 backends
    for r in reports:
        assert r.out_path.exists()
    files = {p.name for p in tmp_path.glob("*.md")}
    assert "add-reasoning.markdown.md" in files
    assert "add-reasoning.db.md" in files


def test_every_op_resolves_in_both_backends(tmp_path: Path) -> None:
    # the seam contract requires both backends to define every op a procedure references
    reports = cc.compile_all(CF, tmp_path)
    offenders = {(r.name, r.backend): r.unresolved_ops for r in reports if r.unresolved_ops}
    assert offenders == {}


def test_markdown_and_db_swap_the_right_mechanics(tmp_path: Path) -> None:
    cc.compile_all(CF, tmp_path)
    md = (tmp_path / "add-reasoning.markdown.md").read_text(encoding="utf-8")
    db = (tmp_path / "add-reasoning.db.md").read_text(encoding="utf-8")
    # markdown backend = file/shell mechanics; db backend = tool calls.
    # (assert on the mechanics, not the shared template appendix, which names both worlds)
    assert "agent-core-memory.md" in md
    assert 'powershell -c "[guid]' in md  # markdown-only generate-uuid shell op
    assert "insert(agent_id=" in db  # db-only persist tool call
    assert "insert(agent_id=" not in md


def test_template_inlined_and_reference_rewritten_to_anchor(tmp_path: Path) -> None:
    cc.compile_all(CF, tmp_path)
    md = (tmp_path / "add-reasoning.markdown.md").read_text(encoding="utf-8")
    # the template body is inlined as an appendix under an anchor-able heading
    assert "## Templates (inlined)" in md
    assert "### reasoning-pattern-template" in md
    # the in-body reference points to the in-doc anchor, not an external path
    assert "(#reasoning-pattern-template)" in md
    assert "resources/reasoning-pattern-template.md" not in md


def test_strict_exit_is_clean_on_healthy_tree(tmp_path: Path) -> None:
    rc = cc.main(["--content-root", str(CF), "--out", str(tmp_path), "--strict"])
    assert rc == 0
