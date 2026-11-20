---
name: hotpatch-pr
description: Hot-patch the installed omni plugin cache from a PR branch, open or already merged, and write the PR's hotpatch_markers.json entries. Lists the plugin files the branch changed against the PR's merge base, derives one marker per file that the installed copy demonstrably lacks, writes the entries to the worktree copy and to the installed root copy the guards actually read, installs each file into the cache with a .bak.<UTC stamp> backup beside it, and verifies both copies with the merge-pulse guard. Dry run by default. Use when a skill or drain fix must run before the published payload carries it, whether or not the PR has merged.
prosthetic: true
replaces_when: "The plugin cache installs from a published release by digest, a node records which digest each running process loaded, and nothing is ever hot-patched into an installed copy, on two consecutive drain runs."
restored_from: "none. Packaged from the hand hot-patches of 2026-09-27 and 28 (plugin-tooling-pkg#81, #88, #92, #94, #103)"
ticket: OMN-17427
---

# Hot-patch a PR into the installed plugin (prosthetic)

A fix that the published payload does not carry is copied into the installed plugin cache. Two things
were done by hand each time and forgotten some of the time: the backup that lets `/omni:adopt-merged`
decide later whether the merge superseded the patch, and the `hotpatch_markers.json` entry that lets
the merge pulse turn RED when a plugin update silently removes the patch (it did, 2026-09-28).

`workflows/hotpatch_pr.js` runs the sequence over `scripts/hotpatch_pr.py`, which has offline tests
against a throwaway git repository and a fake cache.

## A merged PR is the ordinary case

The reason to hot-patch is that the running payload predates a fix, and that is normally only noticed
once the fix has merged: the publish was cut before the merge and there is no automatic path from
main to the running copy. So this skill treats a merged PR as first class, and `origin/main` is never
the base (OMN-17427, FRICTION 2026-11-03T01:29:07Z):

- **The base is the PR's merge base**, `git merge-base origin/main HEAD`, which is the commit the PR
  diverged from whether it is open or already merged. Both repositories squash-merge, so a merged head
  is not an ancestor of main and the merge base is still the pre-merge commit. Against `origin/main`
  itself, every token a merged PR added is already in the base and every file reads as "no new marker".
  `--base <sha>` overrides it; a branch already contained in the base (a merge-commit merge, where the
  merge base is HEAD and the diff is empty) is refused by name rather than read as nothing to patch.
- **The installed copy decides the marker.** The merge base only supplies the candidate tokens; the
  marker must be one the *installed* copy does not contain, because that copy is what the guard reads
  and absence there is the whole proof that the text came from the patch and not from the payload. So
  a merged PR needs no hand `--marker`, and a file whose change the payload already carries is still
  refused with nothing written.
- **The base chosen, and why, goes in the PR body.** `changed` and `markers` print `base` and
  `base_reason` for exactly that.

## What it reuses

`merge-drain/scripts/hotpatch_markers.json` and `merge_pulse.read_plugin_guard` (the guard and its
file format), `adopt-merged`'s `.bak.<UTC stamp>` backup convention, and the plugin's
`installed_plugins.json` for the cache path. It bumps no version: since OMN-20497 a PR does not, and
the post-merge bump PR carries the version once the change lands.

Every decision about the installed tree — where it is, what one of its files says, which token
proves a patch of it, its backups, and how its marker file is appended to — lives in the hot-patch
surface of `node_plugin_tree_install_effect`, the node that owns the installed tree (its `IGNORE`
list already carries this surface's own `*.bak*` convention). `scripts/hotpatch_pr.py` reads git and
sequences those calls; it decides nothing about the cache itself, per the ruling
2026-10-15T08:14:15Z, which keeps a baselined mod script shrink-only.

## Order

1. Fix the code in a worktree under `$registry_root/worktrees/<ticket>/`, commit, push, open the PR.
   The marker entries name the PR, so it must exist first. A PR that has since merged is fine.
2. Run the workflow (dry run first, then `execute: true`):

```text
Workflow({
  scriptPath: "${CLAUDE_SKILL_DIR}/workflows/hotpatch_pr.js",
  args: {
    skill_dir: "${CLAUDE_SKILL_DIR}",
    worktree: "<the worktree path>",
    pr: "plugin-tooling-pkg#<n>",
    claude_home: "<config dir>",                  // only when skill_dir is outside <home>/plugins/cache/
    base: "<sha>",                                // only to override the merge base
    markers: ["<plugin-relative file>=<token>"]   // only to name a better marker than the derived one
  }
})
```

   The phases run Scope, **Markers, then Install**, Verify. Markers before Install on purpose: the
   marker has to be a token the installed copy lacks, which it only is before the patch lands, and a
   refusal then leaves the cache unpatched rather than patched and unmarked — the invisible drift the
   guard exists to catch.

3. It returns the base and why, the marker entries added to each copy, the files installed with their
   backups, and both guards' answers. Commit the worktree's `hotpatch_markers.json`, push, then
   `/omni:pr-handoff`. The installed copy already has the entries.

## Marker rules

A marker is a token the branch adds that **the installed copy does not contain**, so it proves the
patch and not the payload; candidates come from the diff against the merge base, longest first,
because a long identifier cannot reappear in an unrelated payload by accident while a short common
word can. A file the base does not have gets the empty marker (the file must exist). Tests, prose and
manifests get no entry: they are not what runs. A file where the installed copy already holds every
added token is refused, with no marker written to either copy and nothing installed: either the
payload already carries that change, or `--marker <file>=<token>` names a better token. Running it
twice adds no duplicate entry to either copy.

## Both marker copies

`merge_pulse.HOTPATCH_MARKERS` is `hotpatch_markers.json` beside the running `merge_pulse.py`, and
adopt-merged's `plugin_guard.check(root)` reads `<root>/skills/merge-drain/scripts/hotpatch_markers.json`.
Both therefore read the copy **inside the installed root**, never a worktree. So entries are appended
to both:

- the worktree copy, which is what gets committed and merges;
- the installed root's copy, which is what every guard reads now, backed up as
  `hotpatch_markers.json.bak.<UTC stamp>` first.

Appended to both, never copied from one to the other: the two hold different histories (on
2026-11-03 the cache copy had 115 entries against main's 111, the four extra being that night's
hot-patches), so overwriting either would delete live entries. `verify` reads both.

A PR that is neither open nor merged on main — a closed or abandoned branch — should not be
hot-patched: nothing will ever retire its marker, so the entry turns the guard permanently RED once
the next publish lands. That check is **not** in the script, because a squash-merged head and an
abandoned head are indistinguishable from the local history alone; it needs the forge. The lane runs
`gh pr view <n> --json state` and stops on `CLOSED` before launching the workflow.

## Known friction (from prior runs)

- **A plugin update replaced a hot-patched cache.** With no marker entries nothing noticed until the drain lost its delegation step. The merge pulse now reads `hotpatch_markers.json`; every hot-patched PR needs its entries in the same hour. → RULING 2026-09-29T00:33:24Z lane=orchestrator-83, OMN-19915
- **A hot-patch with no backup could not be reconciled.** adopt-merged classifies a patch by its `.bak.<stamp>` file. The install step writes it. → OMN-17427
- **The patch is not the release.** The guard passing means the copy carries the fix, not that the version was bumped upstream: since OMN-20497 the post-merge bump PR carries the version after the fix merges.
- **The skill refused the one case it exists for.** Hot-patching a MERGED PR took three hand workarounds: the workflow passed no `claude_home`, so the script read `~/.claude/plugins/installed_plugins.json` (a `"plugins": {}` stub on this host) and died on an uncaught KeyError, and the four subcommands had to be called by hand with `--claude-home`; `pick_marker` resolved the base as `origin/main`, where every token the merged PR added already is, so every file needed a `--marker` flag; and the entries were written only to the worktree copy, so they had to be transplanted into the installed root's copy by hand with their own `.bak`. All three are fixed above: `claude_home` is derived from `skill_dir` and defaults to `$CLAUDE_CONFIG_DIR`, the base is the merge base with the marker proved absent from the installed copy, and both copies are appended to. → FRICTION 2026-11-03T01:29:07Z lane=hotpatch-pool-alarm-0125, 25 minutes, OMN-17427
