"""Ledger entrypoints preserve failures without inferring a checkout age from exit 2."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "omni"


@pytest.fixture
def ledger_env(tmp_path: Path) -> dict[str, str]:
    internal = tmp_path / "internal"
    internal.mkdir()
    (internal / "pyproject.toml").write_text('[project]\nname = "ops-tooling-pkg"\n')
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$LEDGER_FAILURE\" >&2\nexit \"${LEDGER_RC:-2}\"\n"
    )
    uv.chmod(0o755)
    home = tmp_path / "home"
    ledger = home / "docs" / "tracking" / "ROLLING_WORK_LEDGER.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("# ledger\n", encoding="utf-8")
    return {
        **os.environ,
        "registry_root": str(home),
        "ONEX_LEDGER_PATH": str(ledger),
        "ONEX_LEDGER_DETAIL_DIR": str(tmp_path / "detail"),
        "OPS_TOOLING_PKG_PATH": str(internal),
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "LEDGER_FAILURE": "usage: onex-ledger [-h]",
        "SESSION_LANE": "old-ledger-lane",
    }


@pytest.mark.parametrize("rc", [2, 75, 127])
@pytest.mark.parametrize("failure", [
    "usage: onex-ledger [-h]",
    "error: failed to remove file: Read-only file system (os error 30)",
    "onex-ledger resolver: no valid ops_tooling_pkg clone",
    "Traceback: ModuleNotFoundError: No module named 'ledger_dependency'",
    "usage: onex-ledger inbox [-h] [--ledger LEDGER] lane",
    "",
])
def test_every_entrypoint_preserves_unstructured_failure(
    ledger_env: dict[str, str], tmp_path: Path, failure: str, rc: int,
) -> None:
    ledger_env.update(LEDGER_FAILURE=failure, LEDGER_RC=str(rc))
    preflight = tmp_path / "preflight.py"
    preflight.write_text(
        "import json,sys\njson.dump({'checks': []}, open(sys.argv[sys.argv.index('--receipt') + 1], 'w'))\n",
        encoding="utf-8",
    )
    commands = [
        [
            "bash",
            str(PLUGIN / "skills" / "way-of-working" / "scripts" / "session_start.sh"),
            "--purpose",
            "old-ledger",
            "--ticket",
            "OMN-1",
            "--est-hours",
            "1",
            "--displaces",
            "none",
            "--actor",
            "agent",
            "--model",
            "model",
            "--scope",
            "scope",
            "--preflight",
            str(preflight),
        ],
        [
            "bash",
            str(PLUGIN / "skills" / "operator-ruling" / "scripts" / "record.sh"),
            "ask",
            "--lane",
            "old-ledger-lane",
            "--question",
            "choose",
            "--options",
            "a; b",
            "--recommend",
            "a",
        ],
        [
            "bash",
            str(PLUGIN / "skills" / "pr-handoff" / "scripts" / "handoff.sh"),
            "repo#1",
            "old-ledger-lane",
        ],
        [
            "bash",
            str(PLUGIN / "skills" / "friction-record" / "scripts" / "record.sh"),
            "--lane",
            "old-ledger-lane",
            "--ticket",
            "OMN-1",
            "--cost",
            "~1 lane-minute",
            "--text",
            "A failure. Correct move: repair it.",
        ],
    ]
    for command in commands:
        before = Path(ledger_env["ONEX_LEDGER_PATH"]).read_bytes()
        result = subprocess.run(command, env=ledger_env, capture_output=True, text=True)
        assert result.returncode == rc, result
        assert f"REFUSED {rc} onex-ledger-command" in result.stdout, result
        assert "onex-ledger-too-old" not in result.stdout, result
        assert "FIX:" in result.stdout and "detail=" in result.stdout, result
        detail = Path(result.stdout.split("detail=", 1)[1].splitlines()[0])
        assert failure in detail.read_text(), result
        assert Path(ledger_env["ONEX_LEDGER_PATH"]).read_bytes() == before


@pytest.mark.parametrize("rc", [2, 65, 75, 127])
def test_handoff_preserves_typed_refusal_and_retry(
    ledger_env: dict[str, str], rc: int,
) -> None:
    message = f"{'RETRY' if rc == 75 else 'REFUSED'} {rc} existing-rule: original reason"
    ledger_env.update(LEDGER_FAILURE=message, LEDGER_RC=str(rc))
    result = subprocess.run(
        ["bash", str(PLUGIN / "skills/pr-handoff/scripts/handoff.sh"), "repo#1", "worker"],
        env=ledger_env, capture_output=True, text=True,
    )
    assert result.returncode == rc
    assert result.stdout == message + "\n"


def test_handoff_missing_result_is_a_protocol_failure(ledger_env: dict[str, str]) -> None:
    ledger_env.update(LEDGER_FAILURE="unexpected output", LEDGER_RC="0")
    result = subprocess.run(
        ["bash", str(PLUGIN / "skills/pr-handoff/scripts/handoff.sh"), "repo#1", "worker"],
        env=ledger_env, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "REFUSED 2 onex-ledger-protocol" in result.stdout
    assert "detail=" in result.stdout and "onex-ledger-too-old" not in result.stdout


def test_handoff_invalid_override_reports_resolver_failure(ledger_env: dict[str, str]) -> None:
    ledger_env["OPS_TOOLING_PKG_PATH"] += "/absent"
    result = subprocess.run(
        ["bash", str(PLUGIN / "skills/pr-handoff/scripts/handoff.sh"), "repo#1", "worker"],
        env=ledger_env, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "REFUSED 2 onex-ledger-command" in result.stdout
    detail = Path(result.stdout.split("detail=", 1)[1].splitlines()[0])
    assert "no valid ops_tooling_pkg clone" in detail.read_text()
    assert ledger_env["OPS_TOOLING_PKG_PATH"] in detail.read_text()


def test_handoff_keeps_partial_append_evidence_on_unstructured_failure(
    ledger_env: dict[str, str],
) -> None:
    ledger_env["LEDGER_FAILURE"] = "OK MSG row-already-appended\nerror: subsequent command failed"
    result = subprocess.run(
        ["bash", str(PLUGIN / "skills/pr-handoff/scripts/handoff.sh"), "repo#1", "worker"],
        env=ledger_env, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert result.stdout.startswith("OK MSG row-already-appended\nREFUSED 2 onex-ledger-command")
