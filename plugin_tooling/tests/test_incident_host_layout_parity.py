"""OMN-17427: the host parity probe on the layout a lab host really has (incident of 2026-10-17, ~13:10Z).

plugin-tooling-pkg#835 added the clone check to the host parity record and passed its own tests, which built
every clone under the registry root. On the lab hosts the private repositories sit BESIDE the registry root, so
the probe refused h903, h906, h907 and h908 with "clone ops_tooling_pkg is missing from the registry root" and
no lane was placed for about 30 minutes. This test rebuilds the recorded layout of h908
(``fixtures/incidents-2026-10-17/host_layout_hx.json``: which entries are clones under the root, which beside it,
which are plain directories) and runs the real probe against it. Fixed by plugin-tooling-pkg#853.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_lab_host_parity import Lab, items, lab_tool

LAYOUT = json.loads((Path(__file__).parent / "fixtures/incidents-2026-10-17/host_layout_hx.json").read_text())


@pytest.fixture
def lab(tmp_path: Path) -> Lab:
    return Lab(tmp_path)


def build_recorded_layout(lab: Lab) -> None:
    for name in LAYOUT["under_the_registry_root"]["clones"]:
        lab.clone(name)
    for name in LAYOUT["beside_the_registry_root"]["clones"]:
        lab.clone(name, beside=True)
    for name in LAYOUT["beside_the_registry_root"]["plain_directories"]:
        (lab.registry.parent / name).mkdir()
    for name in LAYOUT["under_the_registry_root"]["plain_directories"]:
        (lab.registry / name).mkdir(exist_ok=True)
    lab_tool(lab, "pre-commit")


def test_the_recorded_layout_is_the_one_that_broke_placement() -> None:
    """The fixture holds the property the incident turned on: ops_tooling_pkg is beside the root and not under it."""
    beside = LAYOUT["beside_the_registry_root"]["clones"]
    under = LAYOUT["under_the_registry_root"]["clones"]
    assert "ops_tooling_pkg" in beside and "ops_tooling_pkg" not in under
    assert set(LAYOUT["clones_a_unit_needs"]) <= set(beside) | set(under)


def test_every_clone_a_unit_needs_reads_present_on_the_recorded_host_layout(lab: Lab) -> None:
    build_recorded_layout(lab)
    record = lab.probe(LAYOUT["clones_a_unit_needs"])
    assert items(record) == [], "the probe refused a host that holds every clone it was asked about"
    assert [c.name for c in record.clones if not c.present] == []


def test_a_clone_the_recorded_host_does_not_hold_is_still_refused(lab: Lab) -> None:
    """The negative control: the same layout, one more name that is in neither place, is refused by name."""
    build_recorded_layout(lab)
    record = lab.probe([*LAYOUT["clones_a_unit_needs"], "omnibase_absent"])
    assert items(record) == ["clone:omnibase_absent"]


def test_a_plain_directory_beside_the_root_is_not_a_clone_on_the_recorded_layout(lab: Lab) -> None:
    """docs-repo (hyphens) is a plain directory beside the root on the host, next to the clone docs_repo."""
    build_recorded_layout(lab)
    record = lab.probe(["docs-repo", "docs_repo"])
    assert items(record) == ["clone:docs-repo"]
