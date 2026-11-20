---
name: session-resume
description: Resume an orchestration session after a restart, a crash or a usage-limit outage. Find every CLAIM the outage left dangling (live ledger and archive rolls, the reconciler's 7-day window), decide per lane from live state whether its work landed, check the inbox, hand a stopped lane's ready PR to the landing lane through pr-handoff's readiness-gated MSG and close only that dead CLAIM, notify the landing lane of a stopped landing sub-lane, relaunch the rest with read-back-before-act and a supersedes-claim pointer, and check that every PR the dangling CLAIMs named ends with one owner. Never merges, arms, reruns or polls CI. Dry-run safe under ONEX_DRY_RUN (report-only reconciler, only this session's STATUS appended, to a sandbox ledger). Runs as step 4 of way-of-working, after preflight and the session CLAIM; a session that opens this skill first loads way-of-working and starts at its step 1. Also use mid-session when lanes stop reporting at once.
prosthetic: true
replaces_when: "The ledger-reconcile workflow runs at session start with a threshold measured from the outage time rather than a 6h floor, and hands each dangling lane to a relaunch step that carries a supersedes-claim pointer, on two consecutive resumes with no dangling CLAIM found by hand. As of 2026-09-23 the workflow wrapper still coerces a zero threshold to 6h (../ops_tooling_pkg/src/ops_tooling_pkg/handlers/ledger_reconcile/ledger-reconcile.js, Number(args.staleHours) || 6)."
restored_from: "omniclaude e7ec45412 plugins/onex/skills/crash_recovery/SKILL.md (orientation only; that skill listed pipeline state files, this one reconciles the ledger)"
ticket: OMN-19221
---

# Session resume (prosthetic)

A restart or usage limit kills **every** background lane at once, and none of them writes a
TERMINAL. Until you reconcile, the ledger shows their CLAIMs as live scope, so nobody touches that
work and nobody finishes it. This skill uses the rolling-ledger process every lane uses: it reads
through the existing readers, writes rows only through `onex-ledger` in the `## Ledger` section,
and routes to the sibling skills instead of re-implementing them.

**Where this runs.** This skill is step 4 of `/omni:way-of-working`, which first runs preflight,
names the session lane and appends the session CLAIM that step 2's positive control looks for. If
this skill was opened first (a fresh session told "limits reset"), stop here, invoke
`/omni:way-of-working` and start at its step 1; it calls this skill back. Mid-session, when lanes
stop reporting at once, run it directly: the session CLAIM already exists.

Run `/omni:ledger-catchup` first for the bounded digest (holds in force, rulings, unanswered MSGs).
This skill then answers the one question the digest does not: which lanes died, and what happens to
their work.

**Landing is not this skill's job.** One drain per repository lands PRs. Under RULING
2026-09-25T14:34:28Z lane=`merge-drain-83`, the target for a PR in `<repo>` is
`repo-drain-<repo>`. Confirm the routing model in the catchup digest's RULING section; if a newer
RULING changes it, apply the newer target rule wherever the blocks below say `<landing lane>`. This
skill never merges, arms, disarms, reruns, updates a branch or polls CI, and it composes no handoff
of its own: a dead lane's ready PR reaches the landing lane through `/omni:pr-handoff`'s script, with
that skill's readiness gates, and a relaunched lane hands its own PR over with `/omni:pr-handoff`.

## 0. Setup, at the top of every Bash call that runs a step

Shell variables do not survive between Bash tool calls, so every block below starts with this:

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
```

**Dry run.** With `ONEX_DRY_RUN` set, `registry_root` must be a sandbox registry root (it holds
`.dryrun-sandbox`, copies of the ledger scripts, and a scratch ledger that `ONEX_LEDGER_PATH` names).
In a dry run:

- only this session's own STATUS row is appended, to the sandbox ledger, through the same
  `onex-ledger`. Every row that acts for another lane (a TERMINAL closing a dead lane's CLAIM, a
  handoff or notice MSG) is composed and printed, never appended (the `## Ledger` block does this);
- the reconciler runs `--report`, never `--apply` (step 3a);
- the only GitHub reads are `gh pr view` of the PRs the dangling CLAIMs name; there is no search
  and no org-wide inventory in any mode (step 5);
- briefs are written to files and never dispatched;
- the step 3c per-lane reads run in this session, because a dry run dispatches no lane.

Never suppress stderr in any step (rule 16). An empty result gets a positive control before it is
reported.

## 1. Fix the outage time

Name the moment the lanes died: the restart time, or the usage-limit time. Take it from the last
rows any lane wrote (`tail -40 "$L"`), from a pre-restart handoff row addressed `to=next-session`,
and from the operator's message. Call it `T0`, a full UTC stamp such as `2026-09-23T14:52:23Z`.

## 2. List every dangling CLAIM, live ledger plus archive rolls

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
python3 "${CLAUDE_SKILL_DIR}/scripts/dangling_claims.py" --ledger "$L" --since "<T0 minus a few hours>" --t0 "<T0>"
```

`${CLAUDE_SKILL_DIR}` is filled in by the harness with this skill's directory. The script is
read-only. It reads `"$L"` and every `"$(dirname "$L")"/archive/ROLLING_WORK_LEDGER_*.md` roll,
parses rows with the committed grammar module (`src/ops_tooling_pkg/ledger/ledger_grammar.py`,
`parse_row` and `Row.token`), and prints one line per CLAIM that no later row closes:

`claim_stamp lane state last_row source ticket repo pr worktree parent consent`

A CLAIM is closed by a later TERMINAL that names it in `closes-CLAIM=`, by a later TERMINAL naming
no claim whose `claim-lane=` (or, without one, whose `lane=`) is the claim's lane, by a later CLAIM whose
`supersedes-claim=` names it, or by a RELEASE whose `re=` names it. Every CLAIM of a lane is judged,
not only its latest. A reference names a claim by its LCT1 claim token (matched by the row digest
`onex-ledger` minted it from, never by the append time at its end), by its claim id
`<stamp>-<lane>` (the form this skill writes), or by a bare stamp. Two lanes often CLAIM in the same
second, because a fan-out starts them together, so a bare stamp binds only the claim of the
closer's `claim-lane=`, then its `lane=`, then the lane a `-r` relaunch replaces, then a shared
ticket. When that still leaves two claims, the script binds neither and prints an `AMBIGUOUS` line
on stderr, so a closer for one sibling never hides the other. Read both rows by hand, and treat
each as dangling until step 3 decides it from live state. An `UNRESOLVED token` line on stderr is a
token whose CLAIM is not in a canonical row; the reconciler (step 3a) reads the other shapes.

`--since` defaults to 7 days, the reconciler's window; widen it when the outage followed a quiet
stretch, and never describe the result as "at any age". `consent` is the dead CLAIM's `consent=`
citation, which step 4 carries into the relaunch.

**Positive control.** Your own session's CLAIM must appear as `ACTIVE`. If it does not, look for it
first: `grep -F "lane=<your lane> " "$L" | grep -F "| CLAIM |"`. No such row means the session never
wrote its CLAIM: stop, invoke `/omni:way-of-working` and start at its step 1, which writes it. A row
that is there but missing from the list means the reader is broken or pointed at the wrong file:
stop and report, and do not act on the list.

`state` is `QUIET` when the lane wrote no row at or after `T0`, and `ACTIVE` otherwise. A lane
counts as dead when it is `QUIET` and its PR and branch show no activity after `T0`. `ListAgents`
cannot see a peer session's lanes, so it is not the liveness test. Do not declare a lane dead in a
message: the lane-liveness guard refuses it. The finding goes in the `## Ledger` STATUS row.

The landing lane's own CLAIM and heartbeat rows, and its sub-lanes' CLAIMs (`parent=` the landing
lane), are not yours to judge or close: the landing lane is a separate, parallel workflow. Step 3
sends it one notice for a `QUIET` sub-lane. If the landing lane itself is `QUIET`, report it in the
STATUS row and to the operator; never relaunch the landing lane or its sub-lanes from here.

The script skips rows in the older bar-led and heading shapes and counts them in its summary line.
The reconciler (step 3a) reads those shapes, and is the cross-check.

**2b. The session's own background work, from process state (OMN-20603).** A dangling CLAIM is not
the only thing an outage stops: a driver workflow runs per-cycle agents and holds no session-level
CLAIM, so step 2 cannot see it. Run the lane liveness read, which `/omni:session-start`'s hook also
runs on every prompt:

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
python3 "${CLAUDE_SKILL_DIR}/../session-start/scripts/loops_check.py" liveness read --session-lane "<your lane>" --ledger "$L" \
  [--session "<the Claude session id of the session that stopped>"]
```

It reads every Workflow run the named sessions started (the current session, each `--session`, and
each earlier session the hook recorded for the lane), every lane in the session's `lanes.txt`, and
every open CLAIM with `parent=<your lane>`, and omnimarket's `node_lane_liveness_compute` decides
each one: `LIVE`, `FINISHED`, `DEAD` with its `RESUME` action, or `UNKNOWN` when a read failed. A
`DEAD` workflow is resumed by its action (a run of this session by `Workflow resumeFromRunId`, an
earlier session's run by a fresh `Workflow scriptPath`, since a run id resumes only in its own
session) and gets one STATUS row from the `status-row` command its line prints, appended in the
`## Ledger` block. A `DEAD` remote lane goes through step 3's table like any dangling CLAIM, and is
relaunched by step 4. An `UNKNOWN` is read by hand, never resumed on a guess.

## 3. Decide each dangling lane from live state

**3a. The reconciler.** Run it directly, never through the workflow wrapper (which coerces a zero
threshold to 6h). Its report exits 1 when dangling rows exist; that is a result, not an error.

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
S="<your session scratch dir>"; mkdir -p "$S"
if [ -n "${ONEX_DRY_RUN:-}" ]; then
  python3 "$registry_root/scripts/ledger_reconcile.py" --report --stale-hours 0.01 --since-days 7
else
  # live-lanes.txt: every lane step 2 printed as ACTIVE, one per line, plus the landing lane
  python3 "$registry_root/scripts/ledger_reconcile.py" --apply --stale-hours 0.01 --since-days 7 --live-lanes "$S/live-lanes.txt" --max-appends 20
fi
echo "rc=$?"
```

The reconciler resolves the ledger from its own location (`$registry_root/scripts/..`), so in a
sandbox it reads the sandbox copy and prints `REPORT mode`. Under `ONEX_DRY_RUN` it is **never**
called with `--apply`. A claim that the reconciler and step 2 disagree on is a disagreement to read
(the reconciler's row for it, and the ledger rows themselves), not a result. One known source: the
reconciler binds a bare-stamp reference to every same-second claim that shares the closer's ticket,
where step 2 binds none. When the reconciler calls such a claim closed and step 2 lists it, keep it
on the list and decide it in 3c from live state.

**3b. Check your inbox before you write anything on another lane's behalf.** This is
`/omni:ledger-msg` section 4, the same check `/omni:pr-handoff` step 1 makes before a handoff:

```bash
: "${registry_root:?set registry_root to the registry root}"
export ONEX_LEDGER_PATH="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
IB="${CLAUDE_SKILL_DIR}/../ledger-msg/inbox.sh"
if [ -f "$IB" ]; then bash "$IB" "<your lane>"; else echo "inbox.sh is not beside this skill: invoke /omni:ledger-msg and run its section 4"; fi
```

When the block prints `inbox.sh is not beside this skill`, your next tool call is the Skill tool
with `omni:ledger-msg`, and you run its section 4 for your lane. Never skip the check and never
replace it with your own grep. A MSG or HOLD addressed to you or to `to=all` is binding: if one says
to stop, wait or leave a lane or PR alone, do that, and answer it through `/omni:ledger-msg` before
going on. Run the check again immediately before the `## Ledger` block if more than a few minutes
have passed.

**3c. Per lane, live reads** (read-only; in a dry run the sandbox's fake `gh` serves `pr view`):
`gh pr view <n> --repo OmniNode-ai/<r> --json state,mergedAt,mergeCommit,headRefOid,isDraft`, the
worktree's `git -C <wt> status --porcelain` and `git -C <wt> log origin/<base>..HEAD`, and the
ticket state. Read one PR at a time; never a search.

For a PR that is open and whose work looks finished, run `/omni:pr-handoff`'s own readiness check.
It is read-only (one `gh pr view`), prints the MSG it would send, and appends nothing:

```bash
: "${registry_root:?set registry_root to the registry root}"
HR="${CLAUDE_SKILL_DIR}/../pr-handoff/scripts/handoff_row.sh"
bash "$HR" "<r#n>" "<land|train|companion>" "<your lane>" --to "<landing lane>" --expect-head "<headRefOid read in 3c>" --msg-only; echo "rc=$?"
```

Exit `0` means ready: the printed row is a preview only. Exit `4` is NOT-READY, with the reason on
stderr: a draft, a title or body that does not cite exactly one OMN id, a body with no lab line, or
a head that moved. Exit `5` is a failed read: report it, never guess. `needs=` follows
`/omni:pr-handoff`: `land` for an ordinary PR, `train` for a runtime-affecting PR, `companion` for a
PR waiting on its change-control companion.

Take the first row of this table that matches:

| Live state | Verdict | Action |
| -- | -- | -- |
| its PR merged | `landed` | the reconciler's `--apply` closes it. If it does not (and always in a dry run), the `## Ledger` block adds the closing TERMINAL, part (a) |
| the lane is the landing lane, or its CLAIM's `parent=` is the landing lane (a landing sub-lane) | `landing-notified` | never relaunch it and never close its CLAIM: the landing lane owns its own sub-lanes. The `## Ledger` block sends the landing lane one notice MSG, part (c). If the landing lane itself is `QUIET`, send nothing: report it in the STATUS row and to the operator |
| its PR is open, the work is finished (the worktree is clean with nothing unpushed, or no worktree is recorded), and the readiness check exits `0` | `handed-off` | the `## Ledger` block hands the PR to the landing lane with `handoff_row.sh` and closes the dead CLAIM, part (b) |
| its PR is open but the readiness check exits `4` | `relaunch` | relaunch (step 4). Put the NOT-READY reason in the brief; the relaunched lane fixes it and hands off with `/omni:pr-handoff` |
| work half-done (a draft PR, a dirty worktree, unpushed commits) | `relaunch` | relaunch (step 4). The relaunched lane finishes and hands off with `/omni:pr-handoff` |
| nothing started | `relaunch` or `released` | relaunch. Use `released` only when the operator said the work is no longer wanted: the `## Ledger` block closes the CLAIM with `outcome=released`, part (d) |

The head is always the one you read live, never the old brief's. A PR that has auto-merge enabled is
still decided by this table: every change to a PR's merge state belongs to the landing lane, so this
skill neither arms nor disarms anything, and the landing lane's own hold check covers any HOLD
scoped to the PR.

## 4. Relaunch with read-back-before-act

Name the new lane `<old>-r` (then `-r2` and so on). Compose its CLAIM template:

```bash
: "${registry_root:?set registry_root to the registry root}"
python3 "${CLAUDE_SKILL_DIR}/scripts/relaunch_claim.py" --dead-lane "<old>" --dead-claim "<old CLAIM stamp>" \
  --dead-parent "<its parent column from step 2>" --consent "<its consent column from step 2>" \
  --landing-lane "<landing lane>" --dispatcher "<your lane>" \
  --ticket "<its ticket>" --t0 "<T0>" --repo "<r>" --pr "<r#n>" --worktree "<wt>" --claim-only
```

With `--claim-only`, stdout is the one CLAIM line and nothing else, and the `ROUTE=` line goes to
stderr. That one line is what `way-of-working` step 4 passes to `session.py relaunch-brief
--claim-template`, which refuses a value with more than one CLAIM line. The script is read-only. The relaunched CLAIM carries `parent=<your lane>` (the resuming lane, as
`/omni:lane-brief` sets it) and `supersedes-claim=<old CLAIM stamp>-<old lane>`, the claim id, which
stays unique when a sibling claimed in the same second (never a bare stamp, and never a line number,
which a roll invalidates). It carries the old CLAIM's `consent=` citation when step 2's `consent`
column shows one (a `-` means none), so a consent-bound relaunch still cites its OPERATOR-CONSENT
row. It is checked against the committed grammar before it is printed. When the dead lane is the landing lane or one of its
sub-lanes, the script prints `ROUTE=landing-lane` and exits 3: go back to step 3, whose verdict for
it is `landing-notified`. Composing needs `registry_root` (for the grammar module) and exits 2 without
it.

Write the brief with `/omni:lane-brief`, pasting this template as its CLAIM template line. The brief
opens with: "You are resuming a lane killed at T0. Before any write, re-read the PR head, the
worktree and the ledger rows of the old lane, and report what you found." It also says: "When your
PR is ready, hand it to the landing lane with /omni:pr-handoff and stop; never merge, arm, rerun or
poll CI." The relaunched lane never replays the old brief's steps blindly: the PR may have moved.
Lint the written brief before dispatch; exit 0 is required:

```bash
: "${registry_root:?set registry_root to the registry root}"
python3 "${CLAUDE_SKILL_DIR}/scripts/relaunch_claim.py" --dead-lane "<old>" --dead-claim "<old CLAIM stamp>" \
  --dead-parent "<its parent>" --consent "<its consent column>" --landing-lane "<landing lane>" \
  --dispatcher "<your lane>" --lint-brief "<brief file>"
```

The lint fails a brief whose CLAIM template drops the carried `consent=`.

Dispatch the linted briefs through `/omni:fan-out`. In a dry run, the brief stays a file and is
never dispatched.

## 5. Every named PR has one owner, then new work

Close the loop on the PRs the dangling CLAIMs named, and on nothing wider:

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
python3 "${CLAUDE_SKILL_DIR}/scripts/dangling_claims.py" --ledger "$L" --since "<T0 minus a few hours>" --prs
```

Each PR it prints must have exactly one outcome from steps 3 and 4: `landed` (merged), `handed-off`
(pr-handoff's MSG to the landing lane, and the dead CLAIM closed), `landing-notified` (still owned by
the landing lane's own sub-lane CLAIM), or owned by one relaunched lane (its CLAIM template carries
`pr=`). A
PR with none, or with two, is fixed before any new work. A `pr=` cell holding a bare number is
joined to `repo=` only when `repo=` names one repository; any other bare number is printed to
stderr as `AMBIGUOUS`, and you resolve it by hand from the CLAIM.

This skill never builds an org-wide owner map. Every open PR in the org already has an owner: the
landing lane, whose own inventory picks up any PR whose lane has closed its CLAIM. Only then take
new work, through `/omni:fan-out`.

## Ledger

This is the one place this skill appends. It routes to the existing writers instead of composing
their rows: the handoff MSG comes from `/omni:pr-handoff`'s `handoff_row.sh` (with its readiness
gates), the notice MSG follows `/omni:ledger-msg` section 2, and `close_claim_row.py` composes only
the TERMINAL that closes a dead lane's CLAIM. That TERMINAL is written under the dead lane
(`lane=<dead lane>`), with your lane as `closed-by=` and `closes-CLAIM=<stamp>-<lane>`, the claim id,
so every reader that closes by `lane=` (the landing lane's owner map included) closes the dead lane
and never your own session CLAIM. Compose the rows inside this block, never in an earlier call, because each carries the
time it was printed. Repeat a part once per lane it applies to, and leave out the parts no lane
needs. The `sleep 1` before each MSG keeps two MSG ids from this lane out of the same second. The
loop appends in order and stops at the first refusal.

**Dry run.** Under `ONEX_DRY_RUN` the loop appends only this session's own STATUS row, to the
sandbox ledger (the setup guard makes sure it is one). Every other row acts for another lane, so the
loop prints it as `DRY-RUN not appended:` and appends nothing for it. The printed rows are the
result a reviewer checks. This is the same rule as `/omni:way-of-working` section 0.

```bash
: "${registry_root:?set registry_root to the registry root}"
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
ME="<your lane>"; TO="<landing lane>"
HR="${CLAUDE_SKILL_DIR}/../pr-handoff/scripts/handoff_row.sh"
CR="${CLAUDE_SKILL_DIR}/scripts/close_claim_row.py"
ROWS=()
# (a) landed: one per landed claim the reconciler did not close
T="$(python3 "$CR" --lane "$ME" --dead-lane "<dead lane>" --dead-claim "<its CLAIM stamp>" --landed --ticket "<its ticket>" --pr "<r#n>" --squash "<merge sha read live>")" && ROWS+=("$T") || echo "NOT COMPOSED (a): read the stderr line above"
# (b) handed-off: pr-handoff's MSG, then the TERMINAL closing the dead CLAIM; both or neither
sleep 1
M="$(bash "$HR" "<r#n>" "<land|train|companion>" "$ME" --to "$TO" --expect-head "<head read in 3c>" --msg-only)" && T="$(python3 "$CR" --lane "$ME" --dead-lane "<dead lane>" --dead-claim "<its CLAIM stamp>" --after-msg "$M")" && ROWS+=("$M" "$T") || echo "NOT COMPOSED (b): read the stderr line above; the verdict becomes relaunch"
# (c) landing-notified: one notice MSG, /omni:ledger-msg section 2 shape (one stamp for row and id)
sleep 1; TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROWS+=("$TS | MSG | from=$ME | to=$TO | id=$TS-$ME | ticket=<its ticket> | repo=<r> | pr=<r#n> | Resume notice from $ME: lane <dead lane> wrote no row after <T0>; its CLAIM <its CLAIM stamp> is still open and is yours to close or carry on")
# (d) released: only on the operator's word that the work is no longer wanted
T="$(python3 "$CR" --lane "$ME" --dead-lane "<dead lane>" --dead-claim "<its CLAIM stamp>" --released --ticket "<its ticket>" --reason "<one line: the ruling that dropped it>")" && ROWS+=("$T") || echo "NOT COMPOSED (d): read the stderr line above"
# (e) resumed from the step 2b read: one per workflow resumed, the STATUS row its DEAD line names
T="$(python3 "${CLAUDE_SKILL_DIR}/../session-start/scripts/loops_check.py" liveness status-row --session-lane "$ME" --lane "<workflow name>" --kind workflow --ref "<run id>")" && ROWS+=("$T") || echo "NOT COMPOSED (e): read the stderr line above"
# this session's own row, last
OWN="$(date -u +%Y-%m-%dT%H:%M:%SZ) | STATUS | lane=$ME | T0=<outage time> | dangling=<lane:verdict,...> | relaunched=<new lanes, or none> | dry_run=<0|1> | <one line of what was decided>"
ROWS+=("$OWN")
for ROW in "${ROWS[@]}"; do [ -n "$ROW" ] || continue
  if [ -n "${ONEX_DRY_RUN:-}" ] && [ "$ROW" != "$OWN" ]; then echo "DRY-RUN not appended: $ROW"; continue; fi
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --append "$ROW" || { echo "REFUSED at: $ROW"; break; }
done
```

A part that prints `NOT COMPOSED` added no row. Read its stderr line, correct that lane's verdict
in the STATUS row (a refused handoff is `relaunch`), and never append a STATUS that reports a
handoff whose MSG is not on the ledger.

- The verdicts in `dangling=` are the step 3 ones: `landed`, `handed-off`, `landing-notified`,
  `relaunch`, `released`, or `alive` for a lane you found still working.
- `/omni:ledger-write` is the grammar reference; read it live with `onex_ledger.py "$L" --print-grammar`.
- **Exit 65 is a lint refusal: fix the row and append again.** Never bypass it, never hand-edit the
  ledger, never retype a row under a legacy type. Exit 75 is a lock timeout; a retry is safe.
- Read back: `grep -F "<your lane>" "$L" | tail` shows your rows in order. Peers append too, so
  look for your own `id=` and stamps, not for the last lines.
- Record the outage with `/omni:friction-record` if it cost more than a few minutes.
- The relaunched lanes write their own CLAIMs from the step 4 template. This skill never claims on
  a lane's behalf.

**Known follow-up: the typed ledger.** When the rolling ledger moves to the typed JSONL ledger
(`onex-ledger` in ops_tooling_pkg, plan `beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md`
in docs_repo), the append line above is the one writer line that changes. The step 2
reader (`dangling_claims.py`), `close_claim_row.py` and the reconciler change inside the readers
that plan already owns, and the handoff MSG changes with `/omni:pr-handoff`.

## Guardrails

- Never take over a lane that is still alive. Read its last row time and its PR and branch activity
  first.
- Never answer "what is the state" from the pre-outage handoff table. Read live.
- The foreground does not run the per-lane verification reads. Send them to a read-only background
  lane. A dry run is the one exception: it dispatches nothing, so it reads inline.
- Never merge, arm, disarm, rerun, update a branch or poll CI. A PR goes to the landing lane by one
  MSG; the landing lane does the rest.
- Never compose a handoff MSG yourself. It comes from `/omni:pr-handoff`'s `handoff_row.sh`, whose
  readiness gates (one OMN id, a lab line, a live head) apply to a dead lane's PR exactly as to a
  live lane's. A PR that fails them is relaunched, not handed off.
- Check the inbox (step 3b) before writing any row on another lane's behalf.
- Never relaunch the landing lane or one of its sub-lanes, never close a sub-lane's CLAIM, and never
  name the landing lane as a relaunched lane's `parent=`.
- Never run `ledger_reconcile.py --apply`, a GitHub search, a dispatch or any GitHub mutation under
  `ONEX_DRY_RUN`.

## Known friction (from prior runs)

- **Closing a dead lane closed the session, for the landing lane.** The closing TERMINAL was
  written as `lane=<resuming lane> | claim-lane=<dead lane>`. The step 2 reader bound it by
  `closes-CLAIM=`, but the landing lane's owner map closes by `lane=`, so the live session CLAIM, and
  every PR it owned, left the owner map the moment the session closed any dead lane (the 2026-09-24
  integration run: three open CLAIMs became one). `close_claim_row.py` now writes the row under the
  dead lane (`lane=<dead lane> | closed-by=<your lane>`), and a `claim-lane=` row already on the
  ledger is read as acting for that lane by both readers. Staging build, OMN-17427.
- **A resume relaunched only lanes with dangling CLAIMs** and missed the two driver workflows that
  kept merges moving, which hold no CLAIM, for about four hours. Step 2b reads every run the session
  started from the harness's record. → FRICTION 2026-10-11T19:11:42Z lane=orchestrator-8e80, OMN-20603
- **The restart near 18:50Z on 2026-09-22 left four CLAIMs dangling,** found by hand and relaunched
  as -r and -r2. → FRICTION 2026-09-23T00:57:51Z lane=friction-to-skills item=F6
- **The usage limit near 22:29Z on 2026-09-22 killed lanes mid-task.** One lane was presumed dead and
  superseded, another resumed by reading back first, which was correct. → FRICTION
  2026-09-23T00:57:52Z lane=friction-to-skills item=F16
- **The reconciler's 6h floor hides a fresh death,** and the workflow wrapper coerces a zero
  threshold to 6h. Call the script directly with `--stale-hours` (step 3a). → FRICTION
  2026-09-23T01:01:05Z lane=friction-to-skills; OMN-17573
- **A dangling CLAIM with a wrong scope misleads the next lane.** Re-derive scope from live state,
  not from the dead lane's files. → FRICTION 2026-09-22T13:00:10Z lane=dod-closeout-enumerate-verify-1305
- **Orphaned PRs appear after an outage,** because the dead lanes' PRs have no owner. Step 3 hands
  each finished one to the landing lane and step 5 checks that every named PR has one owner. →
  FRICTION 2026-09-23T00:57:51Z lane=friction-to-skills item=F1
- **The liveness guard refuses a message that declares a lane dead.** Put that fact in a ledger row,
  in neutral words ("wrote no row after T0"). → FRICTION 2026-09-23T00:58:03Z lane=friction-to-skills item=F17
- **The step 2 awk compared an unanchored first field, paired claims by lane only, kept each lane's
  latest CLAIM, and was rewritten whenever the skill was invoked with arguments.** Step 2 now runs
  `dangling_claims.py`, which parses with the committed grammar module, judges every CLAIM, honours
  `closes-CLAIM=`, `supersedes-claim=` and `RELEASE re=`, and reads the archive rolls. → FRICTION
  2026-09-23T14:54:18Z lane=omn17427-foreground, OMN-19257, OMN-19268
- **A resume under a dry run was not isolated:** step 3 ran the reconciler with `--apply` and step 5
  ran an org-wide owner map (a GitHub search), whatever the environment. Step 3a now branches on
  `ONEX_DRY_RUN`, step 5 reads only the PRs the dangling CLAIMs name in every mode, and the setup
  guard refuses a dry run outside a sandbox registry root. Fixed 2026-09-24 in the
  orchestration-skills pass, OMN-17427.
- **A dry run in a fresh `claude -p` process got the real `registry_root`,** because the Bash tool
  sources the shell profile on every call and a profile env file can re-export it. The setup guard
  refused the run, which is its job. To dry-run in a sandbox, put the sandbox exports in a file and
  pass it as `CLAUDE_ENV_FILE`, which is sourced after the profile. Measured 2026-09-24 in the
  orchestration-skills pass, OMN-17427.
- **Resumed sessions used to disarm armed PRs and relaunch landing work themselves.** Under the
  repo-drain routing ruling every change to a PR's merge state belongs to that repository drain, so a
  resume now sends one MSG instead, and relaunches only non-landing work with `parent=<resuming
  lane>`. Changed 2026-09-24 in the orchestration-skills pass, OMN-17427.
- **A resume composed its own copy of the handoff MSG and skipped `/omni:pr-handoff`'s readiness
  gates,** so a dead lane's PR with no lab line could reach the landing lane as `needs=land`. It also
  wrote rows on other lanes' behalf with no inbox check first, and closed landing sub-lanes' CLAIMs.
  The MSG now comes from `handoff_row.sh --msg-only`, the inbox check is step 3b, this skill composes
  only the closing TERMINAL (`close_claim_row.py`), and a landing sub-lane gets a notice instead.
  Fixed 2026-09-24 in the orchestration-skills pass, OMN-17427.
- **`supersedes-claim=` was written as a line number,** which a roll invalidates. It is now the
  dead claim's token or claim id. Fixed 2026-09-23, OMN-19230 lineage.
- **Same-second CLAIMs hid a dead sibling.** The step 2 reader matched a close reference to any
  claim whose stamp it ended with, whatever its lane. A fan-out starts lanes in the same second (the
  live ledger held 28 same-second CLAIM pairs in one week), so a TERMINAL or relaunch for one lane
  closed its twin too, and the twin dropped out of steps 2 and 5. It also compared a claim token's
  trailing append time to the claim stamp, so a CLAIM closed by its token still read as dangling.
  The reader now binds tokens by row digest, binds a bare stamp by lane and ticket and never across
  two candidates, and this skill writes the `<stamp>-<lane>` claim id. Fixed 2026-09-24 in the
  orchestration-skills pass, OMN-17427.
- **A relaunch dropped its `consent=`.** Step 2 printed no consent column and step 4 passed none, so
  a consent-bound lane came back without its citation. Step 2 prints it, step 4 carries it, and the
  brief lint fails without it. Fixed 2026-09-24, OMN-17427.
- **A dry run appended rows for other lanes,** where `/omni:way-of-working` says a dry run appends
  only the session's own rows. The `## Ledger` loop now prints those rows and appends only the
  STATUS. Fixed 2026-09-24, OMN-17427.
