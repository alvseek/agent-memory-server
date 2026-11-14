"""Write-time summary bounds over real repositories; legacy reads remain lossless."""

import pytest

from munnin.business_services.memory_service import (
    CONTENT_SUMMARY_MAX_CHARACTERS,
    MemoryService,
)
from munnin.data_entities.memory_record import MemoryRecord, RecordType, SharedRecord


@pytest.fixture
def svc(memory_repo):
    return MemoryService(memory_repo, user_id="alvi")


def _insert(svc, scope, summary, **fields):
    return svc.insert(
        scope=scope,
        agent_id="meta" if scope == "agent" else None,
        record_type="knowledge",
        content="original body",
        content_summary=summary,
        uuid="summary-record",
        title="original title",
        **fields,
    )


@pytest.mark.parametrize("scope", ["agent", "shared"])
@pytest.mark.parametrize("character", ["x", "界", "😀"])
def test_summary_limit_accepts_exactly_1000_unicode_characters(svc, scope, character):
    assert CONTENT_SUMMARY_MAX_CHARACTERS == 1000
    summary = character * 1000
    assert _insert(svc, scope, summary)["content_summary"] == summary
    replacement = "é" * 1000
    assert svc.edit_metadata(
        "summary-record", content_summary=replacement,
    )["content_summary"] == replacement


@pytest.mark.parametrize("scope", ["agent", "shared"])
def test_oversized_insert_creates_nothing(svc, scope):
    with pytest.raises(ValueError, match="at most 1000 characters; received 1001 characters"):
        _insert(svc, scope, "😀" * 1001)
    assert svc.query() == []


@pytest.mark.parametrize("scope", ["agent", "shared"])
@pytest.mark.parametrize("operation", ["insert", "edit_metadata"])
def test_oversized_summary_rejects_the_entire_write(svc, scope, operation):
    before = _insert(svc, scope, "original summary")
    with pytest.raises(ValueError, match="at most 1000 characters; received 1001 characters"):
        if operation == "insert":
            _insert(svc, scope, "x" * 1001)
        else:
            svc.edit_metadata(
                "summary-record", title="must not change", content_summary="x" * 1001,
            )
    assert svc.get("summary-record")["content_summary"] == before["content_summary"]
    assert svc.get("summary-record")["title"] == before["title"]
    assert svc.get("summary-record")["content"] == before["content"]


@pytest.mark.parametrize("scope", ["agent", "shared"])
def test_legacy_summary_is_readable_and_unrelated_edits_still_work(svc, memory_repo, scope):
    # Bypass the service to model a row imported or stored before the input limit.
    fields = dict(
        uuid="legacy-record", user_id="alvi", record_type=RecordType.knowledge,
        full_content="legacy body", content_summary="界" * 2000,
    )
    if scope == "shared":
        memory_repo.insert_shared(SharedRecord(**fields))
    else:
        memory_repo.insert(MemoryRecord(agent_id="meta", **fields))
    assert svc.get("legacy-record")["content_summary"] == "界" * 2000
    assert svc.edit_metadata("legacy-record", title="new title")["content_summary"] == "界" * 2000
    indexes = svc.awaken("meta")
    index = indexes["knowledge_index"] if scope == "agent" else indexes["shared"]["knowledge_index"]
    assert index[0]["content_summary"] == "界" * 2000
    assert svc.edit_metadata("legacy-record", content_summary="short")["content_summary"] == "short"
    cleared = svc.edit_metadata("legacy-record", clearing=["content_summary"])
    assert cleared["content_summary"] is None


def test_limit_also_applies_to_optional_summaries(svc):
    with pytest.raises(ValueError, match="received 1001 characters"):
        svc.insert(
            agent_id="meta", record_type="identity", content="body",
            content_summary="x" * 1001,
        )
