"""Brief gate for CLAUDE.md rule 24 — the lab is the first place a change runs.

Operator ruling 2026-09-08T12:12:28Z, firm (durable record: the RULING row at
`docs/tracking/ROLLING_WORK_LEDGER.md:4725`): lab integration passes and lab
hotfix verification are PERMANENT PROCESS. Rule 24(c) makes that a property of
every lane brief that builds or lands code, and rule 5 says a check nobody runs
is advisory. This file is the check.

**The property.** Every `.claude/workflows/*.js` lane whose prompt text carries a
LANDING VERB must also name the lab-first step: the word `lab`, plus the lane it
actually means (`lab-host-a` or `lane-k`). A brief that tells an agent to merge a PR
without telling it where the change runs first is how twelve staging runs were
spent on 2026-09-08 learning what a lab pass shows in minutes.

**Match shape — deliberately not a bare word ban.** `LAND` as a bare substring
hits `LANDED`, which is a VERDICT noun in the ground-state verdict ladder
(`OPEN | LANDED | DEPLOYED | PROBED | UNKNOWN`) and appears a dozen times in
prose that lands nothing. Matching it would make this test fire on lanes that
only *measure* landings, which is the same failure `test_morning_lane_rules.py`
avoids for `Todo` vs `TodoWrite`. So the trigger is the imperative form only:
`gh pr merge`, or `LAND IT` / `LAND the` / `LAND this`.

Check-only. Nothing here rewrites a file — rule 19 forbids an auto-fixing hook in
this shared tree. A failure names the file and the sentence to add.
"""

import re
from pathlib import Path

import pytest
from test_workflow_brief_cutover import NAMES

REPO = Path(__file__).parent.parent
LANE_DIR = REPO / "src" / "ops_tooling_pkg" / "handlers"

# A lane that BUILDS OR LANDS code: it tells an agent to merge, in the
# imperative. `LANDED` (the verdict noun) is deliberately not matched -- see the
# module docstring.
LANDING_VERB = re.compile(r"gh pr merge|\bLAND\s+(?:IT|the|this)\b")

# The lab-first step, matched as two independent halves so the sentence can be
# reworded without this test going stale on style: the word, and the lane it
# means. Naming "the lab" without naming which lab is the vague form that got
# skipped; naming `lab-host-a` inside an unrelated host list is not the step.
LAB_WORD = re.compile(r"(?i)\blab\b")
LAB_LANE = re.compile(r"\lab-host-a|lane-k")

FIX_HINT = (
    "Add the lab-first step to this brief's rules block (CLAUDE.md rule 24(c)), "
    "e.g.: 'LAB-FIRST (CLAUDE.md rule 24). The lab is the first place a change "
    "runs; staging is promotion. Any runtime-affecting change is exercised on "
    "the lab -- the lab-host-a dev lane or the lane-k k3s overlay -- before it is "
    "landed or delivered onward, and the PR body cites that readback.'"
)


def _lane_briefs() -> list[Path]:
    return sorted(LANE_DIR / folder / f"{name}.js" for name, folder in NAMES.items())


def _building_briefs() -> list[Path]:
    return [p for p in _lane_briefs() if LANDING_VERB.search(p.read_text(encoding="utf-8"))]


@pytest.mark.unit
def test_lane_brief_dir_is_not_empty() -> None:
    """Positive control: an empty glob would make every assertion below vacuous."""
    assert _lane_briefs(), f"no lane briefs found under {LANE_DIR}"


@pytest.mark.unit
def test_at_least_one_brief_lands_code() -> None:
    """Positive control for the trigger itself.

    If `LANDING_VERB` ever stops matching anything, the parametrized test below
    silently collects zero cases and reports green while enforcing nothing --
    the empty-result-is-not-evidence failure this repo has measured repeatedly.
    """
    assert _building_briefs(), (
        f"no brief under {LANE_DIR} matched {LANDING_VERB.pattern!r}; either the "
        "landing verb changed shape or the trigger is broken -- fix the pattern, "
        "do not delete the test"
    )


@pytest.mark.unit
@pytest.mark.parametrize("path", _building_briefs(), ids=lambda p: p.name)
def test_building_brief_names_the_lab_first_step(path: Path) -> None:
    """A brief that lands code names where the change runs first (rule 24(c))."""
    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    if not LAB_WORD.search(text):
        missing.append("the word 'lab'")
    if not LAB_LANE.search(text):
        missing.append("the lane it means ('lab-host-a' or 'lane-k')")
    assert not missing, (
        f"{path.relative_to(REPO)} carries a landing verb but does not name "
        f"{' and '.join(missing)}. {FIX_HINT}"
    )
