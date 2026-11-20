---
name: ledger-preflight
description: Check the rolling-ledger environment at session start, in one place, through /onex:preflight and the onex-overlays session_preflight overlay. It adds five declared checks, each with its fix line. The ledger path is set; its file name keeps the row lint on; it is the registry ledger and not a copy; the row grammar loads; the landing controller is live on this host and writes its ledger. Every check is a blocker. It also proves those checks ran, because a stale per-user overlay otherwise passes silently. Use at every session start, as way-of-working step 2, and whenever a ledger append is refused or goes to the wrong file.
prosthetic: true
replaces_when: "The session orchestrator's own health gate runs session_preflight.py with the overlay at every session start, so a session never has to invoke this by hand, on two consecutive weeks with no ledger append refused for an environment reason. On 2026-09-24 nothing runs preflight unprompted, and the overlay carried no ledger check."
restored_from: "none. New checks, which replace a round-1 draft prerequisites script that duplicated /onex:preflight"
ticket: OMN-17427
---

# Ledger preflight (onex-overlays session_preflight overlay)

The rolling work ledger holds coordination and state history for every session and lane. Work starts
with a CLAIM and ends with a TERMINAL. Lanes talk to each other through MSG rows, and a finished PR
reaches the landing lane through one MSG. The operator's words become RULING or OPERATOR-CONSENT
rows. All of it breaks quietly if the environment is wrong:

- an append goes to a copy that no reader looks at;
- a file with another name takes rows unlinted;
- a grammar module is missing, so every CLAIM is refused;
- a host is detached, so its HOLDs and handoff MSGs reach nobody.

This skill makes a session start prove the ledger environment once, before the first row.

**It is a thin wrapper.** It holds no check recipes. The checks live in one place, the
`session_preflight` overlay of the `onex-overlays` plugin, and the public `/onex:preflight` runner
runs them. This skill only says how to run them, how to read the result, and where each result
sends you. Do not copy a check body into a script or into this file. The one script it ships for
sessions, `scripts/ledger_checks_ran.py`, probes nothing: it reads the runner's receipt to prove
which checks ran.

**It builds nothing about landing.** The landing controller, a launchd tick, owns landing (RULING
2026-09-29T12:02:35Z); the hand-run drain lanes it replaced are retired. A session never merges, arms,
reruns or polls CI; it hands a PR over with one MSG to `landing-controller` through `/omni:pr-handoff`,
and stops. So the only landing-related fact preflight reports is whether the controller is live on
this host and writes to its ledger.

**Every check blocks.** Operator RULING 2026-10-21T18:21:36Z lane=preflight-blockers-1820: preflight
warnings "should be blocking", because a warning nobody acts on is drift. The overlay declares every
check `severity: blocker`, and plugin-tooling-pkg `tests/test_session_preflight_all_blockers.py`
fails the build on any other severity.

## 0. Prerequisites and the dry-run guard

Step 2 needs two locations, and they are separate on purpose:

- `registry_root` (required, no default): the registry root. The overlay's ledger checks compare the
  ledger against it, and the ledger scripts load from it.
- `ONEX_PREFLIGHT_RUNNER` (optional): the full path of the onex plugin's `session_preflight.py`.
  When it is unset, step 2 uses `$registry_root/omniclaude/plugins/onex/scripts/session_preflight.py`,
  the runner in the registry's own omniclaude clone. The runner is code in the onex plugin tree,
  not part of the ledger environment, so it does not have to move when `registry_root` does.

Step 2 checks both before it runs anything. An unset `registry_root` prints
`REFUSED: registry_root is unset` and a missing runner prints `REFUSED: no preflight runner at <path>`,
each with its fix, and step 2 stops there (exit 2).

**A dry run** points `registry_root` and `ONEX_LEDGER_PATH` at a sandbox registry root, and sets
`ONEX_PREFLIGHT_RUNNER` to the real runner's path **before** it switches `registry_root`. A sandbox
root holds no `omniclaude/` tree. Without the override, step 2 refuses with
`no preflight runner at <sandbox>/omniclaude/...`, and that refusal is correct. It must not be
worked around by copying the runner into the sandbox, because a lone copy cannot import its sibling
modules (step 2, exit table). Preflight is read-only, so apart from those three variables a dry run
runs step 2 exactly as written. A dry run that also points `XDG_CONFIG_HOME` into the sandbox (to
test the per-user fallback) must pin `GH_CONFIG_DIR` to the real one (see Known friction). It first
runs this guard:

```bash
if [ -n "$ONEX_DRY_RUN" ] && [ ! -f "$registry_root/.dryrun-sandbox" ]; then echo "REFUSED: ONEX_DRY_RUN set outside a sandbox registry root (no .dryrun-sandbox marker under registry_root)"; exit 2; fi
```

The guards are `if` forms, not brace groups, because a headless session's command checker refuses a
brace group that contains a quote.

## 1. Point preflight at the overlay

The runner takes the first overlay it finds, in this order:

1. `--overlay <file>`;
2. `SESSION_PREFLIGHT_OVERLAY_PATH`;
3. each root in `ONEX_SKILL_OVERLAY_ROOTS`, joined with `session_preflight/overlay.yaml`;
4. **the per-user install**, `${XDG_CONFIG_HOME:-$HOME/.config}/onex/overlays/session_preflight/overlay.yaml`.

The first two are explicit: one that names a missing file is refused, not skipped. The last two fall
through when absent. The run refuses (exit 2, naming every location tried) **only when all four
miss**. So with no variable set, the runner does not fail fast. It quietly uses whatever per-user
copy exists, however old it is.

**That fallback is the trap.** A per-user copy installed before the ledger checks existed carries
none of them. Preflight then exits 0 and prints nothing under `quiet`, even with `ONEX_LEDGER_PATH`
unset. That is a green run in which not one ledger check ran. Do one of these, and do not rely on an
unrefreshed per-user copy:

- set `SESSION_PREFLIGHT_OVERLAY_PATH` (or `ONEX_SKILL_OVERLAY_ROOTS`) to the overlay in the
  **marketplace clone**, whose path stays stable across plugin versions; or
- refresh the per-user copy from that overlay each time the plugin version changes:
  `python3 <runner> --install-overlay <marketplace overlay>`, where `<runner>` is the path step 2
  resolves (`ONEX_PREFLIGHT_RUNNER`, or the registry's omniclaude clone).
  It validates the overlay before writing it, and refuses (exit 2) an overlay with a check that has
  no fix line.

Either way, step 2 proves which checks ran. An exit 0 alone does not.

## 2. Run it quiet, prove the ledger checks ran, and stop on a blocker

Call the runner directly (it is the same runner `/onex:preflight` uses), and write its receipt to a
scratch file, never into the registry. `mktemp` puts it in the system temp directory, which is
scratch in a dry run too. Run this block as written:

```bash
if [ -z "$registry_root" ]; then echo "REFUSED: registry_root is unset. Fix: export registry_root=<registry root> (the directory holding docs/tracking/ROLLING_WORK_LEDGER.md)"; exit 2; fi
RUNNER="${ONEX_PREFLIGHT_RUNNER:-$registry_root/omniclaude/plugins/onex/scripts/session_preflight.py}"
if [ ! -f "$RUNNER" ]; then echo "REFUSED: no preflight runner at $RUNNER. Fix: export ONEX_PREFLIGHT_RUNNER=<real registry root>/omniclaude/plugins/onex/scripts/session_preflight.py (a dry run always sets this; see step 0)"; exit 2; fi
R="$(mktemp)"; python3 "$RUNNER" --intent quiet --receipt "$R"; PF=$?; echo "preflight exit $PF"
if [ "$PF" -le 1 ]; then python3 "${CLAUDE_SKILL_DIR}/scripts/ledger_checks_ran.py" --receipt "$R"; echo "ledger-checks exit $?"; fi
```

The loader fills in `${CLAUDE_SKILL_DIR}` with this skill's own directory, so the source carries no
machine path. The receipt lists every check the resolved overlay declared, passed or not. The runner writes it on
every outcome except a refusal, so the confirmation runs only after `preflight exit 0` or `1`.
`ledger_checks_ran.py` is read-only. It exits 0 (`ledger-checks: ran 5/5`) only when all five
check_ids from step 4 are in the receipt. It exits 1 (`NOT RUN n/5`, naming the missing ones and the
fix) when the overlay that resolved predates them. It exits 2 when the receipt is missing or empty,
and then it says which. **Treat its exit 1 as a blocker, whatever preflight's own exit was**, and fix
it with step 1. Without a receipt at hand, `--intent normal --all` prints one `PASS` or failure line
per check, and the five ledger titles must be among them.

Until the overlay change in section 6 ships, the marketplace clone's overlay also lacks the five
checks, so this confirmation fails everywhere except against the staged overlay. That is the check
working as intended, not a defect in it.

| What the block printed | Meaning | What you do |
|---|---|---|
| `REFUSED: registry_root is unset`, and no `preflight exit` line | nothing ran; the registry root is unknown | run the `Fix:` on that line, then re-run the block |
| `REFUSED: no preflight runner at <path>`, and no `preflight exit` line | nothing ran; that path holds no runner. In a dry run, `registry_root` names a sandbox and `ONEX_PREFLIGHT_RUNNER` was not set | run the `Fix:` on that line (step 0), then re-run the block |
| `preflight exit 0`, then `ledger-checks exit 0` | every blocker passed, and the ledger checks were among them | continue to step 3 |
| `preflight exit 0`, then `ledger-checks exit 1` | a stale or foreign overlay resolved; no ledger check ran | not a pass. Fix step 1, then re-run the block |
| `preflight exit 1`, then `ledger-checks exit 1` | a stale or foreign overlay resolved, **and** one of its own checks failed. None of the printed blockers is a ledger check | fix step 1 first, because those blockers came from the wrong overlay. Then re-run the block and read the new lines |
| `preflight exit 1`, then `ledger-checks exit 0` | at least one blocker failed | print the runner's lines **exactly as written**. Run each fix, then re-run. **Append no ledger row until this exits 0.** An append now would be refused or would land in a file no reader sees. |
| `preflight exit 1`, with a Python traceback and no `BLOCKER` line | the runner never ran: a lone copy of `session_preflight.py` cannot import its sibling modules (`ModuleNotFoundError`) | nothing was checked. Point `ONEX_PREFLIGHT_RUNNER` at the runner inside a full onex plugin tree, never a copied file |
| `preflight exit 2`, and no `ledger-checks` line | preflight refused; nothing was checked | print the runner's stderr line (`preflight: REFUSED — ...`), fix the cause below, re-run the block |

The runner refuses (exit 2) for any of these causes:

| Refusal text names | Cause | Fix |
|---|---|---|
| `no preflight overlay resolved` | none of the four locations in step 1 holds an overlay (both variables unset or pointing at nothing, and the per-user directory empty), or `--overlay` names a missing file | set `SESSION_PREFLIGHT_OVERLAY_PATH` to the overlay in the marketplace clone (the reason lists every location tried) |
| a field or check of the overlay | the overlay is malformed: a check with no `fix`, an unknown `kind` or `severity`, a duplicate `check_id` | fix the overlay, then prove it with `session_preflight.py --install-overlay <overlay>` |
| `session-intent resolver is missing` | `lib/intent.sh` is not beside the runner's `scripts/` directory, because the scripts directory was copied or run from a partial checkout. This reason names no fix command | point `ONEX_PREFLIGHT_RUNNER` at the runner inside a full onex plugin tree (normally `<registry root>/omniclaude/plugins/onex/scripts/session_preflight.py`), never a lone copy |
| `session-intent resolver returned` | `intent.sh` ran but printed none of `quiet`, `normal`, `tick`, so the resolver itself is broken | re-run with `--intent quiet`; if it still refuses, record the broken resolver with `/omni:friction-record` and stop |
| `points at no readable file` | `SESSION_PREFLIGHT_OVERLAY_PATH` names a file that does not exist. An explicit selector is refused, never skipped (step 1) | point it at the overlay in the marketplace clone, or unset it |
| `is not a readable file` or `could not be read` | the overlay path resolves but the file cannot be opened | fix the path or its permissions |
| `under the tick intent` | `--intent tick` with nowhere to write the verdict | add `--receipt <file>` or set `SESSION_PREFLIGHT_RECEIPT` |

Present the runner's lines unchanged. The fix line is the part a reader acts on, so never reword it.

## 3. Read the host mode

Run the runner once more, under `normal`. A command tool keeps no shell variables between calls, so
resolve the runner again rather than reuse `RUNNER`:

```bash
python3 "${ONEX_PREFLIGHT_RUNNER:-$registry_root/omniclaude/plugins/onex/scripts/session_preflight.py}" --intent normal
```

The runner prints a check's title, not its id. A `BLOCKER` line titled `The landing controller is
live on this host and writes to its ledger` (the `coordination_host` check) means one of two things:
the controller's heartbeat (`$LANDING_STATE_DIR/heartbeat`, by default
`~/.local/state/omni/landing/heartbeat`) is missing or older than 600 s, twice its interval; or none
of the newest 2,000 ledger lines on this host carries the controller's `actor=script:landing-controller`
cell. A remote lane has no controller of its own and is judged on its snapshot's rows alone. Either
way this is a **detached host**, and the session does not start: run the fix line (the controller's
status, then `--kickstart` for a stopped one), or start the session on the coordination host. The
detached-host rules in `/omni:way-of-working` section 5.5 say why a session here would reach nobody.

With no such line, this is the coordination host.

## 4. The five checks

All five checks run on every pass, and every one is in the receipt. Each later check passes
vacuously when the input that an earlier check guards is missing or wrong. So an unset variable
prints one line and not four, and `ran 5/5` still holds, because all five ran. The run still exits 1,
because the earlier check is a blocker.

| check_id | Severity | What it catches | Why it matters |
|---|---|---|---|
| `ledger_path` | blocker | `ONEX_LEDGER_PATH` is unset or resolves to nothing | the ledger skills take the path from this variable, and it has no default (rule 8) |
| `ledger_basename` | blocker | the file is not named `ROLLING_WORK_LEDGER.md` | `onex-ledger` lints only the governed file name (`--print-grammar` lists it). Under any other name, a malformed row is accepted silently |
| `ledger_is_registry_ledger` | blocker | the `realpath` differs from `$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md` | some readers build the path from `registry_root`. A copy splits the writers from those readers, so a HOLD goes unseen. A symlink to the real file passes |
| `ledger_grammar` | blocker | `onex-ledger --print-grammar` does not exit 0 | the packaged grammar module is missing, so every governed append would be refused at the first CLAIM |
| `coordination_host` | blocker | the landing controller's heartbeat is missing or over 600 s old here, or no `actor=script:landing-controller` cell is in the newest 2,000 lines (a remote lane: the cell only) | the ledger is one file on one host. A host the controller does not run on and write to is detached (step 3); its HOLDs and handoff MSGs reach nobody |

Each fix line is in the overlay, beside its check.

`coordination_host` matches the controller's typed `actor=` cell, never free text, so a MSG that
only addresses `landing-controller` does not count. The hand-run `merge-drain-*` and `repo-drain-*`
lanes it used to look for are retired and no longer count. The typed-ledger migration replaces the
cell match with a typed actor field (Known follow-up).

## 5. Ledger

Preflight itself writes no row. The session's first row is the session CLAIM, which comes after
this skill exits 0. `/omni:way-of-working` writes it through `/omni:ledger-write`. Every append in
this skill's scope uses this one line, kept here and nowhere else in the file (a passing preflight
proves `$ONEX_LEDGER_PATH` names this same file, so the two spellings are one ledger):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_ledger.py" "$registry_root/docs/tracking/ROLLING_WORK_LEDGER.md" --append '<row>'
```

A dry run passes a scratch copy of the ledger as the first argument instead, so the same lint runs
and the real file is untouched.

Exit 65 is a lint refusal. Fix the row; never route around the lint. If a blocker cost real time,
record it with `/omni:friction-record` before your TERMINAL.

**Known follow-up.** When the typed JSONL ledger replaces the markdown file (onex-ledger in
ops_tooling_pkg; plan `beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md` in the planning corpus), four checks change. `ledger_basename`, `ledger_is_registry_ledger` and
`ledger_grammar` move to that ledger's path and its own schema probe. `coordination_host` reads the
controller's rows as a typed actor field instead of the cell match. The append line above changes in the
same place.

## 6. Testing, and shipping the overlay change

`tests/sandbox_preflight_cases.py` in this skill's directory builds one sandbox registry root per
case. Each root uses the shared resolver and the `ops_tooling_pkg` checkout, the real ledger's
header, and fixture rows appended through `onex-ledger`. Each case changes exactly one
variable. The script is read-only against the real registry, and it asserts that the real ledger's
head hash is unchanged and that no row carries the run's nonce.

- `--help` prints usage.
- `--list` is the dry mode: it prints the cases and builds nothing.
- `--keep` keeps the sandboxes for inspection.
- `--no-full` skips the two full-overlay cases, which run every machine-wide check and are slow.

The cases cover:

- each W1 blocker: the variable unset, the name `other.md`, a divergent copy, and the grammar module
  absent;
- a symlink to the real ledger, which is accepted;
- the host blocker under `normal` and `quiet` when no controller row is in the ledger, and again
  when the controller's heartbeat is gone;
- a MSG that only addresses the controller, which does not count;
- the host row matching the controller's actor cell and heartbeat, as a blocker;
- the per-user fallback, with no selector variable and `XDG_CONFIG_HOME` inside the sandbox: an
  empty per-user directory refuses (exit 2); a stale per-user overlay with no ledger checks gives the
  silent green (exit 0, nothing printed, `ONEX_LEDGER_PATH` unset), which `ledger_checks_ran.py`
  catches (exit 1, `NOT RUN 5/5`); after `--install-overlay` refreshes the copy, the `ledger_path`
  blocker returns and the confirmation passes (`ran 5/5`);
- the same unset variable against the full staged overlay;
- the `--install-overlay` validation, and a fix-less copy that is refused;
- the step 0 and step 2 blocks of this file, extracted and run exactly as written, under both bash
  and zsh (zsh with no startup files, see Known friction). An unset `registry_root` refuses and names it.
  A sandbox `registry_root` with no `ONEX_PREFLIGHT_RUNNER` refuses and names the override. The
  documented dry run passes with `ran 5/5`. An unset `ONEX_LEDGER_PATH` gives its one blocker with
  `ran 5/5`. A refused overlay prints `preflight exit 2` with its stderr reason, and the
  confirmation is skipped. The dry-run guard refuses a root with no sandbox marker.

The zero-leak isolation count also has a positive control: the same count over a sandbox ledger must
find the fixture rows.

The change ships as one PR to plugin-tooling-pkg. Every file this directory holds has a named
destination there. Nothing ships to the public onex plugin: the runner already exists.

| Staged here | Lands in plugin-tooling-pkg at | Why there |
|---|---|---|
| `upstream/plugins/onex-overlays/overlays/session_preflight/overlay.yaml` | the same path | the five checks and their fix lines. The runner reads them from here |
| `upstream/plugins/onex-overlays/.claude-plugin/plugin.json` | the same path, `0.1.1` to `0.1.2` | acceptance O3 |
| `SKILL.md` | `plugins/omni/skills/ledger-preflight/SKILL.md`, frontmatter `name: ledger-preflight`, invoked as `/omni:ledger-preflight` | onex-overlays is data only (its `plugin.json` declares no skills or hooks), so the skill cannot live beside the overlay. The omni plugin is where every other ledger skill lives |
| `scripts/ledger_checks_ran.py`, `tests/sandbox_preflight_cases.py` | `plugins/omni/skills/ledger-preflight/scripts/` and `plugins/omni/skills/ledger-preflight/tests/` | the step 2 script path, built from the skill directory the loader fills in, then resolves in the shipped skill as it does here. ci-watch, merge-drain and pr-land ship their scripts the same way |
| (no staged copy) | `plugins/omni/.claude-plugin/plugin.json`, patch bump | a new skill in the omni plugin |
| `upstream/marketplace.json.patch` | `.claude-plugin/marketplace.json` | both entries, `onex-overlays` to `0.1.2` and `omni` to its new patch version |

The staged name is `onex-overlays session_preflight overlay`, with spaces. It is named after this
catalog entry only so that the staging plugin can load it (as
`onex-overlays-session_preflight-overlay`). The shipped name is `ledger-preflight`, hyphenated like
its sibling skills. That rename is the only change the PR makes to `SKILL.md`, and the body is copied
unchanged. Sibling skills that route here by the staged name (way-of-working step 3) switch to
`/omni:ledger-preflight` in the same PR.

`tests/sandbox_preflight_cases.py` finds the overlay under test in either layout. In the staged layout it
uses `upstream/`. In the shipped layout it uses the sibling `onex-overlays` plugin
(`plugins/onex-overlays/overlays/session_preflight/overlay.yaml`). `--overlay` overrides both. So
the same file runs unedited in both places.

Read the omni version from `main` when the PR is cut, not from this file. An open PR that bumps
another plugin's entry in `marketplace.json` conflicts only textually: rebase onto it and keep both
bumps. The change has no ordering dependency on any other PR.

The lane that ships the change follows the ledger lifecycle, with every row through the append line
in section 5:

1. Before the first write, it checks for a concurrent CLAIM on the ticket and the newest RULING rows
   (`/omni:lane-brief` does this for a dispatched lane), then writes its CLAIM: `lane=`, `actor=` or
   `model=`, `ticket=`, the repo and worktree, and the cost sentence.
2. It writes a STATUS row at checkpoints (sandbox cases green, PR opened).
3. It does not land the PR. Before the push it checks its inbox with `/omni:ledger-msg`. Once the PR
   is open it sends ONE MSG to `landing-controller` through `/omni:pr-handoff`, carrying the PR, the head
   sha and `needs=land`. That skill also fills in the `from=` and `id=` cells the grammar requires.
   The lint does not check `pr=`, `head=` or `needs=`, so the sender checks that all three are there
   before the append. It never merges, arms, reruns or polls CI.
4. It writes its TERMINAL with `friction=none`, or `friction=<one line>` after the matching FRICTION
   row exists (`/omni:friction-record`), and stops. The TERMINAL also carries
   `closes-CLAIM=<token>`, where the token is the `CLAIM-TOKEN` that `onex-ledger` printed when
   the CLAIM was appended. The grammar makes that cell optional (the lint accepts a TERMINAL
   without it), but it is what ties the TERMINAL to the exact CLAIM it closes, and lanes on the
   ledger write it.

## Routes to

`/onex:preflight` (the runner), `/omni:way-of-working` (host modes and session start),
`/omni:ledger-write` (appends), `/omni:ledger-catchup` and `/omni:session-resume` (after preflight
passes), `/omni:ledger-msg` (the inbox before anything irreversible, and the one handoff MSG for a
finished PR), `/omni:lane-brief` (open CLAIMs and RULINGs before dispatch), and
`/omni:friction-record`. The committed standing rules live in ops_tooling_pkg
`lane_rules/lane-rules-block.md`.

## Known friction

- A zsh profile that exports `registry_root="${registry_root:-...}"` fills in the variable for every
  command a session runs. On such a host, step 2's `registry_root is unset` refusal never fires. The
  profile's default is used instead, and in a dry run that silently names the real registry. So a
  dry run always sets `registry_root` explicitly, and step 0's sandbox-marker guard is what catches a
  root that is not a sandbox. The sandbox cases run zsh with `-f` for this reason.
- `gh` keeps its sign-in under `$XDG_CONFIG_HOME/gh`. A dry run that points `XDG_CONFIG_HOME` into a
  sandbox, to exercise the per-user overlay fallback, makes `gh` look signed out. The full overlay's
  code-host sign-in check then prints a false `gh auth login` blocker. Set
  `GH_CONFIG_DIR="$HOME/.config/gh"` in the same command whenever you redirect `XDG_CONFIG_HOME`.
  The sandbox cases avoid this by building the stale overlay from the ledger-only rows, and by
  leaving `XDG_CONFIG_HOME` alone in the full-overlay cases.

- The runner prints a check's verdict, not its probe output. A failing `ledger_grammar` therefore
  says `probe exited 2`, and its fix line is the probe itself, which prints the real reason.
