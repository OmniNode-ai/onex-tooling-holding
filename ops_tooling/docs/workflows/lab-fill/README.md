# lab-fill (the lab fill controller) — format contract

The runnable half is `src/ops_tooling_pkg/handlers/lab_fill/lab-fill.js`, and its config is
`lab-fill.config.json` beside it. This document is the format contract. A format change edits both in
the same commit. `tests/test_lab_fill.py` runs the script's pure block under node, and also runs the
whole script with stub agents, so the decisions described here are tested against the source the
Workflow runtime runs.

## Why

On 2026-10-03 the operator reported idle lab hosts eight times. The session's throughput tick
(`throughput_tick.py`, plugin-tooling-pkg#299) prints `MISSING lab-headroom:<host>`, but it fires only
inside the orchestrator's interactive session. It also counts headroom by the runner's slot caps rather
than by real idle: h903 read full at 6 lanes while 85% idle. This controller runs unattended from
launchd, in the same family as the closer (`dod-closeout-sweep`). It counts both measures, dispatches
the work itself, and records the gap between them.

## Why the budget

Fire 20261003T181004Z was killed at the 1020 s bound during Dispatch after Enumerate paged every
team issue created since 2026-08-30 to find OMN-17427's descendants. The bounded subtree command
and absolute phase deadlines reserve time for Dispatch and the final receipt.

Fires 20261007T205004Z, 211005Z and 221005Z were killed at the same bound, and the completed fires that
day took 650 to 964 s. A deadline written into an agent's prompt does not stop the agent. Enumerate took
170 to 572 s of its 210 s, of which the read itself was 35 to 190 s. The rest was the agent copying the
read's output, up to 436 KB with 274 approved rows, into its answer. When it could not copy all of it,
the agent chose which candidates to keep. In fire 221005Z Enumerate ran 514 s, and Dispatch, whose end
is fixed, cut 9 of 11 selected lanes. Verify took 80 to 243 s of its 60 s. Each phase is now bounded by
code (OMN-17427). The read stops before Enumerate's deadline. Verify's re-read is one command that stops at its deadline.

Fire 2026-10-08T0210Z selected 12 lanes on 11 free slots and placed 1; the other 11 were
`skipped:deadline`. No lane was ambiguous. The one dispatch agent re-checked ownership lane by lane in
prose (the claim index, the PR claim registry, a ledger grep, the watcher), read the clock at 02:21:43Z
against a 02:23:04Z deadline with the checks for the rest unfinished, and stopped. It was the seventh run
with `skipped:deadline` in the ledger (OMN-20690). The deterministic reads are now one command before the
agent starts, each lane has its own slice of the window, and a window that placed nothing fails the fire
and names the lane that used it.

Some fires write their result and STATUS after 570–835s yet keep the session alive
until the 1020s ceiling. The driver polls this fire's non-empty result every 5s,
then grants 90s (`ONEX_MORNING_RESULT_GRACE_S`), capped at 45s before the ceiling
or the time seen if already later. Before terminating a lingering session it logs
the process group, records `settled_after_result` and prints `MORNING_TICK_SETTLED`
with the linger seconds. Version-1 result validation and idle alerts still run;
the ceiling and phase budgets stay the same.

A fire whose Claude run never carried out the Workflow wrote no result, and the driver used to read an absent result as nothing
to judge. On 2026-10-15 every h906 fire from about 00:30Z to 02:50Z logged only "You've hit your weekly limit", the lab sat with
free slots, and nobody was told (OMN-20864). The driver now alerts once for a fire that ends `failed`, `timeout` or
`abandoned_background` with no result: category `lab_fill_refused` when the run log carries a Claude usage-limit notice
(`hit your ... limit`, `usage limit reached`, `out of extra usage`), else `lab_fill_no_result`. The receipt keeps the phase and
exit the run left, names the `degraded_class` (`lab-fill-claude-refused`, `lab-fill-no-result`) and carries the alert's exit in
`idle_alert_exit`. The text says free slots are unread, because no measurement ran. The fire does not dispatch: lab-fill's planner
and dispatch steps are Claude agents, so a fire refused for a limit places nothing until a Claude-free planner exists.

## Invocation

```js
Workflow({ scriptPath: '<abs>/lab-fill.js', args: { date: '2026-10-03', fireId: '20261003T181000Z-lab-fill', config: { /* lab-fill.config.json */ } } })
Workflow({ scriptPath: '<abs>/lab-fill.js', args: { date: '2026-10-03', config: { /* ... */ }, apply: false } })
```

The launchd driver resolves `parentLane` from the live session's `session.env`, overriding the
installed config. `SESSION_ENV` names an explicit session; unattended launchd chooses the newest
initialized session without a later TERMINAL in the ledger. It refuses when no open session can
be read. It reads the file as data and never sources shell code.

The launchd driver reads `lab-fill.config.json` from beside the installed script and passes it as
`args.config` (`morning_workflows_tick.sh`, `PACKAGE_CONFIG`). If the file is unreadable or is not one
JSON object, the fire ends `config_invalid` with exit 65 before any agent runs. A top-level arg
overrides the corresponding scalar config key. Phase budgets and candidate-cache settings come from
the config objects.

| Key (args, or config path) | Default | Meaning |
| -- | -- | -- |
| `date` | required | `YYYY-MM-DD` |
| `fireId` | none | the driver's fire id. The run key is `<date>T<HHMM>Z` from it, else the date |
| `pillar` / `config.pillar` | **required** | the work label (`all` in the shipped config) |
| `parentLane` / `config.parentLane` | **required** | `--parent` of every dispatched lane, and `parent=` on the STATUS row |
| `config.landingRuling.ruling`, `config.landingRuling.lane` | **required** | the routing RULING (stamp and the lane that wrote it) that `lane_brief.py constraints` pastes as the brief's 3a.3 part (OMN-20864). A run without them refuses before dispatching anything |
| `config.authority.ruling`, `config.authority.lane` | **required** | the operator RULING stamp (`YYYY-MM-DDTHH:MM:SSZ`) and the lane that wrote it. `laneTask` renders them, with the parent ticket, as the brief's `AUTHORITY:` line, which a lane's verify-authority-first standing rule reads. A run without them refuses before dispatching anything |
| `parentTicket` / `config.ticketScope.parentTicket` | **required** | the tree the scoped tickets sit under (`OMN-17427`) |
| `milestone` / `config.ticketScope.milestone` | **required** | the milestone a scoped ticket may carry (`M4`). Being under the parent ticket is the scope: a blank milestone passes, a different non-blank milestone is out of scope |
| `config.ticketScope.sprints` | none | a list of `{ projectId, start, end }` sprint windows (dates `YYYY-MM-DD`, inclusive, no overlap). The run date picks the one window that holds it, and that sprint project replaces the parent subtree/milestone restriction for tickets; every pillar is eligible. A run date no window holds refuses the run, naming the date and the declared span, so an ended sprint is never read as an empty one (OMN-17427). Declaring it beside `projectId` refuses |
| `config.ticketScope.projectId` | none | one pinned sprint project, for a config without `sprints`; it does not follow the sprint roll |
| `config.ticketScope.operatorId` | required with sprints or projectId | Linear assignee id allowed alongside unassigned work; another person's tickets are excluded |
| `config.prRepos` | [] | M4 implementation/proof repositories eligible for red or stalled PR repair, independently of the ticket's project or parent |
| `config.fleetRepos` | [] | the repositories a reroute may name (OMN-20842); a lane result naming any other is refused by name and the ticket dispatches nowhere. An empty list refuses every reroute |
| `excludeAreas` / `config.ticketScope.excludeAreas` | [] | whole words that exclude a candidate by title, label or area (`dashboard`, `onboarding`, `cloud`) |
| `config.defects.labels`, `config.defects.terms` | [] | what marks a pillar-quality defect |
| `boundS` / `config.boundS` | 1020 (cap 3600) | fire bound in seconds; phase budgets must total at most this minus 45 |
| `config.phaseBudgetS.*` | probe 150, enumerate 210, dispatch 420, verify 60, fallback 60, report 60 | positive seconds per phase (cap 1800 per key); omitted keys keep defaults |
| `config.candidateCache.fallbackMaxAgeMin` | 720 (cap 10080) | maximum age in minutes for a fallback cache |
| `config.candidateCache.maxCandidates` | 40 (cap 80) | candidates returned by the bounded read |
| `maxLanes` / `config.maxLanes` | 8 (cap 12) | lanes dispatched per run |
| `maxPerHostPerRun` / `config.headroom.maxPerHostPerRun` | 4 (cap 12) | lanes put on one host per run, because a lane's load does not show in the next probe yet |
| `config.headroom.maxBusyPerCore`, `laneCores`, `laneMemGb`, `memHeadroomGb` | 0.75, 2, 8, 2 | the real-idle measure below |
| `stalledHours` / `config.stalledHours` | 6 | a PR with no activity for this long is stalled |
| `landingLane` / `config.landingLane` | `landing-controller` | where a lane hands its PR |
| `laneTimeoutMin` / `config.laneTimeoutMin` | 60 (cap 180) | the runner's `--timeout-min` |
| `apply` | true | false: probe, enumerate and select, then return the plan without dispatching or writing a row |
| `force` | false | skip the idempotency precheck |

The parent lane in the shipped config names the orchestrator session that owns the fill. When that
session changes, the config changes in a PR. The script contains no such value.

## Declared capacity (OMN-17427)

The shipped run cap is **12**, the code cap, and the per-host ceiling is **12**. The old ceiling
of four (clamped to six in code) could not use a 32-core host's idle CPU. At the unchanged 75% CPU
bar and two cores per lane, fully idle h907/h908 allow `floor(32 × .75 / 2) = 12` lanes each;
h903's 12 cores allow `floor(12 × .75 / 2) = 4`. Memory still limits that to
`floor((available GiB − 2) / 8)`, and runner slots/admission can lower it further. Twelve lanes
require 98 GiB available, six require 50 GiB, four require 34 GiB, and one requires 10 GiB.
A read on h908 on 2026-10-06 observed h907 at 59.9 GiB free, h908 at 41.2 GiB, and h903 at
10.2 GiB: these memory budgets allow 7, 4 and 1 additional lanes respectively before live CPU
and runner constraints. Those are observations, not static host guarantees.

The declared M4 PR repositories cover the delegation libraries/runtime, CLI/plugin, consumer-flow
and proof producers: core, infra, omnimarket, omniclaude, omnimemory, omniintelligence,
infra_repo and this tooling repository. Board C11–C17, C28 and C29 name infra and
infra_repo as their proof producers. The sprint ticket source has no repository/pillar exclusion.

## Phases

Every phase has an absolute deadline counted from the driver's fire start, including seconds from
`fireId`; the kill timer starts at that same instant. A manual run without `fireId` uses Probe's first
`clock_utc` read as the start. Probe reads the clock again as `finished_utc`, so the script can skip
live Enumerate when fewer than 60 seconds remain in its window. Late phases do not move later
deadlines: Dispatch always keeps its fixed end time.

| Phase | Default budget (s) | Cumulative deadline from start (s) |
| -- | -- | -- |
| Probe | 150 | 150 |
| Enumerate | 210 | 360 |
| Dispatch | 420 | 780 |
| Verify | 60 | 840 |
| Fallback | 60 | 900 |
| Report | 60 | 960 |

The budgets total 960 s inside the 1020 s bound, leaving at least the required 45 s margin for
agent startup and the driver's receipt writing. A config whose budgets exceed `boundS - 45` is refused.

1. **Probe** (sonnet). Precheck: a STATUS row for `lane=lab-fill` with `run=<run key>` means the run
   was already delivered. Then the remote-lane runner's own placement read runs: `landing_placement`'s
   `load_pool`, `read_pool` (one probe per host, with its admission bar) and `lane_slots`, plus
   `codex_placement`'s Codex hosts, the hosts with a usage-limit mark, and the lanes that the runner's
   receipts show running. The read places nothing and writes no marker.
2. **Headroom** (script, `hostHeadroom`, `planCapacity`). For each lab host (never the launching host),
   two counts are taken:
   - **Real idle.** Free cores are `maxBusyPerCore × cores` minus the busy-core sample, or minus load1
     when the probe read no sample. Lanes by real idle are the smaller of free cores divided by
     `laneCores` and (free memory − `memHeadroomGb`) divided by `laneMemGb`.
   - **The runner's lane slots.** These include its cap and its admission bar.

   A host gets the smaller of the two counts, never more than `maxPerHostPerRun`. A host gets none when
   it is unreadable, limited, refused by the runner, or has no engine login. When real idle exceeds the
   runner's slots, the host is `cap-bound` and the STATUS row names it: that is the h903 case, where the
   cap is the limit and the host is not. The run's budget is `min(maxLanes, sum of host lanes)`.
3. **Enumerate** (sonnet). With headroom and time, one bounded Python command pages open leaf
   tickets from the declared sprint project across every pillar, plus delegation defects. Without a
   project declaration it retains the parent subtree read (eight levels). Both use at most 20 Linear
   requests. The shipped config declares the M4 End-to-End sprint windows from 2026-09-28 to
   2026-11-01 (`ticketScope.sprints`, ids and windows as the sprint board's `sprint_copy.py` names
   them) and the run date picks the sprint; it is not inferred from the umbrella ticket's project.
   A single pinned project read the ended October 5–11 sprint for every tick from 2026-10-12, as
   `ticket:empty:seen=0` with free slots and no alarm. A sprint past the last window is declared by
   appending its project and window; until then the run refuses.

   Red and stalled non-draft PRs in `prRepos` come from the PR watcher state, never GitHub. The reader
   requires schema 1, an inventory tick no older than eight minutes, resync no older than 90 minutes,
   and CI bound to the PR head. A stale snapshot reports `unreadable-from-snapshot`; a missing head
   reports `partial:unreadable-head`. Queued PRs are left to landing. PRs still need an OMN ticket,
   whose person assignment is read even when that ticket is outside the sprint. PR hold-family
   labels are kept as `hold_reason` (the arming-only label does not block repair).

   Ticket and PR ownership come from one whole-ledger claim index and open PR CLAIM rows. Existing
   fences and pending landing handoffs remain enforced before the candidate cap. Only unassigned
   work or work assigned to `operatorId` passes; another person yields `assigned-other`.

   Results are capped after ownership/assignment/fence checks; the shipped candidate cap is 80.
   A `cache-only` fallback runs when live enumeration cannot finish inside its phase deadline.

   The command's `timeout` runs to 45 s (`ENUM_RETURN_S`) before Enumerate's absolute deadline. It
   is read from the clock when the command starts, so a late start shortens the read. It is never
   more than the budget less 30 s and never less than 5 s. The script is given that bound less 15 s
   as `LAB_FILL_READ_BUDGET_S`: each Linear request and the fences call is cut to what is left, and
   when it is spent the read stops, prints its JSON and names the source it was in (`notes`, for
   example `read budget exhausted in project-issues`) instead of being killed with nothing printed.

   The `cache-only` fallback has its own bound, because it runs after the live read timed out, when
   Enumerate's deadline has already passed. Its cap is the Fallback budget (60 s); when less than
   that is left of the dispatch window once Dispatch keeps its last 240 s (`DISPATCH_RESERVE_S`),
   the bound is that remainder. It is never below 30 s (`CACHE_READ_FLOOR_S`):
   measured on a 32-core lab host over a 55,000-row ledger, the whole read took 1.6 s warm, 2.0 s
   with the venv rebuilt and 17.8 s rebuilt on a host running twice as many busy loops as cores.
   Sharing the live read's bound clamped it to 5 s and the fallback never produced a candidate
   (run 2026-10-08T0630Z).

   Two more tier 1 sources are read on every call, live or `cache-only`, because the candidate cache holds
   the sprint tickets only (OMN-20786). Each is one bounded child of the canonical plugin-tooling-pkg
   clone, and each only adds candidates:
   - `plan-stalled`: the `next_action_ticket` of each STALLED plan from `plans_today.py --json --no-msg
     --summaries none` whose `priority` is `urgent` or `high` and whose `next_action_kind` is `dispatch-fix` or
     `dispatch`. The other kinds are not lane work (`hand-to-drain` and `land-or-close` are the landing
     controller's; `mint-tickets`, `read-plan`, `wait` and `decide` are not dispatchable). The tool refuses a run
     with no Linear snapshot and a plan has no priority without one, so the read first writes the snapshot its
     skill documents (the In Progress issues of team OMN and those updated in the last two days, with
     `priorityLabel`) from at most 16 Linear requests of its own.
   - `ruling-pending`: each `mechanism_tickets` entry of each `unmechanized` ruling from
     `ruling_mechanisms.py --json`. That tool exits 1 when anything is unmechanized and still prints its
     report, so exits 0 and 1 are a read and any other exit is not. A ruling with no pending ticket is counted
     (`no-pending-ticket`) and never dispatched: those are the orchestrator's backlog.

   One Linear read of the named tickets then drops, with a counted reason in `source-reasons`, a ticket
   that is Done or canceled (`done`), an epic with children (`has-children`), has an open PR in the PR
   watcher (`open-pr`: in flight) or cannot be found (`ticket-unreadable`). The rest enter the same
   selection as a sprint ticket: ownership by the claim index and handed-off PRs, assignment (`assigned-other`
   unless unassigned or `operatorId`), fences, excluded areas and the unchanged-input rules. After two
   rising reads, the open-count gate ranks eligible non-landing work after landing work, filling only slots
   landing work leaves free (RULING 2026-10-12T05:25:08Z, OMN-20780). They carry their own scope
   (`under_parent` and the milestone do not apply) and the umbrella rule.
   So a ticket both sources name is one lane (`duplicate`), and the next tick finds that lane's CLAIM, or its
   open PR, and dispatches nothing new. A ticket's brief carries the plan or the ruling row it came from.

   Tier 2 reads `lab-fill.approved-work.json` beside the config on every live enumeration,
   independently of the tier 1 cache. The versioned object has `version: 1` and a `rows` array.
   Each row requires nonempty, single-line strings: `id`, `kind` (`process-fix`, `partial-node`
   or `wiring`), `ticket` (`OMN-<number>`), `repo` (repository name), `goal` (one-line goal),
   `acceptance_check`, `added_by` (approving lane/actor), and `added_at` (UTC ISO timestamp).
   IDs and tickets must be unique. Optional `blocked_until` is a nonempty, single-line reason
   naming the prerequisite that must finish. Such rows remain declared but cannot dispatch;
   remove the blocker in a reviewed data change after proving the prerequisite. Optional
   `blocked_on` is a list of prerequisite tickets (`OMN-<number>`, unique, never the row's own
   ticket); Enumerate reads their Linear state in the same batch and the selection node skips
   the row `blocked-on:<tickets>` until every one is completed (an unread prerequisite is not
   Done). Optional `repo_confirmed_by` names the lane whose evidence confirmed the declared
   repository; the node then keeps it (`declared:confirmed`) over the ticket's PRs. Optional
   A repository the ticket declares in Linear (a `Repo:` line of its description naming a
   `config.fleetRepos` entry; two different ones declare nothing) replaces the row's `repo`
   (`linear-declared`), and a confirmed row repository still outranks it.
   A lane that stops under the brief's REPOSITORY rule writes `owning-repo=<repository>` in its
   TERMINAL (a "belongs to <repository>" sentence in its receipt's `result` counts too). Enumerate
   reads the `result` of each lab-fill receipt that ended in the last 48 hours; a blocked, partial
   or no-op lane that names a fleet repository other than the one it ran in is a pending reroute:
   the next tick dispatches the ticket there once (`reroute:<lane>`), the repository stays for
   later ticks, and every other hold (prerequisite, stay-out, owner, merged implementation,
   unchanged input after the rerouted lane) still applies. A name outside the fleet registry is
   `reroute-refused:unknown-repo:<name>` in the skipped list and the STATUS notes. A repository a
   stop already sent the ticket to is never sent to again.
   An approved row is dispatched only when its ticket is provable (OMN-20721): the ticket text
   carries none of `PLACEHOLDER_MARKERS` (`PLACEHOLDER`, `Not startable`, matched as written), every
   ticket Linear lists as blocking it is completed, and the row's acceptance check names a command
   (`uv`, `curl`, ...) found on `PATH` or a path found in the row's clone. A row that fails is
   skipped `precheck:<reason>` (`placeholder`, `dependency-open`, `acceptance-unrunnable`) and
   named once per (row, reason) in the STATUS notes; the reported keys ride in
   `input-baselines.json`. The precheck sits after every other hold and clears none. Ticket text
   is the description only: a plan the ticket cites is not read. A row whose last lane ended
   blocked, partial or no-op is held until its ticket's `updatedAt` is later than the baseline's
   or its content hash (`row_hash`) differs; the six-hour cooldown frees plain tickets, never an
   approved row.
   `checked_at` (UTC, `YYYY-MM-DDTHH:MM:SSZ`) is when the row was last validated against merged
   history; the freshness rule below compares it with merge times. Optional `host`
   is a nonempty string matching `[A-Za-z0-9_.-]+`, naming the lab host the work must run on
   (a host-local unit install, disk or swap change). Without it, the runner places the lane.
   Invalid rows are counted as `malformed`; an invalid document/version is unreadable.

   The listing hands approved rows over as references (`kind`, `ticket`, `id`, `repo`,
   `repo_source`, optional `host`), at most the run's budget of them. On 2026-10-07 the full rows
   came to about 430 KB and the enumerate agent returned the first 40 without goal or acceptance check,
   so every one was refused `malformed-approved`. Dispatch resolves each row by id from the
   approved-work list into the brief's `GOAL` and `ACCEPTANCE CHECK` lines. It skips the lane
   `approved-row-unresolved` when the row is gone, changed kind or ticket, or is blocked.

   The list is ordered data: M4 tickets and confirmed prerequisites first, then highest source
   rank (lowest number), with measured process value before partial/wiring work at equal rank.
   Unranked plan close-out rows follow the ranked inventories in source order; conversion rows
   follow those. Deduplicate by ticket, retain its most specific acceptance and highest rank.
   Enumeration and selection preserve the file order across all approved kinds; tier 1 still
   precedes every tier 2 row. Inventory updates use ordinary PRs, never a generated runtime script.

   The 2026-10-07 load uses docs_repo #1084's ranked process-fix export, #1085
   sections 3/11, #1086's reviewed close-out rows, and #1089's conversion export. Blocked, held,
   excluded and UNBOUND plan appendix rows are not approval. Grouped carriers use the owning
   ticket's acceptance, without authorizing adjacent residuals or conditional rollouts. Rows
   without a resolvable owning repository remain outside this list. Done/canceled tickets and
   merged implementation PRs are removed at import; merged change-control companions do not
   prove implementation completion. Open implementation PR rows stay declared for ownership
   filtering. The lab-fill, remote-lane, landing-controller and check-policy-gate conversions
   retain explicit blockers for other work in flight.
   [The import audit](approved-work-import-2026-10-07.json) records source heads, live-read
   timestamps, exclusions, retained open PRs and prerequisite reasons. It is provenance data;
   only the controller-owned approved-work file supplies candidates.

   Approved completion facts are never cached. A bounded batch Linear read checks ticket state
   and assignment; completed or canceled tickets are skipped. A fresh watcher inventory with
   the same eight-minute/90-minute freshness requirements checks implementation PRs by
   ticket in their title across repositories. A merged PR skips its approved row; `evidence(...)`
   companions in onex_change_control do not prove implementation completion. Unreadable tickets or watcher
   state cannot dispatch approved work. Cache-only reads report `not-read:cache-only` for
   nonempty approved lists. At most 500 declared rows and 20 total Linear requests are admitted.
   Open implementation PRs in that snapshot also mark approved rows owned, even after their
   lane's CLAIM closes. Live ownership, fences and pending landing handoffs apply too. The existing
   sprint/project and milestone restrictions apply to tier 1; the approved list declares tier 2's
   scope. The tier 1 candidate cap is unchanged; approved rows are appended after that cap.

   A row's done state comes from facts, not from the import (OMN-17427). The pure
   `mark_approved_work_done` operation of the selection node (`node_lab_fill_selection_compute`,
   `HandlerApprovedWorkFreshness`) folds facts the caller read into the rows and does no I/O: a row
   whose Linear state type is `completed`, `canceled` or `duplicate` becomes `done: true` with
   `done_basis: linear-state`; a row whose ticket's acceptance checks the reader found passing on the
   repository's default branch becomes `done: true` with `done_basis: acceptance-on-main`, and its
   `done_evidence` names each merged pull request and the first 12 characters of its merge commit
   (`repo#n@commit`); a row that is partly done keeps `done: false` and a one-line `remaining` note
   naming what is left, which the dispatch brief appends as "Already shipped, remains: ...". Pass
   with no evidence, a partial with no remaining line or a malformed pull request or commit is
   refused. Acceptance status `merged` (an implementation merge naming the ticket is on a default
   branch and nothing a lab lane could build remains; closeout and live readbacks are the closer's)
   marks the row done with `done_basis: merged-history`, and `duplicate_of` marks it done with
   `done_basis: duplicate`. Facts may also correct a row that stays open: `repo` with
   `repo_confirmed_by`, `blocked_on` (merged with the row's own) and `blocked_until`. A partial or
   corrected row gets `checked_at` set to the request's time. `remove_done` drops every row that ends
   done from the returned rows (its verdict says `removed`). The loader refuses (counts as malformed) a `done` that is not a boolean, a done row with
   no single-line `done_evidence`, a `remaining` that is empty or multi-line, a malformed
   `checked_at` and an unknown `done_basis`; a declared done row is skipped as `done:declared` after the live `done:pr-merged`
   and `done:ticket` reads. Re-run the check when the list is loaded and whenever a lane finds a row
   already shipped: read Linear state for every row, search merged pull requests by ticket, read the
   acceptance checks of each candidate against the default branch, pass the facts to the operation
   and commit the returned rows. [The freshness audit](approved-work-freshness-2026-10-07.json)
   records the first run: its reads, counts and per-row verdicts. [The 2026-10-08 prune](approved-work-prune-2026-10-08.json)
   classifies every approved row lab-fill dispatched in the 48 hours before it from the lanes'
   results (done, superseded, prerequisite-missing, wrong-repo, unreadable, owned, actionable) and
   records what changed in each row.

   Merged history is read on every live enumeration (OMN-17427). Between 19:34Z and 19:44Z on
   2026-10-08, 19 approved rows were dispatched that no lane had touched in 48 hours; 6 had merged
   weeks earlier. The watcher holds only recent PRs, and the import never re-read merge history, so
   lab-fill kept picking them. Enumerate now reads `git log` of each registry clone's default branch
   (`origin/dev`, else `origin/main`; the clone layout of `onex-triage-started-node`, under `registry_root` or
   the `mergedHistoryRoot` parameter, over `mergedHistoryDays`, default 120). It keeps, per ticket, the
   newest commit whose subject names it, ignoring `evidence(...)` companions. A row whose ticket has
   such a merge newer than its `checked_at`, or any such merge when it has no `checked_at`, is skipped
   `stale:merged-after-check:<repo>@<sha12>` until the producer re-validates it. A row whose own
   repository's clone cannot be read is skipped `unreadable:merged-history:<repo>`. When no clone can
   be read, the approved source is unreadable. [The 2026-10-08 reconcile](approved-work-reconcile-2026-10-08.json)
   classified all 362 rows against Linear and merged history. It removed done-merged and duplicate
   rows through `mark_approved_work_done`, corrected repositories, added blockers and stamped
   `checked_at` on every kept row with a merge. It also lists the done-merged tickets still open in
   Linear, for the closer.

   Every STATUS carries `tier1-candidates`, `tier2-candidates`, `tier1-dispatched` and
   `tier2-dispatched`, including zero. Candidate counts describe the chosen enumerator/cache
   output after filtering; source diagnostics retain prefilter counts. Dispatch counts use
   the same placement outcomes as aggregate `dispatched`, excluding `not-started` and
   `skipped:*`; selected rows cut at the deadline or rejected by ownership are not dispatched.

   The skip rules are decided by `node_lab_fill_selection_compute` (OMN-20662), a pure compute
   node that Enumerate calls in process with the ledger window (48 hours, archives included), the
   PR watcher's state and the landing controller's state. A candidate is skipped when:
   - a PR it would work on is handed to the landing lane (a handoff MSG, a `handed-off` TERMINAL or
     STATUS) and not merged or closed, or the controller holds it (a live lease, or a record it has
     not parked), unless the controller escalated it back (a parked record, a degraded entry in its
     last tick, or a MSG from a `landing` lane to another lane after the handoff). This includes
     `pr-red` and `pr-stalled` repair: lab-fill no longer reworks or rebases a PR the controller owns
     (`owned:handed-off:<pr>`);
   - any lane holds a live CLAIM on its ticket or PR, including a lab-fill lane with no TERMINAL
     (`owned`);
   - a PR that names its ticket merged, other than a change-control evidence companion
     (`implementation-merged:<prs>`, ticket, defect and approved kinds; ownership is checked first).
     Whether the ticket is done is the closer's question: `dod-closeout-sweep` already reads every
     started ticket a merge of the last 7 days names. Replayed over the lab-fill lanes of
     2026-10-07 14:25Z to 17:25Z, this skips 13 of 54, OMN-18931 three times after omnimarket#3469
     merged;
   - its last lab-fill lane ended blocked, partial or no-op (`unchanged-input:<outcome>`), or it had
     two lab-fill attempts in 24 hours (`dispatch-limit:unchanged-input`), and neither the ticket
     nor its PRs moved since that lane ended: the ticket's `updatedAt` is not later than it read
     then, and its open PR heads (change-control companions aside) are the same. The first read
     after the lane's TERMINAL is stored as the baseline in
     `$registry_root/.claude_scratch/lab-fill/input-baselines.json`; a read older than the TERMINAL
     records nothing and still skips. An unread watcher never counts as a changed head. The
     repository's default branch moving is not a change to the ticket: it moved nearly every tick,
     and a ticket's defect and approved-row candidates shared one baseline with different shas, so
     blocked tickets came back every 20 minutes (OMN-19396 at 1510, 1610 and 1650 with no ticket
     update). An `unchanged-input` hold ends `cooldown_hours` (6) after the lane's TERMINAL
     (`cooldown-elapsed:<outcome>:<lane>` in the eligible decision's detail); a dispatch limit
     does not;
   - it is a defect that names a repository outside the lab-fill repositories (`prRepos` and the
     fence authority's list) by its repo field, a repository label or a bracketed slug in its title,
     and is not in the declared project (`out-of-repository-scope`). A defect with no repository
     identity stays in scope.

   - (OMN-20864) its ticket is one a lab lane cannot read (`ticket-unreadable`): the launching
     host's Linear read returned an empty description (`ticket-unreadable:launching-host-read-empty`;
     a lab lane has no better read), or its latest lab-fill lane stopped because it could not read
     the ticket (`ticket-unreadable:lane-stopped:<outcome>`). A PR repair needs no ticket text and is
     never held this way;
   - (OMN-20864) its repository cannot be resolved for the lane (`repo-unresolved`): no evidence
     names one (`repo-unresolved:no-evidence`), the one named is not in `config.fleetRepos`
     (`repo-unresolved:not-in-fleet:<repo>`), or its latest lane stopped in the wrong repository and
     named no fleet repository it had not already been sent to (`repo-unresolved:lane-stopped:<outcome>`);
   - (OMN-20864) the cooldown does not release a stop whose cause is the ticket's own. Each stopped
     lane's receipt `result` is classified by `stop_cause` (`ticket-unreadable`, `wrong-repository`,
     `already-done`, `red-not-on-branch`, `prerequisite`, `lab-environment`, else `unclassified`) and
     the decision's detail carries `cause=<cause>`. Only a `partial` lane, a lane whose result is not
     known, or a cause outside the ticket (`prerequisite`, `lab-environment`) waits out
     `cooldown_hours`; every other stop holds until the ticket, its PR heads or its row change.
     Replayed over the 478 lab-fill dispatches of 2026-10-09T14:50Z to 2026-10-12T14:50Z, these three
     rules exclude 105 of the 237 dispatches the previous rules admit. Of those 105 lanes, 2 handed off a
     PR, 4 ended partial and 99 produced nothing (67 blocked, 25 never placed, 5 done with nothing
     built, 2 failed or unknown).

   Controller state is read from `$HOME/.local/state/omni/landing` (`state.json`, the last line of
   `ticks.jsonl`); a missing file reads as no controller facts.

   The same node names the repository an eligible ticket's lane works in, from where the work
   lives and never from a default (`repo` and `repo_source` on the candidate; the runner gets
   `--repo`, and the brief carries a `REPOSITORY:` line naming the evidence). A PR candidate works
   on its PR. Otherwise the PRs that name the ticket decide, newest first with knowledge-base PRs
   after code: the watcher's open and merged PRs and the ticket's GitHub attachments in Linear
   (`attachments(last:20)`, read by the same tree, defect and approved-row queries). Companions and
   `registry_root` PRs never count. A confirmed declared repository (`repo_confirmed_by`) is kept
   first (`declared:confirmed`). An approved row's declared repository is kept when one of those
   PRs is in it (`declared+ticket-pr`); otherwise the first PR's repository wins
   (`ticket-pr:<pr>`). Without PRs, the known repositories its title, goal and acceptance check name
   as file paths, by label or by bracketed slug decide when there is exactly one (`named-files`),
   and the declared repository is the last resort (`declared`). On 2026-10-07 OMN-19381 was
   declared in ops_tooling_pkg while its only PR is omniclaude#2452, and its lab-fill lanes
   ended blocked at 1510, 1550 and 1650.

   A `pr-red` lane, and a `pr-stalled` lane on a PR the controller parked or escalated, is a
   pr-land lane that lands the PR through `/omni:pr-land` (RULING 2026-10-10T04:08:23Z,
   OMN-20780). The candidate and dispatch carry `escalated: true` when the controller parked
   or escalated the PR.

4. **Select** (script, `selectWork`). A candidate is skipped with a reason in these cases:
   - it is owned, by a claim holder or a PR claim (`owned:<lane>`);
   - its ticket is fenced (`fenced`). The parent ticket is an umbrella and fences nothing;
   - it matches an excluded area (`excluded-area:<area>`);
   - it is assigned to another person (`assigned-other`) or carries a PR hold (`held`);
   - with project scope, a ticket is outside the project or a PR is outside `prRepos` (`out-of-scope`);
     with legacy subtree scope, it is outside the parent or carries another non-blank milestone;
   - it is a defect without a pillar label or term (`not-a-pillar-defect`);
   - it is the parent ticket itself (`umbrella`);
   - it repeats a PR or ticket already kept (`duplicate`).

   Order: tier 1 retains `pr-red`, `pr-stalled`, `defect`, `ticket` and `plan-stalled` / `ruling-pending` (the last
   two rank with `ticket`), then ticket number. A `pr-red` or `pr-stalled` PR the landing controller parked or escalated back
   (`landing`) ranks before every other ungated item (RULING 2026-10-10T04:08:23Z, OMN-20864): an idle slot lands PRs first.
   Tier 2 follows with approved rows by ticket number, filling every remaining free lane slot.
   Deduplication by ticket/PR spans both tiers. Approved lane briefs carry the declared goal and
   acceptance check and require integration before building, within close-out scope. Selection counts
   a slot on the host with the most lanes left that holds its engine; the runner places each lane on the host with
   headroom when it launches. Only work that names its host is pinned, and its slot is counted there.
   An unpinned lane follows the runner's own order: the lab hosts first, the launching host only when
   no lab host has a slot and it passes its own bar. On 2026-10-07/08, 32 of 347 lanes ended no-host,
   every one pinned, and in 31 of them the runner's read showed another qualifying host with a slot.
   A self-contained code candidate goes to Codex when a Codex host has a lane left, and to sonnet
   otherwise. Other candidates prefer sonnet and
   fall back to Codex when no Claude host has a lane left. If neither engine has an available host,
   the candidate is deferred (`no-host-for-engine`); a pin without headroom is deferred
   `pinned-host-no-headroom`, naming its host. A pin the runner refuses with no-host is deferred
   `pinned-host-refused`, naming its host and lane. Past the budget, candidates are deferred
   (`over-cap`). **No lane is ever assigned to a host without lanes.**
5. **Dispatch** (sonnet, twice; OMN-20690). Ownership is decided in code, then the lanes that cleared are
   dispatched one at a time, each inside its own slice of the window.
   1. **Ownership** (`ownershipRead`, one command, one agent that only runs it). Before the dispatch agent
      starts, one command reads the entire eligible candidate pool before the lane cap. An exact open
      CLAIM owns work only while its lane wrote a row in the last 45 minutes, including rows on
      other subjects and MSG rows with `from=`. A TERMINAL ends the lane. PRs match the structured
      PR cells, including comma-separated lists; ticket-only work matches ticket cells. A per-PR
      claim does not own a shared cause. An unreleased controller cause lease owns its members;
      a revoked lease still owns them until its entry or worker receipt confirms release.
      The ticket index's 12-hour window and per-PR registry are not ownership authorities here.
      Ownership produces `owned:<owner>` (all live owners are named) or a free verdict. Unread ledger
      or controller state produces `owned-unreadable`. An approved row with a merged implementation
      reads `done`; an unread watcher reads `completion-unreadable`. A missing verdict reads
      `ownership-unread`. Selection runs again over the cleared pool, so a live owner appearing on
      the first candidate releases the slot to the next unowned candidate in the same fire.
      The same command reads each unowned lane's ticket with `lane_brief.read_ticket` and
      `lane_brief.ticket_flags`, imported from the omni plugin's `lane-brief/scripts` (OMN-20864; the
      predicate `lane_brief.py check` applies, not a copy). A ticket Done or Canceled in Linear, or with a
      merged implementation, reads `ticket-state:<done|canceled|merged>`, or `ticket-state:not-found`, and is
      dropped before a brief is assembled; a lab-fill brief never carries a `ticket-state-ack`. One Linear read
      per ticket on daemon threads bounded by `ticketReadBudgetS`; a ticket that could not be read reads
      `ticket-state=unreadable:<cause>` in the detail and is tried, since `check` stays the backstop.
   2. **Dispatch**. The agent is handed the lanes that cleared and runs no ownership read. It defines
      `lane_slice` (`laneSliceShell`): the seconds left to Dispatch's absolute deadline divided by the lanes
      still to do, so a lane may take its share of what is left and never the whole window; a lane that
      finishes early leaves its time to the lanes behind it. Lanes go strictly one at a time, in priority
      order, and a lane is finished (checks, brief, dispatch) before anything is read for the next. A slice
      under 15 seconds is the end of the window: `detached=false`, `skipped=deadline` and the clock in
      `detail`. A lane whose commands exceed its slice is `skipped=lane-timeout:<seconds>s`. Every lane
      returns `elapsed_s`. For each lane that is started, in order:
      1. Re-check Linear assignment, fences, PR holds and (approved rows) ticket completion live:
         another assignee is `assigned-other`; an unreadable assignment is `ticket-unreadable` and cannot
         dispatch.
      2. Write the brief under `$registry_root/.claude_scratch/lab-fill/<run key>/<lane>.md`: the
         script-rendered task (`laneTask`, with the lane's ROUTE line and the `AUTHORITY:` line rendered from `config.authority`), then the committed standing
         rules printed verbatim by the omni plugin's `scripts/lane_rules_block.py`, then lane-brief's
         own section 3a Constraints, the output of `lane_brief.py constraints` (OMN-18397, OMN-20864).
         The standing rules carry the premise, report-to-file and literal mint-delegation rules.
         Assembly checks each standing rules paragraph with lane-brief's required markers before the
         constraints are appended. An unreadable or incomplete rules block stops assembly: do not
         dispatch; return `detached=false`, `skipped=brief-rules-unreadable` and the reader or
         validation error in `detail`. The constraints carry 3a.1 to 3a.8 and, themselves, the 3a.9
         delegation and 3a.10 lab parts. Their arguments are rendered by the script
         (`constraintsArgs`, in each lane's `constraints_args`: parent lane, landing lane,
         `config.landingRuling`, model, an out-of-scope list and the repository) and the agent copies
         them. Assembly ends with `lane_brief.py check --lab` on the finished brief: a refusal exits 3,
         and the agent does not dispatch that lane: `detached=false`, `skipped=brief-check-refused` and
         the REFUSED lines in `detail`. Before OMN-20864 the assembly printed only 3a.9 and 3a.10, so
         `check` refused every lab-fill brief (no 3a section, no 3a.1 to 3a.8) and never ran at dispatch.
      3. Run the script-rendered command (`dispatchCommand`): `onex_remote_lane.py run --detach
         --parent <parent lane> --ticket <ticket> --model sonnet|codex --effort high`, plus
         `--host <host>` only for a pinned lane, and
         `--repo`, `--ref` and `--pr` when they are known.
   3. **Refill** (OMN-20864). A lane the dispatch step drops for its own candidate's reason
      (`brief-check-refused`, `approved-row-unresolved`, `assigned-other`, `ticket-unreadable`, `done`,
      `completion-unreadable`, `held`, `fenced`) costs the candidate, not the slot. The script reads the
      returned lanes, frees the slots those lanes held, and hands the next untried candidates (the same
      selection, over the slots left and never past `maxLanes`) to another dispatch agent whose prompt opens
      with `REFILL ROUND <n>`. This repeats while the last round lost a candidate to a refusal, up to eight
      rounds, until the host's slots are filled or the candidates run out. A window cut (`deadline`,
      `lane-timeout`) or `brief-rules-unreadable` is not the candidate's and frees nothing: the refill stops.
      A candidate naming a ticket or PR a handed lane already named is not tried again. Each refusal is
      recorded with its reason: in `placements` (`skipped:<reason>` with the REFUSED lines), in the result's
      `refusals` and `refill_rounds`, and in `skipped` (so `skip-reasons` names it on a tick that places nothing).

   **How a lane closes (OMN-20864).** Every brief carries a `CLOSE:` line (`CLOSE_RULE`). The merge pulse judges a
   lane's delegation unless its TERMINAL carries the typed `delegation=na:<reason>` cell, and lab-fill lanes that
   only read wrote `delegated=0 delegation_reason=...`, which counts as undelegated: all five lab-fill lanes
   that queue-status named at 2026-10-13T19:33Z closed that way. The line tells a lane that only reads to write
   `delegation=na:<reason>` and no `delegated=` cell, and ties `outcome=done` to an `evidence=` cell naming the
   lane's own report of the commands it ran with their exit codes and output, plus a `pr=` cell for every PR
   it pushed; a result copied from an earlier lane's report is not evidence, and a lane that ran no command or
   could not read what its brief names closes `outcome=blocked`. Ticket briefs add a `TICKET READ:` line: a lab
   lane has no Linear tool, so it reads the ticket with the host's `LINEAR_API_KEY`, and a ticket it cannot read
   stops it as `ticket-unreadable` (lane `lab-fill-omn19361-10131910` closed `done` with "Linear body unread"; the
   hook-event trace counted two completed tool calls in the whole agent). The runner's own close check
   (`node_remote_lane_close_compute`, outcome `rejected-no-delegation`) judges the final message's
   `DELEGATION` line and applies to lab-fill lanes already; it does not re-judge a TERMINAL the lane wrote
   itself, which is the follow-up for the runner's repository.

   The runner writes each lane's CLAIM. Verify records the lanes cut at the window as `skipped:deadline`; they
   do not count as dispatched.

   **A window that placed nothing fails the run.** When the dispatch agent was handed lanes and every one of
   them ended `skipped:deadline` or `skipped:lane-timeout` (nothing placed, nothing pending), the script
   writes the Report phase's STATUS row as usual and then throws `DISPATCH_WINDOW_CONSUMED`
   (`dispatchFailure`). The fire exits non-zero, and the message names the lane with the largest
   `elapsed_s` (without timings, the first lane started), so the driver's failure notice says which lane used
   the window. Lanes skipped for ownership never count: they were not the agent's work. A dry run
   (`apply: false`) never dispatches, so it never fails this way.
6. **Verify** (sonnet, then script `verifyPlacement`). The agent runs one command (`verifyRead`) and
   returns what it prints. The command re-reads every 15 seconds while a receipt is missing or names
   no host. It stops after the smaller of 150 seconds and the interval from Dispatch's deadline to
   Verify's deadline (60 s by default), or at Verify's absolute deadline, whichever comes first. A
   late start reads once. Without deadlines the limit stays 150 s. A Codex lane is re-read until its
   receipt is final or 45 seconds have passed, because the runner's Codex sandbox probe runs after the
   receipt already names the host with status `running`. A lane whose receipt still says `preparing`
   or `placing` is re-read for up to 90 seconds (`PREPARING_WAIT_S`, never past the window) before it
   is reported, and a lane still preparing then is `pending`, not `placed`. The command also returns
   each receipt's own `reason`, `error`, `failure` and `result` whole.
   Outcomes: `placed` (the pin for a pinned lane, any receipt host for an unpinned one),
   `placed-elsewhere` (pinned only), `deferred:pinned-host-refused` (a pin refused with no-host),
   `refused` (unpinned no-host, usage, route mismatch),
   `engine-failed:<status>` (a Codex lane that ended in the runner's Codex setup, below), `pending`,
   `not-started`, `skipped:deadline`, `skipped:lane-timeout:<seconds>s`, `skipped:owned:<lane>`,
   `skipped:owned-unreadable`, `skipped:ownership-unread`, `skipped:done` or `skipped:completion-unreadable`. An `engine-failed` lane is not a
   placement and holds no slot. A deferred lane holds no slot either.
7. **Fallback** (sonnet, only when a lane needs it; script `planFallbacks`). See Engine fallback below.
8. **Report** (sonnet). Writes the script-composed idle FRICTION when required, reads it back,
   atomically writes the per-fire result, then appends and reads back STATUS by its deadline.
   A refused FRICTION write records `friction_recorded=false` and refuses STATUS, so the
   idempotency precheck cannot hide an undelivered alarm.

Lane names are `lab-fill-<ticket digits>-<MMDDhhmm>`.

## The per-lane table (OMN-19854)

A report that says "3 of 6 placed" hides why the other three were not (usage report 2026-10-16,
finding 2: reports were built from truncated output, and lanes sat `placing` or ended no-host with the
reason only in the receipt). Every run now renders one row per lane, the dispatched lanes first, then
each fallback and capacity retry, read from the lane's own receipt: `lane | ticket | model | host |
state | class | reason`. The workflow result carries it as `lane_rows` (data) and `lane_table`
(markdown, ending in a line that says whether the STATUS row was read back from the ledger, yes or NO
with the refusal), and the idle result file carries the table as `lane_table`.

| State | Receipt |
| -- | -- |
| `placed` | a host named and a status that is not `preparing` or `placing` (a lane that ran and failed is still placed) |
| `preparing` | `preparing` or `placing` after Verify's wait |
| `no-host` | status `no-host` or `node-unavailable` |
| `host-limited` | status `host-limited` or `host-auth-expired` |
| `refused` | a setup refusal (`mint-refused`, `usage`, `ledger-snapshot-failed`, ...) or a final receipt with no host |
| `never-started` | the dispatch did not detach the lane (its own detail is the reason), or no receipt was read |

The reason is the receipt's text, first of `reason`, `error`, `failure.reason`, `result`, in double
quotes; a pipe is escaped and a newline becomes ` / `, nothing else changes. A refusal whose receipt
names none says so (`(the receipt names no reason; status=...)`), never a blank. Each refusal has a class:
`capacity` (no host had a free slot), `policy` (a rule refused it: a priority holdback, a mint, timeout
or brief refusal), `limit` (a usage limit or an expired login) or `other`.

A `capacity` refusal of an unpinned lane is retried once, as `<lane>-retry`, pinned to another host
that admits its engine and still has a free lane in the capacity read (`planFallbacks`, run by the
Fallback phase with the engine fallback). A pinned lane (its host is part of the work), a retry lane
and any refusal that is not capacity are never retried; with no other admitting host the retry row
reads `never-started` with `skipped:no-other-admitting-host`.

`node_lab_fill_receipt_table_compute` (`lane-k-fill-receipt-table`) is the same decision as a pure
node for readers that are not this script: JSON lanes and receipts in, rows, the table and the planned
retries out. The script holds a port of it because a Workflow script cannot import Python;
`tests/test_lab_fill_lane_table.py` runs both on the same receipts and fails on any difference.

## Engine fallback (OMN-17427)

Codex is not always usable on a host. The runner ends a Codex lane in its own setup, before Codex
starts, with status `codex-sandbox-unavailable`, `codex-missing` or `codex-not-logged-in` (its receipt
carries `failure.retryable: true`, and the lane's exit is 70). No work was done, so the controller sends
the same brief to Claude once.

The runner contract the controller relies on (nothing in the runner changed): `onex_remote_lane.py run
--detach --model <engine>` with `--host <host>` only for a pinned lane writes a receipt with
`lane`, `status`, `host`, `final`, `exit_code` and `engine`; `--model` must equal the brief's ROUTE line (`REMOTE-LANE-ROUTE-MISMATCH`
otherwise); a Claude account that hit its usage limit is marked by `.limited-<host>` in the placement
directory, read by `landing_placement.limited_hosts`. The Codex probe and its sandbox checks are the
runner's and are not read or reimplemented here.

Two cases, both named in the STATUS row:

- **Before dispatch.** A self-contained code candidate prefers Codex. When no Codex host (a host whose
  Codex probe passes) has a lane left, `selectWork` counts a slot on a Claude host and marks the item
  `fallback: codex -> sonnet, no-codex-host`. Pinned work checks only its named host for either engine.
- **After dispatch.** Verify reads a Codex lane's receipt as `engine-failed:<status>`. `planFallbacks`
  gives that lane **one** fallback: a new lane named `<lane>-fb`, `--model sonnet`, the sonnet ROUTE
  line, the original task plus a `FALLBACK:` paragraph that says why. Hosts offered are those with a
  Claude login and a lane left (a limited, refused or full host has none; the dead lane's slot comes
  back). A pinned fallback offers only its pin; without a Claude lane there it is skipped
  `pinned-host-no-claude`. Unpinned fallbacks offer ranked hosts and leave placement to the runner.
  The fallback agent then reads the `.limited-<host>` markers live (`fallbackHostPick`), takes
  the first offered host that is not limited, re-checks ownership (the runner closed the dead lane's
  CLAIM; a peer's live claim skips the fallback), writes the brief with the same standing-rules and
  delegation blocks, runs the runner command once and reads the receipt once, recording its host
  when named. No host: the fallback is
  skipped with `no-claude-host`.

There is one fallback per brief per run: a fallback lane, a sonnet lane and a lane that did run Codex never
produce another, and the agent never retries. The next 20-minute fire starts from a clean read, so a
brief whose ticket is still unowned can be fallen back again in that run, once.

## Lane priority classes (OMN-20864)

Operator RULING 2026-10-15T08:14:02Z: "<removed>".
Lab lanes come from three dispatchers: the landing controller (one fix worker per PR and cause), this controller, and the
orchestrator's own remote-lane dispatches. Placement was first come, first served, so whichever dispatcher fired first
took the last free slot. Every lane now carries one declared priority class:

| Class | What it covers |
| -- | -- |
| `mvp-landing` | landing a PR in an MVP repository (`priority.mvpRepos`: omnibase_infra, omnibase_core, omnimarket, omniclaude, omnidash) or a PR of the delegation pillar (the `defects` labels and terms) |
| `process-fix` | an approved `process-fix` row, the mechanism ticket of a process ruling (`ruling-pending`), or landing a PR in a process repository (`priority.processRepos`: ops_tooling_pkg, plugin-tooling-pkg), the landing, dispatch, capture and automation machinery |
| `other` | everything else: sprint tickets, delegation defects that are not yet a PR, wiring and partial-node rows, PRs in other repositories |

How a free slot is chosen:

1. **This controller** (`selectWork`, `priorityClass`) ranks eligible candidates by class after the open-count gate and
   before every older key (landing, kind, ticket), so a short run budget goes to mvp-landing first, then process-fix.
   Each dispatch item carries `priorityClass`, and the dispatch command passes it to the runner as
   `ONEX_LANE_PRIORITY_CLASS`. An older runner ignores the variable.
2. **The remote-lane runner** reads `--priority-class` (default: `ONEX_LANE_PRIORITY_CLASS`, else `other`) and writes it on the
   lane's receipt and as a `priority=` cell on its CLAIM.
3. **Placement** (`landing_placement`) admits by class when the pool is short. The last free lane slot is kept for
   mvp-landing, and the last two for mvp-landing and process-fix. A lower class refused that way reads
   `PRIORITY-HOLDBACK`; it waits for the next tick and is never placed by preempting anything.
4. **The landing controller** gives each fix worker the class of its PR's repository: an M4-repository PR worker is
   mvp-landing, an ops_tooling_pkg or plugin-tooling-pkg PR worker is process-fix.

A lower class never preempts a running lane: the classes only order free slots, and no dispatcher stops a running lane
to free one.

## The open-count gate (OMN-20714)

RULING 2026-10-08T03:53:20Z (the orchestrator lane, the operator's "<removed>"):
lab-fill stops starting PR-producing work while the open PR count is rising. RULING 2026-10-12T05:25:08Z ("The lab
should never be idle. If there is work to be done, you should not be waiting on a process.", OMN-20780) amends it:
after two rising reads, landing work and delegation experiments still go first, and non-landing work is ranked after
them and dispatched only into slots they leave free.

Enumerate reads the count the way queue-status does, from the same two files and with the same rules.
The current count is the number of open pull requests in the PR-watcher state (`ONEX_PR_WATCHER_STATE`, else
`$registry_root/.claude_scratch/pr-watcher/state.json`), trusted only on `pr_state_local`'s terms: schema 1, the
operator and repository fields present, the last complete tick at most 8 minutes old, the last full resync at most 90 minutes old,
at least one open PR, and every open PR with a head and a default branch. The earlier reads are the `history` points of
queue-status's trend file (`$XDG_STATE_HOME`, else `~/.local/state`, then `omni/queue-status/last.json`), which lab-fill reads
and never writes. The series is the contiguous recent history (points older than a day drop, and a point more than six hours
before its successor ends the history) followed by the current count, exactly queue-status's `trend_points`, and the trend is its
`strictly` test on the last three points:

| Trend | Last three counts | Gated |
| -- | -- | -- |
| `rising` | each step strictly up (`150>155>160`) | yes |
| `falling` | each step strictly down | no |
| `holding` | anything else: an equal step or a zig-zag | no |
| `insufficient` | fewer than three points, or the trend file missing or unreadable | no |
| `unread` | the watcher state not trusted (the reason is the detail, `watcher-stale:12m`) | no |

The decision is `HandlerOpenCountGate` in `node_lab_fill_selection_compute` (the `decide_open_count_gate` operation, pure, no
I/O); the heredoc in this script does the two reads and hands the verdict to `HandlerLabFillSelection` as
`open_count_gated`. When gated, selection ranks `pr-red` and `pr-stalled` (work on an existing PR that gets it landed) and
`defect` (the delegation defects: the config's `defects` labels and terms) before eligible `ticket`, `process-fix`, `partial-node`
and `wiring` work, which fills only the slots ungated work leaves free. Every other gate applies first, including
unchanged-input and its baselines. Undispatched gated work is one counted `open-count-gate:rising` deferral per kind
(`{"id": "open-count-gate:process-fix", "reason": "open-count-gate:rising", "n": 337}`), so deferrals do not list every approved row.

A count or trend that cannot be read never gates, and the STATUS row says so (below): the gate is a brake on a measured rise, and
a flat or unknown queue is not one.

## Stay-out rulings (OMN-17427)

RULING 2026-10-01T10:53:36Z (`lane=dashboard-stayout`) bars every agent lane from dashboard code, dashboard
carriers and the dashboard owner's PRs, unless that owner asks or the operator overrides. From 2026-10-07T18:40Z to
2026-10-08T15:59Z lab-fill launched five lanes on OMN-19916, a carrier of M4 criterion C32, and each ended
`outcome=blocked`. Each cost a lab slot and a Claude session. The ruling does not name OMN-19916, and selection
read no ruling, so nothing stopped the next launch.

**The defect: the ruling row carries no machine-readable scope.** Its scope is prose in one cell,
`Binding: no agent lane works on <what> (<scope>) unless ...`. No cell names a ticket, a pillar or a criterion,
and the parenthesis names the ticket OMN-19969, PR omnimarket#3172, the repository omnidash and the criteria
C31 and C32, not their carrier tickets. A ruling row is never edited, so selection reads what it does carry
and resolves it against the closest declared sources. This ruling form is the only one read: a RULING row without
the `Binding: no agent lane works on` clause is not a stay-out ruling, and the other rulings that say a thing
"stays out" of something are not read.

Enumerate hands `HandlerLabFillSelection` three inputs, and the handler skips a covered candidate first of all
gates, with reason `stay-out:<ruling stamp>` and the cover as the detail:

| Input | Read from | Covers |
| -- | -- | -- |
| `ruling_lines` | the RULING, RELEASE and OPERATOR-CONSENT rows of the whole ledger, live file and archives (the 48 hour window would lose a ruling after two days) | the tickets (`ticket:`), PRs (`pr:`, also the PRs that name the ticket) and repositories (`repo:`) the parenthesis names, and the pillar its head clause names |
| `criterion_carriers` | the board's `CRITERIA` table, `infra_repo/tools/beta_board/beta_board_data.py` (`ONEX_BETA_BOARD_DATA` overrides the path), read as a literal and never executed | the carrier tickets of each criterion the parenthesis names (`carrier-of:C32`) |
| `pillar_owners` | `pillar_owners.yaml` through `node_pillar_owner_effect` | a ticket assigned to the owner of a pillar the ruling names (`pillar:dashboard`) |

The source used for OMN-19916 is the board's carrier tickets for C32. The pillar-owner map gives only a pillar to its
owner's Linear user id, so it covers by assignee, which `assigned-other` already skips before selection's decision
is read, and it carries nothing for a ticket assigned to the operator or to nobody.

A ruling is lifted by a later RELEASE, RULING or OPERATOR-CONSENT row whose `re=`, `ruling=`, `releases=` or
`overrides=` cell is the ruling's stamp or its id (`<stamp>-<lane>`). `amends=` and `unrelated=` do not lift, and a row
that releases a hold the ruling caused (the landing controller's HOLD ids) does not lift the ruling. The owner asking is a
message, not a row that can be matched, so it lifts nothing until the operator or the orchestrator writes the override.

A criterion the ruling names that the board did not resolve (no clone of the board's repository on the launching host, or
a table that has no row for it) is not guessed at: its carriers are not skipped, and the STATUS row's notes say
`stay-out: no board carriers for C31,C32 (<why the board was unread>)`.

## The STATUS row

```text
<ts> | STATUS | lane=lab-fill | ticket=OMN-17427 | actor=launchd:lab-fill | model=sonnet | run=2026-10-03T1810Z | parent=<parent lane> | pillar=delegation | hosts=h903:0(runner-cap)/run2/cap-bound,h907:4/run1 | budget=4 | candidates=cache:12:age=35m | dispatched=2 | tier1-candidates=0 | tier2-candidates=12 | tier1-dispatched=0 | tier2-dispatched=2 | placed=2 | skipped=2 | deferred=0 | engines=lab-fill-omn9-10031810:codex,... | fallbacks=none | cap-bound=h903 | lanes=lab-fill-omn9-10031810@h907:placed,...
```

`candidates=` records the source and candidate count, plus cache age when present: `enumerate`,
`enumerate-cache`, `enumerate+cache`, `enumerate-partial`, `cache`, or `none`. A pure STATUS render
without a candidate result uses `candidates=not-read:0`. A dispatching row has 25 cells after its timestamp, and 26 when the Enumerate read decided the open-count gate. An empty fill adds `skip-reasons`, optional
`prefiltered`, `source-reasons`, and `tier-reasons`. The last groups read status, counts and
rejection/deferral reasons into `tier1-m4-sprint` and `tier2-approved`, including no-headroom,
stale/unreadable sources and empty approved lists. `source-reasons` lists every kind (`ticket`, `defect`, `pr-red`,
`pr-stalled`, `plan-stalled`, `ruling-pending`, `process-fix`, `partial-node`, `wiring`) with read status, seen/eligible counts and counted rejection/deferral reasons. No
headroom reports every source `not-read:no-headroom`. Unreadable enumeration never reports a
successful empty read: a kind that a truncated read (`enumerate-partial`) did not return reads
`unreadable:enumerate-partial` in `tier-reasons`, never `empty:`. Cache source diagnostics keep
their original read status and cache age.

`open-count=<trend>:<last three counts>[:gated][:trend-file=<missing|unreadable:…>]` follows `deferred=`: `open-count=rising:150>155>160:gated`,
`open-count=holding:161>161>161`, `open-count=unread:watcher-stale:12m`, `open-count=insufficient:161:trend-file=missing`. A
tick whose Enumerate output carried no gate decision (no candidates read) has no such cell.

`engines=` lists `<lane>:<engine>` for every lane (a launched fallback lane included), `none` when no lane
ran. `fallbacks=` lists each fallback taken, `none` otherwise: `<lane>:codex->sonnet@<host>:preflight:no-codex-host`
for one chosen before dispatch, `<dead lane>:codex->sonnet@<host>:<outcome>:<status>` for one after (outcome
as for any lane, or `skipped:no-claude-host`). `dispatched=` counts every runner launch, a fallback included;
`placed=` counts lanes running on their host, so an `engine-failed` lane is dispatched but not placed.
`lanes=` carries the fallback lanes after the original ones. The last two cells summarise the lane
table below: `states=<state>:<n>,...` and `refusals=<lane>:<class>,...` (each `none` when empty).

`hosts=` lists `<host>:<lanes>`, or `(reason)` when the host got none, then `/run<n>` for the lanes
already running there and `/cap-bound` where it applies. Every successful acting run writes one STATUS row,
including a run with no headroom (`budget=0`). An idle run also writes FRICTION as described below. That keeps a run that dispatched nothing visible.

## Schedule

`ai.omninode.lab-fill` is rendered by `launchd/morning-workflows/morning_trigger_install.sh` from
`INTERVAL_AGENTS` (`lab-fill:10,30,50:1:1020`) with `launchd/ai.omninode.interval-workflow.plist.tmpl`.
It fires every 20 minutes, at :10, :30 and :50 local time, which stays off the :15 and :45 fires. The
ceiling is 1020s. The watchdog treats it as multi-fire. Install or reload that one label from the
canonical clone on `main`:

```bash
registry_root="<registry root>" bash launchd/morning-workflows/morning_trigger_install.sh --only lab-fill
```

A merged change to this script or its config reaches the next fire only after that install. The
driver runs the package copy in `lib/` beside the installed driver, which the installer replaces whole,
not the clone.

The Python the script imports (`ops_tooling_pkg.nodes.node_lab_fill_selection_compute`) is not in that copy: Enumerate runs it with
`uv run --project "$registry_root/../ops_tooling_pkg"`, so it is the canonical clone's, kept current by `internal-clone-sync`. A change
that adds an import to the script (the open-count gate, OMN-20714, imports `HandlerOpenCountGate`) must be installed only after the
clone holds the merge commit, or Enumerate fails on the import until the clone catches up. The order is: the merge, the clone at that
commit (`git -C "$registry_root/../ops_tooling_pkg" merge-base --is-ancestor <merge sha> HEAD`), then the install above.


## Idle alarm and SessionStart observation (OMN-17427)

An acting run with measured free slots and no accepted dispatch writes a `class=lab-idle`
FRICTION row before STATUS. It names `idle-hosts=<host>:<free slots>`, `free-slots`, both
`tier1-m4-sprint` and `tier2-approved` reasons (read status, seen and eligible counts,
selection rejections), and dispatch-time refusals. The required friction cost is an
estimate: free slots multiplied by the next 20-minute fill interval, in lane-minutes. A newly appearing owner, deadline,
engine refusal or placement refusal cannot turn a zero fill into silence. A detached lane
with pending receipt counts as started; a runner refusal does not. Dry runs write neither
rows nor results and raise no alarm; a full lab raises no idle alarm.

### Work and demand fields; an unreadable enumeration fails the tick (OMN-20796)

Every STATUS row carries `dispatched=`, `placed=`, `free_slots=`, `eligible=` and
`enumerate=ok|partial|unreadable|not-read` as fields the ledger row reader returns. `enumerate=unreadable` is no usable
list (source `none`, `cache-stale` or `enumerate-partial`) or a live read whose every kind
reads unreadable; `partial` is a list served from or merged with a cache, or with a kind that did
not read; `not-read` is a tick with no headroom, which never tried. An unreadable enumeration writes a
`class=lab-enumerate-unreadable` FRICTION row in place of `class=lab-idle` (an unread queue is
not an empty one), then the STATUS row, then ends the run failed with `ENUMERATE_UNREADABLE`.
An enumerate read that printed no JSON and whose stderr tail names a `ModuleNotFoundError` or
`ImportError` is typed apart (OMN-20863): the script and the package it imports are different commits,
the shape of 2026-10-09 when an installed copy imported a module the clone had deleted. That tick
writes a `class=lab-import-drift` FRICTION row (`failure=IMPORT_DRIFT`, `module=<name>`), alerts
`LAB IMPORT DRIFT`, and ends failed with `IMPORT_DRIFT`, never as a zero-candidate tick. The driver's
preflight ([the recorded preflight description](https://example.invalid/private-repo)) refuses to start a fire whose script package differs
from the clone before any read runs.
The result file carries `enumerate`, `eligible`, `enumerate_failed`, `import_drift` and `source_unreadable` beside the fields above.
Its `idle_alarm` keeps the driver's rule (free slots and no dispatch), so the idle alert still names the cause.

A stalled-plan or unmechanized-ruling source that cannot be read fails the tick too (OMN-20786): the tool
exited with a code it does not use for a finding, printed no JSON or no list, timed out, or its Linear or PR
watcher inputs could not be read. Unlike a sprint kind that did not read, which leaves `enumerate=partial`
and the tick green, these two are never read as empty. The enumeration is still `partial` (the sprint read
succeeded), the other source still dispatches, and after the STATUS row the tick writes a
`class=lab-source-unreadable` FRICTION row (`failure=SOURCE_UNREADABLE`, `failing-source=<kinds>`,
`read-error=<the tool's own error>`), alerts `LAB SOURCE UNREADABLE`, adds a `sources-unreadable=<kinds>` cell
to the STATUS row and ends failed with `SOURCE_UNREADABLE`. An unreadable enumeration or an import drift takes
precedence and keeps its own class.

### A read that did not complete is a read failure, never an idle lab (OMN-20762)

The node (`node_lab_fill_selection_compute`, operation `decide_enumeration_read`) decides how completely the enumerate
read saw the queue and the read's JSON carries it as `enumeration_read` (`outcome=complete|partial|failed`,
`empty_is_evidence`, `failed_reads`). Only a `complete` read, served live with every kind read, makes an empty list evidence of an empty
queue. A read that printed no list has no verdict and reads `unreadable`; a list that carries none is not known complete and reads
`partial`. The STATUS row's `skip-reasons=no-candidates` is written only for a complete read that returned zero candidates; a failed
read writes `enumerate-failed:<source>`, a partial one `read-partial:<source>`, and a tick that never read `not-read`. A kind a
failed read did not return reads `unreadable:<source>` in the source and tier reasons, never `<source>:seen=0`. A read that timed
out or was served from a cache (`enumerate+cache`, `enumerate-cache`, `cache`), with free slots and no dispatch, writes a
`class=lab-enumerate-partial` FRICTION row (`failed-reads=`) and alerts `LAB ENUMERATE PARTIAL`; the tick does not end failed, since
the work the read did return was placed. A live list with one kind that did not read stays an idle row whose tier reasons name the
kind (`skip-reasons=read-partial:enumerate` on its STATUS row). `class=lab-idle` is never written for a read that failed.

Report writes `.onex_state/morning-workflows/results/<fire id>.json`, schema version 1,
with workflow/fire identity, `observed_at`, per-host load/running/free counts,
`free_slots`, accepted `dispatched`, `approved_work_depth`, `available_work`,
`idle_alarm`, `friction_recorded`, `friction_cells`, `alert_text` and `session_line`.
The approved depth is a row count, including rows rejected during eligibility checks;
unreadable depth is null, displayed as UNKNOWN. Probe reads the depth even with no
headroom; enumeration still supplies eligibility and tier diagnostics.

The launchd driver validates this fire's result. It atomically publishes
`.onex_state/morning-workflows/lab-fill-latest.json` and invokes the existing
`alert_channel_send("lab_fill_idle", alert_text)` bot path for idle fills. The alerter
named by top-20 item 12 (`omnibase_infra/scripts/ci/nonrequired_check_failure_rate.py`,
the plan's B1 alerter) uses the same SLACK_BOT_TOKEN and SLACK_CHANNEL_ID destination;
the watchdog already consumes the shared `alert-channel.sh` sender. No operator account
post, new destination or sender is added. `ONEX_ALERT_CHANNEL_LIB` overrides that existing
library path. Delivery failure, missing library or missing credentials leaves a degraded
receipt (exit 70), `idle_alert_exit`, and the normal failure notice. Missing/invalid results
or an unrecorded FRICTION leave exit 65; an idle result still attempts delivery when
FRICTION failed. Raising and successfully delivering an idle alarm itself exits zero.

The omniclaude `[session-goal]` hook reads the verified latest observation without network
or writes. It prints one line with load, running lanes and free slots per host, totals and
approved-work depth. It adds IDLE when free slots and eligible work coexist. Observations
older than two fill intervals (40 minutes), or future observations, are marked STALE and
cannot claim IDLE; missing/invalid observations print UNKNOWN. This lab line also appears
when GOAL.md is missing. Existing lite/quiet/tick intent gates still apply.
