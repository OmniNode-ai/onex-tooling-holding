# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-18837: a row the ledger lock accepted cannot vanish without being named.

On 2026-09-19 an append was accepted at 14:05:31Z, a claim token was issued, and the
row was gone from the working tree 75 seconds later with no tree-moving git command
in between. The retrospective trace could not name the writer. The lock now admits one
holder (OMN-19262), but any writer that rewrites the whole file without taking the lock
(a restore from a stale copy, an editor save, a script) still drops the rows appended
after its read, and nothing said so: the next append succeeded and the publisher found
the hole only when it compared against ``main``.

The ledger command now keeps a witness beside its lock file: the rows it accepted, with
their claim tokens. Every later write verb, under the lock, checks that each witnessed
row is still in the ledger or an archive split. A row that is in neither is written to a
durable findings file naming the row and its claim token, and the append that noticed it
exits ``EXIT_LOST_ROW`` after its own row landed.

* AC1 -- the reproduction: append a claim row, overwrite the ledger from a copy read
  before that append, without the lock (the lost update), and append again.
* AC2 -- the append exits non-zero and the findings file names the row and the token.
  The same reproduction against the pre-change command exits 0 in silence; the positive
  control below (no overwrite) is the case that must stay silent.
* AC3 -- the check is called from ``main`` with no opt-in variable, and the fixture that
  replaces the check with a no-op admits the reproduction silently, which is what makes
  the registration, not only the code, the thing that refuses.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ops_tooling_pkg.ledger import lock as _lock_module

pytestmark = pytest.mark.unit

_SCRIPT = Path(_lock_module.__file__)
_SPEC = importlib.util.spec_from_file_location("ledger_lock_witness", _SCRIPT)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)

_BASE = "- 2026-09-24 base row one\n- 2026-09-24 base row two\n"
_CLAIM = (
    "- 2026-09-24 [lane-a] OMN-18837 - CLAIM: the row the lock accepted actor=claude:sonnet5 "
    "est ~1 lane-hours; displaces nothing; (OMN-18837)"
)
_NEXT = "- 2026-09-24 [lane-b] OMN-1 - the next append"
_TOKEN = re.compile(r"CLAIM-TOKEN (LCT1-\S+)")


def _run(ledger: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(ledger), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _append(ledger: Path, row: str) -> subprocess.CompletedProcess[str]:
    return _run(ledger, "--append", row)


def _findings(ledger: Path) -> list[dict[str, Any]]:
    path = MOD.lost_rows_path_for(MOD.lock_path_for(ledger))
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _lose_the_claim(tmp_path: Path) -> tuple[Path, str, str]:
    """Accept a claim row, then drop it the way a lock-bypassing writer does."""
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_BASE, encoding="utf-8")
    stale_copy = ledger.read_text(encoding="utf-8")
    accepted = _append(ledger, _CLAIM)
    assert accepted.returncode == 0, accepted.stderr
    token = _TOKEN.search(accepted.stdout)
    assert token, accepted.stdout
    assert _CLAIM in ledger.read_text(encoding="utf-8")
    # The lost update: a whole-file write of a copy read before the append.
    ledger.write_text(stale_copy, encoding="utf-8")
    assert _CLAIM not in ledger.read_text(encoding="utf-8")
    return ledger, token.group(1), accepted.stdout


def test_ac1_ac2_the_append_after_a_lost_row_exits_non_zero_and_names_the_claim(
    tmp_path: Path,
) -> None:
    ledger, token, _ = _lose_the_claim(tmp_path)

    result = _append(ledger, _NEXT)

    assert result.returncode == MOD.EXIT_LOST_ROW, (result.returncode, result.stderr)
    assert token in result.stderr
    assert "CLAIM: the row the lock accepted" in result.stderr
    # After the row, never instead of it: the append that noticed still landed.
    assert _NEXT in ledger.read_text(encoding="utf-8")
    found = _findings(ledger)
    assert len(found) == 1
    assert found[0]["claim_token"] == token
    assert found[0]["row"] == _CLAIM
    assert found[0]["ledger"] == str(ledger.resolve())


def test_a_reported_loss_is_reported_once_and_stays_on_disk(tmp_path: Path) -> None:
    ledger, _, _ = _lose_the_claim(tmp_path)
    assert _append(ledger, _NEXT).returncode == MOD.EXIT_LOST_ROW

    again = _append(ledger, "- 2026-09-24 [lane-c] OMN-2 - a later append")

    assert again.returncode == 0, again.stderr
    assert len(_findings(ledger)) == 1


def test_positive_control_an_intact_ledger_is_silent(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_BASE, encoding="utf-8")
    assert _append(ledger, _CLAIM).returncode == 0

    result = _append(ledger, _NEXT)

    assert result.returncode == 0, result.stderr
    assert "LOST ROW" not in result.stderr
    assert _findings(ledger) == []


def test_a_row_moved_to_an_archive_split_is_not_lost(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_BASE, encoding="utf-8")
    assert _append(ledger, _CLAIM).returncode == 0
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "ledger-split.md").write_text(_CLAIM + "\n", encoding="utf-8")
    ledger.write_text(_BASE, encoding="utf-8")

    result = _append(ledger, _NEXT)

    assert result.returncode == 0, result.stderr
    assert _findings(ledger) == []


def test_an_in_place_edit_through_the_command_verb_is_sanctioned(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(_BASE, encoding="utf-8")
    assert _append(ledger, _CLAIM).returncode == 0
    edit = (
        "import sys, pathlib; p = pathlib.Path(sys.argv[1]); "
        "p.write_text(p.read_text().replace('accepted', 'accepted (fixed)'))"
    )
    assert _run(ledger, "--", sys.executable, "-c", edit, str(ledger)).returncode == 0

    result = _append(ledger, _NEXT)

    assert result.returncode == 0, result.stderr
    assert _findings(ledger) == []


def test_ac3_the_check_is_registered_in_main_with_no_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("ONEX_LEDGER_WITNESS", "ONEX_LEDGER_VERIFY_ACCEPTED"):
        monkeypatch.delenv(name, raising=False)
    ledger, token, _ = _lose_the_claim(tmp_path)

    assert MOD.main([str(ledger), "--append", _NEXT]) == MOD.EXIT_LOST_ROW
    assert any(item["claim_token"] == token for item in _findings(ledger))


def test_ac3_with_the_check_unregistered_the_reproduction_is_admitted_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger, _, _ = _lose_the_claim(tmp_path)
    capsys.readouterr()
    monkeypatch.setattr(MOD, "verify_accepted_rows", lambda _ledger: [])

    assert MOD.main([str(ledger), "--append", _NEXT]) == 0
    assert "LOST ROW" not in capsys.readouterr().err
    assert _findings(ledger) == []
