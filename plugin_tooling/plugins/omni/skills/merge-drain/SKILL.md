---
name: merge-drain
description: The red-PR fixer's procedure. The landing controller's cause worker follows sections 1 to 4 to find the one source of a red that several PRs in one repository share. It takes a live inventory, maps every PR to exactly one owner, classifies the red (the base head, the gate itself, a sibling pin, change-control companion contention, or not shared), and fixes it once at the source with drafts delegated to Codex, the lab and GLM. By hand it is also a merge sweep that maps every open PR, classifies drafts and reds, re-validates holds older than 12h and reports per-repo counts. Use for "why is repo X at 0/8", "several PRs fail the same check", "merge sweep", and after a merge-order hold lifts. The session drain that used to run this loop is deleted (OMN-20416).
prosthetic: true
replaces_when: "`onex skill merge_sweep` (node_pr_lifecycle_orchestrator) emits a per-PR classification (draft/DECLINED, companion open, change-control cascade, real red, held) and executes the fix and merge path itself, and the merge-sweep named workflow calls it rather than doing the sweep by hand, on two consecutive drains. On 2026-09-22 the node's --dry-run --inventory-only returns a correct org-wide open-PR list (60 against a live gh count of 58, taken minutes apart), but it carries no per-PR classification, and every drain lane that day bypassed the node."
restored_from: "omniclaude c77af59cd plugins/onex/skills/merge_sweep/SKILL.md"
ticket: OMN-19210
---

# Merge drain (prosthetic): the red-PR fixer's procedure

**What this is now (RULING 2026-10-03T20:46:24Z lane=orchestrator-de99, OMN-20416).** merge-drain is the
procedure of the landing controller's **cause worker**: a headless `claude -p` worker, one lease per shared red
cause, started by `scripts/landing_worker_run.py` in a DETACHED checkout of the source repository's base branch
(`worktrees/OMN-19998-landing/`, on a lab host or here). Its brief (`brief_class=shared_cause`) names the
cause key, every (check, signature, example annotation), every member PR with its head, and whether the base head
fails the same check, and cites **sections 1 to 4 below** as its procedure: how to read the repository (1), who
owns every PR (2), how to classify a red (3) and how to delegate the drafts (4, 4a, 4b). The session drain that used
to loop over these sections, `workflows/repo_drains.js`, is deleted: a Claude session is no longer on the path from
a red to a lane. By hand the sections are still a merge sweep.

The cause worker runs this order (plan 2.5 of `beta/plans/2026-10-03-red-pr-fixer-plan.md`) and `render_cause_prompt`
in `landing_worker_run.py` is its fixed text:

1. Read one member's failing job log and the base head's run of the same check (section 1's map says which PRs
   share the check).
2. Classify the source, in this order, stopping at the first that holds (section 3's classes): **the base head** is
   red; **the gate** itself produces the message for PRs that did nothing wrong; a **sibling pin** moved; **change-control
   companion contention**, where only the minimal unblock is allowed because change-control is being retired (heal
   or consolidate, as OMN-20411 and OMN-20412 did by hand); or **not shared**.
3. Fix once at the source, in one PR in the source repository, titled with the ticket the members share, else
   OMN-20413. The controller lands it like any PR, ahead of others.
4. Never push to a member branch whose owner is not the controller (section 2's owner map decides); list the
   members that need their own change in the fix PR's body.
5. Draft code through `delegation_step.py code` and text through `landing_text.py` (sections 4a and 4b).

It ends with exactly one result, which `landing_workers.read_result` grades: `cause_fix_submitted {fix_ref, fix_head}`
(`fix_ref` as `<repo>#<n>`, `fix_head` 40 hex), `cause_not_shared {reason}` (a non-empty reason) or
`external_blocker {blocker_kind, blocker_ref}`. Anything else is `unparseable`. Each worker run also writes
`usage.json` beside `result.json`: the engine runs with `--output-format json`, and the file records the CLI's
`total_cost_usd`, tokens and duration with `usage_source=MEASURED` and `cost_basis=cli_reported`, or
`usage_source=UNKNOWN` with every figure null when the CLI printed none. Nothing is estimated. Dispatch, leases, caps
and the park are the controller's (`/omni:landing-controller`). Its park retry (OMN-20864) follows the PR's base
branch tip, its head and a named blocker PR merging or closing, with a 60-minute backstop. Non-PR refs,
including ledger lines, retry next tick. Automatic retries preserve the attempt budget per head; only new
heads start new work. Parks produce local evidence without an operator MSG or RELEASE requirement.

Steps 1 to 3 are one read-only script, `drain_map.py`, shipped next to this file. It writes nothing
to GitHub, Linear or the ledger. Run it, then read what it printed before dispatching anything.

`scripts/landing_scorecard.py` reads `$registry_root/.claude_scratch/landing-metrics.jsonl` for six UTC clock hours
of merges by repo and sample-weighted means of latency medians. `landing_floors.json` sets each repo's hourly
floor (override with `ONEX_LANDING_FLOORS`); merge-pulse reports RED when a repo with waiting PRs falls below
its floor over the previous and current clock hours. Missing or corrupt inputs report UNKNOWN and make the pulse AMBER.

`drain_map.py` reads PR state from the PR watcher's state file through `pr_state_local.py` (next to
it) when that file is fresh, and reads GitHub only for a head the watcher has not read yet, or for
everything when the file is stale or missing, printing why (RULING 2026-09-27T18:05:21Z, OMN-19852).
Every run prints `reads: local=N github=M source=...`. On a fresh state, `github=` above a handful
is a defect to report, not a cost to accept.

Waiting on a PR (OMN-17427): a script, workflow agent or session that needs a PR to appear, take a new head,
finish CI or merge makes one call, `pr_state_local.py --pr <repo>#<n> --wait-until
seen|head=<sha>|ci-done|green|merged|closed|terminal [--timeout <s>]`, never a `sleep` loop around a read. It
re-reads the state file only when the watcher (or a remote lane's runner) rewrites it, returns 0 on the first
rewrite that meets the condition, and exits 124 at the timeout (540 s by default, at most 3600) or 3 when it read
no fresh state. A lane that would wait for CI or a merge hands the PR off (`/omni:pr-handoff`) and ends instead.
From 2026-10-07T12Z to 2026-10-14T12Z the hook-event projection held 1,619 such loops, 54.0 h of Bash time.

## 1. Inventory: the node first, gh as the control

```bash
S="<scratch dir for this drain>"; mkdir -p "$S"
"$registry_root/omnibase_infra/scripts/onex" skill merge_sweep --dry-run --inventory-only > "$S/inv.json"
F="<drain root>/freed.json"   # one per drain, kept across runs and successors (step 3a)
python3 "${CLAUDE_SKILL_DIR}/scripts/drain_map.py" --out "$S" --node-inv "$S/inv.json" \
  $( [ -f "$F" ] && echo --freed "$F" )
```

Exit 0 is a clean map and exit 3 a failed positive control. **Exit 4 is a complete map with
held-stale PRs**. **An exit 5 is a complete map with in-flight PRs** (`drain-done=no
reason=in-flight=N`) and no held-stale PR; exit 4 wins when both conditions exist. A PR waiting on CI,
armed, stacked, live-owned or paused is in flight, so `drain-done=yes` means every open PR is
merged, closed or held with a fresh hold: ANY in-flight PR makes it `no`. Every file is
written and every line printed for exits 4 and 5, so they are complete maps to dispatch from, not
crashes to retry; after exit 4, run step 3a.

The node's list is `.result.org_wide_open_remainders` in `inv.json` (about 2.5 minutes to run).
The script makes zero GraphQL calls (OMN-19611). Its PR list is one REST pulls read per repository
with anything open, its control is one search-bucket read, and it prints both, with the PRs only one
side has. Changed files come from git: the PR heads are fetched into the canonical clones as
`origin/pr/<n>` (a scratch mirror when a clone is missing or refuses the refs), and the files are in
`changed-files.json` beside the map. Check-runs are cached by head sha next to `--out`, and the
`api:` line prints the pages the run spent. A PR merging between the two reads explains a difference of one or two;
anything larger, re-read before going on. Zero open PRs from gh is a hard failure (exit 3), never a
clean drain. Skip `rsd-repo` (archived) and `omnigemini` (parked) entirely; the script does, and
does not report them.

## 2. Owner map: every PR gets exactly one owner

An owner is any of:

- **an open (dangling) CLAIM** that names the PR by `repo#n` or `pr=` with its repo, by a ticket in
  the PR's title or head branch, by the head branch name, or by the PR's `worktrees/<dir>`
  worktree, unless that CLAIM's lane has since handed the PR off (a STATUS or TERMINAL row of
  the lane carrying `handed-off=<repo>#<n>`, after the CLAIM: `pr-handoff` session-lane mode writes
  it for the orchestrator's own PR, whose session CLAIM stays open). A change-control companion and
  a stacked PR inherit their parent PR's owner. Only the CLAIM's own fields match (OMN-19846): the
  ticket is its `ticket=` field, never a `ticket=` quoted in its prose; `pr=` is the list of PR
  tokens right after it, never a number further on; a ticket owns no PR, however few lanes CLAIM it
  (OMN-19998). The match is the one owner rule, `plugins/omni/scripts/ledger_tail.claim_names`
  (OMN-17427), which the sweep's claim check reads too: the CLAIM owns the PR only when its `pr=`
  cell names it or it names the PR's head branch as a whole token. A repo#n in the CLAIM's prose,
  in scope or out of it, a cause cell and a worktree path never own (the OMN-19846 phrase readers
  and the worktree match are gone);
- **a routing MSG** addressed to a concrete worker lane other than its sender (not `to=all` or `to=operator`, and not a
  dispatcher: a lane some CLAIM in the window names as `parent=`, `drain=` or `landing-identity=`,
  such as the orchestrator, a drain or the landing identity) whose own `owns=<repo>#<n>[,<repo>#<n>]` cell
  names the PR (OMN-22478). A repo#n spelled in the MSG's text routes nothing, so a lane that names a PR as
  context makes no one its owner; a lane that means to give a PR to a worker writes the cell.
  A MSG to a dispatcher is a report or a handoff into its queue, so the PR stays dispatchable. The
  recipient owns it only while that lane is live under the same 45-minute
  rule. A later TERMINAL from the recipient, a STATUS from it naming the PR merged or closed, or a
  MSG from it handing the PR back ends that routing ownership;
- a PR claim (`python3 $registry_root/omniclaude/scripts/pr_claim_registry_cli.py list`);
- a hold (step 3's hold check); or
- an operator decision (production-gate PRs: `base=main` in `onex_change_control` or
  `infra_repo`; dependabot PRs blocked on withheld org secrets).

**Dangling CLAIM, the canonical definition** (the same one ledger-reconcile and the OMN-19256 row
grammar in `$registry_root/../ops_tooling_pkg/src/ops_tooling_pkg/ledger/ledger_grammar.py` use): a CLAIM is closed when a
later row closes it by id (`closes-CLAIM=<claim token or ts>`), by supersession (a later CLAIM
carrying `supersedes-claim=<that claim's ts>`), by lane (TERMINAL, or a legacy closer the grammar
lists, whose `lane=` or `claim-lane=` equals the claim's lane, after it), or by `RELEASE re=<claim ts>`.
A closer that carries `claim-lane=` acts for that lane: its `lane=` is the writer (a resumed session
closing a stopped lane's CLAIM), so it closes the `claim-lane=` lane only, never the writer's own
CLAIMs.
Rows are found in both row shapes (timestamp-led and bar-led). Every CLAIM of a lane is evaluated,
not just its latest. The live ledger plus the `archive/*-split.md` rolls from the same window are
searched. Anything else is dangling. The mechanical reconciler (the `ledger-reconcile` skill,
`python3 $registry_root/scripts/ledger_reconcile.py --report`) implements this and is the preferred tool
for the dangling list; hand awk is the fallback. `drain_map.py` applies the same definition to match
claims to PRs.

**The window.** A CLAIM can own a PR only when its row timestamp is at or after the read time minus
`--since-days` (default 7). That is the window `ledger_reconcile.py --since-days` and the
`session-resume` skill use, so all three see the same CLAIMs. It is by row timestamp, not by roll
file name: a roll is named for the day it was cut, and the 2026-09-16 split holds rows from
2026-08-31. A CLAIM older than the window owns nothing, live or dead, so its PR is unowned here and
is worked like any other unowned PR, with no `supersedes-claim` to cite. `drain_map.py` prints the
window start and how many older CLAIM rows it left out. If an older CLAIM matters, widen
`--since-days` for this script and `session-resume` together, never for one of them.

**Known divergence, read before trusting the reconciler here.** As of 2026-09-23,
`ledger_reconcile.py` does not yet implement the whole definition: it pairs a lane's TERMINAL with
one open CLAIM only (last in, first out, one to one), and it has no `RELEASE re=` or `claim-lane=`
closer. On a lane with several CLAIMs, or one released by a RELEASE row, its dangling list differs
from `drain_map.py`'s. Until the reconciler is fixed (separate work in `registry_root`), the owner
column of `drain_map.py` decides dispatch; use the reconciler's list as a cross-check only.

The owner column prints each owner's CLAIM time, what matched, the lane's last row, and `live` or
`DEAD`. **Only a live owner blocks dispatch:** a lane that wrote a row within 45 minutes of the read
(`--dead-after-minutes`), or a `pr_claim_registry` claim on the PR whose heartbeat is that fresh. A
dangling CLAIM from a lane silent longer (a lane killed by a restart, a lane from days ago) is a
dead owner. Its PR is dispatchable, and the action names the dead CLAIM: the new lane runs with
`session-resume` semantics (`/omni:session-resume`): it cites `supersedes-claim=<that CLAIM's ts>`
and reads back the dead lane's branch, worktree and last rows before acting. Two live owners on one
PR is a conflict: resolve it before any dispatch.

A PR with no owner gets a lane. **Never describe what a PR contains until you have read it.**

## 3. Hold check and classification

**Canonical hold check** (read-only, no tail cap). A PR is held if ANY of:

1. it carries a label in the hold label family (its name starts with `hold` and a colon), read via
   `onex scm pr-view OWNER/REPO#N` (labels), **except the family's auto-merge member**. That one label is the
   auto-merge workflow's arm gate (the label `check_auto_merge_hold.py` lists in `HOLD_LABELS`,
   OMN-18179), not a merge hold: lanes put it on a handoff so automation does not arm the PR and the
   lander merges it on the exact head. Removing it is the landing lane's call (RULING
   2026-09-24T14:21:58Z), and merging such a PR once green was approved (OPERATOR-CONSENT
   2026-09-24T11:00:36Z). A PR carrying it is classified on its checks like any other and routed to
   its lander, and it is **never armed**: green goes on `WOULD-LAND-NO-ARM` (pr-land step 7, squash
   on the exact head), red goes on `WOULD-DISPATCH` marked `never arm`. An author who wants a real
   hold writes a HOLD row (item 2) or uses another label of the family, and either still holds
   beside it;
2. a HOLD row scopes it (`pr=<repo>#<N>`) or its repo (`repo=<repo>`), with or without `to=`, and no
   later `RELEASE re=<that hold's id>` and no `until=` already past. A HOLD with an `id=` counts from
   every roll in the window until its RELEASE. A HOLD with a `pr=` field holds the PRs that field
   names; other PRs its text cites are citations. An id-less (legacy) HOLD cannot be released by id, so
   it holds only on the day it was written (or until a RELEASE from the same lane names the PR); an
   older one prints in `holds.txt` as `stale-legacy, verify` and does not hold. If it matters, read it
   and decide by hand. An id-bearing HOLD with `release=operator` and a well-formed
   `ruling=<source row>` is an operator-standing hold: it is durable, never stale, and only
   `RELEASE re=<id>` releases it; while it stands, it covers every other hold on its PR;
3. a row in the live ledger or today's archive roll names the PR by repo AND number and carries an
   **instruction** within 400 characters of the mention: do not arm, merge or land it, not
   standalone, merge it alongside another. This is the instruction-only matching of the `lane-brief`
   hold scan. Report text never holds: RELEASE rows and reports (STATUS, TERMINAL, FRICTION,
   CORRECTION, ACK; `drain_map.py` `REPORT_TYPES`) are skipped. **A STATUS row never creates a hold**
   (OMN-19852): an order or a wait a lane writes in its own status ("must land after
   omnimarket#2958", `state=waiting_order`) is context, and it once made onex_change_control#11522
   and its parent omnimarket#2968 wait on each other. A STATUS row may still say a hold is lifted.
   To stop another lane, write a HOLD row or a MSG through `/omni:ledger-msg`; "DRAFTS HELD: ...", "is body-held" or "on hold" is a description, not an instruction,
   a lane describing itself ("I never merge") is not an instruction about the PR, and a bare mention
   of "standalone" with no negation anywhere in its own clause is a description of where something
   ELSE could land ("landing there or as a fast standalone PR", OMN-19846), not an instruction that
   THIS PR not be merged standalone;
4. pr-land's own pause check stops on it (OMN-19852): `drain_map.py` runs `pause_check.sh` on every PR
   it would dispatch and holds on its `LABEL`, `HOLD` and `PARKED` findings (`PAUSE_CHECK_STOPS`,
   hold line `(5)`), so no lane is sent to stop at pr-land step 3. Its `REPO-PAUSE` is the merge pause
   below and its `PR-ROW` is left to item 3: on the live ledger of 2026-09-28 `PR-ROW` read 40 of 50
   open, not-held PRs paused, mostly on pr-watcher tick MSGs counting `held-excluded=`;
5. its newest lane TERMINAL is `outcome=needs_operator` (hold line `(6)`), until a RULING,
   OPERATOR-CONSENT or RELEASE row names the PR or a new CLAIM is written on it. A new head does not
   end it. docs-repo#845 was re-dispatched three times onto the operator's own "not
   for merge" PR comments before this rule;
6. its repository is parked by operator ruling (`PARKED_REPOS`): class `held(parked)`.
   `pause_check.sh` reads the same set and prints `PARKED`.

**A merge pause is not a hold.** A STATUS or RULING row that declares a merge pause covering the repo
(a runtime-merge pause, for example), not lifted by a later row, binds only a PR that the repo's
rebuild trigger classifies runtime-affecting: the check `ticket-pipeline` step 6 uses, run by
`drain_map.py` against the PR's changed files and labels, with a positive control (a runtime handler
path) and a negative control (`README.md`) per repo first. A PR it cannot classify fails closed as
runtime-affecting. Even then the pause blocks the **merge, never the fix**: a paused PR with reds
still goes on `WOULD-DISPATCH`, marked `merge waits on pause`, and a paused green PR goes
on `WAIT-PAUSE` instead of `WOULD-ARM`.

A pause declaration is `drain_map.py` `pause_sentence` and `pause_scopes_repo`, the one matcher
pr-land's `pause_check.sh` also reads (`repo_pause_lines`): a STATUS or RULING row with no `pr=` or
`state=` field (a row about one PR never pauses a repository), a present-tense instruction ("runtime
merges stay paused", "hold every runtime merge", "no other merges", "merge freeze", "no runtime merge
until 22:50Z"; never a lane's own "No merge, no ready-flip" or a census's "no other merges since
22:12Z"), scoped by its `repo=` field or, with none, by the pause sentence naming the repo.

**Landing order (single source, `drain_map.py` `LANDING_ORDER`).** Companions land first: a
change-control companion gates its parent's change-control checks, so it merges on its own CI before
its parent and never waits on it. The parent's cascade move says the same ("land it first on its own
CI, then rerun the parent's failed eligibility run whole"), and pr-land's pause check prints the
order under any `ORDER` row.

Match PRs by repo and number (`omnibase_infra#4005`), never by a bare `#N`. A match stops the lane
for that PR and is reported. `drain_map.py` prints every match with its row in `holds.txt`, and
prints each merge pause in force and which PRs it binds. Item 3 and the pause are text matches:
read the printed row before reporting it. In PR bodies and commit messages, write "the hold label
family" or "merge-hold vocabulary" and never the literal label names (CLAUDE.md rule 15).

**Classes.** Read the body, files and checks of each PR. The title is evidence only for a parked
state, which is often written only there; never characterise a PR's content from its title.

| Class | Test | Move |
| -- | -- | -- |
| held(...) | the hold check above matched (label, live HOLD, today's id-less HOLD, an instruction row, a pause_check stop, a needs_operator TERMINAL; held(parked) for a parked repo); a merge pause alone never makes a PR held | stop; report the hold row or label |
| operator-gated | `base=main` in `onex_change_control` or `infra_repo` | operator decision; no lane (counted as held) |
| parked | title or body says PARKED, awaiting consent, or do not merge | report; no lane |
| stacked | the base is another feature branch, not `dev`/`main` (its usual only red is `non-dev-base-guard`) | lands after its parent; owner = the parent's owner; no fixer |
| companion | a bot-authored `onex_change_control` PR naming an OPEN parent PR or head sha | **lands first** (`drain_map.py` `LANDING_ORDER`, OMN-19852): it gates its parent's change-control checks, so it is routed by its own state like any PR (green: `WOULD-ARM`; red: `WOULD-DISPATCH pr-land`; a draft: reported; CI running or armed: wait) and never waits on its parent. It inherits the parent's live owner, whose lane lands it first |
| waiting(order), same contract file | an open `onex_change_control` PR that modifies the same `contracts/<name>.yaml` as an older open PR the drain has not held or exempted (OMN-17427) | one lane per contract file: the oldest keeps its class, each later one reads `WAIT-ORDER(contract)` with the oldest as predecessor and is freed at the map read after the predecessor merges or closes. Different contract files do not wait on each other. The landing controller dispatches no worker on a companion, so only this map needs the rule |
| orphan companion | a companion whose parent is not an OPEN PR in this read: merged, closed, or no PR at all (an observation append names only a sha) | `WOULD-DISPATCH pr-land`, never `WOULD-ARM`: the lane reads the parent live first; merged or none, the companion lands on its own CI; closed unmerged, report it superseded. With CI still running it reads `pending` |
| queued (class `green-armed`, detail `queued=merge-queue`) | the PR watcher's record carries `queued` (its live `mergeQueue` read; GitHub clears `autoMergeRequest` at enqueue, so the PR reads unarmed otherwise, OMN-20554) | in flight: wait for the queue; never `WOULD-ARM`, never a fixer, whatever the head's check list reads |
| bot (release) | a bot-authored release PR (`chore: release <package> <version>`, or a `release/` head) | release train: the landing controller lands it once release-cut's premise reads READY (OMN-20864); `pr-handoff` still refuses a handoff |
| bot cascade | any other bot-authored PR that is not a change-control companion: a dependency bump, a contract-pin advance, a lane-census refresh | routed by its own state like the operator's own PR (green: `WOULD-ARM`, and `arm_green_prs.py` admits bot authors; red: `WOULD-DISPATCH pr-land`). Nothing else lands them: until 2026-09-28 they were all reported as release-train PRs and sat open for up to a day |
| superseded bot | a bot cascade PR with a newer open PR of the same series (same repo, base and title once versions, shas and the trigger note are blanked) | `WOULD-DISPATCH pr-land`: close it with a comment naming the newer PR, never land it (the drain goal's superseded rule) |

**The landing policy (OMN-17886, OMN-20249).** There is no author class: every author's PR is classed on its own
merits like the operator's (RULING 2026-10-14T02:24:46Z: "We should merge them if they are green. If they are not
ready to be merged, they should be draft PRs."). A runtime-affecting one still needs a lab PASS for its head, and a
draft or a held PR (the first row) stays off the lists for everyone. The plugin's `scripts/landing_policy.py` prints the
rule; the machine-local `landing_policy.yaml` and its `report_only` value are retired and a file left on a host is not read.

| draft, work unfinished | the last TERMINAL naming it says BUILT/DRAFT, or names a gap (an `outcome=held` or blocked report, a missing PASS) | owner = the gap's ticket; do not flip, no fresh lane |
| draft | `isDraft`, none of the above | report: not ready (RULING 2026-10-14T02:24:46Z); the watcher reads no CI of a draft and the controller skips it, so it is never `WOULD-DISPATCH` and never counted dispatchable. The map prints `DRAFTS (n)` on its own line; its author flips it when it is ready |
| pending | a check is still running on the head | wait |
| green, armed | no red, auto-merge armed | wait for the merge |
| green, unarmed | no red, not armed | arm through `pr-land` step 4; no fixer. With the auto-merge arm-gate label: `WOULD-LAND-NO-ARM`, the lander merges on the exact head (`pr-land` step 7) and never arms |
| change-control cascade | the four change-control contexts red together: `occ-preflight / eligibility`, `verify / verify`, `OCC Companion Merged Gate (OMN-15214)`, `CI Summary` (their `call-reject-skip-token /` copy and `OCC Preflight Dependency` ride along); or any red gate of `occ-preflight / eligibility`, `OCC Preflight Dependency`, `OCC Companion Merged Gate`, whatever else is red (the other reds are read after it clears) | `pr-land` step 5, keyed on the body's Evidence-Source companion: open, land it first on its own CI, then rerun the parent's eligibility run whole; merged, rerun it whole |
| real red | any other red | a `pr-land` lane, sonnet (opus for substantive conflicts) |
| superseded | its diff is already on the base (found on reading) | close with a supersession comment, after `pr_claim_registry_cli.py claim` |

A draft's `DECLINED` / `PR_DRAFT` autobind outcome is expected. It is not a dropped mint. Three
lanes misread it on 2026-09-22, and one hand-authored a companion that had to be closed.

Every open PR lands in exactly one bucket, and the script prints the counts on one line:
`summary: open=N held= live-owned= dispatchable-fix= dispatchable-arm= waiting-on-pause= waiting= reported=`,
then `reported-by-class:` and `fix-detail: dead-owner= merge-waits-on-pause=`. `WOULD-DISPATCH` is
the dispatchable-fix bucket (cascade and real red with no live owner, including those whose
owner is dead or whose merge waits on a pause), `WOULD-ARM` the dispatchable-arm bucket (green,
unarmed, no live owner, no pause binding it), and `WAIT-PAUSE` the green PRs a pause binds. `WAITING`
lists the PRs a one-shot lane left on a wait (step 3b), each with its kind. Those lists are the
dispatch plan; every other PR is reported, not worked.

## Landing controller (OMN-19998)

`scripts/landing_controller.py` is a launchd tick (ops_tooling_pkg `launchd/landing-controller`) and
the only lander since G-ACT passed (2026-09-29T08:11:25Z; the Claude drain was retired by RULING
2026-09-29T06:34:17Z). Every tick acts: it merges pinned to the head, reruns once per head, updates
branches, delivers and closes its own change-control companions, and dispatches fix workers for red
PRs under leases. It has no observe-only, report-only or dry-run mode (RULING 2026-09-29T12:02:35Z);
a tick that cannot act refuses and writes a DEGRADED receipt, which the drain watchdog acts on.
`../landing-controller/SKILL.md` has the refusals, and this table the two rules owned here:

| Act | When | How |
| -- | -- | -- |
| `arm` | a green, unheld, unowned, non-draft PR at its head, no merge pause, no live-read refusal in the last 30 min | `arm-green/scripts/arm_green_prs.py --arm-only` on a one-tick map directory: the live re-read and every refusal of that script apply |
| fired order edge | every predecessor of the PR merged (closed is not merged) after its red was graded, and a change-control check is among the reds | the node's `fired_edge_graded_stale` (`node_pr_lifecycle_triage_compute`) classes the red `cascade`, so the node reruns the whole gating run once per head and merges when it goes green; a red that survives the rerun goes to a worker. No drain is messaged: the drain is retired (RULING 2026-09-29T06:34:17Z), and `notify_drain` reached nobody (OMN-19998) |

A hostile-review red (`Hostile Review Gate`, `Hostile Review Thread Gate`, `Hostile Reviewer
(adversarial gate)`) is class `reviewer_pool` (OMN-20067): never a code red, so it draws no fix worker
and is left out of a worker's brief beside a real red. It earns one whole-run rerun per head, oldest
first, only while the lab-host-d reviewer endpoint has a free slot (4 slots, less the reviewer runs queued or
running); otherwise the PR reads `pending` until a slot frees or the head moves.

Once that one rerun is spent the red is read from the Hostile Reviewer job's log (OMN-19998, OMN-20910). A
`blocked` verdict is a finding both voters agree on and goes to a fix worker. A `degraded_quorum` verdict is
reviewer availability, never code, and never goes to a fix worker: it is rerun up to `HOSTILE_FRESH_RERUNS` times per
head while a reviewer slot is free; with none free it waits `HOSTILE_WAIT_MINUTES`; then it is escalated, once per
head, by a `kind=reviewer` MSG to the orchestrator and a DEGRADED tick, the PR gated as
`hostile_reviewer_unavailable:<verdict>@<head>`. An escalated head is rerun once more every `HOSTILE_RETRY_MINUTES`
while a slot is free. A log that gave no verdict gets one fresh run, then a worker, which reads the log.

Owners are the union of the claim registry and the ledger (`landing_ledger.py`, which calls this
skill's `ledger_owners`, `hold_findings`, `lane_wait` and `wait_trigger`, so a PR the map calls owned or
held is never armed).

### Engine rc 86 and the no-result record (OMN-22655)

Engine rc 86 is `NO_RESULT_EXIT` in `scripts/landing_worker_run.py`: a worker's engine ended and left no `result.json`,
so the runner wrote a `no_result_file` record in its place. 86 is not an exit code of the engine. A clean engine exit
(0) becomes 86; a non-zero exit keeps its own code in `engine_rc`; the engine's own code is always in
`original_engine_rc`. The record, the worker's TERMINAL row and the controller's `worker-failures.jsonl` row carry
the cause the worker ended on (`node_cause_result_read_effect`, read from the worker's output):

- `pr_create_refused`: the output carries the refusal of `onex scm pr-create`; `refusal` holds it.
- `fix_pushed_pr_not_opened`: the output names a pushed branch and says the pull request is not open.
- `unrecognised`: neither; the log tail in `last_log_lines` is all there is.

`branch` and `fix_head` are set when the output names them. A retry reads these before it rebuilds the fix.

### Product-floor alarm (OMN-19815)

`scripts/floor_alarm.py` runs independently of sessions under launchd every 10 minutes.
Every run acts, logs its result, and locks its state directory against concurrent runs.
Its six inputs and their sources are:

| Input | Source |
| -- | -- |
| Product floors | sibling `landing_scorecard.py` reader and `landing_floors.json`; `ONEX_LANDING_FLOORS` override |
| Product merges | canonical-clone reflogs named by `ONEX_STATE_DIR/logs/canonical-clone-sync.jsonl`, otherwise `registry_root/.onex_state/logs/canonical-clone-sync.jsonl`; docs-only changes excluded |
| Waiting PRs | `registry_root/.claude_scratch/pr-watcher/state.json`, OPEN, non-draft, excluding `held-excluded` |
| Controller dispatch | landing state directory's `ticks.jsonl`; last three rows, including refusals, and newest-row age. Zero workers is a breach only when a tick's `worker_eligible` (the open red PRs under no gate, hold or lease) names a PR, or a tick carries no such list (OMN-17427) |
| Episode state | required `--state-dir`: `state.json`, `lock`, and one `runs.jsonl` receipt per run |
| Delivery destinations | required `--ledger` through `uv run --project "$registry_root/../ops_tooling_pkg" onex-ledger` (inherits bus write mode); `ONEX_ALERT_CHANNEL_LIB` or the public plugin's `alert-channel.sh`, with credentials sourced only by its bash child |

All paths accept CLI overrides. A changed breach set writes one STATUS row; a breach lasting
30 minutes sends one delivered alert per episode. UNKNOWN inputs persisting 30 minutes become
findings. Recovery writes a cleared row. Exit codes: 0 no breach (or concurrent lock held),
1 breach handled, 3 ledger/alert delivery or state write failed, 64 usage/environment refusal.

## 3b. Lane waits and lane-written pauses (OMN-19852)

**A lane's wait keeps its PR in flight until the wait's trigger fires.** A landing lane is one-shot
(no GitHub-polling waiters), so a lane that finds a wait it cannot clear ends with TERMINAL
`outcome=waiting_ci`, `waiting_lab` or `waiting_order` (a lab-proof lane that found no free host ends
`outcome=no_host`, a lab wait too). Its TERMINAL closes its CLAIM, and without this rule the PR read
as unowned and the drain re-dispatched a lane that found the same wait (queue-status at
2026-09-27T17:49Z: 7 of 11 "dispatchable PRs with no lane" were such waits). `drain_map.py` reads the
newest TERMINAL about each PR in the CLAIM window: its `pr=` field names the PR, or, with no `pr=`
field, it is the PR's own per-PR lane (`land-<repo>-<n>-...`, `prove-<repo>-<n>-...`). When that
outcome is a wait, the TERMINAL's `head=` is the PR's current head (a TERMINAL with no `head=` counts
for `--wait-no-head-hours`, default 6), and no CLAIM on the PR came after it, the PR goes in the
`waiting` bucket, class `waiting(<kind>)`, with the lane, the wait's state and its recheck trigger in
the owner and action columns, until the trigger fires:

| Wait | Trigger (the PR is dispatchable again) |
| -- | -- |
| `waiting_ci` | the head's check-runs, re-read when the cached read is older than the TERMINAL, are no longer pending; with no runs at all, after `--wait-fallback-hours` (default 2) |
| `waiting_order` | every predecessor it names is no longer open: a `parents=` or `waits=` field (`parents=none` names none), else a "merge-order parent / stack parent / waits on / stacked on / blocked by <repo#n>" phrase; with none named, after the fallback |
| `waiting_lab`, `no_host` | a later row names the head with a lab PASS, or is a RELEASE naming it (a lab lease released after its run); otherwise after the fallback |

A fired trigger is printed in the PR's detail (`wait fired: ...`). A wait never overrides a hold, a
live owner or a reported class, and it never makes a PR held: it only keeps the PR off the dispatch
lists, and it counts toward `in-flight` and `waiting=` on the `SUCCESSION` line.

**A lane-written merge pause expires with its lane.** A pause declared by a STATUS row, not a RULING
or OPERATOR-CONSENT row, stops binding once its lane has written no row for `--pause-expire-hours`
(default 12): the map prints it as `EXPIRED PAUSE` and it binds no PR. runtime-train-83's
2026-09-24T22:40:18Z pause still bound omnibase_infra#4215 three days after the lane stopped, after
the rule it served was replaced (RULING 2026-09-27T14:31:58Z lane=orchestrator-83). A later row
carrying `lifts-pause=<the pause row's ts>` lifts exactly that pause, in the map and in pr-land's
`pause_check.sh` alike (both read it through `drain_map.py` `lifted_pause_stamps`). An operator's RULING
pause never expires by time; only a row that lifts it does. A window-close report (`window=closed`) and a row
carrying `lifts-pause=` declare no pause: on 2026-11-03 three window-close rows saying "no other merge on
omnimarket during the window" skipped update_branch on 18 PRs for two hours (OMN-22348).

## 3a. Hold re-validation: no hold stands unexamined for more than 12 hours

A hold whose source is a text row, that is an instruction row (item 3) or an id-less HOLD row, is
re-examined once it is 12 hours old (`--stale-after-hours`). A label, a HOLD row with an `id=`, and
a RULING or OPERATOR-CONSENT row are released by their own mechanism and are never re-examined here.
`drain_map.py` writes every hold to `holds.json` with a key (`<repo>#<n>@<row ts>/<lane>`), its kind
and a status (`durable`, `fresh`, `stale`, `revalidated`, `covered`, `freed`). An operator-standing
hold is never re-examined and marks every other non-freed hold on its PR `covered`, so those holds
are not re-examined and cannot make the PR held-stale. Otherwise, a held PR is held-stale when any
of its holds is stale, even beside a fresh, re-validated or durable hold; the map lists it on the
`HELD-STALE` line and exits 4.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/hold_revalidate.py" --map "$S" --out "<drain root>" \
  $( [ -f "<drain root>/freed.json" ] && echo --freed-in "<drain root>/freed.json" )
```

`hold_revalidate.py` is read-only on GitHub (REST GET only). For each stale hold it reads the held PR
and the clause the instruction sits in, and decides:

| Verdict | When |
| -- | -- |
| `freed-void` | the held PR is merged or closed; the clause names this PR only as another PR's dependency; every dependency it names is closed unmerged |
| `freed-met` | every dependency PR it names is merged; an `until <stamp>` has passed; an "until green" PR is green now |
| `still-holds` | a named dependency is still open; an `until` stamp is ahead; the PR is not green |
| `needs-decision` | a release, image, deploy or lab-receipt condition (never decided from text), or no condition at all |

`X before Y` means Y waits on X (X is `freed-void` for that clause), and `do not land before X`
means the held PR waits on X.

It writes `freed.json` (carrying earlier `freed-*` records forward) and `hold-revalidation.md`. Re-run
`drain_map.py --freed <drain root>/freed.json`: a freed hold no longer holds, and a hold re-validated
as `still-holds` within 12h is not stale. A newer row about the same PR has its own key, so it still
holds.

A `needs-decision` hold is the orchestrator's to decide from the row, never to leave stale:
`--decide '<key>=keep:<why>'` (good for 12h, then re-examined), `--decide '<key>=free:<why>'`
(permanent for that row), or, for a standing hold such as an operator exclusion, a HOLD row with an
`id=` (and an `until=` when it has an end) through `ledger-msg`, which is durable and never stale.
The reason is required and lands in `freed.json` and the report.

## 4. Dispatch

**The cause worker dispatches no per-PR lanes.** Members stay on the controller's per-PR path, or are suppressed
while the cause holds a lease. For the worker, "dispatch" is delegation: the drafts of the one fix go through 4a and
4b. The rest of this section is the by-hand sweep.

One lane per PR on the `WOULD-DISPATCH` list, briefed with the `lane-brief` skill
(`/omni:lane-brief`) and the `pr-land` skill (`/omni:pr-land`) as its procedure.
Respect merge-order rulings: serialize the chain a RULING names, and parallelize everything else.
The session ceiling is 15 concurrent lanes (raised from 12 on 2026-09-22), and that counts lanes
already running. Do not dispatch onto a PR that already has an owner.

Before dispatching, and again before arming or merging anything yourself, re-run the step 3 hold
check (re-run `drain_map.py`; it is read-only) and the `/omni:ledger-msg` inbox check (section 4
there) for this drain's own lane name and `to=all`. The inbox reads only MSG and HOLD rows with an
`id=`; the hold check covers STATUS pauses, legacy HOLD rows and labels, which the inbox misses.
Each dispatched `pr-land` lane runs its own checks per its brief; that does not substitute for the
drain's own check at the orchestration level.

**Landing machinery first (RULING 2026-09-28T01:42:20Z, OMN-16336).** A PR that fixes the landing
machinery itself is started before any other PR, because every other PR waits on it. `drain_map.py`
marks a PR priority when one of these holds, and prints the mark in the tsv detail as
`priority=<why>`:

- the orchestrator's priority list names it: `$registry_root/.claude_scratch/drain-root/priority.txt`,
  one `repo#n reason` per line, `#` comments allowed, re-read at every map refresh (append a line
  to put a PR first; a merged or closed PR left on the list is harmless). `--priority-file off`
  disables it, `--priority-file <path>` reads another file;
- it carries the `drain:priority` or `priority:landing` label;
- its changed files are the landing machinery: the merge-drain, arm-green, pr-land, pr-handoff,
  ci-watch and queue-status skills; the CI Summary, eligibility, change-control preflight, companion,
  auto-merge and merge-queue workflows; the gate, summary and throttle scripts under `scripts/ci/`;
  the PR watcher; and the gh shim and its read router.

Priority PRs are listed first in `WOULD-DISPATCH`, `WOULD-ARM` and `WOULD-LAND-NO-ARM`, and the map
prints `PRIORITY (n): ...` (the listed ones) and a `priority-detail:` line that also names priority
PRs that are not dispatchable (owned, held, waiting). A sweep starts the `PRIORITY` PRs'
lanes before any other. Priority only orders: it never frees a hold, an owner, a wait or a class.

**Green PRs need no lane.** The map's `WOULD-ARM` and `WOULD-LAND-NO-ARM` lists go to the arm step
first (`/omni:arm-green`, run once on the fresh map): it arms or squash-lands what is green on the
exact head, and only a PR it skips for a reason a lane can fix (a stale or conflicted branch, a red
rollup, repeated failed-checks dequeues) gets a `pr-land` lane; a draft is reported, never laned.

**Bulk operations.** More than one PR in a repo to update-branch, arm, or rerun goes through the
throttle (CLAUDE.md PR CI requirement 4), never a hand loop over `gh`. Its operations are
`update-branch`, `arm-automerge`, `rerun-failed` and `noop-dry-run`. Dry-run first:

```bash
python3 "$registry_root/omnibase_infra/scripts/ci/bulk_pr_throttle.py" --owner OmniNode-ai \
  --repo <repo> --prs <n,n,n> --operation arm-automerge --dry-run
```

## 4a. Delegation (required, OMN-19855)

The drain writes more text than any other lane, and on 2026-09-26 the repo-drain lanes delegated
none of it (lane-brief "Why 3a.9"). So the drain's own pure-text subtasks go through `onex delegate`
first: summaries (the step 5 report prose, succession and handoff MSG prose), PR bodies and PR
comments it writes or repairs, ticket comments, and classification of CI logs and failure excerpts.
Exact counts, PR numbers, shas, lists of identifiers, class names and verbatim quotes stay
deterministic: compute them in the shell and pass them to the prompt as a fact table, then
fact-check the draft against that table before use.

```bash
"$registry_root/omnibase_infra/scripts/onex" delegate "<Summarize|Classify ...: one instruction line, then the fact table>" \
  --task-type document --ticket <the drain's ticket> --bus kafka --lane dev --locus deployed-lane \
  --state-root "$registry_root/.onex_state"
```

For a classification of a CI log use `--task-type reasoning` (there is no classification task type; the CLI validates `--task-type` against the task-class contract). GLM is no longer a rung of
`onex delegate`: the Coding Plan terms allow it only inside a supported tool such as Claude Code, so
`--backend-id cloud-glm` always fails (omnimarket#3136, OMN-20173). GLM through Claude Code goes first for
a text step (OMN-20844; `--first lab` keeps the lab-first order), which `delegation_step.py text` runs for you through `/omni:harness-delegate
--harness claude-glm`, `glm-5.3-flash` first and `glm-5.3` once when flash fails or its answer is refused (OMN-20456). `delegation_step.py text` builds the call's goal contract first (OMN-20026): the task-class
template's check names are mapped through `goal_contract_map.json`, each `--acceptance-criterion '<shell command>'` becomes a
`command` item, and one `disposition` item is added. A check name with no row in the map, a task class the template does not
declare or an unreadable template refuses the call (exit 2) before any engine runs, and every receipt of the call carries
`goal_id`, `parent_goal_id` (from `ONEX_PARENT_GOAL`), `contract_sha256` and the contract items. Every `pr-land` lane dispatched in step 4 carries the same
step through its brief (part 3a.9); a brief without it is refused by `lane_brief.py check`.

The operator ruling of 2026-09-28T06:24:10Z (OMN-17427) says lanes delegate as much work as possible to Codex, Jev, GLM and the lab models before spending Claude. Each subtask goes to an engine by its kind: pure text to GLM through Claude Code (`/omni:harness-delegate --harness claude-glm`) and then the lab through `onex delegate` (OMN-20844), typed decisions with a fixed answer set on any repository but `docs_repo` (operator RULING 2026-10-13T18:34:53Z, OMN-20106) to Jev through the omnimarket typed-decision node, and mechanical code edits, test scaffolds, lint and type fixes and conflict-resolution drafts through Codex first (operator ruling 2026-09-30, OMN-20106; the plan period ends about 2026-10-30), then GLM through Claude Code (OMN-20844), then the code-edit node on the lab, then the lab agent (crush, interim); the lane verifies, while Claude reviews every draft and diff and makes every call that touches a gate, the ledger, a merge or an operator's words. Lane-brief part 3a.9 carries the commands, and `lane_brief.py check` refuses a brief whose 3a.9 drops Jev, Codex or the lab code step. Measured on 2026-09-28 from a lane, the lab answered in 26 s, Jev in 0.23 s; GLM through Claude Code answered a 15 KB summary in 38 s on 2026-10-01. The cause worker and the per-PR workers do not paste this routing as prose either: they run the receipted steps of 4b, so a worker never depends on reading this section.

| Subtask | Engine | Command |
| -- | -- | -- |
| pure text: PR bodies and comments, commit messages, summaries, TERMINAL and MSG prose, free-text log classification | GLM through Claude Code, then the lab | `python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/delegation_step.py" text --lane <lane> --step <step> --prompt-file <file>` (`harness-delegate --harness claude-glm`, then the lab through `onex delegate --locus deployed-lane`, receipted; OMN-20844) |
| typed decision with a fixed answer set, any repository but `docs_repo` | Jev | `python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/delegation_step.py" decide ...` (section 4b: every option described, deciding facts computed in code, receipted). Raw form, when no lane step fits: `env -u PYTHONPATH uv run --frozen --project "$registry_root/omnimarket" python -m omnimarket.nodes.node_typed_decision_effect < <scratch>/decision.json` with `criteria` as option -> `{what, not_for}` objects (omit `incumbent_answer`; exit 0 Jev decided, 3 Jev abstained) |
| mechanical code edits, test scaffolds, lint and type fixes, conflict-resolution drafts | Codex, then GLM, then the code-edit node, then crush (interim) (OMN-20844) | `codex exec -C <worktree> -c model_reasoning_effort="high" -s workspace-write -c sandbox_workspace_write.network_access=true --json -o <scratch>/codex-final.txt - < <scratch>/codex-prompt.txt > <scratch>/codex.jsonl` (no model flag); second route `delegation_step.py code ... --writable '<glob>' --check 'NAME=<argv command>'`, which runs `onex code-edit run` on the lab with each model turn an `onex delegate` run (run ids in `runs=`); interim fallback `python3 "${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lab_crush.py" --worktree <worktree> --scratch <scratch> --task-file <scratch>/task.txt` (crush on the lab model in the lane's own worktree, only when the node route is skipped or fails; OMN-20292 pending); GLM through Claude Code editing the lane's worktree runs right after Codex (`--glm last` keeps it last), `python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-delegate/scripts/harness_delegate.py" run --harness claude-glm --task-class code_generation --writable-repo <worktree> --prompt-file <task> --check '<focused test>'` (or `delegation_step.py code`, which runs all four), and the lane reviews the diff |
| review, verification, gates, ledger, merges, operators' words | Claude (the lane) | read every draft and diff, rerun the tests |

A sweep lane's TERMINAL carries one of `delegated=<n> runs=<run_id>[,<run_id>...] codex=<thread_id>[,...] lab_agent=<session_id>[,...] jev=<correlation_id>[,...]`
or `delegated=0 delegation_reason=<why>`; a TERMINAL with neither is listed by
`/omni:delegation-health` and counted as silent by `onex-delegation-accounting`. Before a sweep
read the `deleg` line of `/omni:queue-status`: a DEGRADED delegation reason is acted on like any
other, through its FIX line.

### 4b. Delegation steps, receipted (OMN-17427)

The prose routing above was skipped: at 2026-09-28 13:2xZ, 7 of 184 TERMINAL rows since the
06:24:10Z ruling carried `delegated>0` (RULING 2026-09-28T13:26:50Z lane=orchestrator-83). So every
`land-*` or `prove-*` lane of a sweep, and the cause worker, runs its
delegation through `scripts/delegation_step.py`, which calls the engine itself and writes a receipt
under `$registry_root/.claude_scratch/delegation-receipts/<lane>/`. For pure text the lab is the first responder
because it is the product (RULING 2026-09-28T13:29:22Z lane=orchestrator-83).

| Step | Subcommand | Engine chain |
| -- | -- | -- |
| D1 CI-log triage, D4 published text (PR body, comment, evidence, MSG, TERMINAL note) | `text` | GLM first (OMN-20844; `--first lab` keeps the old order): GLM through Claude Code inside a 300 s slice that keeps 150 s of the budget for the lab, then `onex delegate --locus deployed-lane` on the lab-host-a dev lane, then the same call in-process. GLM through Claude Code (`harness-delegate --harness claude-glm`, receipt `route=harness:claude-glm` with `harness_receipt`, which the audit resolves) as a ladder, `glm-5.3-flash` first and one `glm-5.3` call when flash exits non-zero, answers nothing, shows a 429 or 1302 capacity signal or fails the step's acceptance check (never a retry of flash, never two GLM calls at once; flash takes about half of the GLM slice and the escalation is skipped with a named receipt error when under 30 s is left; the second receipt carries `escalated_from`), inside a 480 s budget; a lane-probe refusal (OMN-19914) retries the same rung once; every attempt leaves a receipt |
| D2 typed decision with a fixed option set | `decide` (`--preset ci-cause\|pr-triage\|task-class`, or `--criterion` for every option) | Jev on every repository but `docs_repo`; the lab, then GLM through Claude Code, on that one or when Jev abstains, answers none_of_these or fails |
| D3 real-red fix (land lanes) | `code`, then `review` | Codex first (no model flag), then GLM through Claude Code editing the worktree (OMN-20844; a GLM run that fails or changes nothing falls through), then `onex code-edit run` on the lab, then one interim `lab_crush.py` attempt if the node route is skipped or fails (OMN-20292 pending). GLM runs `glm-5.3-flash` first and `glm-5.3` once when flash exits non-zero or leaves the worktree unchanged (a flash that changed the worktree is not escalated; both attempts keep their receipts); the lane records `accepted` or `rejected` with a reason |
| every answer received | `dispose` | `--disposition used\|edited\|discarded\|ignored --reason-code <code>` on the receipt (or `--lane <lane> --run <run id>` for a direct `onex delegate` call; or the `receipt.json` a direct `harness_delegate.py --harness claude-glm` run left, with `--lane <lane>` when the receipt names none, OMN-17427: it is refused unless its run directory holds the `prompt.md` the receipt hashed); a used or edited answer adds `--artifact pr:<owner/repo#n>\|commit:<sha>\|doc:<ref>` (where it landed; a receipt's own `repo`/`pr` or head counts), an edited one adds `--final-file <the text you used>` so the edit ratio is measured against the draft; a code `review` verdict is its disposition (OMN-20011), and an accepted one names `--head`. Each disposition is published as one `delegation-disposition-recorded` event keyed by the delegation (OMN-20012), and a disposition that missed the bus prints `DISPOSITION-NOT-PUBLISHED` and exits 1: re-run the same dispose. dispose returns within 45 s: a publish still running then prints `DISPOSITION-PUBLISH-PENDING` and exits 0, and its detached publisher writes the outcome onto the receipt. A failed attempt takes `--disposition ignored --reason-code engine_failed` and no other (OMN-20511) |
| nothing to delegate | `na` | a typed reason: owned-elsewhere, report-only, head-moved, waiting-quota, already-proven, conflict-only, engine-down (only after failed attempts) |

`delegation_step.py code` accepts repeated `--writable`, `--check NAME=COMMAND` and `--context` values, plus `--max-turns` (20 by default, 1..40). The node route needs at least one writable glob and one check; checks are split with shlex into argv and run without a shell in the worktree. Each model turn is an `onex delegate` run, on the deployed lane first; a first attempt that could not run, or whose turns all failed with no delegate run, is retried once with `--delegate-in-process`. A code-edit loop counts as one delegated subtask, with its turn run ids in `runs=` and its loop receipt as the answer. The audit resolves every turn receipt; `require=["node-turns-only"]` rejects crush sessions and node model turns without run ids, counted from the loop receipt's turns that the model answered (a turn the deployed lane refused before any model was reached is not one) (OMN-20293).

Receipts are `delegation-receipt/2` (OMN-20011): each carries the answer digest and a pointer to the
answer (`answer_sha256`, `answer_ref`, never the content), timing, the command digest, the hook session
and agent ids when the environment has them, the lane's own answer for a decision (`incumbent_given`, with
`incumbent_shown_to_engine` false because Jev is asked blind), and the lane's
disposition. `cells` refuses to print, and the ledger grammar refuses a TERMINAL that names a receipt,
while any receipt has no disposition (`UNDISPOSED`, OMN-20015). The DLG line of `audit` carries
`undisposed=<n>` and an undisposed receipt makes the lane unverified.

The disposition is also measurement (OMN-20012). `scripts/delegation_disposition.py` builds the
content-free `ModelDelegationDispositionRecorded` event with omnimarket's own model in the dispatch venv,
keyed by the delegation (an `onex delegate` run's correlation, a harness run id, a Jev correlation, a
Codex thread, code-edit loop id, or a uuid5 of a crush session), and publishes it through `node_event_emit_effect`, relaying
through the dev lane's runtime when this host's bus identity cannot write the topic. On the lab it lands as
one `delegation_dispositions` row, joinable to `delegation_events`, so used, edited, rejected and ignored
delegate output can be counted per model, task class and lane. The outcome is written back on the receipt
as `disposition_event`.

**How to ask Jev (OMN-20149; the Jev usage eval, `reports/2026-09-30-jev-usage-eval.md` in the
planning corpus, n=149 public items).** The wording moved Jev from 66% to 77%, and computing the
deciding facts in code first moved it to 92%; the engine moved the result by at most 5 points. So
`decide` asks the measured way and refuses the measured worst case:

- Every option needs a description, `--criterion '{"<option>": "what it covers, and what it does not"}'`
  (a string, or `{"what": ..., "not_for": ...}`). An option described by its own name is refused.
- A `none_of_these` option is added to what Jev sees. Jev answering it is an `abstain` with
  `abstain_reason` `none_of_these`, and the lab decides, so the lane never forces a wrong pick.
- `--question` names the fields to judge from; `--focus` says which facts to judge from and what the
  answer decides.
- For the three decisions the eval measured, `--preset ci-cause` (real, cascade, stale, base-inherited),
  `--preset pr-triage` (needs_fix, rerun, wait) and `--preset task-class` carry the eval's exact wording
  and compute the deciding facts from the lane's raw public JSON in `--facts-file`
  (`scripts/decision_presets.py`: the check kind, whether a newer copy passed, whether the base branch
  failed the same check, whether the log says cancelled, the counts and the kind of each failed check).
  Any other decision: work the deciding facts out yourself, or in code, and pass only those.
- Jev is good at a bounded choice over supplied facts and poor at finding them (61% on CI cause from the
  raw check history, 90% from computed facts). Its `rerun` against `needs_fix` call on PR triage stays the
  hardest (7 of 12 rerun cases missed even with computed facts): treat that answer as a second opinion.
- The node's visibility read is authenticated with the lane's `gh` token, passed to the child process
  only, and a public answer is cached for 10 minutes, so a burst of decisions no longer trips GitHub's
  60-an-hour anonymous cap.

For `delegation_step.py decide`, pass the required `--own-answer <option>` to record the lane's
answer in the receipt. It is NEVER sent to Jev. The receipt records `own_answer`, Jev's `answer`,
and `agrees` after the call. A typed `no_answer` result records status `abstain`, an empty answer,
`agrees: null`, and `abstain_reason`, then falls back to the lab. Abstentions appear as
`jev-abstain=<n>` in cells and DLG summaries when present; they count as neither real Jev answers
nor failures.

The lane pastes `delegation_step.py cells --lane <lane> --since <CLAIM ts>` verbatim into its
TERMINAL and returns the same line as `delegation_cells`, which the land, prove and group result
schemas require. Each drain tick runs `delegation_step.py audit` over the lanes that settled since
the last tick and puts `delegation_audited=`, `receipt_ok=`, `unverified=`, the per-engine counts and
the unverified lanes in its heartbeat STATUS; the close audits what is left and names every
unverified lane in its MSG to the orchestrator. An unverified lane is reported, not trusted: no
receipt, a typed `na` that contradicts the lane's state, a real-red fix with no code attempt, an
unreviewed code draft, or a claimed id with no receipt behind it.

## 5. Report in the operator's format

Per repo, `repo·merged/open`, followed by one line per unmerged PR: `#n class owner`. Nothing unowned,
no guesses. `drain-map.md` is that report minus the merged count. The full table goes to
`$registry_root/.claude_scratch/reports/merge-drain-<UTC>.md` and the message carries the path and the
read time printed by the script.

## 6. Close out: read the SUCCESSION line

Re-run steps 1 to 3a after the lanes return, and read the `SUCCESSION` line of that last map, not
the lanes' reports:

```
SUCCESSION: open=N dispatchable=D fix=F arm=A held=H held-stale=S in-flight=I live-owned=L pending=P armed=M stacked=T paused=U waiting=W exempt=E freed=K revalidated=R drain-done=yes|no reason=...
```

- **`drain-done=yes`** (fix=0, arm=0, held-stale=0, in-flight=0, exit 0): write the sweep's TERMINAL
  row with the merged shas, the per-class counts and the SUCCESSION line verbatim. That is the only
  line that closes a sweep.
- **`drain-done=no`**, whatever stopped the sweep (a time box, the lane cap, a usage limit): report the
  SUCCESSION line verbatim and say so in the TERMINAL (`outcome=run-ended`). No session drain is started to
  continue it, because the rolling drain is retired (OMN-20416): the landing controller's per-PR workers and its
  cause workers carry the work. A TERMINAL reporting done while the last map printed `drain-done=no` or exited 4
  or 5 is a false report.
- A sweep never ends early on an exit 4. It runs step 3a first, so whoever reads the map next inherits only
  holds that have a verdict.

## 7. The merge pulse and the recurring tick

The recurring tick is a check, never a status ping. On every firing it **runs the merge
pulse first** (OMN-19852, RULING 2026-09-28T20:32:17Z lane=orchestrator-83) and speaks on RED:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/merge_pulse.py"          # one line: verdict, reason first, then the fix
python3 "${CLAUDE_SKILL_DIR}/scripts/merge_pulse.py" --json   # the typed record
```

The pulse reads the same repository scope as the merge sweep: `merge_pulse.read_out_of_scope` calls the sweep's
`sweep_rules.load_out_of_scope` over `merge-sweep/sweep_scope.json` (OMN-17427), and keeps no list of its own. A repository
ruled out there (today `infra_repo`) is left out of every RED and AMBER finding and out of the fix that leads
queue-status's NEXT: its armed-red stall, dev head, floor breach, order edges and PRs. One line under the pulse,
`out of scope: <repo> armed=<n> red=<n> ...`, names it with the counts it held. An unreadable scope file is AMBER
(`sweep scope: ...`), never an empty scope.

The pulse also checks the installed plugin against `scripts/hotpatch_markers.json`, reports missing markers as RED with a PR-state-aware fix, and flags open priority plugin PRs without marker entries as AMBER.

It reads merges in the last 30 minutes and the 30 before from fresh canonical-clone history only,
the drain's own merged TERMINALs, each landing repo's `dev` head against its required contexts, the
drain heartbeat age, the arm-step candidates of the last map refresh, the drain's lanes by outcome
and order reason, the lab pool's free and proving slots, and the open-PR trend. A fresh clone-sync
zero remains zero; a stale or absent sync is AMBER with `no GitHub search fallback`. Required-context
definitions (branch protection plus rules) are cached per repo for six hours in
`<state-dir>/required-contexts.json`; check-runs and push-runs are never cached. Exit 0 GREEN, 1 AMBER
(an input unreadable, a gh budget exceeded, a noisy external gh caller, the rate halved, or a required
dev-head context still running), 2 RED. The tick
never answers "nothing needs you" on a RED or AMBER pulse: it prints the pulse line and dispatches the
fix it names in the same turn. RED is any of: zero merges in 30 minutes while dispatchable or green
PRs exist (fix: land lanes for them); a landing repo's `dev` head red on a required context, or its latest post-merge push CI run red (invisible on PR heads; fix: an
opus diagnosis lane); drain heartbeat older than 20 minutes or no open drain run (fix: relaunch with
`supersedes-claim=`); free lab slots while PRs wait on the lab (fix: prove lanes, and `pool_max`);
a `waiting_order` edge whose parent is merged or closed (fix: a fresh land lane for the child). An
order parent resolves from the PR-watcher state first, then a squash subject ending `(#N)` on the
parent repo's canonical-clone `origin/dev` or `origin/main`, and only then one budgeted REST call.
The watcher state is loaded once per run. The hook-events stall view prints `events: not yet` until
the hook-events projection is live. `queue_status.py` runs the same pulse and a RED becomes a
DEGRADED reason with its fix leading NEXT.

Every `gh_api` invocation increments `PulseInputs.gh_calls` under a lock. The default per-run budget
is 40 (`ONEX_PULSE_GH_BUDGET` overrides); over budget is AMBER `gh-budget`. The summary and JSON
record print the count, budget, and top three lanes from the shared gh-shim log. That log is read
from `ONEX_GH_CALLS_LOG`, else `$ONEX_STATE_DIR/gh-calls.log`, else
`$registry_root/.onex_state/gh-calls.log`, using only its last 4 MB and rows from the last 30 minutes.
Malformed rows are skipped and refused calls are counted separately. A lane other than this pulse's
own over 150 calls (`ONEX_PULSE_GH_CALLER_BUDGET` overrides) is AMBER `gh-callers`; a missing log is
informational, while an unreadable log is an unread input.

Then, in the same turn, it reads:

1. the live drain's last ledger row and its planned end (the run's CLAIM or its launch MSG);
2. the live open-PR count from the fresh PR-watcher state (`LocalState.open_counts`: no drafts and no
   repository `merge-sweep/sweep_scope.json` rules out, OMN-17427), printed with
   `drafts=N (excluded) out-of-scope=N (excluded)` beside it; if that is unavailable, the drain map's
   open count, counted the same way, with the watcher freshness reason printed. If neither local
   source exists, stop with an untrusted read. Never call GitHub search from the tick;
3. the last `SUCCESSION` line the drain printed;
4. the landing measurement line (OMN-19852), printed verbatim in the tick's report:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_landing_metrics.py" --one-line`. It is the same
   line queue-status prints; within 5 minutes of the last recorded window it re-prints that record
   with `(cached)` and makes no GitHub call. An `unavailable:` line is printed as it is and never
   blocks the tick.

Then exactly one of:

- open PRs remain: report the live count, the landing line and the last `SUCCESSION` line, with the pulse
  line when it is RED or AMBER. Start nothing: the session drain is retired (OMN-20416), and the fix a RED pulse
  names goes through the landing controller (its per-PR and cause workers, `/omni:landing-controller`) or a lane the
  operator names;
- the last `SUCCESSION` line is `drain-done=yes` and the live count agrees: report the work done, citing the
  `SUCCESSION` line and the count with its read time.

"No open PRs", "nothing to do" or "all held" is never an answer on its own: it carries the live count,
its positive control and the SUCCESSION line from the same turn, and a held count carries its
held-stale count.


## Known friction (from prior runs)

Read this before step 1. Each line gives the symptom, the correct move, and the ledger row behind
it, cited as `<row timestamp> lane=<lane>` because a roll renumbers every line. Find a row with
`grep -rn '<timestamp>' $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md $registry_root/docs/tracking/archive/`.
Record new friction with the `friction-record` skill (`/omni:friction-record`) and add a line here
in the same PR.

- **The Claude session drain burned lanes for few merges, and is deleted.** On 2026-09-28 the drains started 95 lanes for 3 merges, on 2026-09-29 202 agents for 1 merge, and on 2026-10-03 `repo-drains-2a21b` ran 39 lanes for 2 merges and wrote a TERMINAL asking for a successor that never ran. The fix is the shared-cause worker: one lease per cause key, two attempts, a fleet cap on cause workers, one fixer HOLD row to stop it, and `usage.json` per run so the cost per merge is measured. `workflows/repo_drains.js` and `/omni:drain-restart` are gone. → TERMINAL 2026-10-03T18:49:02Z lane=repo-drains-2a21b, RULING 2026-10-03T20:46:24Z lane=orchestrator-de99, OMN-20416

- **The pulse called a ticking landing controller "no open drain run".** R3 read only drain-run rows, so after the drains were retired it printed RED with FIX "start /omni:merge-drain" while the controller ticked OK in mode=act. R3 now takes the newest mode=act OK/DEGRADED line of `~/.local/state/omni/landing/ticks.jsonl` (`--landing-state-dir`, `LANDING_STATE_DIR`) as the heartbeat, and its fixes name the controller kickstart, never a drain launch. FRICTION 2026-10-01T03:32:16Z lane=qdiag-202610010215

- **`delegation_step.py code` read a successful Codex draft as a failed sandbox** when the draft read this script, whose source quotes the sandbox failure markers; the markers now count only in stderr, failed commands and patch events. → OMN-20173
- **A lane claiming under the drain's own ticket owned every PR carrying it.** `claim_matches` let a CLAIM with no `pr=` field own any PR whose title or branch carried the CLAIM's ticket. The drain, the orchestrator and every harvest or report lane claim under the umbrella ticket OMN-17427, which many landing-machinery PRs carry too, so on 2026-09-28 docs-repo#821, omnibase_core#1800, plugin-tooling-pkg#75 and infra_repo#1725 read live-owned by friction-harvest-83 and friction-report-83, lanes that never touch a PR, and no lander went to them. A ticket an open CLAIM of a dispatcher lane carries owned no PR by ticket alone; the CLAIM had to name the PR, its branch or its worktree (since OMN-19998 no ticket owns a PR, and `umbrella_tickets` is gone). → CLAIM 2026-09-28T04:20:34Z lane=drain-throughput-83v, OMN-17427
- **Sibling lanes that each CLAIMed one shared ticket owned every PR under it.** The validator burn-down wave-1 lanes all CLAIMed OMN-20201 with no `pr=` field, so each read as the owner of every sibling's PR, and `local_worktrees` mapped a branch only to its ticket directory (`worktrees/OMN-20201`), which every sibling's CLAIM names. `umbrella_tickets` now also returns any ticket that CLAIM rows of two or more lanes carry in the window (open or closed), and `local_worktrees` maps a branch to its exact worktree path, matched as a whole path token (`names_path`). (OMN-19998 later removed the ticket match for a ticket one lane claims, too.) → FRICTION 2026-10-01T01:58:01Z lane=vburn-W1-B5, OMN-19846
- **Bot cascade PRs were never landed.** Every bot-authored PR that was not a change-control companion was classed `bot`, "release train / bot", and reported as exempt, but the release train lands only release PRs, so dependency bumps, contract-pin advances and census refreshes sat open: twelve on 2026-09-28, six green and unarmed for up to a day, and three pin advances plus two census refreshes of one series each open at once in omnibase_infra. Only a release PR is `bot` now; the newest PR of a series routes like the operator's own and the older ones are dispatched to be closed as superseded. → CLAIM 2026-09-28T04:20:34Z lane=drain-throughput-83v, OMN-17427
> - **GitHub reads spent the operator's own bucket.** Every read a lane made (`gh pr view`, `gh pr checks`, `gh api` GETs, the check-run pages) went through the operator's login, which is the one 5,000/hour bucket that merges and arming also need, and the bucket ran out. The gh shim at `~/.local/bin/gh` now sends those read shapes to the read-only App bot-app's installation token. It is on for every caller through `~/.config/omni/gh-read-routing.env`, and each call is logged with `identity=app` in `~/.cache/omni/gh-usage/`. Writes (`pr merge`, `pr ready`, `run rerun`, `api -X POST|PUT|PATCH`, a GraphQL mutation) stay on the operator. Do nothing special for a read made through `gh`. A script that calls the API without gh uses `GH_TOKEN=$(~/.omninode/bin/onex-gh-reader-token token)`, and `~/.omninode/bin/onex-gh-read <gh args>` is a gh that refuses writes. A read logged `operator-fallback` means the mint failed: record friction, and never work around it with the operator token. → CLAIM 2026-09-27T19:06:52Z lane=github-reads-app-83, RULING 2026-09-25T14:18:52Z lane=merge-drain-83 (Q3)
- **A change-control gate red was called real red.** The map called a PR a cascade only when 3 of the 4 core contexts were red and nothing else was. The eligibility gate polls 1500s for the PR's Evidence-Source companion to merge, fails closed, and is never re-run after the companion lands, so 9 of 24 "real-red" PRs were red on that gate alone or beside followers it caused (a coverage census refusing because the test shards skipped), and the map named the follower as the PR's red. `drain_map.py` now classifies any red gate as a cascade and names the companion and its state in the action: an open companion lands first, a merged one means rerun the parent's eligibility run whole. → 2026-09-27T01:50:03Z lane=repo-drains-83i-diag
- **Companions with no open parent were reported forever.** The map called every bot-authored `onex_change_control` PR naming a parent `companion`, "lands with its parent", even when the parent had merged or did not exist (an observation append), so the companion class held the open total flat for two hours and no lander ever went to the orphans. `drain_map.py` now classifies them `orphan-companion` and dispatches a lander. A public-repo-hygiene exit 2 on an OCC PR is cleared by updating its branch onto `dev`, never by a rerun, which replays the PR's own old caller. → 2026-09-26T22:28:41Z lane=repo-drains-83i-diag
- **Orphaned PRs.** Lanes dispatched per PR from partial lists left 3 PRs with no owner, and the operator found them first. Build the step 2 owner map from the full inventory before any dispatch, and dispatch the unowned first. → 2026-09-23T00:57:51Z lane=friction-to-skills item=F1, 2026-09-22T19:17:00Z lane=ownership-inventory, docs-repo#656, OMN-19192
- **Characterising unread PRs.** The omnimarket PRs were called "bumps" without being read. Read the title, body and files before describing any PR. → 2026-09-23T00:58:02Z lane=friction-to-skills item=F2
- **Answering from a snapshot.** A live question was answered from the 18:41Z handoff table. Every state answer comes from a read taken in the same turn and carries its read time. → 2026-09-23T00:58:02Z lane=friction-to-skills item=F3
- **Decision asks that were not questions.** Decision B went out as a framed option, and the answer needed interpreting (RULING 2026-09-22T18:59:42Z lane=manual-merge-drain-0425). Ask one plain yes/no question with the default stated. → 2026-09-23T00:58:03Z lane=friction-to-skills item=F4
- **Foreground verification reads.** The foreground orchestrates only. Send every verification read to a read-only background lane. → 2026-09-23T00:58:03Z lane=friction-to-skills item=F5
- **A restart or usage limit kills every lane.** Dangling CLAIMs were found by hand, and ledger-reconcile's default 6h floor hides a CLAIM killed minutes ago. Run the `session-resume` skill (`/omni:session-resume`) before step 1 of any resumed drain. → 2026-09-23T00:57:51Z lane=friction-to-skills item=F6, 2026-09-23T00:57:52Z lane=friction-to-skills item=F16
- **Double dispatch.** One finding forwarded to two lanes gave omnimarket#2783 two owners and duplicate companions onex_change_control#10851 and #10853. Send a finding to the one lane that holds an open CLAIM on the target PR, or to a new lane if none does. Never send it to two. → 2026-09-23T00:58:03Z lane=friction-to-skills item=F7, 2026-09-22T22:00:46Z lane=occ-shadow-timeout, 2026-09-22T23:53:37Z lane=market-shadow-timeout
> - **A message to a busy lane is not delivered until its turn ends, not "at its next tool round."** CORRECTED by the CORRECTION row 2026-09-23T02:09:09Z lane=friction-f8-correction: the orchestrator sent 8 SendMessage calls to chain-3963-3939 over about 6.5 hours (scope changes, a pause, a disarm notice, a hold), every send returned success, and the lane received none of them while it was working — all 8 landed at once only after it wrote TERMINAL and went idle, by which point it had merged 5 more PRs (omnibase_infra#3885, #3943, #3947, omnimarket#2766, #2730). Idle lanes (reconciler-fix, small-repos-drain, market-drain) received messages promptly. A successful send is not a delivery receipt. To pause a repo, disarm the PRs yourself (`gh pr merge <n> --repo <r> --disable-auto`) and read back `autoMergeRequest`, and/or write a ledger RULING/HOLD row every brief requires re-reading before each merge — never rely on a message reaching a running lane. This is Claude Code harness behavior (SendMessage to a busy background agent queues until it next goes idle), not a repo defect; design around it, do not file a repo ticket for it. → 2026-09-23T02:09:09Z lane=friction-f8-correction (correction), 2026-09-23T00:57:52Z lane=friction-to-skills item=F8, 2026-09-22T22:19:08Z lane=chain-3963-3939, 2026-09-22T20:31:55Z lane=m4-c9-probe, 2026-09-22T21:10:18Z lane=m4-c8-probe
- **Silent lanes.** chain-3963-3939 wrote no row for 1h29m while two PRs merged. Brief every lane to write a STATUS row at each merge, and treat a lane silent for 45 min as unknown, not as progressing. → 2026-09-23T00:57:52Z lane=friction-to-skills item=F8
- **Re-sent final reports.** market-drain re-sent its report and dropped the #2324 item, so a second lane was needed. Track each open question to one owner, and require a new CLAIM for any item handed over after TERMINAL. → 2026-09-23T00:57:52Z lane=friction-to-skills item=F9, 2026-09-22T20:31:54Z lane=market-2324-assess, 2026-09-22T21:16:41Z lane=market-drain
- **Runtime merges stacking unexercised.** For about 3.5h, 4 runtime merges landed with no PASS lab receipt while the lab-host-a host was saturated. Each runtime PR is now exercised before it merges, on its own head, by the lab-pool rule (RULING 2026-09-27T14:31:58Z lane=orchestrator-83), so a runtime PR no longer waits on the dev head's lane-j receipt. The post-merge lane-j receipt still gates staging: if those receipts are failing, run `lab-rebuild-triage`. → 2026-09-23T00:57:52Z lane=friction-to-skills item=F10, 2026-09-22T23:22:55Z lane=lab-rebuild-diag, 2026-09-23T00:40:46Z lane=infra-release-cut
- **Two lanes, one PR or worktree.** land-3972 rebased a live lane's worktree. The step 2 ownership check covers worktrees too. → 2026-09-22T21:36:45Z lane=c15-reroute-fix-r2
- **One runtime token held green runtime PRs after the ruling that ended it.** The drain handed one runtime token to one lane at a time and let only that lane enqueue a runtime-affecting omnibase_infra PR, behind a PASS lane-j receipt for the current dev head. After the RULING 2026-09-27T14:31:58Z lane=orchestrator-83 it still returned CI-green omnibase_infra#4206 and #4188 as `waiting_order order_reason=token`. the drain's workflow applied the lab-pool rule from then on (RULING 2026-09-27T14:31:58Z lane=orchestrator-83; the workflow is deleted, OMN-20416): no token, each runtime PR enqueues on a PASS readback for its own head, and a missing readback gets one prove lane. A running drain keeps the copy it loaded; its successor picks up the rule. → 2026-09-27T16:12:27Z lane=drain-runtime-token-83, 2026-09-27T15:29:23Z lane=land-omnibase_infra-4206-83r, 2026-09-27T15:28:31Z lane=land-omnibase_infra-4188-83r
- **Two drain agents worked the same PR and worktree.** A restarted owner map treated still-running per-PR lanes as dead and duplicated omniclaude#2350 and #2353. `pr-land` now starts every pass with its read-only claim guard and refuses live foreign registry, ledger or correlated worktree ownership; the drain map still decides dispatch ownership before the lane starts. → 2026-09-25T21:10:49Z lane=orchestrator-83
- **Draft autobind DECLINED read as a dropped mint.** This is expected for a draft (step 3). → OMN-19210 inventory, 2026-09-22T22:48:55Z lane=prosthetic-skills
- **Fleet CI timeouts under load.** infra_repo Repo Scripts DB Tests and pre-commit hit their caps on unrelated PRs from 21:00Z. Rerun once, then report the class instead of re-dispatching fixers. → 2026-09-22T23:03:11Z lane=m4-c10-probe, 2026-09-22T23:38:46Z lane=m4-c12-probe, 2026-09-23T00:13:21Z lane=m4-c13-probe, OMN-19209
- **Liveness guard refuses a stand-down.** A message naming another lane reads as a death declaration. Refer to peers by row timestamp, not by lane name. → 2026-09-23T00:58:03Z lane=friction-to-skills item=F17
- **Owner map matched PR numbers only.** A lane whose CLAIM names a ticket, not a PR, held omniclaude#2322 and omnibase_infra#4008, and a companion (onex_change_control#10943) of a claimed PR, yet all three read as unowned and would have had a second lane put on them. Step 2 now matches by ticket, branch, worktree and companion, over the archive rolls as well as the live ledger, with the canonical dangling definition (`drain_map.py`). → 2026-09-23 functional test of this skill, OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **"Real red: anything else" swallowed four classes.** Green-unarmed, stacked, parked and collaborator-authored PRs all fell into real red and got fixer lanes. Step 3 now has a row and a move for each, and allows the title as evidence for parked state only. On the same live state the old text would dispatch 19 to 22 lanes and this one dispatches 1 (the old count grows as PRs open; reads: 19 vs 1 at 16:25Z, 21 vs 1 at 16:42Z, 22 vs 1 at 16:50Z, all 2026-09-23). → OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **The step 4 hold check missed holds in force.** The runtime-merge pause was a STATUS row, and the `ledger-msg` inbox reads only MSG and HOLD rows with an `id=` (0 rows that day). Step 3 now runs the canonical hold check (labels, HOLD rows, naming rows, merge pauses), and step 4 re-runs it before every dispatch and arm. → OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **Dead citations and stale numbers.** The ledger rolled at 2026-09-23T14:00:47Z and every `ledger:<line>` pointer here pointed past the end of the file or at an unrelated row; the lane cap read about twelve (the ceiling is 15 since 2026-09-22); bulk operations named no throttle; "the four change-control contexts" were never named; "owned" had no definition. Citations are now row timestamps, and steps 2 to 4 carry the rest. → OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **The "preferred" reconciler disagrees with the drain's owner map.** `ledger_reconcile.py` pairs TERMINALs to CLAIMs last in, first out and one to one, and has no `RELEASE re=` or `claim-lane=` closer, so on a multi-claim or released lane its dangling list differs from `drain_map.py`'s. Step 2 now says so, and `drain_map.py`'s owner column decides dispatch until the reconciler is fixed. Step 3 also states the window for id-less legacy HOLD rows (live ledger and today's roll only). → OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **`drain_map.py` held or owned 35 of 36 open PRs.** On the 17:40:17Z read the runtime-merge pause held every omnibase_infra PR (16) and blocked their fixes too, CLAIMs from lanes dead for days (codex lanes of 2026-09-13 to 21, chain-r2 after the 14:52:23Z restart) counted as owners, and report text ("DRAFTS HELD: ...", "is body-held") plus id-less HOLD rows from earlier days counted as holds, so the orchestrator reported one dispatchable PR. The pause now binds only runtime-affecting PRs (the step 6 trigger, with controls) and only their merge, an owner must be live (a row or a registry heartbeat within 45 minutes), item 3 matches instructions only, an old id-less HOLD prints `stale-legacy, verify`, collaborator green PRs are armable, and the summary prints one bucket per PR. → 2026-09-23T17:43:32Z lane=merge-drain-7f, 2026-09-23T18:06:20Z lane=drain-map-fix, OMN-19346
- **Owners older than session-resume's window.** `drain_map.py` applied `--since-days` to roll file names, not row timestamps, so the 2026-09-16 split brought in CLAIMs from 09-08 to 09-15 as owners of infra_repo#1463, registry_root#408 and omnibase_infra#3247. The action read `owner silent >45m: session-resume first`, yet `session-resume` never searches that far back, so neither skill would work them, and the drain dispatched onto them by hand. Step 2 now filters CLAIMs by row timestamp to the reconciler's window and states it; a draft whose last TERMINAL reports it held with the gap named (2026-09-23T17:52:19Z lane=drain-c9-pair, no C9 PASS) classifies draft-unfinished instead of taking a fresh lane. → 2026-09-23T17:51:36Z lane=merge-drain-7f, OMN-19230 lineage; fixed 2026-09-23 by the omni-skill-fixes pass
- **A resumed session's closing row read as closing the session.** `session-resume` closed a stopped lane's CLAIM with a TERMINAL whose `lane=` was the resuming session and whose `claim-lane=` was the stopped lane. `drain_map.py` read every closer's `lane=` as closed, so the live session CLAIM (and every PR it owned) dropped out of the owner map the moment it closed any dead lane, while `session-resume`'s own reader still listed it. A closer carrying `claim-lane=` now closes that lane only, and `session-resume` writes the row under the stopped lane. → 2026-09-24 integration run of the orchestration skills (staging build), OMN-17427
- **The session's own PR stayed owned after its handoff.** The orchestrator's session CLAIM carries the goal ticket, and the goal PR carries the same ticket, so the owner map matched the live session CLAIM to the PR by ticket until the session ended; no TERMINAL the handoff could write released it without ending the session. A `handed-off=<repo>#<n>` STATUS from the claiming lane now ends that CLAIM's ownership of the PR. → 2026-09-24 integration run of the orchestration skills (staging build), OMN-17427
- **The auto-merge arm-gate label read as a merge hold.** On the 2026-09-25T11:51:33Z read `drain_map.py` classed 54 of 89 open PRs held, 43 of them by the hold label family's auto-merge member alone (`holds.txt` of `merge-drain-83e-2026-09-25T113859Z`), which lanes apply on handoff so the auto-merge workflow does not arm the PR while the lander merges it on the exact head. The drain could not see the landers' queue, and a lander merging a labelled PR looked like a hold violation. That label now routes the PR to its lander, never armed (`WOULD-LAND-NO-ARM`); every other label of the family, and any HOLD row, still holds. `pr-land`'s pause check prints it as `ARM-OFF`, not a stop. → 2026-09-25T12:11:36Z lane=hold-label-reconcile-83, OMN-17427
> - **The map stalled on the GraphQL bucket while REST had thousands left.** `drain_map.py` read every PR with `gh pr view`, the default branch with `gh repo view`, changed files with `gh pr diff` and the inventory with `gh search prs`, all GraphQL, so on 2026-09-25 the repo drains slept on a GraphQL reset twice. It now reads PRs, the default branch and checks over REST, changed files from PR heads fetched into the canonical clones, and caches check-runs by head sha. → operator ~14:53Z 2026-09-25, RULING 2026-09-25T14:34:28Z lane=merge-drain-83, OMN-19611
- **A routed PR still read unowned.** The landing identity routed knowledge-base#88 and omnibase_infra#4093 to live partition landers by MSG at 12:01Z, but the 12:23Z owner map counted only CLAIM rows and the PR claim registry, so both appeared dispatchable again. A concrete-lane MSG naming `repo#n` now owns the PR while its recipient is live, until that lane terminates, reports the PR merged or closed, or hands it back. → TERMINAL 2026-09-25T12:25:30Z lane=merge-drain-83e (the row originally cited as ledger line 3870), OMN-17427
- **A MSG that named a PR as context made its recipients the PR's owners.** The reader routed any concrete-lane MSG whose text spelled `repo#n`, so the orchestrator's MSGs held registry_root#488 for three lanes (02:56Z to 03:57Z on 2026-11-06) and omnimarket#5205, #5186 and #5206 (17:30Z and 17:42Z), the upstream of seven pull requests among them, each until a hand-back row. A MSG routes a PR now only through its own `owns=<repo>#<n>` cell; the recorded 17:42:32Z row routes nothing and the same row with the cell routes. → OMN-22731, OMN-22478
- **The done signal inverted or omitted active wait states.** `drain-done=yes` was printed with open PRs pending, armed, stacked, live-owned or paused, a PR with one stale hold beside a valid one was not held-stale, and `X before Y` freed Y while X was open. Count every active wait as in-flight, mark a held PR stale when any hold is stale, and read X as Y's dependency. → MSG 2026-09-26T01:55:56Z lane=never-passive-skill-contract-verify-83, OMN-19691
> - **A drain ended on its clock with dispatchable PRs left, and its holds went unexamined.** The overnight
>   session cron fired the drain tick every 7 minutes; each answer was "no duplicate drain, the drain runs
>   until 02:00Z", nothing was queued after 02:00Z while about 74 PRs were open in omnimarket and
>   omnibase_infra (gh pr list at 00:57Z), and 53 PRs held in `repo-drains-83-d/r2/holds.txt` were never
>   re-checked, some by conditional instructions from lanes long gone. The contract at the top of this
>   file, step 3a (`hold_revalidate.py`, `--freed`), the `SUCCESSION` line with exit 4 on held-stale,
>   step 6's successor MSG and step 7's succession tick answer it. → MSG 2026-09-26T00:59:33Z
>   lane=orchestrator-83, RULING 2026-09-26T01:01:16Z lane=orchestrator-83, OMN-19691
- **Lanes that ended on a wait were re-dispatched onto the same wait, and a dead lane's pause bound for three days.** At 2026-09-27T17:49Z queue-status reported 11 dispatchable PRs with no lane; 7 had a landing lane that day that ended `outcome=waiting_ci`, `waiting_lab` or `waiting_order` (omnimarket#2955 had three such lanes), and omnibase_infra#4215's merge still waited on runtime-train-83's 2026-09-24T22:40:18Z pause. Step 3b now keeps a waiting PR in flight until its recheck trigger fires, and expires a lane-written pause 12h after its lane's last row. Replayed at the 18:08:50Z ledger read: dispatchable 11 to 7, `waiting=7`, `paused=3` to 0. → CLAIM 2026-09-27T17:58:09Z lane=drain-waiting-pause-83, OMN-19852
- **Most of the live-owned bucket was false.** Replayed at the 2026-09-27T05:48:05Z ledger read, the map put 49 PRs live-owned and only 8 were real: 23 were owned by `orchestrator-83 (routed pr-ref)` (child lanes reporting to their parent, 3 of them companions inheriting it), 13 by the per-PR land lane `land-omnibase_spi-321-83k`, whose CLAIM carried the umbrella ticket OMN-19766 and whose `pr=` value was read on into `ruling=...:4198`, and the rest by PRs cited in CLAIMs' OUT OF SCOPE lists or handed-off clauses and by a `ticket=` quoted in prose. At 06:5xZ the live read went from 28 live-owned to 4, all real. Step 2 now matches only a CLAIM's own fields, never a scoped CLAIM's ticket beyond its PRs, never an excluded PR, and never a MSG to a dispatcher lane. → diagnosis of drain 83k (workflow wf_f7efc463-8ea, 2026-09-27), CLAIM 2026-09-27T06:20:53Z lane=drain-map-liveowned-fix-83, OMN-19846
- **A descriptive "standalone" mention held a PR it never instructed anything about.** Item (3)'s "standalone" alternative fired on any merge/land/arm word within 40 chars of "standalone" with no negation required, so `omnibase_infra#4154` was held on two rows' (2026-09-26T07:22:01Z lane=repo-drain-omnibase_infra-pr, and 2026-09-26T08:25:45Z lane=repo-drain-omnibase_infra-pr, quoting the first back) "landing there or as a fast standalone PR, whichever the omnimarket drain judges faster" -- prose describing where an unrelated omnimarket companion fix could land, not an instruction about `#4154` at all. A bare "standalone" match with no negation anywhere in its own clause (`descriptive_standalone()`) is now dropped; a real "not standalone" / "do not merge ... standalone" still holds because its clause carries a negation, even when that negation is not immediately adjacent to the merge/land/arm word. → CLAIM 2026-09-27T09:44:26Z lane=standalone-hold-fix-83, OMN-19846
- **Per-PR STATUS rows paused a whole repo, and a status row's order made a companion and its parent wait on each other.** pr-land's pause check matched "no merge" in five lanes' own STATUS rows about other PRs (ledger 8261, 9348, 9584, 9754, 10053) as onex_change_control merge pauses, so every landing lane stopped until it read each row by hand; and a STATUS row saying omnimarket#2968 "must land after" two PRs held #2968 while its companion onex_change_control#11522 was reported "lands with its parent". A repo pause is now one matcher (`pause_sentence`, shared with `pause_check.sh`) that needs a present-tense pause instruction in a row with no `pr=`/`state=` field, scoped to the repo; STATUS joined the report types that never hold; companions land first (`LANDING_ORDER`). → STATUS 2026-09-27T14:42:22Z lane=occ-merge-now-83, OMN-19852
> - **The CLAIM step still could not write its own row after the header-CLI-flags fix.** repo-drains-83y/83z's CLAIM was refused three more times on real values: no `--actor`/`--model` (attribution guard), then `--actor`/`--model` with no rule-4 cost sentence (`--est-hours`/`--displaces` absent), then `--displaces nothing` (a refused placeholder). The TERMINAL close step had the matching gap: no `--friction`, which the grammar also requires. The CLAIM and TERMINAL prompts now compute every required value from a real read (a `date -u` clock read and END for `--est-hours`, one `gh search` count for `--displaces`, `friction=none` unless a real item was found) and name every flag explicitly, never leaving one for the dispatched agent to guess or omit. → FRICTION 2026-09-28T07:38:20Z lane=orchestrator-83, MSG 2026-09-28T07:38:20Z-orchestrator-83 to=drain-script-reconcile-83, OMN-17427
