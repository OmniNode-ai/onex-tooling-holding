"""Lane briefs say push, hand off, exit; the PR watcher reports CI results (OMN-19852).

The PR watcher (ops_tooling_pkg ``pr_watcher``, launchd ``ai.omninode.pr-watcher``) reads every
open pull request's CI once per tick and reports results to the landing lane, so no lane polls its
own PR. These tests pin that contract in the three briefs lanes run, and refuse the polling
instructions it replaced."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "omni" / "skills"
BRIEFS = {
    "pr-land": SKILLS / "pr-land" / "SKILL.md",
    "pr-handoff": SKILLS / "pr-handoff" / "SKILL.md",
}
CONTRACT = "the PR watcher reports CI results"
POLLING = (
    "Poll at minute intervals",
    "If auto-merge is armed (step 4), wait for it.",
    "a fresh dispatch next cycle re-reads it",
)


@pytest.mark.parametrize("name", sorted(BRIEFS))
def test_brief_names_the_watcher_contract(name: str) -> None:
    text = BRIEFS[name].read_text(encoding="utf-8")
    assert CONTRACT.lower() in text.lower(), f"{name} does not say {CONTRACT!r}"
    assert "push, hand off, exit" in text.lower()
    assert "ai.omninode.pr-watcher" in text


@pytest.mark.parametrize("name", sorted(BRIEFS))
def test_brief_carries_no_polling_instruction(name: str) -> None:
    text = BRIEFS[name].read_text(encoding="utf-8")
    found = [phrase for phrase in POLLING if phrase in text]
    assert not found, f"{name} still tells a lane to poll: {found}"


def test_positive_control_the_polling_phrases_are_detectable() -> None:
    sample = "... the move is a fresh head, never a rerun. Poll at minute intervals. ..."
    assert any(phrase in sample for phrase in POLLING)
