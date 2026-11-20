"""OMN-20199: the operator guardrail script shows the remote sudo prompt and protects the model servers."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/omni/scripts/lab_host_guardrails.sh"
TEXT = SCRIPT.read_text()


def test_the_ssh_pty_output_is_streamed_to_the_terminal_not_captured() -> None:
    assert not re.search(r"\$\(\s*ssh\b", TEXT), "out=$(ssh -tt ...) hides the remote sudo prompt"
    ssh_lines = [line for line in TEXT.splitlines() if "ssh -tt" in line]
    assert ssh_lines and all("tee" in line for line in ssh_lines)
    assert "mktemp" in TEXT


def test_earlyoom_avoids_vllm_and_the_other_services_and_still_prefers_pytest() -> None:
    avoid = re.search(r"--avoid '([^']*)'", TEXT)
    assert avoid, "no --avoid regex"
    rx = re.compile(avoid.group(1).replace("\\\\", "\\").replace("\\$", "$"))
    # The /proc/<pid>/comm values read on lab-host-a and .202 on 2026-09-30 (OMN-20206). earlyoom matches comm, not argv.
    for comm in ("llama-server", "VLLM::EngineCor", "k3s-server", "containerd", "containerd-shim", "dockerd",
                 "postgres", "qdrant", "memgraph", "redpanda", "sshd", "Runner.Listener", "systemd"):
        assert rx.search(comm), f"{comm} is not avoided"
    # Guessed names that are no process's comm are gone: vLLM's own comm is VLLM::EngineCor, the deploy agent's is python.
    for never in ("vllm", "deploy_agent", "VLLM::Worker"):
        assert not rx.search(never), f"{never} is not a comm value seen on a lab host"
    for victim in ("pytest", "python", "python3", "RunnerXListener"):
        assert not rx.search(victim), f"{victim} must stay killable"
    assert "--prefer '^(pytest|py\\\\.test)" in TEXT


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash")
def test_the_script_parses() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
