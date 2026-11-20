"""Guard: no committed script puts a broker credential on the `rpk`/`docker exec` argv (OMN-19513).

`ps` on a shared host shows every process's full argv to every user with a shell there. An
`-X user=`, `-X pass=`, `--user`, `--password` or `docker exec -e *PASS*=`/`*TOKEN*=`/`*SECRET*=`
flag whose value is a literal or an expanded shell variable puts the live secret on that table for
the life of the call. The safe shape pipes the credential over stdin into the remote/inner shell,
which reads it into `RPK_USER`/`RPK_PASS`/`RPK_SASL_MECHANISM` (the env names `rpk` reads natively)
before `exec`-ing `rpk` with no `-X user=`/`-X pass=` flag at all.

The scan is static (grep-shaped), not a live process check, so it catches the pattern before it is
ever run. Every refusal below has a positive control (a synthetic bad script) proving the scanner
actually fires, per this repo's convention (see tests/test_skill_scripts.py docstring): a scanner
that finds everything or nothing is equally useless.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# `-X user=<value>` / `-X pass=<value>` / `--password <value>` where <value> is a shell
# expansion ($VAR, ${VAR}, $(...)) or a non-empty quoted/bare literal -- i.e. an actual
# credential value reaching argv, not a bare flag name in prose or a `-X user= -X pass=`
# placeholder with nothing after the `=`.
_RPK_FLAG_WITH_VALUE = re.compile(
    r"""-X\s+(user|pass)=(?:"[^"]+"|'[^']+'|\$\{?\w+\}?|\$\([^)]+\)|[^\s"'-][^\s]*)"""
)
_LONG_PASSWORD_FLAG = re.compile(r"--password[= ]\S")

# `docker exec -e SOMETHING_PASS=...` / `-e ..._TOKEN=...` / `-e ..._SECRET=...`: the flag's
# value is host-side argv even though the exec'd process never sees it as a CLI flag.
_DOCKER_DASH_E_SECRET = re.compile(
    r"docker\s+exec\b[^\n]*-e\s+\w*(PASS|TOKEN|SECRET)\w*="
)


def _find_violations(text: str) -> list[str]:
    hits = []
    for pattern in (_RPK_FLAG_WITH_VALUE, _LONG_PASSWORD_FLAG, _DOCKER_DASH_E_SECRET):
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append(f"line {line_no}: {m.group(0)!r}")
    return hits


def _shell_scripts() -> list[Path]:
    return sorted(p for p in REPO.rglob("*.sh") if ".git" not in p.parts)


def test_positive_control_catches_a_planted_argv_credential(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sh"
    bad.write_text('docker exec redpanda rpk -X user="$U" -X pass="$P" topic list\n')
    assert _find_violations(bad.read_text()), "scanner must fire on a planted -X pass=$VAR"


def test_positive_control_catches_a_literal_password_flag(tmp_path: Path) -> None:
    bad = tmp_path / "bad2.sh"
    bad.write_text("rpk --password hunter2 topic list\n")
    assert _find_violations(bad.read_text())


def test_positive_control_catches_docker_exec_dash_e_secret(tmp_path: Path) -> None:
    bad = tmp_path / "bad3.sh"
    bad.write_text('docker exec -e RPK_PASS="$P" redpanda rpk topic list\n')
    assert _find_violations(bad.read_text())


def test_negative_control_the_safe_stdin_shape_is_clean() -> None:
    good = (
        'printf \'%s\\n%s\\n\' "$U" "$P" | docker exec -i redpanda '
        "sh -c 'read -r RPK_USER; read -r RPK_PASS; export RPK_USER RPK_PASS "
        "RPK_SASL_MECHANISM=SCRAM-SHA-256; exec rpk \"$@\"' _ topic list\n"
    )
    assert not _find_violations(good), "the stdin-piped shape must read as clean"


def test_bare_flag_name_with_nothing_after_equals_is_not_flagged() -> None:
    # SKILL.md prose describing the flag names themselves (no value after `=`) is not a leak.
    prose = "pass `-X user= -X pass= -X sasl.mechanism=SCRAM-SHA-256` (never a value here)\n"
    assert not _find_violations(prose)


def test_no_shell_script_in_this_repo_puts_a_credential_on_rpk_or_docker_exec_argv() -> None:
    offenders: dict[str, list[str]] = {}
    for script in _shell_scripts():
        hits = _find_violations(script.read_text(encoding="utf-8"))
        if hits:
            offenders[str(script.relative_to(REPO))] = hits
    assert not offenders, (
        "credential(s) on rpk/docker-exec argv (visible to every user via `ps`) in: "
        f"{offenders}. Pipe the value over stdin into RPK_USER/RPK_PASS/RPK_SASL_MECHANISM "
        "instead (see scripts/command_loop_probe.sh)."
    )
