---
name: pr-land
description: Land one pull request end to end, from claim through live read, hold check, ready flip and arming, CI triage (change-control cascade vs real red), fix, squash merge on the exact head, and readback and ledger. Use whenever a lane is told to get a PR merged.
prosthetic: true
replaces_when: "The merge-queue governor (node_pr_arm_gate_compute + node_pr_lifecycle_merge_effect) has an `onex skill` entry and lands three PRs end to end with a typed receipt, handling draft and ready-flip arming itself. On 2026-09-22 `onex skill auto_merge` returns `Unknown skill` (the mapping was deregistered by OMN-14151), ci_watch has no skill mapping, and /onex:auto_merge points at nothing."
restored_from: "omniclaude b94357001 plugins/onex/skills/auto_merge/SKILL.md (with 7105ce585 pr_polish and 36ea99867 ci_watch)"
ticket: OMN-19210
---

# PR land (prosthetic)

One PR, one lane. Set these on their own lines first, and use them everywhere below:

```bash
R=OmniNode-ai/<repo>          # owner/repo
REPO=<repo>                   # bare repo name
N=<number>
LANE=<your lane name>
S=$SCRATCH/<lane>             # lane-unique scratch dir
export ONEX_LEDGER_PATH="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
export registry_root="${registry_root:?set registry_root}"
```

Every script this skill calls ships in the plugin, prints its evidence and ends with one verdict
line. None writes to the ledger, GitHub or Linear. `tests/test_skill_md.py` in this skill's
directory lints this file offline. The one script that touches anything local is
`scripts/runtime_class.sh`: it executes the repo's rebuild trigger in dry-run inside the canonical
clone's existing venv, through `uv run --frozen --no-sync`, so it neither syncs packages nor rewrites
the lock. An exit code a step does not name is never a pass.

## 1. Claim

1. Run `python3 "${CLAUDE_SKILL_DIR}/scripts/claim_guard.py" "$R#$N" --lane "$LANE"` as the first
   action on **every pass**, including a second or later pass over the same PR. It reads the claim
   registry and the live ledger plus archive rolls in the canonical 7-day window, using the shared
   45-minute lane-liveness rule. Its ledger owners are exactly merge-drain's step 2 owners, from the
   same code (`drain_map.ledger_owners`, OMN-19846): an open CLAIM matched by its own fields and not
   handed off since, or a MSG routing the PR to a worker lane. A MSG to a dispatcher lane (the
   orchestrator, a drain, the landing identity), an OUT OF SCOPE or handed-off mention, a `ticket=`
   quoted in prose, any ticket at all (a CLAIM owns a PR only by naming it in `pr=`, as repo#n, by its head
   branch or by its exact worktree path, OMN-19998), and a STATUS, HOLD or FRICTION row
   naming the PR do not own it, so a PR the drain map frees is not refused here. A stacked PR or a
   change-control companion with no owner of its own inherits its open parent's owner, as the map
   does: the guard reads the parent live (the PR the companion's title names, or the open PR whose
   head branch is the stacked PR's base) and a refusal carries `via-parent=<repo#n>`. It also checks a
   local worktree when the freshest PR-specific registry or ledger activity inside 20 minutes
   belongs to another lane that has not since ended its part (TERMINAL, `handed-off=`, hand-back
   MSG): a tracked or untracked file modified inside the same window is correlated to that lane (an
   ownership stop, not proof of which process wrote the file). A refusal exits `1`, prints
   `check=<registry|ledger|worktree> owned-by=<lane>`, and writes nothing. Stop and report every
   finding. Exit `2` is untrusted and is also a stop; only `VERDICT CLEAR` / exit `0` proceeds.
2. `grep -nE "pr=$N\b|#$N\b" $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md | tail`. If there is an
   open CLAIM by another lane (no TERMINAL or CLOSEOUT after it) that names this PR as its own, stop
   and report. A CLAIM listing the PR as OUT OF SCOPE or handed off is not a claim on it.
3. `python3 $registry_root/omniclaude/scripts/pr_claim_registry_cli.py list`. If a claim is held, stop. Otherwise
   run `... claim <owner/repo#N> --action merge` **without** `--lane`.
4. Append the ledger CLAIM (lane rules block: cost sentence, `actor=`).

## 2. Read live, never from the brief

**Read the PR watcher's state first; call GitHub only right before a mutation** (RULING
2026-09-27T18:05:21Z, OMN-19852). The launchd PR watcher (`ai.omninode.pr-watcher`) keeps every open
PR's head, base, draft flag, labels, auto-merge, title, body and its CI verdict at that head (red and
pending names) in a local state file, re-read every five minutes. Every pre-check those facts answer
reads the state, not GitHub:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/pr_state_local.py" --pr "$R#$N"; echo "rc=$?"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/pr_state_local.py" --pr "$R#$N" --json > "$S/local.json"
```

`rc=0` prints one line (`head= base= draft= armed= labels= ci=GREEN|RED|PENDING|UNREAD red= pending=`),
and the JSON carries `.facts.title` and `.facts.body`. Use them for the production-gate, ticket,
rule-15, hold-label and draft checks below and for the CI verdict. When `ci=PENDING`, or `ci=UNREAD`
(the watcher has not read this head yet) and you have nothing to mutate, hand off (step 5) with no
GitHub read at all. `rc=3` prints why the state cannot answer (stale, missing, PR absent): read GitHub
with `pr_snapshot.py` as below, and name the reason in your row.

GitHub (`pr_snapshot.py`, `ci_state.sh`) is read only as the **exact-head check immediately before a
mutation**: the ready flip, an arm, a merge, a rerun, an update-branch, and the comment read for a lab
readback the body lacks. Never re-read a PR to see whether something changed: the watcher re-reads CI
and reports a change to the landing lane by ledger MSG.

Every GitHub read of a PR and its checks in this skill goes through `scripts/pr_snapshot.py`: one GraphQL request
returns the head, draft flag, labels, mergeStateStatus, title, body, the last comments, auto-merge,
the repository's `allow_auto_merge`, the last ready-for-review time, and (with `--full`) every
check-run copy, the required contexts and the workflow runs. It reads the raw check-run status and
conclusion, never a rendering, and spends GraphQL points instead of about eight core REST requests
per read (OMN-19586). Exit 3 prints `UNREADABLE <R>#<N>: <reason>` and means the read could not be
trusted: stop and re-read, never proceed on it.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --full --json "$R#$N" > "$S/pr.json"; echo "rc=$?"
jq -r '.prs[0].title, .prs[0].body' "$S/pr.json" | grep -oE 'OMN-[0-9]+' | sort -u
```

Each condition below says what to do when it fails. A failed condition never becomes a note in a
row while the lane carries on.

| Condition | When it fails |
| -- | -- |
| `base=main` in `onex_change_control` or `infra_repo` means this is a **production-gate PR** | Stop. Report `NOT-LANDABLE production-gate <R>#<N>`. A lane does not land it |
| The title carries an `OMN-n` (pr-title gate) | Stop and report `NOT-LANDABLE no-ticket-in-title`. A retitle moves the Linear attachment, so the PR owner does it |
| Title and body cite exactly one ticket | With more than one, do not flip or arm. Report the list to the orchestrator: each cited ticket needs its own `dod_evidence` and companion contract, and two companions writing one contract conflict (see the 2026-09-23T01:28:32Z lane=c17-finish row). With none, stop as above |
| The body never spells the skip-token prefixes, merge-hold vocabulary or the evidence-source stamp line in prose (rule 15) | Stop and report `NOT-LANDABLE rule-15-prose`. Do not edit the body yourself: a body edit cancels the producers (ci-watch class P1) and re-attaches the tickets |
| A code change carries its lab readback (host, lane, command, observation) in the body **or** a PR comment | If you own the change, run the lab proof (`/omni:ticket-pipeline` step 7) and post the readback as a comment. Otherwise stop and report `WAITING lab-readback <R>#<N>`. Do not flip ready without one |
| `R=OmniNode-ai/plugin-tooling-pkg` and the PR changes `plugins/<p>/`: the PR leaves the plugin version alone, or moves it above main's in both `plugin.json` and the `.claude-plugin/marketplace.json` entry (OMN-20497) | No bump is required: a post-merge bot PR bumps. The required `validate-plugin` check refuses a version a PR lowered or broke; fix that by putting main's value back. Never add a bump to a PR |

Since OMN-20497 (operator RULING 2026-10-04T09:26:32Z lane=review-session-9143) an plugin-tooling-pkg
PR does not bump the plugin version. Every bump PR was colliding with every other on a strict `main`.
After changes land, `.github/workflows/plugin-version-bump.yml` opens or updates one bot PR,
`chore(OMN-20497): post-merge plugin version bump`, which the landing controller lands.

Classify the PR as runtime-affecting or not before the ready flip, by asking the PR's own repo's
rebuild trigger in dry-run. A runtime-affecting merge redeploys the lab (rule 24), needs its lab
readback (the table above) and follows any runtime-merge sequencing ruling in force:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/runtime_class.sh" "$R" "$N"; echo "rc=$?"
```

`rc=0` prints `RUNTIME-AFFECTING`, `rc=10` prints `NOT-RUNTIME-AFFECTING` (a repo with no rebuild
trigger reads this way), and `rc=3` means it could not classify: treat that as runtime-affecting.
The trigger is read from the canonical clone `$registry_root/<repo>`, so the script prints that clone's
HEAD beside the verdict; a stale clone classifies with stale rules.

Decide `substantive_conflict` (`mergeable_state=dirty` or any doubt about the squash result) with a
real three-way merge, never a two-dot `git diff`. A two-dot diff between the live base and the PR's
head lists every file the base branch has gained since the PR's fork point as if the PR deleted it,
so a clean PR reads as a conflict on every file dev gained meanwhile (measured on
omnibase_infra#4178, 2026-09-27: ~1.5 lane-hours lost across four lanes to exactly this false
positive). Bring both tips into the canonical clone first, through the canonical-clone sync's
refresh rather than a `git fetch` (the lane git-fetch guard, OMN-20495, refuses a lane fetch), then:

```bash
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh "OmniNode-ai/$REPO" --branch "$BASE_REF" --branch "$HEAD_REF" --wait   # the PR's baseRefName and headRefName
# BASE = the live base branch tip sha, e.g. origin/dev; HEAD = the PR head sha
bash "${CLAUDE_SKILL_DIR}/scripts/conflict_check.py" "$REPO" "$BASE" "$HEAD"; echo "rc=$?"
```

`rc=0` prints `VERDICT SUBSTANTIVE_CONFLICT=false` and the resulting tree oid: report
`substantive_conflict=false`. `rc=1` prints one `CONFLICT <path>` line per real conflicted path
(never inferred from a two-dot diff) and `VERDICT SUBSTANTIVE_CONFLICT=true paths=<n>`: report
`substantive_conflict=true` and cite the path list. `rc=2` means the check could not run
trustworthily (a sha not fetched, no canonical clone): treat as unresolved and run the refresh above or read again (never `git fetch`, OMN-20495),
never as clean or conflicting. The script writes only a loose tree object; it never touches the
index, the working tree or a ref.

## 2a. Compose or repair body evidence as a pair (OMN-20054)

The PR owner uses `scripts/pr_snapshot.py --body-file` before creating a body or making an
otherwise-authorized evidence repair. This mode is offline: it reads no PR or CI state and writes
only the named output. It emits the evidence-source stamp and evidence-ticket line together and
refuses either line without its partner, duplicate lines, malformed values or a changed existing
line. It never mints a companion or authorizes a body edit.

Save the prior body from the trusted snapshot (`.facts.body` in the watcher JSON) to a file.
Pass that file as `--previous-body-file` for every replacement or repair; omitting it is only for
initial creation. A replacement draft without evidence inherits the exact prior pair. An incomplete
prior pair needs a complete owner-verified pair in the draft or both explicit arguments, preserving
the surviving line verbatim. An incomplete draft is refused even with explicit arguments.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --body-file "$S/draft-body.md" --previous-body-file "$S/previous-body.md" --out "$S/paired-body.md"
```

For a verified hand-authored companion, use the same command with both `--evidence-source <OCC
companion reference or commit>` and `--evidence-ticket <ticket>`. With neither argument, an initial
unstamped body stays unstamped for autobind. Repeated composition does not duplicate the pair.
Only exit 0 makes the output usable; exit 64 refuses it and leaves an existing output untouched.
Pass the absolute output path to the authorized body writer. Keep lab corrections in author
comments; never rewrite a body just to add lab proof. Never delete the stamp or relax its guard.

## 3. Holds

Run the pause check. It is read-only, reads the whole live ledger with no tail cap, and reads the
PR's labels live:

```bash
export ONEX_LEDGER_PATH="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
bash "${CLAUDE_SKILL_DIR}/pause_check.sh" "$R" "$N" "<your lane>"
```

`${CLAUDE_SKILL_DIR}` is filled in by the harness with this skill's own directory. If you are
reading this file somewhere other than a loaded skill, run `pause_check.sh` from the directory that
holds this `SKILL.md`. It prints one line per finding and a verdict:

| Line | What it found |
| -- | -- |
| `LABEL` | a label on the PR in the hold family (`hold:*`, `do-not-merge`, `wip`, `blocked`, ...), except the auto-merge member |
| `ARM-OFF` | the hold family's auto-merge member, the auto-merge workflow's arm gate (`check_auto_merge_hold.py` `HOLD_LABELS`, OMN-18179). **Not a stop:** never arm the PR (skip the arm in step 4) and merge it on the exact head in step 7 once the required checks read green. It never cancels another finding |
| `HOLD` | a HOLD row with no `RELEASE re=<its id>` and no passed `until=`, scoped to this PR, to its repo (`repo=` with no `pr=`), or to your lane or `to=all`. A HOLD needs no `to=` to apply. A `surface=` lease holds a proof surface, never a PR or a repo |
| `PR-ROW` | a row naming this PR, by repo **and** number, whose text pauses it (hold, do not merge, standalone, merge alongside), not lifted by a later RELEASE, or lifting RULING or OPERATOR-CONSENT, naming the PR. A report never pauses a PR: STATUS, TERMINAL, FRICTION, CORRECTION and ACK rows are `CONTEXT` (`drain_map.py` `REPORT_TYPES`, OMN-19852). A lane that means to stop another lane writes a HOLD, or a MSG through `/omni:ledger-msg` |
| `REPO-PAUSE` | a row that declares a merge pause on the repo, as `drain_map.py` `repo_pause_lines` decides it, so pr-land and the drain map use one matcher: a STATUS or RULING row with no `pr=` or `state=` field, whose present-tense instruction pauses merges ("runtime merges stay paused", "hold every runtime merge", "no other merges", "merge freeze"), scoped by its `repo=` field or, with none, by naming the repo in the pause sentence. A lane's own "No merge, no ready-flip" is a description, never a pause, and so is a window-close report (`window=closed`: "no other merge on omnimarket during the window") and a row that carries `lifts-pause=` (OMN-22348). A later row carrying `lifts-pause=<the pause row's ts>` lifts exactly that pause, read by the same `drain_map.py` reader the drain map uses. Not lifted by a later row on the repo or a release naming this PR |
| `PARKED` | the repo is parked by operator ruling (`drain_map.py` `PARKED_REPOS`): the drain map classes the same set `held(parked)`. Lifting a park is a new ruling (OMN-19852) |
| `ORDER` | a row naming this PR that orders it (must land after, merge order, lands first). **Not a stop.** The check prints the landing order from `drain_map.py` `LANDING_ORDER`: companions land first, on their own CI, and never wait on their parent. Each PR an `ORDER` row names is then read live and printed as `ORDER-STATE <repo>#<n>`: a merged one satisfies the order, a closed-unmerged one is an `ORDER FINDING` (the dependant needs its own decision), an open or unreadable one still orders the PR. Never wait on an order whose predecessors are all merged or closed (OMN-19852) |
| `CONTEXT` | every other row naming this PR. Not a stop, but read each one before acting |

Exit `3` (`VERDICT: PAUSED`) means **stop**: leave the PR draft (or disarm it, step 4), and report
every finding line. Exit `2` means the check could not decide (the label read failed, the ledger is
unreadable): that is a stop too. Exit `0` is clear. Your own lane's rows are skipped except its HOLD
and RELEASE rows, which still apply. Pass your lane name. A repo-wide pause lifted in unparsed prose reads
as `REPO-PAUSE`: read the newest such row, and if it is lifted, say which row lifts it in your
report rather than proceeding silently.

If a merge-order RULING sequences this repo (for example "clear X first, then Y, and no other
runtime-affecting PR until Y reads green"), respect it even when the check is clear, and say which
row holds the PR. An order written in a STATUS row is not such a ruling: it is context. A
change-control companion is never behind its parent in any order: it lands first (OMN-19852, the
onex_change_control#11522 / omnimarket#2968 mutual wait).

## 4. Ready and arm

A draft is **not** a dropped change-control mint. Its autobind outcome is `DECLINED` / `PR_DRAFT` by
design, and the downstream change-control contexts fail because of it. Do not hand-author a companion
for a draft.

**Guardrail (the 2026-09-23T02:09:09Z lane=friction-f8-correction row):** immediately before this
ready flip (`onex scm pr-ready OWNER/REPO#N`), and again immediately before the handoff, rerun
step 3's pause check **and** the `/omni:ledger-msg` inbox check (section 4 there) for your lane
name, which also catches a canonical `MSG` row addressed to you by id. Run each as its own command,
not chained to the flip or the arm. A SendMessage pause sent to you while you are working is not
guaranteed to arrive before you act. It can sit undelivered for hours and land only when your turn
ends. The ledger read is the only check that reaches you reliably, so do not treat a quiet inbox as
"no hold in force."

When no hold applies:

```bash
HEAD=$(python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --field headRefOid "$R#$N")
onex scm pr-ready "$R#$N"
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" "$R#$N"   # read back draft=, auto= and head= on its one line
```

If step 3 printed `ARM-OFF`, stop after the ready flip and its readback: do not arm, by hand or
otherwise, and merge in step 7 once the required checks read green. Removing that label is the
landing lane's call only (RULING 2026-09-24T14:21:58Z), and a merge on the exact head does not need
it removed.

The autobind callers fire on `ready_for_review` in every product repo (infra_repo since #1618).
`auto-merge.yml` arms on the flip wherever OMN-19216 has landed. If `autoMergeRequest` still reads
null after the flip, hand off through `/omni:pr-handoff` (`needs=land`) and stop touching it.
The landing controller arms only where `allow_auto_merge` is true, on the exact head it read,
so a push after that read cannot ride the arm.

Where `allow_auto_merge` is false (registry_root, omnibase_compat, omniintelligence, omnibase_spi and
knowledge-base on 2026-09-16), do not arm. Merge in step 7 once the required checks read green. The
merge verb always follows the CLAUDE.md Merge Queue Policy: `--squash` always, and `--auto` only
where `allow_auto_merge` is true.

## 5. CI triage on the head sha

**Push, hand off, exit; the PR watcher reports CI results.** Read CI once, at the head you have. Never poll, `--watch` or sleep for a check to finish. When the verdict is PENDING, or you have just pushed a fix, hand the PR off at that head (`/omni:pr-handoff`) and exit: the PR watcher (the launchd agent `ai.omninode.pr-watcher` in ops_tooling_pkg, every 120 s) reads that head's check-runs and reports GREEN, or RED with the failing contexts, to the landing lane by ledger MSG. A red comes back to the owning lane as a MSG, and a fix lane is dispatched for it. The watcher also arms a green change-control companion of an open parent and reruns a parent's cascade reds once its companion merged, so neither needs a lane.

Take the verdict from the watcher's state first (step 2's `pr_state_local.py` line: `ci=` at
`head=`). `PENDING` or `UNREAD` means hand off now, with no GitHub read. The reader below takes the
same verdict itself: `ci_state.sh` reads the watcher's state first, and while that state is fresh it
prints `VERDICT GREEN|RED|PENDING <sha> ... source=watcher` with zero GitHub requests (OMN-20421). **That
line is a valid step-5 verdict**: accept it for triage and for hand-off, and do not repeat the read to
see whether something changed. It reads GitHub only when the state is stale, missing, at another head or
holds no CI read for this PR (a draft), and then it prints why. Run `ci_state.sh --live` (the reader
below, forced to GitHub) only as the exact-head check right before a mutation: a merge or an arm on
GREEN, a rerun on RED. The watcher keys on every check-run name it read, so its GREEN does not see a
required context nobody has reported yet or `mergeStateStatus`, and its RED carries names, not run and
job ids. A watcher RED names the only checks whose logs you may read: take their run and job ids from
`--live` (`reds.tsv`), never read a log of a check the state does not name red.

**Jev decides the class of a red first, on every repository but `docs_repo` (OMN-19432; RULING 2026-10-13T18:34:53Z, OMN-20106).** Before you act on a RED
verdict, ask `delegation_step.py decide --preset ci-cause` for each required red (the command and the facts it
needs are in `/omni:ci-watch` step 4), and `--preset pr-triage` when the question is fix, rerun or wait. It is
a second opinion at 3 cents per 447 questions, never the gate: the reader below and ci-watch's class table
decide what is done.

Read check-runs, never the rollup, **paginated**, and key the verdict on the base branch's
**required** contexts. Run ci-watch's reader (`/omni:ci-watch` steps 1 and 2):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/ci-watch/scripts/ci_state.sh" "$R" "$N" "$S/ci"; echo "rc=$?"          # the watcher's verdict while fresh
bash "${CLAUDE_PLUGIN_ROOT}/skills/ci-watch/scripts/ci_state.sh" --live "$R" "$N" "$S/ci"; echo "rc=$?"   # the exact-head check before a mutation
```

On GitHub (`--live`, or a state that cannot answer) it reads through `pr_snapshot.py --full` (one GraphQL
request) and falls back to the paginated REST endpoints only when the snapshot cannot read the PR, saying so. It prints
`check-runs read=<n> total_count=<n>`, and exits 3 unless the two are equal. It also
prints each required context (branch protection plus rulesets) with its newest copy's state, and one
`VERDICT GREEN|RED|PENDING` line (`rc` 0, 1 or 2). Every non-green copy, required or optional, with
its run and job id, is in `$S/ci/reds.tsv`. If you read by hand instead, read the full snapshot
and compare the row count with the total it proves:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --full --json "$R#$N" > "$S/snap.json"; echo "rc=$?"
jq -r '.prs[0].check_runs_total' "$S/snap.json"
jq -r '.prs[0].check_runs[]|[.name,.status,(.conclusion//"-")]|@tsv' "$S/snap.json" > "$S/cr.tsv"; echo "rc=$? rows=$(wc -l < "$S/cr.tsv")"
```

An unpaginated read returns only the first 100 rows. On omnibase_infra#3991 (149 rows then, 179 on
2026-09-23) it missed the one failing required context, `CI Summary`.

Classify every red on a required context, and every red that CI Summary names. The short table:

| Red | What it is | Remedy |
| -- | -- | -- |
| `occ-preflight/eligibility`, `verify/verify`, `OCC Companion Merged Gate`, `CI Summary` together | change-control cascade | Read the body's **first** evidence-source companion PR. If it is MERGED, rerun the whole run. If it is OPEN, land the companion first, because it merges first. If the PR is draft, see step 4. The cascade can have a 5th run: after those reruns, re-fetch check-runs and rerun any run still carrying a non-success conclusion on an `EXPECTED_EXTERNAL_CONTEXTS` name (found via its own `details_url`) — e.g. a separate workflow's own OCC Preflight Dependency job, left stuck skipped from before the companion merged — before assuming CI Summary will go green |
| Receipt or deploy gate names a missing evidence-ticket line beside a stamp | incomplete evidence pair (ci-watch C13) | The owner repairs both lines through step 2a, preserving the existing stamp; a rerun alone cannot fix the body. Hand the result to the landing controller |
| `missing_ticket` with an empty ticket list on a PR whose title cites one | the verdict was taken on the create event, before the body was set | Rerun the whole run. Do not "fix" the title |
| a gate that reads the evidence-source companion, red on a **draft** with no companion: omnimarket `deploy-gate / deploy-gate` (log `DEPLOY GATE FAILED: ... no cited ticket has deploy DoD evidence`) or omnibase_core `Contract Compliance Check` (log `PR body is missing required 'Evidence-Source:' line`) | draft residue (ci-watch D5) | Nothing to rerun. It clears when the ready flip mints the companion |
| `CI Tests Gate`, `Test-Failure Ratchet Gate` beside a red `Tests (Split n/m)` | followers of the test matrix | Diagnose the red shard's own log. The followers clear with it |
| after the ready flip, a run created **before** the flip (a push-event or draft-era run: its `created_at` is earlier than the PR's last `ready_for_review` event) reads cancelled or red, or CI Summary names its rows | draft-era run (ci-watch D3 and D7, OMN-19379) | **Never rerun it**, whole or `--failed`. A rerun replays the draft payload: the test matrix skips, `CI Tests Gate` goes red, and those fresh reds on the head poison the ready run's own rerun. The landing controller takes a fresh head (update-branch) while non-draft, or the owning lane pushes an empty commit before handoff |
| a check cancelled after a ready flip, push or body edit (`cancel-in-progress`), in a run created **after** the last ready flip | concurrency cancellation | if a newer run of the same workflow is already queued or running at the head (ci-watch P5, which `ci_state.sh` reads as PENDING), wait for it and never rerun the superseded run; otherwise rerun the whole run |
| timeout at the job ceiling with no test failed, under fleet load | capacity | rerun once, then report |
| anything else | a real failure | fix it (step 6) |

Hand off through `/omni:pr-handoff` (`needs=land`); the landing controller reruns the whole run once. Never use `--failed` after a body edit, never
rerun a run that is still queued, and never rerun a run created before the PR's last ready flip.
Read both times before any rerun on a PR that was ever a draft:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --field lastReadyForReviewAt "$R#$N"
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --full --json "$R#$N" | jq -r '.prs[0].workflow_runs[]|select(.id=="<run-id>")|[.event,.created_at]|@tsv'
```

A run whose `created_at` is earlier than the flip is draft-era whatever its `event` reads (`push` or
`pull_request`), and the move is a fresh head, never a rerun. Do not wait for a rerun or a fresh head to finish: hand off and exit, and the PR watcher reports the result. This table is the short form. For the
full decision table (draft residue, replayed reruns, stale copies, base-inherited reds, timeouts), the
rerun rules and log reading, run the `ci-watch` skill (`/omni:ci-watch`). Every blocker class has a
remedy. A label is not a fix.

## 6. Fix a real red

Work in `$registry_root/worktrees/<ticket>/<repo>/`. Never stash, reset or use `--no-verify`.
Reproduce RED, fix, run focused tests only, exercise the change on the lab, post the lab readback as
a PR **comment** (never a body edit — a body edit on a PR citing ticket identifiers re-attaches and
re-flips those tickets), push. Draft the comment and the commit message through step 6a. Evidence may be hand-authored only from artifacts you can re-read live. Never rewrite
a recorded sha after a rebase: rebind through the PR-number arm instead. A push moves the head:
re-read `HEAD`, and run step 4's guardrail again before arming. Then push, hand off, exit: the PR watcher reports the new head's CI results, so never watch them.

## 6a. Delegate first: text to the lab and GLM, decisions to Jev, code to the lab; then you check it

A landing pass writes text at fixed points: the lab-readback comment (step 6), a fix commit
message (step 6), the `NOT-LANDABLE` or `WAITING` report, and the TERMINAL outcome (step 8).
Draft each one through `onex delegate` first. This is the operator's standing rule that delegation
is the product and is dogfooded. On 2026-09-26 the repo-drain lanes, which run this skill, wrote
1,008 ledger rows and 18 PR bodies with no delegation at all.

1. Build the facts in the shell: the sha, the check names and their conclusions, the counts, the
   ids. Anything exact stays exact. The model rewords facts well and counts them badly: three
   graded runs of that day got a count wrong and still scored 1.0.
2. Draft:

   ```bash
   "$registry_root/omnibase_infra/scripts/onex" delegate "Rewrite as a two-sentence PR comment, using only these facts: <facts>" \
     --task-type document --ticket "<OMN-n>" --bus kafka --lane dev --locus deployed-lane \
     --state-root "$registry_root/.onex_state"
   ```

   Open the prompt with a verb such as Rewrite, Summarize or Classify. If the deployed lane refuses
   with no bound consumer (a runtime merge in the last 15 minutes), retry once with
   `--bus inmemory --locus in-process` in place of the three lane flags. If the wrapper refuses
   below the proven floor, do not work around it: write the text yourself and record the reason.
3. Check the draft against the facts before it leaves the lane. Every number, sha, check name and
   ticket in it must be in your facts. A draft that states a decision, an approval or anybody's
   words that the facts do not contain is discarded. A quality score of 1.0 is not evidence.
4. Keep the run id: the directory `onex delegate` wrote under `$registry_root/.onex_state/runs/`.

The same rule covers the other engines. The operator ruling of 2026-09-28T06:24:10Z (OMN-17427) says lanes delegate as much work as possible to Codex, Jev, GLM and the lab models before spending Claude. Each subtask goes to an engine by its kind: pure text to the lab through `onex delegate` and then GLM through Claude Code (`/omni:harness-delegate --harness claude-glm`; the cloud-glm backend pin is retired and always fails, omnimarket#3136, OMN-20173), typed decisions with a fixed answer set on any repository but `docs_repo` (operator RULING 2026-10-13T18:34:53Z, OMN-20106) to Jev through the omnimarket typed-decision node, and mechanical code edits, test scaffolds, lint and type fixes and conflict-resolution drafts through Codex first (operator ruling 2026-09-30, OMN-20106; the plan period ends about 2026-10-30), then the lab agent, then GLM; the lane verifies, while Claude reviews every draft and diff and makes every call that touches a gate, the ledger, a merge or an operator's words. Lane-brief part 3a.9 carries the commands, and `lane_brief.py check` refuses a brief whose 3a.9 drops Jev, Codex or the lab code step. Measured on 2026-09-28 from a lane, the lab answered in 26 s, GLM pinned in 27 s, Jev in 0.23 s.

| Subtask | Engine | Command |
| -- | -- | -- |
| pure text: PR bodies and comments, commit messages, summaries, TERMINAL and MSG prose, free-text log classification | the lab, then GLM | `"$registry_root/omnibase_infra/scripts/onex" delegate "<instruction + fact table>" --task-type document --ticket <OMN-n> --bus kafka --lane dev --locus deployed-lane --state-root "$registry_root/.onex_state"`; second try GLM through Claude Code, `python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-delegate/scripts/harness_delegate.py" run --harness claude-glm --model glm-5.3-flash --task-class document --prompt-file <scratch>/prompt.md --check 'test -s "$HARNESS_ANSWER_FILE"' --lane <lane> --ticket <OMN-n>` (or `delegation_step.py text` for both rungs) |
| typed decision with a fixed answer set, any repository but `docs_repo` | Jev | `env -u PYTHONPATH uv run --frozen --project "$registry_root/omnimarket" python -m omnimarket.nodes.node_typed_decision_effect < <scratch>/decision.json` (exit 0 Jev decided, 3 the incumbent answered) |
| mechanical code edits, test scaffolds, lint and type fixes, conflict-resolution drafts | Codex, then the lab agent, then GLM | `codex exec -C <worktree> -c model_reasoning_effort="high" -s workspace-write -c sandbox_workspace_write.network_access=true --json -o <scratch>/codex-final.txt - < <scratch>/codex-prompt.txt > <scratch>/codex.jsonl` (no model flag); fallback `python3 "${CLAUDE_PLUGIN_ROOT}/skills/lane-brief/scripts/lab_crush.py" --worktree <worktree> --scratch <scratch> --task-file <scratch>/task.txt` (crush on the lab model in the lane's own worktree); third route one GLM draft through Claude Code, `harness_delegate.py run --harness claude-glm --task-class code_generation --writable-repo <worktree> --prompt-file <scratch>/task.txt --check '<focused test>' --lane <lane> --ticket <OMN-n>`, which the lane verifies itself |
| review, verification, gates, ledger, merges, operators' words | Claude (the lane) | read every draft and diff, rerun the tests |

The TERMINAL row (step 8) carries one of `delegated=<n> runs=<run_id>[,<run_id>...] codex=<thread_id>[,...] lab_agent=<session_id>[,...] jev=<correlation_id>[,...]` (leave out an engine you did not use) or
`delegated=0 delegation_reason=<why>`. `onex-delegation-accounting` in ops_tooling_pkg counts
these per lane and day for the morning report, and a TERMINAL with neither counts as silent.

## 7. Merge on the exact head

Hand off through `/omni:pr-handoff` (`needs=land`) and stop touching the PR.
The landing controller arms or squash-merges on the exact head once the required contexts are green;
the PR watcher reports the merge, or a merge-queue removal with its reason.

On a base branch with a `merge_queue` rule (`onex scm branch-protection "$R" --branch "$BASE"` returns branch protection and required checks; checked live, never assumed from the repo name — every merge target may grow one), the landing controller enqueues first; success does not prove a merge (OMN-19852): read back `state`/`mergedAt`/`mergeQueueEntry` through `onex scm pr-view "$R#$N"` before reporting `merged`. A PR the queue removed for failed checks (a `merge-queue removal` MSG from the PR watcher, or a read showing it left the queue with no `mergedAt`) is RED, not merged: the controller sends it back and the owning lane fixes the cause and pushes, then hands off again, or returns `blocked`. **Never** bypass the queue with a direct REST squash or an admin merge — that was the exact OMN-17427 incident (`omnibase_infra#4197`, dequeued for failed checks then landed anyway by a direct REST squash 12 minutes later).

Squash only, with no `--admin`. `--auto` belongs only in step 4, and only where `allow_auto_merge`
is true.

## 8. Readback and close out

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --json "$R#$N" | jq -r '.prs[0]|[.state,.mergedAt,.mergeCommit]|@tsv'
```

Append the TERMINAL row with the merge sha, `friction=` and the step 6a delegation cells. Release the PR claim. Report `MERGED <sha>`
only after this readback. An agent's "done" is not evidence.

**When `$R` is `OmniNode-ai/plugin-tooling-pkg`, this step is not optional.** A merge to that
repository reaches no running session until someone updates the installed copy, and an update does
nothing until main carries a new plugin version. Since OMN-20497 that version comes from the
post-merge bump PR, not from the merged PR, so read the version on main rather than the merge's.

```bash
# before the update: what is installed now
jq -r '.plugins["omni@private-repo"][0]|[.version,.gitCommitSha]|@tsv' ~/.claude/plugins/installed_plugins.json
# what the merge shipped
MERGE=$(python3 "${CLAUDE_SKILL_DIR}/scripts/pr_snapshot.py" --field mergeCommit "$R#$N")
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh OmniNode-ai/plugin-tooling-pkg --wait   # not a git fetch (OMN-20495)
git -C "$registry_root/plugin-tooling-pkg" cat-file -e "$MERGE^{commit}" || echo "REFUSED: merge $MERGE not on origin/main yet"
git -C "$registry_root/plugin-tooling-pkg" show "$MERGE:plugins/omni/.claude-plugin/plugin.json" | jq -r .version
claude plugin marketplace update private-repo
claude plugin update omni@private-repo
claude plugin update onex-overlays@private-repo   # if that plugin changed
# after: the version must now equal the merged version, and the gitCommitSha must have moved
jq -r '.plugins["omni@private-repo"][0]|[.version,.gitCommitSha]|@tsv' ~/.claude/plugins/installed_plugins.json
```

If the merged version equals the version that was installed before, the post-merge bump has not
landed yet, so the update is a no-op and nothing is delivered. Report `MERGED awaiting-version-bump
<version>` and name the open bump PR (head `automation/omn-20497-plugin-version-bump`). Never open a
version-bump PR by hand, and never report MERGED-and-live. Once the readback shows the new
version, start a new session, because skills are snapshotted at session start. Report the installed
version before closing out. Do this yourself; do not hand it to the operator as a follow-up.

## Known friction (from prior runs)

Read this before step 5. Each line gives the symptom, the correct move, and a pointer you can
re-read. A pointer names a ledger row by its timestamp and lane, which survives a roll. Find it with
`grep -hF '<timestamp>' $registry_root/docs/tracking/ROLLING_WORK_LEDGER.md $registry_root/docs/tracking/archive/*-split.md | grep -F 'lane=<lane>'`.
Record new friction with the `friction-record` skill (`/omni:friction-record`).

> - **GitHub reads spent the operator's own bucket.** Every read a lane made (`gh pr view`, `gh pr checks`, `gh api` GETs, the check-run pages) went through the operator's login, which is the one 5,000/hour bucket that merges and arming also need, and the bucket ran out. The gh shim at `~/.local/bin/gh` now sends those read shapes to the read-only App bot-app's installation token. It is on for every caller through `~/.config/omni/gh-read-routing.env`, and each call is logged with `identity=app` in `~/.cache/omni/gh-usage/`. Writes (`pr merge`, `pr ready`, `run rerun`, `api -X POST|PUT|PATCH`, a GraphQL mutation) stay on the operator. Do nothing special for a read made through `gh`. A script that calls the API without gh uses `GH_TOKEN=$(~/.omninode/bin/onex-gh-reader-token token)`, and `~/.omninode/bin/onex-gh-read <gh args>` is a gh that refuses writes. A read logged `operator-fallback` means the mint failed: record friction, and never work around it with the operator token. → CLAIM 2026-09-27T19:06:52Z lane=github-reads-app-83, RULING 2026-09-25T14:18:52Z lane=merge-drain-83 (Q3)
- **The claim guard refused PRs the drain map freed.** It counted any foreign row naming the PR in the last 45 minutes as ownership, so a TERMINAL, STATUS, FRICTION, HOLD or report MSG stopped a lander the map had sent (23 of 39 refusals false on the 08:05:03Z snapshot). The guard now refuses only the owners `drain_map.ledger_owners` returns, plus live registry claims. The residual prose-mention class of that shared rule (a `pr=`-scoped CLAIM owning PRs its do-not-land list or registry snapshot named) is closed by omni 0.4.42; a `pr-ref` refusal left is a PR the CLAIM names for its own work. → 2026-09-27T08:23:36Z lane=claim-guard-align-83, OMN-19846
- **Sibling lanes on one shared ticket refused each other's PRs.** Every validator burn-down wave-1 lane CLAIMed OMN-20201, so the guard refused each lane its own PR with `by=ticket`, and the worktree match read only the shared ticket directory. A ticket two or more lanes CLAIMed in the window now owns nothing by ticket alone, and the worktree match names the exact worktree path. A refusal left on a shared ticket is a lane whose CLAIM names the PR, its branch or its worktree: a real conflict. → FRICTION 2026-10-01T01:58:01Z lane=vburn-W1-B5, FRICTION 2026-10-01T02:04:37Z lane=vburn-W1-B3, OMN-19846
- **occ-preflight sits in progress for many minutes.** It waits up to 1500s for the cited companion to MERGE (`omnibase_core/scripts/ci/occ_preflight_wait.py`). Cancelling and rerunning it does nothing. Land the companion. → 2026-09-22T23:53:29Z lane=market-shadow-timeout
> - **Companion open, green, not armed.** occ-preflight then times out and fails closed. Arm the companion (`gh pr merge <n> --squash --auto`), then rerun the failed runs. → 2026-09-22T23:15:13Z lane=omn16856-c17-carrier
- **Append-only gate after a merge from dev.** Regenerating an already merged receipt trips the append-only and receipt-hardening gates. Leave the merged receipt byte-identical. Add a net-new supersede receipt that carries only the rebind, with `contract_entry_sha256` computed by `omnibase_core.validation.validator_receipt_gate.compute_contract_entry_sha256`. → 2026-09-22T23:53:29Z lane=market-shadow-timeout
- **Hand-authored companion beside the autobind.** This produces duplicates that conflict on the same `dod_evidence` (onex_change_control#10851, #10853). Never hand-author a companion while the autobind can still mint one. → 2026-09-23T00:58:03Z lane=friction-to-skills item=F7, 2026-09-22T23:53:37Z lane=market-shadow-timeout
- **Ready flip and push together.** The result is a run cancelled with zero jobs and no CI Summary on the head. If that run was created after the flip, rerun it whole; if it was created before the flip, take a fresh head (step 5). → 2026-09-22T20:27:44Z lane=market-drain
- **Autobind body edit cancels producers.** occ-preflight, the hostile-review producers and the skip-token scan are cancelled with no replacement run, and CI Summary reads cancelled_without_replacement. Rerun those runs whole. → 2026-09-23T00:03:18Z lane=lab-rebuild-unstick, OMN-15822
- **Shadow job red.** Read the job log first. Exit 124, or a cancel at `timeout-minutes`, is a budget timeout, not a test failure. → 2026-09-23T00:57:52Z lane=friction-to-skills item=F15, 2026-09-22T21:40:11Z lane=occ-shadow-timeout, 2026-09-22T23:53:37Z lane=market-shadow-timeout
- **Repo-scripts or pre-commit timeouts on infra_repo under fleet load.** Rerun once, then report. The xdist cap is infra_repo#1629. → 2026-09-22T23:03:11Z lane=m4-c10-probe, 2026-09-22T23:38:46Z lane=m4-c12-probe, 2026-09-23T00:13:21Z lane=m4-c13-probe, OMN-19209
- **Release-identity gate red on a PR opened while release-on-merge publishes.** dev sits at a published version until the bump PR lands. Wait for the bump, then update the branch. → 2026-09-23T00:14:14Z lane=clean-install-deleg
- **Skip-count ratchet on new integration-proof ids.** Amend the baseline in the OMN-18916 shape. Never lower the bar. A rebase can also move in-repo provenance line citations. → 2026-09-22T22:36:00Z lane=land-3972
- **Body guard reads `--body-file` literally.** Pass an absolute path, not a shell variable or a relative path. → 2026-09-22T20:31:13Z lane=m4-c9-probe
> - **SCOPE_GATE refuses a compound push plus `gh pr create` with a heredoc body containing apostrophes.** Split the commands. → 2026-09-22T21:20:46Z lane=unified-verif-obs-plan
- **A pause or hold sent by message may never reach you while you are working.** CORRECTED by the 2026-09-23T02:09:09Z lane=friction-f8-correction row: a message to a lane mid-turn is not delivered until that turn ends, which can be hours, not "the next tool round" — a lane merged 5 PRs after 8 successful-but-undelivered pause/hold sends, all of which arrived at once only after it went idle. A successful SendMessage is not a delivery receipt, and you cannot rely on receiving one. Re-read the ledger for HOLD/RULING rows addressed to your lane or repo immediately before each ready flip (step 4) and each arm — that is the only stop that reaches you reliably. If you do get a pause message, disarm (`--disable-auto`) and read back before anything else, then write a STATUS row; write a STATUS row at every merge regardless. → 2026-09-23T02:09:09Z lane=friction-f8-correction (correction), 2026-09-23T00:57:52Z lane=friction-to-skills item=F8
- **A runtime-affecting merge has no rebuild.** Read its Runtime Rebuild Trigger run. A DNS resolution failure is transient, so rerun that run once. → 2026-09-23T00:57:52Z lane=friction-to-skills item=F11 (run 35793186217)
- **Draft-first PR never armed.** Before OMN-19216 lands, `auto-merge.yml` fires only on opened, so arm the PR by hand after the flip (step 4). → 2026-09-22T22:48:55Z lane=prosthetic-skills, 2026-09-22T20:31:13Z lane=m4-c9-probe
- **Two lanes on one PR.** Step 1 stops you, but only if you run it. → 2026-09-22T21:36:45Z lane=c15-reroute-fix-r2
- **A later pass joined a PR and shared worktree that another live lane still owned.** The first-pass-only claim check let duplicate drain dispatches work omniclaude#2350 and #2353 concurrently. Run step 1's read-only guard on every pass; `owned-by=<lane>` is a write-nothing stop. → 2026-09-25T21:10:49Z lane=orchestrator-83 (correction), 2026-09-25T21:08:30Z lane=repo-drain-omniclaude-pr, 2026-09-25T20:42:07Z lane=repo-drain-omniclaude-pr
- **The hold check missed a live hold.** Step 3 was a RULING/HOLD grep capped at 15 rows, and it
  missed a hold-family label plus a handoff row saying the PR must not land standalone. Step 3 is
  now `pause_check.sh`: every row naming the PR by repo and number, unreleased HOLDs by scope, repo
  pause declarations and labels, with no cap. The step-5 check-run read also stopped at 100 of 149
  rows until it took `--paginate`. → OMN-19268
- **Merging to plugin-tooling-pkg does not reach any session.** The installed marketplace clone and
  the installed `omni` plugin stay pinned at whatever version they last updated to; a merge alone
  changes nothing running. Run both plugin-update commands and start a new session before reporting
  done (step 8). → 2026-09-23T14:45:48Z lane=omn17427-foreground
- **A release-on-merge version bump collides with a PR's own bump, a post-companion rerun sweep skips runs still behind a timed-out OCC Preflight Dependency, and a PR body names a sibling fix by ticket id instead of PR number (holding deploy-gate red until both merge).** While dev reads release-on-merge, take dev's version instead of bumping; after a companion merges, rerun every run whose jobs include OCC Preflight Dependency, not only the ones holding a failing check-run; name a sibling fix by PR number in the body, never by ticket id. → 2026-09-23T13:38:13Z lane=storm-fix-market
- **Step-5 read was unpaginated.** It saw 100 of 149 check-runs and missed the only failing required context on omnibase_infra#3991. Step 5 now runs ci-watch's `ci_state.sh`, which pages and proves the row count against `total_count`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **Step 2 named conditions with no action.** A lane that found two tickets, or no lab readback, had no instruction and carried on. Every step-2 condition now says stop, report or do. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **The step-4 arm lacked `--match-head-commit`,** so an arm could land a head nobody had read. It now arms on the exact head, and only where `allow_auto_merge` is true. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **plugin-tooling-pkg PR #14 merged at an unchanged 0.4.5,** so `claude plugin update` was a no-op and nothing was delivered. Step 2 then refused an unbumped plugin PR; since OMN-20497 PRs do not bump and the post-merge bump PR carries the version, and step 8 still requires the installed-version readback to change. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **Dead ledger line citations.** The ledger rolled at 2026-09-23T14:00:47Z, and every line-number pointer here pointed past EOF or at an unrelated row. Pointers are now `<timestamp> lane=<lane>`. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **"Every script is read-only" was not true of `runtime_class.sh`,** which ran `uv run` in the canonical clone and synced a package into its venv. It now runs `uv run --frozen --no-sync`, and the skill says what it touches. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **The step-5 short table named draft residue for omnimarket only.** On omnibase_core#1745 (draft) `Contract Compliance Check` failed on a missing `Evidence-Source:` line, which is the same draft residue (ci-watch D5), but the short table matched only omnimarket's `deploy-gate`, so the red read as a real failure. The row now names both gates. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **The step-5 cancellation row said rerun even when a replacement run was already queued.** On omnibase_infra#4032 at 2026-09-23T22:25Z a newer CI run sat pending at the head while the older run's jobs were cancelled; rerunning the superseded run spends a rerun and races the replacement. The row now says to wait for the newer run (ci-watch P5) and rerun only when none exists. Fixed 2026-09-23 by the omni-skill-fixes pass (OMN-19230 lineage); shipped by OMN-19387.
- **A whole rerun of a cancelled push-era run after the ready flip replayed its draft payload** (fourth occurrence). On omnibase_infra#4043 the rerun of the cancelled push-event CI run 35970519445 skipped the test matrix and turned `CI Tests Gate` red, which poisoned the ready run's own rerun; only a fresh head (c7c0d3780) cleared it. Step 5 now forbids rerunning any run created before the last ready flip and says to read `created_at` against the flip first. → 2026-09-24T09:17:58Z lane=reds-stacked, 2026-09-24T06:12:23Z lane=wr-recovery-r2, 2026-09-23T18:32:10Z lane=k3s-lab-receipt-diag, OMN-19379
- **Every lander re-read the same PRs by hand.** 945 PR reads hit 371 distinct PRs in one
  16-hour session, `omnibase_core#1761` by 22 lanes, about eight core REST requests per read, and
  the shared bucket ran out. Every read in this skill now goes through `scripts/pr_snapshot.py`
  (one GraphQL request, raw check-run fields) and `runtime_class.sh` reads changed files from local
  git. → OMN-19586, docs_repo beta/tracking/2026-09-25-gh-quota-measurement.md
- **The auto-merge arm-gate label stopped the pause check.** The hold family's auto-merge member printed as `LABEL` and `VERDICT: PAUSED`, while its only mechanical consumer (`check_auto_merge_hold.py`, OMN-18179) gates the auto-merge workflow's arm, and landers were already merging such PRs on the exact head. It now prints `ARM-OFF` (never arm, merge in step 7) and is not a stop; every other label of the family still stops. → 2026-09-25T12:11:36Z lane=hold-label-reconcile-83, OMN-17427
- **The change-control cascade has a 5th run the rerun table didn't name.** CI Summary can fail closed on an `EXPECTED_EXTERNAL_CONTEXTS` name from a separate workflow (e.g. context `validate`, a Runtime Profiles workflow's own OCC Preflight Dependency job) that is not one of the 4 in-run jobs the cascade row covers. Left stuck skipped from before the companion merged, CI Summary treats it as fail-closed even though every in-run job is green, because `EXTERNAL_GOOD_CONCLUSIONS` excludes skipped for L4 contexts (`ci_summary_gate.py`). Rerunning only the standard 4 runs leaves it stuck. Fix: after those reruns, re-fetch check-runs, find the failing context's own run via its `details_url`, rerun that run too, then rerun CI Summary once more. → 2026-09-27T02:03:27Z lane=land-omnimarket-2973-83, OMN-18812
- **A hand-authored companion's self-bind receipt landed under `drift/occ_bindings/`** (matching an older cross-repo precedent, OCC#11152). That path is never read: `omnibase_core.validation.validator_occ_merge_eligibility` resolves a receipt only at `drift/dod_receipts/<TICKET>/<ITEM_ID>/`, per `onex_change_control/CLAUDE.md`, so eligibility reported `missing_receipt` with no signal that the file existed at the wrong path. Author every hand-authored receipt at `drift/dod_receipts/<TICKET>/<ITEM_ID>/`, never `drift/occ_bindings/`, whatever an older precedent shows. → 2026-09-27T05:16:47Z lane=land-omnimarket-2976-83, OMN-15247 lineage
- **A second consumer PR on a multi-consumer ticket bound the wrong evidence, or errored closed.** `omnibase_core.validation.validator_receipt_supersession`'s target-aware resolution (OMN-16432) binds a shared `evidence_item_id` to whichever consumer PR's `replacement.pr_number` matches; once ANY `dod_evidence` entry for that key already carries one `<CHECK>.supersede.<PR>.yaml`, every later consumer that touches the same entry must add its OWN `<CHECK>.supersede.<PR>.yaml` naming its own PR number, or resolution falls through to the legacy highest-suffix tier and `resolve_supersession` can bind a different consumer's evidence. An entry with zero prior supersede files needs no new file. Before pushing, call `validate_occ_merge_eligibility` directly against the local worktree (`contracts_dir`/`receipts_dir` pointed at it) to read the exact `missing_or_nonpass_receipts` list rather than round-tripping through a live CI push-and-wait cycle. → 2026-09-27T05:16:47Z lane=land-omnimarket-2976-83, OMN-15247 lineage
- **A two-dot `git diff` between the base and a PR's head read a clean squash as a conflict.**
  Every file the base branch gained since the PR's fork point shows as a deletion in a two-dot
  diff, so a PR that never touched those files still reads `substantive_conflict=true`. Step 2 now
  runs `scripts/conflict_check.py`, a real three-way `git merge-tree --write-tree`, which reads
  only the PR's own conflicted paths. → 2026-09-27 friction, omnibase_infra#4178, ~1.5 lane-hours
  across four lanes; docs_repo reports/2026-09-28-overnight-friction-report.md
  section 2.1
- **A chain lane's CLAIM read as dead while it was still working a long chain of PRs**, and a
  second lane took it over 50 minutes later. `claim_guard.py`/`drain_map.py` now give a CLAIM whose
  `pr=` field names 2 or more PRs (a chain CLAIM) `CHAIN_DEAD_AFTER` (3 hours) instead of the flat
  45-minute `DEAD_AFTER`; a single-PR CLAIM is unaffected. → FRICTION 2026-09-27T15:48:05Z
  lane=qd-land-omnibase-infra-4180-83; docs_repo
  reports/2026-09-28-overnight-friction-report.md section 2.1 item 4
- **The pause check stopped every onex_change_control lane on five other PRs' STATUS rows.** Each said "No merge" about its own pass (ledger 8261, 9348, 9584, 9754, 10053), and the old REPO-PAUSE regex took a bare "no merge" as a merge pause; an expired surface lease (HOLD 2369) stopped omnimarket lanes the same way. REPO-PAUSE now comes from `drain_map.py` `repo_pause_lines` (a pause instruction scoped to the repo, never a row about one PR), STATUS rows are CONTEXT, orders print as `ORDER` with the landing order (companions first), and a HOLD past its `until=` or on a `surface=` holds nothing. → STATUS 2026-09-27T14:42:22Z lane=occ-merge-now-83, OMN-19852
