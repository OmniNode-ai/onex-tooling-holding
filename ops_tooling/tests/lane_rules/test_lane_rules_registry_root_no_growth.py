"""Pin the registry_root no-growth rule every dispatched lane receives verbatim.

``lane_rules/lane-rules-block.md`` is handed to every dispatched lane verbatim. The pinned
line tells a lane that registry_root no longer accepts new files and that it must move what it
touches. Match its load-bearing fragments rather than its complete prose, so the explanation can
be reworded without making the test stale.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BLOCK = Path(__file__).resolve().parents[2] / "lane_rules" / "lane-rules-block.md"

REQUIRED: dict[str, re.Pattern[str]] = {
    "the no-growth ruling": re.compile(r"registry_root no longer grows"),
    "the ruling timestamp": re.compile(r"RULING 2026-09-26T14:02:19Z"),
    "the prohibition on new registry_root files": re.compile(
        r"never add a file to the registry_root repository"
    ),
    "the move-what-you-touch direction": re.compile(r"move what you touch"),
    "the freeze-gate": re.compile(r"freeze-gate"),
}

NO_GROWTH = REQUIRED["the no-growth ruling"]
INTERNAL_HOMES = (
    re.compile(r"ops_tooling_pkg"),
    re.compile(r"docs_repo"),
)


def missing_fragments(text: str) -> list[str]:
    """Return the labels of the no-growth fragments ``text`` lacks."""
    problems = [label for label, pattern in REQUIRED.items() if not pattern.search(text)]
    paragraph = next((item for item in text.split("\n\n") if NO_GROWTH.search(item)), "")
    if not all(pattern.search(paragraph) for pattern in INTERNAL_HOMES):
        problems.append("the two internal homes in the no-growth paragraph")
    return problems


def _block() -> str:
    assert BLOCK.is_file(), f"{BLOCK} is missing; it is the lane-rules block's home"
    return BLOCK.read_text(encoding="utf-8")


@pytest.mark.parametrize("label", sorted(REQUIRED), ids=lambda label: label)
def test_block_carries_the_no_growth_fragment(label: str) -> None:
    assert REQUIRED[label].search(_block()), f"the lane-rules block does not carry {label}"


def test_no_growth_paragraph_names_both_internal_homes() -> None:
    paragraph = next(item for item in _block().split("\n\n") if NO_GROWTH.search(item))
    assert all(pattern.search(paragraph) for pattern in INTERNAL_HOMES)


def test_block_has_no_missing_no_growth_fragments() -> None:
    assert missing_fragments(_block()) == []


def test_check_rejects_a_block_without_the_no_growth_paragraph() -> None:
    """Negative control: every fragment disappears when its paragraph is removed."""
    paragraphs = _block().split("\n\n")
    mutated = "\n\n".join(item for item in paragraphs if not NO_GROWTH.search(item))
    assert mutated != _block(), "the no-growth paragraph was not found; the control proves nothing"
    assert set(missing_fragments(mutated)) == {
        *REQUIRED,
        "the two internal homes in the no-growth paragraph",
    }
