"""The lab stack reaper model holds its properties and carries an approving verdict (OMN-20864).

Plan unit M47, deliverable 1: a TLA+ model whose adopted design holds NeverRemoveLive (never remove
a stack with a live CLAIM) and RemovedWithinOneInterval (a TERMINAL-closed stack is removed within
one interval), each property failing on a mutation, and an approving independent verdict that names
the model's digest. TLC runs on a lab host (``lab_stack_reaper_tlc.py``); this reads the committed
results, so editing the model or a configuration without rerunning TLC and the review turns it red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lab_stack_reaper_tlc import (
    DEADLINE,
    EVENTUALLY_REMOVED,
    EXPECTED,
    MODEL_DIR,
    NEVER_REMOVE_LIVE,
    NO_USER_LOSES_STACK,
    OVERDUE_ALARMED,
    PASS,
    model_digest,
)

NO_ERROR = "Model checking completed. No error has been found."
VIOLATION_RE = re.compile(
    r"^Error: (?:Invariant (\w+) is|Temporal property (\w+) was) violated\.$", re.MULTILINE
)
VERDICT_RE = re.compile(r"^\*\*VERDICT: (PASS|PASS-WITH-CONDITIONS|FAIL)\.\*\*", re.MULTILINE)
DIGEST_RE = re.compile(r"^Model digest: `([0-9a-f]{64})`", re.MULTILINE)
HOME_RE = re.compile(r"(?:/home|/Users)/[^/\s]+/")


def outcome_problems(text: str, expected: str) -> list[str]:
    """Why a result file does not show its expected outcome; empty when it does."""
    rc = re.findall(r"^rc=(\d+)$", text, re.MULTILINE)
    found = re.findall(VIOLATION_RE, text)
    violated = [invariant or temporal for invariant, temporal in found]
    problems: list[str] = []
    if not rc:
        problems.append("no rc line: the run did not finish")
    if expected == PASS:
        if NO_ERROR not in text or rc != ["0"]:
            problems.append(f"expected no error and rc=0, read violated={violated} rc={rc}")
    elif violated != [expected] or rc == ["0"]:
        problems.append(f"expected {expected} violated, read violated={violated} rc={rc}")
    return problems


def verdict_problems(review: str, digest: str) -> list[str]:
    """Why REVIEW.md is not an approving verdict on this digest; empty when it is."""
    problems: list[str] = []
    verdicts = VERDICT_RE.findall(review)
    if not verdicts:
        problems.append("no verdict line")
    elif verdicts[-1] == "FAIL":
        problems.append("the newest verdict is FAIL")
    named = DIGEST_RE.findall(review)
    if not named:
        problems.append("the verdict names no model digest")
    elif named[-1] != digest:
        problems.append(f"the verdict names {named[-1]}, the model is {digest}")
    return problems


def _result(name: str) -> str:
    return (MODEL_DIR / "results" / f"{name}.out").read_text(encoding="utf-8")


def _names(expected: str) -> list[str]:
    return sorted(n for n, e in EXPECTED.items() if e == expected)


def test_config_set_matches_expectations() -> None:
    configs = sorted(p.stem for p in (MODEL_DIR / "cfg").glob("*.cfg"))
    results = sorted(p.stem for p in (MODEL_DIR / "results").glob("*.out"))
    assert configs == sorted(EXPECTED)
    assert results == sorted(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_results_carry_model_digest(name: str) -> None:
    first = _result(name).splitlines()[0]
    assert first == f"model_digest={model_digest()}", f"{name}: rerun TLC on the current model"


@pytest.mark.parametrize("name", _names(PASS))
def test_adopted_design_passes(name: str) -> None:
    assert outcome_problems(_result(name), PASS) == []


SAFETY = (NEVER_REMOVE_LIVE, NO_USER_LOSES_STACK)
REMOVAL = (DEADLINE, OVERDUE_ALARMED, EVENTUALLY_REMOVED)
WITNESSES = ("NoRemovalEver", "NoLateRemoval", "NoRetrySucceeded")


@pytest.mark.parametrize("name", [n for p in SAFETY for n in _names(p)])
def test_never_remove_live_mutations(name: str) -> None:
    assert outcome_problems(_result(name), EXPECTED[name]) == []


@pytest.mark.parametrize("name", [n for p in REMOVAL for n in _names(p)])
def test_deadline_mutations(name: str) -> None:
    assert outcome_problems(_result(name), EXPECTED[name]) == []


@pytest.mark.parametrize("name", [n for p in WITNESSES for n in _names(p)])
def test_removal_witnesses(name: str) -> None:
    assert outcome_problems(_result(name), EXPECTED[name]) == []


def test_each_property_fails_on_a_mutation() -> None:
    for prop in (*SAFETY, *REMOVAL, *WITNESSES):
        assert _names(prop), f"no configuration violates {prop}"


def test_verdict_names_model_digest() -> None:
    review = (MODEL_DIR / "REVIEW.md").read_text(encoding="utf-8")
    assert verdict_problems(review, model_digest()) == []


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_results_hold_no_home_path(name: str) -> None:
    assert not HOME_RE.search(_result(name))


# Planted inputs: each check refuses what it exists to refuse.


def test_planted_mutation_that_passes_is_refused() -> None:
    planted = f"model_digest=x\n{NO_ERROR}\nrc=0\n"
    assert outcome_problems(planted, NEVER_REMOVE_LIVE)


def test_planted_mutation_violating_another_property_is_refused() -> None:
    planted = "Error: Invariant NoUserLosesStack is violated.\nrc=12\n"
    assert outcome_problems(planted, NEVER_REMOVE_LIVE)
    fixed = planted.replace("NoUserLosesStack", NEVER_REMOVE_LIVE)
    assert not outcome_problems(fixed, NEVER_REMOVE_LIVE)


def test_planted_temporal_violation_is_read() -> None:
    planted = f"Error: Temporal property {EVENTUALLY_REMOVED} was violated.\nrc=13\n"
    assert outcome_problems(planted, EVENTUALLY_REMOVED) == []
    assert outcome_problems(planted, PASS)


def test_planted_adopted_violation_or_timeout_is_refused() -> None:
    assert outcome_problems(f"Error: Invariant {DEADLINE} is violated.\nrc=12\n", PASS)
    assert outcome_problems("TLC timed out after 3600s\nrc=124\n", PASS)
    assert outcome_problems(f"{NO_ERROR}\n", PASS)


def test_planted_verdicts_are_refused() -> None:
    digest = "a" * 64
    good = f"**VERDICT: PASS-WITH-CONDITIONS.**\n\nModel digest: `{digest}`\n"
    assert verdict_problems(good, digest) == []
    assert verdict_problems(good, "b" * 64)
    assert verdict_problems(good.replace("PASS-WITH-CONDITIONS", "FAIL"), digest)
    assert verdict_problems("**VERDICT: PASS.**\n", digest)


def test_planted_model_edit_changes_digest(tmp_path: Path) -> None:
    copy = tmp_path / "model"
    (copy / "cfg").mkdir(parents=True)
    for path in [MODEL_DIR / "LabStackReaper.tla", *(MODEL_DIR / "cfg").glob("*.cfg")]:
        (copy / path.relative_to(MODEL_DIR)).write_bytes(path.read_bytes())
    assert model_digest(copy) == model_digest()
    module = copy / "LabStackReaper.tla"
    module.write_text(module.read_text().replace("UseLock THEN", "~UseLock THEN"))
    assert model_digest(copy) != model_digest()
