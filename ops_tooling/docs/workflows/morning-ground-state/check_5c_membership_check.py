#!/usr/bin/env python3
"""OMN-17170 guard: §5c 'landed in current sprint project?' must be answered by a
live PAGINATED list_issues(project: <successor id>) membership read — never by
the successor project's status/existence, and never by get_project's
resourceCount (which counts attached resources, not issues; confirmed live
2026-08-30: resourceCount:0 on a project holding 369 issues).

Regression: the 2026-08-30 morning-ground-state report asserted 'no ticket has
been moved into it yet' for the successor sprint project based on the project
merely existing/being Planned. A live paginated readback the same day found
369 tickets already in it. Root cause: neither the script prompt
(src/ops_tooling_pkg/nodes/node_morning_ground_state_orchestrator/prompts/briefs.md)
nor the README
format contract
(docs/workflows/morning-ground-state/README.md) mandated a paginated
membership read of the SUCCESSOR project to answer 'landed in current sprint
project? yes/no' -- only the previous-project side was covered.

Fails (RED) until both files carry the explicit successor-membership-read
directive AND the get_project/resourceCount anti-pattern warning.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JS = (
    ROOT
    / "src"
    / "ops_tooling_pkg"
    / "nodes"
    / "node_morning_ground_state_orchestrator"
    / "prompts"
    / "briefs.md"
)
README = ROOT / "docs" / "workflows" / "morning-ground-state" / "README.md"

REQUIRED_README_MARKERS = [
    # must explicitly require a paginated read of the successor/current project
    re.compile(
        r"paginat\w+ (?:read|membership).{0,200}(?:successor|current sprint project)", re.I | re.S
    ),
    re.compile(r"successor|current sprint project", re.I),
    # must explicitly forbid inferring membership from status/existence or resourceCount
    re.compile(r"resourceCount", re.I),
]

REQUIRED_JS_MARKERS = [
    re.compile(r"5c.{0,400}paginat", re.I | re.S),
    re.compile(r"5c.{0,400}(?:successor|current sprint) project", re.I | re.S),
]


def check(path: Path, patterns: list[re.Pattern], label: str) -> list[str]:
    if not path.exists():
        return [f"{label}: file missing: {path}"]
    text = path.read_text()
    failures = []
    for pat in patterns:
        if not pat.search(text):
            failures.append(f"{label}: missing required pattern {pat.pattern!r}")
    return failures


def main() -> int:
    failures = check(README, REQUIRED_README_MARKERS, "README") + check(
        JS, REQUIRED_JS_MARKERS, "morning node briefs"
    )
    if failures:
        print("RED — §5c successor-membership-check guard failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("GREEN — §5c successor-membership-check guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
