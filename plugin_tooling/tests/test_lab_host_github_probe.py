"""OMN-20911 AC3: a lab-lane probe says whether the host gives a lane a way to read GitHub.

``lab_host_guardrails.sh --github-check --local`` runs on the host and prints one GUARDRAIL line per
question: does the GitHub API answer, is a GitHub credential variable exported, is a read-token command
configured for the gh shim, does gh hold a stored login. Each case below runs the real script in a real
shell against a scripted ``curl`` and ``gh`` and a throwaway HOME; the host that passes every question is
the control for each host that fails one.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/omni/scripts/lab_host_guardrails.sh"
SECRET = "not-a-real-credential-value"


# The tools the script and its login shell use. The PATH holds these and the scripted curl and gh only, so a
# case without curl or gh really has none, and no case reaches the network.
TOOLS = ("bash", "cat", "cut", "grep", "env", "hostname", "id", "uname", "tr", "mktemp", "rm", "base64", "tee",
         "sed", "dirname", "basename", "head", "sleep", "awk", "ls")


def _exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _probe(tmp_path: Path, *, curl_code: str = "000", curl_rc: int = 6, gh_logged_in: bool = False,
           env_extra: dict[str, str] | None = None, env_file: str = "", routing_file: str = "",
           with_curl: bool = True, with_gh: bool = True) -> tuple[int, dict[str, tuple[str, str]], str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    if with_curl:
        _exec(bindir / "curl", f"#!/bin/bash\n[ '{curl_code}' = 000 ] || printf 'HTTP/2 %s\\r\\ncontent-type: application/json\\r\\n\\r\\n{{}}' '{curl_code}'\nexit {curl_rc}\n")
    if with_gh:
        _exec(bindir / "gh", f"#!/bin/bash\n[ \"$1 $2\" = 'auth status' ] || exit 2\nexit {0 if gh_logged_in else 1}\n")
    home = tmp_path / "home"
    (home / ".omnibase").mkdir(parents=True)
    (home / ".config" / "omni").mkdir(parents=True)
    (home / ".omnibase" / ".env").write_text(env_file)
    (home / ".config" / "omni" / "gh-read-routing.env").write_text(routing_file)
    (home / ".profile").write_text("")
    env = {"PATH": str(bindir), "HOME": str(home), "USER": "probe", "TMPDIR": str(tmp_path),
           **(env_extra or {})}
    proc = subprocess.run(["bash", str(SCRIPT), "--github-check", "--local"], env=env, capture_output=True,
                          text=True, timeout=60, check=False)
    lines = {}
    for ln in proc.stdout.splitlines():
        m = re.match(r"GUARDRAIL \S+ (github-\S+) (PASS|FAIL|SKIP) (.*)", ln)
        if m:
            lines[m.group(1)] = (m.group(2), m.group(3))
    return proc.returncode, lines, proc.stdout + proc.stderr


def test_lab_host_github_probe_passes_a_host_with_no_route_no_credential_and_no_login(tmp_path: Path) -> None:
    rc, lines, out = _probe(tmp_path)
    assert rc == 0, out
    assert {k: v[0] for k, v in lines.items()} == {
        "github-route": "PASS", "github-token-env": "PASS", "github-read-token-cmd": "PASS", "github-gh-login": "PASS"}, out
    assert "HOST" in out and " PASS" in out


@pytest.mark.parametrize(
    ("kwargs", "failing"),
    [
        ({"curl_code": "200", "curl_rc": 0}, "github-route"),
        ({"curl_code": "401", "curl_rc": 0}, "github-route"),
        ({"with_curl": False}, "github-route"),
        ({"env_file": "export GH_TOKEN=" + SECRET + "\n"}, "github-token-env"),
        ({"env_file": "GITHUB_ENTERPRISE_TOKEN=" + SECRET + "\n"}, "github-token-env"),
        ({"routing_file": "GH_READ_TOKEN_CMD=mint-a-token\n"}, "github-read-token-cmd"),
        ({"gh_logged_in": True}, "github-gh-login"),
    ],
)
def test_lab_host_github_probe_fails_the_one_question_the_host_answers_wrongly(
    tmp_path: Path, kwargs: dict, failing: str
) -> None:
    rc, lines, out = _probe(tmp_path, **kwargs)
    assert rc == 1, out
    assert [k for k, v in lines.items() if v[0] == "FAIL"] == [failing], out
    assert "HOST" in out and " FAIL" in out
    # Positive control for the probe's output: the credential's value never reaches it.
    assert SECRET not in out


def test_lab_host_github_probe_names_an_exported_credential_in_the_login_shell(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".bash_profile").parent.mkdir(parents=True, exist_ok=True)
    (home / ".bash_profile").write_text(f"export GH_TOKEN={SECRET}\n")
    rc, lines, out = _probe(tmp_path)
    assert rc == 1, out
    assert lines["github-token-env"][0] == "FAIL" and "GH_TOKEN" in lines["github-token-env"][1], out
    assert SECRET not in out


def test_lab_host_github_probe_changes_nothing_and_needs_no_root(tmp_path: Path) -> None:
    before = sorted(p.name for p in tmp_path.iterdir())
    rc, _lines, out = _probe(tmp_path)
    assert rc == 0, out
    assert "sudo" not in out and "ROLLBACK" not in out
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(before + ["bin", "home"])
