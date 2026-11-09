"""Existing-record references: exact stored IDs or unambiguous UUID prefixes."""

from __future__ import annotations

import re
from dataclasses import dataclass


class InvalidRecordReference(ValueError):
    """A reference is neither an existing exact ID nor a valid UUID prefix."""


def normalize_prefix(reference: str) -> str:
    """Normalize only lookup input; stored IDs and creation inputs are untouched."""
    normalized = reference.replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{6,32}", normalized):
        raise InvalidRecordReference(
            "UUID prefix must contain 6 to 32 hexadecimal characters "
            "(hyphens are optional and do not count toward the minimum)"
        )
    return normalized


@dataclass(frozen=True)
class RecordCandidate:
    table: str
    uuid: str
    title: str | None


def uuid_candidate(candidate: RecordCandidate) -> bool:
    """Prefix lookup applies to UUIDs, never arbitrary legacy exact identifiers."""
    return re.fullmatch(r"[0-9a-f]{32}", candidate.uuid.replace("-", "").lower()) is not None


class AmbiguousRecordReference(Exception):
    """Multiple visible records match; callers must supply a longer reference."""

    def __init__(self, reference: str, candidates: list[RecordCandidate]) -> None:
        self.reference = reference
        self.candidates = sorted(candidates, key=lambda row: (row.uuid, row.table))
        choices = "; ".join(f"{row.uuid} ({row.title or 'untitled'})" for row in self.candidates)
        super().__init__(f"ambiguous UUID prefix {reference!r}: {choices}; use a longer prefix")

    def detail(self) -> dict[str, object]:
        return {
            "error": "ambiguous_uuid",
            "message": str(self),
            "candidates": [{"uuid": row.uuid, "title": row.title} for row in self.candidates],
        }
