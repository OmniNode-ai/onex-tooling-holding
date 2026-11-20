"""A truncated Workflow result is never summarized, and its fire is receipted degraded (OMN-20882).

The harness cuts a Workflow tool result past about 174000 characters. The driver names the file
that holds the full result in the agent's prompt and receipts the fire. A fire whose agent said it
read a cut result is ``degraded`` exit 70, not ``completed`` exit 0. A fake agent stands in for
``claude -p`` and plants a 200000 character result.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from _trigger_delegation_step import delegation_step_stand_in, pool_env
from _trigger_git_env import strip_git_env

strip_git_env(os.environ)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "launchd" / "morning-workflows" / "morning_workflows_tick.sh"
PLANTED_CHARS = 200_000
MARKER = "WORKFLOW_RESULT_TRUNCATED"

# The fake agent reads the result path out of its own prompt, as the real agent does, and plants
# a result of PLANTED_CHARS characters there before it answers.
PLANT = (
    'target="$(printf "%s" "$2" | grep -o "[^ ]*[.]workflow-result[.]txt" | head -n1)"\n'
    f'head -c {PLANTED_CHARS} /dev/zero | tr "\\0" x > "$target"\n'
)


def _drive(
    tmp_path: Path, workflow: str, claude_body: str, **extra: str
) -> tuple[subprocess.CompletedProcess[str], Path, list[dict[str, object]]]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    prompt = tmp_path / "prompt.txt"
    claude = tmp_path / "fake_claude.sh"
    claude.write_text(
        f'#!/bin/bash\nprintf "%s" "$2" > "{prompt}"\n{claude_body}exit 0\n', encoding="utf-8"
    )
    claude.chmod(0o755)
    env = {
        **pool_env(tmp_path),
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "registry_root": str(home),
        "CLAUDE_BIN": str(claude),
        "DOCS_REPO_PATH": str(tmp_path / "kb"),
        "ONEX_TENANT_ID": "test-tenant",
        "ONEX_ENVIRONMENT": "dev",
        "ONEX_CONTRACTS_DIR": str(tmp_path / "contracts"),
        "ONEX_DELEGATION_STEP_PATH": delegation_step_stand_in(tmp_path),
        "ONEX_MORNING_DATE": "2026-10-03",
        "ONEX_MORNING_MAX_RUNTIME_S": "60",
        "ONEX_MORNING_DEFER_HORIZON_S": "0",
        "ONEX_MORNING_DEFER_DRY": "1",
        **extra,
    }
    result = subprocess.run(
        ["bash", str(DRIVER), workflow],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=90,
    )
    receipts = home / ".onex_state" / "morning-workflows" / "fire-receipts.jsonl"
    rows = [json.loads(line) for line in receipts.read_text(encoding="utf-8").splitlines()]
    return result, prompt, [r for r in rows if r["workflow"] == workflow]


def test_launcher_result_written_to_file(tmp_path: Path) -> None:
    result, prompt, rows = _drive(
        tmp_path, "dod-closeout-sweep", PLANT + 'printf "STATUS row confirmed\\n"\n'
    )
    assert result.returncode == 0, result.stdout + result.stderr
    final = rows[-1]
    path = Path(str(final["workflow_result_file"]))
    text = prompt.read_text(encoding="utf-8")
    # The path is fixed by the driver, sits in the results channel, and is handed to the agent.
    assert path.parent == tmp_path / "home" / ".onex_state" / "morning-workflows" / "results"
    assert path.name == f"{final['fire_id']}.workflow-result.txt"
    assert str(path) in text
    assert MARKER in text and "never from memory" in text
    assert len(path.read_text(encoding="utf-8")) == PLANTED_CHARS
    assert (final["phase"], final["exit"], final["result_truncated"]) == ("completed", 0, False)


@pytest.mark.parametrize("workflow", ["hourly-tick", "friction-classify"])
def test_launcher_result_written_to_file_for_every_workflow_call(
    tmp_path: Path, workflow: str
) -> None:
    result, prompt, rows = _drive(tmp_path, workflow, "")
    assert result.returncode in (0, 65), result.stdout + result.stderr
    assert str(rows[-1]["workflow_result_file"]) in prompt.read_text(encoding="utf-8")


def test_launcher_result_written_to_file_not_for_selftest_or_node_runs(tmp_path: Path) -> None:
    result, prompt, rows = _drive(tmp_path, "dod-closeout-sweep", "", ONEX_MORNING_SELFTEST="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert rows[-1]["workflow_result_file"] is None
    assert "Result file" not in prompt.read_text(encoding="utf-8")


def test_truncated_result_receipt_degraded(tmp_path: Path) -> None:
    result, prompt, rows = _drive(
        tmp_path,
        "dod-closeout-sweep",
        PLANT + f'printf "{MARKER} the result ends mid-structure\\n"\n',
    )
    assert result.returncode == 70, result.stdout + result.stderr
    final = rows[-1]
    assert final["phase"] == "degraded"
    assert final["exit"] == 70
    assert final["degraded_class"] == "workflow-result-truncated"
    assert final["result_truncated"] is True
    notices = list((tmp_path / "home" / ".onex_state").rglob("dod-closeout-sweep.failure.json"))
    assert len(notices) == 1
    notice = json.loads(notices[0].read_text(encoding="utf-8"))
    assert (notice["phase"], notice["exit"]) == ("degraded", 70)
    assert "workflow-result-truncated" in notice["first_line"]
    assert final["workflow_result_file"] in notice["first_line"]
    assert str(final["workflow_result_file"]) in prompt.read_text(encoding="utf-8")


def test_truncated_result_receipt_degraded_needs_the_marker_on_its_own_line(
    tmp_path: Path,
) -> None:
    # Positive control: a summary that merely names the marker mid-sentence is still completed.
    result, _, rows = _drive(
        tmp_path,
        "dod-closeout-sweep",
        PLANT + f'printf "no {MARKER} was needed; STATUS row confirmed\\n"\n',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (rows[-1]["phase"], rows[-1]["result_truncated"]) == ("completed", False)


@pytest.mark.parametrize("workflow", ["dod-closeout-sweep"])
def test_background_launch_acknowledgment_is_not_read_as_a_cut_result(
    tmp_path: Path, workflow: str
) -> None:
    """OMN-20864: the Workflow tool answers first with "Workflow launched in background. Task ID:
    ...", and the result comes later as the task's notification. A fire (20261016T0250Z) read
    that acknowledgment as a cut result and printed the marker, and its fire was receipted degraded.
    The contract names the acknowledgment and says to wait for the notification."""
    result, prompt, _ = _drive(tmp_path, workflow, "")
    assert result.returncode in (0, 65), result.stdout + result.stderr
    text = prompt.read_text(encoding="utf-8")
    assert "Workflow launched in background" in text
    assert "is neither the result nor a cut result" in text
    assert "completion notification" in text


@pytest.mark.parametrize("status", ["failed", "failed (run wf-test)", "completed"])
def test_workflow_failure_header_overrides_a_zero_exit_agent(tmp_path: Path, status: str) -> None:
    plant = (
        'target="$(printf "%s" "$2" | grep -o "[^ ]*[.]workflow-result[.]txt" | head -n1)"\n'
        f'printf "task-id: test\\nrun-id: wf-test\\nstatus: {status}\\n'
        'agents: 14 done\\nstatus: failed\\n" > "$target"\n'
        'printf "STATUS row confirmed\\n"\n'
    )
    result, _, rows = _drive(tmp_path, "dod-closeout-sweep", plant)
    if status.startswith("failed"):
        assert result.returncode == 70, result.stdout + result.stderr
        assert (rows[-1]["phase"], rows[-1]["exit"]) == ("failed", 70)
        assert rows[-1]["degraded_class"] == "workflow-failed"
        notice = (
            tmp_path
            / "home/.onex_state/morning-workflows/notifications/dod-closeout-sweep.failure.json"
        )
        assert "workflow status=failed" in json.loads(notice.read_text())["first_line"]
    else:
        # A quoted failed status in the body is not the transport header.
        assert result.returncode == 0, result.stdout + result.stderr
        assert rows[-1]["phase"] == "completed"
