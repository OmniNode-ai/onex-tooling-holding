# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT

"""Parity of the canonical-clone git hook family with the behaviour recorded from the shell
scripts it replaced (OMN-20684).

The commit/push guard, the reference-transaction guard and the shared position library were
three shell scripts. OMN-20684 turns them into one declared node behind one hook shim. This
file is the proof that nothing the hooks decided changed: every scenario below drives the
installed hook directly (the same entry git runs) with the stdin and arguments git hands it,
and the outcome (exit code, stderr, refusal log, marker, chained command, resulting ref and
tree state) is compared with ``golden/canonical_clone_guard_parity.json``, which was recorded
from the shell scripts at commit cc1e1a28 before they were deleted.

The golden was recorded and shown green on the unchanged shell scripts first. Re-record from any
hook directory with::

    uv run python tests/test_canonical_clone_guard_parity.py --record <git-hooks dir>

The end-to-end git behaviour (a real ``git commit``, ``checkout``, ``update-ref``) is pinned
separately by ``test_canonical_clone_ref_guard.py`` and its neighbours.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from _git_env import scrub_git_location_env

REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_HOOKS = REPO_ROOT / "src/ops_tooling_pkg/handlers/canonical_clone" / "git-hooks"
GOLDEN = Path(__file__).parent / "characterization" / "golden" / "canonical_clone_guard_parity.json"

ZERO = "0" * 40
CONSENT_ROW = "2026-09-16T00:00:00Z | OPERATOR-CONSENT | lane=test | scope=branch-delete"


@dataclass
class World:
    """A throwaway registry with the hook family installed the way a host installs it."""

    root: Path
    live_dir: Path
    registry: Path
    clone: Path
    worktree: Path
    shas: dict[str, str]
    marks: dict[str, Path] = field(default_factory=dict)

    @property
    def hooks_dir(self) -> Path:
        return self.live_dir / "canonical-clone"


def _env(world_root: Path, overrides: Mapping[str, str | None]) -> dict[str, str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(world_root),
        "USER": "paritytest",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "OMN-20684 Test",
        "GIT_AUTHOR_EMAIL": "person@example.com",
        "GIT_COMMITTER_NAME": "OMN-20684 Test",
        "GIT_COMMITTER_EMAIL": "person@example.com",
    }
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return scrub_git_location_env(env)


def _git(
    world_root: Path, cwd: Path, *args: str, env: Mapping[str, str | None] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_env(world_root, env or {}),
        capture_output=True,
        text=True,
        check=False,
    )


def _must(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def build_world(tmp: Path, source_hooks: Path) -> World:
    """Install ``source_hooks`` as the live family beside a fixture registry."""
    root = tmp.resolve()
    owner = root / "ops_tooling_pkg"
    live_dir = owner / "scripts" / "git-hooks"
    live_dir.parent.mkdir(parents=True)
    shutil.copytree(source_hooks, live_dir, symlinks=True)
    # The live layout: the package the hook shim imports sits at <owner>/src.
    (owner / "src").symlink_to(REPO_ROOT / "src")

    registry = root / "registry_root"
    (registry / "omni_worktrees").mkdir(parents=True)
    clone = registry / "some_repo"
    clone.mkdir()
    _must(_git(root, clone, "init", "-q", "-b", "dev"))

    def commit(name: str) -> str:
        (clone / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
        _must(_git(root, clone, "add", f"{name}.txt"))
        _must(_git(root, clone, "commit", "-q", "-m", name))
        return _must(_git(root, clone, "rev-parse", "HEAD"))

    c1 = commit("one")
    _must(_git(root, clone, "checkout", "-q", "-b", "side"))
    c3 = commit("side")
    _must(_git(root, clone, "checkout", "-q", "dev"))
    c2 = commit("two")
    _must(_git(root, clone, "branch", "old", c1))
    worktree = registry / "omni_worktrees" / "OMN-20684" / "some_repo"
    _must(_git(root, clone, "worktree", "add", "-q", "-b", "wt-branch", str(worktree), c2))
    _must(_git(root, clone, "config", "core.hooksPath", str(live_dir / "canonical-clone")))
    return World(
        root=root,
        live_dir=live_dir,
        registry=registry,
        clone=clone,
        worktree=worktree,
        shas={"c1": c1, "c2": c2, "c3": c3},
    )


Step = tuple[object, ...]


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[Step, ...]
    # Called with the world before the steps run; returns the cwd key -> path table additions.
    setup: Callable[[World], None] | None = None


def hook(
    name: str,
    *args: str,
    cwd: str = "clone",
    stdin: str = "",
    env: Mapping[str, str | None] | None = None,
) -> Step:
    return ("hook", name, tuple(args), cwd, stdin, dict(env or {}))


def git_step(*args: str, cwd: str = "clone") -> Step:
    return ("git", tuple(args), cwd)


def write_step(where: str, relpath: str, content: str) -> Step:
    return ("write", where, relpath, content)


def _consent_file(world: World) -> None:
    (world.registry / "ledger.md").write_text(f"first\n{CONSENT_ROW}\nthird\n", encoding="utf-8")


def _sentinel_hook(exit_code: int, hook_type: str = "pre-commit") -> Callable[[World], None]:
    def setup(world: World) -> None:
        hooks = world.clone / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        path = hooks / hook_type
        path.write_text(
            '#!/usr/bin/env bash\nprintf "%s|" "$@" > "$SENTINEL"\nexit ' + str(exit_code) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    return setup


def _fake_precommit(world: World) -> None:
    bin_dir = world.root / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "pre-commit"
    fake.write_text(
        '#!/usr/bin/env bash\nprintf "%s|" "$@" > "$SENTINEL"\nexit 7\n', encoding="utf-8"
    )
    fake.chmod(0o755)
    world.marks["bin"] = bin_dir


def _stray_clone(world: World) -> None:
    stray = world.root / "elsewhere" / "stray"
    stray.mkdir(parents=True)
    _must(_git(world.root, stray, "init", "-q", "-b", "dev"))
    (stray / "a.txt").write_text("a\n", encoding="utf-8")
    _must(_git(world.root, stray, "add", "a.txt"))
    _must(_git(world.root, stray, "commit", "-q", "-m", "a"))
    _must(_git(world.root, stray, "config", "core.hooksPath", str(world.hooks_dir)))
    world.marks["stray"] = stray
    plain = world.root / "plain"
    plain.mkdir()
    world.marks["plain"] = plain


def _stray_with_roots_file(world: World) -> None:
    _stray_clone(world)
    (world.live_dir / "registry-roots").write_text(
        f"registry_root={world.registry}\nroot={world.registry}\nroot={world.root / 'elsewhere'}\n",
        encoding="utf-8",
    )


def _stray_with_bad_roots_file(world: World) -> None:
    _stray_clone(world)
    (world.live_dir / "registry-roots").write_text("garbage line\n", encoding="utf-8")


def _initializing_worktree(world: World) -> None:
    (world.clone / ".git" / "worktrees" / "half-made").mkdir()


def _half_applied_checkout(world: World) -> None:
    # What git leaves behind when the HEAD transaction of `checkout side` is refused: the index
    # and tree already hold `side` while HEAD is still `dev`.
    _must(_git(world.root, world.clone, "read-tree", "-u", "--reset", "side"))


def _half_applied_with_local_edit(world: World) -> None:
    _half_applied_checkout(world)
    (world.clone / "side.txt").write_text("edited after checkout\n", encoding="utf-8")


SWITCH_LINE = ZERO + " ref:refs/heads/side HEAD\n"


def _tx(*lines: str) -> str:
    return "".join(f"{line}\n" for line in lines)




_SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", re.MULTILINE)
_ACTOR_RE = re.compile(r"actor=.*$", re.MULTILINE)


def _normalise(text: str, world: World) -> str:
    out = text.replace(str(world.root), "<ROOT>")
    for label, sha in world.shas.items():
        out = out.replace(sha, f"<{label}>").replace(sha[:12], f"<{label}:12>")
    out = _TS_RE.sub("<ts>", out)
    return _ACTOR_RE.sub("actor=<actor>", out)


def _expand(value: str, world: World) -> str:
    return (
        value.replace("@root", str(world.root))
        .replace("@registry", str(world.registry))
        .replace("@bin", str(world.marks.get("bin", "")))
        .replace("@path", os.environ["PATH"])
    )


def _where(world: World, key: str) -> Path:
    return {
        "clone": world.clone,
        "worktree": world.worktree,
        "root": world.root,
        "stray": world.marks.get("stray", world.root),
        "plain": world.marks.get("plain", world.root),
    }[key]


def run_scenario(scenario: Scenario, source_hooks: Path) -> list[object]:
    with tempfile.TemporaryDirectory(prefix="omn20684-parity-") as tmp:
        world = build_world(Path(tmp), source_hooks)
        if scenario.setup is not None:
            scenario.setup(world)
        results: list[object] = []
        for step in scenario.steps:
            kind = step[0]
            if kind == "hook":
                _, name, args, cwd_key, stdin, overrides = step
                assert isinstance(name, str) and isinstance(args, tuple)
                assert isinstance(cwd_key, str) and isinstance(stdin, str)
                assert isinstance(overrides, dict)
                env_overrides: dict[str, str | None] = {"registry_root": str(world.registry)}
                for key, value in overrides.items():
                    env_overrides[key] = None if value is None else _expand(value, world)
                stdin_text = stdin
                for label, sha in world.shas.items():
                    stdin_text = stdin_text.replace("{" + label + "}", sha)
                done = subprocess.run(
                    [str(world.hooks_dir / name), *args],
                    cwd=_where(world, cwd_key),
                    env=_env(world.root, env_overrides),
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                results.append(
                    {
                        "hook": f"{name} {' '.join(args)}".strip(),
                        "rc": done.returncode,
                        "stdout": _normalise(done.stdout, world),
                        "stderr": _normalise(done.stderr, world),
                    }
                )
            elif kind == "git":
                _, git_args, cwd_key = step
                assert isinstance(git_args, tuple) and isinstance(cwd_key, str)
                done = _git(world.root, _where(world, cwd_key), *git_args)
                results.append({"git": " ".join(git_args), "out": _normalise(done.stdout, world)})
            elif kind == "write":
                _, where, rel, content = step
                assert isinstance(where, str) and isinstance(rel, str) and isinstance(content, str)
                (_where(world, where) / rel).write_text(content, encoding="utf-8")
            elif kind == "read":
                _, where, rel = step
                assert isinstance(where, str) and isinstance(rel, str)
                target = _where(world, where) / rel
                text = target.read_text(encoding="utf-8") if target.exists() else None
                results.append({"read": rel, "content": text and _normalise(text, world)})
            elif kind == "exists":
                _, where, rel = step
                assert isinstance(where, str) and isinstance(rel, str)
                results.append({"exists": rel, "value": (_where(world, where) / rel).exists()})
        results.append(_final_state(world))
        return results


def _final_state(world: World) -> dict[str, object]:
    log = world.clone / ".git" / "onex-canonical-clone-refusals.log"
    refs = _git(world.root, world.clone, "for-each-ref", "--format=%(refname) %(objectname)")
    return {
        "refusal_log": _normalise(log.read_text(encoding="utf-8"), world) if log.exists() else None,
        "refs": _normalise(refs.stdout, world),
        "head": _normalise(
            _git(world.root, world.clone, "symbolic-ref", "-q", "HEAD").stdout, world
        ),
        "status": _git(world.root, world.clone, "status", "--porcelain=v1").stdout,
    }




def _golden() -> dict[str, list[object]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data










