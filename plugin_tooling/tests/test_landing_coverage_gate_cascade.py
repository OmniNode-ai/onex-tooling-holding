"""The Coverage Sweep Gate is in the cascade class only on its skipped-shards cascade.

omnimarket's gate refuses ("coverage census refused ... The test shards did not run") when the OCC Preflight
Dependency pollers time out and Detect Changes and the Tests shards are cancelled; five landing workers
(L1018, L1021, L1024, L1026, L1028) went to such PRs as product reds. A real coverage failure fails the gate's
"Combine shard coverage" step with the shards run, and stays the PR's own.

Fixtures are the check-run rows of two real omnimarket CI runs: 36907651015 (PR 3202, cascade) and
36829627458 (shards ran, gate failed in its combine step).
"""

from __future__ import annotations

import json
from pathlib import Path
from tests.landing_rules_runtime import classify_red, rules

_FIX = Path(__file__).resolve().parent / "fixtures" / "coverage-gate"


GATE = "Coverage Sweep Gate"


def _runs(fixture: str) -> list[list[str]]:
    return json.loads((_FIX / fixture).read_text())["runs"]


def _red(runs: list[list[str]], *, skip: tuple[str, ...] = ()) -> list[str]:
    return sorted(r[0] for r in runs if r[2] == "failure" and r[0] not in skip)


CASCADE_RUNS = _runs("omnimarket_3202_run_36907651015_cascade.json")
SHARDS_RAN = _runs("omnimarket_run_36829627458_shards_ran.json")


def test_the_cascade_fixture_reds_are_release_identity_summary_and_the_gate() -> None:
    assert _red(CASCADE_RUNS) == ["CI Summary", GATE, "Release Identity Gate"]


def test_the_skipped_shards_gate_is_a_cascade_check() -> None:
    assert rules().is_cascade_check(GATE, CASCADE_RUNS) is True


def test_a_gate_red_over_shards_that_ran_is_not_a_cascade_check() -> None:
    assert rules().is_cascade_check(GATE, SHARDS_RAN) is False


def test_the_gate_with_no_run_rows_is_not_provably_the_cascade() -> None:
    assert rules().is_cascade_check(GATE) is False
    assert rules().cascade_only([GATE]) is False


def test_cascade_with_a_merged_companion_is_class_cascade() -> None:
    red = ["OCC Preflight Dependency", GATE, "CI Summary"]
    runs = [*CASCADE_RUNS, ["OCC Preflight Dependency", "completed", "failure", "2026-10-01T18:40:00Z"]]
    assert classify_red(red, runs, companion_merged=True) == "cascade"


def test_gate_only_cascade_with_an_open_companion_is_cascade_only() -> None:
    assert rules().cascade_only([GATE, "CI Summary", "OCC Preflight Dependency"], CASCADE_RUNS) is True


def test_a_real_coverage_drop_is_a_product_red() -> None:
    red = [GATE, "CI Summary"]
    assert classify_red(red, SHARDS_RAN, companion_merged=True) == "product"
    assert classify_red(red, SHARDS_RAN, companion_merged=False, edge_fired=True) == "product"
    assert rules().cascade_only(red, SHARDS_RAN) is False


def test_the_gate_with_only_a_shard_that_ran_among_cancelled_ones_is_product() -> None:
    runs = [["Detect Changes", "completed", "success", ""], ["Tests (Split 1/2)", "completed", "success", ""],
            ["Tests (Split 2/2)", "completed", "cancelled", ""]]
    assert rules().is_cascade_check(GATE, runs) is False
