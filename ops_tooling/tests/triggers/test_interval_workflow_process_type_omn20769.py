"""OMN-20769 — interval workflows run at launchd's Standard process type, not Background.

Measured 2026-10-09 on the operator's Mac: the lab-fill cache-only enumerate read, byte for byte
the command the 15:34Z fire ran, finished in 4-5 s from a terminal and from a one-shot launchd job
with ``ProcessType`` Standard, and in 22-25 s from the same job with ``ProcessType`` Background
(a pure-CPU loop: 0.17 s against 0.84-1.64 s). Background is darwinbg: throttled CPU and I/O for
the job and every child, so the ``claude -p`` run, each Bash call it makes and each ``uv run``
read all slowed together, and the enumerate reads hit their 79 s and 60 s bounds with no output.
The dod-closeout-sweep and adopt-merged workflows are deadline-bound runs; none may be Background.
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path

import pytest
from _trigger_git_env import strip_git_env

strip_git_env(os.environ)

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "launchd" / "morning-workflows" / "morning_trigger_install.sh"
INTERVAL_TEMPLATE = (
    REPO_ROOT
    / "launchd"
    / "morning-workflows"
    / "launchd"
    / "ai.omninode.interval-workflow.plist.tmpl"
)


def _interval_workflows() -> list[str]:
    text = INSTALLER.read_text(encoding="utf-8")
    array = re.search(r"INTERVAL_AGENTS=\(\n(.*?)\n\)", text, re.DOTALL)
    assert array is not None, "could not locate the INTERVAL_AGENTS array in the installer"
    found: list[str] = re.findall(r'^\s*"([a-z-]+):', array.group(1), re.MULTILINE)
    return found


def test_interval_template_declares_standard_process_type() -> None:
    template = INTERVAL_TEMPLATE.read_text(encoding="utf-8")
    body = template.split("<plist", 1)[1]
    assert re.search(r"<key>ProcessType</key>\s*<string>Standard</string>", body)
    assert "<string>Background</string>" not in body


@pytest.mark.skipif(__import__("shutil").which("plutil") is None, reason="plutil is macOS-only")
def test_every_rendered_interval_plist_is_standard(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path),
            "registry_root": str(tmp_path),
            # A dry run renders here and never under the live LaunchAgents (OMN-17427).
            "MORNING_DRY_RUN_DIR": str(tmp_path / "Library" / "LaunchAgents"),
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(INSTALLER), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    agents = tmp_path / "Library" / "LaunchAgents"
    for workflow in _interval_workflows():
        plist = agents / f"ai.omninode.{workflow}.plist"
        lint = subprocess.run(
            ["plutil", "-lint", str(plist)], capture_output=True, text=True, check=False
        )
        assert lint.returncode == 0, lint.stdout + lint.stderr
        rendered = plistlib.loads(plist.read_bytes())
        assert rendered["ProcessType"] == "Standard", workflow
        assert rendered["LowPriorityIO"] is False, workflow
