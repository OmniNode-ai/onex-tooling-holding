---
name: pr-handoff
description: Hand a ready pull request to the landing controller through the rolling ledger, so merged is the only way a PR ends and nobody asks the operator to review code. Confirms the head live, appends one MSG to landing-controller (pr=, head=, needs=land|train|companion), then the lane's own TERMINAL outcome=handed-off, and stops touching the PR. For a PR the orchestrator's own session lane owns (its CLAIM names the PR or the PR's ticket), session-lane mode writes the MSG and a STATUS handed-off=<repo>#<n> instead of a TERMINAL, so the controller's owner read releases the PR and the session CLAIM stays open. No SendMessage, no off-ledger wake-up, no merging, arming, reruns or CI polling. Use when a lane's PR is green locally with lab proof in the body, when a lane is told to "get it merged", and when someone asks why a PR is unmerged or waiting on review.
prosthetic: true
replaces_when: "The typed work ledger (onex-ledger in ops_tooling_pkg) records a handoff as a typed event that the landing lane consumes directly, so no lane has to print and append the two rows by hand."
restored_from: "none. New process, updated for the model-free landing RULING row 2026-09-29T06:34:17Z lane=orchestrator-83 (OMN-19852): the launchd landing controller lands every PR and no repo drain runs"
ticket: OMN-17427
---

# PR handoff (prosthetic)

The launchd landing controller (`ai.omninode.landing-controller`, state under
`~/.local/state/omni/landing/`) sweeps every open PR and lands it with no model in the loop. Under
RULING 2026-09-29T06:34:17Z lane=`orchestrator-83` (ledger line 15743, "take the model out of the
loop") and the repo-drains-84k TERMINAL of 2026-09-29T11:03:50Z (ledger line 16159, "Landing is owned
by the launchd landing controller ... no successor drain by design"), no repo drain runs and a PR is
handed to `landing-controller`, never to `repo-drain-<repo>`. Every other lane writes the code, opens
the PR, pushes its fixes, and then hands the PR over with this skill. The reasons are cost and
ownership: many lanes watching and arming PRs at once exhausted the shared GitHub API quota, and a PR
with two owners gets landed twice or not at all.

A handoff is two ledger rows and nothing else. The MSG is the record: which PR, at which head, needs
what. The TERMINAL is what the controller reads: it closes this lane's CLAIM, and the controller's
ledger read (`landing_ledger.py`, through `drain_map.ledger_owners`) then finds no live owner for the
PR, so the PR is the controller's to arm, land or send to a worker. The controller reads owners
(open CLAIMs not ended by a `handed-off=` row, and MSG routes to live worker lanes, which are a MSG's own
`owns=<repo>#<n>` cell and never a `repo#n` spelled in its text, OMN-22478), HOLD rows and
instruction rows, and merge-order waits. It never reads a MSG to itself as ownership
(`drain_map.LANDING_LANES`), so the handoff MSG cannot make the PR look owned by the controller.
Nobody is woken by a message.

A PR the orchestrator's own session lane owns cannot end that way: a TERMINAL under the session lane
would close the session CLAIM and end the session. Such a PR is handed off in **session-lane mode**
(section 3a): the same MSG, then a STATUS under the session lane carrying `handed-off=<repo>#<n>`,
which the owner map reads as the end of the session's ownership of that one PR. The session CLAIM
stays open and the session keeps working.

This skill never asks the operator to review code. A PR is done when it is merged, not when a
person has looked at it. This skill builds no landing machinery either: who lands, and how, belongs
to the landing lane.

## 0. Dry-run guard and inputs

Run the guard before anything else:

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
: "${registry_root:?set registry_root}" "${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"; echo "ledger=$ONEX_LEDGER_PATH"
```

Exit `2` means stop: a dry run is pointed at the real registry root. In a dry run, `registry_root`
and `ONEX_LEDGER_PATH` point into a sandbox registry root, and the rows below land in the sandbox
ledger. Never point a dry run at the real ledger.

You need these inputs. Shell variables do not survive from one Bash call to the next, so each block
below sets them again at its top: write the values in each time.
- `PR`: `<repo>#<number>`, for example `omnimarket#9002`.
- `LANE`: your own lane name, as your CLAIM row spells it.
- `NEEDS`: one of the three below. "Get it merged" for an ordinary PR is `land`.
- `TO`: the landing recipient, `landing-controller` unless a newer RULING names another (step 3).
- `MODE`: `lane` for a dispatched lane handing off its own PR (the usual case), or `session` when
  `LANE` is the orchestrator's own session lane (section 3a).

`NEEDS` is one of:
- `land`: an ordinary PR, ready to squash-merge.
- `train`: a runtime-affecting PR. The landing lane routes it to the runtime merger.
- `companion`: the PR waits on its change-control companion. This is the one case where a draft
  may be handed off.

## 1. Check your inbox

The step 4 command checks your inbox first, before the live PR read and before any append. When it
prints `BLOCKED inbox`, it lists every action item addressed to your lane (a HOLD or a MSG whose
`to=` names your lane). A HOLD addressed only `to=all` does not block here: step 4's HOLD check reads
it with the landing controller's reader and holds the PR (exit `8`) when it covers the PR. Read them and decide. Answer each with an ACK row of your lane
(`/omni:ledger-write ACK --lane <your lane> --to <sender> --re <its id>`); the block names every item
still lacking one (`ACK needed: <id>`). Then rerun with `--inbox-seen <the newest id it printed>` only when
none stops the handoff. The id names what you read; it clears an item only when your lane's ACK for it is on
the ledger (OMN-21658), so naming the id alone never clears the gate. An action item newer than that id
blocks again. It reads `ONEX_LEDGER_PATH`, so it
reads the same ledger. Never skip the check or replace it with your own grep of the ledger.

A MSG or HOLD addressed to you, or to `to=all`, is binding. If one says to stop, change course or
wait, do that instead of handing off, and answer it with `/omni:ledger-msg` first. A `to=all` MSG
that relays a newer landing RULING is the one input step 3 reads from here.

## 2. Check the PR is ready

The script in step 4 checks these live and refuses the handoff when one fails. Know them before
you run it:
- The PR is open.
- It is not a bot's `chore: release` PR. The landing controller lands it on its own once
  `/omni:release-cut`'s premise (`cut_facts.sh`) reads READY for dev's tip (OMN-20864). The script
  still refuses it for every `NEEDS`, `--session` and `--msg-only` too. Hand off nothing and report
  it as "release PR: the controller owns it".
- It is not a draft, unless `NEEDS=companion`. An unfinished draft is not handed off: finish it.
- Its title carries exactly one OMN id, and its body cites that id (extra, genuinely related ticket
  ids in the body — an epic, an upstream or a companion ticket — are fine; a body citing no ticket
  id at all, or citing only other ids, is still refused).
- It has a lab line: host, lane, command and what you observed (rule 24). A PR with no lab proof is
  not ready. The line is in the body (put there at creation, never added by a later edit) or in a PR
  comment written by the PR's author or by the PR write node under its own login (OMN-20913; a bot's
  release, pin or lock PR has no author who can comment, so `onex scm pr-comment` posts its proof; the
  logins are those `write_identity.comment_author_logins` declares in node_github_repo_write_effect's
  contract and those `comment_author_logins` declares in that node's private deployment overlay
  (`node_github_repo_write_effect/overlay.yaml` under a root of `ONEX_SKILL_OVERLAY_ROOTS`, else
  ops_tooling_pkg's `config/onex/overlays`; the lane write login is a person's account name, so it
  lives there and in no public repository, OMN-17427), both read by `handoff_row.sh` and
  `handoff.sh`; a source that declares none leaves the author alone): a line starting `Lab:` that carries `head=<sha>` naming the
  live head (7 to 40 hex characters, a prefix of the live head). A comment that names another head
  does not count: post a new one. A refusal tells you to comment, never to edit the body: a body
  edit cancels the in-flight `pull_request` producer runs, and a rerun replays the pre-edit body.
  One PR needs no lab line (operator ruling 2026-10-04T10:11:35Z, OMN-20523): a bot's version-only
  bump. When the body has no lab line and the author is a bot, read the PR through
  `onex scm pr-view OWNER/REPO#N` and its diff in the canonical clone; exempt it when it has 1 to 8 files and each changes only
  a version: `pyproject.toml`, `plugin.json` or `marketplace.json` version lines, a `uv.lock` version
  line directly below the repo's own package name, or a `CHANGELOG.md` that adds a release heading and
  removes no text. A human author, any other file, a failed read or a ninth file leaves the lab-line
  rule in force. The exemption is named on stderr and in the MSG text, and the result line below ends
  ` lab=exempt:version-bump`.
  A second PR needs no lab line (operator ruling 2026-10-12T22:05:22Z, OMN-20864: "for pin bump PR, as long
  as the tests pass ... that can be evidence enough"): a bot's pin or lock refresh. When the body has no lab
  line and the author is a bot, every changed file (1 to 8, plain modified files) is a version-only change
  as above or matches a path pattern in `lab_exempt_paths.json` (lock files: `uv.lock`, `poetry.lock`,
  `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, at the root or nested), and the PR
  watcher reads every required check green at the exact head (`ci.sha` is the head, `ci.verdict` is GREEN,
  no red or pending context): the green CI is the evidence. A red, pending or unread check, any other file
  in the diff (source, a workflow, `pyproject.toml` beyond its version line), or a human author leaves the
  lab-line rule in force. The patterns live in that file, never in the script; widening them is a new
  ruling and an edit there. The landing controller applies no lab-line rule, so the file has one reader.
  The exemption is named on stderr (`lab-exempt=pin-refresh`) and in the MSG text, and the result line ends
  ` lab=exempt:pin-refresh`.
  A third PR needs no lab line (operator ruling 2026-10-14T03:57:46Z, OMN-20730, item 4 answered "yes"): a
  tests-only, comment-only or docs-only PR, whoever the author is (every lane commits as one person). When the
  body has no lab line, every changed file (1 to 30, plain added or modified files) is a docs file
  (`docs/*.md`, `.rst`, `.txt`, a README), a test file (under a `tests` directory, or named `test_*.py`,
  `*_test.py` or `conftest.py`), or a modified file whose changed lines are all blank or whole-line comments
  in a language `lab_exempt_paths.json` declares a comment prefix for, and the PR watcher reads every
  required check green at the exact head: the green CI is the evidence, as for a pin refresh. A line that is
  a tool directive (`noqa`, `type:`, `pragma` and the other markers declared there), a shebang, a docstring, a
  trailing comment after code, a SKILL.md, CLAUDE.md or AGENTS.md (files agents follow), a removed or renamed
  file, a source file that is new, a red, pending or unread check, or a thirty-first file leaves the
  lab-line rule in force. The declaration is the `low_risk` section of `lab_exempt_paths.json`, never the
  script. The files are read for every lab-less body, so the read is no longer a bot's alone; a failed read
  leaves the rule in force. The "heavy gates" half of the ruling is each repository's own docs-only skip tier
  in CI and is not touched here. The exemption is named on stderr (`lab-exempt=low-risk`) and in the MSG text,
  and the result line ends ` lab=exempt:low-risk`.
  A fourth PR needs no lab line (operator ruling 2026-10-21T21:14:58Z, OMN-17427: "start sending backlog tickets to
  the cloud I mean they can use mocks right CI will catch issues"): a small-code PR whose head a lane with cloud
  placement built. `handoff.sh` reads the placement from the handing-off lane's own CLAIM `host=` cell and from the
  remote-lane runner receipts of cloud lanes (a CLAIM with `host=cloud:`) whose result names the PR at the live
  head, and passes it to `handoff_row.sh`. When the body has no lab line, the placement names a `cloud:` host for the
  live head, the PR is handed off with `--needs land`, its repository is not excluded, it changes 1 to 40 files and
  none is a runtime-affecting file (a deploy, a migration, a CI workflow, a container or a service unit), and the PR
  watcher reads every required check green at the exact head, the green CI is the evidence. A lab or unknown
  placement, a red, pending or unread check, `needs=train` or `companion`, or a runtime-affecting file leaves the
  lab-line rule in force, with the reason on stderr (`cloud-ci not granted: ...`). The rules are the `cloud_ci`
  section of `lab_exempt_paths.json`, never the script. The other three kinds are judged first. The exemption is
  named on stderr (`lab-exempt=cloud-ci`) and in the MSG text, and the result line ends ` lab=exempt:cloud-ci`.
  A cloud-built PR writes no `Lab:` line about a host it never ran on.
- A PR that changes what runs on a host also names the installed revision (operator 2026-10-31, OMN-21815: "If we don't
  actually test it before we merge it and it doesn't work, then we have to create another PR and wait for another
  merge"). When a changed file is a host install, a launchd or systemd unit, a tool, a hook or a plugin (the
  `host_install` section of `lab_exempt_paths.json`: its `paths`, and the repository's own `repo_paths`; tests, docs and
  `contracts/` never count, and neither does a `prod_paths` file, so prod and anything that needs a grant are out of this
  rule), tests passed is not the proof. The Lab line (a body line, or a comment of the author or the write node that names
  the live head) or a STATUS row of the handing-off lane or ticket carries `installed=<host>:<revision>`, the revision a
  prefix of the live head or a commit that has the live head as an ancestor, and `observed=<what ran>`: the unit's next
  tick, the tool's next call, the hook firing. An observation that is only that tests passed, that is too short, or that
  names no run (`observed_words`) is refused, as is a revision that is neither the live head nor a descendant of it. A
  Mac plugin install is a merge commit built on the current install (so no other lane's installed fix is dropped), so
  it can never equal a PR head; the head's code is what runs when `git merge-base --is-ancestor <live head>
  <revision>` exits 0, read in the repository's canonical clone (`$registry_root/<repo>`; for ops_tooling_pkg `OPS_TOOLING_PKG_PATH`, else the
  sibling `$registry_root/../ops_tooling_pkg`, and for the overlay home `OVERLAYS_PATH`, else the sibling
  `$registry_root/../overlays`; the same clone the changed-files read uses, and a clone that is not a directory is refused by its
  path; the install path keeps the merge under `refs/tags/adopt-merged/`). A revision that does not contain the live head (including one that holds
  only an older head of the PR) is refused as `does not contain it`; a revision or head the clone cannot read, or no
  clone, is refused as `UNREAD`, never passed (OMN-17427). The proof is read first from the body and the ledger; the changed files are
  read only when it is missing, and the comments only for a PR that does change what runs on a host. A read that fails is
  exit 5. An exempt kind above (version bump, pin refresh, low-risk, cloud-ci) is judged first and needs no install
  proof; a missing or empty `host_install` declaration requires nothing. The node `install-proof` read of
  `node_pr_handoff_reads_effect` decides it, with the verdict functions in `node_pr_handoff_lab_exempt_compute`.
  Install the branch revision through the declared installer on the lab first (the omni plugin:
  `adopt_merged.py install-tree --branch <b>`; a host unit: `onex-host-install`), never a hand edit; every brief's 3a.11 Install first part
  (`/omni:lane-brief`) says the same to a dispatched lane. The result line adds `install-first
  installed=<host>:<revision> source=<body|comment|status>` on stderr, ending ` contains-head=<head>` when the revision is a
  descendant of the head and not the head itself.
- Its head, as the PR watcher last read it (at most one tick old), is the head you pushed. Pass `--expect-head` with `git rev-parse HEAD` from your
  worktree when you have one.
- It is green where you can see it without polling: your local lint, format, type and focused
  tests passed before the push.

A CLAIM of your own lane must name the PR (`pr=` or the `<repo>#<n>` reference in its text) or
carry its ticket in `ticket=`. A STATUS row of your own lane that names the PR (`pr=`, `prs=` or a
`<repo>#<n>` token in its text: the push you recorded, or the sweep plan listing it) counts the same way
(OMN-17427), so a triage lane whose CLAIM names only its carrier ticket records each PR it takes in a STATUS
row and then hands it off; the lane still needs one CLAIM, and a MSG, a FRICTION row or another lane's
STATUS holds nothing. A `no-claim` refusal names the one row that fixes it (a STATUS of your lane with a
`pr=<repo>#<n>` cell, through `/omni:ledger-write`); a hand-written MSG to the landing lane in its place carries
no `pr=` or `head=` cell, so the controller cannot read it. Those are the ways the landing lane's owner map ties a PR to your
lane before the handoff, so the handoff is what unties it. In session-lane mode that CLAIM is the
session CLAIM (section 3a).

A remote lane that mints a child ticket and titles its PR with it holds a CLAIM under the brief's carrier
ticket only. It runs `onex_remote_lane.py child-claim --child <OMN-n>` right after the mint (remote-lane
skill): that writes `ticket=<child> | parent_ticket=<carrier>` into its ledger copy and its relay outbox.
`handoff.sh` counts such a child CLAIM only when the carrier is the ticket of another CLAIM of the lane and
the child's live Linear parent is that carrier (`LINEAR_API_KEY`); a wrong parent refuses `no-claim` (exit 3)
and a parent it cannot read refuses `live-read` (exit 5), so a lane cannot claim an arbitrary ticket
(OMN-20845).

## 3. Name the landing lane

The recipient is `landing-controller`, the same for every repository: landing runs with no model in
the loop, and there is one landing target. No routing RULING is read or checked (OMN-20864, operator
2026-10-28: a gate that costs more friction than it helps is turned off; the old check refused real
handoffs and each refusal sent a lane to a hand-written MSG that skipped every other check).
`--to`, `--ruling-lane` and `--ruling-ts` are still accepted and ignored, so an older command line
keeps working; do not pass them.

- `HANDOFF` printed: the MSG to `landing-controller` is written and the handoff is done.
- If your own lane is the landing lane, this skill is not for you.

## 3a. Session-lane mode (the orchestrator's own PR)

Use `MODE=session` when the PR is owned by the orchestrator's session lane, the lane
`way-of-working` step 3 named, rather than by a dispatched lane. That is the case whenever the
session CLAIM names the PR or carries the PR's ticket, as it does for a PR on the session's goal
ticket. The session hands the PR off and keeps working; its CLAIM stays open.

The landing lane's owner map (`merge-drain`'s `drain_map.py`) ties a PR to an open CLAIM of a live
lane that names it, by the PR reference, `pr=`, a ticket, the branch or the worktree. A STATUS or
TERMINAL row of that same lane, written after the CLAIM and carrying `handed-off=<repo>#<n>`, unties
that one PR from every earlier CLAIM of the lane, whichever way it matched. Session-lane mode writes
exactly that STATUS:

1. Run the Ledger block with `MODE=session` and `LANE=<session lane>`. It keeps both gates of lane
   mode: the RULING grep for `TO`, and a CLAIM of the session lane that names the PR or carries its
   ticket.
2. It appends two rows, in order: the MSG from the session lane to the landing lane, then a STATUS
   under the session lane with `handed-off=<repo>#<n>`, the head and the MSG id. There is never a
   TERMINAL under the session lane: the session TERMINAL is written once, at the end of the
   session, by `way-of-working` section 6.
3. The controller escalates a real red it cannot land (its `ticks.jsonl` degraded list), and `way-of-working`
   section 3 reads the session lane's inbox and that list every turn. A new head after a fix is handed off again the same
   way: one new MSG and one new STATUS.

The session's handed-off PRs are its `handed-off=` STATUS rows.

**Never a question for the operator.** A refusal from the block names its fix, and the session
applies it and runs the block again. No PR waits on an operator's choice of how to hand it off.
If no CLAIM of the session lane names the PR or its ticket, the PR is not the session's own: its
owning lane hands it off in lane mode, or, when that lane has stopped, `session-resume` does.

## Ledger (step 4)

This is the only place this skill writes to the ledger, and it is one command:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/handoff.sh" <repo>#<number> <your lane> --needs <land|train|companion> --mode <lane|session> --delegation "<cells>" [--expect-head <sha>] [--ticket <OMN-n>] [--inbox-seen <id>] [--worktree <path>]... [--keep-worktree]
```

It checks the inbox (step 1) and the lane's CLAIM, reads the PR once
through `handoff_row.sh`, then appends the MSG and the TERMINAL (in session-lane mode, the session
STATUS) in that order, stopping at the first refusal, so the closing row is never written without
its MSG. It never sends a `SendMessage` wake-up. `HANDOFF <repo>#<n> head=<sha7> to=<lane> id=<msg id>
closed=<row> worktree=<cell|none> ledger=<ts> detail=<file>` (then ` lab=exempt:version-bump`, ` lab=exempt:pin-refresh`, ` lab=exempt:low-risk` or ` lab=exempt:cloud-ci` for an exempt PR, preceded by one `EXEMPT lab line: ...` line) is the whole result; everything else is in the detail file.
`NOT-READY`, `REFUSED` and `BLOCKED inbox` each print the fix on the next line. `--help` prints the
full contract.

**A PR under an active HOLD is held, not handed off (OMN-17427).** After the CLAIM gate,
`handoff.sh` reads the HOLD rows in force that cover the PR with the landing controller's own
reader (`drain_map.hold_findings`: repo and PR scope, `until=`, RELEASE rows, the fixer and surface
carve-outs). If one covers it the command prints `HOLD-ACTIVE <repo>#<n>: ...` and, per hold,
`HOLD id=<id> who=<lane> since=<ts> released-by=<condition> src=<file:line> reason=<words>`, writes no
MSG (the controller would hold the PR and never land it), and closes with a held row: the TERMINAL
carries `outcome=held | hold=<id>` (session mode: a STATUS with `held=<repo>#<n>`; `--msg-only`: no
row). The last line is `HELD <repo>#<n> head=<sha7> hold=<id> closed=<row> ...` and the exit is `8`.
Report the PR as held in the lane result, never as handed off, and do not lift or work around the
HOLD: only the operator or the HOLD's own release condition ends it.

**A held PR is a draft (OMN-17427, operator RULING 2026-10-16T03:58:15Z: a PR is held only if it is a
draft or a grant).** A HOLD on a PR that stays ready
holds nothing: the landing controller enqueues and merges it (plugin-tooling-pkg#1092 carried a HOLD with an
unmet `after=`, stayed ready and merged at 2026-10-21T12:46:14Z, which took bus lab runs down). So the held
close converts the PR to draft through `onex scm pr-edit --draft` (node_pr_hold_draft_effect), prints
`DRAFTED <repo>#<n>: ...` before the `HELD` line, writes `drafted=<repo>#<n>` into the closing row and ends the
`HELD` line with `drafted=<repo>#<n>`. A draft PR under an active HOLD is closed as held as well, not refused as
NOT-READY. When no HOLD covers a PR any more, a handoff of a PR that a held close drafted (a ledger row carrying
`drafted=<repo>#<n>`) marks it ready through `onex scm pr-ready` first and prints `READIED <repo>#<n> head=<sha>: ...`;
a RELEASE row marks it ready too, once no other HOLD covers it. The ledger writer refuses a `pr=` HOLD on a PR that
is open and not a draft (`/omni:ledger-msg`).

The exact-prefix RULING gate and CLAIM gate are the step 3 and step 2 checks, enforced here rather than left to prose, and
they run in both modes. Exit `3` from the block means one of them failed and nothing was written:
no RULING names `TO` (stop and report it), or no CLAIM of `LANE` names the PR or carries its ticket
(a TERMINAL with no CLAIM would be an orphan). The RULING gate and the no-CLAIM-at-all gate run
before the one GitHub read; the PR-or-ticket gate runs after it, because the ticket comes from the
live title.

When the PR watcher has not seen the PR yet, or its copy is stale, `handoff_row.sh` makes ONE live read through
the bus gateway (`onex scm pr-view --source bus --bus-lane dev`, never `gh`) and judges that record exactly as it
judges a watcher record; the answer is cached for 120 seconds (`PR_HANDOFF_LIVE_TTL_S`) under
`$registry_root/.claude_scratch/pr-handoff-live`, so a retry reads nothing again. The same read answers a watcher
record still at the head you replaced, in place of the wait for the next tick. A read that fails falls to the
blocking wait for the watcher below, then exit `5` (`live-read`). The live record carries no CI read, so the bot pin-refresh exemption does not
apply to it. `PR_HANDOFF_LIVE_READ_COMMAND` and `PR_HANDOFF_LIVE_BUS_LANE` replace the command and the lane.

Exit codes of the command: `3` a gate refused, nothing written; `4` NOT-READY from `handoff_row.sh`,
the reason on stderr (fix it per step 2, push, and run the block again); `5` the read failed: the PR watcher state is stale or has not seen the PR or its newest push yet. The command
already blocked once for it (`pr_state_local.py --wait-until seen`, then `--wait-until head=<sha>` with
`--expect-head`, up to `PR_HANDOFF_HEAD_WAIT_S`, 330 s by default, returning on the watcher rewrite that shows
it), so run it once more at most, or end the lane: a remote lane's runner retries a refused handoff from the
launching host. Never loop `sleep` around it (OMN-17427); it never falls back to GitHub, and you never guess the head; `6` an unread inbox action item blocked it; `8` an active HOLD row covers the PR, so it was held and not handed off (the held close was written); `64` a usage error. `handoff_row.sh --help` prints the full
contract.

- Add `--expect-head <sha>` when you have a worktree.
- Pass `--ticket <OMN-n>` when the PR's title and head branch carry no OMN id (for example a
  public knowledge-base PR whose sanitize gate forbids naming an internal ticket): its ticket
  resolves only through `--ticket`; `handoff.sh` forwards it to `handoff_row.sh`, and the MSG row
  carries `source=ticket-flag`.
- **Lane closeout (OMN-17427, OMN-20148).** Once every gate above has passed, and only when a
  TERMINAL is written (lane mode, no `--msg-only`), the handoff closes out the lane's own tree: the
  PR branch is on origin, so the tree is not needed after the handoff. `closeout_cell.sh` takes the
  path the lane's own CLAIM named in `worktree=` (its newest CLAIM on the PR's ticket, else its
  newest CLAIM; `--worktree` only when the CLAIM named none), and, when that tree's HEAD is the PR's
  live head, runs ops_tooling_pkg's `onex-lane-closeout --lane <lane> --worktree <path>` from
  `$registry_root`: archive and verify, then `git worktree remove --force`. The TERMINAL carries the
  ledger's disposition cell for that same path: `worktree=pinned-removed:<path>@<archive>`,
  `worktree=removed:<path>` (already gone) or `worktree=kept:<path>:<reason>` (`head-differs-from-pr`,
  `removal-not-authorized`, `process-inside`, `mid-operation`, `not-a-worktree`, `asked-to-keep`, an
  archive that did not verify). A CLAIM that named no tree (`worktree=none`) adds no cell. The
  ledger refuses a TERMINAL with no cell when its CLAIM named a path, and refuses `removed` or
  `pinned-removed` while the path exists. A closeout never fails a handoff: every refusal is a `kept:`
  cell and the handoff lands. It runs after the gates, so a refused handoff removes nothing. A
  `kept:` tree is left to the triage timers. `--keep-worktree` skips it
  (`worktree=kept:<path>:asked-to-keep`), for a lane that will push to the same tree again; use it,
  or `--msg-only`, when more PRs from the same tree follow. Run the handoff from outside the tree
  (a shell whose working directory is not the worktree; never `cd`): a shell whose working directory is the tree is a process inside it, and keeps
  it. The pin restores the tree: `worktree-triage` documents how.
- **`--delegation "<cells>"` (OMN-17427):** required in every mode but `--mode session` and
  `--msg-only`, since those never print a TERMINAL. Pass one of `delegated=<n> runs=<ids>`
  (`codex=`/`jev=`/`lab=`/`glm=`/`lab_agent=` accepted alongside `runs=`), `delegated=0
  delegation_reason=<reason>` (one of `no-text-or-code`, `route-refused:<status>`, `route-unavailable:<run id>`, `read-only-lane`), or `delegation=na:<reason>` (`<reason>` is 2 to 41 characters of `[a-z0-9-]`, starting with a letter or digit, no spaces; `-`, `none`, `n/a` and `x` are placeholders and refused) — the same accounting `/omni:ledger-write`
  takes on any other TERMINAL. The TERMINAL row is checked against the ledger grammar before the MSG is appended (OMN-21674), so a reason past the limit refuses with nothing written. Before you pass cells that name receipts (`runs=`, `codex=`, `lab_agent=`, `jev=`),
  dispose of each answer (OMN-20011): `python3 "${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/delegation_step.py"
  --omni-home "$registry_root" dispose --receipt <path> --disposition used|edited|discarded|ignored
  --reason-code <code>` (a direct `onex delegate` call with no receipt: `--lane <lane> --run <run id>`; a used
  or edited answer adds `--artifact pr:<owner/repo#n>`, an edited one `--final-file <the text you used>`; each
  disposition is published as one bus event, OMN-20012), then
  take the cells from `delegation_step.py cells`, which refuses while any receipt is undisposed. The ledger
  grammar refuses the TERMINAL for the same reason (OMN-20015). Without it, `handoff_row.sh` (step 4) refuses before printing
  either row, exit `64`, so nothing is appended: neither the MSG nor a TERMINAL the ledger's
  grammar would refuse on its own. That refusal-after-the-MSG-landed shape was the bug
  (ops_tooling_pkg#36/#37 added the grammar's delegation-cell requirement; this flag is the
  writer-side fix, since the MSG carries no such requirement and used to land alone).
- Friction: write the FRICTION row first with `/omni:friction-record`. Without `--friction`, the
  script reads the lane's FRICTION rows since its CLAIM (the first CLAIM after its last TERMINAL)
  and the TERMINAL carries `friction=FRICTION <ts>` for each; with none, `friction=none`. Pass
  `--friction "<one line>"` to cite the row in your own words. `--friction none` beside such a row
  refuses (exit `3`), since it would be false. `onex-ledger` refuses a TERMINAL that cites friction
  with no FRICTION row for the lane.
- Exit `65` from `onex-ledger` is a grammar or lint refusal. Read the stderr line, fix the
  cause, and run the block again. Never edit the ledger by hand and never bypass the lint.
  `/omni:ledger-write` has the full exit table.
- Read back: both appends exited `0`, and `$L` now holds your MSG (`to=` the landing lane,
  `head=` the live sha) and, after it, your TERMINAL `outcome=handed-off`, or in session-lane mode
  the session STATUS `handed-off=<repo>#<n>`. Peers append too, so look for your own `id=`, not
  for the last two lines. In session-lane mode the session CLAIM has no TERMINAL.
- **Several PRs from one lane:** run the script with `--msg-only` for every PR but the last, so
  the lane writes one TERMINAL. Each PR still gets its own MSG. Session-lane mode has no
  `--msg-only`: each PR's own STATUS is what releases it, so each handoff writes its own two rows.

Row shapes, for reading them back (the script writes them; never hand-write one):

```
<ts> | MSG | from=<lane> | to=<landing lane> | id=<ts>-<lane> | ticket=OMN-n | repo=<repo> | pr=<repo>#<n> | head=<sha> | needs=<land|train|companion> | Handoff from <lane>: ...
<ts> | TERMINAL | lane=<lane> | ticket=OMN-n | outcome=handed-off | repo=<repo> | pr=<repo>#<n> | head=<sha> | handed_to=<landing lane> | msg=<MSG id> | friction=<none|line> | ... | worktree=<cell> | Handed <repo>#<n> to <landing lane> by MSG; ...
```

In session-lane mode `<lane>` is the session lane and the STATUS takes the TERMINAL's place:

```
<ts> | STATUS | lane=<session lane> | ticket=OMN-n | handed-off=<repo>#<n> | repo=<repo> | head=<sha> | handed_to=<landing lane> | msg=<MSG id> | ...
```

The MSG text is plain on purpose. It carries no instruction words about merging, so the landing
lane's hold check never reads a handoff as a hold.

## From a lab host (OMN-20281)

A remote lane whose host writes the ledger through the bus (`ONEX_LEDGER_WRITE_VIA=bus`) runs `handoff.sh`
unchanged. Its gates read the lane's own copy of the ledger, which holds the lane's CLAIM (the runner mirrors
it) and every row the lane wrote through the bus, and the MSG and the TERMINAL are appended to the canonical
ledger by the one append command, MSG first. The runner sees that TERMINAL closes the lane's CLAIM and
writes no second one. Use `--msg-only` when the lane keeps working and the launching host should still
write the TERMINAL from the lane's final message. If the bus append returns exit `75` (no receipt), the MSG's
outcome is unknown: read the ledger for its `req=` cell before running the handoff again, because a second
run would hand the PR off twice.

The runner mirrors its CLAIM from the launching host's bus outbox when the bus queued it, and a lane whose
ledger copy cannot get its CLAIM is not started (OMN-20864). After the lane ends, the detached runner retries
a `no-claim` handoff refusal from the launching host while the CLAIM is on its way to the live ledger,
without needing a `wait` caller.

The row's writer is the host's broker login, attested by the per-principal writer topic ACL; no credential
is handed to a lane. `ONEX_LEDGER_RELAY_OUTBOX` (set by the runner for every lane) is the broker-down fallback.
If the bus cannot be opened (exit `69`, broker down or no login) and this append wrote no `OK` line,
`handoff.sh` queues all rows there and ends its result line with `relay=queued:bus-unavailable`; the launching
host appends them when the lane ends. A refused row or unknown outcome (`65`, `70`, `75`) is never queued,
and neither is a partial append: queuing could append a row twice. A queued handoff is landed; do not hand-relay it.

A remote lane on a host with no bus runs `handoff.sh` unchanged too. Its gates read the lane's copy of the
ledger, which holds the CLAIM the runner mirrored in, and with `ONEX_LEDGER_RELAY_OUTBOX` set the script queues the
MSG and the closing row in that file and ends its result line with `relay=queued`. The launching host appends
them when the lane ends, MSG first, and writes no second TERMINAL when the queued one landed.

## Over the bus (OMN-20636)

A lab host's copy of the PR watcher state is taken when the lane launches, so a lane that opens its own
PR is refused `5` by step 2 on every retry (FRICTION 2026-10-05T14:01:01Z). With `--via bus` (or
`ONEX_PR_HANDOFF_VIA=bus`) and `ONEX_PR_HANDOFF_BUS_COMMAND` set to the argv prefix of
`onex work-ledger handoff --bus-lane <lane> --omnibase-path <root>`, the script runs the inbox,
CLAIM and friction gates as before, reads the PR's title, body and comments once
(`onex scm pr-view OWNER/REPO#N`), and publishes one handoff request instead of deciding. `node_pr_handoff_orchestrator`
(omnimarket) decides on the PR watcher's live observations: a PR the watcher has not seen yet, a push it
has not observed yet and a draft are waits, not refusals, and it re-decides on every observation of the
PR until the request's wait budget (default one hour) runs out. When ready it appends the same MSG and
closing row through the ledger's bus append; nothing is appended by the lane. Pass `--expect-head` with
the full sha you pushed. The result is one of `HANDOFF` (already handed off), `HANDOFF-ACCEPTED`
(accepted; stop touching the PR, the orchestrator writes the rows), `NOT-READY <error_code>: <detail>`
(exit 4, nothing appended) or `HANDOFF-PENDING` (exit 7: published, no answer in 30 s; the request stays
on the bus; tell your parent). A bot's version-only bump or pin or lock refresh is not exempted in this mode (the exemption needs the changed files): use `--via local`. The worktree is always kept in bus mode, because readiness is decided after the script ends; the remote-lane runner's host closeout removes it when the lane ends. A lab comment counts only from the PR's author or the write node's declared login (OMN-20913), and only when one of its `head=` cells names the head you pushed.
The contracts, the golden chain and each error chain are in omnimarket `tests/chains/pr_handoff`.

## 5. Stop

**Push, hand off, exit; the controller lands, the PR watcher reports CI results.** The PR watcher (the launchd agent `ai.omninode.pr-watcher` in ops_tooling_pkg, every 120 s) reads each open PR's CI once per tick, and the landing controller arms a green PR and dispatches a worker for a red one on its own. Nobody polls the head, this lane included.

After the TERMINAL (in session-lane mode, the session STATUS), this lane stops touching the PR.
You never merge it, never arm auto-merge, never rerun CI, never update its branch, never poll or watch its checks, never remove a hold label
and never open or chase its change-control companion. You never SendMessage the landing lane: the
MSG row is the whole handoff. Your one terminal report to the orchestrator, per the lane rules,
names the PR, the head and `handed off to <landing lane>`.

If the controller escalates your PR (its `ticks.jsonl` degraded list under
`~/.local/state/omni/landing/`, with a reason such as `escalation_exhausted`), that is your signal to
fix the PR, not to arm or merge it. The orchestrator's inbox loop dispatches a fix lane through
`fan-out`. That lane pushes the fix and runs this skill again with the new head: one new MSG per new
head.

## 6. A red that is not yours

When the controller escalates a red that your change did not cause, it is not fixed inside your PR.
It becomes its own minimal fix PR, on its own ticket, from a new lane dispatched through
`fan-out`, and that PR is handed off the same way. Your PR waits for it at the landing lane.

## Routes to

- `/omni:ledger-msg`: the inbox check, the MSG shape, and answering a MSG.
- `/omni:ledger-write`: the append contract and `onex-ledger` exit codes.
- `/omni:lane-brief`: the Constraints block that carries the newest RULING rows.
- `/omni:friction-record`: before a TERMINAL that cites friction.
- `/omni:ledger-catchup` and `/omni:session-resume`: after a restart, before handing off again.
- ops_tooling_pkg `lane_rules/lane-rules-block.md`: the standing rules every brief carries.

## Known follow-up

The typed work ledger (`onex-ledger` in `ops_tooling_pkg`, plan
`beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in docs_repo) replaces the
`onex_ledger.py --append` line in the Ledger section. That is a one-line change, because the skill
appends in that one place and `handoff_row.sh` only prints rows.

## Known friction

- **A lab-pool lease HOLD addressed to all blocked every unrelated handoff.** The landing controller
  writes a `to=all` surface HOLD for each lab-pool lease (`landing-lab-<repo>-L<n>` lanes), and the
  inbox gate counted it as an action item, so plugin-tooling-pkg#1135 was refused with exit `6` on a
  `surface=101-runtime` lease HOLD, and ops_tooling_pkg#970 on a `surface=landing-controller-install`
  one, neither of which covered the PR. The gate now blocks only on a MSG or a HOLD whose `to=` names
  the lane; a `to=all` HOLD is left to the PR HOLD check, which still holds a PR it covers. →
  FRICTION 2026-10-22T01:01:21Z lane=ruling-mechanisms-0020 (OMN-17427)

- **A bot's release PR was accepted for `needs=land` and never landed.** The script read no author, so
  omnibase_core#1844 (`chore: release`, a bot) was handed off and the lane was told the controller
  would land it, while the controller gates that PR for the release train; it sat about 3.5h. The
  script now reads the author and refuses it, naming `/omni:release-cut`. → FRICTION 2026-10-02T08:46:21Z lane=qdiag-core-floor-1844, omnibase_core#1844, OMN-20342

- **The lab-line refusal sent lanes to edit the PR body.** `handoff_row.sh` accepted a lab line only
  in the body, so a lane that pushed without one edited the body afterwards. That edit is an
  `edited` event: it cancels in-flight `pull_request` runs of every workflow whose concurrency group
  is `<workflow>-<pr number>` with `cancel-in-progress` on (Receipt Gate, Reject skip-gate bypass
  tokens), and a rerun replays the event it reruns, so a red `ci.yml` (which has no `edited`
  trigger) never sees the new body. The ready check now also reads the lab line from a comment of
  the PR's author that names the live head, and the refusal points at that comment. Measured on
  omnimarket#3223 and omnibase_infra#4456 (OMN-17427).
- **The skill routed every PR to a repo drain that no longer ran.** `repo-drain-<repo>` was the
  default recipient and the 2026-09-25 per-repository RULING its authority, so after the drains were
  retired (repo-drains-84k TERMINAL, ledger 16159) every handoff wrote a MSG nobody read, and a MSG
  to a lane the controller sees as live would have made the controller skip the PR as owned. The
  default is now `landing-controller` under RULING 2026-09-29T06:34:17Z, and `drain_map` never reads
  a MSG to the controller as an owner. → OMN-19852, orchestrator-83 handoff 2026-09-29 section 5 item 5

- **A TERMINAL said friction=none beside the lane's own FRICTION row.** The script defaulted
  `--friction` to `none`, so a lane that recorded friction and ran the block without the flag wrote
  a false answer. The default is now the lane's FRICTION rows since its CLAIM, and an explicit
  `none` beside one refuses. → FRICTION 2026-09-27T08:23:36Z lane=claim-guard-align-83 (OMN-19846)
- **PR handoff took 3 tool calls.** It is now one command, `handoff.sh`, which prints one result line and writes the rest to a detail file. → RULING 2026-09-26T14:03:27Z lane=orchestrator-83 (OMN-17427)

- **The landing lane's name is a constant here.** If the landing lane is relaunched under a new
  name, handoffs go to the old name until the constant in `handoff.sh` is changed (`--to` is ignored since
  OMN-20864). Recorded
  2026-09-24 in the staging build.
- **A dry run can inherit the real `registry_root`.** An `env` block in the user's Claude settings
  overrides the value a test launches with, so the Bash tool sees the real registry root and the
  step 0 guard refuses (correctly, writing nothing). Launch the dry run with
  `--settings '{"env":{"registry_root":"<sandbox>","ONEX_LEDGER_PATH":"<sandbox ledger>"}}'`.
  Recorded 2026-09-24 in the staging build.
- **The session's own PR could not be handed off.** The first session-lane mode moved the PR to a
  per-PR child lane and refused a session CLAIM that named the PR. In the 2026-09-24 integration run
  the session CLAIM named its goal PR, the block exited `3`, and the session asked the operator to
  choose a way out, twice. Built as specified, it still failed: the owner map matched the live
  session CLAIM to the goal PR by its ticket, so the child lane's TERMINAL released nothing. Session
  mode now writes a `handed-off=<repo>#<n>` STATUS under the session lane, which the owner map in
  the same release reads as the end of that CLAIM's ownership of the PR however it matched; the
  gate accepts a session CLAIM that names the PR or its ticket; and a refusal names its fix rather
  than a question. `merge-drain` and this skill ship together: an owner map that predates the
  `handed-off=` reader keeps a goal-ticket PR owned until the session TERMINAL. Recorded 2026-09-24
  in the staging build.
- **The inbox script belongs to `ledger-msg`.** A plugin without that skill beside this one (the
  staging build) falls back to invoking `/omni:ledger-msg`, which costs one extra skill load.
  Recorded 2026-09-24 in the staging build.
- **A correct public-KB PR could never be handed off.** `handoff_row.sh` refused every PR whose
  title carried no OMN id, but the public `knowledge_base` repo's sanitize-text CI (its
  `sanitization_patterns.py`) fails any title, body or commit naming an internal ticket, so no
  public-KB PR could ever carry one. `knowledge-base#93` was landed by hand-authoring the ledger
  rows instead of using this skill. `handoff_row.sh` now falls back to `--ticket`, then to exactly
  one OMN id in the head branch name, when the title carries none, and records the source
  (`title`/`branch`/`ticket-flag`) in the MSG row; it still refuses when no ticket is found
  anywhere. FRICTION 2026-09-27T02:16:32Z lane=dispatch-port-plan-pr-83 (OMN-19843).
- **A host fix was handed off at tests passed and "installs after merge".** The lab-line rule accepted a Lab line that
  said only that tests passed for a PR that changes a unit, a tool, a hook or a plugin, so a fix that did not work
  after the merge cost another PR and another merge. The check above refuses it unless the installed revision and the
  observed run are named. → OMN-21815, operator 2026-10-31T17:2xZ
