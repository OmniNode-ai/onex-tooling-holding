"""One fresh updated head occupies a strict base's update slot while its CI runs (OMN-20864)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests import test_landing_controller as tlc
from tests.test_landing_controller import Harness
from tests.test_landing_strict_cause_fix_order import A, B, _action, _snap, lc, lg
from tests.test_landing_strict_pipeline import STRICT, _log, _rows, _setup, _tick, pr, sha

# OMN-20864: reuse the controller suite's installed-script and world fixtures.
plugin, world, h = tlc.plugin, tlc.world, tlc.h


@pytest.fixture(autouse=True)
def _plugin_tooling_pkg_in_scope(plugin: Path) -> None:
    """These replays were recorded while plugin-tooling-pkg was in scope (OMN-21373)."""
    tlc.lift_out_of_scope(plugin, "plugin-tooling-pkg")


def _pending() -> tuple[Any, dict[str, Any]]:
    snap = _snap(**{A: pr(1, rollup="PENDING", merge_state="BLOCKED"), B: pr(2, merge_state="BEHIND")})
    since = (snap.now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return snap, {A: {"fresh": [sha(1)], "updated_at": since, "at": snap.now_ts}}


def _plan(tmp_path: Path, snap: Any, mem: dict[str, Any]) -> dict[str, Any]:
    (tmp_path / lg.STRICT_SLOT_FILE).write_text(json.dumps(mem), encoding="utf-8")
    return lc.strict_plan({"actions": [_action(2, "update_branch")]},
                          gh=SimpleNamespace(strict_base=lambda _repo, _base: True), snap=snap, state_dir=tmp_path)


def test_pending_fresh_head_defers_another_update_on_its_strict_base(tmp_path: Path) -> None:
    snap, mem = _pending()
    plan = _plan(tmp_path, snap, mem)
    assert plan["deferred_updates"] == {0: STRICT[0]}
    assert plan["inflight"] == {STRICT[0]: A}
    assert plan["details"][0] == (
        f"strict base {STRICT[0]}: {A} is up to date at {sha(1)[:7]} with checks pending since its update at "
        f"{mem[A]['updated_at']}; an update now would be behind once it merges, so it waits")


@pytest.mark.parametrize("case", ["success", "failure", "behind", "foreign-head", "expired", "no-updated-at", "yielded"])
def test_heads_that_are_not_inflight_do_not_defer_another_update(tmp_path: Path, case: str) -> None:
    snap, mem = _pending()
    if case in ("success", "failure"):
        snap.live[A].rollup = case.upper()
    elif case == "behind":
        snap.live[A].merge_state = "BEHIND"
    elif case == "foreign-head":
        snap.live[A].head = sha(1, 1)
    elif case == "expired":
        mem[A]["updated_at"] = (snap.now - timedelta(seconds=lg.STRICT_INFLIGHT_S + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif case == "no-updated-at":
        del mem[A]["updated_at"]
    else:
        mem[A]["yielded"] = sha(1)
    plan = _plan(tmp_path, snap, mem)
    assert plan["deferred_updates"] == {} and plan["inflight"] == {}


def test_strict_slot_record_timestamps_updates_and_observe_keeps_the_timestamp() -> None:
    snap, _ = _pending()
    mem = lg.strict_slot_record({}, [(A, sha(1), f"old -> {sha(1, 1)}")], snap.now_ts)
    assert mem[A]["updated_at"] == snap.now_ts
    before = deepcopy(mem)
    snap.live[A].head = sha(1, 1)
    later = (snap.now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen = lg.strict_slot_observe(mem, snap.live, later)
    assert mem == before and seen[A]["updated_at"] == snap.now_ts
    assert seen[A]["at"] == later
    again = lg.strict_slot_record(seen, [(A, sha(1, 1), "updated")], later)
    assert again[A]["updated_at"] == later and seen[A]["updated_at"] == snap.now_ts


def test_strict_base_waits_for_fresh_ci_then_merges_and_updates_the_next_pr(h: Harness) -> None:
    _setup(h, {n: pr(n, merge_state="BEHIND", after_update={
        "head": sha(n, 1), "rollup": "PENDING", "merge_state": "BLOCKED"}) for n in (1, 2)}, STRICT)
    _tick(h)
    [updated] = _log(h, "update_branch")
    short = updated["pr"]
    other = B if short == A else A
    assert _log(h, "merge") == []
    out = _tick(h)
    assert len(_log(h, "update_branch")) == 1
    row = _rows(out, "update_branch")[other.split("#")[-1]]
    assert row["outcome"] == "deferred" and row["strict_deferred"]
    assert "checks pending since its update" in row["detail"]
    receipt = json.loads((h.state / "ticks.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["strict_order"][0]["inflight"] == f"OmniNode-ai/{short}"
    h.world.edit(lambda w: w["prs"][short].update(rollup="SUCCESS", merge_state="CLEAN"))
    out = _tick(h)
    assert [e["pr"] for e in _log(h, "merge")] == [short]
    assert [e["pr"] for e in _log(h, "update_branch")] == [short, other]
    assert any(o["outcome"] == "updated" for o in _rows(out, "update_branch").values())


def _loose_plan(tmp_path: Path, rollup: str, strict: bool | None, **extra: Any) -> dict[str, Any]:
    snap = _snap(**{B: pr(2, rollup=rollup, merge_state="BEHIND")})
    for k, v in extra.items():
        setattr(snap.live[B], k, v)

    def strict_base(_repo: str, _base: str) -> bool:
        if strict is None:
            raise OSError("settings unread")
        return strict
    return lc.strict_plan({"actions": [_action(2, "update_branch")]},
                          gh=SimpleNamespace(strict_base=strict_base), snap=snap, state_dir=tmp_path)


@pytest.mark.parametrize("rollup", ["PENDING", "SUCCESS"])
def test_a_running_or_green_head_on_a_base_that_needs_no_update_keeps_its_ci(tmp_path: Path, rollup: str) -> None:
    """OMN-19998: omnimarket dev requires no branch up to date (strict=False, its merge queue ruleset disabled), so
    an update there of a head whose checks run or pass merges nothing sooner; it restarts CI while dev moves on."""
    plan = _loose_plan(tmp_path, rollup, False)
    assert plan["deferred_updates"] == {0: STRICT[0]}
    assert plan["details"][0].startswith(f"base {STRICT[0]} requires no branch up to date")


@pytest.mark.parametrize(("rollup", "strict", "extra"), [
    ("FAILURE", False, {}),  # a red head may be red for its base: the update stands
    ("PENDING", True, {}),  # a strict base merges only a current head
    ("SUCCESS", None, {}),  # an unread setting orders like a strict base
    ("SUCCESS", False, {"mergeable": "CONFLICTING"}),  # a conflict is the node's to handle
])
def test_an_update_stands_on_a_red_head_a_strict_or_unread_base_or_a_conflict(
        tmp_path: Path, rollup: str, strict: bool | None, extra: dict[str, Any]) -> None:
    assert _loose_plan(tmp_path, rollup, strict, **extra)["deferred_updates"] == {}
