#!/usr/bin/env python3
"""Port the staged lane-brief skill into an plugin-tooling-pkg worktree, with its version bump.

DRY RUN BY DEFAULT: without --apply it reads and prints, and writes nothing anywhere. It never runs
git add, commit or push, never opens a PR, and never calls a mutating gh verb; its only gh calls
are `gh pr list` and `gh api .../contents` reads.

Why this exists. plugin-tooling-pkg's validate_plugin.py check 5 refuses a change under
plugins/omni/ unless the omni version is above the base's in BOTH plugins/omni/.claude-plugin/
plugin.json and the omni entry of .claude-plugin/marketplace.json: the plugin cache is keyed by
version, so a change on an unchanged version reaches nobody. Other open PRs bump the same two
files, so the right number is only known at port time. This helper reads it then:

  floor  = max(the base's omni version, the omni version on the head of every open PR that
           touches either manifest)
  target = floor with its patch number plus one, unless the worktree already carries a version
           above floor (then it is kept, so a re-run is a no-op)

An open PR whose version is not above the base must re-bump when it rebases; whichever of it and
this port lands second re-bumps above the first. The plan prints that per PR.

--apply (only with --repo-root naming a worktree, never the canonical clone at
$registry_root/plugin-tooling-pkg, which is refused with exit 4):
  1. copies SKILL.md, scripts/ and tests/ of the staged skill into
     plugins/omni/skills/lane-brief/ (this port/ directory and __pycache__ are not copied)
     and its shared rules helper and ledger resolver into plugins/omni/scripts/
  2. writes target into plugin.json and the omni marketplace entry (json, indent 2, as committed)
  3. lists the skill's suite in tests/test_skill_dir_suites.py SUITES, whose coverage test fails
     any skill tests/ directory it does not list

BLOCKER MEASUREMENT (both modes). Before anything is written, the staged suite is RUN the way the
repo's required check runs it: registry_root, ONEX_LEDGER_PATH and LANE_BRIEF_REQUIRE_REGISTRY removed
from the environment, and the readers taken from the target checkout's own
plugins/omni/skills/ledger-msg and ledger-catchup (where they sit as siblings after the port). A
non-zero exit is a BLOCKER: the plan prints it with the suite's tail and exits 3, and --apply writes
nothing. After --apply the ported copy is run once more from its new directory with no reader
override at all (exactly what CI sees); a failure there is also exit 3 (the files stay written and
unstaged, for the porting lane to read).

Usage:
  python3 port/port.py --repo-root <plugin-tooling-pkg worktree> [--base origin/main]
  python3 port/port.py --repo-root <worktree> --apply
  python3 port/port.py --repo-root <dir> --no-gh --open-pr-version 21=0.4.11    (offline plan)

Exit codes: 0 plan printed (and applied with --apply); 2 unreadable input; 3 BLOCKER measured; 4 refused.
Tests: python3 tests/test_port.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = "lane-brief"
PLUGIN = "omni"
PLUGIN_JSON = "plugins/omni/.claude-plugin/plugin.json"
MARKET_JSON = ".claude-plugin/marketplace.json"
MANIFESTS = (PLUGIN_JSON, MARKET_JSON)
SUITES_FILE = "tests/test_skill_dir_suites.py"
SUITE_LINE = f'    "{SKILL}": [[sys.executable, "-B", "tests/test_lane_brief.py"]],'
COPY = ("SKILL.md", "scripts", "tests")
# lane_brief.py imports the rules helper, which imports the ledger resolver.
SHARED_SCRIPTS = ("lane_rules_block.py", "onex_ledger.py")
EXIT_OK, EXIT_INPUT, EXIT_BLOCKER, EXIT_REFUSED = 0, 2, 3, 4
CI_UNSET = (
    "ONEX_LEDGER_PATH",
    "LANE_BRIEF_REQUIRE_REGISTRY",
    "LANE_BRIEF_READER_SKILLS_DIR",
    "LANE_BRIEF_READER_SKILLS_DIR_ONLY",
)


class Fail(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code


def vtuple(v: str) -> tuple[int, ...]:
    core = v.split("-", 1)[0].split("+", 1)[0]
    try:
        return tuple(int(x) for x in core.split("."))
    except ValueError as exc:
        raise Fail(EXIT_INPUT, f"version {v!r} is not dotted numbers") from exc


def bump_patch(v: str) -> str:
    t = list(vtuple(v))
    while len(t) < 3:
        t.append(0)
    t[-1] += 1
    return ".".join(str(x) for x in t)


def git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise Fail(
            EXIT_INPUT, f"git {' '.join(args)} failed in {root}: {out.stderr.strip()}"
        )
    return out.stdout


def market_entry_version(market: dict, name: str) -> str | None:
    for entry in market.get("plugins", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            v = entry.get("version")
            return v if isinstance(v, str) else None
    return None


def base_versions(root: Path, base: str) -> tuple[str, str | None]:
    plugin = json.loads(git(root, "show", f"{base}:{PLUGIN_JSON}"))
    market = json.loads(git(root, "show", f"{base}:{MARKET_JSON}"))
    return plugin["version"], market_entry_version(market, PLUGIN)


def head_versions(root: Path) -> tuple[str, str | None]:
    plugin = json.loads((root / PLUGIN_JSON).read_text(encoding="utf-8"))
    market = json.loads((root / MARKET_JSON).read_text(encoding="utf-8"))
    return plugin["version"], market_entry_version(market, PLUGIN)


def gh_json(args: list[str]) -> object:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise Fail(EXIT_INPUT, f"gh {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def open_pr_versions(repo: str) -> list[tuple[int, str, str]]:
    """(number, head sha, omni version on that head) for each open PR touching a manifest. Read-only."""
    prs = gh_json(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,headRefOid,files",
        ]
    )
    found: list[tuple[int, str, str]] = []
    for pr in prs:  # type: ignore[union-attr]
        paths = {f["path"] for f in pr.get("files") or []}
        if not paths & set(MANIFESTS):
            continue
        sha = pr["headRefOid"]
        blob = gh_json(["api", f"repos/{repo}/contents/{PLUGIN_JSON}?ref={sha}"])
        plugin = json.loads(base64.b64decode(blob["content"]))  # type: ignore[index]
        found.append((int(pr["number"]), sha, str(plugin["version"])))
    return found


def plan(
    base_v: str,
    base_entry: str | None,
    head_v: str,
    head_entry: str | None,
    prs: list[tuple[int, str, str]],
) -> tuple[str, list[str]]:
    lines = [f"base: plugin.json {base_v}, marketplace entry {base_entry}"]
    if base_entry != base_v:
        lines.append(
            f"BLOCKER: the base's two manifests disagree ({base_v} vs {base_entry}); check 1 fails before check 5"
        )
    floor = base_v
    for num, sha, v in prs:
        note = (
            "above base"
            if vtuple(v) > vtuple(base_v)
            else f"NOT above base {base_v}: it must re-bump itself on rebase"
        )
        lines.append(f"open PR #{num} head {sha[:9]} carries {v} ({note})")
        if vtuple(v) > vtuple(floor):
            floor = v
    if vtuple(head_v) > vtuple(floor) and head_entry == head_v:
        target = head_v
        lines.append(
            f"worktree already carries {head_v} in both manifests, above floor {floor}: kept"
        )
    else:
        target = bump_patch(floor)
        lines.append(
            f"floor {floor}; target {target} in plugin.json and the {PLUGIN} marketplace entry"
        )
    if prs:
        lines.append(
            "whichever of this port and each open PR above lands second re-bumps above the first; re-run this plan after every rebase"
        )
    return target, lines


def write_version(root: Path, target: str) -> None:
    p = root / PLUGIN_JSON
    plugin = json.loads(p.read_text(encoding="utf-8"))
    plugin["version"] = target
    p.write_text(json.dumps(plugin, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = root / MARKET_JSON
    market = json.loads(m.read_text(encoding="utf-8"))
    hits = [
        e
        for e in market.get("plugins", [])
        if isinstance(e, dict) and e.get("name") == PLUGIN
    ]
    if len(hits) != 1:
        raise Fail(
            EXIT_INPUT,
            f"{MARKET_JSON} has {len(hits)} entries named {PLUGIN!r}, expected 1",
        )
    hits[0]["version"] = target
    m.write_text(json.dumps(market, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def suites_with_entry(text: str) -> tuple[str, bool]:
    """Return (text with SKILL listed in SUITES in sorted key order, whether it changed)."""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("SUITES")), None)
    if start is None:
        raise Fail(EXIT_INPUT, f"{SUITES_FILE} has no SUITES dict")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("}")), None
    )
    if end is None:
        raise Fail(EXIT_INPUT, f"{SUITES_FILE} SUITES dict is not closed")
    key_re = re.compile(r'^    "([^"]+)":')
    keys = [
        (i, m.group(1)) for i in range(start + 1, end) if (m := key_re.match(lines[i]))
    ]
    if any(k == SKILL for _, k in keys):
        return text, False
    at = next((i for i, k in keys if k > SKILL), end)
    lines.insert(at, SUITE_LINE + "\n")
    return "".join(lines), True


def copy_skill(src: Path, dest: Path) -> list[str]:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in COPY:
        s, d = src / name, dest / name
        if s.is_dir():
            if d.exists():
                shutil.rmtree(d)
            shutil.copytree(s, d, ignore=ignore)
        else:
            shutil.copy2(s, d)
        copied.append(name)
    # These imports sit outside the skill directory. Carry them with the port so
    # the installed skill also runs in a checkout without the registry root.
    (dest.parents[1] / "scripts").mkdir(parents=True, exist_ok=True)
    for name in SHARED_SCRIPTS:
        shutil.copy2(src.parents[1] / "scripts" / name, dest.parents[1] / "scripts" / name)
        copied.append(f"plugin scripts/{name}")
    # lane_brief.py reads its line rules from this node (OMN-19998); the ported copy needs it beside the plugin.
    for node in (Path("src/plugin_tooling_pkg/nodes") / name for name in ("node_release_plan_guard_compute", "node_cause_fix_guard_compute")):
        if (src.parents[3] / node).is_dir():
            shutil.copytree(src.parents[3] / node, dest.parents[3] / node, dirs_exist_ok=True, ignore=ignore)
            copied.append(f"node {node.name}")
    return copied


def run_suite(skill_dir: Path, readers: Path | None) -> tuple[int, str]:
    """Run tests/test_lane_brief.py from skill_dir with the CI environment (no registry root)."""
    env = {k: v for k, v in os.environ.items() if k not in CI_UNSET}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if readers is not None:
        env["LANE_BRIEF_READER_SKILLS_DIR"] = str(readers)
        env["LANE_BRIEF_READER_SKILLS_DIR_ONLY"] = "1"
    out = subprocess.run(
        [sys.executable, "-B", "tests/test_lane_brief.py"],
        cwd=skill_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    return out.returncode, (out.stdout + out.stderr)[-1500:]


def blockers(root: Path, skill_src: Path) -> list[str]:
    readers = root / "plugins" / PLUGIN / "skills"
    rc, tail = run_suite(skill_src, readers)
    if rc == 0:
        return [
            f"suite: the staged tests/test_lane_brief.py passes with no registry root and the readers of {root.name} (rc=0)"
        ]
    return [
        f"BLOCKER: the staged tests/test_lane_brief.py exits {rc} with no registry root and the readers "
        f"of {root.name}, which is how this repo's required check would run it once SUITES lists it; "
        f"fix the staged suite and re-run the plan. Suite tail:\n{tail}"
    ]


def refuse_canonical(root: Path) -> None:
    home = os.environ.get("registry_root", "").strip()
    if home and root.resolve() == (Path(home) / "plugin-tooling-pkg").resolve():
        raise Fail(
            EXIT_REFUSED,
            "REFUSED: --repo-root is the canonical clone; apply only in a worktree under omni_worktrees",
        )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--repo-root",
        required=True,
        help="an plugin-tooling-pkg checkout (a worktree for --apply)",
    )
    ap.add_argument(
        "--base",
        default="origin/main",
        help="the ref check 5 compares against (default origin/main)",
    )
    ap.add_argument(
        "--repo",
        default="OmniNode-ai/plugin-tooling-pkg",
        help="GitHub repo whose open PRs are read",
    )
    ap.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="the staged skill directory",
    )
    ap.add_argument(
        "--no-gh", action="store_true", help="do not read open PRs (the plan says so)"
    )
    ap.add_argument(
        "--open-pr-version",
        action="append",
        default=[],
        metavar="N=VERSION",
        help="an open PR's omni version, given instead of read (repeatable; implies no gh read for it)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write the copy, the bump and the SUITES entry",
    )
    a = ap.parse_args(argv)
    try:
        root = Path(a.repo_root)
        if not (root / PLUGIN_JSON).is_file() or not (root / MARKET_JSON).is_file():
            raise Fail(
                EXIT_INPUT,
                f"{root} is not an plugin-tooling-pkg checkout (no {PLUGIN_JSON} or {MARKET_JSON})",
            )
        src = Path(a.skill_dir)
        if not (src / "SKILL.md").is_file():
            raise Fail(EXIT_INPUT, f"{src} holds no SKILL.md")
        if a.apply:
            refuse_canonical(root)
        base_v, base_entry = base_versions(root, a.base)
        head_v, head_entry = head_versions(root)
        prs: list[tuple[int, str, str]] = []
        for item in a.open_pr_version:
            num, _, ver = item.partition("=")
            if not num.isdigit() or not ver:
                raise Fail(EXIT_INPUT, f"--open-pr-version {item!r} is not N=VERSION")
            prs.append((int(num), "given", ver))
        if not a.no_gh and not a.open_pr_version:
            prs = open_pr_versions(a.repo)
        target, lines = plan(base_v, base_entry, head_v, head_entry, prs)
        if a.no_gh and not a.open_pr_version:
            lines.append(
                "UNVERIFIED: open PRs were not read (--no-gh); re-run with gh before the port PR"
            )
        found = blockers(root, src)
        lines += found
        blocked = any(x.startswith("BLOCKER") for x in lines)
        print(
            f"lane-brief port plan ({'APPLY' if a.apply else 'DRY RUN, nothing written'}) against {a.base}"
        )
        print("\n".join(lines))
        suites_path = root / SUITES_FILE
        new_suites, suites_change = suites_with_entry(
            suites_path.read_text(encoding="utf-8")
        )
        print(
            f"{SUITES_FILE}: {'add ' + SUITE_LINE.strip() if suites_change else 'already lists ' + SKILL}"
        )
        if blocked:
            print(
                "BLOCKED: nothing written"
                if a.apply
                else "BLOCKED: an --apply would write nothing"
            )
            return EXIT_BLOCKER
        if not a.apply:
            return EXIT_OK
        dest = root / "plugins" / PLUGIN / "skills" / SKILL
        copied = copy_skill(src, dest)
        write_version(root, target)
        if suites_change:
            suites_path.write_text(new_suites, encoding="utf-8")
        print(
            f"applied: copied {', '.join(copied)} to {dest.relative_to(root)}; version {target}; nothing staged or committed"
        )
        rc, tail = run_suite(dest, None)
        if rc != 0:
            print(
                f"BLOCKER: the ported suite exits {rc} from {dest.relative_to(root)} with no reader override "
                f"and no registry root (what CI sees); files are written and unstaged. Suite tail:\n{tail}"
            )
            return EXIT_BLOCKER
        print(
            f"post-apply: the ported suite passes from {dest.relative_to(root)} as CI runs it (rc=0)"
        )
        return EXIT_OK
    except Fail as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
