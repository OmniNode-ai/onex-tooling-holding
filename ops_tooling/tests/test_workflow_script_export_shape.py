# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""Workflow-tool script-contract tests (OMN-13640).

The Claude Code Workflow tool parses a `.claude/workflows/*.js` script by
extracting one leading ``export const meta = {...}`` literal and then running
the REMAINDER of the file as a plain, non-module script -- it never treats the
file as an ES module past that one extraction. Any second ``export`` anywhere
else in the file is therefore a hard launch-time failure, ``SyntaxError:
Unexpected keyword 'export'``, not a test-time one.

Measured, 2026-09-14: ``linear-comments-hourly.js`` shipped (registry_root#273)
with SEVEN ``export`` statements -- ``meta`` plus six pure helper functions
exported purely so the test suite could reach them -- and the Workflow tool
refused to launch it. The hourly tick therefore kept running the old,
non-delegating 40-line copy. Every OTHER script in this directory carries
exactly one ``export``, which is the mechanical signature of the defect: this
file is the outlier, not the pattern.

This test encodes the contract directly against the script text (not by
attempting to invoke the Workflow tool itself, which has no headless
entrypoint reachable from pytest) so a future script cannot regress the same
way, and wires it as a pre-commit hook + CI gate in the same PR that fixes
the specific instance (CLAUDE.md rule 5: enforcement, not detection).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO / "src" / "ops_tooling_pkg" / "handlers"
SCRIPTS = sorted(p for p in WORKFLOWS_DIR.rglob("*.js") if p.is_file())

# Matches an `export` keyword at the start of a (possibly indented) line --
# the shape every real top-level export/meta declaration takes in these
# scripts. Deliberately does not try to parse full JS: a textual signature is
# what the tool itself keys off (a regex/prefix extraction of one literal),
# so a textual test is the right level of fidelity for this contract.
EXPORT_LINE_RE = re.compile(r"^\s*export\b", re.MULTILINE)
META_LITERAL_RE = re.compile(r"^export const meta\s*=\s*\{")


def _first_statement_line(text: str) -> str:
    """The first non-blank, non-comment line of the file.

    Comments and blank lines are allowed before the meta literal (the tool's
    own authoring example shows a license/doc header first); an executable
    statement is not.
    """
    in_block_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if not stripped:
            continue
        if stripped.startswith("//"):
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        return line
    return ""


@pytest.mark.unit
def test_positive_control_workflow_scripts_exist() -> None:
    """A zero-script glob would make every assertion below vacuously pass."""
    names = [p.name for p in SCRIPTS]
    assert len(SCRIPTS) >= 5, f"expected several workflow scripts, found {names}"
    assert "linear-comments-hourly.js" in names, names


@pytest.mark.unit
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_workflow_script_carries_exactly_one_export(script: Path) -> None:
    """The tool extracts exactly one leading `export const meta` literal and
    runs everything after it as a non-module script -- a second `export`
    anywhere else in the file is a SyntaxError at launch time. This is the
    class of defect that shipped in linear-comments-hourly.js (seven
    `export` statements: meta plus six helpers exported only for the test
    suite's benefit).
    """
    text = script.read_text(encoding="utf-8")
    exports = EXPORT_LINE_RE.findall(text)
    assert len(exports) == 1, (
        f"{script.relative_to(REPO)} carries {len(exports)} `export` statements; "
        "the Workflow tool permits exactly one (`export const meta`). Move any "
        "other exported helper to a plain, non-exported declaration -- tests can "
        "still reach it by reading the file and evaluating the block under node, "
        "the way tests/test_linear_comments_hourly_delegation.py does."
    )


@pytest.mark.unit
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_workflow_script_begins_with_meta_literal(script: Path) -> None:
    """`export const meta = {...}` must be the first statement. Comments and
    blank lines may precede it; any executable statement may not.
    """
    text = script.read_text(encoding="utf-8")
    first = _first_statement_line(text)
    assert META_LITERAL_RE.match(first), (
        f"{script.relative_to(REPO)}: the first statement must be "
        f"`export const meta = {{`, got: {first!r}"
    )
