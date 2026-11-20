"""The host closeout removes the ending lane's own pre-commit and uv caches (OMN-23198 AC2).

On 2026-11-08 h902's root filesystem was at 8.1 GB free; about 12 GB of it was eight lane-named pre-commit and
uv caches that lanes had set for themselves and nothing removed when the lanes ended. Everything runs for real
here: the closeout's own shell against a throwaway HOME and registry root, counting the lane-named cache
directories left on the host afterwards, and the directories that must survive.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from test_remote_lane import rl
from test_remote_lane_closeout_order import LANE, RUN_ID, Host

cache_closeout_summary = sys.modules[rl.closeout_summary.__module__].cache_closeout_summary

OTHER = "rl-b"


def _mk(path: Path, size: int = 1024) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "blob").write_bytes(b"x" * size)
    return path


def _closeout(host: Host, **extra: str) -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(host.home), "PATH": os.environ["PATH"], **extra}
    script = rl.closeout_script(RUN_ID, LANE, str(host.omni), None, retry_s=0)
    return subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True, env=env, check=False)


def _lane_caches(host: Host) -> list[Path]:
    """Lane-named cache directories left under the cache and scratch roots (what AC2's falsifier counts)."""
    roots = [host.home / ".cache", host.omni / ".claude_scratch" / LANE, host.home / "lab-run" / "scratch" / LANE]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found += [p for p in root.iterdir() if p.is_dir() and ("uv" in p.name or "pre-commit" in p.name)
                      and (LANE in p.name or root.name == LANE)]
    return found


def test_a_lane_named_cache_under_the_user_cache_root_is_removed_when_the_lane_ends(tmp_path: Path) -> None:
    host = Host(tmp_path)
    cache = host.home / ".cache"
    mine = [_mk(cache / f"landing-{LANE}-pre-commit"), _mk(cache / f"{LANE}-uv-cache"),
            _mk(cache / f"uv-cache-{LANE}"), _mk(cache / f"{LANE}-uv"), _mk(cache / f"{LANE}-pre-commit-cache")]
    assert len(_lane_caches(host)) == 5
    closed = _closeout(host)
    assert closed.returncode == 0, closed.stderr
    assert _lane_caches(host) == []
    assert sorted(c["path"] for c in rl.parse_cache_closeout(closed.stdout)) == sorted(str(p) for p in mine)
    assert all(c["status"] == "removed" and c["kb"] >= 1 for c in rl.parse_cache_closeout(closed.stdout))


def test_the_pool_caches_and_another_lanes_caches_survive(tmp_path: Path) -> None:
    host = Host(tmp_path)
    cache = host.home / ".cache"
    keep = [_mk(cache / "pre-commit"), _mk(cache / "uv"), _mk(cache / f"{OTHER}-uv-cache"),
            _mk(cache / f"landing-{OTHER}-pre-commit"), _mk(cache / "other-pre-commit"),
            _mk(cache / f"{LANE}-notes"), _mk(cache / f"x{LANE}-uv-cache")]
    _mk(cache / f"{LANE}-uv-cache")
    closed = _closeout(host)
    assert closed.returncode == 0, closed.stderr
    assert [p for p in keep if not p.exists()] == []
    assert not (cache / f"{LANE}-uv-cache").exists()


def test_a_symlink_named_for_the_lane_is_neither_followed_nor_removed(tmp_path: Path) -> None:
    host = Host(tmp_path)
    target = _mk(tmp_path / "shared-cache")
    link = host.home / ".cache" / f"{LANE}-uv-cache"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    closed = _closeout(host)
    assert closed.returncode == 0, closed.stderr
    assert link.is_symlink()
    assert (target / "blob").exists()
    assert rl.parse_cache_closeout(closed.stdout) == []


def test_scratch_cache_dirs_of_the_lane_go_but_its_reports_and_other_lanes_stay(tmp_path: Path) -> None:
    host = Host(tmp_path)
    nvme = tmp_path / "nvme-scratch"
    mine = host.omni / ".claude_scratch" / LANE
    for scratch in (mine, host.home / "lab-run" / "scratch" / LANE, nvme / LANE):
        _mk(scratch / "uv-cache")
        _mk(scratch / "pre-commit")
        (scratch / "result.md").write_text("report\n", encoding="utf-8")
    other = _mk(nvme / OTHER / "uv-cache")
    closed = _closeout(host, ONEX_LANE_CACHE_SCRATCH_ROOTS=f"{nvme}:{tmp_path / 'missing'}")
    assert closed.returncode == 0, closed.stderr
    for scratch in (mine, host.home / "lab-run" / "scratch" / LANE, nvme / LANE):
        assert not (scratch / "uv-cache").exists()
        assert not (scratch / "pre-commit").exists()
        assert (scratch / "result.md").exists()
    assert other.exists()
    assert len(rl.parse_cache_closeout(closed.stdout)) == 6


def test_the_sweep_runs_when_the_lane_made_no_worktrees(tmp_path: Path) -> None:
    host = Host(tmp_path)
    (host.omni / "omni_worktrees" / LANE).rmdir()
    _mk(host.home / ".cache" / f"{LANE}-uv-cache")
    closed = _closeout(host)
    assert closed.returncode == 0, closed.stderr
    assert "LANE-CLOSEOUT-NONE" in closed.stdout
    assert _lane_caches(host) == []


def test_the_sweep_runs_beside_a_lane_tree_and_the_tree_is_still_closed(tmp_path: Path) -> None:
    host = Host(tmp_path)
    tree = host.tree_in_run_dir("OMN-1/repo")
    _mk(host.home / ".cache" / f"{LANE}-pre-commit")
    closed = _closeout(host)
    assert closed.returncode == 0, closed.stderr
    assert _lane_caches(host) == []
    assert [c["tree"] for c in rl.parse_closeout(closed.stdout)] == [str(tree)]
    assert not tree.exists()


def test_a_cache_that_cannot_be_removed_is_reported_and_the_rest_still_go(tmp_path: Path) -> None:
    host = Host(tmp_path)
    cache = host.home / ".cache"
    stuck = _mk(cache / f"{LANE}-uv-cache" / "inner" / "deeper")
    gone = _mk(cache / f"{LANE}-pre-commit")
    inner = stuck.parent
    inner.chmod(0o555)  # its entries cannot be unlinked
    try:
        closed = _closeout(host)
        cells = {c["path"]: c["status"] for c in rl.parse_cache_closeout(closed.stdout)}
        assert cells[str(gone)] == "removed"
        assert cells[str(cache / f"{LANE}-uv-cache")] == "failed"
        assert "could not remove" in cache_closeout_summary(rl.parse_cache_closeout(closed.stdout))
    finally:
        inner.chmod(0o755)


def test_the_summary_is_empty_when_the_lane_left_nothing_and_never_spells_a_worktree_cell() -> None:
    assert cache_closeout_summary([]) == ""
    text = cache_closeout_summary([{"status": "removed", "kb": 3072, "path": "/h/.cache/rl-uv-cache"}])
    assert "removed 1 lane cache dir(s), 3 MB" in text
    assert "worktree=" not in text


def test_the_terminal_text_names_the_cache_removals_beside_the_trees_and_alone() -> None:
    caches = [{"status": "removed", "kb": 2048, "path": "/h/.cache/rl-uv-cache"}]
    none = rl.closeout_summary([], unavailable=False, caches=caches)
    assert none == "host closeout: the lane made no worktrees; host cache closeout: removed 1 lane cache dir(s), 2 MB"
    cells = [{"rc": 0, "tree": "/o/t", "cell": "worktree=removed:/o/t", "note": ""}]
    assert rl.closeout_summary(cells, unavailable=False, caches=caches).endswith("; host cache closeout: removed 1 lane cache dir(s), 2 MB")
    assert rl.closeout_summary(cells, unavailable=False) == "host closeout: removed:/o/t"
