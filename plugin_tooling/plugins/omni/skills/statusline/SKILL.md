---
name: statusline
description: Install or reconfigure the local PR extension of the Claude Code status line. With arguments it edits the repo filter (hide web, show node, only m4, show all, list, reset). With install it copies the extension to the state directory's bin. The extension renders, with no gh call per render, line A (per milestone criteria proven and PRs red, CI running, ready or armed, held, draft, then the off-milestone total) and line B (per repository red, pending, ready, held and draft, with the hidden repositories named, dimmed). Use when the operator says to hide or show a repo on the status line, to focus the status line on one milestone, or after a plugin update to reinstall the extension.
prosthetic: true
replaces_when: "A projection on the bus carries per-milestone and per-repository open-PR state and the status line reads that, so this extension no longer reads the PR watcher file, the ledger and the board data file itself, on two consecutive sessions."
restored_from: "none: new skill (OMN-20285)"
ticket: OMN-20285
---

# Status line PR extension (prosthetic)

The public status line script runs an executable `statusline-prs` for the PR segment of its third
line and prints its second output line as a fourth line. This skill ships that executable and the
filter that bounds what it shows.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/statusline_prs.py" install
python3 "${CLAUDE_SKILL_DIR}/scripts/statusline_prs.py" config list
```

Requires `ONEX_STATE_DIR`. Reading the PR watcher state needs `registry_root`, and holds need
`ONEX_LEDGER_PATH`; without the ledger the line says `holds unread` instead of showing none.

## Arguments

`/omni:statusline <command>` runs `config <command>` with the same words:

- `hide web node`, `show node`, `show all` (hides nothing), `list`, `reset` (default: hide web and node).
  A repository is named by its status line abbreviation or its full name: core infra spi claude dash
  intel mem web node market cc-int base-int occ kb compat (also kb-pub home base gem rsd gh).
- `only m4`, `only m4 m4.5`, `only off`, `only all`: show PRs of those milestones only (`off` is the
  off-milestone group). The hidden-repository note and an `only:` note stay on line B, so a filtered
  view is never mistaken for the whole queue.
- A word that names no repository or milestone refuses and edits nothing.

Run it as `python3 "${CLAUDE_SKILL_DIR}/scripts/statusline_prs.py" config <command>` and report the
one line it prints. The change shows on the next render, because the filter applies at render time.

## What the lines mean

Line A: `M4 probe 7/12 1✗ │ off 10✗ 7◔ 11✓ ⏸2 ✎22 │ fleet cleared 7/32`

- `M4 probe 7/12`: criteria in that milestone's bucket whose probe passes in the latest board
  publish, out of the bucket's criteria. This is proof passing and is never a cleared count. The
  board's cleared also needs every carrier ticket closed and the result holding, and the board
  publishes it only as the fleet-wide `fleet cleared x/y` at the end (read from the publish log;
  no per-milestone or per-criterion cleared is published, so none is shown). Read cleared for one
  milestone on the Beta Release Board itself.
- `✗` red, `◔` CI running, `✓` ready or armed, `⏸N` held, `✎N` draft (counts that are never durations). Zero counts are omitted.
- A PR belongs to a milestone when an `OMN-n` in its title or branch is a carrier of one of that
  milestone's criteria (highest priority first: M4, M4.5, M5, M3, M2, M1). Anything else is `off`.
- Held is a watcher-excluded PR or a PR named by a ledger HOLD still in force (an expired `until=`
  releases it). A landing-controller lab lease names no PR, so it never reads as a hold.

Line B: `infra 2✗3◔2✓ ✎9 ·claude 1✗1✓ ...·hidden: web node`. Repositories with no open PR are
omitted. The dashboard repository carries a dim `(L)`: its owner is the dashboard pillar's owner
(ruling 2026-10-01). When the line would pass 160 columns the repositories with the least
actionable work drop first and `+N more` says how many.

## Data and freshness

A render reads `$ONEX_STATE_DIR/statusline/snapshot.json` and never calls `gh`. A render that finds
the snapshot older than 60 seconds, or older than the watcher state, spawns a detached
`refresh`, which rebuilds it from the watcher state, the ledger (incrementally, by byte offset) and
the board data. The board's proofs-passing summary is one `gh` read, cached 30 minutes. A watcher
tick older than 30 minutes shows `⚠ watcher stale Nm`. With no snapshot yet the extension exits 1 and
the public script keeps its own segment.

## Known friction

- The status line process bounds the extension to 300 ms; the render path is about 50 ms. A slow
  host serves the last good output for up to an hour.
