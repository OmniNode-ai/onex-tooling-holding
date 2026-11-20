---
name: fan-out
description: Turn a task into background lanes the way this team works. Inventories ownership through the existing readers (the lane-brief ledger grep, one gh pr view per PR, ListAgents, the skill list, kb-ask), sends one MSG to any live owner instead of dispatching a second lane, shapes one lane per independent unit with its model and effort named, writes every brief through lane-brief with the section 3a Constraints block, runs long jobs detached with a progress file, and records each wave as one STATUS row and in the session's lanes.txt. Use for any work beyond reading a plan or talking to the operator - "execute the plan", "pick up X", "do these tickets" - and when the landing lane returns a red that needs a fix lane.
prosthetic: true
replaces_when: "/onex:lane_dispatch dispatches one committed, named brief per call and does no ownership inventory, no section 3a Constraints block and no wave STATUS. Its overlay does resolve (through ONEX_SKILL_OVERLAY_ROOTS), so that is not the gap. Retire this prosthetic when lane_dispatch, on three consecutive waves, runs the ownership check, pastes the 3a readers' output into each brief and appends the wave STATUS by itself."
restored_from: "none. New process, distilled from the orchestration-skills catalog (round 2); it routes to lane-brief, ledger-msg, ledger-catchup and merge-drain rather than restating them"
ticket: OMN-17427
---

# Fan-out (prosthetic)

The foreground orchestrates; lanes do the work. This skill turns a task into background lanes:
one lane per independent unit, none on work another live lane already holds, each with a brief
that carries the standing constraints verbatim. It dispatches, records the wave, and stops. It
never builds, merges, arms or polls anything itself.

Landing is not part of this skill. The launchd landing controller lands every open PR with no model
in the loop, under the standing routing RULING (2026-09-29T06:34:17Z, lane=`orchestrator-83`); the
target for every repository is `landing-controller`, and no repo drain runs. fan-out never
dispatches landing work, and every brief it writes tells the lane to hand a ready PR to the landing
controller by one ledger MSG and stop, and to treat a controller escalation of its PR as its signal
to fix, never to arm or merge.

Assume parallel sessions and many lanes are running. Every step below exists because two lanes
once collided, or because a rule told to the orchestrator never reached a lane.

The helper is `scripts/wave.py` in this skill's directory (`--help` lists every subcommand). It is
read-only except for three scratch writes you name (`manifest`, `record`, `progress`, each with
`--print` to write nothing). `name` mints lane names and writes nothing. It never opens the ledger, never calls `gh` and never dispatches. It
routes every read to an existing reader: `lane_brief.py grep`, `rulings` and `constraints`
(`/omni:lane-brief`), `inbox.sh` (`/omni:ledger-msg`), and `drain_map.py --only-pr`
(`/omni:merge-drain`) when that form exists. `preflight` also reads `lane_brief.py constraints
--help` and blocks when the section 4 command below no longer fits it. Its tests are
`tests/test_fan_out.py`, and `tests/sandbox.sh` builds the dry-run sandbox they use.

## 0. Guard, session and inbox (run first, every time)

Shell state does not survive between tool calls, so open **every** block in this skill with these
lines, writing the session lane literally:

```bash
registry_root="${registry_root:?set registry_root to the registry root}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
set -a; . "$registry_root/.claude_scratch/sessions/<session lane>/session.env" || exit 2; set +a
W="${CLAUDE_SKILL_DIR}/scripts/wave.py"; LB="${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lane_brief.py"
S="$registry_root/.claude_scratch/sessions/$SESSION_LANE"
```

Then, once per invocation:

```bash
python3 "$W" preflight --plugin-root "${CLAUDE_PLUGIN_ROOT}"; echo "preflight rc=$?"
python3 "$W" inbox
```

- **No `session.env`, no fan-out.** It is written by `/omni:way-of-working` at session start and
  names the session lane every wave row carries. A missing file is a `BLOCKER` naming that fix.
- Any `BLOCKER` line stops the skill. Print the line and its fix, and do nothing else. A
  `BLOCKER lane-brief: interface drift` line means section 4's command would exit 2 and write no
  3a: record it with `/omni:friction-record` and stop; never patch the command inline to get past it.
- A `DEGRADED` line is not a stop. Carry it into the premise table of every brief it affects.
  The usual one is `drain_map --only-pr: absent`: PR ownership then comes from `owners` plus one
  `gh pr view` per PR.
- The inbox is binding. A HOLD or MSG addressed to the session lane or to `to=all` that pauses
  dispatch, or the repos in this task, stops this wave. Report it, and do not work around it.

**Dry run.** Under `ONEX_DRY_RUN`, inside a sandbox registry root only:
- each Bash call starts from the user's shell profile, which can set `registry_root` back to the real
  registry root. So open every block with one literal line that exports the sandbox values:
  `registry_root`, `ONEX_LEDGER_PATH`, `ONEX_DRY_RUN=1`, and `PATH` with the sandbox `bin/` first.
  Without that line the guard refuses, which is its job;
- briefs are written to files and never dispatched, and there is no Agent, Workflow or SendMessage call;
- the wave's own rows (the MSGs and the STATUS) are appended, into the sandbox ledger, through the same `onex-ledger` resolver;
- `lanes.txt` gets the would-be lanes, each marked as not dispatched;
- GitHub reads are `gh pr view` and `gh auth status` only, and nothing is mutated;
- `/omni:kb-ask` and `/onex:delegate` are skipped, because both run on the lab route. Note each skip in the report;
- a premise that needs Linear or a clone the sandbox lacks is written `UNVERIFIED (dry run)`.

## 1. Inventory: route every question to an existing reader

List the units of work first: each ticket, PR, plan task or worktree the request names. Then
answer each question below with the reader named, never from memory:

**Never open the ledger yourself.** No `cat`, `grep`, `rg`, `head`, `tail`, `sed`, `awk` or Read
tool on `$ONEX_LEDGER_PATH`, on `ROLLING_WORK_LEDGER.md` or on its `archive/` rolls, in any step.
The live file is several megabytes: one hand read fills the context and still misses the rolls.
Every ledger question has a reader: `python3 "$W" owners` and `python3 "$LB" grep '<text>'` for
rows naming an item, `python3 "$LB" rulings` for RULING rows, `python3 "$W" inbox` (`inbox.sh`)
for MSG and HOLD rows to a lane, and `/omni:ledger-catchup` (`catchup.sh`) for the recent window.
If no reader answers the question, record it with `/omni:friction-record` rather than reading the file.

| Question | Reader |
| -- | -- |
| Does a lane already hold ticket or worktree X? | `python3 "$W" owners <items...>` (runs lane-brief step 1.4, `lane_brief.py grep`, over the live file and its rolls) |
| Does a lane hold PR `repo#n`, and what state is it in? | `python3 "$W" owners <repo#n>` for the ledger owner. For live state: `drain_map.py --only-pr <repo#n> --out "$S/drain"` when preflight listed that form, otherwise one `gh pr view <n> --repo OmniNode-ai/<repo> --json state,isDraft,headRefOid,labels`. **Never run `drain_map.py` without `--only-pr`**: that form searches the whole org and spends the shared GitHub quota. |
| Which lanes are running now? | `ListAgents` (the live count for the 15-lane cap). Pass their names to `owners --live-lanes`. |
| Does a skill already do this job? | The skill list: `/omni:` and `/onex:` (operating rule 1). A ticket goes to a lane that runs `/omni:ticket-pipeline`; a plan goes to `/omni:plan-write`. Fan out to the skill, not around it. Landing is never a fan-out unit: a "merge", "land" or "drain the PRs" request is the landing lane's work, so it goes to that lane as one MSG per PR (`/omni:pr-handoff`), never to a lane of this wave. |
| Is there already a plan or decision for this? | `/omni:kb-ask` (invoke without args, then ask). Skipped in a dry run. |
| Which lane lands PRs, and what else is ruled? | `python3 "$LB" rulings --tail 15`, the newest RULING rows. Pin the landing RULING's lane cell and timestamp from it (section 4). |
| What do the ticket and PR say right now? | `get_issue`, `gh pr view` — one read per premise, recorded in the brief's premise table (lane-brief step 1.3). |

## 2. Ownership: one verdict per item

`owners` prints one line per item. Act on the verdict, not on a guess:

| Verdict | Meaning | Action |
| -- | -- | -- |
| `OWNED-LIVE` | an open CLAIM (no later TERMINAL) whose lane wrote a row in the last 45 minutes, or is in `ListAgents` | **Do not dispatch.** Send the owner one MSG (the Ledger section), and list the item as routed. |
| `OWNED-LIVE`, and `actor=` names another person or tool | the item belongs to someone else's lane | the same MSG to that owner. Keep it off the operator's list: the owner answers by MSG. |
| `OWNED-STALE` | an open CLAIM whose lane has been silent past the window | not a fresh lane. Route it to `/omni:session-resume`, which relaunches with a supersedes pointer. |
| `SELF` | this session's own CLAIM | dispatchable |
| `UNOWNED` | no CLAIM names it in a `ticket=`, `pr=` or `worktree=` cell | dispatchable |

- An item the operator or a RULING put out of scope is dropped. Name it in the report.
- `owners` also prints a `note` line when other rows mention the item only in prose. Read those rows (the `at=` pointer) before you dispatch.
- Two live lanes on one item is friction: record it with `/omni:friction-record`.
- Work that routes to an owner never goes to the operator. The operator is not a relay between lanes.

## 3. Shape the lanes

**One lane per independent unit.** Units that touch the same files or the same PR go in one lane;
everything else runs in parallel. Wave size is capped: the running lanes (`ListAgents`) plus this
wave's lanes stay at or under **15**, per the standing ruling. Overflow waits for the next wave.

**Name each lane with the helper, never by hand.** The suffix is random on every call, so two
sessions briefing the same ticket never share a `lane=` name and ledger ownership stays unambiguous:

```bash
python3 "$W" name OMN-<a> OMN-<b>    # prints one "<item> lane=<unit>-<4 random hex>" line per item
```

Copy each printed name as it is. Never type or reuse a suffix, and never take one from an example
or an earlier wave. The name is the lane's `lane=` everywhere.

**Model and effort are named per lane, never inherited.** A delegated lane does not see the
orchestrator's model, so an unnamed model is a silent downgrade or upgrade:

| Work | Model | Effort |
| -- | -- | -- |
| anything that must be true (code, tickets, PRs, verification) | sonnet (the floor) | `medium`; `high` for cross-repo or unfamiliar code |
| diagnosis: a red nobody understands, a root cause, a design question | opus | `high` or `xhigh` |
| pure text: summaries, drafts, classification with no side effect | `/onex:delegate` on the lab first, GLM through Claude Code (`/omni:harness-delegate --harness claude-glm`, or `delegation_step.py text` for both rungs) second; the cloud-glm backend pin is retired (OMN-20173). A Claude lane only when the delegate result fails its check. | `low` |
| typed decisions with a fixed answer set, every repository but docs_repo (RULING 2026-10-13T18:34:53Z) | Jev, through `node_typed_decision_effect` (lane-brief 3a.9) | n/a |
| self-contained code: mechanical edits, test scaffolds, conflict drafts | Codex first through `delegation_step.py code` (no model flag), then the lab: crush on the lab model through lane-brief's `scripts/lab_crush.py`, then one GLM draft through Claude Code (`/omni:harness-delegate --harness claude-glm --task-class code_generation --writable-repo <worktree>`); the lane reads the diff, runs focused tests and owns the PR (operator ruling 2026-09-30, OMN-20106) | `high` |

- Every lane's brief carries part 3a.9, which routes its own subtasks to Codex, the lab, GLM and Jev (operator rulings 2026-09-28T06:24:10Z, OMN-17427, and 2026-09-30, OMN-20106); `lane_brief.py check` refuses one that drops an engine or passes a model flag to Codex, and queue-status's `delegation-share` line lists the lanes that delegated nothing.
- Heavy work is placed on the pool host with the most free capacity and sent over the event bus (operator direction 2026-09-29, OMN-20101, OMN-20105): every lane's brief carries part 3a.10, which sends test runs beyond one focused file, builds, lint over a tree and headless agent runs through `/omni:lab-run --via bus` (the pool is every lab host plus the launching host, which takes work only under the same load bar; exit 75 when every host is over it); `lane_brief.py check` refuses a brief without it, and the heavy-work guard refuses such a command on a host without headroom. Push the lane's branch before it runs.
- Haiku is removed (operator ruling OMN-17427, 2026-10-01). `check-wave` refuses it for every lane; trivial text work goes to `onex delegate` (local lab models).
- Resolve the concrete model ids from the session environment, not from this file.

**Long jobs run detached.** A job that can outgrow one agent turn, such as a sweep over hundreds
of items, is split into shards. It runs in the background with a progress file, and never runs
in-turn:

```bash
python3 "$W" progress --lane <lane> --shards <n> --print    # drop --print to write it
```

The brief names that `progress.json` path. The lane updates it after every shard and appends one
STATUS row per shard. A relaunch resumes from the first shard not marked done. The reason is
cost: a job recovered by hand every day is a design defect, not routine operations. Fix it once,
and record the friction.

## 4. Write each brief through lane-brief

Follow `/omni:lane-brief` (load it without args) for every lane. It owns the premise check, the
task section, the pasted rules block, the repo deltas and the report contract. This skill adds
only what a wave needs:

- **Pin the routing ruling once per wave.** Find the RULING row whose words establish the
  model-free landing routing (the landing controller), in the `rulings` output from section 1, never from memory. When it has scrolled
  off, widen `--tail` or run `python3 "$LB" grep 'RULING | lane='`. Copy two values out of that one
  row, literally:
  - its leading timestamp, which goes to `--landing-ruling`;
  - its `lane=` cell, which goes to `--landing-ruling-lane`.

  Each brief's `--landing-lane` is `landing-controller`. A newer RULING that changes the routing
  model replaces the authority inputs and target lane together. lane-brief pastes exactly the row
  that begins `<timestamp> | RULING | lane=<lane> |` into 3a.3, and refuses (exit 3) when no such
  row exists, so a mistyped lane or timestamp never reaches a brief. It does not read the ruling's
  words, so read the pasted 3a.3 row of the first brief and confirm it is the landing ruling before
  dispatch.
- **Pin one holds window for the whole wave**, so every 3a is reproducible byte for byte:

  ```bash
  T0="${CATCHUP_T0:-$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '-24 hours' +%Y-%m-%dT%H:%M:%SZ)}"; echo "T0=$T0"
  ```

  Write the printed value literally into each command after this one.
- **Give each lane its own brief file**, `$S/briefs/<lane>-brief.md`. Write the premise table, the task, the ops_tooling_pkg `lane_rules/lane-rules-block.md` rules block (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane_rules_block.py"`) and the repo deltas first. Then append 3a from the helper:

  ```bash
  mkdir -p "$S/briefs"
  python3 "$LB" constraints --lane <lane> --parent "$SESSION_LANE" --landing-lane landing-controller \
    --landing-ruling-lane <routing RULING lane> --landing-ruling <routing RULING timestamp> --ticket OMN-<n> \
    --model <model> --effort <effort> --repo <repo> --actor claude:<tier>:subagent --t0 <T0> \
    --out-of-scope '<what this lane must not touch>' [--consent docs/tracking/ROLLING_WORK_LEDGER.md:<line>] \
    --out "$S/briefs/<lane>-3a.md" && cat "$S/briefs/<lane>-3a.md" >> "$S/briefs/<lane>-brief.md"
  ```

  `--parent` is the session lane. That puts `parent=<session lane>` in the lane's CLAIM template, so the lane's ownership traces back to this wave. The lane writes its own CLAIM from that template; the orchestrator never claims for a lane.
- **The task names the skill the lane runs.** A ticket lane runs `/omni:ticket-pipeline`, with its worktree at `$registry_root/worktrees/<ticket>/<repo>/` and its lab-first step. Where that skill's own steps say to land, arm or watch CI, the 3a.3 sentence overrides them.
- **A lane that produces a PR hands it off and stops.** 3a.3 carries the sentence: after the push, the lane sends one ledger MSG to the landing lane (`pr=`, `head=` sha, `needs=land|train|companion`) through `/omni:pr-handoff`, or `/omni:ledger-msg` where that skill is not installed, then writes its TERMINAL. It never merges, arms, reruns, updates the branch or polls CI.
- **Contract before push (OMN-20864).** Keep the shared 3a.10 pre-push contract step in every PR-capable lane's brief: `contracts/OMN-<ticket>.yaml`, one `dod_evidence` entry per acceptance criterion, and where deploy-gate applies a falsifiable deploy check scoped for the hosted runner. The push is refused without it. `check-wave` uses lane-brief's CI-config-derived repo set and refuses a brief that omits the step.
- **A fix lane for a red returned by the landing lane** gets that MSG's `pr=`, `head=` and the named failure as its premises. It runs on the existing PR branch, and hands the PR back by the same handoff.
- **Holds.** Read the new lane's 3a.1 (its inbox) and 3a.2 (every HOLD in force). A HOLD addressed to the lane or to `all` binds it when the HOLD's `repo=`, `pr=` or `ticket=` cell matches the lane, or when the HOLD has no scope cell.
  - If the hold's own words limit it to merge or landing order, the lane may still build. 3a carries the hold, and the landing lane enforces it at merge time.
  - Any other binding hold: write the brief, and **hold the lane**. Do not dispatch it; name it in the wave's `--held`.
  - When unsure, hold.

**Check the wave as a set before anything is dispatched:**

```bash
python3 "$W" check-wave "$S"/briefs/<lane-a>-brief.md "$S"/briefs/<lane-b>-brief.md \
  --lanes <lane-a>,<lane-b> --running <count from ListAgents>; echo "check-wave rc=$?"
```

It runs `lane_brief.py check --recompute` on each brief, which re-reads `inbox.sh` and
`catchup.sh` and requires 3a to be byte-identical to a fresh read. It also refuses:
- a brief with no `model=` and `effort=`;
- a lane on haiku;
- two briefs on one lane or one ticket;
- a wave over the cap.

Any `PROBLEM` line means do not dispatch. Fix the brief and run the check again.

## 5. Surface large waves, without asking

When a wave has **more than 3 lanes**, or **any consent-bound lane**, write the lane list and
every 3a block to one file, and give the operator its path in one line:

```bash
python3 "$W" manifest --wave <n> "$S"/briefs/<lane-a>-brief.md "$S"/briefs/<lane-b>-brief.md
```

This is not a question. Proceed unless one of these applies:
- a plan gate is open: the plan says to stop for review;
- a HOLD binds the wave;
- a lane is consent-bound with no OPERATOR-CONSENT row to cite. Route that lane to `/omni:operator-ruling` and dispatch the rest.

## 6. Dispatch and record

- **Live.** Dispatch each lane that is clear in the background: a Workflow, or an Agent in the background, with the lane's own model and effort. The prompt is the brief file, whole. Never dispatch in the foreground, and never SendMessage another lane.
- **Dry run.** Dispatch nothing. The briefs on disk are the output.

Then record the lanes you dispatched (in a dry run, the lanes that would go), never the held ones:

```bash
python3 "$W" record --lanes <lane-a>,<lane-b> --tickets OMN-<a>,OMN-<b>
```

`lanes.txt` uses way-of-working's format, `<lane> dispatched <ticket>`, so its every-turn inbox
loop and its session boundary read the same file. Then write the wave's rows (the Ledger section).

## Ledger

This is the only place this skill writes to the ledger. `wave.py` prints the rows and never
appends them. Build the wave's rows file first, with the MSGs before the STATUS:

```bash
mkdir -p "$S/waves"
python3 "$W" msg-row --route <item>:<owner lane> [--route <item>:<owner lane> ...] > "$S/waves/wave-<n>.rows"   # omit when nothing was routed
python3 "$W" status-row --wave <n> --lanes <lane-a>,<lane-b> --tickets OMN-<a>,OMN-<b> \
  --models <model-a>,<model-b> [--held <lane>] [--routed <item>:<owner lane>] >> "$S/waves/wave-<n>.rows"
cat "$S/waves/wave-<n>.rows"
```

Then append them, in order, stopping at the first refusal:

```bash
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
while IFS= read -r ROW; do
  [ -n "$ROW" ] || continue
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --append "$ROW" || { echo "REFUSED at: $ROW"; break; }
done < "$S/waves/wave-<n>.rows"
```

**The rows this skill writes:**
- One **MSG** per item routed to a live owner, in `/omni:ledger-msg`'s shape: `from=<session lane>`, `to=<owner>`, `id=<its own stamp>-<session lane>`, and the item's `ticket=`, `pr=` or `worktree=` cell. `msg-row` steps each stamp by a second, so two MSGs in one wave never share an id. It also refuses consent-shaped words, because a MSG is never consent.
- One **STATUS** per wave: `lane=<session lane>`, `wave=`, `lanes=`, `tickets=`, `model=`, plus `held=` and `routed=` when used.
- **FRICTION** goes through `/omni:friction-record`, never here. Its second occurrence files a ticket.

Lanes write their own CLAIM, STATUS and TERMINAL rows from their brief.

**Exit codes:**
- `65` is a grammar or lint refusal. Read the stderr line, fix the row, and run the loop again from the refused row. The grammar is printed by `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --print-grammar`.
- `75` is a lock timeout. Run the loop again; `onex-ledger` skips an identical row that is already at the tail.

Never edit the ledger by hand.

**Read back** through the lane-brief reader, never by opening the ledger: each append exited `0`,
and `python3 "$LB" grep "lane=$SESSION_LANE | wave=<n>"` prints the STATUS.

## 7. Report

Report in plain words, naming each thing rather than giving a bare number:
- the lanes dispatched, each with its ticket, model and effort;
- the lanes held, and the hold that binds each one;
- the items routed to an owner, and which owner;
- the items dropped as out of scope;
- the stale owners sent to `session-resume`;
- the manifest path, when one was written;
- in a dry run, the brief paths and the skipped steps.

End the report on the next move you are making, never on a question. Ordering is yours to decide:
the order lanes run in, which PR is handed off first, and whether a ready PR waits for a peer are
settled by the rules above and by the landing lane, not by the operator. A question the rules
already answer costs the operator a turn and leaves work waiting. The only questions that reach the
operator go through `/omni:operator-ruling`, as a genuine tradeoff.

Then stop. Each lane reports once, at its terminal. `/omni:verify-claims` checks a report before
it is relayed.

## Known follow-up

The typed JSONL work ledger (`onex-ledger` in ops_tooling_pkg, plan
`beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in docs_repo) replaces the
markdown ledger:
- **Writer.** The one `onex_ledger.py` append line in `## Ledger` changes, and nothing else in this skill does.
- **Readers.** `lane_brief.py grep` (behind `owners`), `inbox.sh`, `catchup.sh` and `drain_map.py` change inside the reader tasks that plan already owns. `wave.py` opens no ledger file, so it adds no reader site to cut over.

## Known friction (from prior runs)

- **Standing constraints did not reach delegated lanes.** A hold, the landing ruling and the model tier were told to the orchestrator and never pasted into a lane's prompt, so a lane merged under a hold and another ran on the wrong model. Section 4 pastes the readers' output through lane-brief 3a, and `check-wave` refuses a brief without it. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A second lane was dispatched onto work a live lane already held,** and the two lanes collided on one branch. `owners` runs before any brief, and a live owner gets a MSG instead. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **Work for a lane's owner was routed through the operator.** Section 2 sends the owner a MSG. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A job that outgrew one agent turn was recovered by hand, run after run.** Long jobs run detached with a progress file and a STATUS per shard (section 3), and the recurrence is recorded as friction so it gets fixed once. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A PR owner map run without `--only-pr` searched the whole org** and spent the shared GitHub quota. The inventory uses the per-PR form only. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **Two MSGs minted in the same second share an id.** `msg-row` steps each row's stamp. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **fan-out's constraints command drifted from lane-brief's interface.** lane-brief began requiring `--landing-ruling`; this skill's command did not pass it, so it exited 2 with no 3a, while preflight still printed ready because it looked for one flag by name. A dry run passed only because the model also loaded lane-brief and copied its form. preflight now reads the helper's required and accepted flags and blocks on any mismatch with `CONSTRAINTS_FLAGS`, and the tests run section 4's command exactly as written. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **Lane names were copied, not generated.** An example name in this file was reused as-is by every run that briefed the same ticket, so two sessions would have written one `lane=` for two lanes. Names now come from `wave.py name`, and the dry-run harness checks that each lane name first appears in that helper's output. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **The report ended on an ordering question to the operator.** In the 2026-09-24 integration run the wave report asked whether the session's own PR should be handed off first, which the rules already settle (a ready PR is handed off at once). Section 7 now ends the report on the next move and routes a genuine tradeoff through `operator-ruling`. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A dry run read the whole ledger with `cat`** during inventory. Section 1 now forbids any hand read of the ledger and names the reader for each question; the harness fails a transcript that opens it. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A dry run's sandbox variables did not survive into the Bash tool.** The shell profile reset `registry_root` to the real registry root, and the guard refused the run. Section 0's dry-run list now says to re-export the sandbox values at the top of every block. Staged by the orchestration-skills pass, OMN-17427 lineage.
