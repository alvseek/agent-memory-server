"""Opaque edit preconditions derived from the entire persisted record state."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict

from munnin.data_entities.memory_record import SharedRecord


class EditConflict(RuntimeError):
    """A guarded request no longer matches its original editing context."""


class RevisionConflict(EditConflict):
    """The stored record changed; no write was applied."""


class TenantConflict(EditConflict):
    """The authenticated acting tenant changed; no write was applied."""


def record_revision(record: SharedRecord) -> str:
    """Include every entity field, including owner, scope, lifecycle and full body.

    Timestamps alone have insufficient resolution. Scope is explicit even when row
    identifiers happen to coincide between the two tables. No revision is persisted.
    """
    encoded = json.dumps(
        {"scope": type(record).__name__, "row": asdict(record)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "v1:" + hashlib.sha256(encoded).hexdigest()


def check_revision(record: SharedRecord, expected_revision: str | None) -> None:
    if expected_revision is not None and not hmac.compare_digest(
        record_revision(record).encode("utf-8"), expected_revision.encode("utf-8")
    ):
        raise RevisionConflict("record changed; reload before saving")
