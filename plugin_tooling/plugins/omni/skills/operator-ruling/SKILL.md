---
name: operator-ruling
description: The two-way decision channel with the operator, kept on the rolling ledger. Ask only what the derivable test cannot answer, as one plain question with options and a recommendation (a MSG to=operator). Record the answer as a RULING with the words verbatim (amends= where a ruling stands), consent or an away grant as an OPERATOR-CONSENT with both scope lists, and a hold as a HOLD. Relay a binding ruling to lanes by one MSG. Use when a decision is needed, when the operator answers a proposal, says they are leaving or back, or says hold, stop or go. It runs itself when invoked with arguments (shell-quoted flags, a line of three dashes, then the verbatim operator's words) and a forked subagent writes the row and returns the result line and CITE-AS, so the caller runs no Bash.
prosthetic: true
replaces_when: "The typed work ledger (onex-ledger) records operator decisions as typed RULING and OPERATOR-CONSENT events, and the orchestrator's session loop asks, records and relays without anyone invoking this skill, on two consecutive weeks. Nothing today does either."
restored_from: "none. New process, from the ledger-messaging RULING 2026-09-23T13:20:11Z lane=omn17427-foreground"
ticket: OMN-17427
context: fork
background: false
model: sonnet
effort: low
allowed-tools: Read, Write, Bash(python3:*)
argument-hint: "<ask|ruling|consent|hold|release> --lane L [flags], then a line of three dashes, then the operator's words verbatim"
---

# Operator ruling (prosthetic)

The operator's decisions steer every lane, so they have to live where every lane reads: the rolling
work ledger. A decision said only in chat is lost at the next restart. A consent a lane cannot cite
authorizes nothing (rule 18). A hold that never reaches the lanes stops nothing. This skill covers
both directions. A question goes out as a MSG only when nothing on file already answers it, and
every answer comes back as the row its kind requires.

The skill writes only through its `## Ledger` section. It reads through the existing readers
(`/omni:ledger-catchup`, `/omni:ledger-msg`, `/omni:lane-brief`) and re-implements none of them.

## Run it: one Skill call (forked executor)

**Caller.** Invoke this skill with arguments and it does the whole write in a forked subagent: one
Skill call, and no Bash in your own context. The arguments are a header of shell-quoted words, then
a line holding only `---`, then the body, verbatim (the operator's words, for `ruling` and `consent`; the other kinds take no body). Quotes, pipes, percent signs and
several lines in the body need no escaping; the scripts decide what they become. The header is `record.sh`'s own command line (sections 2 to 4 below name every flag), with the words after `---` instead of `--words-file`.
Example:

```text
/omni:operator-ruling ruling --lane orchestrator-83 --question 'Ship the lab change and hold prod?' --ticket OMN-17427 --mechanism plugin-tooling-pkg/plugins/omni/skills/pr-land/scripts/claim_guard.py --relay-to all --relay-text 'hand PRs to the landing lane'
---
Yes. "Ship it" | then hold prod.
```

The reply is the script's own result line (`RULING <ts> lane=... kind=... mechanism=... amends=... unrelated=... relay=<n>`, `CONSENT <ts> ... cite=consent=...`, `HOLD <ts> id=...`, `RELEASE ...` or `ASK <ts> id=... say=...`) plus a `CITE-AS:` line, or a
`REFUSED <code> <rule>: <reason>` line and a `FIX:` line, in which case nothing was written: fix
the arguments and invoke again. Invoked with no arguments, it replies with the argument shapes and
the path of this file. The kind may also be given as `--kind <ask|ruling|consent|hold|release>` in place of the leading word (a ruling's own `--kind process|decision` is a different flag and is unchanged). A `consent` may carry `--amends <ts>` naming the earlier consent row it continues; the row must exist or the call is refused (`consent-amends`) before anything is written. Both scope lists of a consent are header flags (`--approved`, `--out-of-scope`), never part of the body. Any refusal that a change of arguments can fix ends with an `EXAMPLE` block: the caller's own arguments in the accepted shape, with a quoted `<placeholder>` for each flag still missing (the operator's words are never copied back). Words over several lines need `--join-lines`, as section 3 says; without it the row is refused. A `ruling` with `--ticket` must name every open ruling on that ticket once, as `--amends`, `--supersedes` or `--unrelated` (section 5); an unnamed one is refused with the list. A `ruling` or `consent` also takes `--session-id` (section 3b) so the row is linked to the prompt that holds the words. Header options for any of these skills: `--ledger <path>` runs
against another ledger file (a scratch copy named `ROLLING_WORK_LEDGER.md`), and
`--session-env <path>` sources a `session.env` first.

**Forked executor: you, when this prompt ends with an ARGUMENTS line.** Do exactly these steps
and nothing else, in two tool calls. The sections below this one are the caller's reference, not
steps for you. Every tool call costs a round of hooks, which on a loaded host is a minute or more
each, so the directory is made when this skill loads, not by a tool call of yours (OMN-17427).

1. Your directory, private to this invocation:
   !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" newdir operator-ruling`
   If the line above is a directory path, that is `<that directory>`. If it still reads as a
   command, run that command once with Bash and use the directory it prints.
2. With the Write tool, write everything after `ARGUMENTS: ` to the end of this prompt, byte for
   byte, to `<that directory>/args.txt`. Include every later line. Add nothing, trim nothing,
   re-quote nothing, and never paraphrase: the body may be the operator's words.
3. Run once with Bash:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" operator-ruling --args-file <that directory>/args.txt`
   A bad argument is refused in about a second, before any ledger read. The result line comes
   first, then `CITE-AS:` (or, on a refusal, `REFUSED`, `FIX:` and `EXAMPLE`), then the trailer: a
   `STEP <name> start budget=<n>s` and a `STEP <name> done rc=<code> <n>s` line for each slow step
   (the read and the append are stopped at their budget, exit 124) and a `TIMING` line.
4. Reply with its stdout verbatim and nothing else, whatever the exit code, `STEP` and `TIMING`
   lines included. Never retry, reword, edit the file, run another command or read the ledger. The
   script never adds `--amends` on its own: a RULING that leaves an open same-ticket ruling unnamed
   comes back refused (`ruling-relation`), like every other refusal, to the caller, who names each
   one.

With no ARGUMENTS line, run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/skill_exec.py" usage operator-ruling` and reply with its output,
then the line `Procedure: ${CLAUDE_SKILL_DIR}/SKILL.md`.

## 0. Before anything

Shell state does not survive between tool calls, so open **every** block in this skill with these
lines. Write the `SESSION_ENV` path literally, as `/omni:way-of-working` step 3 printed it:

```bash
SESSION_ENV="<the SESSION_ENV path way-of-working step 3 printed>"
[ -f "$SESSION_ENV" ] || { echo "BLOCKER: no session.env at $SESSION_ENV; run /omni:way-of-working first"; exit 2; }
set -a; . "$SESSION_ENV"; set +a
registry_root="${registry_root:?set registry_root to the registry root}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
[ -n "${SESSION_LANE:-}" ] || { echo "BLOCKER: $SESSION_ENV sets no SESSION_LANE"; exit 2; }
```

- **Prerequisites:** `ONEX_LEDGER_PATH`, and the session's `session.env`. That file names the
  session lane (`SESSION_LANE`), and it restores `registry_root` when a shell profile has reset it.
  A lost path is recovered with `session.py show --lane <lane>` in `/omni:way-of-working`. With no
  `session.env` at all, stop: run `/omni:way-of-working` first. `ruling_rows.py` refuses (exit 2)
  when it gets neither `--lane` nor `SESSION_LANE`.
- **Your lane holds an open CLAIM.** `/omni:way-of-working` writes the session CLAIM. If your lane has
  none, write one through `/omni:ledger-write` before the first row here.
- **Read your inbox:** `/omni:ledger-msg` section 4, for your own lane. A HOLD or MSG addressed to you
  binds you before anything this skill records.

## 1. The derivable test: ask nothing that is already decided

A question to the operator costs their attention, and one they have already answered costs it twice.
Before asking, check four sources. Ask only if all four come up empty.

1. **A standing RULING or OPERATOR-CONSENT.** On the subject's ticket, one read lists them:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" query --kind RULING,OPERATOR-CONSENT --ticket <OMN-n> --archives --limit 5`
   (a count line, then the newest rows cut short; the full rows are in the detail file it names).
   The recent window is `/omni:ledger-catchup` section 3. Never grep the raw ledger for this. Read
   any cited row in full before relying on it.
2. **CLAUDE.md or a memory.** The operating rules, and the standing rulings in memory, settle most
   process questions: where documents go, what needs a grant, which model tier a lane runs on.
   Who lands a PR is settled too. One landing lane owns all PR landing by a standing RULING, and a
   lane with a ready PR hands it over with one MSG (`/omni:pr-handoff`). Never ask it.
3. **An approved plan, or a go already given.** A plan the operator approved implies its next steps.
   An approved recommendation is not reopened without new evidence, and "execute" carries its own
   authorization.
4. **Someone else's lane.** If another lane or owner holds the work, the question goes to that lane
   as a MSG (`/omni:ledger-msg` section 2), not to the operator.

A question that only confirms a settled fact is never asked. When the answer is derivable, act on it
and cite its source, for example `per RULING <ts> lane=<lane>`, in your next STATUS or CLAIM.

The test is shown in the ask, and `ruling_rows.py ask` refuses one that does not show it (OMN-21065,
RULING 2026-10-10T17:54:23Z): `--source <path[:line[-line]]>` for each source read, `--derivation` for
what they settle and why they leave this open, and two or more `--options`. A cited source that already
answers the question is refused (exit 3): a paragraph that shares the question's words and carries some of
the options but not all of them. The check is lexical, so cite the lines you read, not a whole file. A
rolling-ledger citation (`docs/tracking/ROLLING_WORK_LEDGER.md:<line>` or `ROLLING_WORK_LEDGER.md:<line>`)
reads `ONEX_LEDGER_PATH`, the file the rows are appended to and the inbox reads (`record.sh` passes it
as `--ledger-file`), never a copy under the registry root (OMN-16177).

## 2. Ask: one plain question, its options and a recommendation

A question that passes the test is written in words, with no bare ticket, PR or check numbers.
Name each thing by what it is. Give two or three options and your recommendation, with its reason
in one line. Record the row:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/record.sh" ask --lane "$SESSION_LANE" --ticket "<OMN-n>" \
  --question "<one plain question>" --options "<A: ...; B: ...>" --recommend "<A, because ...>" \
  --source "<path:first-last>" --derivation "<what the sources settle, and why this is left open>" \
```

A row is stamped when it is **built**, not when it is appended, so `record.sh` builds with
`ruling_rows.py` and appends in one call. For several questions, run it once per question; two
built in the same second share an id, and the second is refused as a duplicate (exit 65): run that
one again. Never write a row by hand to get around a collision.

The `question="..."` cell is the shape the
decisions register reads (`/omni:ledger-msg` section 2a). Then ask the same question in the
conversation, using the `say-in-conversation=` text the script printed. Keep working on everything
the question does not block. Waiting idle for the answer is itself a cost.

## 3. Record the answer as the row its kind requires

**A RULING carries `--question`: the question or options the operator's words answer, even with `--re`. The context is one cell, `question=`, beside the verbatim answer; empty or placeholder context is refused. Always record the operator's words exactly as said.** Write them to a file with the Write tool,
never through `echo` or shell quoting, and pass `--words-file`. The script keeps the bytes and removes
only one trailing newline. Never trim, correct, soften or paraphrase the words inside the quotes.
Context goes in `--note`, after them. Two cases need a marked form, because a row is one line of
pipe-separated cells:

- Words that span lines are refused unless you pass `--join-lines`. That joins the lines with
  ` / ` and marks the row `verbatim=joined-lines`.
- A `|` in the words would open a new cell, and a `"` would end the quote. The script then encodes
  exactly three characters (`%` as `%25`, `|` as `%7C`, `"` as `%22`) and marks the row
  `verbatim=encoded`. `ruling_rows.py decode --row "<row>"` prints the exact words back. Anyone
  quoting such a row decodes it first.

| The operator says | Build | Then |
|---|---|---|
| A decision that changes a standing process | `record.sh ruling --question "<question or options>" --words-file F --ticket <subject> --mechanism <path>` (or `--mechanism-ticket <OMN-n>`, or `--mint-mechanism-ticket '<title>' --parent <epic> --mint-gate '<binding>'`, section 3a), plus, for each standing ruling step 1 found on the same ticket, `--amends <ts>` (it continues or changes it), `--supersedes <ts>` (it replaces it) or `--unrelated <ts>` (a different matter filed under the same ticket; it stays in force) (all repeat) | relay it (section 4) if it binds any lane |
| A one-off decision (close this PR, pick option B) | `record.sh ruling --question "<question or options>" --kind decision --words-file F --ticket <subject>` | nothing to enforce, so no mechanism |
| A terse go on a proposal | `record.sh ruling --question "<proposal question or options>" --re <the proposal's MSG id>`, with `--kind decision` or the proposal's mechanism | the go authorizes that proposal as written, nothing more; execute it |
| Consent to consent-bound work | `record.sh consent --approved "<a; b>" --out-of-scope "<c; d>"` (`--amends <ts>` when it continues an earlier consent row) | read the line back and cite it in the executing CLAIM (the `## Ledger` section) |
| Leaving for a while, keep work moving | `record.sh consent --away --approved "<what they allowed>"` | ask nothing; open the reply with one line saying work continues quietly inside the scope, then the two lists; anything outside the scope waits as a question (section 2) for their return |
| Hold, stop, or pause | `record.sh hold --to <lanes\|all>` or `--repo`/`--pr` | relay is automatic: the HOLD is in every addressed lane's inbox |
| Release, or go again after a hold | `record.sh release --re <hold id>`; `--pr <repo>#<n>[,<repo>#<n>...]` lifts it for those PRs only | |
| "Update the plan, then stop" (a plan gate) | `record.sh ruling` | update the plan through `/omni:plan-write`, then stop on that thread: no tickets, no dispatch past the named step |
| Yes to a structural change | first show the target shape (a tree, a file list, the new layout), then record the yes with `record.sh ruling` | do nothing structural before the yes |
| Back from away | nothing here | run `/omni:operator-status` |
| Anything touching prod or a credential | see section 5 | |

**A ruling whose subject is already settled is refused** (OMN-17427, 2026-10-17: a ruling that no
infra_repo work belongs in M4 was recorded although earlier words had settled it). Before `record.sh ruling`
reads the ledger it runs `queue_status.py --ruling-settled`: if the question and the words share three subject
words with the question (else the words) of an earlier RULING or OPERATOR-CONSENT row of the last 45 days **on the
same ticket**, the call is refused (`ruling-settled`) with that row's stamp. The operator's words that only repeat
it record nothing; the reply cites the row (`per RULING <ts>`). Words that change or add to it are recorded with
`--amends`, `--extends` or `--supersedes` naming the row's stamp, which passes the check. A captured operator prompt
is never a source, and neither is a CORRECTION row or a row on another ticket (OMN-23314, 2026-11-09: "Ok agreed"
was refused three times on words shared with eight unrelated captures: standup notes, a job post, plan-review
requests). A decision the operator really already ruled is on the ledger as a RULING, and that still refuses.

**An answer closes the ask it answers** (OMN-16177, RULING 2026-10-14T18:04:24Z
lane=orchestrator-bb1a). The inbox closes a MSG only on an ACK `re=<its id>`, so an answered ask
used to sit open beside the real ones. A `ruling` with `--re <ask id>` and `--ticket` writes, after
the RULING, one ACK `re=<ask id>` addressed to the lane that asked. A ruling or consent that answers
other asks names each with `--answers <ask id>` (repeatable). `record.sh` keeps an ACK only when the
ledger shows the id is a MSG to=operator, and for `--re` only on the same ticket. The result line
says `answered=<ids>`, and `not-answered=<id>:<reason>` for each one it dropped. Before recording,
read the open asks (`/omni:session-start` unit 5, `loops_check.py operator-waiting`) and name every one the words
answer.

**The OUT OF SCOPE floor.** Every consent row names production and credential rotation in OUT OF
SCOPE, and the script adds them if you left them out. An away grant (`--away`) also names staging.
Rule 12 needs a fresh in-session go for a staging-class namespace, and a grant given before leaving
is not one. So an away grant whose APPROVED SCOPE names staging is refused (exit 3), the same way a
consent naming production is. Leave staging out and hold it as a question for the operator's
return. `OUT OF SCOPE: none` names nothing, so the script refuses it (exit 3) and the grammar does
too (exit 65).

**The row lane is yours.** `lane=` is the lane that recorded the row, never the operator.
`from=operator` is refused.

## 3a. A process ruling names its mechanism

A ruling that changes a standing process (who lands PRs, where plans go, that lanes stop polling
GitHub, that change-control companions are batched) is remembered only while someone remembers it,
unless something enforces it. So `ruling_rows.py ruling` is `--kind process` by default and refuses
(exit 3) unless the row names what enforces it (OMN-19854):

- `--mechanism <path>`: the check, hook, guard or script that already enforces it, as a path
  relative to the registry root (`$registry_root`) or its parent, where `ops_tooling_pkg` lives. For
  example `plugin-tooling-pkg/plugins/omni/skills/pr-land/scripts/claim_guard.py` for the landing
  lane, or a workflow file for a required check. `#anchor` or `:line` may follow. Repeat the flag, or
  give a comma list. A path that does not resolve under `$registry_root` or its parent is refused (exit
  3, also when `registry_root` is unset) unless the row also carries `--mechanism-ticket`; with the ticket
  the row is accepted with a `mechanism-unresolved=` line, so every unmechanized ruling has a ticket
  to dispatch (OMN-20780).
- `--mechanism-ticket <OMN-n>`: nothing enforces it yet. File the ticket that builds the mechanism
  first, through `/omni:create-ticket`, then record the ruling citing it. The ruling reads
  `UNMECHANIZED (pending OMN-n)` until a CORRECTION row links a `mechanism=` path that resolves and
  is wired.
- `--mint-mechanism-ticket '<title>' --parent <epic> --mint-gate '<binding>'`: nothing enforces it
  and no ticket builds it yet, and the ruling must not wait for one. One invocation does three steps
  (OMN-20859):
  1. The RULING is appended at once, through the same guarded append (every refusal above still
     applies), carrying `mechanism-pending=<its own stamp>` and the title, parent and Gate binding
     the mint needs (`mechanism-parent=`, `mechanism-gate=`, `mechanism-title=`). From this step on
     a lane brief may cite the RULING row as authority.
  2. `ruling_rows.py mint` builds the ticket exactly as `/omni:create-ticket` would send it (Backlog,
     under the parent, no project, the Gate line, a falsified criterion, and the marker line
     `Ruling-marker: <ruling ts> lane=<lane>`), runs the create gate's own checker over it
     (`omniclaude/plugins/onex/hooks/lib/ticket_creation_guard.py` under `$registry_root`), searches Linear
     for a ticket whose body already carries the marker, and creates one only when none does.
  3. A CORRECTION row links it: `corrects=<ruling ts> | ruling-lane=<lane> | mechanism-ticket=<OMN-n>`.

  The result line adds `mechanism-pending=<ts> mint=<OMN-n> link=<CORRECTION ts>`. When the create
  failed, hung, or its answer was lost, or the gate's checker refused the payload, it reads
  `mint=pending link=pending`, a `PENDING:` line says why, and the exit is 4: the ruling is recorded
  and stands. `bash "${CLAUDE_SKILL_DIR}/scripts/record.sh" mint --ruling <ruling ts>` (run
  directly; it is not a kind of the forked call) finishes steps 2 and 3 from the row (add
  `--mint-gate`, `--parent` or `--mint-mechanism-ticket` to replace what the row carries). It
  searches the marker before any create, so a create whose answer was lost is found, never made
  twice, and a ruling already linked is reported `mint=linked-before` with nothing written. Each
  Linear call and the checker get `ONEX_RULING_MINT_TIMEOUT_S` seconds (default 30), the whole mint
  `ONEX_RULING_MINT_BUDGET_S` (default 150). Naming `--mechanism` or `--mechanism-ticket` beside it
  is refused, as is `--kind decision`.
- `--kind decision`: a one-off with nothing to enforce (close this PR, pick option B, approve this
  plan). Naming a mechanism with it is refused, because the two contradict each other.

The row carries `kind=` and the `mechanism=` / `mechanism-ticket=` cells. The checker
`queue-status/scripts/ruling_mechanisms.py` reads them back. Every queue-status tick and the session
preflight's `ruling_mechanisms` row list each process ruling of the last 14 days that has no
resolved, wired mechanism (a ticket alone, a path that is gone and a path nothing runs all count), and
each such ruling older than 24 hours makes queue-status DEGRADED.

**A ruling recorded without a mechanism** (older rows, or a mechanism found later) is fixed by one
CORRECTION row through `/omni:ledger-write`, never by rewriting the RULING:

```text
<ts> | CORRECTION | lane=<your lane> | corrects=<ruling ts> | ticket=<OMN-n> | mechanism=<repo path> | <what enforces it>
```

Use `mechanism-ticket=<OMN-n>` in place of `mechanism=` only while the mechanism is still to be built
(the ruling stays unmechanized, pending that ticket). A one-off leaves the audit only by an operator
row: a RULING or OPERATOR-CONSENT carrying `kind=decision`, or this CORRECTION with `kind=decision`
and `operator-row=<that row's ts>`; a `kind=decision` CORRECTION without one is refused (OMN-19854). Several rulings in the same second are told apart with
`ruling-lane=<lane>`.

## 3b. Link the row to the words it covers (OMN-18531, plan task TA.4)

A ruling or consent says what the operator said; the link says where. The forked executor finds the
operator-typed prompts of the caller's session whose text holds the recorded words (whitespace
normalized) and writes `prompt_id=<uuid>` and `covers=<start>:<end>` (character offsets into that
prompt, counted in Unicode code points) on the row. Pass **`--session-id <the operator's session id>`**
in the header: the forked executor's own session is not the operator's. `--transcript <path>` names the
file when it is not under `$CLAUDE_CONFIG_DIR/projects/*/<session id>.jsonl` (default `~/.claude`).
It reads the transcript on its own host and compares the words after `---` (or `--words-file`), before
any joining or encoding.

An operator-typed prompt is a user record with a `promptId` and a `promptSource` of `typed` or `queued`,
that is not a compact summary, meta record, sidechain, tool result or harness notification. A compact
summary carries a `promptId` but no `promptSource`; a headless driver carries `sdk`.

| The words are found in | The row gets | The result line |
|---|---|---|
| exactly one operator-typed prompt | `prompt_id`, `covers` | `LINK linked prompt_id=... covers=a:b` |
| several operator-typed prompts | `prompt_match=ambiguous`, no id | `LINK ambiguous matches=n` |
| none (or no transcript on this host, or no `--session-id`) | neither: written unlinked, never refused | `LINK unlinked: ...` |
| only synthetic records (compact summary, tool result, harness text) | nothing is written | `REFUSED 65 synthetic_source_only` |

The link fields are computed, so `--prompt-id`, `--covers`, `--prompt-match`, `--confirms` and
`--confirmed-by` in the header are refused. A row without `prompt_id` is "recorded, unlinked": it never
claims the words were verified.

**Confirming a candidate.** A candidate the context package listed becomes a ruling only on the
operator's own word: `--confirm <candidate_digest> --candidate-file <candidate file> --listed-at <UTC
stamp of the package>`, the words after `---` being the candidate's quote exactly. The digest is the
sha256 (64 lowercase hex) of the candidate's JSON with the five keys `kind`, `quote`, `event_id`,
`prompt_id`, `offsets` (`"<start>:<end>"`), sorted keys, `,` and `:` separators, non-ASCII kept. It writes
the row only when an operator-typed prompt later than `--listed-at` holds `confirm <first 12 hex of the
digest>`, the quote still sits verbatim at the offsets of the cited prompt, and the words equal the quote.
The row carries `confirms`, `prompt_id`, `covers` and `confirmed_by` (the confirming prompt). Each failure
refuses with its reason (`confirm_digest_mismatch`, `confirm_body_differs`, `confirm_not_found`,
`confirm_offsets_stale`) and writes nothing.

**A review row (D10).** `--reviewed <first prompt id>..<last prompt id>` on a ruling records that the
operator reviewed those prompts with nothing further to record, the ids being the ones the compaction
trailer printed and the words after `---` the operator's. Both ids must be operator-typed prompts of
`--session-id`, first not after last in capture order (`reviewed_malformed`, `reviewed_unknown_prompt`,
`reviewed_reversed`, `reviewed_unverifiable` refuse). The row is linked to the operator's prompt by the
table above like any other ruling.

## 4. Relay a binding ruling: one MSG

A ruling that binds other lanes reaches them by exactly one MSG. Record it with the RULING in one call,
so `record.sh` writes the RULING first and never relays a refused ruling. Both `--relay-to` and
`--relay-text` are required for a relay: an empty recipient, `none` in any recipient slot, or an
empty or `none` body is refused before any row is written, with the missing field named:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/record.sh" ruling --question "<question or options>" --lane "$SESSION_LANE" --ticket "<OMN-n>" \
  --mechanism "<repo path>" \
  --words-file "<words file>" --relay-to "<lane-a,lane-b|all>" --relay-text "<what each lane now does>" \
```

- The relay cites the ruling as `operator RULING <ts> lane=<lane>` in its text. It carries no `re=`
  cell and no `ruling=` cell. The ruling guard counts either one as an acknowledgement, which would
  close the ruling on the receivers' behalf. Each receiving lane ACKs for itself with a bare
  `re=<ruling ts>` (`/omni:ledger-msg` section 5).
- A relay is never consent-shaped. The grammar refuses a MSG carrying `APPROVED SCOPE`,
  `OUT OF SCOPE`, the consent row's type name, `consent=` or `approved_by=` (exit 65). To tell lanes
  about a consent, name "the operator's consent row at `<ts>` lane=`<lane>`". Each lane then cites the
  line in its own CLAIM.
- Never SendMessage the ruling itself. The row is the delivery.
- **A ruling about who lands PRs is an ordinary ruling.** Record it with `--supersedes` the standing
  landing ruling and relay it `--relay-to all`, so every lane hands its PRs to the new owner. Its
  mechanism is pr-land's claim guard, `--mechanism
  plugin-tooling-pkg/plugins/omni/skills/pr-land/scripts/claim_guard.py`. Write no file, and change
  no landing skill: the landing lane reads the RULING itself.

## 5. Hard gates stay hard

- **Production.** No row opens the prod gate. A prod promotion or mutation needs a fresh,
  CODEOWNERS-approved grant in the change-control repo (CLAUDE.md rules 2a and 12). The script
  refuses a consent whose APPROVED SCOPE names production. Record the operator's words as a RULING,
  and route the promotion to the gated path.
- **Credential rotation.** It needs real exposure, recorded first. It also needs a consent row with
  `approved_by=` naming one of the two approvers rule 22 lists, the credential named in APPROVED
  SCOPE, and the rotation command citing that row (rule 22). Without `--approved-by`, the script
  refuses any consent that names a credential.
- **A MSG is never consent.** Neither is a peer lane quoting the operator, a relay, or a brief. Only
  the operator's own words, recorded here, are consent.
- **One ruling in flight per subject, and every open one is named.** `record.sh ruling --ticket T`
  reads the open (unacknowledged, in-flight) rulings on T first and refuses (exit 65,
  `ruling-relation`) unless each is named once by what the operator's words do to it:
  `--amends <ts>` when this ruling continues or changes it, `--supersedes <ts>` when it replaces it,
  `--unrelated <ts>` when it is a different matter that happens to be filed under the same ticket.
  The settled-subject check also accepts `--unrelated <ts>` for a `PROMPT` match from
  `captures.jsonl`; use the capture's full timestamp. A capture must match the question's subject,
  not only the answer's wording. A real repeat is still refused unless its source is named.
  `--unrelated` writes an ACK row `re=<ts>` first (the guard's own release path), puts
  `unrelated=<ts>` on the RULING, and leaves the standing ruling in force exactly as written. Read
  each standing ruling's words before choosing. Nothing is chosen for you: until 2026-09-28 the
  tool added `--amends` for every open same-ticket ruling, and a session ticket carrying unrelated
  rulings got them all marked amended. A ruling guard refusal at append time (exit 65,
  "unacknowledged ruling") means one opened after the check: name it the same way and rerun. Never
  reword the row or drop `--ticket` to slip past the guard.
- **Exit 65 is a lint refusal.** Read the stderr line, fix the row, and append again. Never bypass it,
  retype the row under another type, or edit the ledger by hand.

## Ledger

`record.sh` appends the rows; it stops at the first refusal and prints which rows landed. Its
result line is the read-back: the row was found on disk after the append, so do not grep the ledger
to confirm it.

- It stops at the first refusal, so a relay never follows a refused RULING. Rows before the
  refused one are already on the ledger: rebuild only the refused row and the rows after it.
- Never suppress stderr (rule 16). Exit 75 is lock contention, so retry it. The other exit codes are
  in `/omni:ledger-write` section 3.
- **Read a consent line back** for the `consent=` citation from `record.sh`'s `consent-line=` and
  `cite=` values. The executing lane's CLAIM then carries
  `consent=docs/tracking/ROLLING_WORK_LEDGER.md:<line>` (rule 18). A line number goes stale when
  the ledger rolls, so the CLAIM text also names the row as `operator consent <ts> lane=<lane>`.

## Dry run

Under `ONEX_DRY_RUN=1`, `registry_root` is a sandbox registry root and `ONEX_LEDGER_PATH` points at the
sandbox's scratch copy of the ledger. The sandbox's `session.env` is written by the same
`session.py init` that `/omni:way-of-working` runs, under `$registry_root/.claude_scratch/sessions/`.
The guard in section 0 refuses anything else. Rows are appended to that copy by the same
`onex-ledger`, so the grammar and the guards still run. `ruling_rows.py` never reads or writes
the ledger in any mode: it prints rows and writes only the `--out` file in your scratchpad.
Nothing is committed, dispatched, sent or merged.

If the guard refuses, stop and report which variable is wrong. Do not re-point `registry_root`
yourself: the guard exists to catch exactly that mismatch. A user-level Claude settings `env` block
that sets `registry_root` overrides the launching process's value in every Bash call. A dry-run harness
therefore passes the sandbox values with `claude --settings '{"env":{...}}'`, which takes precedence.

## Known follow-up

**Typed ledger cutover.** The typed work ledger replaces the markdown file: `onex-ledger` in
`ops_tooling_pkg`, from the plan `beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in
docs_repo. When it lands, the append line in `## Ledger` is the one line that changes
here. The consent read-back becomes an event-id lookup. The reads this skill routes to change inside
their own skills.

## Known friction

- **One call sat for five minutes with no output, and a bad argument took a minute to come back.**
  The scripts ran in 0.6 seconds (a refusal) and 6 seconds (a row), but each of the fork's three
  tool calls paid 60 to 175 seconds of per-call hooks on a host at load 90 to 120, and nothing said
  which step was running. The directory is now made at load (two tool calls, not three), bad
  arguments are refused before the ledger read, and each step prints a `STEP` line under a time
  budget, with a `TIMING` line at the end. → FRICTION lane=ruling-skill-diag-1810 (OMN-17427)
- **Three foreground calls were refused on argument shape, each costing a retry:** `--kind consent`
  (the kind must be the first word), `--approved` missing (the scope lists were written into the
  body), and `--amends` on a consent (only a ruling took it). The kind is now also accepted as
  `--kind`, a consent takes `--amends <ts>` (checked against the ledger), and every fixable refusal
  ends with an `EXAMPLE` built from the caller's own arguments. → OMN-17427
- **Invoking the skill still put Bash calls in the orchestrator's foreground,** because the skill was a recipe the caller ran. The skill now runs itself in a forked subagent when invoked with arguments (the first section). → operator instruction 2026-09-26 (OMN-19821)
- **Process rulings were recorded and then forgotten,** because nothing named what enforced them
  (batching change-control companions, the one landing lane, lanes not polling GitHub, public-work
  plans to the public knowledge base). A process ruling now names its mechanism or is refused, and
  queue-status and the session preflight list the ones that do not. → section 3a (OMN-19854)
- **Recording a ruling took 3 tool calls.** It is now one command, `record.sh`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

New friction goes through `/omni:friction-record`: one FRICTION row, then a one-line pointer here,
before your TERMINAL.

- **An ask citing the rolling ledger was refused for every line.** The source check resolved a
  5,568-line copy of the ledger while the live one held the cited lines 10930, 11759 and 14221, so
  each read as outside the file. A ledger citation now reads the row writer's ledger. → section 1;
  FRICTION 2026-10-14T18:09:56Z lane=orchestrator-bb1a (OMN-16177)
- **Answered asks stayed in the operator's inbox.** An answer wrote a RULING and nothing closed the
  MSG it answered, so stale asks buried the open ones. The answer now writes the ACK. → section 3;
  RULING 2026-10-14T18:04:24Z lane=orchestrator-bb1a (OMN-16177)

- **A ruled decision whose meaning lived only outside the ledger** could not be read by the next
  lane. Every answer is now a row, words verbatim, before the turn ends. → section 3; FRICTION
  2026-09-24T10:48:02Z lane=ops-tooling-pkg-reconcile (OMN-19212)
- **Questions that were not questions:** a settled fact confirmed, a derivable decision escalated, a
  question with no recommendation. The usual answer was "go with your recommendation", which meant
  the question should not have been asked. → section 1; prompt-history mining for OMN-17427
- **Bare numbers in questions.** The operator cannot rule on a ticket or PR number alone. Name each
  thing in words. → section 2; prompt-history mining for OMN-17427
- **The ruling guard names one open ruling per refusal,** and a ruling set recorded as several rows
  on one subject needs every sibling cited. → section 5; FRICTION 2026-09-23T14:30:26Z
  lane=omn17427-foreground and 2026-09-23T12:34:51Z lane=omnihome-cleanup (OMN-18258)
- **A dry run met the real `registry_root`** because a shell profile or the user-level settings `env`
  block reset it. Section 0 now sources `session.env`, which restores the root, before the guard,
  and the Dry run section says to stop and report. → FRICTION 2026-09-24T16:12:49Z
  lane=orch-skill-fan-out-r2 (OMN-17427)
- **The tool marked unrelated rulings amended.** `record.sh` added `--amends` for every open ruling on
  the ticket and the executor rebuilt guard refusals the same way, so the Jev credential-store
  ruling (2026-09-27T14:31:57Z) and the runtime-lane ruling (14:31:58Z) read as amended by two .202
  rulings filed under the same tickets. Each open ruling is now named by the caller, and
  `--unrelated` acknowledges one without amending it. → section 5; CORRECTION rows
  2026-09-28T01:52:55Z and 2026-09-28T01:52:56Z lane=fix-x-followups-83 (OMN-17427)
- **A relay that cites the ruling with `re=` or `ruling=` acknowledges it** on the receivers' behalf.
  The ruling guard then no longer protects the subject, so the relay cites the ruling in its text
  only. → section 4; round-1 build of this skill (OMN-17427, OMN-18258)
- **Several questions built in one second got the same id,** the first append was refused, and a
  hand-written workaround put rows out of order. `--add` now stamps each row after the file's
  newest. → section 2; FRICTION 2026-09-24T17:11:46Z lane=orch-skill-operator-ruling-r2 (OMN-17427)
