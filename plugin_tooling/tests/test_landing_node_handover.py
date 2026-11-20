"""Plan S8 pulled forward for one repository at a time (OMN-20750): the landing node arms, the controller is the backstop.

For a repository named in the controller's node hand-over configuration (``node-handover.json`` in its state dir,
or the file ``LANDING_NODE_HANDOVER`` names; the shipped default names none), the controller no longer merges, which
on a merge-queue repository is the enqueue, a green PR on first sight. omnimarket's landing orchestrator arms it. The
controller merges it only as a backstop, once the head has been green and unarmed for the configured minutes, and
records that merge as ``handover: backstop`` with the elapsed minutes, so node arms and backstop arms can be counted
apart. The clock is the controller's own (``node_handover_clock`` in its sidecar), keyed ``repo#n@head``, so a new
head starts it again. Every other repository lands as before.

The PR the controller holds is presented to the pinned node as pending, so the node emits no merge for it and never
gives it the runtime token: a held omnimarket PR cannot hold an omnibase_infra runtime PR back.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tests import test_landing_controller as base
from tests.test_landing_bus_owner_deferral import lf
from tests.test_landing_controller import SHA, Harness, actions

h, plugin, world = base.h, base.plugin, base.world

M = "omnimarket#40"
NODE_M = f"OmniNode-ai/{M}"
CORE = "omnibase_core#11"
INFRA = "omnibase_infra#20"
WAIT = 15


def _ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _green(head: str, **extra: Any) -> dict[str, Any]:
    return {"head": head, "rollup": "SUCCESS", "created_at": "2026-09-20T00:00:00Z", "runtime": False, **extra}


def setup(
    h: Harness, prs: dict[str, dict[str, Any]], *, repos: list[str] | None = None, clock: dict[str, str] | None = None
) -> None:
    """The world holds exactly ``prs``; the hand-over file names ``repos`` (none: no file); the sidecar holds ``clock``."""
    h.world.edit(lambda w: w.update(prs=prs))
    cfg = h.tmp / "node-handover.json"
    if repos is not None:
        cfg.write_text(json.dumps({"repos": repos, "wait_minutes": WAIT}), encoding="utf-8")
    h.env["LANDING_NODE_HANDOVER"] = str(cfg)
    if clock is not None:
        (h.state / "sidecar.json").write_text(json.dumps({"node_handover_clock": clock}), encoding="utf-8")
    h.open_gate()


def receipt(h: Harness) -> dict[str, Any]:
    rec: dict[str, Any] = json.loads((h.state / "ticks.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    return rec


def merge_rows(h: Harness) -> list[dict[str, Any]]:
    path = h.state / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    return [r for r in rows if r["kind"] == "merge"]


def clock(h: Harness) -> dict[str, str]:
    side: dict[str, Any] = json.loads((h.state / "sidecar.json").read_text(encoding="utf-8"))
    return dict(side.get("node_handover_clock") or {})


def merged(h: Harness, short: str) -> bool:
    return bool(h.world.read()["prs"][short].get("state") == "MERGED")


# ------------------------------------------------------------------------------------ the node's window


def test_a_young_green_omnimarket_pr_is_left_to_the_node(h: Harness) -> None:
    """Green and unarmed, first seen this tick: no merge (no enqueue), the clock starts at this head."""
    setup(h, {M: _green(SHA["c"])}, repos=["omnimarket"])
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert actions(out, "merge") == []
    assert not merged(h, M) and merge_rows(h) == []
    rec = receipt(h)
    assert rec["node_handover"]["prs"] == {M: "await"}
    assert rec["node_handover"]["repos"] == ["omnimarket"] and rec["node_handover"]["wait_minutes"] == WAIT
    assert " handover_await=1" in out["summary"]
    assert list(clock(h)) == [f"{M}@{SHA['c']}"]


def test_still_inside_the_window_on_a_later_tick(h: Harness) -> None:
    setup(h, {M: _green(SHA["c"])}, repos=["omnimarket"], clock={f"{M}@{SHA['c']}": _ago(WAIT - 2)})
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert actions(out, "merge") == [] and not merged(h, M)
    assert receipt(h)["node_handover"]["prs"] == {M: "await"}


def test_at_the_wait_the_controller_merges_once_and_records_the_backstop(h: Harness) -> None:
    """Green and unarmed for the configured minutes: one merge, typed ``handover: backstop`` with the minutes."""
    since = _ago(WAIT + 1)
    setup(h, {M: _green(SHA["c"])}, repos=["omnimarket"], clock={f"{M}@{SHA['c']}": since})
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert [(a["subject"], a["head_sha"]) for a in actions(out, "merge")] == [(NODE_M, SHA["c"])]
    assert merged(h, M)
    [row] = merge_rows(h)
    assert row["outcome"] == "merged" and row["handover"] == "backstop"
    assert row["handover_since"] == since and row["handover_elapsed_min"] >= WAIT
    assert receipt(h)["node_handover"]["prs"] == {M: "backstop"}
    assert " handover_backstop=1" in out["summary"]
    again = h.tick()
    assert again["rc"] == 0, (again, h.last.stderr[-2000:])
    assert actions(again, "merge") == [] and len(merge_rows(h)) == 1


def test_an_armed_pr_stays_the_nodes_past_the_wait(h: Harness) -> None:
    """The node armed it (or GitHub holds it armed): the controller never merges it, however long it is green."""
    setup(h, {M: _green(SHA["c"], armed=True)}, repos=["omnimarket"], clock={f"{M}@{SHA['c']}": _ago(WAIT * 4)})
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert actions(out, "merge") == [] and not merged(h, M)
    assert receipt(h)["node_handover"]["prs"] == {M: "armed"}


def test_a_head_change_starts_the_clock_again(h: Harness) -> None:
    """The clock of head c was past the wait; the PR moved to head d, which is first seen now: held, one key."""
    setup(h, {M: _green(SHA["d"])}, repos=["omnimarket"], clock={f"{M}@{SHA['c']}": _ago(WAIT * 2)})
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert actions(out, "merge") == [] and not merged(h, M)
    assert receipt(h)["node_handover"]["prs"] == {M: "await"}
    assert list(clock(h)) == [f"{M}@{SHA['d']}"]


# ------------------------------------------------------------------------------ every other repo, unchanged


def test_a_green_pr_of_another_repo_merges_at_once(h: Harness) -> None:
    setup(h, {CORE: _green(SHA["c"]), M: _green(SHA["d"])}, repos=["omnimarket"])
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert [a["subject"] for a in actions(out, "merge")] == [f"OmniNode-ai/{CORE}"]
    assert merged(h, CORE) and not merged(h, M)
    [row] = merge_rows(h)
    assert row["outcome"] == "merged" and "handover" not in row
    assert receipt(h)["node_handover"]["prs"] == {M: "await"}


def test_with_no_configuration_omnimarket_merges_as_before(h: Harness) -> None:
    """The shipped default: no hand-over file, no repository handed over."""
    setup(h, {M: _green(SHA["c"])})
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert [a["subject"] for a in actions(out, "merge")] == [NODE_M]
    assert merged(h, M)
    assert receipt(h)["node_handover"] == {"repos": [], "wait_minutes": None, "source": "", "error": "", "prs": {}}
    assert "handover_" not in out["summary"]


def test_a_held_omnimarket_runtime_pr_never_holds_the_runtime_token(h: Harness) -> None:
    """omnimarket#40 and omnibase_infra#20 are both runtime and lab-proven; the node lands one runtime PR at a time.
    The held omnimarket PR is pending to the node, so the infra PR takes the token and merges this tick."""
    setup(
        h,
        {
            M: _green(SHA["c"], runtime=True, lab_ready=True, created_at="2026-09-01T00:00:00Z"),
            INFRA: _green(SHA["d"], runtime=True, lab_ready=True),
        },
        repos=["omnimarket"],
    )
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert [a["subject"] for a in actions(out, "merge")] == [f"OmniNode-ai/{INFRA}"]
    assert merged(h, INFRA) and not merged(h, M)


def test_an_invalid_configuration_hands_nothing_over_and_says_why(h: Harness) -> None:
    setup(h, {M: _green(SHA["c"])})
    Path(h.env["LANDING_NODE_HANDOVER"]).write_text(json.dumps({"repos": ["omnimarket"]}), encoding="utf-8")
    out = h.tick()
    assert out["rc"] == 0, (out, h.last.stderr[-2000:])
    assert [a["subject"] for a in actions(out, "merge")] == [NODE_M]
    assert "wait_minutes" in receipt(h)["node_handover"]["error"]
    assert " handover_error=1" in out["summary"]


# ---------------------------------------------------------------------------------------- the pure parts


def test_load_node_handover(tmp_path: Path) -> None:
    f = tmp_path / "h.json"
    env = {lf.NODE_HANDOVER_ENV: str(f)}
    assert lf.load_node_handover(env, tmp_path) == {"repos": [], "wait_minutes": None, "source": "", "error": ""}
    f.write_text(json.dumps({"repos": ["omnimarket", "omnimarket"], "wait_minutes": 15}), encoding="utf-8")
    assert lf.load_node_handover(env, tmp_path) == {
        "repos": ["omnimarket"],
        "wait_minutes": 15,
        "source": str(f),
        "error": "",
    }
    # the state dir's own file when the variable is unset
    (tmp_path / lf.NODE_HANDOVER_FILE).write_text(json.dumps({"repos": [], "wait_minutes": 15}), encoding="utf-8")
    assert lf.load_node_handover({}, tmp_path)["source"] == str(tmp_path / lf.NODE_HANDOVER_FILE)
    bads: list[object] = [
        {"repos": ["omnimarket"]},
        {"repos": ["omnimarket"], "wait_minutes": 0},
        {"repos": ["omnimarket"], "wait_minutes": True},
        {"repos": "omnimarket", "wait_minutes": 15},
        {"repos": ["omni market"], "wait_minutes": 15},
        {"repos": [], "wait_minutes": 15, "extra": 1},
        [],
    ]
    for bad in bads:
        f.write_text(json.dumps(bad), encoding="utf-8")
        got = lf.load_node_handover(env, tmp_path)
        assert got["repos"] == [] and got["error"], bad
    f.write_text("{", encoding="utf-8")
    assert lf.load_node_handover(env, tmp_path)["error"].startswith("unreadable")


def test_handover_step_and_clock() -> None:
    since, now = "2026-10-10T16:00:00Z", "2026-10-10T16:14:59Z"
    assert lf.handover_step(since, now, armed=False, wait_minutes=15) == ("await", 14)
    assert lf.handover_step(since, "2026-10-10T16:15:00Z", armed=False, wait_minutes=15) == ("backstop", 15)
    assert lf.handover_step(since, "2026-10-10T17:00:00Z", armed=True, wait_minutes=15) == ("armed", 60)
    prev = {f"{M}@{SHA['c']}": since, f"{CORE}@{SHA['a']}": since, "omnimarket#41@" + SHA["b"]: since}
    heads = {M: SHA["c"], CORE: SHA["b"]}  # CORE moved to b, #41 is gone
    assert lf.handover_clock_next(prev, heads) == {f"{M}@{SHA['c']}": since}
