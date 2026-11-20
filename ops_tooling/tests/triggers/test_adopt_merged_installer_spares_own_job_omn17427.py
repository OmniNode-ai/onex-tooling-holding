"""The installer adopt-merged runs never unloads the job running it (OMN-17427).

The adoption job (launchd label ``ai.omninode.adopt-merged``) refreshed the morning package by
running the installer named in its own target table. The recorded entry for that target,
``morning-workflows-lib``, ran ``morning_trigger_install.sh --new-agents-only``; once the deferral
was dropped the installer ran inside the adoption job's own launchd job, booted out
``ai.omninode.adopt-merged`` before its bootstrap, and 115 of 117 hourly runs failed.

The fixtures hold the REAL recorded target entry, captured from the adoption job's
``adoption_targets.json`` at the commit before the fix and at the fix, and the real ledger row the
failed runs left. Nothing here is a hand-written argv: the installer is run with the argv the job
ran, against the installer in this tree, with a recording ``launchctl``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from _trigger_git_env import strip_git_env

strip_git_env(os.environ)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "incident_regression_omn17427"
RECORDED_TARGET = FIXTURES / "adopt_merged_morning_workflows_lib_target.json"

# The label of the job that runs the adoption script: the ledger rows are written by lane
# adopt-merged, and the installer's own agent table names the workflow `adopt-merged`.
OWN_LABEL = "ai.omninode.adopt-merged"
LABEL_CHANGING_VERBS = ("bootout", "bootstrap", "enable", "disable", "kickstart", "load", "unload")


def _recorded(which: str) -> dict[str, Any]:
    recorded = json.loads(RECORDED_TARGET.read_text(encoding="utf-8"))
    target: dict[str, Any] = recorded[which]["target"]
    return target


def _run_recorded_installer(
    tmp_path: Path, installer: list[str]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the recorded installer argv as the adoption job does: ``bash <script> <mode>``."""
    assert installer[0] == "bash", installer
    home = tmp_path / "home"
    bindir = tmp_path / "fakebin"
    log = tmp_path / "launchctl.log"
    for directory in (home, bindir):
        directory.mkdir()
    fake = bindir / "launchctl"
    fake.write_text(
        f'#!/bin/bash\necho "$*" >> "{log}"\n[ "$1" = "print" ] && exit 113\nexit 0\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(home),
        "registry_root": str(tmp_path / "omni"),
        "ONEX_LEDGER_PATH": str(tmp_path / "ledger.jsonl"),
        "ONEX_TENANT_ID": "tenant-a",
        "ONEX_ENVIRONMENT": "dev",
        "ONEX_CONTRACTS_DIR": str(tmp_path / "contracts"),
    }
    result = subprocess.run(
        ["bash", str(ROOT / installer[1]), *installer[2:]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        cwd=ROOT,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


def _unloads_own_job(calls: list[str]) -> list[str]:
    return [
        c
        for c in calls
        if c.split(" ", 1)[0] in LABEL_CHANGING_VERBS and c.endswith("/" + OWN_LABEL)
    ]


def test_the_recorded_fixed_installer_argv_never_unloads_the_adoption_job(tmp_path: Path) -> None:
    fixed = _recorded("fixed")
    result, calls = _run_recorded_installer(tmp_path, fixed["installer"])
    assert result.returncode == 0, (fixed["installer"], result.stdout, result.stderr)
    assert _unloads_own_job(calls) == [], calls
    assert not [c for c in calls if c.split(" ", 1)[0] in LABEL_CHANGING_VERBS], (
        "the adoption job reloads no label at all",
        calls,
    )


def test_positive_control_the_recorded_broken_installer_argv_unloads_the_adoption_job(
    tmp_path: Path,
) -> None:
    """The check above must see the recorded fault, or its empty result proves nothing."""
    broken = _recorded("broken")
    assert broken["installer"][2:] == ["--new-agents-only"], broken["installer"]
    result, calls = _run_recorded_installer(tmp_path, broken["installer"])
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert f"bootout gui/{os.getuid()}/{OWN_LABEL}" in _unloads_own_job(calls), calls


def test_the_fix_changed_only_the_mode_flag_of_the_recorded_target() -> None:
    broken, fixed = _recorded("broken"), _recorded("fixed")
    assert broken["installer"][:2] == fixed["installer"][:2]
    assert (ROOT / fixed["installer"][1]).is_file()
    assert fixed["installer"][2:] == ["--lib-only"]
    assert "defer_while_running" in broken and "defer_while_running" not in fixed


