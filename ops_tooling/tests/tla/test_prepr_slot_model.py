"""The pre-PR model exercises slots scoped to two independent hosts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

MODEL = Path(__file__).resolve().parents[2] / "tla" / "prepr_slot"
EXPECTED = {
    "design": None,
    "design_nonfork": None,
    "design_wide": None,
    "approval_any": "ForkApproved",
    "check_then_act": "NoTwoProvers",
    "enter_at_current": "ForkApproved",
    "pass_any_receipt": "PassIsCurrent",
    "post_stale": "ReceiptFresh",
    "release_keeps_head": "ReleasedSlotEmpty",
    "witness_eviction": "NoEviction",
    "witness_occupied": "NoOccupant",
    "witness_pass": "NoPass",
    "witness_receipt": "NoReceiptEver",
}
NO_ERROR = "Model checking completed. No error has been found."


def _digest() -> str:
    digest = hashlib.sha256()
    for path in [MODEL / "PreprSlot.tla", *sorted((MODEL / "cfg").glob("*.cfg"))]:
        digest.update(path.relative_to(MODEL).as_posix().encode() + b"\n")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _outcome_matches(text: str, expected: str | None) -> bool:
    rc = re.findall(r"^rc=(\d+)$", text, re.MULTILINE)
    errors = re.findall(r"^Error: Invariant (\w+) is violated\.$", text, re.MULTILINE)
    if expected is None:
        return rc == ["0"] and NO_ERROR in text and "Error:" not in text
    return rc == ["12"] and errors == [expected] and NO_ERROR not in text


def _sets(name: str) -> dict[str, set[str]]:
    text = (MODEL / "cfg" / f"{name}.cfg").read_text(encoding="utf-8")
    return {
        key: {value.strip() for value in values.split(",")}
        for key, values in re.findall(r"^\s*(\w+) = \{([^}]+)\}", text, re.MULTILINE)
    }


def test_wide_design_has_three_provers_and_two_hosts_of_two_slots() -> None:
    sets = _sets("design_wide")
    assert len(sets["Provers"]) >= 3
    assert len(sets.get("Hosts", set())) >= 2
    assert len(sets.get("SlotNumbers", set())) >= 2
    assert len(sets["Heads"]) >= 2


def test_slot_identity_includes_the_host() -> None:
    text = (MODEL / "PreprSlot.tla").read_text(encoding="utf-8")
    assert re.search(r"^Slots\s*==\s*Hosts\s*\\X\s*SlotNumbers\s*$", text, re.MULTILINE)
    # Small mutation probes still exercise contention for one physical slot.
    sets = _sets("check_then_act")
    assert len(sets["Provers"]) >= 2
    assert len(sets.get("Hosts", set())) == 1
    assert len(sets.get("SlotNumbers", set())) == 1


@pytest.mark.parametrize("path", sorted((MODEL / "cfg").glob("*.cfg")), ids=lambda p: p.stem)
def test_every_probe_declares_host_scoped_slots(path: Path) -> None:
    sets = _sets(path.stem)
    assert sets.get("Hosts")
    assert sets.get("SlotNumbers")
    assert "Slots" not in sets


def test_probe_set_includes_designs_mutations_and_witnesses() -> None:
    assert {p.stem for p in (MODEL / "cfg").glob("*.cfg")} == set(EXPECTED)
    assert {p.stem for p in (MODEL / "results").glob("*.out")} == set(EXPECTED)


@pytest.mark.parametrize("name", [name for name, outcome in EXPECTED.items() if outcome is None])
def test_design_checks_every_safety_invariant(name: str) -> None:
    text = (MODEL / "cfg" / f"{name}.cfg").read_text(encoding="utf-8")
    checked = set(re.findall(r"^INVARIANT (.+)$", text, re.MULTILINE)[0].split())
    assert {
        "TypeOK",
        "NoTwoProvers",
        "ReleasedSlotEmpty",
        "ReceiptFresh",
        "PassIsCurrent",
        "ForkApproved",
    } <= checked


@pytest.mark.parametrize("name", EXPECTED)
def test_tlc_results_are_current_and_show_the_expected_outcome(name: str) -> None:
    text = (MODEL / "results" / f"{name}.out").read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"model_digest={_digest()}", "rerun TLC on the current model"
    assert _outcome_matches(text, EXPECTED[name])
    assert not re.search(r"/(?:home|Users)/[^/\s]+/", text)


def test_outcome_reader_refuses_missing_runs_and_wrong_mutants() -> None:
    passing = f"{NO_ERROR}\nrc=0\n"
    mutant = "Error: Invariant NoTwoProvers is violated.\nrc=12\n"
    assert _outcome_matches(passing, None)
    assert _outcome_matches(mutant, "NoTwoProvers")
    assert not _outcome_matches(passing, "NoTwoProvers")
    assert not _outcome_matches(mutant, None)
    assert not _outcome_matches(mutant, "ForkApproved")
    assert not _outcome_matches(NO_ERROR, None)
    assert not _outcome_matches("TLC timed out\nrc=124\n", None)


