---
name: lab-run
description: Place a test suite, build, lint or headless agent command on the pool host with the most free capacity and send it over the event bus. The pool is every lab host plus the launching Mac, which takes work only under the same load bar. Placement reads each host's capacity advertisement from the bus, the chosen host's serve process runs the command at the pushed sha, and the receipt (exit code, log path, output tail) comes back as an event. Refuses with exit 75 when every host is over the bar and never runs the command locally outside placement. Use for any test run beyond one focused file, any build, lint over a tree, and any lab-model code draft.
prosthetic: true
replaces_when: "the landing controller and the pre-PR verify lanes place their own work on the lab through the same picker, so a lane no longer chooses a host or types a command to reach one, on two consecutive weeks of lane reports."
restored_from: "none. New tool, from the operator direction of 2026-09-29 that work also runs on the other lab machines, and that this must be automatic and not something the operator remembers."
ticket: OMN-20105
argument-hint: "--via bus --lane <lane> --repo <repo> --ref <pushed branch> -- <command...>"
---

# Lab run (prosthetic)

The launching Mac is one machine of five. On 2026-09-29 it sat at load 40 to 69 on 24 cores while
h908 sat at 1 on 32. This skill is the one way a lane puts heavy work on the pool. Lane briefs
carry it as part 3a.10, `lane_brief.py check` refuses a brief without it, and the user-level
heavy-work guard refuses a heavy Bash command on a host with no headroom and prints this command.

## Run it

Push the branch first. The unit runs at the pushed sha; a working tree is never shipped.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/onex_lab_run.py" --via bus --lane "<lane>" --repo "<repo>" \
  --ref "<pushed branch>" -- <command...>
```

`--via bus` (OMN-20105): the runner resolves the pushed sha, then `python -m
omnimarket.lab_work.cli run` listens for each host's capacity advertisement on the bus lane the
host table names (`bus_lane:`, today `lane-s`, the lab-host-a CI bus (OMN-20213)), places the unit on the eligible host with the
lowest load per core, publishes it on `onex.cmd.omnimarket.lab-work-unit-requested.v1`, and waits
for its receipt on `onex.evt.omnimarket.lab-work-unit-completed.v1`. The host's `onex lab-work
serve` fetches the sha, runs the command in a detached worktree and keeps the log. The
interpreter is `ONEX_LAB_WORK_PYTHON`, else `$ONEX_DISPATCH_VENV/bin/python`.

`--via ssh` is the interim path: a probe of every host over ssh (cached for
`ONEX_LAB_RUN_READING_TTL` seconds, default 15), then an ssh run. Use it only where a host does
not serve the bus yet, and say so in the report.

**The one automatic fallback (OMN-22560).** When the bus placement exits 69 with `placement: refused
(could_not_check)` and `the lab host table could not be read` (the packaged host table is ahead of the dispatch venv's
host-row model) and no unit was sent, the runner prints one line naming the cause and re-places the command once over ssh,
then returns that run's exit code. That refusal ran nothing, so the retry cannot run a unit twice. No other refusal falls
back: exit 75 (every host over the bar), a usage error, a silent bus (its 69 names the broker) and a bus run that started
(a `lab-work: sent` line) keep their exit code, and the retried run never falls back again.

```bash
... --via bus -- uv run pytest tests/ -q                     # a broad suite of your PR
... --via bus --need claude-login -- claude -p "<task>"      # a headless Claude run (h907 today)
... --via bus --dry-run -- true                              # the placement only
... --via ssh --hosts                                        # every host's reading over ssh
```

- `--lane` is required (or `ONEX_LAB_RUN_LANE`).
- Codex runs on the operator Mac and on any host the shared lab host table marks `codex: true` (today h907), per the operator rulings of 2026-10-01T01:07:53Z and 2026-10-01T03:51:23Z (OMN-20106, OMN-20240). `delegation_step.py code` skips it on any other host and routes lab code drafts to `onex code-edit run` through `delegation_step.py code`. The node receives writable globs and named argv checks, split with shlex and run without a shell in the worktree; each model turn is an `onex delegate` run. A loop counts as one delegated subtask and its turn run ids ride in `runs=`. Missing writable globs or checks skip the node route; a skipped or failed node route falls through to `lab_crush.py` as the interim fallback (OMN-20292 pending), then to GLM through Claude Code. A launcher passes the allowed set to a remote host in `ONEX_CODEX_HOSTS`. `--need codex` is not valid. The lane reads the diff and runs the focused tests, then records what it did with the draft: `delegation_step.py review --receipt <code receipt> --verdict accepted --head <pushed sha>` or `--verdict rejected --reason '<why>'`. The verdict is the draft's disposition, published as one bus event keyed by the Codex thread, code-edit loop id or the crush session (OMN-20012), so a lab code draft that was used and one that was thrown away are both counted.
- `--need <tool>` restricts to hosts that have the tool. `claude-login` for a headless Claude run is a login check,
  not a binary check (a Mac's keychain is locked over ssh).
- `--sha <40 hex>` in place of `--ref` runs an exact commit that is on an origin branch.
- With `--via ssh`, `--transport push` sends the sha over ssh instead of fetching it on the host;
  `auto` (default) fetches first and pushes when the host cannot fetch (a private repository).
- `--host <name>` names one host; the load bar still applies to it.
- Admission is the shared rule, `Reading.lane_admission_refusal` in
  `${CLAUDE_PLUGIN_ROOT}/skills/merge-drain/scripts/landing_placement.py` (OMN-20454): load per core, free
  memory, CPU temperature, the macOS CPU-idle rule, memory PSI, swap traffic and pressure, the same for the launching host as for
  every other. The shim (`${CLAUDE_PLUGIN_ROOT}/scripts/onex_lab_run.py`) asks that rule, picks the admitted host with the most
  free capacity and a free unit slot (a host whose advertisement shows `running_units` at `max_units` is passed over and named, OMN-21643), pins it with `--host`, and lifts the downstream `--max-load-per-core` and `--min-free-gb`
  so they cannot overrule it. This skill holds no threshold of its own; change the bar in `landing_placement.py`.
  `--via ssh` reads the full probe. `--via bus` reads the advertisements, which carry cores, load, running
  units, free memory and tools, so temperature, macOS idle and pressure are judged on `--via ssh` only until the
  advertisement carries them.
- `--via bus` also needs the host to have this launcher's lane guard installed (OMN-17427). The unit's stub execs the
  host's installed copy of the guard and exits 78 `LANE-GUARD-MISSING` in 0 s when it is absent, and an idle host that fails
  instantly stays the freest (host.example, at least 7 units, 2026-10-18 to 2026-10-20). Each serve process therefore advertises a
  `lane-guard:<sha256>` entry in its tools for every installed guard whose bytes hash to its directory name, and the shim
  refuses a host that advertises guards but not `lane_guard.host_sha256()` (`node_lane_guard_admission_compute`) with the line `host.example: lane guard 34ef8ab0 not installed`.
  An advertisement with no `lane-guard:` entry at all (a host still on the older serve) is admitted as not yet upgraded
  until every serve advertises; the unit's stub still exits 78 there if the guard is missing. Fix: `install_lane_guard.py
  install-guard --host <host>`. `--via ssh` ships the guard inline and needs no installed copy.

## The bounded scope (OMN-20199)

The shim wraps the command after `--` in the lane guard before it reaches `lane-k-run`, so on whichever host
it is placed, by the bus or by ssh, it runs in `systemd-run --user --scope` with `RuntimeMaxSec` = `--timeout`
(default 1800 s) plus 2 minutes (a longer ask than the 3 h hard cap exits 64), `MemoryMax` 8G (`--mem-max`,
ceiling 32G), `MemorySwapMax=0`, `CPUQuota` 400% (`--cpu-quota`, ceiling 1600%), and a unit named
`onexlane-<lane>-<id>`. Without systemd user scopes it falls back to `timeout --kill-after=60` plus `prlimit`.
`--mem-max` and `--cpu-quota` are this shim's own flags. There is no switch that turns the guard off: on 2026-09-30
an unbounded lane pytest ran 6h43m and took lab-host-a to load 1138. A memory kill exits 137 and a runtime kill 143;
the `LANE-GUARD-END` line in the command's stderr says which (`scope_result` `oom-kill` or `timeout`). The host
reaper stops anything a dead caller left. On `--via bus` the guard travels as a short `python3 -c` stub (a few hundred
characters, under the 20,000-character argv word a work unit allows) that runs the copy of this exact guard
installed on the placed host at `~/.local/share/onex-lane-guard/sha256/<sha256>/lane_guard_host.py` (the bytes of omnimarket's `runtime_lane_guard_host.py`). A host
without that copy answers exit 78 with a `LANE-GUARD-MISSING` line and runs nothing; install it with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/install_lane_guard.py" install-guard --host <ssh target>` (no `--host`
for the launching Mac). `--via ssh` still ships the source inline and needs nothing installed. Details: `${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/SKILL.md` step 5.

## Exit codes

| code | meaning | what you do |
| -- | -- | -- |
| the command's own | it ran on the placed host | the last stderr line is the receipt: host, sha, exit code, log path |
| 75 | every host is over the bar, short of memory, or lacks the tool | report the placement it printed; wait or stop. **Never run the command on the launching host instead.** |
| 69 | no host advertised on the bus in the window | rerun with `--via ssh` and say so; tell the orchestrator a serve process is down |
| 70 | the unit was refused or could not be fetched or run on the host | read `detail` in the receipt |
| 66 | the ref is not pushed to origin | push, then run again |
| 64 | usage, including a `--timeout`, `--mem-max` or `--cpu-quota` past its ceiling | fix the call |
| 78 | `--via bus` only: the placed host has no installed copy of this guard (`LANE-GUARD-MISSING`) | run `install_lane_guard.py install-guard --host <that host>`, or rerun with `--via ssh` and say so |

Cite host, sha and exit code in the PR body.

## Serving a host

Each pool host runs one serve process, under its pool name:

```bash
OMNIBASE_PATH=<dir holding omnimarket/config/ci_bus_lanes.yaml> \
  <venv with omnimarket>/bin/python -m omnimarket.lab_work.cli serve --bus-lane lane-s \
  --host-name <h906|h907|h908|h903|h904> [--rank-penalty 0.25] --work-root "$HOME/lab-run"
```

It advertises cores, load1, free memory, tools and `claude-login` every 10 s and runs only units
addressed to it. On a Mac the venv is built on `/opt/homebrew/bin/python3.13` (Operating Rule 11:
a uv-managed interpreter gets no LAN grant). The launching Mac serves too, so it takes work when
its load is low enough (operator ruling 2026-09-29). `--rank-penalty` keeps an evidence-lane host
(h907 0.25, h908 0.1, as in the ssh host table) last in the ranking without barring it. A host
whose serve process stops goes stale after 20 s and is never placed on. `python -m
omnimarket.lab_work.cli hosts --bus-lane lane-s --omnibase-path "$registry_root"` prints the pool.

## Limits

- A unit whose host dies after placement is answered by nobody; the caller gives up after the
  unit's timeout plus five minutes with exit 70.
- The lane-s login `lane-s-labwork` (SCRAM, OMN-20213) can read and write the lab-work topics, and every pool host
  holds it. The serve
  process runs only repositories of the allowed owners and only allowlisted executables, but
  `uv run` executes whatever the repository at that sha holds.

## Crush picks its model server per run (OMN-20240)

Crush remains the interim code fallback when the code-edit node route is skipped or fails; OMN-20292 is pending. Every non-local row of the lab host table that carries `model_port` serves the lab model there.
`lab_crush.py` reads each such server's load (`/metrics` in-flight requests, else `/slots`), adds the runs
this host has already placed and not yet finished (markers under `LAB_CRUSH_PLACEMENT_DIR`), and picks the
least loaded server whose window fits the measured request, then the lower table `penalty`. It prints
`LAB-CRUSH-ENDPOINT name=... load=... considered=N` and records the choice and every candidate in the
receipt under `endpoint`. `--base-url` or `LAB_MODEL_URL` pins one server. `python3
plugins/omni/skills/lane-brief/scripts/lab_endpoints.py crush-config` generates the `lab-qwen-<host>`
providers of `~/.config/crush/crush.json` from the table (other keys untouched; `--check` reports drift).

## Crush runs are scored (OMN-20233)

The interim fallback `lab_crush.py` (lane-brief, OMN-20292 pending) lists the worktree before crush starts, keeps the tool schemas crush offered
the model (`crush-tools.json`, from the context measurement it already makes), and after the run scores
the session with omnimarket's tool_use rubric through `plugins/omni/scripts/tool_use_rubric.py`. It
writes `rubric_verdict.json` and `lab-crush-receipt.json` into the scratch dir beside `crush-data`, and
prints `LAB-CRUSH-RUBRIC outcome=... failed=...`. The verdict is recorded only; it never changes the exit
code. The same scorer runs over a retained store by hand:
`python -m omnimarket.delegation.rubric.tool_use_score crush --db <scratch>/crush-data/crush.db
--declared-tools <scratch>/crush-tools.json --workspace-root <worktree> --workspace-manifest
<scratch>/workspace-manifest.json --out <scratch>/rubric_verdict.json`.

## Known friction (from prior runs)

- **`--via bus` exited 69 after 54 s on every unit while the packaged host table was ahead of the dispatch venv** (a
  column, `hosts.2.ledger_path`, that the venv's omnimarket host-row model forbids): the shim admitted h901, h902 and h907,
  then the downstream placement printed `placement: refused (could_not_check)` and `the lab host table could not be read`.
  The same class as OMN-22015 and OMN-22141. The shim now re-places that one refusal once over ssh. The focused
  probe of the route is `... --via bus -- true`: exit 0 means the bus placement works, and a fallback line in its stderr
  means the dispatch venv is behind the host table. → OMN-22560
- **`--via bus` refused every unit before placement (`argv words must be non-empty, NUL-free and bounded`).** The shim
  sent the lane guard's whole 31,150-character source as one `python3 -c` word, over the 20,000-character bound of
  `ModelLabWorkUnitRequest`; five lanes fell back to `--via ssh` on 2026-10-01. The bus path now sends a short stub
  that runs the host's installed guard by hash; the bound was not raised. → FRICTION 2026-10-01T02:04:37Z
  lane=vburn-W1-B3, FRICTION 2026-10-01T03:10:57Z lane=vburn-W1-B2, OMN-20105
- **The bus path was first proven on 2026-09-30 with omnimarket `tests/unit` (11,453 passed) placed
  on h904 over the bus.** `-n` with pytest-xdist fails collection on
  `tests/unit/routing/test_omn16200_clean_install_defaults.py`, whose parametrize ids carry a fresh
  uuid per process; ignore that file for an xdist run until it is fixed. → OMN-20105
- **The runner was first proven by running its own test suite on the h903 host.** A private repository
  fetched there without a credential problem; where a host cannot fetch, `--transport push` is the
  path. → OMN-20101
