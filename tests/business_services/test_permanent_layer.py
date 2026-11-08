"""MemoryService.permanent_layer() — the block is projected from the store's records.

The layer used to be the RAS triggers plus a hand-authored digest read from the content
tree. It is now derived, per tenant, from the reasoning lane: one entry per rule, the
stored title as a heading and the rule's ``Final Conclusion`` as the paragraph under it.
"""

from __future__ import annotations

from pathlib import Path

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.memory_record import RecordType, SharedRecord
from tests.conftest import AutoAgentRepository


def _pattern(
    uuid: str,
    title: str,
    conclusion: str | None = "Do the thing, because the other thing broke.",
    *,
    created: str = "2026-01-01",
    modified: str | None = None,
) -> SharedRecord:
    body = f"### {title}\n**Rule**: do the thing.\n**Why**: because."
    if conclusion is not None:
        body += f"\n**Final Conclusion**: {conclusion}"
    return SharedRecord(
        uuid=uuid,
        user_id="",
        record_type=RecordType.reasoning,
        title=title,
        full_content=body,
        created_date=created,
        modified_date=modified,
    )


def _ras(
    uuid: str,
    body: str = "### **MEMORY RECOVERY**\n\nSTOP and reload.",
    *,
    modified: str | None = None,
) -> SharedRecord:
    return SharedRecord(
        uuid=uuid,
        user_id="",
        record_type=RecordType.ras,
        title=uuid,
        full_content=body,
        created_date="2026-01-01",
        modified_date=modified,
    )


def _service(tmp_path: Path, *records: SharedRecord) -> MemoryService:
    repo = AutoAgentRepository(tmp_path / "m.db", user_id="alvi")
    for record in records:
        repo.insert_shared(record)
    return MemoryService(repo, user_id="alvi")


def test_block_is_the_ras_triggers_then_title_and_conclusion(tmp_path: Path) -> None:
    out = _service(
        tmp_path, _ras("r1"), _pattern("p1", "**A RULE** 🎯 TAG 🎯", "Do the thing.")
    ).permanent_layer()

    assert out["content"].startswith("### **MEMORY RECOVERY**")
    assert out["content"].index("MEMORY RECOVERY") < out["content"].index("A RULE")
    assert "### **A RULE** 🎯 TAG 🎯\nDo the thing." in out["content"]
    assert len(out["hash"]) == 12
    assert out["skipped"] == []


def test_a_rule_without_a_conclusion_is_skipped_and_named(tmp_path: Path) -> None:
    out = _service(
        tmp_path,
        _pattern("p1", "**HAS ONE**", "Keep me."),
        _pattern("p2", "**OFF TEMPLATE**", None),
    ).permanent_layer()

    assert "Keep me." in out["content"]
    assert "OFF TEMPLATE" not in out["content"]
    assert out["skipped"] == ["**OFF TEMPLATE**"]


def test_none_declared_is_excluded_without_being_reported(tmp_path: Path) -> None:
    out = _service(
        tmp_path,
        _pattern("p1", "**HAS ONE**", "Keep me."),
        _pattern("p2", "**SAYS NOTHING**", "None declared"),
    ).permanent_layer()

    assert "SAYS NOTHING" not in out["content"]
    assert out["skipped"] == []


def test_entries_are_ordered_by_creation_not_insertion(tmp_path: Path) -> None:
    out = _service(
        tmp_path,
        _pattern("p2", "**SECOND**", "second.", created="2026-02-01"),
        _pattern("p1", "**FIRST**", "first.", created="2026-01-01"),
    ).permanent_layer()

    assert out["content"].index("**FIRST**") < out["content"].index("**SECOND**")


def test_version_is_the_newest_modified_date_the_block_includes(tmp_path: Path) -> None:
    out = _service(
        tmp_path,
        _ras("r1", modified="2026-03-01T00:00:00+00:00"),
        _pattern("p1", "**A RULE**", "Do it.", modified="2026-04-05T10:00:00+00:00"),
    ).permanent_layer()

    assert out["version"] == "2026-04-05"


def test_an_empty_store_answers_empty_rather_than_raising(tmp_path: Path) -> None:
    out = _service(tmp_path).permanent_layer()

    assert out["content"] == ""
    assert out["version"] == ""
    assert out["skipped"] == []
    assert len(out["hash"]) == 12
