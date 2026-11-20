---
name: plans-today
description: Bring up every relevant plan for the day so the operator does not have to remember them. Reads the plans at origin/main of the planning corpus, the PR watcher's state file, the rolling ledger (through its reader) and a Linear snapshot, and for each plan dated in the last 14 days, or carrying an In Progress ticket or an open PR, maps its tasks to tickets and PRs, states each task (merged, open-green, open-red, not-started), names the owning live lane or NONE, counts the hours since anything moved, and marks the plan STALLED, IN-PROGRESS, NOT-STARTED or DONE. Prints a short ranked list with stalled and unowned plans first and a next action each, writes a detail file and a plans-today JSON, and sends one ledger MSG for each stalled plan with no owner. Use for "what are the plans today", "what did we drop", "what is stalled", and it runs as unit 2 of /omni:session-start.
prosthetic: true
replaces_when: "An omnimarket node folds the plans registry, the PR-state projection and the work-ledger projection into one plans-of-the-day projection that the plans page and session start read, on two consecutive mornings with no plan missing from it. Nothing today joins them."
restored_from: "none. New process, from RULING 2026-09-29T15:10:02Z lane=orchestrator-0c2f (ticket OMN-20099): the operator asked for a skill that brings up all relevant plans for the day, called by the session start skill and runnable directly"
ticket: OMN-20099
---

# Plans today (prosthetic)

Plans live in the knowledge base, the Program Board, Linear, open PRs and the ledger, and nothing
joined them: on 2026-09-29 the work-ledger plan, the GitHub PR-state plan and the delegation
judgeability plan each went quiet with no owner and nobody was told. This skill is the join. It is
**thin**: it calls one script beside this file and one existing skill (`/omni:ledger-msg`, through its
own executor), and re-implements no other skill's logic.

## Run it

1. **Write the Linear snapshot** (the script makes no network call; you give it the Linear state). The
   full read is about 500 In Progress issues, so **hand this step to a Workflow lane** (or any agent that is
   not the foreground) and take back only the file path and the row count. The lane calls the Linear MCP
   `list_issues` with `fields` of `id`, `status`, `updatedAt` and `priority` and `limit` 250, following the cursor until
   `hasNextPage` is false: once with `state` set to `In Progress`, once with `updatedAt` set to `-P2D`
   (catches tickets that finished or were touched in the last two days). It writes one line per issue,
   `OMN-1234 In Progress 2026-09-29T16:43:51Z priority=High` (id, the status name, the update time, the
   priority name; ` priority=` is optional and is omitted for "No priority"), to
   `$registry_root/.claude_scratch/plans-today/linear-<UTC date>.txt`. A JSON file
   `{"issues": [{"id", "status", "statusType", "updatedAt", "priority"}]}` is read too.
   The same lane then writes `linear-<UTC date>.json` beside the text file with the signed-in user's open
   issues (id, title, status, statusType, assignee, labels, project, updatedAt, description; `operator` is the
   Linear user id) by running `cd "$registry_root/omnimarket" && env -u PYTHONPATH uv run --frozen python -m
   omnimarket.nodes.node_linear_snapshot_effect --out-dir "$registry_root/.claude_scratch/plans-today"` (the shell's
   `LINEAR_API_KEY`, OMN-22361). The throughput tick's lab fill reads that file for the operator's open
   tickets with no live CLAIM and no open PR; without it the `lab-fill-generator` line says `linear_snapshot unread`.
2. **Run the script:**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/plans_today.py" \
     --linear-snapshot "$registry_root/.claude_scratch/plans-today/linear-<UTC date>.txt" \
     --orchestrator "$SESSION_LANE"
   ```

   It needs `registry_root` and `ONEX_LEDGER_PATH` (both from `session.env`) and fails fast without them.
   It refuses, with the fix in the message, when the Linear snapshot is missing, the PR watcher's
   state is older than 90 minutes, or the knowledge-base clone is absent.
3. **Read the output.** stdout is one line per plan: rank, verdict, owner, hours idle, title, next
   action. Then the detail file (`$registry_root/.claude_scratch/plans-today/<UTC date>/detail.md`: the task
   table of every plan, the evidence basis of every state, the delegation run ids) and
   `plans-today.json` beside it (schema `omni.plans-today/1`, `scripts/plans_today.schema.json`), which
   `/omni:queue-status` reads for its one summary line.
4. **Act on the top of the list.** A `STALLED` line with `owner=NONE` already carries its MSG to the
   orchestrator lane (`emit-msg`, below). Dispatch its next action, or say why not.

`--plan <text>` (repeatable) limits the run, its ranking and its MSGs to plans whose path contains the text. `--summaries none` skips the delegation for a fast run. `--json` prints only the JSON on stdout. `--summaries-budget <s>` bounds the whole delegation phase (default 330 s) and `--summary-timeout <s>` one call (default 240 s). `--no-msg` sends no MSG and exists for dry runs and tests: it is
never used from `/omni:session-start`, because a session start that silences the MSG hides the stall it
just found (no observe-only mode: RULING 2026-09-29T12:02:35Z lane=orchestrator-83).

## What it decides, and where it reads

Each decision below is the script's, recorded here so a change to it is a change to this file.

- **Plans are read at `origin/main`** of the knowledge-base clone after the script's own git-protocol
  fetch (not a GitHub API call, and not one a lane types: the lane git-fetch guard, OMN-20495, refuses a lane `git fetch`), never from the working tree: the local clone was 151 commits behind
  on 2026-09-29. A plan is a top-level `beta/plans/*.md` (the `archive/` rows are terminal). Its date
  is the file name's date prefix, else its registry entry's date (`PLAN_LIFECYCLE.yaml`, read for the
  date, the title and a completed-ticket fallback), else its `state_as_of:` line.
- **`beta/GOAL.md`** is read for its `state_as_of` stamp only, shown in the header line and the JSON: the week's rows, dropped work and proposed dispatch live in that file, and this list does not repeat them. The Program Board page is a published page behind edge auth and is not read.
- **Selected** when dated in the last 14 days, or when a ticket it maps (its task tickets and its
  header `Epic` or `Ticket` lines) is In Progress in the snapshot, or when a PR it names is open in the
  watcher.
- **Tasks** are the rows of a table that has a ticket column or a `Task`, `Step`, `Item` or `Work`
  column, plus headings and bullets that start with a task label (`T1.1`, `JI.3`, `M8`). A task with no
  ticket is `no-ticket`, counted apart from `not-started`. Tasks that map the same tickets are one task.
- **State of a ticket**: an open PR that cites it in title, body or branch name and is red (the watcher's
  `cls` red, or any red check) is `open-red`, otherwise `open-green`; a merged PR, or a completed
  Linear or registry state, is `merged`; else `not-started`. A task takes `open-red` over `open-green`
  over `merged` (all its tickets) over `not-started`. Its evidence basis is in the detail file.
- **Owner** is the live lane holding an open CLAIM naming the ticket or the PR: no TERMINAL from the lane
  since the claim and a row from the lane in the last 45 minutes, the rule `wave.py owners` applies. A
  silent claim is `NONE (stale <lane>)`.
- **Hours idle** is the time since the newest of a ledger row naming a plan ticket or PR, a PR update,
  and a Linear update. This skill's own MSG rows never count as movement.
- **Verdict**: `DONE` when every ticketed task is merged; `NOT-STARTED` when no ticket has a PR, a
  claim, a ledger row or a started Linear state; `STALLED` when nothing moved in 24 hours or an
  `open-red` task has no owner; else `IN-PROGRESS`. Rank: stalled and unowned, stalled and owned, in
  progress and unowned, in progress and owned, not started, done; longest idle first within a class.
- **The next action is computed, never delegated.** A delegated action would state a decision the facts
  do not contain (2026-09-26 finding), so the shell writes it.
- **Priority and next-action ticket (machine-readable).** Every plan in the JSON carries `priority`
  (`urgent`, `high`, `medium`, `low` or `unset`) and `priority_source` (`plan-header`: the plan's own
  `Priority:` header line, `P0` to `P3` read as urgent to low; `linear`: the highest Linear priority among
  its tickets in the snapshot; `none`), and `next_action_kind` (`dispatch-fix`, `hand-to-drain`, `dispatch`,
  `land-or-close`, `mint-tickets`, `read-plan`, `wait`, `decide`, `none`) with `next_action_ticket`: the first
  ticket of the task the sentence names, else the plan's first ticket, else null. A consumer filters
  `verdict == "STALLED"` and acts on the kind and the ticket, never on the sentence
  (`scripts/plans_today.schema.json` requires all four).
- **Every child is bounded (OMN-20787).** A child runs with a deadline (120 s unless the call says more:
  300 s for the ledger read), no stdin of the caller's, its own process group (killed whole at the deadline)
  and its output in temporary files, so a descendant holding a pipe open cannot hold the script. A timed-out
  git or ledger read refuses with the command named (exit 2). The delegation phase has one budget
  (`--summaries-budget`, 330 s) across all plans and all rungs: a plan whose calls do not finish in it keeps
  its template sentence. A timed-out MSG send stops the remaining sends (exit 4). The GLM rung asks the
  harness for at most 170 s, because `harness_delegate.py` refuses a `--timeout-s` of 175 s or more.
- **Summary prose** (two sentences for each of the first eight stalled or in-progress plans, `--summary-limit`; the other plans carry a template sentence built from the same counts, marked `summary_source=template`; a delegate call takes one to three minutes on the lab, the calls run in parallel, and unchanged facts reuse `summary-cache.json`) is asked from `onex delegate` on the lab
  first (`--task-type summarization`, deployed lane, then in-process), then GLM through Claude Code
  (`harness_delegate.py run --harness claude-glm --model glm-5.3-flash`, its `answer.md` read through the
  receipt). GLM runs only through Claude Code: the Coding Plan terms bar direct API calls, so the cloud-glm
  backend pin of `onex delegate` is retired and always fails (omnimarket#3136, OMN-20173).
  The delegate is asked for prose only: counts, identifiers and the verdict stay in the shell. A script
  check rejects any summary that carries a number or an identifier that is not in the computed facts, a
  count on the wrong label ("3 open-red" when 1 is), or that omits the verdict; a rejected or refused summary falls back to a template sentence, marked
  `summary_source=template`. The run ids are in the detail file.
- **`emit-msg`**: each `STALLED` plan with `owner=NONE` gets exactly one MSG to the orchestrator lane,
  through `/omni:ledger-msg`'s own executor (`scripts/skill_exec.py`), naming the plan and the next
  action. The dedupe key is the plan path plus a digest of the plan's state (verdict, each task's state,
  owner and PRs, and the plan's PRs) with no time window (OMN-22249): an unchanged plan is never re-sent, and a change
  of one task state sends exactly one MSG for that plan. It is kept in `msg-dedupe.json` at the root of the
  output directory, not in the day's folder, one entry per plan. The MSG is a report from sender `plans-today` with no
  `needs`, `kind`, `question`, `pr` or `head` cell, so the handoff inbox gate counts it as a notice. A ticket with child
  tickets in the Linear snapshot (a JSON issue names it in `parentId` or `parent`) is an umbrella: it is never an unowned red nor the ticket of a `dispatch-fix` next action. A failed
  send makes the run exit 4, prints `MSG failed: <plan path> rc=<exit code> <reason>` and records the same
  detail in the detail file's MSGs section. The row id is `<second>-<lane>`, so two sends inside one second
  made the second a duplicate-id refusal (exit 65), reproduced 2026-10-15; the send waits out the second and goes
  once more on that refusal alone.

## Reads nothing else

No `gh` and no GitHub API call: PR state comes from the watcher's state file only, and a test fails when
a GitHub client is spawned. The ledger is read only through `onex_ledger.py query`, never by opening the
file. The plans page on the Program Board reading the JSON is a follow-up owned by that page's ticket.

## Ledger

This skill writes no row of its own except the `emit-msg` MSG described above, through `/omni:ledger-msg`.
Any other row goes through `/omni:ledger-write`.

## Known friction (from prior runs)

- **Plans went quiet with no owner and nobody was told.** The work-ledger, GitHub PR-state and
  delegation-judgeability plans stalled together on 2026-09-28 and 2026-09-29. → RULING 2026-09-29T15:10:02Z lane=orchestrator-0c2f, OMN-20099
- **The local knowledge-base clone lags.** Reading `beta/plans` from the working tree returned a plan set
  five days old. The script reads `origin/main` after a fetch. → OMN-20099 premise 5
- **The plan registry is stale by design.** `PLAN_LIFECYCLE.yaml` was last verified on 2026-09-24 and
  omits the newest plans, so it is a fallback for date and completed tickets, never the source of state.
  → `beta/plans/PLAN_LIFECYCLE.yaml`, `meta.last_verified`
- **A default run outlasted a ten-minute caller and was killed twice on 2026-10-09 around 07:00Z.** The
  FRICTION row blamed a pipe-buffer deadlock; `subprocess.run(input=..., capture_output=True)` cannot deadlock
  on size (4 MB in and out returns at once: `test_hang_reproduction_pipe_buffer_is_not_the_cause`). Measured
  instead: the delegation phase had no total bound (a lab call up to 240 s, an in-process retry 240 s and a GLM
  call 300 s for each plan; `onex delegate` against a down lane waited 179 s on 2026-10-09), the GLM rung asked
  the harness for 240 s and the harness refused it at once (exit 64), and the other children had no deadline,
  inherited stdin and read pipes a grandchild could hold. → OMN-20787, `-k hang_reproduction`
