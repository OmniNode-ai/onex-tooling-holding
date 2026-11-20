"""The controller never works a head the PR has left (OMN-19998, omnibase_infra#4929, 2026-10-14).

Worker L7371 pushed #4929's fix and was revoked as timed out; the controller then sent worker L7380 to the
superseded head 64074ace, because the PR watcher's incremental read had not seen the push. Two rules close it:
a worker is never dispatched to a head older than the PR's current head (read exactly, right before the spawn),
and a lease that ran to its deadline while the PR moved off its dispatch head is no failed attempt on the new
head (the lease is revoked, the engine ladder unchanged).
"""

from __future__ import annotations

import json
import time
from typing import Any

from tests import test_landing_controller as base
from tests.test_landing_controller import NODE_X, SHA, Harness, X, _group_gone, actions

# the controller suite's fixtures, by name, so this module's tests run its real-process harness
plugin, world, h = base.plugin, base.world, base.h


def _engine_runs(h: Harness) -> list[dict[str, Any]]:
    return [json.loads(line) for line in h.engine_log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _record(h: Harness) -> dict[str, Any]:
    [rec] = [r for r in h.state_json()["records"] if r["pr"] == NODE_X]
    return rec


def test_a_worker_is_never_dispatched_to_a_head_the_pr_has_left(h: Harness) -> None:
    """The snapshot (the watcher) reads head ``a``; GitHub is at ``b``. No worker starts on ``a``; the next tick,
    once the snapshot has caught up, sends one to ``b`` on the same engine rung."""
    h.open_gate()
    h.world.edit(lambda w: w["prs"][X].update(head_now=SHA["b"]))
    env = {"LANDING_PLACEMENT_DIR": str(h.tmp / "placement")}
    first = h.tick(env=env)
    [stale] = actions(first, "dispatch_worker")
    assert stale["head_sha"] == SHA["a"]
    [outcome] = [o for o in first["outcomes"] if o["kind"] == "dispatch_worker"]
    assert outcome["outcome"] == "head-moved" and SHA["b"][:10] in outcome["detail"]
    assert _engine_runs(h) == []  # nothing ran against the superseded head
    assert not (h.state / "workers" / f"{stale['lease_id']:06d}" / "lease.json").exists()

    h.world.edit(lambda w: w["prs"][X].update(head=SHA["b"], head_now=SHA["b"]))
    second = h.tick(env=env)
    [fresh] = actions(second, "dispatch_worker")
    assert fresh["head_sha"] == SHA["b"] and fresh["brief"]["engine"] == "claude_sonnet"
    assert [o["outcome"] for o in second["outcomes"] if o["kind"] == "dispatch_worker"] == ["spawned"]
    assert _record(h)["ladder_index"] == 0  # the skipped dispatch was no attempt


def test_a_worker_dispatches_when_the_exact_head_is_the_snapshots(h: Harness) -> None:
    """Positive control: the exact head read agrees with the snapshot, so the worker starts."""
    h.open_gate()
    h.world.edit(lambda w: w["prs"][X].update(head_now=SHA["a"]))
    out = h.tick(env={"LANDING_PLACEMENT_DIR": str(h.tmp / "placement")})
    assert [o["outcome"] for o in out["outcomes"] if o["kind"] == "dispatch_worker"] == ["spawned"]


def test_a_timed_out_worker_whose_push_moved_the_head_is_no_failed_attempt(h: Harness) -> None:
    """The lease ran to its deadline and was killed; meanwhile the PR left its dispatch head (the worker's push).
    The node records ``timed_out reason=revoked``, the ladder stays on the same rung and the next worker goes to
    the PR's current head."""
    h.open_gate()
    env = {"LANDING_LEASE_SECONDS": "2", "LANDING_PLACEMENT_DIR": str(h.tmp / "placement")}
    [d1] = actions(h.tick(env=env), "dispatch_worker")
    assert d1["brief"]["engine"] == "claude_sonnet" and d1["head_sha"] == SHA["a"]
    h.wait_alive(d1["lease_id"])
    time.sleep(2.5)
    second = h.tick(env=env)  # deadline passed: the kill is sent
    assert [a["lease_id"] for a in actions(second, "kill_worker")] == [d1["lease_id"]]
    h.wait_for(lambda: _group_gone(int(h.lease_file(d1["lease_id"])["pgid"])))
    h.world.edit(lambda w: w["prs"][X].update(head=SHA["b"]))  # the worker's push, seen by the snapshot
    third = h.tick(env=env)
    recorded = third["decision"]["recorded_outcomes"]
    assert [(r["lease_id"], r["outcome"], r["reason"]) for r in recorded] == [(d1["lease_id"], "timed_out", "revoked")]
    [d2] = actions(third, "dispatch_worker")
    assert d2["brief"]["engine"] == "claude_sonnet" and d2["head_sha"] == SHA["b"]
    assert _record(h)["ladder_index"] == 0
    assert d1["lease_id"] in h.state_json()["revoked_lease_ids"]


def test_a_timed_out_worker_on_an_unmoved_head_is_still_a_failed_attempt(h: Harness) -> None:
    """Positive control: the PR is still at the dispatch head, so the timeout climbs the ladder as it always did."""
    h.open_gate()
    env = {"LANDING_LEASE_SECONDS": "2", "LANDING_PLACEMENT_DIR": str(h.tmp / "placement")}
    [d1] = actions(h.tick(env=env), "dispatch_worker")
    h.wait_alive(d1["lease_id"])
    time.sleep(2.5)
    h.tick(env=env)
    h.wait_for(lambda: _group_gone(int(h.lease_file(d1["lease_id"])["pgid"])))
    third = h.tick(env=env)
    recorded = third["decision"]["recorded_outcomes"]
    assert [(r["lease_id"], r["outcome"], r["reason"]) for r in recorded] == [(d1["lease_id"], "timed_out", "deadline")]
    [d2] = actions(third, "dispatch_worker")
    assert d2["brief"]["engine"] == "claude_sonnet"
