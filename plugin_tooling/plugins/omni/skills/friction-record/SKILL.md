---
name: friction-record
description: Record process friction so that the next lane and the skills can find it. One FRICTION row on the rolling ledger per item, in the shape the friction guard enforces, with a ticket and a cost, plus a one-line pointer in the Known-friction section of the skill whose procedure hit it. Use the moment a gate, tool, brief or peer lane costs you more than a few minutes, and before your TERMINAL row. It runs itself when invoked with arguments (shell-quoted flags, a line of three dashes, then the verbatim friction text) and a forked subagent writes the row and returns the result line and CITE-AS, so the caller runs no Bash.
prosthetic: true
replaces_when: "A friction record is a typed event that the morning friction sweep and every skill's Known-friction section read mechanically, so that no skill carries a hand-maintained friction list, on two consecutive weeks in which every Known-friction line is generated. On 2026-09-22 the ledger FRICTION row was the only surface read by anything: the plugin's /onex:record_friction writes friction.ndjson, which held 28 events, the last on 2026-06-23."
restored_from: "none. New process. It supersedes, for this workspace, the omniclaude record_friction skill's ndjson registry, which nothing has read since June"
ticket: OMN-19221
context: fork
background: false
model: sonnet
effort: low
allowed-tools: Read, Write, Bash(python3:*)
argument-hint: "--lane L (--ticket|--existing) OMN-n --cost '~15 lane-minutes', then a line of three dashes, then the text"
---

# Friction record (prosthetic)

**The canonical friction surface is the FRICTION row on `$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md`.**
It is the surface that is enforced (the OMN-18274 friction guard inside `onex-ledger`),
harvested (the morning-friction-sweep workflow, report in docs_repo
`beta/tracking/<date>-friction-sweep.md`) and aged (`friction_ticket_aging.py`: rows whose ticket
sits in Backlog for more than 7 days). `$ONEX_STATE_DIR/state/friction/friction.ndjson`, written by
`/onex:record_friction`, is not read by any of these. Do not record there instead of the ledger.

## Run it: one Skill call (forked executor)

**Caller.** Invoke this skill with arguments and it does the whole write in a forked subagent: one
Skill call, and no Bash in your own context. The arguments are a header of shell-quoted words, then
a line holding only `---`, then the body, verbatim (the row's text, one line with no pipe, in the shape section 2 gives). Quotes, pipes, percent signs and
several lines in the body need no escaping; the scripts decide what they become. The header is `record.sh`'s own flags without `--text` (section 1 below).
Example:

```text
/omni:friction-record --lane my-lane --ticket OMN-19821 --cost '~15 lane-minutes'
---
SKILL RAN BASH IN THE FOREGROUND. What happened, citing rows by stamp and lane. Correct move: invoke the skill with arguments.
```

The reply is the script's own result line (`FRICTION <ts> lane=... prior-rows-on-ticket=<n> line=<n>`) plus a `CITE-AS:` line, or a
`REFUSED <code> <rule>: <reason>` line and a `FIX:` line, in which case nothing was written: fix
the arguments and invoke again. Invoked with no arguments, it replies with the argument shapes and
the path of this file. Header options for any of these skills: `--ledger <path>` runs
against another ledger file (a scratch copy named `ROLLING_WORK_LEDGER.md`), and
`--session-env <path>` sources a `session.env` first.

**Forked executor: you, when this prompt ends with an ARGUMENTS line.** Do exactly these four
steps and nothing else. The sections below this one are the caller's reference, not steps for you.

1. Run with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" newdir friction-record`
   It prints a fresh directory, private to this invocation.
2. With the Write tool, write everything after `ARGUMENTS: ` to the end of this prompt, byte for
   byte, to `<that directory>/args.txt`. Include every later line. Add nothing, trim nothing,
   re-quote nothing, and never paraphrase: the body may be the operator's words.
3. Run once with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" friction-record --args-file <that directory>/args.txt`
4. Reply with its stdout verbatim and nothing else, whatever the exit code. Never retry, reword,
   edit the file, run another command or read the ledger. The script never adds `--amends` on its own:
   a RULING that leaves an open same-ticket ruling unnamed comes back refused (`ruling-relation`),
   like every other refusal, to the caller, who names each one.

With no ARGUMENTS line, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" usage friction-record` and reply with its output,
then the line `Procedure: ${CLAUDE_SKILL_DIR}/SKILL.md`.

## 1. Is it already recorded?

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/record.sh" --lane <your lane> --ticket <OMN-n> --cost "~15 lane-minutes" --text "<SYMPTOM>. <what happened>. Correct move: <move>."
```

It runs the duplicate query across archives and the live ledger and prints `prior-rows-on-ticket=`.
`REFUSED` and `RETRY` state the failed rule and its fix. For a keyword duplicate search, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" query --kind FRICTION,CORRECTION --grep <word> --archives`; use a known recent FRICTION word as the positive control.

Cells are split on every pipe with the whitespace around it trimmed, so a row with an extra or a
missing space around a pipe, or a bar-led row (`| <ts> | FRICTION | ...`), is still found. It
searches every archive roll and then the live ledger, because a roll moves rows older than a day
out of the live file. The order matters: the rolls (named by date, so the glob sorts them oldest
first) come before the live ledger, so the output runs oldest to newest and `tail` keeps the newest
hits. Each hit is printed with its own file and line, so read the full row with
`sed -n '<line>p' <file>`. Before trusting an empty result (rule 16), run the same command with one
word you know is in a recent FRICTION row, such as `cost`. It must print rows.

If a row covers the same defect class, cite it (`existing=` its ticket) and record only what is new,
such as a second occurrence or a new cost. **A second occurrence files a ticket.** When the class has
no ticket and this is its second row, mint one if your brief grants mint authority. Otherwise say so
in the row and name who owns filing.

## 2. Write the row

Shape (one line):

```
<ts> | FRICTION | lane=<your lane> | ticket=<OMN-n> (or existing=<OMN-n>, or tickets=<a,b>) | cost=~<N> lane-minutes|lane-hours <plus what else it cost> | <SYMPTOM IN CAPS>. <what happened, citing rows by their timestamp and lane, plus PRs and run ids>. Correct move: <what the next lane should do>.
```

Record it through the entrypoint, not a bare `onex-ledger` call typed from memory:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/record.sh" --lane <your lane> --ticket <OMN-n> --cost "~15 lane-minutes" --text "<SYMPTOM>. <what happened>. Correct move: <move>."
```

Exit `65` means a validation check refused the row and nothing was written. The stderr line names
the rule: the grammar or a content lint, which run before the lock, or the friction guard (a cost
with no duration), which runs under the held lock because it reads rows already in the ledger. Fix
the row and append again. The full exit table is in `/omni:ledger-write` section 3.

The guard refuses a row without a lane, a ticket, or a **cost carrying a duration**: `cost=~15 lane-minutes`,
`cost=~2 lane-hours` or `~30 min`. A cost such as `cost=one wrong answer` is refused (the
friction-to-skills rows of 2026-09-23T00:58:02Z to 00:58:03Z, items F2 to F5, F7 and F17, went in
only on a second attempt). When you record friction on behalf of another lane, use your own
lane and add `source-lane=<theirs>`. Otherwise your TERMINAL row's friction assertion cannot find the row.

**Only cite what can be re-read:** a ledger row by its leading timestamp and lane, a PR number, a run
id, a file:line in a repository or a ticket. Never a ledger line number: a roll renumbers every line,
and the 2026-09-23T14:00:47Z roll left most such citations pointing past the end of the file. When
the evidence lives only in a session transcript, say so in the row.

## 3. Feed it into the skill

If a skill's procedure hit the friction (for example `pr-land`, `merge-drain`, `session-resume`,
`lab-rebuild-triage`, `release-cut` or `lane-brief`), add one line to that skill's
`## Known friction (from prior runs)` section: **symptom**, then the correct move, then
`→ <row ts> lane=<lane>` plus the PR or ticket. Keep it to one line. The ledger row carries the detail.
The skills ship in the `omni` plugin (marketplace `private-repo`, repository
`OmniNode-ai/plugin-tooling-pkg`), at `plugins/omni/skills/<name>/SKILL.md`. The installed copy a
session reads is `~/.claude/plugins/cache/private-repo/omni/<version>/skills/<name>/SKILL.md`.
Edit the skill in a worktree of that repository (`$registry_root/worktrees/<ticket>/plugin-tooling-pkg`)
off `origin/main`, leave the plugin version alone, and land the change by PR. Since OMN-20497 the
post-merge bump PR raises the version once the change lands; after that bump PR merges, run
`claude plugin marketplace update private-repo && claude plugin update omni@private-repo`;
a new session loads the new version.

### An incident closes with a regression test built from its real data

RULING 2026-10-17T09:03:06Z (OMN-17427): build what keeps issues from recurring. An incident is a fix or a tool that
passed its own tests and then broke the fleet, and its tests were written against values the author imagined (the host
parity record of 2026-10-17 had no fixture with the real host layout). The FRICTION row of an incident, and the ticket it
names, are closed only when a regression test exists that:

1. is built from the incident's recorded data (probe output, watcher state, a tick line, rendered file text, ledger rows),
   captured as a fixture and scrubbed of secrets and person names, and says where each datum came from;
2. fails on the broken code: the row or the TERMINAL names the commit or file state it was run against and the failing assertion;
3. lives in the repository that owns the code and runs in that repository's required check.

Cite the test file and the fixture path in the row's text or in the closing TERMINAL. A test that passes only on the fixed
code, or whose values are invented, leaves the incident open. Worked example: `tests/test_incident_*.py` and
`tests/fixtures/incidents-2026-10-17/` in plugin-tooling-pkg.

## 4. TERMINAL

Your TERMINAL row carries `friction=see FRICTION rows <row ts>[, <row ts>]` or `friction=none`. The
guard refuses a TERMINAL row that says nothing, and it checks that a FRICTION row exists under your
lane in the same payload or in the ledger.

## Guardrails

- The ledger is append-only. Never edit a landed row. Correct it with a `CORRECTION` row carrying
  `corrects=<the row's timestamp>` (the append path refuses `FRICTION-CORRECTION` since OMN-19256).
- Never spell a trigger literal in a row, a skill or a PR body (rule 15). Name the family instead: "the skip-token prefixes", "merge-hold vocabulary", "the evidence-source stamp line".
- The defer-language lint refuses TERMINAL rows whose wording reads as deferring an item with no ticket. Name the owner of each item instead (FRICTION row 2026-09-22T08:48:00Z lane=friction-synthesize-2026-09-22).
- Keep person names out of anything bound for docs_repo.

## Known friction (from prior runs)

- **Invoking the skill still put Bash calls in the orchestrator's foreground,** because the skill was a recipe the caller ran. The skill now runs itself in a forked subagent when invoked with arguments (the first section). → operator instruction 2026-09-26 (OMN-19821)
- **Friction recording took 2 tool calls.** It is now one command, `record.sh`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **Friction reported in TERMINAL prose instead of rows:** 231 of 237 rows arrived as one backfill. The guard now enforces the row. → docs/workflows/_shared/friction_guard.py, OMN-18274
- **The guard refuses a cost with no duration.** → FRICTION rows 2026-09-23T00:58:02Z to 00:58:03Z lane=friction-to-skills (second attempt)
- **The defer-language lint fired on a report about findings with no ticket.** → FRICTION 2026-09-22T08:48:00Z lane=friction-synthesize-2026-09-22, OMN-13640
- **A heredoc that contains apostrophes, run through Bash, is refused as untokenisable by the scope gate.** Write files with the editor tool, and split compound push and PR-create commands. → FRICTION 2026-09-22T21:20:46Z lane=unified-verif-obs-plan, FRICTION 2026-09-23T01:03:54Z lane=friction-to-skills, FRICTION-CORRECTION 2026-09-23T01:08:34Z lane=friction-to-skills-2, OMN-19019
- **The plugin's ndjson registry has been silent since 2026-06-23.** Recording there hides the friction. → friction.ndjson (28 rows), this skill
- **The duplicate search wrote its field reference as a bare dollar and a digit,** which the skill
  loader replaced with the skill's own arguments whenever the skill was invoked with arguments, and
  its `grep -n` numbered the filtered output instead of the ledger. It now uses `$(2)`, prints each
  hit's own file and line, and searches the archive rolls too. Fixed 2026-09-23 by the
  omni-skill-fixes pass, OMN-19230 lineage.
- **The duplicate search read the live ledger first and the archive rolls after it, then kept the
  `tail`,** so with more than ten hits it showed only old archive rows and dropped every live one: the
  positive control (words `cost` and `lane`) printed ten 2026-09-21 rows from the 2026-09-23 roll and
  none of the 73 FRICTION rows written in the previous 12 hours, and a lane read a recent duplicate as
  "not recorded". The rolls now come first and the live ledger last. Fixed 2026-09-23 by the
  omni-skill-fixes pass, OMN-19230 lineage.
- **Ledger citations by line number went dead when the ledger rolled** at 2026-09-23T14:00:47Z. Every
  citation in this skill is now a row timestamp plus lane, and sections 2 to 4 tell the next writer
  to cite that way. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **Section 2 said exit `65` meant the row was refused before the lock.** The friction guard that
  refuses a cost with no duration runs under the held lock (`onex-ledger`, `main()`), and
  still returns `65` with nothing written. Section 2 now says which checks run on which side. Fixed
  2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **The section 1 duplicate search split cells on `' [|] '`.** A FRICTION or CORRECTION row with an
  extra or a missing space around a pipe, or a bar-led row, was never matched, so a duplicate read as
  new. The search now splits on every pipe and trims the whitespace around it, and reads the type
  from the third field of a bar-led row. Fixed 2026-09-23 by the omni-skill-fixes pass.
