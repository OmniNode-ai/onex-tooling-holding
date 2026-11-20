# dod-closeout-sweep (the closer) — format contract

The runnable half is `src/ops_tooling_pkg/handlers/dod_closeout_sweep/dod-closeout-sweep.js`. This
document is the format contract. A format change edits both in the same commit, and
`tests/test_dod_closeout_sweep.py` executes the script's pure block under node, so the decisions
described here are tested against the same source the Workflow runtime runs.

OMN-19742 retires the registry source after its caller changes land. The newer packaged
closer is preserved during that cutover; missing package scripts fail closed.

## What changed, and why

| Before | After | Measured reason |
| -- | -- | -- |
| One agent per chunk authored the criterion bindings and judged them | A **Bind** agent authors; a different **Accept** agent re-runs and accepts or rejects; the script decides Done | 2026-09-30: every candidate's criteria were bound to one symbol grep, and one binding passed on OMN-19968 where AC1 is false. RULING 2026-10-03T00:40:00Z: a binding is never accepted by the lane that authored it |
| A symbol grep could be a binding | The script refuses inspection-only checks before the acceptor sees them | Same measurement |
| Runs ended with questions to the operator (a release cut, whether an assignee counts as external) | No questions. An unmet or undecidable criterion leaves the ticket open with a Linear comment naming it, and the run report lists it | 2026-10-01 and 2026-10-02 runs |
| Tickets assigned to collaborators were excluded as "external" | Assignee is not a criterion | Closure is ownership-agnostic (operator ruling 2026-09-05) |
| Once a day at 08:45, unbounded (runs of 1 to 3 hours, one timeout at 4h) | Every 2 hours at :45, at most 6 tickets per run, least recently examined first, driver ceiling 6300s | Operator approval 2026-10-03 |
| `dod_verify` without an execution audience | `--execution-audience local_done_gate` | Every call was refused with EXECUTION_AUDIENCE_REQUIRED on 2026-10-02 |
| Sprint name had to end in "(Beta)" | Any `Sprint` name carrying two dates, zero padding optional; the window comes from the project's `startDate`/`targetDate` | Sprints from 2026-09-28 carry a theme, not a suffix; the suffix match returned zero on 2026-10-02. P-OMN-33 is named `Sprint 2026-10-5 → 2026-10-11 …` |
| Scope was the current sprint only | The union of the current sprint's started tickets, the previous sprint's started tickets until the roll moves them, and every started ticket named in a merge subject on a canonical clone in the 7 days before `date` | After the 2026-10-05 roll every run read "3 enumerated, 3 fenced, 0 candidates" while the previous sprint still held 26 started tickets (OMN-17427) |
| A CLAIM with no TERMINAL fenced its tickets forever | A CLAIM fences only while its lane wrote any ledger row in the last 48 hours; older ones are reported as `stale_claims` (`onex-triage-fences-node --stale-after-hours`) | On 2026-10-05, 680 of 729 unpaired CLAIMs were older than that, among them this workflow's own retired per-chunk lanes (`dod-closeout-chunk0` 218h, `dod-closeout-chunk5` 243h) fencing its own candidates |
| A test binding naming its repo as `OmniNode-ai/<repo>` was refused `no-repo`, and the comment said it "only reads source" | The slug is normalized to the repo; a compound or foreign repo is still refused; a shape refusal says it was not runnable as written | 17 of the 23 bindings refused on 2026-10-03..05 were real pytest node ids refused only for the slug |
| The acceptor reviewed only bindings its own binder authored | It also re-runs and re-accepts (or rejects) every existing binding on `dev` that no second lane accepted, appending a re-acceptance record with the original `proposed_by` | `dod_verify` held OMN-19995 on AC_BINDING_SELF_ACCEPTED on 9 runs: an AC1 binding on `dev` had no `accepted_by`, and nothing in the closer could ever accept it |
| A ticket rejected for a reason only a text change can clear was re-adjudicated on every fire, and each fire posted the rejection again | The binder or acceptor names the `amendment` a criterion needs; the open comment names it and records `amendment-text-sha=<hash>` of the description it was made against; `onex closeout text state` (`handlers/handler_closeout_text_state.py`) reads that hash and the description's hash now, and `selectCandidates` skips the ticket while they match | OMN-20124 was re-adjudicated in four fires and OMN-19995 in three on 2026-10-03, each reaching the same rejection (OMN-20521) |
| Two sentences rendered every refusal class | Each class renders its own reason (`REFUSAL_REASONS`) | A refused cwd read the same as a ref off merged dev, and shape faults were told their test was a grep (OMN-20585) |
| The Apply brief said never to tick an acceptance box | It ticks each criterion's box (`- [ ]` to `- [x]`, nothing else) and then flips; the guard decides both | The done-flip guard refused OMN-19453 on 2026-10-06T0645Z for two unticked boxes, every criterion bound and verified; its message: a box is ticked once a bound PASS receipt covers it |
| No evidence PR was opened when its merge wait would not fit before the run clock | The PR is opened until the no-new-work instant and need not merge in the run | 2026-10-06T1245Z: OMN-17735's four criteria were accepted eight minutes before the instant, no PR was opened, and the next run has to redo the work |
| The verifier ran as one foreground call | It runs in the background and its log is read when it exits | 2026-10-06T0445Z: OMN-19361's verifier printed verified at about 874s, its wrapper stopped at 900s, and the ticket was recorded `not_run` |
| Scope was the current and previous sprint plus merges of the last 7 days | Every team ticket In Progress or In Review, in any project or none, plus every Backlog ticket; the script adjudicates one only when at least one PR referencing it is merged and none is open (`handler_closeout_scope prs`, whole clone history, open PRs from the PR watcher state), regardless of merge date or project | Triage 2026-10-16: about 141 started tickets (112 reopened by the 10-02 audit, 29 In Review since September) were never seen, and the closer flipped nothing on 61 runs (OMN-20655) |
| At most 6 tickets per run in pairs | 12 per run (cap 24) in chunks of 3 (cap 4) | 31 to 44 candidates were deferred every run (OMN-20655) |
| Three zero-flip runs over unchanged inputs paused every later fire | The pause skips only a fire with no candidate | The pause skipped runs while candidates waited behind the budget (OMN-20655) |
| The Accept agent ran `onex skill dod_verify --execution-audience local_done_gate` by prose and contracts that moved to product repositories came back unresolved | `handler_closeout_scope verify <id>` resolves `contracts/<id>.yaml` from the product repository's default branch, runs `node_dod_verify --contract-path` and prints the receipt the script reads; no contract is `could_not_run` with `contract unresolved` | Empty receipts and 'contract unresolved' on product-repository-governed tickets (OMN-20655) |
| A criterion waiting on a release cut or deploy was a plain rejection, re-read only when the rotation came round | The acceptor names the post-merge condition as `waiting_on`; the open comment records `waiting-on=<label>: <condition>`, and the script re-checks such a ticket first on every run | Post-merge done conditions were never re-checked (OMN-20655) |

What did not change: **what counts as evidence.** Done still needs a PASS from `dod_verify` with every
criterion bound to a verified check, and the flip still goes through the done-flip guard. The refusal
list only removes shapes; it never admits one that `dod_verify` would not.

## Invocation

```js
Workflow({ scriptPath: '<abs>/dod-closeout-sweep.js', args: { date: '2026-10-03', fireId: '20261003T124504Z-dod-closeout-sweep' } })
Workflow({ scriptPath: '<abs>/dod-closeout-sweep.js', args: { date: '2026-10-03', apply: false } })
```

| Arg | Default | Meaning |
| -- | -- | -- |
| `date` | required | `YYYY-MM-DD`; resolves the sprint |
| `fireId` | none | the driver's fire id. Present: the run key is `<date>T<HHMM>Z` from it. Absent: the run key is the date |
| `project` | live resolution | sprint project uuid override |
| `maxCandidates` | 12 (cap 24) | tickets examined this run |
| `chunkSize` | 3 (cap 4) | tickets per Bind/Accept agent pair; chunks run in parallel, so this sets the length of the slowest one |
| `apply` | true | false: bind, accept and verify, but no Linear write and no evidence PR |
| `force` | false | skip the idempotency precheck |
| `gitOpTimeoutS` / `checkTimeoutS` | 1500 / 600 | `DOD_VERIFY_GIT_OP_TIMEOUT_S` / `DOD_VERIFY_CHECK_TIMEOUT_S` |
| `fences` | [] | extra standing fences on top of the derived list |

## Delegation (OMN-17009)

All five phases attempt the ONEX text chain before writing analysis, review wording or prose.
They compute fact tables and exact checks deterministically, use `delegation_step.py text` with
`--task-type reasoning` for analysis/review wording and `--task-type document` for prose, and
fact-check and dispose each answer. The chain attempts the lab first, then GLM through Claude
Code. Review and gate calls stay with the lane; check commands, rerun output and script-provided
comments remain verbatim.

Each phase's schema requires `delegation: {delegated, runs, reason}`. An immediate runtime guard
refuses missing or malformed cells before downstream calls. A positive integer count requires
nonempty run ids and an empty reason. Zero requires no runs and `route-refused:<status>` or
`route-unavailable:<run id>`. Only Enumerate's `already-delivered` or `peer-owned` precheck may
return zero with `read-only-lane`; the actual run cannot use that exemption, including dry mode.
For `precheck=run`, Enumerate delegates the explanation of its verified scope and exclusions
with `--step enumerate-residuals --task-type reasoning` before its CLAIM instruction, including
when there are zero candidates. Its fact table holds deterministic counts, ids, sources and
exclusion overlaps; exact command output stays unchanged. The lane checks and disposes the
answer, then returns the receipt ids or a recorded route failure whose token has no spaces.
Neither `read-only-lane` nor `no-text-or-code` describes this required residual-prose step.

Checked cells are preserved in the workflow's `delegations` result and passed to Report as facts;
the Report cell is also retained. The reporter disposes answers before TERMINAL and includes the
receipt-backed `delegation_step.py cells` engine cells. These guards verify the record's shape;
receipt resolution and disposition remain the responsibility of the shared delegation and ledger
tools. Stub-agent tests prove phase ordering, without proving live daily-cycle acceptance evidence.

## Phases

1. **Enumerate** (sonnet). Precheck keyed on the run key: a ledger TERMINAL for `lane=dod-closeout-sweep`
   with `run=<run key>` means already delivered; an unanswered CLAIM younger than 110 minutes means a
   peer owns it. The sprint and the previous sprint are still resolved live, as labels only. The scope is
   every team ticket In Progress or In Review, in any project or none, plus every Backlog ticket. One
   command, `python3 -m ops_tooling_pkg.handlers.handler_closeout_scope prs <ids>`, prints per ticket
   the PRs that reference it: merged ones from squash-merge subjects over each canonical clone's whole
   default-branch history, open ones from the PR watcher state (a stale or unread state is an error row,
   never an empty open set). The agent passes its stdout through unchanged as `pr_state`; the script
   keeps a ticket only when at least one referencing PR is merged and none is open, and reports the rest
   as `waiting` with the reason. A candidate also has no children and is not fenced. Each
   candidate carries the time of the newest comment this workflow left on it. The script selects the
   least recently examined first and defers the rest to later runs. Each candidate's text state comes
   from one command, `python3 -m ops_tooling_pkg.handlers.handler_closeout_text_state <ids>`, which reads
   the description and comments from the Linear API (`LINEAR_API_KEY`) and prints, per ticket, the hash
   of the description now, the hash recorded by the newest closer comment, and that comment's time. The
   agent passes the stdout through unchanged and the script parses it. A ticket whose two hashes match is
   held: not selected, reported as `held_for_amendment`, until its description changes. A failed read
   leaves the hash empty, and an empty hash is never held.
2. **Bind** (opus, one per chunk). Reads each ticket's criteria and authors one check per criterion:
   a pytest node id on merged `dev` with a bare registry repo name (for example `omnimarket`;
   `OmniNode-ai/omnimarket` is also accepted and normalised to `omnimarket` before acceptance),
   a command against a clean `origin/dev` checkout, or a read-only lab
   readback, each with the observation that holds only when the criterion is true. A criterion whose
   only proof is a write, or a system the lane cannot reach, gets no check and says so. A criterion whose
   TEXT is the obstacle (it offers options, contradicts a deliberate design, names no observable) gets no
   check and an `amendment`; a ticket with no readable criteria gets a `criteria_amendment`. It writes
   nothing.
3. **Script vetting.** `refusalOf` refuses a check made only of source or PR reads: `symbol-grep-only`,
   `pr-exists-only`, `inspection-only`, plus missing fields, a selector that is not a test id, a ref that
   is not merged `dev`, and a mutating readback. The binder's lane identity is stamped by the script.
4. **Accept** (opus, a different agent). Re-runs each surviving check at its ref, tries to falsify it
   (a test is also run at the parent of the implementing merge), and accepts or rejects it with the
   re-run output, plus an `amendment` when it rejects a criterion that no code change could make
   provable as written. It also re-runs every binding already on `dev` that no second lane accepted (the set
   `dod_verify` reports as `acceptance_self_accepted_bindings`) and accepts or rejects it the same way;
   an accepted one is landed as a re-acceptance record with the original `proposed_by`, never by the
   lane that proposed it. In apply mode it lands one evidence-only OCC PR per ticket carrying only the accepted
   bindings, each with `proposed_by` (the binder) and `accepted_by` (itself), then runs the verifier
   step, `python3 -m ops_tooling_pkg.handlers.handler_closeout_scope verify <id> --execution-audience
   local_done_gate`, for every ticket. That command, not the agent, resolves the contract from the
   product repository whose default branch carries `contracts/<id>.yaml` and runs `node_dod_verify --contract-path` with it. The agent returns its complete JSON stdout as `dod_verify.receipt_json` with
   `outcome: ran`, without flattening or inferring a per-criterion map. A ticket the run clock
   cut off before its verifier call returns `outcome: not_reached` and a verifier that was
   started but produced no JSON returns `outcome: could_not_run` with a one-line `detail`; the
   script reports those as `VERIFY_NOT_REACHED` and `VERIFY_COULD_NOT_RUN`, and keeps
   `VERIFY_RECEIPT_UNREADABLE` for an empty or unparseable receipt that no outcome explains. It makes no Linear write. The PR leaves out
   a binding whose label and `criterion_hash` are already accepted on `dev` by a lane other than its
   proposer, and opens nothing when
   none is new. Every item it adds carries its PASS receipt in the same PR, filled by
   `check_receipt_hardening.py --capture-probe`, because the change-control eligibility gate refuses
   an item without one. Before 2026-10-04 the lane added items without receipts, and 11 of 13 of its
   PRs were red until a landing fix worker captured them.
5. **Decide** (script, `readDodVerify`, `acVerdicts`, `decideTicket`). The script reads the receipt's
   declared result arm: `result` for `ModelDodVerifyState`, `result.terminal_payload` for
   `ModelReceiptRuntimeSummary`. An unknown arm, absent checks, or an unreadable receipt holds.
   Coverage comes from native `checks[].binds_ac`, keyed by `evidence_id`, excluding
   `draft_binds_ac`; only `verified` discharges a criterion. `ac_bindings` is an OCC authoring
   record, not the verifier's per-check field. Before this reader was wired the acceptor was told
   to infer `ac_verdicts` from `ac_bindings`, so native bindings could disappear at that boundary.
   An inferred map is never used. Done only when every criterion's check was not refused, was
   accepted by a lane other than its author, and was verified by `dod_verify`, and `dod_verify` as a
   whole verified with no error code. Otherwise open, with every unmet criterion named, and
   `needs_amendment` set when any unmet criterion carries an amendment. A refused binding (the
   binder's fault) and a failing check (the code's) never carry one.
6. **Apply** (sonnet, apply mode). Applies only to issues with no children: it re-reads children
   before every mutation and returns `fenced-midrun` without writing when any have appeared.
   Ticks each criterion's box and flips the Done tickets with `save_issue`, so the done-flip guard
   decides both; a refusal is recorded verbatim and the ticket gets the open comment instead. Open tickets
   get the script-composed comment, unless the newest closer comment already carries the same
   `signature=` line. It never changes an open ticket's state.
7. **Report** (sonnet). A docs_repo report at
   `beta/tracking/<date>-dod-closeout-sweep-<HHMM>Z.md` only when the run changed something on a ticket;
   always one ledger TERMINAL row carrying `run=<run key>` and the counts.
   Report writes the script's summary JSON unchanged to a minted scratch file and runs
   `python3 -m ops_tooling_pkg.handlers.handler_closeout_completion --ledger <ledger>
   --current <summary.json> --stamp <live UTC stamp> --rows-file <scratch.txt> --report <path>`
   with `PYTHONPATH` naming this package's `src`. It submits the generated payload unchanged
   through the existing guarded ledger append. On the third consecutive completed run with
   zero flips, and every subsequent zero, the payload contains a FRICTION row naming
   `zero_flip_streak` and `top_deferral_reason`, followed by a TERMINAL whose `friction=`
   cites that row's timestamp and lane; cost uses this run's declared ~1.5 lane-hour budget.
   A positive flip resets the streak. Archive rolls and
   the live ledger are one history; mirrored receipts and force replays count once per run
   key. Short circuits and other lanes do not count. Empty scopes still complete and count.
   The top reason is the most frequent unmet-criterion reason (ties lexical), using binding
   refusal classes when present; only when there are no unmet criteria does it use refused
   bindings, flip refusals, held amendments, candidate budget, or an empty-scope reason.
   Missing/malformed history refuses completion; Report must never replace the refusal
   with `friction=none`. The workflow fails when Report cannot confirm the completion append.
   The completion contract runs in `dod-closeout-sweep-scope.yml`
   and the required whole-tree `ci`, with a local pre-commit mirror.

A well-formed empty scope logs `VERIFIED NOTHING: zero candidates`, returns
`verified_nothing: true`, and changes no ticket or report.

## The run clock

The driver kills a run at its ceiling (6300s) and a killed run writes nothing: no Apply, no
Report, no TERMINAL row. From 2026-10-03 to 2026-10-04, 8 of 15 scheduled runs were killed that
way. The tail was a single Accept agent on a chunk of three tickets: its `dod_verify` runs are
serial (10 to 25 minutes each) and each evidence PR waits on a corpus pre-commit (about 10 minutes),
and the old "45 minutes for the chunk" budget was prose an agent cannot clock (it ran 80).

Two changes, both pinned in `tests/test_dod_closeout_sweep.py`:

- `chunkSize` defaults to 3 and `maxCandidates` to 12 (OMN-20655), so twelve candidates are four
  parallel chunks and the slowest agent carries three tickets.
- The script derives absolute instants from the fire id alone (`STOP_AFTER_S`), one pair per stage.
  Bind starts nothing new at fire + 1800s and returns what it holds at fire + 2400s; Accept starts
  nothing new at fire + 3500s and returns at fire + 4300s. A ticket not reached comes back `not_run`,
  which `decideTicket` leaves open, and the least recently examined rule hands it to the next run.
  4300s leaves 2000s of the ceiling for Apply and Report (measured 350 to 1950s). A manual run has
  no fire id, so it has no clock.

The stages used to share one pair. On 2026-10-07T2045Z Bind ran past fire + 3500s, its acceptor
started at 21:46:44Z with no time left, and every criterion came back `run clock: not reached` as an
acceptor rejection (12 of the closer's TERMINAL rows from 2026-10-07 to 2026-10-09 carry that top
reason). Bind's own earlier pair leaves Accept at least 1100s before its no-new-work instant. A
criterion the clock cut off is reported as `not adjudicated: the run clock ran out before the binder
(or acceptor) reached it`, never as a rejection or an amendment.

Bind returns the UTC time it finished as `returned_at_utc`. When that is at or after the Accept
no-new-work instant, no Accept agent starts: each ticket of the chunk is returned not adjudicated,
its verifier is reported `VERIFY_NOT_REACHED`, and the run summary carries one `accept_budget`
object (`phase`, `budget`, `instant`, and each skipped chunk with the time Bind returned). A time
Bind did not give, or a manual run, starts Accept as before.

A throw after Enumerate has appended the run's CLAIM runs one `closeout-terminalize` agent before
the workflow exits. It reads the ledger, and when the run's CLAIM has no later TERMINAL for the
lane it runs `handler_closeout_completion --failure-terminal`, which generates a FRICTION row and a
`TERMINAL ... failed_run=<run> ... outcome=failed` row carrying the thrown reason, and submits both
in one guarded append. The TERMINAL names the run in `failed_run=`, never `run=`, so the run key is
not read as delivered and the zero-flip streak does not count it. A run whose completion was
recorded does not terminalize again.

## Self-pause

From the zero-flip streak `self_pause.zero_flip_streak_threshold` declared in
`src/ops_tooling_pkg/handlers/dod_closeout_sweep/dod-closeout-sweep.contract.json`, a fire whose
inputs are unchanged since the last completed run, and that has no candidate, spends nothing past
Enumerate. A fire with a candidate always runs (OMN-20655): the pause must never skip work that is
waiting behind the per-run budget. The inputs are the
candidate ticket set, the `node_dod_verify` tree on omnimarket `origin/dev` and this script's own
bytes (the acceptor). Enumerate runs `handler_closeout_completion --pause-check` with them; the command
reads the closer's TERMINAL rows, compares the fingerprint the last one recorded in `inputs=`, and
prints its decision. On `pause` Enumerate appends the command's one STATUS row
(`state=skipped-zero-flip-pause`, the streak, the threshold, `inputs=`, `since=<last run>`) and writes
no CLAIM; the script returns `short_circuited: paused`. The script refuses a pause the command did not
decide and a decided pause the agent ran past (`PAUSE_MISMATCH`). Every completed run records its
fingerprint on its TERMINAL, so any changed input resumes the closer on the next fire. An input that
was not read yields no fingerprint, and an unread fingerprint never pauses.

A pause replaces the hand pause: the launchd job keeps firing every two hours and each paused fire
costs one Enumerate agent and one STATUS row instead of the declared 1.5 lane-hours.

## A verifier that bound no check

When `dod_verify` runs but binds no check to any criterion, each accepted criterion names the
verifier's own refusal once, `dod_verify bound no check to any criterion (<check id>: <code>)`,
rather than `no verdict for this criterion`. On 2026-10-12 every product-repository-governed ticket
tried that way returned one failed `contract` check (`REPO_CONTRACT_UNRESOLVED`: the verifier's read
of a merged PR's head and merge time was refused by the gh PR-state read guard) with `binds_ac: []`.

## The open comment

```text
dod-closeout-sweep run 2026-10-03T1245Z: OMN-123 stays open. These acceptance criteria are not proven by a check another lane accepted and dod_verify verified:
- AC1: binding refused (symbol-grep-only): a check that only reads source or PR state does not prove the criterion
- AC2: binding rejected by the acceptor: passes at the parent commit too
The closer re-examines this ticket on a later run. It moves to Done when every criterion has an accepted, verified check.
signature=AC1:binding refused,AC2:binding rejected by the acceptor
```

When a criterion needs a text amendment the comment names it and records the hash it was made against:

```text
- AC7: binding rejected by the acceptor: false as written
Amendment needed. These criteria cannot be proven as written, so no run can close the ticket until its text changes:
- AC7: key the ruling on the ticket, not the actor
The closer skips this ticket until its description changes, then examines it again.
amendment-text-sha=0123456789abcdef
signature=AC7:binding rejected by the acceptor text=0123456789abcdef
```

When a criterion waits on a post-merge condition the comment records it, and the text-state command
reads it back as `waiting_on`, which puts the ticket first on every later run until the condition holds:

```text
- AC2: waiting on release cut of omnimarket carrying the merge
waiting-on=AC2: release cut of omnimarket carrying the merge
The closer re-checks this ticket first on every run until the condition holds.
```

It contains no question. The `signature=` line is what keeps a two-hour cadence from re-posting the same
comment; for an amendment it carries the text hash, so the comment that first records a hold is posted
even when an older comment named the same gaps. `tests/test_dod_closeout_sweep.py` runs the whole script
under node with stub agents over three fires (`test_an_unchanged_rejected_ticket_is_adjudicated_once_and_commented_once`):
the second fire does not bind, accept or comment on the held ticket, and the third, after an edit, does.

## Schedule

`ai.omninode.dod-closeout-sweep`, rendered by `launchd/morning-workflows/morning_trigger_install.sh`
from `INTERVAL_AGENTS` with `launchd/ai.omninode.interval-workflow.plist.tmpl`: Hours 0, 2, ... 22 at
:45 local, ceiling 6300s. Reload that one label with `--only dod-closeout-sweep`. The driver resolves
this script from the installed package (`~/.omninode/morning-workflows/lib`), so the installer must run
after this file changes.

Headless authentication is the driver's: a token file written once by `scripts/lab-host-login` when it
exists, otherwise the shared interactive login, recorded as `auth_source` on the fired receipt. Every
"Not logged in" failure on record landed seconds after an interactive `/logout` (OMN-17427).
