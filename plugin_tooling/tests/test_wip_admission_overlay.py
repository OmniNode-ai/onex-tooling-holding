"""The wip_admission overlay declares the limits of the WIP admission (RULING 2026-10-30T00:03:58Z, OMN-21669).

A host with no wip_admission overlay under ONEX_SKILL_OVERLAY_ROOTS judges no work in progress: the
remote-lane brief gate returns no refusal and the lab fill prints UNKNOWN. The overlay root of the launching host
is the plugin tree this repository ships, so the overlay is committed here. Omnimarket's node refuses a limit
that is not the one its own merges_per_hour and lead_time_hours give; this pins the same arithmetic on the
committed file, so a hand-edited number is caught here before the overlay reaches a host.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml

OVERLAY = Path(__file__).resolve().parents[1] / "plugins/onex-overlays/overlays/wip_admission/overlay.yaml"
# The floor is omnimarket's node_wip_admission_compute contract (config.wip_admission.limit_floor).
LIMIT_FLOOR = 3
# The keys of omnimarket's ModelWipAdmissionOverlay: the model forbids any other, so a stray key refuses the overlay.
OVERLAY_KEYS = {
    "enforce_ruling",
    "dispatchable_repos",
    "fleet",
    "limits",
    "fix_forward_classes",
    "fix_forward_kinds",
    "fix_forward_lane_prefixes",
    "watcher_state_path",
}
LIMIT_KEYS = {"limit", "merges_per_hour", "lead_time_hours", "method", "evidence"}


def document() -> dict[str, Any]:
    document = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def entries() -> dict[str, dict[str, Any]]:
    doc = document()
    return {"fleet": doc["fleet"], **{f"limits.{repo}": row for repo, row in doc["limits"].items()}}


def test_the_overlay_carries_exactly_the_keys_the_node_reads() -> None:
    assert set(document()) == OVERLAY_KEYS
    assert all(set(row) == LIMIT_KEYS for row in entries().values())


@pytest.mark.parametrize("scope", sorted(entries()))
def test_every_limit_is_littles_law_from_its_own_measurement(scope: str) -> None:
    row = entries()[scope]
    assert row["limit"] == max(LIMIT_FLOOR, math.ceil(row["merges_per_hour"] * row["lead_time_hours"]))
    assert str(row["method"]).strip() and str(row["evidence"]).strip()


def test_the_fleet_rate_is_the_sum_of_the_repositories() -> None:
    doc = document()
    total = sum(row["merges_per_hour"] for row in doc["limits"].values())
    assert abs(total - doc["fleet"]["merges_per_hour"]) < 0.01


def test_every_dispatchable_repository_has_a_limit() -> None:
    doc = document()
    assert doc["dispatchable_repos"], "no dispatchable repository means the gate judges nothing"
    assert set(doc["dispatchable_repos"]) == set(doc["limits"])


def test_the_overlay_enforces_and_names_no_home_directory() -> None:
    doc = document()
    assert doc["enforce_ruling"] == "2026-10-30T00:03:58Z"
    text = OVERLAY.read_text(encoding="utf-8")
    assert "/" + "Users" + "/" not in text
    assert doc["watcher_state_path"].startswith("${registry_root}/"), "the host's root comes from the environment"


def test_a_process_fix_lane_prefix_is_declared() -> None:
    doc = document()
    assert doc["fix_forward_lane_prefixes"], "a defect in the admission read must stay repairable"
    assert all(prefix.endswith("-") for prefix in doc["fix_forward_lane_prefixes"])


def test_the_overlay_names_no_open_pull_request_cap() -> None:
    """OMN-23028: there is no pull request limit; the limits bound the work sent to lanes."""
    text = OVERLAY.read_text(encoding="utf-8").lower()
    keys = {key for scope in entries().values() for key in scope} | set(document())
    assert not [key for key in keys if "pull" in key or "open_pr" in key or "max_open" in key]
    assert "no open pull request cap" in text
