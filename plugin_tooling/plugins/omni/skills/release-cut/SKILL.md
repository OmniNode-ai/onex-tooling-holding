---
name: release-cut
description: Cut a package release of one repo through the release train (the repo is the skill's input; omnibase_infra, omnibase_core, omnibase_spi or any other repo the train policy declares). What counts as ready comes from that repo's lab_evidence in config/release_train_policy.yaml. For lane-j repos, the head the release will tag must carry a PASS lane-j lab receipt, at the head itself or at its nearest runtime-affecting ancestor; lane-j-or-instance-lanes accepts a PASS from lane-j or from the receipt lane of any deploy-agent instance that proves the repo, in that order. The release PR stays in draft whenever dev moves past runtime merges without a PASS. For lab_evidence none repos (omnibase_core, omnibase_spi), no receipt can exist and the premise is green dev CI. Use when a ruling says "cut the release when it's ready", or when a downstream PR is unresolvable against every published version.
prosthetic: true
replaces_when: "release-train-nightly.yml evaluates the lab-receipt premise again at the release PR's merge time, not only at decide time, and refuses or re-drafts the PR itself when dev has moved past runtime merges without a PASS, on two consecutive cuts that no lane has to guard by hand. On 2026-09-22 the train decided CUT at 4aca83d9 and opened omnibase_infra#3973, and dev then moved past three FAIL receipts before anyone could merge it (ledger row 2026-09-22T22:33:45Z lane=infra-release-cut)."
restored_from: "none. New process, captured from the 2026-09-22 infra-release-cut run (ledger rows 2026-09-22T19:02:01Z, 2026-09-22T19:55:26Z, 2026-09-22T22:33:45Z and 2026-09-23T00:40:46Z, all lane=infra-release-cut). The old omniclaude release skill (af13e7056) describes a tier-ordered bump pipeline, which is a different flow"
ticket: OMN-19221
---

# Release cut (prosthetic)

The repo to cut is this skill's input: take it from the request (the ARGUMENTS line, or the words of
the ruling). Set it once, on its own line, and use the names below everywhere:

```bash
REPO=omnibase_core
R="OmniNode-ai/$REPO"
```

The train (`release-train-nightly.yml`, which lives in `omnibase_infra` and decides for every repo
declared in `config/release_train_policy.yaml`) **decides** and opens a changelog-only release PR
in the target repo. Merging that PR triggers the repo's `auto-tag-on-merge.yml`, which tags
**whatever dev holds at merge time**, and the release workflow then publishes to PyPI and
fast-forwards `main`. That last fact is the hazard. The train checks its premise when it decides.
Nothing checks it again when the PR merges.

`cut_facts.sh` and `ci_premise.py` live in this skill's `scripts/` directory, with their offline
tests in `tests/`. `trigger_for_sha.sh` and `read_receipt.sh` have exactly one copy, in the
`lab-rebuild-triage` skill's `scripts/` directory: this skill and `cut_facts.sh` call that copy, so a
fix there reaches both skills and there is nothing to keep in sync. All four only read. Never append `2>/dev/null` to any of them,
and prove every zero with the positive control each one prints.

## 1. Authority and claim

A cut needs a RULING row that authorizes it (for example the RULING of 2026-09-22T18:59:42Z
lane=manual-merge-drain-0425, "cut the infra release when it's ready and needs to be"). Your CLAIM
cites it as `consent=docs/tracking/ROLLING_WORK_LEDGER.md:<line>` (rule 18) and also by its row
timestamp, because a line number moves when the ledger rolls. A ruling for one repo does not
authorize another. A release is not a deploy. No prod, grant, staging repin or `lab-host-a` mutation is
in scope.

## 2. Needs to be, and the policy row (measure it)

```bash
SCRATCH_DIR="$(mktemp -d)"
bash "${CLAUDE_SKILL_DIR}/scripts/cut_facts.sh" "$REPO" "$SCRATCH_DIR"
```

It prints the repo's policy row (`mode`, `lab_evidence`), the latest release tag (the highest
`vX.Y.Z`, as the train takes it, not `git describe`), dev's head and declared version, and the
unreleased count scoped the way the train scopes it: `git log --no-merges <tag>..origin/dev -- src
pyproject.toml`, with the train's bookkeeping subjects (the post-release dev version bump and the
release PR itself) excluded. A commit count over the whole tree overstates the need. A repo the
policy does not declare is refused, as the train refuses it. `mode: report_only` means the train
will report the repo and not cut it: stop and say so.

Name the concrete need, for example a downstream PR that no published version can resolve, and set it
for the run: `export CUT_NEED="<repo>#<n>, OMN-nnnn or <package>>=<version>: what it cannot do without this release"`. The script
judges it against the unreleased count (`cut_facts.sh --judge-need NEED COUNT` runs the judgement alone), and prints `NEED ADMITTED: <need>` or
`NEED REFUSED: <reason>` and refuses no need, a placeholder (`none`, `tbd`, `it is ready`), a need that names
no ticket, pull request or pin, and a repo with nothing unreleased. A refused need withholds the dispatch line of
step 4; nothing else in this skill dispatches (OMN-18595, RULING 2026-10-07T18:29:28Z lane=orchestrator-716d: no need, no cut).

## 3. Ready: branch on the policy's `lab_evidence`

`cut_facts.sh` has already evaluated the premise and printed a `PREMISE` line. Read it by branch.

**`lab_evidence: none`** (omnibase_core, omnibase_spi, omnimemory and the other library repos). The
repo has no lab lane and no `runtime-rebuild-trigger.yml`, so **no receipt is keyed by any of its
shas, ever**. Do not wait for one and do not run `lab-rebuild-triage` for it. The premise is green
dev CI on the train's gating commit. The script reads every check-run copy on dev's head (not the
rollup) and the workflow runs on the same commit, and judges them with `ci_premise.py`. One check
name can come from many workflows (on omnibase_core dev 3dbaf248, `occ-preflight / eligibility`
comes from 9 of them), so each copy is keyed by (workflow, check name) and only the newest copy
within a key counts; a green copy from one workflow never hides a red one from another. An older copy
counts as superseded only when it completed before the newest copy started: a red copy that overlaps
the newest one, ties it, or has no `started_at` or `completed_at` is a sibling (matrix legs under one
static job name), not a rerun, and makes the premise `NOT_READY`. Any copy
or workflow run that is still queued or in progress is not green, whatever its timestamps. The
newest run of each workflow (per event) must itself have concluded success, skipped or neutral: a
run that ended `startup_failure`, `action_required` or `failure` makes the premise `NOT_READY` even
with no red check-run copy, because such a run can create no jobs at all.
`PREMISE READY` only when every key's newest copy is success, skipped or neutral and no such run
exists, `NOT_READY` otherwise, and `UNREADABLE` when it read zero check-runs (an empty read is never green). The train names its gating commit as
`candidate_sha` in the decision artifact (step 4); once you have it, run `cut_facts.sh` again with
that sha as its third argument to judge that exact commit. Set `CANDIDATE_SHA` from the artifact:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/cut_facts.sh" "$REPO" "$SCRATCH_DIR" "$CANDIDATE_SHA"
```

**`lab_evidence: lane-j`** (omnibase_infra; omnimarket is `report_only`). The script walks dev's
first-parent history back to the tag and classifies each merge with `trigger_for_sha.sh` from the
`lab-rebuild-triage` skill (merge sha, then PR, then the PR's branch, then the trigger run after the merge, confirmed by its
`PR_MERGE_SHA` or, in omnimarket's reusable-workflow log, `SOURCE_SHA`/`source_sha`). A `NON_RUNTIME` merge never gets a receipt, by design. It stops at the nearest
runtime-affecting ancestor of dev's head (`PUBLISHED` or `DETECTED_NOT_PUBLISHED`) and reads that
sha's lane-j receipt with that skill's `read_receipt.sh`, which lists the artifact by exact name and
downloads it by id through the REST artifacts API in seconds:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/lab-rebuild-triage/scripts/read_receipt.sh" "$R" <sha> lane-j <scratch dir>
```

**`lab_evidence: lane-j-or-instance-lanes`** (omnimarket today). The script performs the same
nearest-runtime-ancestor check once, then reads `lane-j` first and then the receipt lane of each
instance in `config/deploy_lane_routing.yaml` (omnibase_infra origin/dev) whose `lane.proves` names the
repo, in table order (`lane-f`, then `lane-e` on 2026-10-09). A PASS on any surface
satisfies the premise; an unknown merge between the head and ancestor voids inheritance on all of them.
`cut_facts.sh` resolves the policy value to its surfaces itself, from the value and the table, so a new
instance reaches it by its table row; a table it cannot read whole prints `PREMISE UNREADABLE` and exits 2.
A `lab_evidence` value it has no branch for prints `PREMISE UNKNOWN lab_evidence=<value>: ...`; add the branch
and a case to `tests/test_cut_facts.sh` (its enumeration test reads every value from the policy fixture), and
never read the policy note by hand as a way around it.

Only `PASS` counts. An artifact without `receipt.json` prints `NO_RECEIPT`, which is no receipt. A
receipt whose payload `sha` or `lane` differs from its artifact name prints `NAME_PAYLOAD_DISAGREE`,
which the train refuses too. `NONE` is printed only when the script's positive control found a
receipt of the same surface, by the same exact-name query, on an ancestor of the sha; when it
found none the verdict is `NONE_UNPROVEN`, which is unknown (read step 4 of `lab-rebuild-triage`
for what to do). An `UNKNOWN` class (no PR, no run, unreadable log) between the head and that
ancestor voids the inheritance. Read the lane-k receipt the same way with surface `lane-k`. If there is no PASS,
you are waiting, and the lab is probably the reason: run `lab-rebuild-triage`
(`/omni:lab-rebuild-triage`). Do not cut around it.

Do not match trigger runs with `gh run list --json headSha`: for these `pull_request` runs it is
the PR's head commit, never the merge sha. Do not fetch receipts with `gh run download -n <name>`
and no run id: it walks every run and hung for more than 120s.

## 4. Dispatch the train

Before dispatching, look for an open release PR for the same **version**, not the same branch (the
train's duplicate guard is keyed on the branch name, so a hand cut opens a second PR for one
version; ledger row 2026-09-22T00:37:39Z lane=core-release-2350). `cut_facts.sh` prints the open
release PRs naming the candidate version, then `OPEN_RELEASE_PRS <n> (control: <m> open PRs ...)`.
If it prints `OPEN_RELEASE_PRS UNREADABLE` (a `gh pr list` failed, for example on the GraphQL rate
limit, or the control count is not a number below the read limit) and exits 2, the duplicate guard
is not proven: do not dispatch. Wait for the limit to reset and run it again. Read the reset time from the `x-ratelimit-reset` header of a real
response (`gh api --include <endpoint>`) or from the `rateLimit { resetAt }` field of a GraphQL query, never from
the rate_limit endpoint body (it read `used=0` while real headers read 55 to 351, OMN-19470).

Then dispatch the train for the one repo (the train always runs in `omnibase_infra`) only when `cut_facts.sh`
printed `NEED ADMITTED` and the `== next` line; with `NEED REFUSED` there is no cut, so name the need and rerun it:


```bash
gh workflow run release-train-nightly.yml --repo OmniNode-ai/omnibase_infra --ref dev -f repos="$REPO"
```

Read the decision artifact through the artifacts API, by the run's id:

```bash
RUN=<run id of that dispatch>
gh api "repos/OmniNode-ai/omnibase_infra/actions/runs/$RUN/artifacts" --jq '.artifacts[]|select(.name|startswith("release-train-decision-"))|.id'
gh api "repos/OmniNode-ai/omnibase_infra/actions/artifacts/<artifact id>/zip" > <scratch>/d.zip
unzip -p <scratch>/d.zip release-train-decision.json | jq --arg r "$REPO" '.decisions[]|select(.repo==$r)'
```

The object carries `verdict` (`CUT` or `SKIP`), `reason`, `detail`, and `candidate_sha`, which is
the gating commit that step 3's `lab_evidence: none` branch checks for green CI. The train has its
own premises and **no override**. A SKIP names its reason (for example `lab_receipt_unreadable` or
`no_unreleased_release_relevant_work`).

## 5. Guard the release PR until merge

At every poll (about every 15 min), compare dev's head with the sha the train decided at.

For a **lane-j** repo:

- **dev has moved past a runtime merge with no PASS receipt:** convert the release PR to draft
  (`gh pr ready <n> --repo "$R" --undo`), read back `isDraft`, and write a STATUS row naming the
  failing receipts. This is reversible, and it is the correct move (ledger row
  2026-09-22T22:33:45Z lane=infra-release-cut).
- **a PASS appears at dev's nearest runtime-affecting ancestor:** take the PR out of draft if its
  CHANGELOG still describes what will be tagged. Otherwise close it and dispatch the train again at
  the proven head.

For a **`lab_evidence: none`** repo, the guard is the same with green dev CI in place of the
receipt: if dev has moved and the new head is not green, draft the PR.

Let the change-control autobind mint the companion. Hand-author one only when the autobind has
declined, and only from evidence you can re-read.

## 6. Merge and read back

Immediately before merging, run the `/omni:ledger-msg` inbox check (section 4 there) for your lane
name — a release merge tags whatever `dev` holds at that instant, so a HOLD landing after step 3's
last check and before the merge itself is the case this catches.

Merge by hand on the exact head (`gh pr merge <n> --repo "$R" --squash --match-head-commit <head>`),
only while step 3 still holds for dev's head at that moment. Then read back the tag
(`gh release list --repo "$R" --limit 3`, or, for a repo without GitHub releases,
`python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh "$R" --tags --wait`
then `git -C "$registry_root/<repo>" tag --sort=-v:refname | head -3`; a lane's `git ls-remote` is refused
by the lane git-fetch guard, OMN-20495), the PyPI version and `main`'s fast-forward. Write the TERMINAL row with the tag, the merge
sha and the receipt artifact id you relied on (or, for a `lab_evidence: none` repo, the gating
commit and its green check-run read time).

The landing controller now lands a bot's `chore: release` PR on its own: it lifts its release gate
only when `cut_facts.sh` reads `PREMISE READY` for dev's current tip and the PR is green, then merges
or enqueues pinned to the head under the same holds, owners, pauses and lab gate (OMN-20864).
Just before the merge it reads dev's tip again and defers when dev has moved since the premise read.
This step's hand merge remains for a lane that runs release-cut itself. No lane hands the PR off
(`pr-handoff` refuses it); report "release PR: the controller owns it".

## Guardrails

- Never merge a lane-j repo's release PR while dev's nearest runtime-affecting ancestor has a FAIL receipt or no receipt.
- Never make a `lab_evidence: none` repo wait for a lab receipt. None can exist.
- No force or skip input exists. Do not look for one, and do not reach for a hand tag.
- Never cut without a named need: `NEED REFUSED` ends the cut. `tests/test_named_need.py` (`pytest tests -k named_need`, a validate-plugin step and the `release-cut-named-need` pre-commit hook) holds the gate. OMN-18595.
- Downstream pin bumps (dependency-cascade) are separate PRs with their own lanes.
- Never hand a bot's `chore: release` PR off (`pr-handoff` refuses it). The landing controller lands it on its own only when `cut_facts.sh` reads `PREMISE READY` for dev's current tip and the PR is green, merging or enqueuing pinned to its head under the same holds; step 6's hand merge remains for a lane running release-cut itself. OMN-20864.

## Known friction (from prior runs)

- **Green bot release PRs sat unlanded** (omnibase_core#1960 about 5.5h; omnibase_infra#4905) because nothing ran step 6 on its own. The landing controller now owns them, lifting only the release gate after a READY premise for dev's current tip and green PR CI. OMN-20864.
- **A release lane passed a commit SHA as `SCRATCH_DIR`,** creating a SHA-named directory with `runs.tsv` and `ci_premise.txt` in the current repository on 2026-09-24. `cut_facts.sh` now refuses SHA-shaped and relative scratch arguments; pass an absolute directory, or `""` before the SHA to use its temporary-directory default. OMN-19625.
- **`ci_premise.py` could read READY beside a red sibling copy** (two same-named copies in one suite, tied or overlapping, or a red copy with no `started_at`), because only the newest copy counted and a tie went to the later line. A red copy now counts unless it completed before the newest copy started. `tests/test_ci_premise.py` has the tie, overlap and missing-timestamp cases with controls. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **The train decided CUT at 4aca83d9. dev then moved past #3939, #3934 and #3941,** whose receipts were FAIL or missing, so the release PR was drafted to stop an unproven tag. → ledger row 2026-09-22T22:33:45Z lane=infra-release-cut, omnibase_infra#3973
- **No lane-j PASS for any dev sha after 4aca83d9 for more than 5h,** during the lab saturation. → ledger rows 2026-09-23T00:40:46Z lane=infra-release-cut and 2026-09-23T00:57:52Z lane=friction-to-skills item=F10
- **A lane-j artifact with no receipt.json.** The nightly reported SKIP `lab_receipt_unreadable`. → ledger row 2026-09-22T19:02:01Z lane=infra-release-cut
- **The rebuild trigger failed on DNS,** so merge 7954c945 can never carry a receipt unless a later merge re-emits one. → ledger rows 2026-09-23T00:57:52Z lane=friction-to-skills item=F11 and 2026-09-23T00:40:46Z lane=infra-release-cut
- **The duplicate guard is keyed on the branch,** so a hand cut opened a second PR for 0.47.22 (omnibase_core#1739). → ledger row 2026-09-22T00:37:39Z lane=core-release-2350, OMN-19150
- **Release-identity gate red on product PRs** while release-on-merge publishes. It clears when the bump PR lands. → ledger row 2026-09-23T00:14:14Z lane=clean-install-deleg
- **Stale Hostile Review Gate after the stamp line was appended to the body.** Rerun the whole run. → ledger rows 2026-09-22T22:33:45Z lane=infra-release-cut and 2026-09-23T00:03:18Z lane=lab-rebuild-unstick (FRICTION)
- **The skill hardcoded the repo as omnibase_infra,** while the train policy also arms omnibase_core and omnibase_spi with `lab_evidence: none`, so a core cut would have waited forever for a receipt that cannot exist. The repo is now the input and step 3 branches on the policy. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`gh run download -n <name>` with no run id hung for more than 120s.** Receipts and the decision artifact are read through the artifacts API (`read_receipt.sh` in `lab-rebuild-triage`). OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 3 listed runtime merges by `--json headSha`,** which holds PR heads for `pull_request` runs, not merge shas. `trigger_for_sha.sh` in `lab-rebuild-triage` matches by PR and confirms `PR_MERGE_SHA`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 2 counted every commit since the tag,** not the train's scope. `scripts/cut_facts.sh` counts `-- src pyproject.toml` with the bookkeeping subjects excluded, and takes the highest `vX.Y.Z` tag as the train does. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Every `ledger:NNNN` citation, including step 1's authority example, went dead when the ledger rolled at 2026-09-23T14:00:47Z.** Citations are now `<row timestamp> lane=<lane>`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`scripts/trigger_for_sha.sh` and `scripts/read_receipt.sh` were byte copies of the `lab-rebuild-triage` scripts,** with nothing keeping them in sync. The copies are deleted; `cut_facts.sh` and this file call the single `lab-rebuild-triage` copy. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`ci_premise.py` keyed check runs by name alone,** so a red `occ-preflight / eligibility` from one workflow was hidden by a later green copy from another (9 workflows emit it on omnibase_core dev 3dbaf248), and a queued rerun with no `started_at` sorted older than the success it replaced. Copies are now keyed by (workflow, check name), and any copy or run in flight is not green. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`read_receipt.sh` never checked the receipt payload,** so an artifact named for 6fe05c35 whose payload said c159b711, or a lane-j artifact whose payload lane was lane-k, read PASS. It now prints `NAME_PAYLOAD_DISAGREE`, as the train does, and its positive control uses the same exact-name query on an ancestor, so the zero for 6fe05c35 is proven again. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`ci_premise.py` ignored workflow run conclusions,** so a run that ended `startup_failure`, `action_required` or `failure` with no red check-run copy read `PREMISE_CI READY`. The newest run of each workflow and event must itself be green. `tests/test_ci_premise.py` has P1 to P3. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`cut_facts.sh` did not check the open-release-PR read,** the duplicate-version guard step 4 relies on. On the GraphQL rate limit both `gh pr list` calls failed, the list came out empty, the control count was blank, and the script went on to print the next step. It now prints `OPEN_RELEASE_PRS UNREADABLE` and exits 2, and step 4 stops the dispatch. `tests/test_cut_facts.sh` covers it with a failing gh stub. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`cut_facts.sh` read check-runs with the endpoint's default `filter=latest`,** which returns only the newest run of each check name per suite, so the `lab_evidence: none` premise judged 308 of 315 copies on omnibase_core c804d0c726a1 and a red older copy could hide. The read now passes `filter=all`. OMN-19387.
- **A bot release PR was handed off, accepted, and never landed.** `pr-handoff` read no author, accepted omnibase_core#1844 (a bot's `chore: release` PR) with `needs=land`, and told the lane the controller would land it, but the controller gates that PR for this skill, so it sat undecided for about 3.5h. `pr-handoff` now refuses it and names this skill. → FRICTION 2026-10-02T08:46:21Z lane=qdiag-core-floor-1844, omnibase_core#1844, OMN-20342
- **`cut_facts.sh` printed `PREMISE UNKNOWN` for omnimarket,** because it knew only the retired policy value `lane-j-or-lane-f` while the policy said `lane-j-or-instance-lanes`, and `trigger_for_sha.sh` returned `UNREADABLE` for every omnimarket merge, because it looked only for `PR_MERGE_SHA: <sha>` and omnimarket's trigger job log (the reusable workflow) names the merge as `SOURCE_SHA: <sha>`, `source_sha: <sha>` and `source_sha=<sha>`. The surfaces now come from the policy value and the routing table (`cut_facts.sh` reads both), and the log read accepts any of the four markers; both tests use the real policy rows, routing table and job-log excerpts of 2026-10-09. OMN-20065
