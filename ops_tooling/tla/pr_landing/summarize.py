#!/usr/bin/env python3
"""One line per results/*.out: config, invariants, verdict, distinct states, depth, trace length."""

import glob
import os
import re

rows = []
for f in sorted(glob.glob("results/*.out")):
    n = os.path.basename(f)[:-4]
    with open(f) as fh:
        t = fh.read()
    cfg = ""
    if os.path.exists(f"{n}.cfg"):
        with open(f"{n}.cfg") as fh:
            cfg = fh.read()
    chk = " ".join(re.findall(r"^(?:INVARIANTS|PROPERTIES) (.*)$", cfg, re.M))
    m = re.search(
        r"(Invariant \w+ is violated|Temporal property \w+ was violated|No error has been found)", t
    )
    v = m.group(1) if m else ("running or stopped" if "rc=" not in t else "no verdict")
    ds = re.findall(r"([\d,]+) distinct states found", t)
    d = re.findall(r"depth of the complete state graph search is (\d+)", t)
    tr = len(re.findall(r"^State \d+:", t, re.M))
    depth = d[-1] if d else "-"
    trace = tr or "-"
    rows.append(f"{n} | {chk} | {v} | {ds[-1] if ds else '-'} | depth {depth} | trace {trace}")
print("\n".join(rows))
