# morning-worktree-prune — format contract

Sibling processes: [`morning-friction-sweep`](../morning-friction-sweep/README.md) (04:15) · [`morning-ground-state`](../morning-ground-state/README.md) (04:43)

The morning worktree prune is a **process**, not an ad hoc cleanup. Operator mandate, 2026-08-28, verbatim:

> "Build the automated worktree pruner."

And the original design ruling that scoped it, same day, in answer to a direct question about what fires a prune — also verbatim:

> "pruning is keyed to the TICKET CLOSING, not to a PR merging — a ticket spans multiple PRs/companions and worktrees are keyed by ticket dir, so PR-merge is an INPUT to the safety check (it is what makes tree-diff-vs-dev empty), while ticket completion FIRES eligibility."

**Superseded, OMN-18370.** Operator RULING, `docs/tracking/ROLLING_WORK_LEDGER.md:7870` (2026-09-14, in-session, emphatic paraphrase): *if no worktree holds work worth keeping, there is no reason to still have hundreds of them; the buckets were already judged and must not be re-judged daily. A worktree's prune eligibility is keyed to WHAT IT HOLDS, not to its ticket's state.* Shipped in `omniclaude#2165` (squash `91bb11a6`). The ticket-closing rule quoted above is history, not the current predicate — see [The predicate](#the-predicate) for the shipped rule.

This document is the **format contract**. The runnable halves are the committed effect node `morning_worktree_prune_effect` at `src/ops_tooling_pkg/nodes/node_morning_worktree_prune_effect/` (contract, handlers and typed models, OMN-20681) and the committed classifier at `omniclaude/scripts/worktree_auto_prune.py`. The scheduled runner is the effect node `unattended_worktree_prune_effect` at `src/ops_tooling_pkg/nodes/node_unattended_worktree_prune_effect/` (OMN-20681); the pieces it shares with the interactive node and its revoke switch `unattended.yaml` live in `src/ops_tooling_pkg/handlers/worktree_prune/`. None of the three is authoritative alone — see [Versioning rule](#versioning-rule).

Ticket: **OMN-16901**. Recorded hazard it closes the correctness half of: **OMN-15551**.

---

## Architecture note — the sweep is the executor, not the design

Read this before extending anything here.

The daily sweep is the **executor / backstop**. It is not the design, and it is not where the design should end up. The intended end-state is **event-driven**: an auto-close flips a ticket to `Done`, and prune eligibility follows mechanically from that flip — no scheduler, no morning window, no polling (cf. the **OMN-16821** flip-predicate chain, which is the same shape: a state flip is the event, and downstream consequences are pure functions of it).

That end-state is why the predicate is structured the way it is. The whole decision lives as a **pure function** in `omniclaude/src/omniclaude/hooks/lib/worktree_prune_policy.py`:

```python
classify_worktree_prune(facts: ModelWorktreePruneFacts) -> ModelWorktreePruneDecision
```

No git, no network, no filesystem, no clock. Fact collection is the caller's job (`omniclaude/scripts/worktree_auto_prune.py` today; an event hook tomorrow). A future ticket-closed hook calls the same function with the same facts model and gets the same answer, and this workflow becomes the reconciliation backstop for the events that were missed — the same two-layer shape `worktree_reaper.py` already uses for merge events.

**Do not move policy into the node's handlers.** A predicate that only exists inside an effect handler's orchestration cannot be called by an event.

---

## Why the predecessors do not cover this

| Surface | What it keys on | Why it is not this |
| -- | -- | -- |
| `omniclaude/scripts/prune-worktrees.sh` | PR merged **or** remote branch gone, then clean + no-unpushed | Merge-keyed, not ticket-keyed, and manual-invocation-only ("run after batch merge sweeps"). Per OMN-15551 its predicates are *anti-correlated with liveness*: clean + pushed + merged is exactly the state a live lane occupies between push and post-merge verification. Still useful after a batch merge sweep; it stays, and the two disagree on purpose. |
| `omnimarket/.../node_pr_lifecycle_worktree_prune_effect` (OMN-13859) | A single PR merging, in-process from `node_pr_lifecycle_orchestrator`'s `POST_MERGE_TAIL` | Real code, but most real landings go through session-armed `gh pr merge --squash --auto` or the Codex manual merge sweep, not that orchestrator — so the trigger structurally does not fire for most landings. Both nodes are `ISOLATION_ONLY` per `docs/tracking/2026-08-08-omnimarket-node-coverage-census.md`. |
| `omniclaude/scripts/worktree_reaper.py` (OMN-13228) | The `pr-merged` projection, cursor-advanced | Merge-keyed again, and it drives `prune-worktrees.sh`, inheriting its predicates. |
| `/onex:worktree --audit` / `--prune` | Prompt-driven; `--prune` wraps `prune-worktrees.sh` | The skill states its own honest node-backing: none of its modes is node-backed, and nothing schedules it. |

Measured state at authoring (2026-08-28): `find $registry_root/omni_worktrees -maxdepth 3 -name .git | wc -l` → **1012** entries; the classifier's own discovery, which counts only linked worktrees (a `.git` *file*, never a full clone's `.git` directory), reported **1006**. `CronList` showed only `morning-friction-sweep` and `morning-ground-state` armed — nothing worktree-related was scheduled at all.

---

## The scheduled run is unattended (OMN-19399)

**Operator ruling, 2026-09-24 (firm): the prune workflow must remove the safe class unattended.** The standing consent is the OPERATOR-CONSENT row stamped `2026-09-24T13:50:25Z`, lane `worktree-prune-execute-2026-09-24`: APPROVED SCOPE is the classifier's safe class plus empty orphan ticket dirs, through `worktree_auto_prune.py --execute` and its per-row revalidation. OUT OF SCOPE is triage rows, the rescue-only class, stale-dirty rows, non-empty orphans, partial-mutation debris, stale-registration pruning, unpushed commits and any branch with an open pull request.

**What failed on 2026-09-24.** The tick classified 953 worktrees (137 safe) and removed nothing, for three reasons. The tick passed only `date`, so the Prune phase below never ran. The Sweep agent launched the classifier detached, and its turn ended two minutes later at the SubagentStop report-contract hook (ledger FRICTION `2026-09-24T08:24:49Z`); nothing followed up, so the report was never committed. And a failure surfaced only in a receipt, hours later.

**What the 04:20 tick runs now (OMN-19628).** `morning_workflows_tick.sh` runs `python3 -m ops_tooling_pkg.nodes.node_unattended_worktree_prune_effect.handlers.handler_unattended_prune_cli --date <today>` for this workflow, on the literal brew interpreter, in place of `claude -p`. It scans `$registry_root/omni_worktrees` (or `ONEX_WORKTREES_ROOT`) and `$OPS_TOOLING_PKG_HOME/omni_worktrees` (default: `$registry_root/../ops_tooling_pkg/omni_worktrees`) in one run, publishing a report for each root with portable paths. No agent turn is in the path, so no hook can end it early. The runner:

1. Skips when an executed report for the date is already on docs_repo `main`, or when another runner holds the date's lock.
2. Appends a CLAIM row (`lane=worktree-prune-unattended-<date>`).
3. Re-reads `unattended.yaml`, the revoke switch, and resolves the consent row **by stamp and lane**, in the ledger or any `docs/tracking/archive/` roll. It never uses a line number: the older omnibase_infra timer `ai.omninode.worktree-prune` cited `ROLLING_WORK_LEDGER.md:2717` and has refused every run since the 2026-09-20 roll. An absent or disabled config, an unresolvable row, or a classifier that lacks `--hold-open-pr` downgrades the run to classify-and-report. It never widens what is removed.
4. Runs the classifier **in its own process** under `heavy_lock.py --lock /tmp/omninode-worktree-classifier.lock --max-hold 3h --timeout 30m` and waits for it. Every run passes these flags: `--hold-open-pr --no-debris --no-registration-prune --rescue-only` (plus the rescue-only values from `rescue_only_policy.py`), and `--execute` only under the consent. Removal is plain `git worktree remove` after live per-row revalidation. The open-PR listing is re-read fresh for the removal pass.
5. Checks the JSON against the consent's scope (`verify_report`). Every removal must be a safe-class row with both evidence cells. There must be no debris pass, no registration prune, no non-empty orphan, no stale-dirty row and no rescue-only removal. Any breach fails the run.
6. Rewrites operator paths to repo-relative form, runs `scrub_shared_doc.py --write`, commits the two report files through a **worktree** of the docs_repo clone cut from `origin/main` (never a checkout in the canonical clone, OMN-18071), pushes, opens the PR, waits for main's required checks at that head, and squash-merges it on that exact sha.
7. Appends a TERMINAL row with the counts and the merge sha.

**Any failure** (env, classifier, verify, scrub, publish, or anything unexpected) appends a FRICTION row (`existing=OMN-19399`), pages Slack through `alert-channel.sh`, appends `TERMINAL outcome=FAILED` and exits non-zero. The tick receipt then reads `failed`, and the 09:00 watchdog reports it again. A run whose removal was withheld is loud in the same way (`outcome=REPORT_ONLY`). If the runner file is missing, the tick fails closed with `runner_missing`. It never falls back to the agent path.

**The open-PR fence.** `--hold-open-pr` (omniclaude, OMN-19399) adds the block reason `open_pr_fence` to any row whose branch has an OPEN pull request, or whose open listing did not resolve. Without it, limb (c) (pushed at this exact HEAD) would remove a worktree held for review. On 2026-09-24 the first execute lane found three such rows and fenced them by hand.

**What the node below is for (OMN-20681).** The interactive dry run and the operator-asked execute run are the `morning_worktree_prune_effect` node, dispatched over the bus. It replaces the hand-dispatched `Workflow` script, which is deleted; there is no shim. The scheduled path is the `unattended_worktree_prune_effect` node, with the same classifier, fences and publishing; it takes only a date and reads its authorization from `unattended.yaml`.


### Isolated report publishing (OMN-18071, OMN-19539)

The Land step never writes in the canonical docs_repo checkout. It adds a **detached**
worktree of that clone at `origin/main` under `$registry_root/.onex_state/worktree-prune/`, copies the
scrubbed reports in, commits them there and pushes by refspec (`HEAD:refs/heads/<branch>`), so no
branch ref is ever created in the canonical clone and the canonical checkout and index stay
unchanged. Before the worktree is removed, `Shell.rescue_worktree` preserves any commit no branch
points at (a failed delivery leaves one) through the same helper the reaper uses; a refused rescue
keeps the worktree and fails the step. Hand the pull request to landing-controller; closeout owns
cleanup after landing.

OMN-18071's brief recipe (refresh through `canonical_clone_sync.py`, then `git worktree add -b` and
a same-run or prior-date branch policy) was the retired Workflow's. `tests/test_morning_lane_rules.py`
still executes it for the workflows that remain briefs; this node's own isolation is pinned by
`test_land_subject_one_pr_no_merge_no_checks`, which asserts a single detached worktree, no
`checkout`, no `--force` and a refspec push.

## Invocation

```bash
onex run-node node_morning_worktree_prune_effect --timeout 7200 --input '{"date": "2026-08-29"}'                    # dry run
onex run-node node_morning_worktree_prune_effect --timeout 7200 --input '{"date": "2026-08-29", "execute": true}'  # act
onex run-node node_morning_worktree_prune_effect --timeout 7200 --input '{"date": "2026-08-29", "force": true}'    # deliberate re-run: bypass the idempotency pre-check
```

The command topic is `onex.cmd.ops_tooling_pkg.morning-worktree-prune-requested.v1` and the terminal event is `onex.evt.ops_tooling_pkg.morning-worktree-prune-completed.v1`, both declared in the node's `contract.yaml`. The classifier scan takes 30-90 minutes, so a caller passes a long `--timeout` or reads the terminal event later.

| Arg | Required | Default | Meaning |
| -- | -- | -- | -- |
| `date` | yes | — | `YYYY-MM-DD`. Names the output files and scopes the run. Passed explicitly so a run is reproducible and a past date can be re-run. The handler refuses a missing or malformed date. |
| `execute` | no | `false` | `false` classifies and reports, removing **nothing**. `true` runs the second phase, which re-runs the whole predicate with `--execute`. |
| `worktrees_root` | no | — | Override: one root, one report pair. Default: every registry root `ops_tooling_pkg.worktrees.roots` resolves, each with its own report pair. Passed straight through to the classifier. |
| `kb_path`, `registry_root` | no | env | Default `$DOCS_REPO_PATH` and `$registry_root`. Unset is an error naming the variable: there is no default path and no `registry_root` fallback (CLAUDE.md rule 8). |
| `fences` | no | `[]` | Free-text standing fences. Each fence's `OMN-<digits>` tickets are matched against the sweep's safe rows: a fenced ticket's row is struck from the safe set and reported, and an `execute` run that still has a fenced safe row **refuses to run `--execute`** (the classifier has no per-ticket exclusion, so removal cannot be restricted to the rest). A fence with no ticket token cannot be matched and refuses the same way. Independent of the classifier's own claim-awareness. |
| `force` | no | `false` | `true` bypasses the idempotency pre-check entirely (the pre-check is not even run) and re-derives the whole run. The **only** way to overwrite a delivered, conformant report. Same semantics as `morning-ground-state`'s flag (OMN-16972). |

Outputs, per registry root (the first root keeps these names; another root adds its label to the stem), committed in a detached docs_repo worktree and landed by one pull request that the node opens and never merges:

- `beta/tracking/<date>-worktree-prune.md` — the report
- `beta/tracking/<date>-worktree-prune.json` — the machine-readable decisions

Both paths are relative to the **docs_repo** clone, not to `registry_root`.

### Output root — OMN-17235

Per the operator ruling of **2026-08-31** (and OMN-16990 DoD 8): *plans for current
work, deep dives, and tracking / status / rollup artifacts go to
docs_repo.* Since the 2026-09-26 freeze (OMN-19625, OMN-19744) doctrine and ADRs go
there too (`reference/`), brainstorming to `beta/plans/_scratch/`; registry_root has no carve-out.

Before OMN-17235 this workflow hardcoded `docs/tracking/` under `$registry_root` and its
agent brief carried an explicit "EXCEPTION: registry_root docs/process files commit
path-scoped" carve-out. **That carve-out is deleted.** Every path in the table above
is relative to the **docs_repo clone**, read from
`DOCS_REPO_PATH` (or the request's `kb_path`) — **fail-fast, no default,
no `registry_root` fallback** (CLAUDE.md Operating Rule 8). An unset variable refuses the run
with a message naming the variable rather than silently picking a path. The node
commits the reports in a detached worktree of that clone (never in the canonical
checkout itself) and opens the pull request there.

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


Three phases run **sequentially** inside one handler call (`handlers/handler_morning_worktree_prune.py`): a read-only
Precheck gates the other two (see [Idempotency](#idempotency--the-same-date-re-dispatch-guard-omn-17225)
below), then Sweep classifies and reports but cannot remove anything, then Prune — skipped entirely on
a dry run — is the only surface that can remove anything, and it does so by re-running the same
committed script rather than by deleting anything itself. One Land step after the last phase scrubs and
commits the reports and opens the single pull request. No phase is an agent turn: a phase that fails
raises and the dispatch fails, it is never swallowed.

---

## Idempotency — the same-date re-dispatch guard (OMN-17225)

**Ticket: OMN-17225**, extending **OMN-16972**'s `morning-ground-state` guard to this lane.

### The friction

Measured **2026-09-16**: the Sweep phase was dispatched **twice** for the same run date. Per [How
the classifier is launched](#how-the-classifier-is-launched-omn-16901-2026-09-14), Sweep launches a
30-90 minute classifier scan detached under `heavy_lock`. The duplicate dispatch had **already
launched that classifier** (pid `57245`) before a live ledger check — run inside its own agent turn
— found the first pass's `CLAIM` and `TERMINAL` rows and its committed report and open PR
(`ROLLING_WORK_LEDGER.md` `:2354`-`:2355`, `lane=worktree-prune-sweep-dup-0833`,
`outcome=DUPLICATE_DISPATCH_NO_NEW_SCAN`). The duplicate lane then killed its own classifier process
tree and removed the lock files it had created before any report reached the docs_repo
clone. That self-detection and cleanup were **correct** — no report was overwritten and no
double-commit landed — but several minutes of classifier scan time were spent before the check ran.
The guard below moves the identical ledger question in front of the classifier launch.

### The guard

One deterministic check (`handlers/handler_prune_precheck.py`, no agent and no model call) runs before
Sweep and answers a single question: has the scope this dispatch actually asked for already been
delivered, or is a peer lane delivering it right now? It reads the docs_repo clone's
`origin/main` as the clone last saw it (it never fetches, so a stale ref can only make the answer
`run`), the rolling ledger and its archive rolls, and the date's run-state lock.

| Verdict | Condition | Result |
| -- | -- | -- |
| `already-delivered` | the Sweep report pair is on `origin/main` and conformant for this date, for every root, **and**, only when `execute: true` was requested, a commit exists whose subject matches `worktree prune executed <date>` | `{ short_circuited: 'already-delivered', phases_run: [] }` — neither Sweep nor Prune runs |
| `peer-owned` | a live, un-`TERMINAL`-ed ledger `CLAIM` naming one of this workflow's lane stems and this run date, younger than 90 minutes, or the date's run-state lock held by another run | same short-circuit shape, `short_circuited: 'peer-owned'` |
| `run` | anything else — every failed or indeterminate read included | Sweep (and, if requested, Prune) run normally |

### Scope-aware conformance — this workflow can be asked for two different things

Unlike `morning-friction-sweep`, a re-dispatch of this workflow can legitimately ask for **more**
than the first dispatch did: a dry classify (`execute: false`) versus classify-plus-remove
(`execute: true`). `already-delivered` therefore means *the specific scope this dispatch requested*
is already done, not merely that *some* prior run touched this date:

- **`execute: false`** (the dry run) — only the Sweep report needs to be delivered. (The 04:20 tick
  does not dispatch this node at all: it runs the unattended module.)
- **`execute: true`** — **both** the Sweep report **and** evidence of a completed Prune pass for
  this date must exist. The pre-check reads the kb-internal clone's `origin/main` log for the exact
  subject `worktree prune executed <date>` against the report paths (the Land step commits
  precisely that subject when `--execute` ran) — if the Sweep report exists but that commit does not, the
  verdict is `run`, naming which half is missing.

### The one stated residual

A dispatch that requests `execute: true` when only a dry Sweep for the same date was previously done
does **not** skip Sweep — the whole run re-derives, including a second classifier scan. Sweep is
safe to repeat (it only classifies and commits a report; it never removes anything), so this is
wasted classifier time in the rare case someone escalates to `execute` after an unrelated same-date
dry run — never a correctness bug, since Prune always re-validates the predicate against live state
regardless of which Sweep pass produced the report it read. A finer-grained guard could skip Sweep
and run only Prune against the prior commit, but Prune is written expecting the in-run sweep
outcome from the same dispatch, not a foreign commit from a different one — building that
resumability was decided against here (the OMN-17225 ticket body: *"decide on read, do not assume
shared code is cheaper for two callers"*) in favor of the simpler, still-correct whole-run guard.

### Why peer-owned matching is a SUBSTRING, not an exact list

Same measured reason as the `morning-friction-sweep` guard: this workflow's own ledger rows on
2026-09-16 show `lane=worktree-prune-sweep`, `worktree-prune-sweep-dup-0833` and
`worktree-prune-sweep-2026-09-11-retry` all naming the same Sweep phase
(`ROLLING_WORK_LEDGER.md` `:2354`-`:2355`). The pre-check matches on the lane field **containing**
one of the phase stems (`worktree-prune-sweep`, `worktree-prune-execute`, `worktree-prune-publish`,
`worktree-prune`) plus the run date appearing in the row's own text.

### The clock, the fail direction, and `force`

Same as `morning-ground-state` and `morning-friction-sweep`: one clock reading, returned as
`clock_utc`, used for the 90-minute comparison. An **UNKNOWN** pre-check (any read that fails, or a
check that raises) falls through to a **full run**; it never skips. `force: true` bypasses the
pre-check entirely (it is not even run; the result says `precheck_ran: false`) and is the only way to
overwrite a delivered, conformant report.

### Validation

`tests/worktrees/test_morning_worktree_prune_node.py` drives the handler with the phases faked and
asserts the DoD directly: a same-date re-dispatch with an `already-delivered` or `peer-owned` pre-check
verdict runs **zero** phases — meaning the classifier is never launched — and a `run` verdict (or
`force`) runs Sweep (and Prune, when requested) normally. Its legacy-parity case replays the golden
output of the retired Workflow script (`tests/worktrees/fixtures/morning_worktree_prune_legacy_parity.json`,
captured from that script's own dry-read at `b723e3b`) and holds the new handler to the same phase
sequence, short-circuit verdicts, force bypass and unknown-pre-check fall-through. The tests run in the
required `ci` job's whole-tree pytest; the separate `morning-worktree-prune contract` workflow is gone
with the script it ran.

---

## The predicate

Declared once in this contract and executed by the committed classifier's pure predicate (`omniclaude/src/omniclaude/hooks/lib/worktree_prune_policy.py`); the node quotes no second copy and passes no predicate text anywhere. It is the whole safety argument, so it must not drift. Two parts, evaluated in order: **eligibility fires, safety gates.**

### 1. Eligibility — the trigger

**Content-keyed as of OMN-18370** (operator RULING, `docs/tracking/ROLLING_WORK_LEDGER.md:7870`, 2026-09-14; shipped in `omniclaude#2165`, squash `91bb11a6`). This supersedes the ticket-close-keyed rule quoted at the top of this document.

No live lane owns the worktree: the path carries an identifiable `OMN-NNNN` ticket — without one, "no open `CLAIM`" cannot be established at all, so an untickable path fails closed — and that ticket carries no ledger `CLAIM` newer than its newest `TERMINAL` row.

The ticket's own tracker lifecycle state (`Done` / `Canceled` / `In Progress` / `Backlog` / `Unknown`) is **observed and reported as triage context, but decides nothing.** An empty or fully-merged worktree carries no work regardless of the ticket, so a worktree under an `In Progress` or `Backlog` ticket is removable exactly like one under a `Done` ticket, provided part 2 also passes.

**Former precedence note — retained for history, no longer applicable.** An earlier revision of this rule read "Linear terminal **OR** ledger `TERMINAL` with no newer open `CLAIM`" alongside "tickets still open are NEVER eligible" and had to resolve the collision between them (the "NEVER" clause won; the ledger fallback applied only when tracker state was `UNKNOWN`). OMN-18370 removed the collision at its root: ticket lifecycle is no longer part of the eligibility trigger at all, so there is nothing left to arbitrate.

### 2. Safety — the gate

Applied only after eligibility passes:

- working tree clean (`git status --porcelain` empty), **and**
- no stash attributable to the branch, **and**
- not a detached HEAD, **and**
- the base ref resolved (`origin/dev`, else `origin/main`), **and**
- every git probe behind those facts actually completed, **and**
- **one of** the three limbs the OMN-18370 ruling names as already holding a commit safely:
  - **(a)** zero commits ahead of the resolved base — **or** every ahead commit content-equivalent there (no `+` lines from `git cherry`), **or** the tree-diff against the base empty (`git diff --quiet <base>...HEAD`, the shape a squash merge leaves behind once the squash lands); **or**
  - **(b)** the branch's pull request is **MERGED** (`git diff --quiet` against the merge base cannot see this on its own — a squash-merged branch still shows its own diff there); **or**
  - **(c)** the branch is **pushed to origin at this exact HEAD** — the ruling's one sanctioned way to clear an unmerged commit, since a commit that is on origin is no longer only-local and the worktree no longer holds it uniquely.

That last one is not a formality. A failed `git status --porcelain` — timeout, `OSError`, a
broken gitdir pointer — returns empty stdout, and empty stdout read as a fact means *clean
tree*; a failed `git rev-list --count` read the same way means *nothing ahead*. Those are
exactly the two facts that authorise a deletion. Every probe's exit code is checked and any
failure is recorded by name, so an unreadable fact refuses the gate instead of being inferred
away.

A PR merge is an **input to part 2**, never a trigger for part 1.

### Everything else is triage, never a deletion

Dirty, ahead-unmerged-and-unpushed-and-unmerged-PR, claimed, no ticket, unresolvable base, unreadable — none of it is ever deleted. Each becomes a triage row so a human or the next `morning-friction-sweep` adjudicates it. This is the live `EnumPruneBlockReason` vocabulary in `worktree_prune_policy.py`; the ticket-lifecycle-keyed reasons an earlier revision of this table carried (`ticket_not_closed`, `ticket_unresolved`) were removed by OMN-18370 — the tracker's lifecycle state is still resolved and shown per row as triage context, but no longer names a block reason of its own.

| Block reason | Half | Meaning |
| -- | -- | -- |
| `no_ticket` | eligibility | Directory name carries no `OMN-NNNN` identifier — "no open `CLAIM`" cannot be established at all. |
| `open_claim` | eligibility | A ledger `CLAIM` newer than the `TERMINAL` row — a live lane owns this. |
| `dirty_tree` | safety | Uncommitted changes. Merged-ness never launders them. |
| `ahead_unmerged` | safety | Commits ahead that are in neither the base, a merged PR, nor pushed to origin at this HEAD. |
| `unpushed_stash` | safety | A stash entry naming this branch. |
| `detached_head` | safety | No branch; ahead-ness cannot be proven. |
| `base_ref_unresolved` | safety | Neither `origin/dev` nor `origin/main` resolved. Fails closed. |
| `facts_unreadable` | safety | A git probe failed (not merely timed out), so a safety fact is UNKNOWN rather than clean. Fails closed. |
| `probe_timeout` | safety, but reported as `TIMED_OUT` not `TRIAGE` | A git probe exceeded its time budget under host load (OMN-18370 AC-4). A statement about the host, not the worktree — never counted as a safety finding. |
| `open_pr_fence` | safety, opt-in (`--hold-open-pr`, OMN-19399) | The branch has an OPEN pull request, or the open-PR listing did not resolve. Passed by every unattended run. |
| `partial_mutation_debris` | neither — a distinct predicate (OMN-16951) | The worktree's `.git` link is already gone but the directory still holds content. See [Partial-mutation debris](#partial-mutation-debris-omn-16951) below. |

Every violated condition is reported, not just the first, so one triage row tells the whole story (OMN-18370 AC-3: both eligibility and safety are always evaluated, never short-circuited).

---

## The rescue-only class (OMN-18442)

**This is a second, separate predicate, and it is the only surface of this lane that destroys work.** It does not widen the predicate above, never moves a row from triage to safe, and is evaluated after it against a different question.

### The class the content-keyed predicate cannot reach

A **rescue-only** worktree is one whose branch never opened a pull request and has none open — work a rescue pass swept into a branch that nobody came back for. Measured live 2026-09-16 across 668 worktree records: **415 are rescue-only at any age**, and **233** of those clear every non-age clause.

The predicate above can never remove one of them, and not because of a bug. Being dirty or ahead-unmerged is *exactly why they were rescued*, so every one fails the safety gate on `dirty_tree` or `ahead_unmerged` permanently. The population only grows. Without a second class, the daily prune reports these rows forever and drains none of them.

### Authorization — a standing operator grant, not a lane's judgement

Operator ruling **2026-09-16**, verbatim: **"Seven days is fine"**, answering a recommendation to remove rescue-only worktrees older than seven days without preservation, with an explicit exclusion for hand-held worktrees, and to make that the standing policy of this prune.

The durable authorization is the `OPERATOR-CONSENT` row at **`docs/tracking/archive/ROLLING_WORK_LEDGER_2026-09-18-split.md:2368`** (stamp `2026-09-16T14:34:06Z`, lane `worktree-rescue-abandon-7d-1435`), first cited at `docs/tracking/ROLLING_WORK_LEDGER.md:3624` before the 2026-09-18 ledger roll moved it into that archive split, in the CLAUDE.md rule-18 shape with both an `APPROVED SCOPE` and an `OUT OF SCOPE` list. The execute pass **re-reads that row** before removing anything. A citation is not the grant — the row is, and a row missing its `OUT OF SCOPE` half looks identical to a valid one to the next lane that cites it. If the row does not resolve, or does not name this scope, the rescue-only pass removes nothing and says so.

### The policy values, declared once

The predicate is the pure module **`src/ops_tooling_pkg/worktrees/prune/rescue_only_policy.py`** in this repository — `classify_rescue_only`, its constants, and its hand-held loader. It is the single declaration; the node's classifier invocation reads the numbers from it and this document carries the same values, and `tests/test_morning_lane_rules.py` asserts the module, the invocation and this table agree, so a value changed in one place goes red rather than diverging silently.

| Constant | Value | What it governs |
| -- | -- | -- |
| `RESCUE_ONLY_MAX_AGE_DAYS` | **7** | Both age limbs. A candidate's last commit **and** newest git-visible file must each be strictly older than this. |
| `CLAIM_FENCE_DAYS` | **7** | A ledger `CLAIM` naming the ticket inside this window fences the row. Deliberately a separate constant carrying the same number, because "how old before abandoned" and "how recently did a lane claim it" are two policy questions — tying them in source would move the fence the next time the bar moves. |
| `CONSENT_ROW` | `docs/tracking/archive/ROLLING_WORK_LEDGER_2026-09-18-split.md:2368` | The grant the execute pass acts under and re-reads. |
| `HAND_HELD_FILE_NAME` | `hand_held_worktrees.yaml` | The declared exclusion list, resolved beside the module. |

### The bar is a conjunction, and mtime is measured over git-visible files only

Both age limbs must pass. A tree can carry a 40-day-old commit and a file edited an hour ago; a tree can carry a commit made minutes ago by a rescue pass over files last touched a month back. Either limb alone mis-ages a real worktree in the direction that destroys work.

**`mtime` is the newest of `git ls-files` plus `git ls-files --others --exclude-standard`. Never a filesystem walk.** Measured 2026-09-16 by lane `worktree-rescue-abandon-1330`: a walk reported 663 of 671 worktrees touched within 30 days, because `.grimp_cache/` and `.import_linter_cache/` entries written by a pre-commit run were the newest files, while all 22 uncommitted **source** files in the same tree were 33 days old. Excluding cache directories by name requires guessing the next tool's cache name; asking git drops them out by construction.

### The fences — any one holds the row

Taken from the consent row's own `OUT OF SCOPE` list. Every reason is reported for every held row, never only the first.

| Hold reason | Meaning |
| -- | -- |
| `not_rescue_only_open_pr` | The branch has an open pull request — the work is in review, not lost. |
| `not_rescue_only_merged_pr` | The branch merged a pull request. That row belongs to the content-keyed predicate above, not here. |
| `detached_head` | No branch, so "never opened a pull request" cannot be established at all. Fails closed. |
| `commit_within_window` | The branch tip is at or under the bar. |
| `mtime_within_window` | The newest git-visible file is at or under the bar. |
| `claim_within_window` | A ledger `CLAIM` named this ticket inside `CLAIM_FENCE_DAYS`. |
| `live_lane` | A lane live in the running session owns the ticket. |
| `stash_attributed` | A stash entry names the branch; removing the worktree would strand it. |
| `hand_held` | The declared exclusion file names this branch or path. |
| `path_missing` | The directory is gone — an administrative record, whose remedy is `git worktree prune`, not this policy. |
| `facts_unreadable` | Any probe did not complete, so a fact is UNKNOWN rather than observed. An empty result is not evidence of absence; here the difference is destroying work. |

### The hand-held exclusion bounds the grant

`hand_held_worktrees.yaml` in this directory names worktrees a **person** is working in by hand. A named worktree is never a candidate, whatever its age.

This file is the half of the ruling that bounds it: the operator's answer carried an explicit exclusion for hand-held worktrees, so a policy with no way to say *not this one* would be a different ruling than the one given. Each entry names **either** a `branch` (matched exactly) **or** a `path_contains` (matched as a substring), never both, plus a `reason` and an `added` date. Nothing in it is a regular expression, deliberately — a regex in an exclusion list is how an exclusion quietly grows to cover more than it was written for.

An entry is not permanent. Delete it when the person holding the worktree is done: a stale exclusion is indistinguishable from a live one at removal time, and the population this policy exists to drain is made of worktrees nobody remembered to release.

### Zeros need a positive control

Rescue-only membership turns on a pull-request lookup returning empty. Before any zero is reported, the same lookup runs against a branch with a **known merged** pull request and must come back `MERGED` — otherwise an empty result is indistinguishable from a broken query (CLAUDE.md rule 16). No probe in this pass redirects stderr to `/dev/null`. The control and its result go in the report's Run notes.

### Where it runs — the committed classifier answers this class (OMN-18442 AC6)

`omniclaude/scripts/worktree_auto_prune.py` executes the clause set. The node's Sweep and Prune phases pass it four flags, each read from the constants in the table above and never typed as a literal:

```
--rescue-only
--rescue-only-age-days <RESCUE_ONLY_MAX_AGE_DAYS>
--rescue-only-claim-fence-days <CLAIM_FENCE_DAYS>
--rescue-only-hand-held "${OPS_TOOLING_PKG_HOME:?set OPS_TOOLING_PKG_HOME}/src/ops_tooling_pkg/worktrees/prune/hand_held_worktrees.yaml"
```

- **Sweep** — the classifier writes the `## Rescue-only candidates` section into the report (path, repo, branch, commit age, git-visible mtime age, PR state, last `CLAIM` age, verdict with every hold reason) plus a held-back count by reason, and the JSON report carries the same rows under a `rescue_only` object. The node **reads** the counts off that report; it does not re-derive the class. Nothing is removed in this phase, whatever `execute` says.
- **Prune** — re-derives the set against live state and removes exactly what still classifies `remove`, under the standing consent, listing every removal in the report.

**The age bar is a required flag with no default in omniclaude, and that is the point.** omniclaude is a public repository that cannot depend on this one, and its CI checks out no sibling clone — so a default there would be a second copy of the policy that nothing compares, and a test that resolved this module through an environment variable would *skip* in that CI rather than run. Making the flag required keeps this directory the single place the number is declared and makes a run that forgot to pass it an error rather than a silent adoption of a number nobody ruled on. `tests/scripts/test_worktree_auto_prune_rescue_only.py` in omniclaude asserts mechanically that no such constant is declared there.

**Two homes, one value — stated rather than implied.** `src/ops_tooling_pkg/worktrees/prune/rescue_only_policy.py` stays the declaration of the values and the reference statement of the clauses; `omniclaude/src/omniclaude/hooks/lib/worktree_prune_policy.py` holds the executable predicate, beside the content-keyed one, which is where this document's own architecture note says a pure predicate for this lane belongs so an event hook can call it without a scheduler. The two clause sets are not mechanically pinned equal to each other, because neither repository's CI can see the other; each is pinned by its own fixtures, in both directions, and the value a drift would make dangerous is single-homed here.

**What the classifier cannot observe, named rather than left absent.** It runs in its own process, outside any lane's session, so `live_lane` is reported `false` for every row — that fence is the Prune phase's to apply against live state, never the report's to claim. And the fail-closed direction is structural: an empty pull-request lookup (what a broken `gh` query returns) holds every row on `facts_unreadable` rather than reading as "no pull request", and an unsupplied or unparseable hand-held list holds every row on `hand_held_list_unavailable` — the classifier's own addition to the reason vocabulary above, because a pass that cannot read the exclusion list has not established that anything is unexcluded.

Closed by `omniclaude#2199`.

---

## Partial-mutation debris (OMN-16951)

A `.git`-gone leftover directory is a **distinct shape**, not a subclass of the eligibility/safety predicate above. `discover_worktrees` finds worktrees via a `*/.git` glob — a linked worktree's `.git` is a *file* — so once that file is gone the directory is invisible to it, not merely unprunable. Plain `git worktree remove` can never succeed on it either: there is no linked `.git` for git to resolve from the worktree side. Left alone, a directory in this state disappears from the report entirely rather than failing visibly, and any refusal recorded before OMN-16951 landed showed only `git worktree remove refused: no output` because `_git()`'s stderr was discarded — the refusal reason was never captured.

The classifier now runs a **second discovery pass**, independent of `discover_worktrees`: every ticket-dir child under the worktrees root that carries no `.git` of its own but still holds file content is a candidate (an empty leftover is not debris — `cleanup_empty_ticket_dirs` already reclaims those). For each candidate it cross-references every canonical clone's `git worktree list --porcelain` (one call per clone in the registry, not per worktree) to find the owning clone and its administrative annotation.

The pure predicate, `classify_partial_mutation_debris` in `worktree_prune_policy.py`, decides remediation on exactly one conjunction — both halves provable from observed facts alone:

- the owning clone's `git worktree list` record for this path already says **`prunable`** (git itself agrees the worktree is administratively gone), **AND**
- every remaining file's content is a blob **already present in that clone's object database** (`git hash-object` on the file matches something `git cat-file -e` finds) — byte-identical, so nothing unique is lost.

Both true → `auto_removable`. Either false — no owning clone found, the record not `prunable`, or even one file that cannot be proven reachable — → `triage`, reported for human adjudication, never removed. The conjunction is never weakened to "most files reachable" or "probably the same repo": this predicate never re-derives ticket eligibility, and a debris directory with unverifiable content is never auto-removed regardless of ticket state.

**Remediation, on `auto_removable` rows only, and only on `--execute`:** `git worktree prune` in the owning clone (administrative-record-only — this never touches the directory), then remove the now-orphaned leftover directory. Never `--force` on the git side, and the directory removal is not a blind `rm -rf` — it runs only after the predicate already proved every remaining file's content is reachable. A `triage` row is never touched by the sweep.

The report gains a **`## Partial-mutation debris (N)`** section (path, ticket, repo, remediation, evidence) and its own header count line. The `## Removals` section gains four columns beyond `Path`/`Result`: `Command`, `Exit code`, and `Stderr` — the fix for the "no output" refusal rows, applying to every removal attempt (both a plain `git worktree remove` refusal and a debris remediation attempt), not only the debris case.

---

## How the classifier is launched (OMN-16901, 2026-09-14; OMN-20681)

**The node holds the classifier in its own process until the report exists. No phase waits
inside an agent turn.** The 2026-09-14 rule — never run the 30-90 minute scan inside a turn that
can end early — now holds by construction: the Sweep and Prune phases call
`Shell.run(...)` from `handlers/handler_prune_phases.py`, the same one process seam the
unattended runner uses, and block there with a timeout that is shorter than the heavy lock's hold.

**Why.** At registry scale the scan takes 30-90 minutes (706 worktrees, 23 canonical
clones fetched, 371 ticket states resolved from the tracker, several `git` calls per
worktree). A foreground agent turn cannot hold that long. On four consecutive mornings
the sweep agent ran the classifier in-turn, hit the ceiling, read a truncated log
through a non-follow `tail`, and returned `BLOCKED` with **no report at all** —
`ROLLING_WORK_LEDGER.md` `:6402` (2026-09-11), `:6917` (09-12), `:7168` (09-13),
`:7736` (09-14). The in-turn launch was the whole defect; nothing about the classifier
needed to change.

**The shape.**

| Property | Value | Why it is load-bearing |
|---|---|---|
| process | one `Shell.run` per root, in the handler's own process | no agent turn is in the path, so no hook can end the run early |
| output | `log_path=` direct redirection, no pipe | a pipe makes the exit status the *reader's*, and a non-follow `tail` truncates the run — the shape all four BLOCKED reports came out of |
| lock | `heavy_lock.py --lock /tmp/omninode-worktree-classifier.lock` | **not** the default `/tmp/omninode-heavy-suite.lock` |
| hold | `--max-hold 3h --timeout 30m` | bounded; the lock is released by the kernel on process death, so there is no stale-lock class |
| completion | exit 0 **and** the report JSON exists, then `verify_report` on it | the report existing is the completion fact; the log is not |

**Why a dedicated lock.** `heavy_lock.py` defaults to the machine-wide protocol lock
that serializes the heavy pytest suites. This scan is git- and tracker-I/O bound and
contends with none of them for CPU, but holding that lock for 63 minutes made a peer
lane's `dod_verify` wait its entire 600s budget and fail closed
(`ROLLING_WORK_LEDGER.md` `:7743`). `--lock` gives the classifier an independent
critical section that still serializes classifier against classifier — which is the
only mutual exclusion it actually needs. No change to `heavy_lock.py` was required;
the flag already existed.

**Never `pkill -f`.** A run that must be stopped is stopped by its pid, never by command
substring: `pkill -f` matches across every process on the host, and a lane using it to stop
one doomed run instead killed seven peer lanes' governed pushes
(`ROLLING_WORK_LEDGER.md` 2026-09-03T20:20:07Z). Relaunching a classifier that may
still hold the lock is equally forbidden — the second run simply waits on the first, and the
node's date lock reports it as `peer-owned` to the pre-check.

The `--execute` phase runs the same way, for the same reasons, on the same lock.

Pinned by `tests/worktrees/test_morning_worktree_prune_node.py` — the classifier invocation case
drives the Sweep phase against a fake process seam and asserts the dedicated lock path present
and the machine-wide lock absent, the direct log redirection with no pipe, the rescue-only
flags equal to the policy module's numbers, and that a dry sweep never carries `--execute`,
`--hold-open-pr`, `--no-debris` or `--no-registration-prune`.

---

## Report format

`beta/tracking/<date>-worktree-prune.md`, in this order. The classifier writes sections 1–5; the node's Sweep phase appends 6.

1. **Header** — generated timestamp, root, mode (`DRY RUN — nothing was removed` / `EXECUTE`), scanned / safe / triage / partial-mutation-debris counts, and how many ticket states the tracker actually resolved.
2. **Triage block reasons** — reason → count, descending.
3. **Prune candidates** — path | ticket | branch | eligibility evidence | safety evidence. **Both evidence cells must be non-empty.** A safe row with an empty evidence cell is a classifier defect, not a green light.
4. **Triage rows** — path | ticket | branch | ahead | dirty files | block reasons | ledger claim. Every non-prunable worktree appears here exactly once. This is the same shape as the OMN-16775 hazard row, deliberately, so the friction sweep can consume it.
5. **Partial-mutation debris** (OMN-16951) — path | ticket | repo | remediation (`auto_removable` / `triage`) | evidence. Distinct from the triage rows above: these are `.git`-gone directories the eligibility/safety predicate never sees. See [Partial-mutation debris](#partial-mutation-debris-omn-16951).
6. **Run notes** (appended by the Sweep phase) — which flags the run used, anything struck in the sweep's sanity check and why, and any source the classifier could not read.

On an `--execute` run the classifier appends a **Removals** section: path | result | command | exit code | stderr | detail — for both a plain worktree removal and an `auto_removable` debris remediation. Every attempt, success or failure, carries the exact command and the real stderr text (OMN-16951 defect 1) — never the flat `no output` a stderr-discarding capture used to produce regardless of cause.

---

## What changed when the Workflow became a node (OMN-20681)

The retired Workflow script drove three agent turns. The node does the same phases in one handler
call, and holds the same safety line. Each difference below is deliberate and is pinned by a test
in `tests/worktrees/test_morning_worktree_prune_node.py` or `..._phases.py`.

| Retired Workflow | Node | Why |
| -- | -- | -- |
| Precheck was a `sonnet` agent reading the kb-internal checkout, the ledger and a live `date -u` | `HandlerPrunePrecheck` reads `origin/main` as the clone last saw it, the ledger and its archive rolls, one clock reading, and the date lock | no model call in a guard; a stale ref can only make the answer `run`. Never fetches. |
| `peer-owned` was a ledger `CLAIM` | a ledger `CLAIM`, **or** the date's run-state lock held by another run | the node writes no `CLAIM`, so two node runs must see each other some other way |
| Delivered meant the report was committed and clean in the checkout | delivered means the report pair is on `origin/main` | reports land by pull request; a local commit nobody can find is not delivery |
| A determinate shortfall (nonconforming report, execute half missing) and a live peer both held: the brief did not say | the peer wins (`peer-owned`); only an indeterminate read (a `git` failure that is not a missing path) forces `run` | starting a 30-90 minute scan beside a live peer is the 2026-09-16 incident |
| `fences` were free text an agent was asked to respect | a fence's `OMN-<digits>` tickets strike matching safe rows into Withheld; an `execute` run with a fenced safe row, or a fence with no ticket token, **refuses to run `--execute`** | the classifier has no per-ticket exclusion, so an agent could never keep a fenced row out of an `--execute` pass |
| One root | every registry root, as the unattended runner does (ops_tooling_pkg's `omni_worktrees` since 2026-09-24); `worktrees_root` pins one | the operator ruling of 2026-09-24T12:53:21Z |
| Sweep committed a local branch in the kb-internal checkout; only an `execute` run pushed and opened a PR | one Land step after the last phase, dry or execute: detached worktree, branch `automation/omn-16901-worktree-prune-<date>`, one pull request, never merged | the canonical clone is never committed in; a dry report now lands for the next precheck and the friction sweep to read |
| Agents wrote `CLAIM`/`TERMINAL` ledger rows and returned `ledger_rows` | the node writes no ledger rows and never pages; the dispatching lane owns them | the CLAIM contract exempts only the fleet's named script writers |
| A phase failure was an agent's `BLOCKED` report | a phase failure raises and the dispatch fails | never swallowed |

Stated residuals. (1) A fenced ticket that becomes prunable between the Sweep report and the
`--execute` re-run is not in the Sweep report the fence check reads; the classifier re-derives the set
at removal time and has no exclusion flag. (2) A forced re-run for a date whose branch is already
pushed fails at the push, after the work; the reports remain in the run-state directory.

---

## Safety posture

- **Dry-run is the default.** `--execute` is required to remove anything, at both the classifier and node layers.
- **Removal uses plain `git worktree remove`, never `--force`.** Git re-checks cleanliness itself, independently of the policy that just approved the removal. If git refuses, the refusal stands — it is recorded as a failure, never escalated.
- **The node never hand-deletes.** No `rm -rf`, no `--force`, no editing the JSON to move a row from triage to safe. The Sweep phase may only strike a safe row (empty evidence cell, or a fenced ticket) into the Withheld list, and an `execute` run with a fenced safe row refuses to run `--execute`. If the node disagrees with the classifier, the classifier wins and the disagreement is recorded.
- **The classifier refuses to run without the ledger** (exit 2). A prune with no claim-awareness is exactly the OMN-15551 hazard, so an unreadable ledger is a hard stop, not a degraded mode.
- **Phase 2 re-runs the whole predicate.** A worktree that went dirty, gained a commit, or got re-claimed between classification and removal drops out of the safe set on its own.
- **Tracker unavailability degrades toward not-deleting.** No `LINEAR_API_KEY` (or `--no-tracker`) means every state is `UNKNOWN`, and eligibility falls back to ledger `TERMINAL` rows — which fails closed when there is none.

---

## The shape decision — sibling schedule, not a ground-state step (OMN-18688 AC1)

**Decided 2026-09-18. The live shape is the SIBLING schedule below, and that is accepted as satisfying the operator's intent. The prune is NOT folded into `morning ground-state node`, and must not be.**

The operator consent row (`docs/tracking/ROLLING_WORK_LEDGER.md:4236`) says the prune runs "on this Mac as a step of the morning ground-state workflow". Read literally that is one file; read as the schedule it names, it is the shape already running. OMN-18688 flagged the ambiguity rather than assuming either reading, so here is the call and its reason.

**The decisive reason is the dependency direction.** The prune fires at 04:30 and `morning-ground-state` at 04:43, *specifically so the ground-state run sees this report* — that ordering predates this decision and is the line directly below. Ground-state is a **consumer** of the prune's output. Folding a producer into its own consumer inverts that dependency and destroys the only reason the 13-minute gap exists.

Three more, each sufficient on its own:

| Reason | Detail |
| -- | -- |
| Runtime | The classifier scan runs 30–90 minutes over a registry-scale root. `morning-ground-state`'s phases gate each other and terminate in `GOAL.md`, the artifact the OMN-17168 SessionStart hook reads. A step that long delays the one file the day depends on. |
| Idempotency | The two carry different same-date re-dispatch keys and write different artifacts. Folding them collapses two independent re-run decisions into one, so a re-run of either forces a re-run of both. |
| Architecture | This sweep is the **executor/backstop** for a predicate whose end-state is event-driven (see [Architecture note](#architecture-note--the-sweep-is-the-executor-not-the-design)). Coupling a backstop to a workflow that has nothing to do with worktrees is the wrong dependency, and it is the coupling that would have to be unpicked when the event path lands. |

The operator's words in the same consent row are *"OK fine for creating a new workflow rather than a cron"* — approving a **workflow** over a cron. A sibling named workflow on the morning schedule is exactly that; a cron is what was declined.

**What the shape decision does not change.** The removal keys are unchanged on both hosts and in both shapes: a PR merged or closed, **or** the branch gone upstream, **and** a clean tree, **and** no open ledger `CLAIM` row. Age is an alarm input and **never a deletion key** — the consent row says so in those words, and the only place a day count appears in a removal path is the rescue-only class, which this script reports and never removes.

**Both surfaces state this**, so a reader who greps either one gets the same answer: `metadata.sibling_workflows` in `src/ops_tooling_pkg/nodes/node_morning_ground_state_orchestrator/contract.yaml` names this node (`morning-worktree-prune`) as a sibling and keeps it out of `phase_order`, and this section is the reason of record. `tests/test_morning_lane_rules.py` asserts they agree — a future change that folds the prune in has to update both or go red.

---

## Scheduling — wired 2026-08-30 (OMN-17173)

Fires at **04:30 local**, between `morning-friction-sweep` (04:15) and `morning-ground-state` (04:43), so the ground-state run sees this report.

launchd `StartCalendarInterval` user agent — **wired and proven, OMN-17173**.

| Workflow | Label | Fires |
| -- | -- | -- |
| `morning-friction-sweep` | `ai.omninode.morning-friction-sweep` | 04:15 local |
| `morning-worktree-prune` | `ai.omninode.morning-worktree-prune` | 04:30 local |
| `morning-ground-state` | `ai.omninode.morning-ground-state` | 04:43 local |

Each agent runs `launchd/morning-workflows/morning_workflows_tick.sh <workflow>`, which writes a **firing receipt before it does any work** and then invokes the workflow through headless Claude Code (`claude -p "Workflow({ scriptPath: '<absolute package script>', args: { date: '<today>' } })"`). **Except this workflow:** since OMN-19399 the driver runs `unattended.py` instead of `claude -p` (see [The scheduled run is unattended](#the-scheduled-run-is-unattended-omn-19399)).

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

Three artifacts, one contract:

- `src/ops_tooling_pkg/nodes/node_morning_worktree_prune_effect/` — the runnable orchestration (contract, handlers, typed models)
- `omniclaude/scripts/worktree_auto_prune.py` + `omniclaude/src/omniclaude/hooks/lib/worktree_prune_policy.py` — the classifier and its pure predicate
- this README — the format contract

A change to the predicate, the report format, or the safety posture edits **all of the ones it touches, in the same commit**, and the predicate text in the [The predicate](#the-predicate) section above stays the statement of what the classifier's pure predicate does. Neither half is authoritative alone; a drift between them is a defect in whichever was edited second.

Tests that hold the line, and that a predicate change must keep green:

- `omniclaude/tests/unit/hooks/lib/test_worktree_prune_policy.py` — the pure predicate (OMN-16901, OMN-18370). A dirty tree must never classify safe; an ahead-unmerged branch must never classify safe; a squash-merged branch with an empty tree-diff must classify safe; a branch pushed to origin at its exact HEAD must classify safe. Ticket lifecycle state never blocks eligibility — a clean, zero-ahead worktree under an `In Progress` or `Backlog` ticket IS prunable — and only an open ledger `CLAIM` or a missing ticket does. Also covers `classify_partial_mutation_debris` (OMN-16951): every decision names the `partial_mutation_debris` reason, and `auto_removable` fires on exactly the prunable-AND-fully-reachable conjunction — never a weaker one.
- `omniclaude/tests/scripts/test_worktree_auto_prune.py` — fact collection: ledger claim-awareness (a `CLAIM` after a `TERMINAL` reopens the ticket), stash attribution, tracker state mapping, worktree discovery. Also covers, against real throwaway git repos (OMN-16951): a refused `git worktree remove` surfaces its real command/exit-code/stderr rather than a flat `no output`; a `.git`-gone directory with untouched content classifies `auto_removable`; the same directory with one locally-edited file classifies `triage` instead; `remediate_debris` prunes the administrative record and removes the directory only on the `auto_removable` path.

**The idempotency guard (OMN-17225) is versioned the same way.** The precheck's `PEER_CLAIM_MINUTES`
window, the phase-stem list `PHASE_STEMS` and the scope-aware `already-delivered` conformance rules
are constants of `handlers/handler_prune_precheck.py`; a change to any of them edits this document's
[Idempotency](#idempotency--the-same-date-re-dispatch-guard-omn-17225) section in the same commit.
`tests/worktrees/test_morning_worktree_prune_node.py` is the mechanical check that the two have not
drifted, run by the required `ci` job.

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
