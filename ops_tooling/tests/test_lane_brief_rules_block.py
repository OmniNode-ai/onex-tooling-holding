"""Brief gate for the three defects that cost the most lane-minutes on 2026-09-16 (OMN-18397).

Each rule below exists because a lane paid for its absence the same day, and each
is a property of the BRIEF rather than of the lane that reads it — a lane cannot
verify a premise the brief never marked, cannot write a report to a path the brief
never named, and cannot tell a delegated mint from its own initiative unless the
brief says so in a fixed form.

| Rule | What it cost |
| -- | -- |
| **Premise** | Nine briefs carried a premise the lane then had to disprove; each cost that
lane's first 20-60 minutes. |
| **Report to file** | Six lane reports were truncated mid-sentence, each costing a round trip. |
| **Mint authority** | One lane refused a mint its brief had explicitly delegated and waited 14
minutes for a re-grant. |

**Canonical source, embedded briefs.** The source is now
`ops_tooling_pkg/lane_rules/lane-rules-block.md`, whose fragments are pinned in
that repository. This module keeps only the checks on committed
`.claude/workflows/*.js` briefs: each brief that embeds a rules block must still
carry the load-bearing fragments a dispatched lane actually reads.

**Match shape.** Each rule is matched on the load-bearing fragment that a lane
must actually see, not on a whole sentence, so the prose can be reworded without
this test going stale on style. The mint-delegation grant line is the one
exception: it is matched **verbatim**, because its whole function is to be a fixed
string a lane can recognise without judgement.

Check-only. Nothing here rewrites a file — rule 19 forbids an auto-fixing hook in
this shared tree. A failure names the file and the sentence to add.
"""

import re
from pathlib import Path

import pytest
from test_workflow_brief_cutover import NAMES

REPO = Path(__file__).parent.parent
LANE_DIR = REPO / "src" / "ops_tooling_pkg" / "handlers"
RULES_SOURCE = "ops_tooling_pkg/lane_rules/lane-rules-block.md"

# A brief that EMBEDS A RULES BLOCK: the token `RULES` appears, either as the
# `const RULES = ...` constant the phase prompts interpolate or as the inline
# `RULES:` paragraph the single-prompt lanes carry. A workflow that only drives a
# committed script and returns a schema (the ledger reconciliation node) carries no rules
# block and is deliberately out of scope -- it dispatches no lane that reports in
# prose, mints anything, or acts on a premise.
RULES_BLOCK = re.compile(r"\bRULES\b")

# The literal grant line. Verbatim on purpose: a lane must be able to recognise a
# delegated mint by string match, with no judgement and no paraphrase to weigh.
MINT_GRANT_LINE = "Mint authority: delegated by the orchestrator for exactly one ticket"

# Load-bearing fragments, one per rule. Both halves of the premise rule are
# matched: naming the verified form without naming the unverified one leaves a
# brief free to simply omit the marking, which is the pre-existing state.
REQUIRED = {
    "the premise rule (the verified form)": re.compile(r"verified by:\s*<command>"),
    "the premise rule (the unverified form)": re.compile(r"UNVERIFIED"),
    "the premise rule (the report line)": re.compile(r"Premises falsified:"),
    "the report-to-file path": re.compile(
        r"(?:\.claude_scratch/reports|DOCS_REPO_PATH/beta/tracking/reports)/"
    ),
    "the report-to-file ceiling": re.compile(r"at most 12 lines"),
    "the mint-delegation grant line": re.compile(re.escape(MINT_GRANT_LINE)),
}

FIX_HINT = (
    "Add the three OMN-18397 rules to this brief's rules block, copied from "
    f"{RULES_SOURCE}: PREMISE (premises are marked "
    "'verified by: <command> => <observation>' or 'UNVERIFIED', and the lane opens "
    "with a 'Premises falsified:' line), REPORT TO FILE (full report to "
    "$registry_root/.claude_scratch/reports/<lane>-<YYYY-MM-DDTHHMMZ>.md, at most 12 "
    "lines returned), and MINT AUTHORITY (one mint only, granted by the literal "
    f"line '{MINT_GRANT_LINE}')."
)


def _lane_briefs() -> list[Path]:
    return sorted(LANE_DIR / folder / f"{name}.js" for name, folder in NAMES.items())


def _briefs_with_rules_block() -> list[Path]:
    return [p for p in _lane_briefs() if RULES_BLOCK.search(p.read_text(encoding="utf-8"))]


@pytest.mark.unit
def test_lane_brief_dir_is_not_empty() -> None:
    """Positive control: an empty glob would make every assertion below vacuous."""
    assert _lane_briefs(), f"no lane briefs found under {LANE_DIR}"


@pytest.mark.unit
def test_at_least_one_brief_embeds_a_rules_block() -> None:
    """Positive control for the trigger itself.

    If `RULES_BLOCK` ever stops matching, the parametrized test below collects
    zero cases and reports green while enforcing nothing -- the
    empty-result-is-not-evidence failure this repo has measured repeatedly.
    """
    assert _briefs_with_rules_block(), (
        f"no brief under {LANE_DIR} matched {RULES_BLOCK.pattern!r}; either the "
        "rules-block shape changed or the trigger is broken -- fix the pattern, "
        "do not delete the test"
    )


# Source-copy assertions moved to ops_tooling_pkg tests/lane_rules/test_lane_rules_block.py
# (OMN-17009).


@pytest.mark.unit
@pytest.mark.parametrize("path", _briefs_with_rules_block(), ids=lambda p: p.name)
def test_every_brief_with_a_rules_block_carries_the_three_rules(path: Path) -> None:
    """Every dispatched brief states all three rules itself.

    A lane reads the brief it is handed, not this repository. A rule that lives
    only in the shared file is a rule the lane never sees.
    """
    text = path.read_text(encoding="utf-8")
    missing = [label for label, pattern in REQUIRED.items() if not pattern.search(text)]
    assert not missing, (
        f"{path.relative_to(REPO)} embeds a rules block but does not carry "
        f"{', '.join(sorted(missing))}. {FIX_HINT}"
    )


# Local-copy matching retired: registry_root carries no copy of the block since OMN-17009.


# --- OMN-18554: every brief that CLAIMS must tell the lane to price the claim --
#
# The rule-4 cost-sentence gate now recognizes the dominant `<ts> | CLAIM | lane=`
# row shape, which it could not see before. It REPORTS an unpriced row today and
# REFUSES one from 2026-09-24T00:00:00Z. A brief that does not carry the sentence
# is a brief whose lanes start failing their first write on that date, so the roll
# is asserted here rather than left to whoever remembers.
#
# Scoped to briefs that ACTUALLY append: a brief that never writes a ledger row
# owes no cost sentence, and requiring one there would be noise that trains people
# to paste the paragraph without reading it.
COST_SENTENCE_MARKER = "rule-4 cost sentence"
PIPE_LEAD_CUTOVER = "2026-09-24T00:00:00Z"


def _briefs_that_append_to_the_ledger() -> list[Path]:
    out = []
    for path in _lane_briefs():
        text = path.read_text(encoding="utf-8")
        if "onex-ledger" in text and "--append" in text:
            out.append(path)
    return out


@pytest.mark.unit
def test_at_least_one_brief_appends_to_the_ledger() -> None:
    """Positive control: a zero-length list would make the next test vacuous."""
    assert _briefs_that_append_to_the_ledger(), (
        "no brief under .claude/workflows appends to the ledger; either the briefs "
        "changed shape or this detector is broken -- an empty result is not evidence "
        "that every brief is compliant"
    )


# Cost-sentence source assertions moved to ops_tooling_pkg
# tests/lane_rules/test_lane_rules_block.py (OMN-17009).


@pytest.mark.unit
@pytest.mark.parametrize("path", _briefs_that_append_to_the_ledger(), ids=lambda p: p.name)
def test_every_claiming_brief_carries_the_cost_sentence_rule(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert COST_SENTENCE_MARKER in text and PIPE_LEAD_CUTOVER in text, (
        f"{path.name} appends ledger rows but does not tell the lane to price its "
        f"CLAIM row. Copy the sentence from {RULES_SOURCE}: an "
        "unpriced CLAIM row is reported today and refused from "
        f"{PIPE_LEAD_CUTOVER} (OMN-18554)."
    )


# --- OMN-18766: every brief that CLAIMS must tell the lane to name its executor -
#
# The same shape as the cost-sentence rule above and for the same reason, one step
# further along: the ledger records what a claim costs and what it cost, and now
# records who paid. `ledger_lock.py` REFUSES an unattributed CLAIM row outright --
# there is no dated grace here, because adding `actor=` is one field and not a
# judgement, so a brief that omits it breaks its lane's first write TODAY rather
# than on a future date.
#
# Measured over the live ledger and its two most recent archive splits,
# 2026-09-11 -> 2026-09-18: 613 of 1,163 distinct lanes (53%) and 62.1% of the
# 4,293 rows carried no attribution at all, which is why the rule is in the shared
# block rather than left to whoever remembers.
#
# Matched on two fragments rather than one sentence: the load-bearing content is
# that BOTH spellings are named, since a brief naming only `actor=` sends a
# delegated run looking for a field it does not have.
EXECUTOR_MARKER = "names its executor"
EXECUTOR_FIELDS = ("actor=", "model=")


# Executor source assertions moved to ops_tooling_pkg tests/lane_rules/test_lane_rules_block.py
# (OMN-17009).


@pytest.mark.unit
@pytest.mark.parametrize("path", _briefs_that_append_to_the_ledger(), ids=lambda p: p.name)
def test_every_claiming_brief_carries_the_executor_attribution_rule(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [field for field in EXECUTOR_FIELDS if field not in text]
    assert EXECUTOR_MARKER in text and not missing, (
        f"{path.name} appends ledger rows but does not tell the lane to name the "
        f"executor of its CLAIM row (missing: {missing or [EXECUTOR_MARKER]}). Copy "
        f"the sentence from {RULES_SOURCE}: ledger_lock.py "
        "refuses a CLAIM row carrying neither actor= nor model= (OMN-18766)."
    )
