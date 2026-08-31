"""Serves framework memory procedures/templates as data from the control-files submodule.

Procedures are served as MCP **Prompts** (the "how-to" an agent reads before calling
the data tools) and templates as MCP **Resources** — and both again through tools
(``read_procedure`` / ``read_resource``), the one primitive an agent may invoke on its
own. Content is read **live** from the
submodule on each request — single source of truth, no re-import on edit. That extends
to the one-line description a client shows for each Prompt, which is the procedure's own
opening sentence rather than an authored copy that could drift from it.

Each served procedure is storage-agnostic (a semantic core + a ``## Storage Mechanics``
seam). ``get_prompt`` composes the core with the **db** backend section so a Munnin
client gets DB-tool mechanics; the native markdown mechanics never reach the wire.
``push``/``pull``/``refresh``-memory are not served: the DB write is durable, so there
is nothing to push or pull, and recovering after compaction is another ``awaken`` call
rather than a procedure. ``awaken-agent`` **is** served — ``awaken`` returns the memory,
but the protocol for processing it (the phased identity load, the load-integrity check,
the first-run user-profile ask) is not a record, so it rides in the Prompt.

A procedure may also reference **components** — shared fragments under
``procedures/components/`` that are inlined at their reference point so the delivered
Prompt is self-contained (it never points at a file the client cannot reach). Inlining
runs **before** the seam, because an ``§ op`` arriving inside a component has to be part
of the body the backend section is composed for. Every definition this takes — which
files are procedures, how a component inlines, how the seam composes — is imported from
the framework's own modules through ``seam_bridge``, the same ones
``compile-procedures.py`` runs, so an installed slash command and a served Prompt cannot
drift: there is no second copy to keep in step.
"""

from __future__ import annotations

import re
from pathlib import Path

from munnin.content.seam_bridge import command_set, component_inline, seam_compose
from munnin.logger.logger import get_logger

_log = get_logger("content.loader")

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_EMPHASIS = re.compile(r"\*\*|\*|`")
_OPENERS, _CLOSERS, _TERMINATORS = "([", ")]", ".!?"


def _first_sentence(paragraph: str) -> str:
    """``paragraph`` up to its first sentence terminator — outside any parenthetical.

    A ``.``, ``!`` or ``?`` ends the sentence only when followed by whitespace or the end,
    and never inside ``(...)`` or ``[...]``: a question mark in a bracketed aside is part
    of the sentence, not the end of it.
    """
    depth = 0
    for i, ch in enumerate(paragraph):
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth = max(0, depth - 1)
        elif ch in _TERMINATORS and depth == 0:
            if i + 1 == len(paragraph) or paragraph[i + 1].isspace():
                return paragraph[: i + 1]
    return paragraph

# The served procedures are the framework's command set (``procedures/command_set.py``,
# read through the bridge) minus these. Not served because the DB write is durable —
# there is nothing to push or pull — and recovering after compaction is another ``awaken``
# call rather than a procedure. This is the server's only say over what the framework
# defines: a procedure added to control-files is served on the next request, unlisted.
_EXCLUDED_PROCEDURES = frozenset({"pull-memory", "push-memory", "refresh-memory"})
_PROCEDURES_DIR = "procedures"
# Served procedure -> its single optional argument, as (name, description). Every one is
# optional because each procedure has an ask-if-missing branch, so declaring the argument
# adds a slot without making anything stricter. Authored rather than derived: the
# ``## Arguments`` sections are prose bullets in varying shapes and `wrap-up` has none at
# all, so parsing them would be a heuristic over data that is not deterministic.
_PROMPT_ARGUMENTS: dict[str, tuple[str, str]] = {
    "update-episodic": ("mode", "`new` to force a new episode instead of appending"),
    "add-reasoning": ("context", "the reasoning pattern to document; asks if omitted"),
    "update-emotional": ("moment_type", "happy, sad, frustrated or bonding; asks if omitted"),
    "update-knowledge": ("context", "the knowledge to document; asks if omitted"),
    "load-episodic": ("keyword", "match episodes by keyword; lists the most recent if omitted"),
    "load-knowledge": ("keyword", "match entries by keyword; lists all if omitted"),
    "archive-old-memories": ("scope", "episodic, emotional or all; asks if omitted"),
    "update-memory": ("mode", "`fresh` re-evaluates the whole session, `new` forces a new episode"),
    "wrap-up": ("mode", "`fresh` to re-evaluate the whole session rather than the delta"),
    "create-agent": ("domain", "kebab domain for the new agent; asks if omitted"),
    "list-agents": ("keyword", "filter agents by domain or role"),
    "awaken-agent": ("domain", "the agent domain to awaken; asks if omitted"),
}
_ARGUMENTS_PLACEHOLDER = "$ARGUMENTS"
_DB_BACKEND = "procedures/memory/storage-backends/db.md"
_TEMPLATES_DIR = "procedures/memory/resources"
_COMPONENTS_DIR = "procedures/components"
# Markdown-only file/index scaffold — used by the markdown backend's create-episode `cp`,
# NOT a DB-world block template. Not served as a resource (a Munnin client never cp's a file).
_RESOURCE_EXCLUDE = {"episodic-memory-template"}


def _lead_sentence(text: str) -> str:
    """The first sentence of a procedure's opening paragraph, as plain prose.

    Every procedure opens with its ``#`` title and then a paragraph whose first
    sentence says what the procedure is for; the storage-backend caveat is always a
    later sentence, so stopping at the first one drops the part no client needs.
    Markdown emphasis and links are flattened because this text is delivered as a
    plain description, where ``**bold**`` would arrive as literal asterisks.

    Returns ``""`` when there is no prose paragraph to read.
    """
    body = text.replace("\r\n", "\n")
    for block in body.split("\n\n"):
        paragraph = " ".join(block.split())
        if not paragraph or paragraph.startswith("#"):
            continue
        sentence = _first_sentence(paragraph)
        return _MD_EMPHASIS.sub("", _MD_LINK.sub(r"\1", sentence)).strip()
    return ""


def _h1_title(text: str) -> str:
    """The document's own `#` heading, as a display title.

    Derived rather than authored for the same reason the description is: the heading is
    what the document calls itself, so the two cannot drift, and a title that reads badly
    is a signal to fix the heading rather than to keep a second name beside it.
    """
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("# "):
            return _MD_EMPHASIS.sub("", _MD_LINK.sub(r"\1", line[2:])).strip()
    return ""


class ContentLoader:
    """Reads + composes served framework content from the control-files submodule."""

    def __init__(self, content_root: Path) -> None:
        self._root = content_root

    def available(self) -> bool:
        """True when the control-files submodule is present."""
        return self._root.exists()

    def root(self) -> Path:
        return self._root

    # --- prompts (memory procedures, composed with the db backend) ---

    def _procedures(self) -> dict[str, Path]:
        """The served procedures, name → source file, discovered on every call.

        The set is the framework's own command set (``procedures/command_set.py``, imported
        through the bridge — never a list kept here) minus ``_EXCLUDED_PROCEDURES``. Read
        live, like the content itself: a file that appears is served, a file that goes is
        not, and neither needs a server edit. An absent submodule yields nothing rather
        than failing, so a server without content still boots.
        """
        if not self.available():
            return {}
        commands = command_set(str(self._root))
        found = commands.command_procedures(self._root / _PROCEDURES_DIR)
        return {p.stem: p for p in found if p.stem not in _EXCLUDED_PROCEDURES}

    def _procedure_path(self, name: str) -> Path:
        """The source file of a served procedure. Raises ``KeyError`` for any other name."""
        try:
            return self._procedures()[name]
        except KeyError:
            raise KeyError(f"unknown prompt: {name}") from None

    def list_prompts(self) -> list[str]:
        """The served procedure names."""
        return sorted(self._procedures())

    def describe_prompt(self, name: str) -> str:
        """A one-line purpose for a served procedure, read from the procedure itself.

        Descriptions are what a client shows in its command menu, so twelve procedures
        sharing one templated sentence leaves the menu unable to tell them apart.
        Reading each procedure's own opening sentence fixes that and keeps the two from
        drifting: editing the procedure is the only way to change what clients are told
        about it, and there is no second copy to forget.

        Falls back to naming the procedure when it carries no prose to read. Raises
        ``KeyError`` for an unknown prompt name, as ``get_prompt`` does.
        """
        lead = _lead_sentence(self._procedure_path(name).read_text(encoding="utf-8"))
        return lead or f"Memory procedure '{name}'."

    def title_prompt(self, name: str) -> str:
        """A display title for a served procedure, taken from its own `#` heading.

        Clients show this instead of the hyphenated slug, so a menu reads as sentences
        rather than filenames. Falls back to the slug when the document has no heading.
        """
        return _h1_title(self._procedure_path(name).read_text(encoding="utf-8")) or name

    def argument_prompt(self, name: str) -> tuple[str, str] | None:
        """This procedure's single optional argument as ``(name, description)``.

        ``None`` when the procedure takes none. Every declared argument is optional: each
        procedure asks for what it needs when invoked without one, so the slot only ever
        saves a round trip.
        """
        return _PROMPT_ARGUMENTS.get(name)

    def _inlined(self, text: str) -> tuple[str, tuple[str, ...]]:
        """Inline every component reference; returns ``(text, components used)``.

        A component that cannot be resolved leaves its reference visible in the text
        (``inline.py`` never fails silently) and is logged — a served Prompt carrying a
        dangling link is a real defect, and there is no user on this side to tell.
        """
        inline = component_inline(str(self._root))
        text, missing, used = inline.inline_components(text, self._root / _COMPONENTS_DIR)
        if missing:
            _log.warning("unresolved component references: %s", ", ".join(missing))
        return text, tuple(dict.fromkeys(used))  # de-duplicated, order preserved

    def get_prompt(self, name: str, arguments: str | None = None) -> str:
        """Return the composed procedure, with ``arguments`` filled in when one is given.

        Every procedure carries a ``$ARGUMENTS`` placeholder that an installed slash
        command fills from what the user typed; a served Prompt fills it the same way so
        the two stay equivalent. **Substitution happens only when an argument is actually
        supplied** — an empty invocation leaves the placeholder standing, which keeps a
        no-argument served Prompt byte-identical to the command it mirrors.
        """
        text = self._compose_prompt(name)
        return text.replace(_ARGUMENTS_PLACEHOLDER, arguments) if arguments else text

    def _compose_prompt(self, name: str) -> str:
        """Return the procedure with its components inlined and its db backend section
        substituted in.

        The backend body is this procedure's own ``## [procedure]`` section plus a
        ``## [component]`` section for each component inlined into it, so ops arriving
        via a component resolve without being restated under every caller.

        Falls back to the inlined core if the procedure has no ``## Storage Mechanics``
        marker or the db backend defines nothing for it. Raises ``KeyError`` for an
        unknown prompt name.
        """
        path = self._procedure_path(name)
        # inline first: a component may be what brings this procedure's ops
        core, components = self._inlined(path.read_text(encoding="utf-8"))
        db_path = self._root / _DB_BACKEND
        if not db_path.exists():
            return core
        compose = seam_compose(str(self._root))
        try:
            section = compose.compose_backend_section(
                db_path.read_text(encoding="utf-8"), name, components
            )
            composed = compose.substitute_storage_mechanics(core, section)
        except KeyError:
            # No db section for this procedure, or no marker to swap — serve the core.
            return core
        # a backend section may carry component references of its own
        return self._inlined(composed)[0]

    # --- resources (templates, verbatim) ---

    def list_resources(self) -> list[str]:
        """The served template names (file stems under ``procedures/memory/resources/``)."""
        d = self._root / _TEMPLATES_DIR
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.md") if p.stem not in _RESOURCE_EXCLUDE)

    def describe_resource(self, name: str) -> str:
        """A one-line purpose for a served template, read from the template itself.

        Same derivation as the procedures, and for the same reason: four templates sharing
        one sentence with the name swapped in tells a reader nothing, and an authored copy
        would drift from the file it describes.
        """
        return _lead_sentence(self._resource_text(name)) or f"Framework template '{name}'."

    def title_resource(self, name: str) -> str:
        """A display title for a served template, taken from its own `#` heading."""
        return _h1_title(self._resource_text(name)) or name

    def _resource_text(self, name: str) -> str:
        """The raw template body. Raises ``KeyError`` if absent or excluded."""
        if name in _RESOURCE_EXCLUDE:
            raise KeyError(f"unknown resource: {name}")
        path = self._root / _TEMPLATES_DIR / f"{name}.md"
        if not path.exists():
            raise KeyError(f"unknown resource: {name}")
        return path.read_text(encoding="utf-8")

    def get_resource(self, name: str) -> str:
        """Return a template file verbatim. Raises ``KeyError`` if absent or excluded."""
        return self._resource_text(name)
