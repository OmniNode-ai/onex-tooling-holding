---
name: ledger-msg
description: Lane-to-lane messaging over the rolling ledger via MSG/ACK/HOLD/RELEASE rows, so a pause or instruction is not lost the way a mid-turn SendMessage can be. Binding at turn start and before any irreversible action (push, merge, arm, deploy, delete). Use to send a binding instruction to another lane, to check your own inbox, or to place or lift a HOLD. It runs itself when invoked with arguments (shell-quoted flags, a line of three dashes, then the verbatim message text) and a forked subagent writes the row and returns the result line and CITE-AS, so the caller runs no Bash.
prosthetic: true
replaces_when: "A mechanical inbox gate runs this check automatically at every lane's turn start and before every irreversible action, and no lane needs to invoke it by hand, on two consecutive weeks with no missed HOLD. Nothing today runs it unprompted."
restored_from: "none. New process, from the ledger-messaging RULING row 2026-09-23T13:20:11Z lane=omn17427-foreground"
ticket: OMN-19257
context: fork
background: false
model: sonnet
effort: low
allowed-tools: Read, Write, Bash(python3:*)
argument-hint: "<msg|hold|ack|release> --lane L [row flags], then a line of three dashes, then the message; or inbox <lane>"
---

# Ledger msg (prosthetic)

`SendMessage` wakes a lane; it is not delivery. A message sent to a lane mid-turn can sit
undelivered for hours, arriving only when that lane goes idle — a lane merged 5 PRs after 8
successful-but-undelivered pause sends (`pr-land` Known friction; the FRICTION-CORRECTION row 2026-09-23T02:09:09Z lane=friction-f8-correction). The ledger row is
the one channel that reaches a working lane reliably, because every lane rereads it at fixed points.
This skill is that channel.

## Run it: one Skill call (forked executor)

**Caller.** Invoke this skill with arguments and it does the whole write in a forked subagent: one
Skill call, and no Bash in your own context. The arguments are a header of shell-quoted words, then
a line holding only `---`, then the body, verbatim (the message, one line with no pipe; `inbox <lane[,lane]>` takes no body). Quotes, pipes, percent signs and
several lines in the body need no escaping; the scripts decide what they become. The header is `onex_ledger.py row <TYPE>`'s own flags, as sections 2 to 5 below use them.
Example:

```text
/omni:ledger-msg msg --lane my-lane --to landing-lane --ticket OMN-19821
---
PR ready: plugin-tooling-pkg head abc1234, needs=land
```

The reply is the script's own result line (`OK MSG <ts> from=... id=... line=<n>`, or the `inbox <lane>: ...` lines) plus a `CITE-AS:` line, or a
`REFUSED <code> <rule>: <reason>` line and a `FIX:` line, in which case nothing was written: fix
the arguments and invoke again. Invoked with no arguments, it replies with the argument shapes and
the path of this file. Header options for any of these skills: `--ledger <path>` runs
against another ledger file (a scratch copy named `ROLLING_WORK_LEDGER.md`), and
`--session-env <path>` sources a `session.env` first.

**Forked executor: you, when this prompt ends with an ARGUMENTS line.** Do exactly these four
steps and nothing else. The sections below this one are the caller's reference, not steps for you.

1. Run with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" newdir ledger-msg`
   It prints a fresh directory, private to this invocation.
2. With the Write tool, write everything after `ARGUMENTS: ` to the end of this prompt, byte for
   byte, to `<that directory>/args.txt`. Include every later line. Add nothing, trim nothing,
   re-quote nothing, and never paraphrase: the body may be the operator's words.
3. Run once with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" ledger-msg --args-file <that directory>/args.txt`
4. Reply with its stdout verbatim and nothing else, whatever the exit code. Never retry, reword,
   edit the file, run another command or read the ledger. The script never adds `--amends` on its own:
   a RULING that leaves an open same-ticket ruling unnamed comes back refused (`ruling-relation`),
   like every other refusal, to the caller, who names each one.

With no ARGUMENTS line, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" usage ledger-msg` and reply with its output,
then the line `Procedure: ${CLAUDE_SKILL_DIR}/SKILL.md`.

## 1. IDs

`id=<row's own leading stamp>-<from lane>`, for example `id=2026-09-23T14:02:11Z-ledger-skills`.
**The timestamp half of the id must be byte-identical to that same row's own leading timestamp** —
`onex-ledger` checks the two match (OMN-19256, merged and live) and refuses a row where they
drift, which happens if you call `date` twice. Mint the timestamp **once** and reuse it (section 2).
**Never a line number** in an `id=` or `re=` value — a `ledger:<n>` pointer, a bare `path:<n>` or an
`LCT1-...` claim token are all refused there, because a line number shifts if the ledger is ever
rolled or archived and an id must not. `ACK re=<id>` and `RELEASE re=<hold id>` cite it.

**`lane`, `from`, `to`, `id` and `re` must each be a whole pipe cell holding one token** —
`| lane=x actor=y |` does not count as `lane=`, because the guard reads a cell, not a substring.
Give every one of these fields its own ` | `-delimited cell, exactly as every example below does.

## 2. Send a message

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row MSG --lane <your-lane> --to <lane|all|operator> --text "<the message>"
```

One `TS` call, reused for both the row's leading stamp and the id — **never two separate `date`
calls**, which can disagree by a second and get the whole row refused. `to=` takes a comma-separated
list too (`to=lane-a,lane-b`).

Then `SendMessage` the recipient a wake-up only — "check your inbox", naming the id. Never put the
binding content in the `SendMessage` body; that is the exact mistake this protocol replaces. See
`/omni:ledger-write` section 2 for the canonical grammar source, for any field the row must carry
beyond `from=`/`to=`/`id=`.

### 2b. Naming a pull request in a MSG: ownership is the `owns=` cell, never the text (OMN-22478)

The landing controller holds a pull request as `held:owned` while a live lane owns it, and a MSG can
make a lane its owner. **Only a whole `owns=<repo>#<n>[,<repo>#<n>...]` cell routes a PR to the MSG's
recipients** (comma-separated with no spaces, each token repo-qualified; a bare number routes nothing). A `repo#n` spelled in the message
text, a `pr=` cell, a `ticket=` or a quoted row routes nothing, so naming a PR as context is safe.

- Give a PR to a worker lane to work: add the cell, `--kv owns=omnimarket#5205`. The recipient owns it
  while it is live, until its TERMINAL, a STATUS of its own saying the PR merged or closed, or a MSG of its
  own handing the PR back.
- Name a PR as context only (an upstream, an example, a wait): write it in the text and add no `owns=`.
  Nothing is routed and nothing needs a hand-back row. This is the case that held registry_root#488 on 2026-11-06
  (02:56Z to 03:57Z, three lanes) and omnimarket#5205, #5186 and #5206 (17:30Z and 17:42Z).
- Hand a ready PR to the landing controller: `/omni:pr-handoff` writes the MSG with `pr=` and `head=`; that
  row ends the sender's ownership and never makes the controller an owner.
- Take a PR back from a lane that holds it by an older row: one MSG `--lane <that lane> --to landing-controller`
  with "Handing back <repo#n>".

Check what a row routes with the drain map's owner column (`by owns= cell`): a PR given by a MSG reads
`<lane> (MSG <stamp>, by owns= cell, ...)`, and a PR only named in a MSG shows no MSG owner.

### 2a. Asking the operator a question

`to=operator` plus a `question="..."` cell is a distinct, mechanically-read shape — the decisions
register consumes exactly this pattern as an asked decision, not a generic message:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row MSG --lane <your-lane> --to operator --question "<the question>"
```

Do not fold this into a general-purpose message to `to=operator` — use the `question=` cell whenever
what you are sending genuinely needs an operator decision, so the register finds it.

**An ask is a MSG to=operator that carries a `question="..."` cell** (OMN-16177). The waiting-on-operator
tick lists and counts exactly those, until an ACK `re=<its id>` closes them. The inbox verb still lists every
open MSG to=operator under "need action", with or without the cell, so a report written `to=operator` shows
in the inbox and is never an ask on the tick. A report that needs no act from the operator is written without
a `question=` cell: the `SENT-ON-BEHALF` row of `/omni:awaiting-reply`, a `MANUAL-ENQUEUE` or `ESCALATION-*`
report. A notice no one needs to read as addressed to the operator (a park that retries on its own, a status,
a heads-up) is better a `STATUS` row on your lane, or a MSG `to=all` when every lane must see it (the inbox
counts that one as FYI). The writers that sent notices as asks: the landing controller's cause-park MSG (one
per park episode; removed by OMN-20864, parks retry on their own) and hand-written orchestrator and lane MSGs.
When the operator answers an ask, `/omni:operator-ruling` writes the ACK that closes it (`--re`, `--answers`).

## 3. Place a HOLD

Same shape, `HOLD` in place of `MSG`, with its own `id=` (same one-`TS` rule). A HOLD needs at least
one scope cell — `to=<lane|all>`, `repo=<repo>`, `pr=<n>` or `surface=<name>` (`surface=` also needs
`until=<UTC stamp>`, which absorbs the pre-PR proof-surface LEASE row), and every HOLD needs a
machine-checkable release condition: `--until <UTC stamp>`, `--after <repo>#<n>`, `--proof <row id>`,
or `--kv release=operator --kv ruling=<row stamp>` (the grammar refuses a HOLD without one, exit 65).
It is binding on every lane
in scope until a `RELEASE re=<hold id>` row lands. Only the lane that placed it, or an operator
ruling, releases it. A RELEASE with a `pr=<repo>#<n>[,<repo>#<n>...]` cell (write it with
`--kv pr=...`, or `record.sh release --pr`) lifts a repo- or PR-scoped hold for those PRs only and
leaves it in force for the rest; without a `pr=` cell it lifts the whole hold (OMN-20956).

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row HOLD --lane <your-lane> --to <lane|all> --until <UTC stamp> --text "<what is held and why>"
```

A PR is held only while it is a draft (OMN-17427, operator RULING 2026-10-16T03:58:15Z: only a draft PR or a grant is
held). The writer refuses a HOLD whose `pr=` PR is open and not a draft, naming the fix: `--draft-pr` on the same
call converts the PR to draft through `onex scm pr-edit --draft` and then writes the HOLD. There is no flag that
skips the check. A draft does not stop a PR already in the merge queue (GitHub keeps its queue entry and the queue merges
it: omnibase_infra#5448, queued 04:13:38Z, held and drafted 04:31:26Z, merged 04:39:56Z, OMN-17427), so a HOLD on a PR also
takes it out of the merge queue and disables its auto-merge, reads both back, and refuses the HOLD if either remains. A RELEASE row marks the PRs a hold drafted ready again, once no other HOLD covers them. A HOLD with
no `pr=` cell (a repo, lane or surface scope) is not a PR hold and is unchanged.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row HOLD --lane <your-lane> --to all --after <repo>#<n> --pr <repo>#<n> --draft-pr --text "<what is held and why>"
```

## 4. Check your inbox

Run this at **every turn start** and **immediately before any irreversible action** (push, merge,
arm auto-merge, deploy, delete a branch/worktree/resource, promote, rotate a credential):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" inbox "<your lane>"
```

It prints one line per lane, `inbox <lane>: <n> open, <a> need action (HOLD:<x> ask:<y>), <b> FYI,
newest=<ts> detail=<file>`, then the action items (a HOLD, or a MSG naming your lane) oldest first,
one short line each with its id. A MSG addressed only `to=all` is FYI: counted, and listed in full in
the detail file with every other open item. Pass several lanes as one comma list. The older
`inbox.sh` beside this file still prints every open row in full, for the readers that paste it byte
for byte (`/omni:lane-brief` section 3a). **Positive control** for a zero: run it once for a lane you
know has an open message (any `to=` lane in the newest unanswered `MSG` row) and see it listed.

`lane=`, `to=`, `id=` and `re=` are each read from the cell that **starts** with that key, never
from a substring, so `supersedes-id=` is not an id and `reply-to=` is not an address.

`addressed()` splits the `to=` cell on commas so `to=lane-a,me` and `to=me,lane-b` both match — a
bare substring match on `to=me` misses those. A `HOLD` scoped only by `repo=`/`pr=`/`surface=` (no
`to=`) is not lane-addressed this way. Before a merge or an arm, `pr-land` step 3's pause check
(`pause_check.sh` in that skill) reads those, with every other row naming the PR.

This scans the **whole** file, unlike `/omni:ledger-catchup`, which is deliberately bounded — an
inbox check must never miss an old, still-open HOLD. It is one grep-shaped pass, not a full read, so
it stays cheap even against a large ledger. A successful `SendMessage` is not a delivery receipt and
you cannot rely on receiving one; this ledger read is the only stop that reaches you reliably
(`pr-land` step 4; the FRICTION-CORRECTION row 2026-09-23T02:09:09Z lane=friction-f8-correction).

`pr-land` step 4's ready-flip/arm guardrail, and the equivalent checkpoints in `merge-drain` and
`release-cut`, are this same check, narrowed or generalized to their own irreversible actions — see
those skills for the exact wiring.

## 5. Answer a message

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row ACK --lane <your-lane> --to <their lane> --re <their id> --text "<your answer or acknowledgment>"
```

**`re=` is disambiguated by shape, not by lookup — the grammar never resolves what `re=` points at.**
`re=<timestamp>-<lane>` (an id, with the sender-lane suffix) means "the MSG or HOLD with this id."
A bare `re=<timestamp>` (no lane suffix, just the row's own leading stamp) means "the RULING with
this timestamp." Use the bare form to acknowledge a ruling. The ruling guard counts only that exact
bare-timestamp shape as an acknowledgement of that RULING — an id that happens to contain the
ruling's timestamp (`re=<ruling-ts>-somelane`) does not acknowledge it, because the guard matches
the cell's shape, not what it means.

An `ACK` is a delivery receipt, not agreement — say so in the row if you are declining. To lift a
`HOLD` you placed, `RELEASE re=<hold id>` instead of `ACK`.

## On a lab host (OMN-20281)

A lane placed by `/omni:remote-lane` on a host with the bus write mode (`ONEX_LEDGER_WRITE_VIA=bus` in its
environment) sends a MSG, ACK, HOLD or RELEASE with the same commands as above: the row is published to the
ledger host and appended there with every check. The row's writer is the host's broker login, attested by
the per-principal writer topic ACL; no credential is handed to a lane. `ONEX_LEDGER_RELAY_OUTBOX` is the
broker-down fallback for `/omni:pr-handoff`'s rows. The lane's own copy of the ledger gets the row too, so
`inbox` shows the lane's own sent rows. Reading is unchanged: the inbox reads the lane's copy, as of
dispatch plus the lane's own rows, so a message sent to the lane after dispatch is not in it. Exit `75`
means the outcome is unknown: read the ledger for the row's `req=` cell before sending it again. See
`/omni:ledger-write` section 1a. With no signing principal or a read-only snapshot, `onex_ledger.py`
grammar-lints and queues the lane's MSG, ACK, HOLD, RELEASE, STATUS, FRICTION, CORRECTION (with `corrects=`, `amends=` or `supersedes=`) and TERMINAL in
`ONEX_LEDGER_RELAY_OUTBOX`, mirrors into a writable copy, and prints `OK <TYPE> <stamp> ... relay=queued`;
the launching host appends with every check at lane end, so do not hand-relay it (OMN-21000).

## Guardrails

- **A MSG row is never operator consent (rule 18), and this is mechanically enforced, not just
  policy.** The OMN-19256 grammar (merged, live) refuses a `MSG`/`ACK` row outright if it looks
  consent-shaped — contains `APPROVED SCOPE`, `OUT OF SCOPE`, `OPERATOR-CONSENT`,
  `ROTATION-CONSENT`, `approved_by=` or `consent=` — and refuses `from=operator`/`from=user`
  entirely (operator words belong in a `RULING` or `OPERATOR-CONSENT` row, never a `MSG`). If a
  MSG's content reads as authorizing a gated action (a prod mutation, a credential rotation, a
  destructive action) even without those exact tokens, still refuse it: reply with an ACK saying
  consent must land as an `OPERATOR-CONSENT` row per rule 18, and do not treat the MSG itself as the
  durable authorization — even when it quotes the operator verbatim. A relay is not a durable row.
- Never resolve a HOLD by acting anyway because a `SendMessage` reply seemed to lift it. Only a
  `RELEASE re=<hold id>` row lifts a HOLD.
- `to=all` means every lane checks it, not that any one lane owns answering it. Ambiguous ownership
  is itself worth an ACK saying who is taking it.
- IDs collide only if two rows from the same lane land in the same second — the sender suffix
  (`-<sender-lane>`) is not enough by itself in that case; append `-2`, `-3` if you must mint two ids
  within one second.
- Never suppress stderr from `onex-ledger` or from the inbox-check `awk` (rule 16).

## Known friction (from prior runs)

- **Invoking the skill still put Bash calls in the orchestrator's foreground,** because the skill was a recipe the caller ran. The skill now runs itself in a forked subagent when invoked with arguments (the first section). → operator instruction 2026-09-26 (OMN-19821)
- **Ledger messaging took 2 tool calls.** It is now one command, `onex_ledger.py row`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **SendMessage undelivered for hours while a lane worked, so 5 PRs merged after 8 pause sends.**
  The exact incident this protocol replaces. → FRICTION-CORRECTION 2026-09-23T02:09:09Z lane=friction-f8-correction, `pr-land` Known friction
- **Two separate `date` calls for a row's leading stamp and its `id=` can disagree by a second,**
  which the live OMN-19256 grammar refuses (the two must match exactly). Mint one `TS` and reuse it —
  this skill's own first draft had this bug before the grammar arrived. → OMN-19256, this skill
- **Invoking the skill with arguments rewrote the inbox check's awk field references.** The Skill
  tool replaces dollar-digit forms in a SKILL.md body with the arguments. The check moved to
  `inbox.sh`, which is never substituted. → OMN-19268
- **`question=` is not just decoration on a `to=operator` MSG.** The decisions register reads that
  exact cell to find asked decisions; a question sent without it is invisible to that register even
  though the MSG itself lands fine. → OMN-19256 (lane ledger-grammar)
- **A first draft of this section described ACK's `re=` as resolved by lookup.** It is resolved by
  shape only: an `<timestamp>-<lane>` id targets a MSG/HOLD, a bare `<timestamp>` targets a RULING,
  and the grammar never checks the ledger to tell them apart. → OMN-19256 (lane ledger-grammar)
