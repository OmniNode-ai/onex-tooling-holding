"""The ledger-ask search blocks run with rg absent and without grep -P (OMN-17427).

The skill's Search, lane-chain and PR-chain blocks are extracted from SKILL.md and run under
``bash -c`` with a PATH holding no ``rg``, which is how a lane meets them (rg is a shell function
only inside a Claude Code session). macOS grep has no -P, so the blocks must be POSIX grep -E/-F.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "plugins/omni/skills/ledger-ask/SKILL.md"

LEDGER = """\
2026-09-01T10:00:00Z | RULING | lane=ops | operator words verbatim: "<removed>"
2026-09-01T11:00:00Z | MSG | from=landing-L1 | pr=omnibase_core#1839 handed-off
2026-09-01T12:00:00Z | CLAIM | lane=landing-L1 | pr=omnibase_core#1839 start
not a row: downstream
"""
ARCHIVE = "2026-08-01T10:00:00Z | OPERATOR-CONSENT | lane=old | operator downstream notice\n"


def _blocks() -> list[str]:
    return re.findall(r"```bash\n(.*?)```", SKILL.read_text(), re.S)


def _block(marker: str) -> str:
    return next(b for b in _blocks() if marker in b)


def _env(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for tool in ("bash", "grep", "awk", "sort", "head", "cut", "sed"):
        link = bindir / tool
        if not link.exists():
            link.symlink_to(shutil.which(tool) or f"/usr/bin/{tool}")
    assert shutil.which("rg", path=str(bindir)) is None
    return {"PATH": str(bindir), "HOME": str(tmp_path)}


def _run(tmp_path: Path, script: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "archive").mkdir(exist_ok=True)
    (tmp_path / "LEDGER.md").write_text(LEDGER)
    (tmp_path / "archive" / "a-split.md").write_text(ARCHIVE)
    return subprocess.run(
        [str(tmp_path / "bin" / "bash"), "-c", script],
        cwd=tmp_path,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


def test_search_block_returns_rows_without_rg(tmp_path: Path) -> None:
    block = _block("KINDS='RULING|OPERATOR-CONSENT'")
    r = _run(tmp_path, "LF=LEDGER.md\n" + block)
    assert r.returncode == 0, r.stderr
    assert "invalid option" not in r.stderr and "not found" not in r.stderr, r.stderr
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 2, r.stdout
    assert lines[0].split("\t")[3] == "RULING"  # coverage 3 outranks the archive consent row
    assert lines[0].endswith("LEDGER.md:1")
    assert any(ln.endswith("archive/a-split.md:1") for ln in lines)
    assert not any("not a row" in ln for ln in lines)


def test_lane_and_pr_chain_blocks_without_rg(tmp_path: Path) -> None:
    block = _block("LANE='landing-L1114'").replace("landing-L1114", "landing-L1")
    r = _run(tmp_path, "LF=LEDGER.md\n" + block)
    assert r.returncode == 0, r.stderr
    assert "invalid option" not in r.stderr and "not found" not in r.stderr, r.stderr
    assert "LEDGER.md:3" in r.stdout and "LEDGER.md:2" in r.stdout, r.stdout


def test_skill_names_no_pcre_or_rg_in_blocks() -> None:
    for b in _blocks():
        assert not re.search(r"\brg\b|grep [^|\n]*-P\b", b), b
    assert os.path.exists(SKILL)
