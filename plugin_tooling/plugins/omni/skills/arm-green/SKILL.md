---
name: arm-green
description: Arm or land, with no model in the loop, the green pull requests on a fresh merge-drain map's WOULD-ARM and WOULD-LAND-NO-ARM lists. One batched live GraphQL re-read, then auto-merge arming through omnibase_infra's bulk PR throttle, or a squash on the exact re-read head where the repository has no auto-merge or the PR carries the arm-gate label. Refuses a map older than 20 minutes, stops below 500 remaining quota, never lands a runtime-affecting omnibase_infra or omnimarket PR, and appends one STATUS row per acting run. Use once per drain map refresh, before dispatching pr-land lanes, so lanes go only to PRs that need a fix.
prosthetic: true
replaces_when: "An omnimarket node (node_pr_lifecycle_orchestrator or the merge-queue governor) arms and lands the drain map's green lists itself from the typed map, with the same freshness, quota, hold, author and runtime-class refusals and a typed receipt, and the merge drain calls it instead of this script on two consecutive drain runs."
restored_from: "none: ops_tooling_pkg#25 (OMN-19852) built it as ops_tooling_pkg src/ops_tooling_pkg/arm_green_prs.py; packaged here by OMN-19814 per the RULING 2026-09-27T10:38:47Z lane=scripts-to-skills-ruling-83"
ticket: OMN-19852
---

# Arm green (prosthetic)

The merge-drain map already decides which open pull requests are green, unheld, unowned and not
draft: its `WOULD-ARM` and `WOULD-LAND-NO-ARM` lists. Each of them used to wait for a `pr-land` lane
whose only work was to arm auto-merge or squash on the exact head. This skill does that step
mechanically, so lanes are spent on pull requests that need a fix.

## Run it

Requires `registry_root`; `ONEX_LEDGER_PATH` for the STATUS row (without it the row is printed as
`LEDGER-ROW-UNWRITTEN` for the caller to record). Standard library only: no venv, no install.

```bash
env -u PYTHONPATH python3 "${CLAUDE_SKILL_DIR}/scripts/arm_green_prs.py" --map-dir "<drain map dir>" --lane "<your lane>" --dry-run
env -u PYTHONPATH python3 "${CLAUDE_SKILL_DIR}/scripts/arm_green_prs.py" --map-dir "<drain map dir>" --lane "<your lane>"
```

`--map-dir` defaults to `$registry_root/.claude_scratch/reports/drain-map-latest` (the drain's
canonical map). Run the dry run first when you have not run it this session. Never append
`2>/dev/null` (CLAUDE.md rule 16).

Options: `--ledger <path>` (default `ONEX_LEDGER_PATH`), `--lane <name>` (default `arm-green-prs`;
pass your own lane so the STATUS row is yours), `--receipt-dir <dir>` (the throttle receipts,
default `$registry_root/.claude_scratch/arm-green-prs`).

## What it does, in order

1. Reads the drain map directory. A map older than 20 minutes (the `read_time=` line of its
   `run.log`, else the table's mtime) is refused with exit 2 before any GitHub call. The age limit
   has no override: re-run `drain_map.py` (`/omni:merge-drain` step 1).
2. Reads the remaining quota from the headers of one real GraphQL and one real REST call, never the
   rate_limit endpoint. Below 500 in either bucket it exits 0 having done nothing.
3. Re-reads every candidate live in ONE batched GraphQL query: head, draft, mergeable, merge state,
   status-check rollup, auto-merge request, merge-queue entry, labels, base, author, the last
   timeline events and the repository's auto-merge setting.
4. Skips a candidate unless it is open, not draft, MERGEABLE, rollup SUCCESS, carries no label of
   the hold family (the arm-gate member is allowed for WOULD-LAND-NO-ARM only), is not armed or
   queued, has not been dequeued for failed checks twice since its last commit and since the base branch last moved (never six times since the commit), is on the head and
   base the map read, and is not on the exclusion list. Its author does not matter: a
   collaborator's green, non-draft PR is armed like the operator's, and one that is not ready is a draft
   (RULING 2026-10-14T02:24:46Z, OMN-20249). An
   omnibase_infra or omnimarket candidate must also be not-runtime-affecting: the map's `runtime`
   column, else the canonical rebuild trigger in dry-run after positive and negative controls for
   that repository. Anything unclassifiable fails closed.
5. The landing controller arms WOULD-ARM candidates in auto-merge repositories and
   squash-merges everything else on the exact re-read head, only from merge state CLEAN.
   A lane hands each PR off through `/omni:pr-handoff` (`needs=land`) and stops touching it.
6. Appends one STATUS row through the plugin's `scripts/onex_ledger.py` when the run acted.

`--dry-run` stops after step 4: it prints the plan and the row it would write, and mutates nothing.

## Output

One line per candidate, then one outcome line per action, then the ledger result:

```
ARM   omnimarket#10               head=0123456789 bulk_pr_throttle arm-automerge
MERGE omnibase_spi#20             head=0123456789 no auto-merge
SKIP  omnibase_infra#4184         head=0123456789 merge queue dequeued it for failed checks 2x on this head (needs a fix lane)
OK     arm omnimarket#10 armed
FAILED merge omnibase_spi#20 <gh error>
ledger: rc=0 OK STATUS ...
```

Exit `0` done (including nothing to do and the quota floor), `1` at least one arm or merge failed,
`2` refused (stale or missing map, `registry_root` unset). A SKIP whose reason is a stale or conflicted
branch, a red rollup, repeated failed-checks dequeues or a draft is a PR for a `pr-land` lane; a
`runtime class` SKIP belongs to the drain's runtime-token path, never to this script.

## Guardrails

- It never re-checks ledger holds (the map did, at most 20 minutes ago), never updates a branch,
  reruns CI, dispatches a lane, uses a bypass actor or admin merge, or touches production.
- It is a landing action: run it only from a lane that holds landing authority (the merge drain or
  the landing lane), never from a build lane (feedback: one lane lands PRs).
- The exclusion list (`EXCLUDED_PRS`, `EXCLUDED_REPOS`) and the documented auto-merge policy table
  live in the script. A live `allow_auto_merge` that disagrees with the table fails closed for that
  candidate. Changing either is a plugin change, which the post-merge bump PR versions (OMN-20497).

## Tests

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_lab_run.py" --via bus --lane "<lane>" --repo plugin-tooling-pkg --ref "<pushed branch>" -- python3 -B -m pytest -q -p no:cacheprovider plugins/omni/skills/arm-green/tests/test_arm_green_prs.py
```

## Known friction (from prior runs)

Record new friction with `/omni:friction-record` and add a line here in the same PR.

- **A merge-queue dequeue loop.** omnibase_infra#4184 was re-armed and dequeued for failed checks
  four times on one head. The script now skips a PR dequeued twice for failed checks since its last
  commit, and one already in a merge queue. The count resets when the base branch moves, because a
  failure that predates the base head may have been the base's own (omniclaude#3090 was dequeued four
  times by a lapsed calendar test on dev and stayed unarmable after dev was fixed); six failed-checks
  dequeues since the last commit refuse regardless. → STATUS 2026-09-27T10:57:14Z lane=arm-green-script-83,
  OMN-19852
- **A transient gh HTTP 502 on the batched read skipped every candidate for the tick.** The read had
  no retry, so one failed request mapped every candidate to "no live read". It now retries up to 3
  attempts, 3 seconds apart, and still fails closed when every attempt fails. → OMN-17427
