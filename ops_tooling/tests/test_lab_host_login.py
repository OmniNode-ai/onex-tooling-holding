"""scripts/lab-host-login: the --check verification and the token-file write (OMN-17427).

The check runs each probe in a fresh `env -i` shell; the tests point that shell's PATH at a
directory of stub `claude`, `gh` and `git` executables through LAB_HOST_LOGIN_PATH.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lab-host-login"
FAKE_TOKEN = "sk-ant-oat01-" + "A" * 60


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


def _host(tmp_path: Path, *, claude: str, gh: str, git: str, token: bool) -> dict[str, str]:
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    home.mkdir()
    bin_dir.mkdir()
    _stub(bin_dir, "claude", claude)
    _stub(bin_dir, "gh", gh)
    _stub(bin_dir, "git", git)
    if token:
        token_dir = home / ".config" / "omni"
        token_dir.mkdir(parents=True)
        (token_dir / "claude-oauth-token").write_text(FAKE_TOKEN + "\n")
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LAB_HOST_LOGIN_PATH": f"{bin_dir}:/usr/bin:/bin",
        "LAB_HOST_LOGIN_TIMEOUT": "20",
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
    )


OK_CLAUDE = "echo ok"
OK_GH = 'if [ "$1" = api ]; then echo octocat; else echo "file (/x/hosts.yml)"; fi'
OK_GIT = 'echo "deadbeef\tHEAD"'


@pytest.mark.unit
def test_check_passes_when_every_item_answers(tmp_path: Path) -> None:
    env = _host(tmp_path, claude=OK_CLAUDE, gh=OK_GH, git=OK_GIT, token=True)
    result = _run(env, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS claude" in result.stdout
    assert "PASS gh" in result.stdout
    assert "PASS git" in result.stdout
    assert "RESULT PASS" in result.stdout


@pytest.mark.unit
def test_check_reads_the_token_file_inside_the_child_and_never_prints_it(tmp_path: Path) -> None:
    claude = (
        'if [ "$CLAUDE_CODE_OAUTH_TOKEN" = "'
        + FAKE_TOKEN
        + '" ]; then echo ok; else echo no-token; fi'
    )
    env = _host(tmp_path, claude=claude, gh=OK_GH, git=OK_GIT, token=True)
    result = _run(env, "--check")
    assert "PASS claude" in result.stdout, result.stdout
    assert "using token file" in result.stdout
    assert FAKE_TOKEN not in result.stdout + result.stderr


@pytest.mark.unit
def test_check_fails_with_a_reason_when_not_logged_in(tmp_path: Path) -> None:
    claude = (
        'if [ "$1" = auth ]; then echo \'{"loggedIn": false}\'; exit 1; fi; '
        'echo "Not logged in"; exit 1'
    )
    gh = 'echo \'{"message": "Requires authentication"}\'; exit 1'
    git = 'echo "fatal: could not read Username" >&2; exit 128'
    env = _host(tmp_path, claude=claude, gh=gh, git=git, token=False)
    result = _run(env, "--check")
    assert result.returncode == 1
    assert "FAIL claude" in result.stdout and "no token file" in result.stdout
    assert "FAIL gh" in result.stdout and "Requires authentication" in result.stdout
    assert "FAIL git" in result.stdout and "could not read Username" in result.stdout
    assert "RESULT FAIL: 3" in result.stdout


@pytest.mark.unit
def test_check_honours_skip_claude_and_skip_gh(tmp_path: Path) -> None:
    """OMN-21864: --check used to probe every item whatever was skipped."""
    env = _host(
        tmp_path,
        claude="echo 'Not logged in'; exit 1",
        gh="exit 1",
        git=OK_GIT,
        token=False,
    )
    result = _run(env, "--check", "--skip-claude", "--skip-gh")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKIP claude: --skip-claude" in result.stdout
    assert "SKIP gh: --skip-gh" in result.stdout
    assert "FAIL" not in result.stdout
    assert "PASS git" in result.stdout
    only_claude = _run(env, "--check", "--skip-claude")
    assert "SKIP claude" in only_claude.stdout and "FAIL gh" in only_claude.stdout


def _pool_python(tmp_path: Path, body: str) -> str:
    path = tmp_path / "pool-python"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return str(path)


@pytest.mark.unit
def test_check_accepts_the_host_token_pool_with_no_token_file_and_no_login(tmp_path: Path) -> None:
    claude = (
        'if [ "$1" = auth ]; then echo \'{"loggedIn": false}\'; exit 1; fi; '
        'if [ "$CLAUDE_CODE_OAUTH_TOKEN" = "' + FAKE_TOKEN + '" ]; then echo ok; '
        "else echo 'Not logged in'; exit 1; fi"
    )
    env = _host(tmp_path, claude=claude, gh=OK_GH, git=OK_GIT, token=False)
    env["ONEX_CLAUDE_POOL_PY"] = _pool_python(tmp_path, f'echo "{FAKE_TOKEN}"')
    result = _run(env, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS claude: claude -p answered using the host's token pool" in result.stdout
    assert FAKE_TOKEN not in result.stdout + result.stderr


@pytest.mark.unit
def test_check_reads_a_rate_limited_account_as_logged_in(tmp_path: Path) -> None:
    claude = (
        'if [ "$1" = auth ]; then echo \'{"loggedIn": false}\'; exit 1; fi; '
        'echo "You\'ve hit your limit - resets 6pm"; exit 1'
    )
    env = _host(tmp_path, claude=claude, gh=OK_GH, git=OK_GIT, token=True)
    result = _run(env, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS claude" in result.stdout and "rate-limited" in result.stdout
    assert "not logged in" not in result.stdout.lower()


@pytest.mark.unit
def test_check_names_a_missing_tool(tmp_path: Path) -> None:
    env = _host(tmp_path, claude=OK_CLAUDE, gh=OK_GH, git=OK_GIT, token=True)
    bin_dir = tmp_path / "bin"
    (bin_dir / "gh").unlink()
    # Keep the fresh shell's utilities, but never discover a host-installed gh.
    for name in ("sh", "cat"):
        executable = shutil.which(name, path=env["PATH"])
        assert executable is not None
        (bin_dir / name).symlink_to(executable)
    env["LAB_HOST_LOGIN_PATH"] = str(bin_dir)
    result = _run(env, "--check")
    assert result.returncode == 1
    assert "FAIL gh: gh is not installed" in result.stdout
    assert "PASS claude" in result.stdout
    assert "PASS git" in result.stdout


@pytest.mark.unit
def test_check_scrubs_a_token_out_of_a_failure_line(tmp_path: Path) -> None:
    claude = "echo 'bad credential " + FAKE_TOKEN + "'; exit 1"
    env = _host(tmp_path, claude=claude, gh=OK_GH, git=OK_GIT, token=True)
    result = _run(env, "--check")
    assert "FAIL claude" in result.stdout
    assert FAKE_TOKEN not in result.stdout + result.stderr


@pytest.mark.unit
def test_write_token_file_is_mode_600_and_valid_token_is_strict(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "LAB_HOST_LOGIN_SOURCE_ONLY": "1"}
    probe = f'. "{SCRIPT}"; valid_token "$1" || exit 3; write_token_file "$1" || exit 4'
    ok = subprocess.run(
        ["bash", "-c", probe, "x", FAKE_TOKEN], env=env, capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0, ok.stderr
    target = home / ".config" / "omni" / "claude-oauth-token"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text().strip() == FAKE_TOKEN
    assert FAKE_TOKEN not in ok.stdout + ok.stderr
    for bad in ("", "hello", "sk-ant-short", "sk-ant-" + "A" * 20 + " " + "B" * 30):
        rejected = subprocess.run(
            ["bash", "-c", probe, "x", bad], env=env, capture_output=True, text=True, check=False
        )
        assert rejected.returncode == 3, bad


@pytest.mark.unit
def test_setup_without_a_terminal_refuses_instead_of_hanging(tmp_path: Path) -> None:
    env = _host(tmp_path, claude=OK_CLAUDE, gh=OK_GH, git=OK_GIT, token=False)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # no controlling terminal, as under a non-interactive ssh
        timeout=30,
    )
    assert result.returncode == 2
    assert "needs a terminal" in result.stderr


@pytest.mark.unit
def test_script_is_valid_bash_and_passes_shellcheck() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck not installed")
    result = subprocess.run(
        [shellcheck, "-S", "warning", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout


# --- OMN-20110: a token variable in the environment overrides gh's stored login ------------------
#
# gh reads GH_TOKEN, then GITHUB_TOKEN, before its own hosts.yml, so `gh auth login` refuses with
# "The value of the GITHUB_TOKEN environment variable is being used for authentication" and the
# script only reported "gh auth login failed". Setup now refuses first, names every startup file
# that defines the variable (file:line, value masked) and says what to do.

SECRET = "ghp_" + "Z" * 36


def _seed_startup_files(home: Path) -> None:
    (home / ".zshrc").write_text("# rc\nexport PATH=$PATH\nexport GITHUB_TOKEN=" + SECRET + "\n")
    (home / ".omnibase").mkdir()
    (home / ".omnibase" / ".env").write_text(
        f"A=1\n# GITHUB_TOKEN={SECRET}\nGITHUB_TOKEN='{SECRET}'\nGH_TOKEN={SECRET}\n"
    )


def _token_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = _host(tmp_path, claude=OK_CLAUDE, gh=OK_GH, git=OK_GIT, token=True)
    env["LAB_HOST_LOGIN_ETC"] = str(tmp_path / "etc")  # never scan the real /etc in a test
    env.update(extra)
    return env


@pytest.mark.unit
@pytest.mark.parametrize("name", ["GITHUB_TOKEN", "GH_TOKEN"])
def test_setup_refuses_when_a_token_variable_is_set_and_names_where_it_is_defined(
    tmp_path: Path, name: str
) -> None:
    env = _token_env(tmp_path, **{name: SECRET})
    _seed_startup_files(Path(env["HOME"]))
    result = _run(env)
    assert result.returncode == 2, result.stdout + result.stderr
    err = result.stderr
    assert f"{name} is set" in err
    assert ".zshrc:3: export GITHUB_TOKEN=<redacted>" in err
    assert "env-dir/env-file:3: GITHUB_TOKEN=<redacted>" in err
    assert "env-dir/env-file:4: GH_TOKEN=<redacted>" in err
    assert "env-dir/env-file:2" not in err, "a commented definition sets nothing"
    assert "unset GITHUB_TOKEN GH_TOKEN" in err
    assert "deploy-runtime.sh" in err, "the env-file case must not tell the operator to delete it"
    assert SECRET not in result.stdout + err
    assert "gh auth login failed" not in err


@pytest.mark.unit
def test_setup_refusal_says_so_when_no_startup_file_defines_the_variable(tmp_path: Path) -> None:
    env = _token_env(tmp_path, GITHUB_TOKEN=SECRET)
    result = _run(env)
    assert result.returncode == 2
    assert "Where: no startup file under" in result.stderr
    assert "remove each definition" not in result.stderr
    assert "unset GITHUB_TOKEN GH_TOKEN" in result.stderr
    assert SECRET not in result.stdout + result.stderr


@pytest.mark.unit
def test_setup_refuses_before_any_login_step_runs(tmp_path: Path) -> None:
    env = _token_env(tmp_path, GITHUB_TOKEN=SECRET)
    calls = tmp_path / "calls"
    _stub(tmp_path / "bin", "gh", f'echo "$@" >> "{calls}"; echo octocat')
    _stub(tmp_path / "bin", "claude", f'echo "$@" >> "{calls}"; echo ok')
    result = subprocess.run(
        ["bash", str(SCRIPT), "--renew"],
        capture_output=True,
        text=True,
        env={**env, "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin"},
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
    assert not calls.exists(), "neither claude setup-token nor gh auth login may run first"


@pytest.mark.unit
def test_skip_gh_does_not_refuse_on_a_token_variable(tmp_path: Path) -> None:
    env = _token_env(tmp_path, GITHUB_TOKEN=SECRET)
    result = subprocess.run(
        ["bash", str(SCRIPT), "--skip-gh", "--skip-claude"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        timeout=30,
    )
    assert "GITHUB_TOKEN is set" not in result.stderr
    assert "needs a terminal" in result.stderr


@pytest.mark.unit
def test_check_ignores_the_callers_token_variable_because_it_probes_in_a_fresh_shell(
    tmp_path: Path,
) -> None:
    env = _token_env(tmp_path, GITHUB_TOKEN=SECRET)
    result = _run(env, "--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT PASS" in result.stdout


@pytest.mark.unit
def test_setup_token_stdin_is_the_real_tty_device_not_the_dev_tty_alias(tmp_path: Path) -> None:
    """`claude setup-token < /dev/tty` crashed Bun with EINVAL from kqueue on macOS: the child's
    stdin was the /dev/tty alias node. The stub `claude` records which device fd 0 is."""
    import pty
    import select
    import sys
    import time

    env = _host(tmp_path, claude="true", gh=OK_GH, git=OK_GIT, token=False)
    seen = tmp_path / "stdin-device"
    probe = (
        "import os,sys;st=os.fstat(0);"
        "alias=os.stat('/dev/tty').st_rdev;"
        "print('tty' if os.isatty(0) else 'notty', 'alias' if st.st_rdev==alias else 'real')"
    )
    _stub(tmp_path / "bin", "claude", f'"{sys.executable}" -c "{probe}" > "{seen}"')
    pid, master = pty.fork()
    if pid == 0:  # child: a session leader with the pty as its controlling terminal
        os.execve("/bin/bash", ["bash", str(SCRIPT), "--skip-gh"], env)
    out = b""
    deadline = time.monotonic() + 30
    answered = False
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 1)
        if not ready:
            continue
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if b"Paste the token" in out and not answered:
            os.write(master, b"not-a-token\n")  # the script refuses it; nothing is written
            answered = True
    os.waitpid(pid, 0)
    assert answered, out.decode(errors="replace")
    assert seen.read_text().split() == ["tty", "real"], seen.read_text()
    assert not (Path(env["HOME"]) / ".config" / "omni" / "claude-oauth-token").exists()
