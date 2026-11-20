---
name: lane-brief
description: Write a dispatch brief for a background lane. Embeds the committed standing rules block instead of hand-writing one, runs a premise check against live state and the rolling ledger (live file plus archive rolls, from ONEX_LEDGER_PATH), and adds a section 3a Constraints block pasted byte for byte from the ledger readers (inbox, holds in force, the cited landing RULING row, the newest rulings) with the landing sentence (hand PRs to the landing lane by one ledger MSG), model, effort, consent, OUT OF SCOPE a CLAIM template carrying parent= and a 3a.9 delegation step with the TERMINAL delegation cells. Refuses dispatch when any 3a part is missing. Use before every Agent or workflow dispatch that does work.
prosthetic: true
replaces_when: "/onex:lane_dispatch (plus the lane-brief-regenerate workflow) resolves a committed overlay through LANE_DISPATCH_OVERLAY_PATH, and three consecutive dispatches report a non-zero injected rules byte count, a CLAIM row appended by the dispatch seam before the lane's first write, and a premise table. On 2026-09-22 the variable is unset, so that skill hard-stops by its own contract."
restored_from: "omniclaude 55913e973^ plugins/onex/skills/dispatching-parallel-agents/SKILL.md"
ticket: OMN-19210
---

# Lane brief (prosthetic)

Agent-posted Linear comments have `actor: <lane> (<model>)` as the first line.
Lane and model come from the actual execution identity, never the Linear account author.
Every posting recipe, comment body file and `save_comment` or `create_comment` body carries
that line before the comment text. Human operator comments without an actor line remain
human even when they share the account used by an agent.

```bash
H="${registry_root:?set registry_root to the registry root}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$H/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
```

A brief has five parts, in this order: **premise table, task, rules, constraints (3a), report**.
Write it to a file under the session scratchpad and dispatch from the file. Never retype the rules
or a reader's output from memory.

This skill writes **no ledger rows**. The lane it briefs writes its own CLAIM (from the 3a
template) and TERMINAL. The ledger is the coordination surface: the premise check reads it, and 3a
carries what it says to the new lane.

Set the ledger once. There is no default path (rule 8); the archive rolls are its sibling
`archive/` directory:

```bash
H="${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
A="$(dirname "$L")/archive"
LB="${CLAUDE_SKILL_DIR}/scripts/lane_brief.py"
```

Shell state does not carry between tool calls, so repeat these lines at the top of any later
command that uses `$H`, `$L`, `$A` or `$LB`.

`${CLAUDE_SKILL_DIR}` is filled in by the harness with this skill's own directory. If you are
reading this file somewhere other than a loaded skill, run `scripts/lane_brief.py` from the
directory that holds this file. The helper is read-only in every mode (`--help` says so): it
prints, and its only write is the `--out` file you name. Its tests are
`tests/test_lane_brief.py` in this skill's directory. They need no registry root: the readers come
from the sibling skill directories and the ledger is a fixture, which is how the plugin repo's
required check runs them. With `registry_root` set to a registry root they also append the CLAIM
template through the real `onex_ledger.py` lint to a scratch copy of the ledger; run them locally
with `LANE_BRIEF_REQUIRE_REGISTRY=1` so that tier cannot be skipped.

## 1. Premise check (before writing the brief)

Everything the brief will assert about the world is a premise. Lanes have been briefed on a
cleared criterion, a server key removed minutes earlier, sudo access that did not exist, and a
wrong ticket id. Each was caught only by the lane reading live state first. So read it before the
lane does:

1. **List every factual claim** the brief will make: PR state and head, ticket state, host or lane
   health, which criterion is red, who owns what, which hold is in force.
2. **Check what already answers it before building a probe.** Look at the board readback
   (`/onex:board_readback`), the ledger, the latest handoff in docs_repo
   `beta/handoffs/` (read it out of the object store:
   `git -C "${registry_root:?}/docs_repo" show origin/main:<path>`), and
   `.claude_scratch/reports/`. The ledger read covers the live file and the rolls, rolls first so
   the tail keeps the newest rows:

   ```bash
   grep -HnF -- '<ticket or PR>' "$A"/*-split.md "$L" | tail -n 40
   ```

   `python3 "$LB" grep '<ticket or PR>'` runs the same grep from the ledger's directory, so rows
   print as `archive/<roll>:<n>:` or `ROLLING_WORK_LEDGER.md:<n>:`. Commission a probe only for what none
   of these answers.
3. **Re-read each premise live**, one command each: `python3 "$OMNI_PLUGIN_ROOT/skills/merge-drain/scripts/pr_state_local.py" --pr OmniNode-ai/<repo>#<n>`
   (state, draft, head, CI, from the PR watcher), `git -C "${registry_root:?}/<repo>" log|show origin/<base>` for code and
   merges, `get_issue <id>`, `ssh ... docker inspect ...`, or the ledger's RULING rows. GitHub reads use
   `onex scm pr-view OWNER/REPO#N`, `onex scm pr-list OWNER/REPO` or `onex scm run-list OWNER/REPO`;
   the gh shim refuses direct lane reads (OMN-20911, RULING 2026-10-10T18:17:36Z). Record the result as
   `verified by: <command> => <observation>`. A premise you did not re-read is written
   `UNVERIFIED — falsify first`.

   `OMNI_PLUGIN_ROOT` is the installed omni plugin's root, the directory that holds `skills/` and `scripts/`.
   The remote-lane runner exports it in every lane session, set to the plugin's path on that lane's host, and
   a local landing worker has it set too. A hand-run orchestrator session derives it from this skill: the
   harness fills in the skill's base directory when the skill loads, and the root is two directories above it
   (`export OMNI_PLUGIN_ROOT="$(cd "<base directory>/../.." && pwd)"`). Never look for the script with `find`
   over a directory tree, and never over `/`: a search of the filesystem root cost one worker 420% CPU on a
   host at load 81 to 118 (OMN-17427).
4. **Check ownership.** Grep the live ledger and the rolls for an open CLAIM on the same ticket, PR
   or worktree (a CLAIM with no later TERMINAL or CLOSEOUT for that lane):

   ```bash
   grep -HnF -- '<ticket, repo#pr or worktree path>' "$A"/*-split.md "$L" | grep -E ' [|] (CLAIM|TERMINAL|CLOSEOUT) [|]' | tail -n 20
   ```

   If one is open and live, do not dispatch a second lane onto it: send the owner one MSG through
   `/omni:ledger-msg` instead. Two lanes once held one PR and one rebased the other's worktree.
5. **Check holds and rulings.** Read the newest RULING rows for any merge-order hold, landing or
   sequencing ruling that touches the lane's repos:

   ```bash
   python3 "$LB" rulings
   ```

   It prints the output of `grep -HnE '<RULING row head>' archive/*-split.md <ledger> | tail -n 15`,
   run from the ledger's directory, as printed. Quote a
   row by its timestamp and lane, because a line number moves when the ledger rolls. The same
   output is pasted into 3a.4; you do not retype it.
6. **Check whether each file the lane will touch is on a burn-down baseline.** For every path the
   task names, grep it in that repository's `.onex_ratchets/canonical_file_shape_baseline.txt` and
   `.onex_ratchets/canonical_file_shape_burndown_baseline.txt`, read at `origin/<base>`:

   ```bash
   git -C "${registry_root:?}/<repo>" show "origin/<base>:.onex_ratchets/canonical_file_shape_baseline.txt" | grep -F -- '<path>'
   git -C "${registry_root:?}/<repo>" show "origin/<base>:.onex_ratchets/canonical_file_shape_burndown_baseline.txt" | grep -F -- '<path>'
   ```

   Write the result into the brief per file: `baselined: yes|no (<baseline file>:<line>)`. A baselined
   file only shrinks (RULING 2026-10-01T12:36:54Z), so for a `yes` the brief names the contract, node and
   handler that receives the new logic and sets the code-line budget to zero growth. A handler file that a
   node contract binds leaves the baseline in the same commit and may then change freely. A brief that
   names a file and leaves its baseline status unstated has an unverified premise (step 3).

### 1a. What `check` reads live (OMN-20788)

`check` reads the tickets and files the brief's own prose names, and refuses a brief that misdescribes
them. It reads the prose outside the pasted rules block, the generated 3a block and fenced examples. A
brief that names tickets needs `LINEAR_API_KEY`, from the environment else from the host env file
(`$HOME/env-dir/env-file`, the file the remote-lane runner reads, so a launchd unit with no key in its
environment still assembles briefs; OMN-21872); a brief that names none needs no key. A read that cannot be made exits 2, never a pass.

- **Ticket state.** Every `OMN-<n>` in the prose is read from Linear. A ticket that is Canceled or Done,
  or that carries a merged `feat`, `fix`, `refactor` or `perf` pull request attachment (an umbrella
  ticket with children is exempt from the merged test), is refused unless the brief carries
  `ticket-state-ack=<id>:<state>` with the state the refusal names (`Canceled`, `Done`, `merged`). An
  acknowledgement of a state the ticket is not in is refused as stale. A ticket Linear does not know is
  refused. Evidence, docs and chore pull requests that merged under the ticket do not count.
- **Quoted criteria.** A brief that states what a ticket asks quotes it: a line `ticket-criteria: OMN-<n>`
  followed by the ticket's criterion lines, each prefixed `> `. Each quoted line must equal a live
  criterion line of that ticket (checkbox state, list marker and markdown links aside). A prose sentence
  of the form `OMN-<n> asks|requires|says|states|specifies|wants|demands ...` with no such block is
  refused. Whether an instruction agrees with the criteria it cites stays with the plan review.
- **Paths.** A line `evidence: <repo>@<base>:<path>` must name a path that exists at the base in the
  clone of `<repo>` (a sha or ref is read as written, a bare branch name as `origin/<branch>`). A line
  `creates: <repo>@<base>:<path>` must name a path that does not exist yet, whose parent directory
  exists at the base or is declared by an earlier `creates:` line ending in `/`, and which sits in a
  canonical location: a code file only under `src/<pkg>/{nodes,handlers,models,protocols,contracts,enums}/`,
  `tests/` or `docs/` (the canonical-file-shape ratchet's rule, OMN-20304). The clones are found under
  `--repo-root` (repeatable; default `$registry_root` and its parent).
- **Open and draft pull requests (OMN-23897).** The PR watcher state is read for the open and draft pull
  requests of the repo the CLAIM template names (`open_pr_check` in `handler_lane_engine_failover.py`, beside the live-CLAIM check; the kinds that refuse, the kinds
  that warn, the listing limit and the state-age bound are its overlay's). A pull request that heads the brief's
  branch, or whose title or head ref cites the brief's ticket (an umbrella ticket with children is exempt, as in the
  live-CLAIM check), refuses the brief; one whose body names a file the brief names warns. A line
  `supersedes-pr=<repo>#<n>` in the brief lifts the refusal for that pull request (the brief replaces it). A brief whose
  `## 2. Task` section names an open pull request of its repo as `repo#n` (an `owner/` prefix allowed) or a bare `#n` is
  refused unless the brief carries `continues-pr=<repo>#<n>`, `supersedes-pr=<repo>#<n>` or, when it only reads that pull
  request, `cites-pr=<repo>#<n>`. A line
  `continues-pr=<repo>#<n>` lifts it for a pull request the brief continues (review fixes, a successor after its writer
  ended), and only while no OTHER live lane holds that pull request: a live holder is a lane with an open CLAIM (no
  TERMINAL since) and a row in the last 2 hours that names the pull request in a `pr=` or `prs=` list or a `scope=`
  sentence (`repo#n`), its ticket (an umbrella ticket with children is exempt), or its branch in a `branch=` cell, a
  `scope=` sentence or a worktree path (`.../<ticket>/<repo>`); a lane a STATUS `pr=`/`prs=` row or a MSG `owns=` row
  names the pull request for is read the same way through its own open CLAIM (a MSG's `to=` may list lanes, comma-separated
  or in backticks, and each is read). A lane whose newest row naming the pull
  request is a STATUS `handed-off=` or a MSG to `landing-controller` naming it in `pr=` (the drain map's handoff rule)
  has released it, and its own MSG handing it back (a CI "returned to green" is no hand-back) releases only a hold a MSG
  `owns=` route gave it, never its CLAIM `pr=`, branch, ticket, worktree or STATUS hold, until a CLAIM of that lane written
  after the release names the pull request by `pr=`, scope, branch, ticket or worktree (a CLAIM for other work holds nothing).
  When the watcher state or overlay cannot be read, or the pull request is absent from it, the holder read still runs on
  the `repo#n` key alone. A request to another lane
  (`needs=`) releases nothing. A MSG's sender is read for release only, never as a holder, and a failed ledger read of
  the pull request's number is a holder (the check never reads it as no rows). The brief's own 3a.8 CLAIM template carries a
  `pr=<repo>#<n>` cell for the continued pull request (the remote-lane runner copies it into the lane's CLAIM, where every
  later brief's holder read finds it), read with the remote-lane runner's rule (the lane's own CLAIM line of 3a.8, the
  `pr=` cell, comma-split, each a bare `repo#n`); a `continues-pr=` brief whose CLAIM template carries no such cell is
  refused whether or not the watcher state or overlay can be read; `lane_brief.py constraints --continues-pr <repo>#<n>`
  renders it. All of it goes through the same `item_verdicts` reader the live-CLAIM check uses. The brief's own
  lane is never a holder. With no live holder the check prints `OWN <repo>#<n> is continued by this lane` and the pull
  request is the lane's own; with one it refuses, naming the holding lane and its newest row, and `continues-pr=` never
  lifts it (send that lane one MSG or wait for its TERMINAL). Use `supersedes-pr=` only when the brief truly replaces
  the pull request, never to get past a held one. A watcher state or overlay that
  cannot be read is a `WARN ... not checked` note on the PASS line, never a silent pass.

## 2. Task

Say what done looks like as observable state (a merged sha, a readback, a report path) and the
scope boundary (`OUT OF SCOPE:`, which 3a.7 carries). Name the model and effort explicitly. The
model is never inherited. Sonnet is the default for every lane, open-ended ones included, and Opus is
the exception (RULING 2026-10-27T21:29:22Z, OMN-20864): Opus runs only for a declared complexity reason
or after one failed Sonnet attempt, written as an escalation cell. That ruling amends RULING
2026-10-14T04:56:52Z, which sent every open-ended lane to Opus and so refused the merge sweep's diagnose
lane, which runs on Sonnet (2026-10-29T17:27Z). The lane-kind words, the escalation cell and line names,
the cited-failure prefix and the outcomes that do not count as a failure are rule data in
`lane_kind_rules.json` beside this file (the rule itself is `lane_kind_problems` in the lane placement node's handler), never
literals in `lane_brief.py`; the cell's value grammar is
the lane model policy's own (`complexity:<B4 or above>` or `sonnet-failed:<run or lane>`, the same
check the runner makes). `check` reads the kind from the lane name (a token among the data's open-ended
words, today `diagnose`, `diagnosis`, `cause`, `plan`, `investigate` or `investigation`, split on
`-_.:`; `explanation` is not one) and from a `Lane kind: open-ended` line in the brief (`Lane kind:
ticket` records the other kind). It refuses with the rule named:

| rule | refused when |
| -- | -- |
| `lane-kind rule 1` | a lane names opus and the brief carries no valid escalation cell: an `escalation_reason=` cell on the 3a.8 CLAIM template or the ROUTE line (`--escalation-reason` at generation, or the band's `complexity:B4`/`B5`), or an `Opus reason: <why sonnet cannot do it>` line in the brief (an empty or placeholder reason does not count). A `sonnet-failed:<run or lane>` cell is checked on the ledger and archive/: the cited lane has a CLAIM (`lane=` or `run=`) on a Sonnet model for the same ticket or PR as this brief, and a TERMINAL whose outcome is not a good one |
| `lane-kind rule 3` | a ticket lane (not open-ended) names sonnet while a stated criterion carries no falsifier (add it, or name opus with an escalation cell) |

An open-ended lane on Sonnet passes. `queue-status` flags a running Opus lane with no escalation reason
by the same ruling.

The criteria a brief states are its `- [ ]` lines and the `> ` lines under a `ticket-criteria: OMN-n`
marker, outside fenced examples; a brief that states none is not judged by rule 3.
If the brief grants a ticket mint, include the exact line
`Mint authority: delegated by the orchestrator for exactly one ticket`. A brief bound for a lab host
never carries it and never asks the lane to create a ticket: a headless lab session has no Linear MCP
save path, so the create gate cannot run there (OMN-21021). The launching session mints first and the
brief passes the id (`--ticket`); the lab lane comments on and moves that ticket through the host's
`LINEAR_API_KEY` (operator ruling 2026-10-08T22:58:31Z lane=orchestrator-9f8a).

## 2a. Model-before-build (standing ruling, RULING row 2026-09-23T14:30:21Z lane=omn17427-foreground, item 4)

A build-lane brief that has the lane construct a not-yet-built mechanism with a lease, more than one
writer, or a terminal it must emit cites a TLA+ model of the mechanism and its design-review verdict,
by path, or the brief is refused — write it and stop rather than dispatch. The model finds the
interleaving; a pytest on the real code is still the gate the lane runs, never a replacement for the
model. This is the `plan-write` skill's doctrine gate carried through to dispatch: a plan task that
was marked ready under it already names the model, so copy the citation into the brief rather than
re-deriving it. The formal-verification plan (OMN-19204) proposes a harness at omnibase_infra
`formal/`; until it lands, the model may live in the building lane's own scratch space.

## 3. Rules: embed, never retype

Paste the committed standing block from ops_tooling_pkg
`lane_rules/lane-rules-block.md` verbatim:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lane_rules_block.py"
```

The block carries the ledger lifecycle (CLAIM, TERMINAL, friction), the inbox check, one lane per
PR, lab before PR and the delegation command. Its PR paragraphs still describe polling CI and
arming auto-merge, which the single-landing ruling took away from every lane but the landing lane;
the landing sentence in 3a.3 and the line under it override those steps, so do not hand-edit the
pasted block. Append a delta here only when a rule is new and not yet in the block, and fold it
into the block in the same week.

**Home for new logic, per repository (report ratchet-home-0915, 2026-10-31).** New logic always has a
legal home; a lane that tries another one first costs a commit cycle. Put the row for the target repository
in the brief, under the pasted block:

| Repository | Gates that apply to new logic | Legal home |
| -- | -- | -- |
| omnimarket | file-shape only (no node-home gate, no allowlist) | A new node (contract, node and handler under `nodes/<n>/`), or a handler added to an existing node. |
| omnibase_infra | file-shape and the infra handler ownership gate; no node-home gate | A new node directory is allowed. The handler goes in `src/omnibase_infra/handlers/handler_<x>.py`, bound from the node contract's `handler_routing.handlers[].handler.module`, never under `nodes/<n>/handlers/` (OMN-20821, omnibase_infra#4565 and #5405). The infra allowlist only shrinks. |
| omnibase_core | file-shape and node-home | Models, protocols, enums, contracts and handlers in the canonical directories; a node only if its contract tags it `validator_node` or `validator_support_node`. Every other node goes to omnimarket. |
| omniclaude | file-shape and node-home | As omnibase_core: nodes go to omnimarket; thin skills stay. |
| plugin-tooling-pkg | file-shape, validate-plugin new-work rule, retirement | No new file and no growth. Build it in omnimarket and patch a caller by zero growth lines. |
| ops_tooling_pkg | file-shape, frozen by ruling | Data-only overlay under `config/`. Code goes to omnimarket. |

A new file in a canonical location is not baselined and can be any size; the baselined file it replaces
shrinks by the moved lines in the same commit. Binding a baselined handler from a node contract removes its
baseline line in the same commit and lifts the growth ceiling. Step 1.6 decides which row applies.

**Then read the target repo's own CLAUDE.md** for repo-specific deltas: its base branch, test
markers and commands, landing rules, and any gate that repo alone runs. Read it at the base the lane
will branch from, not from the working tree. The recipe stops on an unreadable base instead of
reading `origin/`:

```bash
H="${registry_root:?set registry_root to the registry root}"
R=plugin-tooling-pkg
B=$(git -C "$H/$R" symbolic-ref --short refs/remotes/origin/HEAD); B="${B#origin/}"
case "$B" in dev|main) git -C "$H/$R" show "origin/$B:CLAUDE.md" ;; *) echo "REFUSED: base branch of $R read as '$B'; stop" ;; esac
```

No fetch first: the canonical-clone sync keeps `origin/<base>` of every canonical clone current
(merge-triggered plus every 3 minutes), and the lane git-fetch guard (OMN-20495) refuses a fetch
typed from a lane. When the read must include a merge from the last minutes, run
`python3 "$H/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh "OmniNode-ai/$R" --branch "$B" --wait` first.

Put what applies to this lane under a `Repo deltas (<repo> CLAUDE.md @ origin/<base>)` heading
below the pasted block. The standing block is written for the product repos. For example, a plugin
repo's CLAUDE.md adds its own plugin-version rule, and a document repo has no lab step.

**Lab-first is not checked for a hand-written brief.** `tests/test_lane_briefs_lab_first.py` in
ops_tooling_pkg scans the packaged handler briefs only. A brief written by this skill and dispatched by hand
is never read by that test. The pasted block carries the lab-first step (the word lab and the
`lab-host-a` dev lane), so keep it in, and for a runtime-affecting lane name the lab surface in the task.

## 3a. Constraints (pasted, never paraphrased)

Standing constraints do not reach a dispatched lane by themselves: a hold, a landing ruling or a
model tier stated to the orchestrator is invisible to a subagent unless its brief carries it. So
the brief carries the readers' own output, generated and pasted by the helper, never summarized:

```bash
python3 "$LB" constraints --lane <new lane> --parent <dispatching lane> \
  --landing-lane landing-controller --landing-ruling-lane <lane cell of the routing RULING> \
  --landing-ruling <its timestamp> --ticket OMN-<n> \
  --model <model id> --effort <low|medium|high|xhigh|max> --repo <repo> \
  [--band <B2|B3|B4|B5> --score <0-21> --dims S<s>A<a>R<r>V<v>N<n>C<c>J<j>] \
  [--escalation-reason <complexity:B4+|sonnet-failed:run-or-lane>] \
  --out-of-scope '<what the lane must not touch>' [--consent docs/tracking/ROLLING_WORK_LEDGER.md:<line>] \
  --out "<scratch>/<new lane>/<new lane>-3a.md"
cat "<scratch>/<new lane>/<new lane>-3a.md" >> "<scratch>/<new lane>/<new lane>-brief.md"
```

The block has eleven parts, each under its own `### 3a.<n>` heading:

| Part | What it carries | Source |
| -- | -- | -- |
| 3a.1 Inbox | every open MSG and HOLD addressed to the new lane or `to=all` | `inbox.sh <new lane>` (`/omni:ledger-msg`), whole output |
| 3a.2 Holds in force | every HOLD with no RELEASE in the window, whoever it is addressed to | `catchup.sh` (`/omni:ledger-catchup`) section 2, with `CATCHUP_T0` pinned and recorded (default window 24h) |
| 3a.3 Landing | the cited routing RULING row, then the landing sentence (with the controller's escalation clause), the PR-creation sentence and the PR-reads sentence (OMN-20911: the local PR readers; `check` refuses a 3a.3 without it), the git-reads sentence and the Bash-timeouts sentence (OMN-19513: the sanctioned `canonical_clone_sync.py refresh ... --branch <base> --branch <head_ref> --wait` in place of the `git fetch` the lane git-fetch guard refuses, OMN-20495, and a timeout beside every long or background Bash call, OMN-20893; `check` refuses a 3a.3 without the refresh; the worktree sentence (OMN-17427): `git -C "${registry_root:?}/<repo>" worktree add "${registry_root:?}/worktrees/<ticket>/<repo>"` with an absolute path, one literal command per repo, and the internal root only where `test -d` finds it; `check` refuses a 3a.3 without it, and `instruction_problems` refuses brief text that gives `git worktree add` a relative `worktrees/` path) | `--landing-ruling <ts>` and `--landing-ruling-lane <lane>` identify the authority row; `--landing-lane landing-controller` identifies the target. The helper refuses (exit 3) when the authority row is absent |
| 3a.4 Standing rulings | the newest RULING rows | the step 1.5 grep |
| 3a.5 Model and effort | `model=<m> effort=<e>`, and with `--band` the line `ROUTE: band=<B> score=<n> dims=<...> dest=<d> model=<m> effort=<e>` (routing rubric W3, OMN-17427: B2 sonnet/medium, B3 sonnet/high, B4 opus/high, B5 opus/xhigh, from `BAND_TABLE`; R=3 or J=3 floors to B4). The CLAIM template and the 3a.9 TERMINAL cells then carry `band=`. `check` refuses a 3a.5 whose model or effort differs from its ROUTE band; a brief with no ROUTE line passes as before. A Codex route (`--model codex`, `dest=codex model=codex effort=<the band's Codex effort>`, high for every band) is accepted from the engine table in `handler_lane_engine_failover.py` (`CODEX_BAND_EFFORT`, `route_engine_problem`), the table the remote-lane runner reads, so the checked brief is the brief that runs (OMN-21647); a `dest=codex` without `model=codex`, a Codex route with another effort, and any model that is neither Claude nor Codex are refused. An opus lane (B4/B5, or `--escalation-reason`) gets the CLAIM template cell `escalation_reason=complexity:<band>` (OMN-21396; the runner and `node_lane_model_policy_compute` refuse Opus without it), and `--escalation-reason sonnet-failed:<run or lane>` is also written on the ROUTE line; `check` refuses an opus-band brief whose CLAIM template lacks the cell | this brief |
| 3a.6 Consent | each `consent=` citation with its OPERATOR-CONSENT row pasted under it, or `consent=not-cited` | the ledger line the citation names; a citation that is not an OPERATOR-CONSENT row is refused (exit 3) |
| 3a.7 Out of scope | `OUT OF SCOPE: <list>` | this brief |
| 3a.8 CLAIM template | the one append command and a CLAIM row with `lane=`, `actor=`, `model=`, `ticket=`, `parent=<dispatching lane>`, `repo=`, `worktree=worktrees/<ticket>/<repo>` (`worktrees/<ticket>` for a lane on several repos), `consent=`, scope and the rule-4 cost sentence | the helper; the lane fills the `<...>` cells and appends through `/omni:ledger-write` |
| 3a.9 Delegation | pure-text steps through `onex delegate` first (summaries, PR bodies, ticket comments, classification of logs and CI failures, OMN-19855); GLM through Claude Code only, with the retired cloud-glm backend refused (OMN-20173); Jev for typed decisions; `onex code-edit run` on the lab through `delegation_step.py code` with writable globs and named argv checks (Codex takes no work since the operator's ruling of 2026-11-05, "You can send reviews to Codex, but no work.": the engine policy's `codex_roles` omits `work`, and `check` refuses a 3a.9 that routes work to Codex), then `lab_crush.py` as the interim fallback only when the node route is skipped or fails (OMN-20292 pending), then GLM through Claude Code; Claude reviews and verifies. `check` accepts three lab code markers: code-edit with `runs=<run_id>`, the draft node path (`onex delegate --task-type code_generation`) with `runs=<run_id>`, or crush with `lab_agent=<session id>`; crush is never required. A code-edit loop counts as one delegated subtask and its turn run ids ride in `runs=`. The TERMINAL cells carry `delegated=<n> runs=<ids> codex=<thread_id> jev=<ids> lab_agent=<ids>` or `delegated=0 delegation_reason=<why>`. `check` also requires the disposition step (`delegation_step.py dispose`, OMN-20011); it requires the exact Codex command and thread cell only while the engine policy lists `work` in `codex_roles`, which the shipped policy does not | the helper, fixed text; see "Why 3a.9" below |
| 3a.10 Where heavy work runs | heavy work (tests beyond one focused file, builds, lint over a tree, headless agent runs) goes to a lab host through `/omni:lab-run`, with the command, the exit-75 refusal and the rule that the command never runs on the launching host instead; `check` refuses a 3a.10 without them (OMN-20101) | the helper, fixed text |
| 3a.11 Install first | a PR that changes a host install, a launchd or systemd unit, a tool, a hook or a plugin is installed from its branch on the lab through the declared installer, verified running, and recorded as `installed=<host>:<revision>` with `observed=<what ran>`; the handoff gate refuses the PR without it; `check` refuses a 3a.11 without the fragments in `install_first.json` (OMN-21815) | the helper, `install_first.json` |

**Contract before push (OMN-20864).** Every brief whose lane may open or push a PR in a repo
whose CI runs repo-evidence / dod-verify or deploy-gate carries this required step, with its ticket:

Before the first push, write contracts/OMN-<ticket>.yaml with a dod_evidence entry per acceptance criterion and, where deploy-gate applies, a falsifiable deploy check scoped so the hosted runner can run it; the push is refused without it.

The shared `lab_block()` puts it before the instruction to push for lab proof, so the constraints
builder, fan-out and lab-fill's block assembly inherit it. `check` derives the governed repo set
from `.github/workflows` job definitions and reusable workflow references under `--repo-root`
(default `$registry_root` and its parent), with no separate repo list. A repo with unread CI config
requires the step conservatively; malformed config refuses the read. A fenced example, a different
ticket, or an instruction missing the hosted-runner scope does not satisfy the check. The remote
runner supplies the same step to handwritten tick/fan-out briefs and both engines' preambles.

**The landing controller lands PRs.** RULING 2026-09-29T06:34:17Z lane=`orchestrator-83` took the
model out of the landing loop, and the repo-drains-84k TERMINAL (ledger line 16159) records that no
repo drain runs: the launchd landing controller lands every open PR. It replaced the per-repository
drain RULING 2026-09-25T14:34:28Z lane=`merge-drain-83` as the routing authority (OMN-19852). Pass
the newest routing row's timestamp as `--landing-ruling`, its lane cell as `--landing-ruling-lane`,
and the target as `--landing-lane landing-controller`. A newer routing RULING replaces all three
inputs together.
This skill builds no landing machinery: it only carries the authority row and repo-specific target
to the new lane.

**What the helper's landing check proves, and what it does not.** It proves that the cited authority
row exists and is a RULING written by the named ruling lane, so a mistyped lane or timestamp is refused. It
does not read what the ruling says. Citing a real RULING that is about something else passes, and
the one pasted row is the only evidence of the mistake. So before dispatch you read the pasted 3a.3
row and confirm that it names the landing lane (see Checks before dispatch). Deciding that by
matching the ruling's prose would be a hand-rolled parser of prose rows; the typed ledger removes
the need (Known follow-up).

The landing sentence is the same for every lane, including a lane the landing lane itself
dispatches, and is never edited:

`Landing: hand each PR to <landing lane> by ONE ledger MSG through /omni:ledger-msg (to=<landing lane> | pr=<owner/repo#n> | head=<sha> | needs=land|train|companion), then stop touching it; never merge, arm, rerun or poll CI.`

How the landing lane runs its own landing work is that lane's business (`/omni:merge-drain`); this
skill does not brief it. A fixed line follows the sentence: it supersedes any step in the pasted rules block that tells a
lane to arm, merge, rerun, update-branch or poll CI. The reason for one drain per repository is cost and
ownership: many lanes polling CI in parallel exhaust the GitHub API quota every lane shares, and a
PR with two owners is landed twice or not at all.

A second fixed line (`PR_CREATION` in the helper) follows it: the PR body carries the lab line at
creation, the body is never edited after the first push (an edit cancels the in-flight
`pull_request` producer runs, and a rerun replays the pre-edit body), and a later or corrected lab
proof goes in a PR comment that starts `Lab: head=<full head sha>`, which the landing handoff reads.
The same line has the body end with `Ticket: <the title's ticket>` and has the create run through
`merge-drain/scripts/landing_text.py guard-create`, which refuses a body without it: `handoff_row.sh` refuses such a body, and
the body edit that fixes it after the push cancels CI (OMN-17427, twice on 2026-10-14).
The same line names the PR base: the repo's landing branch read from GitHub and passed as `--base`, never typed from
memory (OMN-19998; `remote-lane` also states it in every lane prompt that has a repo).
It also tells the lane to end the body with `Closes <ticket>` and to name the branch `omn-<n>-<slug>`: the
closes-ref gate reads either, and neither can be added after the first push (OMN-17427; `remote-lane` states both
from the lane's `--ticket` in every lane prompt that has a repo).

**Why pasted, not summarized.** A summary drops the row that mattered: a hold addressed to all
lanes, or a ruling that changed the landing owner an hour ago. The helper frames each reader's
stdout in a text fence byte for byte, and `check --recompute` proves it.

**Why `worktree=`.** Every CLAIM template names the lane's own tree in one `worktree=` cell (a path
relative to `$registry_root`), and the ledger refuses a CLAIM without it (`worktree=none` for a lane that
has no tree; OMN-20148). The ledger takes one path per CLAIM, so a lane on several repos names the
ticket directory, `worktrees/<ticket>`, and its closeout keeps that cell as `not-a-worktree`.
The cell lets the lane's own handoff find the tree to close out (OMN-17427): the handoff archives and
removes it before it writes the TERMINAL, which carries the ledger's disposition cell
`worktree=pinned-removed:<path>@<archive>`, `removed:<path>` or `kept:<path>:<reason>`. `check`
refuses a 3a.8 with no `worktree=worktrees/` cell.

**Why `parent=`.** Every CLAIM template carries the dispatching lane in a typed `parent=` cell, so
ownership of any row, PR or worktree can be traced back to the lane that dispatched the work, and a
resumed session (`/omni:session-resume`) can tell whose lane died.

**Why 3a.9.** Delegation is the product and lanes are to dogfood it (rulings of 2026-08-29 and
2026-09-17). On 2026-09-26 a measurement of every lane since 00:55Z found that lanes delegated only
where a brief or skill made it a fixed step: the prover and lab-verify loops ran 111 of 117
delegations, and the repo-drain lanes, which wrote most of the text (1,008 ledger appends, 18 PR
bodies), ran none. None of the 198 workflow scripts pasted the rules block that carries the
delegation rule. So the brief now carries the step itself, and the check refuses a brief without
it. The TERMINAL cells make the share measurable per lane: `onex-delegation-accounting` in
ops_tooling_pkg counts them per lane and day, beside the lab and receipt records. A lane with no
text-shaped step still writes `delegated=0 delegation_reason=no-text-or-code`. Since the operator ruling of
2026-10-01 the ledger wrapper refuses a TERMINAL with no delegation cells or with a zero whose reason is not
one of `no-text-or-code`, `route-refused:<status>`, `route-unavailable:<run id>`, `read-only-lane`, and
`/omni:remote-lane` appends this block to any brief that lacks it.

**Prompt size when a lane delegates (measured 2026-09-28, OMN-17427).** A prose class (`document`,
`summarization`, `research`, `planning`, `review`) stays on the lab only up to about 8,192 tokens,
roughly 24k characters to be safe. Past that the router climbs to the free cloud rung, which took
127 s at 45k characters, and a climb two rungs deep hits the handler's 240 s budget, which a lane
reads as "every rung refused". Chunk a long source into slices under 20k characters, one call each,
plus one short call to join; pass `--task-type` every time. A diff or code review runs on the code
rung and takes about 200k characters. A failure inside those limits is not size: retry once after a
peer `reconcile-host` finishes. The table and the evidence are in docs_repo
`guides/delegate-skill-setup.md`, section 6.

**Why GLM is named.** Operator ruling of 2026-09-26 (ledger RULING row 2026-09-26T13:29:02Z
lane=glm-delegation-83-ruling): GLM is a delegation target lanes should use beside Codex and the lab
models. It runs only through Claude Code (OMN-20173): the z.ai Coding Plan terms (docs_repo
`reference/zai-glm-coding-plan-terms.md`, section 4) allow the plan's quota only inside officially
supported tools and bar direct model API calls from our own systems, so omnimarket#3136 retired the
direct GLM rung of `onex delegate`, and its cloud-glm backend pin now always fails. For text, GLM is the
second rung: `delegation_step.py text` tries the lab through the deployed-lane command and then GLM
through `/omni:harness-delegate --harness claude-glm`, and receipts both; a step the brief assigns to
GLM by name runs the harness directly (`--model glm-5.3-flash` first, glm-5.3 when flash is not good
enough). Proven 2026-10-01 by run 00000000-0000-4000-8000-000000000000 (claude-glm, glm-5.3, a 15 KB
summary in 38 s). For code, GLM is the fourth drafting route, Claude Code on GLM editing the lane's
worktree through `--writable-repo`. The lane applies and verifies the draft. `check` refuses a 3a.9
that drops the harness route, and refuses one that still pins the retired backend.


**Why Codex, Jev and the lab code step are named.** Codex was first (operator ruling 2026-09-30, OMN-20106) and takes no work since 2026-11-05 ("You can send reviews to Codex, but no work."), so the order today is the code-edit node on the lab, crush as the interim fallback, then GLM through Claude Code; the Codex command below applies only while the engine policy's `codex_roles` lists `work`. Self-contained build and fix items include mechanical code edits, test scaffolds, lint and type fixes, conflict-resolution drafts and red-PR fixes. Pure text still goes lab first then GLM; typed decisions with a fixed answer set on any repository but `docs_repo` (operator RULING 2026-10-13T18:34:53Z, OMN-20106) still go to Jev. Codex uses the account's config default model at high effort, with no model flag or model config, in the lane's own worktree on an allowed host. The emitted brief carries this exact command:

```bash
codex exec -C <worktree> -c model_reasoning_effort="high" -s workspace-write -c sandbox_workspace_write.network_access=true --json -o <scratch>/codex-final.txt - < <scratch>/codex-prompt.txt > <scratch>/codex.jsonl
```

The thread id is the `thread_id` of the first JSON line of codex.jsonl; MCP start-up errors on stderr do not stop the run. `delegation_step.py code` receipts each attempt and falls through if the binary is missing, the exit is nonzero or the thread id is absent. The second route is `onex code-edit run` on the lab (OMN-20293), using repeated `--writable` globs, `--check NAME=COMMAND` values and optional `--context` paths. Checks are argv, split with shlex and run without a shell in the worktree. `--max-turns` defaults to 20 (1..40). Each model turn is an `onex delegate` run; the loop counts as one delegated subtask and its turn run ids ride in `runs=`. The draft node path, `onex delegate --task-type code_generation`, remains an accepted lab code marker for a draft the lane applies itself. When writable globs or checks are absent the code-edit route is skipped; when it fails the route falls through to crush on the lab model through `lab_crush.py`, the interim fallback, never required, with OMN-20292 pending. The node and lab agent share `--lab-timeout` (default 1200 s), plus the caller's measurement margin; Codex and GLM keep `--timeout` (540 s each). `lab_crush.py --timeout` ends crush's whole process group at the deadline and still writes its receipt (exit 124). The fourth route is one GLM draft through Claude Code editing the worktree through `--writable-repo`. The Claude lane reads every diff, runs the focused tests and owns the PR. `check` requires one of the three lab routes; it requires Codex as well only while the engine policy's `codex_roles` lists `work` (the shipped policy does not: Codex takes reviews only), refuses a Codex work route when it does not, and refuses model flags on Codex commands. TERMINAL carries `codex=<thread_id>` beside `lab_agent=<session id>` and `jev=<correlation_id>`; lab sessions and code-edit turn run ids also ride in `runs=` for the ledger grammar. The loop id keys the code-edit answer's disposition; the audit's `node-turns-only` requirement detects crush sessions and node turns lacking run ids.

The draft is checked, not trusted. Graded outputs from that window counted rows wrong while scoring
1.0, and one Linear reply draft approved a remediation in the operator's voice from facts that held
no such decision. Counts and identifiers stay in the shell; only the prose is delegated.

## 4. Report contract

End the brief with: write the full report to `$registry_root/.claude_scratch/reports/<lane>-<UTC>.md`,
return at most 12 lines, open with `Premises falsified: ...`, append the TERMINAL row (with
`friction=` and the 3a.9 delegation cells) through `/omni:ledger-write`, and send one message at terminal. A lane whose PR is
ready sends the one handoff MSG that 3a.3 names, then appends its TERMINAL with
`outcome=handed-off`, and does not touch the PR again.

## Checks before dispatch

Run the mechanical check first. Exit 3 means **do not dispatch**: fix the named part and re-run.

```bash
python3 "$LB" check "<scratch>/<new lane>/<new lane>-brief.md" --lane <new lane> --recompute; echo "rc=$?"
```

For a brief bound for a lab host (a lane dispatched through `remote-lane`, `/omni:lab-run` or any headless
host session) add `--lab`: `python3 "$LB" check "<brief>" --lab`. It additionally refuses (exit 3) a brief
whose own prose carries the `Mint authority:` grant line as a line of its own, or asks the lane to create a
ticket (`/omni:create-ticket`, `save_issue`, "mint a ticket", "create a Linear ticket"), and names the fix:
mint first, pass the id with `--ticket`. A sentence that forbids the mint ("this lane mints nothing", "do
not run `/omni:create-ticket`", "no minting tickets"), whatever an OUT OF SCOPE header lists (the rest of
its sentence, where `;` separates entries and only `.` `!` `?` ends the list, and the bullets under a header on
a line of its own), a quote, a fence and the pasted blocks are not asks, and a sentence naming the bus route (`onex ticket`, create-ticket section 9) is admitted unless it also names `save_issue` or a Linear MCP tool, and comments, state changes and ruled criterion edits through `LINEAR_API_KEY` stay admitted.
Without `--lab` the grant line is admitted, as for a brief that runs on the launching host. The reading is
prose, so it cannot see every phrasing (for example "create a ticket if none exists" passes); the grant line
is exact. The remote-lane runner runs the same refusal before placement, so a brief that skipped `check` is
refused there too.

`--lab` also reads the brief's own ticket (the 3a.8 CLAIM's `ticket=`) live (OMN-17427). A headless lab lane
has no Linear tool, so when that ticket has a Linear description the brief must carry its words: paste the
block `python3 "$LB" ticket-text --ticket <id>` prints (the ticket's title, state and description under a
`ticket-text: <id>` marker, its `- [ ]` criterion lines under `ticket-criteria: <id>`, every line from the
ticket quoted, so none of it reads as the brief's own premises or asks). A brief without the block, or whose
quote leaves out a criterion line, is refused (exit 3), and so is one whose ticket has no description
(`ticket-text-empty`, OMN-20607: nothing to embed, and a lab lane cannot read the ticket itself). The remote-lane
runner appends the same block at dispatch when a brief has none, with the launching host's key, so the lane receives
it either way, and refuses the dispatch (`REMOTE-LANE-TICKET-TEXT-REFUSED`, reason `ticket-unreadable` or
`ticket-text-empty`) when it cannot read the ticket or the ticket has no description.

It refuses a brief whose 3a section is absent or is missing any of its eleven parts, whose reader
blocks are not reader output, or whose pasted inbox, holds or landing RULING row differs from a
fresh read. It also refuses a brief with no pasted rules block, and one whose tickets or cited paths
do not match the live state (step 1a). It also refuses a brief whose own text tells the lane to run a
command the shared-tree git guard refuses (`git fetch`, `git pull`, `git ls-remote`, `git remote update`, or a
checkout, reset, rebase, push or non-fast-forward merge in the registry clone) and one that starts a background
command (`run_in_background`, `nohup`, a trailing `&`, the runner's `--detach`) with no `timeout` on that line or
the next two (OMN-19513). A negated mention ("never `git fetch`"), a `# comment` tail and a ```text fence of pasted
reader output are not instructions. It does not check what the landing
RULING says. Then confirm by reading:

- The row pasted under 3a.3 is the operator's landing ruling (it names the lane that lands PRs),
  not some other RULING by the same lane. The helper cannot tell them apart.
- Every premise line carries `verified by:` or `UNVERIFIED`.
- No open CLAIM on the same target (step 1.4), and the RULING rows were read (step 1.5).
- The target repo's CLAUDE.md was read at its base and its deltas are in the brief.
- A lane that builds or lands code names the lab-first step (lab, plus `lab-host-a` or `lane-k`). No
  test checks this for a hand-dispatched brief. The building lane runs its own lab proof before
  the PR; the landing lane does not do it for it. If 3a.7 puts the `lab-host-a` lanes out of scope, name
  another lab runtime the lane may use, or state that the change is not runtime-affecting.
- If the lane builds a mechanism with a lease, more than one writer, or a required terminal, the
  brief cites its TLA+ model and design-review verdict (the model-before-build gate), or was
  refused rather than dispatched.
- A brief for a lane that writes `ac_bindings` says the lane proposes and never accepts, and names
  the verifier lane (or Codex) that will accept under `/omni:verify-claims` step 3a (OMN-17427).

In a dry run (`ONEX_DRY_RUN=1` inside a sandbox registry root), write the brief and run the check,
and dispatch nothing.

## Known follow-up

The typed JSONL work ledger (`onex-ledger` in ops_tooling_pkg, plan
`beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in docs_repo) replaces the
markdown ledger. The one append command a brief carries is the `APPEND_CMD` constant in
`scripts/lane_brief.py`, so the writer side of the cutover is a one-line change there. The readers
this skill calls (`inbox.sh`, `catchup.sh` and the step 1 and landing greps) change inside the
reader tasks that plan already owns. The landing lane will then be a typed RULING field read
directly, and the 3a.3 lookup can check that the cited row is a landing ruling instead of leaving
that to the reader of the brief.

## Common rationalizations

Each row is an excuse for writing a brief from memory, with the lane it cost. The rows come from the
night of 2026-10-17 and the FRICTION rows of 2026-10-12 to 2026-10-17. Every one of them was a brief
that a lane ran faithfully and that was wrong before it was sent.

| Excuse | Why it is wrong | What to do instead |
| -- | -- | -- |
| "I know the state, so the premise table can say it is true." | FRICTION 2026-10-12T12:57:38Z lane=labkeys-1d5b: a brief said a host already signed ledger rows and pointed at a mechanism to reuse; neither was true (about 20 lane-minutes). FRICTION 2026-10-12T05:47:11Z lane=process-pickup-1d5b: four tickets were briefed as dropped with no merged fix, and each had a merged pull request. | Mark every premise `verified by: <command> => <observation>` or `UNVERIFIED`, and run the command in section 1 before writing the line. A premise from memory is UNVERIFIED. |
| "The lane can mint the ticket or edit the Linear criterion." | A headless lane on a lab host has no authenticated Linear connector. FRICTION 2026-10-12T07:28:15Z lane=h903-fill-1d5b and 2026-10-15T15:17:21Z lane=omn19174-c10: lanes ended blocked at the mint or the criterion edit, twice on one ticket. | Brief a lab lane to use `node_create_ticket` for the one ticket the brief grants, and to return the exact text of anything else for the orchestrator to file. Mint authority is for exactly one ticket. |
| "The input file is on the host I am on." | The lane runs on whichever host has headroom. FRICTION 2026-10-15T03:49:35Z lane=omn18531-t02 and 2026-10-15T05:42:32Z lane=omn18531-b5: briefs named files held on a lab host the lane never ran on, so each lane ended with a wasted dispatch. | Paste the content into the brief, point at a path in a pushed branch, or cite a ledger row. Name no path that exists on one host only. |
| "The lane will find the script by its description." | FRICTION 2026-10-12T07:49:30Z lane=orchestrator-1d5b: a brief gave the reader's path with a placeholder, and the lane searched the whole disk, holding a host at load 81 to 118 on 12 cores for about 30 minutes. | Write the resolved path, `${OMNI_PLUGIN_ROOT}/skills/...`, and read the file in the premise check. |
| "I will set the variable and add the worktree in one command." | FRICTION 2026-10-12T09:40:53Z lane=friction-report-2026-10-12: the worktree guard could not resolve a path assigned in the same Bash call and refused the command. | Assign the root in one call and use it in the next, from `$registry_root`, never typed from memory. |
| "The lane may read the board with the API, it is one read." | FRICTION 2026-10-13T12:44:32Z lane=omn16632-5a72: the brief's named reader exited 2 because the gh shim refuses a lane's GitHub reads. Lanes read PR state locally. | Name `pr_state_local.py`, `onex scm` reads or a git read on the canonical clone, and nothing that calls GitHub. |
| "A clean brief that the check refuses is the check's fault, so I dispatch anyway." | FRICTION 2026-10-13T03:31:43Z lane=orchestrator-31d9: the check scanned CI files in an unrelated clone beside the registry and refused clean briefs. Skipping the check hides that every later brief fails the same way. | Do not bypass the refusal. Read why it refused, fix the class (the scan's roots) in a lane, and re-run. |
| "The ruling allows it in spirit." | FRICTION 2026-10-16T17:37:18Z lane=private-ci-to-hosted-now: a brief ordered a move that the standing rule forbade, until a ruling amended that rule. | Run the section 1.5 ruling grep and cite the row you rely on. If a row forbids it, the brief asks for the ruling, not the move. |
| "I will leave the open question for the operator in the brief." | The operator had ruled one question three times in one night, and the ledger held all three. Briefs that carry an answered question cost a foreground turn. | Paste the inbox, holds and the newest rulings (section 3a) and answer from them. List only a question no row answers, with the rows you searched. |
| "The brief fixes this one pull request." | One instance fixed leaves the class that blocked it (a no-host lane re-dispatched, a missing repository cloned by hand). | State the class in the task line, brief a fix for the class and give the instance as the proof case. |
| "Handed-off is a good enough end state to ask for." | A handed-off lane leaves the pull request unmerged; "merged" is the only end. A report counting handed-off as done overstates what landed. | Section 4 asks for the PR state the lane read and the hand-off MSG, and the orchestrator counts only merged. |

## Red flags

- A premise with no `verified by:` and no `UNVERIFIED` mark.
- A brief that names a path, a file or a transcript on one host, or a path containing a placeholder.
- A brief that asks a lane to mint, comment on or edit a Linear ticket through a connector the host lacks, or without naming the single ticket it may mint.
- A task whose verb is "fix PR x" with no class named.
- A section 3a part you wrote by hand instead of pasting from the reader.
- A question left open in the brief that a RULING in the last 14 days answers.
- A brief check refusal you answered by dispatching without it.
- A brief that asks the lane to read GitHub, merge, arm or poll CI.

## Known friction (from prior runs)

- **Two dispatchers wrote one fixed scratch name (`brief.md`) and one brief was overwritten mid-assembly,**
  and nothing compared a brief's lane with the lane a launch named (2026-11-01, OMN-21869). Every example now
  writes `<scratch>/<lane>/<lane>-brief.md` and `<lane>-3a.md`; with `LANE_BRIEF_SCRATCH` set, `constraints` and
  `ticket-text` default to that per-lane path when `--out` is omitted. `check --lane <lane>` (and the
  remote-lane runner, before placement, with its `--lane`) refuses a brief whose CLAIM template `lane=` or
  `Lane:` line names another lane, showing both names.

- **Citations by ledger line number went dead when the ledger rolled** at 2026-09-23T14:00:47Z.
  Cite a row by its timestamp and lane. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230
  lineage; shipped by OMN-19387.
- **A brief for a non-product repo carried only the standing block,** which is written for product
  repos. Read the target repo's CLAUDE.md (section 3). Fixed 2026-09-23 by the omni-skill-fixes
  pass, OMN-19230 lineage; shipped by OMN-19387.
- **The lab-first test does not read a hand-written brief** (it globs `ops_tooling_pkg/src/ops_tooling_pkg/handlers/**/*.js`).
  Section 3 says so. Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage; shipped by
  OMN-19387.
- **The step-2 ledger grep read only the live ledger,** and a roll moves rows older than a day into
  the `archive/` rolls, so an older owner or ruling was invisible. Step 1 greps the rolls too.
  Fixed 2026-09-23 by the omni-skill-fixes pass, OMN-19230 lineage; shipped by OMN-19387.
- **The step 1 greps named a fixed ledger path under the registry root,** so a sandbox dry run read
  the real ledger and never saw its fixture rows. They now read `ONEX_LEDGER_PATH` and its sibling
  `archive/`. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A dry-run brief moved the lab proof onto the landing lane** when its OUT OF SCOPE excluded the
  `lab-host-a` lanes. The lab-first check now says the building lane proves its own change and names
  another lab runtime when `lab-host-a` is out of scope. Staged by the orchestration-skills pass,
  OMN-17427 lineage.
- **Standing constraints (holds, the landing ruling, the model tier) did not reach delegated
  lanes,** because a brief summarized them or left them out. Section 3a pastes the readers' output
  and the check refuses a brief without it. Staged by the orchestration-skills pass, OMN-17427
  lineage.
- **The landing check claimed more than it proved.** It accepted any lane that had written any
  RULING and pasted that lane's five newest RULING rows, so a wrong but real lane name produced a
  confident landing sentence. 3a.3 now pastes the one RULING row cited by timestamp and lane, the
  skill states that the helper does not read the ruling's words, and the brief's reader confirms
  the row. A second landing sentence for lanes the landing lane dispatches, which no ruling stated, was removed. Staged by the
  orchestration-skills pass, OMN-17427 lineage.
- **The staged test suite needed a registry root,** so porting it into the plugin repo, whose
  required check runs every skill suite with no `registry_root`, would have turned that check red. The
  suite now runs offline from fixtures and sibling readers, and the registry-only cases run when a
  registry root is set. Staged by the orchestration-skills pass, OMN-17427 lineage.
- **A staged draft of 3a.3 read a committed landing pointer file** through a helper script. The
  operator ruled that landing belongs to the repository drains and that no landing machinery is
  built, so 3a.3 now pastes that lane's RULING rows and the handoff sentence only. Staged by the
  orchestration-skills pass, OMN-17427 lineage.
- **A lab lane was told to mint a ticket and ended blocked at the step.** A headless `claude -p` session on
  a lab host has no authenticated Linear MCP, so the create gate on the MCP save path cannot run: lane
  h903-fill-1d5b ended blocked at its mint step (FRICTION 2026-10-12T07:28:15Z lane=h903-fill-1d5b, the second
  occurrence; first FRICTION 2026-10-08T15:54:15Z lane=redci-bus-triage-1450) and the orchestrator minted
  the ticket and re-placed the lane. `check --lab` and the remote-lane runner now refuse a lab-bound brief that
  grants or asks for a mint; comments and state changes through the host key stay allowed. OMN-21021.
