---
name: merge-sweep
description: "One read-only reading of the PR fleet and the lanes it implies, then a Workflow that dispatches each planned lane to a lab host. Counts product merges only (docs repositories and docs-only PRs excluded) against the per-core-repo floors, calls the landing controller stalled when it dispatched no worker over its last three ticks (or when its ticks cannot be read), classifies each red PR on the newest run of every check (cancelled-latest, draft-era, workflow-scope-arm, stale-base-sql, real), finds chain heads, the PRs the controller gates at head_cap that conflict, and the PRs a merged or green PR supersedes (the only PRs it plans a fix or close lane for; no escalation lane), skips merged, closed and live-owned PRs, takes over stale claims, runs at most hourly, and checks whether the fixes other tickets own have shipped. Load decides placement only, never whether a lane runs. Each lane rechecks its PR with --claim-check before touching it. Use when the orchestrator wants the fleet's merge blockers turned into lab lanes in one pass."
prosthetic: true
replaces_when: "The landing controller (or an omnimarket node it calls) counts product merges per floor, classifies reds on the newest run, plans chain heads, escalations and stale-claim takeovers, and dispatches those lanes itself on two consecutive days, so no sweep is needed beside it."
restored_from: "none: new skill (OMN-20107), from the lessons of the manual merge sweeps of 2026-09-29"
ticket: OMN-20107
argument-hint: "[--json] [--no-lease] [--fixture <reading.json>] [--claim-check <repo>#<n>] [--release-lease --why <why>]"
---

# Merge sweep (prosthetic)

**Wired in to the merge-throughput tick.** The launch decision is a script's, not a model's (OMN-20864, operator
2026-10-14: a sweep that planned 0 lanes cost 63,372 subagent tokens, and one that found the lease held cost 58,287).
When the tick finds a free Claude lab slot it reads the sweep lease from its file (`sweep_rules.lease_peek`, nothing
written) and, if the lease is free, decides from the plan a previous `sweep_read.py --no-lease --json` wrote, then
prints one line before its status line (`sweep_rules.launch_decision`). The tick never waits for the read, which takes
50 to 100 s and the foreground is cut off at two minutes: a plan under 20 minutes old (`sweep-plan.json` in the
session-start state directory) decides and the line ends `(plan read <n>m ago)`; an older, missing or unreadable plan
is never decided from, the tick starts the read detached and prints the `plan is being refreshed` line below
(OMN-20864):

- `sweep: launch lease=free planned=<n> (<kind>=<n> ...) skipped=<n> (<reason>=<n> ...) max_lanes=<free slots>`: the
  lease is free and the plan holds a lane. Only this line has the orchestrator launch the workflow below, with lane
  `sweep-<session lane>-<HHMM>`, parent the session lane and `max_lanes` the line's.
- `sweep: not needed: 0 planned, 17 out-of-scope infra_repo`: nothing planned, with the skipped counts by reason.
- `sweep: not needed: lease held until <t> (a sweep completed <t>); plan not read` (or `held by a sweep running since
  <t>`): the tick does not run the 20-second read when no decision can change.
- `sweep: not launched: plan is being refreshed (last read <n>m ago | no earlier read)`: the plan is stale or missing and
  its read is running detached; the next tick decides from what it wrote. After a failed read the line adds
  `; the last refresh failed: <why>`, and nothing is launched on a guess. `<why>` is the end of the failure: the
  reader's exit code and last stderr lines, or `timed out after <n>s` and the last stderr lines (OMN-20780).
- `sweep: not launched: plan unreadable (<why>)`: the tick could not make the decision (for example, start the read).

No line is printed when no Claude slot is free. The workflow's own reader still takes the lease, so a second sweep
inside the hour still exits 75. The landing controller does not call it and it changes nothing in the controller.

## Run the reader

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/sweep_read.py"            # summary
python3 "${CLAUDE_SKILL_DIR}/scripts/sweep_read.py" --json     # {"reading": ..., "plan": ...}
python3 "${CLAUDE_SKILL_DIR}/scripts/sweep_read.py" --claim-check omnimarket#3156
```

Requires `ONEX_LEDGER_PATH` (claim rows), a fresh PR watcher state (`ONEX_PR_WATCHER_STATE`, default
`$registry_root/.claude_scratch/pr-watcher/state.json`) and the canonical clones under `$registry_root`
(ops_tooling_pkg's is the registry's sibling: `OPS_TOOLING_PKG_PATH`, else `OPS_TOOLING_PKG_HOME`, else
`$registry_root/../ops_tooling_pkg`). A PR head a clone lacks is fetched from `refs/pull/<n>/head` over git
(OMN-20864, no API read) before it is diffed. It
never reads GitHub (OMN-20864; a lane's gh reads are refused, OMN-20911). It reads only: the state's
merge records of the last window (each merge commit's files from its clone), the state's open PRs of
the fleet repositories (base and head refs, draft, armed), for each one the state's newest check runs
at its exact head joined to their job ids, the landing controller's `ticks.jsonl`
(`LANDING_STATE_DIR`, default `~/.local/state/omni/landing`), host load, and each `components.json` source at
`origin/<default branch>` in its clone. A PR the state holds no check-run read for at its head, a
stale state, an unreadable clone source and an absent tick file are printed on stderr and listed in
`reading.unread`, which includes a red PR's changed-file list when the clone lacks its head and `refs/pull/<n>/head`
no longer serves it (`files:<repo>#<n>`; the PR
is then classified with no files, never as one with an empty list); a PR whose CI the watcher does not read (draft, hold label, production gate) is the
state's own answer, not unread. It holds the sweep lease
(`${XDG_STATE_HOME:-~/.local/state}/omni/merge-sweep/sweep.lease`, budget 900 s) unless `--no-lease`;
a held lease exits 75. A sweep that completes keeps the lease for 60 minutes (`LEASE_HOLD_S`, OMN-20864, RULING
2026-10-14T04:56:52Z: the sweep runs at most hourly): a second sweep inside the hour exits 75 with nothing dispatched
and names the holder and the time it holds until. A sweep that fails releases the lease at once, and an unfinished
holder is still reaped after the 900 s budget (OMN-19998): a read, plan or print that raises prints
`sweep_read: the sweep failed in <read|plan|print>: <error>; lease released, no hold (nothing dispatched)` on stderr, frees the lease
and exits non-zero, so the next sweep is not refused. A sweep that completed but whose planned lanes all failed to start
(2026-10-15: the one lane exited 70 and the lease held until the hour ended, 16 lab slots idle) is released by the
dispatcher with `sweep_read.py --release-lease --why "<why>"`: it frees a completed sweep's lease, names the holder and
the reason on stderr, and leaves a sweep still running alone. The workflow runs it when no lane it dispatched started.

`--claim-check <repo>#<n>` exits 0 for FREE or STALE (cite the printed `supersedes-claim=`), 2 when a
live lane owns the PR, 3 when it is merged or closed, 4 when its state could not be read. The asking
lane's own CLAIM is not an owner: `--self-lane LANE` (default `ONEX_REMOTE_LANE`, then `ONEX_LANE`, which the
remote-lane runner exports) leaves that lane's claims out, because the runner writes the lane's CLAIM with its
`pr=` cells before the engine starts. Every other lane's live claim still exits 2. The sweep's lane brief passes
`--self-lane` with the lane's name.

Scope (OMN-20864): `sweep_scope.json` names the repositories the sweep plans no lane for, each with the ruling
that put it there (today `infra_repo`, out of M4 as cloud work, `omnigemini` and `omnicursor`). It is the one
repository-scope setting: the landing controller and the merge pulse read the same file (landing-controller, OMN-17427). The reader names those open PRs without
reading their checks (`reading.out_of_scope_prs`), the plan drops them from every lane kind (diagnose, escalation,
land-chain-head, fix) and lists each in `plan.skipped` with `why: out-of-scope-repo`, and the summary prints
`skipped out-of-scope=<n> repos=<list>` (`0` and `-` when nothing was dropped). The PRs themselves print on a line of their own, `out-of-scope prs=<ids>` (`-` when none), apart from `reds=`, which never counts them. Lifting a repository is a new
ruling and an edit to the file; an unreadable file stops the read, because an unread scope is never an empty one.

Diagnose placement (OMN-19998, OMN-17427): a diagnose lane with a `controller: ...` reason reads the controller's own
files (`ticks.jsonl`, `decisions.jsonl`, `state.json`, `workers/<lease>/result.json` under `~/.local/state/omni/landing`),
which exist on the controller's host only. Five diagnose lanes placed by load on 2026-10-13 ran on h903 and h908 and each
ended "unreadable from this host". `controller_host.json` names that host; the reader puts it in `reading.controller_host`,
and the plan gives such a lane (and no other) `host`. A diagnose lane planned only for `under floor: ...` reads the ledger
and the repositories' git history, which any pool host has, so it carries no `host` and is placed by the pool. Every
diagnose lane carries `host_why`, the sentence saying which of the two it is, and the summary prints `host=<name>` on a
pinned lane's line and `pool-placed` on an unpinned one; it never prints a host the plan did not pin. A pinned lane
planned from a reading with no controller host is refused: an unread host is never replaced by a guess made from load.
An unreadable or malformed file stops the read. Moving the controller is an edit to the file.
The pin travels as the brief's own column-zero `Required host: <host>` line, which `merge_sweep.js` writes when the plan
pins the lane (ops_tooling_pkg), and which the runner (`brief_prerequisites` in `remote-lane/scripts/onex_remote_lane.py`,
which asks `node_brief_prerequisites_compute`) reads as for every other lane: the lane lands there whatever the caller
passed, keeps the pin when the lane queue relaunches it, and refuses a `--host` naming
another host. The brief's title line pins nothing: on 2026-10-18 the workflow's plan schema dropped `host`, and the title
was read as the pin for every diagnose lane until it held a floor-only lane (Known friction, 2026-10-22).

Fix and close lanes (OMN-20864, RULING 2026-10-14T04:56:52Z): the landing controller lands, so the sweep plans no
escalation lane and no fix lane for a red PR. `plan` plans a `fix` lane only for a PR the controller gates at
`head_cap` whose merge state is conflicting (`reading.head_cap_conflicts`: the newest tick that carries a
`worker_gated` map names the PR `head_cap`, and the watcher's review record reads its merge state `DIRTY`; an unread
merge state is recorded as `review:<repo>#<n>` and plans nothing), and a `close` lane only for a PR a merged or green PR
carries the same change of (`reading.superseded`: the same ticket in the title and the same non-empty set of changed
files; a merged superseder is any merge the state keeps for the repository, a green one an open PR with a lower number,
so two identical green PRs keep the older; a file list the clone cannot give matches nothing; a PR whose head has the
superseder's commit in its history, or that sets a different `"version"` in those files, is the next change and not a
copy, so the bump after a bump is never closed as superseded by the last one, and an ancestry the clone cannot answer
is recorded as `ancestry:<superseder>-><pr>` and plans nothing; OMN-20864). A PR in both gets the
close lane. The reds, chain heads and escalations are still read and printed (`reds=`, `chain_heads=`,
`escalations=`), and the land-chain-head and diagnose lanes are unchanged. The owner, handoff, blocked and scope
gates below apply to both lanes; the summary prints `head_cap_conflicts=<n> superseded=<n>`.

Handed off (OMN-20864): the reader gives each fix and escalation entry `handed_off`, the newest MSG to
`landing-controller` that names the PR at its current head, read through `parse_rows` like every other ledger
row (`handoff_at_head`; a handoff at another head, a short or absent head and a MSG to anyone else do not match).
The plan skips an escalation or a fix there with `why: handed-off`, and a PR a live CLAIM (by PR or by its ticket) names
with `why: live-owner`; the summary prints `skipped handed-off=<n> prs=<ids>` and `skipped owned=<n> prs=<ids>`.
A green PR with such a handoff that the controller still escalates is printed once as
`controller-stuck=<n> prs=<ids>` and `plan.controller_stuck`; the controller's re-admission path owns it and no
lane is planned. A new head, or a PR that is no longer handed off at its head, plans a lane again.

Handed off at the same head, behind a strict order (OMN-19998): the reader gives each chain head `head`, `handed_off`
and `strict_queued`, the controller's reason from `strict_queued`: the newest tick carrying a `strict_order` or
`strict_deferred` list names the PR in a base's `held` or `yielded` list, as its `inflight` PR, or as a deferred
action. A chain head handed off at its current head that the newest tick lists so plans no `land-chain-head` lane; the
plan skips it with `why: handed-off-same-head` and the controller's `reason`, and the summary prints
`skipped handed-off-same-head=<n> prs=<ids>` and one `  handed-off-same-head <pr>: <reason>` line each. Both halves
are needed: a handoff at an older head, or a tick that no longer lists the PR, plans the lane again.

Blocked at the head (OMN-20864, OMN-17427): the reader gives each fix, close, chain-head and escalation entry
`blocked`, the newest attempt at the PR's current head when it failed (`blocked_at_head`, which reads the one attempt
record, `plugins/omni/scripts/ledger_tail.failed_at_head`, over `parse_rows`; the landing controller reads the same
ledger rows). An attempt is any lane's TERMINAL naming the PR: a sweep lane's, a controller worker's or any other
lane's. The PRs come from the TERMINAL's `pr=` cells, else the CLAIM it closes, else the lane's newest CLAIM; the
head from the TERMINAL's `head=` cell, else the CLAIM's, and only for a row that names a single PR. `outcome=blocked`
or `outcome=failed` at the head holds the PR until its head moves; a later attempt at the same head that did not fail
re-admits it. A failed row with no head holds the PR for 2 hours only, because it cannot say which head it met, so a
lane that ends blocked writes `head=<sha>` on its TERMINAL. A draft is never planned, whatever lane it would get
(`why: draft`). The plan skips the entry with `why: blocked-at-head` and the summary prints
`skipped blocked-at-head=<n> prs=<ids>`.

Diagnosed recently (OMN-17427): the reading records every diagnose lane TERMINAL of the last two hours in
`reading.diagnoses` (`recent_diagnoses`, over `parse_rows`; a diagnose lane's dispatched name ends in
`-diagnose-<n>`, and one that ended `outcome=blocked` never finished its diagnosis, so it counts for nothing),
each with the controller stall reasons the ticks give as of its stamp, beside `reading.product_merge_at` (the
newest product merge per repo in the window) and `reading.open_by_repo` (each repo's open PRs the landing controller can land, by the rule
`pr_state_local.waiting_on_controller` that `floor_alarm` counts with: OPEN, not a draft, not `held-excluded`; `null` when the
open read itself refused, because an unread set is never a zero). The plan plans no second diagnose lane while
the newest one is inside two hours, its controller reasons are the reading's and no under-floor repo has taken
a product merge since it ended; the skip is listed in `plan.skipped` with `why: diagnosed-recently`, naming the
lane. A repo with zero such PRs is quiet, not under floor: there is nothing in it to diagnose, so its floor
breach alone plans no diagnose lane (the sweeps of 2026-10-13 re-diagnosed one supply-bound stall all morning, and from
2026-10-18 a repo holding only drafts, omnidash#337 and #421, drew one every two hours until the count left drafts out).

A CLAIM owns a PR only by naming it, by the one owner rule (`plugins/omni/scripts/ledger_tail.claim_names`, OMN-17427): in its
`pr=` cells, or as the PR's head branch (a whole token of at least eight characters in the CLAIM's text). A cause
cell, a repo#n in the CLAIM's prose and a worktree path never own a PR. A ticket never owns a PR (OMN-19998: a live lane on OMN-19998 naming no PR read as the
owner of four conflicted PRs of that ticket and the sweep skipped all four; OMN-20864 had already refused the ticket
match for a CLAIM that names other PRs, and eight sweep lanes ended skipped-owned on a fourth PR of the ticket). That
rule is `claim_owner`'s, so `--claim-check`, the fix path and the escalation path all apply it; the sweep reads only
`pr=` cells for a PR, so a lane that works a PR writes it there.

`--fixture <file> --json --no-lease` plans from a saved `{"reading": ...}` with no network.

Frozen bundle (OMN-21073, shadow tooling, deleted with the script): `--now <utc>`, `--floors <file>`, `--scope <file>`,
`--components <file>`, `--load1 <x>`, `--cpus <n>` and `--ticks <file>` each replace one live input and default to
today's behaviour. `--now` is also the time the watcher state's freshness and the ledger's claim horizon are judged
against. With all of them set and `ONEX_PR_WATCHER_STATE` and `ONEX_LEDGER_PATH` naming copies, two runs print the same
`--json` and the same summary however the live floors, scope, components, load and tick files change in between. The
scope the reader read is recorded in the reading as `out_of_scope` and `plan` takes it from there, so live planning,
`--fixture` planning and the summary all use the captured scope; a fixture whose reading carries none reads
`sweep_scope.json` (or `--scope`). An unreadable floors, scope or components file stops the run.

## Run the sweep

Launch the packaged `src/ops_tooling_pkg/handlers/merge_sweep/merge_sweep.js` by absolute
`scriptPath`, resolving its repository from `OPS_TOOLING_PKG_PATH` when set, otherwise
the `../ops_tooling_pkg` sibling of `registry_root`, with args
`{skill_dir: "${CLAUDE_SKILL_DIR}", lane, parent, ticket, model?, max_lanes?, retry_wait_min?, retries?, landing_ruling?, landing_ruling_lane?}`.
It runs the reader once, then builds and checks a brief for each planned lane: each lane brief is
written, then the committed rules block (`scripts/lane_rules_block.py`) and the
lane-brief 3a block (`../lane-brief/scripts/lane_brief.py constraints`, landing RULING
2026-09-29T06:34:17Z lane=orchestrator-83 unless overridden) are appended, and `lane_brief.py check --lab`
must pass before the runner is called; a refused brief returns `brief-refused` and dispatches
nothing. `ticket` (an OMN-<n> the lane works under) is required: the check refuses a brief that
names a Done ticket, so a closed one cannot be carried.
For each brief that passes the check, it dispatches the planned lane through
`../remote-lane/scripts/onex_remote_lane.py` on the lab. Exit 75 from the runner means no host
qualifies (the lab hosts first, then the launching host as the last placement, RULING 2026-10-02T11:39:15Z lane=orchestrator-0c2f): it waits and retries. Exit 77 means the host's
Claude account is limited: it retries once on another host. Lanes beyond `max_lanes` wait for the next
sweep; no lane is filtered by load.

Tickets (OMN-17427): `sweep_read.py` reads the ticket every planned lane works under from Linear, live, and applies the brief
check's own rules to it (the `node_ticket_text_effect` node (`plan_with_tickets`); `lane_brief.py` is loaded and its functions are called, no rule is
copied), so a lane the plan keeps names a ticket `lane_brief.py check --lab` admits. Three sweeps of 2026-10-30 dispatched nothing
because the planner chose from PR titles alone: (1) a diagnose ticket whose own words plan "cut a release" (RULING
2026-10-29T01:50:26Z: iterate with dev tags), (2) a fix lane for omnimarket#4563, whose PR cites only the umbrella
(`REMOTE-LANE-UMBRELLA-REFUSED`), (3) a diagnose ticket (OMN-21478) whose implementation had merged
(`ticket-state-ack=OMN-21478:merged`). Now:

- a diagnose lane takes the first ticket that is open, not an umbrella (OMN-17427, or any ticket with children), has a description,
  whose words plan no release cut and whose implementation has not merged, in this order: a ticket a red PR cites (most cited
  first), a red commit's ticket, `MERGE_SWEEP_DIAGNOSE_TICKET`, the session ticket (`MERGE_SWEEP_SESSION_TICKET`, else the newest
  CLAIM of `ONEX_LANE`), the overlay's `standing_tickets['merge-sweep-diagnose']`. If the only ticket is a merged-implementation one
  that open red PRs still cite, the lane takes it with `ticket-state-ack=<id>:merged (the work still stands: open PRs under it are
  ...)` in its `reasons`. With none the lane is not planned (`skipped diagnose-ticket-needed`) and `needs_ticket` says why. The
  chosen ticket is `lane.ticket`. The dispatcher (ops_tooling_pkg, frozen) picks its diagnose ticket from `reading.reds[].ticket`,
  so those hold only the lane's ticket (the cited one is kept as `cited_ticket`) and it can pick nothing else. With no red PR the
  dispatcher takes the diagnose or session ticket, else the standing one, and that one alone is vouched for.
- a `fix` lane keeps a PR only when its ticket is usable. A PR that cites only an umbrella (or no ticket) takes the non-umbrella
  ticket Linear already has the PR attached to; with none the PR is dropped (`skipped ticket-needed`) and listed in
  `plan.needs_ticket` and on the `needs-ticket=` summary line. The orchestrator running the sweep mints that ticket through
  `/omni:create-ticket` (a lab lane cannot, and the planner never creates one) and the next sweep plans the lane. `land-chain-head`
  and `close` lanes open no PR and keep the session ticket.
- Linear unreadable (`LINEAR_API_KEY` unset or unreachable): no lane that needs a ticket is planned and the summary prints
  `tickets-unread=1 <why>`; a ticket nobody read is never assumed good.

Source-check fixes (OMN-19998): the shared guard is the `node_cause_fix_guard_compute` node, which
reads existing fix PRs and live cause CLAIMs for the same repository and check from local state.
A conflict lane still resolves its conflict. If it discovers a
base red or a shared red requiring a source fix, it follows the same rule as controller workers:
run `landing_text.py fix-guard --fix-repo <repo> --fix-check <check>` before source-fix work, and
`landing_text.py guard-create --fix-repo <repo> --fix-check <check> -- <onex scm pr-create command>`
immediately before a create. The lane-brief constraints carry this rule into every dispatched lane.
Join an existing fix, report a live owner without touching it, and stop when local state is unreadable.
Carry `Fix-Check: <check>` (and `Fix-Cause: <key>` when known) in the draft body so remote publishing
rechecks the guard. Never search GitHub for a fix.

## Lesson to mechanism

| lesson | mechanism |
| -- | -- |
| 1 product merges only, per-core-repo floors | `product_merges`: docs repositories and docs-only PRs excluded, unread file lists never count; floors from merge-drain `landing_floors.json`; under-floor plans a diagnose lane |
| 2 controller stall | `controller_stall`: zero workers over the last 3 ticks while some tick's `worker_eligible` (open red PRs under no gate, hold or lease) names a PR or carries no such list (OMN-17427), a refused tick counts as zero with no list, fewer than 3 ticks or an absent file is stalled, never healthy; plans a diagnose lane |
| 3 never hold for load | `plan`: load sets `lab_only` (load1 per core above 1.0), never removes a lane; the workflow has no load gate |
| 4 stale claims, claim-time recheck | `claim_owner` (live within 45 min of a lane write or a push, closed by TERMINAL, hand-off, supersession or RELEASE), `claim_check_verdict` and `--claim-check` before a lane touches a PR |
| 5 newest-run classification | `classify_checks`: newest run per check name; a stale red under a newer pass is green; cancelled-latest blocks |
| 6 one sweep at a time | `lease_acquire` / `lease_release`, stuck holder reaped after the budget; a failed read or plan releases and prints why, `--release-lease` frees a completed sweep none of whose lanes started (OMN-19998) |
| 7 chain heads first | `chain_heads`; a green head gets a land lane (a red head plans nothing: the controller lands; a draft is never a head, since the controller holds drafts by design, OMN-19998) |
| 8 escalation_exhausted | `escalations` from the newest tick's degraded list is read and printed; no lane (RULING 2026-10-14T04:56:52Z, OMN-20864); a green handed-off one is `controller-stuck` |
| fix and close lanes | `head_cap_gated` + `merge_state_conflicting` give the `fix` lane; `same_change` gives the `close` lane (OMN-20864) |
| 6 hourly | `lease_complete` keeps the lease for `LEASE_HOLD_S` (3600 s) after a completed sweep; a second sweep exits 75 |
| 4, 8 handed off at the head | `handoff_at_head` over `parse_rows`; `plan` skips an escalation or fix for a PR the ledger shows handed off to landing-controller at its current head (`skipped handed-off`) or live-owned (`skipped owned`); a green one still escalated is `controller-stuck`, no lane |
| 4 chain head handed off at the same head | `strict_queued` over the newest tick's `strict_order` and `strict_deferred`, with `handoff_at_head`; `plan` skips a `land-chain-head` lane for it (`skipped handed-off-same-head`, with the controller's reason); a new head or an unlisted PR re-plans it (OMN-19998) |
| 4, 8 blocked at the head | `blocked_at_head` over `parse_rows`; `plan` skips an escalation or fix for a PR a sweep lane ended blocked on at its current head within 6 hours, or with no head recorded within 2 hours (`skipped blocked-at-head`); a new head re-plans it |
| 1, 2 diagnosed recently, quiet repos | `recent_diagnoses`, `product_merge_at` and `open_by_repo` in the reading (OMN-17427); `plan` plans no second diagnose lane within 2 hours of one with the same controller reasons and no product merge since (`skipped diagnosed-recently`), and a repo with zero open PRs is never under floor |
| 4 claim names PRs | `claim_owner` through `ledger_tail.claim_names`: a CLAIM owns a PR only by `pr=` cell or head branch; a ticket, a cause and a prose mention own none |
| 4, 8 out-of-scope repositories | `load_out_of_scope` reads `sweep_scope.json`; `plan` skips a ruled-out repository's PRs in every lane kind and its under-floor entry, the reader never reads their checks, the summary names the skip |
| 9, 14, 17 red classes | `workflow-scope-arm` (never rerun), `draft-era` (update branch), `stale-base-sql` (update branch) |
| 1, 3, 9, 10, 11, 12, 14, 16, 18, 19 owned elsewhere | `components.json` (`load_components`) + `check_components`: each owning source read live, PRESENT or MISSING with its ticket; never rebuilt here |

## Common rationalizations

Each row is an excuse for reading the sweep's plan as work done, or for fixing one pull request by
hand, with the failure it caused. The rows come from the night of 2026-10-17 and the FRICTION rows
of 2026-10-12 to 2026-10-17.

| Excuse | Why it is wrong | What to do instead |
| -- | -- | -- |
| "The sweep ran, so the blockers are in hand." | Four sweeps in a row planned only a draft lane and dispatched nothing that could land a pull request. FRICTION 2026-10-13T03:31:43Z and 2026-10-13T03:38:15Z lane=orchestrator-31d9: a sweep planned one diagnose lane and dispatched nothing because the brief check scanned an unrelated clone beside the registry. | Read the dispatched count and the lane kinds, not the sweep's exit. A plan of one draft lane with floors breached is a failed sweep: find why it planned so little. |
| "The controller owns this fix, so the sweep plans no lane for it." | The controller was the broken part: green pull requests sat 2 to 4 hours. The sweep calls the controller stalled after three ticks with no worker, and a stalled controller owns nothing. | Treat a stalled controller as the finding. Plan the lane that unblocks its gate or fixes its rule, and name the PRs it holds. |
| "A bot release pull request that is red is the release train's to handle." | FRICTION 2026-10-17T04:36:23Z lane=plugin-bump-820-green: a red release pull request stayed gated and got no worker for a day (about 24 lane-hours). | Plan a fix lane for a red release or version-bump pull request. A red head that no worker touches is a class to fix, not a gate to respect. |
| "I will re-dispatch this one lane by hand." | One instance fixed by hand leaves the class. FRICTION 2026-10-17T08:06:33Z lane=floor-diagnose-omnibase_spi-20261017T0756Z: 17 diagnose lanes for one handed-off cause added nothing the controller could act on. | Before planning a lane for a cause, read the newest TERMINAL and MSG for it. Re-plan only when the cause or head changed; otherwise fix what keeps it from landing. |
| "The machine is loaded, so I skip the dispatch." | The skill places by load and never decides by it. A claim of pressure without a reading also misled the operator on 2026-10-17 (61 GB was free). | Dispatch, and let placement choose the host. Print a measured load or memory reading if you say anything about capacity. |
| "I can start on that pull request, the claim looks old." | A live CLAIM row (last 45 minutes) or a controller lease owns the pull request. A second lane duplicates or corrupts the first. | Run `--claim-check <repo>#<n>` in every fix lane before touching it. Owned, merged or closed since the plan: list it and move on. |
| "The fix merged, so the sweep's finding is closed." | A merge ships a plugin change only when the version bump lands and the installed copy matches. | Use the sweep's check that the fixes other tickets own have shipped, and read the installed version. |
| "A third sweep would re-plan the same pull requests." | FRICTION 2026-10-13T08:46:52Z lane=orchestrator-31d9: the lab sat idle 28 minutes with free slots on that reasoning. | Run the sweep (at most hourly) and fill idle slots with landers or triage. A repeat plan that is empty is itself a finding. |

## Red flags

- A plan with no non-draft lane while any per-repository merge floor is breached.
- A sweep that exits without dispatching, or a brief check that refused a brief that reads clean.
- The same cause, repository and head planned for a lane more than once.
- A lane started on a pull request without `--claim-check`, or on one the controller holds a lease on.
- A controller reading marked stalled that the report does not put first.
- A red bot release or version-bump pull request with no lane in the plan.
- A hand fix of one instance with no ticket or lane for the class.
- A sweep counted as work started when its plan held only a draft.

## Known friction

- 2026-10-22 01:02Z to 01:20Z, a diagnose lane that never started (OMN-17427): the sweep planned one diagnose lane for
  `under floor: omnibase_infra,omnibase_spi,plugin-tooling-pkg` alone, pinned it to h906, and placement refused h906 four
  times (priority holdback, plugin parity, CPU; four `no-host` exit-75 receipts, `queued.pin: h906`,
  `prerequisites: {'host': 'h906'}`) while host.example and h904 each had a free slot, so the under-floor repositories got no
  diagnosis. Two pins held it: `plan` gave every diagnose lane the controller host, and the runner read the brief's
  `merge-sweep diagnose lane` title as a `Required host:` line. Now only a lane with a controller reason is pinned, by the
  brief's own `Required host:` line, and `host_why` says why (Diagnose placement above).
- 2026-10-30 11:37Z and 13:07Z, three merge sweeps dispatched nothing (OMN-17427): the planner chose a diagnose ticket whose words
  plan a release cut, a fix lane for a PR citing only the umbrella, and a diagnose ticket whose implementation had merged, and
  `lane_brief.py check` refused each brief. The planner now reads the tickets live and applies the check's rules (Tickets above).
- Lesson 12 (gh 403 on org Actions variables) has no fix point in any source yet, so its component
  reads MISSING with "no fix marker defined yet" until its owner names one.
- Markers for fixes that have not shipped are the owning ticket id or the fix's own term; when the fix
  lands under another spelling, the marker is updated in the same change that confirms it.
- The watcher state does not carry a PR's last `ready_for_review`, so the reader assigns no
  `draft-era` class; such a red reads `real` or `cancelled-latest` (OMN-20864).
- A merge whose commit the reader's clone has not fetched yet has unread files and is never counted
  as a product merge (`excluded.files_unread`); a PR head the clone lacks and the fetch cannot get reads no files, so a red
  auto-merge check on a workflow-changing PR reads `real`, not `workflow-scope-arm`.
- `last_push_at` is not read live yet, so a claim is live only on a lane write within 45 minutes.
- The controller writes `ticks.jsonl` on the operator's host; a reader run anywhere else reads the
  controller as UNKNOWN (stalled with that reason) and plans a diagnose lane.
- The tick launches the workflow from the ops_tooling_pkg clone on the launching host; a clone
  whose merge_sweep.js predates the lane-brief build ignores `ticket` and dispatches briefs without
  3a, so the tick is adopted only once that clone is at or past the change that added the build.
- `lane_brief.py check` reads every ticket a brief names from Linear, so the session that runs the
  sweep needs `LINEAR_API_KEY`; without it every check exits 2 and every lane returns
  `brief-refused` (nothing is dispatched, never a pass).

## Tests

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_lab_run.py" --via bus --lane "<lane>" --repo plugin-tooling-pkg --ref "<pushed branch>" -- python3 -B -m pytest -q -p no:cacheprovider plugins/omni/skills/merge-sweep/tests/test_sweep_rules.py plugins/omni/skills/merge-sweep/tests/test_sweep_read.py plugins/omni/skills/merge-sweep/tests/test_sweep_tickets.py plugins/omni/skills/merge-sweep/tests/test_sweep_dispatch.py
```

`tests/test_sweep_dispatch.py` (needs `node`) runs the dispatcher (`tests/fixtures/merge_sweep.dispatcher.js`, a recorded copy of
the frozen ops_tooling_pkg script, checked equal to it where that checkout exists) with its Workflow globals stubbed
(`tests/dispatch_harness.mjs`) over a recorded reading, so every brief the dispatcher writes goes through the real
`lane_brief.py check --lab` against a loopback Linear and a sandbox ledger, and fails on any refusal. The three refused sweeps
of 2026-10-30 are planted cases, each with a control: the same reading planned without the ticket step is refused (or never
dispatched).
