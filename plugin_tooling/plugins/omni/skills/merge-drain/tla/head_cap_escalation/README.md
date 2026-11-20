# The landing controller never leaves a PR gated with no next action: model and design verdict (OMN-19998)

`HeadCapEscalation.tla` is the model-before-build step for the head-cap escalation in
`scripts/landing_controller.py` (`escalation_plan`, `escalation_actions`) and `scripts/landing_facts.py`
(`escalation_next`, `needs_person_gate`, `armed_since_next`). It was written and checked by TLC before the code.

## What was missing

Operator RULING 2026-10-14T05:17:57Z: "fix the controller so that this [expletive] just doesn't sit there and nothing
happens." Controller ticks 2391 to 2393 (2026-10-14 05:02Z to 05:15Z) each held 23 PRs at
`worker_gated=head_cap` and one at `no_result_file`, with 0 leases and free pool slots. A head that has had
`MAX_DISPATCHES_PER_HEAD` (3) workers, whose last worker left no result, or whose worker reported nothing to fix,
is gated from any further worker until its head moves, and the decision node skips a gated PR outright. Nothing
else acted on those PRs. A green, armed PR that the merge queue never merged had no actor either.

## Design

A PR is a candidate when its worker gate is spent (`head_cap`, `no_result_file`, `no_attempt:<kind>`), or when it is
open, unsuspended, green and armed at one head for an hour by the controller's own clock (sidecar `armed_since`).
Each tick a candidate takes the next stage it has not taken at its head, one stage a tick, each at most once:

| Stage | What the controller does |
| -- | -- |
| `superseded` | an empty net diff, or `git merge-tree` of the head into `origin/<base>` giving the base's own tree: close with a close claim and a comment; any other answer goes on |
| `conflict` | only for a conflicting merge state: one conflict worker on `claude_opus` (merge the base, resolve, push) |
| `triage` | one triage worker on `claude_opus`; its brief lists the results this head's workers left; it returns `fix_submitted`, `close_superseded` or `external_blocker` with `person` and `reason` |
| `needs_person` | the triage worker's person and reason, posted once on the PR; the worker gate reads `needs_person:<who>` until the head changes |

A conflict or triage worker is a lease the controller writes into the node's own write-ahead state, with an id from
the node's `next_lease_id`, inside the node's worker bounds (`max_workers`, `max_workers_per_repo`, the load pause,
the engine). From the next tick the node owns it as its own dispatch: probe, deadline, kill sequence, result record
and release. A candidate those bounds leave out is `waiting`, not idle. The memory (sidecar `head_escalation`) is
keyed by PR and head; a new head or a closed PR drops it.

Every tick line carries `idle_gated=<n>[<prs>]`: candidates this tick left with no next action (no lease, no node
action, no stage, no hold, not waiting). Any idle PR makes the tick DEGRADED, and queue-status turns a PR listed on
two ticks in a row into a DEGRADED reason that names it.

## Model

PRs with heads `1..MaxHead`, CI red and merge state conflicting chosen per head, the node's per-head cap `Cap`.
Actions: `NodeDispatch` (one lease per PR, up to the cap), `Merge` (a green, unconflicted, unstalled PR),
`WorkerEnds` (a fix and a new head, a triage verdict of superseded and a close, or nothing), `Push` (a person moves
the head; the hold lifts with it), `Stall` (a green armed head stops merging), and `Tick(p)`, the controller's
escalation step followed by the idle count. `idle[p]` counts the ticks in a row at which `p` is open, not held for a
person, and nothing can act on it.

| Property | Meaning |
| -- | -- |
| `NoIdle` | no open, unheld PR goes more than `K` ticks with no next action |
| `OneLease` | an escalation worker never runs beside another lease of its PR |
| `StageOnce`, `PostOnce` | each stage at most once per head; the needs-person comment once per head |
| `Ordered` | superseded first; triage before a person is named |
| `HeldNamed` | a hold is always the needs-person stage, posted |
| `Resolves` (liveness) | every spent, unheld PR ends closed, held for a named person, or with a next action |

## TLC verdict (h908, TLC2 2026.09.25 rev 8f4bc8b, 2026-10-14)

| Config | Expected | Result |
| -- | -- | -- |
| `V_safety` (2 PRs, cap 2) | Safety holds | no error, 30,276 distinct states |
| `V_three` (3 PRs, cap 3) | Safety holds | no error, 9,800,344 distinct states |
| `L_resolves` | Safety and `Resolves` hold under weak fairness | no error, 174 distinct states |
| `M_no_escalation` (the controller before this change) | must violate `NoIdle` | violated |
| `M_no_needs_person` (no person named after triage) | must violate `NoIdle` | violated |
| `M_no_stall_escalate` (armed stall not escalated) | must violate `NoIdle` | violated |
| `M_no_once` (a stage not recorded) | must violate `StageOnce` | violated |
| `M_no_lease_guard` (escalate beside a live lease) | must violate `OneLease` | violated |
| `M_live_no_needs_person` (positive control for `Resolves`) | must violate `Resolves` | violated |

Run: `java -cp tla2tools.jar tlc2.TLC -config cfg/<name>.cfg -workers 4 -deadlock HeadCapEscalation.tla` on a lab host
(Operating Rule 21).

## Design-review verdict

**GO.** `M_no_escalation` reproduces tick 2392: a spent head with no lease has no action and `NoIdle` fails. Two
guards are mandatory and the code carries both: a stage is recorded in the memory written ahead with the state before
it is performed (`M_no_once`: without it the superseded check and the comment repeat every tick), and an escalation
worker is never started for a PR that holds a lease (`M_no_lease_guard`). The needs-person stage is what closes the
chain (`M_no_needs_person`, `M_live_no_needs_person`): a triage that fails without naming anyone would leave the PR
idle again. Raising the per-head cap would not: the model's cap is a parameter and every value leaves the same
spent state behind.
