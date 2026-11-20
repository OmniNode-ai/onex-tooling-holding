"""Which registry roots the worktree tools scan (OMN-19627, OMN-19628)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from _worktree_git_env import scrubbed_git_env

from ops_tooling_pkg.worktrees.roots import (
    RootsError,
    canonical_clones,
    clone_label,
    resolve_roots,
    root_owning,
)

pytestmark = pytest.mark.unit


def _clone(path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", str(path)], check=True, env=scrubbed_git_env(), capture_output=True
    )
    return path


def test_roots_refuse_without_registry_root() -> None:
    with pytest.raises(RootsError, match="registry_root is not set"):
        resolve_roots({})
    with pytest.raises(RootsError, match="registry_root is not set"):
        resolve_roots({"registry_root": "  "})


def test_roots_are_registry_root_then_ops_tooling_pkg_beside_it(tmp_path: Path) -> None:
    omni = tmp_path / "registry_root"
    omni.mkdir()
    (tmp_path / "ops_tooling_pkg").mkdir()
    roots = resolve_roots({"registry_root": str(omni)})
    assert [r.label for r in roots] == ["registry_root", "ops_tooling_pkg"]
    assert roots[0].worktrees == (omni / "omni_worktrees").resolve()
    assert roots[1].worktrees == (tmp_path / "ops_tooling_pkg" / "omni_worktrees").resolve()


def test_roots_negative_control_no_second_root_when_nothing_is_beside_registry_root(
    tmp_path: Path,
) -> None:
    omni = tmp_path / "registry_root"
    omni.mkdir()
    assert [r.label for r in resolve_roots({"registry_root": str(omni)})] == ["registry_root"]


def test_roots_honour_the_explicit_variables(tmp_path: Path) -> None:
    omni = tmp_path / "registry_root"
    omni.mkdir()
    internal = tmp_path / "elsewhere" / "internal"
    internal.mkdir(parents=True)
    pinned = tmp_path / "pinned"
    roots = resolve_roots(
        {
            "registry_root": str(omni),
            "ONEX_WORKTREES_ROOT": str(pinned),
            "OPS_TOOLING_PKG_HOME": str(internal),
        }
    )
    assert roots[0].worktrees == pinned.resolve()
    assert roots[1].registry == internal.resolve()


def test_roots_refuse_an_explicit_internal_home_that_is_not_a_directory(tmp_path: Path) -> None:
    omni = tmp_path / "registry_root"
    omni.mkdir()
    with pytest.raises(RootsError, match="OPS_TOOLING_PKG_HOME"):
        resolve_roots({"registry_root": str(omni), "OPS_TOOLING_PKG_HOME": str(tmp_path / "no")})


def test_roots_canonical_clones_cover_both_roots_and_the_root_clone_itself(
    tmp_path: Path,
) -> None:
    omni = tmp_path / "registry_root"
    _clone(omni / "omnibase_core")
    (omni / "not_a_clone").mkdir()
    internal = _clone(tmp_path / "ops_tooling_pkg")
    _clone(internal / "omnibase_core")
    roots = resolve_roots({"registry_root": str(omni)})
    found = [clone_label(root, clone) for root, clone in canonical_clones(roots)]
    assert found == [
        "registry_root/omnibase_core",
        "ops_tooling_pkg",
        "ops_tooling_pkg/omnibase_core",
    ]


def test_roots_owning_is_strict_and_per_root(tmp_path: Path) -> None:
    omni = tmp_path / "registry_root"
    omni.mkdir()
    (tmp_path / "ops_tooling_pkg").mkdir()
    roots = resolve_roots({"registry_root": str(omni)})
    inside = (tmp_path / "ops_tooling_pkg" / "omni_worktrees" / "OMN-1" / "x").resolve()
    owner = root_owning(inside, roots)
    assert owner is not None and owner.label == "ops_tooling_pkg"
    assert root_owning(roots[0].worktrees, roots) is None, "a root is not inside itself"
    assert root_owning((tmp_path / "other").resolve(), roots) is None
