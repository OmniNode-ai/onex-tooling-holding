---
name: ledger-catchup
description: Catch up on the rolling work ledger after a session start, without reading the whole file. Bounded to a recent window (default 12h, widen with a parameter), it reports open CLAIMs split live vs dead, HOLDs still in force, RULINGs and OPERATOR-CONSENT rows, unanswered MSG rows, CORRECTION rows and a STATUS count, recent FRICTION, and the newest handoff pointer, in about 50 lines. Use manually after session start, before dispatching or continuing work.
prosthetic: true
replaces_when: "A mechanical session-start step runs this same bounded digest automatically and a lane never has to invoke it by hand, on two consecutive session starts. Nothing today runs it unprompted."
restored_from: "none. New process, built from the ledger-messaging RULING row 2026-09-23T13:20:11Z lane=omn17427-foreground"
ticket: OMN-19257
---

# Ledger catchup (prosthetic)

`docs/tracking/ROLLING_WORK_LEDGER.md` is 5,900+ rows and growing. Reading it fully at every
session start does not scale. This skill reads only a recent window and prints a bounded digest —
open work, force-in-effect holds, rulings, unanswered messages, friction, and where the last
handoff is — so a resumed session can act without reading the whole file. It is not a substitute
for `session-resume` (crash/outage reconciliation, which intentionally reads at any age, not just a
window) or the ownership inventory in `merge-drain`.

## 0. Run the digest

Sections 1 to 5 below are one verb. Run it with the window in whole hours (default 12):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" catchup --hours 12
```

The stdout line carries the counts and detail path; the detail file is the full digest these sections
describe. `REFUSED` and `RETRY` carry the fix line.

The window starts at the first **row** stamped at or after `T0`: a line whose first cell is a UTC
timestamp. Header prose, headings and continuation lines are never rows, so they can neither open
the window nor be counted (the earlier recipe compared the first cell of every line, matched header
prose at line 10, and read almost the whole file). The script prints that start line and the row
there, so the start is checkable. Line numbers it prints are the ledger's real line numbers.

Exit `3` means no row is stamped at or after `T0` (the ledger rolled, or the window is longer than
the ledger's age): widen the window, or say so and stop. Exit `2` is bad input. Never suppress
stderr (rule 16).

Every `lane=`, `id=` and `re=` is read from the cell that **starts** with that key, first token
only, never from a substring match, so `supersedes-id=` or text that happens to contain `re=` is
never taken as an id.

Each list section prints its newest 6 rows (`CATCHUP_CAP=<n>` changes that) and a count of the
older rows it did not show, so nothing is cut silently. The whole digest stays near 40 lines.

## 1. Open CLAIMs, live vs dead

The script lists every lane whose latest CLAIM in the window has no later TERMINAL or CLOSEOUT for
that lane. For each one, cross-check it against `ListAgents`. **Live** = the lane name appears in
`ListAgents` (its last ledger row may simply not have posted yet: normal, not dangling). **Dead** =
not in `ListAgents` and its last ledger row predates `T0`. A dead lane with unfinished scope is
`session-resume`'s job, not this skill's. This section only surfaces it.

## 2. HOLDs in force

Canonical `HOLD` rows resolve by `RELEASE re=<hold id>`, not by lane, so the script matches on the
`id=` cell. Legacy `HOLD`/`HELD` rows (the pr-land family, predating the MSG/ACK/HOLD/RELEASE
grammar) carry no `id=`/`re=` pair. They are PR-lifecycle verdicts, not lane-blocking holds, and are
listed separately, for awareness only.

## 3. RULINGs and OPERATOR-CONSENT rows

Every row printed is a full ledger line, cut at 150 characters. Read the cited line in full
(`sed -n '<N>p' "$ONEX_LEDGER_PATH"`) before acting on anything binding.

## 4. Unanswered MSG rows

A `MSG` whose `id` was minted before the window will not appear here even if it is still
unanswered: this section is bounded to the window, not exhaustive. Widen the window if you suspect
an older unanswered message. `/omni:ledger-msg` section 4 runs an unbounded version of this same
check at every lane's own turn start. This section exists for human or foreground orientation, not
as the lane-level inbox gate.

## 5. CORRECTION rows, the STATUS count, and recent FRICTION

CORRECTION rows amend earlier rows, so a row you read in section 3 may have been corrected here.
STATUS rows are counted, not listed: they are the bulk of any window. The newest FRICTION rows close
the digest.

## 6. Newest handoff

```bash
# origin/main is kept current by the canonical-clone sync; no fetch (OMN-20495)
git -C "$registry_root/docs_repo" show origin/main:beta/handoffs/LATEST.md
```

## Positive control

An empty section is not evidence the ledger is quiet (rule 16). It may mean the window, the field
name, or the `awk` field separator is wrong. Before trusting a zero, check two things:

- Section 1 names your own lane: your CLAIM row for the work you are doing should appear as a
  dangling entry, because you have not yet written a TERMINAL.
- The start line is right. An independent anchored read must return the same line number:
  `grep -nE '^20[0-9]{2}-[01][0-9]-[0-3][0-9]T' "$ONEX_LEDGER_PATH" | awk -v t0="<T0 as printed>" '{ts=substr($(0), index($(0), ":") + 1, 20)} ts >= t0 {print; exit}'`
  prints the first row at or after `T0`, prefixed with the same line number the digest printed.

If either fails, the window or the parsing is broken. Fix that before reporting any section as
empty.

## Guardrails

- Never read the whole file (`cat`, an unbounded `grep`, a full `wc -l` scan). If the default 12h
  window returns too much to fit ~50 lines, narrow it (fewer hours) rather than truncating a section
  silently — say which sections were cut and why.
- This skill only reads. It never appends, and it never decides a dead lane's work is abandoned —
  that is `session-resume` (step 3).
- Legacy row types are never rewritten — read them, do not normalize them.

## Known friction (from prior runs)

- **Ledger catchup took 2 tool calls.** It is now one command, `onex_ledger.py catchup`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **The window started at header prose, and the digest read almost the whole file.** Step 0
  compared the first cell of every line against `T0`, so line 10 of the header opened the window.
  The start is now anchored to a row timestamp, `id=`/`re=`/`lane=` to the start of a cell, and the
  recipe lives in `catchup.sh`. → ledger 2026-09-23T14:54:18Z, OMN-19268
- **Invoking the skill with arguments rewrote its awk field references.** The Skill tool replaces
  dollar-digit forms in a SKILL.md body with the arguments. The recipe moved to `catchup.sh`, which
  is never substituted. → OMN-19268
