# morning-friction-sweep — format contract

Sibling process: [`morning-ground-state`](../morning-ground-state/README.md) · runs **before** it

The morning friction sweep is a **process**, not an ad hoc report. Operator mandate, 2026-08-28, verbatim:

> "We need an automated process that runs every morning and captures friction from the previous evening's run and then creates Linear tickets for any friction that needs fixing."

The standing rule behind it: a reusable process, never an ad hoc report — the same rule that produced `morning-ground-state`.

This document is the **format contract**. The runnable half is the canonical typed handler at `src/ops_tooling_pkg/nodes/node_morning_friction_sweep_orchestrator/handlers/handler_morning_friction_sweep.py`. Neither is authoritative alone — see [Versioning rule](#versioning-rule).

---


### Isolated report publishing (OMN-18071)

The input precheck resolves the canonical docs_repo clone read-only, then
runs `canonical_clone_sync.py refresh OmniNode-ai/docs_repo --branch main --wait`.
A failed refresh stops the run. It pins the refreshed `refs/remotes/origin/main` SHA;
the publishing brief reuses that revision without another refresh and uses `git worktree add -b` at `$registry_root/worktrees/<ticket>/docs_repo`.
Friction and prune use separate dated ticket directories; ground-state phases share their
run's branch. All generators, artifact writes, scrubs, commits and pushes run in that isolated
worktree. The canonical checkout and index stay unchanged.

An existing path must be this clone's clean linked worktree with no live peer owner. A same-run
branch preserves earlier phases' commits. A prior-date branch is re-branched from the refreshed
revision only when its commits (and any existing target branch) are ancestors of that revision.
Dirty, unmerged or foreign work is preserved and reported BLOCKED. Never silently reuse a prior
date's branch. Hand the PR to landing-controller; closeout owns cleanup after landing. The
canonical-clone and worktree guards remain unchanged.

`tests/test_morning_lane_rules.py` executes the emitted recipes against a sandbox remote and
clone, checks the refreshed base and canonical checkout/index, and exercises dirty, unmerged,
foreign, same-run and prior-date worktrees plus a refused refresh.

## Invocation

The workflow runs itself every morning under launchd (see [Scheduling](#scheduling)). To run it by hand — paste this, changing only the date:

```bash
python3 -m ops_tooling_pkg.nodes.node_morning_friction_sweep_orchestrator.handlers.handler_friction_sweep_cli --date 2026-09-16
```

The workflow's name is `morning-friction-sweep`, which is what produces the morning friction report — there is no separate `morning-friction-report` workflow and creating one would publish a competing report into the same folder on the same morning. The **run date** is the morning the report is produced, and the report is about the **previous UTC day**, so the line above, run on 2026-09-16, reports 2026-09-15's friction.

The same caller accepts `--force` to bypass the idempotency precheck and
`--dry-run` to scan and report without Linear mutation. `--lookback-hours` and
repeatable `--fence` map to the typed command's `lookbackHours` and `fences`.
The caller resolves the declared dev bus; configure the executor workspace and
tenant as described under Canonical runtime below.

| Arg | Required | Default | Meaning |
| -- | -- | -- | -- |
| `date` | yes | — | `YYYY-MM-DD`. Names the output file and scopes "this run". Passed explicitly so a run is reproducible and a past date can be re-run. The script throws if it is missing. |
| `dryRun` | no | `false` | Scan and report, **no Linear mutation**. The report labels the filed section `WOULD FILE (dry run)`. The watermark still advances. |
| `lookbackHours` | no | `24` | Used **only** when `beta/tracking/friction-sweep-state.json` is absent (first run). Once the state file exists the watermark always wins. |
| `fences` | no | `[]` | Free-text standing fences injected into all source and prose-producing phase briefs. Empty means fence-free; the agents still skip any friction an active lane already owns. |
| `force` | no | `false` | `true` bypasses the idempotency pre-check entirely (the pre-check agent is not even spawned) and re-derives the whole run. The **only** way to overwrite a delivered, conformant state file + report. Same semantics as `morning-ground-state`'s flag (OMN-16972). |

Outputs, both committed path-scoped in a docs_repo report worktree:

- `beta/tracking/<date>-friction-sweep.md` — the report
- `beta/tracking/friction-sweep-state.json` — the watermark + fingerprint ledger

Both paths are relative to the **docs_repo** clone, not to `registry_root`.

### Output root — OMN-17235

Per the operator ruling of **2026-08-31** (and OMN-16990 DoD 8): *plans for current
work, deep dives, and tracking / status / rollup artifacts go to
docs_repo.* Since the 2026-09-26 freeze (OMN-19625, OMN-19744) doctrine and ADRs go
there too (`reference/`), brainstorming to `beta/plans/_scratch/`; registry_root has no carve-out.

Before OMN-17235 this workflow hardcoded `docs/tracking/` under `$registry_root` and its
agent brief carried an explicit "EXCEPTION: registry_root docs/process files commit
path-scoped" carve-out. **That carve-out is deleted.** Every path in the table above
is now relative to the **docs_repo clone**, resolved in bash as
`KB="${DOCS_REPO_PATH:?...}"` — **fail-fast, no default, no `registry_root`
fallback** (CLAUDE.md Operating Rule 8). An unset variable aborts the phase with a
message naming the variable rather than silently picking a path. The brief then
verifies `$KB` is a clone of `OmniNode-ai/docs_repo` before writing,
creates a worktree at the pinned revision, commits path-scoped there, and opens the PR.

Enforcement is mechanical on both ends: the `kb-doc-gate / kb-doc-gate` required check
on `registry_root` `main` (`.kb-doc-gate.yaml`) rejects a new doc-class markdown file under
`registry_root/docs`, and `check_no_local_paths.py` + `check_beta_layout.py` in
docs_repo reject an operator-machine path or a stray file in `beta/`
root. Write portable paths in the report body.

**`docs/tracking/ROLLING_WORK_LEDGER.md` is the one deliberate exception** and stays in
`registry_root`: its literal path is cited by 62 files across omniclaude (4),
omnibase_infra (30) and omnimarket (28), so repointing this workflow alone would fork
the append-only ledger and break the §0a claim protocol for every other lane. Moving it
is a fleet-wide repoint plus a file migration — its own ticket. `.kb-doc-gate.yaml`
carries a matching **temporary** single-path allow entry for it.


Ten agents run in **five phases** (nine with `--force`), and the Scan phase is a **parallel fan-out** (OMN-18474):

```
Precheck (state snapshot, then idempotency)  ──▶  Scan (5 agents, dispatched together)  ──▶  Synthesize  ──▶  Adjudicate  ──▶  Report
  sonnet         ├── friction-scan          sonnet           opus            opus            opus
                 ├── friction-source-linear      sonnet
                 ├── friction-source-checkpoints sonnet
                 ├── friction-source-ci          sonnet
                 └── friction-source-guards      sonnet
```

The five source agents are awaited together in one `asyncio.gather`. They are independent reads of independent surfaces, so running them serially spends wall clock for nothing — and, more importantly, one agent reading nine sources fails **all** of them when it fails, whereas five agents fail independently and a dead source surfaces as one `UNKNOWN` row instead of a truncated run.

The phase boundaries are the same isolation guarantee as before, now with one more: the precheck is read-only and gates everything after it (see [Idempotency](#idempotency--the-same-date-re-dispatch-guard-omn-17225)); **every source agent is read-only and writes only its own handoff**; the synthesizer reads five handoffs and writes one, touching no Linear and no state; the adjudicator mutates Linear and writes no files; only the reporter commits. A failure in one phase cannot half-write the state file or leave a filed ticket unrecorded.

**The adjudicator is the only Linear writer in this workflow.** The source agents are forbidden from any Linear write, including comments. A source that thinks something needs filing puts it in its handoff and lets the adjudicator decide — a source that files it itself double-files it.

### Watermark versus window — not the same thing (OMN-18474)

Operator ask, 2026-09-16, verbatim (dictated): *"I want to create a prompt for a parallel workflow to schedule a friction report every morning about the previous day's friction"*. That adds a **window**. It does not replace the **watermark**, and conflating the two would undo OMN-17023.

| | Watermark | Window |
| -- | -- | -- |
| Answers | "what have I not read yet" | "which day is this report about" |
| Shape | a row anchor — heading + body digest | `[<prev-day>T00:00:00Z, <date>T00:00:00Z)`, the previous UTC day |
| Derived from | the committed state file | `args.date`, never wall clock |
| Survives a ledger roll | **yes** — that is why it exists | not applicable |

The watermark is the **floor** and the window is the **reporting frame**. Evidence above the watermark but outside the window is still reported — it is late-arriving evidence for the window, not a reason to drop a row. Replacing the anchor with a wall-clock day bound would reintroduce the 2026-08-27 defect exactly: 19,744 lines moved out of the ledger, the stored mark addressed different content, and every row between was skipped silently and permanently.

---

## Sources — scanned since the watermark, never from memory

| # | Source | Watermark unit | What is harvested |
| -- | -- | -- | -- |
| a | `docs/tracking/ROLLING_WORK_LEDGER.md` | **row anchor** — heading + body digest, resolved by `ledger_watermark.py` (see below) | Every `TERMINAL` row, plus any row in the scanned range carrying residual/friction language: *residual, friction, PARTIAL, blocked, workaround, had to, does not, silently, flaky, clobber, stale, collision, re-ran, second attempt, two-strike, not located, gap*. A TERMINAL row reporting clean success with no residual is **not** a candidate. |
| b | PR watcher state — validated by `pr_state_local.py` | `watermarks.pr_watcher.last_tick` (complete tick) | Current landing blockers, armed/queued observations and long-lived pending checks with dated evidence. Stale or incomplete reads are `UNKNOWN`, never `unchanged, 0 candidates`; historical queue transitions require event evidence. |
| c | `beta/deep-dives/*_DEEP_DIVE.md` | filename of the latest processed | The latest file only, and only if newer than the watermarked one. Its friction / residual / process-finding sections. |
| d | Previous day's `beta/tracking/<prev-date>-friction-sweep.md` | filename | Its **New friction (first occurrence)** fingerprints, carried forward as the **match set** — not as fresh candidates. This is the mechanism by which a first occurrence becomes a second one. |

Sources `a`–`d` are read by the core scanner, on the watermark. Sources `e`–`h` were added by **OMN-18474**, are read by four separate agents in parallel with it, and are bounded by the **window** plus their own declared freshness bound rather than by the watermark.

| # | Source | Agent | Bound | What is harvested |
| -- | -- | -- | -- | -- |
| e | Linear comments posted inside the window | `friction-source-linear` | `linear_comments_max_age_hours` = **48** | Comments carrying friction or occurrence markers: *occurrence, friction, recurred, recurrence, still failing, again, blocked, workaround, silently, stale, flaky, collision, re-ran, second attempt, two-strike, fails open, fails closed*. Also the **escalation input** for OMN-17403 Decision C: issues already carrying `occurrence_comment_ceiling` or more occurrence comments whose `statusType` is `started`. Read-only — it reports, the adjudicator decides. Linear filters **truncate**, so the agent paginates and reports whether the listing was exhausted |
| f | Session checkpoints and morning-workflow run logs | `friction-source-checkpoints` | `checkpoints_max_age_hours` = **48** | `.claude_scratch/**` lines dated in the window matching *friction, falsified premise, retraction, blocked, refused, truncated, workaround, had to, silently, stale, collision, re-ran, second attempt, two-strike, clobber*; plus `.onex_state/morning-workflows/runs/*.log` and `fire-receipts.jsonl`, where a `failed` phase, a non-zero exit, `timed_out`, `bg_abandoned`, or `missed_days > 0` is friction with a citable anchor |
| g | Required checks that FAILED on PRs that MERGED inside the window | `friction-source-ci` | `ci_lookback_max_age_hours` = **48** | Grouped **by check name** across PRs. One check name failing on many PRs in a day is a gate defect; one check failing once on one PR is that PR being wrong and is not friction. Pre-merge, post-merge and `cancelled`-by-supersession are reported as three different things |
| h | PreToolUse guard and hook refusals | `friction-source-guards` | `guard_logs_max_age_hours` = **48** | Refusals under `.onex_state/hooks/` and `.onex_state/scratch_guardlogs/`, with the refusal profile grouped by (verdict, command, target). A guard refusing the same command against the same target hundreds of times is a **mis-scoped guard**, which is the high-value finding on this surface |

Each of those four numbers is declared identically in `src/ops_tooling_pkg/nodes/node_morning_friction_sweep_orchestrator/handlers/handler_morning_friction_sweep.py` as `LINEAR_COMMENTS_MAX_AGE_HOURS`, `CHECKPOINTS_MAX_AGE_HOURS`, `CI_LOOKBACK_MAX_AGE_HOURS` and `GUARD_LOGS_MAX_AGE_HOURS`, for the same reason the PR watcher bound is: a bound declared in prose but not in the brief the agent actually reads is the same defect in a new costume.

#### Every source declares a bound, and `UNKNOWN` is a verdict

The rule OMN-18212 established on source `b` is now the rule for **every** source, old and new. A source agent measures the age of the newest artifact on its surface **before** it harvests anything. Over its bound, the verdict is `UNKNOWN`: the artifact id, its measured age and the bound go in `unreadable`, and **nothing is harvested**. A source may never return verdict `READ` with zero candidates unless it positively established that the surface is fresh.

`unchanged, 0 candidates` is the correct output for a healthy quiet window. It is also the output for a producer that has been dead for nine days. Nine consecutive runs reported exactly that against a dead producer, because the read never failed — it returned stale bytes. `READ` versus `UNKNOWN` is what separates them, and it is the whole job.

**Every zero carries a positive control.** Before a source reports a zero it runs the same query shape against an input known to return rows and records the control and its row count. Four consecutive confident false *"zero failures"* readings were produced on 2026-09-13 by a sweep with its stderr suppressed; the control is the only reason they were caught. Source agents are forbidden from appending `2>/dev/null` to a verification sweep for the same reason.

#### Two measured facts about sources `f` and `h`, recorded so they are not re-derived

* **Checkpoint mtime lies.** Measured 2026-09-16: files under `.claude_scratch/checkpoints/` carried mtimes from that morning while their newest **content** date was 2026-09-04, eleven days stale. An mtime is touched by any process that opens a file; only a date inside the content says when the content was written. Source `f` measures freshness by **content date**, never by mtime.
* **The canonical-clone guard log carries no timestamps.** Measured 2026-09-16: `.onex_state/hooks/canonical-clone-guard.log` holds bare records shaped `DENY Bash 'git fetch' in <path> (canonical clone: <name>)` and `UNRESOLVED …`, with no time on any line. Refusals in that file therefore **cannot be attributed to a day at all**. Source `h` reports day attribution for it as `UNKNOWN`, gives the whole-file refusal profile instead, and says plainly that the profile is whole-file rather than window-scoped. Inventing a day attribution there would be fabrication. Making that log day-boundable is itself a friction candidate the source is told to raise.

### Reading the PR watcher state (source b)

The existing `merge-drain/scripts/pr_state_local.py` reader is the only resolution path, under
the `merge-drain/scripts` directory beside `$ONEX_DELEGATION_STEP_PATH`. Run `python3 "$(dirname "$ONEX_DELEGATION_STEP_PATH")/pr_state_local.py"
--status --max-age-minutes 8` before harvesting, then enumerate `prs` keys at the path it reports
and read each record with the same command's `--pr <repo>#<n> --json` mode. The reader honors
`ONEX_PR_WATCHER_STATE` (including a lab snapshot); otherwise it reads
`.claude_scratch/pr-watcher/state.json` under the registry root. An explicit snapshot is never
replaced with another file. No GitHub PR or CI reads are allowed on a refusal.

`pr_watcher_max_age_minutes` = **8**. The workflow's `PR_WATCHER_MAX_AGE_MINUTES` agrees with
this bound and the existing reader's default. Freshness is the content timestamp `last_tick`
(the last **complete** tick), never mtime. The reader additionally requires `last_full_resync`
within 90 minutes, valid schema/read-source fields, nonzero open PRs as a positive control,
head shas and repository default branches. The run header records tick, measured age, bound,
full resync and the open-PR count. Exit 3, missing/unreadable state or a partial read makes the
source `UNKNOWN`, with the exact command and reason; nothing is harvested and the source
watermark stays unchanged. A fresh unchanged tick may report zero **new** candidates with
that positive control. Stale data may never be called `unchanged, 0 candidates`.

Harvest current evidenced landing blockers and `facts.armed` / record-level `queued` observations.
CI evidence requires `ci.sha == facts.head_sha`, a `ci.read_at` within the same freshness bound,
and actual check-run ids/status/start timestamps from `ci.detail`. Missing, skipped or wrong-head
CI is `UNKNOWN-not-proven` for CI-dependent fingerprints. An armed PR absent from the queue
has not thereby been proven to have **never** enqueued. The state is a snapshot, not queue history:
repeated dequeue/re-enqueue, repeated gate firings and sweeps with no state change require dated
event evidence. Without it, those signals remain `UNKNOWN-not-proven`.

The watermark is `watermarks.pr_watcher`, carrying a portable path, `last_tick` and
`last_full_resync` from the successful scan handoff. On migration, ignore the old
`watermarks.codex_merge_sweep.last_tick`: its run ids are not watcher timestamps. Scan available
fresh records on the first watcher read and label the migration; advance only after a complete
successful read. Store stable citation anchors in fingerprint evidence: repository/PR, head sha,
check-run id/status, or head sha plus armed/queued values. Count the same head/check/state once
across ticks. A newer watcher tick is an observation, never itself a new friction occurrence.

**Retired by this change (OMN-17427, Top-20 item 10):** `_codex_merge_sweep/` and
`.onex_state/merge-sweep/merge-sweep-inproc-*/result.json` are no longer resolution paths.
Their producer is dead; 16 reports recorded stale data, reaching 93.1 hours against the former
24-hour bound. Keep old watermarks only as historical evidence. Do not fall back to these files.

#### Decision: the local launchd tick is retired, not repaired (2026-09-16, OMN-18212 AC2b / AC3)

`.onex_state/manual-merge-sweep/latest/` was resolution path (2) until 2026-09-16 and is now removed
from this contract. Its producer was the `ai.omninode.manual-merge-sweep-tick` launchd agent,
removed the same day. Recorded so the next run does not re-derive it, with the evidence each claim
rests on:

* **It had not produced anything since 2026-09-07T17:35Z** — nine days, against a declared 300 s
  interval. `launchctl print` could not find the label in the user's `gui` domain at all, while its
  three sibling `ai.omninode.morning-*` agents were loaded, so this was one never-bootstrapped label
  rather than a machine-wide fault.
* **Nothing depended on it.** The merge sweep at that time ran in-session and wrote the now-retired in-proc result; PR landing goes through the `node_pr_lifecycle_orchestrator` family invoked in-session and
  never read this directory. What the dead agent cost was evidence, not merges.
* **Repairing it would have re-created a one-off.** The plist and its runner script were
  hand-built: no installer owns the label — `launchd/morning-workflows/morning_trigger_install.sh`
  covers only the three morning agents — and the runner is a local, gitignored operational script.
  Re-bootstrapping it would have restored a hand-built install that no `--status` leg can see, which
  is the shape the standing rules refuse.
* **Its stale output was actively misleading.** That tick's `summary.json` (`open_pr_count=56`) and
  `classified.json` were quoted as live PR-health figures in three consecutive sweep reports while
  five or more days old.

The parent's requirement that the local tick be *retired or explicitly demoted, stating which and
why* is discharged by this section: **retired**.

A source that cannot be read is reported as `UNKNOWN` with its **exact failing command**. It is never
inferred and never silently dropped — `reference_empty_result_is_not_evidence_of_absence`. Since
OMN-18212, a source that *can* be read but is older than its declared bound is reported the same way.

---

## The ledger watermark — a row anchor, not a line number (OMN-17023)

`watermark_schema_version` = `2`. The same number is declared in
`src/ops_tooling_pkg/nodes/node_morning_friction_sweep_orchestrator/handlers/handler_morning_friction_sweep.py` as `WATERMARK_SCHEMA_VERSION` and in the
state file; `tests/test_workflow_brief_watermark_contract.py` asserts all of them equal, so a
schema change that touches one and not the others fails CI instead of being misread.

**Why this is not a line count.** It was, until 2026-08-29. On 2026-08-27 the ledger was
split — 19,744 lines moved out of a 21,752-line file — and the stored mark (21,618) then
addressed entirely different content. Every row between was skipped, silently and
permanently. The defect is not that the mark drifted; it is that a line number has
nothing to compare itself against, so no amount of care by the reader can detect the
drift. A future rewrite would skip *more* rows, not fewer.

The mark is now the identity of the last row read: its heading line plus a 12-hex digest
over its normalized body. Both halves matter — headings repeat across lanes, and a digest
alone cannot be found by eye in an archive.

**Resolve it, never compute it.** The run calls the committed tool and quotes its JSON:

```bash
python3 $registry_root/omnibase_infra/scripts/ledger_watermark.py \
  $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md \
  --state $KB/beta/tracking/friction-sweep-state.json \
  --source rolling_work_ledger --resolve      # then --advance, after the state edits
```

| Exit | Meaning | What the run does |
| -- | -- | -- |
| 0 | resolved | read from `resume_line` to EOF; `unread_entries` is the row count the handoff must account for |
| 3 | `UNRESOLVED` — the anchor row is gone, or its digest changed because the row was edited after being read | **STOP for this source.** Do not scan, do not advance, do not guess a line. Report it in `unreadable_sources` with the command and its stderr |
| 4 | `SCHEMA` — the state file still carries the v1 line-number watermark | run the same command once with `--migrate`, then `--resolve` again. Never hand-edit the state file to clear this |

The anchor **survives a roll**: when the row has been archived, the resolver finds it in
`docs/tracking/archive/` and everything now live is correctly unread. That is the case a
line number cannot represent at all.

The anchor is **never written by hand** — `--advance` writes `anchor_heading`,
`anchor_digest` and `line_count_at_advance` atomically, after the run's fingerprint edits
are saved. A hand-typed anchor is a hand-typed lie that the next run cannot detect.

The section that gets rolled, and the caps that trigger the roll, are owned by
`src/ops_tooling_pkg/handlers/handler_ledger_roll.py` and its `ledger_roll.conf`, run by a
`post-merge` hook (`onex-ledger-roll-install`), not a schedule.

---

## What counts as friction

**Friction is process pain**: gate defects, tooling failures, cross-lane collisions, hand-workarounds an agent had to invent, silent-failure surfaces, docs that sent a lane the wrong way, scheduling/arming misses.

**Not friction**: an ordinary product bug already tracked as product work; a test failure that is just the code being wrong; a one-line "this was annoying" with no failure mode attached.

---

## The fingerprint

This is the load-bearing mechanism. It is quoted **identically** into all three agent briefs; it must not drift between them.

```
fr-<surface>-<failure-mode>
```

- **`<surface>`** — the tool, gate, script, or process step that misbehaved, normalized to its canonical identifier: `gh-pr-edit`, `prepush-selector`, `scratchpad-path`, `occ-autobind`, `merge-queue`, `deploy-onex-prod`, `ledger-lock`, `worktree-hookspath`, `coderabbit-gate`.
- **`<failure-mode>`** — normalized verb-object for what it did wrong: `silent-exit1-no-write`, `narrowing-missed-ci-tests`, `cross-lane-clobber`, `stale-pending-verdict`, `ssm-timeout`, `fails-open-on-unknown`.
- Lowercase, hyphenated, ASCII, ≤ 60 chars.

**Excluded from the fingerprint — evidence, never identity:** ticket ids, PR numbers, dates, times, SHAs, lane names, agent names, repo names, file paths, error message text, counts. Two incidents differing *only* in those fields are the **same** fingerprint.

### Matching, in order

1. **Exact** fingerprint string equality against `friction-sweep-state.json` → `fingerprints`.
2. **Signature match** — compare against each stored entry's one-sentence `signature`. Same surface *and* same failure mode ⇒ **reuse the existing fingerprint**; record the reuse in that entry's `aliases`. A rename is a match, not a new friction.
3. **Legacy form.** A prior friction-ticketing convention already exists in Linear, with titles shaped `[Friction] merge_sweep:<domain>/<failure-mode> — N occurrences / score X (30d)`. Live examples: OMN-13107 `ci/armed-never-enqueued`, OMN-13110 `ci/zombie-queued-run`, OMN-13111 `ci/anonymous-git-ratelimit`, OMN-13112 `ci/queue-stall-no-alert`, OMN-13113 `ci/hot-patch-rebuild-wipe`, OMN-13930 `tooling/cli-node-resolution`. The mapping is `merge_sweep:<domain>/<mode>` → `fr-<domain>-<mode>`. The sweep **must search the legacy form too**; a legacy hit is an **existing ticket** — comment the occurrence there, never file a duplicate — and the legacy slug is recorded in that entry's `aliases`.
4. Only if none of the above matches, **mint** a new fingerprint.

### Occurrence counting

An occurrence is a distinct **source-cited event**, deduped by `(source file, source anchor)`.

- Two ledger rows narrating the same single incident = **one** occurrence.
- A worker re-describing yesterday's incident is **not** a new occurrence.
- The count only ever increases from evidence citable by file + line.

**Source handoff contract (OMN-19725): occurrences_this_run must equal evidence.length.**
Every evidence element carries nonempty `source` and `anchor` strings. Enumerate every
anchor behind the count, one entry per distinct `(source, anchor)`; examples are not a count.
This rule applies to the core scanner and all four parallel source briefs.

Synthesize runs `python -m ops_tooling_pkg.nodes.node_friction_synthesis_effect.handlers.handler_friction_synthesis_cli` over all
five source handoffs with `--output` before analysis. The adapter publishes through the existing
local event-bus runtime to `node_friction_synthesis_effect`; its contract declares the
request and terminal topics and routes to `HandlerFrictionSynthesis.handle(request)`.
Host-local files stay on the caller’s host; accounting never bypasses the bus. The reducer derives each fingerprint's
count from its unique `(source, anchor)` pairs across all harvests. Two five-anchor harvests
sharing three anchors yield seven. An unsupported assertion is **UNPROVEN**: its
unenumerated portion contributes **0**, the refusal is printed to stderr and retained in
`unproven`, and valid anchors remain countable (16 asserted, four anchors yields four).
Entries missing either field contribute zero. UNKNOWN sources contribute zero and remain
in `sources_unknown`. Prior cumulative counts are separate; this reducer counts this run.

The synthesis agent enriches only the analysis fields, then runs the same inputs with
`--verify <merged-handoff>`. A changed count, anchor list, source set, candidate set or
refusal note fails verification and stops synthesis before adjudication. Zero-anchor
candidates permit no Linear mutation. Adjudicate copies `unproven` into its handoff and
Report prints every refusal in New friction. Semantic fingerprint matching remains the
source lane's responsibility before harvest; analysis never renames reducer rows.

The AC1-AC3 regression fixtures in `tests/test_morning_lane_rules.py` and
`tests/test_friction_synthesis.py` run in the `omni-home-tests` CI job and the
`omni-home-rule-enforcing-tests` pre-commit hook in this owning repository.


---

## Classification — the standing friction rule

| Condition | Action |
| -- | -- |
| Occurrences **≥ 2**, no ticket exists | **FILE A TICKET** — after the Linear duplicate search |
| Occurrences **== 1**, no ticket | **RECORD ONLY**, with the fingerprint printed verbatim so the next run matches it |
| An **open** ticket exists | Never re-file. Add **one evidence comment**: new occurrence's citation + quote, running count, whether the scope widened |
| A **closed** ticket exists and it recurred | Comment the recurrence; flag as **reopen-candidate** in Known. Do not reopen it unilaterally |
| An **active lane** already owns it (open PR, un-`TERMINAL`-ed `CLAIM`) | Do not file, do not comment. Record as **in-flight**, citing the PR or CLAIM |
| A ticket is **In Progress** and its fingerprint's `occurrence_comment_count` is already `>=` the ceiling below | Do **not** comment. **ESCALATE** — see next section |

**Linear duplicate search runs before any create, always.** Search the surface term and the failure-mode term **separately** (a single joined query misses), search the **legacy `[Friction] merge_sweep:…` title form** alongside the new fingerprint, include `Done`/`Cancelled` issues so a fixed-and-closed friction is not re-filed, and paginate — Linear filters truncate (`reference_linear_project_filter_truncation`).

### Ticket shape

Title: `<surface>: <failure mode> (Nth occurrence)`. Description, in order:

1. **Fingerprint** — the slug verbatim on its own line. This is how the next run cross-references it.
2. **Occurrences** — a table: date | source | anchor | quote.
3. **Failure mode** — stated as a defect, not a complaint.
4. **Blast radius** — cost per occurrence, lanes hit.
5. **Acceptance criteria** — concrete, verifiable, biased toward **mechanical enforcement**. A detection-only fix is a defect in the fix (Operating Rule 5: detection not wired as a gate gets ignored). Where the fix is a script or gate, name the CI gate / pre-commit hook it must be wired into.
6. **Provenance** — `Filed by morning-friction-sweep (<date>), operator mandate 2026-08-28.`

Priority by blast radius. A silent-failure surface or a gate that fails open outranks an annoyance. `Urgent` only when it is actively corrupting evidence or blocking a lane right now.

---

## Occurrence-comment ceiling — escalate, don't keep commenting (OMN-17403 Decision C)

`occurrence_comment_ceiling` = **3**. The same number is declared as `OCCURRENCE_COMMENT_CEILING` in
`src/ops_tooling_pkg/nodes/node_morning_friction_sweep_orchestrator/handlers/handler_morning_friction_sweep.py`, and `tests/test_morning_lane_rules.py` asserts the two
agree, so changing one without the other fails rather than drifting.

**The rule (operator ruling, 2026-09-16, adopting the recommendation in
`docs_repo` `beta/plans/2026-09-12-process-friction-remediation-plan.md`, Recommendation
C; durable record: `docs/tracking/ROLLING_WORK_LEDGER.md`, RULING row lane=rulings-b-c-1330):** once
**three** occurrence comments have already been filed on a ticket that is already **In Progress**, the
sweep does not file a fourth (or fifth, or sixth). Instead it **escalates** the item into this run's
report, counted, naming the ticket id and the number of days since the fingerprint's `first_seen`.

**Why.** `OMN-17403` (the ledger-watermark defect this very process depends on to see the ledger at
all) had taken **twelve** occurrence comments with the latch never clearing before this ruling. Each
comment costs a Linear write and a lane's adjudication time reading it; past the third, a comment is
not informing anyone new — the ticket is already In Progress and already knows.

**Mechanics.** Each fingerprint's state-file entry (see the "State file" section below) carries
`occurrence_comment_count`, which increments by 1 on the ordinary "EXISTING OPEN TICKET"
comment route and is **left unchanged** on the escalation route — so a fingerprint that has crossed the
ceiling stays pinned at it and is reported again on every subsequent run until the ticket moves out of
In Progress or is closed. That repetition is deliberate: the point is that the operator sees it every
morning, not once.

**Handoff shape.** The adjudicate phase's handoff JSON carries an `escalated` array (sibling to `filed`
/ `commented` / `known` / `first_occurrence`), one entry per escalation this run: fingerprint, ticket
id, the current `occurrence_comment_count`, and days since `first_seen`. The report phase renders it
verbatim as report section 6, "Escalated (occurrence-comment ceiling reached)".

**Scope.** The ceiling applies only when the ticket's live status is **In Progress**. A not-yet-started
ticket with a high comment count is a different problem (a stale or misfiled ticket — see the triage
rules in `morning-ground-state`) and still gets its ordinary evidence comment here.

---

## The report: ten sections, in this order

Output: `beta/tracking/<date>-friction-sweep.md`.

| # | Heading | Contents |
| -- | -- | -- |
| 1 | `## Run header` | Run date, **the window this report is about**, dry-run flag, and one row **per source** — source id \| verdict `READ`/`UNKNOWN` \| watermark or window bound it was read from \| measured freshness against its declared bound. All nine source rows print every run; a source missing from this table is indistinguishable from a source that returned nothing. Then unreadable sources with their exact failing commands |
| 2 | `## New friction` | fingerprint \| signature \| source citation (`file:anchor`) \| first-or-repeat \| occurrence count |
| 3 | `## Tickets filed` | ticket id + link \| fingerprint \| why it crossed the line (which occurrence, cited) |
| 4 | `## Evidence comments added` | ticket id \| fingerprint \| occurrence number \| what the comment added |
| 5 | `## Known / already-ticketed` | fingerprint \| ticket \| status (`open` / `closed-reopen-candidate` / `in-flight-lane`) \| cross-reference |
| 6 | `## Escalated (occurrence-comment ceiling reached)` | ticket id + link \| fingerprint \| prior comment count \| days since first occurrence — OMN-17403 Decision C, the operator-facing counted list |
| 7 | `## Root causes and proposed pickups` | **OMN-18474.** Two tables under one heading. First, root causes: cause (one sentence) \| fingerprints under it \| total occurrences \| distinct lanes hit. Second, the ranked pickups, **at most five**: rank \| cause \| lanes blocked \| recurrence \| existing ticket or `unticketed`. The only section that **proposes** rather than records — and it proposes nothing not already evidenced above it |
| 8 | `## Aging friction citations` | **OMN-18274 AC-2.** The only section produced by a command rather than a judgement: `uv run --project "$registry_root/../ops_tooling_pkg" onex-friction-ticket-aging --ledger <ledger> --archives docs/tracking/archive --resolve-linear`, its stdout pasted unaltered. Ages the ticket each FRICTION row **cites** — `STALE` (row older than seven days, ticket still backlog/triage/unstarted) \| `UNCITED` (row named no ticket) \| `UNRESOLVED` (status did not resolve, reported rather than assumed benign). Exit `2` is REFUSED: print the refusal, mark the source `UNKNOWN`, never an empty section |
| 9 | `## Falsified brief premises` | **OMN-18397 AC3.** Cited post-rule dispatch and falsified TERMINAL counts, three cited historical controls, or `UNKNOWN` with its exact gap. See the audit contract below; this section never prints only `none this run`. |
| 10 | `## Watermark advanced to` | per-source new watermark value + the literal state-file path |

**An empty section prints its heading and the literal `none this run`, except the premise audit, which always prints counts or `UNKNOWN` with evidence.** Never omit a heading — a missing heading is indistinguishable from a missed scan.

### Hard rules

| Rule | Why |
| -- | -- |
| **Under 180 lines.** Tables over prose. | A report nobody reads at 04:15 has zero value. Length is the failure mode. Raised from 150 by OMN-18474, which added four sources and one section — raised **once**, deliberately, not per addition. |
| **Root causes group; they never replace.** | The grouping section summarises what the evidence sections already carry. A cause that appears only in section 7 is unevidenced and does not belong in the report at all. |
| **Every claim carries its source citation.** | A friction with no citable evidence cannot be counted as an occurrence, so it cannot ever cross the filing line. |
| **Failed read ⇒ `UNKNOWN` + the failing command.** | An empty section must never imply "nothing happened". |
| **The scanner touches no Linear; the adjudicator writes no files; only the reporter commits.** | Phase isolation keeps a mid-run failure from half-writing state or losing a filed ticket. |

---

## Refreshed prior state (OMN-19723)

Before the idempotency check or any expensive phase, `friction-state-precheck` runs
`handler_friction_state_snapshot`. The reader invokes the sanctioned
`canonical_clone_sync.py refresh --branch main --wait` in the KB clone, pins the
resulting `origin/main` commit, and copies the committed state and same-date report
into unique read-only scratch files. It never reads the clone's working tree or
fetches itself. State bytes are preserved unchanged, including literal environment
prefixes in stored ledger anchors. The returned `prior_state` records the commit,
paths, and whether each file existed at that commit.

Precheck, watermark resolution, synthesis, adjudication, and report inputs use that
same snapshot throughout the run. A refresh failure, invalid state, unreadable
snapshot, or missing reader returns `UNKNOWN` and stops before scanning or writes;
there is no local fallback. This freshness check also runs with `force: true` and
`dryRun: true`; force bypasses only idempotency. Proven absence of the state at the
pinned revision remains an explicit first run, with empty prior fingerprints.

The report phase creates its worktree from the pinned commit before writing. It
copies prior state into that worktree, carries every fingerprint forward, and advances
only resolved watermarks there. Snapshot files remain unchanged. If schema migration
is needed, the scanner migrates a separate scratch copy. Every handoff records the
snapshot revision and the watermark resolver's `resume_line` and anchor evidence.

`tests/test_morning_lane_rules.py` checks the read paths, a stale checkout and matching
negative control, byte preservation, refresh failure, and CI/hook selection. The
migrated required `ci` job and `omni-home-rule-enforcing-tests` hook select that file;
the dry workflow read also verifies UNKNOWN stops normal, forced, and dry runs.

## Idempotency — the same-date re-dispatch guard (OMN-17225)

**Ticket: OMN-17225**, extending **OMN-16972**'s `morning-ground-state` guard to this lane. `OMN-16972`'s
own scope line said the failure shape "applies to the morning-workflow family generally
(ground-state, friction-sweep, worktree-prune)"; this section is that clause discharged for
`morning-friction-sweep`.

### The friction

Measured **2026-09-16**: this workflow was dispatched **twice** for the same `run_date`. The
duplicate `friction-scan` dispatch self-detected only **after** it had already started — a live
ledger check running *inside* the already-dispatched Scan agent found the first pass's `CLAIM` and
`TERMINAL` rows and aborted without a second scan or mutation
(`ROLLING_WORK_LEDGER.md` `:2330`-`:2331`, `lane=friction-scan-dup-2026-09-16`,
`outcome=DUPLICATE_DISPATCH_NO_NEW_SCAN`). The same morning cost roughly 15 minutes of duplicate
agent time and 463k subagent tokens on the second run (`:2371`). The self-detection was **correct**
— it is exactly the fence rule working — but it ran after the expensive agent was already paying
for a full derivation. The guard below moves the identical question in front of Scan, so a
duplicate costs one cheap read, not three expensive agents.

### The guard

**One** `sonnet`/`low` agent runs before Scan and answers a single question: has that run date's
friction sweep already been delivered, or is a peer lane delivering it right now? Because Scan hands
Adjudicate a transient scratch JSON that is never persisted between runs, the three derivation
phases are **not** independently resumable the way `morning-ground-state`'s five phases are — so
this guard gates the **whole run**, once, rather than gating each phase separately the way
`PHASE_SPECS` does there.

| Verdict | Condition | Result |
| -- | -- | -- |
| `already-delivered` | **both** the pinned state file's own `last_run_date` field equals the run date **and** the report exists at the same revision and is conformant | `{ short_circuited: 'already-delivered', precheck: <verdict>, expensive_agents_spawned: 0 }` — Scan, Adjudicate and Report are never dispatched |
| `peer-owned` | a live, un-`TERMINAL`-ed ledger `CLAIM` naming one of this workflow's lane stems and this run date, younger than 90 minutes | same short-circuit shape, `short_circuited: 'peer-owned'` |
| `run` | no delivered artifact or live peer, after a proven state snapshot | Scan, Adjudicate and Report dispatch normally |

`already-delivered` **beats** `peer-owned`, the same precedence `morning-ground-state` uses: a
delivered, committed, conformant state file + report is finished work, and a lingering un-`TERMINAL`-ed
`CLAIM` behind it does not un-deliver it.

### Why `last_run_date` is the PRIMARY signal, not a line-count scan

The ticket body names this directly: `friction-sweep-state.json`'s `last_run_date` is a **stronger**
idempotency signal than anything `morning-ground-state` had when it was built, because the state
file is written **last**, by `TASK 2` of a completed Report phase — it cannot read a finished date
without that run having actually finished. Reading `2026-08-29` on `2026-08-30` is exactly how
`OMN-17173` first proved a scheduled run had not fired that morning. The report's own commit +
conformance is checked too, as the **secondary** signal, so a state file that was hand-edited or
corrupted independently of a real run does not read as delivered on its own.

### Why peer-owned matching is a SUBSTRING, not `morning-ground-state`'s exact list

`morning-ground-state`'s `PHASE_SPECS` matches a lane name against a **fixed list** of literals
(`'ground-state-report'`, `'ground-state'`, and so on). That does not hold up against this
workflow's own observed ledger rows: on 2026-09-16 alone the three phases were dispatched under
`lane=friction-scan`, `friction-scan-2026-09-16`, `friction-scan-dup-2026-09-16`,
`friction-adjudicate-2026-09-16` and `friction-report-2026-09-16` — five distinct literal strings
naming three phases (`ROLLING_WORK_LEDGER.md` `:2330`-`:2331`, `:8528`-`:8535`). A dispatching lane
picks its own descriptive `CLAIM` name at claim time; it is not drawn from a fixed enum. The
pre-check therefore matches on whether the lane field **contains** one of the phase stems
(`friction-scan`, `friction-adjudicate`, `friction-report`, `friction-sweep`) plus the run date
appearing in the row's own text — broader than an exact match, and it is what the measured naming
drift actually requires.

### The clock and the fail direction

Same as `morning-ground-state`: the pre-check performs one live `date -u` read and returns it as
`clock_utc` — this script holds no clock of its own, per its determinism rule. An **UNKNOWN**
pre-check (a failed read, a dead agent, an indeterminate check) falls through to a **full run**; it
never skips. A false `already-delivered` would silently drop a morning's friction filing, which is
strictly worse than a duplicate.

### `args.force`

`force: true` bypasses the idempotency pre-check entirely — the pre-check agent is not even spawned — and
re-derives the whole run. It is the **only** way to overwrite a delivered, conformant artifact, and
it is the caller's explicit choice: passing it also lets the run overwrite `last_run_date` and the
watermarks, which is what corrupts the next morning's drift baseline if used by accident.

### Validation

`tests/nodes/test_morning_friction_sweep.py` executes the typed handler against transcripts captured from main's final JS at the merge point and asserts the DoD directly: a same-date re-dispatch with
an `already-delivered` or `peer-owned` pre-check verdict produces **zero** expensive agents, and a
`run` verdict (or a bypass via `force`) dispatches all eight expensive agents. The pinned-state precheck always runs, including
with `--force`; `UNKNOWN` stops before those agents. `node --check` is not sufficient here
for the same reason it is not sufficient for `morning-ground-state` — it cannot see control flow and
is blind to a `${...}` reshaping an agent brief. Wired as the `morning-friction-sweep contract`
required CI check (`.github/workflows/morning-friction-sweep-contract.yml`).

---

## State file — `beta/tracking/friction-sweep-state.json`

Mechanical state lives in a file (`feedback_mechanical_state_tracking`). Read at the start of the run, written at the end.

```json
{
  "watermark_schema_version": 2,
  "process": "morning-friction-sweep",
  "last_run_date": "YYYY-MM-DD",
  "watermarks": {
    "rolling_work_ledger": { "path": "docs/tracking/ROLLING_WORK_LEDGER.md",
                             "section_heading": "## §5 Action Log (append-only)",
                             "archive_dir": "docs/tracking/archive",
                             "anchor_heading": "<the last row read>",
                             "anchor_digest": "<12 hex over that row's body>",
                             "line_count_at_advance": 0 },
    "pr_watcher":         { "path": "", "last_tick": "", "last_full_resync": "" },
    "deep_dives":          { "path": "beta/deep-dives", "latest_processed": "" },
    "friction_report":     { "latest_processed": "" }
  },
  "fingerprints": {
    "fr-<surface>-<failure-mode>": {
      "signature": "one sentence: surface + failure mode",
      "aliases": [],
      "first_seen": "YYYY-MM-DD",
      "last_seen": "YYYY-MM-DD",
      "occurrences": 1,
      "status": "recorded",
      "ticket": null,
      "occurrence_comment_count": 0,
      "evidence": [{ "date": "YYYY-MM-DD", "source": "", "anchor": "" }]
    }
  }
}
```

`status` is one of `recorded` (occurrence 1, not filed), `ticketed` (a ticket exists), `resolved` (the ticket landed and the friction has not recurred since).

`occurrence_comment_count` (OMN-17403 Decision C) counts evidence comments actually **posted** on this
fingerprint's open ticket — distinct from `occurrences`, which counts source-cited events including the
one that got it filed. It increments by 1 each time the "EXISTING OPEN TICKET" comment route fires, and
is left unchanged when the occurrence-comment ceiling route fires instead. Absent (a pre-Decision-C
entry) reads as 0.

Two rules that the whole process depends on:

- **Carry every prior fingerprint forward**, even ones that did not recur. Dropping a fingerprint resets its occurrence count to zero and permanently hides a future repeat. This is the single failure mode that silently breaks the process. **Merge, never overwrite.**
- **Advance each watermark to what was actually read**, not to "now". A watermark ahead of the read is data loss.
- **The rolling-ledger anchor is written by `ledger_watermark.py --advance`, not by hand**, and only when the resolve leg succeeded. If it exited 3, the anchor stays exactly where it was and the report says `NOT ADVANCED` with the reason.

---

## Scheduling

The sweep fires at **04:15 daily** — deliberately **before** `morning-ground-state` at **04:43**, so that morning triage sees the tickets this run just filed rather than discovering the same friction a day later.

launchd `StartCalendarInterval` user agent — **wired and proven, OMN-17173**.

| Workflow | Label | Fires |
| -- | -- | -- |
| `morning-friction-sweep` | `ai.omninode.morning-friction-sweep` | 04:15 local |
| `morning-worktree-prune` | `ai.omninode.morning-worktree-prune` | 04:30 local |
| `morning-ground-state` | `ai.omninode.morning-ground-state` | 04:43 local |

Each agent runs `launchd/morning-workflows/morning_workflows_tick.sh <workflow>`, which writes a **firing receipt before it does any work** and then invokes the friction sweep through the canonical dev-bus caller. The other scheduled workflows retain their registered callers.

```bash
bash launchd/morning-workflows/morning_trigger_install.sh            # install + bootstrap all three
bash launchd/morning-workflows/morning_trigger_install.sh --status   # load state + last_fired per workflow
bash launchd/morning-workflows/morning_trigger_install.sh --uninstall
```

### The driver is copied out of the repo, deliberately

`morning_trigger_install.sh` installs the driver to `~/.omninode/morning-workflows/bin/morning_workflows_tick.sh` and points the agent at *that* copy, not at the path inside the checkout. A scheduler whose liveness depends on the working tree's branch state is not durable — `$registry_root` is a live shared branch that concurrent lanes commit to, and the trigger must keep firing while it is mid-rebase, on a feature branch, or missing the trigger path entirely. `registry_root` in the agent's environment still points at the canonical clone, so the workflows themselves resolve normally. Re-run the installer after changing the driver.

### The firing receipt

`$registry_root/.onex_state/morning-workflows/fire-receipts.jsonl` — append-only, two rows per run (`phase: fired` at entry, `phase: completed|failed` at exit), written by the **trigger**, not by the workflow. A run that fired and produced no report is therefore distinguishable from a run that never fired at all — which was the whole failure mode before OMN-17173.

`last_fired/<workflow>.json` carries `last_fired` / `last_completed` / `last_exit`. Each fire computes `missed_days` against the previous `last_fired`, so a skipped morning is visible in the next morning's receipt rather than invisible forever.

### Correcting the record: launchd *does* fire on this Mac

The prior text here (and memory `feedback_local_durability`) said launchd "does not fire reliably" and told sessions to use session-bound `CronCreate`. **Measured 2026-08-30, that is wrong.** The four `StartInterval` tick plists in `~/Library/LaunchAgents` wrote 18 MB (`repowise-sync`, 21600 s) and 567 KB (`manual-merge-sweep`, 300 s) of output, on cadence, through 2026-08-26 — with the machine up continuously since the 2026-08-23 boot. They stopped because they were **`bootout`'d and never re-bootstrapped** (`launchctl print` → *NOT LOADED*, while `launchctl print-disabled` still reports them *enabled*), most likely by `tick-bundle-uninstall.sh`, which that same memory instructs sessions to run. An unloaded agent not firing is not launchd being unreliable.

> **Dated pointer, 2026-09-16 (OMN-18212).** The `manual-merge-sweep` agent cited above as evidence
> is no longer on this machine: it was never re-bootstrapped after that `bootout`, produced nothing
> between 2026-09-07T17:35Z and its removal, and has been retired — see [the decision
> above](#decision-the-local-launchd-tick-is-retired-not-repaired-2026-09-16-omn-18212-ac2b--ac3).
> The measurement this paragraph reports is unchanged and still stands; only one of its two named
> examples has since been retired, for reasons unrelated to whether launchd fires.

The one genuine launchd failure on record — `docs/diagnoses/diagnosis-2026-04-26-merge-sweep-launchd-bootstrap-fail.md`, `Bootstrap failed: 5: Input/output error` — was a **single label** whose `ProgramArguments` pointed at an external volume (`<volume>/...`), while the sibling `ai.omninode.*` agents in the same `gui/501` domain loaded fine *in that same diagnosis*. It was never a machine-wide launchd fault. These three agents run entirely from the internal disk under `$registry_root`, so that failure mode does not apply.

`StartCalendarInterval` was then proven directly rather than assumed: a one-off agent scheduled 4 minutes out fired at **11:02:00 EDT on 2026-08-30**, `runs = 1`, `last exit code = 0`, receipt `20260830T150200Z`, headless Claude round-trip complete in 44 s.

### Known constraint — Linear MCP is unavailable headless

`claude -p` cannot complete the Linear MCP OAuth handshake (measured: `LINEAR_FAIL=linear-server MCP requires OAuth authorization (not possible in this non-interactive session)`). The driver therefore sources `~/env-dir/env-file`, which carries `LINEAR_API_KEY`, so headless runs reach Linear over the REST/GraphQL API instead of MCP. Triage phases must use the API path, not `mcp__linear-server__*`, when running under the trigger.

### Why not the alternatives

* **`CronCreate`** — session-bound by construction: in-memory, dies with the session, fires only while the REPL is idle. It is a per-session convenience, never the durable answer.
* **An omniclaude daemon periodic task** — measured 2026-08-30: there is **no long-lived omniclaude daemon.** Every `omniclaude` process on this Mac is an ephemeral per-hook subprocess spawned by an active Claude Code session (longest observed elapsed: 12 s). A periodic task hung there cannot fire when no session is running, which is exactly the gap being closed.
* **`lab-host-a` cron** — works, but adds a network hop and an SSH credential to a purely local concern, and the workflows read local worktrees. Held as the fallback if the Mac's login session proves unreliable.

---

## Versioning rule

**The contract, the script and the watermark schema version together.** `watermark_schema_version` = `2` appears in this document, in the script, and in the state file, and CI asserts they agree.

**The contract and the script version together.** Any change — a new source, a changed report section, a relaxed or tightened classification rule, a fingerprint-format change — edits **both** `docs/workflows/morning-friction-sweep/README.md` and the node's `handlers/prompts.yaml`, `models/phase_schemas.yaml` and handler **in the same commit**. Neither file is authoritative alone: the script's agent briefs point at this document, and this document describes what the script runs. A change to one and not the other is drift, and drift is how a process silently reverts to ad hoc.

**A fingerprint-format change is a breaking change.** Existing entries in `friction-sweep-state.json` will stop matching, every recorded friction silently resets to occurrence 1, and repeats become invisible. If the format must change, migrate the existing keys in the same commit and record the old slug in each entry's `aliases`.

The handler is deterministic by construction: date supplied via the typed request, and every "how far back" question answered by the committed watermark rather than by wall clock.

**The idempotency guard (OMN-17225) is versioned the same way.** The precheck's `PEER_CLAIM_MINUTES`
window, the phase-stem list `PHASE_STEMS` and the `already-delivered` / `peer-owned` conformance
rules are quoted into the script's `PRECHECK` agent brief; a change to any of them edits this
document's [Idempotency](#idempotency--the-same-date-re-dispatch-guard-omn-17225) section in the
same commit. The dry-read validator
(`tests/nodes/test_morning_friction_sweep.py`) is the mechanical
check that the two have not drifted — it is wired as the `morning-friction-sweep contract` required
CI check (`.github/workflows/morning-friction-sweep-contract.yml`), mirroring `morning-ground-state`'s
own gate. `node --check` is explicitly not the gate, for the reason stated in the Idempotency
section above.

### Scrub before the commit — OMN-17235

Every artifact this lane writes into the docs_repo clone goes through
the write-time scrub before it is committed:

```bash
uv run --project "$registry_root/../ops_tooling_pkg" onex-shared-doc-scrub --write <paths written>
```

Exit `0` clean or repaired, `1` a local path with no portable form (fix the citation,
never commit around it), `2` **REFUSED** on the register rule — the document quotes
heated or profane operator language verbatim; re-render that passage as an attributed
professional paraphrase carrying its date and its firmness, then re-run. Nothing is
written on a refusal. Contract: `docs/workflows/_shared/README.md`. The step is
mandatory: `tests/test_morning_lane_rules.py` fails if this lane's script stops naming
the helper.


# morning-friction-sweep — packaged delegation contract

The executable handler is `src/ops_tooling_pkg/nodes/node_morning_friction_sweep_orchestrator/handlers/handler_morning_friction_sweep.py`.

## Delegation

The mandatory step applies to friction-report. The schema wrapper preserves every existing
requirement and property and adds the required `delegation` cell. Results are checked again
and violations fail the workflow after all phases have run. A phase skipped by the precheck
has no delegation requirement.

```text
DELEGATION (OMN-17009; mandatory and receipted, not optional): the prose of this lane, including handoffs, ticket descriptions/comments and reports, is drafted through the ONEX delegation chain, not by your own turns.
 1. Compute the FACT TABLE first, deterministically: every count, id, sha, path, date and verbatim quote is computed or copied in code or shell and written to a scratch file (a path minted by lane_scratch.py). A number, an identifier or a quote is never delegated, because the draft cannot be trusted to reproduce it.
 2. Draft the prose around that table: python3 "$ONEX_DELEGATION_STEP_PATH" text --lane <your ledger lane name> --step <slug> --prompt-file <scratch>/prompt.md --ticket OMN-17009 . It tries the lab first and GLM second and leaves a receipt. The prompt file names the fact table it was given and says what to write, facts only. What you delegate is the prose the section spec already calls for (sentences and prose cells); the section spec itself, the table shapes and the verbatim lines stay exactly as specified.
 3. Fact-check the draft, then dispose of it: every number, id, sha, path and name in it must appear in your fact table; recount anything counted; discard a draft that states a decision, an approval or an operator's words that the facts do not contain. Then record what you did with it: python3 "<removed>" --omni-home "$registry_root" dispose --receipt <receipt path> --disposition <used|edited|discarded|ignored> --reason-code <code>
 4. A code edit this lane makes (a script, a test, a config) goes to Codex first: delegation_step.py code --lane <your ledger lane name> --worktree <worktree> --prompt-file <scratch>/codex-prompt.txt --scratch <scratch>. You review every diff.
 5. For ticket OMN-17009, prose-producing phases must reject delegated=0 with reason read-only-lane and only allow delegated=0 for route-refused:<status> or route-unavailable:<token>. A route-unavailable reason is route-unavailable:<token> with no spaces: the token is the run id, or one hyphenated word such as delegation-step-failed when no run exists. Prose after the colon fails the check, so put the explanation in your report and never in the reason. Genuine precheck skips still require no delegation, while positive delegated counts require run ids and an empty reason. Return the delegated count, runs array, and reason string, and paste these same cells into TERMINAL. The phrase "nothing to draft", the phrase "deterministic render", an empty reason or any other text is REFUSED and fails the run: a report made of tables still has prose cells and framing sentences, and those are what you delegate. Put the same values on your TERMINAL row, as delegated=<n> runs=<ids> or as delegated=0 delegation_reason=<reason>.
```

## Falsified brief premises (OMN-18397 AC3)

The packaged report contract extends the original nine sections with
`## Falsified brief premises`, immediately before `## Watermark advanced to`.
The precheck requires all ten headings, so an older report cannot skip the audit.
Every emitted phase brief, including the read-only precheck, carries the complete
Premise paragraph. The premise guard executes normal and forced runs to check the
prompts handed to agents; finding the paragraph elsewhere in the generator does
not satisfy that guard.

The report computes counts from the live ledger and archive rolls. It cites the
rule's landing timestamp and evidence, pairs each TERMINAL with its latest
preceding CLAIM for the exact same lane, and selects dispatches by CLAIM time
strictly after landing. TERMINAL time bounds the reporting window.

The same query must establish a falsified premise in each historical control:
`omn16831-tenant-canary-1125`, `c4-probe-fleet-move-1222`, and
`omn17284-chain-legs-1252`. A lane-name match alone does not establish it.
`Premises falsified: none` is a negative result. Missing control evidence,
unreadable sources, unpaired TERMINAL rows, an unverified landing timestamp,
or an empty eligible cohort produce `UNKNOWN`, never an observed zero.

The required `premise_audit` result records status, landing timestamp and citation,
eligible and falsified TERMINAL counts, cited per-lane positive controls,
unreadable sources, and a reason. `UNKNOWN` carries a null falsified count and
an explanation. The workflow validates the result again after the report agent
returns, even if schema enforcement was bypassed. A measured nonzero count is
returned as a finding; this contract does not claim AC3's zero outcome occurred.


## Canonical runtime (OMN-20674)

Operator tooling belongs in `ops_tooling_pkg/nodes/` (OMN-20563). The node package
`node_morning_friction_sweep_orchestrator` registers under `onex.nodes`. Its
`contract.yaml` declares typed ingress, handler routing, the command and both
terminal topics, and the existing infra coding-agent command/reply topics.
The handler reuses infra request/response wiring and coding-agent workspace
validation/execution; the five source phases retain concurrent fan-out.

The launchd trigger invokes the thin `handler_friction_sweep_cli` caller. It
resolves the declared **dev** bus and its identity, sends a typed command and
waits for a terminal. Configure `registry_root`, `ONEX_FRICTION_WORKSPACE` (an absolute
workspace on the executor's allowed roots) and `ONEX_TENANT_ID`; no broker or
workspace is guessed. The original executable and dry-read entrypoint are removed.

Run `uv run pytest tests/nodes/test_morning_friction_sweep.py
 tests/nodes/test_morning_friction_sweep_bus.py tests/test_morning_lane_rules.py -q`
for merge-point executable parity (including failed snapshots under `--force`),
guards and contract dispatch. The fixture records the legacy source SHA-256;
its prompts, phase schemas and results were captured by executing main's JS body
with an `AsyncFunction` and recorded agent responses before deleting the script.
The lab proof uses the real in-memory bus, discovery and auto-wiring with a
captured phase transcript because this unpublished node is absent from the
lab deployment; it cannot mutate tickets or the real watermark.

Deployment limitation: the current infra coding-agent command accepts the model,
but has no effort field. The original medium/high effort remains explicit in
phase options and ROUTE briefs; live execution parity requires upstream support
for transporting that setting. This conversion is not ready to land until that
support and a live phase proof are supplied.
