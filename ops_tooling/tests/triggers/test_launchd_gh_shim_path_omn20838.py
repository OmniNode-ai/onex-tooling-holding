"""OMN-20838 -- every launchd plist puts the gh routing shim ahead of the real gh.

The operator Mac keeps a routing shim at ``~/.local/bin/gh``. It sends reads to the read-only App
token and writes one row per call to ``gh-calls.log``. A launchd job gets only the PATH its plist
declares, and thirteen jobs listed ``/opt/homebrew/bin`` and ``/usr/local/bin`` ahead of the shim
directory, so their ``gh`` resolved to the real binary. On 2026-10-09 the dod-closeout-sweep job
spent the operator's own core bucket that way (11 token-less ``--paginate`` spawns accounted for
64 calls in a 91 s sample) and none of it reached the call log.

The rule is structural: in every rendered plist that sets a PATH, the shim directory is the first
entry. A plist that must run the real binary says so in its own template, in a comment carrying
``ONEX_GH_PATH_REAL:`` and a reason, so the exception is visible at the file it excuses and a
reviewer reads it in the diff. This file keeps no list of names.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from _trigger_git_env import strip_git_env

strip_git_env(os.environ)

REPO_ROOT = Path(__file__).resolve().parents[2]
MORNING_INSTALLER = REPO_ROOT / "launchd" / "morning-workflows" / "morning_trigger_install.sh"
TEMPLATE_ROOTS = (REPO_ROOT / "launchd", REPO_ROOT / "src")
FAKE_HOME = "<home>"
SHIM_DIR = f"{FAKE_HOME}/.local/bin"
REAL_MARKER = "ONEX_GH_PATH_REAL:"
MIN_REASON_CHARS = 30
PATH_KEY = re.compile(r"<key>PATH</key>\s*<string>([^<]*)</string>")
MARKER = re.compile(re.escape(REAL_MARKER) + r"\s*(.*?)\s*(?:-->|$)", re.DOTALL | re.MULTILINE)


def path_violation(path_value: str, home: str) -> str | None:
    """Return why a PATH lets the real gh win over the shim, or None when the shim is first."""
    entries = [entry for entry in path_value.split(":") if entry]
    shim = f"{home}/.local/bin"
    if shim not in entries:
        return f"shim directory {shim} is not on PATH {path_value!r}"
    if entries[0] != shim:
        return f"{entries[0]} comes before the shim directory {shim} on PATH {path_value!r}"
    return None


def plist_violation(text: str, home: str) -> str | None:
    """Check one rendered plist; one with no PATH key inherits the launchd default and is clean."""
    declared = PATH_KEY.search(text)
    if declared is None:
        return None
    return path_violation(declared.group(1), home)


def templates() -> list[Path]:
    found: list[Path] = []
    for root in TEMPLATE_ROOTS:
        found.extend(path for path in root.rglob("*.plist.tmpl") if ".venv" not in path.parts)
    return sorted(found)


def real_gh_reason(text: str) -> str | None:
    """The reason a template runs the real gh on purpose, or None when it does not say so."""
    match = MARKER.search(text)
    return match.group(1) if match else None


def test_the_template_scan_sees_the_templates() -> None:
    # A scan over an empty glob passes for any content. The morning, host-installer, landing
    # controller and drift templates are all known to exist; fewer than that means the glob broke.
    names = {path.name for path in templates()}
    assert len(names) >= 20, sorted(names)
    for expected in (
        "ai.omninode.interval-workflow.plist.tmpl",
        "ai.omninode.hourly-workflow.plist.tmpl",
        "ai.omninode.morning-workflow.plist.tmpl",
        "ai.omninode.landing-controller.plist.tmpl",
        "ai.omninode.host-drift.plist.tmpl",
        "ai.omninode.drain-watchdog.plist.tmpl",
    ):
        assert expected in names


@pytest.mark.parametrize("template", templates(), ids=lambda path: path.name)
def test_template_puts_the_shim_directory_first(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    if PATH_KEY.search(text) is None:
        pytest.fail(f"{template.name} sets no PATH; declare one so the shim is first")
    reason = real_gh_reason(text)
    if reason is not None:
        assert len(reason) >= MIN_REASON_CHARS, (
            f"{template.name}: {REAL_MARKER} needs a reason of at least "
            f"{MIN_REASON_CHARS} characters, got {reason!r}"
        )
        return
    rendered = text.replace("__HOME__", FAKE_HOME)
    assert plist_violation(rendered, FAKE_HOME) is None, plist_violation(rendered, FAKE_HOME)


def test_real_gh_marker_is_rare_and_explained() -> None:
    # The two daemons that read their own quota with their own token. A third marker is a
    # decision a reviewer should make on purpose, so the count is asserted rather than assumed.
    marked = sorted(
        path.name
        for path in templates()
        if real_gh_reason(path.read_text(encoding="utf-8")) is not None
    )
    assert marked == [
        "ai.omninode.omnimarket-release-cut.plist.tmpl",
        "ai.omninode.pr-watcher.plist.tmpl",
    ]


def test_control_swapped_path_is_flagged() -> None:
    # The positive control: the order the thirteen jobs shipped with must be caught.
    swapped = (
        f"<key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:{SHIM_DIR}:/usr/bin</string>"
    )
    reason = plist_violation(swapped, FAKE_HOME)
    assert reason is not None and "/opt/homebrew/bin comes before the shim directory" in reason


def test_control_missing_shim_directory_is_flagged() -> None:
    absent = "<key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>"
    reason = plist_violation(absent, FAKE_HOME)
    assert reason is not None and "is not on PATH" in reason


def test_control_shim_first_is_clean() -> None:
    ordered = (
        f"<key>PATH</key><string>{SHIM_DIR}:/opt/homebrew/bin:/usr/local/bin:/usr/bin</string>"
    )
    assert plist_violation(ordered, FAKE_HOME) is None


def test_control_templates_scan_flags_a_planted_bad_template(tmp_path: Path) -> None:
    planted = tmp_path / "ai.omninode.planted.plist.tmpl"
    planted.write_text(
        "<plist><dict><key>EnvironmentVariables</key><dict>"
        "<key>PATH</key><string>/opt/homebrew/bin:__HOME__/.local/bin:/usr/bin</string>"
        "</dict></dict></plist>",
        encoding="utf-8",
    )
    rendered = planted.read_text(encoding="utf-8").replace("__HOME__", FAKE_HOME)
    assert plist_violation(rendered, FAKE_HOME) is not None
    assert real_gh_reason(rendered) is None


def test_every_plist_the_morning_installer_renders_puts_the_shim_first(tmp_path: Path) -> None:
    # The installer substitutes the placeholders itself; this reads what it actually writes.
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path),
            "registry_root": str(tmp_path),
            "MORNING_DRY_RUN_DIR": str(tmp_path / "Library" / "LaunchAgents"),
        }
    )
    result = subprocess.run(
        ["/bin/bash", str(MORNING_INSTALLER), "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rendered = sorted((tmp_path / "Library" / "LaunchAgents").glob("ai.omninode.*.plist"))
    # Nine workflow agents (3 daily, 1 late, 2 hourly, 3 interval) and the watchdog.
    assert len(rendered) >= 10, [path.name for path in rendered]
    for plist in rendered:
        text = plist.read_text(encoding="utf-8")
        assert PATH_KEY.search(text) is not None, plist.name
        assert plist_violation(text, str(tmp_path)) is None, (
            f"{plist.name}: {plist_violation(text, str(tmp_path))}"
        )
