---
name: worktree-triage
description: Triage every worktree on this host in one command. Removes the classifier's safe class, pins every quiet non-live tree by ARCHIVE (unpushed-commit bundle and patches, the binary tracked diff and an untracked-file tar under .onex_state/worktree-pins, each verified, no commit, no push, no hook) and then removes it, keeps live trees (a process inside, an open CLAIM naming the path, recent activity), and sends the ambiguous ones to onex delegate (the lab rung; its GLM second rung pins the retired cloud-glm backend and fails until the tool moves to the Claude Code harness) with every answer checked against the git facts. Writes one ledger STATUS row (removed, pinned, kept, GB freed) and pages on a failed run or low disk. The same command runs every six hours from a launchd agent on the Mac and a systemd timer on the lab host; use this skill to run it now, to dry-run it, to read the last run, or to install or check the schedule. Use when someone says worktrees are eating the disk, asks what the triage removed, or wants the backlog cleared without asking tree by tree.
prosthetic: true
replaces_when: "an omnimarket node owns the whole triage (classify, archive pin, delegate, remove) and emits its run as a typed event the dashboard projects, and both hosts' timers call the node instead of onex-worktree-triage, for two consecutive weeks of runs."
restored_from: "none. New skill, from the operator direction of 2026-09-29 that worktree triage be automatic and use lab and GLM delegation, under the standing rule pin anything useful, then remove, no permission question."
ticket: OMN-17427
argument-hint: "[--dry-run] [--no-delegate]"
---

# Worktree triage (prosthetic)

The tool lives in the private operator-tooling repository, the ops_tooling_pkg clone in the
parent of `registry_root`. This skill is a thin shim over its command. Nothing here decides what is
removed: the classifier, the rubric and the archive verification do.

Operator standing rule (2026-09-24, restated 2026-09-29): pin anything useful, then remove; skip
only live work; do not ask first. So do not ask the operator before running it.

## Run it

```bash
OI="${registry_root:?}/../ops_tooling_pkg"
uv run --project "$OI" onex-worktree-triage --host operator-mac --dry-run   # what it would do
uv run --project "$OI" onex-worktree-triage --host operator-mac             # do it
```

On the lab host the host key is `lab-host-a`, run there (never over a Mac checkout of the lab's trees).
A run takes the lock `.onex_state/worktree-triage/run.lock`; if the scheduled run holds it, yours
exits 0 and does nothing, so read the scheduled run's report instead of waiting on the lock.

The classifier pass is the slow part (tens of minutes to two hours on the Mac at registry scale)
and runs under `heavy_lock`, so start the run from a background lane or leave it to the timer.

## What it does, in order

1. Disk: free space under 15 percent on the registry volume pages.
2. Safe class: omniclaude `scripts/worktree_auto_prune.py --execute` per registry root, with the
   morning prune's fences and under its consent row.
3. Every other tree: live git facts, then the rubric. KEEP: a process inside, an open CLAIM naming
   its path, activity in the last 12 hours, the hand-held list, unreadable, a standalone clone.
   PIN AND REMOVE: quiet for 48 hours with none of those. AMBIGUOUS: in between, a merge or rebase
   in progress, an open pull request quiet under 7 days, or an open CLAIM on its ticket.
4. Ambiguous: `onex delegate` with no backend (the lab rung answers). The tool's second rung still
   pins `cloud-glm`, which is retired and always fails: GLM runs only through Claude Code
   (`/omni:harness-delegate --harness claude-glm`), because the Coding Plan terms bar direct API calls
   (omnimarket#3136, OMN-20173). A row the lab does not answer is therefore kept, which is the safe
   side; moving the tool's rung to the harness is tracked on OMN-20173. The answer names the facts it relied
   on; one wrong value, an unknown fact or none named, and the tree is kept.
5. Pin and remove: archive, verify, re-check the tree still matches and nothing runs in it, then
   `git worktree remove --force` from its own clone.
6. Report: `.onex_state/worktree-triage/<stamp>-<host>.json` and one STATUS row,
   `lane=worktree-triage-<host>`. The Mac's run also relays the lab host's newest report.

Removal of the pin-and-remove class needs an authority row named in the tool's `triage.yaml` that
resolves in the ledger. Without it the run removes the safe class only and pages that the rest was
withheld. Record the operator's words with `/omni:operator-ruling` and set the stamp and lane there.

## Read the last run

```bash
python3 -m json.tool "$registry_root/.onex_state/worktree-triage/latest-operator-mac.json" | head -60
grep 'lane=worktree-triage-' "$ONEX_LEDGER_PATH" | tail -4
```

A pinned tree is restored from its directory under `.onex_state/worktree-pins/<ticket>/`: fetch
`unpushed.bundle` into a clone, check out its HEAD, `git apply --binary tracked.diff`, and extract
`untracked.tar`. `meta.json` names the original path, branch, head and base.

## The schedule

```bash
bash "$OI/launchd/worktree-triage/install.sh" --status      # Mac: loaded, last exit, log tail
bash "$OI/launchd/worktree-triage/install.sh"               # Mac: (re)install from the clone
ssh 192.0.2.127 'cd <lab clone of ops_tooling_pkg> && registry_root=<lab registry> bash systemd/worktree-triage/install.sh --status'
```

Before claiming a scheduled run happened, read the launchd log or `journalctl` and the STATUS row;
a loaded agent that never fired looks installed and does nothing.

## Never

git stash, reset or clean of a canonical clone; branch deletion; a push; any hook bypass;
`pkill -f`; removing a tree whose archive did not verify.

## Known friction

None recorded yet. Record one with `/omni:friction-record` and add a one-line pointer here.
