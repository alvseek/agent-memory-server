"""The episodic page engine: contract vectors plus the traversal the contract promises.

The vectors are a shared artifact (`tests/conformance/episode_page_vectors.json`) that Hermod's
independent helper runs verbatim, so a drift between the two servers is loud. Its checksum is
pinned here; changing a vector therefore has to be a deliberate edit in both repositories.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

from munnin.business_services.episode_page import count_groups, page_body

#: sha256 of the shared artifact. If this fails, the vectors changed — either re-record it
#: here and in Hermod's copy, or restore the file.
VECTORS_SHA256 = "cbaeac95ad6bc0de9dd48a7519a52e6ed802313b96be68269b622a6d5b588a4a"
VECTORS_PATH = pathlib.Path(__file__).resolve().parents[1] / "conformance" / (
    "episode_page_vectors.json"
)

_ARTIFACT = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
VECTORS = _ARTIFACT["vectors"]
OK_VECTORS = [v for v in VECTORS if "expected" in v]
ERROR_VECTORS = [v for v in VECTORS if "error_contains" in v]


def _call(vector: dict):
    return page_body(
        vector["content"],
        cursor=vector["cursor"],
        limit=vector["limit"],
        max_body_bytes=vector["max_body_bytes"],
        splittable=vector["splittable"],
    )


def test_artifact_checksum_is_pinned() -> None:
    digest = hashlib.sha256(VECTORS_PATH.read_bytes()).hexdigest()
    assert digest == VECTORS_SHA256


def test_vectors_cover_the_contract_surface() -> None:
    names = {vector["name"] for vector in VECTORS}
    # The cases the plan names by hand, so a future edit cannot quietly drop one.
    for expected in (
        "no-headers",
        "preamble-rides-with-first-group",
        "one-group",
        "thirty-groups-page-1",
        "equal-timestamps-adjacent-limit-1",
        "equal-timestamps-nonadjacent-page-1",
        "ceiling-oversized-first-group-still-emitted",
        "fenced-fake-heading-is-not-a-boundary",
        "legacy-spellings-group-together",
    ):
        assert expected in names


@pytest.mark.parametrize("vector", OK_VECTORS, ids=[v["name"] for v in OK_VECTORS])
def test_vector(vector: dict) -> None:
    page = _call(vector)
    expected = vector["expected"]
    assert page.content == expected["content"]
    assert page.blocks_returned == expected["blocks_returned"]
    assert page.blocks_total == expected["blocks_total"]
    assert page.next_cursor == expected["next_cursor"]


@pytest.mark.parametrize("vector", ERROR_VECTORS, ids=[v["name"] for v in ERROR_VECTORS])
def test_vector_refusals(vector: dict) -> None:
    with pytest.raises(ValueError) as caught:
        _call(vector)
    # The refusal has to name what was wrong; the exact sentence is each server's own.
    assert vector["error_contains"] in str(caught.value)


# --- the traversal the contract promises ---------------------------------

THIRTY = "".join(
    f"### 2026-01-01 10.{index:02d} - g{index:02d}\n\nbody {index:02d}\n" for index in range(30)
)
_BLOCK = re.compile(r"### \d{4}-\d{2}-\d{2} \d{2}\.\d{2} - g\d{2}\n\nbody \d{2}\n")


def _walk(content: str, *, limit: int | None = 3, max_body_bytes: int | None = None):
    """Every page of one record, following ``next_cursor`` to null."""
    pages = []
    cursor = None
    for _ in range(1000):  # a runaway guard, not an expected page count
        page = page_body(
            content, cursor=cursor, limit=limit, max_body_bytes=max_body_bytes
        )
        pages.append(page)
        if page.next_cursor is None:
            return pages
        cursor = page.next_cursor
    raise AssertionError("traversal never terminated")


def test_traversal_terminates_and_reconciles_every_block_once() -> None:
    pages = _walk(THIRTY)
    assert len(pages) == 10
    assert [page.blocks_returned for page in pages] == [3] * 10
    assert all(page.blocks_total == 30 for page in pages)
    joined = "".join(page.content for page in pages)
    assert joined == THIRTY
    assert len(_BLOCK.findall(joined)) == 30


def test_traversal_survives_a_prepended_block() -> None:
    """Continuation names a moment, not an offset, so a block added between two reads cannot
    shift the caller's place — and the already-read page is not replayed."""
    first = page_body(THIRTY, limit=3)
    assert first.next_cursor == "2026-01-01 10.03"

    newer = "### 2026-01-02 08.00 - arrived between reads\n\nnew body\n"
    grown = newer + THIRTY

    second = page_body(grown, cursor=first.next_cursor, limit=3)
    assert second.blocks_total == 31
    assert second.content.startswith("### 2026-01-01 10.03")
    assert newer not in second.content
    assert [page.blocks_returned for page in [first, second]] == [3, 3]
    # The new block is only reachable by a fresh read from the start — it is not replayed.
    fresh = page_body(grown, limit=1)
    assert fresh.content == newer


def test_nonadjacent_grouping_reconciles_every_slice_once() -> None:
    """A grouped page may change adjacency, but no source slice may be lost or duplicated."""
    blocks = [
        "### 2026-11-09 11.00 - a\n\nA\n",
        "### 2026-11-09 10.00 - b\n\nB\n",
        "### 2026-11-09 11.00 - c\n\nC\n",
    ]
    content = "".join(blocks)
    pages = _walk(content, limit=1)
    assert len(pages) == 2
    collected = "".join(page.content for page in pages)
    for block in blocks:
        assert collected.count(block) == 1
    # Non-adjacent equal timestamps travel together, which is why a partial page may reorder.
    assert pages[0].content == blocks[0] + blocks[2]


def test_full_uncapped_read_is_byte_identical() -> None:
    content = "".join(
        f"### 2026-11-0{day} 1{day}.00 - day {day}\n\nbody \u00e9 {day}\n" for day in range(1, 6)
    )
    page = page_body(content)
    assert page.content.encode("utf-8") == content.encode("utf-8")
    assert page.blocks_returned == page.blocks_total == 5
    assert page.next_cursor is None


def test_ceiling_never_splits_a_group() -> None:
    """The first group of a page is indivisible, so the ceiling can only stop *additions*."""
    content = "".join(
        f"### 2026-03-0{day} 10.00 - d{day}\n\n" + ("x" * 200) + "\n" for day in range(1, 4)
    )
    page = page_body(content, limit=1, max_body_bytes=10)
    assert page.blocks_returned == 1
    assert page.blocks_total == 3
    assert page.content == content.split("### 2026-03-02")[0]
    assert page.next_cursor == "2026-03-02 10.00"


def test_count_groups_agrees_with_the_page() -> None:
    assert count_groups(THIRTY) == page_body(THIRTY, limit=1).blocks_total == 30
    assert count_groups("") == 1
    assert count_groups(THIRTY, splittable=False) == 1


@pytest.mark.parametrize("limit", [0, -3, True, "2", 1.5])
def test_limit_must_be_a_positive_whole_number(limit) -> None:
    with pytest.raises(ValueError):
        page_body(THIRTY, limit=limit)


@pytest.mark.parametrize("ceiling", [0, -1, False, "100"])
def test_ceiling_must_be_a_positive_number(ceiling) -> None:
    with pytest.raises(ValueError):
        page_body(THIRTY, max_body_bytes=ceiling)
