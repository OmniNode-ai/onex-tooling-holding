#!/usr/bin/env python3
"""summarize.py [results-dir]: one markdown row per results/<cfg>.out.

Columns: config, expected (from the name: M_ must violate, S_ must reach its
NotS invariant's violation, the rest must report no error), verdict, distinct
states, depth, pass/fail against the expectation, and for a trace the action
sequence TLC printed."""

import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "results")
HEAD = "| Config | Expected | TLC verdict | Distinct states | Depth | Meets expectation"
print(HEAD + " | Trace (actions) |")
print("| -- | -- | -- | --: | --: | -- | -- |")
for f in sorted(root.glob("*.out")):
    t = f.read_text(errors="replace")
    name = f.stem
    found = re.findall(r"([\d,]+) distinct states found", t)
    ds = f"{int(found[-1].replace(',', '')):,}" if found else "?"
    d = re.search(r"depth of the complete state graph search is (\d+)", t)
    depth = d.group(1) if d else "-"
    if "No error has been found" in t:
        verdict = "No error has been found"
    elif v := re.search(r"Invariant (\w+) is violated", t):
        verdict = f"Invariant {v.group(1)} is violated"
    elif "Temporal properties were violated" in t:
        verdict = "Temporal properties were violated"
    else:
        verdict = "INCOMPLETE (" + (re.findall(r"rc=\d+", t) or ["no rc"])[-1] + ")"
    if name.startswith("M_"):
        expected, ok = "violation", "violated" in verdict
    elif name.startswith("S_"):
        expected = f"NotS{name[2:]} violated (reached)"
        ok = verdict == f"Invariant NotS{name[2:]} is violated"
    else:
        expected, ok = "no error", verdict == "No error has been found"
    acts = re.findall(r"^State \d+: <(\w+)", t, re.M)
    if re.search(r"^State \d+: Stuttering", t, re.M):
        acts.append("(stutter)")
    trace = " > ".join(acts) if "violated" in verdict else ""
    print(
        f"| `{name}` | {expected} | {verdict} | {ds} | {depth} "
        f"| {'yes' if ok else '**NO**'} | {trace} |"
    )
