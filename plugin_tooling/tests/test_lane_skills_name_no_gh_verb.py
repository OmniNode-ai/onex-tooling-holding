"""The lane-facing landing skills name ``onex scm`` and no gh verb (OMN-20913, AC2).

A lane reaches GitHub through ``onex scm <verb>`` (omnimarket, the source-control
nodes): PR and CI state reads answer from the PR watcher state and the canonical
clones, the other reads and the PR authoring writes go over the bus. Merging,
arming, rerunning and updating a branch are the landing controller's, handed to it
with ``/omni:pr-handoff``. A skill that still tells a lane to run a gh verb sends it
around the nodes.

A gh verb inside quoted history (a Markdown blockquote line, starting ``>``) is a
record of what happened, not an instruction, and is not counted. There is no
allowlist or baseline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "omni" / "skills"

SCANNED = tuple(
    SKILLS / name / "SKILL.md"
    for name in (
        "pr-land",
        "pr-handoff",
        "merge-drain",
        "ci-watch",
        "arm-green",
        "lane-brief",
    )
)

# `gh <command>` for every gh command that reaches GitHub, with or without
# global flags between them.
GH_VERB = re.compile(
    r"\bgh(?:\s+--?[A-Za-z][\w-]*(?:[ =][^\s`]+)?)*\s+"
    r"(pr|run|api|workflow|release|repo|issue|label|search|secret|variable|cache"
    r"|ruleset|gist|browse|project|attestation|org|codespace|status)\b"
)


def is_quoted_history(line: str) -> bool:
    return line.lstrip().startswith(">")


def gh_verb_lines(text: str) -> list[tuple[int, str]]:
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if not is_quoted_history(line) and GH_VERB.search(line)
    ]


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.parent.name)
def test_skill_names_no_gh_verb(path: Path) -> None:
    found = gh_verb_lines(path.read_text(encoding="utf-8"))
    assert not found, (
        f"{path.relative_to(ROOT)} names a gh verb; name `onex scm <verb>` or the "
        f"landing controller instead: {found}"
    )


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.parent.name)
def test_a_gh_verb_put_back_into_a_skill_is_found(path: Path) -> None:
    put_back = "Arm it with `gh pr merge <n> --squash --auto`."
    text = path.read_text(encoding="utf-8") + "\n" + put_back
    assert gh_verb_lines(text)[-1][1] == put_back


@pytest.mark.parametrize(
    "line",
    [
        "gh pr merge 12 --squash --auto",
        "Rerun with `gh run rerun <id>`.",
        'gh api "repos/$R/commits/$SHA/check-runs"',
        "| C2 | arm it (`gh pr merge <n> --squash --auto`) |",
        "gh --repo OmniNode-ai/x pr view 3",
        "  gh workflow run ci.yml --ref dev",
        "Never `gh pr view`, `gh pr list` or a `gh api` GET.",
        "(`gh issue view --json`)",
    ],
)
def test_a_gh_verb_is_found(line: str) -> None:
    assert gh_verb_lines(line) == [(1, line.strip())]


@pytest.mark.parametrize(
    "line",
    [
        "> 2026-09-23: every `gh pr view` failed with API rate limit exceeded.",
        "  > the map read every PR with `gh pr view`",
        "onex scm pr-view OmniNode-ai/omnimarket#3765",
        "the gh shim refuses every read from a lane",
        "authenticated with the lane's `gh` token",
        "the shared gh-shim log, gh-calls.log",
    ],
)
def test_quoted_history_and_non_verbs_are_not_counted(line: str) -> None:
    assert gh_verb_lines(line) == []


def test_every_scanned_skill_exists() -> None:
    assert all(path.is_file() for path in SCANNED), [
        str(p) for p in SCANNED if not p.is_file()
    ]
