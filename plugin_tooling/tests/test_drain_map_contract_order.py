"""Open change-control PRs that modify one contract file run one lane at a time (OMN-17427).

At 12:40Z on 2026-10-03 the drain ran four companion lanes at once (onex_change_control#12537, 12541,
12550, 12554), all appending to contracts/OMN-17427.yaml, so each merge re-conflicted the others. The map
now lists only the oldest of such a group as dispatchable and puts the rest to waiting(order) behind it,
through the lane-wait order trigger. Each rule has a positive control beside it. Run through the same
harness as test_drain_map.py.
"""

from __future__ import annotations

from pathlib import Path

from test_drain_map import LIVE_CLAIM, listed, make_pr, ok, run_map, tsv

OCC = "onex_change_control"
CONTRACT = "contracts/OMN-17427.yaml"


def occ(n: int, files: list[str], created: str, **over: object) -> dict:
    return make_pr(OCC, n, red=True, files=files, createdAt=created, **over)


def four_on_one_file() -> dict[str, dict]:
    return {
        f"{OCC}#{n}": occ(n, [CONTRACT], f"2026-09-23T10:0{i}:00Z")
        for i, n in enumerate((12537, 12541, 12550, 12554))
    }


def test_four_companions_on_one_contract_file_run_one_lane_and_three_wait(tmp_path: Path) -> None:
    proc, out = run_map(tmp_path, [LIVE_CLAIM], four_on_one_file())
    stdout = ok(proc)
    table = tsv(out)
    assert listed(stdout, "WOULD-DISPATCH") == {f"{OCC}#12537"}
    assert table[f"{OCC}#12537"]["bucket"] == "dispatchable-fix", table[f"{OCC}#12537"]
    for n in (12541, 12550, 12554):
        row = table[f"{OCC}#{n}"]
        assert row["bucket"] == "waiting" and row["class"] == "waiting(order)", row
        assert f"{OCC}#12537 is the oldest open PR modifying {CONTRACT}" in row["action"], row
    assert f"CONTRACT-ORDER (3): {OCC}#12541<-{OCC}#12537 {OCC}#12550<-{OCC}#12537 {OCC}#12554<-{OCC}#12537" in stdout


def test_age_decides_the_oldest_not_the_pr_number(tmp_path: Path) -> None:
    prs = {
        f"{OCC}#20": occ(20, [CONTRACT], "2026-09-23T10:05:00Z"),
        f"{OCC}#21": occ(21, [CONTRACT], "2026-09-23T10:01:00Z"),  # opened first
    }
    proc, out = run_map(tmp_path, [LIVE_CLAIM], prs)
    stdout = ok(proc)
    assert listed(stdout, "WOULD-DISPATCH") == {f"{OCC}#21"}
    assert tsv(out)[f"{OCC}#20"]["class"] == "waiting(order)"


def test_companions_on_different_contract_files_are_all_dispatchable(tmp_path: Path) -> None:
    prs = {
        f"{OCC}#30": occ(30, ["contracts/OMN-1.yaml"], "2026-09-23T10:00:00Z"),
        f"{OCC}#31": occ(31, ["contracts/OMN-2.yaml"], "2026-09-23T10:01:00Z"),
        f"{OCC}#32": occ(32, ["contracts/OMN-3.yaml"], "2026-09-23T10:02:00Z"),
        f"{OCC}#33": occ(33, ["README.md"], "2026-09-23T10:03:00Z"),  # no contract file at all
    }
    proc, out = run_map(tmp_path, [LIVE_CLAIM], prs)
    stdout = ok(proc)
    assert listed(stdout, "WOULD-DISPATCH") == {f"{OCC}#{n}" for n in (30, 31, 32, 33)}
    assert "CONTRACT-ORDER (0): -" in stdout
    assert not any(row["bucket"] == "waiting" for row in tsv(out).values())


def test_the_next_companion_is_released_when_its_predecessor_closes_or_merges(tmp_path: Path) -> None:
    for state in ("MERGED", "CLOSED"):
        prs = four_on_one_file()
        prs[f"{OCC}#12537"]["state"] = state
        proc, out = run_map(tmp_path / state, [LIVE_CLAIM], prs)
        stdout = ok(proc)
        assert listed(stdout, "WOULD-DISPATCH") == {f"{OCC}#12541"}, state
        assert tsv(out)[f"{OCC}#12554"]["class"] == "waiting(order)", state
        assert f"{OCC}#12554<-{OCC}#12541" in stdout, state


def test_a_held_member_does_not_stall_the_group(tmp_path: Path) -> None:
    prs = four_on_one_file()
    prs[f"{OCC}#12537"]["labels"] = [{"name": "hold" + ":merge"}]  # the oldest is held out of the drain
    proc, out = run_map(tmp_path, [LIVE_CLAIM], prs)
    stdout = ok(proc)
    assert tsv(out)[f"{OCC}#12537"]["bucket"] == "held"
    assert listed(stdout, "WOULD-DISPATCH") == {f"{OCC}#12541"}


def test_a_pending_predecessor_still_holds_the_others(tmp_path: Path) -> None:
    prs = four_on_one_file()
    prs[f"{OCC}#12537"] = make_pr(OCC, 12537, files=[CONTRACT], createdAt="2026-09-23T10:00:00Z",
                                  checks=[["tests", "in_progress", None, None]])  # CI running: pending
    proc, out = run_map(tmp_path, [LIVE_CLAIM], prs)
    stdout = ok(proc)
    assert tsv(out)[f"{OCC}#12537"]["class"] == "pending"
    assert listed(stdout, "WOULD-DISPATCH") == set()
    for n in (12541, 12550, 12554):
        assert tsv(out)[f"{OCC}#{n}"]["class"] == "waiting(order)"


def test_a_group_in_another_repo_or_off_the_contract_path_is_untouched(tmp_path: Path) -> None:
    prs = {
        "omnimarket#40": make_pr("omnimarket", 40, red=True, files=[CONTRACT], createdAt="2026-09-23T10:00:00Z"),
        "omnimarket#41": make_pr("omnimarket", 41, red=True, files=[CONTRACT], createdAt="2026-09-23T10:01:00Z"),
        f"{OCC}#42": occ(42, ["docs/notes/contracts/OMN-1.yaml"], "2026-09-23T10:00:00Z"),
        f"{OCC}#43": occ(43, ["docs/notes/contracts/OMN-1.yaml"], "2026-09-23T10:01:00Z"),
    }
    proc, out = run_map(tmp_path, [LIVE_CLAIM], prs)
    stdout = ok(proc)
    assert listed(stdout, "WOULD-DISPATCH") == {"omnimarket#40", "omnimarket#41", f"{OCC}#42", f"{OCC}#43"}
