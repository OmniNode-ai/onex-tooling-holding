"""The nightly canary reads siblings at their live branch, so it never gates a change (OMN-20001).

Operator ruling 2026-10-01: a merge in one repo must not turn another repo red. The canary
workflow checks out eleven sibling repos with no ref, which is correct for a monitor and wrong
for a gate. This test pins the one property that keeps it a monitor: it runs only on
``schedule`` and ``workflow_dispatch``, and no other workflow here waits on it.
"""

from __future__ import annotations

import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CANARY = WORKFLOWS / "nightly-planted-sample-canary.yml"
NON_GATING_TRIGGERS = {"schedule", "workflow_dispatch"}
PRE_COMMIT_RUN = 'uvx pre-commit run --color never --files $files > "$log" 2>&1'






















def test_guarded_refusal_records_exit_status_and_continues_under_bash_errexit() -> None:
    script = """
for sample in first second; do
    rc=0
    (exit 1) || rc=$?
    printf '%s rc=%s\\n' "$sample" "$rc"
done
echo later-marker
"""
    completed = subprocess.run(
        ["bash", "-e", "-c", script], check=True, capture_output=True, text=True
    )
    assert completed.stdout.splitlines() == ["first rc=1", "second rc=1", "later-marker"]
