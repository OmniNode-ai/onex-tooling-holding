"""An order edge is resolved against the live state of its head at map time (OMN-19852).

omnibase_compat#216 merged 2026-09-27T09:39Z and the drain kept the PRs ordered behind it (omniclaude#2371,
omnimarket#2956) stopped for over a day: a MSG saying "must land after <a#1>" is read by the hold check as
an instruction (INSTRUCTION_RE), and an instruction hold has no release except a row nobody writes. The
predecessor's state was never read. The same row ("omnimarket#2968 must land after omnimarket#2956 and
omnimarket#2958") also held omnimarket#2956, the predecessor itself, because it is named near the phrase.

Each rule has a positive control beside it: an OPEN predecessor still holds, and a co-landing phrase
("must land alongside") is not an order edge. Run through the same harness as test_drain_map.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_drain_map import LIVE_CLAIM, TODAY, listed, make_pr, ok, run_map, tsv  # noqa: E402


def order_msg(ts: str, pr: str, phrase: str) -> str:
    repo, n = pr.split("#")
    return (f"{TODAY}T{ts}Z | MSG | from=lane-x | to=all | ticket=OMN-9 | repo={repo} | pr={pr} | needs=land | "
            f"Handoff: PR body states landing order: {phrase}. Lab proof attached.")


def test_an_order_hold_clears_when_every_predecessor_is_merged(tmp_path: Path) -> None:
    rows = [
        order_msg("16:00:00", "omnimarket#20", "must land after omnibase_compat#216 and omnibase_compat#217"),
        order_msg("16:01:00", "omnimarket#23", "must land after omnimarket#24"),  # positive control: #24 open
        LIVE_CLAIM,
    ]
    prs = {
        "omnimarket#20": make_pr("omnimarket", 20, red=True),
        "omnimarket#23": make_pr("omnimarket", 23, red=True),
        "omnimarket#24": make_pr("omnimarket", 24, red=True),
        "omnibase_compat#216": make_pr("omnibase_compat", 216, state="MERGED"),
        "omnibase_compat#217": make_pr("omnibase_compat", 217, state="MERGED"),
    }
    proc, out = run_map(tmp_path, rows, prs)
    stdout = ok(proc)
    table = tsv(out)
    assert not table["omnimarket#20"]["class"].startswith("held("), table["omnimarket#20"]
    assert "omnimarket#20" in listed(stdout, "WOULD-DISPATCH")
    assert table["omnimarket#23"]["class"].startswith("held("), table["omnimarket#23"]  # open head: still holds
    assert "omnimarket#23" not in listed(stdout, "WOULD-DISPATCH")
    assert "omnimarket#24" in listed(stdout, "WOULD-DISPATCH")  # the predecessor is not held by its dependant's row


def test_an_order_hold_with_one_open_predecessor_still_holds(tmp_path: Path) -> None:
    rows = [
        order_msg("16:00:00", "omnimarket#30", "must land after omnibase_compat#216 and omnimarket#31"),
        LIVE_CLAIM,
    ]
    prs = {
        "omnimarket#30": make_pr("omnimarket", 30, red=True),
        "omnimarket#31": make_pr("omnimarket", 31, red=True),
        "omnibase_compat#216": make_pr("omnibase_compat", 216, state="MERGED"),
    }
    proc, out = run_map(tmp_path, rows, prs)
    ok(proc)
    assert tsv(out)["omnimarket#30"]["class"].startswith("held(")


def test_a_predecessor_closed_unmerged_clears_the_edge_and_surfaces_a_finding(tmp_path: Path) -> None:
    rows = [
        order_msg("16:00:00", "omnimarket#40", "must land after omnimarket#41"),
        LIVE_CLAIM,
    ]
    prs = {
        "omnimarket#40": make_pr("omnimarket", 40, red=True),
        "omnimarket#41": make_pr("omnimarket", 41, state="CLOSED"),
    }
    proc, out = run_map(tmp_path, rows, prs)
    stdout = ok(proc)
    assert not tsv(out)["omnimarket#40"]["class"].startswith("held(")
    assert "ORDER-FINDINGS (1)" in stdout
    assert "omnimarket#40" in stdout and "omnimarket#41 closed unmerged" in stdout


def test_a_co_landing_phrase_is_not_an_order_edge(tmp_path: Path) -> None:
    rows = [
        order_msg("16:00:00", "omnimarket#50", "must land alongside omnibase_compat#216"),
        LIVE_CLAIM,
    ]
    prs = {
        "omnimarket#50": make_pr("omnimarket", 50, red=True),
        "omnibase_compat#216": make_pr("omnibase_compat", 216, state="MERGED"),
    }
    proc, out = run_map(tmp_path, rows, prs)
    ok(proc)
    assert tsv(out)["omnimarket#50"]["class"].startswith("held(")


def test_an_order_phrase_naming_no_pr_stays_a_hold(tmp_path: Path) -> None:
    rows = [order_msg("16:00:00", "omnimarket#60", "must land after the parent"), LIVE_CLAIM]
    prs = {"omnimarket#60": make_pr("omnimarket", 60, red=True)}
    proc, out = run_map(tmp_path, rows, prs)
    ok(proc)
    assert tsv(out)["omnimarket#60"]["class"].startswith("held(")


def test_a_waiting_order_on_a_closed_unmerged_head_fires_and_surfaces_a_finding(tmp_path: Path) -> None:
    rows = [
        f"{TODAY}T17:00:00Z | TERMINAL | lane=land-omnimarket-70-83 | ticket=OMN-1070 | friction=none | "
        f"outcome=waiting_order | repo=omnimarket | pr=omnimarket#70 | head={70:040d} | parents=omnimarket#71 | stopped",
        f"{TODAY}T17:01:00Z | TERMINAL | lane=land-omnimarket-72-83 | ticket=OMN-1072 | friction=none | "
        f"outcome=waiting_order | repo=omnimarket | pr=omnimarket#72 | head={72:040d} | parents=omnimarket#73 | stopped",
        LIVE_CLAIM,
    ]
    prs = {
        "omnimarket#70": make_pr("omnimarket", 70, red=True),
        "omnimarket#71": make_pr("omnimarket", 71, state="CLOSED"),
        "omnimarket#72": make_pr("omnimarket", 72, red=True),
        "omnimarket#73": make_pr("omnimarket", 73, red=True),  # open: still waits (positive control)
    }
    proc, out = run_map(tmp_path, rows, prs)
    stdout = ok(proc)
    assert listed(stdout, "WAITING") == {"omnimarket#72(order)"}
    assert "omnimarket#70" in listed(stdout, "WOULD-DISPATCH")
    assert "ORDER-FINDINGS (1)" in stdout and "omnimarket#71 closed unmerged" in stdout


def test_a_merge_record_clears_the_order_edge(tmp_path: Path) -> None:
    from test_drain_map import watcher_state_for

    prs = {"omnimarket#80": make_pr("omnimarket", 80, red=True)}
    state = watcher_state_for(prs)
    state["merges"]["omnimarket#81"] = {"repo": "omnimarket", "number": 81,
        "merged_at": state["last_tick"], "head_sha": "a" * 40, "base": "dev"}
    rows = [order_msg("16:00:00", "omnimarket#80", "must land after omnimarket#81"), LIVE_CLAIM]
    proc, out = run_map(tmp_path, rows, prs, state=state)
    ok(proc)
    assert tsv(out)["omnimarket#80"]["bucket"] == "dispatchable-fix"


def test_an_unread_predecessor_keeps_the_order_hold(tmp_path: Path) -> None:
    prs = {"omnimarket#80": make_pr("omnimarket", 80, red=True)}
    rows = [order_msg("16:00:00", "omnimarket#80", "must land after omnimarket#81"), LIVE_CLAIM]
    proc, out = run_map(tmp_path, rows, prs)
    ok(proc)
    assert tsv(out)["omnimarket#80"]["bucket"] == "held"
    assert "PR-STATE REFUSED: omnimarket#81 is not in the state" in proc.stdout
    assert "state could not be read" in proc.stdout


def test_an_unread_wait_predecessor_stays_unknown(tmp_path: Path) -> None:
    prs = {"omnimarket#80": make_pr("omnimarket", 80)}
    rows = [f"{TODAY}T17:00:00Z | TERMINAL | lane=land-80 | ticket=OMN-1080 | "
            f"outcome=waiting_order | pr=omnimarket#80 | head={80:040d} | parents=omnimarket#81 | stopped",
            LIVE_CLAIM]
    proc, out = run_map(tmp_path, rows, prs)
    ok(proc)
    assert "PR-STATE REFUSED: omnimarket#81 is not in the state" in proc.stdout
    assert tsv(out)["omnimarket#80"]["bucket"] == "waiting"
    assert not listed(proc.stdout, "WOULD-ARM")
