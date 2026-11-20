"""The liveness reader the pre-merge liveness read's tests run is pinned and CI fetches exactly that pin (OMN-22725)."""

from __future__ import annotations

import re
from pathlib import Path

from tests.throughput_tick_runtime import PINS, pin

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "validate-plugin.yml"
PIN = PINS["LIVENESS_READER_SRC"]


def test_the_pin_names_a_full_commit_and_the_reader() -> None:
    p = pin(PIN)
    assert re.fullmatch(r"[0-9a-f]{40}", p["commit"]), p["commit"]
    assert p["node"] == "src/omnimarket/nodes/node_automation_liveness_overlay_check_effect"
    assert p["node"] in p["node_files"]


def test_the_workflow_fetches_the_pinned_reader_and_exports_its_source() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert str(PIN.relative_to(ROOT)) in text
    assert "LIVENESS_READER_SRC=$GITHUB_WORKSPACE/_external/liveness-reader/src" in text
    assert "- *liveness-reader" in text
    assert 'print(*p["node_files"], *p["package_files"]' in text, "the step reads the member list from the pin, so CI cannot drift from it"
