# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-19347: onex-ledger and the script it replaces take the SAME lock file.

The callers of ``ledger_lock.py`` (skills, hooks, briefs, the Codex automation)
move to ``onex-ledger`` in a separate cutover, one caller at a time. Until the
last one has moved, both tools append to the live rolling ledger. They exclude
each other only if they derive the identical lock-file path from the ledger's
resolved path. The derivation below is pinned to omnibase_infra
``scripts/ledger_lock.py`` at fc0250a91 (OMN-19262): a lock directory named
``.ledger_locks`` beside the ledger, and a file named
``<ledger name>.<first 24 hex of sha256(resolved path)>.flock``. Changing any
part of it before the cutover completes gives the two tools two different locks
on one file, which is the two-writer defect OMN-19262 closed.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ops_tooling_pkg.ledger import lock

pytestmark = pytest.mark.unit


def test_the_lock_file_path_matches_the_legacy_derivation(tmp_path: Path) -> None:
    ledger = tmp_path / "tracking" / "ROLLING_WORK_LEDGER.md"
    ledger.parent.mkdir()
    ledger.write_text("", encoding="utf-8")
    resolved = ledger.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:24]
    expected = resolved.parent / ".ledger_locks" / f"ROLLING_WORK_LEDGER.md.{digest}.flock"
    assert lock.lock_path_for(ledger) == expected


def test_the_lock_directory_constants_match_the_legacy_script() -> None:
    assert lock.DEFAULT_LOCK_DIRNAME == ".ledger_locks"
    assert lock.LOCK_FILE_SUFFIX == ".flock"
    assert lock.LOCK_DIR_GITIGNORE == "# ledger_lock.py lock files, never tracked (OMN-19262)\n*\n"


def test_a_held_lock_refuses_a_second_writer_through_the_cli(tmp_path: Path) -> None:
    ledger = tmp_path / "WORK_LEDGER.md"
    ledger.write_text("# ledger\n", encoding="utf-8")
    row = f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} | a second writer"
    with lock.LedgerLock(ledger, 5.0):
        rc = lock.main([str(ledger), "--timeout", "0", "--append", row])
    assert rc == 75
    assert ledger.read_text(encoding="utf-8") == "# ledger\n"
