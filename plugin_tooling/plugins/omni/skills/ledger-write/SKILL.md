---
name: ledger-write
description: The one way to append a row to the rolling work ledger — wraps onex-ledger --append behind the required ONEX_LEDGER_PATH env var (no default) and points at the canonical row grammar instead of restating field lists that go stale. Use whenever a lane needs to write a CLAIM, STATUS, TERMINAL, HOLD, RELEASE, MSG, ACK, RULING, OPERATOR-CONSENT or FRICTION row. It runs itself when invoked with arguments (shell-quoted flags, a line of three dashes, then the verbatim row text) and a forked subagent writes the row and returns the result line and CITE-AS, so the caller runs no Bash.
prosthetic: true
replaces_when: "onex-ledger --append itself refuses a non-canonical row type or a canonical row missing a required field (OMN-16728, landing as OMN-19256), so this skill's job shrinks to pointing at the ledger path and the grammar source rather than any enforcement of its own."
restored_from: "none. New process, from the ledger-messaging RULING row 2026-09-23T13:20:11Z lane=omn17427-foreground"
ticket: OMN-19257
context: fork
background: false
model: sonnet
effort: low
allowed-tools: Read, Write, Bash(python3:*)
argument-hint: "<TYPE> --lane L [row flags], then a line of three dashes, then the row text; or append-rows, the dash line, then the rows"
---

# Ledger write (prosthetic)

Every lane in this workspace shares one ledger. `onex-ledger` is the mutex that keeps concurrent
appends from interleaving; this skill is the one path every lane is expected to go through to reach
it, so the path, the required env var and the row grammar live in one place instead of being
retyped by every skill and every hand-written brief.

## Run it: one Skill call (forked executor)

**Caller.** Invoke this skill with arguments and it does the whole write in a forked subagent: one
Skill call, and no Bash in your own context. The arguments are a header of shell-quoted words, then
a line holding only `---`, then the body, verbatim (the row's free text, one line with no pipe; or, after `append-rows`, pre-built rows, one per line). Quotes, pipes, percent signs and
several lines in the body need no escaping; the scripts decide what they become. The header is `onex_ledger.py row <TYPE>`'s own flags (section 3 below lists them per type). A RULING or OPERATOR-CONSENT goes through `/omni:operator-ruling` instead, which keeps the words verbatim and adds the OUT OF SCOPE floor.
Example:

```text
/omni:ledger-write CLAIM --lane my-lane --ticket OMN-19821 --actor claude:opus:workflow-lane --model claude-opus --est-hours 2 --displaces 'merge-drain lane time' --kv worktree=worktrees/OMN-19821/omnimarket
---
what the lane will do, in one line
```

The reply is the script's own result line (`OK <TYPE> <ts> lane=... line=<n>`) plus a `CITE-AS:` line, or a
`REFUSED <code> <rule>: <reason>` line and a `FIX:` line (and, when the row lacks a cell such as
`worktree` or `delegated`, a `MISSING-CELL: <name>` line), then `EXIT <code>`; in a refusal nothing was
written: fix the arguments and invoke again. A reply of "Skill execution completed with an empty
result" is the fork dropping the refusal, never a success: assume nothing was written, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" ledger-write --args-file <file>` yourself to read
the refusal, and do not write the CLAIM late. Invoked with no arguments, it replies with the argument shapes and
the path of this file. Header options for any of these skills: `--ledger <path>` runs
against another ledger file (a scratch copy named `ROLLING_WORK_LEDGER.md`), and
`--session-env <path>` sources a `session.env` first.

**Forked executor: you, when this prompt ends with an ARGUMENTS line.** Do exactly these four
steps and nothing else. The sections below this one are the caller's reference, not steps for you.

1. Run with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" newdir ledger-write`
   It prints a fresh directory, private to this invocation.
2. With the Write tool, write everything after `ARGUMENTS: ` to the end of this prompt, byte for
   byte, to `<that directory>/args.txt`. Include every later line. Add nothing, trim nothing,
   re-quote nothing, and never paraphrase: the body may be the operator's words.
3. Run once with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" ledger-write --args-file <that directory>/args.txt --relay`
   (`--relay` makes the process exit 0 and end its output with an `EXIT <code>` line, so a refusal
   is output to relay, never a failed command to stop on).
4. Reply with its stdout verbatim and nothing else. A `REFUSED` line, its `FIX:` line and a
   `MISSING-CELL: <name>` line are the result, not an error: relay them. An empty reply is never
   correct, because the caller reads it as "nothing written, no reason" (OMN-17427). Never retry, reword,
   edit the file, run another command or read the ledger. The script never adds `--amends` on its own:
   a RULING that leaves an open same-ticket ruling unnamed comes back refused (`ruling-relation`),
   like every other refusal, to the caller, who names each one.

With no ARGUMENTS line, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" usage ledger-write` and reply with its output,
then the line `Procedure: ${CLAUDE_SKILL_DIR}/SKILL.md`.

## 1. Resolve the ledger path (fail-fast)

```bash
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
```

**No default.** A skill or brief that hardcodes `docs/tracking/ROLLING_WORK_LEDGER.md` instead of
reading this var keeps writing to the wrong file the day the ledger moves (part of the registry_root
retirement track, rule 20 OUT OF SCOPE note). The operator sets this once per machine; the exact
settings line for this machine is `ONEX_LEDGER_PATH=$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md`
— report it, do not edit `settings.json` yourself.

## 1a. On a lab host: the same command writes through the bus (OMN-20281)

A lane placed on a lab host by `/omni:remote-lane` has `ONEX_LEDGER_PATH` pointing at its copy of the
ledger taken at dispatch, and the runner exports `ONEX_LEDGER_WRITE_VIA=bus` with the publisher command
(`ONEX_LEDGER_BUS_APPEND_COMMAND`) when the host's row of the shared host table declares a ledger bus
and the host passed the runner's probe. Nothing in this skill changes: `onex-ledger --append` then runs
its stateless checks, stamps the row with `req=` and `via=bus:<host>`, publishes it, and waits for the
ledger host's receipt. The row's writer is the host's broker login, attested by the per-principal writer
topic ACL; no credential is handed to a lane. The ledger host appends it to the ledger of record under the
lock with every state-dependent guard, so a refusal comes back as the usual `REFUSED 65 <rule>` line, and an accepted row
prints `OK ... line=<n> via=bus req=<id> status=accepted`. `ONEX_LEDGER_BUS_MIRROR=1` copies each accepted
row into the lane's local copy, so the lane's own CLAIM, FRICTION and MSG rows are visible to
`pr-handoff`'s CLAIM and FRICTION gates and to the inbox.

- RULING and OPERATOR-CONSENT rows are accepted over the bus only from the ledger host's operator principal.
  A lane asks for one in a MSG to the orchestrator.
- Exit `75` over the bus means no receipt arrived: the outcome is unknown, and the request may be appended
  later. Read the ledger for the row's `req=` cell before writing it again; the skill never retries it.
- Exit `69` means the bus cannot be opened (broker down or no login). `ONEX_LEDGER_RELAY_OUTBOX` is the
  broker-down fallback: `/omni:pr-handoff` queues its rows only if this append accepted none, ending its
  result line with `relay=queued:bus-unavailable`. For other rows, report it; do not write the ledger by hand.
- A lane on a host with no bus mode still has a read-only snapshot, and the launching host writes its CLAIM
  (mirrored into the snapshot) and TERMINAL. Its handoff is queued by `handoff.sh` and appended by the
  launching host when the lane ends.

- With no signing principal or a read-only snapshot, `onex_ledger.py` grammar-lints and queues the lane's
  own MSG, ACK, HOLD, RELEASE, STATUS, FRICTION and TERMINAL in `ONEX_LEDGER_RELAY_OUTBOX`, mirrors into a
  writable lane copy, and prints `OK <TYPE> <stamp> ... relay=queued` (OMN-21000). The launching host appends
  with every check when the lane ends; do not hand-relay a queued row.

## 2. Know the row shape before you write it

The canonical row grammar lives in ops_tooling_pkg at
`src/ops_tooling_pkg/ledger/ledger_grammar.py`. The plugin's `scripts/onex_ledger.py`
resolves `OPS_TOOLING_PKG_PATH` when set, otherwise `$registry_root/../ops_tooling_pkg`,
and refuses an invalid selected checkout with both paths named. There is no registry-copy
fallback. The knowledge-base mirror is `reference/ledger-row-grammar.md` (invariant `INV-116`).
Read the live grammar before writing a row:

```bash
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --print-grammar
KB="${DOCS_REPO_PATH:?set DOCS_REPO_PATH to the docs_repo clone}"
# origin/main is kept current by the canonical-clone sync; no fetch (OMN-20495)
git -C "$KB" show origin/main:reference/ledger-row-grammar.md
```

The table and mapping below were verified against a live `--print-grammar` run on 2026-09-23; no
field differs from ledger-grammar's original draft.

Row shape for a **new** row: `<YYYY-MM-DDTHH:MM:SSZ> | <TYPE> | key=value | key=value | ... | free text`.
One field per pipe cell; a field is a cell that starts with `key=`. An identity field (`lane`, `from`,
`to`, `id`, `re`) must be a *whole* cell, `key=<token>`, no spaces inside it. A bar-led, bullet-led or
heading-led row is refused on this ledger — only the leading-timestamp shape opens a row (see this
skill's own docstring warning about crossing into the row above).

**11 canonical types and their required fields:**

| type | required | notes |
|---|---|---|
| `CLAIM` | `lane`, `ticket=` or `tickets=` cell | plus the pre-existing guards: `actor=`/`model=`, a rule-4 cost sentence `est ~N lane-hours; displaces X; (OMN-n)`. A bare `OMN-n` cell with no `ticket=`/`tickets=` key is refused — the id must be the *value* of that field, not a free-standing cell |
| `STATUS` | `lane` | |
| `TERMINAL` | `lane`, `friction`, a delegation cell | `friction=none` or a line; a cited friction needs a matching `FRICTION` row for the lane. **Delegation (OMN-17427, ops_tooling_pkg#36/#37):** one of `delegated=<n> runs=<ids>` (`codex=`/`jev=`/`lab=`/`glm=`/`lab_agent=` accepted alongside `runs=`), `delegated=0 delegation_reason=<reason>` with `<reason>` one of `no-text-or-code`, `route-refused:<status>`, `route-unavailable:<run id>`, `read-only-lane` (operator ruling 2026-10-01; any other reason is refused, and `no-delegation-line` is the remote-lane runner's own, accepted only with `outcome=rejected-no-delegation` or `failed`; `not-attempted:<why>` is the runner's reason for a lane that reached no delegate call, OMN-20489, and `route-unavailable:` is for an `onex delegate` run whose routing returned no rung), or `delegation=na:<reason>` — pass it via `--kv`, e.g. `--kv 'delegated=1 runs=run-a'`. A machine writer (`actor=script:`/`actor=launchd:`/`model=none`) is exempt. A TERMINAL with neither is refused (`65`) at append time, by this plugin's `onex_ledger.py` before `onex-ledger` runs and by the grammar after; `/omni:pr-handoff`'s `handoff.sh` takes this as its own `--delegation "<cells>"` flag so a handoff's TERMINAL is never built without one |
| `FRICTION` | `lane`, `ticket`\|`tickets`\|`existing=OMN-n` | `cost=` is schema-optional but the pre-existing OMN-18274 friction guard refuses the row without one carrying a duration — treat it as required in practice |
| `CORRECTION` | `lane`, one of `corrects=`/`amends=`/`supersedes=` | value is the corrected row's own leading stamp (a `path:line` is still accepted) |
| `RULING` | `lane`, the operator's words in double quotes | |
| `OPERATOR-CONSENT` | `lane`, quoted operator words, a cell `APPROVED SCOPE: <non-empty>`, a cell `OUT OF SCOPE: <non-empty>` | placeholders (`-`, `none`, `n/a`) refused |
| `MSG` | `from=<lane>`, `to=<lane\|all\|operator[,...]>`, `id=<row's own stamp>-<from lane>` | `lane=` optional, must equal `from=` if present; refused if it looks consent-shaped (see `/omni:ledger-msg` guardrails); `from=operator`/`from=user` refused |
| `ACK` | `from`, `to`, `id` (same rules), `re=` | `re=` is **shape-disambiguated, never looked up**: `re=<id>` (`<timestamp>-<lane>`) acks a `MSG`/`HOLD`; a bare `re=<timestamp>` (no lane suffix) acks the `RULING` with that leading stamp — the ruling guard matches only that exact bare shape, so an id that happens to contain a ruling's timestamp does not count. Same consent-shaped refusal as `MSG` |
| `HOLD` | `lane`, `id=<row's own stamp>-<lane>`, at least one of `to=`/`repo=`/`pr=`/`surface=` | `surface=` also needs `until=<UTC stamp>` — this and the RELEASE row below are conditional rules that live only in `--print-grammar`'s prose `rules` list (no structured `required_if` key exists yet) |
| `RELEASE` | `lane`, `re=` | Same shape rule as `ACK`: `re=<id>` (`<timestamp>-<lane>`) releases a `HOLD`; a bare `re=<timestamp>` gives up the `CLAIM` with that leading stamp. `surface=` also needs `result=<PASS\|FAIL\|ABORTED>` and `restored=<yes\|no>` |

**The delegation cell is read from `--kv` and nowhere else (OMN-21810).** Pass it exactly as
`--kv 'delegated=0 delegation_reason=read-only-lane'` (or two `--kv` flags, one per cell),
`--kv 'delegated=<n> runs=<ids>'`, or `--kv 'delegation=na:<slug>'`. These are not read, and a TERMINAL
that uses them is refused `MISSING-CELL: delegated`: `--delegated`, `--delegation-reason`, `--cell`, the
`--delegation` flag (that one is `handoff.sh`'s), and `delegated=0` written in the row text. The refusal's
`FIX:` line names the spelling it found. A `delegated=0` reason outside the declared set (for example
`dispatch-only-lane`) is refused with the accepted values; a lane that has none of them uses
`delegation=na:<slug>`, where the slug is 2 to 41 characters of lowercase letters, digits and hyphens,
starting with a letter or digit, and not a placeholder such as `none`.

**The worktree cell (OMN-17427, OMN-20148).** A CLAIM carries `worktree=<path>` or `worktree=none`, one
cell: pass `--kv worktree=worktrees/OMN-n/<repo>` (a path relative to `$registry_root`; one path, so a
lane on several repos names `worktrees/OMN-n`) or `--kv worktree=none` for a lane that has no
tree. `onex-ledger` refuses a CLAIM without it once ops_tooling_pkg's OMN-20148 grammar is live, and
`--kv` works on either side of that change. A script or launchd lane (`actor=script:*`,
`actor=launchd:*`, `model=none`) is exempt. The lane's closing TERMINAL carries the disposition of the
tree its CLAIM named: `worktree=removed:<path>`, `worktree=pinned-removed:<path>@<archive>` or
`worktree=kept:<path>:<reason>`, with the same path the CLAIM named, and `removed`/`pinned-removed`
are refused while the path still exists. `/omni:pr-handoff` writes that cell itself. A lane that
writes its own TERMINAL runs, from outside the tree (a shell whose working directory is not the worktree; never `cd`),
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_lane_closeout.py" --lane <lane> --worktree <path>`, and
passes the one line it prints, which is already `worktree=<disposition>`, to `--kv` unchanged. A cell
has no space and no pipe.

**IDs and `re=` values never carry a line number** — a `ledger:<n>` pointer, a `path:<n>` or an
`LCT1-...` claim token are all refused there. A duplicate `id=` already live in the ledger is refused. For
`MSG`/`HOLD`, the id's leading timestamp must equal *that same row's own* leading timestamp — mint
both from one `$(date -u ...)` call, never two separate calls that could return different seconds
(see `/omni:ledger-msg` section 2 for the exact pattern).

**An identity field (`lane`, `from`, `to`, `id`, `re`) must be a whole pipe cell holding exactly one
token.** `| lane=x actor=y |` does not count as a `lane=` field — the guard reads a cell, not a
substring, so a second `key=value` sharing that cell is invisible to it. Give every field its own
` | `-delimited cell, as every example in this skill and in `/omni:ledger-msg` already does.

**Asking the operator a question is a `MSG`** with `to=operator` and a `question="..."` cell — the
decisions register reads that shape specifically as an asked decision, not a generic message:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row MSG --lane <your-lane> --to operator --question "<the question>"
```

**Legacy types are never rewritten, only mapped forward for new writes.** A few examples: `NOTE`,
`PROGRESS`, `ACTION`, `EVIDENCE`, `HELD`, `MERGED` -> `STATUS`; `DONE`, `CLOSEOUT`,
`LANE-TERMINAL-STATE` -> `TERMINAL`; `LEASE` -> `HOLD` (with `surface=`, `until=`); `HANDOFF`,
`QUESTION`, `DECISION-REQUESTED` (`to=operator`) -> `MSG`; `FRICTION-CORRECTION`,
`TERMINAL-ADDENDUM`, `NOTE-CORRECTION` -> `CORRECTION`; `OPERATOR-RULING`, `DECISION` -> `RULING`.
`REPLAY` and `STRANDED-CLONE NOTE` are tool-internal and refused from a caller.

**Do not treat this list as complete — it has already drifted once inside this same ticket** (the
live map carries roughly 15 more legacy types than were in the first draft sent in chat, including
`REVIEW_HOLD`, `CLOSE_SUPERSEDED` and `TICKET`). The refusal itself names the mapping for any type
not listed here, so it is never a dead end; when you need the full map, read it live:

```bash
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --print-grammar | python3 -c \
  'import json,sys; print(json.dumps(json.load(sys.stdin)["legacy_type_map"], indent=2))'
```

`onex-ledger` now mechanically enforces the full table above (OMN-19256, live as of
2026-09-23T14:40Z): a non-canonical type or a missing required field is refused at append time, not
only agreed in prose. For the pre-existing per-type guards that predate this grammar (attribution/cost
on `CLAIM`, friction cross-check on `TERMINAL`), `friction-record`, `session-resume` and `pr-land`'s
own Known-friction sections carry the guard's refusal text, not a duplicate of it.

## 3. Append

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row <TYPE> --lane <you> ...
```

Use `row` for one typed row and `append-rows <file|->` for pre-built rows. `row` prints `OK` with
the timestamp, line and detail file, or `REFUSED`/`RETRY` with the fix. Per-type flags are:

| type | flags beyond `--lane` (any type also takes `--kv key=value` and `--text` or `--text-file`) |
|---|---|
| CLAIM | `--ticket`, `--actor`, `--model`, `--est-hours`, `--displaces`, `--kv worktree=<path>\|none`, optional `--scope` |
| STATUS | optional `--ticket` |
| TERMINAL | `--friction`, `--kv worktree=<disposition>` (when its CLAIM named a tree), optional `--closes-claim`, `--outcome`, `--ticket` |
| MSG | `--to`, optional `--question` (a question for the operator), `--ticket` |
| ACK | `--to`, `--re` |
| HOLD | a scope (`--to`, `--repo`, `--pr` or `--surface`) and a release condition (`--until`, `--after` or `--proof`) |
| RELEASE | `--re`; for a surface, `--surface`, `--result`, `--restored` |
| RULING | `--words-file` (the operator's words, verbatim), `--ticket`, optional `--amends`, `--amends-open`, `--supersedes`, `--note` |
| OPERATOR-CONSENT | `--words-file`, `--approved`, `--out-of-scope` (prefer `/omni:operator-ruling`, which adds the OUT OF SCOPE floor) |
| FRICTION | `--ticket` or `--existing`, `--cost` with a duration |
| CORRECTION | exactly one of `--corrects`, `--amends`, `--supersedes` |

The id of a MSG, ACK or HOLD is minted from the row's one stamp, so it always matches.

### Commitments: an operator ask that must not be dropped (OMN-23013)

An ask the operator gives in session becomes a ledger row the moment it is given, with its owner and a check that
proves it on the running system, so a compaction or a long session cannot drop it. It is not a new row type: it is a
STATUS row with `kind=commitment`, built by omnimarket's `node_commitment_writer_effect` (which refuses an ask with no
owner or no runnable check, and encodes the ask's pipes and quotes so it stays verbatim) and appended as a pre-built row:

```bash
# 1. The ask, verbatim, in a file; the node prints one row on stdout (exit 65 and the reasons on stderr when it refuses).
ASK_FILE="$(mktemp)"   # write the operator's words into it first
ROW="$(env -u PYTHONPATH uv run --frozen --project "${ONEX_COMMITMENT_OMNIMARKET:-$registry_root/omnimarket}" \
  python -m omnimarket.nodes.node_commitment_writer_effect \
  --lane <you> --owner <lane that owes it> --check '<argv line, no shell, no pipe>' \
  --ask-file "$ASK_FILE" [--ticket OMN-n] [--requires <ref>[,<ref>]])"
# 2. Append the row (the skill's append-rows form; nothing is appended when step 1 refused).
/omni:ledger-write append-rows
---
<the row printed in step 1>
```

The check is one argv line, for example `uv run onex host-read --host h902 --expect nvme-root`. The check runner node
(`node_commitment_check_runner_effect`) runs it on a schedule, only when its first word is in the runner overlay's
allowlist, and writes a `status=verified` reading when it passes and a `status=regressed` reading when it fails after it
passed; the work-state projection lists every unfinished commitment as work. An ask that is no longer wanted leaves the
open work through the same two steps with `--withdraw <commitment id>` in place of `--owner`, `--check` and `--ask-file`
(withdrawn is final). `ONEX_COMMITMENT_OMNIMARKET` names another omnimarket checkout (a branch not yet merged) and
`ONEX_COMMITMENT_OVERLAY` pins the rules overlay.

Exit codes:

| code | meaning | what to do |
|---|---|---|
| `0` | appended, or skipped as a duplicate of an identical recent append | nothing |
| `2` | usage error (argparse), including a malformed claim token | fix the command line |
| `65` | the row was refused by a validation check and nothing was written. Before the lock: the OMN-19256 grammar (a legacy or unknown type, a missing required field, an id that does not match the row stamp, a consent-shaped MSG, a bar-led, bullet-led or heading-led row) and the content lints (quantitative claim, defer language, clock skew, the CLAIM cost sentence and attribution guards), plus a refused `--replay-*` request. Under the held lock, because they read rows already in the ledger: the OMN-18274 friction guard (a FRICTION cost with no duration, a TERMINAL whose friction assertion finds no row), the RULING guard, and the grammar's duplicate-id check. The `-- <command>` editor verb also returns `65` when its edit breaks a claim rule, after restoring the file | read the stderr line, which names the rule; fix the row and append again |
| `74` | the append would cross a section cap | report it; the ledger needs a roll |
| `75` | lock timeout | retry; the dedup window catches an accidental duplicate |
| `76` | the payload does not open a row at all (plain text, an indented continuation line), so it would extend the row above | start the payload with a row timestamp |
| `77` | the ledger path sits directly in a repository root (a placeholder passed through literally) | pass the real ledger path |
| `78` | stranded clone: the row WAS appended, but the clone is on a branch that `onex-commit-lock` refuses | do not append it again; report the branch |

`65` is the code for every validation refusal, whichever side of the lock it ran on, and the one a lane meets most. `onex-ledger --help`
prints no exit table, and the table in the script's module docstring does not list `65`, `77` or
`78`. Those paths are in `main()` and the stranded-clone guard, so this table is the complete one. Read stderr before assuming a nonzero exit is your payload's fault: `75` is
contention, not a bad row.

To check a row's shape without the lock or the ledger, run the grammar directly. It exits `1` and
prints the reasons when it would refuse:

```bash
uv run --project "${OPS_TOOLING_PKG_PATH:-$registry_root/../ops_tooling_pkg}" python -m ops_tooling_pkg.ledger.ledger_grammar --check '<the row>'
```

That checks shape only. The content lints and the duplicate-id check run only inside
`onex-ledger`. To rehearse a full append, use `row --print-only` plus a scratch copy of the ledger
under the name `ROLLING_WORK_LEDGER.md` (the grammar judges only a file of that name).

A `CLAIM` row's stdout carries a `ledger_lock: CLAIM-TOKEN ...` line. Keep it if you will later need
`--verify-claim-token` to prove the claim preceded a mutation.

## 4. Never hand-edit

The ledger is append-only. A malformed row is followed by a `CORRECTION` row carrying
`corrects=<the row's timestamp>` (the append path refuses the legacy `FRICTION-CORRECTION` shape
since OMN-19256 — see the legacy-mapping list in section 2), never an edit of the row itself. Never
`git commit`/`git push` this file
directly inside `$registry_root` either — `onex-ledger --append` is the only writer of ledger
content, and ops_tooling_pkg's `onex-commit-lock` covers every other shared `registry_root` path.

## Guardrails

- Never suppress stderr from `onex-ledger` (rule 16). A nonzero exit is the guard doing its job,
  not noise.
- Never pass `--dedup-window 0` to dodge the duplicate check, unless deliberately replaying a row
  via `--replay-before`/`--replay-source`, which carries its own provenance requirement.
- A `MSG` row is never operator consent (rule 18) — see `/omni:ledger-msg`, which is the skill that
  sends and reads `MSG`/`ACK`/`HOLD`/`RELEASE` rows. This skill only appends; it does not interpret.

## Known friction (from prior runs)

- **A forked call returned "Skill execution completed with an empty result" for a CLAIM the grammar had
  refused** (no `worktree=` cell), three calls in each of two lanes, so a lane wrote its CLAIM 18 minutes
  late and a second lane took the same PR. The script's own output already held the refusal. The fork now
  runs the script with `--relay` (exit 0, closing `EXIT <code>` line), names the missing cell on a
  `MISSING-CELL:` line, and is told an empty reply is never correct; `tests/test_skill_exec.py` runs a real
  worktree-less CLAIM against a temporary ledger. Probe 2026-10-03 on h907: the pre-change fork relayed the
  refusal on 3 of 3 calls, so the drop is intermittent and the fork's reply is not under the script's control.
  → FRICTION 2026-10-03T13:29:05Z and 2026-10-03T14:03:06Z (OMN-17427)
- **Invoking the skill still put Bash calls in the orchestrator's foreground,** because the skill was a recipe the caller ran. The skill now runs itself in a forked subagent when invoked with arguments (the first section). → operator instruction 2026-09-26 (OMN-19821)
- **Ledger append took 2 tool calls.** It is now one command, `onex_ledger.py row`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **The exit-code list left out `65`,** the code for every grammar, lint and guard refusal, so a lane
  read a refused row as an unknown failure. Section 3 now lists every code `main()` returns. Fixed
  2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **Ledger citations by line number went dead when the ledger rolled** at 2026-09-23T14:00:47Z. Every
  citation in this skill is now a row timestamp plus lane. Fixed 2026-09-23 by the omni-skill-fixes
  pass, OMN-19230 lineage.
- **The grammar-mirror read assumed the docs_repo clone sat under `$registry_root`,** a
  silent default that rule 20 forbids, and read a possibly stale `origin/main`. It now resolves the
  clone from `DOCS_REPO_PATH` (fail-fast) and fetches first. Fixed 2026-09-23 by the
  omni-skill-fixes pass, OMN-19230 lineage.
- **Recipes after the first used `$L` without setting it,** and shell variables do not survive between Bash tool calls, so a lane that ran one section in a fresh call passed an empty ledger path to `onex-ledger` (measured: `Is a directory`, nothing written). Every block that reads or writes the ledger now resolves `L` itself. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **Section 3 said exit `65` always meant a refusal before the lock was taken.** The friction guard,
  the RULING guard and the duplicate-id check run under the held lock (`onex-ledger`,
  `main()`, the block after the dedup check) and also return `65`. Nothing is written either way, and
  the fix is the same, but the stated mechanism was wrong. The row now names both sides. Fixed
  2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **The table gave `76` for a row in the wrong shape.** A bar-led, bullet-led or heading-led row is
  refused by the grammar with `65`; `76` is only for a payload that opens no row at all (measured on a
  scratch copy: a bar-led STATUS returned 65, plain text and an indented line returned 76). Fixed
  2026-09-23 by the omni-skill-fixes pass.
