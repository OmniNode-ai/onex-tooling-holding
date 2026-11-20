---
name: ticket-pipeline
description: Carry one Linear ticket from claim to a merged, lab-proven PR and a Done flip on evidence. Covers claim and ownership check, live intake, worktree, RED-first implementation with focused tests, self-review, runtime-affecting classification, lab-first proof, a draft PR, the ready flip and landing through pr-land, the post-merge lab receipt, and closeout. Use when a lane is told to "do OMN-n", "implement this ticket" or "take this ticket to merged", and for any per-ticket code change in a product repo.
prosthetic: true
replaces_when: "`onex skill ticket_pipeline <OMN-n>` resolves (node_ticket_pipeline) and carries three consecutive tickets from claim to merged PR, with every phase wired and a lab readback in each PR, and no hand step. On 2026-09-23 `onex skill ticket_pipeline` returns `Unknown skill` (it is absent from the known-skills list), and node_ticket_pipeline runs PRE_FLIGHT with no side effects and IMPLEMENT in `compile_only` mode (it compiles a dispatch-worker prompt and runs nothing). Every later phase returns `NOT_IMPLEMENTED` with `blocked_reason: phase_not_wired` (omnimarket handler_ticket_pipeline.py `execute_phase`)."
restored_from: "omniclaude 4a5e9f9be plugins/onex/skills/ticket_pipeline/SKILL.md (with prompt.md and topics.yaml at the same commit)"
ticket: OMN-19221
---

# Ticket pipeline (prosthetic)

One ticket, one lane, one PR per repo. `T=OMN-<n>`, `R=OmniNode-ai/<repo>`,
`L=$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md`, and `B` is the repo's base branch, resolved
live in step 3 and used by every later command. Ledger pointers below name a row by its timestamp
and lane, because a roll renumbers lines. Find one with
`grep -hF '<timestamp>' $L $registry_root/docs/tracking/archive/*-split.md`. Every factual answer comes from a read
taken in this turn. A brief, a handoff table or a lane report is where you start looking, not
proof (ledger row 2026-09-23T00:58:02Z lane=friction-to-skills item=F3).

This skill sequences other skills and does not repeat them. `lane-brief` writes a sub-lane's
brief. `create-ticket` mints a ticket. `plan-write` writes a plan. `ci-watch` triages CI.
`pr-land` lands the PR. `release-cut` cuts a release. `lab-rebuild-triage` diagnoses a lab
rebuild. `friction-record` records friction. `session-resume` resumes after a restart. If one of
them covers a step, use it.

## What the old pipeline did, and where it lives now

| Old phase (4a5e9f9be) | Status on 2026-09-23 | Today's path |
| -- | -- | -- |
| lock, state.yaml, `pipelines/ledger.json`, `--skip-to`, auto-detect | machinery gone | ledger CLAIM plus a live read of the ticket's PRs (steps 1 and 2) |
| generate_contract, enrich_contract | superseded | the change-control autobind mints the companion and contract when the PR opens non-draft or flips ready |
| decision_context_load, conflict_gate, TCB | `generate_tcb` is not registered; `decision_store` is registered but was not exercised for this skill | the premise and inventory check in step 2 |
| implement via `ticket_work` | `ticket_work` is not an `onex skill`, and its node is a structural placeholder | step 4, done by this lane |
| local_review via `local_review` | registered, but node_local_review is a pure FSM that reports clean on the first pass without reading the diff | step 5: `/code-review` on your own diff |
| hostile_review, review_gate, cdqa, mergeability_gate | only `hostile_reviewer` is registered; CI runs the hostile-review producers on every PR | CI, triaged with `ci-watch` (`/omni:ci-watch`) |
| test_iterate, test_coverage_gate | machinery gone | step 4: RED first, focused tests only (rule 21) |
| ci_watch, pr_watch, auto_merge | not registered (auto_merge was deregistered by OMN-14151) | `/omni:ci-watch`, then `/omni:pr-land` |
| integration_verification_gate, verification_sweep | replaced by lab-first | steps 6, 7 and 9 (rule 24 and the post-merge lab receipt) |
| cross_repo_split via `decompose_epic` and `epic_team` | not registered | step 2: one PR per repo, and `/omni:create-ticket` plus `/omni:lane-brief` for a split |
| Slack gates and notifications | lanes do not send to Slack | ledger rows plus one report to the orchestrator |

## 0. Preflight

Run `/onex:preflight --intent quiet` and act on any blocker line's fix command. Read the committed
standing rules once from ops_tooling_pkg `lane_rules/lane-rules-block.md`:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane_rules_block.py"`. This skill
assumes all of them. Before anything else, grep for peers:
`grep -nE "$T\b" $L | tail -20`.

- An open CLAIM on `T` (no TERMINAL or CLOSEOUT after it) from another lane means **stop and
  report**. Do not create a worktree and do not start alongside it. Two lanes shared one worktree
  for 20 minutes on 2026-09-21 without seeing each other (ledger row 2026-09-21T21:00:34Z lane=dod-serializer-3).
- If you are resuming after a restart or a usage limit, run `session-resume` (`/omni:session-resume`) first (ledger rows 2026-09-23T00:57:51Z lane=friction-to-skills item=F6; 2026-09-23T00:57:52Z lane=friction-to-skills item=F16).

Then append your CLAIM:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --append "$(date -u +%Y-%m-%dT%H:%M:%SZ) | CLAIM | lane=<lane> | actor=<executor> | model=<model id> | ticket=$T | repo=<repo> | worktree=worktrees/$T/<repo> | scope=<one line>. OUT OF SCOPE: <list> | est ~<N> lane-hours; displaces <what>; ($T)"
```

The CLAIM needs `actor=` or `model=`, the rule-4 cost sentence and its own `worktree=<path>` cell (one path, `worktrees/$T` for a lane on several repos, or `worktree=none`; OMN-20148), or `onex_ledger.py` refuses it.

## 1. Intake: the ticket, read live

1. `get_issue $T`. Record the title, the acceptance criteria (with their falsifiers), the
   `Gate:` line, the parent, the relations (blockedBy), the state and `gitBranchName`. Only cite
   ticket ids you have read with `get_issue` in this lane.
2. **Existing work.** Read it from the PR watcher's state file, never from GitHub (operator ruling
   2026-09-27T18:05Z: every PR-state read comes from that file, GitHub is for mutations and the
   exact-head check only; OMN-20421):
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/pr_state_local.py" --find "$T"` prints one
   line for every PR, open or recently merged, whose title, branch or body names the ticket (`rc=3`
   means the state is stale or missing: search GitHub once for the ticket id, and say why in your row). Merged work older than the state keeps is
   `git -C "$registry_root/$R" log origin/<default> --grep="$T" --oneline` over the canonical clone. A
   sweep that drops stderr reads an error as an empty result, so print the `rc`:

   | Live state | Start at |
   | -- | -- |
   | a merged PR already satisfies the criteria | step 9 (verify and close out, do not re-implement) |
   | an open PR with an open CLAIM by another lane | stop and report its owner |
   | an open PR with no owner, and your brief covers it | step 8 (`pr-land`), after reading its body and files |
   | a branch, no PR | step 4, in a worktree on that branch |
   | nothing | step 2 |

   Read each PR before you describe it: `pr_state_local.py --pr "$R#<n>" --json` carries its title and
   body, and `git diff --stat origin/<base>...origin/<head_ref>` after a fetch lists its files.
   A title is not its content (ledger row 2026-09-23T00:58:02Z lane=friction-to-skills item=F2).
3. **Blockers.** A blockedBy ticket that is not Done blocks you: report it and stop. Do not work
   around a dependency. An empty description, or one with no acceptance criteria, gets reported
   too. Do not invent criteria.

## 2. Premises and shape

- **Premise check.** List each fact the ticket or brief asserts about the world: a file, a
  function, a flag, a host, a PR state, a sudo or key setup. Re-read each one live and record
  `verified by: <command> => <observation>`. Four lanes in a row stopped at step 0 on one false
  premise (ledger rows 2026-09-22T15:48:23Z lane=new-host-access-network-r3; 2026-09-22T15:53:00Z lane=new-host-prep-gpu-r3), and a ticket's stated root cause was wrong (ledger row 2026-09-20T11:17:34Z lane=runner2-reregister-1125).
- **Inventory.** Search current code before writing new code: `grep -rn "<key term>" src/`
  across the repos the ticket touches. Extend what exists.
- **Repo shape.** One ticket should map to one PR in one repo. A multi-repo ticket gets one
  change-control companion per PR, and every one of them appends to the same contract, so each
  merge leaves the next DIRTY and it has to be hand-unioned, one merge at a time (ledger rows 2026-09-23T01:28:32Z lane=c17-finish; 2026-09-23T02:25:38Z FRICTION lane=prosthetic-skills). Choose one of two shapes. Split the ticket per repo: mint the children with `create-ticket` (`/omni:create-ticket`)
  (you need mint authority), then brief sibling lanes with `lane-brief` (`/omni:lane-brief`). Or keep one ticket, land
  the PRs serially, and plan for the structural union. With more than one cross-repo migration
  pair in flight, land the market contracts in the same order as the infra vendors (ledger row 2026-09-20T00:13:32Z lane=obs-board-drive-1700).
- **Design-scale work** (a new layer, framework or standing system) goes to `plan-write` (`/omni:plan-write`), and
  the operator reviews the plan before anything is implemented.

## 3. Worktree and branch

Resolve the base branch from the canonical clone, never from memory and never from GitHub (the gh shim
refuses every read from a lane, OMN-20911):

```bash
git -C "$registry_root/<repo>" symbolic-ref --short refs/remotes/origin/HEAD
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh OmniNode-ai/<repo> --branch <base> --wait
git -C "$registry_root/<repo>" rev-parse origin/<base>
git -C "$registry_root/<repo>" worktree add "$registry_root/worktrees/<ticket>/<repo>" -b <gitBranchName> <sha>
```

The first command prints `origin/<base>`; drop the `origin/` prefix. Only `dev` and `main` are bases in this
fleet: any other value is a stop, never a guessed base. The refresh (OMN-20495) replaces a `git fetch`: it
fetches under the canonical-clone sync's own lock and returns once `origin/<base>` is at or past the remote
head. A lane's own fetch, pull or ls-remote against GitHub is refused by the lane git-fetch guard. `<sha>` is
the `rev-parse` output of the refreshed `origin/<base>`. Every later `origin/dev` in older notes means
`origin/<base>`. For registry_root itself the clone is `$registry_root`, not `$registry_root/<repo>`: run
`git -C "$registry_root" ...` and put the worktree at `$registry_root/worktrees/<ticket>/registry_root`.

- Write each command as one literal line: the ticket id, repo, base and sha typed in, with `$registry_root` the
  only variable (later steps write `$T`, `$B` and `$R` for the ticket, base and repo: type their values in).
  A Bash call starts a new shell, so a `$T`, `$B` or `$R` set in an earlier call is empty in
  this one, and the worktree guard refuses a loop variable, `$PWD`, a positional parameter or `$(...)` in the
  path or the branch name (457 refusals, 122 lanes, 2026-09-23 to 2026-10-31; fixture
  `tests/fixtures/worktree-step-2026-10-31/refusal_rows.json`). Give git the ABSOLUTE path: the
  `worktree=worktrees/...` cell of the CLAIM is a ledger cell relative to `$registry_root`, and git resolves a
  relative path inside the clone `-C` names, where the guard refuses it (393 refusals, 149 lanes). Never type
  the root from memory and never redefine `registry_root` inline: the directory `omni_worktrees` beside the registry
  root is a stray root, never used (operator ruling 2026-09-24T12:53:21Z, ticket OMN-19388). The guard refuses
  a `git worktree add`, `mkdir` or `git clone` into it.
- Never branch, stage or commit in `$registry_root/<repo>`. Never `git stash`, `git reset`, `--no-verify`
  or `core.hooksPath` anywhere. If a canonical clone is left mid-merge and that breaks a hook,
  report it. Do not repair the clone yourself (ledger row 2026-09-21T08:51:06Z lane=delegation-output-bar-0410).
- A branch that was already squash-merged is spent. A follow-up takes a new branch off the base,
  because reusing the old one opens as CONFLICTING (ledger row 2026-09-21T03:32:25Z lane=session-goal-0320).
- Move the ticket to In Progress only once the worktree and the first commit exist.

## 4. Implement: RED first, focused tests

Self-contained build and fix drafts use Codex first (operator ruling 2026-09-30, OMN-20106; the plan period ends about 2026-10-30), then the lab agent, then GLM; the lane verifies. Run `delegation_step.py code` in the lane's own worktree; it keeps the `lab_crush.py` route and then one GLM draft through Claude Code (`/omni:harness-delegate --harness claude-glm --writable-repo <worktree>`). GLM runs only through Claude Code: the Coding Plan terms bar direct API calls, so the cloud-glm backend pin of `onex delegate` is retired and always fails (omnimarket#3136, OMN-20173). Never pass a model flag to Codex. The Claude lane reads every diff, runs focused tests and owns the PR. Pure text stays lab first, then GLM through Claude Code (`delegation_step.py text`); typed decisions go to Jev.

1. **Write the failing test first and watch it fail.** To prove RED against the base without
   touching your uncommitted work, read the pre-image out of the object store:
   `git show "origin/$B:<path>" > <scratch>/<lane>-<file>`. Otherwise, commit the implementation
   first and **confirm the commit exists** (`git log -1 --oneline`) before you run
   `git checkout "origin/$B" -- <path>` and restore with `git checkout HEAD -- <path>`. That
   restore returns the file to HEAD, not to your working tree (ledger rows 2026-09-20T01:56:50Z lane=deploy-agent-false-success-diag-0016; 2026-09-20T03:32:39Z lane=deliver-candidate-green-omn18364-2255 ("the rule-17 RED-proof recipe"); 2026-09-21T11:22:06Z lane=obs-board-drive-1700, OMN-19021).
2. Make the minimal change. Keep to the repo's conventions, which are in its own CLAUDE.md.
3. **Run focused tests only**: the changed test files, or `-k` scoped to the behaviour, finishing
   within a few minutes. Never run a directory-wide or bare `pytest` on the launching host (rule 21);
   a broad selection runs on the lab or in CI. Never suppress stderr, and give any zero result a
   positive control.
4. Before each commit, run `uv run ruff format src/ tests/ && uv run ruff check --fix src/ tests/`,
   then `pre-commit run --all-files`. Fix every failure, including any that existed before your change.
5. **A pre-commit failure can look like a successful commit.** Read `git log -1` after every commit.
   Two lanes lost work believing a refused commit had landed (ledger rows 2026-09-20T03:32:39Z lane=deliver-candidate-green-omn18364-2255 ("the rule-17 RED-proof recipe"); 2026-09-20T17:49:51Z lane=chain-canary-ledger-hop-1600).
6. **Whole-tree ratchets**, such as public-repo hygiene and the skip count, refuse commits for
   reasons you cannot see from your diff. The rules block explains both. Rename; never raise a budget.
7. **Version bumps** (publishing repos). Before you pick a version, list the versions every open
   head claims: `pr_state_local.py --open-heads "$R"` (number, head branch and head sha of every open PR
   of the repository, from the watcher's state) plus each head's version file. For a Python package that is `pyproject.toml`. **For omniclaude**
   it is the changed plugin's `plugins/<plugin>/.claude-plugin/plugin.json` together with that
   plugin's entry in the marketplace manifest. The two bump together, in the same PR as the change,
   because the plugin cache is keyed by version. **plugin-tooling-pkg PRs do not bump at all**
   (OMN-20497, operator RULING 2026-10-04T09:26:32Z lane=review-session-9143): after the change
   lands, its `plugin-version-bump` workflow raises the version in both manifests in one bot PR.
   Leave both version lines alone; its required `validate-plugin` check refuses a version a PR
   lowered, one that is not dotted integers, and the two files disagreeing. omniclaude also ships more than one
   marketplace manifest, so read its CLAUDE.md for the one that lists the plugin you changed. The post-release bump bot takes numbers too (ledger rows 2026-09-20T17:57:37Z lane=obs-board-drive-1700; 2026-09-21T23:40:20Z lane=kafka-producer-retry-2). The
   release-identity gate refuses a version that has already been published, and it refuses at
   commit time, after the whole hook chain has run (ledger row 2026-09-20T21:41:04Z lane=autobind-collision-selfbind-1715).
8. **Applied migrations are immutable.** Never edit a file under a migrations path that already
   exists on the base (ledger row 2026-09-20T12:10:40Z lane=manual-merge-drain-0742). An omnimarket node migration also needs its mirror in the
   omnibase_infra vendor tree, or the sync hook refuses every infra commit (ledger row 2026-09-21T17:46:13Z lane=omn18868-67-seam-gates-restart).
9. Commit with a `<type>($T): <subject>` message, from a message file whose name starts with
   your lane name (see Guardrails).

Text-shaped side steps, such as drafting the PR body from a fact table you have verified, go
through `/onex:delegate` first (rules block, "Delegation"). Pass `--task-type document` for
prose: the default classifier can route "write a ..." prompts to code generation and reject the
answer (ledger rows 2026-09-20T03:32:38Z lane=deliver-candidate-green-omn18364-2255; 2026-09-22T12:55:56Z lane=draft-pr-classify-1250).

## 5. Review your own diff

Run `/code-review` on the branch diff and fix every correctness finding before you open the PR.
Do not use `onex skill local_review` as a review: its node reads no diff and returns clean.
Hostile review runs in CI on the PR itself. An optional local pass is
`bash $registry_root/omnibase_infra/scripts/onex skill hostile_reviewer ...` (registered, but
not exercised when this skill was written).

## 6. Classify: is it runtime-affecting?

A merge is runtime-affecting when the rebuild trigger fires on it: the `runtime_change` label,
a canonical deploy-gate runtime path, or a lane-state path (migrations, the compose model, the
dependency manifest and lock). Ask the trigger itself rather than judging by eye:

Only two repos are wired to the trigger (a `runtime-rebuild-trigger` workflow at their base, read
2026-09-23): omnibase_infra for its own merges, and omnimarket as a vendored sibling. A PR in any
other repo (plugin-tooling-pkg, registry_root, docs_repo, omniclaude and the rest) fires
no rebuild. It is **not runtime-affecting**. Say so in the PR body, with that reason, and skip the
command. Check the wiring rather than trusting this list. A repo is wired when a workflow file named
for the trigger exists at its base (a text grep also hits the many workflows that merely mention it):
`git -C $registry_root/<repo> ls-tree --name-only "origin/$B" .github/workflows/ | grep runtime-rebuild-trigger`
(for registry_root itself, `git -C $registry_root ...`). Empty output means not wired; on 2026-09-23 only
omnibase_infra and omnimarket printed a file.

For omnibase_infra:

```bash
uv run --project $registry_root/omnibase_infra python $registry_root/omnibase_infra/scripts/trigger_rebuild_on_merge.py \
  --changed-files "$(git -C <worktree> diff --name-only "origin/$B...HEAD" | paste -sd, -)" \
  --labels "" --base-branch "$B" --source-sha 0000000000000000000000000000000000000000 \
  --runtime-path-validator $registry_root/omniclaude/scripts/validation/validate_pr_deploy_required.py --dry-run
```

`--base-branch` takes only `dev` or `main`, and it chooses the lane (`dev` is the dev lane, `main`
is lane-i). For an omnimarket worktree, add `--source-repo OmniNode-ai/omnimarket` and
`--primary-ref <omnibase_infra origin/dev sha>`. The script refuses a sibling without the second.

`Runtime change detected` means it is runtime-affecting. `No rebuild trigger` means it is not.
Both answers were checked on 2026-09-23 with a positive control (a runtime handler path) and a
negative control (a README-only change). A runtime-affecting PR takes the full lab proof in step
7 and the pause rules in step 8.

## 7. Lab-first proof, then a draft PR

**The lab is the first place a change runs** (rule 24). Operator ruling 2026-09-22: run the
changed behaviour on a lab runtime **before the PR exists**, even if that means hotpatching one.
The procedure is the docs_repo runbook `runbooks/2026-09-21-pre-pr-proof-surfaces.md`.
Read it from `origin/main` via `git -C $registry_root/docs_repo show origin/main:<path>`.
From that runbook:

- **Choose the surface class (runbook section 0).** For a model, wire shape or contract field, use
  `mac-scratch:<lane>`. For a migration, grant or constraint, use `<host>-scratchdb:<lane>`. For
  consumer wiring, routing, handler behaviour under a real broker, or a projection that has to
  write rows, use the dev lane on h907 under the hotpatch rule in the next bullet. The dogfood
  stacks on h903 and h904 are gone, so no lane takes them. Do the cheap proof first.
- **Hotpatching the lab-host-a dev lane** is sanctioned for this purpose only. Record it as a ledger
  row, then restore the lane (or let the next merge-driven rebuild do it). Never hotpatch
  lane-i, judge, the collaborator lane or anything the prod gate reads, and never use `--cold`.
- **Name what the proof touched, not what it addressed.** Read the observation back from the
  thing itself. "Tests pass" is not a lab readback.

Then open the PR:

1. Write the body **before** `onex scm pr-create`, with the editor tool, into
   `<scratchpad>/<lane>-pr-body.md`. It cites exactly one ticket (`$T`), and its `## Lab readback`
   section starts with one line `Lab: host=<host> lane=<lane or surface> command=<command>
   observed=<observation> restored=yes|no`. For a non-runtime change, the readback is the
   focused-test command and its output. Say so plainly. It ends with the line `Closes $T`, and the
   branch is named `omn-<n>-<slug>` (the hyphen after `omn`): the closes-ref gate reads either, and
   neither can be added after the first push. The lab line is in the body at creation:
   `/omni:pr-handoff` refuses a PR with no lab line, and the body is never edited to add one
   afterwards, because a body edit cancels the in-flight `pull_request` producer runs and a rerun
   replays the pre-edit body. If the lab line is missing or names an old head, post a PR comment
   that starts `Lab: head=<full head sha>` instead (the handoff reads it).
2. Push, then create the PR, as **two separate commands**. A compound push-plus-create line with a
   heredoc body is refused (ledger row 2026-09-22T21:20:46Z FRICTION lane=unified-verif-obs-plan):

   ```bash
   git -C <worktree> push -u origin HEAD
   python3 "${OMNI_PLUGIN_ROOT:?}/skills/merge-drain/scripts/landing_text.py" guard-create -- \
     onex scm pr-create "$R" --head "$(git -C <worktree> branch --show-current)" --base "$B" --bus-lane dev --draft --title "<type>($T): <subject>" --body-file /abs/path/<lane>-pr-body.md
   ```

   The body ends with the line `Ticket: $T`. `landing_text.py guard-create` refuses the create (exit 3, nothing opened) when the
   title's ticket has no such line in the body, because `/omni:pr-handoff` refuses "body cites no ticket id" and the
   body edit that cures it cancels CI (OMN-17427). A body drafted through
   `landing_text.py --pr-body --ticket $T` already ends with it.

   **Always open the PR as a draft.** Auto-merge arms on open in twelve repos, and on 2026-09-21
   one PR was armed 57 seconds after it opened, before its proof existed (runbook section 0a).
   Pass the body file as an absolute path; the body guard reads the path literally (ledger row 2026-09-22T20:31:13Z lane=m4-c9-probe).
3. If the proof ran on a leased surface, post the proof line from runbook section 6.2 **as a
   comment, while the PR is still a draft**. Later proofs also go in comments, never as body
   edits. Editing the body re-attaches tickets, and on a live PR it cancels the in-flight
   producers (ledger rows 2026-09-23T00:03:18Z FRICTION lane=lab-rebuild-unstick; 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 ("omnibase_infra#3971: a synchronize push")).
4. Read back: the body file you wrote is the expected value, and `onex scm pr-create` printed the terminal event with the URL and
   number. `pr_state_local.py --pr "$R#<n>" --json` reads title, body, draft flag and head from the
   watcher's state once its next tick has seen the PR (within about five minutes). `PR-STATE MISSING`
   right after the create is expected: do not poll for it. The live check of the body is the exact-head
   read `/omni:pr-land` makes before the ready flip.

## 8. Ready and land (through `pr-land`)

Hand the PR to the `pr-land` skill (`/omni:pr-land`) from its step 2. It owns the hold check, the ready flip,
arming, CI triage (with `ci-watch`), fixes, the squash merge on the exact head, and the
readback. This step adds only the per-ticket rules below.

**Before every ready flip and before every arm**, run `pr-land` step 3's pause check
(`pause_check.sh`, shipped in the pr-land skill) and the `/omni:ledger-msg` inbox check. A capped
RULING/HOLD grep missed a live hold (OMN-19268). A pause sent to you by message is not delivered
while you are working. On 2026-09-22 a lane merged five PRs after eight pause messages it never
received (ledger row 2026-09-23T02:09:09Z lane=friction-f8-correction). The ledger read is the only
stop that reliably reaches you.

**Runtime-merge pause.** Apply this to runtime-affecting PRs only:

1. **Sequencing rulings.** If a RULING orders runtime merges in this repo, keep your PR draft
   until its turn. For example, the RULING row 2026-09-22T18:54:53Z lane=manual-merge-drain-0425
   cleared omnibase_infra#3963 first, then omnibase_infra#3939, and allowed no other
   runtime-affecting omnibase_infra or omnimarket PR until omnibase_infra#3939 read MERGED. Write a
   STATUS row that cites the ruling's timestamp and lane.
2. **The lab must be keeping up.** Read the lane-j lab receipt for dev's nearest
   runtime-affecting ancestor (the commands are in `release-cut` step 3). If that receipt is FAIL
   or missing, **do not stack another runtime merge**. Keep the PR draft, write a STATUS row naming
   the receipt, and run `lab-rebuild-triage` (`/omni:lab-rebuild-triage`). On 2026-09-22 four runtime merges landed without a
   PASS receipt while the host was saturated (ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F10).
3. **Pausing yourself.** If you have already flipped or armed and a hold applies, run
   `gh pr merge <n> --repo $R --disable-auto`, then `gh pr ready <n> --repo $R --undo`. Read back
   `isDraft,autoMergeRequest` and write a STATUS row.

**Draft-era runs are poison.** Never rerun a CI run created while the PR was a draft, because a
rerun replays the draft event, skips the tests, and turns CI Tests Gate red. That includes a
push-era run that was cancelled around the ready flip: a run whose `created_at` is earlier than the
last `ready_for_review` event is draft-era, whatever its `event` reads (`pr-land` step 5, OMN-19379). If a draft-era row
blocks CI Summary, push a fresh head while the PR is non-draft (ledger rows 2026-09-21T23:40:15Z lane=kafka-producer-retry-2; 2026-09-23T01:05:02Z lane=omn17099-backend-overlay; 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 ("omnibase_infra#3971: a synchronize push")).

**Change-control evidence.** The autobind mints the companion when the PR is non-draft. It merges
before your PR. Write a hand-authored companion only when the autobind has provably declined or
stalled. Check that with a positive control: when was the last companion minted fleet-wide
(ledger row 2026-09-23T02:11:52Z FRICTION lane=omn19201-response-contract)? Build it only from artifacts you can re-read live now. A companion needs both the
receipt and the structural self-bind (ledger row 2026-09-20T17:11:38Z lane=occ-preflight-eligibility-red-0815). Name each receipt `<check_type>.yaml`, and
write long values as literal block scalars (ledger row 2026-09-21T21:00:49Z lane=dod-serializer-3). After a rebase, never rewrite a recorded
sha; rebind through the PR-number arm instead. The evidence-source stamp line appears only on a
line of its own. It names this PR's own merged companion, because it selects the tree that the
eligibility check reads (ledger row 2026-09-20T17:08:21Z lane=integration-seams-plan-and-probes-0140). Never spell it, or any other trigger literal, in prose (rule 15).

## 9. After the merge: receipt, Done, TERMINAL

1. Read back the merge (`pr-land` step 8): state, `mergedAt`, merge sha.
2. **Runtime-affecting:** find the merge's Runtime Rebuild Trigger run, then its lane-j
   receipt (`lab-pass-receipt-lane-j-<sha>`; the commands are in `release-cut` step 3).
   `"PASS"` is the only passing value. If there is no trigger run, or the trigger failed on a
   transient broker DNS error, rerun it once (ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F11). A FAIL receipt, or one that never
   arrives, goes to `lab-rebuild-triage` (`/omni:lab-rebuild-triage`). Put the receipt result in the TERMINAL row.
3. **Done flip, on a bound receipt only.** Run
   `bash $registry_root/omnibase_infra/scripts/onex skill dod_verify $T --execution-audience local_done_gate`
   (the flag is required: without it the verifier refuses with `EXECUTION_AUDIENCE_REQUIRED`) and read
   `verify_status`, `acceptance_basis`, the per-check results and the released check. Run the
   ticket's own acceptance probes live, read-only. The done-flip guard (OMN-13856, OMN-20368)
   allows Done only when `contracts/$T.yaml` in the product repository that implemented the ticket (at
   its default branch, naming the merged PR) binds EVERY
   labelled acceptance criterion through `binds_ac`, each discharged by a PASS receipt taken
   against the current contract entry. Nothing substitutes for that: not a merged PR, not ticked
   boxes, not a comment, not an exemption label. `NO_ACCEPTANCE_CHECKS`, a skipped or refused
   verdict, or a receipt the contract has since changed under is a hold, never a flip, and the
   remedy is to bind the criteria (`binds_ac`) and land fresh receipts through an evidence PR, then
   re-run dod_verify. The evidence lane writes each `ac_bindings` record with `proposed_by` set to
   its own lane and with no `accepted_by` or `accepted_at`, and names the verifier in its handoff.
   It never writes its own lane into `accepted_by`: node_dod_verify reads that record as not
   accepted and turns a verdict that would be VERIFIED into SKIPPED with `AC_BINDING_SELF_ACCEPTED`
   (omnimarket#3279), and the hosted `repo-evidence / dod-verify` check refuses it as
   `ac_binding_self_accepted`. A second lane, a verifier lane or Codex,
   re-runs the bound check and accepts it (`/omni:verify-claims` step 3a); the operator sees only
   disagreements. Do not tick an acceptance box yourself before that receipt exists: the guard
   refuses the edit. After a passing receipt, tick the boxes with one `save_issue` call that patches only
   the boxes, then flip Done with a second call: one call that does both is refused while a box is still
   unticked (OMN-20368 hook, measured 2026-10-29). Write a cross-repo PR as its full URL, because a bare `#N` resolves in the
   wrong repo. Other holds: an unmet criterion, an indeterminate probe, or merged but unreleased in
   a publishing repo. For the last of these, the remedy is `release-cut` (`/omni:release-cut`).
   Leave the ticket open and name the gap.
4. Worktree: lane closeout removes it (OMN-17427, OMN-20148). Your CLAIM named the tree in
   `worktree=` (step 0). `pr-handoff`'s `handoff.sh` archives and removes that tree before it writes
   your TERMINAL, and the TERMINAL carries `worktree=pinned-removed:<path>@<archive>`,
   `worktree=removed:<path>` or `worktree=kept:<path>:<reason>`. Where your TERMINAL is not written by
   a handoff, or the handoff kept the tree, run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_lane_closeout.py" --lane <lane> --worktree worktrees/$T/<repo>`
   from outside the tree (a shell whose working directory is not the worktree; never `cd`) and pass the one line it prints, already
   `worktree=<disposition>`, to your TERMINAL with `--kv`. A `kept:<path>:<reason>` cell names why the
   tree stays (a process inside it, no removal authority yet); the triage timers cover it. The ledger
   refuses a TERMINAL with no cell when your CLAIM named a path. Leave nothing uncommitted in it.
5. Append the TERMINAL row. It closes your CLAIM, names the merge sha, the lab receipt verdict and
   the Done or hold decision, and carries `friction=none` or cites your FRICTION rows (record new
   friction with `friction-record` (`/omni:friction-record`) first). Send one report to the orchestrator: the full report
   goes to `$registry_root/.claude_scratch/reports/<lane>-<UTC>.md`, the message is at most 12 lines,
   and it opens with `Premises falsified: ...`.

## Guardrails

- One ticket id per PR title and body. Never a second ticket id, never a guessed id.
- Never push to a PR, or work in a worktree, that another lane owns. A lander never authors
  product code on a PR whose lane is still live (ledger rows 2026-09-20T00:27:18Z lane=manual-merge-drain-2245; 2026-09-20T16:34:52Z lane=manual-merge-drain-1149, OMN-18919).
- Scratch files carry your lane name: `<scratchpad>/<lane>-pr-body.md`, never `pr_body.md`. Twice a
  peer's generic file became another lane's commit message or PR body (ledger rows 2026-09-21T03:00:22Z lane=obs-board-drive-1700; 2026-09-22T23:38:46Z FRICTION lane=m4-c12-probe; 2026-09-23T00:13:21Z FRICTION lane=m4-c13-probe).
- Write files with the editor tool, then run git and gh as separate commands. A heredoc
  containing apostrophes, or prose that names git verbs, gets the whole command line refused, and
  the next command may then read a stale file (ledger rows 2026-09-20T22:39:32Z lane=silent-gates-review-2145; 2026-09-23T01:03:54Z lane=friction-to-skills, OMN-19019).
- After writing a file that assigns a secret-shaped identifier, read the bytes back or run the
  file. The write can land a redaction placeholder on disk (ledger row 2026-09-20T15:58:47Z lane=omn18891-prepr-topic-isolation-1345).
- Squash only. Never `--admin`, never a skip token, never an allowlist added to get past a gate.
  If a gate fires, fix its input.
- Never kill a process you did not start (`pkill -f` is banned). Never mutate prod, lane-i,
  judge, the collaborator lane, or the public cluster.
- Any ruling you need goes to the orchestrator as one plain yes/no question with the default
  stated (ledger row 2026-09-23T00:58:03Z lane=friction-to-skills item=F4).

## Known friction (from prior runs)

Read this before step 4. Each line gives the symptom, then the correct move, then a pointer you
can re-read by its timestamp (`grep -hF '<timestamp>' $L $registry_root/docs/tracking/archive/*-split.md`). Friction from landing and CI is in `pr-land` and
`ci-watch`. Record new friction with `friction-record` (`/omni:friction-record`) and add a line here in the same PR.

- **F1 Orphaned PRs.** A PR that no lane owns sits unnoticed. When step 1 finds an open PR for the ticket, name its owner or take it before starting new work. → ledger row 2026-09-23T00:57:51Z lane=friction-to-skills item=F1, OMN-19192
- **F2 Characterising unread PRs.** Read the title, body and files before you describe any PR. → ledger row 2026-09-23T00:58:02Z lane=friction-to-skills item=F2
- **F3 Answering from a snapshot.** Every state claim comes from a read taken in the same turn, with its read time. → ledger row 2026-09-23T00:58:02Z lane=friction-to-skills item=F3
- **F4 Decision asks that were not questions.** Ask one plain yes/no question and state the default. → ledger row 2026-09-23T00:58:03Z lane=friction-to-skills item=F4
- **F5 Foreground verification reads.** An orchestrator running this skill for someone else sends reads to a background lane. → ledger row 2026-09-23T00:58:03Z lane=friction-to-skills item=F5
- **F6 and F16: a restart or usage limit kills lanes mid-ticket.** On resume, run `session-resume` (`/omni:session-resume`), read back what landed, and supersede the old CLAIM. → ledger rows 2026-09-23T00:57:51Z lane=friction-to-skills item=F6; 2026-09-23T00:57:52Z lane=friction-to-skills item=F16
- **F7 One finding forwarded to two lanes** produced two owners and duplicate companions. One finding goes to one lane, the one holding the open CLAIM. → ledger row 2026-09-23T00:58:03Z lane=friction-to-skills item=F7
- **F8 A pause sent by message never arrived.** Re-read HOLD and RULING rows before each ready flip and each arm (step 8). → ledger row 2026-09-23T02:09:09Z lane=friction-f8-correction (correction of the row 2026-09-23T00:57:52Z lane=friction-to-skills item=F8)
- **F9 An item handed over after TERMINAL.** Write a new CLAIM and answer that item first. → ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F9
- **F10 Lab host saturated.** Runtime merges landed without a PASS receipt. Apply the runtime-merge pause (step 8.2) and run `lab-rebuild-triage` (`/omni:lab-rebuild-triage`). → ledger rows 2026-09-23T00:57:52Z lane=friction-to-skills item=F10; 2026-09-22T23:22:55Z lane=lab-rebuild-diag
- **F11 The rebuild trigger gave up on a transient DNS error.** Rerun that trigger run once (step 9.2). → ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F11
- **F15 A shadow job's timeout read as a test failure.** Exit 124, or a cancel at `timeout-minutes`, is a budget timeout. Read the log. → ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F15
- **F17 The liveness guard refused a stand-down message that named a peer lane.** Refer to a peer by its CLAIM row's timestamp, not its lane name. → ledger row 2026-09-23T00:58:03Z lane=friction-to-skills item=F17
- **Two lanes, one worktree.** Claim and grep the ledger before `git worktree add` (step 0). → ledger rows 2026-09-21T21:00:34Z lane=dod-serializer-3; 2026-09-22T21:36:45Z FRICTION lane=c15-reroute-fix-r2
- **Worktree guard refused `"$WT"`.** Fixed by OMN-19229: the guard now expands variables. The old
  advice, to pass a literal absolute path, sent lanes to type the root from memory, and some typed
  the stray sibling root. Use `"$registry_root/worktrees/$T/<repo>"`. → ledger row 2026-09-23T01:34:21Z FRICTION lane=reconciler-fix; operator ruling 2026-09-24T12:53:21Z, OMN-19388
- **The RED-proof restore destroyed uncommitted work, three times.** Use `git show "origin/$B:<path>" > scratch`, or commit first and confirm the commit with `git log -1`. → ledger rows 2026-09-20T01:56:50Z lane=deploy-agent-false-success-diag-0016; 2026-09-20T03:32:39Z lane=deliver-candidate-green-omn18364-2255 ("the rule-17 RED-proof recipe"); 2026-09-21T11:22:06Z lane=obs-board-drive-1700, OMN-19021
- **A refused commit read as success.** Read `git log -1` after every commit. → ledger rows 2026-09-20T03:32:39Z lane=deliver-candidate-green-omn18364-2255 ("the rule-17 RED-proof recipe"); 2026-09-20T17:49:51Z lane=chain-canary-ledger-hop-1600
- **The worktree venv repair (`check-omnimarket-venv-drift.sh --repair`) broke venv purity, and the next commit failed silently.** Run `uv sync --frozen` before committing. → ledger row 2026-09-20T17:49:51Z lane=chain-canary-ledger-hop-1600
- **Reused a squash-merged branch and got CONFLICTING.** Cut a new branch off the base. → ledger row 2026-09-21T03:32:25Z lane=session-goal-0320
- **A lander edited an already-applied migration.** Applied migration bytes are immutable. Put the rationale in the PR body or a test comment instead. → ledger row 2026-09-20T12:10:40Z lane=manual-merge-drain-0742
- **Market migration without its infra vendor mirror.** Every omnibase_infra commit is then refused by the sync hook. Land both halves. → ledger rows 2026-09-21T17:46:13Z lane=omn18868-67-seam-gates-restart; 2026-09-21T22:35:00Z FRICTION lane=pr-fix-omnibase_infra-3923
- **Cross-repo migration pairs deadlocked.** Land the market contracts in the same order as the infra vendors. → ledger row 2026-09-20T00:13:32Z lane=obs-board-drive-1700
- **Version number collisions with the post-release bump bot.** List the versions every open head claims before bumping, and expect to rebump. → ledger rows 2026-09-20T17:57:37Z lane=obs-board-drive-1700; 2026-09-20T17:58:05Z lane=omn18891-prepr-topic-isolation-1345; 2026-09-21T23:40:20Z lane=kafka-producer-retry-2, OMN-18923
- **A just-published dependency reported unsatisfiable.** Use `UV_NO_CACHE=1`, not `--refresh-package`, and check the simple index before lowering a pin. → ledger row 2026-09-20T06:02:08Z lane=core-release-04718-unblock-codex-1845
- **Rewriting the whole PR body silently dropped the machine-added stamp line.** Edit the body surgically, restore only that one line naming the real merged companion, then rerun the whole run. → ledger row 2026-09-20T03:50:05Z lane=runtime-autowire-crashloop-fix-2150
- **A rerun replayed the draft event.** Push a fresh head while non-draft instead of rerunning a draft-era run. → ledger rows 2026-09-21T23:40:15Z lane=kafka-producer-retry-2; 2026-09-23T01:05:02Z lane=omn17099-backend-overlay; 2026-09-23T03:41:23Z lane=m4-c16-producer-r2 ("omnibase_infra#3971: a synchronize push")
- **A skipped gate never re-ran under `--failed`.** Rerun the whole run. Branch protection reads every copy of a required context. → ledger row 2026-09-20T10:28:37Z lane=core-release-04718-unblock-codex-1845
- **The evidence-source line cited a sibling repo's companion**, and eligibility read a tree with no receipt. Cite this PR's own companion; the tell is `occ_commit_sha` in the verdict JSON. → ledger row 2026-09-20T17:08:21Z lane=integration-seams-plan-and-probes-0140
- **A hand-authored companion failed a full cycle.** It needs the receipt plus the self-bind, receipts named `<check_type>.yaml`, and literal block scalars. → ledger rows 2026-09-20T17:11:38Z lane=occ-preflight-eligibility-red-0815; 2026-09-21T21:00:49Z lane=dod-serializer-3, OMN-18921
- **A failed supersede receipt latches for the PR's lifetime.** The runner executes declared checks in a depth-1 checkout with no tags, so write checks that pass there. → ledger rows 2026-09-21T18:09:53Z lane=omn18868-67-seam-gates-restart; 2026-09-21T17:46:31Z lane=omn18868-67-seam-gates-restart, OMN-19050
- **deploy-gate and Contract Compliance each refuse what the other demands for a live-runtime claim.** Put the live probe in the pre-PR proof receipt with a countersign, not in a contract. → ledger row 2026-09-21T23:39:58Z lane=dogfood-x-surface
- **One ticket across several repo PRs produced DIRTY companions.** Split the ticket per repo, or serialize the structural unions. → ledger rows 2026-09-23T01:28:32Z lane=c17-finish; 2026-09-23T02:25:38Z FRICTION lane=prosthetic-skills
- **The autobind stopped minting fleet-wide.** Positive-control the last mint time before you hand-author anything. → ledger row 2026-09-23T02:11:52Z FRICTION lane=omn19201-response-contract
- **A handoff named a suspect subsystem before anyone read the failing log.** Read the failing job's own last log line first. → ledger row 2026-09-20T08:25:41Z lane=occ-preflight-eligibility-red-0815
- **Integration Test Coverage fired on a comment-only change.** It is advisory, not a required context. Do not revert working code to quiet it. → ledger row 2026-09-20T08:03:05Z FRICTION lane=deploy-agent-false-success-diag-0016
- **A heredoc or compound command was refused, then a stale body or message file was read.** Write the file first, then run the commands separately. → ledger rows 2026-09-20T22:39:32Z lane=silent-gates-review-2145; 2026-09-21T03:00:22Z lane=obs-board-drive-1700; 2026-09-22T21:20:46Z FRICTION lane=unified-verif-obs-plan, OMN-19019
- **The Write tool put a redaction placeholder on disk.** Run or collect the file right after writing it. → ledger row 2026-09-20T15:58:47Z lane=omn18891-prepr-topic-isolation-1345
- **The delegate misrouted prose to code generation.** Pass `--task-type document` for prose. → ledger rows 2026-09-20T03:32:38Z lane=deliver-candidate-green-omn18364-2255; 2026-09-20T06:31:29Z lane=merge-sweep-residuals-0615; 2026-09-22T12:55:56Z lane=draft-pr-classify-1250
- **The brief's premises were stale.** Re-read every premise before the first write (step 2). → ledger rows 2026-09-22T15:48:23Z lane=new-host-access-network-r3; 2026-09-22T21:34:28Z lane=pc2-rung-register; 2026-09-22T12:28:07Z lane=delegation-drive-2
- **Read a stale docs_repo clone.** Read `origin/main` from the object store, not the working tree. → ledger row 2026-09-20T13:40:13Z lane=prepr-lane-epic-mint-1320
- **Step 3 and step 6 hardcoded `origin/dev` and `--base-branch dev`.** plugin-tooling-pkg has no
  `dev` branch, and registry_root and docs_repo land on `main`. Resolve `B` from
  `gh api repos/<owner>/<repo> --jq .default_branch` (step 3) and use it everywhere. Only omnibase_infra
  and omnimarket are wired to the rebuild trigger (step 6), checked by the trigger workflow's file
  name at the base, not by a text grep. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230
  lineage.
- **The version-collision check (step 4.7) covered only `pyproject.toml`.** A plugin repo bumps
  `plugin.json` and its marketplace entry together. Fixed 2026-09-23 by the omni-skill-fixes pass,
  OMN-19230 lineage.
- **Step 3's base read was not validated.** An API failure left `B` empty, and the recipe went
  on to fetch and branch from `origin/`. The read now falls back to the canonical clone's checked-out
  branch (it was `git ls-remote --symref` until the lane git-fetch guard, OMN-20495) and accepts only
  `dev` or `main`. OMN-19387.
- **Every `ledger:NNNN` pointer went dead when the ledger rolled** at 2026-09-23T14:00:47Z. They
  now name a row by its timestamp and lane. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230
  lineage.
- **Step 1 searched merged PRs with `--state merged`,** which gh refuses (`--state` takes only open
  or closed). Use `--merged`. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **Step 3's recipe had no registry_root case:** `git -C $registry_root/<repo>` names a directory that does
  not exist when the repo is registry_root itself. Step 3 now says to use `git -C $registry_root`. Fixed
  2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
- **Step 7 and the guardrails named a lane by a person's name.** They now say "the collaborator
  lane". Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage.
