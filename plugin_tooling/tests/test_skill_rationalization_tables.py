"""Orchestrator and lane-brief skills keep a Common rationalizations table and a Red flags list (OMN-17427).

On 2026-10-17 the operator approved a per-skill anti-rationalization table: each row is an excuse a
session gave for skipping a step, why it is wrong, and what to do instead, built from a real failure.
The skills below are the ones an orchestrator reads before it acts, so each keeps a non-empty table
and a non-empty list, and a later edit that drops or empties either turns this test red. Run it from
the repository root: ``python -m pytest tests/test_skill_rationalization_tables.py -q``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "plugins" / "omni" / "skills"

TABLE_SKILLS = ("session-start", "queue-status", "merge-sweep", "lane-brief", "remote-lane")
HEADER = ("Excuse", "Why it is wrong", "What to do instead")
MIN_ROWS = 5
MIN_FLAGS = 5
# A row names the failure it came from; a reason or an action shorter than this is a slogan.
# An excuse is a quoted sentence and can be short ("Merged, so it is running.").
MIN_CELL = 30
MIN_EXCUSE = 10
HEADING_RE = re.compile(r"^## (.+?)\s*$", re.M)


def section(text: str, title: str) -> str | None:
    """The body of the ``## <title>`` section, up to the next ``## `` heading, or None."""
    headings = list(HEADING_RE.finditer(text))
    for index, heading in enumerate(headings):
        if heading.group(1) == title:
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            return text[heading.end() : end]
    return None


def table_rows(body: str) -> tuple[list[str], list[list[str]]]:
    """The header cells and the data rows of the first Markdown table in ``body``."""
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    cells = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    return cells[0], cells[2:]


def findings(text: str) -> list[str]:
    """Every way ``text`` fails to carry the table and the list; empty when it carries both."""
    out: list[str] = []
    table = section(text, "Common rationalizations")
    if table is None:
        out.append("no '## Common rationalizations' section")
    else:
        header, rows = table_rows(table)
        if tuple(header) != HEADER:
            out.append(f"table header is {header}, expected {list(HEADER)}")
        if len(rows) < MIN_ROWS:
            out.append(f"table has {len(rows)} rows, needs at least {MIN_ROWS}")
        for number, row in enumerate(rows, start=1):
            if len(row) != len(HEADER):
                out.append(f"row {number} has {len(row)} cells, expected {len(HEADER)}")
            elif len(row[0]) < MIN_EXCUSE or any(len(cell) < MIN_CELL for cell in row[1:]):
                out.append(f"row {number} has an empty or thin cell")
    flags = section(text, "Red flags")
    if flags is None:
        out.append("no '## Red flags' section")
    else:
        items = [line for line in flags.splitlines() if line.startswith("- ") and len(line) > 2 + MIN_CELL]
        if len(items) < MIN_FLAGS:
            out.append(f"red flags has {len(items)} items, needs at least {MIN_FLAGS}")
    return out


@pytest.mark.parametrize("skill", TABLE_SKILLS)
def test_skill_keeps_its_rationalizations_table_and_red_flags(skill: str) -> None:
    text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    assert findings(text) == []


def _good() -> str:
    cell = "x" * MIN_CELL
    rows = "\n".join(f"| a{n} {cell} | b{n} {cell} | c{n} {cell} |" for n in range(MIN_ROWS))
    flags = "\n".join(f"- flag {n} {cell}" for n in range(MIN_FLAGS))
    return (
        "## Common rationalizations\n\n"
        "| Excuse | Why it is wrong | What to do instead |\n| -- | -- | -- |\n"
        f"{rows}\n\n## Red flags\n\n{flags}\n\n## Known friction\n"
    )


def test_the_check_passes_a_complete_section() -> None:
    assert findings(_good()) == []


def test_the_check_refuses_a_dropped_table() -> None:
    dropped = _good().replace("## Common rationalizations", "## Notes")
    assert "no '## Common rationalizations' section" in findings(dropped)


def test_the_check_refuses_an_empty_table() -> None:
    empty = re.sub(r"\n\| a\d.*", "", _good())
    assert any("rows, needs at least" in finding for finding in findings(empty))


def test_the_check_refuses_an_empty_cell() -> None:
    blank = _good().replace("| c0 " + "x" * MIN_CELL + " |", "| |", 1)
    assert any("row 1" in finding for finding in findings(blank))


def test_the_check_refuses_a_wrong_header() -> None:
    renamed = _good().replace("Why it is wrong", "Notes")
    assert any("table header" in finding for finding in findings(renamed))


def test_the_check_refuses_dropped_red_flags() -> None:
    dropped = _good().replace("## Red flags", "## Misc")
    assert "no '## Red flags' section" in findings(dropped)


def test_the_check_refuses_a_thin_red_flags_list() -> None:
    thin = re.sub(r"\n- flag [1-9].*", "", _good())
    assert any("red flags has" in finding for finding in findings(thin))
