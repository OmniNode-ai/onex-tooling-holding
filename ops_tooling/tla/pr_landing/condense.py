#!/usr/bin/env python3
"""Condense a TLC counterexample: one line per state with the action and the fields that changed."""

import re
import sys

with open(sys.argv[1]) as fh:
    txt = fh.read()
m = re.search(r"Error: (Invariant \S+ is violated|Temporal properties were violated)", txt)
print(m.group(0) if m else "no violation")
states = re.split(r"\nState (\d+): ", txt)
prev: dict[str, str] = {}
for k in range(1, len(states), 2):
    n, body = states[k], states[k + 1]
    head, _, rest = body.partition("\n")
    act = re.sub(r" line \d+.*", "", head.strip("<>"))
    vs = {}
    for blk in re.split(r"\n(?=/\\ )", "\n" + rest):
        blk = blk.strip()
        if not blk.startswith("/\\ "):
            continue
        name, _, val = blk[3:].partition(" = ")
        vs[name.strip()] = " ".join(val.split())
        if "Stuttering" in val or name.startswith("Back to"):
            break
    ch = [f"{v}={vs[v]}" for v in vs if prev.get(v) != vs[v] and v not in ("latest",)]
    if k == 1:
        ch = [f"{v}={vs[v]}" for v in ("gh", "row", "net") if v in vs]
    print(f"--- {n} {act}")
    for c in ch:
        print("    " + c[:900])
    prev = vs
