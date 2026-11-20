"""No CI job here reads onex_change_control, and no declaration names it (OMN-20074).

RULING 2026-10-14T05:30:13Z: every repository comes off onex_change_control by the end of the day.
This repository read it in two CI jobs, the automation liveness completeness job and
``nonblocking-path-inventory``, each of which checked it out beside the other registry repositories
and scanned it. The liveness overlay and its sources declaration moved to the overlays repository
(OMN-20804); the remaining checkouts and the inventory entries for its workflows left together.
Selector: ``-k off_occ``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OCC = "onex_change_control"
OVERLAYS = ROOT / "src/ops_tooling_pkg/overlays"


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _scalars(node: object) -> list[str]:
    """Every string value in a parsed document, so a comment is not read and a value always is.

    A ``name`` label is prose for a person, not a repository, path or command, so it is not read.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() if k != "name" for s in (*_scalars(k), *_scalars(v))]
    if isinstance(node, list):
        return [s for item in node for s in _scalars(item)]
    return []






def test_observe_only_inventory_off_occ_lists_no_change_control_path() -> None:
    document = _load(OVERLAYS / "observe_only_inventory.yaml")
    assert isinstance(document, dict)
    entries = document["entries"]
    assert [e for e in entries if OCC in (e["repo"], e["owner_repo"])] == []
    assert any(e["repo"] == "registry_root" for e in entries)




