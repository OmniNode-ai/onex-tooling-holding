"""Destination-driven freeze of new work (OMN-19998, OMN-21374).

Operator RULING 2026-10-16T07:14:01Z: ops_tooling_pkg should hold no code; it holds data only.
The working-tree destinations config freezes published items and no_code directories against
additions, edits and moves in. Other additions must be non-code files inside data_dirs.
Deletions and moves out pass. Each refusal names the item, its destination and its task.

The `ci` job checks the change's diff; the check-only pre-commit hook checks the staged index.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict, cast

import yaml


class _Owner(TypedDict):
    destination: str
    task: str


class _Unlisted(_Owner):
    item: str


class _NoCode(_Owner):
    prefix: str


class _Item(_Owner):
    id: str
    prefixes: list[str]
    status: Literal["pending", "published", "removed"]


class _Destinations(TypedDict):
    data_dirs: list[str]
    code_suffixes: list[str]
    unlisted: _Unlisted
    no_code: list[str | _NoCode]
    items: list[_Item]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _load_destinations(path: Path) -> _Destinations:
    try:
        loaded = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read destinations {path}: {exc}") from exc
    keys = ("data_dirs", "code_suffixes", "unlisted", "no_code", "items")
    if not isinstance(loaded, dict) or any(key not in loaded for key in keys):
        raise ValueError(f"destinations {path} must declare {', '.join(keys)}")
    return cast(_Destinations, loaded)


def _item_for(path: str, config: _Destinations) -> _Unlisted:
    matches = [
        (prefix, item)
        for item in config["items"]
        for prefix in item["prefixes"]
        if path.startswith(prefix)
    ]
    if not matches:
        return config["unlisted"]
    _, item = max(matches, key=lambda match: len(match[0]))
    return {"item": item["id"], "destination": item["destination"], "task": item["task"]}


def _is_code(repo: Path, path: str, head: str | None, config: _Destinations) -> bool:
    suffix = Path(path).suffix
    if suffix:
        return suffix in config["code_suffixes"]
    # Read bytes from the compared tree or index, never from the working copy.
    blob = subprocess.run(
        ["git", "show", f"{head or ''}:{path}"], cwd=repo, capture_output=True, check=True
    ).stdout
    return blob.startswith(b"#!")


def _offenders(repo: Path, name_status: str, head: str | None, config: _Destinations) -> list[str]:
    """One refusal per path, in diff order, with the first applicable reason."""
    found: list[str] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        kind, path = parts[0][:1], parts[-1]
        if len(parts) < 2 or kind not in {"A", "C", "R", "M", "T"}:
            continue
        owner = _item_for(path, config)
        verb = "moves a file into" if kind == "R" else "edits a file under"
        if kind in {"A", "C"}:
            verb = "adds a file under"
        no_code = [
            entry
            for entry in config["no_code"]
            if path.startswith(entry if isinstance(entry, str) else entry["prefix"])
        ]
        reason: str | None = None
        if no_code:
            entry = max(no_code, key=lambda e: len(e if isinstance(e, str) else e["prefix"]))
            if not isinstance(entry, str):
                owner = {
                    "item": entry["prefix"],
                    "destination": entry["destination"],
                    "task": entry["task"],
                }
            reason = f"{verb} a no_code directory"
        elif any(
            item["status"] == "published" and any(path.startswith(p) for p in item["prefixes"])
            for item in config["items"]
        ):
            reason = f"{verb} a published item"
        elif kind in {"A", "C"}:
            if _is_code(repo, path, head, config):
                reason = "adds a code file"
            elif not any(path.startswith(prefix) for prefix in config["data_dirs"]):
                reason = "adds a file outside the data directories"
        if reason:
            found.append(
                f"{path}: {reason}; item={owner['item']} "
                f"destination={owner['destination']} task={owner['task']}"
            )
    return found


def _check(repo: Path, base: str | None, head: str | None, config: _Destinations) -> list[str]:
    rev = base or "HEAD"
    if head is None:
        listing = _git(repo, "diff", "--cached", "--name-status", "-M", rev)
    else:
        listing = _git(repo, "diff", "--name-status", "-M", rev, head)
    found = _offenders(repo, listing, head, config)
    if head is None and base is None:
        # In a staged merge, keep only refusals also new against the merged-in parent.
        merging = subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if merging.returncode == 0:
            other = merging.stdout.strip()
            listing = _git(repo, "diff", "--cached", "--name-status", "-M", other)
            other_refusals = set(_offenders(repo, listing, head, config))
            found = [line for line in found if line in other_refusals]
    return found


def check(repo: Path, base: str | None, head: str | None) -> list[str]:
    """Refusals for ``base..head``; ``head`` None compares the staged index with ``base``."""
    return _check(repo, base, head, _load_destinations(repo / "config/migration/destinations.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze new work in ops_tooling_pkg (OMN-21374)."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="", help="revision the change is measured against")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--staged", action="store_true", help="check the index against HEAD")
    parser.add_argument(
        "--destinations", type=Path, help="working-tree migration destinations YAML"
    )
    args = parser.parse_args(argv)
    if not args.staged and not args.base:
        print("src freeze: no base revision given; refusing to pass unchecked", file=sys.stderr)
        return 2
    try:
        config = _load_destinations(
            args.destinations or args.repo / "config/migration/destinations.yaml"
        )
        found = _check(args.repo, args.base or None, None if args.staged else args.head, config)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"src freeze: {exc}", file=sys.stderr)
        return 2
    if found:
        print("src freeze (OMN-21374): ops_tooling_pkg takes no new work; it holds data only.")
        for line in found:
            print(f"  {line}")
        return 1
    print("src freeze (OMN-21374): no refused change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
