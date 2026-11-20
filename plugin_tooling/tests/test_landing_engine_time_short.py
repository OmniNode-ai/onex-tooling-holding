"""A worker the lab pool gave no engine time made no attempt, and its PR is neither gated nor charged (OMN-19998).

ops_tooling_pkg#761 (head b8ba9835) sat green and unlanded for hours on 2026-10-17. Its conflict escalation worker,
lease 10049, was spawned at 18:39:28Z on a 45-minute lease, waited for a pool slot until 19:01:44Z, prepared its
worktree on h903 until 19:15:15Z, and started its engine with 691 s left before the deadline, under the 20-minute
``PLACEMENT_RESERVE_S`` the placement wait keeps for the engine. The engine was ended at 572 s with no result file, and
the controller counted the lease as the head's conflict attempt. Of the 18 workers in the newest 1,312 lease
directories whose engine started with under 20 minutes left, 10 ended ``no_result_file``, against 222 of 1,294 that
started with more.

The worker now checks the reserve again after its setup and, when the setup spent it, writes the same
``blocked lab_capacity_unavailable`` result as a pool that had no headroom, without starting the engine
(``test_landing_worker_relay.py::test_a_setup_that_spent_the_reserve_starts_no_engine_and_writes_the_pool_result``). The
controller reads that result as a no-attempt caused by the pool, like ``host_tools_refused`` (OMN-20961): the lease is
revoked, the PR is not gated, and the dispatch is given back to the head's count.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_landing_no_attempt_results import HEAD, NOW, PR, _lease, _write_result, lc, lf, lw

LAB = {"kind": "blocked", "reason": "lab_capacity_unavailable"}


def test_a_worker_the_pool_gave_no_engine_time_made_no_attempt(tmp_path: Path) -> None:
    _write_result(tmp_path, 1, LAB)
    assert lc.no_attempt_kind(lw, tmp_path, 1) == lf.LAB_CAPACITY_REASON


def test_a_pool_short_pr_or_cause_lease_is_revoked_without_a_gate(tmp_path: Path) -> None:
    cause = "cause:OmniNode-ai/omniclaude:7cf85c4ab1d1"
    leases = [_lease(1), _lease(2, pr=cause), _lease(3)]
    payloads = {1: LAB, 2: LAB, 3: {"kind": "blocked", "reason": "src_freeze_refuses_new_node"}}
    for lid, payload in payloads.items():
        _write_result(tmp_path, lid, payload)
    results = [{"lease_id": le["lease_id"], "pr": le["pr"], "kind": "blocked"} for le in leases]
    probes = [{"lease_id": le["lease_id"], "group_alive": False, "tagged_alive": False} for le in leases]
    rows = lc.revoke_no_attempt_results(lw, tmp_path, leases, probes, results, NOW)
    assert [(r["lease_id"], r["result_kind"]) for r in rows] == [
        (1, "lab_capacity_unavailable"), (2, "lab_capacity_unavailable")]
    assert [r["lease_id"] for r in results] == [3]  # a worker that hit a wall is still the node's to grade
    assert lc.recover_no_result_inputs(tmp_path) == {}  # the pool's fault gates no PR, and a lost sidecar replays none


def test_a_pool_short_worker_is_not_charged_to_its_head() -> None:
    assert lc.POOL_FAULT_KINDS == ("host_tools_refused", "lab_capacity_unavailable")
    d = {PR: {"head": HEAD, "n": 3, "at": NOW}}
    assert lf.uncount_head_dispatches(d, [(PR, HEAD)]) == {PR: {"head": HEAD, "n": 2, "at": NOW}}


@pytest.mark.parametrize("payload", [
    {"kind": "blocked", "reason": "nothing_to_fix: all green"},
    {"kind": "waiting_ci"},
    {"kind": "fix_submitted", "reason": "lab_capacity_unavailable"},
])
def test_other_no_attempt_kinds_are_read_as_before(tmp_path: Path, payload: dict[str, str]) -> None:
    _write_result(tmp_path, 1, payload)
    assert lc.no_attempt_kind(lw, tmp_path, 1) == {"blocked": "nothing_to_fix", "waiting_ci": "waiting_ci"}.get(
        payload["kind"])
