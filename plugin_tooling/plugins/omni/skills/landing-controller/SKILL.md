---
name: landing-controller
description: The landing controller, a launchd tick every 300 s with no model in its decision. Each tick reads one snapshot (the PR watcher, one batched live read, the ledger, the process table, worker result files), decides with the pinned landing decision node (the S1 to S20 tested decide_landing), writes its state first, then merges pinned to the head, reruns once per head, updates branches, and dispatches, reaps and kills detached fix workers under leases keyed repo#pr. Use to install it, read its status, or check why a tick refused. Acting is its only mode (no observe-only, RULING 2026-09-29T12:02:35Z); it replaced the hand-run merge drain when gate G-ACT passed on 2026-09-29T08:11:25Z.
ticket: OMN-19998
---

# Landing controller

The plan is docs_repo `beta/plans/2026-09-27-merge-drain-that-merges-plan.md`
(sections 0, T3, T5). The controller is `../merge-drain/scripts/landing_controller.py`; the decision
is omnimarket's `node_pr_landing_decision_compute` at the commit in
`../merge-drain/landing_decision.pin.json`, run through `landing_decide_bridge.py` in the decision
runtime the installer builds (a pydantic-only venv on the brew interpreter, Operating Rule 11).

The red rules are the node's too (OMN-20745): the red class of a head, the cancelled check copies, the change-control
cascade, the reviewer pool, the fired order edge, the companion wait, the stale CI Summary and the pending required
contexts are pure handlers of omnimarket's `node_pr_lifecycle_triage_compute`, at the same pinned commit. The tick
calls them through `landing_decide_bridge.py --rules`, one process per tick (`RulesClient`); `landing_facts.py` holds
none of them, and `grep -n "def classify_red" landing_facts.py` finds nothing. A rule change is an omnimarket change
and a repin.

Superseded CI runs are cancelled by a node too (OMN-17427): each tick, after the autobind re-drives, the controller
starts omnimarket's `node_superseded_run_cancel_effect` through `onex node` once per repository holding an open PR
(`superseded_run_sweeps`, `ONEX_BIN` as for the throughput read). The node reads the repository's queued and in-progress
run list and its merge queue and decides from those two reads alone: a pull_request run whose head is not the head of the
PR's newest run in the list, and a merge_group run whose commit is no longer a queue entry. The request carries the
repository and nothing else, so no watcher snapshot can make a run on the current head look stale. Each cancel is one
`superseded_run_cancel` outcome (repo, run id, reason); a sweep that did not run is one `superseded_run_sweep` error
outcome and never stops the tick. The sweep runs detached from the tick (OMN-19998): one `onex node` start took
7-17 s on the controller host at load 25, so 21 runs cost a tick 419 s. The tick records the last finished sweep's
outcomes (`superseded-sweep-result.json`) once and, when no sweep is running (`superseded-sweep.pid`), writes its
repositories and heads to `superseded-sweep-request.json` and starts `landing_controller.py superseded-sweep`.
The node's contract secret `GITHUB_TOKEN` comes from the environment or else the gh login (`gh auth token`), passed to
the node's process only. A node run that fails (exit code, timeout, no `cancelled` list) stops the sweep, so one
failing repository costs at most one timeout; the error keeps the receipt's reason and the head of stderr, and a
`skipped` outcome names the repositories not tried. A typed `read_error` for one repository does not stop it. Up to
`LANDING_SUPERSEDED_SWEEP_WORKERS` (default 2) runs are in flight at once and `LANDING_SUPERSEDED_SWEEP_BUDGET_S`
(default 900) bounds the sweep's wall time: each run's timeout is what is left of it, and a run it cuts short is
deferred, not failed. The watcher snapshot only orders the repositories, never what is cancelled: a repository whose
open PR heads changed since its last sweep goes first, then the one swept longest ago. `superseded-sweep.json` records
each sweep and each repository's last sweep, and a sweep started right after one that failed for every repository it
tried is skipped with that reason.

The criteria of a ticket are checked before a merge, by a node (OMN-21676). The hosted `repo-evidence / dod-verify` job
holds no Linear credential and no repository secret, so it records the comparison of a contract's accepted criteria with
the live ticket as delegated (`criteria_delegated` on its verdict) and compares nothing. Before the controller merges a
head it starts omnimarket's `node_dod_criteria_check_effect` through `onex node` (`node_landing_criteria_hold_effect`),
asked for the PR and the exact head. The node reads the PR, the `contracts/<ticket>.yaml` of each ticket the title cites
at that head and the live ticket through the ticketing project tracker, with the Linear credential in the lab key store.
Real drift holds the merge as a deferred `merge` row whose detail names the criterion, and so does anything unreadable
(the PR, the contract, the ticket, the credential) and a node run that fails, times out, answers for another head or
returns no verdict: an unmeasured criterion is never a passed one. The controller reads no Linear credential and holds no
drift rule.

Drift the merge base already carries holds no merge (OMN-19998, the liveness precheck's rule, OMN-22725).
omnibase_infra#5814 sat green and CLEAN for 764 minutes, deferred every tick on `AC49 deleted from the ticket`, while AC49
and the item claiming it were in `contracts/OMN-19998.yaml` at its merge base and on dev's tip: the PR only added entries
binding AC1, so neither a change to it nor an update-branch could clear the hold. `merge_criteria_hold` (in
`node_landing_shared_base_effect`) takes the node's drift entries from its verdict and, with the canonical clone, reads each
drifted ticket's contract at the merge base and at the head. When the head keeps every merge-base entry unchanged and adds
nothing that names a drifted label or item, the merge goes and one `criteria_drift_inherited` row (outcome `inherited`)
names the base's drift, its merge base and its items, for the base contract to retire. Every other hold stands exactly as
the node gave it: an unreadable ticket, a check that did not run, a verdict with no drift entries, a changed or removed
contract entry, an added binding of the drifted label, a contract new in the PR, and any read that fails (no clone, no
tip, no merge base, no YAML reader).

## Install and status

The installer is ops_tooling_pkg `launchd/landing-controller/install.sh`. There is no mode to pick:
the controller acts on every tick, or refuses the tick (the table below). Installing without G-ACT
receipts is refused, never downgraded to a watching install.

```bash
bash "$OPS_TOOLING_PKG/launchd/landing-controller/install.sh" --g-act-dir <dir>
bash "$OPS_TOOLING_PKG/launchd/landing-controller/install.sh" --status
```

The installer writes `~/.local/state/omni/landing/g-act.json` only when
`../merge-drain/scripts/landing_g_act.py verify` accepts the three G-ACT receipts in `<dir>`: the
TLC verdict on `LandingController.tla` from a lab host, the scenario and replay JUnit run, and the
`tests/test_landing_controller.py` JUnit run, each bound to the pinned decision commit and the
controller's sha256. A consent string alone never opens acting mode. Build a receipt with
`landing_g_act.py build tlc|pytest ...` (see its `--help`).

```bash
env -u PYTHONPATH /opt/homebrew/bin/python3.13 ~/.omninode/landing-controller/skills/merge-drain/scripts/landing_controller.py status
```

### Refresh from main on every tick (OMN-20864, OMN-19998)

While `~/.omninode/landing-controller/landing_install.json` is present, every tick first starts
`landing_g_act.refresh_install` detached (`landing_controller.py refresh-install`, pid in `refresh-install.pid`,
output in `refresh-install.log`) when none is running, and ticks at once on its verified copy; the next start runs
what the refresh installs. It works only from `origin/main` of the canonical plugin-tooling-pkg clone, never
from a branch. Main's tip is the PR watcher's branch tip for `plugin-tooling-pkg@main` (the clone's own, kept current by
the clone sync) when the state read it inside its 8-minute bound and the clone holds the commit; only otherwise does the
refresh fetch main from GitHub, which goes through the gh credential helper (OMN-17427). When the files the installer copies changed on main, it builds the scenario, replay and controller
receipts on the lab (`prove-install`), runs `install.sh --refresh-install`, reads the result back and records it in
`installed-revision.json`. The fetch and the lab proof hold `install.lock` only; the install itself waits for
`tick.lock` (up to `REFRESH_TICK_WAIT_S`, 1500 s) and writes `install-pending` meanwhile, which makes a tick that
takes the lock give it up at once (`INSTALL-PENDING`) (OMN-19998). The refresh used to run in the tick's process,
under `tick.lock` and before the heartbeat: after plugin-tooling-pkg#863 changed an installed file on 2026-10-17,
the lab proof's 1800 s timeout left no tick receipt from 16:36:27Z to 17:21:29Z, and the watchdog's kickstart
restarted the same proof. Never move `landing_install.json` aside: that left the controller off main until someone
put the file back. A branch install runs the ops_tooling_pkg installer with `--branch-hours N` (1 to 6), which
records `branch_until` and `branch_source` in the file. Until `branch_until` each refresh prints (in its log)
`CONTROLLER-BRANCH-HELD until=... source=...` and keeps the branch copy without a fetch or lab run; the first tick
after it converges to main and the installer writes a record with no hold. A `branch_until` that does not parse is
logged as an install failure, never a silent hold (OMN-19998).

- **TLC receipt.** The tick takes the TLC receipt for main's decision pin from `g-act/`, or else from
  `g-act-<pin[:8]>/` beside it in the state dir (where a TLC run for a new pin writes its receipt). With neither,
  it refuses before the lab run with `CONTROLLER-INSTALL-REFUSED: TLC-RECEIPT-MISSING` on stderr and a
  `class: tlc-receipt-missing` line in `install-failures.jsonl`. It also writes one ledger `FRICTION` row per pin
  (`class=install-tlc-missing`, deduplicated through `install-friction.json`) and keeps its verified copy.
- **Backup.** Before the installer runs, the tick copies `skills/`, `scripts/`, `landing_runtime.json`, `g-act/`
  and `g-act.json` to `refresh-backups/<stamp>-<commit>-*/` and keeps the newest five. If the install or its
  readback fails, the tick restores that backup and logs `CONTROLLER-INSTALL-FAILED ... restored the previous
  install`. `installed-revision.json` names the backup.

## External blockers wait at the judged head (OMN-17427)

Only an operator_decision, production_gate or hold_row result that names its person holds a head (RULING
2026-10-16T03:58:15Z: only a draft or a grant holds a PR; RULING 2026-10-16T03:24:42Z: nothing waits on a person); there
is no "operator" default. An upstream_open result keeps its own park, lifted when the upstream PR merges or closes, and a
collaborator result keeps the collaborator path. An upstream_open hold written before this narrowing is released into
that park on the first tick (external_blocker.released_to=park), keeping the node record's fingerprint.
Such a result, from a PR worker or a shared-cause worker, records needs_person in the existing
sidecar head_escalation entry with external_blocker carrying its source lease, blocker ref and kind. The ordinary
worker path and the escalation path both respect it. The queue-status held line and throughput NOTE held lines
show the PR, person and reason. A base movement or elapsed retry window does not clear it. A new PR head, a closed
upstream blocker or a re-read cleared cause releases it. A person can release that entry under tick.lock by setting
external_blocker.released to true; the source lease remains as a tombstone so its old result cannot reinstall the hold.
Existing workers finish under their original leases: results are recorded, the normal exit grace and deadline bound
any lingering processes, and confirmed termination releases their slots. No manual revocation is needed.

## A blocker the standing rulings already answer does not name the operator (OMN-19998)

The controller marks a PR `needs_person:<who>` from the person a worker's external_blocker result names, and workers name
`operator` for gates a standing ruling already routes (the no-growth freeze in a frozen repository, a pull request waiting on a
release, a runner or reviewer outage, an external repository's check). `external_hold_memory` now passes the person, reason and
refs of an operator-named hold to `node_landing_escalation_route_compute`, which matches them, in order, against the classes of the
`landing_escalation_routing` overlay and, for the first class that also has a route, writes that route's owner kind as the person
(`port-lane`, `release-lane`, `runner-owner`, `reviewer-owner`, `external-owner`) and `routed {class, owner_kind, ruling, named}` in the
`head_escalation` entry. A reason that matches no class, or a class with no route, keeps the operator: only a class with no ruling
and no owner reaches the operator. A hold written before the table is routed on the next tick. An overlay that cannot be read routes
nothing and each operator-named entry carries `routing_unread` with the reason. Classes, routes and rulings are overlay values;
adding a class is an overlay edit.

## The next tick starts one interval after this one started (OMN-19998)

launchd re-arms `StartInterval` only when the job exits, so every tick that exited was followed by a full 300 s of idle:
ticks 2823 to 2853 (2026-10-16T18:28Z to 2026-10-17T00:17Z) ran 211 to 926 s (p50 377 s) and each next tick started 302 to
314 s after the last one ended, a period of p50 685 s and p90 872 s. On 2026-11-05 ticks 7059 to 7084 ran 75 to 118 s and
took a period of 381 to 415 s for the same reason. A tick that returned 0 now waits out what is left of `TICK_INTERVAL_S`
(300), holding no lock and no alarm, and execs the next tick in the same process (`chain_wait_s`, stdout `TICK-CHAINED
tick_s=... chain_s=... wait_s=...`), with the install refresh first as on any start, while the wait and one more tick of
the same length end inside `TICK_CHAIN_WALL_S` (1500) of the chain's launchd start. The bound keeps a chained process under
loops_check's 30-minute running-tick bound; past it the process exits and launchd's next fire, 300 s later, starts a new
chain. A refusal (exit 1) and a test world (`--facts-source file:`) never chain. `LANDING_TICK_INTERVAL_S` and
`LANDING_TICK_CHAIN_WALL_S` override, and a wall of 0 turns chaining off.

The heartbeat is also written the moment a tick takes the lock, with that tick's start stamp, and again with its
receipt. Before this it was written only at the end, so a running tick's run record was the previous tick's end
plus the idle, and `ruling_mechanisms.py` judged the controller unwired at 871 s against twice the 300 s interval
(2026-10-17T00:47Z).

## A tick past its deadline ends itself (OMN-19998)

A live tick still running `TICK_DEADLINE_S` (1500 s) after its start ends with exit 3, stderr
`TICK-DEADLINE: ...` and an `UNKNOWN` receipt with `refusal: TICK-DEADLINE`, so launchd's next start runs a fresh tick
instead of nothing; the slowest recorded tick ran 926 s. The state is written before every act and every write is
atomic, so the end is the crash the controller already recovers from. `LANDING_TICK_DEADLINE_S` overrides; 0 turns it
off.

## Bounded parallel live reads (OMN-19998)

`LiveGitHub.live` runs its chunk reads and its per-PR merge-queue removal reads at most `READ_WORKERS` (4) at a time,
with the answers the serial reads give; `LANDING_READ_WORKERS` overrides and 1 reads serially. These are the reads a
stale PR watcher state sends to GitHub for every PR.

## No handover, no observe-only repo

The section 0 handover (`landing_controller.py drain <repo>`, which ended a repo in observe-only) is
gone with the Claude drains it handed repos to (RULING 2026-09-29T06:34:17Z). A repo is kept out of
landing only by a HOLD row naming it, which the decision node reads every tick. An
`observe_only_repos` entry or a `drain-requested.json` left by the old handover is cleared on the next
tick.

## Lab proofs (OMN-18893)

A green runtime PR in `omnibase_infra` or `omnimarket` with no PASS lab-pool readback for its head
is gated by the node. Each tick, for each such repository with no live prover, the controller writes
a prover lease to `lab/state.json` and spawns `../merge-drain/scripts/landing_lab_prover.py run`
(detached, no model). The prover plans groups with omnibase_infra's `prepr_pool_group.py`, proves
each group ON TOP OF every PR that already holds a readback and every group that passed in the job,
with `prepr_runtime_pool.py run` on a free lab host under a HOLD, appends the PASS readback to each
member's body (the next tick lands them one by one), and bisects a failure down to the breaking PR,
which gets a FAIL comment and is not proved again at that head for six hours. The model and the
design verdict are `../merge-drain/tla/lab_group_prover/`.

```bash
env -u PYTHONPATH /opt/homebrew/bin/python3.13 ~/.omninode/landing-controller/skills/merge-drain/scripts/landing_lab_prover.py status
```

Each tick receipt carries a `lab` section (`spawned`, `released` with per-verdict counts, `live`,
`fails`, `backoff`); `decisions.jsonl` logs `lab_spawn`, `lab_release` and `lab_kill`.

## The worker engines are data (OMN-19998)

RULING 2026-10-29T18:02:40Z, operator: "fix the lander for merging green prs or do it manually via cron or better yet,
with delegation." The decision node picks a rung of the ladder that is also in the tick's `available_engines`, and the
controller offered it `["claude_sonnet"]` only, from a literal in `landing_controller.engines_available`, with the ladder,
the escalation engine, the retired-engine map and the Codex-first brief classes as literals in `landing_facts` and
`landing_placement`. They are all `merge-drain/scripts/landing_engines.json` (the installer copies `scripts/*.json`, so the install carries it) now, read by `node_landing_pool_capacity_compute`:
`claude_engines`, `delegated_engines` (`codex_high`), `ladder`, `cause_ladder`, `escalation_engine`, `retired_engines`,
`mechanical_brief_classes`, `code_brief_classes` and `delegation_routes` (the order a worker drafts through: Codex, GLM
through Claude Code, the code-edit node, the lab agent for code; GLM then the lab for text). Adding or removing a delegated
engine is an edit of that file. A delegated engine is never a ladder rung (a rung outside `claude_engines` reads as the
default), so Claude stays the escalation; the worker swaps the first rung of a Codex-first class for the delegated engine
on a lab host (see Worker placement). A missing or malformed file reads as Sonnet only. The install proof runs on the fetch transport and moves to the next clean pool host when a host could not take it (`node_landing_push_refusal_effect`; h904 timed out every push for two days). `LANDING_CODEX_MECHANICAL=0`
withdraws the delegated engines. `tests/test_landing_engine_policy_node.py`.

## Worker load pause

The node dispatches no fix worker while this host's load1 is above the policy's
`load_pause_threshold` (`landing_facts.policy_for`), and while load1 is above the core count at most
two workers run. With no lab runner the bar is 2.5 load per core (60 on the 24-core Mac), because the
worker's tests run here. When `landing_facts.lab_run_argv` resolves ops_tooling_pkg's
`lane-k-run` (`LANDING_LAB_RUN_CMD`, else `lane-k-run` on PATH, else the ops_tooling_pkg clone
through `uv run --project`), the worker prompt sends every test, lint, type check and build to the
least-loaded lab host and forbids running them here, and the bar becomes 4.0 load per core (96 on
the Mac). Read the bar a tick used in `last-facts.json` under `policy`.

## Worker placement across the pool

With a worker pool (`landing_placement.DEFAULT_POOL`, or `LANDING_POOL_HOSTS` as a JSON list of rows;
`[]` turns it off and the load pause above applies), this host's load pauses nothing. Every tick
probes each pool host (the Mac locally, the lab hosts over ssh) for cores, load1 and free memory. A
host has room for another worker while `cores - load1 - 2 x (workers placed there)` is at least 2,
4 GB is free and its `cap` is not reached. `max_workers` is the placed workers plus the free slots
of the whole pool, so dispatch pauses only when no machine has headroom. A lab host with no Claude login counts
while the Codex engine can run there (`landing_facts.pool_capacity`, OMN-19998): on 2026-10-18 h908 held seven
Codex slots and added nothing. Each worker then takes the
host that holds a login for its engine and ranks first on `landing_placement.spread_key` (a host with nothing placed, then the
lowest placed-over-cap fraction, then the most free capacity: ranked on free cores alone h908 carried 75 percent of the workers,
OMN-20531); a worker with no Claude host free is not placed and the next tick retries. The landing ladder stays Claude tiers (sonnet, opus, opus):
`landing_facts.ENGINE_LADDER` is unchanged. The engine policy for mechanical work sits at the worker (OMN-20531, operator RULING
2026-10-04T18:17:13Z): a brief of class behind, conflict_mechanical, cascade_red, companion_red or companion_orphan on the first rung runs
as the Codex engine (`codex_high`, `codex exec -s workspace-write`, high effort, the account's default model) on a lab host the shared table
marks `codex: true` that has a Codex login, a writable lane workdir, a Codex sandbox that can write it, no Codex usage-limit mark and a free
slot (`landing_placement.choose_codex`), never on the launching host; with no such host it falls back to the node's Claude engine, and a
failed Codex worker still steps the PR to claude_opus. `LANDING_CODEX_MECHANICAL=0` turns the routing off. Delegation takes every class whose fix is
code in the PR (OMN-20106, operator RULING 2026-10-08T23:38:53Z): real_red, conflict_substantive and runtime also run rung 1 as the Codex engine
(`landing_facts.CODEX_FIRST_BRIEF_CLASSES`), with Claude the escalation: the Codex worker is told to end blocked with
`reason=codex_attempt_failed` rather than push a fix it could not make pass, the PR's next worker is claude_opus, and the rung budget is the same
as before. shared_cause stays on Claude (its worker classifies the source before it fixes anything), drafting its code through the delegation
step. `LANDING_CODEX_CODE=0` turns off the three code classes alone. A rerun, an update-branch and a companion wait are the controller's own
actions and run no model. The controller runs from the copy `install.sh` makes under `~/.omninode/landing-controller` (see Install and status),
not from a clone: the routing change reaches it only after the pull request is merged, the version-bump pull request has landed and the
installed plugin release is the new one (`claude plugin update omni@private-repo`), and then `install.sh --g-act-dir <the receipts dir>` is run again (the controller file itself is
unchanged by this routing, so its sha256 and the G-ACT receipts still match). The probe's preflight lines
(WORKDIR, CODEXLOGIN, CODEXSANDBOX; CODEXLOGIN is `unavailable` when `codex login status` timed out or could not run, which refuses the Codex engine only) and the placement dir's `.limited-`, `.codex-limited-` and `.codex-sandbox-` marks decide, and
`placement.json` names every host skipped and why (`codex_fallback`, `skipped`). A Codex worker that ends with no result on a usage limit
or a sandbox write failure is revoked, so it spends no escalation rung. Codex also stays a drafting route inside a Claude worker. The prompt routes code drafts
through `delegation_step.py code`: Codex first, then the lab agent (`lab_crush.py`), then one
GLM draft through Claude Code (`harness_delegate.py run --harness claude-glm --task-class code_generation
--writable-repo <worktree>`; the cloud-glm backend pin of `onex delegate` is retired, OMN-20173), with receipts
for failed attempts when the host has no Codex binary. Never pass a model flag to Codex.
The worker session reads every diff and runs focused tests before committing. The Mac is eligible only with that headroom. On a lab host the worker commits in a worktree under
`~/lab-run/runs/` and never pushes itself; the landing worker then pushes them from that same lab host (OMN-19998:
`landing_worker_run.push_from_host`, the repository's pre-push hooks installed and run there, bounded at 1,800 s on that
host) and writes `push_evidence`, so the pre-push suite never runs on this host. Only a lab host with no gh credential
falls back to `push_back` from this host, which fetches the commits back and pushes them. A host without gh gets the PR's checks and failed-step logs
as a file. A remote engine ends at the lease deadline or when the controller kills its ssh session.
`workers/<lease>/placement.json` records the host, the engine and every host's reading; markers in
`~/.local/state/omni/landing/placement/` hold a slot while the worker's pid lives. The transport is
ssh until the event-bus placement (OMN-20105) replaces it.

## Worker lane environment (OMN-17427)

Every worker starts with the lane environment the push hooks and the PR-ownership guard resolve a lane from:
`ONEX_LANE` (`landing-L<lease>`), `ONEX_RUN_ID`, `ONEX_LANE_HOST` (a lab host) and the host's registry roots
(`registry_root`, `ONEX_STATE_DIR`, `ONEX_HOOK_EMIT_JOURNAL_DIR`, `ONEX_WORKTREES_ROOT`, `ONEX_WORKSPACE_CONFIG_ROOT`),
plus `ONEX_LEDGER_PATH` for a worker on the controller host. It is the remote-lane runner's own set: `lane_env` and
`host_path_env` are defined once in `landing_placement.py` and both launches use them
(`landing_worker_run.worker_lane_env` for the local worker and for the fallback push the controller host makes for a
credential-less lab host's worker; `lane_env_lines` for a lab host's run step, which exports the roots only when the host's registry root was
found). Before this, only `LANDING_LANE` was set, and the guard refused a worker's PR mutation as `INDETERMINATE_LANE`
or `ONEX_STATE_DIR is not set`. The change reaches the controller after the installed plugin release is the new one
and `install.sh --g-act-dir <the receipts dir>` is run again.

## Worker text goes through the lab (OMN-17427)

On 2026-10-01 110 of 126 finishing landing and quick-fix lanes in 12 hours delegated nothing: the worker wrote its
PR comment, close comment, commit message and report by hand. The worker prompt now carries a mandatory text step:
every such text is drafted by `merge-drain/scripts/landing_text.py`, which drafts through GLM first
(`harness-delegate --harness claude-glm`, glm-5.3-flash then glm-5.3, log line `engine=glm`; OMN-20844) and then
calls the sanctioned wrapper
(`omnibase_infra/scripts/onex delegate --task-type <summarization|document|review> --bus kafka --lane dev
--locus deployed-lane`, graded by the task class's own contract: no `--criteria`, no `--criteria-mode`, because
`replace-task-class` with `concise` scored every body over 250 words 0.6 against the 0.8 bar, and
`final_artifact_only` vetoes a body that quotes a command in a fence; use `document` for a PR body) and logs one line per call to the lease's `delegation.jsonl` (a lab host's log is read back
by the collect step). When the dev-bus call is refused, the helper retries once with `--bus inmemory --locus
in-process` against the lab endpoints and the log line says `form=inmemory`. The worker checks the draft against its
facts. A lab-hosted worker's relayed TERMINAL carries `delegated=<n> runs=<ids>` from the log, else
`delegated=0 delegation_reason=<the worker's stated reason>` (`MISSING:` when it stated none). A local worker's cells
land in `state/delegation.jsonl` each tick and the tick line carries `worker_delegated=<with a run>/<finished>`.
The lab hosts' dev-bus identity is OMN-20263 (done 2026-10-01 08:54Z); each host exports its own registry root
(`LANDING_DELEGATE_HOME`) for the wrapper.

## Bot release PRs (OMN-20864)

A bot's `chore: release` PR is gated until release-cut's premise (`cut_facts.sh`, the read its
steps 3 and 6 make) reads `PREMISE READY` for its base's current tip. The controller reads only
open, ready, green release PRs based on dev, at most once per repo tip per 15 minutes; unreadable
reads retry next tick. Then it decides the PR like any green PR, merging or enqueuing pinned to
its head with holds, owners, pauses, draft, `do_not_land` and the lab gate unchanged. A red or
pending release PR stays gated and gets neither a merge nor a worker, however long it has been red (OMN-22314).
OMN-19998 lifted that gate after 30 minutes red, and the worker it sent pushed product changes onto omnibase_core#2247
(lease L24372), a bot release branch the release train owns; the lift is gone. The release-train identity (title
prefixes, whether the author must be a bot) is data in `merge-drain/scripts/release_train_identity.json`, not a
code literal. A red release PR is reported in the tick line (`release_red=<n>[<pr>,...]`) and the receipt's
`release_red`, for the release train's owner to re-cut or fix on dev. The gate applies again when the head is green, and the premise still decides
the merge. `pr-handoff` still refuses it.

A release merge tags whatever dev holds at that instant, so step 6's condition (the premise still
holds for dev's head at that moment) is checked again at the merge: `release_hold` reads the base
tip live just before the merge (both the node's merge and the pipeline merge) and defers the merge
when the tip is unread or differs from the tip the premise read, for example after another merge in
the same tick. The next tick reads the premise again at the new tip. A release PR is never put on the
node hand-over clock, so this check always runs. At most one premise command runs per tick (a
lane-j read walks dev's history); a second release PR reads `UNREADABLE` with the cap named and
is read on a later tick. On a merge-queue repository the merge is an enqueue, and entries ahead of
it land first, as they do for step 6's hand merge.

The tick receipt's `release_premise` maps each bot release PR to its repo, base, head, dev tip,
verdict, reason and cache status. Tick-line cells `release_prs=` and `release_ready=` count those
PRs and READY verdicts. `LANDING_RELEASE_PREMISE_CMD` overrides the premise command with a JSON
argv list for tests; the controller appends the repo and scratch directory arguments.

## A green, CLEAN PR held by a gate alone is merged after 15 minutes (OMN-19998)

RULING 2026-10-16T11:40:09Z (amends 03:58:15Z): a PR is held only while it is a draft or a grant. omnimarket#4004 sat
green and CLEAN from 09:09Z to 11:38Z, gated `release_train`, until a person merged it. Each tick, an open PR that is
green and CLEAN, whose only suspension is a gate, and whose gates are not in `landing_facts.GREEN_HELD_KEEP`, starts a
clock at its head (`green_held_clock` in the sidecar, keyed `repo#n@head`; a new head starts it again). The clock
starts at the head's green time, the newest check-run completion the watcher holds and the stamp the throughput tick's
green-held alarm reads, not at the tick that first sees it: omnibase_core#2034 went green at 23:50:49Z, two worker
leases kept its clock from starting until 00:05:39Z, and the controller would have acted after the alarm's 30 minutes
(`landing_facts.green_since_of`, `green_held_since`). Held for
`GREEN_HELD_MINUTES` (15, the alarm's 30 less the controller's tick lag), the PR reaches the pinned node without
the gate, so the node merges it (the enqueue on a merge-queue base) pinned to its head, and `release_hold` no longer
defers it. omnibase_core#2046 went green at 07:32:50Z, the tick at 07:50:17Z saw it held 17 minutes under the old 20,
and the next tick's merge landed at 08:03:46Z, 31 minutes after green: ticks start up to 9.35 minutes apart and merge
up to 5.57 minutes in. The merge row in `decisions.jsonl`
carries `green_held_override` (the gates overridden), `green_held_since`, `green_held_min` and `rulings`. The tick
receipt's `green_held` and the tick-line cell `green_held=` count the lifted PRs. The decision node is unchanged, so
the TLC pin still holds.

Never lifted: a draft, a hold, a lane's ownership or a lease, a do-not-land label, and the gates `operator_main` (the
grant: a PR into main of an operator-gated repository), `queued`, `retarget`, `base_blocked` and `ledger_pause`. The
throughput tick's `MISSING green-held:<repo#n>` (session-start `loops_check.green_held_findings`) is the alarm for a
PR still held 30 minutes or more.

## A ready PR the tick took no action on is merged that tick (OMN-17427)

Exception class `controller-leaves-clean-green-unmerged`, mechanized on its second occurrence: ops_tooling_pkg#883
(head bb930beb, 31 minutes), #879 (3cf526f5, 45 minutes) and #894 (e9f4be56, 41 minutes) were green on every check
and CLEAN, not merged or queued, until the orchestrator merged each by hand at its exact head on 2026-10-20. After the
pipeline merge, the clean-green merge node takes each PR this tick's `pr_reasons` reads `ready` (green, clean, unarmed, no
gate, no collaborator author) that no outcome of the tick names (`node_clean_green_merge_effect`'s `clean_green_unmerged`, the detector)
and merges it with `gh.merge` pinned to its head (an enqueue on a merge-queue base). It makes at most one merge a tick
on a base that requires up-to-date branches or whose setting is unread, and `CLEAN_GREEN_MAX_PER_TICK` (3) in all. A base
read not strict (`strict_of`, the `strict-bases.json` cache) takes every ready PR up to the cap after any merge this tick
(OMN-19998): on 2026-11-10 omnimarket:dev (strict=False) took one node merge a tick from 19:42Z to 20:04Z and five ready
PRs there were deferred `a merge on omnimarket:dev this tick` for 45 to 95 minutes. Each merge is a `merge` row in `decisions.jsonl` with
`clean_green: true`. A case it leaves for the next tick is a `clean_green_deferred` row whose `detail` says why: the tick
budget, the cap, a merge already made on its base this tick, a red merge-queue base, or a hand-over or release hold. A
merge GitHub refuses (`failed` or `error`) is the one case emitted to the exception queue (`exception` on the row),
keyed `repo#n@head`. The controller starts no lane for it.

## A green head the watcher reads UNKNOWN is read from GitHub (OMN-19998)

The tick serves a PR from the PR watcher's record while that record and the controller's timeline memo are fresh
(`landing_github.watcher_live`). GitHub reports a merge state of `UNKNOWN` until it has computed mergeability, and the
node merges only a clean head, so a green PR served `UNKNOWN` read `ready` in `pr_reasons` and got no merge for as long
as the memo stayed fresh (up to 60 minutes). plugin-tooling-pkg#862 sat so from tick 2955 to tick 2958 (2026-10-17T16:14Z
to 16:36Z) while #863 beside it, read from GitHub, read clean and was enqueued at tick 2955. A green head whose watcher
merge state is `UNKNOWN` now goes to the batched GitHub read (`why` cell `merge-state-unknown` in the receipt's
`watcher_live`); a red or pending head's merge state decides nothing, so the watcher still serves it.

## A green head GitHub reads BLOCKED behind a strict base is behind (OMN-19998)

GitHub reads a green head that is behind a base requiring branches up to date BLOCKED, not BEHIND, when the base also
lands through a merge queue. The node merges only a clean head (or a behind one on a merge-queue base) and updates only
a behind one, so plugin-tooling-pkg#1012 head ac5b9217c672 read `ready` from tick 3225 to tick 3230 (2026-10-19, green
from 12:17Z, four commits behind main) and got no action while #1016 and #1017, up to date, were enqueued. The
shared-base node's read phase (`read_strict_behind`) reads each green BLOCKED head's base setting (`strict-bases.json`),
the base tip and the head's ancestry (the canonical clone, else GitHub's compare); a head that does not contain the tip
of a strict base reaches the node as `behind`, which it enqueues on a merge-queue base and updates elsewhere. An unread
setting, tip or ancestry leaves it BLOCKED. The same read takes every live PR's merge-queue answer while the PR
watcher state is fresh: tick 3229 (804 s) built its facts after 527 s of contract heals and release premises, past the
state's 8-minute bound, and every PR then read `merge_queue: false`.

## Base-blocked merge-queue ejections (OMN-20126)

When the merge queue removes a green head for failed checks, the controller reads why: the PR's newest
failed merge group (`gh-readonly-queue/<base>/pr-<n>-<base sha>`), that group's failed jobs (the CI
Summary aside), and each of those checks on the base sha the group was built on, as it stood at the
removal. When every failed check had already failed on that base, the ejection is a base-branch red
(2026-09-30: omnibase_infra dev's `Lockfile CVE Scan (OMN-16228)`), which no PR-level worker can fix.
Such a PR is base-blocked: it gets a gate suspension, so no fix worker and no re-enqueue, and every tick
line carries `base_blocked=<n>[<check>]` (the receipt's `base_blocked` names the PRs). Once a later
merge_group run of the blocking check's workflow on the same base concludes success, the PR is a plain
green head again, the next tick re-enqueues it, and the line carries `base_block_lifted=<n>`.

A group failure the base did not share is not the PR's to fix while every check on its head is green
(OMN-17427). On 2026-10-21 plugin-tooling-pkg#1021, #1030, #1061, #1078, #1079, #1084 and omnibase_infra#5208
and #5217 left the queue that way and got fix workers (leases 12992 and 13028 on #1061) instead of a fresh
enqueue; the lab had no slot, every worker ended `lab_capacity_unavailable`, and they sat green and unqueued.
`node_landing_green_requeue_compute` now decides it: an open head with a SUCCESS rollup, MERGEABLE and CLEAN,
removed for failed_checks at a known time (the live read's `queue_ejected_at`) and not base-blocked is enqueued
again once per removal, `MAX_GREEN_REQUEUES` (3) times a head, each grant a `green_requeue` row in
decisions.jsonl (`outcome` `readmitted` with `requeue_n`, then one `spent` row). The sidecar key is
`green_requeue`, the receipt's `green_requeue` names the re-admitted PRs and the tick line gains
`green_requeue=<n>`. Such a head is never sent a fix worker: past its re-enqueues, or with no known removal
time, it is gated `green_ejected` (its reason reads `queue_ejected`), spent at once, and the queue retry below
re-admits it; the head-cap escalation takes it only after that retry is spent. The transient re-admission
(`queue_transient`) is decided by the same node.

A fix worker on a head red on its own checks and ejected too gets a prompt that names the ejection (OMN-17427).
`landing_worker_run.queue_ejection_text` reads the newest failed_checks removal at the dispatched head, the
ejecting group's failed jobs (CI Summary aside) and each job's test-summary block, and tells the worker to
merge the base, fix, push and report `fix_submitted`, never `armed` for that head. omnibase_infra#4404 head
61187be7 was ejected five times on 2026-10-01 while four workers reported armed. The read never stops a
worker; a failed read leaves the old prompt.

## Companion waits and stale external blockers (OMN-20140)

A PR whose only reds are the change-control cascade (the OCC Companion Merged Gate, occ-preflight
eligibility and the CI Summary that follows them) while its companion (the watcher's
`evidence_companion`) is open is `companion_wait`: it gets a gate suspension, so no fix worker, since
no PR-level change turns those checks green before the companion merges (28 of 86 workers on
2026-09-30 returned `external_blocker upstream_open` on an open companion). Every tick line carries
`companion_wait=<n>` and the receipt's `companion_wait` names the PRs and companions. When the
companion merges or closes, that same tick reruns the PR's failed runs (`companion_rerun=<n>`) and the
node sees the PR pending until the rerun grades it. A companion that is open and red on its own checks
enters the node's facts and gets the fix worker (`companion_red=<n>`); a companion that is not red is
gated, so the controller never merges one. A real red beside the cascade, a conflicting head, a red
read at an older head, or an unknown companion keeps the old path: a worker.

An `external_blocker` result's ref is kept in the sidecar with the state the worker judged
(`external_seen`; `upstream_open` means open), and the node's blocker fingerprint carries that state.
A later tick that reads the ref merged or closed clears it (`blocker_cleared=<n>`), so the fingerprint
changes and the node reruns or re-dispatches the PR; when its reds are the cascade, the controller
reruns them that tick. Before this, a result recorded after its blocker merged (tick 125 on
2026-09-30, omnibase_infra#4333-#4335 on OCC#11886) was suppressed forever.
Cause parks and `external_blocker` waits retry on the next tick after the PR's base branch tip moves,
its head moves, or its named blocker PR merges or closes, with a 60-minute backstop (OMN-20864), except that an
`upstream_open` blocker has no backstop (OMN-19998): its gate (`external:<ref>`) and its park hold while the ref reads open
and lift when it merges or closes or the PR's head moves. Orchestrator decision, lane upstream-gate-0655: on 2026-10-22
plugin-tooling-pkg#1158, #1148, #1141, #1139 and #1124 were each due a worker an hour after their judgement with the
upstream still open, about 2.5 dispatches an hour. The rule is `landing_facts`' (`UNBOUNDED_KINDS`, `worker_gate_of`, `retry_parks`); every other known
kind keeps the hour.
A ledger line, timestamp, run or other non-PR ref cannot hold a worker: it is dropped next tick.
A retry trigger preserves the attempt budget at that head. Per-PR workers stay capped at three;
causes have at most three attempts across park episodes, including the bounded retry. A changed head starts new work.
Parks write local evidence and require no operator RELEASE or park MSG.

A worker that found nothing to fix (`waiting_ci`, or `blocked` with `reason=nothing_to_fix`) made no attempt.
The pinned node grades both kinds `invalid` and climbs the ladder, so before it reads them the controller
revokes the dead lease (`revoke_no_attempt_results`, `no_attempt_revoked=<n>`): the node records
`timed_out reason=revoked` with the ladder unchanged, and the PR gets no worker until its head or worker inputs
change (`worker_gated_no_attempt=<n>`), the same gate a no-result exit takes. From 2026-10-08T14:10Z to
2026-10-09T09:00Z, 63 of 364 leases ended on those two kinds and sent 34 same-head successors, 31 of them on
claude_opus (OMN-17427). Any other `blocked` reason is still the node's to grade and escalate.

A worker whose host refused its tools made no attempt either: a `blocked` result whose `delegation_reason` is a
`route-refused:` or `route-unavailable:` naming a hook parse or syntax error or no Bash (`host_tools_refused`,
`landing_controller.host_tools_refused`). Its lease is revoked and journalled as `no_attempt_result` the same way, a cause
lease included (the node spends no cause attempt on a revoke), its dispatch is taken back off the PR's head count
(`landing_facts.uncount_head_dispatches`), and the PR is not gated: its next worker goes to another host. On 2026-10-11
every Bash call on h903 was refused (its guard hook did not parse under /bin/bash 3.2); its workers spent head-cap
dispatches (tick 1926: `worker_gated_head_cap=13`) and the attempts of two shared causes (OMN-20961). Placement now refuses
such a host before any worker goes there (`HOOK-PARSE-FAILED`, see the remote-lane skill's admission bar).

Three parks never clear that way, so the controller refuses them on the tick after the result is
recorded (OMN-17427): a ref that is the PR itself, a ref that was already merged or closed when
the worker judged it, and a ref that is not a PR or issue at all (not `<repo>#<n>`: a timestamp, a CI run
or free text; its observed state is only ever `named`, so nothing can change it). The ref is dropped, the fingerprint changes and the node sends a worker again,
within the per-head attempt budget (`park_refused=<n>` counts dropped refs). A worker
that finds its PR superseded reports `close_superseded` (with `head_sha`, and `superseded_by` when a
merged PR carries the change). The controller reads the PR live and closes it with a comment only when
it is open at that head, carries no hold, owner or registry claim, takes a close claim
(`pr_claim_registry_cli.py claim --action close`), and either has an empty net diff against its base
or names a merged superseder (`closed_superseded=<n>`). The node reads a closed one as an
`external_blocker` and an unverified one as `blocked` (invalid), so nothing is closed on a guess.
Before this, omniintelligence#962-#964 and omnimarket#3151 sat parked until a lane closed them by hand.
omnibase_infra#4463 sat at `external_blocker` (ladder_index 1) on 2026-10-02 with the ref
`2026-10-02T13:16:53Z`, the stamp of a merge-group ejection that a rerun of the same merge commit had
already passed; the sidecar held three more such parks (registry_root#724, omnibase_infra#4468 and
onex_change_control#12053), which this refuses on the same bounded path.

## A pushed head settles before its PR is leased again (OMN-19998)

The 2026-10-16T21:20Z yield diagnosis found 83 of 186 leases were conflict resolution; of 56 pushed fixes, 9 went red
again and 25 were simply leased again, omnibase_infra#5032 eight times, #5038 seven, #5026 six and omnimarket#4017 six.
The per-head cap never binds across a push, since a new head counts from one. Two worker gates (`landing_facts`), neither
a spent gate, so neither takes an escalation stage:

- `fix_settle`: a PR whose live head is not the head its last worker was sent to was pushed to, and that head is
  settling (sidecar `fix_settle`: `head`, `since`, `attempted`). It gets no worker while its CI is pending, or green with
  no merge attempt (armed or queued) made at it, for at most `SETTLE_HOURS` (2) from the tick that first saw it. CI
  finished red, CI finished green on a conflicting head (it can be neither armed nor queued), an armed or queued head,
  or the bound releases it.
- `lease_window`: a PR with `MAX_LEASES_WINDOW` (3) leases started in the last `LEASE_WINDOW_HOURS` (6) gets no worker
  until the oldest ages out (sidecar `lease_window`; per-PR workers and escalation workers both count). It is checked
  first, so an escalation stage cannot add a fourth lease inside the window. A lease revoked on a pool fault
  (`host_tools_refused`, `lab_capacity_unavailable`) leaves the window: its start is removed (`lease_window_uncount`).
  A dispatch refused before its worker started (`head-moved`, `claim-refused`) gives its write-ahead stamp back after
  the actions run, so it is no lease (OMN-19998: omnibase_infra#5074's head-moved lease 9962 filled the window on
  2026-10-17).

Tick-line cells `worker_gated_settle=<n>` and `worker_gated_lease_window=<n>` count them when nonzero.

## A spent head is escalated, never left idle (OMN-19998)

RULING 2026-10-14T05:17:57Z. Ticks 2391 to 2393 each held 23 PRs at `worker_gated=head_cap` with no lease and free
pool slots, and nothing acted on them until their heads moved. A PR whose worker gate is spent (`head_cap`,
`no_result_file`, `no_attempt:<kind>`), or that the controller has seen green and armed at one head for an hour
without merging (sidecar `armed_since`), takes one escalation stage a tick, each at most once per head (sidecar
`head_escalation`): `superseded` (an empty net diff, or a merge of the head into `origin/<base>` that leaves the base's
tree as it is, closes the PR after a close claim, with a comment), `conflict` (a conflicting merge state gets one
conflict worker on `claude_opus`), `triage` (one triage worker on `claude_opus`, whose brief lists the results this
head's workers left, returns `fix_submitted`, `close_superseded` or `external_blocker` with `person` and `reason`), and
`needs_person` (that person and reason are posted once on the PR and the gate reads `needs_person:<who>` until the head
changes). A triage `close_superseded` goes through the close path above (live read, hold check, close claim): a PR it
closes is no longer a candidate, and one the path refuses is held with that refusal in the comment (`claim_refused: ...`,
`refuse: ...`, `held: ...`), never "no verdict". The claim runs with `ONEX_LANE_ID=landing-controller`, because the claim
CLI refuses a process with no lane identity and every close from 2026-10-07 to 2026-10-14 (58) was refused for it
(OMN-19998). An escalation worker's lease is written into the node's write-ahead state inside the node's worker bounds,
so the node probes, kills, records and releases it as its own; a PR those bounds leave out is `waiting`. The node
fills the pool to `max_workers` before the escalation runs, so a PR green on its own checks (or red only on a
merge-queue ejection) takes one of two reserved slots (`escalation_slot`'s `reserve`) past the pool and per-repository bounds; the pool
never holds more than `max_workers` plus the reserve (OMN-19998: plugin-tooling-pkg#1033, green and conflicting,
waited `:pool` or `:repo_pool` on every tick from 3329 to 3341). Every tick
line carries `idle_gated=<n>[<prs>]` (a candidate with no next action this tick, which makes the tick DEGRADED) and
`escalation_<stage>=<n>`; queue-status names a PR idle on two ticks in a row as a DEGRADED reason. Model and TLC
verdict: `../merge-drain/tla/head_cap_escalation/`.

A head the node parked after its engine ladder (`degraded: escalation_exhausted`) is a spent head too (omnimarket#3793,
#3817, #3881 and onex_change_control#13549 sat so at ticks 2431 and 2432 with no stage and `idle_gated` empty): it takes
the same stages. The node unparks a head when the triage worker's result is recorded, so the escalation's memory
(`trigger=escalation_exhausted`) keeps the PR gated at that head (`worker_gated=escalation_exhausted`, then
`needs_person:<who>`) until the head moves. A head whose merge-queue ejection waits for its re-admission
(`park_queue_retry`) has that as its next action and is left to it, whatever spent it (`head_cap`, `no_result_file`
or the park), and the receipt's `escalation.waiting` names it `<pr>:queue_retry` (OMN-19998: omnibase_infra#5154 and
plugin-tooling-pkg#1025, green and CLEAN on 2026-10-20, took triage and decide workers whose leases held their lifted
heads at `worker_running`). `idle_gated` also lists any PR the node reports
degraded, for any reason, that holds no lease, no node action this tick, no stage and no needs-person hold.

A triage that returned no verdict is not a decision (OMN-19998; ops_tooling_pkg#572 and onex_change_control#13587 were
held "returned no_result_file and no verdict", onex_change_control#13549 "returned waiting_ci and no verdict", all three
for the operator). Only a triage that names a person and a reason, or a `close_superseded` the close path refused, makes
a `needs_person` hold. A triage that left no result file (`no_result_file`, or a `blocked` of `lab_capacity_unavailable`
or a host that refused its tools) is run once more, the brief carrying `avoid_hosts` with the host it ran on
(`placement.json`), which the worker's placement leaves out while another pool host exists (`retried` in the memory); a
second silent triage holds the PR. A triage that returned `waiting_ci` takes the PR back a stage (`awaiting_ci` and
`ci_waits` in the memory) and the tick line counts it `waiting` as `<pr>:ci`; it is triaged again once its checks are
not pending and its worker input has changed, or after `CI_WAIT_HOURS` (2) with no new reading, and held only after
`MAX_CI_WAITS` (3) such results at one head.
A hold already posted whose reason ends "and no verdict" is taken back the same way on the next tick, when its triage
lease's result is still `no_result` (and the memory has no `retried`) or `waiting_ci` (under the bound), so the three PRs
held before this rule needed no state edit.

## A batch window a sibling conflicted is healed by the tick (OMN-17427)

Every tick reads each open change-control companion live, on any branch but a per-PR machine branch: the
per-repo window `auto/window-<owner>-<repo>-occ-autobind`, the per-ticket `auto/ticket-omn-<n>-occ-autobind`, or
a hand-authored branch (OMN-20411).
One that reads conflicting is healed in the tick: `landing_github.heal_window_branch` fetches it and
`dev` into the canonical `onex_change_control` clone, checks the branch is still at the head the tick
read, merges `dev` in a detached worktree under `worktrees/OMN-19998-landing/`, resolves each
conflicting `contracts/*.yaml` as the union of both sides when both only appended (`dev`'s entries
first), commits with the clone's hooks and pushes as a fast-forward of that head (`window_healed=<n>`;
the receipt's `window_heal` names each). A conflict outside `contracts/*.yaml`, an add/add, or a side
that changed a line is `window_heal_refused=<n>`, and the receipt's detail names every file it could not take;
that head is kept in `window-heal.json` with change-control `dev`'s head at the refusal (one `git ls-remote`),
the tries in a row, the tick and the outcome. A heal that raised (`window_heal_error=<n>`, such as a change-control
hook failing the merge commit) is kept the same way. That head is tried again when it moves, after
`heal_backoff_ticks(fails)` ticks (3, 6, 12, then 24; `LANDING_HEAL_BACKOFF_TICKS`, `LANDING_HEAL_BACKOFF_CAP_TICKS`),
or sooner when `dev`'s advance since the try changed a file the window changes (`heal_base_touches`; conflicts are
only in files both sides changed). OMN-19998 replaced OMN-20468's retry on any `dev` move: `dev` moves nearly every
tick, and on 2026-10-11 three stuck windows took 170 s of each 482 s tick for one heal in 51 ticks. Retries go after
every never-tried head, so they cannot spend the heal budget first; when `dev`'s head cannot be read, no backed-off
head is tried. A conflict in a generated
self-bind (`drift/occ_bindings/OMN-<n>/occ-self-bind-pr-<n>/command.yaml`, the whole allowlist,
`landing_github.HEAL_TAKE_DEV_RES`) takes `dev`'s copy byte for byte: `dev`'s copy is the merged companion's own
binding. Nothing else is ever resolved by taking `dev`. On 2026-10-03 tick 733 refused OCC#12672 on an add/add of
`occ-self-bind-pr-12611/command.yaml` and never tried it again, so omnibase_core#1869 and #1871 waited until a
lane merged `dev` into the window by hand (OMN-20459). A companion with a hold, an owning lane, a registry claim or a worker lease is
`held`, left to its holder. Per-PR machine companions (`auto/<owner>-<repo>-pr-<n>-occ-autobind`) are not touched: omnimarket's scheduled
re-mint owns them. A hand-authored companion has no re-mint, so it takes the same heal; it is a companion
when the watcher's `evidence_companion` of its product PR names it, and it is healed only while an open
product PR names it: a per-PR companion a merged batch window superseded is not healed (OMN-20488; on
2026-10-04 orphans of OCC#12672 took 303 s and 287 s of heal budget in ticks 734 and 736 with no PR
waiting on them). A machine window or ticket batch branch is healed whether or not a member names it yet.
Before this, nothing healed a window: omnimarket's re-mint skips batch branches ("no single product PR to
replay"), its members only waited on it, and on 2026-10-01 OCC#12224 sat conflicting from 22:18Z, with
omnimarket at 0 of 9 merged, until a lane union-merged `dev` into it by hand (ddbf53a136).

The heal's cost is bounded (OMN-20438). The heal worktree is sparse: everything but `drift/` (63,708 of the
clone's 74,697 files), set per git call so the canonical clone's config is never written. A tick starts heals
until `LANDING_HEAL_BUDGET_S` (default 240) is spent; the first always starts, and the rest are
`window_heal_deferred=<n>`, healed by a later tick, never refused. Before a heal, a `*-heal-*` worktree a killed
tick left registered in `worktrees/OMN-19998-landing/` is removed with `git worktree remove --force --force`;
a fix worker's `-L<lease>` worktree there is never touched. On 2026-10-03 the unbounded serial heal of 28 DIRTY
companions held tick pid 17520 for 35 minutes (a full-tree checkout alone took about 3 minutes at load1 31-42).

A product PR gets the same heal on its own base (OMN-19998, `landing_controller.contract_heals`), before the
decision: every open, non-draft PR outside change-control that reads conflicting at its live head and is not red, through
the same `heal_window` and `heal_window_branch` on the PR's own base. `git merge-tree` in the repository's canonical
clone names the conflicting paths first, so a conflict outside `contracts/*.yaml` is refused before any worktree is
made and stays the workers'. A healed PR is shown to the node pending, merge state `unknown`, at the head it replaced, so the node sends
it no conflict worker that tick (`contract_healed=<n>`, `contract_heal_refused=<n>`, `contract_heal_held=<n>`,
`contract_heal_deferred=<n>`; the receipt's `contract_heal` names each; timing `contract_heal_s`). A PR a lane owns,
a registry claim, a worker lease or an out-of-scope repository is left alone; a head that made no progress is kept
in `contract-heal.json` and tried again when it moves or after `heal_backoff_ticks(fails)` ticks, under the same
heal budget. On 2026-10-18 omnimarket#4107 and #4112 sat green and armed for 99 minutes, DIRTY only on
`contracts/OMN-17427.yaml`, which every OMN-17427 PR appends to: each merge to that contract conflicted the others, an
LLM conflict worker merged `dev` in about an hour later, and the next merge to the contract conflicted the new
head again before it landed. Both conflicts were append-only unions.

A PR the snapshot read clean can conflict in the same tick, when a sibling the tick merged first appended to the same
contract. So a product PR whose merge GitHub refuses with `Pull Request has merge conflicts` gets the same heal in that
tick (`landing_controller.merge_conflict_heals`, after the window heals): one `contract_heal` row with
`merge_refused: true`. It shares `contract-heal.json`'s backoff with the heal
before the decision (and never prunes that file's other entries). No heal starts when the heal budget would outrun the
tick budget; that PR is `deferred` and the next tick heals it. Other merge failures, drafts, change-control companions
and leased or owned PRs are left alone. On 2026-10-18 tick 3106 merged ops_tooling_pkg#835 and #836, both appending to
`contracts/OMN-17427.yaml`, then GitHub refused #837 (head 8f3256b9169b), whose only conflict was that contract. No
tick read it DIRTY until the next one, about twenty minutes later, so it sat green past the 30-minute bound.

A live heal runs as a detached job (OMN-19998, `landing_github.heal_job`: `landing_github.py heal-job` in its own
session, its files under `worktrees/OMN-19998-landing/heal-jobs/`, its worktree `<repo>-<n>-healjob-<head8>`, which
the leftover-`-heal-` cleanup never removes). The commit's hooks get `LANDING_HEAL_JOB_TIMEOUT_S` (default 2400). The
tick waits `LANDING_HEAL_JOB_WAIT_S` (default 10 s; 180 s until ticks 7094 and 7096 spent it whole on 2026-11-06) for a job
it started, and a job still running is outcome `running`: the node sees that PR pending, as it sees a healed one, so no
conflict worker goes on top of it. A later tick reads the result and does not wait on the job. At most `LANDING_HEAL_JOBS_MAX` (default 2) jobs run at once; past that a heal is `deferred`. A job that ended with
no result is an `error`, which takes the backoff. pre-commit's merge mode checks every file both sides changed. On
2026-10-18 the merge of `main` into plugin-tooling-pkg#938 (41049a9ff204) brought `.pre-commit-config.yaml` in changed
on both sides, which selects nearly every pytest hook, and the commit ran past 10 minutes. Before this, all 16 product-PR
heals in `decisions.jsonl` were refused `the commit's hooks ran past 180s` and none healed. #938 and #946
(0ba9b863ffad) sat green and DIRTY on one append-only contract for hours.

A heal commit that a hook fails is an `error` that names the hook (OMN-19998, `landing_github.commit_failure`): it leads
with the failed hook ids from pre-commit's `- hook id:` lines and the first lines of the first one's output, and the
commit's whole output stays beside the heal worktree in `<worktree>.commit.log`, which the error names. The error used to
be the last 200 characters of the output, the hooks pre-commit skipped after the failure, which the job then cut to its
first 200: omnibase_infra#5165 (5b0e19cbdfbb) and #5167 (c73afc024e9c) sat green and DIRTY only on
`contracts/OMN-17427.yaml` on 2026-10-20 while their heals ended `...Scheduled scripts are covered by unit drift
(OMN-20037)......`, one of 75 such errors from 2026-10-18 with no product-PR heal ever pushed, and no record named the
hook.

A repository whose heals keep failing is suspended (OMN-19998, `contract-heal-repos.json`, shared by both heals). From
the first contract heal on 2026-10-18 to 2026-10-20T04:09Z, 70 product-PR heads reached a detached heal and about one
pushed a heal commit; 45 ended in an error (35 commits whose hooks exited 1, 10 git calls past their timeout), and each
held its PR pending to the node while it ran (median 18, p90 74 minutes). omnibase_infra#5160 and #5169 read DIRTY at
tick 3307 and got their conflict workers only at ticks 3309 and 3310. After `LANDING_CONTRACT_HEAL_REPO_TRIP` (default
2) heals in a row fail in one repository (an `error`, or a commit killed past its budget; a conflict the union cannot
take does not count), each of its targets is `suspended` (`contract_heal_suspended=<n>`): not healed and not pending, so
the node sends the conflict worker that tick, and no heal budget is spent on it. One probe heal runs
`heal_backoff_ticks(fails - trip + 1)` ticks after the last failure, and a healed head lifts the suspension. A heal
still running is read whatever its repository's state, so no conflict worker races a heal job about to push.

## A PR the batch window declined is re-driven when the window merges (OMN-20042)

The effects runtime declines a PR that arrives while its repository's batch window companion has CI in
flight: the PR head's `occ-autobind / outcome` check run reads `DECLINED ... reason=skip:WINDOW_IN_FLIGHT
... batch window companion: OCC#<n>`, and promises the PR binds on a later rebuild. Nothing ran that rebuild
for the declined PR, so it waited with no companion until a lane or a fix worker hand-authored one (on
2026-10-02, 141 PR-hours in 24 hours; 119 of 182 blocked worker exits). Each tick, for a landable PR (open,
not a draft, no hold) with no `Evidence-Source` companion whose newest
outcome on its current head is such a decline, the controller reads the decline once per head and outcome
time, and once the window it names reads merged or closed it dispatches the repository's own autobind
workflow (`call-occ-autobind.yml`, `workflow_dispatch` with `pr_number`, the OMN-14993 replay a lane runs by
hand). It writes no evidence and opens no companion. A PR is re-driven once per head and window, at most
three times per head (stranded PRs re-driven together can be declined again behind the next window, which
then earns one more dispatch when it merges). While the producer owes the PR its binding (the window is still open, or a
re-dispatch has had no newer outcome for under 30 minutes), a PR red only on the change-control cascade gets
a gate suspension, so no fix worker hand-authors a companion in the meantime; a real red beside the cascade
keeps its worker. Reads and dispatches share the quota governor's cap
(`landing_facts.quota_cap`). The tick line carries `autobind_redrive=<n>`, `autobind_window_wait=<n>` and `autobind_gated=<n>`,
the receipt's `autobind_redrive` names the PRs, `decisions.jsonl` logs `autobind_redrive` rows, and
`autobind-redrive.json` holds the per-head state. The logic is the `autobind_*` functions of `../merge-drain/scripts/landing_github.py`.

## Held PRs are reported, never armed or merged (OMN-20249)

A person's hold beats a green head. The controller gives a PR the `hold` suspension, so the decision
node neither merges it nor sends it a worker, when any of these is true at the tick's live read:

- its most recent auto-merge event is a disable made by a person or a lane (GitHub's own disables on
  close and on convert-to-draft record no decision). Re-arming it by hand writes a newer enable event
  and lifts the hold. The rule is the auto-merge workflow's own arm gate (OMN-18179);
- it carries any label of the hold family. For the controller that includes the auto-merge arm-gate
  label, because the controller's merge on a green head is what an arm would do (pr-land, a lane's own
  landing path, still reads that label as never-arm, merge on the exact head);
- a ledger row names it with report-only or held-for-review wording, in the clause that mentions the
  PR or in a row whose `pr=` cell names it (the merge-drain hold check, `REVIEW_HOLD_RE`).

Who wrote the PR holds nothing: a collaborator's green, non-draft PR is landed like the operator's
(RULING 2026-10-14T02:24:46Z, OMN-20249), and a PR that is not ready is a draft.

A worker re-reads its PR live before its engine starts (`landing_worker_run.hold_check`): a hold placed
after the tick's read stops it with exit 78 (`LANDING-WORKER-HELD`), no engine, no prompt and no result,
and its prompt forbids arming, re-arming or merging a PR that became held mid-run. The incident:
omniclaude#2449 was disarmed by its lane at 2026-10-01T00:55:44Z to wait for a review, and worker
landing-L588 re-armed it at 01:53:50Z on a green head, which merged it at once.

## One repository-scope setting (OMN-17427)

The repositories our lanes may not work in are one file, `skills/merge-sweep/sweep_scope.json` (`out_of_scope`:
repo -> the ruling or relayed operator message that put it there; today `infra_repo`, `omnigemini`
and `omnicursor`). The merge sweep, this controller and the merge pulse read that file and no list of their own;
the controller reads it through `sweep_rules.load_out_of_scope` (`landing_controller.read_repo_scope`). A
repository in it:

- gets no facts (`Snapshot.excluded`), so the node sends it no merge, fix worker or cause lease, and no PR of it is
  read live; the escalation stage drops it from its candidates;
- is lifted back only for the PRs an OMN-20074 ledger RULING names (the section below), read and
  landed like any PR but given no worker; every other PR of it stays unread, and leaving the scope is an edit to the file;
- joins the node's fixer hold (`Snapshot._scoped_hold`, printed as `fixer_hold=`);
- has every open lease, per-PR or cause, revoked at the next tick (`revoke_out_of_scope`; a RULING-lifted PR keeps its): the node records
  `timed_out reason=revoked` with the ladder unchanged and kills the worker, and the tick line says
  `scope_revoked=<n>` and `out_of_scope=<repos>` (receipt: `scope_revoked`).

The controller does not draft, close, label or comment on a PR for being out of scope: it ignores it. An unreadable
file stops the tick (`UNKNOWN`), because an unread scope is never an empty one. A ledger HOLD `scope=fixer` stays the
temporary, per-repository switch; the file is the standing one. Tests: `tests/test_repo_scope.py`.

## A ruling lifts the repository exclusion for named PRs only (OMN-20074)

The controller never lands a PR of an excluded repository (`landing_facts.EXCLUDED_REPOS` and the drain
map's skip and park sets). A ledger row lifts that for the PRs it names and no others: a
RELEASE row (the ledger grammar needs its `re=`: the id of the row that carried the ruling) with
`exclusion=lifted`, the PRs in its `pr=` cell (`repo#n`, comma separated) and `ruling=<ts>` citing a
RULING row in the ledger, or a RULING row carrying `exclusion=lifted` and `pr=`
itself. A message, a hold, a RELEASE citing no ruling, and a ruling that only names the PR in its text lift
nothing. The named PR is read, gated and landed like any PR; every other PR of the repository stays
excluded (`landing_ledger.excused_prs`, the `excused_prs` argument of `build_pr_facts`). The row is read
from the seven-day ledger window, so it lifts nothing once it ages out. An `after=<repo#n>[,<repo#n>]` cell orders the lift (OMN-21599): the
row lifts the exclusion only once every PR it names is merged (read from the watcher state; a closed-unmerged,
unknown or unreadable PR, and an `after=` cell that names no PR, keep the PR excluded). The case: RELEASE
2026-10-30T18:17:49Z lifted the ops_tooling_pkg exclusion for ops_tooling_pkg#1213 with
`after=omnimarket#4607`; the cell was prose to the reader, #1213 merged at 18:53:51Z with #4607 open, and the strict
lab host table loader refused the Mac's table until #4607 landed. The case: RULING
2026-10-14T14:02:35Z lane=orchestrator-31d9 lifted the registry_root park for registry_root#461, the change-control
caller removal, only; RULING 2026-11-04T21:10:32Z lane=orchestrator-31d9 later unparked registry_root permanently.

## The goal's verdict admits a private-repository PR without a per-head RELEASE row (OMN-22798)

RULING 2026-11-06T23:06:27Z lane=orchestrator-31d9 replaced the per-head RELEASE row for private-repository PRs with an
automatic in-scope check. The scope file's `goal_admitted` map (`merge-sweep/sweep_scope.json`, beside `out_of_scope`, read by
`read_scope_admission`) names the out-of-scope repositories it covers, today plugin-tooling-pkg. After the ledger read, each
tick runs `scope_admission` (node_idle_slot_fill_effect) over the goal's own verdict (`landing_goal_read`: the goal_scope
overlay's lists, an in-scope repository, or the ticket rule's chain to a root, the same read the goal check and the lab fill
use): the operator's own PR of a `goal_admitted` repository the goal admits is lifted out of the exclusion as a RELEASE row
would lift it (`scope_admitted=N` on the tick line); one the goal does not admit stays out; a paused one stays out whatever a
RELEASE row says; a draft (the route a HOLD takes) is never judged; and a RELEASE row citing a ruling still admits an unlisted
PR (`release_admitted=N`). An unreadable map lifts nothing (`scope_admission_unread=1`, `SCOPE-ADMISSION-UNREAD` on stderr).
Each decision is one row of `admissions.jsonl` in the state dir (`event` admitted, kept_out or error; `pr`, `head`, `via`
list, ticket, release, paused, unlisted or unread; `exclusion` lifted:scope, lifted:release, held), written only when a PR's
verdict, route, exclusion or head changes (`admissions-state.json`), and counted as `admission_events=N`. The case: fifteen
plugin-tooling-pkg PRs released after 13:55Z on 2026-11-06 sat unmerged because each RELEASE cited a ruling stamp no RULING
row carries (`tests/test_landing_scope_admission.py`).

## A refusal reaches the hand-off lane's parent (OMN-23242)

On 2026-11-08 the controller wrote 181 CRITERIA_DRIFT merge deferrals and 52 PRs ended kept_out, against 21 controller MSG rows,
none about drift; plugin-tooling-pkg#1753 was deferred 73 times between 01:05Z and 23:55Z before any brief named the drift.
When a tick defers a merge (a `decisions.jsonl` row, kind merge, outcome deferred, other than a pipeline tick-budget deferral or
the strict base's one-merge-per-tick queue order) or the goal admission keeps a PR out (`admissions.jsonl` event kept_out) and the
PR has a hand-off MSG row on the ledger (`to=landing-controller`, a `pr=` cell), the controller appends one MSG
`from=landing-controller` to the `parent=` of that lane's newest CLAIM naming `pr`, `head`, `gate` and the detail (for
CRITERIA_DRIFT the ticket and the drifted criteria). Gates: CRITERIA_DRIFT, CRITERIA_UNREADABLE, CRITERIA_CHECK_NOT_RUN,
RELEASE_PREMISE, NODE_HANDOVER, MERGE_DEFERRED and KEPT_OUT. A lane whose CLAIM names no parent lane (a ticket id is not a lane),
or a PR with no hand-off row, is told nothing. Once per PR, head and gate: `parent-msgs.json` in the state dir keeps what was
written (a failed append is not recorded and retries next tick), so a settled tick appends nothing and reads no ledger; a new
head or gate writes one more. Each write is a `kind parent_msg` row in `decisions.jsonl`
(`tests/test_landing_controller.py -k parent_msg`). The row's id is its own stamp and `landing-controller`, the ledger
grammar's shape, and a second message in one tick takes the next second (OMN-19998: an id ending in the gate was refused
`does not end in this row's from=` on every tick from 2026-11-10T19:58:44Z for omnimarket#5746).

## Worker edits to judging paths stay visible (OMN-20768)

The operator standing rule is no required human review until there are full-time engineers. The automatic
judge-review hold violated that rule and is removed. A worker touching a judging path creates an observation:
it adds no label, disarms nothing, changes no CI verdict or suspension, and does not refuse merge, rerun or
update-branch. The controller lands through the normal decision path.

Each tick reads worker results whose head moved off the dispatch head against the canonical clone
(`landing_github.worker_judge_touch`, git reads only). The worker's own change compares the +/- lines of
`merge-base(head, origin/<base>)..head` against the dispatch head, so a path introduced only by a base merge
is excluded. Judging paths include `.github/`, CI scripts, check config and check sections in `pyproject.toml`
or `setup.cfg`, `tests/ci/`, fixtures, `conftest.py`, and baselines or allowlists. An unreadable diff is also an
observation, with its read failure recorded.

The decisions row `judge_touch` names the head, lease and all touched paths. One FRICTION row per observation
carries `ticket=OMN-20768`, `class=worker-touched-judge`, `pr=`, `head=`, `lease=`, `paths=`, and a zero required-review
cost. Failed note writes retry, including after merge or closure, without delaying landing. Current observations live in sidecar `judge_touches`
and receipt `judge_touched`; the tick line carries `judge_touched=<n>`. Records drop after merge or closure once the note is written;
the decisions and ledger evidence remain. The worker brief still forbids weakening checks to hide a product
failure and directs a real check defect to a separate PR that names the check it fixes.

## The judge-review voter is retired (OMN-21017)

Judge touches no longer dispatch review runs or wait for a verdict or person. Existing review leases are
revoked and their results discarded without escalating the fix-worker ladder. There is no review retry limit
that turns into a human gate.

On the first tick after the receipt-gated reinstall (Install and status), sidecar `judge_holds` migrates into
non-blocking `judge_touches`. The sidecar and receipt retain those PRs as `judge_formerly_held`; receipt `judge_legacy_labelled` lists the
ones whose current read still carries the old label, and `judge_held` is empty.
The obsolete `hold:needs-review` label is ignored by controller facts, the worker's hold re-read and the close
path. A disable under that label, or a controller disarm recorded in the migrated record, cannot perpetuate
the removed gate. A record written before `disarm_event` existed carries only `disarmed: true`, which the retired
hold set after its own disable, and counts as that disarm (`landing_facts.retired_judge_disarm_of`, OMN-20864):
omniclaude#2701 stayed on `hold` through three hand-offs on 2026-10-12 and 2026-10-13 because its newest auto-merge
event was still the controller's disable of tick 2092. A record with `disarm_event: false` still holds.
Other hold labels, ledger holds and lane ownership keep their existing behavior. The label
can remain as historical metadata; no person has to remove it and no special re-arm is needed to release it.

## Shared red causes: the controller side of the red-PR fixer (OMN-20417)

The decision node groups red PRs that fail one check with one failure signature into a cause and leases one
cause worker for it (the rules are the node's). The tick turns on its side only when the pinned node declares
the seam: every tick reads `landing_decide_bridge.py --capabilities` from the installed node, and under a node
without it (the pin held b10129a51 until OMN-20413) the tick reads no annotation, passes no new fact, keeps a
lane's PR `hold` and keeps an always-pass dod-verify red in the change-control cascade. Nothing is switched by a
flag. The pin now names omnimarket f73d589e161f3ff5eee39ac60ca96df8469e80fc (the merge of OMN-20744,
including OMN-20746's shared cause signature), which declares the seam,
so a reinstall at this pin turns the cause path on; `tests/test_landing_controller_causes.py` runs the pinned
node itself on the tick-725 snapshot and on eight PRs the node parked `escalation_exhausted`.

Under a node with the seam the tick:

- reads each red PR's failing checks' first failure annotations (`statusCheckRollup.contexts(first:100)` with
  `annotations(first:3)`, six PRs a GraphQL request, inside the quota governor, cached per head and red set in
  `annotations.json`); an unread PR never clusters and is counted in the receipt's `annotation_reads`;
- gives a check read with only the runner's generic "Process completed with exit code" line a stand-in annotation
  keyed on the check, the base branch and the base branch's tip (`landing_facts.generic_annotation_note`, OMN-19998),
  so PRs of one repository red on that check at one base tip share a cause instead of each getting a worker; with
  the tip unread, or another red check of the PR carrying a failure line of its own, the check stays unread;
- reads a `repo-evidence / dod-verify` red whose annotation says "always-pass" as the PR's own red, not the
  cascade, so the PR no longer waits on its companion (the node suppresses per-PR workers for cause members);
- passes `owned` for a lane's PR (no per-PR worker, no merge, may join a cause; a person's hold stays `hold`),
  `gate_since` per PR (kept per head and gate kind in the sidecar), the fixer HOLD scope, the floor alarm's
  breach set (its last `runs.jsonl` row, unread when older than 30 minutes: `floor_state=unread`) and the cause
  owners (an open CLAIM with `cause=`, or `check=` and `repo=`, live in the last 45 minutes, not a dispatcher);
- spawns a cause worker through the same lease, tag, kill and release path as a PR worker, after writing its
  relay CLAIM (`lane=landing-cause-L<lease>`, `cause=`, `check=`, never `pr=` or `repo=`), and writes the
  lane's TERMINAL when the lease is released; no CLAIM, no worker;
- translates the node's legacy `escalate_operator` action into a local `PARKED` evidence receipt, with
  cause, members, attempts and automatic retry conditions. Every tick rebuilds `evidence.json` from open parks
  and stale unacknowledged THROUGHPUT STALL rows (`OWNED_STALL`, OMN-20852), retaining the repository, PR and
  next action. The tick line carries `park_evidence=<n>` and `stall_owned=<n>`. No park asks the operator for a
  RELEASE row or sends a MSG. The sidecar's `retry_waits` and `cause_retries` retain observed base tips, clocks
  and per-head budgets across restarts.
- vets cause blockers (OMN-20068): a member ref, an operator_decision without rule_ref + rule_gap, or one
  decided by `landing_facts.STANDING_RULINGS` (including RULING 2026-10-12T22:02:36Z) becomes cause_not_shared
  so members take the per-PR path (`cause_refused=`). A per-PR operator_decision likewise becomes blocked
  (`decision_refused=`). A legacy park with such a last result is released (`cause_released=`). A park whose
  attempts returned only external_blocker/unparseable is `CONTROLLER_DEFECT` evidence (`cause_defect=`),
  never an operator question.

A PR the node parked `escalation_exhausted` (every rung failed on its head) is covered by a singleton cause on the
next tick, so it is worked instead of only reported (OMN-20413 AC2; this is what the merge sweep's escalation
lane did). The caps are the node's: two cause workers a repository and four across the fleet, so a tick with
eight such PRs leases four causes and the other four wait for a slot; the node keeps listing a covered PR in
`degraded`, which keeps the tick DEGRADED until the park clears.

A park whose only red is a merge-queue ejection forms no cause: the synthetic queue check carries no failure
annotation, so the node keeps it parked with no worker, and the ejection stops a merge (OMN-20864). On 2026-10-13
omnibase_infra#4911's last rung pushed e7bc331c, which went green on its own checks, was ejected too, and was parked
there for good. The controller now re-admits such a head (`landing_facts.park_queue_retry_next`): an open PR parked at
its live head, green on its own checks, red only on the ejection and not base-blocked waits from the tick it is first
seen, and once its base tip moves or `PARK_QUEUE_RETRY_MINUTES` (60) pass, the ejection reads as lifted, the way a
lifted base block does, so the node merges (enqueues) it on the normal path with holds, gates and the runtime token
unchanged. It stays re-admitted until the queue takes it and removes it again, which starts a new wait. A head gets
`MAX_PARK_QUEUE_RETRIES` (2) re-admissions; a new head starts its own. The base tips are one batched read, made only
while such a head exists. The sidecar key is `park_queue_retry`, the receipt's `park_queue_retry` names the re-admitted
PRs and the tick line gains `park_queue_retry=<n>`.

The fixer's kill switch is a HOLD row with `scope=fixer` and `repo=<repo>` or `repo=all`; a RELEASE naming its
id lifts it. It stops the fixer's workers in that scope and holds no PR, so merges, reruns and branch updates
go on (drain_map's hold check skips it). Every released lease, PR or cause, appends one `cost.jsonl` row
(worker minutes from the lease stamps, host, and the worker's `usage.json` as `usage_source=MEASURED`,
`cost_basis=cli_reported`, else `usage_source=UNKNOWN`). Every receipt carries `interactive_claude`, the
`claude` processes with a terminal on the controller host. Tick-line cells under the seam: `causes=`,
`cause_leases=`, `cause_members=`, `cause_exhausted=` and, while a fixer HOLD is in force, `fixer_hold=`.

## Bus owner (OMN-20747)

Every tick reads `pr_lifecycle_ledger_entries` in the dev lane's `omnidash_analytics` database with one ssh
read and a `READ ONLY` transaction. The postgres container is resolved by the `omnibase-infra` compose labels;
the `h907` row's `ssh` target comes from the shared lab host table, including an unavailable worker-placement row.
`LANDING_BUS_CLAIMS_SSH` overrides that target.

A red PR whose current-head decision names a claimed bus owner gets the worker gate and never joins a controller
cluster. A bus-owned cause gets the same rule as a lane's cause CLAIM: no cause worker and no member worker.
With `ci_red_triage.act` false the bus writes no claim, so nothing is deferred until S6 flips a class.

A claim is a lease (OMN-20744 AC-M6). The read selects each row's `next_check_at` as `lease_expires_at`, which
omnimarket's reducer stamps from the TTL in its contract (`owner_claim_lease`). A claim holds only before that
expiry. An expired claim, such as one whose owner's TERMINAL the ledger refused, holds nothing, and neither does
a claim with no readable expiry. So the controller dispatches for that PR again.

The receipt's `bus_claims` reports the read and `bus_deferred` lists the applied PR and cause deferrals with their
owner key, claim, run id and decision key; the tick line gains `bus_deferred=<n>` when nonzero. An unread
projection keeps the controller's dispatch, prints the reason to stderr, records `bus_claims.read=false` with
the error and says `bus_claims=unread` in the tick line. Rollback is a git revert.

## The runner class is the bus path's (OMN-20748)

At the pinned omnimarket commit `ci_red_triage.act` turns the runner class on, and only it. The bus reruns a runner
head's failed Actions runs once and claims the owner `<repo>#<n>@<head>:rerun`. The controller's runner class is its
own `runner_saturation` and `cancelled_producer` reds with red checks (`BUS_RUNNER_CLASSES`); a `reviewer_pool` red
keeps the reviewer-slot rule. For such a red (`bus_runner_step`):

- `spent`: the bus holds this head's rerun claim. The controller never reruns the head (no node rerun, cascade rerun
  or stale step) and presents the red as the PR's own, so a red that survives the bus's rerun goes on to a worker.
- `await`: the bus has not decided this head and the red is under 30 minutes old (`BUS_RUNNER_WAIT_MINUTES`). The
  PR gets the gate `bus_owner:runner@<head>`: no rerun, no worker.
- `declined`: the bus decided without a rerun claim, or never decided a red that is 30 minutes old. The controller's
  own dispatch is the backstop. An unread projection keeps the controller's dispatch too.

A rerun owner's claim never defers a later red of the same head. The receipt's `bus_runner` maps each runner-class
PR to its step and the tick line gains `bus_runner_<step>=<n>`. Rollback: set `ci_red_triage.act.runner` false in
omnimarket, then revert the pair (this change and the omnimarket one its pin names).

## The landing node arms a handed-over repository; the controller is the backstop (OMN-20750)

Plan S8, pulled forward one repository at a time. For a repository the node hand-over configuration names, the
controller no longer merges a green PR on first sight (on a merge-queue repository the merge is the enqueue that
pre-empted the landing orchestrator's arm). The configuration is machine-local, never shipped: the JSON file
`node-handover.json` in the controller's state dir (`~/.local/state/omni/landing/` on the controller host), or the
file `LANDING_NODE_HANDOVER` names:

```json
{"repos": ["omnimarket"], "wait_minutes": 15}
```

No file is the default: no repository is handed over and the controller lands every repository itself. A file that
is not exactly that shape (a repository named with no `wait_minutes`, a wait under 1, an unknown key) hands nothing
over; the receipt's `node_handover.error` says why and the tick line gains `handover_error=1`.

For a green, unsuspended PR of a handed-over repository the controller keeps a clock in its sidecar
(`node_handover_clock`, `repo#n@head` -> the tick that first saw the head green; a new head starts it again, a merged
or closed PR drops it) and takes one step (`handover_step`):

- `await`: unarmed and inside `wait_minutes`. The pinned node sees the PR pending, so it emits no merge and never
  gives the PR the runtime token (a held omnimarket PR never holds an omnibase_infra runtime PR back).
- `armed`: armed or queued at this head. The node's or GitHub's arm stands; the controller never merges it.
- `backstop`: unarmed for `wait_minutes` or more. The node sees the PR as it is and the controller merges it. The
  `decisions.jsonl` merge row carries `handover: backstop`, `handover_elapsed_min` and `handover_since`, so node arms
  and backstop merges count apart.

A behind or conflicting head keeps the node's update-branch and worker. Any merge of a handed-over repository the node
emits anyway at a held head is deferred by the action filter (`handover_hold`), and the end-of-tick strict-base merge
never merges one. The receipt's `node_handover` carries the configuration and each PR's step, and the tick line
gains `handover_<step>=<n>`. Rollback: delete the file (the next tick lands the repository itself), or revert.

## A head held by stale cancelled check copies (OMN-20508)

GitHub reads `mergeStateStatus=BLOCKED` on a head whose required contexts are green when a cancelled copy of a
required name stands beside the newer ones (omnibase_core#1869 sat 15.7 h so, and got nine fix workers that could
fix nothing). The collector reads `merge_state` `blocked` for BLOCKED (after the conflicting, behind and clean
branches) and `cancelled_checks`: the sorted names whose newest copy on the live head is completed and cancelled,
with no queued or running copy and no newer success, from the watcher record's `ci.cancelled` (else from its
`ci.runs`; a same-second tie with a non-cancelled copy leaves the name out). A name that failed stays in
`red_checks`, so the node sees a real red as one. A rollup red with cancelled copies and no failed name is
`cancelled_producer`, not `product`. The tick sends `blocked` and `cancelled_checks` only when the pinned node
declares all of them (`landing_facts.stale_refresh_support`, from `--capabilities`: `cancelled_checks`, the
`blocked` merge state, `stale_refresh_exhausted` and `max_stale_refreshes`); under any older node `blocked` goes
as `unknown` and no `cancelled_checks` is sent, so the facts are what they were. A head the watcher record is not
at has an empty `cancelled_checks` (never guessed). The node's own state record then carries `stale_refreshes`,
which the controller keeps because it writes the node's `next_state` whole.

## A required context that never started is the PR's own red (OMN-19998)

omnimarket#4138 at head 248f3402a610 had 73 completed check-runs and none failed, so the rollup read SUCCESS, but four
contexts required on omnimarket:dev (`CI Summary`, `Customer Path Boundary (OMN-18012)`, `JS Toolchain Hermetic
(OMN-18012)`, `Wire Compatibility Gate`) had no copy on the head: the PR's own `ci.yml` change kept those jobs from
starting, and GitHub read the head BLOCKED. The controller read it green, update-branched it six times
(2026-10-18T22:52:35Z to 2026-10-19T01:25:37Z) and then gated it `lab_unproven`, which the lab prover never takes from
a BLOCKED head, so no worker went to it. `node_landing_blocked_head_compute` (`src/plugin_tooling_pkg/nodes/`) now
names the required contexts with no copy on a head that GitHub reads BLOCKED, the watcher reads GREEN with nothing red
or pending, and whose check-runs all completed at least `ABSENT_SETTLE_MINUTES` (20) before the tick. The base's
required set is read only for such a head, and an unread set names nothing. The facts carry those names as the PR's
`product` red (`red_checks`), so the node sends the fix worker under the usual worker gates, and no lab gate, merge or
update-branch holds the head. The receipt's `landing_classes.absent_required` maps each such PR to its names. The same
node holds the cancelled-required rule below (`cancelled_required_jobs`).

## Stale summaries, main-based PRs and pending checks get no worker (OMN-19998)

On 2026-10-05 the controller sent three or four fix workers to each of several PRs whose fix was not in a worker's
brief (FRICTION 2026-10-05T16:27:13Z lane=drain-9143-m4-1614). These classes decide them in the controller,
from the PR watcher's record at the live head, before the node: the node sees such a PR pending or gated, so it
sends no worker. The functions are the `stale_*`, `retarget_*` and `pending_required_of` of
`../merge-drain/scripts/landing_facts.py`; the tick's side is `class_plan` and `class_actions` in the controller.

- **Stale summary.** `CI Summary` is red, no other check failed or is still running, every other red name was
  cancelled or skipped, and some sibling was cancelled or skipped (omnimarket#3423, #3424 and omniclaude#2551
  landed 4 to 25 minutes after a failed-jobs rerun). The controller reruns the failed and cancelled jobs of the
  head's newest bad run of each workflow (`gh run rerun --failed`, the whole run when that is refused) once per
  head, then update-branches once per head; a skipped matrix row whose name was never expanded (`${{ ... }}`,
  omnibase_infra#4576) clears only on a fresh head, so it starts at the update-branch, and gets the one rerun
  after it when the update-branch left the head unchanged or the PR's refreshes are spent (omnibase_infra#4745
  head 6117d264: the branch was current, and a failed-jobs rerun of run 37839812567 cleared it; OMN-20413).
  Update-branches are counted per PR (`MAX_STALE_REFRESHES` in the node, 2), so a head that stales again cannot loop. With both spent, the node decides and
  a red head gets its worker. Tick cells `stale_rerun=` and `stale_refresh=`; sidecar key `stale_refresh`.
  A provider incident (`INCIDENT_MIN_RUNS` in the node, 12, or more distinct checks cancelled or `startup_failure`, which counts
  as no runner only then) reverses the two steps (`refresh_first`): the one rerun can land inside the incident, so
  the update-branch goes first, counted against the same `MAX_STALE_REFRESHES`, and the rerun stays behind it.
- **External verdict rerun (OMN-20864).** `../merge-drain/external_verdict_checks.json` names required contexts
  graded from outside the PR. Every source's newest admitted run must be green, later than the PR's red copy,
  and inside its maximum age. The controller reruns just that job (`gh run rerun --job`): once per job,
  `MAX_EXTERNAL_VERDICT_RERUNS` (2) per head, with one read of each source per tick inside the quota cap. The PR is
  presented pending that tick, so no worker is sent. Tick cell `external_verdict_rerun=`; sidecar key
  `stale_refresh` (steps `external_verdict:<job id>`).
- **Stale required copy.** GitHub reads the head `BLOCKED` with a failed rollup while the watcher, which reads each
  check's newest copy, reads it green: no red, nothing pending. A superseded run on the same head keeps an old
  failed copy of a required context (the record's `stale_red`, run ids per name). omniclaude#2621 head 671f3c93:
  duplicate CI runs 37847544038 and 37850611450 kept failed `CI Summary` copies, workers found nothing to fix
  until the PR was `escalation_exhausted`, and a failed-jobs rerun of the two runs cleared it (OMN-20413). The
  controller reruns the failed jobs of one such run a tick, newest first (`gh run rerun <id> --failed`, the whole
  run when that is refused; a run at another head or still running is left alone), because runs of one workflow
  rerun together cancel each other (OMN-20038). Each run once per head, at most `MAX_STALE_COPY_RERUNS` (4) per
  head; then the node decides. An unread required set reruns nothing. Tick cell `stale_copy_rerun=`; sidecar key
  `stale_refresh` (steps `rerun_run:<id>`).
- **Retarget.** A PR based on `main` in a repository whose landing branch (the watcher's default branch) is `dev`,
  from a head `main` does not take (not `dev`, `promotion/*` or `hotfix/*`), outside the operator-gated `main`
  repositories. It is gated, so it gets no worker and is never merged into `main`. The operator's own and bot PRs
  are retargeted (`gh pr edit --base dev`, then update-branch; at most twice a head); another author's PR gets one
  comment asking for the retarget, and nothing else. A held, owned or leased PR is gated and left alone.
  omnimarket#3431 took workers 2952, 2956 and 2959, each of which could not change a base. Tick cells `retarget=`,
  `retarget_ask=` and `retarget_wait=`; sidecar key `retarget`.
- **Pending.** A red PR whose required contexts are still running is gated until they finish (worker 2945 found
  only `CI Summary` pending on omnibase_infra#4576 and wrote no result). The required set is the base's branch
  protection plus its rulesets (two REST reads, cached six hours in `required-contexts.json`, an unreadable one 15
  minutes); unread, any pending check holds (fail closed). A context running longer than `PENDING_STUCK_HOURS` in the node (2)
  holds nothing, so a stuck run never parks a PR. Tick cell `pending_gated=`.
- **Required-context refresh (OMN-20780).** The pending class reads a base only when a red PR asks, so a repository
  with no such PR let its `required-contexts.json` entry age past the ruling audit's six-hour bound
  (`stale-cache`). Each live tick now re-reads the landing branch of every registry repository whose entry is
  absent or four hours old (`REQUIRED_REFRESH_AFTER_S`), oldest first, at most four per tick
  (`REQUIRED_REFRESH_PER_TICK`) and out of the cap the class actions left. A failed refresh keeps the good entry,
  marks it `refresh_failed_at` and waits 15 minutes. Summary key `required_refresh` (`refreshed`, `due`, `deferred`); tick cell `required_refreshed=`.

Reads and actions share the quota governor's per-tick cap (`landing_facts.quota_cap` with `QUOTA_READS_TOP`): a
rerun (of the head's runs, one superseded run or one external verdict job) or a retarget costs 2 calls, an
update-branch, a comment or a source read 1, a required-context read 2. What the cap leaves
for the next tick is a `deferred` decisions row and the cell `class_deferred=`; those PRs got no worker either.
The receipt's `landing_classes` names every PR per class; `decisions.jsonl` logs `stale_rerun`, `stale_refresh`,
`stale_copy_rerun`, `external_verdict_rerun`, `retarget` and `retarget_ask` rows. A PR the node acts on itself this
tick (an update-branch of a behind head) is left to that action. A real red beside the summary is never stale and
keeps its worker.

## The cause worker: merge-drain as the red-PR fixer (OMN-20416)

A worker has a second subject besides a PR: a **cause**, the set of red PRs in one repository that fail one check
with one failure signature. `../merge-drain/scripts/landing_worker_run.py` runs it from a cause brief
(`brief_class=shared_cause`) with the same lease, tag, placement and relay rows as a per-PR worker. The brief
carries `cause_key` (`cause:<owner>/<repo>:<sig12>`), `repo`, `base`, `pairs` (`check`, `signature`, `annotation`),
`members` (`pr` as `<repo>#<n>`, `head` 40 hex), `base_fails` (true, false or null) and the per-PR brief's lease
fields. The worker checks out a DETACHED `origin/<base>` of the source repository under
`worktrees/OMN-19998-landing/` (a lab host gets the same checkout, fetched by the base head's sha) and follows
`/omni:merge-drain` sections 1 to 4: classify the source (the base head, the gate itself, a sibling pin,
change-control companion contention with the minimal unblock only, or not shared), then fix it once in one PR in
the source repository. It never pushes to a member branch whose owner is not the controller, and lists the members
that need their own change in the fix PR's body.

It writes one result, graded by `landing_workers.read_result`: `cause_fix_submitted {fix_ref, fix_head}` (`<repo>#<n>`
and 40 hex), `cause_not_shared {reason}` (non-empty) or `external_blocker`; anything else is `unparseable`. On a
lab host the fix needs `gh` there, since the worker pushes the fix branch itself. Every worker run, per-PR or
cause, local or remote, also writes `usage.json` beside `result.json` (the engine runs with `--output-format json`):
`total_cost_usd`, tokens and duration with `usage_source=MEASURED` and `cost_basis=cli_reported`, or
`usage_source=UNKNOWN` with every figure null when the CLI printed none.

The pin carries the decision node's cause output (OMN-20415) and the controller carries its dispatch (OMN-20417,
T4): the lease per cause key, the caps, the attempt budget, the park, and reading `cause_fix_submitted` against the
fix PR. They act once the controller is reinstalled at the pin.

A lab host has no PR watcher state, so the cause fix guard (`landing_text.py fix-guard` and `guard-create`) reads
`unreadable` there, and a remote cause worker that followed it stopped with `unreadable-from-snapshot` and opened no fix
(OMN-19998: landing-cause-L11815 on host.example and landing-L11873, 2026-10-19/20, while plugin-tooling-pkg `main` stayed red
on validate-plugin and validator-tests). The guard node's `dispatch_fix_guard`, called by `landing_worker_run.py`, reads the same guard on the controller
host before a remote cause worker starts, writes it to the lease's `fix-guard.json` and puts it in the prompt: `clear`
starts the fix with the `Fix-Check:` and `Fix-Cause:` body markers, `join` reports `upstream_open` on the existing fix,
`owned` leaves it. An `unreadable` dispatch read keeps the local guard commands.

## One merge per tick on a strict base (OMN-20497)

A base that requires branches to be up to date before merging (branch protection's strict required
checks, or a ruleset's strict policy) takes one merge per tick. After the first merge every other PR on
that base is behind, and GitHub refuses its merge with a required check reading `expected`: the
decisions log held 59 such failures on plugin-tooling-pkg `main`, 15 on ops_tooling_pkg, 8 on
omnibase_spi and 1 on omnibase_infra by 2026-10-04. Now, when the node picks two or more merges on one
base, the controller reads that base's setting (two REST reads, only for such a base, cached six hours in
`strict-bases.json`; a failed read is cached 15 minutes and ordered like a strict base), performs the
first merge, and turns the next candidate's merge into an update-branch so its head is current for the
next tick. The remaining merges on that base are logged `deferred`; the node update-branches a behind head
itself. A first merge that fails leaves the base unchanged, so the next candidate is merged instead. A
non-strict base keeps every merge. The tick line carries `strict_deferred=<n>` and the receipt's
`strict_deferred` names each PR.

## One update and an end-of-tick merge on a strict base (OMN-20502)

A strict base takes `STRICT_UPDATE_CAP` (1) update-branches a tick. Tick 743 performed 12 of the node's
update_branch actions on plugin-tooling-pkg `main` (790 s, every one a plugin version bump), and each head
was behind again after the next merge. The candidate the controller turns from a merge into an update comes
first; the node's own update_branch actions on that base wait, logged `deferred` with `strict_deferred`, and
their heads are taken out of the node's `update_heads` before the state write, so the node picks them again
next tick. The updates a strict base keeps run after that base's merges. At the end of the tick, after the
heals, reruns, re-drives and lab step, one batched live read looks at the updated candidate: when it is open,
at the head the update produced, up to date and green on every check, it is merged pinned to that head (a
`merge` decisions row with `pipeline: true`); otherwise the row is `deferred` with `pipeline: checks pending`,
`checks red`, `behind`, `head moved` or `tick budget` (within `PIPELINE_MARGIN_S`, 60 s, of the tick budget).
A runtime-gated or suspended PR is left to the node. The tick line carries `pipeline=<merged>/<read>`.

The receipt's `timing` carries sub-phase keys beside the phase keys: `read_watcher_s`, `read_live_s`,
`read_companions_s`, `read_ledger_s`, `read_runtime_s`, `enrich_ledger_s`, `enrich_runtime_s`,
`enrich_decide_s`, `perform_actions_s`, `perform_merge_s`, `perform_update_branch_s`, `cascade_rerun_s`,
`window_heal_s`, `autobind_s`, `pipeline_s`, `pre_heal_s`, `plan_s`, `merge_conflict_heal_s`, `lab_s` and `clean_green_s` (the last five
named on 2026-11-06, when ticks 7097 and 7099 held 331 s and 375 s no key named). The ledger's hold scan (`drain_map.hold_findings`) skips a
row that never spells the PR's number before parsing its instructions, which leaves every hold unchanged
and cut the ledger read about 85% on a lab host (`tests/test_landing_tick_phase_replay.py`).

## No update chases a base a head does not need (OMN-19998)

On 2026-10-18 the shared red refresh moved eight omnimarket heads onto dev at 18:28Z, 19:59Z, 21:24Z and
22:31Z. Each time the same check (CI Summary over a Hostile Reviewer timeout) went red again on the refreshed head
while dev moved on, so each refresh restarted their CI and none merged. omnimarket dev requires no branch up to date
(strict=False, merge queue ruleset 14745045 disabled). Two rules now stop that loop:

- The shared red refresh skips a member with checks still running on its head (`shared_base: running`). It also
  skips a member the refresh already moved whose red check is red again within `REFRESH_TTL_S` (6 h)
  (`shared_base: recurred`). Such a red is not a stale-base red. `shared-base-refreshes.json` in the state dir
  records each refresh (from head, tip, checks, time). A member never refreshed, or one red on another check, is
  still brought to the landing tip.
- `strict_plan` defers the node's update of a head whose rollup is PENDING or SUCCESS when its base's strict
  setting reads False (`loose_updates`, detail `base <repo:base> requires no branch up to date`). A red head, a
  conflict, a strict base and an unread setting keep the node's update. A merge-queue base already gets no update
  from the node unless its head is red.

## A declared cause fix goes first; a twice-failed PR yields the update slot (OMN-20713)

On 2026-10-07 the fix for a fleet-wide public-repo-hygiene red, ops_tooling_pkg#290, waited about two hours in
the controller's strict-base queue for ops_tooling_pkg. That queue brought one PR up to date per tick in
PR-number order, and the controller kept re-updating ops_tooling_pkg#222, whose CI kept timing out. The
orchestrator held #222, #286, #288 and #289 by hand. A cause lease's result `cause_fix_submitted` names a fix in
`fix_ref`, or an open cause CLAIM (a `cause=` cell, or `check=` with `repo=`) names it in a `fix=` cell as
`<repo>#<n>`, comma-separated for several. The `pr=` cell on a cause CLAIM names the member PRs suffering the
red, never the fix. Any lane may declare one, an orchestrator included, and it lasts while the CLAIM is open. A
CLAIM-declared fix only orders the controller's actions; the decision node never reads it.
The owner read honours that: a PR named only in a cause CLAIM's `fix=` cell (or again in that CLAIM's prose) is
not owned by the declaring lane, so the declaration cannot suspend the fix as owned; the CLAIM's `pr=` field
still owns what it names (`drain_map.declares_fix`, 2026-10-11 FRICTION on ops_tooling_pkg#456).

On a strict base the controller ranks the base's actions: declared fixes first, then the node's order, then
yielded PRs. A declared fix holds its strict base while it acts this tick (a merge or an update_branch), or while
its head's checks are pending and have been for under `FIX_HOLD_PENDING_S` (3600 s). While it holds, every other
PR's merge and update on that base is logged `deferred` with `strict_deferred` and the detail
`cause fix <repo>#<n> goes first (<why>)`; held updates are released in the node's `update_heads`. A fix that
merges releases the base in the same tick, and the next candidate is the one turned into an update. A fix that
is conflicting, closed, red with no action, yielded, or pending past the bound does not hold.

`strict-slot.json` in the state dir records, per PR, the heads the controller's strict-base updates produced. A
fresh head whose checks rollup reads FAILURE or ERROR (GitHub reads a cancelled or timed-out check as FAILURE)
is a strike; a SUCCESS on a fresh head clears the strikes; a head someone else pushed resets them. After
`STRICT_YIELD_STRIKES` (2) strikes in a row the PR yields: its update_branch on a strict base is deferred with
the detail `<repo>#<n> yields the update slot: ci failed or was cancelled on its fresh heads <shas>; it takes
the slot again when its head changes`, and it is skipped when the controller turns a merge candidate into an
update. It takes the slot again when its head changes or its checks pass on that head. A PR alone on its base
takes no one's slot and is not tracked. Each `ticks.jsonl` row carries `strict_order` (per ordered base: `base`,
`first`, `why_first` as `cause fix: cause lease <key>`, `cause fix: cause CLAIM lane=<lane> cause=<cause>` or
`node order`, `held`, `yielded`) and `strict_yielded` (per yielded PR: its `head` and `strikes`). The tick line
gains `cause_fix_first=<n>` and `strict_yielded=<n>` when nonzero.

A declared fix whose merge a gate holds this tick (the criteria check, a hand-over or release hold, or a shared-base
wait) cannot land now and holds no peer (OMN-19998): `perform` sees the fix's deferral before any peer's turn, because
the fix ranks first, so the green merges behind it are made and a held update goes through the base's per-tick update
cap. The fix's own row reads `deferred` with the gate's reason; a fix that acts (updates, or merges) still holds.

## M4 delegation carrier PRs are worked first (OMN-17427)

RULING 2026-10-09T00:28:38Z lane=orchestrator-9f8a: M4 delegation carrier PRs and board reds come first in
landing (operator 2026-10-09: "<removed>"). The class is the carrier tickets of every
criterion in the board's M4 bucket: `MILESTONES` names the bucket of M4 (`deleg` today, so C11 to C17 and C28 to
C32), and no criterion id is listed in the controller, so a criterion the board moves into or out of M4 moves with
it. C8 to C10 are the M4.5 cloud plane, another bucket, and are not in it. It is read each tick from the board's own
data file, infra_repo `tools/beta_board/beta_board_data.py` (`MILESTONES` and `CRITERIA`), through the canonical clone: one local
`git rev-parse` of the file's blob on `origin/<default branch>`, parsed with `ast` (never run) only when the blob
changed, kept in `m4-carriers.json` in the state dir. No GitHub call is made for it. A PR is in the class when its
title cites a carrier. A failed read keeps the last good carriers (`m4_source` starts `stale: `), or with none the
class is empty (`unread: `); the tick is never refused for it. `LANDING_M4_BOARD_DATA` names a data file instead
(tests and a hand run).

The class orders work and lifts nothing. The M4 PRs' facts carry the node's own `process_fix` priority input, which
the pinned node reads only to rank a tick's PRs (after mergeable and unblocked count, before age), so its fix-worker
dispatch under a short worker cap and its merge and update-branch choices reach M4 PRs first. A held, gated, leased,
pending or conflicting M4 PR is exactly as held, gated, leased, pending or conflicting as any other. In the
controller, a strict base ranks a declared cause fix, then M4 PRs, then the node's order, then yielded PRs (an M4 PR
that yields the update slot stays last); outside a strict base each kind of action (merge, update_branch,
dispatch_worker, rerun) is refilled M4 first inside its own positions, so a kill or a close never moves; and the
quota-capped stale-summary and retarget classes spend their cap on M4 PRs first.

Each `ticks.jsonl` row carries `m4_first` (the class's open PRs, those the tick reached first in the order it
reached them, then the rest), `m4_carriers` (the count read) and `m4_source` (the blob read, `(cached)` when the blob
was unchanged, or why it was stale or unread). The tick line gains `m4_first=<n>` when nonzero.

## One ranked PR priority list (OMN-20074)

A merge queue is first in, first out by enqueue time, and the controller enqueued PRs as they turned green; its
cause-fix order ranked one tick's actions only. On 2026-10-15 ops_tooling_pkg#705, the fix for its red base, sat
about three hours behind entries failing on that base. The lane priority contract
(`merge-drain/scripts/lane_priority_classes.json`) now also ranks PRs: `merge_ranks`, highest first, `other` last.
A PR takes the first rank it meets: `cause-fix` (a declared cause fix: a cause lease's `fix_ref`, or `fix=` on an
open cause CLAIM), `process-fix` (a PR in a repository, or of a ticket, the contract lists under process-fix),
`m4` (the M4 class above), `pin-bump` (a title one of `pin_bump_titles` matches: a release PR or an internal pin
advance) and `other`. Inside a rank the next rank a PR meets breaks the tie (`landing_placement.merge_ranks_met`), so
an M4 PR in a process-fix repository still goes ahead of its peers. Reordering a rank is an edit of the contract and
a ruling, never a list in code.

The controller follows the rank three ways. (a) Workers: a process-fix, M4 or pin-bump PR carries the node's
`process_fix` priority input (a cause fix carries its own), and each tick's worker dispatches go in rank order inside
their own positions. (b) Enqueue order: a strict base ranks its actions by merge rank (a passing PR ahead of a red
fix and a yielded PR last stay as before), and outside a strict base each kind of action is refilled in rank order
inside its own positions (`rank_order`). (c) The red-base gate (`red_base_gates`): a merge-queue base that a live PR
reads as red (the queue ejected it for a base-branch red no later merge_group run lifted, OMN-20126) and that has an
open cause fix is gated. While it is gated only a cause fix enqueues there: every other merge is `deferred` with
`red_base_gate=<repo:base>`, and every other entry already queued there is dequeued (`red_base_dequeue`, one per
head an hour, kept in `red-base-dequeues.json`; a failed dequeue is retried next tick). The node enqueues them
again once the fix merges and the gate lifts. A gate is bounded (OMN-19998): a fix whose own checks are red holds
nothing, and one fix head holds its base for at most `RED_BASE_GATE_MAX_S` (3600 s, the strict-base fix hold), timed
from the first tick that gated it (`red_base_gate_clock`, `red-base-gates.json`; a new fix or head restarts the
clock). The tick it expires writes one `red_base_gate_expired` row and the base's green PRs enqueue again: on
2026-10-23 the gate held 49 green PRs on plugin-tooling-pkg main for over an hour while its fix's merge group waited
on a validator shard that ran to its timeout.

Each `ticks.jsonl` row carries `merge_priority`: `ranks`, `repos` (per repository the PRs of a named rank in rank
order, `{pr, rank, class}`, and the count of the rest as `other`) and `red_base_gate` (`repo:base` to its fix). The
tick line gains `merge_rank=<rank>:<n>,...` and `red_base_gate=<n>` when nonzero. The merge-throughput tick
(`session-start/scripts/throughput_tick.py`) prints the list from the newest receipt, one `NOTE merge-priority:<repo>`
per repository with a PR above rank five and one `NOTE red-base-gate:<repo:base>` per gated base.

## Why each PR waits (OMN-19998)

Each `ticks.jsonl` row carries `pr_reasons`: for every open, non-draft PR the tick saw, `repo#n` to one
whitespace-free word (`landing_facts.pr_reasons`, from the facts the node was given and the leases after its
decision). First match wins: `worker_running` (`worker_running:queue_rejected` when the worker's head is not
conflicting and the merge queue removed it for failed checks, OMN-19998); `needs_person:<who>`; `held:<hold|owned|do_not_land>[+...]`;
`queued`; `gated:<gate>[,<gate>...]` (a worker gate reads `worker_gate:<why>`, cut at 48 characters, and the
gates are those of `gate_reasons`: `ledger_pause`, `operator_main`, `release_train`, `base_blocked`,
`companion_wait`, `lab_unproven`, `autobind`, `retarget`, `pending_required`...); `pending_ci`; `red:<class>`;
`conflicting`; `behind`; `await_arm` (green inside the node hand-over window, the landing node's to arm); `armed`
(green and armed or enqueued, waiting for GitHub); `parent_open:<repo#n>[,...]` (green and unarmed, stacked on an open
merge-order parent: the node lands only a chain root, so it lands after its parent, OMN-19998); `ready` (green, clean
and unarmed: the controller's to merge). The throughput tick's stuck-green alarm does not list a `parent_open` PR while
the tick is fresh: its parent is listed, or is queued, on its own.
A PR is listed at every tick it is open, so its wait is read off the rows between two timestamps instead of
rebuilt from the watcher and the decisions log. It adds about 2 KB to a row (48 PRs), so a day of 288 ticks adds
about 0.6 MB. The field changes no landing decision.

```bash
tail -1 ~/.local/state/omni/landing/ticks.jsonl | python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())["pr_reasons"], indent=1))'
```

## The clone-refresh merge event (OMN-20496)

Right after its own successful merge (outcome `merged` only, never `unknown`, `enqueued`, `dequeued`,
`deferred` or `failed`) the controller starts the canonical clone refresh's merge event, so the clones
refresh without waiting for the PR watcher's 120 s poll. It reads the base, merge commit and merge time with
one `gh pr view --json baseRefName,mergeCommit,mergedAt`, then starts the command in the environment variable
`ONEX_CLONE_REFRESH_PUBLISH` (the same shell-quoted prefix the watcher reads) with `--repo`, `--base`,
`--merge-sha`, `--pr`, `--merged-at` and `--source controller` appended, detached with no stdio and without
`PYTHONPATH`, and never waits for it. The watcher's publish stays as the safety net. An unset variable, an
unreadable read or a spawn error never changes the merge outcome: the reason is in the action's `detail` and in
`clone-refresh-publish-failures.jsonl` in the state dir. The variable must be in the landing controller launchd
agent's `EnvironmentVariables`; the controller runs from the installed copy, so a code change here needs the
installer re-run and the agent reloaded before it takes effect.

## Refusals

| Line | Meaning |
| -- | -- |
| `LOCKED` | another tick holds the lock; exit 0 |
| `HASH-MISMATCH` | the controller file differs from its installed hash; a fix is a skill PR and a re-install |
| `G-ACT-MISSING: <why>` | no gate file naming this controller and the installed decision commit; the drain watchdog kickstarts nothing here and pages, because only a re-install with fresh receipts opens it |
| `DECISION-RUNTIME-MISSING` | no pinned decision runtime installed |
| `QUOTA-DEFERRED` | GitHub quota unread or under 500; the tick decides nothing |
| `UNKNOWN: <why>` | a read failed; never reported as zero (a failed batched live read, such as a `gh` HTTP 502, is retried once, then refuses the tick) |
| `TICK-BUDGET: <detail>` | the tick's read and decision ran past its 720 s wall-clock budget; it writes no state and takes no action, and its receipt carries the phase timing |

State, receipts and logs are under `~/.local/state/omni/landing/`: `state.json` (the node's
controller state, written before any action), `ticks.jsonl`, `decisions.jsonl`, `outcomes.jsonl`,
`workers/<lease>/` (lease, brief, prompt, log, result) and `last-facts.json`.

## Known friction (from prior runs)

Record new friction with `/omni:friction-record` and add a line here in the same PR.

- **External verdict copies stayed red after their sources recovered.** The C17 verdict went green at scheduled
  run 38285156793, but the omnimarket and omnibase_infra PRs still red on the check (38 listed in MSG
  2026-10-12T16:57:27Z lane=c17refresh-1d5b) each needed a hand job rerun. The external verdict class now does that
  when every configured source has a fresh green after the red copy. → STATUS 2026-10-12T18:04:32Z
  lane=orchestrator-1d5b, OMN-20864

- **Test runs on a lab host wrote fixture rows to the canonical ledger.** With `ONEX_LEDGER_WRITE_VIA=bus` the real
  `onex_ledger.py` sends every accepted row to the canonical ledger whatever scratch path a test names, so every run of
  `tests/test_landing_worker_relay.py` on h907 added a fixture `lane=landing-L70` CLAIM and TERMINAL pair. A test that
  runs the real ledger tool unsets the bus variables first (`local_ledger` in that file). → FRICTION 2026-10-03T22:00:06Z lane=rpf-OMN-20416
- **Parallel plugin-tooling-pkg PRs claimed the same next plugin version.** Each peer merge forced a
  rebase and a re-bump on every other open plugin PR (2026-10-02, #249 to #258, five PRs claiming
  0.4.249 to 0.4.253). The fix worker then re-bumped with `validate_plugin.py --bump-to-base`. Since
  OMN-20497 a PR does not bump at all: a post-merge bot PR (`automation/omn-20497-plugin-version-bump`)
  carries the version, the fix worker never edits one, and the controller's own update of a plugin PR
  only resolves a version-line conflict by taking main's value. → OMN-20046, OMN-20497
- **Workers were sent to PRs whose fix is not in a worker's brief.** A CI Summary red only from cancelled or
  skipped siblings, a PR based on main in a dev-landing repository, and a red PR with its required contexts still
  running each took three or four workers that wrote no result. The controller now reruns, refreshes, retargets or
  waits deterministically (section "Stale summaries, main-based PRs and pending checks get no worker"). → FRICTION
  2026-10-05T16:27:13Z lane=drain-9143-m4-1614, OMN-19998
