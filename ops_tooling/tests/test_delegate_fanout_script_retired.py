"""The retired delegate fan-out script is gone and nothing here invokes it (OMN-20678 AC2).

The operator fan-out is the omnimarket bus node ``node_delegate_fanout_effect``.
The morning driver reaches it by ``onex run-node``; the old Workflow script that
used to sit in this repository has no copy and no caller left.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The retired script's file name, spelled in two halves so this file does not
# itself name it.
RETIRED_SCRIPT = "delegate-" + "fanout.js"

# The rolling ledger and this ticket's own contract record the script by name on
# purpose: they are history and the criterion, not callers.
HISTORY = ("docs/tracking/", "contracts/OMN-20678.yaml")


def tracked_files(root: Path) -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [name for name in listing.split("\0") if name]


def files_naming_script(root: Path) -> list[str]:
    """Tracked files outside the history records whose path or text names the script."""
    found: list[str] = []
    for name in tracked_files(root):
        if name.startswith(HISTORY):
            continue
        if name.endswith(RETIRED_SCRIPT):
            found.append(name)
            continue
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if RETIRED_SCRIPT in text:
            found.append(name)
    return found


def test_the_retired_script_has_no_file_and_no_caller() -> None:
    assert files_naming_script(REPO) == []


def test_the_scan_names_a_file_that_calls_the_script(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / "driver.sh").write_text(f"node .claude/workflows/{RETIRED_SCRIPT}\n")
    (tmp_path / "clean.sh").write_text("onex run-node node_delegate_fanout_effect\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    assert files_naming_script(tmp_path) == ["driver.sh"]


def test_the_scan_names_a_file_that_is_the_script(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    (tmp_path / RETIRED_SCRIPT).write_text("export const meta = {}\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    assert files_naming_script(tmp_path) == [RETIRED_SCRIPT]


def test_the_morning_driver_runs_the_bus_node() -> None:
    driver = (REPO / "launchd/morning-workflows/morning_workflows_tick.sh").read_text()
    assert 'BUS_NODE="node_delegate_fanout_effect"' in driver
