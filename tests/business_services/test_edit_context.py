"""Opt-in edit contexts preserve old projections and bind every guarded save."""

import hashlib

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.edit_context import RevisionConflict, TenantConflict
from tests.conftest import AutoAgentRepository


def service(tmp_path, **options):
    repo = AutoAgentRepository(tmp_path / "memory.db", user_id="alvi")
    return MemoryService(repo, user_id="alvi", **options)


def guard(context):
    return {"expected_revision": context["revision"], "expected_tenant": context["tenant"]}


def test_opt_in_read_and_separate_guarded_saves(tmp_path):
    svc = service(tmp_path)
    record = svc.insert(agent_id="meta", record_type="identity", content="body", title="Title")
    assert "edit_context" not in svc.get(record["uuid"])
    loaded = svc.get(record["uuid"], include_edit_context=True)
    assert loaded["edit_context"]["uuid"] == record["uuid"]
    assert loaded["edit_context"]["tenant"] == "alvi"
    saved = svc.edit(record["uuid"], "body", "new body", **guard(loaded["edit_context"]))
    assert "content" not in saved and "full_content" not in saved
    assert saved["title"] == "Title" and saved["edit_context"] != loaded["edit_context"]
    with pytest.raises(RevisionConflict):
        svc.edit_metadata(record["uuid"], title="Stale", **guard(loaded["edit_context"]))
    metadata = svc.edit_metadata(
        record["uuid"], title="New title", **guard(saved["edit_context"])
    )
    assert "content" not in metadata
    assert svc.get(record["uuid"])["content"] == "new body"
    # Existing clients retain their default body-bearing edit response.
    assert svc.edit(record["uuid"], "new body", "legacy")["content"] == "legacy"
    assert "edit_context" not in svc.edit_metadata(record["uuid"], title="Legacy title")


@pytest.mark.parametrize("partial", [
    {"expected_revision": "v1:token"},
    {"expected_tenant": "alvi"},
    {"expected_revision": "", "expected_tenant": "alvi"},
])
def test_partial_precondition_pairs_are_refused(tmp_path, partial):
    svc = service(tmp_path)
    record = svc.insert(agent_id="meta", record_type="identity", content="body")
    with pytest.raises(ValueError, match="together"):
        svc.edit(record["uuid"], "body", "lost", **partial)
    assert svc.get(record["uuid"])["content"] == "body"


def test_expected_tenant_never_selects_an_account_or_leaks_a_body(tmp_path):
    svc = service(tmp_path)
    record = svc.insert(agent_id="meta", record_type="identity", content="private")
    context = svc.get(record["uuid"], include_edit_context=True)["edit_context"]
    with pytest.raises(TenantConflict, match="account changed"):
        svc.edit(record["uuid"], "private", "lost",
                 expected_tenant="another", expected_revision=context["revision"])
    assert svc.get(record["uuid"])["content"] == "private"


def test_each_episode_page_reports_the_same_context_until_the_row_changes(tmp_path):
    svc = service(tmp_path)
    body = "### 2026-11-17 11.00\nNewest\n\n---\n\n### 2026-11-16 10.00\nOlder\n"
    record = svc.insert(agent_id="meta", record_type="episode", content=body,
                        content_summary="Episode")
    first = svc.get(record["uuid"], limit=1, include_edit_context=True)
    second = svc.get(record["uuid"], cursor=first["next_cursor"], include_edit_context=True)
    assert first["edit_context"] == second["edit_context"]
    svc.edit_metadata(record["uuid"], title="Changed while reading")
    changed = svc.get(record["uuid"], cursor=first["next_cursor"], include_edit_context=True)
    assert changed["edit_context"] != first["edit_context"]


def test_editor_pages_reconstruct_nonadjacent_equal_timestamps_byte_exactly(tmp_path):
    svc = service(tmp_path, max_body_bytes=1)
    body = ("preamble\r\n### 2026-11-17 11.00\nFirst é\n\n---\n\n"
            "### 2026-11-16 10.00\nMiddle\n\n---\n\n"
            "### 2026-11-17 11.00\nLast 終\n")
    record = svc.insert(agent_id="meta", record_type="episode", content=body,
                        content_summary="Nonadjacent groups")
    page = svc.get(record["uuid"], include_edit_context=True)
    parts, plain = [], []
    expected = page["edit_context"]
    while True:
        assert page["edit_context"] == expected
        assert page["edit_body"]["sha256"] == hashlib.sha256(body.encode()).hexdigest()
        offset = 0
        plain.append(page["content"])
        for segment in page["edit_body"]["segments"]:
            stop = offset + segment["characters"]
            parts.append((segment["source_start"], page["content"][offset:stop]))
            offset = stop
        assert offset == len(page["content"])
        if page["next_cursor"] is None:
            break
        page = svc.get(record["uuid"], cursor=page["next_cursor"], include_edit_context=True)
    assert "".join(plain) != body  # The old concatenation would have been the wrong baseline.
    assert "".join(text for start, text in sorted(parts)).encode() == body.encode()
