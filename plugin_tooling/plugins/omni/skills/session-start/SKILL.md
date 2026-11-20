---
name: session-start
description: Start or restart an orchestration session with every standing loop running, in one fixed order that calls existing skills and re-implements none of them. Runs way-of-working (preflight, catch-up, session CLAIM, session.env), then plans-today (every relevant plan for the day, ranked, so the operator does not have to remember them), then session-resume and the checkpoint's workflows after a restart, crash or usage-limit reset, then the landing controller's liveness, then the session ticks (merge-throughput, queue-status, awaiting-reply, operator-waiting, which prints the open asks to the operator read from the ledger, and integration-pass, which sees every merged change running or names who makes it run), and ends on one status line naming each missing loop with its fix. The SessionStart and per-prompt hooks bind only a session that has run it once, and a PostToolUse hook writes the checkpoint on every Workflow launch. Use for "start my session", "limits reset", "restarted", "I'm back", when the SessionStart block says so, and whenever the loops may have stopped.
prosthetic: true
replaces_when: "An omnimarket session-start workflow runs the six units below as nodes (way-of-working, plans-today, resume, controller liveness, ticks, loop check) and writes the checkpoint itself, on two consecutive restarts with no loop rebuilt by hand. Nothing today does it."
restored_from: "none. New process, from RULING 2026-09-26T21:22:31Z lane=orchestrator-83 and the 2026-09-26 checkpoints a session rebuilt by hand"
ticket: OMN-19815
---

# Session start (prosthetic)

A session has standing loops: preflight, the session CLAIM, the workflows it launched, the
launchd landing controller (which owns landing; no Claude drain runs), and the session ticks. A
restart or a usage-limit reset stops the ticks and can stop the workflows. On 2026-09-26 the
orchestrator rebuilt all of it by hand four times from a prose checkpoint, and on 2026-09-29 a
session restarted at about 06:36Z and ran for about three hours with no tick and no merge counted,
because nothing told it to run this skill. This skill is the fixed order that puts every loop back,
and a checker that says which one is still missing.

## Self-start: opt in once to bind this session

Three hooks ship in this plugin (`plugins/omni/hooks/hooks.json`) and run `scripts/hook.sh`:

- **SessionStart** (startup, resume, clear and compact) publishes the hygiene vocabulary for every
  eligible session; for an opted-in session it also runs `loops_check.py` read-only and injects
  one block: the `LOOPS` line, each finding, and a binding line: run `/omni:session-start` before
  any other work, because CronCreate ticks never survive a session start. After a compaction the
  ticks do survive, and the check reads the harness's own cron record (the session transcript the
  hook payload names), never a name the model supplies: a missing or hand-written tick is `MISSING`
  there, never `UNKNOWN`. It finishes in under 3 seconds and fails open with a visible `WARN` line
  that still carries the binding line.
- **UserPromptSubmit** (`hook.sh turn`) runs the cheap part of the same check on every prompt of an
  opted-in session (the tick identity and the heartbeat, no launchd, watcher or network read) and says nothing while all
  is well. While a tick is missing, non-canonical or its heartbeat stale, it injects the context AND
  a system message carrying each `MISSING` line and the instruction to run `/omni:session-start`
  before any other work, on every prompt, so ignoring it once cannot silence it. A check that
  errors prints a `WARN` and the binding line, never nothing. The requirement binds the session that
  owns the ticks and no other: while the heartbeat is fresh and another live session of the host
  (its process runs, or its transcript is recent) holds all three canonical ticks in its own cron
  record, a second session, such as one editing an article, is not told to start a second set
  (OMN-17427). With no such session, a dead orchestrator included, the lines and the binding stay.
- **PostToolUse on Workflow and TaskStop** writes the checkpoint below: every launch is recorded
  with its task id, run id and script, and every TaskStop marks its workflow stopped, so a
  checkpoint no longer depends on anyone remembering to write it.
- **The lane liveness read** (`hook.sh liveness`, beside the first two on SessionStart and
  UserPromptSubmit; `scripts/loops_check.py liveness`, OMN-20603) lists the session's background work an
  interrupt, a restart or a crash stopped. It reads process and workflow state, never a lane's own
  rows: each Workflow run from the harness's own record of the session (an agent directory per
  started run and an end record with `completed`, `failed` or `killed`; a
  `killed` run that no TaskStop in the transcript names was aborted), and each remote lane of the
  session (`lanes.txt`, and with the ledger every open CLAIM with `parent=<session lane>`) from its
  runner receipt and the runner's pid. omnimarket's `node_lane_liveness_compute` decides every
  verdict through `onex node`; when a read failed, the node's relay guard makes every unit
  `UNKNOWN`, never dead. The hook is silent while nothing stopped. While something did, it prints
  each `DEAD` line with its `RESUME` action (`Workflow resumeFromRunId=<run> scriptPath=<script>` in
  the same session, a fresh `Workflow scriptPath=<script>` for an earlier session's run, or
  `/omni:session-resume` step 4 for a remote lane) and the command that prints its STATUS row, on
  every prompt until each one is live or finished. It caches the node's answer until the evidence
  changes, so a quiet prompt costs no node call. `loops_check.py liveness read` is the same read by hand,
  with the ledger.

The first two fire only in an interactive session (`CLAUDE_CODE_ENTRYPOINT=cli`) whose cwd is
`$registry_root` or below it (never in a landing worker or a `claude -p` run). `OMNI_SESSION_START_HOOK=off`
turns them off; `=force` fires them anywhere but a worker. None of them blocks: each exits 0.
`tests/test_hooks.py` reads the shipped `hooks/hooks.json` and fails when the SessionStart matcher or
the UserPromptSubmit entry is missing, or a command it names resolves to no script, because an
older build once shipped no `hooks.json` and nothing noticed.

It is **thin**. Each step calls one existing skill, or one script beside this file, and adds no
procedure of its own. **It becomes an omnimarket workflow later** (RULING 2026-09-26T21:22:31Z
lane=orchestrator-83: "we will turn that into a workflow in omnimarket eventually"). So each step
below is a separately callable unit with a stated input, call and output, and nothing passes
between steps except those outputs. The port maps one unit to one node.

## Posture

The foreground's rules, briefly. Each cites the memory that holds the ruling.

- **The foreground orchestrates and reads plans, nothing else.** Every build, read and probe goes to a Workflow lane (`feedback_foreground_background_discipline`). The Agent tool is refused from the main session by a user-level guard (OMN-19763); work goes through Workflow only (`feedback_workflow_tool_only_no_foreground`).
- **A tick that finds nothing new says nothing.** It still does its check; it speaks only on a change, a finish, a break or a question (`feedback_silent_drain_ticks`).
- **A tick reads merge throughput first, never a status ping** (`feedback_drain_tick_reads_merge_throughput`). Landing belongs to the launchd landing controller, and the orchestrator never launches, resumes or swaps a drain (docs_repo `beta/plans/2026-09-27-merge-drain-that-merges-plan.md` section 7). This supersedes the drain-succession tick of `feedback_drain_tick_must_queue_successor`.
- **"Limits reset" is a fact.** A lane whose log ends in a limit message is history, not state: resume it, never stop it, and TaskStop the original before any relaunch so no lane runs twice (`reference_workflow_agents_retry_after_limit`).

## Unit 1. Open the session: /omni:way-of-working

First opt this session in:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/loops_check.py" opt-in --session "${CLAUDE_SESSION_ID}"
```

The hooks bind only a session that has run this skill (RULING 2026-10-13T16:30:51Z); an article-review or other session that never runs it gets no binding.

Session start is optional and manual (operator RULING, OMN-21149): no SessionStart or
UserPromptSubmit hook prints orchestrator output or starts orchestrator work for a session that has
not opted in. The opt-in above writes the session's id to the shared marker directory
(`~/.local/state/onex/session-opt-in/`, or `ONEX_SESSION_OPTIN_DIR`), which turns on, for this session
only: this plugin's tick binding, lane liveness read and plans-of-the-day hook, the public plugin's
session-goal, workspace-sync, host-drift and hook-inventory banners, and the operator access-mode
banner and remote setup check. Because the session opted in after its SessionStart hooks ran, the
command prints the public plugin's banners once, right after its `SESSION-START opted-in` line; read
them as the session's startup state. A session launched with `ONEX_SESSION_OPTIN=1` is opted in from
its first hook; `ONEX_SESSION_OPTIN=0` keeps a session out. Guards never consult the opt-in.

- **Input:** the goal ticket (ask once only if none was named).
- **Call:** `/omni:way-of-working`, its section 2 steps 1 to 3, unchanged: preflight, catch-up, inbox, the session CLAIM and `session.env`.
- **Output:** its `SESSION` line, and the `SESSION_ENV` path it printed. Keep that path; unit 6 reads the preflight receipt beside it.

## Unit 2. The plans of the day: /omni:plans-today

- **Input:** unit 1's session lane (`SESSION_LANE` from `session.env`).
- **Call:** `/omni:plans-today`, run exactly as its own SKILL.md says (Linear snapshot first, then its script). It reads the plans at origin/main, the PR watcher, the ledger and Linear, ranks every plan dated in the last 14 days or carrying an In Progress ticket or an open PR (stalled and unowned first), and sends one ledger MSG for each stalled plan with no owner. Never pass its `--no-msg` here: that flag is for dry runs and tests, and a session start that silences the MSG hides the stall it just found.
- **Output:** the ranked list it printed, and its detail file path. Show the operator the list, so the operator is not the one who remembers the plans. Every `STALLED` line with `owner=NONE` already has its MSG; act on those lines' next actions before reading unit 3.

## Unit 3. Resume, only after a restart, crash or usage-limit reset: /omni:session-resume

- **Input:** unit 1's session lane, and the newest checkpoint:

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/scripts/checkpoint.py" read
  ```

  It prints one `RESUME` line per workflow that was running and one `QUEUED` line per workflow that
  was waiting (task id, run id, role, script, purpose), then the deadlines, decisions and ticks.
  `NO-CHECKPOINT` (exit 3) means there is none: fall back to the newest prose handoff in
  `$registry_root/.claude_scratch/handoffs/`.
- **Call:** `/omni:session-resume` (way-of-working step 4 calls it; follow it there). Then, for every
  `RESUME` and `QUEUED` line whose task is not live: TaskStop that task id if it still shows, then
  Workflow with `resumeFromRunId=<run id>` and `scriptPath=<script>`. Resume by run id; never
  re-derive or rebuild a workflow the checkpoint names. Two exceptions, both enforced by unit 6's
  checker: a checkpoint written more than 12 hours ago is expired and nothing is resumed from it
  (fall back to the newest prose handoff for context only), and a `role=drain` or
  `role=drain-successor` workflow is never resumed (unit 4).
- **Output:** the task ids now live. Unit 6 takes them as `--live-task`.

Skip this unit on a fresh start that follows no outage.

## Unit 4. Landing controller: loaded, ticking, acting (/omni:landing-controller)

- **Input:** the controller's launchd job and its state directory, `~/.local/state/omni/landing/`.
- **Call:** unit 6's checker answers this from the same reads; run it first and act on its `controller` line. It is live when `launchctl list ai.omninode.landing-controller` exits 0, that last tick reads `mode=act` and was not refused (no `refusal=`, status `OK` or `DEGRADED`), and either a tick is running (a launchd PID whose elapsed time is under 30 minutes; ticks have run up to 13) or the last tick finished under 15 minutes ago. A tick's `ts` and the heartbeat hold its start, so the end is `ts` plus `timing.total_s`; judged from the start alone, a 13 minute tick read stale two minutes after it finished. A tick running past 30 minutes, a PID `ps` cannot read and an idle job whose last tick ended over 15 minutes ago all fail closed as `MISSING controller`. A `DEGRADED` tick with a `degraded` list completed and acted: its escalated PRs print on a `NOTE` and belong to the merge-throughput tick, one targeted fix lane per cause.
- **Output:** nothing to do, or one fix, and the fix is always the controller's own: `install.sh --status`, then `install.sh --act --g-act-dir <dir>` once G-ACT verifies, or `launchctl kickstart -k gui/<uid>/ai.omninode.landing-controller` for a stale tick, each as `/omni:landing-controller` gives it. **Never launch, resume or swap the retired Claude drain**: on 2026-09-28 and 2026-09-29 drains started 95 lanes for 3 merges and 202 agents for 1 merge, and the plan's section 7 forbids the orchestrator from doing it. A drain named in an old checkpoint is not resumed (unit 3's checker says so in a `NOTE`).

## Unit 5. Ticks: CronCreate

- **Input:** the session's current ticks (CronList).
- **Call:** create each missing tick with CronCreate, with the cron and prompt below and no other. CronCreate ticks are session-bound, so every start creates them again. A tick prompt is never edited in a session: unit 6 counts a tick only when its cron and prompt equal this pair byte for byte, and reports any other recurring job that names merge, queue, land, tick, awaiting-reply or operator-waiting as `MISSING tick:<name> non-canonical`. Operator feedback about tick behaviour becomes a change to this file plus the matching constant in `scripts/loops_check.py` (`THROUGHPUT_TICK_PROMPT`, `OPERATOR_WAITING_TICK_PROMPT`, `INTEGRATION_PASS_TICK_PROMPT`) through a pull request. After any restart, or a resume where CronList reads "No scheduled jobs", the only valid first action is `/omni:session-start`, never a hand-rebuilt cron.

  | Tick | Cron | Prompt |
  | -- | -- | -- |
  | merge-throughput | `3 * * * *` | the prompt in the block below, verbatim |
  | queue-status | `*/30 * * * *` (every 30 minutes, the cadence `/omni:queue-status` states) | `/omni:queue-status` |
  | awaiting-reply | `17 */2 * * 1-5` (minute 17 of every second hour, Monday to Friday, the cadence /omni:awaiting-reply section 7 states) | `/omni:awaiting-reply 6h` |
  | operator-waiting | `47 */2 * * 1-5` (minute 47 of every second hour, Monday to Friday, thirty minutes after awaiting-reply) | the prompt in the second block below, verbatim |
  | integration-pass | `37 * * * *` (minute 37 of every hour, every day, off the marks the other ticks use) | the prompt in the third block below, verbatim |

  After the ticks, list the session's Routines (OMN-20810): run `RemoteTrigger` with `action=list` and
  write its JSON to `$XDG_STATE_HOME/omni/queue-status/routines.json` (`~/.local/state/omni/queue-status/routines.json`
  when unset). The first queue-status tick reads that file and raises an alarm through `alert_channel_alarm`
  for any recurring Routine whose text has no `routine=<process_id>` naming an overlay entry. A session with no
  Routines API sign-in writes nothing, and queue-status prints `routines UNKNOWN:`.

  The awaiting-reply tick needs the session's Slack and Linear connectors; a session without them
  still runs it and the skill prints both sources as failed in its header, so a broken schedule is
  visible; it posts nothing.

  The merge-throughput prompt (the hourly goal check, OMN-19998), verbatim (`loops_check.py` holds the same string as
  `THROUGHPUT_TICK_PROMPT` and the static test fails when the two differ; it sits outside the table
  because the command in it contains pipe characters):

  ```text
  Hourly goal check (no Claude drain: the retired Claude drain spun 202 agents for 1 merge and is never launched; no GitHub search from the foreground). The goal is the operator's current /goal: landing works for the work we are keeping, which is the pull requests the goal_scope overlay names; everything else stays paused as draft. Run this one command and read its output: python3 "$(python3 -c 'import json,os; p=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))["plugins"]["omni@private-repo"]; print(sorted(p, key=lambda e: e.get("scope") != "user")[0]["installPath"])')/skills/session-start/scripts/throughput_tick.py". It reads the landing controller's files, the PR watcher's state, the goal_scope overlay and the remote-lane runner's live admission, sends only in-scope work through the lab fill and prints one `GOAL` line before the status line: `GOAL changed=<yes|no>` with in-scope merges in the last 60 minutes, in-scope open non-draft pull requests, drafts flipped back and shared reds with no owner, judged against the previous check. When that line says `changed=no`, say nothing, whatever else the output holds. When it says `changed=yes`, say its cells in one line, then act on each in-scope line: for a `MISSING goal-flipped:<pr>` line follow its FIX (a paused pull request returns to draft and only the operator restores one); for each `MISSING lab-headroom:<host>` line dispatch lanes through the remote-lane runner only when the `NOTE lab-fill` line shows `in_scope_unsent` above 0, up to the line's free slots and with the engine its FIX names (free slots with no in-scope work to send are not idle: `NOTE lab-idle-no-scope-work`); for every other MISSING or UNKNOWN line, follow the line's FIX, which names the controller or a read; never dispatch a fix lane for an escalated or floor line, because the landing controller owns those fixes, except a floor line whose FIX names RULING 2026-10-09T04:10:56Z (a park holding a stopped repository for hours), which gets the one fix lane its FIX names. The script has already read the merge sweep's plan itself (no lease, no model, in-scope pull requests only) and printed one `sweep:` line: launch nothing for a `sweep: not needed` or `sweep: not launched` line, and read no plan yourself. Only for a `sweep: launch` line, launch one merge sweep with the Workflow tool, scriptPath "${OPS_TOOLING_PKG_PATH:-$registry_root/../ops_tooling_pkg}/src/ops_tooling_pkg/handlers/merge_sweep/merge_sweep.js" resolved to an absolute path, and args {skill_dir: the output of echo "$(python3 -c 'import json,os; p=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))["plugins"]["omni@private-repo"]; print(sorted(p, key=lambda e: e.get("scope") != "user")[0]["installPath"])')/skills/merge-sweep", lane: sweep-<session lane>-<HHMM UTC>, parent: <session lane>, ticket: <the session CLAIM's ticket>, max_lanes: the max_lanes the sweep line prints, as a string}. The sweep reads the fleet once and dispatches one remote lane per planned lane, each brief built and checked through /omni:lane-brief; its lease still refuses a second sweep (reader exit 75, nothing dispatched), so never launch a second one while one runs. The script has also already filled the free slots with in-scope work from the standing pillar backlog (OMN-17427, RULING 2026-10-14T21:46:25Z; scope: the goal of 2026-11-05): its `NOTE lab-fill | sent=<n> ... idle_after=<k>: ... (in_scope_unsent=<u> out_of_goal_scope=<p>)` line names each lane it sent, so dispatch nothing more for those. The Stop idle guard (`queue_status.py --idle-guard`) refuses a turn that read free headroom with in-scope work unsent, or an UNOWNED red in a repository holding in-scope work, and that dispatched nothing the runner's receipts show. A `MISSING stuck-green:<pr>` line is a CONTROLLER_DEFECT, never 'the controller owns this' (RULING 2026-10-17, OMN-19998): the script has already dispatched the one controller fix lane the line names, once per head, so dispatch nothing more for it unless the line says the dispatch failed, and read the `green-unlanded=<n> oldest=<m>m` cells that end the status line.
  ```

  The operator-waiting prompt, verbatim (`loops_check.py` holds it as `OPERATOR_WAITING_TICK_PROMPT`,
  and the static test fails when the two differ). It answers RULING 2026-10-14T18:04:24Z
  lane=orchestrator-bb1a (OMN-16177): what waits on the operator is a query of the ledger, not a list
  someone keeps:

  ```text
  Waiting-on-operator tick (OMN-16177: the open asks to the operator come from the ledger, never from a list kept by hand). Run this one command: python3 "$(python3 -c 'import json,os; p=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))["plugins"]["omni@private-repo"]; print(sorted(p, key=lambda e: e.get("scope") != "user")[0]["installPath"])')/skills/session-start/scripts/loops_check.py" operator-waiting --new-only. When it prints nothing, say nothing. Otherwise show the operator its output as printed, once: every open ask to the operator, oldest first, grouped by ticket, each with its age, the new ones marked NEW. An UNKNOWN line is a failed read: say so in one line. This tick answers, closes and re-asks nothing; an answer is recorded through /omni:operator-ruling, which closes the ask it answers.
  ```

  The integration-pass prompt, verbatim (`loops_check.py` holds it as `INTEGRATION_PASS_TICK_PROMPT`, and the static test fails
  when the two differ). It answers the operator's words of 2026-11-12 (OMN-19998): a merge is not the finish, so every merged
  change is either seen running where it runs or has a named owner doing the step that makes it run. It adds no script: the
  readings are `adopt_merged.py status` and `drift --json` (the `merged means running` mechanism), the state is one file in the
  state directory the other ticks use, and the tick is a session cron, so it names no `routine=` entry (the routine guard
  refuses only a durable recurring `CronCreate`).

  ```text
  Integration pass (OMN-19998, operator 2026-11-12: a merge is not the finish). ONE job: every change merged since the last pass is either SEEN RUNNING where it runs, or has a named owner doing the step that makes it run this hour. State is one file, integration-ledger.md in the session-start state directory (${OMNI_SESSION_START_STATE_DIR:-$HOME/.local/state/omni/session-start}), one line per merged change: repository and number in plain words, merge time, WHERE IT RUNS, reading, state SEEN RUNNING | NOT RUNNING: owner and step | CI-ONLY | BLOCKED: by what, under a `last-pass:` UTC stamp; create it on the first pass. Steps: 1. Read the file. 2. List what merged since its last-pass stamp from the PR watcher state (state MERGED, merged time after the stamp) and the canonical clones' git log of the landing branch; no GitHub search, no gh reads from the foreground. 3. For EACH, name where it runs and read it there. Reuse what exists, never restate it: for the plugin, the launchd tools and the lane guard run python3 "$(python3 -c 'import json,os; p=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))["plugins"]["omni@private-repo"]; print(sorted(p, key=lambda e: e.get("scope") != "user")[0]["installPath"])')/skills/adopt-merged/scripts/adopt_merged.py" status, then the same with drift --json (its classes stale, missing, held and unmerged ARE the not-running readings, and adopt-merged is the install path: tested install with rollback, never a hand copy); the dev runtime rebuilds itself after an omnimarket merge: read the running image revision and the specific thing the change adds (a registered node, a topic, a table, a grant, a route); a unit on the launching host: read the unit's next run line for the new behaviour; a lab host unit: check WHICH COPY runs, a second copy that nothing runs is a defect to report, not an install; an overlay value must be in the canonical overlays clone AND the code that reads it running; anything else is CI-ONLY. 4. Take each reading through a background workflow (read-only, explicit model), never a foreground probe. 5. For each NOT RUNNING do the step this pass: adopt-merged run, move a pin for a reason, land the settings half, write the deploy ask the declared way, or place a PROVING lane (never a rebuild); if blocked, the line names the blocker and who acts. Never prod, never a hand merge, never a hand-edited installed file, never the dev runtime or broker touched by hand, never a token printed. 6. Rewrite the file and its stamp; carry forward every line still NOT RUNNING or BLOCKED until it reads SEEN RUNNING, oldest first. 7. Say one plain line to the operator, ids named in words: merged since last pass N, seen running M, made to run this pass K, still not running J with the oldest and why. Say nothing when nothing merged and nothing is carried. Name a lane for any workflow as integration-<session lane>-<HHMM UTC>.
  ```

  `loops_check.py operator-waiting` reads the ledger's inbox for the operator and nothing else: every
  MSG to=operator that carries a `question="..."` cell and that no ACK has closed, oldest first, grouped
  by ticket, one line each with its age, and a count. The `question=` cell is the writers' own ask field
  (`/omni:operator-ruling` `ask`, `row MSG --question`). A report row (SENT-ON-BEHALF, MANUAL-ENQUEUE,
  ESCALATION-*, a status note) is a MSG to=operator with no `question=` cell by design: the inbox counts it,
  this list and its `n=` never do. With `--new-only` it prints nothing unless an ask opened since its last run. At
  every session start and resume, after creating the tick, run it once without `--new-only` and show
  the list (it prints `n=0` when nothing waits), so a restart never hides an ask. The tick resolves
  when `/omni:ledger-msg` does, because that skill's inbox is what it reads.
  A run that prints at least one open ask also appends one STATUS row (`actor=script:operator-waiting-tick`,
  with `open=`, `new=`, `tickets=` and `oldest=`) through the plugin's row writer, so the ruling audit
  (RULING 2026-10-14T18:04:24Z) sees the tick acting; a refused write is one `NOTE` line and never hides the list.

  After creating the merge-throughput tick, run its command once now: the script writes the
  heartbeat (a UTC stamp and pid, in `~/.local/state/omni/session-start/`) that unit 6 requires to
  be under 75 minutes old (the tick runs hourly), and nothing else writes it, so a hand-written tick that does not run
  that script never satisfies the check.

  The tick's read is one tracked script, `scripts/throughput_tick.py`: it reads files and two
  processes (the controller's state directory and launchd job, the PR watcher's state, merge-drain's
  per-repo floors, the remote-lane runner's pool, marks and receipts, and one live admission read of
  every lab host through `landing_placement.read_pool`, so a host is `MISSING lab-headroom:<host>` only
  while placement would admit a lane on it, and a host that cannot be read stays `UNKNOWN`, OMN-20864) and hands what it read to
  omnimarket's `node_throughput_tick_decision_compute` through `onex node`, which makes every
  decision (OMN-20686; a node that cannot be run prints one `UNKNOWN throughput-node` finding), no
  GitHub call and no foreground reads, one short output whose last line is `THROUGHPUT OK` or
  `THROUGHPUT STALL n=<findings> unknown=<u of them>: ...`. Before that status line, when a Claude lab slot is free, the script prints one `sweep:` line (OMN-20864): it reads the sweep lease and, when free, decides from the plan a previous `sweep_read.py --no-lease --json` wrote (`sweep-plan.json` in the state directory, fresh for 20 minutes, the line ends `(plan read <n>m ago)`), and says `sweep: launch ... max_lanes=<n>` only for a free lease and at least one planned lane, otherwise `sweep: not needed: <why>`. The tick never waits for that read (50 to 100 s, past the foreground's two-minute limit): a plan that is older, missing or unreadable starts the read detached for the next tick and prints `sweep: not launched: plan is being refreshed (last read <n>m ago | no earlier read)`, plus `; the last refresh failed: <why>` after a failed one; see `/omni:merge-sweep`. Each stall is a `MISSING` line with its `FIX:`:
  the controller, the fleet's merges in the last 60 minutes, a repository under its landing floor,
  or a PR the controller escalated. Every repository with open PRs and no merge in the last 60 minutes
  gets a status check each run (RULING 2026-10-15T00:42:51Z, OMN-19998): the node returns one typed
  verdict for it (merging_normally, waiting_on_ci, base_branch_red, merge_queue_ejecting,
  shared_red_unowned, parked_or_escalated) from the watcher and controller files already read, so no
  model runs, and the script keeps the open units and writes one event per new verdict to
  `throughput-tick.repo-status-events.jsonl` in its state directory. An unowned shared red or an ejecting
  merge queue is a `MISSING repo-status:<repo>` line whose FIX names one cause lane or the controller,
  which the tick prompt's "follow the line's FIX" acts on next turn; the other verdicts are `NOTE` lines.
  A shared red a live cause CLAIM owns is a `NOTE repo-status:<repo>` line naming the lane, not a MISSING (OMN-19998):
  the node reads no ledger row, so the script asks queue-status's own ownership rule, the one the merge pulse uses,
  where a CLAIM on the root check owns every check that inherits it through the workflow's needs graph and a CLAIM on
  the inheriting gate is a CLAIM on its root. A ledger it cannot read leaves the MISSING and adds
  `NOTE repo-status:<repo> | cause CLAIMs unread: <why>`. An ownership read that did not run at all, because its share
  of the tick's budget ended, turns every shared-red line into
  `MISSING repo-status:<repo> | ... shared_red_ownership_unread: <check> ...; ownership unread: <why>` whose FIX is to
  read ownership before any cause lane (OMN-17427): nobody read who owns that red, so the tick never reports it unowned
  and the lab fill's unowned-red reader does not match the line.
  The tick also runs the lane liveness read with a 15-minute bound
  (`loops_check.liveness_tick_findings`, OMN-20603): a unit of this session stopped longer than that is a
  `MISSING lane-dead:<name>` line whose FIX is its resume action and its STATUS row, and a failed
  read is `UNKNOWN lane-liveness`. The tick also prints one `NOTE held:<repo>#<n> | <title> | <person> | <reason's
  first sentence> | held <age>` line per PR the controller holds for a person (OMN-17427; the sidecar's
  `head_escalation` and the watcher state, via `scripts/loops_check.py`, no GitHub): an orchestrator reads the holds
  there instead of in the sidecar, and a hold is a NOTE, never a stall. The tick runs its floor escalation
  (`loops_check.check_floor_escalation`, OMN-19998, RULING 2026-10-15T20:56:54Z) with the bounds in `floor_escalation.json` beside this file: every repository
  in the landing scope (the merge sweep's one repo-scope setting, `FLEET_REPOS` minus `sweep_scope.json`) with no
  `landing_floors.json` entry is `UNKNOWN floor:<repo>`, never skipped; a repository under its floor for more than
  `under_floor_ticks` consecutive ticks with no controller progress (no merge, no new lease, no worker result on its
  PRs) gets ONE diagnose lane, which the tick itself starts through the remote-lane runner, placed by headroom and never
  pinned to the controller's host (the Mac takes no lab lane, OMN-23200); the controller's newest rows travel in its brief,
  once per repository per `dedupe_window_hours`, and prints `MISSING floor-escalation:<repo> | ... DISPATCHED diagnose
  lane <lane> ...` (then a NOTE while the window holds; a failed start is UNKNOWN and is tried again next tick); and an
  open PR green on every check and not merged or queued for longer than `stuck_green_minutes` (30; armed or not,
  never a draft, a conflicting head, a PR held for a person, a grant the controller keeps on purpose or a PR the
  newest controller tick, inside that bound, reads `queued`: the watcher marks no plugin-tooling-pkg PR queued, or
  `worker_running:queue_rejected`: a fix worker on a merge-queue ejection the watcher does not read) is a
  CONTROLLER_DEFECT (RULING 2026-10-17, OMN-19998; "Why are green PRs just sitting there?", 15 green PRs unlanded for
  up to four hours while the line said the controller owns the fix and the controller was what failed): the tick
  prints `MISSING stuck-green:<repo>#<n> | CONTROLLER_DEFECT ...` and itself dispatches ONE controller fix lane through
  the remote-lane runner for the heads no earlier lane covers, once per PR head (`green-unlanded.json` in the
  state directory), with each PR's controller decision history (its `decisions.jsonl` rows and the newest tick's
  reason) in the lane's brief; while the head holds, the line says `already covered by controller fix lane <lane>`.
  A failed start is `UNKNOWN stuck-green-dispatch` and is tried again next tick. The status line ends with
  `green-unlanded=<n> oldest=<m>m` whenever n is above zero, so the number of green heads and the age of the oldest
  are read from the one line. The orchestrator dispatches nothing more for the floor line or the stuck-green line;
  it never answers a green head with "the controller owns it".
  A merged fix to the tick reaches the copy that runs only through adoption (OMN-19998: the stuck-green fix
  plugin-tooling-pkg#850 merged at 14:57:56Z on 2026-10-17 with no adoption run after 12:54Z, and the tick dispatched
  controller fix lanes for #856 and #740, both read `queued` by the controller's newest tick). When
  adopt_merged.py's newest run event (`events.jsonl` beside its state; `ONEX_ADOPTION_STATE` names another) is older
  than 60 minutes or absent, the tick prints `MISSING adoption` and itself starts one detached `adopt_merged.py run`,
  at most once per 60 minutes (`throughput-tick.adopt-start.json`, output in `throughput-tick.adopt-run.log`);
  `ONEX_ADOPT_ON_TICK=0` turns the start off, and with no state to read the line is `UNKNOWN adoption`.
  Adoption recovery is implemented by `node_adoption_recovery_effect` and its handler under
  `src/plugin_tooling_pkg/nodes/` in this repository. The plugin loads its bundled `src/`; only
  script-only copies fall back to `$registry_root/plugin-tooling-pkg/src`.
  A PR a process-fix lane handed off
  (its CLAIM's `priority=process-fix`, its TERMINAL `outcome=handed-off`) is tracked until it is merged and running
  (OMN-19998, `loops_check.process_fix_findings` over the ledger): still unmerged 60 minutes after the hand-off, or
  merged with a running copy to reach and no `ADOPTED` or `DEPLOYED` row 60 minutes after the merge, is a
  `MISSING process-fix:<repo>#<n>` line whose FIX names one driver lane. A lane dispatch the runner ended no-host
  waits in the lane queue (OMN-19998, `landing_placement.lane_queue_*`): the tick starts each queued lane through the
  runner, most urgent class first, while the pool read shows a free slot for its engine (pinned to its `--host` only
  while the pin is under 15 minutes old), and prints one line, `NOTE dispatch-queue: depth=<n> oldest=<m>m (<lane>)
  started=<s> expired=<e>`, instead of one MISSING per lane. The oldest wait past 60 minutes is `MISSING
  dispatch-queue`; a lane the queue expired after three hours is `MISSING dispatch-queue-expired:<lane>` (re-send that
  one); a relaunch that fails is `MISSING dispatch-replace:<lane>`; `--no-replace` sends no lane at all (no replacement, queue start, floor or controller fix lane, adoption run, stuck-owner or fill lane; OMN-17427) and does not advance the floor or stuck-green history. A no-host
  run that never reached the queue (an older runner) is still relaunched as before (`NOTE dispatch:<lane> re-placed`;
  once per run, three times per lane in three hours). That is the scheduled half of the read:
  it alerts even when no prompt has run since the interrupt. If `/omni:queue-status` or `/omni:awaiting-reply`
  does not resolve in this plugin, say so in one line and skip its tick; never fail the start on it.
- **Output:** the ticks now present (`merge-throughput`, `queue-status`, `awaiting-reply`, `operator-waiting`, `integration-pass`) and the waiting-on-operator list. Unit 6 reads the ticks from the session transcript, not from this list.

## Unit 6. One status line: the loop check

- **Input:** unit 1's `SESSION_ENV`, unit 3's live task ids, and the session transcript path (the `transcript=` cell of the hook block; the `--ticks` list of tick names is only the fallback when no path is known, and the transcript overrides it).
- **Call:**

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/scripts/loops_check.py" --session-env "<SESSION_ENV path>" \
    --transcript "<transcript path>" [--after-restart --live-task <id> ...]
  ```

  Read-only in every mode: it appends no row, launches nothing and makes no GitHub call. It reads
  the newest checkpoint, the preflight receipt, the landing controller's launchd job and state
  directory, and the PR watcher's state file (`$registry_root/.claude_scratch/pr-watcher/state.json`)
  for merges in the last 60 minutes. It prints one `MISSING`, `UNKNOWN`, `SKIP` or `NOTE` line per
  finding, each missing loop with its `FIX:`, and the status line last. Under 5 merges an hour with
  PRs open is `MISSING merges`, and every repository in merge-drain's `landing_floors.json` with
  non-draft, non-held PRs open that the controller can land (every author's, per the landing policy: OMN-20249) and fewer merges than its per-hour floor over 2 hours is its own
  `MISSING floor:<repo>`, because a fleet total hides a repository with none; a zero is checked against a seven-day positive control and reads
  `UNKNOWN`, never OK, when the control is zero too, and a watcher state older than 15 minutes is
  `UNKNOWN` (rule 16). A checkpoint older than 12 hours is expired: one `NOTE`, and no resume or
  deadline is proposed from it.

  The tick check does not trust a name. It rebuilds the session's live recurring jobs from the
  transcript (CronCreate adds on its "Scheduled recurring job" result, CronDelete removes on its
  "Cancelled job" result, a session start or resume kills every non-durable job, a job expires after
  7 days) and counts a tick only when its cron and prompt equal unit 5's pair byte for byte. Any
  other recurring job whose prompt names merge, queue, land, tick or awaiting-reply is `MISSING tick:<name>
  non-canonical`: reported, never accepted. The heartbeat is its own finding: `MISSING
  tick-heartbeat` when `throughput_tick.py` has not run in the last 75 minutes. `--tick-check` runs
  only these two checks, which is what the per-prompt hook does.
- **Output:** the last line only: `LOOPS OK checked=...`, or `LOOPS MISSING n=<findings> unknown=<u of them>: <loop>, ...`. Report that one line. For each missing loop, apply its fix (a launch goes to a Workflow lane) and run the check again. Exit 0 is OK, 1 missing or unknown, 2 bad input.

## The checkpoint: write it at every checkpoint and before any restart

The checkpoint is the file units 3 and 6 read. **The PostToolUse hook writes it on every Workflow
launch and every TaskStop** (`scripts/checkpoint_hook.py`), carrying forward this session's own
newest checkpoint, and carrying only decisions, deadlines and ticks (never workflows) from another
session's checkpoint when that one is under 12 hours old. Write it by hand only to add a decision
or a deadline, or when the hook printed a `WARN`. A checkpoint older than 12 hours is expired and
proposes nothing. Its schema is `omni.session-checkpoint/1`, defined in
`scripts/checkpoint.schema.json` and enforced by `checkpoint.py`:

| Field | Holds | Required |
| -- | -- | -- |
| `schema`, `written_at`, `session_lane` | the version, the UTC write time, the session lane | yes |
| `session_ticket` | the goal ticket | no |
| `session_id` | the Claude Code session id, written by the hook | no |
| `workflows[]` | `task_id`, `run_id`, `script`, `purpose`, `role` (drain, drain-successor, lane, other), `status` (running, queued, stopped, done); `ends_at` for a running drain, `start_at` for a queued one | yes, the list may be empty |
| `decisions[]` | `what`, `owner` (operator or session), `since` | yes, the list may be empty |
| `deadlines[]` | `what`, `at`, `action`: a drain's time box, a successor's build-by time | yes, the list may be empty |
| `ticks[]` | `name`, `cadence`, `prompt` | no |
| `notes[]` | free text | no |

Write it with one command. `--from` carries the previous checkpoint forward, and a `--workflow`
with a task id already there replaces that entry:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/checkpoint.py" write --lane "<session lane>" --ticket <OMN-n> \
  --from "<previous checkpoint path>" \
  --workflow "task=<task id>;run=<run id>;script=<script path>;purpose=<what>;role=drain;status=running;ends=<UTC>" \
  --deadline "what=<what>;at=<UTC>;action=<the fix>" \
  --decision "what=<open question>;owner=operator"
```

It writes `$registry_root/.claude_scratch/handoffs/<YYYY-MM-DD-HHMMSSZ>-<lane>-checkpoint.json` and
prints one `CHECKPOINT written=<path>` line with the counts. A record missing a required field is
refused (exit 65) with every finding named, and nothing is written. The prose handoff
(`/onex:handoff`) stays the human pointer; this file is the machine one.

## Ledger

This skill writes no row of its own. Unit 1's `/omni:way-of-working` writes the session CLAIM, unit
2's `/omni:session-resume` writes the resume STATUS and any closing rows, and a launched successor
writes its own CLAIM. Any other row goes through `/omni:ledger-write`.

## Common rationalizations

Each row is an excuse a session gave for skipping a step of this skill, with the failure that excuse
caused. The rows come from the night of 2026-10-17 and from the FRICTION rows of 2026-10-12 to
2026-10-17. If your next message matches the left column, do the right column.

| Excuse | Why it is wrong | What to do instead |
| -- | -- | -- |
| "The controller owns this fix, so I start no fix work." | The controller was the broken part: green pull requests sat 2 to 4 hours held by one of its own gates while the session dispatched other lanes. RULING 2026-10-16T11:40:09Z lane=orchestrator-bb1a made the answer a mechanism: the tick prints every non-draft, non-grant PR that is green and CLEAN but gated for 20 minutes or more. | Act on that line in the same turn, before any other dispatch: merge or enqueue it as the ruling says, then dispatch a lane for the gate that held it. A controller that holds green PRs is the work, not the reason to wait. |
| "The tick says no dispatch for that host, so there is nothing to place there." | FRICTION 2026-10-12T10:05:28Z lane=orchestrator-1d5b: the tick printed a Claude limit for a host all day while its Codex slots were free (about 55 lane-hours unused). | Read headroom per engine. A host limited for Claude with free Codex or lab slots takes Codex and lab lanes. |
| "A third sweep would only re-plan the same pull requests." | FRICTION 2026-10-13T08:46:52Z lane=orchestrator-31d9: the lab sat idle 28 minutes with 11 to 25 free slots on that reasoning. RULING 2026-10-14T21:46:25Z lane=orchestrator-bb1a: fill the slots with manual triage "<removed>" | When slots are free and nothing is queued, dispatch: triage the oldest green PRs, mechanize a ruling, or start another lander. Idle slots are never the safe choice. |
| "The tick ran, so the loops are alive." | FRICTION 2026-10-17T09:33:51Z lane=silent-failure-alarm: the throughput tick exited nonzero on 3 runs in a row; FRICTION 2026-10-17T11:55:45Z: the queue-status trend file was 50 minutes old with the controller live. A tick that ran is not a tick that finished. | Read the exit code and the heartbeat age, not the existence of output. A tick older than its interval is MISSING; restart with `/omni:session-start`, never a hand-built cron. |
| "The cause went to the controller, so another diagnose lane is harmless." | FRICTION 2026-10-17T08:06:33Z lane=floor-diagnose-omnibase_spi-20261017T0756Z: 17 diagnose lanes for one cause already handed off, with no ACK, added no fact the controller could act on. | Before dispatching a floor-diagnose lane, read the newest TERMINAL and MSG for that repository. Dispatch again only when the named cause or head changed. |
| "The lane handed off, so that work is done." | A handed-off lane ends with the pull request unmerged and waiting on the controller. Counting it as done reports work that has not landed. | Count merged, not handed-off. A handed-off PR is open work with an owner; `/omni:queue-status` shows whether it merged. |
| "Merged, so it is running." | A merge to `main` ships nothing until the plugin version bump lands and the installed copy matches. FRICTION 2026-10-13T05:25:27Z lane=adopt-merged: 14 merged fixes had not run for over an hour. | After a merge, read the installed version or the adopt-merged report before saying a fix is live. |
| "The Mac is under memory pressure, so I hold the dispatch." | On 2026-10-17 a session told the operator this without a reading while 61 GB was free. An unmeasured cause sends the operator after the wrong problem. | Print a reading from this turn (load per core, free memory from the tick or `lane-k-run`) beside any statement about capacity. No reading, no claim. |
| "I will ask the operator which way to go." | The operator had ruled one question three times that night, and the ledger held all three. RULING 2026-10-16T03:24:42Z lane=orchestrator-bb1a: no PR waits on the operator. The question guard refuses a decision the ledger has already ruled. | Search the RULING, OPERATOR-CONSENT and CORRECTION rows for the subject words first and cite the row. Ask only when none answers. |
| "I will rebuild the cron by hand, I know the set." | A hand-written tick replaced the canonical set for about 67.5 hours (Known friction below). | Tick prompts are never edited in a session. Run `/omni:session-start` and let unit 6 compare them byte for byte. |

## Red flags

- A line in the tick naming a green, non-draft, non-grant PR gated 20 minutes or more that you read and did not act on in the same turn.
- Free lab slots in the tick while no lane is in flight and your next message is not a dispatch.
- A statement about memory, load, disk or quota with no reading from this turn next to it.
- A CLAIM list holding the same lane-name prefix three or more times, or a diagnose lane dispatched twice for an unchanged cause and head.
- A tick heartbeat older than its interval, or a tick job whose last exit was nonzero.
- A question to the operator whose subject words appear in a RULING of the last 14 days.
- A report that counts handed-off lanes as landed, or says "merged" where it means "running".
- A sweep launched that planned only a draft lane. It has happened four times; read the plan before counting it as work started.
- A manual fix of one instance (re-dispatching a lane that found no host, cloning a missing repository) with no ticket or lane for the class.

## Known friction (from prior runs)

- **The loops were rebuilt by hand after every restart.** On 2026-09-26 four prose checkpoints (10:45Z, 13:15Z, 15:10Z, 19:50Z in `$registry_root/.claude_scratch/handoffs/`) each listed the running workflows by task id for the next session to resume by hand. The checkpoint schema and units 3 and 6 replace that. → RULING 2026-09-26T21:22:31Z lane=orchestrator-83, OMN-19815
- **A drain ended with no successor** (2026-09-25/26). Superseded: the controller owns landing now, so there is no successor to queue and unit 4 checks the controller instead. → RULING 2026-09-26T01:01:16Z lane=orchestrator-83, then plan section 7
- **Nothing ran this skill after a restart.** On 2026-09-29 the session restarted at about 06:36Z and no one invoked it: every CronCreate tick was gone and no merge was counted for about three hours. The SessionStart hook now injects the binding instruction. → OMN-19815
- **A two-day-old checkpoint asked for nine dead resumes and a new drain.** The newest checkpoint on 2026-09-29 was written 2026-09-27T01:13Z; `--after-restart` reported 17 missing loops, including a launch of `repo-drains-83k`. Checkpoints now expire at 12 hours, drains are never resumed, and the hook writes the checkpoint on every launch. → OMN-19815
- **Units 4 and 5 still wired the Claude drain** after it was stopped for starting 202 agents for 1 merge. Unit 4 is the controller check and unit 5 is the merge-throughput tick. → OMN-19815, OMN-19998
- **A limit reset read as a live limit.** Five workflows were stopped after the operator said limits had reset. Unit 3 resumes by run id and never stops. → `reference_workflow_agents_retry_after_limit`
- **A running controller tick read MISSING, and one repository's four-hour gap hid inside the fleet total.** The controller judged a tick by the start stamp its heartbeat carries, and a tick runs up to 13 minutes; the throughput tick counted merges fleet-wide, so `omnibase_infra` went 4h22m with no merge while the fleet merged more than 5 an hour. Unit 4 now counts a running tick as live, unit 6 names every repository under its floor, and the tick's read is one tracked script. → OMN-19815
- **A stopped repository waited on the operator to notice it.** On 2026-10-15 the floor lines covered only the four repositories in `landing_floors.json`, so `ops_tooling_pkg` took no merge after 2026-10-14T16:21Z (the watcher state's newest) while its ci fix sat green and unarmed for hours with no line naming it, and `omnibase_infra` sat under floor for more than four hours because every floor line's FIX was the controller's and nothing escalated when the controller did not clear it. The tick now covers the whole landing scope, escalates a repository the controller makes no progress on to one diagnose lane by itself, and names a stuck green PR. → RULING 2026-10-15T20:56:54Z, OMN-19998
- **A hand-written tick replaced the canonical set for about 67.5 hours.** FRICTION 2026-10-02T08:27:05Z lane=m4-c32-launch (existing OMN-19815), the third occurrence after 2026-09-26 and 2026-09-29. The orchestrator session ran with no canonical merge-throughput tick from 2026-09-29T12:48Z to 2026-10-02T08:21Z (about 67.5 h) and no queue-status tick from 2026-09-29T20:43Z (about 59.6 h); a hand-edited session script stood in, product-repo landing floors stayed breached overnight and nothing acting read them. Three mechanism gaps, now closed. (1) The check tested string membership of tick names the model supplied and never compared the cron or prompt with the canonical ones: it now rebuilds the tick set from the transcript and matches the pair byte for byte, and a foreign tick is `MISSING non-canonical`. (2) The binding line was text injected once per compaction, ignored six times: the UserPromptSubmit hook repeats it on every prompt while the condition holds, and the throughput tick's heartbeat is a truth source only that script writes. (3) On a compaction the hook could not read the cron list and reported `UNKNOWN` (`LOOPS MISSING n=0 unknown=3`), and for about 38 hours after a reboot resume no omni hook ran at all because that build had no `hooks.json`: compaction now evaluates the transcript and the heartbeat, `n=` counts unknowns, and the release check in `tests/test_hooks.py` reads the shipped `hooks/hooks.json`. The process rule is in unit 5: tick prompts are never edited in a session, and a restart means `/omni:session-start`, never a hand-rebuilt cron. → OMN-20338, OMN-19815
- **A merge was treated as the finish.** On 2026-11-12 the operator asked for an hourly pass that integrates whatever merged, and for it to be part of session start rather than a cron made by hand in one session. It is the `integration-pass` tick: prompt text and a declared schedule, reusing `adopt_merged.py`, with no new script. → operator 2026-11-12, OMN-19998
- **Interrupts stopped background workflows with no notice, for hours.** On 2026-10-11 an operator message stopped eight lanes in seven workflows, found 90 minutes later; two later interrupts stopped four workflows (review-voter fallback, key pool, landing drivers) for about five hours while the session reported them running; and a resume that read only dangling CLAIMs missed two driver workflows that held no CLAIM, because the checkpoint the hook writes listed one of four. The standing remedy was a memory note the orchestrator had to remember. The lane liveness hook now reads the harness's own record of every run the session started on every prompt and at session start, and the throughput tick alerts past 15 minutes. → FRICTION 2026-10-11T06:39:24Z lane=orchestrator-9f8a, 2026-10-11T19:11:42Z and 2026-10-11T23:15:38Z lane=orchestrator-8e80; OMN-20603
- **The awaiting-reply check ran only when someone remembered it.** Its skill asked for a check every two hours on working days and installed no schedule, so on 2026-10-12 the orchestrator ran it by hand. It is now a canonical session tick that unit 6 checks byte for byte. → OMN-20864
- **Decisions waiting on the operator sank under new topics.** On 2026-10-14 the prod grant registry, the core release order, the delegation quality gate and others sat for hours, several only in a session checkpoint, while the operator's inbox held stale park notices and answered asks. The operator ruled that the ledger already holds them and a tick should query it: the operator-waiting tick prints the open asks, and an answer recorded through `/omni:operator-ruling` closes the ask it answers. → RULING 2026-10-14T18:04:24Z lane=orchestrator-bb1a, OMN-16177
