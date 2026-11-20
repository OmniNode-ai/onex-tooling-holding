---
name: verify-claims
description: "Check a lane's report against live state before anyone relays it. Split the report into typed claims (PR merged or open, handoff MSG sent, file on branch, ticket state, ledger row, no hold in force at merge, delegation receipt), check each one live as VERIFIED, FALSIFIED or UNVERIFIED, record the verdict as a STATUS countersign, write a CORRECTION when a TERMINAL was false, and kick the lane back with a MSG row. The run itself follows the ledger lifecycle: it opens a CLAIM only when none covers it, records friction through friction-record, and closes its own CLAIM with a TERMINAL. Only verified claims reach the operator, each named in words. Use when a lane or workflow reports, before a status report cites work as done, and before a ticket goes to Done."
prosthetic: true
replaces_when: "A lane's claims are typed events in the typed work ledger (onex-ledger in ops_tooling_pkg) and /onex:verified_dispatch checks each one against live state and writes the countersign itself, so no orchestrator runs this by hand, for two consecutive weeks with no false done relayed."
restored_from: "none. New process, from the orchestration-skills catalog (skill 3), built on the rolling-ledger process the lanes already use"
ticket: OMN-17427
---

# Verify claims (prosthetic)

A lane's report is a self-report. Lanes have reported PRs as merged that were open, files as
written that never reached the branch, handoffs that were never sent, and delegations that left
no receipt. Relayed as written, each of those reaches the operator as fact, and the next decision
is built on it. This skill reads every claim from its live source first. What the live source
confirms is relayed as done. What it contradicts is corrected on the ledger and sent back to the
lane. What cannot be checked is relayed as unverified, with the reason.

A merge claim is checked two ways: that the PR merged at the head claimed, and that no hold
covered it at the moment it merged. The second check is merge-drain's own hold check, replayed to
the merge time, so a merge through a hold is caught even when the merge itself is real. Who
landed a PR is not checked here: the landing lane owns all landing.

## 0. Dry-run guard and setup

Shell state does not persist between Bash calls. Put these lines at the top of every Bash call
in this skill, with the three values filled in:

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
export registry_root="${registry_root:?set registry_root}"
export ONEX_LEDGER_PATH="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
REPORTING_LANE=<the lane whose report you are checking>
MY_LANE=<your own lane, the one whose open CLAIM covers this work>
WORK=<your session scratchpad>/verify-claims-<the reporting lane>
mkdir -p "$WORK"
```

**Never read the ledger by hand in this skill.** No `grep`, `tail`, `cat`, `awk` or `sed` on
the ledger or its `archive/`, at any step, for any reason. Every ledger read this skill needs is
made by a command below: the inbox through `/omni:ledger-msg`'s own `inbox.sh` (step 1), and the
lane's rows, handoff MSGs and holds through the step 3 script. If you need a ledger fact no
command here gives you, run `/omni:ledger-catchup`.

`MY_LANE` must have an open CLAIM, because every row this skill writes is written as that lane.
Ask the script, never the ledger:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" --lane-state "$MY_LANE"
echo "lane-state rc=$?"
```

- rc `0` (`open-claim <ts>`): a CLAIM already covers this run, usually the orchestrator session's
  own. Open nothing. That lane's own TERMINAL closes it, not this skill (step 6).
- rc `1` (`no-open-claim`): open a CLAIM now, before any other write. The script prints the row
  into `$WORK/rows.txt` and the Ledger block appends it. The ticket is the one the report is about.
  The rules block's read-before-cite applies to it outside a dry run.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" --lifecycle claim --verifier-lane "$MY_LANE" \
  --ticket <OMN-n the report is about> --actor <who runs this, e.g. claude:opus5:foreground> \
  --est 0.3 --displaces "<what this check displaces>" --about "$REPORTING_LANE" > "$WORK/rows.txt"
echo "claim row rc=$?"
```

Then run the Ledger block. Once it reads back `VERIFIED`, mark that this skill opened the CLAIM,
so step 6 closes it: `touch "$WORK/opened-claim"`.

- rc `2`: the ledger could not be read. Fix `ONEX_LEDGER_PATH` and rerun. Never start without a
  CLAIM.

In a dry run, `registry_root` and `ONEX_LEDGER_PATH` point into a sandbox registry root, and the
rows in the Ledger section land in the sandbox's scratch copy of the ledger. Never point a dry
run at the real ledger.

Prerequisites: `gh` and `jq` on PATH. The script uses four helpers and copies none of them:
merge-drain's `drain_map.py` in this plugin (the hold check), `/omni:ledger-msg`'s `inbox.sh`
beside it (the inbox check; the canonical clone's copy under `$registry_root/plugin-tooling-pkg` when
this plugin has no ledger-msg), the row grammar at
`$registry_root/../ops_tooling_pkg/src/ops_tooling_pkg/ledger/ledger_grammar.py` (the handoff check), and
`src/ops_tooling_pkg/delegation_receipt_check.py` in the ops_tooling_pkg clone (`OPS_TOOLING_PKG_PATH`, else `$registry_root/../ops_tooling_pkg`; the delegation check).

## 1. Check your inbox

This is the `/omni:ledger-msg` inbox check (section 4 there), run as written. The script runs that
skill's own `inbox.sh` for `MY_LANE`; it copies none of it. Run it after the setup lines:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" --inbox "$MY_LANE"
echo "inbox rc=$?"
```

- rc `0`: the inbox was read. Each line printed above the count line is an open MSG (no ACK) or
  HOLD (no RELEASE) addressed to you or to `to=all`, and it is binding. It may already say the lane
  was relaunched, or that the report is superseded. `0 open item(s)` means nothing is waiting.
- rc `2` (`inbox unavailable`): `inbox.sh` was not found or failed. Invoke the Skill tool with
  `omni:ledger-msg` and run its section 4 for `MY_LANE`. Do not grep the ledger instead.

## 2. Extract the claims

Work from the report itself: the lane's terminal message, the workflow result, or the report
file. Never work from someone's summary of it. Save the report text to `$WORK/report.md`, because
the `delegation` kind reads that file.

A report written under the lane rules block carries a claims list; copy it. In a prose report,
**every sentence that asserts state becomes one claim.** Map each to a kind:

| The report says | Claims to write |
|---|---|
| "merged `<repo>#<n>`" | `pr_merged` (with `head=` when the report gives one) and `no_hold_at_merge` |
| "opened" or "ready" `<repo>#<n>` | `pr_open` (with `head=` when given) |
| "handed off" `<repo>#<n>` | `handoff_msg` with `to=repo-drain-<repo>` under the standing routing RULING (`/omni:ledger-catchup` shows the current model) and `head=` when given, plus `pr_open`, or `pr_merged` if the repository drain has already landed it |
| "wrote", "added", "fixed" a file on a branch | `file_on_branch` with `repo`, `branch`, `path` |
| "`OMN-n` is Done" (or any state) | `ticket_state` with `expected=`. Make the Linear read yourself (`get_issue`), then set `observed=` and `observed_at=` on the claim. Without that read it stays UNVERIFIED |
| "wrote the CLAIM / TERMINAL / HOLD row" | `ledger_row` with the row head `<ts> \| <TYPE> \| lane=<lane>` |
| "delegated", "drafted on the lab", a run id | one `delegation` claim for the whole report (it reads `$WORK/report.md`, `## Delegation` section or not) |
| CI is green, or a red is a known class | no kind here. Route it to `/omni:ci-watch`, and relay it as unverified until ci-watch has read it |
| "bound" or "accepted" `AC<n>` of `OMN-n` (an `ac_bindings` record) | no kind. Run step 3a as the second lane, never as the lane in `proposed_by` |
| anything else: "deployed", "all tests pass", "no regressions" | no kind. Relay it as unverified, reason "no live check for this claim". Never drop it silently |

A count is not a claim. "Fixed five PRs" becomes five claims, one per named PR. If the report
gives only the number, that is itself an unverified claim: "the report gives a count, not the
items".

Write the claims file. The top-level `lane` and `report` apply to every claim:

```json
{
  "lane": "<reporting lane>",
  "report": "<WORK>/report.md",
  "claims": [
    {"kind": "pr_merged", "subject": "omnimarket#1234", "head": "<sha prefix>"},
    {"kind": "no_hold_at_merge", "subject": "omnimarket#1234"},
    {"kind": "handoff_msg", "subject": "omnimarket#1235", "to": "<landing lane>"},
    {"kind": "pr_open", "subject": "omnimarket#1235"},
    {"kind": "file_on_branch", "repo": "omnimarket", "branch": "<branch>", "path": "src/<path>"},
    {"kind": "ticket_state", "subject": "OMN-1234", "expected": "Done"},
    {"kind": "delegation"}
  ]
}
```

## 3. Run the check

Normally the check runs **inside one read-only background lane**, dispatched through
`/omni:fan-out`, whose brief says: run the command below, write nothing else, report the exit
code. The foreground only dispatches, reads and decides, and this check makes many live reads.
**In a sandbox dry run (`ONEX_DRY_RUN` set), run it inline and dispatch nothing.** Under
`ONEX_DRY_RUN` the command adds `--dry-run`, which also skips the branch fetch.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" "$WORK/claims.json" --json \
  --resolve-lane-rows --verifier-lane "$MY_LANE" --inbox "$MY_LANE" ${ONEX_DRY_RUN:+--dry-run} > "$WORK/verdict.json"
echo "verify_claims rc=$?"
jq -r '.rows[]' "$WORK/verdict.json" > "$WORK/rows.txt"
jq -r '.artifacts[] | "\(.verdict)\t\(.artifact)", (.claims[] | "    \(.)"), (.findings[] | "    FINDING: \(.)")' "$WORK/verdict.json"
jq -r '.inbox.summary, (.inbox.open[] | "    \(.)")' "$WORK/verdict.json"
```

The script groups the claims by artifact (a PR, a file, a ticket, a report). **An artifact is
VERIFIED only when every claim on it is.** A PR that did merge, but through a hold, is a
FALSIFIED artifact. Step 7 relays by artifact, never by single claim.

Read `$WORK/verdict.json` yourself, never a lane's summary of it. The `inbox` block is your
inbox again, read now: a new open item there is binding before the Ledger block runs. The script never writes: it
prints the ledger rows to append under `.rows`, and the Ledger section appends them.
`--resolve-lane-rows` finds the reporting lane's newest CLAIM and TERMINAL rows, so you never grep
the ledger for them.

| rc | meaning | what you do |
|---|---|---|
| `0` | every claim VERIFIED | append the countersign, close out, relay |
| `1` | at least one claim FALSIFIED or UNVERIFIED (`overall` is `FALSIFIED` or `PARTIAL`) | append the rows, kick back on FALSIFIED, relay per step 7 |
| `2` | bad input: unknown kind, missing field, `ONEX_LEDGER_PATH` or `registry_root` unset | fix the claims file or the environment; the stderr line names the cause |

What each kind reads, and how it fails closed:

| Kind | Live source | Fails closed |
|---|---|---|
| `pr_merged` / `pr_open` | one declared exact-head read per PR (`ONEX_GH_EXACT_HEAD`, `gh pr view --json state,mergedAt,headRefOid`): state, merge time, exact head | a read error is UNVERIFIED; a wrong state or head is FALSIFIED |
| `handoff_msg` | the lane's MSG row naming the PR in its `pr=` cell, split by the row grammar's own `parse_row` | zero rows parsed is UNVERIFIED; no match, a different recipient or a different head is FALSIFIED |
| `file_on_branch` | the script's own ls-remote of the branch and fetch of that branch (a lane types neither, OMN-20495), then `cat-file -e` in the canonical clone | no clone is UNVERIFIED; a missing branch or file is FALSIFIED |
| `ticket_state` | the `observed=` value from your own Linear read | always UNVERIFIED until that read is made; it prints the probe to run |
| `ledger_row` | a fixed-string match on the row head over the ledger and its `archive/` rolls | zero rows read is UNVERIFIED (the positive control) |
| `no_hold_at_merge` | merge-drain's `drain_map.py`, called in-process: its `hold_findings` over its own `load_rows`, replayed to the merge time, and its runtime classifier for a merge pause | a hold or a binding pause is FALSIFIED; a missing `drain_map.py`, a changed interface, or an `ONEX_LEDGER_PATH` other than the ledger drain_map reads is UNVERIFIED, never VERIFIED |
| `delegation` | `delegation_receipt_check.py <report> --since <lane CLAIM>`; with no `## Delegation` section, the runs the report cites in prose are looked up with that check's own `cited_runs` and `resolve_run` | any PROBLEM the check prints is FALSIFIED, and the finding is that PROBLEM text: a missing section and a missing receipt are different findings, and a prose-cited receipt that exists is said to exist |

**Prove every zero.** An absence is only a finding when the reader demonstrably saw data (rule
16). The evidence line carries the control: the rows read for `ledger_row`, `handoff_msg` and
`no_hold_at_merge`, and the branch found on origin for `file_on_branch`. A FALSIFIED "absent"
whose evidence shows no control is UNVERIFIED; relay it that way.

## 3a. Accept an acceptance-criterion binding (second lane)

A lane never accepts a binding it wrote (operator RULING 2026-10-03T00:40:00Z
lane=orchestrator-2a21, OMN-17427). A verifier lane, or Codex as a cross-model reviewer, re-runs the
bound check and accepts it. The operator sees only disagreements.

A binding is an `ac_bindings` record on a contract `dod_evidence` item: `label`, `criterion_hash`,
`proposed_by`, `accepted_by`, `accepted_at`. A record with no `accepted_by` is a draft. A record
whose `accepted_by` is its own `proposed_by` is not an acceptance: node_dod_verify reads it as a
draft and names it `AC_BINDING_SELF_ACCEPTED` (omnimarket#3279), and the onex_change_control hosted
gate refuses it as `ac_binding_self_accepted` (onex_change_control#12466). Names match after
casefolding, dropping an `@host` suffix and reading `lane=` tokens, so `mac-occ-contracts@mac` and
`lane=mac-occ-contracts` name the same lane.

1. Confirm your lane is not the lane in `proposed_by`. Never set `accepted_by` on a record with no
   `proposed_by`; write the authoring lane into `proposed_by` first.
2. Read the item's checks and criterion text from the contract at the companion PR head.
3. Re-run every check yourself, in the item's `cwd`, at the commit the item's receipt names
   (`commit_sha`).
4. Decide whether the check as run proves the criterion's text. A passing check that does not
   exercise what the criterion states is a disagreement; so is a failing or zero-test run.
5. Agree, open companion PR: set `accepted_by: "<your lane>"` and `accepted_at` on that record; keep
   `proposed_by`. Re-mint the item's receipt from your own re-run, because its
   `contract_entry_sha256` hashes the whole item including `ac_bindings`. Push to the companion
   branch and hand the new head to the landing controller with `/omni:pr-handoff --needs land`.
6. Agree, merged contract: a merged item cannot be edited. Append a new item with the same checks;
   its record carries the same label and the current `criterion_hash`, `proposed_by` naming the
   original author and `accepted_by` your lane, with its own receipt.
7. Disagree: write nothing to the contract. Send one MSG through `/omni:ledger-msg` to `operator`
   with `ticket=`, `pr=`, the item id, the label, and what the re-run showed (exit code and the
   deciding output line).
8. Record both outcomes as claims in the countersign (Ledger section).

## Ledger

This is step 4, and the only place this skill writes to the ledger. It appends whatever the
script last printed into `$WORK/rows.txt`, and it runs three times in a run:
- **section 0**, only when `MY_LANE` had no open CLAIM: the verifier's own CLAIM;
- **after step 3**, always, in order:
  - a STATUS countersign: `countersigns=<the lane's TERMINAL timestamp>`,
    `verdict=VERIFIED|PARTIAL|FALSIFIED`, naming every falsified and unverified claim;
  - a CORRECTION `corrects=<that TERMINAL>`, when the TERMINAL asserted something false;
  - a kick-back MSG `to=<reporting lane>` in the `/omni:ledger-msg` shape
    (`id=<ts>-<your lane>`), when anything was FALSIFIED. The lane's inbox check reads it;
- **step 6**, only when this skill opened the CLAIM: the verifier's own TERMINAL.

FRICTION rows are not written here. They go through `/omni:friction-record` (step 6).

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
L="${ONEX_LEDGER_PATH:?set ONEX_LEDGER_PATH to the rolling work ledger}"
while IFS= read -r ROW; do
  [ -n "$ROW" ] || continue
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$L" --append "$ROW" || { echo "REFUSED at: $ROW"; break; }
done < "$WORK/rows.txt"
# Read back every row just appended, through the script (reader site R2), never a grep of the ledger:
jq -R -s '[split("\n")[] | select(length > 0) | {kind: "ledger_row", subject: (split(" | ")[0:3] | join(" | "))}]' \
  "$WORK/rows.txt" > "$WORK/readback.json"
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" "$WORK/readback.json"
```

- The loop stops at the first refusal, so a MSG is never written after a refused CORRECTION.
- Exit `65` is a grammar or lint refusal. Read the stderr line, fix the claims file or the flags,
  rerun step 3, and run this block again. Never edit the ledger by hand and never hand-write a
  row. `/omni:ledger-write` has the full exit table, and `onex_ledger.py "$L" --print-grammar`
  prints the grammar.
- Read back: each append exited `0`, and the readback prints `VERIFIED ledger_row` for every row
  in `rows.txt`. Anything else means the row is not on the ledger. Do not relay a countersign, and
  do not treat a CLAIM or TERMINAL as written, until it reads back.
- No `countersigns=` timestamp (`no-terminal-row`) means the lane wrote no TERMINAL. A lane that
  reported done without one has broken the lifecycle; say so in the relay.

## 5. Kick back

- **The lane is still running:** the MSG row is the kick-back. It is binding at the lane's next
  inbox check. Never SendMessage the lane: a message resurrects a stopped lane and it resumes
  spending.
- **The lane has stopped** (it wrote its TERMINAL, the usual case) **or died:** relaunch a fix lane
  through `/omni:fan-out`. Its brief, written with `/omni:lane-brief`, cites the MSG `id=` and
  the CORRECTION, and its CLAIM carries `parent=<your lane>`. In a dry run, say which lane you
  would relaunch and dispatch nothing.
- **A merge through a hold is already merged.** Do not revert it on your own: a revert is a
  destructive action and needs the operator. Report it naming the hold, and bring the revert
  question through `/omni:operator-ruling`.
- **A fix that produces a PR** goes to the landing lane by one MSG through `/omni:pr-handoff`.
  Neither this skill nor the fix lane merges, arms, reruns or polls CI.

## 6. Close out

Every run ends here, including one that stopped early on a refusal or a bad input.

1. **Friction first.** Some things this run hit are real friction: an append refused with `65`
   that took more than one fix, a helper the script could not find, a claim left unchecked for a
   tool reason rather than a missing fact, or anything else that cost more than a few minutes.
   Record each one with `/omni:friction-record`, as `MY_LANE` with its ticket and cost, one
   FRICTION row per item. Its section 1 finds an earlier row of the same class, and a second
   occurrence files a ticket. Its section 3 adds the one-line pointer under Known friction below.
   A limit already listed there (a Linear claim left UNVERIFIED, say) is not new friction unless
   it cost time. In a dry run the FRICTION row goes to the sandbox ledger like every other row.
2. **Close the CLAIM this skill opened.** Only when `$WORK/opened-claim` exists. The outcome is
   the overall verdict in lower case (`verified`, `partial`, `falsified`), or `stopped` when the
   run ended before step 3 wrote `verdict.json`:

```bash
[ -z "${ONEX_DRY_RUN:-}" ] || [ -f "$registry_root/.dryrun-sandbox" ] || { echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root"; exit 2; }
[ -f "$WORK/opened-claim" ] || { echo "CLAIM not opened by this skill: its own lane closes it"; exit 0; }
OUTCOME="$(jq -r '.overall | ascii_downcase' "$WORK/verdict.json" 2>&1)" || OUTCOME=stopped
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_claims.py" --lifecycle terminal --verifier-lane "$MY_LANE" \
  --ticket <the CLAIM's ticket> --outcome "$OUTCOME" --about "$REPORTING_LANE" \
  --friction <none, or one line naming the FRICTION rows from item 1 by timestamp> > "$WORK/rows.txt"
echo "terminal row rc=$?"
```

   The script resolves `closes=` from the open CLAIM. It exits `2` when there is no open CLAIM,
   and when `--friction` cites friction but the lane has no FRICTION row since its CLAIM (the
   message names `/omni:friction-record`; `onex_ledger.py`'s friction guard would refuse the row
   too). Run the Ledger block, then confirm with `--lane-state "$MY_LANE"`: rc `1` means no
   dangling CLAIM is left for the ledger-reconcile workflow or `/omni:session-resume` to read as
   a dead lane.

3. **A CLAIM this skill did not open** (section 0 rc `0`): write no TERMINAL here. The covering
   lane closes it with its own TERMINAL: the session close-out in `/omni:way-of-working`, or the
   dispatching lane's own. The relay's Ledger line hands it the countersign timestamp and the
   FRICTION rows from item 1, so that its `friction=` can cite them.

## 7. Relay

The relay is your last output: write it after step 6 has run. Relay from `.artifacts`, one line
per artifact.
- **Only VERIFIED artifacts are relayed as done**, each named in words: the repository and PR
  number with what the PR does, the file path and branch, the ticket and its state. Never a bare
  number, never only a count. An artifact with any FALSIFIED or UNVERIFIED claim is never listed
  as done, even when some of its claims are true. It does not appear on the Done line at all,
  not even to explain why it is missing: the claims about it that are true go on its Not true or
  Not checked line. When no artifact is VERIFIED, the Done line is the single word "none".
- **FALSIFIED artifacts** are relayed as what the lane said against what live state shows, in plain
  words, **from the artifact's `findings`**. Those are the same words the CORRECTION and the
  kick-back MSG carry, so the relay and the ledger never disagree about a claim. Rephrase them
  for reading, but never replace a finding with your own reading of the report: if the finding
  says the report has no Delegation section and the cited receipt exists, the relay says exactly
  that, not "no receipt". For example: "the lane says it merged the omnimarket PR 1234. It did
  merge, but a hold on that PR was in force when it merged."
- **UNVERIFIED artifacts** are relayed as unverified, with the reason from the evidence line.
- Report the evidence, not a guess at its cause. When you add an inference, label it as one.
- When `overall` is not VERIFIED, the lane's work is not reported as done, and nothing from it
  goes to a channel or a ticket's Done. Before a ticket moves to Done, run `/onex:dod_verify` as
  well.

Shape:

```
<lane>: <N> claims checked, verdict <overall> (countersign <STATUS ts>).
Done (verified): <each VERIFIED artifact in words, with its evidence; "none" when there are none>.
Not true: <each FALSIFIED artifact: claimed vs live>. Kicked back by MSG <id>; <relaunch or waiting>.
Not checked: <each UNVERIFIED artifact and why>.
Ledger: countersign <STATUS ts>; <TERMINAL ts closing this skill's CLAIM, or "covered by <lane>'s CLAIM <ts>">; friction <none, or the FRICTION rows>.
```

## Routes to

- `/omni:ledger-msg`: your inbox check (its `inbox.sh`, run by step 1 and step 3), and the
  reporting lane's reading of the kick-back.
- `/omni:ledger-write`: the row grammar and the append exit table. Your own CLAIM and TERMINAL
  are printed by the script (`--lifecycle`) and appended by the Ledger block.
- `/omni:friction-record`: one FRICTION row per real friction, before your TERMINAL (step 6),
  plus its pointer line under Known friction. A second occurrence files a ticket.
- `/omni:way-of-working`: the session TERMINAL that closes a covering session CLAIM.
- `/omni:ledger-catchup`: the standing RULING that names the landing lane.
- `/omni:fan-out` and `/omni:lane-brief`: the read-only check lane, and a relaunched fix lane.
- `/omni:pr-handoff`: a fix lane's PR goes to the landing lane by one MSG.
- `/omni:ci-watch`: any claim about CI colour or a red's class.
- `/onex:dod_verify`: before a ticket goes to Done.
- `/omni:operator-ruling`: a revert, or any other decision a finding needs from the operator.
- `/omni:merge-drain` (`drain_map.py`): the hold check this script calls in-process. Never a copy
  of it, and never a change to it.

## Known follow-up

The typed work ledger (`onex-ledger` in `ops_tooling_pkg`, plan
`beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in docs_repo) replaces the
`onex_ledger.py --append` line in the Ledger section. That is a one-line change, because the skill
appends in that one place (the countersign rows and its own CLAIM and TERMINAL alike) and the
script only prints rows. The script's one ledger reader (site
R2: the `ledger_row` match, the `handoff_msg` match and `--resolve-lane-rows`) becomes an event-id
lookup, proposed for the plan's no-prose gate list. The hold check follows drain_map, and the
inbox check follows `/omni:ledger-msg`'s `inbox.sh`, when the plan's reader tasks move them to the
typed ledger.

## Known friction

Each line below came from the 2026-09-24 staging dry runs, whose rows went only to a scratch
ledger, so none has a FRICTION row on the real ledger yet. When one recurs in a live run, record
it with `/omni:friction-record` (step 6) and add its `→ <row ts> lane=<lane>` pointer here.

- **Executors read the ledger by hand.** In two dry runs (2026-09-24) the executor skipped the
  inbox check and grepped or tailed the ledger instead, even with `/omni:ledger-msg` loaded. Step 1
  is now one concrete command, the step 3 command re-reads the inbox, and the rule against hand
  reads sits in section 0. Recorded 2026-09-24 in the staging build.
- **A sandbox shell can carry the real `registry_root`.** The Bash tool's shell profile may export the
  real registry root over the sandbox one. The section 0 guard then refuses the call, as it
  should; export the sandbox root at the top of the call and rerun. Seen once in the 2026-09-24
  dry runs.
- **Prose reports have no Delegation section.** A report in free prose fails the OMN-17009 check
  for the missing section, whatever its receipts. The finding says which it is, and whether a
  receipt the prose cites exists; an earlier build wrote "has no receipt" for both. Recorded
  2026-09-24 in the staging build.

- **Linear is not scriptable here.** `ticket_state` stays UNVERIFIED until you make the MCP read
  and put `observed=` on the claim. Recorded 2026-09-24 in the staging build.
- **Labels are current, not historical.** `no_hold_at_merge` replays ledger holds to the merge
  time, but reads hold labels as they are now. The evidence line says so. Recorded 2026-09-24.
- **A merge pause fails closed without the runtime classifier.** Where the omnibase_infra clone
  or its venv is missing (a sandbox), drain_map cannot classify the PR and treats a repo merge
  pause as binding. The evidence line carries drain_map's own "fails closed" note. Recorded
  2026-09-24.
- **The hold check reads a fixed path.** drain_map reads `$registry_root/docs/tracking/`, not
  `ONEX_LEDGER_PATH`. When the two differ, `no_hold_at_merge` is UNVERIFIED rather than reading a
  different ledger. Recorded 2026-09-24.
- **`file_on_branch` fetches.** It fetches the one claimed branch into the canonical clone's
  remote-tracking refs, and touches nothing else there. `--no-fetch` or `--dry-run` reads only
  what is already fetched. Recorded 2026-09-24.
