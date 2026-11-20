"""OMN-22154: ``tool_servers_healthy`` ignores claude.ai account connectors.

The account-level claude.ai connectors (listed by ``claude mcp list`` as ``claude.ai <Name>``) are
not servers the session configures and no lane uses them, so one that needs authentication must not
block a lane. A server the session configures itself that fails to connect or needs authentication
still blocks.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "plugins/onex-overlays/overlays/session_preflight/overlay.yaml"

CONNECTOR_LINE = "claude.ai Notion: https://mcp.notion.com/mcp - ! Needs authentication"
CONNECTED_LINE = "claude.ai Gmail: https://gmail.mcp.claude.com/mcp - ✓ Connected"
OWN_CONNECTED = "myserver: mycmd --serve - ✓ Connected"
OWN_FAILED = "myserver: mycmd --serve - ✗ Failed to connect"
OWN_NEEDS_AUTH = "myserver: https://example.invalid/mcp (HTTP) - ! Needs authentication"


def tool_servers_command() -> str:
    checks = yaml.safe_load(OVERLAY.read_text())["checks"]
    (check,) = [c for c in checks if c["check_id"] == "tool_servers_healthy"]
    assert check["severity"] == "blocker"
    return check["command"]


def run_check(tmp_path: Path, listing: list[str]) -> int:
    """Run the overlay's command with a fake ``claude`` first on PATH printing ``listing``."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text(
        "#!/bin/sh\n"
        '[ "$1 $2" = "mcp list" ] || exit 64\n'
        "echo 'Checking MCP server health...'\n"
        + "".join(f"echo '{line}'\n" for line in listing)
    )
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(
        tool_servers_command(), shell=True, check=False, env=env, capture_output=True, timeout=60
    ).returncode


def test_claude_ai_connector_needing_authentication_passes(tmp_path: Path) -> None:
    assert run_check(tmp_path, [CONNECTOR_LINE]) == 0


def test_claude_ai_connectors_do_not_hide_a_healthy_own_server(tmp_path: Path) -> None:
    assert run_check(tmp_path, [CONNECTED_LINE, CONNECTOR_LINE, OWN_CONNECTED]) == 0


@pytest.mark.parametrize("own_line", [OWN_FAILED, OWN_NEEDS_AUTH])
def test_own_server_unhealthy_fails(tmp_path: Path, own_line: str) -> None:
    assert run_check(tmp_path, [own_line]) != 0


@pytest.mark.parametrize("own_line", [OWN_FAILED, OWN_NEEDS_AUTH])
def test_own_server_unhealthy_fails_beside_a_connector(tmp_path: Path, own_line: str) -> None:
    assert run_check(tmp_path, [CONNECTOR_LINE, own_line]) != 0
