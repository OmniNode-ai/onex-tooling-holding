"""A head a worker found nothing to fix, that the watcher reads green, is merged, not held (OMN-19998).

plugin-tooling-pkg#1763 sat green and CLEAN in the throughput tick for 55 minutes at 2026-11-09T08:31Z, held by the
controller's ``gated:worker_gate:no_attempt:nothing_to_fix``; omnibase_infra#5810 and #5817 were held the same way
earlier that night. A worker that finds nothing red to fix has said the facts' red names nothing, and the gate it
leaves holds the head until the head or the worker's input changes. The facts now read such a head green (no check
named red, the watcher GREEN at the head, no conflict), so the node merges it. A red the facts name still goes to a
worker and stays gated after a nothing_to_fix answer, and a conflicting head is never held by that answer.
"""

from __future__ import annotations

import json
from typing import Any

from tests.test_landing_controller import Harness, _group_gone, actions, h, plugin, world
from tests.test_landing_controller import SHA, X
from tests.test_landing_controller import NODE_X
from tests.test_landing_controller_classes import _only, lf

FIXTURES = (h, plugin, world)  # the harness fixtures pytest finds in this module's namespace

HEAD = SHA["a"]
NOW = "2026-11-09T08:30:00Z"
GREEN_RUNS = [["Lint", "completed", "success", "2026-11-09T03:49:54Z"],
              ["validate-plugin", "completed", "success", "2026-11-09T04:27:11Z"]]
INPUT = "f" * 64


# --------------------------------------------------------------------------------------- the pure parts


def _facts(**extra: Any) -> dict[str, Any]:
    return {"state": "open", "ci": "red", "red_checks": [], "merge_state": "clean", "head_sha": HEAD, **extra}


def _ci(**extra: Any) -> dict[str, Any]:
    return {"sha": HEAD, "red": [], "pending": [], "runs": GREEN_RUNS, "verdict": "GREEN", **extra}


def _judged(**extra: Any) -> dict[str, Any]:
    return {"head": HEAD, "input": INPUT, "kind": "nothing_to_fix", "lease_id": 1, **extra}


def test_a_nothing_to_fix_judgement_at_this_input_makes_a_green_watcher_head_green() -> None:
    assert lf.blocked_head_handler.nothing_to_fix_green(_facts(), _ci(), _judged(), INPUT) == {"ci": "green", "red_class": None, "red_checks": []}


def test_every_other_shape_keeps_the_facts_red() -> None:
    cases = {
        "a red the facts name": (_facts(red_checks=["Tests"]), _ci(), _judged(), INPUT),
        "a conflicting head": (_facts(merge_state="conflicting"), _ci(), _judged(), INPUT),
        "a watcher red": (_facts(), _ci(red=["Tests"], verdict="RED"), _judged(), INPUT),
        "a watcher pending check": (_facts(), _ci(pending=["Tests"], verdict="PENDING"), _judged(), INPUT),
        "a watcher record at another head": (_facts(), _ci(sha=SHA["b"]), _judged(), INPUT),
        "no judgement": (_facts(), _ci(), None, INPUT),
        "a judgement at another head": (_facts(), _ci(), _judged(head=SHA["b"]), INPUT),
        "a judgement at another input": (_facts(), _ci(), _judged(), "0" * 64),
        "another kind of no-attempt": (_facts(), _ci(), _judged(kind="waiting_ci"), INPUT),
        "a closed PR": (_facts(state="closed"), _ci(), _judged(), INPUT),
        "a head already green": (_facts(ci="green"), _ci(), _judged(), INPUT),
        "an unread watcher record": (_facts(), None, _judged(), INPUT),
    }
    for name, (facts, ci, judged, fingerprint) in cases.items():
        assert lf.blocked_head_handler.nothing_to_fix_green(facts, ci, judged, fingerprint) == {}, name


def _gate(facts: dict[str, Any], no_result: dict[str, Any]) -> str:
    return lf.worker_gate_of("omnibase_core#10", facts, judged={}, dispatches={}, records={}, now=NOW, no_result=no_result)


def test_a_conflicting_head_is_never_held_by_a_nothing_to_fix_answer() -> None:
    facts = {"state": "open", "ci": "green", "merge_state": "conflicting", "head_sha": HEAD, "red_checks": []}
    judged = {"head": HEAD, "input": lf.worker_input_fingerprint(facts), "kind": "nothing_to_fix"}
    assert _gate(facts, judged) == ""


def test_the_control_a_red_or_other_no_attempt_still_gates() -> None:
    red = {"state": "open", "ci": "red", "merge_state": "clean", "head_sha": HEAD, "red_checks": ["Tests"]}
    assert _gate(red, {"head": HEAD, "input": lf.worker_input_fingerprint(red), "kind": "nothing_to_fix"}) == "no_attempt:nothing_to_fix"
    conflicting = {**red, "merge_state": "conflicting"}
    for kind in ("waiting_ci", "host_tools_refused"):
        assert _gate(conflicting, {"head": HEAD, "input": lf.worker_input_fingerprint(conflicting), "kind": kind}) == f"no_attempt:{kind}"


# ------------------------------------------------------------------------------- the real controller tick


def _pr(**extra: Any) -> dict[str, Any]:
    """The controller's read of the held PR: GitHub's FAILURE rollup, a GREEN watcher record, CLEAN."""
    return {"head": HEAD, "rollup": "FAILURE", "merge_state": "CLEAN", "red": [], "pending": [], "runs": GREEN_RUNS,
            "created_at": "2026-11-08T08:58:34Z", **extra}


def _receipt(h: Harness) -> dict[str, Any]:
    return json.loads((h.state / "ticks.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def _nothing_to_fix_tick(h: Harness) -> dict[str, Any]:
    """Send one worker that answers nothing_to_fix, then tick again: the tick that read the gate."""
    h.mode_file.write_text("blocked-nothing-to-fix", encoding="utf-8")
    [d1] = actions(h.tick(), "dispatch_worker")
    h.wait_for(lambda: (h.state / "workers" / f"{d1['lease_id']:06d}" / "result.json").exists())
    h.wait_for(lambda: _group_gone(int(h.lease_file(d1["lease_id"])["pgid"])))
    return h.tick()


def test_tick_merges_a_green_watcher_head_after_a_worker_found_nothing_to_fix(h: Harness) -> None:
    _only(h, X, _pr())
    second = _nothing_to_fix_tick(h)
    assert second["rc"] == 0, second
    assert [a["subject"] for a in actions(second, "merge")] == [NODE_X], second
    assert actions(second, "dispatch_worker") == [], second
    receipt = _receipt(h)
    assert receipt["worker_gated"] == {}, receipt["worker_gated"]
    assert receipt["landing_classes"]["nothing_to_fix_green"] == {X: HEAD}


def test_tick_control_a_red_the_facts_name_still_goes_to_a_worker_and_stays_gated(h: Harness) -> None:
    _only(h, X, _pr(red=["Tests"], runs=[["Tests", "completed", "failure", "r1"]]))
    second = _nothing_to_fix_tick(h)
    assert second["rc"] == 0, second
    assert actions(second, "merge") == [] and actions(second, "dispatch_worker") == [], second
    receipt = _receipt(h)
    assert receipt["worker_gated"] == {X: "no_attempt:nothing_to_fix"}
    assert receipt["landing_classes"]["nothing_to_fix_green"] == {}


def test_tick_control_a_conflicting_head_gets_another_worker_not_a_hold(h: Harness) -> None:
    _only(h, X, _pr(merge_state="DIRTY", mergeable="CONFLICTING"))
    second = _nothing_to_fix_tick(h)
    assert second["rc"] == 0, second
    assert actions(second, "merge") == [], second
    assert [a["head_sha"] for a in actions(second, "dispatch_worker")] == [HEAD], second
    assert X not in _receipt(h)["worker_gated"]
