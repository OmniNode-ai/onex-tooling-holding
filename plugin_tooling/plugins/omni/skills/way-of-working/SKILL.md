---
name: way-of-working
description: Load FIRST for "start my session", "I'm new here", "usage limits reset", "restarted", "I'm back" and "how does this team work", before session-resume, which this skill calls itself once preflight and the session CLAIM are done (resume depends on both). It is the front door to an orchestration session with the rolling ledger as the backbone, CLAIM to TERMINAL, RULING and OPERATOR-CONSENT for the operator's words, MSG between lanes, one MSG hands a PR to the landing lane, and a routing table with one skill per situation. Also use at a checkpoint, handoff or end of day.
prosthetic: true
replaces_when: "A session-start node validates the environment, claims the session lane and runs the resume check without a prose procedure, and a per-turn hook runs the inbox check for the session lane and its handed-off lanes, on two consecutive weeks of sessions with no dangling session CLAIM and no operator-relayed lane message. Nothing today does either unprompted."
restored_from: "none. New process, distilled from the orchestration-skills catalog (round 2) and the standing lane rules block; it routes to the existing ledger skills rather than restating them"
ticket: OMN-17427
---

# Way of working (prosthetic)

This is the front door. It teaches one way to run a session and hands each situation to one skill.
The rolling work ledger is the backbone. Work begins with a CLAIM and ends with a TERMINAL. The
operator's words become a RULING or an OPERATOR-CONSENT row. Lanes talk through MSG rows. A PR
reaches the landing lane through one MSG. The foreground dispatches, reads, decides and reports,
and nothing else.

Assume you are one of several sessions and many lanes running at once. Every rule below exists
because two of them collided.

**The start order is fixed.** Every session start runs section 2 steps 1 to 5 in order, and a
usage-limit reset, crash or restart changes none of it. Do not jump to `session-resume` first: it is
step 4, and it depends on steps 1 to 3. If `session-resume` is already open, stop it here and start
at step 1. Its positive control looks for this session's CLAIM
(step 3) as live, and its STATUS row is written under this session's lane (step 3).

**You decide, then report.** At session start the operator is asked at most one question: the goal
ticket, and only when none was named. The lane name, the cost estimate, the outage time and each
dead lane's verdict are yours to decide from the rules below; decide them, write them down and
report them. A question the rules already answer costs the operator a turn and stalls the session.

## 0. Dry-run guard (run first, every time)

```bash
registry_root="${registry_root:?set registry_root to the registry root}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
```

A dry run happens only inside a sandbox registry root: a scratch `registry_root` holding copies of the
ledger scripts and a ledger of fixture rows, marked by `.dryrun-sandbox`. Under `ONEX_DRY_RUN`:

- This session's own rows are written, into the sandbox ledger, through the same `onex_ledger.py` (the sandbox copy). A row that acts for another lane (a TERMINAL closing a dead lane, a relaunched lane's CLAIM) is printed, not appended.
- Briefs are written to files and never dispatched. No Agent, Workflow or SendMessage call.
- Every GitHub or Linear mutation is printed, not run. Reads are `gh pr view` and `gh auth status` only.
- The dangling-CLAIM reconciler runs with `--report`, never `--apply`.
- The ownership check is per PR (one `gh pr view` per PR the dangling CLAIMs name), never an org-wide search and never a check-run read.

If an installed `session-resume` predates these dry-run branches, apply the last two substitutions
yourself when you follow it.

If the guard refuses although you were told this is a sandbox, check `registry_root` first: a shell
profile can set it back to the real registry in every tool call. Set it to the sandbox root at the
head of each block until step 3 records it, and never "fix" the refusal by removing the guard.

## 1. Posture: six rules

Each is one line with its reason. The authority is `$registry_root/CLAUDE.md`; read it, not this.

1. **The foreground only orchestrates.** It dispatches, reads, decides and reports; building in the foreground blocks every other decision and burns the context the session needs (Workflow and background lanes are the default).
2. **The ledger is state history.** Nothing starts without a CLAIM or ends without a TERMINAL, because a lane that dies silently leaves scope nobody may touch.
3. **Verify live, never trust a report.** A lane's "done" is a claim until `gh`, `git` or the ledger confirms it (operating rule 3).
4. **Merged is the only terminal state of a PR, and one repository drain lands it.** The operator ruled that one drain per repository owns PR landing, because parallel CI watching exhausts the shared GitHub quota; every other lane hands its PR over with one MSG and stops (section 5.4).
5. **The lab comes first.** A runtime change is proven on the lab before staging (operating rule 24).
6. **Hard gates stay hard.** Prod promotion, credential rotation, destructive actions outside the approved scope and unsolicited architecture changes each need their own approval (operating rules 2, 2a, 12, 22); a standing autonomy grant never covers them.

## 2. Session start

Do these in order. Stop at the first blocker and print its fix line. Shell state does not survive
between tool calls, and a shell profile may reset `registry_root` in each one, so after the command open
each block by sourcing the literal `SESSION_ENV` path it printed: `set -a; . "<SESSION_ENV path>"; set +a`.
That restores the session lane and the registry root the session started with.

1. **Goal ticket.** The session CLAIM needs one `OMN-` ticket. Use the one the operator named. Only if none was named, ask once, in one plain question.
2. **Cost values.** Set them yourself; never ask for them. `--est-hours` is your estimate of the session's lane-hours: 2 for a session that opens with a resume, 4 for a full working session, or your own better number. `--displaces` names what this session pushes back: the next queued item from the last digest you read, or `nothing queued` when there is none.
3. **Open the session.** Pick the purpose yourself (`orchestrator` when nothing better fits), then run:

   ```bash
   bash "${CLAUDE_SKILL_DIR}/scripts/session_start.sh" --purpose <purpose> --ticket <OMN-n> --est-hours <N> --displaces "<step 2 value>" --actor "claude:<model>:foreground" --model "<model id>" --scope "<one line: what this session orchestrates>"
   ```

   It runs the session lane, preflight, host-mode, catchup, inbox, dangling-claim check, CLAIM and session files in one call. The preflight receipt stays at `$registry_root/.claude_scratch/sessions/<lane>/preflight.json`, under the registry root and never in a system temp directory. Read its one `SESSION` line: it gives the lane, claim timestamp, host, warning count, digest and inbox counts, dangling count, `SESSION_ENV`, and the detail file. `BLOCKED preflight` stops the session with nothing written: print the line and its `FIX`, repair what it names and rerun; never route around it. Preflight validates `registry_root`, `ONEX_LEDGER_PATH` (set, named `ROLLING_WORK_LEDGER.md`, and the registry file itself), the ledger grammar, `gh` login and `DOCS_REPO_PATH`. A warning (`preflight=ok+<n>warn`; the receipt names each one) does not stop the session: mention it once in the report, and repair it only when this session's work needs that surface. `REFUSED` and `RETRY` carry their own fix line: apply it and rerun. The detail file holds the full digest and the inbox rows: open it only when a count on the `SESSION` line needs a look (a HOLD in force, an inbox action item), and never print or page through the ledger file itself, which runs to thousands of lines. `dangling=` counts CLAIMs with no closing row in the reconciler's seven-day window; the live ledger always carries some, so it is not by itself a reason to resume. The scope may name the goal PR: the session owns a PR its CLAIM names or whose ticket it carries, and hands it off without closing this CLAIM (section 4).
4. **Resume, when the session opened after a usage-limit reset, a crash or a restart.** Only now, with the CLAIM appended and `session.env` written, invoke `session-resume` (the copy in the same plugin as this skill) and follow it with this session's lane as `<your lane>`. Decide as it says, without asking:
    - **The outage time** (`T0`) is the reset or restart time. Take it as `session-resume` step 1 says, from the last rows lanes wrote before this session (the catchup digest in the step 3 detail file shows them) and the operator's message. Never ask for it.
    - **A dead lane whose PR merged** is `landed`: its CLAIM is closed.
    - **A dead lane with work left** (no PR, a draft, a dirty worktree) is `relaunch`, as `<its lane>-r`. Use `released` only when the operator said that work is no longer wanted.
    - **Each relaunch gets a brief file.** Compose the CLAIM template with `session-resume` step 4, then write the brief:

      ```bash
      python3 "${CLAUDE_SKILL_DIR}/session.py" relaunch-brief --lane <lane> --new-lane <dead lane>-r \
        --dead-lane <dead lane> --dead-claim <its CLAIM stamp> --t0 <T0> \
        --claim-template "<the one CLAIM line step 4 printed>" --scope "<one line: its unfinished work>"
      ```

      Step 4's compose command carries `--claim-only`, so its stdout is exactly that one line; paste
      it whole. A pasted block that still holds the `ROUTE=` line is reduced to its one CLAIM line,
      and a value with no CLAIM line or with two is refused.
      It prints `BRIEF=<path>`. Lint it with `session-resume` step 4's `--lint-brief`. In a live session, hand the file to `lane-brief` and dispatch through `fan-out`. In a dry run the file is the result, and it is never dispatched.
    - **Under `ONEX_DRY_RUN`**, run `session-resume`'s Ledger block with its STATUS row only (`lane=<your lane>`, `T0=`, `dangling=`, `relaunched=<the -r lanes, briefed>`, `dry_run=1`). Print, and do not append, every row it would write for another lane: the TERMINAL closing a landed lane, a handoff or notice MSG, a RELEASE.

    Only after `session-resume` step 5 do you take new work.
5. **Report, in plain words.** Say what preflight found, the session lane, each dead lane with its verdict and next move (the PR by what it does, not only its number), the rows written and where, and the first thing you would do next. End on that first move, not on a question: when the goal ticket's scope is unknown, the first move is reading the ticket. No row syntax in the reply.

## 3. Every turn

At the start of every turn, and immediately before any irreversible action (push, merge, arm, deploy, delete):

```bash
set -a; . "<SESSION_ENV path>"; set +a
HANDED="$(python3 "${CLAUDE_SKILL_DIR}/session.py" lanes --lane "$SESSION_LANE" --state handed-off | paste -sd, -)"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" inbox "$SESSION_LANE${HANDED:+,$HANDED}"
```

One call prints one count line per lane (`inbox <lane>: <n> open, <a> need action (HOLD:<x> ask:<y>), <b> FYI`) and the action items under it; the full rows are in the detail file it names. A lane that handed off its PR has stopped, so the landing lane's reply about a real red lands in
that lane's inbox, and you read it for it. A real red goes to `fan-out` as a fix lane. The operator
never relays a message between lanes or tools: when they do, answer only what is new in it, then
fix the channel so the next one arrives on the ledger.

## 4. Where each situation goes

One skill per situation. Do not re-implement any of them here.

| Situation | Skill |
| -- | -- |
| New work, a plan to execute, tickets to do, a red that needs a fix lane | `fan-out` |
| A brief for one lane | `lane-brief` |
| A lane reported back | `verify-claims` |
| A PR is ready | `pr-handoff` (one MSG to the landing lane, sent through `ledger-msg`) |
| A PR this session's own lane owns is ready | `pr-handoff` in session-lane mode (`MODE=session`: the MSG, then a STATUS `handed-off=<repo>#<n>` on the session CLAIM, never a session TERMINAL) |
| A question for the operator, or the operator's answer, consent or hold | `operator-ruling` |
| Status, what happened while away, what is next | `operator-status` |
| A restart, crash or usage-limit reset | `session-resume` |
| A binding message to another lane, a lane HOLD, the inbox | `ledger-msg` |
| What happened on the ledger recently | `ledger-catchup` |
| Any other row to append | `ledger-write` |
| A plan to write | `plan-write` |
| A ticket to create | `create-ticket` |
| A ticket to implement end to end | `ticket-pipeline` |
| Friction that cost more than a few minutes | `friction-record` |
| A question about a past decision or a runbook | `kb-ask` |
| Who is waiting on the operator for a reply (Slack and Linear) | `awaiting-reply` |
| The environment at session start | `preflight` (onex) |
| The prose handoff at a session boundary | `handoff` (onex) |
| Pure-text work a local model can do | `delegate` (onex) |

A name marked (onex) is `/onex:<name>`; every other name is `/omni:<name>`. Before any raw
dispatch, look for an existing skill that already does the job (operating rule 1). No skill here
lands a PR: landing belongs to the landing lane (section 5.4).

A PR the session lane itself owns (the session CLAIM names it, or it carries the goal ticket) never
goes through plain `pr-handoff`: its TERMINAL would close the session CLAIM and end the session.
Hand it off with `MODE=session` (`pr-handoff` section 3a) as soon as it is ready, without asking the
operator: the MSG goes to the landing lane, a STATUS `handed-off=<repo>#<n>` under the session lane
releases the PR in the landing lane's owner map, and the session CLAIM stays open. The landing lane
answers a red to the session lane, whose inbox section 3 reads every turn. A block refusal names
its fix; apply it and run the block again.

## 5. The ledger in one page

The ledger is `$ONEX_LEDGER_PATH`, which preflight holds equal to
`$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md`. It is appended through `onex_ledger.py`,
never edited by hand. Read the grammar live, never from a copy:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$ONEX_LEDGER_PATH" --print-grammar`.

### 5.1 Which row, when, and who writes it

| When | Row | Written by |
| -- | -- | -- |
| Session start | CLAIM (`lane=`, `ticket=`, `actor=`/`model=`, cost sentence) | this skill |
| Lane start, before its first write | CLAIM (plus `repo=`/`pr=`/`worktree=`, `consent=docs/tracking/ROLLING_WORK_LEDGER.md:<line>` for consent-bound work, `parent=<dispatching lane>`) | the lane itself; the orchestrator never claims for a lane |
| A dispatch wave | STATUS (`lanes=`, `tickets=`, `model=`) | `fan-out` |
| A checkpoint | STATUS | the lane; this skill for the session |
| A countersign of a lane report | STATUS (`countersigns=`, `verdict=`) | `verify-claims` |
| An earlier row was wrong | CORRECTION (cites the row by timestamp and lane) | whoever finds it |
| Friction costing more than a few minutes | FRICTION (a second occurrence files a ticket) | `friction-record` |
| The operator decides | RULING (the words verbatim; `amends=` when a ruling already stands) | `operator-ruling` |
| Consent-bound work | OPERATOR-CONSENT (APPROVED SCOPE and OUT OF SCOPE, before acting) | `operator-ruling` |
| Stop or resume | HOLD / RELEASE | `operator-ruling` for the operator's; `ledger-msg` for a lane's |
| Between lanes | MSG / ACK | `ledger-msg` |
| A PR is ready | MSG to the landing lane, then TERMINAL `outcome=handed-off` | `pr-handoff` |
| The session's own PR is ready | MSG to the landing lane, then a STATUS `handed-off=<repo>#<n>` under the session lane (never a session TERMINAL) | `pr-handoff` session-lane mode |
| The end | TERMINAL (`friction=`; FRICTION rows first) | the lane; this skill for the session |

Cite a row by its leading timestamp and lane in prose, a CORRECTION, an ACK or a relay MSG: a roll
renumbers every line. The one exception is `consent=`, which keeps the path-and-line form operating
rule 18 fixes (section 5.4), because the readers that resolve consent parse only that form.

### 5.2 Reading

Every decision read goes to an existing reader: the `catchup` verb, the `inbox` verb, ownership and the newest RULING rows before a dispatch (`lane-brief` step 1), and
dead lanes (`session-resume`). For anything else (a lane's rows, a PR's rows, a ticket's rulings,
the holds on a PR) use `onex_ledger.py query` or `onex_ledger.py holds`, which print a count and a
few short rows and put the rest in a detail file. Never grep the raw ledger, and never write a new
parser of prose rows.

### 5.3 Append exit codes

- **65** is a lint refusal. Read the message, fix the row, append again. Never retype it under a legacy type, and never bypass the lint.
- **75** is a lock timeout. Append the same row again; the dedup window makes the retry safe.
- **0** prints a claim token for a CLAIM. Keep it only if a later step asks for it.

### 5.4 Consent and landing

- A MSG is never consent. Consent is an OPERATOR-CONSENT row with both scope lists, recorded by `operator-ruling` from the operator's own words before the work starts. The executing CLAIM cites it as `consent=docs/tracking/ROLLING_WORK_LEDGER.md:<line>`, the form in operating rule 18 and the committed lane rules block; the decisions register and the credential-rotation guard (whose `ROTATION-CONSENT:` line takes the same form) resolve only that. Add the consent row's timestamp and lane in the CLAIM's text when you want a citation that survives a roll, never in place of the path and line. The grammar refuses a consent-shaped MSG.
- One drain per repository lands PRs. Under RULING `2026-09-25T14:34:28Z lane=merge-drain-83`, a PR in `<repo>` goes to `repo-drain-<repo>`. A change of routing model is a new RULING recorded through `operator-ruling`, and the newest one stands; `ledger-catchup` lists the RULINGs in its window.
- Every other lane may write code, open a PR and push fixes. After its push it sends ONE MSG to that PR's repository drain naming the PR, its head sha and what it needs (`pr=`, `head=`, `needs=land|train|companion`), writes its own TERMINAL `outcome=handed-off`, and stops touching the PR: no merge, arm, hold-label removal, rerun, update-branch, CI watch or check-run polling, and no chasing change-control companions. `pr-handoff` does this through `ledger-msg`.
- A real red comes back from the landing lane as a MSG to the lane that wrote the PR; section 3 reads it, and `fan-out` turns it into a fix lane.

### 5.5 Detached host

The ledger is one working-tree file on one coordination host. Preflight's `coordination_host`
blocker, or host mode `detached` or `unknown`, means the landing controller is not live on this host
or does not write to its ledger. Every preflight check blocks (RULING 2026-10-21T18:21:36Z), so a
session does not start here: run the check's fix line, or start on the coordination host. A lane
already running on a host that became detached follows these rules:

1. The local ledger coordinates only this person's own lanes.
2. HOLD, MSG and CLAIM rows written here reach nobody on the coordination host, so never touch a shared surface from here: the lab lanes, the lab hosts or the clusters.
3. Rulings reach this host only through the committed rules block, by pulling the registry.
4. A PR from here is left open and ready, with one ticket and its lab proof, and is never merged, armed or polled. A MSG written here does not reach the landing lane; it owns landing org-wide and finds open PRs on its own sweep.

## 6. Session boundary (a checkpoint, a handoff, end of day)

1. **Lanes.** For every lane in `lanes.txt`, find whether it still holds an open CLAIM, from the digest rather than the ledger:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" catchup --since "$CLAIM_TS" --cap 500
   python3 "${CLAUDE_SKILL_DIR}/session.py" boundary --lane "$SESSION_LANE" < "<detail path from catchup>"
   ```

   Each `OPEN` lane must be live in `ListAgents`, or be closed by its own TERMINAL, or be handed to `session-resume` in the next session. Never write another lane's TERMINAL, and never declare a lane dead in a message; a finding goes in a row.
2. **Checkpoint STATUS.** Write the in-flight lanes, the HOLDs this session placed, and the next action with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row STATUS ... --kv lanes=... --kv next=...`.
3. **Handoff.** At a handoff or end of day, run `/onex:handoff` for the prose pointer.
4. **Session TERMINAL.** Record each real friction first with `/omni:friction-record`. Then write it with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row TERMINAL ... --closes-claim "$CLAIM_TS" --friction <none, or one line naming those FRICTION rows>`. A checkpoint that is not the end writes only the STATUS.

## Ledger

The `row` verb is the one append path for this skill. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row <TYPE> ...` for each typed row; it prints `OK` with the timestamp, line and detail path, or `REFUSED`/`RETRY` with its fix.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" row <TYPE> --lane "$SESSION_LANE" ...
```

In a dry run, the verb writes only to the sandbox ledger.

**Known follow-up: the typed ledger.** The markdown ledger is being replaced by a typed JSONL ledger
(`onex-ledger` in `ops_tooling_pkg`; plan `beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md`
in the planning corpus). When it lands, the append line above is the one line of this skill
that changes. The reads change inside the readers this skill routes to.

## Anti-patterns

- **A session opened only to check tool health.** Use the CLI (`claude mcp list`); a session that probes and stops is noise.
- **A standby peer session with no role.** Give it a scoped role in its session CLAIM, and have it record what it does as rows, or do not open it.
- **SendMessage to a peer lane.** It resurrects a stopped lane and it spends. The channel is a MSG row; the orchestrator relays.
- **Relaying a lane's report unverified.** Route it through `verify-claims` first.
- **A lane that lands, arms, reruns or watches CI on its own PR.** One MSG to the landing lane, then stop (section 5.4).
- **Asking the operator to review a PR.** A PR ends when it is merged, not when a person has read it.
- **Answering "what is the state" from a handoff table.** Read live.
- **A foreground build, "just this once".** Dispatch it.
- **Flagging a broken environment without repairing it.** Preflight prints the fix; run it, then rerun preflight.

## Known friction (from prior runs)

- **Session start took 7 tool calls.** It is now one command, `session_start.sh`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **Required environment was flagged every session and never fixed.** An unset knowledge-base path produced the same warning session after session. Preflight now holds it as a blocker with its fix, and step 2 stops on it. → catalog round 2 (orchestration-skills), mined usage report
- **Lanes died silently at a usage-limit reset** and their CLAIMs read as live scope. Step 10 routes to `session-resume` before any new work. → `session-resume` Known friction
- **A reset prompt loaded `session-resume` instead of this skill.** Its description also claims the first step of a resumed session and names no pointer back here, so on a host with hundreds of installed skills a fresh session told "limits just reset" sometimes skipped preflight and the session CLAIM, wrote no row and stopped to ask the operator (one full-install run in seven in the round-2 verification; every run on a new person's install, the omni and onex plugins only, loaded this skill first). This skill's description now opens with the reset and start phrases and names the precedence. The rest of the fix is not in this skill: `session-resume` must say it runs after this skill's preflight and session CLAIM and point back here, and it ships in the same release. Until then, a session that opens `session-resume` first stops, loads this skill and starts at step 1. → round-2 verification, bare prompt
- **A loaded copy of this skill still jumped from start to resume** and asked the operator for the cost values and for each dead lane's fate. Steps 7 and 10 now say the session decides both, and "You decide, then report" bounds the start to one question. → round-2 test
- **No run wrote its relaunch brief** and each asked whether to relaunch or release. Step 10 now makes `relaunch` the default and `session.py relaunch-brief` writes the file. → round-2 test
- **Consent was cited by timestamp.** An earlier draft taught one citation form for every row, so a lane following it wrote `consent=` with a timestamp that the decisions register and the credential-rotation guard cannot resolve. Section 5.4 now gives the rule-18 path-and-line form, and section 5.1 limits the timestamp form to other citations. → round-2 verification
- **The operator became the relay between lanes.** Section 3's loop over handed-off lanes' inboxes removes the relay. → catalog section 9
- **The shell profile reset `registry_root` in every tool call** during the round-1 dry run, so the sandbox root was lost between blocks. The section 0 guard refused, as it should. `session.env` now records the root, and every block after step 9 sources it. → section 2, round-1 test
- **A dry-run resume read check-runs.** The first round-1 run's ownership check went through the org owner map and issued a `gh api .../check-runs` read. Section 0 now limits a dry run to one `gh pr view` per PR, and the next run's gh log held only `pr view` and `auth status`. → round-1 test
- **The preflight receipt was written to the system temp directory,** outside the sandbox root, in the 2026-09-24 integration run. Steps 2 and 3 now keep it in the session folder under `registry_root`. → integration run, staging build
- **A dry run that reached the real ledger or the org-wide search** is prevented only by the sandbox registry root and the guard in section 0; the readers still build some paths from `registry_root`. → catalog section 2.6
