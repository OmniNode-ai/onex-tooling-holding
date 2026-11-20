---
name: operator-status
description: "Answer \"status\", \"what happened while I was out\" and \"what's next\" from live state, in plain words. Reads the rolling ledger through the existing readers (ledger-catchup, the ledger-msg inbox, the session's lanes.txt) and counts a lane's result as done only when verify-claims marks it VERIFIED, including a pull request its repository drain has merged since a lane handed it off. Reports what merged, what waits to land, what is running and who owns it, and what is blocked with its next action. Never lands, merges or arms anything: landing belongs to the repository drains. Then gives a short ranked list of next moves against the milestone, starts through fan-out any move an approved plan already implies, and sends genuine tradeoffs to operator-ruling. Outbound messages stay drafts. Writes one STATUS row per report. Use for a status or what's-next question, when the operator returns from an away notice, or when a result the operator is waiting on arrives."
prosthetic: true
replaces_when: "A mechanical status projection answers the same three questions from the typed work ledger, with verified-only done items and plain-word names, and the orchestrator has not had to run this procedure by hand for two consecutive weeks. Nothing today projects it."
restored_from: "none. New process, from the orchestration-skills catalog (skill 6), built on the rolling-ledger process the lanes already use"
ticket: OMN-17427
hooks:
  PreToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: "python3 \"${CLAUDE_PLUGIN_ROOT}/skills/operator-status/scripts/ledger_read_guard.py\""
---

# Operator status (prosthetic)

The operator asks three questions more than any other: what is the state, what happened while I
was away, and what is next. A good answer is live, verified and in plain words. A bad one relays a
lane's self-report, lists bare numbers, or repeats a stale blocker. This skill is the procedure for
the good answer. It reads the rolling work ledger only through readers, and it writes one row, a
STATUS, per report.

It does not re-implement its neighbours. Claim checking is `/omni:verify-claims`. Dispatch is
`/omni:fan-out`. Questions and decisions are `/omni:operator-ruling`. Messages between lanes are
`/omni:ledger-msg`. A dead lane is `/omni:session-resume`. Appending a row is `/omni:ledger-write`,
and the lane rules every dispatched lane follows are the committed ops_tooling_pkg
`lane_rules/lane-rules-block.md`. Invoke each skill by name, without arguments.

**Landing is not part of this skill.** One landing lane owns every pull request landing, org-wide
(currently `repo-drain-<repo>` under the per-repository routing RULING; the newest routing RULING settles it). A lane with
a ready pull request hands it over through `/omni:pr-handoff`: one MSG to the landing lane, then
its TERMINAL `outcome=handed-off`. This skill reads a pull request's state and reports it. It
never merges, arms, reruns or polls CI, and never proposes a move that would.

## 0. Guard and inputs

Shell state does not persist between Bash calls. Start every Bash call in this skill with the
guard line, then run the inputs script once:

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
export registry_root="${registry_root:?set registry_root to the registry root}"
export ONEX_LEDGER_PATH="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
export DOCS_REPO_PATH="${DOCS_REPO_PATH:?set DOCS_REPO_PATH to a docs_repo clone}"
bash "${CLAUDE_SKILL_DIR}/scripts/status_inputs.sh"
```

It prints `SESSION_DIR`, `SESSION_LANE`, `SESSION_TICKET`, `CLAIM_TS`, `LAST_REPORT`,
`WINDOW_START`, `LANES` (the session's `lanes.txt`), `DRY_RUN`, `GOAL_PATH` (the milestone
file), `REPORT_PATH`, `REPLY_PATH` and `RUN_MARKER`. Keep them: the steps below fill their
angle-bracket fields from this output. Every variable is required with no default: an unset one,
or a knowledge base clone with no `beta/GOAL.md`, stops the script with exit 2 and names it.

`RUN_MARKER` is the file that marks this report as running. While it exists, this skill's hook
(`scripts/ledger_read_guard.py`, declared in the frontmatter) blocks two things: a hand read of the
ledger, and a question or decision row appended without `/omni:operator-ruling`. A blocked call
prints the reader to use instead. The `## Ledger` section removes the marker after the report
STATUS, and a marker older than an hour is ignored.

- When the operator said when they left ("<removed>", "I left at noon"), add
  `--since <that moment as a UTC stamp>`. The window starts at the newest of the session CLAIM,
  the last report and that moment.
- Exit 3 means there is no session yet: run `/omni:way-of-working` first. Exit 2 with `REFUSED`
  means a dry run is pointed at a real registry root: stop and say so. Never work around it.

`${CLAUDE_SKILL_DIR}` is this skill's directory, filled in by the harness. Reading this file
elsewhere, run the scripts from the directory that holds this `SKILL.md`.

## 1. Read live, through the readers

In a normal session, run the reads below in **one read-only background lane**, briefed through
`/omni:lane-brief`, so the foreground only reads the result. The brief carries that lane's CLAIM
and TERMINAL, as every lane's does. The report itself runs under the session's own CLAIM and adds
no CLAIM of its own. Under `ONEX_DRY_RUN` in a sandbox, run the reads inline and dispatch
nothing.

Never read the ledger by hand: no `grep`, `tail`, `sed`, `cat` or Read on it or its `archive/`.
The hook blocks it while the run marker exists. Every ledger fact below comes from a reader:

- **A section of rows**: the catchup digest (item 1). It numbers each row by its line in the
  ledger and cuts it at 150 characters.
- **A row in full** (a HOLD's condition, a FRICTION's text, a RULING's words): pass the digest's
  line numbers to `python3 "${CLAUDE_SKILL_DIR}/scripts/lane_results.py" --rows <n> <n>`. It
  prints `ROW <n> <row>` for each, through the governed grammar.
- **What is addressed to a lane**: the `/omni:ledger-msg` inbox (item 4).

1. **The session digest.** Run `/omni:ledger-catchup` over the whole session, not only the away
   window, so a HOLD or an open CLAIM from before the window is still seen: set
   `CATCHUP_T0=<CLAIM_TS>` and `CATCHUP_CAP=200` in front of its script, as its step 0 shows.
   Take the open CLAIMs (section 1), HOLDs in force (section 2), RULING and OPERATOR-CONSENT rows
   (section 3), unanswered MSG rows (section 4), CORRECTION rows (section 5) and FRICTION
   (section 6). A row stamped before `WINDOW_START` is standing state, not news.
2. **What the lanes say they finished.** Turn each lane's newest TERMINAL into claims files:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/lane_results.py" --lanes "<LANES>" --read-state \
     --window-start "<WINDOW_START>" --out-dir "<SESSION_DIR>/status/claims-<report stamp>"
   ```

   Each lane gets a `LANE` line with `result=in-window`, `before-window` or `none`. A
   before-window TERMINAL was in an earlier report: do not repeat it. The claim kinds are the
   ones verify-claims' own claim table gives, and the script picks none of its own. An in-window
   TERMINAL becomes one of three things:

   - **`CLAIMS`** for a lane that says it merged a pull request: `pr_merged` and
     `no_hold_at_merge`, the table's mapping for "merged".
   - **`HANDED-OFF`**, followed by a `CLAIMS` line, for a lane that gave its pull request to the
     landing lane and stopped: `handoff_msg` (the MSG to the lane in `handed_to=`, at the head
     the TERMINAL names), plus one state claim, chosen by the script's one state read
     (`--read-state`, one `gh pr view` per hand-off): `pr_merged` when the landing lane has
     merged it, `pr_open` otherwise. The line prints that `state=` and the `live_head=`. A live
     head that differs from `head=` means the pull request moved after the hand-off, so say so.
     `state=unread` means the read failed and there is no state claim: report the hand-off as
     not verified, reason "its state could not be read".
   - **`NO-CLAIM`**: nothing a script can check, such as a hand-off that names no landing lane.
     Report it as not verified, with its reason.

   Hand each claims file, exactly as written, to `/omni:verify-claims`, with `SESSION_LANE` as your
   lane. Add no claims and drop none. verify-claims checks each claim live, writes its
   countersign, its CORRECTION and its kick-back MSG through its own Ledger section, and prints
   one verdict per artifact. Count by that artifact verdict only:

   | Artifact verdict | Lane result | Goes under |
   |---|---|---|
   | VERIFIED | merged | Done |
   | VERIFIED | handed off, and `pr_merged` among its claims | Done, landed by the landing lane |
   | VERIFIED | handed off, and `pr_open` among its claims | Waiting to land, held by the lane in `handed_to=` |
   | FALSIFIED or UNVERIFIED | any | Not verified, with the artifact's findings as the reason |

   A FALSIFIED hand-off means the MSG is missing or goes elsewhere, so the pull request waits on
   nobody. verify-claims kicks the lane back, and re-sending the hand-off through
   `/omni:pr-handoff` is that lane's move.
3. **What is running, and who owns it.** A lane with `result=none` has no TERMINAL. Cross it with
   `ListAgents` and with digest section 1. In `ListAgents`, it is running. Absent there but open in
   section 1, it is dangling: name it and route it to `/omni:session-resume`. Never relaunch it
   from here.
4. **What is addressed to the lanes.** Run the `/omni:ledger-msg` inbox check for the session
   lane, for each lane in `lanes.txt`, and for each `handed_to=` lane from item 2. A MSG or HOLD
   addressed to a lane binds it. Reading another lane's inbox is a read: answer nothing on its
   behalf.
5. **What is blocked.** Every HOLD in force (digest section 2 or an inbox) is a blocked item. Its
   owner is the lane in the HOLD row's `lane=` cell, the only lane that can RELEASE it. Name the
   work it stops (the open CLAIM on the same pull request, repo or surface) and the next action:
   the condition the HOLD text states, or a question to its owner through `/omni:ledger-msg`.

An empty section is not evidence of a quiet ledger (rule 16). Before you report "nothing blocked"
or "nothing running", confirm the digest printed its window start line and listed the session's
own CLAIM, which is its positive control.

**If `/omni:verify-claims` is not installed**, check each `pr_merged` and `pr_open` claim yourself
with one read per pull request, and nothing more:
`gh pr view <n> --repo OmniNode-ai/<repo> --json state,mergedAt,headRefOid`. A claim is VERIFIED
only when the state is the one claimed (MERGED or OPEN), and on the claimed head when the claim
names one. Any other state is FALSIFIED, and a read error is UNVERIFIED. `no_hold_at_merge` and
`handoff_msg` stay UNVERIFIED, reason "verify-claims is not installed": do not grep the ledger for
them here. So in this interim check nothing is Done; a merge whose pull request read MERGED goes
under Not verified with that reason. Run no other `gh` verb from this skill. Say in the report
that this interim check ran, and that no countersign was written.

## 2. Write the report

Write the full report to `<REPORT_PATH>` (under the session directory, never committed) and
reply with at most 15 non-blank lines, headings included. Leave an empty section out of the reply
(the file says "nothing"). Process notes (what ran inline, what a neighbouring skill needed,
dry-run caveats) and any preamble go in the file, never the reply. Anything longer stays in the
file, and the reply gives its path.

Order, and what each part carries:

1. **Done, checked live.** Lead with implementation and test progress. Only artifacts
   verify-claims marked VERIFIED, as the step 1 table sorts them. One line per item: what it does, in words, then the
   identifiers in parentheses. "The ledger grammar now refuses legacy row types
   (omnimarket#9001)", never "#9001 merged".
2. **Not verified.** Each lane result that did not verify, with the reason in words: "the inbox
   archive fix is reported merged, but its pull request is still open (omnibase_infra#9003)".
3. **Waiting to land.** Each verified hand-off whose pull request is still open: what it does,
   and that the landing lane holds it. No landing move is proposed for it; landing is that lane's work.
4. **Running.** Each running lane: what it is doing and which lane owns it. Each dangling lane,
   and that it goes to session-resume.
5. **Blocked.** Each blocked item: what is stopped, who holds it, and the next action.
6. **Next.** The ranked moves from step 3.
7. **Friction**, only when the window holds FRICTION rows: what it cost, in words, with its
   ticket when the row names one.

Every non-empty section gets at least one line in the reply. When the cap bites, merge a
section's items into one line ("Done: the grammar change and the archive reader, both checked
live (omnimarket#9001, plugin-tooling-pkg#9002).") rather than drop the section; the file keeps
one line per item.

Rules for every line:
- Name things, never bare numbers or bare codes. A count comes with the items it counts.
- Re-read a blocker or a "decision needed" live before repeating it. A stale blocker is a false
  report.
- No unsolicited critique or explanation of the operator's own writing, plans or decisions. Report
  state and moves, and stop.

## 3. What's next

1. Read the milestone and its open rows from `<GOAL_PATH>`, and the plan its rows cite under
   `beta/plans/` beside it. Ask `/omni:kb-ask` when a row's meaning is unclear.
2. Rank at most five moves by how directly each closes an open milestone row. A move whose
   precondition just verified moves up.
3. Mark each move with one of three states:
   - **starting**: an approved plan already implies it and its precondition is verified. Hand it to
     `/omni:fan-out` now, in the same turn. Under `ONEX_DRY_RUN`, fan-out writes the brief to a
     file and dispatches nothing. If fan-out is not installed or refuses, append the move to
     `<SESSION_DIR>/next-moves.md`, marked starting, with fan-out's reason. In the reply the
     move still opens with **Starting:**, followed by where it went (dispatched, briefed, or
     queued in that file).
   - **needs your call**: a genuine tradeoff with no standing RULING. Invoke the Skill tool with
     `operator-ruling` and follow it: it asks one plain question with options and a
     recommendation, and its own Ledger section records the question. Never write that row
     yourself; the hook refuses a question or decision row appended before operator-ruling is
     loaded. If the skill cannot be loaded, the move still reads **Needs your call** in the
     reply, with the question and your recommendation, and nothing is appended.
   - **waiting**: blocked by a HOLD or an unverified result. Name what it waits on.
4. A falsified lane result is also a move: the kick-back to that lane, which `/omni:verify-claims`
   sends through `/omni:ledger-msg`, or a relaunch through `/omni:fan-out` when the lane has
   stopped.
5. Landing is never a move here. A pull request waiting to land is the landing lane's, and the
   report says so. A lane that still owes its hand-off gets one move: hand off through
   `/omni:pr-handoff`. A milestone row whose next step is landing work reads as **waiting** on
   the landing lane. No move builds or changes landing machinery, and no question to the
   operator asks how landing should work.

Never ask the operator what a plan or a RULING already answers.

## 4. Plain-words check

Write the reply you are about to send, word for word, to `<REPLY_PATH>`. Then check both files,
and fix every flagged line before answering. The reply check takes one `--require` per non-empty
section, named by its first word (`Done`, `Not`, `Waiting`, `Running`, `Blocked`, `Next`,
`Friction`), and flags a section the reply left out:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plain_words_check.py" "$registry_root/<REPORT_PATH>"
python3 "${CLAUDE_SKILL_DIR}/scripts/plain_words_check.py" "$registry_root/<REPLY_PATH>" --max-lines 15 --require Done --require Friction
```

Name every non-empty section in `--require`; the two above are an example.

It is a heuristic: it deletes identifiers (pull request and ticket references, shas, lane names
that carry a digit, letter-digit codes, timestamps, bare numbers) and flags a sentence whose
remainder has fewer than 4 content words, or ends on a dangling word. Headings are checked like
any other line, so a heading cannot carry an identifier-only statement; only a date or timestamp
in a heading is free. `--max-lines 15` also flags a reply over the line cap. Exit 1
lists each flagged line. Rewrite in words, or move detail to the report, rewrite the reply file,
and run both again until both exit 0. A file path or file name in backticks is a pointer, not an
identifier, so "Full report: `<REPORT_PATH>`." passes.

**Your answer is the reply file, verbatim.** Once both checks exit 0, write no more edits: your
final message to the operator is the reply file's text, character for character, with nothing
before or after it. No opening summary, no dry-run note, no closing line about the ledger; each of
those belongs in the report file, and adding one after the check re-opens the line cap the check
just passed. If you want to say more, edit the reply file and run the check again.

## 5. Outbound messages are drafts

When the status calls for a message to someone outside the session (a channel update, a reply, an
email), write it as a draft only: a file under `<SESSION_DIR>/drafts/`, or a platform draft.
Report where the draft is. Nothing leaves as a sent message from this skill. A draft goes out only
after the operator approves it, and that approval is recorded as a RULING through
`/omni:operator-ruling` that names the draft.

## Ledger

This is the only place this skill appends. It writes exactly one STATUS row per report, after the
report file exists and the plain-words check passes. Dispatches, questions, countersigns,
corrections and messages are written by the skills this one routes to, never here.

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
registry_root="${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROW_1="$TS | STATUS | lane=<SESSION_LANE> | ticket=<SESSION_TICKET> | report=<REPORT_PATH> | verified=<n> | unverified=<n> | blocked=<n> | Status report for the window since <WINDOW_START>: <one line in words>"
OK=1
for ROW in "$ROW_1"; do [ -n "$ROW" ] || continue
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --append "$ROW" || { echo "append exit $?"; OK=0; break; }
done
[ "$OK" = 1 ] && rm -f "<RUN_MARKER>"
```

- Fill the angle-bracket fields from step 0 and the report. Leave out the `ticket=` cell when the
  session has none. `report=` is the path relative to `registry_root`, never an absolute path.
- `verified`, `unverified` and `blocked` count the report's Done, Not verified and Blocked items.
- The grammar is printed by `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --print-grammar`.
  Exit 65 is a lint refusal: fix the row and append again, never retype it under another type.
  Exit 75 is a lock timeout: retry, the default dedup window makes it safe. Never edit the ledger
  by hand. `/omni:ledger-write` has the full exit table.
- Read back through the reader, never with `tail`: the append exited 0, and
  `python3 "${CLAUDE_SKILL_DIR}/scripts/lane_results.py" --newest STATUS --lane <SESSION_LANE>`
  prints the row with this report's `report=` path. Peers append too, so the row need not be the
  last line.
- The loop removes the run marker only after the append succeeds. On a failed append the marker
  stays, and the hook keeps guarding until the append is retried or the hour passes.
- In a live session `ONEX_LEDGER_PATH` is `$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md`, the
  rolling work ledger every lane appends to. In a dry run it points at the sandbox copy of the
  ledger, and the row goes there through the same command.

## Dry run

Under `ONEX_DRY_RUN=1`, `registry_root` must be a sandbox registry root holding `.dryrun-sandbox`,
with `ONEX_LEDGER_PATH` on its ledger copy. The reads run inline. The STATUS, and the rows
verify-claims writes, go to the sandbox ledger. Moves marked starting become briefs or lines in
`next-moves.md`, never dispatches. No `gh` verb other than `pr view` runs. The fixture builder and
isolation check for this skill's scenario is `tests/sandbox_fixture.sh`.

## Known follow-up

The typed work ledger (`onex-ledger` in `ops_tooling_pkg`, plan
`beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in docs_repo) replaces the
markdown ledger. The append line under `## Ledger` is the one writer line that changes. The one
reader this skill owns, the TERMINAL lookup in `lane_results.py`, becomes a typed query; it is
proposed as a fourth reader site for the plan's no-prose gate list; its `--rows` and `--newest`
modes become typed lookups by row id. The hook's ledger names (`ROLLING_WORK_LEDGER`,
`$ONEX_LEDGER_PATH`) change with the file. Every other read changes inside the readers this skill
routes to.

## Known friction

- **The lane TERMINAL lookup is a reader site of its own.** No shipped reader lists a lane's
  TERMINAL cells (the catchup digest lists open CLAIMs, and verify-claims resolves only a
  TERMINAL's timestamp), so `lane_results.py` reads them: a fixed-string row-head match, then the
  governed grammar module, typed cells only. Retire it when verify-claims or the typed ledger
  answers "what did this lane report done". Recorded 2026-09-24.
- **The inbox reads only rows addressed to a lane.** A HOLD keyed by `pr=` or `repo=` with no
  `to=` shows in the digest's HOLD section, not in any inbox. Step 1, item 5, reads both.
- **The sent reply drifted from the checked reply.** In a 2026-09-24 dry run the executor passed
  the check on the reply file, then answered with an extra opening paragraph and a caveats
  section, 19 lines against the cap of 15. Step 4 now says the answer is the reply file,
  verbatim. Recorded 2026-09-24.
- **Executors read the ledger by hand, whatever the body says.** Every 2026-09-24 dry run (ten of
  ten) ran `sed`, `tail` or `grep` on the ledger even though section 1 forbade it. Two causes: the
  catchup digest cuts each row at 150 characters, so the executor fetched the whole HOLD or
  FRICTION row by line number; and the Ledger section's read-back said "the row is the last line",
  which reads as `tail`. Fixed by a reader for each need (`lane_results.py --rows` and
  `--newest`) and by the frontmatter hook, which blocks the hand read while the report runs.
  Recorded 2026-09-24.
- **The question row was hand-built.** A 2026-09-24 dry run wrote the operator question as a MSG
  itself instead of invoking operator-ruling, a second append site in this skill's flow. The hook
  now refuses a question or decision row until operator-ruling has been loaded after this skill.
  Recorded 2026-09-24.
- **The hook outlives the report.** Claude Code keeps a skill's frontmatter hooks for the rest of
  the session, so the guard scopes itself by the run marker and does nothing without one. A report
  abandoned before its STATUS leaves the marker for up to an hour; delete
  `<SESSION_DIR>/status/.run-active` to end it early. The guard matches command text: a read
  hidden in a script file is not seen.
- **The reply dropped a section to fit the cap.** Two 2026-09-24 runs left the window's FRICTION
  out of a full 15-line reply. Step 2 now merges items rather than drop a section, and the reply
  check's `--require` flags a missing one. Recorded 2026-09-24.
- **The plain-words check is a heuristic.** It catches identifier-only sentences, not wrong
  descriptions. Until 2026-09-24 it skipped heading lines, so a report written as headings passed
  unchecked; headings are checked now.
- **A test session can reset `registry_root`.** A user settings file that sets `registry_root` in its
  `env` block overrides the variable a dry-run harness exported, and the guard then refuses (exit
  2, measured 2026-09-24). Pass the sandbox root through the session's own settings (for
  `claude -p`, `--settings` with an `env` block), never by editing the guard.
