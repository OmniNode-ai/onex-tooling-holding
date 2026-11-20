---
name: ci-watch
description: Watch one pull request's CI on its exact head sha, read the base branch's required contexts and every check-run copy (paginated, not the rollup), classify each red against today's known classes (the change-control cascade, draft-era residue, replayed reruns, cancelled producers, stale copies, followers, base-inherited reds, shadow and runner-saturation timeouts, rate limits), apply the one correct move per class, and report a terminal state keyed on the required contexts with its read time. Use from pr-land step 5, or whenever a lane must answer "why is this PR red, and what clears it".
prosthetic: true
replaces_when: "`onex skill ci_watch` resolves to a node that reads the check-runs API per head sha (every copy, paginated), classifies the red classes in step 4 by name with a typed verdict per class, and refuses to report green on a zero-row read, on three PRs in a row with no lane triage by hand. On 2026-09-23 `onex skill ci_watch` returns `Unknown skill` (it is absent from omnibase_infra `src/omnibase_infra/cli/skill_mapping.yaml`). `onex node node_ci_watch` runs, but it wraps the PR checks rollup and the failed-job log read, so it reads the rollup and knows none of these classes."
restored_from: "omniclaude 1e33287a0 plugins/onex/skills/ci_watch/SKILL.md (with topics.yaml at the same commit)"
ticket: OMN-19221
---

# CI watch (prosthetic)

One PR, one head sha. Set these on their own lines first:

```bash
R=OmniNode-ai/<repo>
N=<number>
S=$SCRATCH/<lane>/ci-<repo>-<number>     # lane-unique scratch dir
```

Run this in a background lane, not in the foreground orchestrator (memory
`feedback_foreground_background_discipline`). Keep all scratch files under a lane-unique directory.
Two lanes that wrote the same generic filename in a shared scratchpad have published each other's PR
bodies and commit messages (2026-09-20T12:15:19Z lane=obs-board-drive-1700, 2026-09-21T03:00:22Z
lane=obs-board-drive-1700, 2026-09-22T23:38:46Z lane=m4-c12-probe).

**Headless note (a lab lane, `claude -p` through the remote-lane runner).** The watch is ONE read:
`ci_state.sh` once, then act on its verdict (it takes the PR watcher's verdict while the watcher's state is
fresh and prints `source=watcher`, with zero GitHub requests; OMN-20421). Never run `--watch`, `run_in_background` or `Monitor`, and
never stop to wait for a notification: a headless session ends at its final message, so the lane would exit 0
with "waiting for CI" and no handoff (2026-10-01: finish-3212, why-report-contract, why-detached-head,
codex-h908-capable). On PENDING, do not re-read: hand off with `omni:pr-handoff --needs land` even while CI is
PENDING (the PR watcher reads CI and the landing controller acts on it), or report the blocker. The runner marks a lane that ends waiting with no handoff
`outcome=ended-waiting`.

Pointers name a ledger row by `<timestamp> lane=<lane>`, which survives a roll. Find one with
`grep -hF '<timestamp>' $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md $registry_root/docs/tracking/archive/*-split.md | grep -F 'lane=<lane>'`.

## 1 and 2. Pin the head, read the required contexts, read every copy

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/ci_state.sh" "$R" "$N" "$S"; echo "rc=$?"          # the watcher's verdict while its state is fresh
bash "${CLAUDE_SKILL_DIR}/scripts/ci_state.sh" --live "$R" "$N" "$S"; echo "rc=$?"   # the exact-head check, from GitHub
SHA=$(jq -r .headRefOid "$S/pr.json")
```

**Where the verdict comes from (OMN-20421; RULING 2026-09-27T18:05Z: every PR-state read comes from the PR
watcher's state file, GitHub is for mutations and the exact-head check only).** Without `--live`, the script
reads `merge-drain/scripts/pr_state_local.py` first. While the watcher state is fresh (last complete tick at
most 8 minutes old, inventory resynced within 90) and holds this PR's CI at its current head, the verdict is
the watcher's, with zero GitHub requests, and the line ends `source=watcher`. The watcher keys on every
check-run name it read at the head (newest copy of each, required or not), not on the required contexts: its
GREEN means no reported copy is red or pending, but it cannot see a required context nobody has reported yet,
`mergeStateStatus`, or run and job ids; its RED names the failing checks and carries no `reds.tsv`. It reads
GitHub, saying `watcher state not used: <reason>`, when the state is stale or missing, the PR is absent or a
draft (the watcher never reads a draft's CI), or the watcher has not read this head. `--live` forces GitHub:
use it as the exact-head check right before a merge, an arm or a rerun, and to get the run and job ids of the
red names the watcher gave you, which are the only logs to read. Everything below describes that GitHub read.

The script is read-only, and its offline regression test is `tests/test_ci_state.py` (a fake `gh`
serves fixtures; it also runs the by-hand block below as written). It does four things:

1. **Pins the head.** It writes `pr.json` with the head sha, draft state, base, `mergeable`,
   `mergeStateStatus`, auto-merge and labels.
2. **Reads the REQUIRED contexts** of the base branch from both places GitHub enforces them:
   `repos/$R/branches/<base>/protection/required_status_checks` and `repos/$R/rules/branches/<base>`
   (rulesets, type `required_status_checks`, one page of up to 100 rules; a full page could be
   truncated, so it exits 3). It writes them to `required.txt`. They differ per repo
   and branch. On 2026-09-23 omnibase_infra `dev` required only `CI Summary`, omnimarket `dev`
   required 34 contexts (35 by 18:44Z), infra_repo `dev` 6, and registry_root `main` 3. No ruleset carried required contexts, and
   the rules endpoint was proven live against omnibase_infra `main`, which returns its release
   ruleset. GREEN and RED are keyed on these contexts, never on "no red anywhere". When neither
   source requires any context, the verdict keys on every check-run name AND every legacy commit
   status context at the head, and prints a `WARNING` line saying so.
3. **Reads every check-run copy, paginated.** It checks the row count against the API's
   `total_count` and exits 3 on any mismatch. It also reads the legacy commit statuses and the
   workflow runs at the head. It writes `cr.tsv` (id, name, status, conclusion, started, completed,
   url, suite), `statuses.tsv`, `runs.tsv`, and `reds.tsv` (every non-green copy, `REQUIRED` or
   `optional`, with its run id and job id).
4. **Prints one line per required context** with its newest copy's state, plus the older non-green
   copies beside it. Then it prints a verdict:
   `VERDICT GREEN|RED|PENDING <sha> required=<n> checkruns=<n>/<total> mergeStateStatus=<s> read_at=<UTC>`.
   The exit code is 0 for GREEN, 1 for RED, 2 for PENDING, and 3 when the read could not be trusted.
   Never read a 3 as green.

**Which copy counts.** A required context passes when its **newest** copy at the head is completed
with success, neutral or skipped. Newest means the latest `started_at` (else `completed_at`), then the
highest id; a copy with neither timestamp (a queued copy, or a completed copy cancelled before a
runner picked it up) counts as the newest, so the context reads PENDING or RED, never GREEN. Measured 2026-09-23 on omnimarket#2807: three older failing copies
of the required `occ-preflight / eligibility` sat beside one newer success, and GitHub reported
`mergeStateStatus=CLEAN`. The old claim that "branch protection evaluates every copy" is therefore
dropped. The 2026-09-20 BLOCKED cases (2026-09-20T10:28:37Z lane=core-release-04718-unblock-codex-1845
and 2026-09-20T22:40:48Z lane=core-release-successor-1915) are real, but that measurement does not
explain them. The script still lists older non-green copies as C5 candidates. When the required
contexts read green but GitHub says BLOCKED, DIRTY or BEHIND, it prints a `MISMATCH` line instead of
passing silently. Read class C5, R4, R5 and A1, and the review state, before concluding anything
else. On a MISMATCH the script itself also reads check-suites (a GitHub App's own umbrella object,
one level above its check-runs) and prints a `STUCK-CHECK-SUITE` line for class A1 when it finds
one; this is a best-effort extra read that never changes the verdict or its exit code.

Reading the header lines:

- `draft=True`: see classes D1, D5 and D6 in step 4 before reading anything as a failure.
- `mergeStateStatus=UNSTABLE` with `mergeable=MERGEABLE`: the required checks pass and only optional
  ones are red. Report that; do not fix optional reds on a landing lane.
- `BEHIND` on a strict base (registry_root `main`, infra_repo `dev`, omnidash `dev`, omnibase_spi `dev`
  on 2026-09-23, from the `strict` field the script prints): every peer merge re-queues a full round.
  See class R4.
- `mergeStateStatus=UNKNOWN`: GitHub has not computed it yet. Re-read in a minute. It is not a verdict.

Every read below is for `$SHA`. If the head moves while you watch it, stop and start again from this
step, because a verdict on the old head says nothing about the new one.

**By hand** (only if the script is unavailable):

```bash
set -o pipefail
BASE=$(jq -r .baseRefName "$S/pr.json")
onex scm branch-protection "$R" --branch "$BASE"; echo "rc=$?"
onex scm pr-checks "$R#$N"; echo "rc=$?"
onex scm run-list "$R" --head-sha "$SHA"; echo "rc=$?"
```

These return required checks, the watcher's CI record (red, pending, runs, red_facts and detail with job ids), and head runs with `created_at` and `event`, respectively.

Rules for the read itself (rule 16):

- Check `rc` and the row count on every call. Never append `2>/dev/null`. An unpaginated read at 149
  check-runs reported present required contexts as missing (2026-09-20T22:40:48Z
  lane=core-release-successor-1915).
- A zero-row result is not "nothing is red". The script exits 3 on zero check-runs and zero statuses.
  By hand, prove the query once against a head you know has rows, such as the base branch tip.
- The PR's `base.sha` is not the merge base. When you need the base, resolve it yourself (memory
  `reference_gh_pr_base_sha_is_not_the_merge_base`).
- On a 403, or on check-runs that fail in under a minute at a checkout step, you have hit the shared
  identity's rate limit (class T3). Read the reset time from the failing response, never from a
  rate-limit endpoint read, which reports a different identity's bucket.

## 3. Wait correctly

- Never poll (OMN-20421). On PENDING, hand the PR off (`/omni:pr-handoff`) and exit: the PR watcher reads that
  head's checks every five minutes and the landing controller acts on the verdict. A single
  `onex scm pr-checks "$R#$N"` read returns the watcher's CI record; lanes never watch or poll.
- Do not cancel `occ-preflight / eligibility`. It waits up to 1500s (25 min) for the cited companion
  to **merge**, by design (`omnibase_core/scripts/ci/occ_preflight_wait.py`, `DEADLINE_SECONDS=1500`).
  Cancelling and rerunning it restarts the clock and changes nothing (2026-09-22T23:53:29Z
  lane=market-shadow-timeout).
- A run that is queued or in progress cannot be rerun, so do not try.
- The watch is over when one of the terminal states in step 7 holds. Do not stop at "mostly green".

## 4. Classify every red

Self-contained build and fix drafts use Codex first (operator ruling 2026-09-30, OMN-20106; the plan period ends about 2026-10-30), then the lab agent, then GLM; the lane verifies. Run `delegation_step.py code` in the lane's own worktree; it keeps the `lab_crush.py` route and then one GLM draft through Claude Code (`/omni:harness-delegate --harness claude-glm --writable-repo <worktree>`). GLM runs only through Claude Code: the Coding Plan terms bar direct API calls, so the cloud-glm backend pin of `onex delegate` is retired and always fails (omnimarket#3136, OMN-20173). Never pass a model flag to Codex. The Claude lane reads every diff, runs focused tests and owns the PR. Pure text stays lab first, then GLM through Claude Code (`delegation_step.py text`); typed decisions go to Jev.

Classify every red on a **required** context (`REQUIRED` in `reds.tsv`), and every red that CI
Summary names in its log. Reds on optional contexts that nothing names do not block. Report them,
and do not fix them on a landing lane.

**Ask Jev first when the repository is public (OMN-19432).** Which class a red belongs to is a bounded
choice over facts, the case Jev measured best (92% top pick with the deciding facts computed in code,
96% precision on the answers it acted on, 155 ms median, about 3 cents per 447 questions). Before you
spend a turn reasoning from the log, put the failed check, its log tail, the other copies of it on this
head and the same check on the base branch in a JSON file and ask:
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/delegation_step.py" decide --lane <lane> --step ci-cause --repo <repo> --preset ci-cause --facts-file <json> --own-answer <your read, or none_of_these>`.
A `none_of_these` or an abstain means the table below decides. An answer disagreeing with the table row
you matched is a reason to read the log again, never a reason to skip a row. Jev decides on every repository
but `docs_repo` (operator RULING 2026-10-13T18:34:53Z, OMN-20106), private code repositories such as
`infra_repo` included; the step refuses the knowledge base (and its alias `docs-repo`) and the table decides alone there.
Put the correlation id in the TERMINAL's `jev=` cell.

Read the failing job's own log before you form a theory (step 6). One lane spent its window probing a
runtime that the first log line had already cleared (2026-09-20T08:25:41Z
lane=occ-preflight-eligibility-red-0815). Match each red name to exactly one row. The **pointer** is
where the evidence lives. A `<timestamp> lane=<lane>` pointer is a ledger row (the grep at the top),
and `remedy <n>` is a row of `$registry_root/.claude_scratch/reports/merge-sweep-remedy-table-2026-09-22.md`
(rows 25 to 28 are also in docs_repo `runbooks/manual-merge-sweep.md`, "Blocker
classes and their recorded remedies").

For a receipt, deploy or contract-compliance body-line error, classify its saved job log offline
before applying the cascade rows:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/ci_state.py" --classify-log "$S/failed-job.log"
```

Exit 1 prints the specific red class and fix (C13 for the missing evidence-ticket line, C10 for a
missing stamp); exit 2 means unclassified, so use the remaining table. This mode makes no GitHub
request and never reports CI green. C10 still requires the D5 draft check. The fixture excerpt from
omnidash#336 job 109025862675 is covered by `tests/test_evidence_classifier.py`.

### F. Followers: never the cause while a producer is red

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| F1 | `CI Summary` red while any gate it lists is red, in progress or absent. Its log prints `CI Summary verdict: FAILURE` and a `strict gates:` list | Diagnose the gates it names, not CI Summary itself. If the list shows `in_progress` or `<absent>` rows, it graded early (P2) | omnibase_infra#3991 job 107029174748 (2026-09-23) |
| F2 | `CI Tests Gate` red with `Test matrix failed (result: failure)` beside a red `Tests (Split n/m)` | A follower of the test matrix. Read the red shard's log (`FAILED <test id>`). The gate clears when the shard does | omnibase_infra#3991 jobs 107034119167 and 107032636808 |
| F3 | `Test-Failure Ratchet Gate` red with `TEST-FAILURE RATCHET GATE BLOCKED (OMN-13027)` naming the same test cluster as the red shard | A follower. Fix the test (class X), or, if R3 proves it inherited from the base, report it. Never add a baseline entry by hand without a ticket | omnibase_infra#3991 job 107034119314 |
| F4 | `Contract Compliance Check` red with DoD lines `[X] test_passes: Failing CI checks: <list>` (the contract's CI-checks probe read the head while other checks were red or still running) | A follower for those lines: diagnose the checks it lists, then rerun the Contract Compliance run whole once they read green. Any other `[X]` line (a `command:` probe that failed, such as a self-bind to a companion that no longer resolves) is not a follower: treat it as class X, or C4 when it names a companion receipt. On a draft with no `Evidence-Source:` line, see D5 first | omnibase_core#1745 (draft) job 107351769841, read 2026-09-23T22:08Z: `[SUMMARY] OMN-18157: 4/7 PASS, 0 WARN, 3 BLOCK`, two `test_passes` followers and one failed `occ-self-bind-pr-9012` command probe |

### C. The change-control cascade

The cascade set is `occ-preflight / eligibility` (many copies, one per caller workflow),
`OCC Preflight Dependency`, `verify / verify` (the Receipt Gate), `OCC Companion Merged Gate`, the jobs
that `needs:` the preflight (they skip), and `CI Summary` as a follower. CI Summary is never the cause
while any of the others is red. Diagnose the earliest red and let the rest follow.

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| A1 | A GitHub App check suite (not an individual check-run) sits QUEUED for a long time, or is never created, and names no required context. `ci_state.sh` prints `STUCK-CHECK-SUITE app=<slug> suite=<id> status=queued age=<duration>` on a green-but-BLOCKED MISMATCH. GitHub still reports `mergeStateStatus=BLOCKED` on it though branch protection never named it, so a PR green on every required context still cannot merge | Never rerun it: there is nothing queued to rerun, and never wait it out. Hand off through `/omni:pr-handoff` (`needs=land`); the landing controller takes a fresh head (update-branch), or the owning lane pushes an empty commit before handoff | FRICTION 2026-09-27T13:25:44Z, omniclaude#2376 (QUEUED 13 hours, cleared by update-branch), OMN-17427 |
| C1 | Every red is in the cascade set, and the body's first evidence-source companion reads MERGED | The landing controller reruns the **whole** run of each red caller once, never `--failed`, never a run twice for the same cause | remedy 1, 2026-09-22T05:48:19Z lane=pr-fix-omniclaude-2287-rerun |
| C2 | Same set, and the companion is OPEN; preflight in progress or failed at its 1500s deadline | Do not rerun the parent. The landing controller lands the companion first, arming it if green and unarmed in onex_change_control, then reruns the parent's red runs whole once | remedy 2, 2026-09-22T23:15:13Z lane=omn16856-c17-carrier, 2026-09-21T17:46:31Z lane=omn18868-67-seam-gates-restart |
| C3 | `OCC Preflight Dependency` timed out at about 13 min while eligibility was still polling | A follower of C2, not a defect in the PR. Clear C2 first, then rerun its runs whole | OMN-18857, 2026-09-21T18:35:42Z lane=seam-defect |
| C4 | The companion itself is red with `nonpass_receipt` naming a check from **your** PR | A real FAIL. Fix the assertion or its precondition in your PR. Do not read it as the fleet false red | 2026-09-21T17:46:31Z lane=omn18868-67-seam-gates-restart |
| C5 | An older non-green copy of a required context sits beside a newer copy (the script's `C5 candidates`), and GitHub reads `BLOCKED` while the newest copies are green (the script's `MISMATCH` line) | Rerun that exact run id whole. With many stale callers (core has fourteen), a fresh head is cheaper. If GitHub reads CLEAN, the stale copy is not blocking: leave it | remedy 18 + §G row 18, 2026-09-20T22:40:48Z lane=core-release-successor-1915, omnimarket#2807 (CLEAN beside three stale copies, 2026-09-23) |
| C6 | A gate that `needs:` the preflight reads `skipped` with zero steps, and CI Summary fails on it | `--failed` never re-executes a skipped job. Rerun the whole run so the graph runs again | 2026-09-20T10:28:37Z lane=core-release-04718-unblock-codex-1845 |
| C7 | Eligibility says `missing_ticket` with `ticket_ids=[]`, but the title cites a ticket | The verdict was taken on the create event, before the body was set. Rerun the whole run; do not edit the title | 2026-09-22T14:11:18Z lane=occ-10767-opus |
| C8 | Receipt Gate red, and the autobind outcome posted a legitimate decline seconds after the gate read | An ordering race, fixed at the source by omnibase_core#1741. Take a fresh head (R1); do not author a companion | remedy 27 |
| C9 | Publisher succeeded, but no `occ-autobind / outcome` ever posted and no companion minted | The mint stalled. Re-trigger `occ-autobind-manual-replay` once. If the consumer is down fleet-wide, report it and do not rerun the publisher | §G row 5/20, 2026-09-23T02:11:52Z lane=omn19201-response-contract, 2026-09-21T08:15:05Z lane=omn18944-backup-cronjob-alert-0325 |
| C10 | `verify / verify` names a missing evidence-source stamp line on a PR whose companion merged | A wholesale body rewrite deleted the machine-added stamp. Restore both evidence lines through pr-land step 2a, naming the verified companion and its ticket; preserve any surviving line verbatim | 2026-09-20T03:50:05Z lane=runtime-autowire-crashloop-fix-2150 |
| C11 | `occ-preflight / eligibility` log reads `[declined_terminal] autobind_declined_terminal ... skip:DEFER_HAND_AUTHORED — <repo>#<N>: OCC#<n> (hand_authored, <branch>) carries evidence for <ticket>` and `No later poll changes this verdict`; the body carries no evidence-source stamp line | The autobind will not mint while a hand-authored companion claims the ticket, so no rerun and no fresh head clears it. Read OCC#<n> live. If it is this PR's companion, the owner cites it in the body and lands it (then C2). If it is another lane's companion (for example a draft parent-epic contract), report it to that owner and stop. Never hand-author a second companion beside it: two companions on one `dod_evidence` conflict | omnimarket#2820 job 107388525805 (OCC#10767 open, draft, read 2026-09-23T23:57Z) |
| C12 | On a **ready** (non-draft) PR, `OCC Companion Merged Gate` and `verify / verify` fail because the body has no evidence-source stamp line, and their logs quote the autobind outcome `DECLINED ... skip:NO_RED_DERIVABLE_CHECK — <repo>#<N>: no changed-file candidate is RED-derivable against the merge base; hand-authored evidence is required (OMN-15247)` and `a deliberate, permanent refusal`. `CI Summary` then fails as F1 on the strict gate | Not the fleet false red and not a race: no rerun, no fresh head and no replay mints a companion (the log says so). The PR's owner hand-authors the OCC companion carrying the ticket's `dod_evidence`, composes both evidence lines through the pr-land step-2a helper, naming the companion and its ticket (preserve the existing body: C10), and it proceeds as C2. A lane without that ownership reports it and stops. Check first that no hand-authored companion already exists for the ticket (C11) | omnibase_infra#4037 jobs 107449406197 and 107449405431 (CI Summary 107449406415 is the F1 follower), read 2026-09-24T01:24Z |
| C13 | Receipt Gate or deploy gate explicitly says the body contains an evidence-source stamp but is missing an evidence-ticket line | The PR owner uses pr-land step 2a to compose the complete verified pair and preserve the existing stamp verbatim. Do not delete the stamp, relax the guard or rerun alone; hand the repair to the landing controller. Match this specific error before C1/C2 | OMN-20054: omnidash#336 jobs 109025862675, 109047320123, 109065660669 (2026-09-28) |

### D. Draft residue

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| D1 | PR is draft with a real code diff; autobind reads DECLINED `skip:PR_DRAFT`; the whole change-control family is red | Working as designed (draft-only red). No rerun, no fresh head and no hand citation clears it. Fix real reds, then flip ready when the PR's slot comes; the flip mints the wave | remedy 29, the 2026-09-21T23:01:47Z RULING (a dash-led row with no `lane=` cell: find it by the timestamp alone) |
| D2 | After the ready flip, CI Summary fails on a **bare** name (`deploy-gate`, `zone-filter`) that sits `skipped`, while the compound `deploy-gate / deploy-gate` is green | Draft-era orphan. CI Summary supersedes only same-named rows, so no rerun clears it. Mint a fresh head while non-draft | remedy 30, 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the omnibase_infra#3971 row) |
| D3 | A rerun of a run created while the PR was draft turns the test matrix `skipped` and `CI Tests Gate` red ("PR is draft") | A rerun replays the original event, draft state included. Never rerun a draft-era run. Take a fresh head | 2026-09-21T23:40:15Z lane=kafka-producer-retry-2, 2026-09-23T01:05:02Z lane=omn17099-backend-overlay |
| D4 | Ready flip and a push landed together, and the head has a run cancelled with **zero jobs** and no CI Summary, **created after** the last ready flip | Concurrency cancellation. Rerun the whole cancelled run. If the cancelled run was created before the flip, it is D7, not D4 | 2026-09-22T20:27:44Z lane=market-drain |
| D5 | A gate that reads the evidence-source companion is red on a **draft** whose body cites none. omnimarket `deploy-gate / deploy-gate`: the log prints `Evidence-Source not present — using canonical OCC contract source`, then `DEPLOY GATE FAILED: PR touches runtime paths but no cited ticket has deploy DoD evidence`. omnibase_core `Contract Compliance Check`: `Contract Compliance evidence resolution failed: PR body is missing required 'Evidence-Source:' line` | Draft residue. The autobind does not mint a companion for a draft, so the gate has no companion to read. No rerun and no hand companion. It clears with the companion the ready flip mints. If it is still red after that companion MERGED, it is real: the ticket's contract needs its `dod_evidence` (class X) | omnimarket#2803 (draft, hold-family label) job 107168061055; omnibase_core#1745 (draft) job 107338979389, both read 2026-09-23 |
| D6 | omnibase_core `Tests Gate` red on a **draft** targeting `dev`, log `test-parallel was SKIPPED but the docs-only precondition does not hold (zone-filter docs_only='false', ...)`, with the `Tests (Split ...)` and `Integration Tests (Split ...)` matrices `skipped` in the same run | Draft residue. The OMN-16215 draft admission gate skips both test matrices on a draft PR to `dev`, and `Tests Gate` fails closed on any skip that is not docs-only, so it is red on every such draft by design. No rerun (D3). It clears with the runs the ready flip starts. If it is red after the flip, read the matrix shards (F2) | omnibase_core#1745 (draft) job 107407768383 in run 35927516630, read 2026-09-23T22:30Z; the gate is `tests-gate` and the draft condition is on `test-parallel` in omnibase_core `.github/workflows/ci.yml` at `dev` |
| D7 | After the ready flip, a run created **before** the flip (its `created_at` is earlier than the PR's last `ready_for_review` timeline event; `event` reads `push` or `pull_request`) is cancelled or red, often a cancelled push-run's contexts past the 600s grace or an unexpanded `Tests` matrix row that CI Summary names | Draft-era run. **Never rerun it, whole or `--failed`, and never rerun the CI Summary run to clear it:** a rerun replays the draft payload (the matrix skips, `CI Tests Gate` goes red), those fresh reds land on the head, and the ready run's own rerun then fails on them too. The landing controller takes a fresh head (update-branch) while non-draft, or the owning lane pushes an empty commit before handoff. Read both times first (step 5) | 2026-09-24T09:17:58Z lane=reds-stacked (omnibase_infra#4043, run 35970519445, fourth occurrence), 2026-09-24T06:12:23Z lane=wr-recovery-r2, 2026-09-23T18:32:10Z lane=k3s-lab-receipt-diag, OMN-19379 |

### P. Producers cancelled or graded early

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| P1 | After a body edit (yours or the autobind's), occ-preflight, Hostile Review and the skip-token scan read `cancelled`, and CI Summary says `cancelled_without_replacement` | Rerun each cancelled run **whole**. Never `--failed` after a body edit | 2026-09-23T00:03:18Z lane=lab-rebuild-unstick, 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the omnibase_infra#3971 row), OMN-15822 |
| P2 | CI Summary concluded before producers it names had finished, so it read their stale instances (omnibase_infra#3973: it ran 22:19:22 to 22:19:36Z, before the Hostile Review and skip-token successes at 22:19:59 to 22:20:10Z; omnibase_infra#3991 on 2026-09-23 listed `in_progress` and `<absent>` gates) | Wait until every producer it names has a completed success at the head. Then rerun the CI Summary run once, or take a fresh head if orphaned rows remain | 2026-09-23T04:20:28Z lane=infra-release-cut, 2026-09-21T23:40:17Z lane=kafka-producer-retry-2 |
| P3 | CI Summary's external sweep names only standalone workflows that sit `skipped` at the head | Rerun each standalone workflow's own run and confirm it green, **then** rerun the summary once | remedy 19 |
| P4 | `Enable Auto-Merge (cancelled_without_replacement)` after a hand workflow dispatch | The dispatch ran without `--ref`, so it ran on the default branch's sha. The landing controller dispatches again on the head branch via `onex scm workflow-run OWNER/REPO --workflow W --ref BRANCH` | remedy 31 |
| P5 | A required copy is red (often `CI Summary` with its gates `completed/cancelled`, `in_progress` or `<absent>`), and `runs.tsv` holds a **newer** run of the same workflow at the same head that has not completed (queued, pending or in progress). A body edit, ready flip or re-trigger started it, and `cancel-in-progress` is cancelling the older run's jobs. `ci_state.sh` prints `PENDING (... superseded by a newer '<workflow>' run <id> ...: class P5)` and reads PENDING, not RED | Wait for the newer run: it posts its own copy of every context. Do not rerun the superseded run and do not diagnose its cancelled jobs. Classify only the newer run's copies once they complete | omnibase_infra#4032 read 2026-09-23T22:25Z: CI run 35928148237 (CI Summary job 107408082605 failed at 22:25:21Z, 37 of 58 jobs cancelled) superseded by CI run 35928201285, created 22:24:51Z and pending |

### T. Timeouts that are not test failures

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| T1 | A product-readiness shadow job is red, the log shows exit 124 or a cancel at `timeout-minutes`, and no test failed | A budget timeout. Since omnimarket#2783 (`7c97ef6a`) exit 124 reports `product_conclusion=timeout`, an infra conclusion. onex_change_control's shadow was scoped by #10828 (`308531a3`). The job is not required; report it and do not fix it on a landing lane | OMN-19194, 2026-09-23T00:57:52Z lane=friction-to-skills item=F15, 2026-09-22T21:40:11Z lane=occ-shadow-timeout |
| T2 | infra_repo `Repo Scripts Tests`, `Repo Scripts DB Tests` or `pre-commit` cancelled at their 10 or 15 min cap, with zero test failures (often "2860 passed" in the log) | Runner saturation, from `pytest -n auto` starting 32 xdist workers per 2-CPU container. Read lab-host-a load first (a read-only `uptime` over ssh to the lab-host-a host, with the login the CLAUDE.md `lab-host-a Server` section gives). Rerun once; if it is cancelled again, report it under OMN-19209 (the cap is infra_repo#1629, still OPEN on 2026-09-23) and stop spending reruns | 2026-09-22T23:03:11Z lane=m4-c10-probe, 2026-09-22T23:22:42Z lane=m4-board-rescope, 2026-09-23T00:02:17Z lane=pc2-runner-register, 2026-09-23T00:55:49Z lane=m4-byo-probe, 2026-09-23T02:15:20Z lane=m4-c17-probe, 2026-09-23T02:18:52Z lane=m4-c14-probe |
| T3 | A job fails in under a minute at "Check out the omnibase_infra sibling" with `API rate limit exceeded` | Shared identity rate limit, fleet-wide. Cut demand, wait for the reset, then rerun the whole run once | remedy 22, 2026-09-20T12:11:38Z lane=ledger-publish-1035, 2026-09-22T00:44:08Z lane=ledger-publish-0030 |
| T4 | `occ-preflight / eligibility` (any caller copy) fails with `[fail_now] body_unreadable`, right after a `##[warning]` line on the preflight's PR read that ends `exited 1: invalid character 'U' looking for beginning of value` | The GitHub API returned a non-JSON body to the preflight's PR read, and the preflight fails closed. The PR did not cause it. If the same log also shows `companion_unmerged ... OCC#<n> is still OPEN`, that is class C2: the landing controller lands the companion first. Once the companion reads MERGED (or none is cited), the landing controller reruns the whole run once. If the rerun fails the same way, it is fleet-wide: check T3 and report it rather than spending more reruns | omnimarket#2817 job 107338322072, omnimarket#2812 job 107343439868, omnibase_core#1745 job 107339244006 (companion OCC#10978, merged by the time of the read), all read 2026-09-23T19:2xZ |
| T5 | A gate that downloads the run's artifacts (omnibase_core `Skip Count Ratchet (OMN-18776)`) fails with `error downloading test-results-<n>: HTTP 503: No server is currently available`, three attempts, then `could not download this run's JUnit reports after 3 attempts`, while every test shard it reads is green | A GitHub artifact-service outage, not the PR. On a non-draft PR, rerun the whole run once. On a draft, or a run created while the PR was draft, do not rerun (D3): the ready flip's fresh runs read the artifacts again. If a rerun fails the same way, it is fleet-wide: report it and stop spending reruns | omnibase_core#1745 job 107364241490 (draft; all 88 `Split` shard copies green), read 2026-09-23T20:55Z and again at 22:07Z |

### R. Rerun limits, the base branch and branch state

| # | Recognise it by | Correct move | Pointer |
| -- | -- | -- | -- |
| R1 | A gate that is its own workflow is still red with identical text after its fix merged to its own repo's trunk | A rerun replays the pinned pre-merge merge ref, so it runs the old validator. The landing controller takes a fresh head (update-branch), or the owning lane rebases or pushes an empty commit before handoff. On a bot PR, re-read `triggering_actor` afterwards | remedy 26, remedy 28 |
| R2 | Dependabot PR: every red job consumes a secret, and `triggering_actor` is `dependabot[bot]` | Rebase or add an empty commit and push under the session identity with the lease form | runbook, Blocker classes |
| R3 | The same failure is red at the base branch tip | Inherited. Compare by **test identity**, never by exact job name: shard counts differ between dev push runs and PR runs and change from day to day (measured on omnibase_infra on 2026-09-23: the dev tip at 22:12Z carried `Tests (Split n/2)`, while PR heads read the same hour carried `n/15` on three PRs and `n/2` on a fourth, and earlier that day `n/10` and `n/4`), so an exact-name read at the base returns zero rows. Run `bash "${CLAUDE_SKILL_DIR}/scripts/base_compare.sh" "$R" <base> '<job family prefix>' '<identity>' ['<identity>' ...]`, passing **every** failure identity from the PR's log, where rc 1 is INHERITED, 0 is NOT-INHERITED and 2 is UNDETERMINED. An identity is a failing pytest node id, or, for a check with no test ids (a lint, a policy or a domain-enforcement job), `line:<the first SPECIFIC failure line of the PR's log>` with its timestamp stripped, which must appear in a red base copy's log. Specific means it names the failure: a violation with a file path, an assertion message, a rule code with its location. Never pass the runner's `##[error]Process completed with exit code 1.` line, a gate verdict (`<gate>=FAIL`, `CI Summary = FAILURE`) or a bare `FAIL`: every red copy of the check prints those, so they match any unrelated base red. The script refuses them and any line with too little specific text (`REFUSED line:...`, rc 2); read step 6 again and take the line that names the violation. At least one identity is required for **every** family: with none, the script reads UNDETERMINED (rc 2), sharded or not, because a red base copy of the same check name proves nothing about the PR's own failure (the base may fail on `src/a.py` while the PR adds a new violation in `src/b.py`). It prints one `INHERITED <id>` or `NOT-INHERITED <id>` line per identity, and rc 1 only when **every** identity is carried at base: a PR that adds a new failure beside an inherited one reads rc 2, and each `NOT-INHERITED <id>` is this PR's own red to fix (class X). INHERITED needs a **failure line** for the test id in a red base copy's log (`FAILED <id>`, `ERROR <id>`, or `<id> ... FAILED`, with the id ending there, so `<id>_bar` and `<id>[other-param]` do not count); a mere mention (a `PASSED` line, a durations or warnings listing) is not a failure. A bare `FAILED <id>` with no ` - <message>` counts only inside pytest's `short test summary info` section, so a gate that echoes its baseline as `FAILED <id>` lines is not read as a base failure. Known limit: an echoed list whose lines carry ` - <message>` still matches, so read the matched line printed after each `INHERITED` before reporting. A family is sharded when the prefix, or any base copy's name, carries a shard marker (`Split`, `n/m`, ...), or the family has more than one copy: prefix `Tests` with the single base copy `Tests (Split 1/1)` is sharded. For a base-head read by hand, `onex scm run-list "$R" --head-sha <base-sha>` returns its runs; `onex scm run-view "$R" --run-id <run-id>` returns jobs and `onex scm job-log "$R" --job-id <job-id>` returns the log tail (at most 64 KiB) for the failure-identity comparison. Report an inherited red and do not fix it inside this PR | 2026-09-20T00:57:52Z lane=deploy-agent-false-success-diag-0016 |
| R4 | Green, then `BEHIND` again because a peer merged (strict up-to-date base) | Update the branch and re-watch. On registry_root `main` the ledger-publish lanes merge every 3 to 5 min, so merge on the exact head as soon as the required checks read green | 2026-09-21T12:14:58Z lane=morning-ground-state-dropped-work-2345, 2026-09-21T04:40:48Z lane=morning-ground-state-dropped-work-2345, 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the infra_repo#1615 row) |
| R5 | `DIRTY` | Usually a branch behind its base, not a fleet gap. Merge the base in; do not chase drift | remedy 32 |
| R6 | The release-identity gate is red because `pyproject` is not ahead of the latest published version, on a PR opened while release-on-merge was publishing | The base sits at a published version until the bot bump PR lands. Wait for the bump, then update the branch. Never lower the version floor | 2026-09-23T00:14:14Z lane=clean-install-deleg, 2026-09-20T21:41:04Z lane=autobind-collision-selfbind-1715 |

### X. Anything else

A red that matches no row is a real failure until proven otherwise. Run R3 first, because an
inherited red is not this PR's to fix. Then hand it to pr-land step 6 (`/omni:pr-land`: worktree,
RED, fix, focused tests, lab readback), and record the new class with the `friction-record` skill
(`/omni:friction-record`) so this table grows.

## 5. Rerun rules, in one place

- **Whole run by default:** hand off through `/omni:pr-handoff` (`needs=land`); the landing controller reruns the whole run once. If the controller sends back a code red, the owning lane fixes it and pushes, then hands off again.
- **`--failed` only** for a plain job-level timeout (T2) in a run with no skipped dependents and no
  body edit since the run started. Never use it after a body edit (P1) or when a dependent is skipped
  (C6).
- **Never** rerun a queued or in-progress run, the same run id twice for the same cause, or a run
  created while the PR was draft (D3), and never rerun a run created before the PR's last ready flip,
  even one that was cancelled by the flip or by a push beside it (D7, OMN-19379). Read both times
  before any rerun on a PR that was ever a draft:

  ```bash
  onex scm run-list "$R" --head-sha "$SHA"
  ```

  This returns head runs with `created_at` and `event`; the landing controller compares them with its last ready-flip time.
  A run whose `created_at` is earlier than the flip is draft-era whatever its `event` reads, and the
  controller takes a fresh head.
- **A rerun replays the original event and the pinned merge ref.** When the stale thing is the event
  (draft state), the ref (a fix in the gate's own repo), or a check name that no longer exists (D2), only
  a fresh head clears it. The landing controller takes a fresh head (update-branch), or the owning lane pushes an empty commit
  in its worktree before handoff (remedy 30).
- **`onex scm workflow-run OWNER/REPO --workflow W --ref BRANCH` always names the head branch** (remedy 31); auto-merge dispatch belongs to the landing controller.
- **Never cancel** `occ-preflight / eligibility` (step 3), and never cancel or `pkill` a run that
  belongs to another lane.
- Record each rerun, with its run id and class, in your STATUS or TERMINAL row.

## 6. Read the log

```bash
onex scm job-log "$R" --job-id <job-id> --tail-bytes 65536 | jq -r .result.text > "$S/job.log"; echo "rc=$? bytes=$(wc -c < "$S/job.log")"
```

It keeps the last 64 KiB of the log (`.result.truncated` says when the head was dropped). The job id is in the watcher's CI `detail` (`onex scm pr-checks`). Check `rc` and the byte count before you grep.

Read the first SPECIFIC failure line of the failing step, and note the step name: a failure at a
checkout step or in the job-started hook is infrastructure, not the diff. The first `##[error]` line is
often only the runner's `Process completed with exit code 1.` (on omnibase_infra#3991 job 107317804928,
Application Database Domain Enforcement, it is the only one), which names no failure. The specific
line sits beside that exit line, above or below the gate's own verdict, so print the window around
it with the env and group lines removed:

```bash
E=$(grep -n 'Process completed with exit code' "$S/job.log" | head -1 | cut -d: -f1); echo "exit line=${E:-none}"
sed -n "$(( ${E:-0} > 25 ? ${E:-0} - 25 : 1 )),$(( ${E:-0} + 5 ))p" "$S/job.log" | grep -v 'Z   [A-Za-z_][A-Za-z0-9_]*: \|##\[endgroup\]\|##\[group\]\|shell: \|Z env:'
```

Take the line that names the violation, the file, the test id or the assertion. On job 107317804928
that is the `docker/migrations/.../091_grant_app_dashboard_savings_series.sql: application target ...`
line printed after `application_database_sql_gate=FAIL`; on a pytest shard it is the
`FAILED <node id> - <message>` line of the short summary, whose node id is the R3 identity. That line,
timestamp stripped, is the `line:` identity for R3. The runner's exit line and a gate verdict
(`<gate>=FAIL`) are not: `base_compare.sh` refuses them. When the exit line is absent (a cancelled or
timed-out job), use `grep -n '##\[error\]\|FAILED ' "$S/job.log"` and read the step it falls in.

## 7. Terminal report

Report exactly one state, with the head sha and the read time (a UTC timestamp from this turn):

| State | Meaning |
| -- | -- |
| `GREEN <sha> <time>` | `ci_state.sh` printed `VERDICT GREEN`: every **required** context's newest copy passes, read from paginated check-runs with the count equal to `total_count`, and no `MISSING`. Optional reds are listed beside it, not hidden |
| `WAITING <class> <sha>` | a known, legitimate wait: C2 companion open, D1, D5 or D6 draft, P2 (CI Summary graded while producers it names still run: its own CI run still `in_progress` in `runs.tsv`), P5 (a newer run of the same workflow at the head supersedes the red copy's run), T2 capacity, or a required context PENDING or MISSING. Name the owner of the next move |
| `RED-REAL <check> <sha>` | a required context is red with class X (or F2/F3 over a real test failure); handed to pr-land step 6 |
| `RED-INHERITED <check> <sha>` | R3 proved the base tip red on the same test identity. Reported, not fixed here |
| `TIMEOUT <sha>` | the lane's watch budget was spent. List the reds that are still open, with their classes |

A handoff table or a peer's report is a starting list, not an answer. Every state claim comes from a read
taken in the same turn (2026-09-23T00:58:02Z lane=friction-to-skills item=F3).

## What the old skill did that is gone, and what replaces it

| Old step (omniclaude 1e33287a0) | State on 2026-09-23 | Use instead |
| -- | -- | -- |
| First action: dispatch `onex:polymorphic-agent` | Agent removed; `grep_guard_no_polymorphic_agent.sh` refuses the reference | Run this skill in the lane you are in |
| `_bin/ci-status.sh` snapshot or `--wait` | Still present, but it wraps the PR checks rollup | Steps 1 and 2 (`ci_state.sh`: required contexts, check-runs, every copy) |
| `wait_for_pr_status` / inbox-wait push mode (OMN-2826) | `omniclaude.services.inbox_wait` does not exist | Step 3 polling |
| `onex run-node` / `onex node node_ci_watch` | Runs (dry run verified 2026-09-23), but reads the rollup and has no class table | Steps 2 and 4 |
| `Skill(onex:ci_fix_pipeline)` fix dispatch | Skill absent | pr-land step 6 |
| Pre-existing failure: auto-dispatch a background fix PR against base | Conflicts with one-lane-per-PR ownership and ledger claims | R3: report the inherited red; the orchestrator dispatches |
| `ModelSkillResult` to `$ONEX_STATE_DIR/skill-results/…/ci-watch.json` | Nothing reads it | Step 7 state in the lane's final message and its ledger row |
| `max_fix_cycles=3`, `timeout_minutes=60` | The limits the brief sets | The lane brief's budget, and "never the same run twice" |

## Guardrails

- Never suppress stderr on a verification read, and prove every zero with a positive control (rule 16).
- Never spell the skip-token prefixes, merge-hold vocabulary or the evidence-source stamp line in prose
  in a PR body, commit message or comment (rule 15). Restoring the real stamp line on its own line
  (C10) is the one exception.
- Never hand-author a change-control companion while the autobind can still mint one (2026-09-23T00:58:03Z
  lane=friction-to-skills item=F7). The rules for hand authoring are in the runbook's "Authoring a
  change-control companion by hand".
- No admin merge, skip tokens, `--no-verify` or `core.hooksPath` override. A label is not a fix: every
  class above has a move.
- This skill reads and reruns. It does not flip ready, arm or merge; those are pr-land steps 4 and 7.
  Before any rerun on a PR another lane holds, check its ledger CLAIM (pr-land step 1).

## Known friction (from prior runs)

Each line gives the symptom, the correct move, and a pointer (a `<timestamp> lane=<lane>` ledger row,
found with the grep at the top). Record new friction with the `friction-record` skill
(`/omni:friction-record`).

> - **A GitHub App check suite sat QUEUED for 13 hours and blocked a PR that was green and armed.**
>   It named no required context, so the required-contexts table read every row green, but GitHub
>   still reported `mergeStateStatus=BLOCKED` on the unfinished suite. `ci_state.sh` now reads
>   check-suites (not just check-runs) on a green-but-BLOCKED MISMATCH and prints
>   `STUCK-CHECK-SUITE` for class A1; `gh pr update-branch` cleared it. → FRICTION
>   2026-09-27T13:25:44Z, omniclaude#2376, OMN-17427
- **A whole rerun of a cancelled push-era run after the ready flip replayed its draft payload** (fourth occurrence). On omnibase_infra#4043 the rerun of the cancelled push-event CI run 35970519445 skipped the test matrix and turned `CI Tests Gate` red, which poisoned the ready run's own rerun; only a fresh head (c7c0d3780) cleared it. D7 and step 5 now forbid rerunning any run created before the last ready flip. → 2026-09-24T09:17:58Z lane=reds-stacked, OMN-19379
- **Rollup green, PR BLOCKED.** Fourteen caller copies of one context stayed failing beside newer successes. Read every copy (steps 1 and 2); rerun those runs or take a fresh head. Measured since: GitHub does not always block on an older copy (omnimarket#2807 read CLEAN beside three), so trust the script's `MISMATCH` line, not the copy count alone. → 2026-09-20T22:40:48Z lane=core-release-successor-1915, 2026-09-20T10:28:37Z lane=core-release-04718-unblock-codex-1845
- **Skipped gate never re-executes.** Four `--failed` reruns over two hours changed nothing; one whole-run rerun cleared it. → 2026-09-20T10:28:37Z lane=core-release-04718-unblock-codex-1845
- **Preflight cancelled and rerun twice.** Its 1500s wait was misremembered as about 180s. Read `occ_preflight_wait.py` and land the companion. → 2026-09-22T23:53:29Z lane=market-shadow-timeout
- **Companion green but never armed.** The preflight timed out on four checks. Arm the companion, then rerun. → 2026-09-22T23:15:13Z lane=omn16856-c17-carrier, 2026-09-23T01:28:32Z lane=c17-finish
- **Real receipt FAIL misread as the fleet false red.** The companion's `nonpass_receipt` named the lane's own test. Read the companion's preflight reason first. → 2026-09-21T17:46:31Z lane=omn18868-67-seam-gates-restart
- **`missing_ticket` on a PR that cites six tickets.** The verdict came from the create event. Rerun the whole run. → 2026-09-22T14:11:18Z lane=occ-10767-opus
- **Draft-era rerun replayed draft state.** The test matrix skipped and `CI Tests Gate` went red. Take a fresh head. → 2026-09-21T23:40:15Z lane=kafka-producer-retry-2, 2026-09-23T01:05:02Z lane=omn17099-backend-overlay
- **Bare `deploy-gate` orphan after ready.** CI Summary's same-name supersede cannot clear it. Take a fresh head while non-draft. → 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the omnibase_infra#3971 row), remedy 30
- **Zero-job cancelled run after ready plus push.** No CI Summary on the head. Rerun the whole run. → 2026-09-22T20:27:44Z lane=market-drain
- **Body edit cancelled the producers.** `cancelled_without_replacement`. Rerun each run whole. → 2026-09-23T00:03:18Z lane=lab-rebuild-unstick, 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the omnibase_infra#3971 row)
- **Body rewrite dropped the stamp line.** The Receipt Gate failed on a PR with a merged companion. Restore the complete pair through pr-land step 2a; preserve the existing body. → 2026-09-20T03:50:05Z lane=runtime-autowire-crashloop-fix-2150
- **CI Summary graded its own wave before the wave formed, or read stale instances.** Wait for the producers, then rerun the summary once or take a fresh head. → 2026-09-21T23:40:17Z lane=kafka-producer-retry-2, 2026-09-23T04:20:28Z lane=infra-release-cut
- **Shadow timeout read as a product failure.** Exit 124 is now `timeout` (infra). → 2026-09-23T00:57:52Z lane=friction-to-skills item=F15, OMN-19194
- **infra_repo repo-scripts and pre-commit cancelled at their caps under lab-host-a load 76 to 396.** Rerun once, then report under OMN-19209. → 2026-09-22T23:03:11Z lane=m4-c10-probe, 2026-09-23T00:55:49Z lane=m4-byo-probe, 2026-09-23T02:18:52Z lane=m4-c14-probe, 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 (the infra_repo#1615 row)
- **Rate-limit failures at the sibling checkout.** A second whole-run rerun failed identically. Wait for the reset. → 2026-09-20T12:11:38Z lane=ledger-publish-1035, 2026-09-22T00:44:08Z lane=ledger-publish-0030, 2026-09-22T00:53:54Z lane=ledger-publish-0030
- **The gate's own fix is merged, and a rerun still fails.** The rerun replays the old merge ref. Take a fresh head. → remedy 26
- **Autobind stopped minting fleet-wide after 00:27Z.** Positive-control against a recent companion before you blame the PR; replay once, then report. → 2026-09-23T02:11:52Z lane=omn19201-response-contract
- **Publisher rerun three times to force a re-mint.** It never re-mints, and the brief forbids it. → 2026-09-21T08:15:05Z lane=omn18944-backup-cronjob-alert-0325
> - **Log grep returned nothing on a red job.** The fetch refused on escape sequences. Pass `--allow-escape-sequences` where `gh api --help` lists it (step 6 detects it) and check `rc`. → runbook B6
- **Answered from a stale handoff table.** Every state claim needs a read from the same turn. → 2026-09-23T00:58:02Z lane=friction-to-skills item=F3
- **Release-identity red right after a release published.** Wait for the bot bump PR, then update the branch. → 2026-09-23T00:14:14Z lane=clean-install-deleg
- **A peer overwrote a lane's body or status file in the shared scratchpad.** Use a lane-unique directory (the top of this skill). → 2026-09-22T23:38:46Z lane=m4-c12-probe, 2026-09-23T01:05:02Z lane=omn17099-backend-overlay
- **Theory before log.** The first log line had already cleared the suspected runtime. → 2026-09-20T08:25:41Z lane=occ-preflight-eligibility-red-0815
- **Step-2 summary awk used bare positional fields.** Loaded with arguments, the harness substituted them, the awk became a syntax error piped into `sort | uniq -c`, and it printed nothing, which read as "no reds". The summary is now `ci_state.sh`; the by-hand awk uses `$(n)` fields under `set -o pipefail` with `rc` printed. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **GREEN was never keyed on the required contexts.** The skill never read them, yet GREEN depends on them (omnibase_infra `dev` requires only `CI Summary`). Steps 1 and 2 now read branch protection and rulesets and key the verdict on them. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **"Protection evaluates every copy" was unverified.** The skill stated it as fact. Measured false on omnimarket#2807 (CLEAN beside three older failing copies), so it is dropped for the newest-copy rule plus a `MISMATCH` line. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **No class for omnimarket `deploy-gate / deploy-gate` red on a draft with no companion.** Added as D5. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **Follower gates were missing.** Only CI Summary was named as a follower. `CI Tests Gate` and `Test-Failure Ratchet Gate` are now F2 and F3. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
> - **The R3 base read failed and compared the wrong thing.** The unencoded `?check_name=` query failed with `PROTOCOL_ERROR`, and exact job names differ between dev push runs and PR runs, so exact-name reads returned 0. R3 now uses `gh api -X GET -f check_name=` and compares by test identity (`scripts/base_compare.sh`). Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **Dead ledger line citations.** The ledger rolled at 2026-09-23T14:00:47Z, and every `ledger:<line>` pointer here pointed past EOF or at an unrelated row. Pointers are now `<timestamp> lane=<lane>`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **A red CI Summary was reported as RED-REAL while its producers still ran.** On omnibase_infra#4017 the newest CI Summary copy failed at 18:31Z with its gates `in_progress` or `<absent>` and its own CI run still `in_progress`. That is P2, a legitimate wait, so step 7 now lists P2 under WAITING. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **No class for a preflight that failed closed on an unreadable PR body.** On 2026-09-23, three PRs read red on `occ-preflight / eligibility` with `[fail_now] body_unreadable` after a non-JSON GitHub API response (`invalid character 'U'`). The table had no row for it, so the red read as a real failure. It is now T4: C2 first if the companion is open, then one whole-run rerun, then report it as fleet-wide. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **A truncated ruleset read and a crash could both pass as a verdict.** `ci_state.py` read `rules/branches/<base>` at the default page size of 30 and never checked for truncation, so a required context on a later page was dropped and the PR could read GREEN without it. An unreadable `total_count` crashed the script with exit 1, which reads as RED, not as an untrusted read. It now reads 100 rules per page and exits 3 on a full page, and every crash in `ci_state.py` or `base_compare.py` exits 3 (a `base_compare.py` crash used to exit 1, which reads as INHERITED). Offline regression test: `tests/test_ci_state.py`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **The Delivery-status paragraph said the fixes were in the installed 0.4.9 cache.** At 2026-09-23T20:48Z, and again at 22:11Z, that cache was byte-identical to plugin-tooling-pkg main 2671330 and carried none of them. The paragraph now says they are staged only. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **The by-hand ruleset read was unpaginated too.** It read `rules/branches/<base>` at the default page of 30 rules with no row count, the same truncation the script had. It now reads `--paginate` at 100 per page and prints `rows=`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **No follower class for Contract Compliance's CI-checks probe.** On omnibase_core#1745 the newest `Contract Compliance Check` failed on `[X] test_passes: Failing CI checks: ...` lines that only mirror other checks, beside one real failed command probe; nothing in the table separated the two, so the whole check read as a real failure. It is now F4. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **Person identifiers in commands and pointers.** T2 spelled an ssh login and D1 cited a row by a personal actor tag. T2 now points at the CLAUDE.md `lab-host-a Server` section for the login, and D1 cites the row by its timestamp. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **No class for a gate that failed on a GitHub artifact outage, and D5 covered omnimarket only.** On omnibase_core#1745 (draft) `Skip Count Ratchet` failed on `HTTP 503` artifact downloads with every shard green, and `Contract Compliance Check` failed on a missing `Evidence-Source:` line. Neither matched a row, so both read as real failures. The first is now T5, and D5 now names the omnibase_core form. The R3 shard names also moved again within the day (PR heads at `n/15` and `n/2`, the dev tip at `n/2`), so R3 no longer rests on one shard count. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **The T5 row sat outside its table.** A blank line between T4 and T5 split the T table, so T5 rendered as a stray paragraph rather than a class a lane matches a red against. The blank line is gone, and `tests/test_skill_md.py` now fails on any table row that sits outside a table (plus the arg-substitution, home-path and line-citation lints). Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **A red copy from a superseded run read as RED.** On omnibase_infra#4032 at 2026-09-23T22:25Z, `CI Summary` failed in a CI run whose jobs were being cancelled, while a newer CI run at the same head sat pending. The script read RED, and no class said to wait for the newer run, so a lane would diagnose or rerun a superseded run. `ci_state.py` now reads such a copy as PENDING and names the newer run, the table has class P5, and step 7 lists P5 under WAITING. Regression cases `p5-*` in `tests/test_ci_state.py`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **No class for omnibase_core's `Tests Gate` on a draft.** On omnibase_core#1745 (draft) `Tests Gate` failed with `test-parallel was SKIPPED but the docs-only precondition does not hold`: the draft admission gate skips the test matrices on every draft to `dev`, and the gate fails closed on that skip. No row matched, so it read as a real failure. It is now D6. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage).
- **R3 read INHERITED on a mention, not a failure.** `base_compare.py` decided INHERITED when the failing test id appeared anywhere in a red base shard's log, including as `<id> PASSED` and as the prefix of a different failing test (`FAILED <id>_bar`), and on a family-name match alone for a sharded family given no test id. A green omnibase_infra shard log (job 107389025429) carries ten passing node ids, so this read a PR's own red as inherited. It now needs a failure line for the id with an id boundary, and refuses (rc 2) a sharded family with no id. Regression cases `r9-b*` in `tests/test_ci_state.py`. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **A queued copy with no `started_at` sorted oldest.** Beside an older successful copy, the newest (queued) copy of a required context sorted first, so the context read green and the PR GREEN while a rerun was still to report. A copy that has not completed and has no `started_at` now sorts newest, so the context reads PENDING. Regression case `r9-x1`. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **R3 dropped a PR's new failure when another failing id was inherited.** With two failing test ids, `base_compare.py` read INHERITED (rc 1) when either one failed at base, printed nothing for the other, and so turned the PR's own new failure into "report, do not fix". It now prints one line per id and reads INHERITED only when every id fails at base. It also treats a family as sharded when any base copy's name carries a shard marker, so prefix `Tests` beside the single copy `Tests (Split 1/1)` no longer reads INHERITED by name. Regression cases r6-bc1, r6-bc1c and r6-bc4 in `tests/test_ci_state.py`. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **A completed copy with no `started_at` sorted oldest.** An older success beside a newer cancelled copy that GitHub never stamped as started read GREEN. Copies are now ordered by `started_at`, else `completed_at`, then id, and a copy with neither timestamp sorts newest. Measured: 0 of 1107 completed copies on 11 live PRs lacked `started_at`. Regression cases r6-x1, r6-x1b and r6-x1c. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **No class for an autobind that declined because a hand-authored companion exists.** On omnimarket#2820 eligibility failed with `skip:DEFER_HAND_AUTHORED` naming the open draft OCC#10767, and no row matched, so the red fell to class X. Added C11. Fixed 2026-09-23 by the omni-skill-fixes pass.
> - **The step-1 head read stopped on GraphQL exhaustion.** At 2026-09-23T23:50Z every `gh pr view` failed with `API rate limit already exceeded` while the REST core budget was full, so `ci_state.sh` (and pr-land's label read) exited 3 on every PR. Both now fall back to REST `pulls/<N>` for the same fields; any other `gh pr view` failure still exits 3. Regression cases r6-pr-view-failure-is-untrusted and r6-graphql-rate-limit-falls-back-to-rest. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **R3 read INHERITED by job name for a non-sharded check.** With no test id, a non-sharded check red at the base tip read rc 1 INHERITED whatever the base failure was, so a PR's own new violation beside an unrelated base violation was reported, not fixed. `base_compare.py` now requires a failure identity (a test id, or `line:<first error line>`) for every family and reads UNDETERMINED (rc 2) without one. Regression cases v8-b1, v8-b1b, v8-b1c and v8-b1d. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **With no required contexts, a failing legacy commit status read GREEN.** `ci_state.py` said it keyed on every check-run "conservatively" but ignored commit statuses, so a failing `ci/jenkins` status beside a green check-run read GREEN. With no required context on either source it now keys on every check-run name and every status context. Regression cases v8-a1, v8-a1b and v8-a1c. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **R3 read an id echoed in a gate's baseline dump as a base failure.** A red base `Tests Gate` log that printed `known failures baseline:` then `FAILED <id>` read INHERITED for a PR's new failure of that id. A bare `FAILED <id>` line now counts only inside pytest's short test summary section. Regression cases v8-b3, v8-b3c and v8-b3d; live control omnibase_infra#4035 still reads INHERITED on the real summary line. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **R3 read INHERITED on a runner line, so a PR's own red was reported as not this PR's to fix.** The R3 row and step 6 said to pass the first `##[error]` line as the `line:` identity. On omnibase_infra#3991 job 107317804928 that line is only `Process completed with exit code 1.`, which the red dev-tip job 107433716342 also prints, so `base_compare.sh` read INHERITED whatever the base failure was. The script now refuses runner and gate boilerplate and low-specificity lines (rc 2, `REFUSED line:`), and the R3 row and step 6 say to take the first specific failure line. Regression cases y1-y4 and yz1-yz3 in `tests/test_ci_state.py`. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **No class for an autobind that refused permanently on a ready PR.** On omnibase_infra#4037 the change-control gates failed on `skip:NO_RED_DERIVABLE_CHECK` with "a deliberate, permanent refusal", and no row matched, so a lane would have rerun the publisher, which the log says cannot help. It is now C12: hand-authored companion by the owner, then C2. Found by the live classification of this pass. Fixed 2026-09-23 by the omni-skill-fixes pass.
- **A hand-authored companion's self-bind receipt landed under `drift/occ_bindings/`** (matching an older cross-repo precedent, OCC#11152). That path is never read: `omnibase_core.validation.validator_occ_merge_eligibility` resolves a receipt only at `drift/dod_receipts/<TICKET>/<ITEM_ID>/`, per `onex_change_control/CLAUDE.md`, so `occ-preflight / eligibility` read `missing_receipt` with no signal that the file existed at the wrong path. Author every hand-authored receipt at `drift/dod_receipts/<TICKET>/<ITEM_ID>/`, never `drift/occ_bindings/`, whatever an older precedent shows; see pr-land's "Authoring a change-control companion by hand" pointer. → 2026-09-27T05:16:47Z lane=land-omnimarket-2976-83, OMN-15247 lineage
- **A second consumer PR on a multi-consumer ticket bound the wrong evidence, or errored closed.** `omnibase_core.validation.validator_receipt_supersession`'s target-aware resolution (OMN-16432) binds a shared `evidence_item_id` to whichever consumer PR's `replacement.pr_number` matches; once ANY `dod_evidence` entry for that key already carries one `<CHECK>.supersede.<PR>.yaml`, every later consumer that touches the same entry must add its OWN `<CHECK>.supersede.<PR>.yaml` naming its own PR number, or resolution falls through to the legacy highest-suffix tier and `resolve_supersession` can bind a different consumer's evidence. An entry with zero prior supersede files needs no new file. → 2026-09-27T05:16:47Z lane=land-omnimarket-2976-83, OMN-15247 lineage
