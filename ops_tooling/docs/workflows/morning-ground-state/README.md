# Canonical morning ground-state node (OMN-20673)

The registered `node_morning_ground_state_orchestrator` replaces the former Workflow entry point.
Dispatch it with `onex node node_morning_ground_state_orchestrator --input <command.json>` using
an explicitly configured dev bus. The typed command requires `date`, `correlation_id`,
`emitted_at`, and `tenant_id`; the existing phase arguments keep their camelCase aliases.
The scheduled trigger resolves the packaged `contract.yaml`. Reconciliation reuses
`onex-ledger-reconcile` through a delegated bus phase; no sibling script path is required.

The scheduled driver requires `ONEX_TENANT_ID`, `ONEX_ENVIRONMENT` and `ONEX_CONTRACTS_DIR`,
resolved from the environment then login zsh; missing values fail before dispatch
(`bus_env_unset`, exit 78). Its final output must contain the actual ModelSkillResult JSON
on its own line prefixed `MORNING_GROUND_STATE_RECEIPT ` (one space). The driver checks the
last such line for `status=success`, integer `exit_code=0`, the requested `result.date` and
an object in `result.goal`; absent or invalid receipts fail with `result_invalid`, exit 65.
These checks exclude selftests.

The contract declares start/completed topics and the existing delegation request/reply topics.
Infra `RequestResponseWiring` owns broker communication. The Definition-B handler coordinates
phases; prompt resources and typed phase models preserve their formats. `morning-worktree-prune`
is a sibling workflow, not a ground-state step (OMN-18688 AC1).

Verification: `uv run pytest tests/test_morning_ground_state_node.py tests/test_morning_lane_rules.py -q`.
The parity fixture was captured against the original at `fb456511` before deletion. Nine scenarios
compare phase routing, schema, prompt digest and output. The lab bus test uses the canonical
in-memory bus and recorded phase results because a real full morning writes shared Linear state
and replaces the published session goal.

The admission cap was RESCINDED by RULING 2026-09-21T14:46:45Z; its removed report section stays removed.

# morning-ground-state — format contract

Tickets: **OMN-16841** (node-ified successor) · **OMN-17170** (Reconcile + Goal phases) · **OMN-17195** (Integrate phase) · **OMN-16972** (the Precheck phase / same-date re-dispatch guard) · **OMN-17168** (the SessionStart hook that reads `GOAL.md`) · **OMN-17173** (the missing durable trigger) · Epic cross-link: **OMN-16776**

The morning ground-state run is a **process**, not an ad hoc report. Operator direction, 2026-08-28, verbatim:

> "we need a reusable process, like we do for everything, so it doesn't become an ad hoc report"

and 2026-08-30, verbatim (voice-to-text), on the beta re-baseline specifically:

> "There should be done automatically (this) I believe we have a workflow. If not we should create one. And it should've eventually become a node-based workflow."

and 2026-08-30, verbatim (voice-to-text), on the day's landed work:

> "Every morning we should be trying to come up with a plan to integrate anything that was done the day before."

This document is the **format contract** for that process. The runnable half is the registered node with `contract.yaml`, handler and prompt resources under `src/ops_tooling_pkg/nodes/node_morning_ground_state_orchestrator/`. Neither is authoritative alone — see [Versioning rule](#versioning-rule).

---

## What the process produces

| Artifact | Path | Written by | Lifetime |
| -- | -- | -- | -- |
| *(no artifact — a per-phase run/skip decision)* | — | **Precheck** | the run only; returned as `precheck` |
| Ground-state report | `beta/tracking/<date>-morning-ground-state.md` | GroundState | one per day, kept |
| Date snapshot | `beta/tracking/ground-state-date-snapshots.json` | GroundState (last) | overwritten wholesale |
| Reconciliation report | `beta/tracking/<date>-beta-rebaseline.md` | Reconcile | one per day, kept |
| **Integration plan** | `beta/tracking/<date>-integration-plan.md` | Integrate | one per day, kept |
| **Session goal** | **`beta/GOAL.md`** | Goal | **overwritten wholesale — current state only** |
| **Decisions register** | **`beta/tracking/DECISIONS.md`** | DecisionsRegister | **standing — rebuilt in place every run** |
| Decisions register (machine-readable) | `beta/tracking/decisions.json` | DecisionsRegister | standing — rebuilt in place every run |
| Reconciler rows | `docs/tracking/ROLLING_WORK_LEDGER.md` (in `registry_root`) | LedgerReconcile | append-only |

**Every path in that table except the ledger is relative to the docs_repo
clone, not to `registry_root`.** See "Output root" below.

`beta/GOAL.md` is the canonical path. **OMN-17168's SessionStart hook reads exactly that path** and reports its `state_as_of` age at session start — which is why the path is stable and the file is overwritten rather than dated.

### Output root — OMN-17235

Per the operator ruling of **2026-08-31** (and OMN-16990 DoD 8): *plans for current
work, deep dives, and tracking / status / rollup artifacts go to
docs_repo.* Since the 2026-09-26 freeze (OMN-19625, OMN-19744) doctrine and ADRs go
there too (`reference/`), brainstorming to `beta/plans/_scratch/`; registry_root has no carve-out.

Before OMN-17235 this workflow hardcoded `docs/tracking/` under `$registry_root` and
carried an explicit "EXCEPTION: registry_root docs/process files commit path-scoped"
carve-out in its agent brief. That carve-out is **deleted**. Every phase now:

1. resolves `$DOCS_REPO_PATH` in bash as
   `KB="${DOCS_REPO_PATH:?...}"` — **fail-fast, with no default and no
   `registry_root` fallback** (CLAUDE.md Operating Rule 8). An unset variable aborts the
   phase with a message naming the variable; it never silently picks a path.
2. verifies `$KB` is a clone of `OmniNode-ai/docs_repo`,
3. writes and commits its artifact path-scoped on branch
   `<owner>/omn-17195-morning-<date>` **in that clone**, and
4. leaves the push and the single daily PR to the Goal phase.

Enforcement is mechanical on both ends: the `kb-doc-gate / kb-doc-gate` required
check on `registry_root` `main` (`.kb-doc-gate.yaml`) rejects a new doc-class markdown
file under `registry_root/docs`, and `check_no_local_paths.py` in docs_repo
rejects an `/Users/`, `$registry_root` or `registry_root/<repo>/` reference inside the
published artifacts. Write portable paths in the file bodies.

**The one deliberate exception is `docs/tracking/ROLLING_WORK_LEDGER.md`**, which
stays in `registry_root`. Its literal path is cited by 62 files across omniclaude (4),
omnibase_infra (30) and omnimarket (28); repointing this workflow alone would fork
the append-only ledger across two files and break the §0a claim protocol for every
other lane. Moving it is a fleet-wide repoint of all 62 call sites plus a file
migration — its own ticket. `.kb-doc-gate.yaml` carries a matching **temporary**
single-path allow entry for it, and `scripts/ledger_lock.py` already takes the
ledger path as a positional argument, so no code change gates that move (proven by
`tests/test_ledger_lock_path_parametrization.py`).

---

## Why extension, not a sibling workflow

The 2026-08-30 direction could have been met by a sibling `beta-rebaseline` workflow calling `workflow('morning-ground-state', { date })` as its first step. It was **not**, deliberately:

1. **OMN-17168 already contracts this workflow as GOAL.md's producer.** Its hook requests morning ground-state when `beta/GOAL.md` is stale or missing. A sibling would have made an already-filed ticket wrong on day one.
2. **Reconcile's only input is the ground-state report.** Wrapping adds a nesting layer and a second format contract for no gain.
3. **This contract already has an extension path** — [Versioning rule](#versioning-rule) governs adding a phase. Forking the process is precisely the drift the standing rule forbids.

The cost is accepted honestly: the morning run is now longer, and the reconciliation is serialized behind the ground-state read. `args.publish: false` is the cheap mode for a re-run that must not touch the board.

---


### Isolated report publishing (OMN-18071)

The publishing brief resolves the canonical docs_repo clone read-only, then
runs `canonical_clone_sync.py refresh OmniNode-ai/docs_repo --branch main --wait`.
A failed refresh stops publishing. It pins the refreshed `refs/remotes/origin/main` SHA and
uses `git worktree add -b` at `$registry_root/worktrees/<ticket>/docs_repo`.
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

Write a command JSON file with explicit run identity and date:

```json
{
  "date": "2026-08-30",
  "correlation_id": "12345678-1234-5678-1234-567812345678",
  "emitted_at": "2026-08-30T08:43:00Z",
  "tenant_id": "omninode",
  "publish": false,
  "fences": []
}
```

```bash
onex node node_morning_ground_state_orchestrator --input command.json --timeout 14400 --output receipt
```

Configure the explicit dev Kafka bus and packaged contracts before dispatch.
A deliberate re-run sets `force: true`. To reconcile a later sprint, supply
`planDocs`, `mustDoDoc`, and `offRailsDoc` in the same command. The existing
phase argument names and defaults below remain supported.

| Arg | Required | Default | Meaning |
| -- | -- | -- | -- |
| `date` | yes | — | `YYYY-MM-DD`. Names the output files and scopes "today". Passed explicitly so a run is reproducible and a past date can be re-run. The script throws if it is missing. |
| `fences` | no | `[]` | Free-text standing fences injected into every agent's brief. Empty means fence-free; the agents are still instructed to skip any ticket with an open PR or an un-TERMINAL-ed ledger CLAIM. |
| `planDocs` | no | `['docs/plans/2026-08-29-beta-readiness-plan.md']` | Plan documents whose **falsifiable rows** the Reconcile phase measures ground state against. Array — several plans can be reconciled in one run. |
| `mustDoDoc` | no | `'docs/tracking/2026-08-29-sprint-split.md'` | The ordered must-do / landing-sequence document. Pass `''` to skip. |
| `offRailsDoc` | no | `'docs/tracking/2026-08-29-beta-off-the-rails-analysis.md'` | The document carrying the operator-set top three. Pass `''` to skip. |
| `integrationRepos` | no | the twelve registry repos + `omnimarket` | Repos the Integrate phase scans for merges in the window. Parameterized so a repo joining or leaving the registry changes the **args**, not the script. |
| `integrateSince` | no | the day before `date` | Inclusive lower bound of the integration window — *"anything that was done the day before"*. Widen it after a missed morning so nothing falls through the gap. |
| `kbInternalPath` | no | `''` | Absolute path to a `docs_repo` clone. Empty means resolve it (see below). |
| `publish` | no | `true` | `false` writes the local artifacts and performs **no** kb-internal PR and **no** Linear mutation; the report still names what *would* have been corrected. |
| `force` | no | `false` | `true` bypasses the [idempotency pre-check](#idempotency--the-same-date-re-dispatch-guard) entirely — the pre-check agent is not even spawned — and re-derives every phase. The deliberate-re-run escape hatch, and the only way to overwrite a delivered, conformant artifact. It also rewrites the date-snapshot state file, which is what corrupts the next morning's drift baseline, so pass it when you mean it and not otherwise. |

**The plan-row sources are parameterized so the process outlives this sprint.** The defaults are the current beta documents; a later sprint changes the args, not the script. Hardcoding a replacement inside an agent brief is a contract violation.

### kb-internal path resolution

Resolved in this order and no other:

1. `args.kbInternalPath`, if given. If it is not a clone of `OmniNode-ai/docs_repo`, the run reports `BLOCKED` naming the path it checked — it does **not** substitute another path.
2. `$DOCS_REPO_PATH`, if set and valid.
3. Otherwise clone `OmniNode-ai/docs_repo` under `$registry_root/worktrees/OMN-17170/`.

If none yields a clone, `publish_state` is `BLOCKED` with the failing command named. Guessing a path, or falling back to a same-named directory that happens to exist, is forbidden — CLAUDE.md rule 8 (fail-fast, never a silent wrong default).

**As of OMN-17235 this is no longer a publish-only concern.** The clone is where the
artifacts are *written in the first place*, so an unresolvable path is a hard abort of
the writing phase, not a degraded run that still leaves a local copy behind — there is
no local copy any more. The bash-level `${DOCS_REPO_PATH:?...}` guard in
each brief is what makes step 2 fail loudly instead of defaulting.

### Source-doc resolution

Each source document is read from the kb-internal `beta/plans/` or `beta/tracking/` mirror when a file of that basename exists there, otherwise from `$registry_root/<path>`. **The run records which copy it read for each source** — the two copies can diverge, and that divergence is itself a finding, not something to silently pick a winner for. If neither exists, the source is `UNKNOWN` with both absolute paths named.

Six agents run at most: one cheap **idempotency pre-check** first, then **ground-state reporter** and **morning triage** in parallel, then **plan-reconcile**, **integration-plan**, and **session-goal** in series. The first split is deliberate — the reporter must observe the board *before* triage changes it. The last three are serial because each consumes the previous one's output. On a re-dispatch of an already-delivered date, only the first of those six runs.

---

## Idempotency — the same-date re-dispatch guard

**Ticket: OMN-16972.** Re-deriving an artifact this process already delivered is not merely wasteful — it is **destructive**.

### The friction, twice

| | What happened |
| -- | -- |
| **2026-08-29** | The workflow ran twice for one date — 07:15Z (`64ff931d1`) and ~15:15Z (`164d3fd09`). The 07:15Z run had already written `ground-state-date-snapshots.json` with `as_of: 2026-08-29`, so the second run's §5a drift comparison silently became an **intra-day ~12h comparison instead of a 24h one**. The report had to flag it rather than produce a wrong multiplier. |
| **2026-08-30** | Three dispatches inside ~40 minutes. The second and third each burned a **full opus phase** re-deriving live state before their agents worked out *by hand* that the day's artifact was already committed, and aborted — ledger rows `ground-state-report (second dispatch)` TERMINAL 15:36:00Z, `(third dispatch)` TERMINAL 15:47:00Z, `morning-triage-adjudication (third dispatch)` TERMINAL 15:52:00Z. |

Those aborts were **correct**, and *why* they were correct is the design input. Regenerating `docs/tracking/<date>-morning-ground-state.md` would have deleted the dated **Correction** section that *this document* cites by path as the OMN-17170 §5c regression evidence — a destructive edit to a live citation from the governing contract.

Since **OMN-17173** wired a launchd trigger at 04:43 local, a scheduled run followed by a hand dispatch is now the **ordinary** case, not the exception.

### The guard

The `Precheck` phase runs **before the money is spent**, not inside the expensive agent. One `sonnet`/`low` agent answers, per phase, whether that phase's own artifact for the date is already delivered and whether a peer lane holds a live claim on it. Each phase then either dispatches or short-circuits.

| Verdict | Condition | Phase result |
| -- | -- | -- |
| `already-delivered` | artifact **exists** + **committed** + **clean** (`git status --porcelain` empty) + **conformant** | `{ skipped: 'already-delivered', evidence: <commit sha> }` — no derivation spawned |
| `peer-owned` | an un-`TERMINAL`-ed `CLAIM` row for the phase's lane name in `ROLLING_WORK_LEDGER.md`, **less than 90 minutes** old | `{ skipped: 'peer-owned', evidence: <the CLAIM's stamp + lane> }` |
| `run` | anything else — **including every failed or indeterminate read** | the phase dispatches normally |

`already-delivered` **beats** `peer-owned`: a delivered, committed, conformant artifact is finished work, and a lingering claim behind it does not un-deliver it. A `CLAIM` older than 90 minutes with no `TERMINAL` is a **stale** claim, not a live peer — it blocks nothing and is reported in `residuals` instead.

### What each phase is checked against

| Phase | Artifact | Conformance |
| -- | -- | -- |
| GroundState | `beta/tracking/<date>-morning-ground-state.md` | ≤ 200 lines; all six sections present **and in order**, with 5a–5d and 6a–6c; section 4 links the committed, clean `<date>-delegation-accounting.md` companion with its bounded window and source table, or records accounting UNREADABLE with the failing command and stderr; **and** `beta/tracking/ground-state-date-snapshots.json` committed with `as_of == <date>` |
| Triage | a `TERMINAL` row for lane `morning-triage-adjudication` carrying `<date>` | the row reports the four counts (flipped / held / corrected / commented) — a `TERMINAL` with no counts is not a delivered pass |
| Reconcile | `beta/tracking/<date>-beta-rebaseline.md` | ≤ 250 lines; rows table with the ladder columns, counts, top three, mismatch list; every verdict token in the ladder vocabulary |
| Integrate | `beta/tracking/<date>-integration-plan.md` | ≤ 250 lines; window line, per-repo scan table, rows **grouped by destination** with a probe column, counts, named holds |
| DroppedWork † | `beta/tracking/<date>-dropped-work.md` | ≤ 200 lines; all four section headings verbatim, each with its count line, its probe and its positive control; no section reporting 0 without a control that returned rows |
| Goal † | `beta/GOAL.md` | ≤ 88 lines; exactly the six header keys **then the five dropped-work headline keys**; `state_as_of` is a full UTC observation timestamp (`YYYY-MM-DDTHH:MM:SSZ`). **In `publish` mode the published copy is checked too** — `beta/GOAL.md` in kb-internal must carry the same full UTC timestamp as the local goal in `state_as_of`, else the verdict is `run` |

† **Reported, never gating.** These two phases are in `UNCONDITIONAL_PHASES` and run whatever verdict the guard returns — see "Unconditional phases" below for why the artifact class, not the cost, decides this. Their conformance row is still checked and still reported, because a delivered-but-nonconformant verdict is the signal that a previous run wrote a malformed artifact.

The snapshot clause on GroundState is load-bearing: the snapshot is written **last** by a completed run, so a snapshot still reading an earlier `as_of` means the previous run did not finish and its report must not be treated as delivered. The published-copy clause on Goal is the same idea applied to the publish leg — short-circuiting on the local copy alone would silently drop the kb-internal publish, and `beta/GOAL.md` is the exact path the OMN-17168 SessionStart hook reads.

### The fail direction is toward doing the work

An **UNKNOWN** pre-check — a failed read, a dead agent, a phase the pre-check did not return a row for — falls through to a **full run**. It never skips. A false `already-delivered` would silently deliver nothing on a genuine fresh morning, which is strictly worse than a duplicate. The fall-through is not unguarded either: every phase brief still carries the standing fence that produced the two correct manual aborts above.

### A short-circuited upstream is a normal input, not a missing one

Downstream phases already take their upstream as a **path**, so nothing changes for them. When an upstream short-circuited as `already-delivered`, the downstream brief is told to **read the committed artifact from disk and treat it exactly as one written moments ago** — not to re-derive it, not to call it stale, not to downgrade a verdict because no agent in this run produced it. When an upstream is `peer-owned` the brief says the opposite honestly: the artifact may be absent or half-written, so read it only if it exists and is clean, otherwise report **BLOCKED** naming the peer claim and write nothing that would race the peer.

### The clock

The script holds no clock — its determinism rule forbids that. The 90-minute window is evaluated by the pre-check agent from a **single live `date -u` read**, returned as `clock_utc`, exactly like every other fact in this process. A ledger row stamped in the *future* relative to that reading is a peer appending right now (observed 2026-08-30) and is treated as age 0, i.e. live.

### Validation

`tests/test_morning_ground_state_node.py` executes the Definition-B handler with
recorded phase replies. Nine pre-deletion parity scenarios compare the original
outputs, phase routing, schemas and prompt digests; an additional unavailable-agent
check proves the precheck fails toward a full run. An already-delivered date
produces zero expensive agents while DroppedWork and Goal remain unconditional.

```bash
uv run pytest tests/test_morning_ground_state_node.py -q
```

The lab test dispatches a typed command and consumes its correlated completion
on the canonical in-memory bus. Kernel resolution and delegation RPC serialization
have separate focused checks. The existing format guards read the node's rendered
resources and typed phase models.

---

## Ledger reconciler — the §0a dangling-claim sweep (LedgerReconcile)

**Ticket: OMN-17466.** The `ROLLING_WORK_LEDGER.md` §0a protocol requires a CLAIM row before a lane mutates and a TERMINAL row when it finishes. A lane killed mid-flight (usage-limit outage, `kill -9`) dies **without** its TERMINAL row, and a dangling CLAIM is indistinguishable from a lane still running — so every later actor (this workflow's Precheck included) treats that scope as claimed indefinitely. Recovery used to be a manual review pass (precedent: commit `305744733`, six wave-2 TERMINAL rows appended by hand after direct gh verification). Per operator ruling, that recovery is now mechanical and automatic — a recurring manual sweep is not an acceptable process.

**The step runs FIRST, before Precheck.** It invokes `onex-ledger-reconcile --json`, the bus adapter for `node_ledger_reconcile_effect` in ops_tooling_pkg. The contract declares command and terminal topics; the node owns parsing, verification and safe appends. Tests live in `tests/ledger/test_reconcile.py` and `tests/ledger/test_reconcile_node.py` (OMN-20677).

What it does, mechanically:

- A CLAIM with no matching TERMINAL for the same lane, older than **6 hours** (`--stale-hours`), over **all history** (`--since-days 0` in the morning workflow; CLI default remains 7 days), is **DANGLING**.
- The claim's cited evidence handles (repo#PR refs, commit SHAs) are verified against **live** state — `gh pr view --json state,mergedAt,mergeCommit`, `git cat-file`/`git merge-base --is-ancestor` against the canonical clones — never against a lane self-report. Ticket binding excludes fence-check citations of peer lanes' PRs (a PR whose title cites only a different ticket, or that landed before the claim existed, is not this claim's evidence).
- **COMPLETED** (every bound handle provably merged/landed) → a TERMINAL row marked `RECONCILER-AUTO-CLOSE` is appended via `scripts/ledger_lock.py`, carrying the verifying merge SHAs. **ORPHANED** (bound evidence verifiably dead: PR open-and-abandoned or closed unmerged) → a `RECONCILER-NEEDS-ATTENTION` row; the claim stays open for adjudication. **UNKNOWN** (no extractable or resolvable evidence) → report only, nothing appended. A completion is never fabricated.
- Canonical **HOLDs** older than the same threshold release with an exact `re=<hold id>` only when every structured `pr=` target and `after=` dependency is verified merged, including its merge timestamp/SHA. Aliases and `repo=... | pr=<number>` are resolved. OPEN/CLOSED/failed lookups never release a hold. Operator-standing holds, proof/surface holds, unexpired or unreadable `until=` conditions, live holders and recently active holders stay in force. A merge does not prove runtime restoration.
- A caller that supplies its **current live roster** as `args.liveLanes` also enables `--silent-hours 72`. An explicitly empty array means the caller verified no lanes are running; omitting the array disables silent retirement. Invalid lane names skip the reconcile step (logged) rather than disappear from the roster. The roster travels as `--live-lane` arguments with `--live-roster`, so concurrent passes share no roster file.
- A handle-free CLAIM with at least **72 hours of lane silence**, absent from that roster, may close with **`outcome=abandoned`**. This releases ownership and asserts no completion. Recent own rows, pending HOLDs and watch/monitor/receipt steps prevent it; claims carrying PR/SHA/branch handles whose evidence cannot be verified remain UNKNOWN. The result counts landed `auto_closed`, `abandoned` and HOLD `released` separately.
- The existing **60-row append cap** counts all planned TERMINAL, STATUS and RELEASE rows together and refuses the whole pass with exit 4 if exceeded. Raising it is an operator decision.
- Re-runs are idempotent per (lane, claim-timestamp); appends respect the ledger mutex (bounded retries on exit 75); the appended rows are NOT committed: they stay in the working-tree ledger and reach origin through the ledger-publish PR path. A reconciler commit on the shared tree's local main is unpushed by construction and blocks the rule-19 fast-forward sync (OMN-19212).
- In dry mode (`args.publish false`) the reconciler runs report-only and writes nothing.
- **Fail direction:** a missing or broken reconciler never kills the morning run — the failure is logged and every phase falls through to the normal flow.

## Decisions register — every ruling and consent, with a derived status (DecisionsRegister)

**Ticket: OMN-18575.** Operator ruling, 2026-09-17, firm, rendered as an attributed professional paraphrase: *there is nowhere that collects the rulings we have made and keeps them visible, so they keep being forgotten, and that keeps happening repeatedly.*

The instance that produced the ruling: a phased pre-push retirement (OMN-18162, "do one at a time") completed phase 0 across three repositories on 2026-09-11 and then stopped, because the phase-0 report was never written and nobody dispatched phase 1. Nothing broke. The decision simply stopped being visible, and the operator had to ask why six days later. Two more of the same shape were live the same morning.

**The store is the ledger; this is a projection of it.** Every ruling and consent is already a durable `RULING` or `OPERATOR-CONSENT` row in `docs/tracking/ROLLING_WORK_LEDGER.md` and its archive rolls. Nothing was missing from the record — what was missing was a derived view saying, per decision, whether anything happened afterwards. This step never becomes a second place a decision can be recorded, and a disagreement between the register and the ledger is always resolved in the ledger's favour.

The deciding logic is committed at `src/ops_tooling_pkg/handlers/handler_decisions_register.py` and installed as the `onex-decisions-register` command (moved out of registry_root's `docs/workflows/_shared/`). Its real bytes are run by `tests/decisions/test_decisions_register.py`. The phase brief only drives the tool and commits what it wrote.

### The status ladder

Decided in this order, first match wins; every verdict carries the evidence that produced it.

| Status | Derived from |
| -- | -- |
| `SUPERSEDED` | a later decision or correction resolves a citation to this row |
| `HELD` | the decision is itself a hold and no later row releases it |
| `EXECUTED` | a TERMINAL row cites the decision, or the decision's own lane wrote one after it |
| `IN PROGRESS` | claimed or progressing, no TERMINAL row |
| `STALLED` | the same, but nothing has moved for longer than the window |
| `PENDING` | nothing cites it and its lane never acted |
| `UNVERIFIED` | the evidence does not decide — **with the reason, never a guess** |

`STALLED` exists because it is the status the ruling was actually about. Folded into `IN PROGRESS`, the OMN-18162 shape reads as live work and the register reports it as healthy — reproducing, inside the fix, the failure being complained about.

### DECISION-REQUESTED — the register's own blind spot, closed

**Second pass, OMN-18575.** The register derived only from `RULING` and `OPERATOR-CONSENT` rows — decisions that were **made**. A decision that was **asked** and never answered produced no row of either class, so it was invisible here, which is to say invisible everywhere.

Measured: a plan review finished 2026-09-16T22:58Z and put five decisions to the operator. None was answered, none was recorded on any surface the register reads, and the whole thing was dropped until somebody asked what had happened to it fourteen hours later. The register built to stop decisions being forgotten could not see the five most recently forgotten ones.

A question is now a first-class row, appended through `scripts/ledger_lock.py`:

```
<ts> | DECISION-REQUESTED | lane=<lane> | asked_of=operator|<owner>|<owner> | question="<one sentence>" | recommendation="<one sentence>" | source=<doc path> | This row is a pending decision until a RULING/OPERATOR-CONSENT row cites its timestamp
```

It is deliberately **not** a `RULING` with an empty decision. A question is not a ruling; its owner is the person it was asked **of** rather than a lane; and it goes stale far faster.

| | question | work |
| -- | -- | -- |
| status | `ASKED` → `ANSWERED` | `PENDING` / `IN PROGRESS` / `STALLED` / … |
| owner | the person in `asked_of` | the executing lane |
| resolved by | a `RULING` or `OPERATOR-CONSENT` row **citing this row's timestamp** | a `TERMINAL` row |
| alarm window | **3 days** | 7 days |
| sort | **ahead of everything** | forgetting set, then the rest |

Three days rather than seven because a question waiting on a person is a different kind of overdue from work waiting on a lane — seven would have let the measured case sit almost a week before anything said so, longer than it actually took a human to notice. A question sorts ahead of every other row because the work has an owner who could still pick it up, while the question is blocked on one person who does not know it is waiting.

**Resolution is by citation and nothing else.** Unrelated later activity by the asking lane does not answer a question, and a `RULING` that happens to be about the same subject but cites nothing does not either.

### DECISION-LINK — declared relations between decisions

Three relations the ledger's append-only shape cannot express in the rows themselves, because each was discovered after both rows already existed.

```
<ts> | DECISION-LINK | lane=<lane> | relation=answers|duplicate-of | subject=<stamp or file:line> | object=<stamp or file:line> | <why>
```

| relation | effect |
| -- | -- |
| `answers` | the `ASKED` row at `subject` resolves to `ANSWERED`, evidenced by the ruling at `object` |
| `duplicate-of` | the decision at `subject` is folded into `object`; one entry, the re-ruling carried as evidence |

A fourth relation is a field rather than a row: **`reopens=<stamp or file:line>`** on any later row declares a decision unfinished and outranks an earlier `TERMINAL`. Without it the first terminal row wins forever, so a decision closed on one *half* of itself reads `EXECUTED` permanently — measured on the public API cutover, whose network half terminated while its serving half was still blocked.

**Both spellings, and why.** A timestamp is the stable key and survives a ledger roll, but rows appended together share one — the five seeded questions all carry `13:49:37Z` and one lane, so no stamp names any single one. A `file:line` citation does, at the cost of not surviving a roll. An unresolvable or **ambiguous** reference resolves to nothing and the link is dropped, which leaves the decision visible rather than silently retired.

**A link is honoured only when both rows it names exist.** A typo would otherwise retire a decision, which is the same harm as the supersession bug: a row vanishing because of something written about it elsewhere.

### Re-ruling detection — flagged, never merged

Two decisions on one ticket inside 24 hours whose wording overlaps by at least 0.30 are flagged as a possible re-ruling. **Both still render.** Merging takes a `DECISION-LINK` row.

The threshold was measured against the live ledger, not chosen: the ticket-and-window rule alone flagged **57 of 231** decisions, a quarter of the register, and noise gets ignored. Adding the wording test gives **4**, every one a true positive on inspection. At 0.45 it gives none, because the real pairs are paraphrases rather than restatements.

### The forgetting alarm

`--check` exits 1 when a decision is `PENDING`, `HELD` or `STALLED` past the **7-day** window with no declared next action. The phase returns `alarm` and the orchestrator surfaces it.

**Fail direction: reported, not fatal.** A decision nobody has actioned for eight days is a real finding, but it is not a reason to abandon the ground-state report, the triage and the session goal — that converts one forgotten decision into a whole forgotten morning, the same failure one size larger.

**A next action is read, never invented.** It comes from a later row citing the decision that carries a `next=`, `blocked_on=`, `needs=`, `awaiting=` or `unblock=` field. There is deliberately **no sidecar file** of hand-written next actions: a second store is a second thing to forget. The remedy for an alarm is a ledger row — never an edit to the generated register, which the next run overwrites.

### The hourly tick line

The generator prints what the tick needs on stdout, so the tick shells it and reads the line rather than re-deriving anything:

```bash
uv run --project "$registry_root/../ops_tooling_pkg" onex-decisions-register \
  --ledger $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md \
  --archive-dir $registry_root/docs/tracking/archive --stale-days 7 --check
```

The proposed one-line addition to the tick's checkpoint contract — the tick text itself is the operator's and is not edited here:

```
- <ts> decisions: <n> pending, <m> held, <s> stalled, <k> asked, <a> past window with no next action; oldest asked <date>
```

Exit 1 is the alarm. The tick **reports** it and does not fail on it, the same fail direction as the morning phase.

### Ordering, constrained from both sides

**The worktree goes under `worktrees/`, never beside the clone.** The kb-commit convention originally derived its worktree path from the canonical clone's own path, producing a sibling named `<clone>-morning-<date>`. The canonical-clone guard matches a sibling of that shape **as a canonical clone** and refuses the `git add` the same brief goes on to instruct — and then refuses the cleanup that would undo it, so the lane wedges rather than merely failing (measured 2026-09-17, OMN-18575). Worktrees now sit at `$registry_root/worktrees/<TICKET>/docs_repo` like every other lane's. The **clone** is still resolved fail-fast from `$DOCS_REPO_PATH` with no default; a worktree under `worktrees/` is not a fallback for it and never could be, since it does not exist until the clone has already been resolved.

After `LedgerReconcile`, because the reconciler has just appended TERMINAL rows for dangling claims whose evidence provably landed, and those rows are exactly what `EXECUTED` is derived from. After the `Precheck` agent, because the idempotency guard must be the first `agent()` dispatch in this lane (OMN-16972/OMN-17225). So it sits between `Precheck` and `GroundState` — after both constraints, ahead of every expensive phase.

It is **not** gated on the Precheck verdict. Every other phase writes a dated artifact that must not be re-derived once delivered; this one rebuilds a standing document in place from the whole ledger, which has moved since the last run. Re-deriving it is the point.

### What the register cannot tell you

1. **A line citation does not survive a ledger roll.** The convention is a line number into the ledger; a roll moves rows into an archive split at different numbers. The resolver matches the stable timestamp first and falls back to a line only when it lands inside the file it names. An unresolvable citation is reported, never silently dropped.
2. **A shared lane name is not evidence.** 42 of the 108 live decision rows carry `lane=orchestrator`, which writes rows continuously; inferring `EXECUTED` from "its lane has a later TERMINAL" would manufacture dozens of false verdicts. Those decisions resolve by explicit citation only, which is why `UNVERIFIED` is a large bucket.
3. **`PENDING` means there is no ledger evidence, not that the work is undone.** Measured on the day the register was built: two consents from 2026-09-04 both render `PENDING`, and a live read shows both were acted on. Neither executing lane appended a citing terminal row. The register is accurate about the ledger and wrong about the world, and that gap is the finding.
4. **It enforces visibility, not compliance.** `EXECUTED` means a lane said it finished.

## Date classes (COMMITTED vs TARGET)

Direction (accepted): Linear dates split into two classes.

- **TARGET** (default) — an internal estimate. Moves freely; a slip is normal planning noise, reported but not escalated.
- **COMMITTED** — an external dependency (a customer date, a partner date, a named commitment). Moving it requires a conversation.

**Mechanism, verified live against the Linear MCP tools (2026-08-28), not invented:** issues already carry a native `dueDate` field (`list_issues`/`get_issue`, `fields: ["dueDate"]`) — one date axis, used for both classes. Linear exposes no second date field or custom-field split here, so the class is carried by a **label**, `date:committed` (workspace label; verified creatable via `create_issue_label`; created once by hand 2026-08-28, id `00000000-0000-4000-8000-000000000000`, color `#eb5757`). A ticket with a `dueDate` and the label is COMMITTED; a ticket with a `dueDate` and no label is TARGET; a ticket with no `dueDate` is unscheduled — not a class at all. This is the smallest true mechanism: no invented custom field, no second date property that Linear doesn't have.

Label creation is **idempotent by convention, not by re-invocation**: `list_issue_labels(name: "date:committed")` first; `create_issue_label` only if that result is empty. It will not be empty again — the label already exists — so every future run is check-only.

**Retro-classification is explicitly NOT done by this workflow.** None of the ~80 existing sprint tickets carry the label yet. Per the estimate given only 2-3 are truly committed, and *which* ones is the operator's call, not a sweep's guess made durable. The ground-state run instead lists **candidates** (below) for the operator to confirm.

### Committed-class candidate detection

Each ground-state run scans sprint-scope tickets that do NOT already carry `date:committed` for external-dependency signals: a customer or partner name, or an explicit phrase naming an outside deadline ("customer needs this by", "partner date", a named company) in the title or description. Candidates are listed in the Date drift section (ticket id + the matched phrase) for the operator to confirm or dismiss. **The scan never applies the label itself.**

### Date-snapshot state file

`beta/tracking/ground-state-date-snapshots.json` (in the kb-internal clone) holds the previous run's per-ticket `dueDate` snapshot so drift can be computed without re-deriving history. Mechanical state in a file, not memory — and no `Date.now()` in the script; the file's `as_of` is the run's own `args.date`.

```json
{
  "as_of": "2026-08-28",
  "tickets": {
    "OMN-16790": { "dueDate": null, "class": "target" },
    "OMN-16803": { "dueDate": "2026-09-05", "class": "committed" }
  }
}
```

Read BEFORE the run's live Linear reads touch it (that's the "previous" snapshot the drift comparison needs). Written LAST, after drift is computed — overwritten wholesale with today's live scope (sprint project + last-48h-updated tickets), never merged or appended. `class` is `"committed"` when the ticket carries `date:committed` at read time, else `"target"`. Bootstrapped empty (`{"as_of": null, "tickets": {}}`) on 2026-08-28; the first real run is a BOOTSTRAP RUN (see below).

---

## The ground-state report: six sections, in this order

### 1. Feature table

Every Linear ticket in the **current beta sprint project** that is `In Progress` or `In Review`, plus any ticket carrying a merged-but-unreleased or open PR.

The sprint is resolved **live** — it is the dated Linear **PROJECT** covering `args.date`, not a Cycle (`reference_linear_sprint_target`). Paginate; project filters truncate (`reference_linear_project_filter_truncation`).

Columns, exactly:

| ticket | assignee | one-line state | evidence state | blocker | next action + owner |
| -- | -- | -- | -- | -- | -- |

- **evidence state** — merged PRs verified via the **pulls API**, never a PR body claim or an agent self-report.
- **blocker** — a named ticket, decision, or person, or the literal `NONE`. "Waiting on CI" is not a blocker; the PR number and the red check are.
- **next action + owner** — every row has one. A row with no owner is a defect in the row, not an acceptable state.

### 2. Open-PR census

OMN-19589: `HandlerMorningGroundState` harvests one immutable PR watcher snapshot
for the census and terminal `pr_inventory` result. It resolves `ONEX_PR_WATCHER_STATE`,
otherwise the existing watcher file under `registry_root`. It validates schema, source
fields, heads, an eight-minute complete-tick bound and a ninety-minute full-resync
bound. It accepts at most 16 MiB and renders at most 500 rows with an explicit omitted
count. STALE or UNREADABLE snapshots harvest no rows and report their reason;
unreadable and omitted records cannot be reported as clean or zero candidates.

Per PR: same-head, dated CI only; armed and record-level queued observations;
pending check id, start and age fields. Missing evidence is unknown. A snapshot
does not establish historical never-enqueued or zombie verdicts. The census uses
this single feed, without per-PR GitHub polling or retired in-process result paths.
Never rerun a queued run to get a verdict.

### 3. Decision stack

**Enumerated live, every run.** This section must never be a hardcoded list, and yesterday's items are never carried forward unverified — that is precisely how a process degrades back into an ad hoc report. Derive it from:

1. Sprint tickets whose latest comment or description poses an unanswered operator question or names an unmet approval/grant.
2. Un-TERMINAL-ed `CLAIM` rows and explicitly recorded holds in `docs/tracking/ROLLING_WORK_LEDGER.md`.

One line each: **what is being decided | what it blocks | age** (age cited from the first live timestamp available).

### 4. Runtime / lane health

One line each for: dev lane (last refresh receipt), stability lane, prod (last dispatch outcome), CI runner fleet (queue depth). Each line cites the command behind it. Lane identity is per-lane — never treat `lab-host-a` as a single `8085` service (see the lane map in `CLAUDE.md`).

Delegation accounting is part of section 4 (OMN-17427, top-20 item 9). Call the built reader once, after resolving `ONEX_STATE_DIR` and `ONEX_LEDGER_PATH` from the session environment. Missing variables are UNREADABLE. Capture `ACCOUNTING_UNTIL` once with `date -u +%Y-%m-%dT%H:%M:%SZ`; the lower bound is the workflow's `integrateSince` at UTC midnight, inclusive, and the upper bound is exclusive.

```bash
uv run --project "$registry_root/../ops_tooling_pkg" onex-delegation-accounting \
  --ledger "$ONEX_LEDGER_PATH" --include-archive \
  --runs-root "$ONEX_STATE_DIR/runs" \
  --since "<integrateSince>T00:00:00Z" --until "$ACCOUNTING_UNTIL" --format md
```

Add `--harness-root` for each existing harness receipt root at `$ONEX_STATE_DIR/harness-delegate` and the house tenant's configured harness receipt store. State every supplied and unavailable source. Supply `--lab-tsv` only when an existing export supplies it, naming that source. Save stdout verbatim as `beta/tracking/<date>-delegation-accounting.md` in the same knowledge-base worktree and commit as the report; scrub the companion with the report's shared-document scrub before committing. Section 4 links it, repeats the exact window and Run sources table, and displays at most 12 Lane delegation rows with an omitted-row count. Keep `terminals_silent` and `cited_runs_unverified` visible. `n/a` is unavailable, never zero; TERMINAL citations, including Codex and Jev cells, are claims rather than receipt-backed proof. Never derive these counts in the report lane. A non-zero exit or missing required source is **UNREADABLE**, with the failing command and stderr, while the rest of the morning report continues; never replace a failed read with zero.

### 5. Date drift

Direction: "the system should report drift, not rely on someone volunteering bad news." Four parts, in this order, plus the candidate list from above:

**a. Due-date moves since the previous run.** Read `beta/tracking/ground-state-date-snapshots.json` (the prior snapshot) BEFORE any live read in this run touches it. For every ticket in today's scope (sprint project + last-48h-updated — same footprint as the feature table), compare its live `dueDate` to the snapshot value. One row per ticket that moved, newly appeared with a `dueDate`, or lost its `dueDate`: ticket | class | old dueDate | new dueDate | delta (days). A ticket absent from the prior snapshot is `(first appearance, no drift computed)` — never a fabricated 0-day move. On the very first run ever (empty/missing snapshot file), report `BOOTSTRAP RUN — no prior snapshot; this run seeds it` and skip the comparison — do not report "0 tickets drifted" as if a comparison happened.

**b. Committed-class status.** Every ticket carrying `date:committed`, **workspace-wide** (`list_issues(label: "date:committed")`) — a committed date does not stop mattering when a ticket rolls out of the active sprint project. Row: ticket | dueDate | days-until/overdue | state. Sort soonest-due / most-overdue first. Zero committed tickets is an expected, honestly-reported state (`0 tickets carry date:committed — see candidates below`), not a section to omit.

**c. Sprint-close carry.** "Date holds, scope moves": the sprint boundary does not move, so what didn't make it must be visible. On a mid-sprint run, report `mid-sprint — no carry to compute yet, current sprint runs <startDate>→<targetDate>`. At or after a sprint close, diff the previous sprint PROJECT's ticket set (resolved live, same pagination rule as the feature table — `reference_linear_project_filter_truncation`) against the current sprint project: list every ticket from the previous project that is NOT `Done`/`Canceled`. Row: ticket | prior state | landed in current sprint project? (yes/no).

**Membership check is mandatory and live, on the successor project specifically (OMN-17170).** "Landed in current sprint project?" is answered by a paginated read — `list_issues(project: <successor project id>)`, continued to `hasNextPage:false` — that performs a live membership check of the successor project itself, then matches each previous-project ticket ID against that membership set. Two failure modes are explicitly forbidden:
- Inferring "no ticket has landed yet" from the successor project's mere existence or its status (e.g. `Planned`) — a project can hold hundreds of tickets while its own status is still `Planned`.
- Using `get_project`'s `resourceCount` field as a ticket-count proxy — `resourceCount` counts attached resources (documents, links, attachments), **not issues**. Live-verified 2026-08-30: a successor project holding 369 issues returned `resourceCount:0`.

Regression evidence: the 2026-08-30 morning-ground-state report asserted the successor project `Sprint 2026-08-31 → 2026-09-13 (Beta)` had zero tickets moved into it, based on the project existing and being `Planned`. A live paginated read the same day found 369 tickets already in it (182 Backlog / 115 Todo / 45 In Progress / 16 Done / 9 Duplicate / 1 Canceled / 1 In Review). See the dated Correction section appended to `docs/tracking/2026-08-30-morning-ground-state.md` and `docs/workflows/morning-ground-state/check_5c_membership_check.py` (a lightweight contract-text guard, since this repo carries no functional code to unit-test against).

**d. Velocity multiplier, per closed ticket.** For every ticket with a live `completedAt` in today's scope, compute `multiplier = (completedAt − startedAt) / (dueDate − startedAt)` **only when both `startedAt` and `dueDate` are present** (`fields: ["startedAt","dueDate","completedAt"]`). `<1` closed faster than planned, `>1` slower. When `dueDate` or `startedAt` is missing — the common case as of 2026-08-28, verified live: `dueDate` is null across the current sprint's sampled tickets — report `UNKNOWN — missing <field>`, never a fabricated ratio or an assumed default. Mostly-UNKNOWN is the honest state while `dueDate` adoption is near zero; it is not a defect in this section.

### 6. Closure path health

Added 2026-09-03 (ledger `RULING` row, lane `ruling-closure-path-priority`). Operator ruling, verbatim intent: *"In Progress means a worktree and a commit exist for it. Comments are not activity. Done requires durable evidence and the path that produces it is the top priority."*

The other five sections measure the **work**. This one measures the **path that turns finished work into `Done`** — verifier, closer, OCC evidence, staging proof. It is last in the report and first in priority: while it is RED, every feature lane is filling a bucket with no bottom, because work that lands cannot be closed. **A RED row here outranks every row in sections 1–5.**

Four probes, in this order. Each renders as one row carrying an explicit `RED`/`GREEN` and the command behind it. A probe that could not be read is `UNKNOWN` with the failing command — **never `GREEN`**.

| probe | GREEN when | RED when |
| -- | -- | -- |
| **6a verifier runnable** | one `dod_verify` run on the fixed pin finishes under the ceiling **and** emits a parseable verdict | over ceiling, no receipt arm, or a synthetic host-contention check |
| **6b closer effective** | the newest sweep run flipped at least one ticket, or reached no candidates at all | `tickets_flipped == 0` while `tickets_gap_posted + tickets_errored > 0` |
| **6c staging green** | both staging workflows' newest completed runs are `success` **and** the terminal business-proof gate actually evaluated | either workflow red, or the business-proof gate `skipped` |
| **6d release staleness** | no *enforced* publishing repo carries unreleased packaged-source commits older than 24h, no repo was unreadable, **and** the sweep's own positive control produced rows | any enforced repo stale, any repo unreadable, or a zero that its control could not corroborate |

#### 6a — verifier runnable

Run the verifier **once**, on a **fixed pin** (`args.closureProbeTicket`, default `OMN-16984`):

```
uv run --project "$registry_root/../ops_tooling_pkg" python -m ops_tooling_pkg.handlers.handler_closeout_scope verify <pin> --execution-audience hosted
```

The pin is fixed on purpose. This probe measures the **verifier**, so the subject must not vary run to run — otherwise a slow morning is indistinguishable from a hard ticket. `OMN-16984` qualifies on three counts, all live-checked 2026-09-03: it is `Done` (`completedAt 2026-09-01T20:16:15.039Z`), it is in the beta sprint project, and it carries `contracts/OMN-16984.yaml` at `onex_change_control` `origin/dev`. It is also the **only** ticket in that day's 36-run measurement whose behaviour check ever reached `VERIFIED` (`OK (19850ms): 16 passed in 1.55s`). If *that* ticket cannot produce a verdict, the verifier is down — not the ticket.

Quote the **wall seconds** and the **terminal status**, both verbatim. `GREEN` requires **both**: wall `< args.closureProbeCeilingSeconds` (default `600`), **and** the key `result.terminal_payload.total_checks` present and `> 0`.

Three RED renderings, never collapsed into one — they have different owners:

- **over ceiling** → `RED — verifier over ceiling (<wall>s of <ceiling>s)`. Measured 2026-09-03 over 36 runs: min `444s` / median `655s` / max `1346s`. The median already exceeds the 600s ceiling, so this row is *expected* to be RED today. The ceiling is the requirement, not a description of current behaviour.
- **no receipt arm** → exit `0` with no `result.terminal_payload.total_checks` key → `RED — receipt arm missing (OMN-16961)`. Name the ticket. This is the defect that has held the closer at zero flips since it shipped; the fix is built and unpushed behind `OMN-17793`.
- **host contention** → a single synthetic `occ_worktree_unavailable` check → `RED — host contention, NOT a ticket verdict (OMN-17796)`. Never render this as a verdict *about the pin*. It is the verifier failing to materialise an OCC worktree under load (a worktree add over a 300s ceiling, against ~270 registered `onex_change_control` worktrees), and rendering it as a ticket failure is exactly how a false *"not all ACs are receipt-proven"* reaches Linear.

Before running, re-confirm the pin is still `Done` and the product-contract resolver finds its contract on a product repository's default branch. If either is false, re-pin **and say the pin moved** — a silent substitution destroys the run-over-run comparison this probe exists for.

#### 6b — closer effective

```
gh run list --repo OmniNode-ai/omnibase_infra --workflow evidence-autoclose-sweep.yml \
  --limit 5 --json databaseId,conclusion,createdAt,status
gh run view <newest completed id> --repo OmniNode-ai/omnibase_infra --log
```

**The run conclusion is not the probe.** That workflow returns `success` on every zero-flip day, which is precisely how a closer that has never flipped a ticket went unnoticed. The probe reads the sweep step's own result JSON — the `node_evidence_autoclose_sweep_effect` line in the log — and reports, from that JSON: mode (`APPLY` / `DRY-RUN`, taken from the job name, which renders from the same guard that gates the flag), `companions_scanned`, `bindings_extracted`, `tickets_flipped`, `tickets_gap_posted`, `tickets_skipped`, `tickets_errored`.

**RED when `tickets_flipped == 0` and `tickets_gap_posted + tickets_errored > 0`** — the sweep reached verdicts and flipped nothing. Render it as:

```
RED — 0 flipped of <bindings_extracted> bound, <gap_posted> gapped, <errored> errored
```

**never as the bare number `0`.** A zero with candidates is an alarm; a zero with no candidates is a quiet night. The two must not print the same — that is the whole point of this row.

Two further obligations:

- Quote verbatim any `tickets_errored` reason containing *produced JSON with no `result.terminal_payload.total_checks`* and label it `OMN-16961 observed in production`. That string is the 6a defect surfacing in the live closer.
- State the mode honestly. **This is no longer true as of OMN-17658: a scheduled tick is NOT `DRY-RUN` by construction and CAN flip.** Arming authority for a scheduled run moved into the node contract's `scheduled_apply` — the workflow job for a `schedule` trigger is named `Evidence Autoclose Sweep (SCHEDULE - contract decides)` and passes no arming value at all; the contract alone decides, and the sweep receipt's `mode` field is the only way to tell what it decided: `apply_scheduled`, `dry_run`, `disarmed`, or `halted`. Live proof this is not theoretical: run `35190114002` (2026-09-17, trigger `schedule`) resolved to `apply_scheduled` and flipped `OMN-18408`. A `0` on a scheduled tick therefore proves nothing about mode by itself — read the receipt's `mode` field before drawing any conclusion, and report it verbatim alongside the flip count.

The launchd **dod-closeout-sweep** also gets its own row in 6b (OMN-20655). Run:

```bash
PYTHONPATH="$registry_root/../ops_tooling_pkg/src" python3 -m \
  ops_tooling_pkg.handlers.handler_closeout_completion \
  --ledger "$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md" --ground-state
```

Copy the output row verbatim and cite the command. It reads the same completed receipts
as the sweep completion step, across archive rolls and the live ledger, counting each run
key once. Three or more consecutive zero-flip runs render **RED**, with the streak length
and latest top deferral reason. A positive flip resets it. Legacy receipts without a reason
render `unknown`; no receipts or a failed read is **UNKNOWN**, never GREEN. This row is
required even when the evidence-autoclose closer above is green.

#### 6c — staging green

Newest **completed** run of each, with conclusion, `createdAt`, and the **name** of the first failing step (`gh api repos/<org>/<repo>/actions/runs/<id>/jobs`):

- `deliver-dev-candidate-to-staging.yml` — `OmniNode-ai/omnibase_infra`
- `deploy-onex-staging.yml` — `OmniNode-ai/infra_repo`

Then answer one further question explicitly: **did the terminal business-proof gate evaluate?**

Match that step **by name** — the step whose name contains `BUSINESS PROOF gate` (`OMN-15256`) — and **never by step number**. Numbers shift every time a step is inserted above them, and a number-matched probe silently starts reporting on a different step. (Live example, run `33777439327`: the gate is step **48**; step **47** is the *advisory* staleness check. A probe pinned to `47` would report on the wrong gate and would keep doing so without ever erroring.)

A conclusion of `skipped` means the gate **never evaluated**, and that is `RED` even when every step before it is green — a deploy that never reaches its own terminal proof has proven nothing.

Also report the consecutive-red streak per workflow, walking the run list back to the first non-failure: `RED for <n> runs since <createdAt>`.

---

#### 6d — release staleness

Added 2026-09-07 (`OMN-18010` deliverable 3). The other three probes measure whether finished work can be *closed*; this one measures whether it was ever *shipped*. `omnimarket#2304` merged 2026-09-05 and sat unreleased with its release ticket in Backlog, `#2334` did the same, and `omniintelligence` and `omniclaude` have each carried roughly three months of unreleased packaged source. A merge that never reaches an index is not delivery, and until this row existed nothing in the morning would have said so.

The former checker belonged to the retired governance clone. No replacement reader has been verified, so this probe is currently **UNKNOWN** with that reason. It remains read-only and never cuts a tag.

If a replacement reader supplies a current JSON report, retain the following reporting requirements. Report as one row: `stale`, `stale_unenforced`, `errors`, and `positive_control.passed` with its `detail`. Then list **every** finding whose verdict is not `FRESH`, oldest first, as `repo · tag · age · packaged-commit count`.

`GREEN` only when **all three** hold: `stale == 0`, `errors == 0`, and `positive_control.passed` is `true`.

A zero whose control failed or never ran is **`RED`, not `GREEN`**. A sweep whose path filter silently matches nothing returns zero rows and reads exactly like a clean bill of health (`reference_empty_result_is_not_evidence_of_absence`); the control is a re-run against a known-old base ref that must produce rows before the zero means anything.

`stale_unenforced > 0` renders as `GREEN (enforced) / <n> repos carrying release debt` — **never** as a bare `GREEN`. Those repos are the deferred half of the gate's shrink-only enforcement roster, and they are exactly the merged-but-unreleased work this section exists to surface; collapsing them into the enforced verdict recreates the blindness the ticket was filed for.

An unavailable measurement is `UNKNOWN`, never `GREEN`.

---


## Hard rules

| Rule | Why |
| -- | -- |
| **Under 200 lines.** Tables over prose. | A report nobody reads at 07:00 has zero value. Length is the failure mode. |
| **Live reads only, never memory.** Every fact from a Linear MCP / `gh` / `git` read performed in *this* run. | The report's only value is that it is true *this morning*. A remembered fact is a stale fact wearing a timestamp. |
| **Failed read ⇒ `UNKNOWN` + the failing command.** Never infer, never fill a gap from a prior report. | `reference_empty_result_is_not_evidence_of_absence`. A confident wrong row is worse than a blank one. |
| **The reporter mutates no ticket state.** | Observation and mutation are separate lanes; triage owns all board changes. |
| **The date-snapshot file is read before, written after.** Never fabricate a drift comparison the file couldn't support. | The snapshot IS the previous-run fact; reading it late or skipping the write silently breaks tomorrow's drift section. |
| **Never auto-apply `date:committed`.** The candidate scan lists, it does not label. | Committed-vs-target is an operator call — see [Date classes](#date-classes-committed-vs-target). |
| **`DEPLOYED` is never inferred from `LANDED`; `PROBED` is never inferred from `DEPLOYED`.** | Root cause RC-E — "Done stops at merged". Inferring one rung up is how the whole reconciliation goes false at once. |
| **`GOAL.md` holds only not-yet-`PROBED` beta-path rows.** Finished work never appears in it. | The remainder *is* the artifact (RC-H). A goal file padded with completed rows is a summary, and a summary is where a remainder disappears. |
| **A delivered, committed, conformant artifact for the date is never re-derived without `args.force`.** | Re-deriving is destructive, not just wasteful: it deletes cited evidence and rewrites the drift baseline. OMN-16972. |
| **An `UNKNOWN` pre-check runs the phase; it never skips it.** | Silently delivering nothing on a fresh morning is worse than a duplicate. Fail toward the work. |
| **A `CLAIM` older than 90 minutes with no `TERMINAL` blocks nothing.** | A stale claim that gates a morning is a fence outliving its reason — report it in `residuals`, do not obey it. |
| **`LANDED` never counts as integrated.** A row is integrated when its probe passes against the *running* system. | Merged code that reaches no lane, no image and no consumer is finished work that helps nobody. On 2026-08-30 the ladder read **16 of 45 rows `LANDED` against 4 `DEPLOYED`** — the gap, not the merge rate, was the constraint. |
| **An integration row without a probe is invalid.** No probe ⇒ the row goes to residuals as *"no probe determinable: &lt;what could not be resolved&gt;"*. | A plan you cannot falsify is a wish. This is the same rule the verdict ladder enforces, applied to the action rather than the state. |
| **A hold is named, never silently skipped.** A held row appears in full, with its hold and the action that runs once it lifts. | Dropping a blocked row is how a blocker becomes invisible and a fence outlives its reason. |
| **A repo with merges but zero integration rows states `nothing to integrate: <why>`.** | An empty cell is indistinguishable from a repo nobody scanned. The reason is the evidence that the scan happened. |
| **Linear is reconciled FROM the diff, never read as truth. Evidence-less `Done` is flagged, never reopened.** | The board is a report of the work, not the work. Reopening on an unrun probe overwrites operator decisions with a guess. |
| **A green workflow conclusion is never evidence that the closer works.** Read the sweep's own result JSON. | `evidence-autoclose-sweep.yml` returned `success` on every run while flipping zero tickets since it shipped. The conclusion measures the job, not the closure. |
| **A zero flip count with candidates is `RED`, never a number.** | `0 flipped / 0 candidates` is a quiet night; `0 flipped / 5 gapped` is a broken closer. Printing both as `0` is how the second one hid. |
| **The business-proof gate is matched by step NAME, never by step number.** | Step numbers shift when a step is inserted above them. A number-matched probe reports on the wrong step and never errors while doing it. |
| **A RED closure-path probe outranks every other row in the report.** | Operator ruling 2026-09-03: *"Done requires durable evidence and the path that produces it is the top priority."* While the path is broken, landed work cannot be closed at all. |

---

## Triage rules: flip / hold / correct

The evidence-autoclose sweep is deliberately unarmed, so triage is a manual **receipts-based adjudication** pass. Scope: the current sprint project plus every ticket updated in the last 48h.

**The fence list comes from `uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-fences-node docs/tracking/ROLLING_WORK_LEDGER.md` (add `--open-prs` to include tickets with a live PR) and is never hand-derived** — a ticket in its `fenced_tickets` is live-claimed scope belonging to another lane: comment if you must, never flip it. Hand-derivation is what let OMN-15954's dangling CLAIM (`ROLLING_WORK_LEDGER.md:600`, lane `omn17349-staging-delivery`, no TERMINAL) escape the 2026-09-03 fan-out fence list until an adjudicator caught it live (OMN-17757).

### Flip to Done — only when all hold

- Every PR on the ticket is **merged**, verified via the pulls API.
- The done-flip guard's bar (OMN-20368): the OCC contract on `origin/dev` binds each labelled criterion (`binds_ac`) to a PASS receipt on the current entry. A merged PR, ticked boxes, `NO_ACCEPTANCE_CHECKS`, a skip or a stale receipt is a hold.
- Every AC spot-verified **at the merged tip**, not at the PR branch.
- The flip carries an adjudication comment citing the receipts: PR number + merge SHA + the line proving each AC.

**A flip with no cited receipt is a defect, not a closure.**

**Applies only to issues with no children.** Parent and epic state is derived by the rollup; this lane never writes it. The exclusion covers every rule in this section — flip, hold and correct alike — and the Linear-reconciliation table below.

### Hold (comment, do not flip)

- Any unmet AC.
- Any DoD box that cannot be honestly checked off. Amend the description only where evidence genuinely supports it — never to make a box checkable.
- Any ticket assigned to an external collaborator mid-work.

### Correct

- **Stale claim** — `In Progress` with no commit on a ticket-named branch/worktree, no PR event, and no ledger CLAIM in 24h: comment asking state, or return to `Backlog` with the reason recorded. **Comments do not count** — see the dated rule below, and derive the set with `uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-started-node`. **Do not strip assignees.** Applies only to issues with no children.
- **Misfiled** — `In Review` with no PR: return to `In Progress` using the fabricated-In-Review correction pattern (precedent: OMN-16536). Applies only to issues with no children.

### Done ticket, mechanism provably absent — reopen vs. successor (OMN-17403 Decision B, 2026-09-16)

Operator ruling, 2026-09-16 (`docs/tracking/ROLLING_WORK_LEDGER.md`, RULING row lane=rulings-b-c-1330,
adopting the orchestrator's recommendation: *"Go for your recommendation on b, and c."*): when adjudication finds a **Done** ticket whose acceptance criteria were **never actually met** at closure — the
mechanism it claims to have installed/wired/enforced was never actually installed/wired/enforced —
**REOPEN** the original ticket; the evidence trail stays attached to the AC it failed. When the AC
**were** genuinely met at closure and something has since **regressed** (config drift, a later change
silently disabled it, a dependency moved), **MINT A SUCCESSOR** citing the original as prior art; the
original closure stays honest. Either way, add an evidence comment naming which of the two applies and
why, citing the live probe. Precedent pattern (four times in two days pre-ruling): OMN-16972, OMN-14241,
OMN-18262, OMN-18175 — each Done, each with the class recurring after closure.

### Started means a worktree and a commit — comments never count (2026-09-03, OMN-16729)

> **Operator ruling, 2026-09-03:** *"In Progress means a worktree and a commit exist for it. Comments are not activity. Done requires durable evidence and the path that produces it is the top priority."*

**The rule.** A ticket is **idle** when, inside the 24h window, there is:

1. no commit on a branch or worktree **named for the ticket**, *and*
2. no PR event, *and*
3. no ledger `CLAIM` (or `CLAIM_UPDATE`) naming it in `docs/tracking/ROLLING_WORK_LEDGER.md`.

Those three are the **only** admissible signals. A comment — on Linear or on a PR — is not one of them and is never weighed.

**Why the third disjunct had to die.** The retired wording was *"`In Progress` >24h with zero commits, PRs, **or comments**"*. A triage lane's own adjudication comment is a comment, so every ticket this pass touched became un-stale for the next pass. That is measured, not theorised — `docs/tracking/archive/ROLLING_WORK_LEDGER_2026-08-31-split.md:2437` records the rule collapsing after a single run: *"six of seven carry substantive triage comments from the 08-29 pass that already adjudicated them … so the rule's own trigger (zero commits, PRs, **or comments**) is not met."* Six of seven candidates were rescued from the stale bucket by the previous pass's own output.

**Derive it mechanically, never by eye.**

```bash
uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-started-node OMN-17470 OMN-17503 --no-metadata            # explicit ids
uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-started-node --project <sprint project id>                # needs LINEAR_API_KEY
printf 'OMN-17470\nOMN-17506\n' | uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-started-node --no-metadata
```

**`--metadata`, `--project`, or `--no-metadata` is now required (OMN-18040).** `PARENT` and
`EXTERNAL` are derived only from Linear facts (`has_children`, `assignee`) supplied via
`--metadata <file>` or resolved automatically by `--project`. All three invocations above used to
omit both, which silently rendered `has_children=None`/`assignee=None` for every ticket and both
fences read `0` — indistinguishable from "no ticket has children or an external assignee". The
script now refuses to run without one of the three flags; `--no-metadata` is the explicit
acknowledgment for the explicit-id/stdin forms above, which do not carry Linear facts inline. If
you need `PARENT`/`EXTERNAL` for an explicit-id run, resolve metadata separately (a Linear GraphQL
children+assignee read over the ids) and pass it via `--metadata <file>`.

Per ticket it reports the worktree path (or none), commits ahead of `origin/dev`, last commit time,
PR count and states, last ledger CLAIM time, and one verdict with its reason:

| Verdict | Means | Lane action |
| -- | -- | -- |
| `PARENT` | the issue has children | never written — the rollup derives it. Checked first; no evidence is even weighed. |
| `EXTERNAL` | assigned to an external collaborator | comment-only, never flipped or demoted |
| `STARTED` | at least one admissible signal inside the window | leave it |
| `UNSTARTED` | none of the three | this is the stale-claim set — comment, or return to `Backlog` with the reason |
| `UNKNOWN` | PR evidence could not be fully read (a repo's PR list was truncated) | never demote on this — treat like an outage, ask state instead |

**Three traps the script closes, all observed live:**

- **A worktree is not a commit.** `worktrees/OMN-17470/omnimarket` existed and was clean — at `f62aaa4f`, which is OMN-17469's foundation commit. Zero commits ahead of base is zero evidence, and the script counts it as such.
- **`updatedAt` is not a PR event.** GitHub bumps a PR's `updatedAt` when somebody comments on it. Admitting it would restore the retired comment disjunct through the side door, so `pr_event` is `max(createdAt, mergedAt, closedAt, last commit on the PR)`. `updated_at` is still reported, labelled informational.
- **A fixed `--limit` page is not the whole repo (OMN-18040).** `gh pr list --limit 200` on a high-churn repo (`onex_change_control` ran ~9800 PRs at measurement time) only ever sees the ~200 most recent — every older PR reads as `pr_count=0` with `errors: []`, a confident wrong answer. The page now escalates until a call returns fewer rows than it asked for (exhausted) or `--pr-max-limit` (default 20000) is hit; a repo still at the ceiling is named in `truncated_repos` and `errors`, and any ticket that would otherwise read `UNSTARTED` on that incomplete evidence reads `UNKNOWN` instead. This adds real wall-clock time on the largest repos (~1 minute for `onex_change_control` alone, once per run) — the cost of reading the repo in full instead of a fixed slice of it.

A `gh` or `git` failure is recorded in `errors` and never rendered as absence of evidence: an outage must not manufacture `UNSTARTED` verdicts. The rule and the script are covered by `tests/test_triage_started.py` and `tests/test_morning_lane_rules.py`.

### Report

Counts of **flipped / held-with-reason / corrected / commented**, each bucket listing its ticket ids.

---

## Reconcile — plan rows vs measured ground state

The half that makes the morning a **process** rather than a report: the ground state this run just measured, judged against the plan's falsifiable rows. Off-rails rev-2 **B1** (`docs/tracking/2026-08-29-beta-off-the-rails-analysis.md` §4.2).

Output: `beta/tracking/<date>-beta-rebaseline.md`, under 250 lines, tables over prose.

### What counts as a row

A **falsifiable row** states a condition an external observer could disprove: the plan's numbered beta conditions and its gates, each numbered must-do row with its Done-proof probe, each operator top-three item. A row with no disprovable condition is **not a row** — it is listed in residuals as *"not falsifiable as written"*. Inventing a probe for a vague row is how a reconciliation launders prose into evidence.

### The verdict ladder

Cumulative stages. Report the **highest stage actually reached**.

| Verdict | Means | Proof required |
| -- | -- | -- |
| `OPEN` | not merged | — |
| `LANDED` | merged to the integration branch | pulls API `merged_at` **plus** the merge SHA. A PR body claim is not proof. |
| `DEPLOYED` | the merged artifact is **running** on the lane the row's probe targets | an image digest, a release-version readback, or a live introspection response |
| `PROBED` | the row's own Done-proof probe **ran in this run** and returned the expected result | the exact command **and its actual output** |
| `UNKNOWN` | a read or probe failed | the failing command, named |

**Never infer `DEPLOYED` from `LANDED`.** That inference is root cause **RC-E** in the off-rails analysis — "Done stops at merged" — and it is the single most common way this report goes false. **Never infer `PROBED` from `DEPLOYED`.** `UNKNOWN` is an honest verdict; a guessed verdict is a defect.

Each row also carries `beta_path` — true where the plan's own gates depend on it, false where the row is real but off the beta critical path. Only beta-path rows reach `GOAL.md`.

### Linear mismatches

For every row carrying a ticket, compare the reconciled verdict with the live Linear state. The Reconcile phase **reports and does not mutate**; the Goal phase owns mutation under a stricter rule. Two directions, labelled distinctly:

- **Evidence-less Done** — ticket `Done`, row not `PROBED`.
- **Lagging board** — row `PROBED`, ticket not `Done`.

### Hard rule

**The diff is derived, never retyped.** Every verdict traces to a command run in *this* run or to a cited line in a source document. Nothing carries forward from yesterday's report; nothing is remembered.

---

## Integrate — yesterday's landed work, planned into lanes

Reconcile **measures** the `LANDED`-vs-`DEPLOYED` gap. Integrate **acts** on it.

Operator direction, 2026-08-30, verbatim:

> "Every morning we should be trying to come up with a plan to integrate anything that was done the day before."

Without this phase a row parks at `LANDED` indefinitely and every morning reports it truthfully — a correct report of a stuck system, produced daily, changing nothing. On the morning the phase was written the ladder read **16 of 45 must-do rows `LANDED` against 4 `DEPLOYED`**: merged code reaching no lane, no image and no consumer was the dominant waste in the beta push, and nothing in the process converted that measurement into an action.

Model `sonnet`, effort `medium`. Runs **after Reconcile** (whose ladder is its input) and **before Goal** (whose rows it nests under).

Output: `beta/tracking/<date>-integration-plan.md`, under 250 lines, tables over prose.

### Input — three sources, none skipped

| Source | What it contributes |
| -- | -- |
| The Reconcile ladder | every row at `LANDED` — already measured, already judged, and stuck |
| Merges in the window | `gh pr list --repo OmniNode-ai/<repo> --state merged --search 'merged:>=<since>'` across `args.integrationRepos` |
| Artifacts published in the window | PyPI releases (latest version + upload time vs what the lanes actually run) and images built (`gh run list` on the build/publish workflows, plus the pushed tag or digest) |

The window is `args.integrateSince` (default: the day before `args.date`) through `args.date`. It is derived from `args.date`, never from the clock — determinism is a property of the whole process, not just of Reconcile.

### What an integration row carries

| Field | Rule |
| -- | -- |
| `what` | one line, plain language, naming the behavior a user or a lane gets |
| `source` | the Reconcile row id, `<repo>#<pr>`, the release, or the image tag |
| `kind` | `deploy` · `repin` · `wire` · `release` · `dogfood` |
| `destination` | **specific to the point of being executable** — which lane/cluster via which named pipeline (`scripts/deploy-runtime.sh`, `refresh_stability_lane.sh`, the SSM path for staging); or which pin in which dependency file; or which consumer to wire; or the dogfood command. **"Deploy it" is not a destination.** |
| `next_action` | the single next thing a lane does, as a command or an unambiguous instruction |
| `probe` | the command that proves it **integrated** — see below |
| `hold` | a named hold (e.g. `RUNTIME_REPIN_RELEASED`, an operator fence quoted from the decision stack) or the literal `none` |
| `ticket` | searched for first, reused where one exists; created only when the search returns nothing |
| `unblocks` | the Reconcile row id this moves up the ladder, so Goal can nest it |

**The probe interrogates the running system** — a version or digest readback from the lane, a live introspection response, a consumer-group offset, an installed-package version in a clean environment, an HTTP response from the deployed surface. **A merge check is not a probe:** merged is the row's *input*, not its proof. This is the same distinction the verdict ladder draws between `LANDED` and `DEPLOYED`, applied to the action instead of the state.

### Grouped by destination, not by repo

Rows that ride the same deploy or the same repin are **one batch**, and the report says so. Three rows waiting on one stability-lane refresh is one action; reporting it as three is how a morning plan becomes noise. Batches are ordered by how many `LANDED` rows each unblocks, most first.

### The four rules

Encoded in the schema and the agent brief, **not left to judgement** — each has a cheap failure mode that reads as success.

1. **`LANDED` never counts as integrated.** Do not write a row off because the PR merged, and never report a `LANDED` row as needing no action. If one genuinely needs none, that is a *claim*, and it goes in residuals with the reason the merged artifact is already reachable by its consumer.
2. **A row without a probe is invalid.** It goes to residuals as *"no probe determinable: &lt;what could not be resolved&gt;"* rather than shipping with a vague or merge-based probe.
3. **A hold is named, never silently skipped.** The held row still appears in full, with the action that runs once the hold lifts, and every distinct hold also appears in the top-level `holds` list.
4. **A repo with merges but zero rows states `nothing to integrate: <why>`** — a real reason ("3 merges, all docs-only"; "2 merges, both CI config, no runtime surface"), never a bare empty cell. Zero merges records `merged_in_window: 0` and says so.

### This phase plans; it never integrates

Integrate **deploys nothing, repins nothing, restarts nothing, and touches no lane.** It writes rows that other lanes execute under their own gates. Any prod-touching row inherits the prod-promotion gate unchanged — a row in this plan is not an approval, and the plan is not a grant.

---

## Dropped work — the five sections nobody is driving

Every other phase of this workflow measures work somebody is already driving. Reconcile classifies rows that exist on a plan; Integrate acts on merges that happened; Triage adjudicates tickets that moved. **None of them can see a plan that stopped moving, a ticket that was minted and never started, or a lane report nobody ever opened**, because none of those produces an event. They are invisible by construction, and the morning report stays perfectly truthful the whole time it is missing them.

Operator default, 2026-09-20, not vetoed, rendered as an attributed paraphrase: the question "how do we make sure this work doesn't get dropped again" is answered by the morning ground state running **daily and unconditionally** and carrying five sections that name unpicked-up work, printed by the session-start hook.

The failure of record: the enforcement-integration plan (epic `OMN-18527`, children `OMN-18528`–`OMN-18538`) was minted 2026-09-16 and sat Backlog/unassigned with no PR for **four days** while the failures it was written to close kept recurring. Both the plan text and `PLAN_LIFECYCLE.yaml` were stale. No daily surface said so. Ticket `OMN-18954`.

Model `opus`, effort `high`. Runs **after Integrate** and **before Goal**, whose header block carries its counts. Output: `beta/tracking/<date>-dropped-work.md`, under 200 lines, tables over prose.

### The five sections, in this order, under these headings verbatim

| Heading | What it enumerates |
| -- | -- |
| `RED ON DEV HEAD` | per registry repo: the integration-branch head sha, the **failing or absent** required contexts on it, the lab-pass receipt result for that sha on each lane that emits one, and the age in hours of the last successful deploy-agent job |
| `RED ON DEV HEAD` — clone-health half | per canonical clone under the registry root: unmerged paths, staged and unstaged tracked edits counted separately, and commits behind origin; plus the dispatch venv's reconcile verdict, exit code and age. A clone with unmerged paths is **WEDGED** and sorts first. The remedy named on every unclean row is the sanctioned convergence script, never a hand-run checkout |
| `STALE PLANS` | every dated plan under `beta/plans/` minted in the last 30 days, plus every `active` `PLAN_LIFECYCLE.yaml` entry: days since minted, days since the text last changed, the live Linear state **by state type** of every ticket it names, the Done / In Progress / Backlog-unassigned counts, and a **flag** wherever the plan text or the registry entry claims a state the live data contradicts |
| `UNSTARTED WORK BY AGE` | current beta-sprint tickets AND workspace-wide projectless tickets, in separate subsections, whose state **type** is `backlog` or `unstarted`, minted more than 48h ago, with no assignee and no pull-request attachment — grouped by parent epic, oldest first, naming the plan that minted it |
| `UNREAD LANE REPORTS` | lane reports in the orchestration scratch directory that nobody has read, in two classes: **unclosed** (written in the last 24h, and the lane has no `CLOSEOUT` and no `TERMINAL` row in the ledger) and **orphaned** (older than 7 days, and no ledger row has ever named the lane or the file). Per row: filename, lane, age, and which row type is missing |
| `PROPOSED DISPATCH LIST` | at most ten items from the four above, ranked by gate class then age, one line each: `<ticket or repo> \| parent: <epic\|none> \| plan: <doc\|none> \| gate: <class> \| age: <n>d \| why: <clause>` |

Gate class, highest first: `BLOCKING-MERGE` (a failing or absent required context on a head sha), `FAIL-CLOSED` (a gate that refuses when it cannot resolve — a missing lab-pass receipt, an unresolvable premise), `PLAN-CONTRADICTED`, `UNREAD-REPORT`, `UNSTARTED`.

#### `UNSTARTED WORK BY AGE` — sprint and projectless scopes (OMN-17427, top-20 item 11)

The 2026-09-30 ruling files new tickets in the Backlog with no project. Read two scopes
independently and report each under its own subsection: **SPRINT PROJECT**, using the current
beta sprint project resolved live from the dated project covering the report date (not a Cycle),
and **PROJECTLESS BACKLOG**, workspace-wide with GraphQL filter `project: { null: true }`.
Do not constrain the projectless read to sprint membership, a fixed parent epic, or a
creation-date lower bound.

Both scopes use the same eligibility predicate: state type `backlog` or `unstarted`, created
strictly more than 48 hours before the report date at 00:00:00Z, no assignee, and no attachment
that is a pull request. Complete issue pagination until `hasNextPage: false` in each scope,
and complete attachment pagination before declaring a ticket has no PR.

Group by parent epic, oldest first within each group; use `none` for a missing parent. Carry
ticket id, title truncated to 60 characters, age in days, parent epic id, and the minting plan
found by grepping `beta/plans/` for the ticket id (or `none`). Compute each scope's total,
distinct parent-epic count and oldest age **before applying the display limit**. Keep under
40 displayed rows across both subsections, reserving at least one row for each nonempty scope,
and state each scope's total and omitted count even when one scope is empty.

For the section count and the `unstarted_work_by_age` headline, deduplicate by ticket id and
count the union of both scopes. Count distinct non-null parent epic ids across that union;
adding the two epic counts double-counts a parent with children in both scopes. Feed eligible
tickets from both scopes into the `PROPOSED DISPATCH LIST` before truncating displayed rows.
A failed or incomplete read is **UNKNOWN**, with its command in the section's `unknown` array.
Union totals, epic count and oldest age are UNKNOWN while either scope is incomplete. The
schema's integer `count` is then the number of confirmed qualifying tickets only, explicitly
labelled partial in the report; a sprint-only total must never be presented as complete.

Name a live positive control for each scope. Re-read OMN-18527 and children OMN-18528 through
OMN-18538 with their current project, state type, createdAt, assignee and PR attachments;
they can also control the projectless read when their project is null. Show why a control no
longer qualifies for a scope. No count is copied from a previous report or inferred from a
missing control.

#### Clone health lives in the red-head section (OMN-19007)

Measured 2026-09-21: the canonical infrastructure clone sat in an abandoned merge for six hours.
Every delegate invoked through the wrapper died at import, and every lane that hit it read the
failure as a quirk of delegation, because the symptom appears nowhere near the cause. The
session-start workspace-sync hook did print a drift warning — once, at session start, on a surface
nobody reads daily. **A warning printed where nobody looks is the same as no warning.**

It is reported inside `RED ON DEV HEAD` rather than as a section of its own because it is the same
question one layer closer: whether that repository's head is usable. The remote half asks whether
CI is red; this half asks whether the working copy on this machine is. The row that stops work
today is usually the second.

The remedy text names `converge-canonical-clone.sh` and `reconcile-workspace-venvs.sh` and
explicitly forbids a hand-run checkout, reset or merge — that is the plumbing Operating Rule 19 and
the OMN-18798 guard exist to refuse, and it discards a peer lane's work with no record. The
convergence script preserves the full diff and the untracked files under
`.onex_state/canonical-clone-converge/` and writes a ledger row; a hand-run repair does neither.

An unreadable reconcile surface is `UNKNOWN` naming the path, never `IN SYNC`, and a verdict older
than a day is `STALE` with its age.

#### `PARENTS OVER ADMISSION CAP` — rescinded (OMN-19003)

The section reported parents the ticket-creation guard was refusing new children under, keyed on
the count rather than on age because a parent can block every new child while all of its own
children are recent. The operator **rescinded** that cap on 2026-09-21 — rolling work ledger
`RULING` row `2026-09-21T14:46:45Z`, item (f). No parent is refusing anything now, so every row
the section would write is a false claim, and the section is gone with the cap, along with its
`ADMISSION-BLOCKED` gate class and its headline key. Re-adding either needs a fresh operator
ruling, not a reading of this paragraph.

#### `UNREAD LANE REPORTS` — the two traps (OMN-18948)

**The ledger is rolled, so the live file is not the corpus.** `docs/tracking/ROLLING_WORK_LEDGER.md` splits into `docs/tracking/archive/ROLLING_WORK_LEDGER_*-split.md`, and a citation older than the last roll is not in the live file at all. A grep of the live ledger alone reports nearly every older report as orphaned — a fabricated finding, not a discovery. The probe greps the live ledger **and** every archive split, and the section names both.

**The lane name is the basename.** Reports are `<lane>.md`, and a lane's own ledger rows carry the same string as `actor=<lane>`, which is what makes the join possible without a registry. The directory also holds `.log`, `.tsv` and `.json` working files; those are not reports, are excluded, and the count of exclusions is stated.

**The count is printed by a hook in another repository, and that is a two-file change.** The session-start goal surface greps an explicit list of header keys. A key this phase writes and that list omits is printed nowhere, so the section would be measured every morning and read by nobody — the same failure the section exists to report, one layer up. Each side pins its own copy of the key list against an independently spelled tuple, because neither repository's CI checks out the other, so a rename goes red on both halves rather than silently unprinting one.

**The control is a closed lane, never a written file.** The positive control names a lane whose report is in the directory and whose `CLOSEOUT` or `TERMINAL` row the same grep does find, with the file and line it found it at — that is what tells "no unclosed lanes" apart from "the row shape changed and the grep matched nothing". Manufacturing a control by creating or touching a file in that directory is forbidden: the phase is read-only on the filesystem, and a control that writes is a mutation under another name.

### Four constraints, each answering a failure that reads as success

They apply to every section, the fifth included.

1. **Live probes only.** A section derived from a plan document or a registry file would inherit exactly the staleness it exists to detect. Nothing is carried forward from yesterday's report.
2. **A positive control per section, not only per zero** (CLAUDE.md rule 16). An empty section and a broken query produce the same output; only a control tells them apart, and a control that is only written when the count happens to be zero has never been exercised. The standing control for `STALE PLANS` and `UNSTARTED WORK BY AGE` is the enforcement-integration plan and its eleven children, which qualified for both on 2026-09-20 — a zero on either section must show those live rows and state why they no longer qualify.
3. **Selection by Linear state `type`, never by a workflow-state display name.** The display names are being retired; a name-matched filter goes silently empty on a rename. Pinned by `tests/test_morning_lane_rules.py`.
4. **Section four proposes; it never acts.** This phase dispatches nothing, assigns nothing, mints nothing and changes no ticket state. An automation that both finds the work and starts it has no review point, and what was asked for was a list to dispatch *from*.

`ABSENT` is reported separately from `FAILING`, because a required context with no check-run at all on the head sha is the one a rollup hides. A probe that errors is `UNKNOWN`, named with its failing command, and is never folded into a count as an absence. Stderr is never suppressed on any probe in this phase.

### Two whole-tree ratchets a lane of this workflow will meet (OMN-18968)

Both refused the lane that built this phase, both correctly, and a lane meets them at commit time
rather than design time unless it has read them first.

- The **public-repo hygiene gate** counts the registry clone's lowercase directory name, anywhere
  in a public repository's tracked files, as tree-surface exposure against a burn-down budget. A
  Python identifier and a code comment were enough to take the tree over. Rename; the budget is
  never a place to book new debt.
- The **skip-count ratchet** refuses a test that is collected and then skipped on a runner. That
  rules out any cross-repo check whose other clone is absent there — such a check compares against
  a list spelled in its own repository and runs everywhere, or it does not exist.

Both are stated in full, for every lane rather than only this workflow's, in
`ops_tooling_pkg/lane_rules/lane-rules-block.md`. This is a pointer, not a second copy: a rule
transcribed twice goes stale in one of them.

### Three probe-semantics corrections (OMN-18968)

Each was measured on the phase's first live run, and each produced a plausible, clean-looking
result rather than an error. They are written into the brief so they are not re-derived every
morning.

| What goes wrong | What the brief now requires |
| -- | -- |
| The issues connection omits archived issues by default, so 376 of 2,736 cited ids resolved to nothing and every plan citing one would have read as stalled | ask for archived issues explicitly; a citation that still resolves to nothing is then a genuinely dangling reference and is reported as one |
| The lifecycle registry's `UNSTARTED` verdict is defined over a plan's OPEN cited tickets only — read plan-wide it emitted 98 false contradictions | read `resolved_status` with its own scope; a plan whose completed tickets are done and whose two open ones are unstarted is in progress, not contradicted |
| A sha's check results are every run that ever touched it. On a release-synced repo the integration head IS the release head, so a release-branch failure reads as an integration-branch blocker; and a pull-request-scoped context reads as absent on a push-produced sha | select runs by event **and** head branch; report pull-request-scoped contexts as `NOT APPLICABLE`; put release-sync failures in a row of their own, outside the red count |

**Two of the three blocking-merge candidates the first live run proposed were the third
misattribution.** The one real finding was a container-drift setup failure on a genuine
integration-branch push run. That ratio is the reason the rule is spelled in the brief rather than
left to the phase's judgement.

**The honest limit this exposes.** A positive control proves a query returned rows. It cannot
prove the query asked the right question — the first two corrections were caught by the control,
the third was caught only by a lane acting on the output.

### The five headline lines

The phase returns exactly five lines in `headline`, which the Goal phase copies **verbatim** into `GOAL.md`'s header. They are the only counts the OMN-17168 SessionStart hook can read, and it greps them by these exact key spellings:

```
dropped_work: beta/tracking/<date>-dropped-work.md · derived <utc ts> · sections <n>/4 conformant
red_on_dev_head: <n> repo(s) with a failing or absent required context · <n> head sha(s) with no PASS lab-pass receipt · last deploy-agent success <n>h ago
stale_plans: <n> of <n> dated plans contradicted by live Linear · <n> unstarted-only · oldest <n>d since minted
unstarted_work_by_age: <n> ticket(s) >48h old with no assignee and no PR · across <n> epic(s) · oldest <n>d
proposed_dispatch: <n> candidate(s) · top: <the first line's subject and its gate class>
```

An unresolvable slot reads `UNKNOWN`. It never reads `0` — a zero nobody measured is worse than an absent count, because it renders as good news.

## Unconditional phases — DroppedWork and Goal are never short-circuited

`DroppedWork` and `Goal` are exempt from the idempotency guard's verdict. The guard still **reports** on them, so a stale or malformed artifact stays visible; its verdict simply cannot decide that they do not run. In the script this is the `UNCONDITIONAL_PHASES` set, consulted by `runs()`.

The reason is a property of the **artifact**, not a convenience, and it is the same reason that already exempts `DecisionsRegister`. Every gated phase writes a **dated** report: once delivered for the date it is finished work, and re-deriving it is pure waste. `GOAL.md` is the opposite kind of file — a **standing current-state document**, overwritten wholesale on every run, and the exact path the SessionStart hook reads. A verdict of `already-delivered` on it saves no work; it decides, silently, that today's session opens on an older picture. `DroppedWork` is unconditional for the same reason: its entire output is a set of live counts that the standing file carries.

There is deliberately **no freshness predicate, no skip predicate and no argument** that turns either phase off. `args.publish` still decides whether the result is *published*, which is a different question from whether it is *derived*.

Consequence for the OMN-16972 DoD surface: `expensive_agents_spawned` counts **gated** phases only, and the two unconditional ones are counted and named separately in `unconditional_agents_spawned` / `unconditional_phases`. Folding them in would make a clean same-date re-dispatch read `2` and the guard would look broken while working exactly as specified.

## Goal — the session goal, and reconciling Linear from it

`GOAL.md` contains **exactly** the reconciled rows whose verdict is not `PROBED` and whose `beta_path` is true, **plus the Integrate phase's actions nested as sub-rows under the rows they unblock**. Nothing else. A row at `PROBED` is finished work and must not appear. A non-beta-path row belongs in the reconciliation report's appendix.

An empty goal is a **real, reportable state** — stated with the count of rows examined, never padded.

### Header keys, exactly

Capture `state_as_of` when deriving the goal with `date -u +%Y-%m-%dT%H:%M:%SZ` (`YYYY-MM-DDTHH:MM:SSZ`). Use the observed UTC time, never a date-only value or midnight synthesized from the report date. The workflow date still selects dated input reports. Legacy date-only goals cover the whole UTC day; the SessionStart hook measures their age from 23:59:59Z and states that basis in its output (OMN-20661).

```
state_as_of: <full UTC timestamp>
source_plan: <planDocs paths, and which copy each was read from>
ground_state: beta/tracking/<date>-morning-ground-state.md
reconciliation: beta/tracking/<date>-beta-rebaseline.md
rows_examined: <n>
rows_open: <n>
```

Then, **immediately after those six keys and before the first goal row**, the five dropped-work headline lines, copied **verbatim** from the `DroppedWork` phase's `headline` array — unedited, unre-counted, in the order it returned them. If that phase reported `BLOCKED` or returned no headline, the block is replaced by the single line `dropped_work: UNAVAILABLE — <reason>` and the reason goes in `residuals`. An **absent** block is a reportable state; a **fabricated** one is a defect, and a zero nobody measured is the worst of the three, because it renders as good news.

Then one entry per goal row: **row id | what it is in one line | current verdict | next action + a NAMED owner | the exact probe command that flips it to `PROBED`**.

### Integration actions are sub-rows, never free-floating rows

Every integration row whose `unblocks` names a goal row is written as an indented sub-row directly beneath it:

```
-> <integration row id> | <destination> | <next action> | <probe> | hold: <hold>
```

An integration action **never appears as a top-level row.** It exists to move one specific plan row up the ladder, and detaching it from that row is exactly how an integration plan degrades back into a task list nobody can prioritize. Rows whose `unblocks` is `none`, or which name a row not in `GOAL.md` (already `PROBED`, or off the beta path), go to residuals with that reason — they stay in the integration plan, they just do not belong in the goal file.

**A goal row at `LANDED` with no integration sub-row is a defect in that run**, flagged in residuals by row id: Integrate is required to produce either an action or an explicit reason for every `LANDED` row, so a silent absence means one of the two phases failed.

**Under 88 lines** — raised from 60 when the sub-rows were added (OMN-17195), and from 80 to 88 for the five-line dropped-work block (OMN-18954), and still a hard cap. This file is read aloud at session start by the OMN-17168 hook; length is its failure mode. If the cap would be exceeded, drop the **lowest-leverage whole goal rows** and record in the header how many were dropped and where to read them. Never silently truncate the sub-rows off a row you kept — a row without its actions is the pre-Integrate failure mode restored.

### Publishing

`beta/GOAL.md` is overwritten wholesale — it is a current-state file, never appended. The reconciliation report is mirrored to `beta/tracking/<date>-beta-rebaseline.md` and the integration plan to `beta/tracking/<date>-integration-plan.md`, both under the **same publish/DRY semantics**: published in `publish: true`, written locally only in `publish: false`. One branch, one commit, one PR.

The merge verb is **read live** (`gh api repos/OmniNode-ai/docs_repo --jq '{auto:.allow_auto_merge,squash:.allow_squash_merge,merge:.allow_merge_commit,rebase:.allow_rebase_merge}'`) and never guessed or copied from another repo — repo merge settings drift, as the registry table in `CLAUDE.md` documents at length. The merge is verified via `gh pr view --json state,mergedAt` before `publish_state` may be reported `PUBLISHED`.

### Linear reconciliation rule

**Linear is reconciled FROM the diff, never read as truth** (memory `feedback_session_goal_from_ground_state_reconciled_to_plan`).

**Applies only to issues with no children.** An issue with children — a parent or an epic — is never written by this lane in any row of the table below. Parent and epic state is derived by the rollup, and a parent that reaches `PROBED` here is reported, not flipped.

| Case | Action |
| -- | -- |
| Issue **has children** (parent or epic) | **Leave alone, in every row below.** Report the mismatch; the rollup derives parent state. |
| Row `PROBED`, ticket not `Done` (no children) | **Flip to Done.** The adjudication comment carries the probe command and its output. |
| Ticket `Done`, row not `PROBED` (no children) | **Flag with a comment** naming the missing probe. **Do not reopen.** |
| Anything else | Leave alone. |

A correction requires **both** a merged PR verified via the pulls API **and** a live probe executed in this run that returned the expected result — both, not either.

**Evidence-less Done is flagged, not reopened.** Reopening a ticket on the strength of a probe nobody ran manufactures churn and overwrites the operator's own board decisions with a guess.

---

## dod-closeout-sweep — the deep pass

The implementation is `src/ops_tooling_pkg/handlers/dod_closeout_sweep/dod-closeout-sweep.js`.
Dispatch it by absolute `scriptPath`, as the packaged launcher does. The complete current
contract is [the closer's format contract](../dod-closeout-sweep/README.md); this summary
replaces the former Verify/Audit pipeline and same-date delivery model.

**Applies only to issues with no children.** Parent and epic states belong to the rollup.
Enumerate excludes parents; Apply re-reads children before each mutation and returns
`fenced-midrun` without writing when a child has appeared. Live-claimed tickets remain fenced.
The fence list comes from `uv run --project "$registry_root/../ops_tooling_pkg" onex-triage-fences-node docs/tracking/ROLLING_WORK_LEDGER.md --open-prs`,
and is **never hand-derived**. Re-read it before mutations because another lane can claim work
while the sweep is running.

The sprint is resolved **live** from the dated Linear PROJECT covering `args.date`, never
from a Cycle or a stored sprint id. `args.project` overrides that live resolution. The current
project, immediately previous dated project, and started tickets with merged product PRs are
the enumeration scope. Zero or ambiguous current-project resolution produces the named
`SPRINT_RESOLUTION_FAILED`, rather than selecting a remembered sprint.

The seven phases are Precheck, Enumerate, Bind, Accept, Decide, Apply and Report. Each parsed
criterion must have a behavior check authored in an isolated worktree, accepted by a separate
agent with a red result at the parent and a green result after the check, and verified by
`dod_verify`. A source grep or a PR-state readback cannot prove a criterion. An absent binding,
unaccepted check, unverifiable acceptance result, unreleased publishing-repo merge, or incomplete
verification leaves the ticket open with the unmet criteria named. Apply uses `save_issue`,
so the durable done-flip guard decides every proposed Done transition.

The Enumerate result is a JSON object containing `candidates` and `counts`, never a bare
array. An invalid return throws `SCOPE_SHAPE_VIOLATION`; a malformed result cannot become an
empty successful sweep. A valid empty scope emits `VERIFIED NOTHING: zero candidates` and
returns `verified_nothing: true`. Since it changes no ticket, it writes no report file or PR.

The run key comes from the scheduled fire, not just the date. A duplicate fire's TERMINAL row for `lane=dod-closeout-sweep` carrying its `run=` key
short-circuits; a later two-hour fire examines the least recently examined tickets. By default,
six candidates become parallel chunks of two. Fire + 3500 seconds is the stop-starting clock
and fire + 4300 seconds is the return clock, leaving budget for Apply and Report. A skipped
criterion remains `not_run`, and the next fire can reach it.

The verification command includes its audience:
`bash "$registry_root/omnibase_infra/scripts/onex" skill dod_verify <TICKET> --execution-audience local_done_gate`.
`DOD_VERIFY_ALLOW_STALE_OCC_REF` is never set. Read-only probes that cannot establish an AC
produce an honest hold; the lane does not substitute a synthetic probe for a required live write.

A run with changes writes a time-qualified report in
`$DOCS_REPO_PATH/beta/tracking/` and one ledger TERMINAL carrying the run key,
counts, refused bindings, and unmet criteria. Open comments carry a stable `signature=` so
identical outcomes do not repost the same comment on every fire. The launcher schedule is
every two hours at :45, with a 6300-second ceiling.

---

## Scheduling — wired 2026-08-30 (OMN-17173)

Fires at **04:43 local**, after `morning-friction-sweep` (04:15) and `morning-worktree-prune` (04:30), so this run's triage sees what those two just produced.

launchd `StartCalendarInterval` user agent — **wired and proven, OMN-17173**.

| Workflow | Label | Fires |
| -- | -- | -- |
| `morning-friction-sweep` | `ai.omninode.morning-friction-sweep` | 04:15 local |
| `morning-worktree-prune` | `ai.omninode.morning-worktree-prune` | 04:30 local |
| `morning-ground-state` | `ai.omninode.morning-ground-state` | 04:43 local |

Each agent runs `launchd/morning-workflows/morning_workflows_tick.sh <workflow>`, which writes a **firing receipt before it does any work** and then asks the existing headless scheduler agent to dispatch the registered morning node with an explicit typed command over the configured dev bus. The other scheduled workflows retain their own entry points.

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

**The contract and the script version together.** Any format change — a new section, a changed column, a relaxed or tightened triage rule — edits **both** `docs/workflows/morning-ground-state/README.md` and `src/ops_tooling_pkg/nodes/node_morning_ground_state_orchestrator/prompts/briefs.md` **in the same commit**. Neither file is authoritative alone: the script's agent briefs point at this document, and this document describes what the script runs. A change to one and not the other is drift, and drift is how the process silently reverts to ad hoc.

The script is deterministic by construction: no `Date.now()`, no `Math.random()`, date supplied via `args`. The pre-check's 90-minute window needs a clock and gets one the same way every other fact here does — a live read by the agent, never a clock read in the script.

**This rule is now mechanically checked.** `test_morning_ground_state_node.py` fails if the script and this contract drift apart on the idempotency surface — see [Validation](#validation). Run it before every commit that touches either file.

---

## Successor

**OMN-16841** node-ifies the ground-state half: delivery facts (ticket transitions, PR state + CI verdicts, decisions) emitted as events on the bus, materialized as a `ground_state` projection, rendered by the system-health dashboard widget — the pattern epic **OMN-16776** establishes for flow truth, applied to delivery truth. At that point the markdown report is regenerated *from the projection* and this contract is updated in the same change (AC4 there).

**OMN-17019 (C9)** supplies the obligation projection the Reconcile and Goal phases should render from. The operator's 2026-08-30 direction is explicit that this "should've eventually become a node-based workflow": ground-state EFFECTs → reconcile COMPUTE → goal projection REDUCER → ORCHESTRATOR, with `GOAL.md` becoming a rendered view of the open-obligations projection rather than a committed file, and the OMN-17168 SessionStart hook reading that projection instead of the file. Off-rails rev-2 is equally explicit that B1 (this workflow's Reconcile + Goal half) is a **view** over C1, not the authority — build it as a renderer, and re-point it at the projection when C1 reaches L2. That re-point is part of B1's DoD, not a follow-on.

Until then, **this committed workflow is the interim** and remains the sanctioned path.

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


# morning-ground-state — packaged delegation contract

The executable handler is `src/ops_tooling_pkg/nodes/node_morning_ground_state_orchestrator/prompts/briefs.md`.

## Delegation

The mandatory step applies to morning-triage (ledger lane morning-triage-adjudication), plan-reconcile
(morning-plan-reconcile), integration-plan and dropped-work (morning-dropped-work). The schema wrapper preserves every existing
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
