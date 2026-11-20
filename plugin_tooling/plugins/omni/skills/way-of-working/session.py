#!/usr/bin/env python3
"""Session files and session rows for /omni:way-of-working.

This script never opens the rolling ledger and never appends to it. It builds the three rows the
skill owns (the session CLAIM, a checkpoint STATUS, the session TERMINAL) and prints them, so the
skill's one ## Ledger block appends them. It also writes and reads the session's own scratch files
(session.env and lanes.txt), reads a preflight receipt for the host mode, and reads the output of
the ledger-catchup digest (never the ledger) to say which of this session's lanes still hold an
open CLAIM.

Subcommands:
  name PURPOSE                     print a session lane name, <purpose>-<4 hex>
  init --lane L --claim-ts TS --ticket OMN-n --host-mode M [--dry-run] [--root DIR]
                                   write <root>/<lane>/session.env (with registry_root as it stands)
                                   and an empty lanes.txt; print SESSION_ENV=<absolute path>
  show --lane L [--root DIR]       print session.env
  lanes --lane L [--state S] [--root DIR]
                                   print the lane names in lanes.txt, optionally one state only
  host-mode --receipt FILE         print coordination, detached or unknown from a preflight receipt
  claim-row | status-row | terminal-row ...
                                   print one ledger row (see each subcommand's --help)
  boundary --lane L [--root DIR]   read the catchup digest on stdin; print OPEN or NOT-OPEN per lane
  relaunch-brief --lane L --new-lane N --dead-lane D --dead-claim TS --t0 TS
                 --claim-template LINE --scope TEXT [--dry-run] [--root DIR]
                                   write <root>/<lane>/briefs/<N>.md, the relaunch brief for a dead
                                   lane (read-back-before-act opening, the pr-handoff sentence, the
                                   CLAIM template session-resume composed); print BRIEF=<path>.
                                   LINE is the output of session-resume's relaunch_claim.py
                                   --claim-only; its default two-line output is also accepted and
                                   reduced to its one CLAIM line

The default root is $registry_root/.claude_scratch/sessions (registry_root is required, no default).
--dry-run on init and relaunch-brief prints what it would write and writes nothing. Every other
subcommand is read-only.

lanes.txt format: one lane per line, "<lane> <state> [<ticket>]", '#' comments allowed. States:
dispatched, handed-off, terminal. fan-out appends dispatched lanes; a lane that handed its PR to
the landing lane is marked handed-off.

Exit codes: 0 ok; 2 bad input or refused; 3 init refused because session.env already exists, or
relaunch-brief refused because that brief already exists.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import sys
from pathlib import Path

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]*$")
TICKET_RE = re.compile(r"^OMN-\d+$")
PURPOSE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
PLACEHOLDERS = {"", "-", "--", ".", "?", "n/a", "na", "nil", "none", "nothing", "tbd", "unknown"}
HOST_MODES = ("coordination", "detached", "unknown")
LANE_STATES = ("dispatched", "handed-off", "terminal")
CATCHUP_OPEN_HEADER = re.compile(r"^1\. Open CLAIMs in the window")
CATCHUP_NEXT_HEADER = re.compile(r"^[2-9]\. ")
CATCHUP_OPEN_ROW = re.compile(r"^\s+\d+: (\S+)\s*$")
CATCHUP_TRUNCATED = re.compile(r"^\s+\.\.\. \d+ older rows in this section not shown")


class Refused(Exception):
    pass


def _root(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    home = os.environ.get("registry_root")
    if not home:
        raise Refused("registry_root is not set (no default: set it to the registry root)")
    return Path(home) / ".claude_scratch" / "sessions"


def _cell(name: str, value: str) -> str:
    """A value that goes into one pipe cell: no pipe, no newline."""
    if "|" in value or "\n" in value:
        raise Refused(f"{name} may not contain '|' or a newline: {value!r}")
    return value.strip()


def _token(name: str, value: str) -> str:
    if not TOKEN_RE.match(value or ""):
        raise Refused(f"{name} must be one token ([A-Za-z0-9._:/#-]), got {value!r}")
    return value


def _ts(value: str) -> str:
    if not TS_RE.match(value or ""):
        raise Refused(f"--ts must be a UTC stamp like 2026-09-24T15:00:00Z, got {value!r}")
    return value


def _ticket(value: str) -> str:
    if not TICKET_RE.match(value or ""):
        raise Refused(f"--ticket must be OMN-<digits>, got {value!r}")
    return value


def _not_placeholder(name: str, value: str) -> str:
    if (value or "").strip().lower() in PLACEHOLDERS:
        raise Refused(f"{name} records nothing ({value!r}); name the real value")
    return value


def _kv(pairs: list[str]) -> list[str]:
    out = []
    for pair in pairs or []:
        key, sep, val = pair.partition("=")
        if not sep or not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", key):
            raise Refused(f"--kv takes key=value, got {pair!r}")
        out.append(f"{key}={_cell(key, val)}")
    return out


# --------------------------------------------------------------------------- rows


def claim_row(a: argparse.Namespace) -> str:
    lane = _token("--lane", a.lane)
    ticket = _ticket(a.ticket)
    actor = _token("--actor", _not_placeholder("--actor", a.actor))
    if a.est_hours <= 0:
        raise Refused("--est-hours must be above zero")
    displaces = _not_placeholder("--displaces", _cell("--displaces", a.displaces))
    cells = [_ts(a.ts), "CLAIM", f"lane={lane}", f"actor={actor}"]
    if a.model:
        cells.append(f"model={_token('--model', a.model)}")
    cells.append(f"ticket={ticket}")
    if a.scope:
        cells.append(f"scope={_cell('--scope', a.scope)}")
    kv = _kv(a.kv)
    # A session lane owns no worktree of its own; the ledger wants the cell said (OMN-20148).
    if not any(c.startswith("worktree=") for c in kv):
        kv.append("worktree=none")
    cells += kv
    hours = f"{a.est_hours:g}"
    cells.append(f"est ~{hours} lane-hours; displaces {displaces}; ({ticket})")
    cells.append(_cell("--text", a.text))
    return " | ".join(cells)


def status_row(a: argparse.Namespace) -> str:
    cells = [_ts(a.ts), "STATUS", f"lane={_token('--lane', a.lane)}"]
    if a.ticket:
        cells.append(f"ticket={_ticket(a.ticket)}")
    if a.t0:
        cells.append(f"T0={_ts(a.t0)}")
    cells += _kv(a.kv)
    cells.append(_cell("--text", a.text))
    return " | ".join(cells)


def terminal_row(a: argparse.Namespace) -> str:
    friction = _cell("--friction", a.friction)
    if not friction:
        raise Refused("--friction is required: 'none', or one line naming this lane's FRICTION rows")
    cells = [_ts(a.ts), "TERMINAL", f"lane={_token('--lane', a.lane)}"]
    if a.ticket:
        cells.append(f"ticket={_ticket(a.ticket)}")
    if a.closes_claim:
        cells.append(f"closes-CLAIM={_ts(a.closes_claim)}")
    if a.outcome:
        cells.append(f"outcome={_token('--outcome', a.outcome)}")
    cells.append(f"friction={friction}")
    cells += _kv(a.kv)
    cells.append(_cell("--text", a.text))
    return " | ".join(cells)


# --------------------------------------------------------------------------- files


def cmd_name(a: argparse.Namespace) -> int:
    if not PURPOSE_RE.match(a.purpose):
        raise Refused(f"PURPOSE must be lowercase words joined by '-', got {a.purpose!r}")
    print(f"{a.purpose}-{secrets.token_hex(2)}")
    return 0


def cmd_init(a: argparse.Namespace) -> int:
    lane = _token("--lane", a.lane)
    env = {
        "SESSION_LANE": lane,
        "CLAIM_TS": _ts(a.claim_ts),
        "GOAL_TICKET": _ticket(a.ticket),
        "HOST_MODE": a.host_mode,
    }
    # The registry root as it stood at init. A later block sources session.env to get it back,
    # because the shell profile of each tool call can reset registry_root (seen in the round-1 dry run).
    if os.environ.get("registry_root"):
        env["registry_root"] = _cell("registry_root", str(Path(os.environ["registry_root"]).resolve()))
    folder = _root(a.root) / lane
    body = "".join(f"{k}={v}\n" for k, v in env.items())
    lanes = "# <lane> <state: dispatched|handed-off|terminal> [<ticket>]\n"
    if a.dry_run:
        print(f"DRY-RUN would write {folder / 'session.env'}:")
        print(body, end="")
        print(f"DRY-RUN would write {folder / 'lanes.txt'} (header only)")
        return 0
    if (folder / "session.env").exists():
        print(f"REFUSED: {folder / 'session.env'} exists; pick a new session lane name", file=sys.stderr)
        return 3
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "session.env").write_text(body, encoding="utf-8")
    if not (folder / "lanes.txt").exists():
        (folder / "lanes.txt").write_text(lanes, encoding="utf-8")
    print(f"wrote {folder / 'lanes.txt'}")
    print(f"SESSION_ENV={(folder / 'session.env').resolve()}")
    return 0


def _read_lanes(folder: Path) -> list[tuple[str, str]]:
    path = folder / "lanes.txt"
    if not path.is_file():
        raise Refused(f"{path} is missing; run init first (way-of-working step 2)")
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        state = parts[1] if len(parts) > 1 else "dispatched"
        if state not in LANE_STATES:
            raise Refused(f"{path}: unknown state {state!r} for lane {parts[0]!r}")
        rows.append((parts[0], state))
    return rows


def cmd_show(a: argparse.Namespace) -> int:
    path = _root(a.root) / _token("--lane", a.lane) / "session.env"
    if not path.is_file():
        raise Refused(f"{path} is missing; run way-of-working step 2 first")
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_lanes(a: argparse.Namespace) -> int:
    for lane, state in _read_lanes(_root(a.root) / _token("--lane", a.lane)):
        if a.state is None or a.state == state:
            print(lane)
    return 0


def cmd_host_mode(a: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"cannot read preflight receipt {a.receipt}: {exc}") from exc
    for check in data.get("checks") or []:
        if check.get("check_id") == "coordination_host":
            print("coordination" if check.get("ok") else "detached")
            return 0
    print("unknown")
    return 0


def cmd_boundary(a: argparse.Namespace) -> int:
    lanes = _read_lanes(_root(a.root) / _token("--lane", a.lane))
    open_lanes: set[str] = set()
    in_section = seen_header = False
    for line in sys.stdin.read().splitlines():
        if CATCHUP_OPEN_HEADER.match(line):
            in_section = seen_header = True
            continue
        if in_section and CATCHUP_NEXT_HEADER.match(line):
            in_section = False
        if not in_section:
            continue
        if CATCHUP_TRUNCATED.match(line):
            raise Refused("catchup truncated the open-CLAIM list; rerun it with a larger CATCHUP_CAP")
        m = CATCHUP_OPEN_ROW.match(line)
        if m:
            open_lanes.add(m.group(1))
    if not seen_header:
        raise Refused("stdin carries no catchup section 1; pipe the ledger-catchup digest in")
    for lane, state in lanes:
        verdict = "OPEN" if lane in open_lanes else "NOT-OPEN"
        print(f"{verdict} {lane} (lanes.txt state={state})")
    if a.lane in open_lanes:
        print(f"OPEN {a.lane} (the session CLAIM itself; closed by the session TERMINAL)")
    return 0


CLAIM_CELL = re.compile(r"\|\s*CLAIM\s*\|")


def claim_line(value: str) -> str:
    """The one CLAIM line of --claim-template. session-resume step 4 prints it alone with
    relaunch_claim.py --claim-only; a pasted multi-line block (its default output: a ROUTE line,
    maybe a WARN line, then the CLAIM line) is reduced to its one CLAIM line. Zero or several
    CLAIM lines are refused, never guessed."""
    lines = [ln.strip() for ln in value.strip().splitlines() if ln.strip()]
    if len(lines) <= 1:
        return lines[0] if lines else ""
    claims = [ln for ln in lines if CLAIM_CELL.search(ln)]
    if len(claims) != 1:
        raise Refused(f"--claim-template carries {len(claims)} CLAIM lines in {len(lines)} lines; pass the one "
                      "CLAIM line session-resume step 4 printed (relaunch_claim.py --claim-only)")
    return claims[0]


def relaunch_brief(a: argparse.Namespace) -> str:
    lane = _token("--lane", a.lane)
    new = _token("--new-lane", a.new_lane)
    dead = _token("--dead-lane", a.dead_lane)
    dead_claim = _ts(a.dead_claim)
    t0 = _ts(a.t0)
    template = claim_line(a.claim_template or "")
    scope = _not_placeholder("--scope", _cell("--scope", a.scope))
    if not re.search(r"\|\s*CLAIM\s*\|", template):
        raise Refused("--claim-template is not a CLAIM row; paste the line session-resume step 4 printed")
    if not re.search(rf"\|\s*lane={re.escape(new)}\s*(\||$)", template):
        raise Refused(f"--claim-template does not carry lane={new}")
    if not re.search(rf"\|\s*parent={re.escape(lane)}\s*(\||$)", template):
        raise Refused(f"--claim-template does not carry parent={lane} (the resuming session lane)")
    if f"supersedes-claim={dead_claim}" not in template:
        raise Refused(f"--claim-template does not carry supersedes-claim={dead_claim}")
    spec = importlib.util.spec_from_file_location(
        "lane_brief_for_relaunch", Path(__file__).resolve().parents[1] / "lane-brief/scripts/lane_brief.py"
    )
    assert spec and spec.loader
    lb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lb)
    ticket = re.search(r"\|\s*ticket=(OMN-[0-9]+)\b", template)
    contract = lb.contract_block(ticket.group(1) if ticket else "OMN-<ticket>")
    return (
        f"# Relaunch brief: {new}\n\n"
        f"You are resuming a lane killed at {t0}. Before any write, re-read the PR head, the worktree "
        f"and the ledger rows of the old lane ({dead}, CLAIM {dead_claim}), and report what you found. "
        "Never replay the old brief's steps blindly: the work may have moved.\n\n"
        f"Scope: {scope}\n\n"
        f"{contract}\n\n"
        "When your PR is ready, hand it to the landing lane with /omni:pr-handoff and stop; never "
        "merge, arm, rerun or poll CI.\n\n"
        "Your CLAIM, which you append yourself before your first write (replace <ts> with the time "
        "you append it):\n\n"
        f"{template}\n"
    )


def cmd_relaunch_brief(a: argparse.Namespace) -> int:
    body = relaunch_brief(a)
    path = _root(a.root) / a.lane / "briefs" / f"{a.new_lane}.md"
    if a.dry_run:
        print(f"DRY-RUN would write {path}:")
        print(body, end="")
        return 0
    if path.exists():
        print(f"REFUSED: {path} exists; a second relaunch is <dead lane>-r2", file=sys.stderr)
        return 3
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    print(f"BRIEF={path.resolve()}")
    return 0


# --------------------------------------------------------------------------- cli


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=__doc__.split("\n\n", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("name", help="print <purpose>-<4 hex>")
    s.add_argument("purpose")
    s.set_defaults(fn=cmd_name)

    s = sub.add_parser("init", help="write session.env and lanes.txt")
    s.add_argument("--lane", required=True)
    s.add_argument("--claim-ts", required=True)
    s.add_argument("--ticket", required=True)
    s.add_argument("--host-mode", required=True, choices=HOST_MODES)
    s.add_argument("--root")
    s.add_argument("--dry-run", action="store_true", help="print, write nothing")
    s.set_defaults(fn=cmd_init)

    for name, fn in (("show", cmd_show), ("lanes", cmd_lanes), ("boundary", cmd_boundary)):
        s = sub.add_parser(name)
        s.add_argument("--lane", required=True, help="the session lane")
        s.add_argument("--root")
        if name == "lanes":
            s.add_argument("--state", choices=LANE_STATES)
        s.set_defaults(fn=fn)

    s = sub.add_parser("host-mode", help="read coordination_host from a preflight receipt")
    s.add_argument("--receipt", required=True)
    s.set_defaults(fn=cmd_host_mode)

    s = sub.add_parser("claim-row", help="print the session CLAIM row")
    s.add_argument("--ts", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--ticket", required=True)
    s.add_argument("--actor", required=True, help="who runs it, e.g. claude:<model>:foreground")
    s.add_argument("--model")
    s.add_argument("--scope")
    s.add_argument("--est-hours", type=float, required=True)
    s.add_argument("--displaces", required=True)
    s.add_argument("--kv", action="append", default=[], help="extra key=value cell")
    s.add_argument("--text", required=True)
    s.set_defaults(fn=lambda a: print(claim_row(a)) or 0)

    s = sub.add_parser("status-row", help="print a checkpoint STATUS row")
    s.add_argument("--ts", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--ticket")
    s.add_argument("--t0", help="outage time, on a resume STATUS")
    s.add_argument("--kv", action="append", default=[])
    s.add_argument("--text", required=True)
    s.set_defaults(fn=lambda a: print(status_row(a)) or 0)

    s = sub.add_parser("terminal-row", help="print the session TERMINAL row")
    s.add_argument("--ts", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--ticket")
    s.add_argument("--closes-claim", help="the session CLAIM's timestamp")
    s.add_argument("--outcome")
    s.add_argument("--friction", required=True)
    s.add_argument("--kv", action="append", default=[])
    s.add_argument("--text", required=True)
    s.set_defaults(fn=lambda a: print(terminal_row(a)) or 0)

    s = sub.add_parser("relaunch-brief", help="write the relaunch brief for one dead lane")
    s.add_argument("--lane", required=True, help="the session lane (the resuming lane)")
    s.add_argument("--new-lane", required=True, help="<dead lane>-r, or -r2 on a second relaunch")
    s.add_argument("--dead-lane", required=True)
    s.add_argument("--dead-claim", required=True, help="the dead CLAIM's stamp")
    s.add_argument("--t0", required=True, help="the outage time")
    s.add_argument("--claim-template", required=True, help="the CLAIM line session-resume step 4 printed")
    s.add_argument("--scope", required=True, help="one line: what the dead lane was doing")
    s.add_argument("--root")
    s.add_argument("--dry-run", action="store_true", help="print, write nothing")
    s.set_defaults(fn=cmd_relaunch_brief)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
