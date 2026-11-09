"""MemoryService crosses one real boundary: a disposable SQLite/PostgreSQL store.

Tenant identity is supplied by the test rather than an external issuer. No extra
fixture is needed: service.insert is the real upstream stage that creates the two
records. The existing memory_repo fixture provisions and tears down the test world.
"""

from dataclasses import asdict

import pytest

from munnin.business_services.memory_service import MemoryService
from munnin.data_entities.record_reference import AmbiguousRecordReference

A = "acbfed01-1234-4321-9876-123456789abc"
B = "acbfed02-1234-4321-9876-123456789abc"


def test_service_prefix_targets_one_record_and_refuses_ambiguous_write(memory_repo):
    service = MemoryService(memory_repo, user_id="alvi")
    for uuid in (A, B):
        service.insert(agent_id="meta", record_type="knowledge", uuid=uuid,
                       title=uuid, content="original", content_summary="test record")

    changed = service.append("AC-BF-ED-01", " changed")
    assert changed["uuid"] == A
    assert changed["content"] == "original changed"
    assert service.get(B)["content"] == "original"

    before = [asdict(memory_repo.get(uuid)) for uuid in (A, B)]
    with pytest.raises(AmbiguousRecordReference) as caught:
        service.append("acbfed", " forbidden")
    assert {row.uuid for row in caught.value.candidates} == {A, B}
    assert [asdict(memory_repo.get(uuid)) for uuid in (A, B)] == before
    assert service.archive("ACBFED01") == {"uuid": A, "status": "archived"}
    assert service.unarchive("ACBFED01") == {"uuid": A, "status": "active"}
