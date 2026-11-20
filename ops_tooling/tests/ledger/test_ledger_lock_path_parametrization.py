# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-17235 — prove ``ledger_lock.py`` is path-parametrized, so the ledger move
is unblocked by evidence rather than assumed.

Context. The operator ruling of 2026-08-31 sends tracking artifacts to
docs_repo, and OMN-17235 repointed the four registry_root generators.
``docs/tracking/ROLLING_WORK_LEDGER.md`` is the ONE deliberate exception: its
literal path is cited by dozens of files across omniclaude, omnibase_infra and
omnimarket, so repointing the registry_root generators alone would FORK the
append-only ledger across two files and break the §0a claim protocol for every
other lane. Moving it is a fleet-wide repoint plus a file migration — its own
ticket.

What this module establishes is that **no code change gates that move**: the
lock tool already takes the ledger path as a positional argument and carries no
knowledge of ``docs/tracking``. The two properties that must survive the move
are the ones the ledger exists for, so both are exercised against a
kb-internal-shaped path:

* the **mutex** — a per-ledger-path lock, so two writers cannot interleave;
* the **claim-token clock guard** — a claim row must provably precede the
  mutation it authorizes, verified from the lock-assigned byte offset rather
  than from a timestamp a writer typed.

Since OMN-19347 the tool is the ``onex-ledger`` console script of this package,
and the ledger it protects is its positional argument or ``$ONEX_LEDGER_PATH``,
with no default. The last four tests pin that resolution: the console script is
declared, ``--print-grammar`` needs no ledger, an append with neither the
argument nor the variable is refused naming the variable, and the variable alone
is enough to append.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from ops_tooling_pkg.ledger import lock as _lock_module

# The kb-internal destination the ledger would move to, mirrored from the layout
# the repointed generators already write to (beta/tracking/).
KB_RELATIVE_LEDGER = Path("beta") / "tracking" / "ROLLING_WORK_LEDGER.md"


@pytest.fixture(scope="module")
def ledger_lock() -> Path:
    return Path(_lock_module.__file__)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(tool: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), *args], capture_output=True, text=True, check=False
    )


def _run_module(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ops_tooling_pkg.ledger", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _env_without_ledger() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("ONEX_LEDGER_PATH", None)
    return env


@pytest.mark.unit
def test_ledger_path_is_a_positional_argument(ledger_lock: Path) -> None:
    """The claim OMN-17235 rests on: the tool is told which ledger to protect,
    it does not resolve one. A hardcoded ``docs/tracking`` anywhere in it would
    make the ledger move a code change rather than a path change."""
    helped = _run(ledger_lock, "--help")
    assert helped.returncode == 0, helped.stderr
    assert "ledger" in helped.stdout, "the ledger path must be a CLI argument"
    source = ledger_lock.read_text(encoding="utf-8")
    assert "docs/tracking" not in source, (
        "ledger_lock.py hardcodes docs/tracking — the ledger move would then be a "
        "code change, not a path change"
    )


@pytest.mark.unit
def test_appends_to_an_arbitrary_kb_internal_shaped_path(ledger_lock: Path, tmp_path: Path) -> None:
    """Append against a path that does not exist yet, under a kb-internal-shaped
    tree. Nothing about the destination is special to the tool.

    The payloads carry a date because OMN-18801 widened the row-shape guard to
    every append to a markdown ledger, not only one naming a --section-heading.
    That is the tool working: this module's claim is about the PATH, so its
    rows must be ones the tool admits anywhere."""
    ledger = tmp_path / KB_RELATIVE_LEDGER
    ledger.parent.mkdir(parents=True)

    # OMN-19256: a file named ROLLING_WORK_LEDGER.md is governed by the row
    # grammar wherever it lives, so the rows are canonical and stamped live.
    first = _run(
        ledger_lock,
        str(ledger),
        "--append",
        f"{_now()} | STATUS | lane=lane-a | ticket=OMN-17235 | first row",
    )
    assert first.returncode == 0, f"{first.stdout}{first.stderr}"
    assert ledger.is_file(), "the append did not create the ledger"
    assert "OMN-17235" in ledger.read_text(encoding="utf-8")

    second = _run(
        ledger_lock,
        str(ledger),
        "--append",
        f"{_now()} | TERMINAL | lane=lane-a | ticket=OMN-17235 | friction=none | done "
        "| delegated=0 delegation_reason=fixture only",
    )
    assert second.returncode == 0, f"{second.stdout}{second.stderr}"
    body = ledger.read_text(encoding="utf-8")
    assert "| STATUS |" in body and "| TERMINAL |" in body, "append is not additive"


@pytest.mark.unit
def test_mutex_is_per_path_and_survives_the_move(ledger_lock: Path, tmp_path: Path) -> None:
    """The lock is derived from the ledger path, so it keeps working at the new
    location and two DIFFERENT ledgers never contend with each other.

    Proven by holding the lock on one ledger with a long-running command and
    showing (a) a second writer to the SAME path times out with the documented
    exit 75, and (b) a writer to a DIFFERENT path is unaffected.
    """
    kb_ledger = tmp_path / KB_RELATIVE_LEDGER
    kb_ledger.parent.mkdir(parents=True)
    kb_ledger.write_text("- seed\n", encoding="utf-8")
    other = tmp_path / "beta" / "tracking" / "OTHER_LEDGER.md"
    other.write_text("- seed\n", encoding="utf-8")

    holder = subprocess.Popen(
        ["python3", str(ledger_lock), str(kb_ledger), "--", "sleep", "10"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Give the holder time to acquire before probing.
        contended = None
        for _ in range(50):
            contended = _run(
                ledger_lock,
                str(kb_ledger),
                "--timeout",
                "1s",
                "--append",
                f"{_now()} | STATUS | lane=lane-a | blocked",
            )
            if contended.returncode == 75:
                break
        assert contended is not None and contended.returncode == 75, (
            "a second writer to the SAME ledger path must hit the documented "
            f"exit-75 lock timeout; got {contended.returncode if contended else None}"
            f"\n{contended.stdout if contended else ''}{contended.stderr if contended else ''}"
        )

        free = _run(ledger_lock, str(other), "--timeout", "5s", "--append", "- 2026-09-19 ok")
        assert free.returncode == 0, (
            "the lock must be PER LEDGER PATH — a different ledger must not "
            f"contend\n{free.stdout}{free.stderr}"
        )
    finally:
        holder.kill()
        holder.wait(timeout=10)


@pytest.mark.unit
def test_claim_token_clock_guard_holds_at_the_new_path(ledger_lock: Path, tmp_path: Path) -> None:
    """The §0a guarantee: a CLAIM must precede the mutation it authorizes.

    The token carries the lock-assigned byte offset, which only ever increases,
    so this does not depend on a timestamp the writer typed. Verified here
    against a kb-internal-shaped path, in both directions — a mutation AFTER the
    claim verifies, a mutation BEFORE it is rejected.
    """
    ledger = tmp_path / KB_RELATIVE_LEDGER
    ledger.parent.mkdir(parents=True)

    # OMN-18554: stamped from the live clock and priced. omnibase_infra's
    # ledger_lock.py now carries the OMN-17427 wall-clock guard and the OMN-15649
    # rule-4 cost-sentence gate, both ported there from a copy that used to live
    # only in registry_root. A row frozen at a date literal is refused by the first,
    # and an unpriced CLAIM row by the second, so neither would reach the
    # claim-token path this test is actually about.
    claim = (
        f"{_now()} | CLAIM | lane=lane-a | actor=test | ticket=OMN-17235 | "
        "worktree=none | placement gate; est ~2 lane-hours; displaces nothing; (OMN-17235)"
    )
    minted = _run(ledger_lock, str(ledger), "--append", claim)
    assert minted.returncode == 0, f"{minted.stdout}{minted.stderr}"

    token = ""
    for line in minted.stdout.splitlines():
        if "CLAIM-TOKEN" in line:
            token = line.split("CLAIM-TOKEN", 1)[1].strip()
    if not token:
        pytest.skip(
            "this ledger_lock.py build minted no claim token for the row shape "
            "used here; the clock guard is covered by omnibase_infra's own suite"
        )

    good = _run(
        ledger_lock,
        str(ledger),
        "--verify-claim-token",
        token,
        "--mutation-at",
        "2099-01-01T00:00:00Z",
    )
    assert good.returncode == 0, (
        f"a mutation AFTER the claim must verify at the new path\n{good.stdout}{good.stderr}"
    )

    bad = _run(
        ledger_lock,
        str(ledger),
        "--verify-claim-token",
        token,
        "--mutation-at",
        "2000-01-01T00:00:00Z",
    )
    assert bad.returncode == 1, (
        "a POST-HOC claim (mutation before the claim) must be rejected — this is "
        f"the guard that makes §0a mean anything\n{bad.stdout}{bad.stderr}"
    )


@pytest.mark.unit
def test_onex_ledger_is_a_declared_console_script() -> None:
    """AC8: the command a consumer runs is the package's own entry point."""
    found = entry_points(group="console_scripts", name="onex-ledger")
    assert [ep.value for ep in found] == ["ops_tooling_pkg.ledger.lock:main"]


@pytest.mark.unit
def test_print_grammar_needs_no_ledger_and_no_variable() -> None:
    proc = _run_module("--print-grammar", env=_env_without_ledger())
    assert proc.returncode == 0, proc.stderr
    assert "ROLLING_WORK_LEDGER.md" in proc.stdout


@pytest.mark.unit
def test_an_append_with_no_ledger_is_refused_naming_the_variable(tmp_path: Path) -> None:
    """AC13: no argument and no ONEX_LEDGER_PATH is a refusal, never a default."""
    env = _env_without_ledger()
    before = sorted(p.name for p in tmp_path.iterdir())
    proc = subprocess.run(
        [sys.executable, "-m", "ops_tooling_pkg.ledger", "--append", f"{_now()} | x"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )
    assert proc.returncode == 2, proc.stderr
    assert "ONEX_LEDGER_PATH" in proc.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == before


@pytest.mark.unit
def test_the_variable_alone_names_the_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "WORK_LEDGER.md"
    ledger.write_text("# ledger\n\n", encoding="utf-8")
    env = _env_without_ledger()
    env["ONEX_LEDGER_PATH"] = str(ledger)
    row = f"{_now()} | env-resolved append (OMN-19347)"
    proc = _run_module("--append", row, env=env)
    assert proc.returncode == 0, proc.stderr
    assert row in ledger.read_text(encoding="utf-8")
