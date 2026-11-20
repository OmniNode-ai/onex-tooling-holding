---
name: queue-status
description: One read-only PR-queue health check for the orchestrator's recurring tick. Prints merges in the last and previous two hours by repo from fresh canonical-clone history, the open PR count from the PR watcher (or the drain map when the watcher is stale) and its trend since the last run, the open queue by merge-drain blocker class, drain liveness and succession, whether open change-control companions outnumber their per-repository batch windows and whether any repository switched batching off, per registry repository whether it is off onex_change_control (references counted by kind in the clone at its default branch, plus the required contexts that name an OCC job; `off` only when every count is zero), the operator process rulings of the last 14 days that have no mechanism built and wired (a ticket alone is pending work), the delegation-share line (how many lanes closed in the last 12 hours delegated work to Codex, the lab, GLM or Jev, and which delegated nothing), the landing measurement line (merges per hour by kind, how each merge landed, how lanes ended, against the previous tick and the 2026-09-26 baseline), the hook-event reads (a per-lane trace, a stall read when merges stop, a per-model comparison, all from what the lanes' tool calls did and not from what they wrote about themselves), a direct-gh call budget, then one VERDICT line (OK, or DEGRADED with the reason) and the NEXT action to dispatch. It never uses GitHub search and never merges, arms, reruns or dispatches. Use on every queue tick (every 30 minutes), after a session start, and whenever someone asks "is the merge queue healthy" or "why are merges slowing down".
prosthetic: true
replaces_when: "An omnimarket node or workflow emits the same per-window merge counts, open trend, blocker classes, drain liveness and verdict as a typed result on the bus, and the session-start workflow calls it instead of this script, on two consecutive sessions. On 2026-09-26 no node reports merge throughput; the drain's reports count work per run, and the drop from 44 to 27 to 25 merges per two hours while open PRs rose 123 to 130 was noticed by the operator, not by a report."
restored_from: "none: new skill (OMN-19814)"
ticket: OMN-19814
---

# Queue status (prosthetic)

One command, one block, one verdict. It reads only. What it tells the orchestrator to do, the
orchestrator dispatches itself (`/omni:merge-drain`, `/omni:pr-land`, `/omni:session-resume`).

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/queue_status.py" --tick
```

As the session's queue-status tick, run it with `--tick` (the launchd unit sets `ONEX_TICK=1`): a tick refuses
`--no-landing` with exit 64 before any read, because a tick exists to show the landing block (OMN-19998; the
session skipped it on about 93 tick runs). Requires `registry_root`. Reads `ONEX_STATE_DIR` for the clone-sync log. Without a fresh clone-sync run,
merge counts are untrusted and the script exits 3; there is no GitHub search fallback. Takes about
10 seconds when a recent drain map exists. The total deadline is 90 seconds by default; a needed
`drain_map.py` run continues detached after its budget, while the report reuses the last map and
shows its age. Each lab-side read (delegation health, hook events, pool status) waits at most `--lab-read-budget`
seconds for its host (default 40% of `--deadline`, between 5 and 40) and starts at the first step beside the other
independent reads, so a host that does not answer is `unread` and a DEGRADED reason, never the tick's deadline.
Every step of the tick (scorecard, watcher state, clone sync, merge counts, drain map, ledger rechecks, drain state,
rulings, companions, occ refs, milestone, inbox, delegation, merge pulse, hook events, landing state, liveness, landing)
runs inside its weighted share of the usable 90% of the time left (`node_tick_read_budget_compute`, `TICK_STEPS`); a
step that meets its budget is cancelled (the child it waits for is killed), prints `step    <name> unread (step budget
<n>s of the <D>s deadline exceeded)` and is a DEGRADED reason, and the block, VERDICT and NEXT still print. The drain
map step on its budget starts the needed run detached (when none is in flight) and reuses the newest finished map
under the state directory or one level under the reports root, where a drain writes its own map. A new step is added to `TICK_STEPS` and run through `tick_step`; the parametrized test fails until
it is (`tests/test_queue_status.py::test_a_step_that_hangs_is_unread_inside_the_deadline_and_the_block_still_prints`).

Exit `0` is OK, `1` is DEGRADED, and `3` means the clone-sync merge count or both local open-count
sources were unavailable. Exit 3 prints the reason, writes no trend point, and is never reported as
a healthy queue.

## What it prints

```
MERGE-PULSE GREEN|AMBER|RED reason=<first reason> | FIX: <its one fix> | ALSO: ... | merges 30m=N prev30=M drain=D src=git | ... | gh: calls=N/40 top=<lane>:N,... unattributed=P% refused=R | events: not yet
sred    <repo>: <shared red context> xN OWNED by <lane,...>|UNOWNED [<repo#n> ...] | ...   (only when the pulse names an armed-red stall)
QUEUE-STATUS read=<UTC> windows prev=<A>..<B> last=<B>..<now>
merges  last2h=N prev2h=M source=git
  by repo (last/prev): repo=n/m ...
open    N source=pr-watcher|drain-map (watcher state <why>) (+d since <last run>); trend merges=... open=...
queue   map open=N read=<map read time> source=reused <dir>|ran drain_map.py ... [; map reused age=Nm (stale: <reason>)]
  buckets: <drain_map buckets>   classes: <drain_map classes>
drain   live lanes (row <45m): N ...; newest <ts> <lane>
  runs: <open drain-run CLAIMs, last row, declared time box>
  successor: <newest successor named, by whom, started or NOT started>
deleg   120m expected rungs: local/<model>=N <provider>/<model>=N; lanes running=N; newest event <ts>
  pin-only rung <backend_id> (<provider>/<model>, <tier>; ordinary routing excludes it): no smoke or pinned run in 24h | PASS attempts=N accepted=N in 24h, newest <ts> | FAIL ...
  terminals: <n> lanes claimed since <stamp> closed without delegated= cells (report only)
occ     companions open=N batch-windows=W (per-pr=P ticket-batch=T window=B) by repo: repo=n ...
occ     batching flag OMNI_OCC_COMPANION_BATCH_MODE: <scope>='<value>' ... | unset everywhere (default on)
occ     refs repos=N off=a on=b unproven=c unread=d (live use only, at origin/<default>; mentions listed apart; required contexts from the controller cache; onex_change_control not measured)
  <repo>@<branch>: on workflow=n dependency=n precommit=n script=n code=n docs=n other=n contexts=n [<context>, ...]
  <repo>@<branch>: off | unproven (references all zero; contexts=unread (<why>)) | unread (<why>)
rulings RULING-MECHANISMS read=<UTC> window=14d rulings=N process=P ... unmechanized=U missing-path=K
milestone M4 board green|red read=<UTC> published=<UTC> run=<id>
  criteria: <n> green <n> red   red: <name>(streak=N,last_ok=<date>) ...
milestone unavailable: <the reader's own error lines, the gateway's cause before its REFUSED line>   (unread only past the board read's own wait)
running launchd-jobs=N (running now M) lane-runners=K workflows=W
  launchd <label> pid=<pid>|idle last_exit=<n>   (each loaded ai.omninode job whose command starts lanes or workflows)
  lane <lane> host=<host> model=<model> ticket=<id> since <UTC> by <starter> (receipt|process)
  workflow <name> session <id> wrote <n>m ago
  duplicate <tick>: launchd <label>, session pid <n>
stops   <stop> held by <ledger row id> (HOLD|RULING <UTC>)   (a deliberate stop a ledger row covers; kept out of DEGRADED)
opus    FLAG lane=<lane> ... started by <starter>: no escalation reason on its CLAIM or brief
placement DEFECT lane=<lane> ended no-host at <UTC> [(pinned host <host>)] while <host> read slots=<n> free; ... reading: <host>:cores=...,slots=<n>,login=...
degraded N reason(s)[, unowned repeats first]
  <reason> | first seen <UTC> age <age> runs=<n> | owner <CLAIM lane=<lane>|controller lease landing-L<n>|no owner>
inbox   <orchestrator lane>: N open item(s); BLOCKER unanswered: <id>, ...
landing delegation-share: since <UTC-12h> lanes=N delegated=A (P%) zero-with-reason=Z silent=S | engines onex-runs=R (lab=l glm=g other=o) codex=C jev=J | delegated-nothing (K): <lane> <lane>(silent) ... +M more
adopt   adoption: drift=N (<class>=n ...) adopted_prs=N pending_prs=N last_run=<UTC> age=<m>m errors=N | never run | unavailable: <why>
exceptions decision=N open=M unmechanized=K | exceptions unreadable: exception-queue.jsonl: <why>
trace   hook events <2h window>: events=N agents=A main-threads=M named-by-ledger=K/A newest=<ts> src=<lane>/<database>
  <lane or agent:id> calls=N failed=F refused=R retries=T span=HH:MM-HH:MM model=<model> (self-reported when the events carry none)
  repeats: work <lane> + <lane> shared-calls=N; stop <lane> + <lane> xN; prompt main:<session> xN | none
  claims-vs-events: <lane>: TERMINAL outcome=merged after only N completed tool call(s) in the whole agent; ... | none
stall   merges 30m=0; N agents active <30m window>: refused=a polling=b waiting=c quiet=d working=e   (or: not read: merges 30m=N)
  <state> <lane or agent:id> calls=N failed=F refused=R polling=<tool xN> waiting=Xm quiet=Ym
models  since <6h>: lanes started=N joined-to-events=J
  <model> (events|self-reported) lanes=N finished=F blocked=B open=O calls/lane=x (n=J) error-rate=E% handed-off=H came-back-red=R
landing landing-metrics <window> (<h>): merges N = r/h, product P = r/h, companions C (x/product), ...; attributed A%; lanes T: merged %, handed-off %, ...; green->merged p50 ..., red->fixed p50 ... | vs prev ...; vs 09-26 ...
fixer   6h: leases=N worker-min=M usd=U (MEASURED=a UNKNOWN=b) controller merges=G per-merge leases=x worker-min=y usd=z | controller merges=0 per-merge n/a | controller merges unread (no decisions.jsonl) | fixer: unread (no cost.jsonl)
parity  DEGRADED host=<host> item=<clone:<repo>|hook:<repo>|dispatch-venv|gh-auth|pytest|plugin:<name>>: <reason> (read <UTC>) | parity  OK hosts=N newest read=<UTC> | parity  no record in <dir>
parity  kb-clone host=<host> head=<sha8> behind=<n> commits lag=<age> (origin/main <sha8>) | at origin/main | not in the host records yet (<hosts>)
cost    gh calls=N budget=12 search=0 (map: reused|ran|none)
OVER BUDGET
reads: local=N github=M source=pr-watcher state <tick> age=<s>s | drain-map (watcher state <why>)
VERDICT: OK | DEGRADED reason=<reason> | <reason> ...
NEXT: <the first action to dispatch> (also: ...)
```

The `top=` lanes are labelled by joining each `session:<id>` cell of the gh call log to the lane identity registry (`ONEX_LANE_REGISTRY_ROOT`, else `ONEX_STATE_DIR`, else `$registry_root/.onex_state`, subdirectory `lane_identity`; a miss prints `session:<first 8 hex>`), and `unattributed=P%` is the share of windowed calls whose label still starts `session:` or `parent:` (OMN-20420).

## How to read the verdict

DEGRADED carries every reason that applies, and NEXT names the highest-priority action. Act on NEXT
in the same turn, through the skill it names, and cite the VERDICT line in the dispatch.

| Reason | Meaning | NEXT |
| -- | -- | -- |
| `drain map stale Nm` | the last map is over 30 minutes old while a detached refresh is pending | check host load and the run under the state dir's `run-*`, then wait for its map |
| `queue-status deadline Ns exceeded in <step>` | the total `--deadline` passed while a read was still running; the script printed a partial block (`QUEUE-STATUS INCOMPLETE`, the merge and open counts already read) and exited 1 | find the slow step it names (host load, a hung child), and rerun; `--deadline 0` disables the limit |
| `N step(s) unread (step budget): <names>` | each named step met its share of the deadline and was cancelled; its own `step    <name> unread (...)` line is above `cost` | find why that step is slow (host load, the read it makes) before raising `--deadline`; the drain map step has started its run detached |
| `drain map unavailable (...)` | the map budget expired or a run is in flight, with no earlier map to reuse | check the detached run's `run.rc` under the state dir's `run-*`, then rerun queue-status |
| `no live drain` | no drain lane wrote a ledger row in 45 minutes and no drain run is open | confirm the landing controller is live (`/omni:session-start` unit 3: loaded, a tick under 15 minutes old, `mode=act`) and fix it by its own install or kickstart (`/omni:landing-controller`); never launch a drain |
| `drain silent Nm` | a drain run's CLAIM is open but nothing drain-shaped wrote in 45 minutes | write the silent run's TERMINAL citing `supersedes-claim=`, then the same controller check; never relaunch it |
| `time box ends ... no successor queued` | a run ends within the hour and no successor has been named since its CLAIM | let it end; the same controller check. Nobody launches a successor |
| `dispatchable PRs with no lane: N` | the drain map's dispatchable-fix plus dispatchable-arm buckets, which by definition have no live owner, counting only PRs the read at least one drain refresh (10 minutes) earlier also listed, each PR once whatever the spelling of a renamed repository (`docs_repo` and `docs-repo`) and never a draft, which prints on its own `drafts:` line (OMN-19814); a PR the drain has only just been handed prints on a `newly dispatchable` line instead, since its lane starts within one refresh and CLAIMs minutes later | one `/omni:pr-land` lane per PR through the live drain |
| `merge rate falling for 2 runs` | last-2h merges fell on two consecutive runs | read the largest blocker class in the block and dispatch its fix |
| `open count rising for 2 runs` | the open count rose on two consecutive runs | same: inflow is beating landing |
| `delegation <provider>/<model> ... had 0 events in 120m while N lanes ran` | an expected delegation rung (the first ordinary rung of an expected tier; a rung the contract marks `explicit_pin_only` is never expected) answered nothing in the lab projection while lanes were running (`/omni:delegation-health`, OMN-19855) | the health check's FIX line: smoke that rung, then brief text steps through `onex delegate` |
| `pin-only rung <backend_id> ... had N attempts and 0 accepted answers in 24h` | a smoke or pinned run reached a pin-only rung and none was accepted (OMN-20341) | the health check's FIX line: the pinned smoke |
| `delegation health unreadable (...)` or `untrusted` | the lab delegation read failed or read zero rows in total; never read as healthy | restore the read with the FIX named in the reason |
| `change-control companions outnumber batch windows: N > W (...)` | more open autobind companions in onex_change_control than batch windows: some repository has two or more open companions (OMN-16336) | find why that repository's companions were not batched into its window: a companion minted before window batching reached the runtime, the per-PR companion effect leg, a legacy per-PR re-mint, or a repository that turned batching off; fix the producer, then close the extras once their product PRs are rebound |
| `change-control batching switched off: OMNI_OCC_COMPANION_BATCH_MODE <scope>='<value>'` | an org or repository Actions variable turns batching off, or holds a value the publisher refuses (OMN-16336) | remove the variable from the named scopes, or record the ruling that keeps it off |
| `process rulings with no mechanism: N` / `ruling mechanism paths missing: N` | an operator RULING of the last 14 days, older than 24 hours, changed a standing process and has no mechanism built and wired: a ticket alone, a path that is gone, or a path nothing requires and runs (OMN-19854, OMN-20780) | last in NEXT, after every queue action: run `ruling_mechanisms.py` below and, per line, build and wire the mechanism (its ticket is on the line) and append its CORRECTION row |
| `merge pulse RED: <reason>` | `merge-drain/scripts/merge_pulse.py` (OMN-19852) found zero merges with mergeable PRs, a red landing `dev` head, a heartbeat over 20 minutes, idle lab slots while PRs wait on the lab, or a stale order edge; the pulse's own fix leads NEXT | dispatch the fix the pulse names, before any other action |
| `merge pulse RED: <repo>: N armed PRs, M red ... ownership: <context> xN OWNED by <lane> or UNOWNED` | a shared red is OWNED only by (a) a live non-dispatcher CLAIM that names the cause (a `cause=<repo>:<check>` cell, or the check name AND the repo on its first line) and whose lane wrote a row in the last 45 minutes, or (b) an unreleased controller cause lease in `state.json` (owner `landing-L<n>`); a per-PR CLAIM never owns, so 21 PRs each with a live lane still read UNOWNED (OMN-20418, replacing the OMN-19852 per-PR owner rule). A CLAIM owns the whole family of checks that share a cause: one on a root owns every gate that inherits it (`<gate> xN inherits <root>`), and one on the inheriting gate is a CLAIM on its root; the throughput tick's `repo-status` line reads the same rule (OMN-19998). Otherwise it is UNOWNED, and no lane is working it, whatever a summary line says | OWNED: read that lane's rows or the controller's cause leases and dispatch nothing new; the lane drops out at 45 minutes of silence. No watcher state, or an unreadable `state.json` / `ticks.jsonl` of the controller: the reason says `ownership unread`, and neither answer is claimed (never OWNED) |
| `merge pulse RED: ... UNOWNED` with NEXT `dispatch ONE cause lane ...` | the largest UNOWNED shared red has no lease for it in the last two lines of the controller's `ticks.jsonl` (a fixer HOLD, a spent budget, no capacity, or a cause under the threshold). NEXT prints the exact `onex_remote_lane.py run ... --lane cause-<repo>-<check> ...` command, with `--cause <repo>:<check>` (the runner writes it into the lane's CLAIM) and the PRs named; queue-status prints it and never runs it (OMN-20418) | run that one command (the runner's `--cause` puts the cell on the CLAIM it writes, which the controller reads as the owner and dispatches nothing for that cause). When the controller shows a lease in either of its last two ticks, NEXT says the controller is on it and names no lane: dispatch nothing |
| `held` line (no reason) | the PRs the controller holds for a person (OMN-17427): its sidecar's `head_escalation` entries with `needs_person` done, still open at that head in the watcher state. The line gives the count, the count per person, the oldest hold with its age and its reason's first sentence. `held    none` when nothing is held, `held    unread (...)` when the sidecar cannot be read. Information only; it never degrades the verdict | the throughput tick prints one `NOTE held:` line per held PR (repo#n, title, person, reason, age); the person acts, the controller sends no more workers to that head |
| `fixer` line (no reason) | the controller's `cost.jsonl` (one row per released lease, written by the controller) over six hours: leases, worker-minutes and USD per controller merge, with merges counted from the controller's own `decisions.jsonl` (`kind=merge outcome=merged`), never GitHub. USD sums only `usage_source=MEASURED` rows and the `UNKNOWN` count is printed beside it. A missing `cost.jsonl` prints `fixer: unread (no cost.jsonl)`, never zero (OMN-20418) | read it as cost per merge against the 2026-10 baseline of 7.5 leases and 141 worker-minutes per merge; nothing to dispatch |
| `fixer burn <repo>: N leases dispatched in 2h at X per controller merge` | at least 20 leases dispatched for one repo in two hours at more than 15 per controller merge of that repo (zero merges counts), twice the measured baseline (OMN-20418). Never read off an unread merge count | the fixer HOLD for that repo: a ledger HOLD row `scope=fixer repo=<repo>` through `/omni:ledger-msg` (`hold --lane <your lane> --to all --kv scope=fixer --kv repo=<repo> --until <UTC stamp>`, then a line of three dashes and the reason); the controller then dispatches no worker for the repo and revokes its live ones; a RELEASE row lifts it |
| `landing controller park holds <repo> (N open PRs): <cause> parked until <T>` (and a `park` line) | the controller's `state.json` holds a cause with `parked_until` later than now and member PRs, so its members get no worker; one reason per parked cause. A missing or unreadable `state.json` prints `park    unread (...)` and is no reason of its own (OMN-20852) | the NEXT is the retry conditions from the cause's `PARKED` record in the controller's `evidence.json` (automatic; nothing to append). `CONTROLLER_DEFECT` means a controller defect: dispatch a controller fix lane from the worker results; never an operator question, OMN-20068. |
| `landing controller convergence is off: landing_install.json is moved aside (<file>)` or `landing controller install <rev> is behind main for <N>m` (and an `install` line) | the controller's install record (`~/.omninode/landing-controller/landing_install.json`) is missing, so no tick refreshes the install from main; or the installed `source_commit` (`installed-revision.json`) lacks a main commit older than two hours. An unread revision or clone prints `install unread (...)` or `lag unread` and is no reason of its own (OMN-19998) | move the record back (`mv <file> landing_install.json`); a branch install uses `install.sh --branch-hours`. For the lag, clear the newest refusal in `install-failures.jsonl`, which the NEXT quotes; the next tick refreshes from main |
| `plugin version bump <repo>#<n> open <N>m (over 90m), ci=<verdict>` (and a `bump` line) | the post-merge plugin version bump pull request (branch `automation/omn-20497-plugin-version-bump`) has been open past `BUMP_STUCK_AFTER` in the watcher state, so the plugin changes merged since the last bump run on no host. Every run prints `bump    <repo>#<n> open <N>m ci=<verdict> head=<sha> pushed=<time>`, `bump    none open`, or `bump    unread (...)` with no fresh watcher state, which is no reason of its own (OMN-20497) | read the PR's checks and head push times (`pr_state_local.py --pr`), the plugin-version-bump runs and the controller's ticks for it, and fix what holds it; never merge or arm it by hand |
| `lab host parity failed: <host> (<items>)` | a lab host's latest parity record, kept in the placement directory by every pool read, fails an item (OMN-20266): a registry clone missing or behind its origin tip (`clone:<repo>`), a clone without its executable pre-commit hook (`hook:<repo>`), a dispatch venv whose omnimarket revision differs from the launching host's, gh auth or pytest failing, or an installed omni plugin whose file tree differs from the tree of the revision it shipped (`plugin:<name>`, a hot-patched runner). One `parity  DEGRADED host=... item=...` line per failing item. Placement refuses the host for what the unit needs, and a plugin that differs refuses it for every unit | repair the named item on that host; the next pool read replaces the record, and a host read clean stops being reported |
| `lab host docs_repo clone behind origin/main: <host> <age>` (and a `parity  kb-clone` line) | each pool read records the docs_repo clone of every lab host beside the registry clones (OMN-21470: the lab clones were 8 to 10 days old and no parity item looked); the tick measures the age of the oldest commit the host's clone lacks against the canonical clone's `origin/main`, because the host's own `tip` is its own stale origin. Past 24 hours is a reason; a clone not yet in a host's record is one line for all such hosts | bring the named host's clone to `origin/main` through the clone-maintenance unit or a fast-forward |
| `duplicate <tick> tick copies: ...` or `queue-status tick ran at gaps of Am, Bm, Cm against a 30m cadence: a second copy is running it` | a loaded launchd job and a session process (or two launchd jobs) run the same tick; or two of the last three gaps between runs in the trend history are under 18 minutes while the tick's cadence is 30 (OMN-21470: the recorded gaps were 15, 14 and 17 minutes) | cancel the session copy (CronList, then CronDelete its id) or boot the launchd job out; keep one |
| `opus lane(s) started without an escalation reason: <lanes>` (and `opus    FLAG` lines) | a lane on Opus, running (its receipt and brief) or started in the last eight hours (its CLAIM), whose CLAIM and brief state no escalation reason: a prior failed Sonnet attempt on the same ticket or PR, or a stated complexity reason. The line names the starter (OMN-21470; RULING 2026-10-27: every lane starts on Sonnet) | restart the lane on Sonnet, or have its starter record the reason on the CLAIM |
| `placement said no-host against free slots: <N> refusals on <M> lanes in 2h, newest <lane> (<host> slots=<n>)` (and `placement DEFECT` lines, one per lane, four at most) | lane receipts of the last two hours ended no-host while their own pool readings show a host with `slots` above zero, the engine's login and no admission or lane refusal (a pin that names a host in the readings limits this to that host); each line carries the count, the readings and the pin (OMN-21470: a pin on `lab` was refused while h904 read slots=3, and the receipts of 36 hours held 2279 such refusals) | read the receipt and the placement node's decision for the lane; a pin that names no host, a stale limit marker or an unshown bar is the defect |
| `merge pulse unavailable` | the pulse script raised; never read as healthy | run it by hand and fix its failure |
| `milestone board red: <checks> since <time>` | the M4 board's latest publish carries at least one acceptance-criteria row read `red` (OMN-17427: the board read red for hours before anyone saw it) | dispatch an opus diagnosis lane for the red board checks |
| `hook events unreadable (...)`, `hook events untrusted (the projection table holds 0 rows ...)` or `hook events stale: newest <ts> (Nm old)` | the claude_hook_events read failed, the table is empty, or its newest row is more than 15 minutes old while the tick runs (OMN-19513): a trace over a stale table describes the past | the action named: deploy or repair `node_projection_claude_hook_events`, or check the hook capture producer and the consumer lag |
| `orchestrator inbox: N unanswered (ids)` | at least one open MSG addressed to the orchestrator lane names BLOCKER and has no ACK (OMN-17427: a fleet-wide-red BLOCKER MSG sat unread 31 minutes) | read and answer the named MSG(s), then ACK them |

A `stops` line is a deliberate operator stop that a ledger HOLD (in force: before its `until=` and with no RELEASE) or a RULING of the window names in one cell, with a word that says it is a stop: a landing controller install record moved aside with an `operator-stop` suffix, a launchd job whose plist sits under `~/Library/LaunchAgents/retired-*`, a host recorded out for repair. It prints once as `held by <row id>`, and the faults it would raise (the convergence-off reason, the host's parity lines, a retired job's reasons) are left out of DEGRADED. A row that only names the thing covers nothing, and a stop no row covers stays a fault (OMN-21470).

Every DEGRADED reason also prints a `degraded` line with when it was first seen (from the trend history, which stores each run's reasons), its age and its owner: a live CLAIM (the lane wrote a ledger row in the last 45 minutes and its CLAIM names a file, host, check, PR or ticket the reason names), an unreleased controller cause lease for a shared red, or `no owner`. A reason seen on two runs with no owner sorts first in the VERDICT (OMN-21470).

The trend compares this run with the last two runs within six hours of each other; a longer gap
starts a new series (another session), so the first two runs of a session never report a trend.
The in-run comparison `last2h` against `prev2h` is printed for reading, not for the verdict.

A `successor ... NOT started` line with live drain lanes is not DEGRADED: per-repo lanes are working.
It becomes `no live drain` the moment those lanes go quiet. In the controller era (OMN-19998,
OMN-19815) no drain reason ever asks for a drain launch: the landing controller owns landing and the
orchestrator never launches, resumes or swaps a drain (docs_repo
`beta/plans/2026-09-27-merge-drain-that-merges-plan.md` section 7).

## Where each number comes from, and what it costs

**Merges, by repo: the canonical clones, zero GitHub API.** The launchd agent
`ai.omninode.canonical-clone-sync` (OMN-19607) fetches every canonical clone under the registry
roots every 3 minutes, git transport only, and logs each run to
`$ONEX_STATE_DIR/logs/canonical-clone-sync.jsonl`. It was built after the operator's 2026-09-25
ruling that lanes query the clones instead of spending API reads. Each fetch that moves a base branch
writes a reflog entry on `refs/remotes/origin/<branch>` stamped with the fetch time, so a PR landed
when the fetch that first carried its squash commit (subject ending `(#N)`) ran, to within one sync
interval. Commit dates are not used: a merge-queue commit is built before it lands
(omnibase_infra#4176 was built at 20:53Z, merged at 21:15:37Z and fetched at 21:15:50Z). A `main`
update in a repo that also has `dev` counts only commits not on `origin/dev`, so a release
fast-forward never recounts dev merges; a hotfix PR landing on `main` alone still counts. A PR seen
in two clones counts once, at its earliest time.

The clone sync holds merge history only. A missing run or one older than 15 minutes produces
`QUEUE-STATUS UNTRUSTED: merge counts need the canonical clone sync ...; no GitHub search fallback`
and exits 3 before a trend point is written. A zero from a fresh sync is a real zero.

**Open count.** A fresh `$registry_root/.claude_scratch/pr-watcher/state.json` supplies
`local.open_counts(...).open`: the open PRs that are not drafts and not in a repository the merge
sweep rules out (`merge-sweep/sweep_scope.json`, read through `pr_state_local.read_out_of_scope`,
never a copy; OMN-17427). The same line prints `drafts=N (excluded) out-of-scope=N (excluded)`, so
the number left out stays visible; a draft in an out-of-scope repository is counted as a draft, so
`open + drafts + out-of-scope` is the watcher's whole open inventory. An unreadable scope prints
`out-of-scope=unread (<why>)` and still leaves the drafts out. If the watcher is stale or unreadable,
the count is `q.open` from the drain map, counted the same way, and the line names the watcher
reason. If neither local source exists, the run exits 3. The trend and the "open count rising for 2
runs" reason read this count only: a history point carries `open_basis` and a point written before
the change (drafts counted) is not part of the series.

**Blocker classes: merge-drain's `drain_map.py`, read-only.** Its buckets and classes are counted
from `drain-map.tsv`; nothing here re-derives an owner, a hold or a class. A map newer than 30
minutes under `$registry_root/.claude_scratch/reports` (where drains write theirs) is reused. Otherwise
the script runs `drain_map.py` into a `run-*` directory directly under its state directory, keeping
the check-runs cache in the state directory between ticks. That run spends core REST quota (one
pulls list per repo with open PRs, plus check-runs for heads the cache lacks); `--no-run-map` skips
it and prints `classes unavailable`.

**Drain liveness.** The rolling ledger, parsed with `drain_map.py`'s own row reader and its
canonical dangling-CLAIM definition. A drain lane is any lane with `drain` or `drains` as a name
segment (`repo-drains-83j`, `repo-drain-omnimarket-pr`, `merge-drain-83`), except `drain-watchdog`.
A drain run is a `repo-drains-*` or `merge-drain-*` lane; its CLAIM is closed by its own TERMINAL or
by a TERMINAL from its family (`repo-drains-83i-close` closes `repo-drains-83i`). The time box is the
last `until=`, `ends=`, `time-box=` or `deadline=` stamp in the run's rows. The successor is the
newest `successor=<lane>` or successor-required MSG naming a lane in a drain lane's row, and it has
started once any row from that lane or its family follows.

**Lab delegation.** `/omni:delegation-health`'s `collect()`, imported, read-only: the lab
projection over ssh through the `delegation_health` overlay, about three seconds. Its verdict joins
this one; its silent-TERMINAL count is printed as a report and is never a reason. Each pin-only rung
(the contract's `explicit_pin_only`, OMN-20341) prints one evidence line under the `deleg` line: absent
or passing results never change the VERDICT, a present result with no accepted answer is a reason. It
adds no read, so the 90 s deadline is unchanged. `--no-delegation` skips it and the block says so (tests).
**Change-control companion batching (OMN-16336).** A fresh watcher state supplies
`local.pulls_of("onex_change_control")`; there is no GitHub fallback. Without it the line says
`companions: unavailable (watcher state <why>)`. Only the autobind producer's branches
count: `auto/window-<owner>-<repo>-occ-autobind` (one per product repository, the default),
`auto/ticket-<t>-occ-autobind` (a legacy per-ticket batch) and `auto/<owner>-<repo>-pr-<n>-occ-autobind`
(one per product PR). The producer folds every open product PR of a repository into that repository's
batch window, whatever ticket it cites, so each repository is one window, and a per-PR companion counts
toward its repository's window; a legacy ticket batch cannot fold into a window and stays its own. More
companions than windows is DEGRADED, and the line names the repository and its OCC numbers. While the
companions minted before window batching reached the runtime are still open this reads DEGRADED: that
is the backlog draining, not a false alarm.

**Off change control: the `occ refs` line (OMN-20074).** A repository is off onex_change_control when this
line says `off` for it, and only then. It is not "the repository stopped minting companions": that was the
2026-10-14 inference, made from one signal, and a full read the same day found three repositories off where
several had been reported (the operator's RULING 2026-10-14T05:30:13Z asks for every repository, infra_repo
deferred, off by the end of that day). The `occ refs` read in `scripts/queue_status.py` uses only local state, with no GitHub call:

- every registry canonical clone (the root's direct children whose `.git` is a directory, the root itself, and the
  ops_tooling_pkg clone beside it; a dot-directory, a linked worktree and a clone of anything outside the
  OmniNode-ai organisation are not the registry; onex_change_control is what is measured against, so it is not
  listed), at `origin/<default>` as `origin/HEAD` names it, never the working tree or a branch it happens to hold;
- `git grep` for `onex_change_control` or `onex-change-control` (case and `_`/`-` insensitive), each line counted
  once under the first kind that fits: `workflow` (under `.github/workflows/` or `.github/actions/`: a `uses:` or a
  checkout), `dependency` (a manifest or lockfile: pyproject.toml, uv.lock, requirements*.txt, package.json, ...),
  `precommit` (`.pre-commit-config.yaml` or `.pre-commit-hooks.yaml`: a `repo:` or a hook), `script` (scripts/,
  tools/, bin/, ci/, shell, make, Dockerfile: a fetch or a clone), `code` (a source or test file elsewhere),
  `docs` (prose, a changelog, a ticket contract under `contracts/OMN-*.yaml`, and a comment-only line of any
  file) and `other` (data and configuration). Each line is then placed LIVE or a MENTION, and only live lines
  count toward `on` (the recorded definition: a docs line, a comment, a docstring, a historical record and a test
  fixture string are not live use). `docs` is always a mention; a `dependency` line is live; a `workflow` line is
  live unless it is a `name:`, `description:` or `echo` line; a `precommit` line is live when it is a `repo:`,
  `entry:`, `id:` or `rev:` key, else prose; a `script` or `code` line in Python is placed by its token (a NAME
  token that is the module name, as in `import onex_change_control`, is live; a comment, a docstring, a bare
  string statement, an identifier that merely contains the name, a string of four words or more and any string
  in a test file are mentions; a string that locates the repository, `OmniNode-ai/onex_change_control`, a URL,
  `onex_change_control/contracts`, `home / "onex_change_control"`, is live; a bare name string, a repo-name list
  entry or a topic name is a mention), and in another language by the same rules read from the line; a shell,
  make or Docker line is live outside a test tree; an `other` line is live only under `.github/` or in Terraform;
  any line under a `fixtures/` tree is a mention. A string in non-test source that locates the repository is
  counted live on purpose: a false `off` is the failure this line exists to stop;
- the OCC callers that never spell the repository name, as live `workflow` use: a workflow or action file under
  `.github/` whose name carries an OCC job word (`call-occ-autobind.yml`, `occ-preflight.yml`, `receipt-gate.yml`,
  one line at line 1), and a `uses:` line in any other `.github` file whose reusable is so named
  (`call-occ-autobind-reusable.yml@dev`). A file or call of the receipt gate that sets `evidence-source: caller`
  runs it on the caller's own contracts, the replacement, and is not listed. Without this a repository that still
  mints companions through a shared reusable reads `off`;
- the repository's required contexts on that default branch, from the landing controller's `required-contexts.json`
  (`$LANDING_STATE_DIR`, `--landing-state-dir`), read per base branch and no older than six hours exactly as the
  ruling audit reads it, keeping those that name an OCC job: `occ` as a word (`occ-preflight / eligibility`,
  `OCC Companion Merged Gate`), `change-control`, `receipt gate`, `companion`, and `verify / verify`.

`off` needs every live count zero AND the contexts read. Live references all zero with the contexts unread (no
cache entry, a stale one) prints `unproven`, never `off`; a clone with no `origin/HEAD` or a failed `git grep`
prints `unread`. Any nonzero live count prints `on` with every live kind and the mention counts beside them, so the
remaining work is visible: a repository with only `code` live is closer than one with a `workflow`. The line is
report-only and never changes the VERDICT, and it spends no GitHub call. Run it alone with
`python3 "${CLAUDE_SKILL_DIR}/scripts/queue_status.py" --occ-refs-only` (no other read; exit 0 only when every
repository is off); add `--occ-refs-list` to print each live line as `repo@branch kind path:line text`, the table of
what still uses onex_change_control; `--no-occ-refs` skips it in the block. In the block the step has its own budget
(`--occ-refs-timeout`, 30 s, capped at a quarter of `--deadline` and so that it ends by 65% of it when it starts late; the budget is checked before every git call and in the loops that parse what git returned): past it the lines become one
`occ     refs unread (step budget <n>s exceeded; ...)` and the rest of the block, the VERDICT and NEXT still print
(a slow `git grep` on a loaded host used to take the whole deadline, OMN-19814). The OCC companion producer was removed by
omnimarket#4151 (OMN-17427) and declared retired under OMN-20074: `retired` in `scripts/occ_companion_producer.json`
is true, so the step prints `occ     refs skipped (...)` and reads nothing; `ONEX_OCC_PRODUCER_DECLARATION` names another
file and `--occ-producer-retired` declares retirement for one run. The companion-batching line above measures minting,
which says nothing about whether a repository still reads onex_change_control.

**Batching switched off (OMN-16336).** The Actions variable `OMNI_OCC_COMPANION_BATCH_MODE` at org
scope and on each autobind-calling repository (`AUTOBIND_REPOS`), read from the PR watcher's state
(OMN-17427) with no GitHub call: the watcher reads each variables listing on the operator credential
with gh read routing off (the routed read-only App token has no Actions-variables permission and
answers 404 for every variable, which is a false "unset") and records whether it read it. A scope
whose listing the watcher did not read, or any scope when the state is stale or written before the
field (`caller_fields` below 2), is printed unreadable with the reason, never taken for unset. A set value the publisher reads as the default is printed
with `(reads as window, the default)`. The variable can only turn batching off: unset, `window` and the retired pilot value
`ticket` read as the default, `off` turns it off, and any other value is refused by the publisher. Either
of the last two is DEGRADED and named. A scope that cannot be read is printed as unreadable, never
guessed. `--no-companions` skips the companion and flag reads.

**Process rulings with no mechanism: `scripts/ruling_mechanisms.py`, zero API.** It reads the
RULING and OPERATOR-CONSENT rows of the last 14 days through the same `drain_map.py` row reader (live ledger and archive
rolls) and lists each standing-process ruling that has no mechanism built and wired (OMN-20780). A
`mechanism-ticket=` alone is pending work, never a mechanism: the line reads
`UNMECHANIZED (pending OMN-n)`, or `(pending none)` when the ruling names no ticket either. A
`mechanism=` path counts only when it resolves under `$registry_root` or its parent and is wired; a ruling
with several paths is mechanized only when every path is (OMN-21061):

| the path is | it is wired when |
| -- | -- |
| a content check (a script, a workflow file, a directory) | the workflow job that runs it (or any job of the workflow file itself) is a required context, or a job of its workflow that is one `needs:` it, in the landing controller's cached branch protection (`$LANDING_STATE_DIR/required-contexts.json`, default `~/.local/state/omni/landing`) read for the repository's landing branch (`origin/HEAD`; with that unknown a context counts only when every cached base requires it) and no older than six hours, AND the repository's `.pre-commit-config.yaml` has a hook that references it. A step in a job nothing required polls is unwired. A reusable workflow's job matches as `<caller job> / <job>`. A gate declared `pre_commit: not-applicable` in the repository's `.github/required-checks.yaml` (it judges the PR itself) needs no hook. CI only, or a hook only, is unmechanized |
| a guard registered as a tool hook | a `hooks/hooks.json`, `plugins/*/hooks/hooks.json` or `.claude/settings.json` of its repository references it |
| a timer (`.plist`, `.plist.tmpl`, `.timer`) | its unit is loaded (`launchctl list <label>`, `systemctl show`) and has a run record (a launchd unit's log file, a systemd `LastTriggerUSec`) younger than twice its declared period (`StartInterval`, `StartCalendarInterval` and `OnCalendar` alike); a unit that declares none is unmechanized. A host with no `systemctl` (a Mac) asks the lab pool instead (OMN-19854): one `ssh <host> systemctl show '*.timer'` per remote host of the landing pool (`LANDING_POOL_HOSTS`, else the shared lab host table), both scopes, once per run. Active on any host that answered is loaded; every host answering and none running it is not loaded; a silent host or a scope that failed leaves the unit `UNJUDGEABLE kind=unsupported-probe`, never unloaded |
| a skill script that a tick of the host installer contract runs (`skill_script`, resolved from `OPS_TOOLING_PKG_PATH`, else `$registry_root/../ops_tooling_pkg`) | judged as a timer from the tick's `label`, `start_interval` and `evidence_file` heartbeat: loaded unit and a heartbeat younger than twice the interval; an unreadable contract, an unloaded unit or a stale heartbeat is unwired, and a script no tick declares is still judged as a content check (OMN-21022) |
| prose (`.md`, `.txt`, `.rst`) | never: a rule written in a document is not enforced by it |

Wiring is judged by textual reference (the repository-relative path, its basename as a whole token,
or its dotted module name) in those files: the audit checks wiring, and each mechanism's own pull
request carries its negative control. A later CORRECTION with `corrects=<ruling ts>` and `mechanism=`
replaces an earlier value. `MISSING-PATH` still lists a `mechanism=` that resolves to nothing.
**A ruling counts only when its mechanism is installed and acting (OMN-19854).** Installed is the
table above; acting is at least one ledger row in the last 24 hours, other than a RULING,
OPERATOR-CONSENT or CORRECTION, whose `actor=` is the mechanism: `<kind>:<name>` with kind one of
script, launchd, timer, hook, systemd, cron, bot, workflow and a name equal to a mechanism path's stem
(hyphens and underscores alike), a timer label's last part or a declared tick's name; a bare
`actor=hook` takes its name from the row's `guard=` cell. A `mechanism-actor=<actor>` cell on the ruling
or its link row names the identity exactly instead. A model lane (`claude:`, `codex`) acting never counts.
A CI check writes no row when it judges a pull request, so `mechanism-actor=workflow:<check context>`
(spaces in the context written as underscores) also counts each `success` or `failure` run of that check in
the last 24 hours on a pull request of a repository the mechanism paths name, read from the PR watcher state
(`$ONEX_PR_WATCHER_STATE`, else `$registry_root/.claude_scratch/pr-watcher/state.json`); a skipped, cancelled or
timed-out run never counts (OMN-17427). With no `mechanism-actor=`, a script path's check is each required job
whose steps run it (a step that only names it in its `name:` title does not), and a workflow file's is its job
when it has exactly one; a workflow file of several jobs (a `ci.yml`) derives none. A timer or declared tick
acts by running: a loaded unit whose run record is inside the last 24 hours counts, as `RUN actor=timer:<unit>`
(OMN-19854).
An installed mechanism with no such row, run or run record is a `NOT-ACTING` line and fails the exit code; the summary
carries `mechanized=` (installed), `acting=` (counted) and `not-acting=`. When a wired check derived no actor, the
`NOT-ACTING` line ends `derived no check actor; name the job that runs it: mechanism-actor=workflow:<job>` over the
required jobs that name the path: copy it into a CORRECTION with `corrects=` and `mechanism=` (OMN-19854). A test file (under `tests/`,
`test_*.py`, `*_test.py`, `conftest.py`) is never a mechanism.

OPERATOR-CONSENT rows are audited beside RULING rows (`type=OPERATOR-CONSENT` on the line). The rule
for process versus decision is fixed: the operator row's own `kind=process` or `kind=decision`, else
`mechanism=`/`mechanism-ticket=` (process), else an OPERATOR-CONSENT is a decision (`basis=consent`: "Yes",
"Send", "Agreed" approve one action, not a standing process) and a RULING is process (`basis=default`); a
consent that is standing process carries `kind=process` and is judged; words are never read. Only
an operator row moves a ruling out of the audit: a RULING or OPERATOR-CONSENT that links it with
`kind=decision`, or a CORRECTION with `kind=decision` and `operator-row=<ts>` naming an existing RULING
or OPERATOR-CONSENT row. Any other `kind=decision` link is refused and listed as `DEMOTION-REFUSED`.
Run it alone for the per-ruling lines:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/ruling_mechanisms.py" --days 14      # --quiet: summary only; --json
```

`--json` carries `schema: 2`, each unmechanized ruling with `pending_ticket` (the `mechanism-ticket=` or `none`),
its `wiring` verdicts and `grace_hours`: the list a dispatcher reads to mint or build the missing
mechanism. Three arrays are additive: `declared_not_enforced` (a gate its repository declares REQUIRED that
is neither a cached context nor needed by one), `unjudgeable` (per mechanism, why this host cannot tell:
`no-cache`, `stale-cache`, `unreadable-cache`, `no-clone`, `no-contract`, `unsupported-probe`,
`unsupported-schedule`, `unresolved-placeholder` (a `.plist.tmpl` no declared host tick names, or one several share); an `UNJUDGEABLE` line fails the exit code and is never skipped; a ruling whose every unwired path is unjudgeable is listed `UNDETERMINABLE`, counted in `undeterminable=` and not in `unmechanized=`: run the audit where the evidence lives, build nothing) and
`path_verdicts` (every path of every process ruling). Exit 0 is clean, 1 lists at least one ruling, 2 means the ledger could not be read. Every
finding is listed at once, but queue-status prints DEGRADED only for a ruling older than 24 hours, so
a mechanism has a day to land. The operator-ruling skill refuses a new process ruling whose
`mechanism=` path does not resolve unless it carries a `mechanism-ticket=` (its section 3a), so every
new unmechanized ruling has a ticket; rulings recorded before that with neither read `(pending none)`.
The session preflight carries the same check as its `ruling_mechanisms` warning row.

**Delegation share (operator RULING 2026-09-28T06:24:10Z, OMN-17427).** The first `landing` line
counts, over the last 12 hours (`--delegation-share-hours`), every lane that closed a TERMINAL:
how many carried delegation cells (`delegated=<n>` with `runs=`, `codex=` or `jev=`, the cell names ops_tooling_pkg's grammar still carries; a lab agent session id rides in `runs=`), how many
wrote `delegated=0 delegation_reason=<why>`, and how many were silent, then the runs cited per
engine (onex delegate runs split lab/GLM from their local receipts under
`$registry_root/.onex_state/runs/`, GLM through Claude Code from the harness-delegate receipts under
`$registry_root/.onex_state/harness-delegate/` and `~/.local/state/omni/harness-delegate/` (OMN-20374), cited ids
that match no receipt as `unverified=`, Codex thread ids, lab agent session ids, Jev correlation ids), and the lanes that
delegated nothing, silent ones marked `(silent)`. The classification is ops_tooling_pkg's
`onex-delegation-accounting` (`share_summary`), imported through the plugin's clone resolver the
same way `/omni:delegation-health` imports it, so the morning report, the health check and this
line never disagree. It is report-only and never changes the verdict; the enforcement is
lane-brief part 3a.9, which `lane_brief.py check` refuses without Codex first, the lab, GLM, Jev and lab code
steps. A clone that predates the share format prints `delegation-share: unavailable: ...`.
Run it alone: `onex-delegation-accounting --format share --since <UTC> --runs-root
"$registry_root/.onex_state/runs"` from the ops_tooling_pkg clone.

The `deleg2h` line reports the share of TERMINALs in the last two hours whose cells resolve to a real
receipt, by engine. Relayed onex runs are read from the local runs root, and Codex existence
records are also read from `$registry_root/.claude_scratch/delegation-receipts-relayed/`. For `land-*` and `prove-*` lanes, a share below 50% is a DEGRADED reason; typed
`delegation=na:<reason>` rows are left out of the share base. A TERMINAL with
`outcome=rejected-no-delegation` (the remote-lane runner's close for a lane whose final text had no
DELEGATION line, OMN-17427) is counted on its own as `rejected-no-delegation=<n>`, apart from `none`.
Each such lane also gets a `  rejected-no-delegation: lane=<lane> starter=<who>` line, the starter read from the
lane's CLAIM (`parent=`, else `principal=`, else `unknown`), and a DEGRADED reason and action naming the starter
(OMN-21573).
A third line counts the claude-glm harness receipts on this host for the same window
(`glm receipts on this host`: runs, done by model, failed, how many a TERMINAL cites, tokens; OMN-20844):
GLM runs that tools and skills make write no TERMINAL, so the engine count above read `glm=0` while they
happened. A landing-text log line with `engine=glm` counts as GLM, not lab.
`--no-delegation` skips this check.

**Milestone board: infra_repo's own `read_published_board.py --summary` (OMN-17427),
one Actions API read.** That script reads `publish-beta-board.yml`'s own `publish` job for the run
whose `Upload to S3` step last succeeded, never the served board (behind Google Workspace edge auth
since OMN-18044) and never a live render. `--summary` also returns the generator's own printed
acceptance-criteria table (name, `green`/`red`, streak, `last_ok`). Any row read `red` is a DEGRADED
reason naming every red check and the oldest `last_ok` among them (2026-09-28 FRICTION: the M4 board
read red for hours -- C13, C29 -- before the operator asked and found it). `ONEX_BETA_BOARD_READER`
overrides the reader's path (test seam); the live default is `$registry_root/infra_repo/tools/beta_board/read_published_board.py`.
An unreadable board (no clone, a bad read, an unparseable summary) is a note, never a claimed red:
absence of evidence is not evidence of red, the CLAUDE.md rule 16 posture read in reverse. `--no-milestone`
skips it.

**Orchestrator inbox: `/omni:ledger-msg`'s own `inbox.sh` (OMN-17427), zero API, one ledger read.**
Never a second parser of the MSG/ACK/HOLD/RELEASE grammar. The orchestrator lane is
`--orchestrator-lane`, else `$ONEX_ORCHESTRATOR_LANE`, else the newest `CLAIM` whose `lane=` is
exactly `orchestrator` or `orchestrator-<suffix>` in the last 3 days. Any open (unACKed) `MSG` whose
row text names BLOCKER is a DEGRADED reason naming its `id=` (2026-09-28 FRICTION: a fleet-wide
`omnibase_infra` red BLOCKER MSG to `orchestrator-83` sat unread 31 minutes because the merge-drain
tick read only `to=operator` rows). `--no-inbox` skips it.

**Landing measurement: ops_tooling_pkg's `onex-landing-metrics` (OMN-19852), one GraphQL
search per new window.** The block's `landing` line is that command's `--one-line` summary, run
through `${CLAUDE_PLUGIN_ROOT}/scripts/onex_landing_metrics.py` (the same clone resolver as
`onex_ledger.py`: `OPS_TOOLING_PKG_PATH`, else `$registry_root/../ops_tooling_pkg`). Per tick it
reads the merges since its last recorded window, classifies each by kind (companion, release bump,
ledger publish, product) and by mechanism from the ledger (sweep-lane fix, arm script, companion
with parent, lane land, prior auto-merge, automation, collaborator merge, unattributed), classifies
every lane TERMINAL by outcome, appends one JSON line to
`$registry_root/.claude_scratch/landing-metrics.jsonl`, and prints deltas against the previous tick and
the 2026-09-26 baseline. Cost: one GraphQL search page per 40 merges (about 5 points each); a run
within 5 minutes of the last recorded window re-prints it with `(cached)` and makes no call, so this
tick and the merge-drain tick share one read. When the landing scorecard has to be regenerated, this
measurement runs first, because the scorecard producer refuses a record older than 15 minutes and this
command is what appends one; the block reuses that run's line. It never changes the VERDICT. When it cannot run the
line says `landing-metrics: unavailable: <reason>` (no clone, a clone that predates
ops_tooling_pkg#26, a timeout after 300 seconds); `--no-landing` skips it and the delegation-share line, outside a tick only. Run it alone for the
full summary (deltas, trailing six hours, mechanisms) or the unattributed list:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_landing_metrics.py"                  # full summary
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_landing_metrics.py" --list-unattributed
```

**Shared-red ownership and the fixer line: the landing controller's own files (OMN-20418).** Read-only,
from `LANDING_STATE_DIR` (else `~/.local/state/omni/landing`; `--landing-state-dir` moves it). The reader
treats absence as "no lease" and is written against the shape the controller writes once the cause-lease
work lands:

- `state.json` `leases`: a **cause lease** carries `cause` (`cause:<owner>/<repo>:<12 hex>`) and no `pr`,
  with `repo`, `checks` (check names) and `members` (`repo#n`). It is unreleased while it is in `leases`
  and not `revoked` with a confirmed release (`released_at`); its owner reads `landing-L<lease_id>`. A
  lease matches a shared red by repo plus check name in `checks`.
- `ticks.jsonl`, last two lines: a `cause_leases` cell, a list of cause keys or `{cause, repo, checks}`
  objects. A missing cell reads as no lease. An unreadable or missing `state.json` or `ticks.jsonl` prints
  `ownership unread`, never OWNED.
- `cost.jsonl`, one row per released lease: `lease_id`, `kind` (`pr`|`cause`), `repo`, `engine`, `host`,
  `worker_minutes`, `total_cost_usd`, `usage_source` (`MEASURED`|`UNKNOWN`), `cost_basis`, `dispatched_at`,
  `released_at`.
- `decisions.jsonl`: the controller's own merges (`kind=merge`, `outcome=merged`, `subject=<repo>#<n>`).

**Trend.** `$XDG_STATE_HOME/omni/queue-status/last.json` (`~/.local/state/...` when unset), outside
every repository: the last run's numbers plus the last 24 runs. `--state-dir` moves it.

## GitHub-call budget

The script never calls GitHub search. Every direct `gh` subprocess that remains (currently the
Actions-variable reads, plus any calls made by the embedded merge pulse) passes through `run()` and
increments one thread-safe `GhBudget`. The default is 12 and `ONEX_QS_GH_BUDGET` overrides it. The
cost line always prints `search=0`; exceeding the budget prints `OVER BUDGET` and adds the DEGRADED
reason `gh call budget exceeded (<n> of <B>)`. The existing `reads:` line reports the same counted
GitHub total.

## Automation liveness (OMN-20810)

Two informational lines in the block, before `adopt`; neither moves the VERDICT. Both come from
`scripts/queue_status.py` (the "automation liveness and Routines" section); `--no-liveness` skips them.

```
liveness processes=N <verdict>=n ... | oldest open episode: <process_id> <verdict> for <h>h<mm>m | top: <process_id> <verdict> <age>, ... (three at most)
liveness UNKNOWN: <error>: <detail>
routines recurring=N undeclared=K[: <id>, ...]
routines UNKNOWN: <why>
```

**The liveness line** is one `onex node node_projection_read_effect` read of
`onex.snapshot.projection.automation-liveness.v1` (the projection `node_projection_automation_liveness`
keeps, one row per declared process, limit 500), never HTTP. It counts the rows by `verdict` (failing
verdicts first, then `healthy`, `no_demand`, `not_ready`, then `unreported` for a declared process that
never emitted), names the oldest row with an `open_episode_id`, and lists the three failing rows that
have been in their verdict longest. A read that does not return a page prints `liveness UNKNOWN:` with
the node's own error and detail (for example `projection_binding_unconfigured` on a runtime with no
projection read binding), and a page with no rows is UNKNOWN too: an unreadable projection is never a
healthy count. The node call is the command `ONEX_BIN` names, else `$registry_root/omnibase_infra/scripts/onex`.

**The routines line.** A script cannot list Routines (the API needs a Claude session's sign-in), so
the session lists them: `/omni:session-start` unit 5 runs `RemoteTrigger` `action=list` and writes the
JSON to `$XDG_STATE_HOME/omni/queue-status/routines.json` (`--routines-json` names another file). Each
enabled Routine with a cron schedule must carry `routine=<process_id>` in its text, naming a `routine`
entry of the automation-liveness overlay (`AUTOMATION_LIVENESS_OVERLAY_PATH`, else ops_tooling_pkg's
`src/ops_tooling_pkg/overlays/automation_liveness_overlay.yaml`; the projection's process ids stand
in when the overlay is unreadable). One with no entry, such as a Routine made by hand in the web
interface, raises through `alert_channel_alarm` (source `queue-status`), once per 24 hours per Routine
(`routine_alarms.json` beside the trend file). A missing listing, or one older than 36 hours, prints
`routines UNKNOWN:` with the fix and raises nothing. The creation side is the PreToolUse guard
`queue_status.py --routine-guard` (registered in `plugins/omni/hooks/hooks.json`), which refuses `RemoteTrigger` create/update of a recurring
Routine, and a durable recurring `CronCreate`, that names no overlay entry.

## The exception queue (OMN-17427)

Operator 2026-10-18, verbatim: "need to make the process as mechanical as possible, where you only have to rule on
the exceptions instead of the rule." Two mechanisms, in `node_exception_queue_effect`, reached through this script:

- **(5) The exception queue is the only path to a human or the orchestrator.** A detector or actor resolves its case
  in code, or it emits one typed row, and nothing else of it reaches the operator or the orchestrator:

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/scripts/queue_status.py" --exception emit --class <kebab-class> --key <case> \
    --source <detector or actor> --evidence <what it read> --tried <what it did> --proposed-fix <what would resolve it> \
    [--decision] [--repo <repo>] [--ticket <OMN-n>] [--parent <orchestrator lane>]
  ```

  A row missing its key, source, evidence, what it tried or its proposed fix is refused (exit 3) and not queued. The
  same open case (class and key) reported again is one row. `--exception list --audience operator` prints only the
  rows marked `--decision`, the only ones the operator rules on; `--exception list` (audience orchestrator) prints every
  other open row for the orchestrator to drain; `--exception resolve --id <id> --by <lane> --how <what>` closes one.
  Every queue-status read prints the `exceptions` line and adds a DEGRADED reason and its action for open decision
  rows, open exception rows and unmechanized classes.
- **(6) A second occurrence becomes code.** When a class's second case is emitted, the queue writes a mechanize brief
  (every row of the class, verbatim) under `<state dir>/briefs/` and starts lane `mechanize-<class>` detached through
  the remote-lane runner: a detector, an actor that resolves the class in code, and a scenario in the friction replay
  suite. One lane per class; a refused start is recorded and the class's next emit retries it, and until then the
  read prints `MISSING mechanize:<class>`.

The queue lives in `$ONEX_STATE_DIR/exception-queue/` (else `$registry_root/.onex_state/exception-queue/`);
`ONEX_EXCEPTION_RUNNER` names another runner and `--no-dispatch` starts none. Test:
`tests/test_exception_queue_node.py`.

## Guardrails

- Read only. No merge, arm, rerun, ready flip, label change, ledger row or dispatch comes from this
  skill. The one outbound write is the undeclared-Routine alarm above. The orchestrator acts on NEXT through the skill it names.
- Never report a number from an exit-3 run, and never read "no open PRs" or "nothing dispatchable"
  from it (merge-drain step 7).
- Never append `2>/dev/null` to the command (CLAUDE.md rule 16). The script never swallows a failed
  read.
- In PR bodies and commit messages refer to held PRs by class, never with the hold label literal
  (CLAUDE.md rule 15).

## Common rationalizations

Each row is an excuse that skipped a step this tick exists to force, with the failure it caused. The
rows come from the night of 2026-10-17 and the FRICTION rows of 2026-10-12 to 2026-10-17.

| Excuse | Why it is wrong | What to do instead |
| -- | -- | -- |
| "The VERDICT is OK, so the queue is healthy." | The verdict is only as fresh as its inputs. FRICTION 2026-10-17T11:55:45Z lane=silent-failure-alarm: the trend file was 50 minutes old while the controller was live, and FRICTION 2026-10-17T10:15:39Z: this tick itself exited nonzero on 3 runs in a row, unseen. | Read the read times and the exit code before the verdict. An OK printed from stale inputs is a DEGRADED you have not noticed yet. |
| "Merges are slow because the Mac is under memory pressure." | On 2026-10-17 a session gave the operator that cause without measuring while 61 GB was free. A cause stated without a number sends the operator after the wrong problem. | Put the reading beside the claim: load per core and free memory from this turn, or the stall read from the hook-event section. If you have no reading, say the cause is unmeasured. |
| "The open count is flat, so the fleet is merging." | A fleet total hides a stopped repository: one repository went 4h22m with no merge while the fleet merged more than 5 an hour (session-start Known friction). | Read the per-repository merges in both windows and name every repository with none. |
| "The ruling has a ticket, so it is mechanized." | The ruling section lists rulings with no mechanism built and wired, and a ticket alone is pending work. | Count a ruling mechanized only when the mechanism's pull request is merged and its check or hook is wired and has a test. |
| "The line says the ruling is unmechanized, so I dispatch a lane to build it." | FRICTION 2026-10-12T08:33:53Z lane=tick-fill4g-1d5b: about a dozen listed rulings already had merged pull requests that no ruling row linked, so a fill lane found 3 real targets after 25 Linear reads. FRICTION 2026-10-12T08:50:00Z lane=tick-fill3h-1d5b: the wiring check rejected a hook registered by absolute path, so wired mechanisms read as unwired. | Before dispatching, look up the merged pull request for the ticket. If one exists, fix the class (the missing link or the wiring check), not the one row. |
| "It merged, so it is running." | A merge to `main` ships a plugin change only when the version bump lands and the installed copy matches. FRICTION 2026-10-13T05:25:27Z lane=adopt-merged: 14 merged fixes had not run for over an hour. | After a merge, read the installed version or the adopt-merged report. Say "merged" for a merge and "running" only for a reading. |
| "Most lanes ended handed-off, so landing is on track." | Handed-off means the pull request waits on the controller. The landing measurement line counts how merges landed and how lanes ended; a handed-off lane is not a merge. | Read merges per hour by kind, not lane outcomes. A rising handed-off count with falling merges is the signal. |
| "NEXT names a lane, but I will ask the operator first." | The NEXT line is the action. The operator ruled that nothing waits on them (RULING 2026-10-16T03:24:42Z lane=orchestrator-bb1a), and the question guard refuses a decision the ledger already answers. | Take the NEXT action. Search the ledger rulings before any question, and cite the row you found. |
| "The tick is noise, I will fix this one blocker by hand." | Fixing one pull request by hand leaves the class that blocked it; the same blocker class returns on the next tick. | Take the blocker class from the table, dispatch a lane for the class, and let the controller land the instances. |

## Red flags

- A VERDICT line read without the age of the trend file, the watcher state or the clone history beside it.
- A tick job whose last exit was nonzero, or a trend file older than one tick interval.
- Merges per two hours falling while open pull requests rise (the 2026-09-26 pattern: 44, 27, 25 merges while open went 123 to 130, noticed by the operator and not by a report).
- A cause for a slowdown (memory, disk, quota, a host) with no measurement printed this turn.
- A repository with zero merges in both windows that the verdict does not name.
- A ruling counted mechanized from a ticket id alone, or counted unmechanized without a search for its merged pull request.
- A merge reported as live with no installed-version reading.
- A NEXT line you answered with a question to the operator.

## Known friction (from prior runs)

- **"Off change control" was inferred from companion minting.** The operator was told several repositories
  were off because they had stopped minting companion PRs; a full read at 13:10Z on 2026-10-14 found only
  omnibase_compat, omnigemini and docs_repo off. The `occ refs` line now counts live references by
  kind and OCC-named required contexts per repository and prints `off` only at zero everywhere; mentions (docs,
  comments, docstrings, bare name strings, test fixtures) print beside the live counts and never block `off`;
  this skill's text defines "off change control" as that line. → OMN-20074, lanes omn20074-occm and omn20074-occ2

- **Per-PR CLAIMs stood a shared red down.** A shared red read OWNED as soon as every one of its PRs had
  a live per-PR lane, so no lane ever worked the one cause they shared and the red sat. A shared red is
  now owned only by a CLAIM that names the cause or by an unreleased controller cause lease, and an
  UNOWNED one names exactly one cause lane. → OMN-20418 (operator ruling 2026-10-03T20:46:24Z)

- **A shared red read as owned while no CLAIM named it.** The 2026-09-29 orchestrator handoff records
  the Hostile Review Gate red, shared by four omnibase_infra PRs, marked owned when no live CLAIM
  named the check or any of those PRs, so no fix lane was dispatched and the PRs sat. The pulse's
  armed-red-stall finding now carries `ownership:` per context through `shared_red_owners`, which
  reads CLAIMs through drain_map's own row reader and the 45-minute liveness rule. → OMN-19852

- **A gate with no cause of its own was named as an unowned cause lane.** On 2026-10-15 queue-status
  twice named Coverage Sweep Gate on omnimarket UNOWNED while the checks it needs were owned: the gate
  refuses by design (`coverage census refused: detect-changes=skipped`) behind the failed
  occ-preflight, and the lane sent at the gate was wasted. merge_pulse now reads the workflow's
  `needs:` graph from the canonical clone and the PR's check-run conclusions; a red behind a failed or
  skipped need is listed as `inherited`, takes the root's owners in `shared_red_owners`, and the cause
  lane is named for the root. A red with no failed upstream stays UNOWNED. → OMN-20418

- **A met milestone read red for hours and a fleet-wide BLOCKER MSG sat unread 31 minutes, and
  nothing in this block said so.** The M4 board (infra_repo tools/beta_board) went red on C13
  and C29 around 2026-09-27 16:40Z and was found only when the operator asked; the same tick's
  merge-drain read only `to=operator` MSG rows, so a BLOCKER row addressed to the orchestrator lane
  went unanswered. This block now carries `milestone` (any red acceptance-criteria row on the
  board's latest publish) and `inbox` (any unACKed MSG naming BLOCKER addressed to the orchestrator
  lane), both DEGRADED reasons. → OMN-17427, lane regression-watch-83b, 2026-09-28


Read this before the first run. Record new friction with `/omni:friction-record` and add a line here
in the same PR.

- **A pinned rung that routing never picks printed as a quiet expected rung.** At 2026-10-02T08:32:37Z
  this block printed `DEGRADED reason=delegation gemini/gemini-2.5-flash (cheap_cloud rung
  cloud-gemini-pro) had 0 events in 120m while N lanes ran` for a rung the contract marks
  `explicit_pin_only`, which ordinary routing excludes; a pinned smoke answered pong at 08:34Z. The
  expected-rung list now skips pin-only rungs and prints each with its smoke evidence. → lane
  pinonly-rung-20341 2026-10-02, OMN-20341
- **The orchestrator tick's read ran past the 90 s deadline.** On 2026-10-01 queue-status printed
  INCOMPLETE (merge pulse, then hook events) at Mac load1 about 9. A profile showed the ledger
  rechecks calling drain_map's `ledger_owners` once per PR with no precomputed owner context, so
  `handed_off` re-scanned every ledger row 34 times (21.9 s). `owner_context` now computes it once per
  recheck (7.8 s). The merge pulse's lab pool status read (about 22 s) is the next largest step.
  → OMN-19814, lane qdiag-202610010430
- **The 90 s deadline passed in the merge pulse at load1 about 15 because every slow read waited its
  turn.** On 2026-10-14 the block printed `DEGRADED reason=queue-status deadline 90s exceeded in merge
  pulse`; a rerun with 100 s completed. A per-phase profile on the 24-core Mac (load1 11 to 14, no map
  run, `--no-write`) put the milestone board read at about 25 s, the delegation share at about 10 s, the
  landing measurement at about 16 s and the pulse's own `collect` at about 4 s, all one after another
  (total 65 to 74 s; the pool status read alone took 3 s that day, since the excluded host's 30 s ssh
  wait is gone). The milestone board, the delegation share and the pool status read read nothing an
  earlier step writes, so `run_main` now starts them on daemon threads before its first step and collects
  each where it used to run (`start_prefetches`; the pulse takes the pool read through
  `args.pool_prefetch`). Same profile after: 35 to 38 s. No read was dropped, and a read that raises still
  raises at its old place. The landing measurement stays in order on purpose (it appends the record the
  scorecard read next), and at about 16 s it is now the largest step. A 3 s pool read on the Mac
  needs an interpreter that can import `omnibase_infra`; the system `python3` there cannot, so the pulse
  reads `lab free=?` until the driver is run by `uv run --project <omnibase_infra>`. → OMN-19814, lane
  omn19814-qspd 2026-10-14

- **The tick missed its deadline in a different lab read each run.** At 2026-10-18T18:12:32Z the tick printed
  `INCOMPLETE ... exceeded in step delegation`, and at 18:14:41Z with `--deadline 110` `... in step merge pulse`, with the
  launching host idle enough. The three lab-side reads each waited longer than the whole deadline (delegation health
  60 s, hook events 120 s, pool status 100 s) and ran one after the other, with the ruling scan (30 s) and the `occ refs`
  step before them, so the step that held the clock at 90 s changed with the lab host's answer time. Profile on h907
  with a fake lab `ssh` that answers after 45 s (the lab runtime host refuses h907's key, so the live figure is not
  readable there): 184 s in all, the delegation read 45 s and the hook-event read 45 s back to back, the default deadline
  firing `in step delegation`; after the change 51 to 65 s, both reads waiting together. `run_main` now starts the
  delegation health block, the hook-event read and the ruling scan on daemon threads with the other prefetches,
  gives each lab read `--lab-read-budget` (40% of `--deadline`, 5 to 40 s) and prints `no answer within Ns (unread)` as a
  DEGRADED reason when a host does not answer, and collects the delegation-share line only until 90% of the
  deadline. The pool driver's own per-host 30 s probe lives in omnibase_infra and is unchanged: a host that hangs there
  costs 30 s inside the pool read, which runs beside every other step. → OMN-19814, lane queue-status-deadline-1822
  2026-10-18

- **The `occ refs` step overran its own budget and the deadline fired in it.** At 2026-10-18T21:07:09Z the tick printed
  `INCOMPLETE ... deadline=90s exceeded in step occ refs` (plugin 0.4.437, which carried the lab-read budgets), and a
  rerun on h907 (load1 12 to 22, 24 cores) did the same at 90 s. The budget was checked only when a git call started
  (`occ_run`), and a per-phase profile of the step put about 75% of it in CPU-bound Python between git calls
  (`occ_python_line_states`: `ast.parse`, `ast.walk` and `tokenize` over 676 matched `.py` files in 23 reads; 8 s of 11 s
  under cProfile, 190 git calls 2.3 s), which ran beside the milestone and delegation prefetch threads on one GIL, so
  under load nothing stopped it. The budget was also a flat quarter of the deadline from wherever the step started (38
  to 40 s into the tick: clone sync 15 s, ruling prefetch wait 8 to 9 s), not what was left. Profile before, h907, five
  ticks: step 14 to 17 s healthy; one run 90 s INCOMPLETE. After: the parse loops and the clone loop check the budget
  (`occ_check_budget`), and `node_tick_read_budget_compute` caps the budget at 65% of the deadline minus the time
  already spent (1 s floor). Same profile: healthy 14 s, loaded 22.5 s then `occ     refs unread (step budget ...)`, the
  tick finishing at 55 to 66 s. At load1 39 the earlier steps took 44 to 49 s, the step got the 14 to 19 s that were left
  and ended on them, and a second run was cut off `in step delegation` instead: the milestone, delegation and landing steps
  after it are the next largest. The step is report-only; making the parse cheaper (a cache by blob id) is not done.
  → OMN-19814, lane queue-status-occ-refs-budget-2110 2026-10-18

- **Each fix budgeted only the step that had just overrun, so the next step overran.** The 2026-10-18 tick was
  INCOMPLETE in delegation (18:12Z), the merge pulse (18:14Z to 20:37Z, #961), occ refs (21:07Z to 22:37Z, #973) and
  then the drain map (23:07Z, canonical clone at main with #973), where the step consumed the whole 90 s although this
  skill says a needed `drain_map.py` run continues detached after its budget: the 60 s run wait was the only bound, and
  the walk of the reports root before it (`newest_map` over tens of thousands of files) and the ledger, inbox, milestone
  and landing steps after it had none; the host's load1 was about 20 on 24 cores. Before: 18 steps, 4 with a budget of their own
  (the three lab reads and occ refs) and the drain map's wait. Now `tick_step` gives every step its weighted share of the
  usable time left, cancels it on the budget and prints `step    <name> unread (step budget ...)`; the table-driven test
  makes each step slow in turn. The deadline's `INCOMPLETE` stays as the backstop for the local compute between steps.
  → OMN-19814, lane queue-status-every-step-budgeted 2026-10-18

- **The change-control batch switch was never flipped, and nothing reported it.** omnimarket#2940
  shipped per-ticket companion batching behind a repository variable that defaulted to off; it stayed
  unset for about 23 hours while every PR minted its own companion. Batching is now the code default
  and this block's `occ` line reports DEGRADED when companions outnumber batch windows. → OMN-16336,
  lane occ-batch-default-83, 2026-09-27

- **A count at its result cap was reported as a measurement.** A merged-PR query returned exactly
  200 because its second merged-at bound was ignored, and the prior window read as flat. The script
  now proves the bound with a union read and refuses any count at a cap (exit 3). → dispatch to lane
  queue-status-skill-83 2026-09-26, OMN-19814
- **Throughput fell for four hours and nobody saw it.** Merges went 44 to 27 to 25 per two hours
  while open PRs rose 123 to 130; the drain's reports counted per-run work only. This skill's trend
  rules are the answer. → dispatch to lane queue-status-skill-83 2026-09-26, OMN-19814
- **Process rulings were recorded and forgotten.** Nothing listed the rulings whose mechanism was
  never built; the verdict now does. → dispatch to lane ruling-mechanism-check-83 2026-09-27,
  OMN-19854
- **Commit dates misplace merge-queue merges by tens of minutes.** The first prototype counted
  omnibase_infra 3/3 against the API's 5/1; landing time now comes from the reflog. → OMN-19814
  build, 2026-09-26T21:2xZ
- **A reused drain map named PRs the live drain had already CLAIMed.** The map can be reused up to
  `--map-max-age-minutes` (30m default) old; five PRs it still listed as dispatchable had all been
  CLAIMed by the live drain's sub-lanes between the map's read and this tick's report, and five
  pr-land lanes were dispatched for nothing. `recheck_dispatchable` now re-reads the ledger at read
  time through drain_map.py's own row reader and owner-match logic and drops any PR a live CLAIM
  now owns, printing the count as already-claimed; an all-dropped result files no DEGRADED reason
  for it. → lane qs-stale-map-fix-83, OMN-19814

## The hook-event reads (OMN-19513)

`scripts/hook_events.py` reads `private_repo.claude_hook_events`, the projection of every Claude
Code hook event (omnimarket's `node_projection_claude_hook_events`), over ssh and `docker exec psql`
in a READ ONLY transaction. Which lane, host and database comes from the delegation-health overlay
(the same one `queue_status.py` reads for lab delegation); `HOOK_EVENTS_DATABASE` selects another
database (a scratch or replay one), and `--hook-events-jsonl` or `HOOK_EVENTS_JSONL` replays a saved
read. The read costs one ssh call and about 3 MB for six hours of events.

The folds are pure functions of the event rows; `hook_events.py` run alone prints the same three blocks.

- **trace** (last 2 hours): per agent, completed tool calls, failures, refusals (a `PermissionDenied`
  call counts once, as refused), and retries (a call whose tool and input digest match an earlier call
  of the same agent that failed). Repeats are found by digest: two lanes sharing five or more rare call
  digests (a digest seen in more than four lanes is boilerplate) are doing the same work, two lanes
  ending on the same non-empty final-message digest stopped on the same thing, and a main thread
  submitting the same prompt digest twice is asking twice. Claims-vs-events lists TERMINAL claims the
  events do not bear out: a work outcome (merged, done, pass, proved) after three completed calls or
  fewer in the whole agent, a finish after the last two calls were failed or refused, work continuing
  after the TERMINAL, and a CLAIM with no TERMINAL whose agent has been silent 30 minutes.
- **stall** (last 30 minutes, read when merges 30m is 0, or with `--hook-stall always`): each active
  agent is `refused` (a refused call in the window), `polling` (the same call three times), `waiting`
  (half its span inside calls of 60 seconds or more), `quiet` (half its span with no call running) or
  `working`.
- **models** (last 6 hours): per model, lanes started, finished against blocked against still open (from
  each lane's TERMINAL outcome), completed calls per lane and failure-plus-refusal rate (from the
  events, for the lanes joined to an agent), and handed-off PRs that a later `action=fix` CLAIM took
  back.

**What the events cannot say, measured 2026-09-28.** Content is restricted: a command, a prompt and an
assistant message are digests only, so "same work" is a digest comparison and a `gh pr merge` inside a
Bash call cannot be seen. A workflow lane is an agent that shares its parent's `session_id` and carries no
lane name, so a lane is named by joining its ledger rows to the agent whose short Bash call was running
at each row's stamp (a CLAIM the dispatcher wrote is scored by when the agent began instead; agents are
joined in passes so a joined agent leaves every other lane's candidates). About 60 percent of lanes join;
the rest print as `agent:<id>` and stay out of every claims-vs-events finding, which needs a join of four
points or more. A subagent's model is the projection's `model` column (the harness sidecar's `model`,
carried as `lineage.agent_model`), read as `coalesce(model, payload->>'model')`. The sidecar is not
readable when `SubagentStart` fires, so that row has no model (0 of 23580 rows since 2026-09-26; for each of 163 agents in the 6 hours to
2026-10-14T12:50Z the first event with a model was a `PreToolUse`) while the agent's later events do (2305 of 2522 subagent `PreToolUse` rows), so a
lane joined to its agent is labelled `events`. A lane whose events carry none (a sidecar the producer
cannot validate, or no joined agent) keeps its own CLAIM cell, labelled self-reported. `SubagentStop`
reached the table for 2 of 501 agents when measured 2026-09-28, so an agent's end is its last event.

Every zero is read against a control: an empty table is untrusted, a stale newest row is a reason, and
`repeats: none` and `claims-vs-events: none` are printed as such, never dropped.
