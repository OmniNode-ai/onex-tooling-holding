"""A lease the pool gave no engine time leaves the PR's lease window (OMN-19998).

plugin-tooling-pkg#778 (head 2dce955f) sat green on every check and conflicting for 715 minutes on 2026-10-17. Tick
2987 (22:40:40Z) held it at ``gated:worker_gate:lease_window``: its sidecar window held four lease starts in six hours,
17:21:29Z, 18:39:28Z, 19:25:30Z and 21:28:05Z, against the base limit of three. Two of the four, escalation leases 10018
and 10050, ended ``blocked lab_capacity_unavailable``: the pool had no headroom and their engine never started. #887
gave such a lease's dispatch back to the head count and gated no PR on it, but its start stayed in the window, so the
pool's fault still spent the PR's leases. The tick now removes the start of each pool-fault lease (``POOL_FAULT_KINDS``)
from the window, the way ``uncount_head_dispatches`` gives back the head count.
"""

from __future__ import annotations

import json

from tests.test_landing_controller import NODE_X, SHA, X, Harness, _group_gone, actions, h, plugin, world
from tests.test_landing_no_attempt_results import HEAD, lf

__all__ = ["h", "plugin", "world"]

PR_778 = "plugin-tooling-pkg#778"
TICK_2987 = "2026-10-17T22:40:40Z"
WINDOW_778 = ["2026-10-17T17:21:29Z", "2026-10-17T18:39:28Z", "2026-10-17T19:25:30Z", "2026-10-17T21:28:05Z"]
POOL_FAULT_778 = [(PR_778, "2026-10-17T17:21:29Z"), (PR_778, "2026-10-17T18:39:28Z")]  # leases 10018, 10050
CONFLICTING = {"state": "open", "ci": "green", "merge_state": "conflicting", "head_sha": HEAD}


def _gate(stamps: list[str]) -> str:
    return lf.worker_gate_of(PR_778, CONFLICTING, judged=None, dispatches=None, records={}, now=TICK_2987,
                             lease_times=stamps, max_leases=lf.lease_window_limit(0))


def test_the_recorded_window_holds_778_and_without_its_pool_faults_does_not() -> None:
    assert _gate(WINDOW_778) == lf.LEASE_WINDOW_GATE  # the control: tick 2987's reason
    freed = lf.lease_window_uncount({PR_778: WINDOW_778}, POOL_FAULT_778)
    assert freed == {PR_778: ["2026-10-17T19:25:30Z", "2026-10-17T21:28:05Z"]}
    assert _gate(freed[PR_778]) == ""


def test_uncount_removes_one_matching_start_and_nothing_else() -> None:
    other = "omnimarket#1"
    window = {PR_778: ["2026-10-17T17:21:29Z", "2026-10-17T17:21:29Z"], other: ["2026-10-17T17:21:29Z"]}
    # two leases of one PR started in one tick, one of them a pool fault: the other stays counted
    assert lf.lease_window_uncount(window, [(PR_778, "2026-10-17T17:21:29Z")]) == {
        PR_778: ["2026-10-17T17:21:29Z"], other: ["2026-10-17T17:21:29Z"]}
    assert lf.lease_window_uncount(window, [(PR_778, "2026-10-17T18:00:00Z"), (PR_778, "")]) == window
    assert lf.lease_window_uncount({other: ["2026-10-17T17:21:29Z"]}, [(other, "2026-10-17T17:21:29Z")]) == {}
    assert window[PR_778] == ["2026-10-17T17:21:29Z", "2026-10-17T17:21:29Z"]  # the input is not changed


def _window_after_one_worker(h: Harness, mode: str) -> tuple[list[str], dict]:
    h.open_gate()
    h.mode_file.write_text(mode, encoding="utf-8")
    [d1] = actions(h.tick(), "dispatch_worker")
    h.wait_for(lambda: (h.state / "workers" / f"{d1['lease_id']:06d}" / "result.json").exists())
    h.wait_for(lambda: _group_gone(int(h.lease_file(d1["lease_id"])["pgid"])))
    second = h.tick()
    assert second["rc"] == 0, second
    side = json.loads((h.state / "sidecar.json").read_text(encoding="utf-8"))
    return list(side["lease_window"].get(X) or []), second


def test_the_tick_takes_a_pool_fault_lease_out_of_the_window(h: Harness) -> None:
    stamps, second = _window_after_one_worker(h, "blocked-hook-refused")
    assert [(r["pr"], r["outcome"], r["reason"]) for r in second["decision"]["recorded_outcomes"]] == [
        (NODE_X, "timed_out", "revoked")]
    [d2] = actions(second, "dispatch_worker")
    assert d2["head_sha"] == SHA["a"]
    assert len(stamps) == 1  # only d2's start: the worker whose host refused its tools spent no lease of the PR


def test_control_a_worker_that_hit_a_wall_stays_in_the_window(h: Harness) -> None:
    stamps, second = _window_after_one_worker(h, "blocked-other")
    assert len(actions(second, "dispatch_worker")) == 1
    assert len(stamps) == 2
