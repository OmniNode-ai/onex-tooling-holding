"""A repository out of scope gets no worker and no lease from the landing controller, and loses its live ones (OMN-17427).

The scope is the merge sweep's ``sweep_scope.json``, the one repository-scope setting. The installed copy these tests
run holds a fixture scope file; the real tick, the pinned decision node and a fake engine do the rest. Each refusal has
its positive control: the same world, with the scope file naming another repository, sends a worker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tests.test_landing_controller as controller_tests
from tests.test_landing_controller import SHA, Harness, _group_gone, actions, red_pr

h = controller_tests.h
plugin = controller_tests.plugin
world = controller_tests.world

PARKED = "omnimarket"
PARKED_PR = f"{PARKED}#11"
PARKED_NODE = f"OmniNode-ai/{PARKED_PR}"
OTHER_PR = controller_tests.X  # omnibase_core#10
OTHER_NODE = controller_tests.NODE_X


def set_scope(h: Harness, repos: list[str]) -> None:
    path = h.controller.parents[2] / "merge-sweep" / "sweep_scope.json"
    path.write_text(json.dumps({"out_of_scope": {r: "RULING 2026-10-15T00:00:00Z lane=fixture" for r in repos}}),
                    encoding="utf-8")


def two_red_prs(h: Harness) -> None:
    h.world.edit(lambda w: w["prs"].update({PARKED_PR: red_pr(SHA["b"]), OTHER_PR: red_pr(SHA["a"])}))


def test_positive_control_both_red_prs_get_a_worker_while_nothing_is_out_of_scope(h: Harness) -> None:
    set_scope(h, ["some_other_repo"])
    two_red_prs(h)
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 0, out
    assert sorted(a["subject"] for a in actions(out, "dispatch_worker")) == sorted([PARKED_NODE, OTHER_NODE])


def test_an_out_of_scope_repository_gets_no_worker_and_no_lease(h: Harness) -> None:
    set_scope(h, [PARKED])
    two_red_prs(h)
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 0, out
    assert [a["subject"] for a in actions(out, "dispatch_worker")] == [OTHER_NODE]
    assert [le["pr"] for le in h.leases()] == [OTHER_NODE]
    assert actions(out, "merge") == [] and actions(out, "update_branch") == []
    assert f"out_of_scope={PARKED}" in out["summary"] and "fixer_hold=" not in out["summary"]  # no ledger HOLD is in force
    assert f"OmniNode-ai/{PARKED}" in out["decision"].get("fixer_hold", [f"OmniNode-ai/{PARKED}"])


def test_an_unreadable_scope_stops_the_tick_never_reads_as_empty(h: Harness) -> None:
    (h.controller.parents[2] / "merge-sweep" / "sweep_scope.json").write_text("not json", encoding="utf-8")
    two_red_prs(h)
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 1 and "UNKNOWN" in out["stdout"] and "repo scope unreadable" in out["stdout"], out
    assert not (h.state / "workers").exists() or not list((h.state / "workers").glob("*"))


def test_a_live_worker_of_a_repository_that_leaves_the_scope_is_revoked_at_the_next_tick(h: Harness) -> None:
    set_scope(h, ["some_other_repo"])
    two_red_prs(h)
    h.open_gate()
    first = h.tick()
    assert sorted(a["subject"] for a in actions(first, "dispatch_worker")) == sorted([PARKED_NODE, OTHER_NODE])
    lease_of = {le["pr"]: le["lease_id"] for le in h.leases()}
    h.wait_alive(lease_of[PARKED_NODE])
    set_scope(h, [PARKED])
    second = h.tick()
    assert second["rc"] == 0, second
    assert [a["lease_id"] for a in actions(second, "kill_worker")] == [lease_of[PARKED_NODE]]
    assert actions(second, "dispatch_worker") == []
    pgid = int(h.lease_file(lease_of[PARKED_NODE])["pgid"])
    h.wait_for(lambda: _group_gone(pgid))
    third = h.tick()  # termination confirmed: released and recorded, as a deadline kill is
    recorded = {r["lease_id"]: (r["outcome"], r["reason"]) for r in third["decision"]["recorded_outcomes"]}
    assert recorded == {lease_of[PARKED_NODE]: ("timed_out", "revoked")}  # the ladder is unchanged: no rung spent
    assert lease_of[PARKED_NODE] in h.state_json()["revoked_lease_ids"]
    assert "scope_revoked=1" in second["summary"]
    assert actions(third, "dispatch_worker") == []
    assert [le["pr"] for le in h.leases()] == [OTHER_NODE]  # control: the in-scope worker's lease stands


@pytest.mark.parametrize("repos", [[PARKED], ["some_other_repo"]])
def test_the_tick_names_the_scope_it_read(h: Harness, repos: list[str]) -> None:
    set_scope(h, repos)
    two_red_prs(h)
    h.open_gate()
    out = h.tick()
    assert f"out_of_scope={','.join(sorted(repos))}" in out["summary"]


def test_permanently_unparked_omniweb_is_read_and_landed_without_a_release(h: Harness) -> None:
    h.world.edit(lambda w: w["prs"].pop(OTHER_PR))
    h.world.edit(lambda w: w["prs"].update({
        "registry_root#483": {"head": SHA["c"], "rollup": "SUCCESS", "created_at": "2026-09-20T00:00:00Z"},
        "registry_root#484": {"head": SHA["d"], "rollup": "SUCCESS", "created_at": "2026-09-20T00:00:00Z"},
    }))
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 0, out
    assert {a["subject"] for a in actions(out, "merge")} == {"OmniNode-ai/registry_root#483", "OmniNode-ai/registry_root#484"}
    scope = out["summary"].split("out_of_scope=", 1)[1].split()[0].split(",")
    assert "registry_root" not in scope
    assert "infra_repo" in scope  # the cloud repository stays excluded
