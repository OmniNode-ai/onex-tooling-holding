"""Proof of deterministic CI sharding and quota-aware workers (OMN-20707)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from _ci_impact import FILES_PER_SHARD, Selection
from _ci_shard import (
    GIB,
    POOL_MEMORY_BYTES,
    POOL_RUNNERS,
    WORKER_MEMORY_BYTES,
    auto_worker_count,
    cgroup_cpu_limit,
    cgroup_memory_limit,
    parse_shard,
    shard_of,
)

REPO = Path(__file__).resolve().parents[1]
# host-35-example's slice share per container (56 GiB / 5) at 5 GiB per worker.
MAX_AUTO_WORKERS_PER_SHARE = 2


@pytest.mark.unit
@pytest.mark.parametrize(
    ("spec", "expected"), [("1/1", (1, 1)), ("3/4", (3, 4)), (" 2/4 ", (2, 4))]
)
def test_parse_shard_accepts(spec: str, expected: tuple[int, int]) -> None:
    assert parse_shard(spec) == expected


@pytest.mark.unit
@pytest.mark.parametrize("spec", ["0/4", "5/4", "4", "a/b", "1/0", "-1/4", ""])
def test_parse_shard_refuses(spec: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_shard(spec)
    assert repr(spec) in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize("total", [1, 2, 4, 7, 8, 16])
def test_shard_partition(total: int) -> None:
    nodeids = {f"tests/test_x.py::test_{i}[p{i % 7}]" for i in range(2000)}
    shards = [
        {nodeid for nodeid in nodeids if shard_of(nodeid, total) == k} for k in range(1, total + 1)
    ]
    for nodeid in nodeids:
        assert 1 <= shard_of(nodeid, total) <= total
        assert sum(nodeid in shard for shard in shards) == 1
    assert set().union(*shards) == nodeids
    if total in (4, 8, 16):
        assert all(shards)


@pytest.mark.unit
def test_shard_of_stable() -> None:
    assert shard_of("tests/test_x.py::test_42[p0]", 4) == 4


@pytest.mark.unit
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("200000 100000", 2),
        ("150000 100000", 2),
        ("50000 100000", 1),
        ("max 100000", None),
        ("x y", None),
    ],
)
def test_cgroup_cpu_limit_v2(tmp_path: Path, content: str, expected: int | None) -> None:
    (tmp_path / "cpu.max").write_text(content)
    assert cgroup_cpu_limit(tmp_path) == expected


@pytest.mark.unit
@pytest.mark.parametrize(("quota", "expected"), [(300000, 3), (-1, None)])
def test_cgroup_cpu_limit_v1(tmp_path: Path, quota: int, expected: int | None) -> None:
    cpu = tmp_path / "cpu"
    cpu.mkdir()
    (cpu / "cpu.cfs_quota_us").write_text(str(quota))
    (cpu / "cpu.cfs_period_us").write_text("100000")
    assert cgroup_cpu_limit(tmp_path) == expected


@pytest.mark.unit
def test_cgroup_cpu_limit_missing(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(tmp_path) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"memory.max": "8589934592"}, 8 * GIB),
        ({"memory.max": "max"}, None),
        ({"memory.max": "max", "memory.high": "4294967296"}, 4 * GIB),
        ({"memory.max": "8589934592", "memory.high": "4294967296"}, 4 * GIB),
        ({"memory/memory.limit_in_bytes": "6442450944"}, 6 * GIB),
        ({"memory/memory.limit_in_bytes": "9223372036854771712"}, None),
        ({}, None),
    ],
)
def test_cgroup_memory_limit(tmp_path: Path, files: dict[str, str], expected: int | None) -> None:
    for name, text in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    assert cgroup_memory_limit(tmp_path) == expected


@pytest.mark.unit
def test_auto_workers_unset_cpu_quota_is_bounded_by_memory_limit(tmp_path: Path) -> None:
    """OMN-17427: cpu.max=max once meant xdist's host-core default (capped at 8) per job."""
    (tmp_path / "cpu.max").write_text("max 100000")
    (tmp_path / "memory.max").write_text(str(10 * GIB))
    assert auto_worker_count(tmp_path, cores=56) == 2  # 10 GiB at 5 GiB per worker


@pytest.mark.unit
def test_auto_workers_takes_the_tighter_of_cpu_and_memory(tmp_path: Path) -> None:
    (tmp_path / "cpu.max").write_text("200000 100000")
    (tmp_path / "memory.max").write_text(str(64 * GIB))
    assert auto_worker_count(tmp_path, cores=56) == 2
    (tmp_path / "cpu.max").write_text("1600000 100000")
    (tmp_path / "memory.max").write_text(str(12 * GIB))
    assert auto_worker_count(tmp_path, cores=56) == MAX_AUTO_WORKERS_PER_SHARE


@pytest.mark.unit
def test_auto_workers_with_no_readable_limit_uses_the_shared_pool_budget(tmp_path: Path) -> None:
    """A container that reads neither limit still shares the 64 GiB slice with its peers."""
    assert auto_worker_count(tmp_path, cores=56) == MAX_AUTO_WORKERS_PER_SHARE
    assert auto_worker_count(tmp_path, cores=1) == 1


@pytest.mark.unit
@pytest.mark.parametrize("container_limit", [20, 24, 32, 64, 128])
def test_auto_workers_never_exceed_the_shared_slice_share(
    tmp_path: Path, container_limit: int
) -> None:
    """OMN-17427: a container's own ceiling is no licence to take more than its slice share.

    host-35-example runs five containers in one 56 GiB-high slice. A container whose own memory.max reads
    20-24 GiB (or more) used to start 5-6 workers; with five containers that overran the slice
    and the kernel SIGKILLed the workers during collection (run 41889179500).
    """
    (tmp_path / "cpu.max").write_text("max 100000")
    (tmp_path / "memory.max").write_text(str(container_limit * GIB))
    workers = auto_worker_count(tmp_path, cores=56)
    assert workers == MAX_AUTO_WORKERS_PER_SHARE
    assert POOL_RUNNERS * workers * WORKER_MEMORY_BYTES <= POOL_MEMORY_BYTES




@pytest.mark.unit
def test_auto_workers_never_below_one(tmp_path: Path) -> None:
    (tmp_path / "memory.max").write_text(str(GIB))
    assert auto_worker_count(tmp_path, cores=56) == 1


def _collect(spec: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    if spec is not None:
        command.append(f"--ci-shard={spec}")
    command.append("tests/test_ci_shard.py")
    return subprocess.run(
        command,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )


def _collected_nodeids(spec: str | None = None) -> list[str]:
    result = _collect(spec)
    assert result.returncode == 0, result.stdout + result.stderr
    return [line for line in result.stdout.splitlines() if "::" in line]


@pytest.mark.unit
@pytest.mark.parametrize("total", [4, 8])
def test_conftest_shard_wiring(total: int) -> None:
    full = set(_collected_nodeids())
    # Positive control: an empty collection would make the partition check vacuous.
    assert len(full) >= 20, full
    shards = [_collected_nodeids(f"{k}/{total}") for k in range(1, total + 1)]
    seen: set[str] = set()
    for shard in shards:
        assert seen.isdisjoint(shard)
        seen.update(shard)
    assert seen == full

    invalid = _collect("5/4")
    assert invalid.returncode != 0
    assert "5/4" in invalid.stdout + invalid.stderr


@pytest.mark.unit
def test_eight_shards_split_each_four_shard_partition() -> None:
    nodeids = {f"tests/test_x.py::test_{i}[p{i % 7}]" for i in range(2000)}
    for k in range(1, 5):
        before = {nodeid for nodeid in nodeids if shard_of(nodeid, 4) == k}
        split = [
            {nodeid for nodeid in nodeids if shard_of(nodeid, 8) == part} for part in (k, k + 4)
        ]
        assert all(split)
        assert split[0].isdisjoint(split[1])
        assert split[0] | split[1] == before


@pytest.mark.unit
def test_sixteen_shards_split_each_eight_shard_partition() -> None:
    """OMN-20413: shard 4/8 reached 94% at the 10-minute limit; 16 shards halve each of the 8."""
    nodeids = {f"tests/test_x.py::test_{i}[p{i % 7}]" for i in range(2000)}
    for k in range(1, 9):
        before = {nodeid for nodeid in nodeids if shard_of(nodeid, 8) == k}
        split = [
            {nodeid for nodeid in nodeids if shard_of(nodeid, 16) == part} for part in (k, k + 8)
        ]
        assert all(split)
        assert split[0].isdisjoint(split[1])
        assert split[0] | split[1] == before






