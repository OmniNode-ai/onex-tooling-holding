---
name: sprint-roll
description: Roll the current sprint into the next and rebalance every sprint after it to one measured cap. Moves what did not finish, pools every open ticket across the window and places it forward by dependency and criterion coverage, sends the remainder to Backlog, applies the beta-critical rule to the next two sprints, and maps every ticket no carrier list names to a release criterion from its own Gate line. Dry run by default; an apply journals each write before sending it and the manifest reverses the whole roll. Drafts the sprint goal and deliverables from the incoming carriers for the operator to approve. Use for "roll the sprint", "what moves to next sprint", "can we fit this", and as the scheduled Monday pre-standup job.
prosthetic: true
replaces_when: "Linear reports per-sprint capacity against measured throughput and refuses an over-committed sprint at planning time, for two consecutive sprint cuts."
restored_from: "New 2026-10-02. The roll was done by hand each Monday, which meant it was not done: the 2026-10-05 sprint already held 18 open tickets against the 18 the prior sprint closed, before any carry-over at all, and nobody had measured that."
ticket: OMN-20395
argument-hint: "[--as-of YYYY-MM-DD] [--cap N] [--by tickets|points] [--apply] [--undo MANIFEST]"
---

# Sprint roll (prosthetic)

A sprint boundary used to be a hand pass: open Linear, drag what did not finish into next
week, and start. Nothing measured whether next week could hold it, so an already-full
sprint absorbed a week of carry-over and the overcommit compounded unseen.

This skill does the arithmetic and proposes the judgement. It never decides scope.

## The work is two nodes, not a script here

The capability lives in `omnibase_core`, under the operator ruling of 2026-10-01: new
capability is a contract + node + handler, and the shrink-only canonical-file-shape
baseline that grandfathers the older skill scripts does not grow. A script in this
directory is refused by the gate, and that refusal is correct — do not add one.

- `node_sprint_roll_compute` (OMN-20396) — the placement arithmetic. Pure: it takes the
  sprint window, the run date and the criterion carrier lists, and returns a plan.
- `node_sprint_roll_apply_effect` (OMN-20397) — every Linear read and write, the write
  journal and the undo replay.

The reads the compute node needs are owned elsewhere and are passed in, never
reimplemented: the sprint window and the carrier lists come from `infra_repo`'s
`tools/beta_board` (`sprint_board_data.load` and `beta_board_data.CRITERIA`). A second
copy of either disagrees with the board the week one of them drifts.

## The order, every Monday and every manual run

The operator's sequence, 2026-10-05. Each step carries the constraint that bit when it
was missing; none of these are preferences.

1. **Carry the in-flight work over.** Everything To do, In Progress or In Review in the
   from-sprint moves to the to-sprint. **Done, Canceled and Duplicate stay where they
   are** — moving a closed ticket forward destroys the from-sprint's burn, and a closure
   that predates a window must never count as that window's burn.

2. **Judge the from-sprint's Backlog one ticket at a time.** Does it belong in the
   to-sprint, on its carrier, its parent, its related work? If yes: give it the sprint's
   end date, a best-guess estimate, and move it. If no, and it carries no date: out of
   every sprint, no estimate, into Backlog.

3. **Fill the gaps in what the to-sprint already held.** Any ticket there without a date
   or an estimate gets both.

4. **Balance it.** Spread by expertise, pillar, ticket count, points and who is actually
   free. Two hard limits: **a walker of a pillar may not build that pillar** (below), and
   **nothing already To do, In Progress or In Review is reassigned.**
   - 4a. Move carriers on the board's overview page when they need moving. Rare.
   - 4b. A genuinely new carrier that needs a new criterion: create both and bind them to
     the milestone, usually M4. Read **The carrier mapping comes first** before doing it —
     this is a `beta_board_data.py` pull request and a gated Linear create, not two clicks.

5. **Every ticket in the to-sprint ends up with a date.** Anything still missing one takes
   the sprint's end date.

6. **Tickets that appeared in the sprint from automation get the same treatment.** In
   flight stays; Backlog goes through step 2. They are not exempt for having arrived
   without a person.

7. **Rightsize the sprint after the to-sprint** the same way, so the next week is legible
   too — reassigning for balance, and again never touching To do, In Progress or In Review.

8. **If there are walks, the test matrix is always present**, in the from-sprint's format.
   - 8a. **Every ticket in the to-sprint is due on the sprint's end date**, including ones
     carried over. The one exception: a date already inside the window is deliberate and
     is kept — OMN-20387 came in due 10-07 of a 10-05 to 10-11 window and keeping it was
     right. Overwrite only a date outside the window.

9. **Dry run to a mock sprint board for the operator to read first.** **NOT BUILT YET**
   (operator, 2026-10-05: "<removed>"). The board renders from `dev`
   on a 15-minute cron to one live URL, so there is no preview target today. Until one
   exists, the dry run's plan text and `roll-plan.json` are the artefact, and nothing is
   applied without the operator reading them.

## A sprint move is three fields

`projectId`, `projectMilestoneId` and `dueDate`, in the same mutation.

Linear **clears the project milestone** when the project changes, and the Sprint tab
groups by the sprint's declared milestone. A ticket moved with the project alone is in the
right sprint and invisible on the board: that is how the seven walk tickets disappeared
from the tab on 2026-10-05. The due date does the opposite — it is kept, so the ticket
arrives carrying the previous sprint's date and reads as overdue on day one. Eleven
tickets in one sprint needed repair for those two faults.

Key the date to the destination project's own `targetDate` rather than a typed date, so it
follows the sprint if the window shifts. After any bulk move, assert `noMs == 0` on the
sprint and that no open ticket has `dueDate < project.startDate`. Both faults are silent.

## Walks are mandatory, and a walker may not build what they walk

**Mandatory.** A walk is the only evidence that somebody who did not build a thing
exercised it from a customer's position. A cap may not defer one: on 2026-10-05 the first
run put all seven in Backlog. They are seated before the cap is consulted, and their size
still counts, so the overflow falls on ordinary work rather than on proof.

**Eligibility bounds the rebalance in step 4.** The walker of a pillar may not be assigned
build work in that pillar, or the receipt it produces is the runner verifying himself —
`model_dod_receipt.py` downgrades exactly that from PASS to ADVISORY. On the 2026-10-05
sprint this one rule explained the whole spread: the walker who builds nothing could take
no build work at all, and two of the three others were each confined to a single pillar.
The role-to-person mapping lives on the walk tickets, never in a plan.

**Done walks still show.** A walk proven in an earlier window stays on the matrix through
`walks_done` in `sprint_copy.py`, flagged, and is excluded from the matrix count and the
walk burndown. Hiding it reads as if the case was never exercised; counting it credits
this week with ticks nobody made.

## Only M4 sprints receive work

The M4.5 bucket is a parked fast-follow list, not a week anybody is planning, and work
that is not M4 goes to Backlog rather than into an M4 sprint. Left in the window it is
rebalanced like any target: on 2026-10-05 it went from 45 open to 20, with 20 moved in and
25 pushed out of a sprint nobody had touched. Drop non-M4 sprints from the window, and say
which ones were dropped rather than doing it silently. Their own tickets stay put, which
is what parked means.

## A parent is never estimated

A parent's children hold the points; estimating both double-counts the sprint. Four
tickets in the 2026-10-05 window carried ten children each. Step 3 fills missing
estimates — it skips parents and reports them, so a blank parent reads as a decision
rather than an omission.

## Running it

`LINEAR_API_KEY` must be in the environment and an `infra_repo` checkout reachable
(`INFRA_REPO`). Compose the request from the board's reads, hand it to the compute
node, then hand the plan to the effect node. The scheduled job in `infra_repo`
(`sprint-roll.yml`) does exactly this and is the reference for the call sequence.

**IT EVALUATES AS THE DAY THE SPRINT CLOSED, WHICH IS NOT TODAY.** The sprint drained is
the one CONTAINING `as_of`, so `as_of` defaults to **yesterday**, never to today. On a
Monday the sprint containing today is the one starting that morning: with a `today()`
default the scheduled run proposed draining the sprint just planned and pushing it into
the two after it. Measured on the merged node — `as_of=2026-10-04` drains 09-28..10-04,
`as_of=2026-10-05` drains 10-05..10-11. The sprint closes Sunday, Monday reads that
balance, so Monday must evaluate as Sunday. The same default keeps a manual mid-week run
correct: it drains the sprint still open rather than one already drained. `--as-of`
forces any reading.

Resolve the source from the PROJECT list first: the board's sprint read returns only the
current and future sprints, so a finished sprint is invisible to it. The compute node's
`resolve_source` and the effect node's `resolve_source_start` must agree — they drifted
once, and a run then loaded the window from one sprint while draining another, measuring
capacity as `0 closed in 7 of 7 days` and capping at 1.

## What it decides, and what it refuses to decide

**Measured, no judgement.** Which tickets are unfinished; the cap; dependency and
coverage order; which upcoming tickets lack the `beta-critical` label; which labelled
tickets no carrier list names.

**Proposed, needs approval.** The sprint goal and the deliverables, drafted once placement
is settled and never before: they are a read of the tickets the sprint actually ended up
holding (operator, 2026-10-16). Read all of them and say what the majority of them add up
to -- one sentence per pillar covering that pillar's tickets, then one goal sentence over
the whole window, written so a person who did not build it could verify it. The pillar
grouping is the shape already typed in `sprint_copy.py`: Delegation, Dashboard, Onboarding.

Majority means what the bulk of the tickets ACHIEVE, not whichever bucket holds the most
rows, and the wording comes from what a customer or developer can then do rather than from
ticket titles: counting rows hands the goal to the biggest pile, and titles describe the
means, so either one produces a goal about the team's own laptops when the window is about
a customer's machine. Check the draft against the incoming carriers' criteria before
handing it over -- a goal no carrier serves is the tell that the majority read drifted.

Then hand it over for approval and write the approved text into
`tools/beta_board/sprint_copy.py`, keyed by the sprint's Linear project id. A sprint with
no entry renders nothing extra, so an unapproved goal is simply absent rather than a guess.

**Never decided here.** Whether the date moves or scope comes out. When the plan is over
cap after the rebalance, report the number and stop; that is the operator's call, and it
is why this runs before standup rather than after.

## Why tickets and not points

Points were the default for one morning, on the belief that every carrier carries an
estimate. That is true of carriers and false of the sprint. Closed OMN tickets by week,
read 2026-10-05, with the estimated share:

| week of | closed | estimated |
| -- | -- | -- |
| 08-24 | 402 | 2 |
| 08-31 | 237 | 0 |
| 09-07 | 193 | 1 |
| 09-14 | 195 | 2 |
| 09-21 | 190 | 17 |
| 09-28 | 80 | 21 |

So a points cap measures the velocity of the estimated MINORITY. It read 39 a week, cut
the 10-05 sprint to 10 tickets, and pushed 35 points of real work into the next sprint
before the operator caught it. Unestimated work does not become free because nobody sized
it, and a median imputation cannot rescue a 26-percent sample.

A ticket count prices a 7-point build and a 1-point fix alike. That error is known and
bounded. A points cap over this data is unbounded, and it evicts. Points mode stays for a
sprint whose work really is estimated, and each ticket's own estimate still prints,
because it is worth seeing even when it is not what the cap is made of.

**The operator's number beats the measurement.** One sprint's closures are the weakest
input to the plan. When `--cap` is given, the per-owner limit is NOT applied on top of it:
an operator stating the team's capacity is not asking for their figure to be re-divided
per person and used to evict.

## The carrier mapping comes first

The board's reconciliation gate FAILs repo-wide when an *open* `beta-critical` ticket maps
to no criterion, and `check_board_reconciliation.py` forbids an allowlist: map it, or drop
the label. So the mapping lands with or before the labelling — a label-only pass reddens
every open pull request in `infra_repo`.

The compute node reads, in order: the ticket's own `Gate:` line naming a criterion, which
is never overridden; then overlap with the criterion's wording at 8 or more terms; then
nothing, reporting the near miss. The bar was measured on the 17 orphans of the 2026-10-05
roll, where 4 to 7 terms was wrong four times in six. Some tickets genuinely are not
beta-critical — repo CI hygiene is the recurring class — and for those the honest output
is to recommend dropping the label rather than inventing a carrier.

## Writing, and undoing

An apply moves projects and states and adds labels. Each write is journalled before it is
sent, so an interrupted run still leaves a reversible record, and the manifest replays
prior values newest-first. Project and label moves reverse cleanly. A Backlog state move
is the one change a person notices, so read the Backlog list in the dry run first.

## Scheduled run

`sprint-roll.yml` in `infra_repo` runs at **13:00 UTC Monday — 08:00 Chicago** on the
self-hosted fleet, an hour before the 09:00 standup (operator, 2026-10-05). The cron is
fixed in UTC, so it fires at 07:00 local once Chicago returns to CST on 2026-11-01 and the
line moves to `0 14 * * 1` then. The margin is deliberate: GitHub's
scheduler commonly runs 5 to 15 minutes late under load, as `publish-beta-board.yml`
documents about itself. The beta board republishes on its own 15-minute cadence, so the
rolled sprint appears without this job touching it.

The scheduled run posts the dry run and applies only the moves. The goal, the deliverables
and any ruling on an unmappable ticket wait for approval, because each is a sentence
somebody has to stand behind at standup.

## Known friction

- The first version measured capacity in points and counted an unestimated ticket as
  zero, so 21 unestimated tickets fitted a sprint for free and the plan read as feasible.
- The first version also injected into the next sprint and left later sprints fixed, which
  parks the roll behind whatever a later sprint already held: 10-12 sat at 20 of a 21 cap,
  so one ticket could enter it while 21 went to the empty 10-19. Pooling the window fixed it.
- It was first built as a script in this directory and refused by the canonical-file-shape
  gate. The refusal was right; the capability moved to two nodes. → OMN-20396, OMN-20397
- The scheduled job defaulted `as_of` to `today()`, so its first Monday would have
  proposed draining the sprint that had just started. It never ran that far: the same run
  died at `ImportError: cannot import name 'LinearTransportError'` after OMN-20450 split
  the module and renamed the class, which is why the job had never once completed.
  → OMN-20395, infra_repo#1800
- A bulk project move dropped every ticket's milestone and left its due date on the
  previous sprint, so seven walks vanished from the Sprint tab and eleven tickets read as
  overdue on day one. → **A sprint move is three fields**
- The first cap in points evicted 35 points of real work on a 26-percent estimate sample.
  → **Why tickets and not points**
- The walk section vanished entirely when the sprint rolled over, because the copy was
  keyed only to the previous sprint's project id. The matrix now carries forward and marks
  that it is inherited. → infra_repo#1816
- Reading the plan's text after the `BACKLOG` line counts the criterion PROPOSALS, not the
  backlog: walks appear there because they map to no criterion, which read as all seven
  being deferred when none were. Read `roll-plan.json`'s `backlog`, never the log tail.
