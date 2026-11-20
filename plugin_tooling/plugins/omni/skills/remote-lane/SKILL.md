---
name: remote-lane
description: "Run one orchestrator lane as headless claude -p on the lab host with the most headroom instead of the launching Mac. Reuses the landing controller's placement (pool probe, placement lock and slot markers) and its ssh transport. Gives the lane the launching host's plugin set, so /omni: and /onex: skills and the onex hooks work there. Streams the lane's log back, writes the lane's CLAIM (with host=) and TERMINAL from the launching host, and leaves a local JSON receipt with the lane's final message. Skips a host whose Claude account hit a usage limit (the controller's `.limited-<host>` marker) and uses the launching host as the last placement after every lab host with a free slot, under its own slot cap and its load and memory bar; exit 75 means no host with a Claude login has a free lane slot. Use when an orchestrator workflow wants a lane off the Mac (host 'lab'), and for any lane brief that needs no local-only state."
prosthetic: true
replaces_when: "the event-bus work placement (OMN-20105) carries a headless Claude lane unit with the plugin set, the CLAIM relay and the receipt, so an orchestrator places a lane by publishing it and no ssh runner is left."
restored_from: "none. New tool, from the operator question of 2026-09-30 whether lanes can use claude -p on the other lab machines."
ticket: OMN-17427
argument-hint: "--brief <file> --lane <lane> --ticket <OMN-n> [--pr <repo#n>] [--cause <repo>:<check>] --model sonnet|opus|glm|codex|code-edit [--risk-class doc|test|lint|small-fix] [--writable <glob>] [--check <NAME=COMMAND>] [--context <path>] [--max-turns <1..40>] [--base-url <GLM endpoint>] [--host h908] [--repo <repo> [--ref <branch>|--sha <40 hex>]] [--parent <orchestrator lane>] [--lane-claim] [--detach]"
---

# Remote lane (prosthetic)

Agent-posted Linear comments have `actor: <lane> (<model>)` as the first line.
Lane and model come from the actual execution identity, never the Linear account author.
Every posting recipe, comment body file and `save_comment` or `create_comment` body carries
that line before the comment text. Human operator comments without an actor line remain
human even when they share the account used by an agent.

Every orchestrator lane's Claude ran on the launching Mac, while h907 and h908 (32 cores each) sat
mostly idle. This skill runs a lane's brief as `claude -p` on a lab host instead.

Task metadata for placement (OMN-20513): a column-zero `Required host: h907` line pins the
brief to that pool host. A `Host-local inputs: h907:/staged/corpus.jsonl` line also pins it;
multiple shell-quoted paths may follow, with an omitted host prefix using `Required host`
or `--host`. Inputs may be absolute or rooted at `~/`, `$HOME/` or `$registry_root/`. Conflicting
hosts, empty declarations and paths without a host are refused before placement; missing or
unreadable inputs are refused on the selected host before workspace preparation and engine launch.
A merge-sweep diagnose lane pins a host only by the same lines (OMN-17427): the merge-sweep workflow writes `Required host:`
when the plan pins the lane to the controller host for a controller reason, and a floor-only diagnose lane carries none and places by the pool.
Fenced examples and ordinary prose do not declare requirements. Codex placement uses the
shared engine preflight, including login, quota and sandbox readings. A host-limited lane's
relayed TERMINAL carries `limit-kind` and `limit-reset` from its receipt.

Claude quota recovery runs through `node_lane_placement_recovery_effect` before the job ends.
The existing account selector marks the exhausted account and verifies another token;
the runner retries Claude, then Codex, then GLM when the lane declares an existing GLM
`--risk-class`. Each attempt has its own run id and receipt. The original receipt records
the attempts, engine transitions and exact ROUTE lines before and after rewriting; the
authored brief stays intact. Ordinary engine failures are reported without replaying work.
`Required engine: claude`, `Required model: opus|sonnet`, or `pinned=true` / `fallback=none`
on a ROUTE line keeps work on Claude and queues it when Claude has no capacity.
Only column-zero declarations outside fenced examples apply. GLM still requires its
declared low-risk class, and landing-controller work remains ineligible for GLM.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/scripts/onex_remote_lane.py" \
  --brief <brief file> --lane <lane> --ticket <OMN-n> --model sonnet --parent <orchestrator lane> [--repo <repo>]
```

`--ticket` is the ticket the lane's PRs are titled with, and the CLAIM's `ticket=`. Without it the runner reads
the brief's own CLAIM line for the lane (`| CLAIM | lane=<lane> | ... | ticket=OMN-<n> | ...`, the line
lane-brief renders), with any `pr=` cell on it. With neither it exits 2 `REMOTE-LANE-NO-TICKET` before anything
is placed or claimed, and a `--ticket` that differs from the brief's exits 2 `REMOTE-LANE-TICKET-MISMATCH`. There
is no default: a CLAIM under the session ticket owns none of the lane's PRs, so pr-handoff refused them with
`REFUSED 3 no-claim` and the lane wrote a second CLAIM by hand (OMN-17427, FRICTION 2026-10-01T14:42:27Z).

A lane that works named PRs passes each one as `--pr <repo>#<n>` (repeatable). The CLAIM then carries
them as its `pr=` field. A ticket owns no PR (OMN-19998), and a lab
host's worktree is invisible to the launching Mac, so without `--pr` the drain map and pr-land's
claim guard do not read the lane as the owner of those PRs (OMN-19846).

For each `--pr`, the runner reads the watcher's head ref and sha and uses the host's canonical clone
when it holds that commit. Otherwise it refreshes the branch ref in the host's bare cache and verifies
that the watcher's commit exists there. The receipt's `pr_heads` records `head_ref`, `head_sha` and
`fetched_sha` (also populated when the commit was already local). An unreadable
watcher head or a failed fetch stops the run before the engine starts (OMN-21018).

Each dispatch saves the brief's bytes in a private directory before placement, recording its path
in `brief_copy` and its digest in `brief_sha256`. The detached child carries the dispatch digest;
the runner checks the source and saved copy again immediately before engine start. A changed or
missing brief ends `status: brief-changed` without starting the engine (OMN-21018).

A cause lane passes `--cause <repo>:<check>` (repeatable), and the CLAIM then carries each value as a
`cause=` cell. The runner also takes a `cause=` cell from the brief's own CLAIM line for the lane. A
malformed value exits 2: argparse for `--cause`, `REMOTE-LANE-CAUSE-INVALID` for the brief. Queue-status and
the landing controller read a shared red as OWNED only by a live CLAIM whose `cause=` cell names it;
the runner writes the lane's CLAIM itself, so a brief's CLAIM line alone never reached the ledger (OMN-20418).

`--effort low|medium|high|xhigh|max` sets the Claude or Codex client's effort. The code-edit engine
has no client and refuses the flag. When the brief carries a `ROUTE: band=<B> score=<n> ... model=<m>
effort=<e>` line (routing rubric W4, OMN-17427), a `--model` or `--effort` that differs from it exits 78 with
`REMOTE-LANE-ROUTE-MISMATCH field=<model|effort>` before anything is placed or claimed, an omitted `--effort`
takes the route's for Claude and Codex, and the receipt records `band`, `score` and `effort`. A brief with no ROUTE line still runs:
the runner warns `REMOTE-LANE-ROUTE-MISSING` and the receipt's three fields are null. The refusal of a missing
ROUTE belongs to the dispatch gate, not to this runner.

**Opus needs an escalation reason (OMN-21396).** `node_lane_model_policy_compute` admits an Opus lane only with
`complexity:<B4 or above>` or `sonnet-failed:<run or lane>` (RULING 2026-10-28T13:32:09Z). `--escalation-reason <value>`
carries it; without the flag the runner takes the ROUTE line's own `escalation_reason=`, else `complexity:<band>` for a
band of B4 or above. The reason goes to the placement request, so an Opus lane with one runs on a lab host, and onto the
`escalation_reason=` cell of the CLAIM and TERMINAL rows . An
Opus dispatch with no reason, or an invalid one, exits 2 with `REMOTE-LANE-OPUS-REASON-MISSING` or
`REMOTE-LANE-OPUS-REASON-INVALID` and the fix, before anything is placed, claimed or queued. A Sonnet lane sends none.

The lane's final report declares its work disposition on an unfenced `LANE_RESULT outcome=<value>`
line before `DELEGATION`: `blocked`, `partial`, `handed-off`, `done`, `skipped-owned` or `unknown`.
An explicit `TERMINAL outcome=<value>` line or a JSON report with a top-level `outcome` is also read.
Absent, invalid or conflicting declarations yield `unknown`; a zero engine exit never supplies `done`.
The receipt's `status` records engine execution and its `outcome` records work disposition. Engine errors
remain `failed`, delegation validation still applies, and the existing background-waiting guard applies
only when no valid work disposition was declared.

A Codex handoff refusal overrides the engine's earlier work declaration: the runner passes the
observed `blocked` declaration and the engine's delegation evidence to the closing node, records
the refusal in the log and receipt, and sends its existing parent notice with PR and head. The
runner exits nonzero with `status: blocked`; a zero handoff leaves the engine's declaration intact
(OMN-21018).

A lane that ends `blocked` also puts `BLOCKER: <one line: what stopped the work, with its evidence>` on its own
line before `LANE_RESULT`. The runner writes the last such line (one cell, at most 300 characters) as the
TERMINAL's `blocker=` cell, and for a handoff refusal it observed, the refusal's PR, head, rc and text. A blocked
lane whose report has no `BLOCKER` line, or one that is empty, a placeholder or only the runner's closeout text,
is not written as blocked: the TERMINAL is `outcome=unknown` with `class=blocked-unstated`, and the runner
echoes `REMOTE-LANE-BLOCKER-UNSTATED`, so the ledger tells a lane with a stated blocker from one without
(OMN-20872).

**The remote-lane nodes (OMN-20669).** Placement, the closing outcome and the sha a lane builds from are
asked of omnimarket's `node_remote_lane_compute`, `node_remote_lane_close_compute` and
`node_remote_lane_effect`, through `onex node <name> --input <file> --output receipt`
(`ONEX_REMOTE_LANE_NODE_COMMAND` overrides the command; the default is `$registry_root/omnibase_infra/scripts/onex node`).
Placement and the closing outcome are the nodes' alone: live receipts showed parity (over the 1344 most recent
receipts on the launching host on 2026-10-11, placement 1292 match and close 852 match, no mismatch), so the
runner's own placement and closing functions are deleted and it acts on the node's answer. A placement node that
is unreachable or fails, or names a host nobody read, places nothing: the lane ends `status: node-unavailable`,
exit 75, with `REMOTE-LANE-NODE-UNAVAILABLE decision=placement` and the error. A closing node that cannot answer
closes the lane `unknown` (`failed` when the engine failed), never `done`, with
`REMOTE-LANE-NODE-UNAVAILABLE decision=close`. The landing ref stays on the parity gate (5 mismatches in the same
receipts): the runner acts on the ref node's answer only when it equals its own, and an unreachable, failing or
disagreeing node leaves the runner's sha standing. The receipt's `node_parity` lists each decision with its
verdict (`acted` for placement and close, `match`, `mismatch` or `unavailable`), and the log prints one
`REMOTE-LANE-NODE-PARITY` line each. The suites run the two nodes' real handlers in process
(`tests/remote_lane_node_double.py`, at the omnimarket commit `landing_decision.pin.json` pins), so a suite with
a node's handler removed fails.

**A missing clone or hook never refuses a host (OMN-19998).** A clone missing from the registry root, a clone behind its
origin tip and a clone without its pre-commit hook are repairs in the lane's parity verdict
(`LANE_PARITY_NEEDS.provision`), not refusals. Before the lane starts, the runner provisions them on the host the
placement node picked (`place_provisioning`): it clones the repository from the organisation into the registry root
(beside it for `ops_tooling_pkg` and `docs_repo`, `landing_placement.BESIDE_ROOT_CLONES`), fast-forwards
a clean clone that is on its default branch, and installs the pre-commit hook. Each provision prints
`REMOTE-LANE-PROVISIONED lane=<l> host=<h> item=<clone:|hook:repo> kind=<clone|fast-forward|hook>` and rides in the
receipt's `provisioned`. A host whose provisioning fails is refused with the error (`REMOTE-LANE-PROVISION-FAILED`, the
receipt's `provision_failed`, a `provision:` item in its PARITY-FAILED text), its slot mark is released and the lane is
placed again on the next host; a lane ends `no-host` only when no host can be made ready. A dirty clone, a clone on
another branch and a repository without a `.pre-commit-config.yaml` are not touched: that is the failure. Every other
parity failure (gh, the dispatch venv, a plugin tree) still refuses the host. A landing worker does not provision.

The runner does these steps in order:

1. **Placement.** It reads the landing controller's pool (`landing_placement`: the shared lab host
   table, each host probed for cores, load, memory and live logins). It takes the placement lock and
   writes a slot marker in the controller's placement directory, so remote lanes and landing workers
   count against the same slots. The host is the placement node's answer on those readings and the host
   marks, taken under the same lock. Only a lab host whose probe reads `login=claude` and that has a
   free slot qualifies. The launching host is the last placement, under its host pool row's `cap`
   (`LOCAL_LANE_SLOT_CAP = 6` when the row names none), `LOCAL_LOAD_PER_CORE = 0.75`, the cores its row's
   `unit_cores` charges each further unit (`WORKER_COST_CORES = 4` when the row names none), and the
   same CPU idle, memory, macOS pressure and swap bars as a lab host
   (`RULING 2026-10-02T11:39:15Z lane=orchestrator-0c2f`; the Mac Studio's row raises the cap and the
   unit charge under `RULING 2026-10-11T16:48:49Z lane=orchestrator-8e80`, OMN-20864). `--host <name>`
   pins one host, which must still qualify. A pin is a requirement (OMN-21718): when the pinned host takes no lane (no free
   slot, an admission bar, a usage limit) the lane is placed on no other host. The runner prints
   `REMOTE-LANE-PIN-REFUSED lane=<lane> pinned=<host>: <why>`, writes the receipt's `pin_refused` cell and ends exit 75
   `no-host` with the pinned host and the refusal in the reason, and the lane queue holds it for that host.
2. **Plugins.** Every plugin enabled in the launching host's `~/.claude/settings.json` outside the
   official marketplace is resolved to its GitHub repository and the commit the launching host has
   (`omni`, `onex-overlays`, `onex` and `typesafe` on the operator's Mac). For organisation plugins,
   extraction prefers the host canonical clone when it holds the commit. Otherwise the bare cache
   supplies it, fetching missing commits. Each extracted tree is cached at
   `~/lab-run/plugins/<repo>-<sha12>`, and the lane loads it with `--plugin-dir`.
   A tree with a root `uv.lock` gets `uv sync --frozen` before the lane starts, so the onex hooks never
   resolve a half-built `.venv` (OMN-17427). A failed sync refuses the lane (exit 70) with `PLUGIN-VENV-FAILED`.
   The commit is the one the launching host has installed: the plugin's `gitCommitSha` in the host's
   `~/.claude/plugins/installed_plugins.json` (OMN-17427). A branch install (`install-tree --with-installed`)
   therefore reaches the lab lanes at once, without waiting for a merge. That commit is an install-tree merge commit that only
   the canonical clone holds, so the runner ships it to the host as a gzip archive of its tree over the host channel's stdin
   (nothing is pushed to the repository, and the host never fetches it by sha); a host copy that cannot archive the commit
   prints `PLUGIN-FETCH-FAILED`, and the archive is shipped then too;
   the receipt's `plugin_shipped` says what it did. The receipt names the marketplace commit as `behind` when it differs and
   the install record's commit as `installed`; the throughput tick prints `MISSING lane-ship:<lane>` for a lane of the last
   six hours whose shipped commit is not the one its receipt says was installed (never hand-replace a tree under
   `~/lab-run/plugins`). The record is read again after every plugin step, because installs land several times an hour and the
   step takes minutes: a record that moved is a new resolution and a new step (twice at most), and a record still moving
   refuses the lane (exit 76) with `REMOTE-LANE-PLUGIN-MOVED` naming each plugin and both commits, so a lane never starts on an
   older commit than the one installed. The receipt's `installed` is that single read and `plugin_moves` lists each move seen.
   Only a plugin with no recorded commit takes the older rule:
   when its marketplace clone tracks the default branch of the canonical clone `$registry_root/<repo>` and
   is behind it on the plugin's directory, the merged commit ships instead and the receipt names the
   marketplace commit as `behind`. A running lane keeps the tree it loaded; a marketplace on another branch keeps its commit.
   Uncommitted local changes are not shipped: the receipt marks such a plugin `dirty: true`. The
   hook mode follows the launching host's `OMNICLAUDE_MODE`.
3. **Workspace.** With `--repo`, preparation uses the host's resolved `$registry_root/<repo>` canonical
   clone when it holds the requested sha, with no GitHub fetch. Otherwise it fetches into
   `~/lab-run/repos/<repo>.git`. The receipt records `source=host-clone` or `source=github-fetch`
   and the owning `clone` path. That owner is persisted in the run context for worktree creation,
   collection and cleanup, including when the canonical clone catches up during preparation.
   Both paths add a detached worktree with the repository's commit hooks. With
   no repo, the lane gets an empty scratch directory. Both are removed at the end unless you pass
   `--keep-remote`. A repo worktree is checked first (OMN-20281): one with uncommitted changes (untracked
   files included), commits beyond its start sha, or a branch with no upstream is **never deleted**.
   Clean-but-unpushed commits are pushed to `wip/<lane>-<run>` and the worktree is then removed; uncommitted
   changes, or a failed WIP push, keep the whole directory. The receipt's `workdir` says which
   (`clean`, `wip-pushed` or `kept`, with the branch or the reason), and `REMOTE-LANE-WORKDIR` is echoed.
4. **Environment and ledger.** Before anything is created on the host, the runner resolves the host's
   own registry root: its `registry_root` when that holds an `omnibase_infra` clone, else
   `~/Code/registry_root`, `~/registry_root`, `/data/omninode/registry_root` (`--remote-omni-home` pins one). A host
   with none is refused (exit 70, `status: omni-home-unresolved`). The run script reads two named keys,
   path names, `DOCS_REPO_PATH` and `OPS_TOOLING_PKG_HOME`, from the host's own env file, `~/env-dir/env-file`
   (OMN-20637); no secret is taken from it. The file is read as data with `read_operator_env_file`'s rules, never sourced, so it can
   neither run anything in the lane's shell nor set a name the runner owns. It prints
   `REMOTE-LANE-HOST-ENV <file> keys=<names found>` (never a value), `-ABSENT` or `-UNREADABLE`; the lane
   runs either way. Every secret comes from the secret store (OMN-21672), and a host env file is only the store's bootstrap
   identity: the `remote_lane` overlay's flat `store_*` keys name the store project, environment and folder, the reader host
   that holds the store identity, the bootstrap names that identity file may hold (`store_bootstrap_env`) and the secret
   names (`store_lane_env`, `LINEAR_API_KEY`), so no host lists them. The reader host reads every listed name from the
   store and the value goes once over SSH stdin into a mode 0600 file `store-secrets.env` in the lane's context directory,
   which the run script reads as data, exports (it wins over anything the host or its login set) and removes. A value the
   target host's own env file holds for a listed name is ignored. The receipt's `store_secrets` and the line
   `REMOTE-LANE-STORE-SECRETS` carry the status, the names and `host-file-ignored=<names>`, never a value; a store that
   cannot answer leaves the lane running without the name, and the host file does not stand in for it. The lane's engine gets the registry root as
   `registry_root`, the orchestrator's `session.env` values (`--session-env`, else the `--parent` lane's
   file under `$registry_root/.claude_scratch/sessions/`; path values, and any key that names a place
   (`*_PATH`, `*_DIR`, `*_ROOT`, `*_HOME`, `*_FILE`), are dropped because they name the launching host's
   filesystem), the host's own `ONEX_STATE_DIR`, `ONEX_HOOK_EMIT_JOURNAL_DIR` and `ONEX_WORKTREES_ROOT`
   (all derived from that host's resolved registry root, also pinned in a per-run `--settings` file so a
   host's own `~/.claude/settings.json` cannot point the hooks at an unmounted or another host's path;
   OMN-20110), and `ONEX_LEDGER_PATH` pointing at a **read-only snapshot** of the
   canonical ledger (live file cut at the last whole row, plus `archive/*.md`) shipped at dispatch and
   removed with the run. The host's registry root is also given the workspace tier-1 runtime config
   (`ops_tooling_pkg/config/onex/runtime/runtime_config.yaml` in the sibling config owner, read from the launching host's copy) when it has none,
   because `onex delegate` through the wrapper refuses a bound root without it (OMN-19193); a present file is
   never overwritten, a file with credential-like text is refused, and the receipt's `runtime_config` says what
   happened. `lane_brief.py grep`, `inbox.sh` and `catchup.sh` work against it and answer
   as of the snapshot time (receipt `ledger_snapshot`). A brief names the launching host's paths, so the
   runner also writes the parent's session env where a brief sources it on the host,
   `$registry_root/.claude_scratch/sessions/<parent>/session.env` (the kept values, quoted, plus the host's own
   `registry_root`; a file the host wrote itself is never overwritten; receipt `session_env.remote`), and the
   footer names that file and the host's `lane_brief.py`, `inbox.sh` and `catchup.sh` in the shipped omni
   plugin (OMN-17427: on 2026-10-01 lanes on h908 found neither and could not check who owns a PR). `--no-ledger-snapshot` ships none. The runner also exports `ONEX_PARENT_LANE` (from `--parent`) and `ONEX_LANE_HOST` (the chosen host's name) beside `ONEX_LANE` before the engine starts and strips all three from a carried `session.env`; the gh shim writes them as `parent` and `host`, and `/omni:queue-status` joins `session:<id>` lanes to the lane identity registry and prints the `unattributed=` share (OMN-20420). When the host's row in the shared table declares `tenant_id`, the runner exports it as `ONEX_TENANT_ID` (shell and settings overlay, after the session env, which never carries that name), so every `onex delegate` in the lane is stamped with it before the host's own install identity, which stays as minted (OMN-18829: every lab row names the house tenant, operator RULING 2026-10-05T16:18:47Z). A lab host's
   own clone holds no live ledger (h907: a stale synced copy, h908: none), and a row written there would
   never reach the canonical file, so without the bus the launching host writes the lane's CLAIM
   (`host=`, `run=`, `parent=`) before the engine starts (no CLAIM, no lane, exit 70) and its TERMINAL
   (`outcome=done|failed`) when the lane ends. The lane is then told not to write the ledger, and the
   snapshot is mode 0444 so an append fails loud.
   The PR watcher's state ships the same way (OMN-20463): a copy at `<run>.ctx/pr-watcher-state.json`, exported as
   `ONEX_PR_WATCHER_STATE`, receipt `pr_watcher_snapshot`. While the engine runs, the launching runner
   refreshes the copy every minute over its existing SSH transport, even during silent tool calls
   (OMN-17427). It validates the live source with the same reader and installs by atomic rename,
   keeping the copy read-only and all watcher timestamps unchanged. `pr_watcher_refresh` records
   the last shipped tick, successes, failures and stop status. The refresh worker stops before
   context cleanup. A watcher or transport failure leaves the last copy to age; the reader's
   eight-minute limit and all full-inventory and exact-head checks still apply.
   **Through the bus (OMN-20281).** The shared host table names the hosts with a dev-lane bus login
   (`ledger_bus_lane`, `ledger_bus_python`: h907 and h908). On such a host the runner probes the pieces
   (the interpreter that imports `omnimarket.work_ledger_bus.cli`, the login in `~/.onex/config.yaml`, `uv`,
   an ops_tooling_pkg clone beside the registry with the bus mirror) and, when all are there, exports
   `ONEX_LEDGER_WRITE_VIA=bus`, `ONEX_LEDGER_BUS_APPEND_COMMAND`, `ONEX_LEDGER_HOST_NAME` and
   `ONEX_LEDGER_BUS_MIRROR=1`, makes the live snapshot file owner-writable, and mirrors its own CLAIM into
   it. The runner writes the CLAIM (`--lane-claim` changes nothing, OMN-24562); the lane writes its STATUS, MSG, FRICTION, HOLD and TERMINAL
   with `/omni:ledger-write`, `/omni:ledger-msg` and `/omni:pr-handoff`: each row goes to the canonical ledger
   through the one append command, with every check, and each accepted row is copied into the lane's copy
   so its own handoff gates see it. The launching host writes the TERMINAL only when the lane wrote none that
   closes its CLAIM; when the lane did, it writes one STATUS with the end status, the engine's exit code and
   the host closeout instead (no double relay). RULING and OPERATOR-CONSENT are accepted over the bus only
   from the ledger host's operator principal. A host that declares no bus, or whose probe fails, keeps the relay;
   the receipt's `ledger_write` is `bus` or `relay: <why>`, and `REMOTE-LANE-LEDGER-BUS-UNAVAILABLE` is echoed.
   The row's writer is the host's broker login, attested by the per-principal writer topic ACL; no credential
   is handed to a lane (OMN-17427). The runner exports `ONEX_LEDGER_RELAY_OUTBOX` to every lane as the
   broker-down fallback. `handoff.sh` queues the MSG and TERMINAL there only when the bus cannot be opened
   (exit `69` with no `OK` line from this append, result line ends `relay=queued:bus-unavailable`) or when the
   host has no bus (`relay=queued`); the end-of-lane relay below runs in both modes. Either is a landed handoff,
   not a failure; do not hand-relay it. Refused or unknown-outcome rows are never queued.
   On the relay the runner still mirrors its CLAIM into the lane's read-only copy (opened for that one append
   and locked again; the snapshot is taken before the CLAIM is written), so `pr-handoff`'s CLAIM gate finds it,
   and `handoff.sh` queues its MSG and closing row in `ONEX_LEDGER_RELAY_OUTBOX` (`ledger-outbox.rows` in the
   run's context directory). With no signing principal or a read-only snapshot, `onex_ledger.py` grammar-lints
   and queues the lane's own MSG, ACK, HOLD, RELEASE, STATUS, FRICTION, CORRECTION (with `corrects=`, `amends=` or `supersedes=`) and TERMINAL, mirrors into a writable copy,
   and prints `OK <TYPE> <stamp> ... relay=queued`; do not hand-relay a queued row (OMN-21000). At lane end the
   runner appends with every check and `via=relay:<host>`, skips rows already on the ledger, reports refusals
   on its closing row, and writes STATUS when a queued carrier TERMINAL landed (`ledger.lane_rows_relayed`).
   A lane that mints a child ticket and titles its PR with it runs `onex_remote_lane.py child-claim --child
   <OMN-n> [--worktree <path>]` on its host right after the mint (OMN-20845; the prompt says so). It refuses
   (exit 3) unless the child's live Linear parent is the ticket of the runner's CLAIM, and exit 5 when Linear
   cannot be read; otherwise it writes the CLAIM `ticket=<child> | parent_ticket=<carrier>` into the lane's copy
   through the same mirror script the runner's CLAIM takes, and queues the same row in the outbox, ahead of the
   handoff rows. The relay appends the lane's own child CLAIM for its carrier, in its queue place, so it lands
   before the handoff MSG. Each one is proved against Linear again first, and one that is not proved is
   left out (`REMOTE-LANE-CHILD-CLAIM-REFUSED`, receipt `ledger.child_claims_refused`). A relayed TERMINAL of the
   child ticket closes the child CLAIM, so the runner still writes its own TERMINAL for the carrier CLAIM.
   The footer also makes text mandatory (OMN-17427): every PR comment, close comment, commit message and report goes
   through `merge-drain/scripts/landing_text.py` (GLM through Claude Code first, then the sanctioned `onex delegate`
   wrapper on the lab route, OMN-20844; the
   omni plugin is found by its installed name, `omni@<marketplace>`: a bare-name lookup missed it and told every
   lane to pass `onex delegate` the `--prompt-file` and `--out` flags it does not take), and the
   lane ends its final message with `DELEGATION delegated=<n> runs=<ids>` or `DELEGATION delegated=0 reason=<r>`,
   `<r>` one of `no-text-or-code`, `route-refused:<status>`, `route-unavailable:<run id>`, `read-only-lane`;
   the launching host puts that on the TERMINAL. Delegation is a required step of every lane (operator ruling
   2026-10-01): the runner appends lane-brief's own 3a.9 block (`lane_brief.delegation_block`, one source) to
   any brief that lacks it, and when the final text has no such line, or one with another reason or a count
   with no `runs=`, it closes the lane `outcome=rejected-no-delegation` (or `failed` for a lane that also
   failed), never `done`, with `delegated=0 delegation_reason=no-delegation-line`, echoes
   `REMOTE-LANE-REJECTED-NO-DELEGATION` and records `delegation: {outcome, problem}` in the receipt.
   **Not-attempted (OMN-20489).** The runner's own zero reason names what it knows. `route-unavailable:<run id>` is
   only for an `onex delegate` run whose routing returned no rung. A lane that ended with no delegate call on record
   (no DELEGATION line, or an engine that failed) closes `delegation_reason=not-attempted:<why>`, where `<why>` is the
   lane's end status (`host-limited`, `guard-runtime-max`, `crashed`, ...), `engine-<rc>`, or `no-delegation-line`; the
   runner's own attempt id is never a reason. Lanes are not told to declare `not-attempted:` in their DELEGATION line
   until the omnimarket close and admission nodes accept it (a lane's line still takes the four reasons above).
   **Contract before push (OMN-20864).** Both Claude and Codex prompts carry lane-brief's shared
   contract step before the engine preamble. It requires `contracts/OMN-<ticket>.yaml` before
   the first push for PR-capable lanes whose repo CI runs repo-evidence / dod-verify or deploy-gate:
   one `dod_evidence` entry per acceptance criterion and, where deploy-gate applies, a falsifiable
   deploy check scoped for the hosted runner; the push is refused without it. This also covers
   lab-fill and handwritten tick-fill briefs that skipped `constraints` or `check`, and Codex
   lanes whose launching host performs the push. A fenced or negated example does not count.
5. **Engine, inside the lane guard (OMN-20199).** `claude -p` runs with the token login,
   `ANTHROPIC_API_KEY` removed and the controller's compose guard installed, **inside a bounded scope**:
   omnimarket's guard program (`node_lane_guard_unit_effect/runtime_lane_guard_host.py`, the one copy, read from the omnimarket checkout the runner resolves; the plugin holds none, OMN-23900) `run` starts it in `systemd-run --user --scope` with a unit named
   `onexlane-<lane>-<id>` and `RuntimeMaxSec` = `--timeout-min` (default 90) plus 2 minutes (a timeout past
   the 3 h hard cap is refused with exit 2, never trimmed; a `--timeout-min` above 90 needs the brief's own
   `Timeout reason:` line, see "Time box" below), `MemoryMax` 8G (`--mem-max`, hard ceiling 32G),
   `MemorySwapMax=0`, `CPUQuota` 400% (`--cpu-quota`, ceiling 1600%) and `TasksMax`. Memory is enforced by the
   kernel inside the lane's own cgroup, so a runaway is killed there and the host is untouched, and every process
   the lane starts (a `setsid` child included) is in the scope and ends with it. Where systemd user scopes are
   unavailable (no linger, no user bus, no memory controller) it falls back to `timeout --kill-after=60` plus
   `prlimit`, and where neither exists (macOS) to a Python watchdog with no memory limit; the receipt's
   `guard` says which ran (`mode`, `linger`, the limits, how it ended, `scope_result` `timeout` or `oom-kill`).
   The compose guard refuses every declared lane, and admits a pre-PR pool slot (`omnibase-infra-lane-q`
   or `-2`) only to the lane that holds the slot's pool lease and, as an ancestor of the call, the slot lock
   `prepr_verify_lane.sh` takes (OMN-20770). Take the lease first, with the lane's own name as holder, then
   run `prepr_verify_lane.sh`, at least one second later (the guard refuses a lease taken in the same second as the
   lock holder started); a lease that expired and was taken again refuses the earlier holder on its next
   docker call, and `prepr_teardown_slot.sh` needs the lease live too.
   A watchdog ends it at the same runtime limit or, with no
   follower for 15 minutes, when the lease its follower touches goes stale. On a lab host the engine runs detached from
   the ssh session (OMN-19998): its stream goes to `run.out` in the lane's context directory and its exit code to
   `run.rc`, and the runner follows that file from a byte offset, reattaching after a dropped session (the receipt's
   `transport` gives the reattach count and each drop) and giving up only after 10 minutes without a working
   session. `ONEX_REMOTE_LANE_DETACH=0` keeps the engine inside the session as before. When the lane ends by any route (result, timeout, crash of this runner) the runner
   stops the unit and kills whatever carries its tag before the closeout and the TERMINAL, and the
   host reaper (`lane_reaper.py`, a systemd user timer every 10 minutes, installed by
   `install_lane_guard.py install --host <target>`) stops what even a dead runner left: a lane unit past its
   deadline, and any test process older than 3 h with no live lane. The reaper never touches a model server,
   docker or compose lane, the deploy agent, the Actions runner or sshd, and writes a FRICTION row per kill
   (queued on the host, appended by the next runner that touches it). A lane the guard ended at its runtime or
   memory limit is `status: guard-runtime-max` or `guard-memory-max`, exit 1. There is no switch that turns the
   guard off. Admission (one rule, `landing_placement.py` `ADMIT_*`): a host with under 10 GB of memory
   available (the lane's 8 GB MemoryMax plus 2 GB headroom) takes no lane; a Linux host with more than 25% of its swap
   in use takes none while it is short of memory now (PSI memory some avg60 over 5%, else pages swapped out during the
   probe's one-second sample); a Mac takes none at `kern.memorystatus_vm_pressure_level` 2 (warn) or above. A host
   whose link loses over 20% of the fifty pings the launching host sends it beside the probe in two consecutive reads
   takes none (`LINK-LOSS`; the policy is the `node_link_gate_compute` node, h904 lost 40-80% on 2026-10-01 and its ssh-link
   timed out on most attempts). The reads are kept per host by `node_link_history_effect` in `link-loss.json` of the placement
   directory; reads under a minute apart count as one and a read older than 30 minutes is forgotten. One lossy read never benches
   a host: host.example was refused on 2026-10-18 for one lost ping of ten. Loss over 5% (`LINK-DEGRADED`) only ranks the host after
   hosts with a cleaner link, and it still takes a lane when no better host has a slot; a failed ssh-probe benches it as ever.
   A unit delivered over the event bus (`--via bus`, `Reading.bus_delivered`) is not judged by the ssh-link at all. A Mac takes none unless its probe's
   `LANGRANT` line reads `ok`: a TCP connect from its python3 back to the ssh peer's address that does not fail
   with "No route to host", which is what a process without the macOS Local Network grant gets
   (`MAC-LAN-GRANT-MISSING`); its Claude login is required as for every host. This
   is on top of the busy-core slot arithmetic. A host whose `~/.claude/settings.json` does not set `includeCoAuthoredBy`
   to false takes no lane and no landing worker, refused as `COAUTHOR-TRAILER-NOT-DISABLED` (`landing_placement.coauthor_refusal`,
   read by the probe's `COAUTHOR` line; h908 lacked it on 2026-09-30 and its commits carried a Claude co-author trailer).
   A host whose hook scripts do not parse under its own `/bin/bash` takes no lane and no landing worker of any engine
   (`HOOK-PARSE-FAILED`, `landing_placement.Reading.hook_parse_refusal`, OMN-20961): the probe's `HOOKPARSE` line runs
   `bash -n` over the `hooks/` tree of every enabled installed plugin and over the plugin trees this runner ships there,
   and a check that cannot run reads `unknown` and refuses too (`HOOK-PARSE-UNKNOWN`, fail closed). After the plugin step the
   runner checks the trees it just shipped and ends `hook-parse-refused` (exit 76) before the engine starts when they fail.
   omniclaude 3fc14b178 shipped a guard hook macOS /bin/bash 3.2 cannot parse on 2026-10-11, and seven lanes and about
   twenty landing workers went to h903 and did nothing.
   The launching host is judged by the same hook parse, memory, pressure and settings (`COAUTHOR`) bars and by its load per core, but not by the two link bars (`LINK-LOSS` and `MAC-LAN-GRANT-MISSING`).
   `REMOTE-LANE-NO-HOST` prints each refusal's reason. Its `stream-json` output streams back line by line: a summary goes to
   stdout and every event goes to `<receipt>.log.jsonl`.
   For Codex scratch lanes, the sandbox also grants the host clones' Git `objects/`, `refs/`,
   `logs/refs/` and `worktrees/` directories (registry children, the sibling `ops_tooling_pkg`,
   and the lane's own repository's common directory). Peer bare caches under `~/lab-run/repos` are never
   granted: on Linux Codex passes its whole permission profile as one argument, about 1.1 KB per root, and
   the kernel refuses one over 128 KiB, so 140 roots on h907 failed every probe with "Argument list too
   long" (OMN-17427). A failed probe's receipt carries the probe log's tail (`codex_sandbox_probe.log_tail`).
   The pool probe runs this same roots program and write probe over the host's registry root with eight spare roots (the
   permission profile on h907 measured 124.7 KiB of the 128 KiB ceiling on 2026-10-18), so a host where the lane's
   probe would fail reads `CODEX-SANDBOX-UNWRITABLE: ... (rc=1 Error: Argument list too long ...)` in placement, reports no free
   Codex slot, and is never chosen for a Codex lane (both render their lines from `node_codex_sandbox_probe_compute`).
   They are resolved and materialized before launch, so a lane
   can create, commit, push and remove its own registry worktree even when its starting directory
   is scratch. The canonical source tree, Git index, `HEAD` and config remain read-only; peers'
   worktree directories are not granted. No canonical fetch is needed or authorized by this grant.
6. **Closeout.** A lane's worktrees live on the host, so the host removes them. The lane is told to make
   any tree at `$registry_root/worktrees/<lane>/<repo>`. When the engine ends, and before the TERMINAL
   is written, the runner runs the host's own `onex-lane-closeout --lane <lane> --worktree <tree>` for every
   tree under that directory (`ops_tooling_pkg` is installed on every lab host, beside the registry root
   or beside its resolved target, and kept current by the host's fast-forward timer). The command archives
   the tree, verifies it, removes it and prints the disposition; the operator's consent row of
   2026-09-30T15:01:08Z (ledger line 18420) is the authority, read from the lane's ledger snapshot. A tree
   whose process is still ending is retried; a tree that is kept (a live process, a merge in progress) is
   reported, never forced. The same guard as the workspace's runs first on each tree (OMN-20281): a tree
   with uncommitted changes, unpushed commits or a branch with no upstream never reaches the command; its
   commits go to a WIP branch (named in the `closeout` note), or, with uncommitted changes or a failed
   push, the line's cell is `kept:<tree>:<reason>` and the tree stays. The dispositions go in the receipt (`closeout`) and, without a `worktree=` cell,
   in the TERMINAL text. A host without the command reports `not installed` and leaves the trees. The
   directory is the ownership proof: a tree anywhere else is never removed. `--keep-remote` skips this step.
   A tree may sit at `<lane>/<repo>` or `<lane>/<ticket>/<repo>`. On a host whose registry is hollow a scratch
   lane adds its trees from a clone inside its run directory, so the trees go first and the run directory
   after. When the closeout keeps such a tree, the run directory is kept too (receipt `workdir` `kept`, reason
   `hosts-git-dir-of:<tree>`), so no tree is left with files and no git dir (OMN-17427).
7. **Receipt.** `~/.local/state/omni/remote-lanes/<lane>/<run>.json` (or `--receipt`) is written as
   `running` once a host is chosen, and is final at the end. It holds `host`, `duration_s`, `closeout`, `result`
   (the lane's final message), `is_error`, `engine_rc`, `plugins`, `readings`, the ledger
   timestamps and the log path.

`--detach` starts the run in the background and prints `DETACHED ... receipt=<path>`, then waits up to
`--placement-wait-s` seconds (default 90) and prints `PLACEMENT ...` as its last line (OMN-20840).
It returns 0 when placed or done, 75 for no-host (with the receipt's reason), the receipt's nonzero exit
code for another final failure (otherwise 1), 3 if still placing, or 70 if the runner died before placement.
`--no-placement-wait` returns at once with exit 0. Follow a placed or still-placing lane with `wait`,
which returns within `--max-s` seconds (default 540, under a Bash call's ten-minute cap):

```bash
# Bash timeout 600000 ms: each wait call returns within 540 s
python3 "${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/scripts/onex_remote_lane.py" wait --receipt <path>
```

A detached lane ending in any status but done sends one MSG to its `--parent` inbox
with status, host, exit and receipt path; the receipt's `parent_notice` says whether it was accepted.

When a lane ends `done`, `wait` also hands off, from the launching host and as the lane, each PR the lane
named and could not hand off itself (OMN-20463). The lab host's copy of the PR watcher state is older than the
lane's push, so `handoff.sh` there refuses with exit 5. The launching host's watcher state is live. `wait` skips
a PR the lane withheld or called a draft, a draft or closed PR, and a PR a handoff MSG already names. It retries
exits 4 and 5 on each watcher tick for 15 minutes (`--handoff-retry-s`). Pending handoffs end the call with exit 3,
and the next `wait` resumes them. The per-PR result is in the receipt's `wait_handoff`. `--no-handoff` turns it off.
The runner mirrors a queued CLAIM from the launching host's bus outbox; a lane whose ledger copy cannot get
its CLAIM is not started (OMN-20864). The detached runner also settles handoffs from the launching host without
a `wait` caller, retrying a `no-claim` refusal while the CLAIM is on its way to the live ledger, including a
Codex landing-step refusal recorded on an error receipt.

### The original instructions (OMN-20604)

Every lane, detached or not, records its original instructions before placement, so the lab job
supervisor (plan `beta/plans/2026-10-05-lab-job-supervisor.md`) can restart it from them. The record
is the plan's `lab-job-submitted` spec (topic `onex.cmd.omnimarket.lab-job-submitted.v1`, section
3.1): brief, engine, repo and full sha, time box, retry policy, done criteria, parent and ticket, plus
the lane, run id, attempt and the runner flags a restart repeats. It is written to
`<run_id>.job.json` beside the receipt, then handed to the plan's submit path
(`python -m omnimarket.nodes.node_lab_job_submit_effect submit --spec-file <file>`, or
`ONEX_LAB_JOB_SUBMIT_COMMAND`). The default submit passes `--bus-lane lane-s` and
`--omnibase-path "$registry_root"`: the CI bus lane and the registry root. The receipt's `job` says
whether it was sent; a refused submit prints `REMOTE-LANE-JOB-UNSENT` and never blocks the lane,
and the file stays as the outbox (a resubmitted `job_id` is a no-op). A record missing repo, ref,
parent or ticket stays in the outbox with `REMOTE-LANE-JOB-UNSENT` naming the gap: the supervisor's
spec requires them.

- `--done <criterion>` (repeatable; default `terminal_row`): `terminal_row`, `exit_zero`,
  `pr_merged:<repo>#<n>`, `check_passing:<repo>#<n>:<context>`. PR criteria are sent as
  `target` (`<owner>/<repo>#<n>`) and, for a passing check, `check_context`.
- `--max-attempts <n>` (default 2) and `--on-time-box continue|fail` (default continue).
- `--job-id lj-<16 hex> --attempt <n>`: a lane the supervisor dispatches keeps its job's id.

## THE RECEIPT RELAY

At close, the launching host copies the lane's cited `runs=` artifacts (`receipt.json` and
`run.json` when present) out of the lab host's registry into its own `$registry_root/.onex_state/runs/`.
A cited id with no onex delegate run but a harness-delegate receipt (GLM through Claude Code,
`.onex_state/harness-delegate/<id>/receipt.json`) has that `receipt.json` alone copied into the launching
host's `.onex_state/harness-delegate/`, where the delegation accounting reads it as GLM (OMN-20374).
Existing local run directories are never touched. One remote call per host handles all missing run
and Codex ids; a lane with everything already local makes none. Landing workers relay their successful
`delegation.jsonl` run ids the same way, even when the worker produces no result file. The code is
`relay_receipts` in `merge-drain/scripts/landing_placement.py`, which both callers already load.

A cited `codex=` rollout stays on the host. Its existence record goes under
`$registry_root/.claude_scratch/delegation-receipts-relayed/<lane>/`, with the host and remote path,
never the rollout content. Keep that root separate: `delegation_step.py` reads every JSON file
under `delegation-receipts/<lane>/` as the lane's own step receipt and would miscount a relay there.
Queue-status reads both roots. The runner records the relay summary as `delegation_relay` and any error;
the relay never changes TERMINAL cells, the lane's outcome or its exit code.

Backfill older TERMINAL citations through the shared lab host table (it prints one JSON report):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/scripts/onex_remote_lane.py" backfill-receipts --since 2026-10-02T00:00:00Z
```

Set `ONEX_LEDGER_PATH` and `registry_root`, or pass `--ledger` and `--omni-home`; neither has a guessed
default. `--hosts-file` overrides the shared table (`ONEX_LAB_RUN_HOSTS`), and `--codex-home`
overrides the local Codex root. Each available remote host gets one query for ids still unresolved.

## THE REPORT RELAY

A lane writes its full report to `$registry_root/.claude_scratch/reports/<lane>-<YYYY-MM-DDTHHMMZ>.md` on the host it
ran on, so a lane placed on a lab host left a report no one on the launching host could read. At close the
runner copies the lane's own `<lane>-<stamp>.md` files (regular files only, a symlink is skipped, at most 8 MiB
each) from that directory into the launching host's `$registry_root/.claude_scratch/reports/` under the same name, in
one remote call, never over an existing file. A lane that wrote no report leaves its final message there instead,
under the first line `<!-- No report file reached this host: ... -->`, so every lane has one readable report.
A lane that ran on the launching host makes no call. The code is the `node_lane_report_relay_effect` node
(`src/omni/nodes/node_lane_report_relay_effect`), which the runner loads. The runner records the summary as
`report_relay` and prints `REMOTE-LANE-REPORT-RELAY`; the relay never changes TERMINAL cells, the lane's outcome or
its exit code. It follows the receipt relay above rather than adding a bus event: the report is read on the
launching host, the runner already holds the connection to the host at close, and a second store for the lab
projection to serve would be a new bespoke surface.

## Code-edit engine (a lane on a lab-served model)

`--model code-edit` runs the delegated code-edit node through `onex code-edit run` (OMN-20293).
Each model turn is one `onex delegate` run on the deployed lane by the node's default route, and the
loop result names every delegate run id. The lane uses the same placement slots, guard, session
environment, ledger snapshot, CLAIM and TERMINAL as the other engines. This engine needs no Claude
client, token login, plugins or settings file. `--base-url` is available only for GLM; the launching
environment's `ANTHROPIC_BASE_URL` is ignored.

```bash
# Bash timeout 180000 ms: --detach waits up to 90 s for placement, then returns
python3 "${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/scripts/onex_remote_lane.py" run \
  --brief <brief file> --lane <lane> --ticket <OMN-n> --model code-edit \
  --writable 'src/**' --check 'tests=python3 -m pytest -q tests/test_module.py' \
  --context <context path> --max-turns 20 --repo <repo> --parent <orchestrator lane> --detach
```

The repeatable `--writable GLOB` is required for code-edit and refused on other engines. Checks are
repeatable `--check NAME=COMMAND` values; the node splits each command with shlex and runs it without
a shell in the worktree, so a check that carries `&&`, a pipe or a redirection is refused with exit 2. With no explicit check, the brief's first `FINAL-CHECK: <command>` line
becomes the check named `final`. A brief with neither is refused with exit 2. Repeatable `--context PATH`
values pass context paths to the node. `--max-turns` is 1..40, with a default of 20. The task file contains
the brief verbatim, without standing footers; a brief over 20000 characters is refused before placement.

The node prints one compact JSON result. An `accepted` loop ends the lane `done` (exit 0); other loop
statuses end it `code-edit-<status>` (exit 1), including `checks_failed`, `no_progress`, `budget_exhausted`,
`delegate_failed` and `infra_error`. A node that could not run ends it `code-edit-not-run` (exit 1).
The final message names the status, loop id, turns and number of changed paths, followed by
`DELEGATION delegated=1 runs=<comma-separated ids>`, or a `route-refused:<status>` reason with no ids.

The receipt has `engine: code-edit` and a `code_edit` block with the loop id and node status, turns,
delegate ids, changed paths, refusals, rubric outcome, writable globs, checks and remote loop receipt
path. Its `model_turns_without_run_id` counts the loop receipt's turns the model answered that carry no delegate run id (a turn the deployed lane refused before any model was reached is not one): a positive value exposes
a delegation defect. The full tree diff comes from the node's loop receipt, including untracked files,
and is saved beside the launching host's lane receipt as `<receipt stem>.diff`, with its path and SHA256
in `code_edit`. The worktree remains on the host exactly as the node left it, as a draft for owner review;
this engine has no commit, push, PR or worktree cleanup step.

## GLM engine (a low-risk lane on the GLM Coding Plan)

`--model glm --risk-class doc|test|lint|small-fix` runs the lane's Claude Code on GLM (`glm-5.3`) instead of the
shared Claude account (lane glm-lane-trial: three trial tasks finished with passing tests, in three to five times
the turns). The endpoint, the model and the key's name are the harness-delegate skill's declaration, so this is
the same Claude-Code-only route the z.ai terms allow; `--base-url` may repeat that endpoint and nothing else.

```bash
# Bash timeout 180000 ms: --detach waits up to 90 s for placement, then returns
python3 "${CLAUDE_PLUGIN_ROOT}/skills/remote-lane/scripts/onex_remote_lane.py" \
  --brief <brief file> --lane <lane> --model glm --risk-class doc --repo <repo> --parent <orchestrator lane> --detach
```

- **Refused (exit 2)** without a `--risk-class`, for a lane or `--parent` named `landing-*` (the landing controller
  and its workers), and for `--risk-class` on any other model. A brief whose ROUTE line names another model is a
  route mismatch (exit 78), as for any lane.
- **The key** is read on the lab host at launch, from harness-delegate's sources (the z.ai config dir that
  `setup-glm` writes, whose endpoint must be the declared one, else `LLM_GLM_API_KEY` in the host's infra env
  file), into an unexported variable set only on the engine's command. It is never on the launching host, in the
  brief, the run script, the settings file, the receipt, the log or the ledger. A host with no key ends
  `status: glm-key-missing` (exit 70) before the engine starts. Every streamed line passes harness-delegate's key
  redaction before the log, the echo and the receipt.
- **No Claude account is touched**: no OAuth token is exported, and a z.ai usage limit ends the lane
  `status: glm-usage-limit` (exit 1) without marking the host.
- **The receipt** carries `engine: glm` and a `glm` block (endpoint, model, risk class) beside `num_turns`,
  `duration_s` and `engine_elapsed_s`, so queue-status can compare GLM lanes with Claude lanes.

## Codex engine (a lane run as `codex exec`)

`--model codex` runs the lane as headless Codex instead of Claude Code (OMN-20363; the operator asked on 2026-10-02 why
the lab hosts ran only `claude -p` lanes). It is the same runner: the same placement lock and slot markers, the same
lane guard (`--timeout-min`, `--mem-max`, `--cpu-quota`), the same worktree, receipt, CLAIM and TERMINAL.

```bash
# Bash timeout 180000 ms: --detach waits up to 90 s for placement, then returns
python3 "${CLAUDE_SKILL_DIR}/scripts/onex_remote_lane.py" run \
  --brief <brief file> --lane <lane> --ticket <OMN-n> --model codex --repo <repo> --parent <orchestrator lane> --detach
```

- **Placement.** Only a host the shared lab host table marks `codex: true` (`codex_placement`, the operator rulings it
  cites), with a free slot under the same admission bar. The launching host takes a Codex lane only when its own row
  marks `codex: true`, judged on its lane bar and lane slots, with its Codex login read by the probe like a lab host's
  (`RULING 2026-10-11T16:48:49Z`, OMN-20864); a landing worker still never runs Codex there. No `login=claude` is asked of it,
  and a Claude usage-limit mark does not keep a Codex lane off a host. No such host with a slot: exit 75.
- **The engine.** `codex exec --json` at `model_reasoning_effort` high (or `--effort`, or the brief's ROUTE effort),
  with the config's default model and no model flag, in the lane's worktree. It is always sandboxed:
  `workspace-write` with network, plus writable roots for the worktree's git metadata, the run's context directory,
  `$HOME/.cache`, the host's own `UV_CACHE_DIR`, `PRE_COMMIT_HOME` and `XDG_CACHE_HOME` as its login profile sets them,
  `$ONEX_STATE_DIR` and `~/.onex` (OMN-19701), the lane's `$ONEX_WORKTREES_ROOT/<lane>` directory, and the two places
  every lane's delegation step writes: `$registry_root/.claude_scratch/delegation-receipts` and
  `~/.omninode/delegation` (the local delegation sqlite; OMN-17427, six h907 lanes ended done on a read-only
  file system at both), and `~/.local/state/omni/landing/placement`, the one directory `onex_lab_run.py --via ssh` writes
  its parity record, link history and slot markers to (OMN-21812; never `landing` or `~/.local/state`). Setup provisions the declared directories and the sandbox pre-flight probe writes a unique
  temporary file in every resolved writable root, including caches and Git metadata. A cache that cannot be
  provisioned refuses with its capability name and path; it is never silently dropped. Codex runs none of the
  Claude Code hooks, so there is no flag that turns the sandbox off.
- **Required write capabilities (OMN-19701).** Task metadata `Required capabilities: linear-write` in the brief,
  or the repeatable `--require-capability linear-write` argument, declares required Linear mutations. The Codex
  engine uses `approval_policy=never` for each invocation, including resumes. Such a declaration refuses before
  placement, remote provisioning or CLAIM with exit 96, status `capability-unavailable`, and the named capability
  in the output and receipt. An unknown capability in brief metadata also refuses. Generic standing rules and
  quoted examples do not declare task requirements. No operator Codex configuration is changed.
- **No ticket mint in a lab brief (OMN-21021).** A lane runs headless on a lab host, where the Linear MCP save
  path (and with it the ticket create gate) does not exist. A brief that carries the line `Mint authority:
  delegated by the orchestrator for exactly one ticket` as a line of its own, or asks the lane to create a ticket
  (`/omni:create-ticket`, `save_issue`, "mint a ticket"), is refused before placement, remote provisioning and
  CLAIM with exit 2, status `mint-refused` and `REMOTE-LANE-MINT-REFUSED` naming the fix: the launching session
  mints first and passes the id with `--ticket`. It is `lane_brief.py check --lab`'s refusal
  (`lab_mint_problems`), so one definition serves both. Comments, state changes and ruled criterion edits
  through the host's `LINEAR_API_KEY` stay admitted. A sentence that names the bus route (`onex ticket`, create-ticket
  section 9) is admitted too, unless it also names the Linear tool directly (`save_issue`, a Linear MCP tool); the
  grant line is still refused.
- **A brief with a task, a driver lane with its PR (OMN-17427).** Two refusals a session's own dispatch helper made
  are the runner's, before placement, remote provisioning and CLAIM, with exit 2: a brief that pastes the standing
  rules block but has no line of its own outside it, the 3a block, fenced examples, headings and the ROUTE and Parent
  lines (`brief-refused`, `REMOTE-LANE-BRIEF-REFUSED`, read with lane-brief's own prose readers), and a driver lane (`pf-drive-<repo>-<n>`, the lane a process-fix FIX names) with no `--pr`
  and no `pr=` cell on its brief CLAIM line (`driver-no-pr`, `REMOTE-LANE-DRIVER-NO-PR`, naming the `--pr` to pass). Both, and the mint refusal above, are
  `node_dispatch_brief_shape_compute` (`src/omni/nodes/`), which the runner asks before placement.
- **A PR-opening lane names its own ticket, not the umbrella (OMN-21301).** A lane with `--repo`, a repo on its brief
  CLAIM line or the contract-before-push step, whose `--ticket` or brief CLAIM ticket is the umbrella OMN-17427, is
  refused before placement, remote provisioning and CLAIM with exit 2, status `umbrella-refused` and
  `REMOTE-LANE-UMBRELLA-REFUSED`: the umbrella's one contract carries every umbrella criterion, so each PR titled with it
  spends up to 40 minutes in dod-verify. The fix is to pass a child ticket with `--ticket`, an existing open child or one
  minted with `/omni:create-ticket` (parent OMN-17427) in the launching session. When the daily create budget is spent
  (`lane_intake_budget`) and no open child fits, the brief carries `Umbrella evidence: lane_intake_budget` and the lane
  adds its own requirement and dod_evidence item to `contracts/OMN-17427.yaml`. A brief with no repo and no contract step
  is admitted. It is `node_dispatch_brief_shape_compute`'s fourth refusal.
- **The ticket's own words travel in the prompt (OMN-17427).** A headless lane has no Linear tool, so on
  2026-10-17 backlog lanes ended blocked on acceptance criteria they could not read. Before placement the runner
  reads `--ticket` from Linear once, with the launching host's key (its environment, else its own
  `~/env-dir/env-file`; never a brief's), and appends the `node_ticket_text_effect` block (`src/omni/nodes/node_ticket_text_effect`): title, state, description and
  criterion lines, quoted. No key travels to the lab host for it. The receipt's `ticket_text` records the read
  (`source=linear|brief|refused`) and the log prints `REMOTE-LANE-TICKET-TEXT`. A brief that already carries a
  `ticket-text: <ticket>` block is left as it is. A ticket the launching host cannot read, or one with no description,
  refuses the dispatch before placement, provisioning and CLAIM (OMN-20607; exit 2, status `ticket-text-refused`): the
  runner prints `REMOTE-LANE-TICKET-TEXT-REFUSED lane=<lane> ticket=<id> reason=ticket-unreadable|ticket-text-empty`,
  because a headless lab lane has no Linear key or tool, so a note telling it to read the ticket itself only ended nine
  lanes `ticket-unreadable` between 2026-10-17 and 2026-10-19. Every route through the runner takes it, the throughput
  tick's lab fill and the launchd lab fill included: they see a refused dispatch and send the lane again on a later tick.
- **The docs_repo clone.** The run script resolves it for every engine (OMN-20637): the host env
  file's `DOCS_REPO_PATH`, else the host's login profile, else `$registry_root/docs_repo`, else `$registry_root/../docs_repo` (the lab hosts keep it
  beside the registry root, OMN-21650), the first that is a clone, and prints `REMOTE-LANE-KB-PATH <path>`. A host with none runs the lane with the
  variable unset after one `REMOTE-LANE-KB-ABSENT` line; the clone is read, not a writable root. `--require-kb`
  makes that host refuse a Codex lane before Codex starts, exit 95 `kb-absent`.
- **Git in the worktree.** Codex makes the gitdir a cwd's `.git` link names read-only whatever the writable roots say,
  so the run script locks the worktree (`git worktree lock`'s file, with this engine's reason, so a peer lane's
  `git worktree prune` of the shared bare repo cannot remove it), sets the link aside and exports `GIT_DIR` and
  `GIT_WORK_TREE` at the same gitdir. The link is restored and the lock removed when Codex ends, and again at cleanup.
- **Commit outside the sandbox (OMN-19806 AC2).** Inside the sandbox some repository hooks cannot see the repository
  (omnimarket's contract-sweep-gate and test-deletion-parity-receipt-gate strip `GIT_DIR` and meet the sandbox's
  read-only `.git` placeholder). So Codex creates its branch, stages its change and writes `codex-commit.msg` and
  `codex-pr.md` (title, then body) in the run's context dir, and ends. The run script then, outside the sandbox and
  with the link back, runs `git commit` with every hook. When the log says `files were modified by this hook`, it
  first re-stages only paths already staged for that commit that now differ in the worktree, prints
  `REMOTE-LANE-CODEX-COMMIT restaged attempt=<n> hook=<ids> paths=<count>` and retries without resuming Codex
  (OMN-20864). Other hook failures, including a fixer that changed no staged path, resume Codex's own thread
  (`codex exec resume`) with the hook output. All retries count toward `CODEX_COMMIT_ATTEMPTS` (three commits in
  all). On success it pushes the branch, opens
  the PR through the source-control node (`onex scm pr-create`, `node_github_repo_write_effect` operation
  `pr_create`, against the landing branch read at dispatch; a lane's `gh pr create` is refused, OMN-20914; the body
  ends with `Closes <ticket>`, added before the create when it holds no closing line, and a lane with no ticket opens
  none: OMN-17427) and, on a bus host, runs `pr-handoff/scripts/handoff.sh --needs land` with
  `delegated=1 codex=<thread id>` (acknowledging the inbox only when no listed HOLD or MSG names the PR or the lane).
  The handoff reads the PR watcher's state, which cannot hold a PR opened seconds ago, so it exits 5 at first
  (OMN-17427, nine lanes on 2026-10-08). On exit 5 alone the run script waits for the state copy's `last_tick` to move
  (at most 150 s per wait, polled every 5 s) and runs the same handoff again, at most two waits; the line then reads
  `REMOTE-LANE-CODEX-HANDOFF rc=<n> retries=<waits>`. No handoff check is relaxed, and no other exit is retried.
  Each step prints a `REMOTE-LANE-CODEX-<STEP>` line that the receipt's `codex_landing` and the result carry.
- **A lane with `--pr` targets updates those PRs and opens none (OMN-20864).** Lane
  `cause-omniclaude-occrebase-1d5b` was dispatched at three PRs and staged a rebase of each; the launcher pushed one
  tree to a new branch and opened a new PR beside the PR it was meant to update, and left the other two. Now the
  prompt of a lane that carries `--pr` tells Codex to stage a tree per target in its own worktree and list it in
  `<ctx>/codex-targets.tsv` (tab separated, `-` for an empty column: `repo#n`, the PR head sha the tree was built on,
  the worktree, the commit message file, the PR body file). The runner uploads the heads the PR watcher's state held
  at dispatch as `<ctx>/codex-pr-heads.tsv` (`repo#n`, head branch, head sha; the receipt's `pr_dispatch_heads`). For
  each listed target the landing step reads the PR live (`gh pr view`) and refuses it unless it is open with its head
  branch in the same repository and its head is the head the tree was built on and the head at dispatch
  (`pr-head-moved`, `pr-not-open`, `pr-cross-repository`). It then runs `git commit` with every hook when a change is
  staged, and pushes the commit to the PR's own head branch: a plain push when the commit descends from the PR head,
  `--force-with-lease=refs/heads/<b>:<head>` when it does not (a rebase), never plain force. A staged PR body replaces
  the PR's body (`gh pr edit`), and the PR is handed to the landing controller. With exactly one target and no list, the
  lane worktree's own staged change or new commits are that target's tree. Every listed target is tried; one that
  fails does not stop the rest. Each target prints `REMOTE-LANE-CODEX-TARGET <repo#n> pushed branch=<b> head=<sha>
  [lease=<old head>] [body=updated|failed]`, `... handoff rc=<n> ...`, `... failed <shape>: <reason>` or `... skipped:
  no tree was staged for it`. A failed target ends the lane `landing-failed` with `landing-shape` (the first failed
  target's: `pr-head-moved`, `pr-not-open`, `pr-cross-repository`, `pr-unreadable`, `commit-hook-failed`,
  `no-commit-message`, `no-change`, `no-worktree`, `not-a-target`, `duplicate-target`, `manifest-incomplete`,
  `no-targets-file` when a lane with several targets left a change in its own worktree and listed none, or git's push
  shapes) and `landing-targets=<the failed repo#n, comma separated>`; the receipt's `landing_failure` lists each failed
  target with its reason and `pushed` the ones that landed, and the kept patch and message are
  `<run_id>.landing/target-<repo>-<n>.{patch,msg,log}`. A target's commit uses the same formatter restaging helper,
  within `CODEX_COMMIT_ATTEMPTS`; other hook failures refuse the target without resuming Codex. A lane without
  `--pr` keeps the new branch and the new PR below.
- **`--no-publish` runs a Codex lane that publishes nothing (OMN-21877).** `--model codex --no-publish` renders no landing
  step, no target push and no handoff into the run script, so the script holds no commit, push, pull request create or
  handoff call, and runs Codex with `network_access=false`, which closes git, gh and the bus-based `onex scm` paths at
  once. The worktree stays (closeout and retention are skipped, as with `--keep-remote`); its diff against the start head
  is the receipt's `diff` (`text`, `bytes`, `sha256`, `path` of the `.diff` file beside the receipt, `worktree`), and the
  receipt and the CLAIM carry `no_publish=true`. `wait` writes no handoff for such a receipt. `--pr` with `--no-publish`
  is refused with exit 2 and `REMOTE-LANE-NO-PUBLISH-REFUSED` before anything is placed or claimed, and so is the flag on
  a lane that is not Codex.
- **A landing that ends without a pushed branch keeps the change (OMN-20841).** A resume that leaves the staged tree
  and the failing hooks as they were stops the loop early (`REMOTE-LANE-CODEX-COMMIT unchanged attempt=<n>
  hook=<pre-commit hook ids>`), and three refused commits end it (`gave-up attempts=3 hook=<ids>`). The push goes to
  `origin`, which the run script first adds from the lane's repository URL when the host's bare clone (`git init
  --bare` plus a fetch by URL) has none: without it git refuses with its "correct access rights" message, which is
  not a credential fault. When the branch's remote head is the head the lane started from (a lane dispatched at a PR
  branch's head that rebuilt it), the push carries `--force-with-lease=refs/heads/<b>:<start>`, so a head someone
  else moved is refused, never overwritten (`PUSH ok branch=<b> lease=<start>`). When the commit is refused or the
  push fails or is skipped, the run script writes `$C/landing-artifact/` (`base`, `change.patch`: the staged diff
  against the start head, or the commits as format-patch plus `change.bundle`; `commit.msg`, `pr.md`, `commit.log`,
  `push.log`) and prints `REMOTE-LANE-CODEX-ARTIFACT kept=<dir> files=<names>`. The runner copies that directory to
  `<run_id>.landing/` beside the receipt before the host's cleanup, records `landing_failure` (`shape`, `hook`,
  `reason`, `artifact`, `files`) and ends the lane `status: landing-failed`, exit 1: the TERMINAL (`outcome=failed`)
  and the parent notice carry `landing-shape=<shape>` and `landing-artifact=<path>`. Shapes: `commit-hook-failed`,
  `commit-hook-unchanged`, `push-refused-access`, `push-non-fast-forward`, `push-lease-refused`,
  `push-detached-head`, `push-failed`. Relaunch from the artifact: `git am change.patch` (commits) or
  `git apply --index change.patch` at `base` (a staged change).
- **Before it starts** the run script checks the binary, `codex login status` and a sandboxed write into the worktree.
  A failure ends the lane typed, before any work: `codex-missing`, `codex-not-logged-in` (the operator runs
  `ssh -t <host> codex login --device-auth`) or `codex-sandbox-unavailable`, exit 70.
- **The result.** The JSONL stream is read into the receipt's result: the final agent message, `session_id` (the
  Codex thread id), `num_turns` (completed items), `commands` and `usage`. The lane is itself the delegation, so a
  final message without a DELEGATION line gets `DELEGATION delegated=1 codex=<thread id>` from the runner, and the
  TERMINAL carries those cells. A ChatGPT plan limit ends the lane `codex-usage-limit` (exit 1) without marking the
  host. The ledger's model cell is `codex`.
- **The ledger.** The launching host always writes the CLAIM (`--lane-claim` is ignored: Codex has no ledger skill).
  On a bus host the brief tells Codex to hand its PR off with `pr-handoff/scripts/handoff.sh`, which writes the MSG
  and TERMINAL; otherwise the launching host writes the TERMINAL from the final message.

## Exit codes

| code | meaning |
| -- | -- |
| 0 | the lane finished and its result is not an error |
| 1 | the lane finished with an error, a nonzero engine exit, or no result event; or a Codex lane's landing kept its change without a pushed branch (`status: landing-failed`, OMN-20841) |
| 2 | usage: unreadable brief, bad lane name, ONEX_LEDGER_PATH unset, a `--timeout-min` above 90 with no `Timeout reason:` line in the brief (`timeout-refused`, OMN-20864), a rules-only brief (`brief-refused`) or a driver lane with no PR target (`driver-no-pr`, OMN-17427), or a `--timeout-min`, `--mem-max` or `--cpu-quota` past its ceiling |
| 3 | `wait` returned before the lane finished: call `wait` again |
| 70 | remote setup failed (plugins, fetch, worktree, upload) or the ledger refused the CLAIM |
| 74 | the lane name already has a live instance (a receipt not final whose runner pid is alive) or a lane queue entry, and `--replace` was not given (`REMOTE-LANE-DUPLICATE`, OMN-22678). Nothing was read, claimed or placed. `--replace` SIGTERMs the live runner, waits for it to close out, dequeues the entry (`.lane-queue-dequeued/`, one `dequeue` event) and then places this run. The throughput tick's queue relaunch carries `--queue-relaunch`: its own entry is admitted, and an entry that is gone refuses (`queue-entry-gone`). |
| 75 | no lab host with a Claude login has a free slot, or every one is refused by the memory and swap bar. Nothing ran anywhere. |
| 76 | the session never started: zero turns, or a hook blocked the prompt (OMN-20110). `status: failed`; the receipt's `failure` holds `kind` (`hook-blocked` or `zero-turns`), `reason` and `retryable: true`, and the TERMINAL is `outcome=failed`. The dispatcher retries on another host (`--host`) or locally. |
| 77 | the host's Claude account hit a usage limit (weekly or session wording, e.g. "You've hit your weekly limit · resets Oct 3"). `status: host-limited`; the receipt's `failure` holds `kind: usage-limit`, `until`, `backoff_s` (6 h weekly, 1 h otherwise) and `retryable: true`. The runner wrote the host's `.limited-<host>` marker (the landing controller's own file and format, in the shared placement directory, `{at, host, lease_id, until}`), so host selection, here and in the controller, skips it until `until`. `workflows/remote_lane.js` retries such a lane once on another host, as `<lane>-r2`; any other dispatcher does the same without `--host`. |
| 79 | the host's Claude OAuth session expired (OMN-20498): a Claude lane's result or closing output carries "Failed to authenticate", "OAuth session expired", "could not be refreshed" or a 401 authentication error. `status: host-auth-expired`; the receipt's `failure` holds `kind: host-auth-expired`, `engine: claude`, `reason` and `retryable: true`, and the runner echoes `REMOTE-LANE-HOST-AUTH-EXPIRED`. The runner wrote `.auth-expired-claude-<host>` (`{at, engine, host, kind: auth-expired, lease_id, until}`) in the shared placement directory, so Claude lane placement, here and in the landing controller, skips that host (a GLM, code-edit or Codex lane may still use it) until an operator clears the mark; `until` is only a 7-day safety bound. `throughput_tick.py` reports the host as `claude auth expired since <stamp>; log in again; no dispatch`. `workflows/remote_lane.js` and `merge_sweep.js` retry such a lane once on another host, as for 77. When the lane ran on a pool token (the token line names its label), the runner first runs the pool's `mark-revoked --label <label>`; while another token answers the host is not marked, the status is `pool-token-revoked`, the failure carries `revoked_label`, and the runner echoes `REMOTE-LANE-POOL-TOKEN-REVOKED` with the pool's ALERT line once. |

### Clearing a host's auth-expired mark

The login probe does not clear it: its smoke prompt result is cached for six hours as a working login, so a session that
expired inside that window still reads as logged in. After logging in again on the host (`claude auth login`), the operator
deletes the mark:

    rm -f "${LANDING_PLACEMENT_DIR:-$HOME/.local/state/omni/landing/placement}/.auth-expired-claude-<host>"

## From an orchestrator workflow: `host: 'lab'`

A workflow places a lane remotely through one thin sonnet agent that writes the brief, starts the
runner detached and waits for the receipt. The helper below is what an orchestrator script defines,
and a lane spec with `host: 'lab'` goes through it instead of a direct `agent()` call.
The same pattern ships as a standalone workflow: launch `${CLAUDE_SKILL_DIR}/workflows/remote_lane.js`
by `scriptPath` with args `{skill_dir: <this skill's directory>, lane, brief_path, parent, ticket, prs?,
model?, repo?, ref?, host?, timeout_min?}` (`prs`: space-separated `repo#n`). It returns the receipt's `exit_code`, `status`, `host`,
`duration_s`, `result` and `receipt` fields.

```js
// PLUGIN: the installed omni plugin root. SCRATCH: a directory the thin agent may write briefs to.
const RECEIPT = { type: 'object', properties: { exit_code: { type: 'number' }, host: { type: 'string' },
  status: { type: 'string' }, duration_s: { type: 'number' }, result: { type: 'string' },
  receipt: { type: 'string' } }, required: ['exit_code', 'status'] }
async function lane(spec) {
  if (spec.host !== 'lab') return agent(spec.brief, { label: spec.lane, model: spec.model })
  const cmd = `python3 ${PLUGIN}/skills/remote-lane/scripts/onex_remote_lane.py`
  return agent(`Write the text between the BRIEF markers, byte for byte, to ${SCRATCH}/${spec.lane}.brief.md with the Write tool.
Then run (a Bash timeout of 180000 ms: placement waits up to 90 seconds): ${cmd} --brief ${SCRATCH}/${spec.lane}.brief.md --lane ${spec.lane} --ticket ${spec.ticket} --model ${spec.model || 'sonnet'} --parent ${spec.parent} --detach${spec.repo ? ' --repo ' + spec.repo : ''}
It prints a PLACEMENT line last. If it exited 0 or 3, run \`${cmd} wait --receipt <the receipt= path it printed>\` again and again (each call returns within 9 minutes) until its exit code is not 3.
Return the final receipt's fields; on any other exit the lane never ran: return that exit code and the PLACEMENT line. Do not do the lane's work yourself, and do not retry a lane that failed.
BRIEF>>>
${spec.brief}
<<<BRIEF`, { label: `${spec.lane}@lab`, model: 'sonnet', effort: 'low', schema: RECEIPT })
}
```

The thin agent does no lane work. The lane's model is `--model`, and it runs on the lab host. An
exit 75 comes back as `status: no-host`: the lab hosts and the launching host are all full or refused.
The lane is not lost (OMN-19998): the runner writes it to the lane queue (`REMOTE-LANE-QUEUED`, the receipt's `queued`
cell, one entry per lane under the placement state directory's `.lane-queue/`, with its relaunch command, model,
priority class, `--host` pin and a three-hour expiry), and the throughput tick starts it on the next free slot of any
admitting host, most urgent class first. The queue entry keeps the pin until it expires (OMN-21718), so the tick relaunches the
lane with `--host` and no other host takes it; an unpinned lane goes to any admitting host. A run that ends no-host again (a flapping host) keeps its entry, wait and expiry and counts an
attempt; a run that places takes its entry out (`REMOTE-LANE-QUEUE-START`). `.lane-queue-events.jsonl` holds one
`enqueue`, `start` or `expire` event per change. So never re-send a queued lane by hand: the tick's
`NOTE dispatch-queue: depth=<n> oldest=<m>m (<lane>)` line is its state, and only an expired lane is `MISSING
dispatch-queue-expired:<lane>`, which is the one to re-send. No local fallback is hand-run any more. An exit 75 with
`status: node-unavailable` is the placement node giving no answer, retried the same way.

## Filing, reading and commenting on tickets from a lab lane

A lab host has no Linear connector, so a lane there uses omnimarket's `node_create_ticket`, the one ticket node
(OMN-20595), with `--operation create|read|comment`. Its key is `LINEAR_API_KEY`, which the lab key store holds
(RULING 2026-10-31T11:06:14Z, OMN-21672). The runner ships it into the lane's environment from the store (step 4 of "Run it"), so a
lane launched by a runner at or after that change already holds it on every host, with or without an env file. A create runs the
installed omniclaude ticket-creation guard (OMN-17942) on the exact payload it files, Backlog with no project and the
description unchanged, and creates nothing when the guard refuses or cannot be found. The guard is the onex plugin
this runner shipped: the `onex@...` entry of the footer's "Plugin directories" line, plus
`/hooks/lib/ticket_creation_guard.py`, passed as `ONEX_TICKET_GUARD_PATH`. Run the node from an omnimarket worktree
(`--repo omnimarket`) after `env -u PYTHONPATH uv sync --frozen -q`:

```bash
G="<onex plugin dir from the footer>/hooks/lib/ticket_creation_guard.py"
( export ONEX_TICKET_GUARD_PATH="$G"
  env -u PYTHONPATH uv run python -m omnimarket.nodes.node_create_ticket --operation read --ticket-id OMN-1234 )
#   create:  --title "<title>" --parent OMN-<n> --description-file <body.md>   (add --dry-run to run only the guard)
#   comment: --operation comment --ticket-id OMN-<n> --body-file <comment.md>
#   <comment.md> begins with actor: <lane> (<model>), then the comment text.
```

- The body follows `/omni:create-ticket` (Gate line, labelled criteria each with a falsifier). The node adds nothing
  to it. A refusal prints `status: error` with the guard's findings in `validation_errors[0]` and exits 1; fix the body
  and run again, never route around the guard.
- With no key the node exits 1 naming `LINEAR_API_KEY`. It never falls back to a local stub, and neither does
  omnibase_infra's `resolve_project_tracker`, which now raises unless a caller selects the stub by name.
- Never print the key. A lane whose environment lacks the key (`REMOTE-LANE-STORE-SECRETS` shows why) reports that and stops.
- The node cannot change a ticket's state. A lane that needs a state change names it in its final message for the
  launching host to make.

## Known limits

- Transport is ssh with the launching user's key, as for the landing workers. The event-bus
  placement (OMN-20105) replaces it when that path carries lane units.
- A lab host needs a Claude login to qualify: a keychain login that unlocks over ssh, or the
  long-lived token file the placement probe reads. Every row of the shared lab host table, including the
  launching host, is read on every placement and ranked, lab hosts first, by spare cores (less the row's `penalty`), so
  the Macs h903 and h904 take a lane whenever their login, LAN grant, memory, pressure and link pass and
  they have the most spare capacity; on 2026-10-01 h908 ran 332 and h907 33 of the day's 365 remote
  lanes, and the Macs none (h903 was last read at 7 GB free and pressure warn, and h904's link lost
  40-80% of packets from 04:05Z; since 2026-10-18 a link benches a host only on sustained loss, above).
- The ledger a remote lane reads is a snapshot: rows written after dispatch are not in it (the lane's own
  rows are, in the bus mode), so an
  ownership or inbox check is as of the receipt's `ledger_snapshot.snapshot_at`. A lane that must see
  live rows, or needs the knowledge-base clone or other local-only state, runs locally. Remote lanes
  are for work whose inputs are GitHub, Linear, the repository and the ledger as of dispatch.

## Common rationalizations

Each row is an excuse for running a lane off the launching host the way it runs on it, with the
failure it caused. The rows come from the night of 2026-10-17 and the FRICTION rows of 2026-10-12
to 2026-10-17.

| Excuse | Why it is wrong | What to do instead |
| -- | -- | -- |
| "No host took the lane (exit 75), so I re-run it by hand." | This skill's own lane ended no-host twice that night (14:46Z and 14:49Z) and each re-run was a hand fix of one instance. The class is fixed: the runner writes a no-host lane to the lane queue, prints `REMOTE-LANE-QUEUED`, and the throughput tick starts it when a slot is free. | Read the queue line and the tick's dispatch-queue line before re-sending. Re-send only a lane that is neither queued nor started. |
| "The lab host has what the launching host has." | FRICTION 2026-10-15T03:49:35Z lane=omn18531-t02 and 2026-10-15T05:42:32Z lane=omn18531-b5: lanes needed transcripts or a file held on another host. FRICTION 2026-10-15T03:55:16Z lane=omn17427-hdrf: on a lab host the pr-handoff and remote-lane suites failed before any change, because the lane's bus-write and watcher environment was set. | Brief the lane for the host it will get. Put inputs in the brief or a pushed branch, and run a suite with the lane's own ledger and watcher variables unset. |
| "The lane can file or edit the Linear ticket with the Linear connector." | A headless `claude -p` lane on a lab host has no authenticated Linear connector: FRICTION 2026-10-12T07:28:15Z lane=h903-fill-1d5b and 2026-10-15T15:17:21Z lane=omn19174-c10, two lanes blocked on one ticket (the second edited a criterion). | A lab lane files, reads and comments through `node_create_ticket` as the section below says. A brief that needs a criterion edited or a mint beyond the one granted has the lane return the exact text for the orchestrator to file. |
| "I wrote a HOLD from the lab lane, so the peer lane sees it." | FRICTION 2026-10-14T12:20:54Z lane=omn19998-ainst: a HOLD written with `relay=queued` reached the canonical ledger only when the lane ended, and a peer installed on timing alone. | Read the result line. A `relay=queued` HOLD binds nobody until the lane ends; sequence the peers yourself, or take the bus path. |
| "The lane handed off, so it is done." | `outcome=handed-off` means the pull request waits on the controller and is not merged. | Count merged. Treat a handed-off lane as an open pull request with an owner, and read the watcher for its state. |
| "I will hot-patch the cache so the fix runs now." | FRICTION 2026-10-16T09:37:53Z lane=strict-serial-cycle: the controller host runs its own hash-guarded install, so a hot patch of the plugin cache did not reach it. Merged is not running until the version bump ships it. | Land the change, let the plugin-version-bump workflow raise the version, then read the installed version before saying it runs. |
| "A few GitHub reads from a controller-fix lane will not matter." | FRICTION 2026-10-14T12:34:33Z lane=orchestrator-31d9: two controller-fix lanes made 215 and 192 GitHub calls in 30 minutes although their briefs forbade reads. | Read PR state with `pr_state_local.py` and `onex scm`. Report a stale state as unreadable instead of reading GitHub. |
| "A cloud session starts headless like any other lane." | FRICTION 2026-10-17T00:44:48Z lane=cloud-overflow-placement: `claude -p --cloud` is refused as interactive only, the interactive start stops at the workspace-trust question, and only one lab host's claude.ai login reaches cloud sessions at all (15 minutes). | Use the runner's pseudo-terminal start from a scratch clone, and place a cloud lane only on a host with a claude.ai sign-in. |
| "I will finish past 75 minutes, the work is nearly done." | RULING 2026-10-14T04:56:52Z lane=orchestrator-31d9: two lanes hit the runtime limit on 2026-10-13/14 and left no result. A lane cut off at the limit reports nothing. | At the time-box line (75 minutes of 90) stop starting new work, push the branch or a draft, and end with `LANE_RESULT outcome=partial`. |

## Red flags

- A script that places many lanes and is run twice. One lane name runs once (OMN-22678): the runner refuses a name with a live or queued instance (exit 74). Read exit 74 as "already placed", never re-run with `--replace` unless the old instance is to be stopped. On 2026-11-06 a second run of a placement script placed 22 lanes twice; six ran two instances at once in one worktree and one duplicate's closeout removed the kept run's worktree.

- A second launch of the same lane name while the first sits in the lane queue or has not yet ended.
- A `no-host` or exit 75 receipt answered with a hand re-run and no look at the queue.
- A brief for a lab lane that needs Linear, a local-only file, a transcript or a host alias that resolves on one host.
- A `relay=queued` result line on a HOLD that a peer lane is waiting on.
- A report that counts a handed-off lane as done, or "merged" where it means "running".
- A lane that reads GitHub, or a lane whose call budget is over.
- A lane that has run 75 minutes and is still starting new work.

## Known friction (from prior runs)

- **Formatter hooks left their fixes unstaged, exhausting Codex's commit retries.**
  `TERMINAL 2026-10-12T16:03:51Z lane=censusbot-1d5b` ended `landing-failed`,
  `gave-up attempts=3 hook=canonical-file-shape,yamlfmt`; lanes were re-dispatched by hand. Both landing paths now
  re-stage only changed paths already staged for the commit and retry before any resume, within the same bound.
  → OMN-20864
- **The lab-only placement rule (Operating Rule 21) kept lanes off the launching Mac while the MVP deadline needed every machine.** The runner now admits the launching host as the last placement under its own cap of 6 (or its host pool row's cap), (`RULING 2026-10-02T11:39:15Z lane=orchestrator-0c2f`, the operator, 2026-10-02: use the entire lab, the Monday MVP deadline leaves no capacity idle). -> OMN-20360
- **The launching host refused every Codex lane by a fixed rule (CODEX-NOT-ON-LAUNCHING-HOST) and its four-core unit charge held the Mac Studio to one or two lane slots at a third of its CPU busy.** Its table row now decides (`codex: true`, `cap`, `unit_cores`), and only the admission bars refuse it (`RULING 2026-10-11T16:48:49Z`). -> OMN-20864
- **A lane's pytest ran 6h43m at full CPU on lab-host-a and, with other work, drove load to 1138 and exhausted 96 GB
  of RAM and swap, taking down the dev lane, the model server and the CI runner (2026-09-30).** Nothing bounded a
  command a lane starts on a lab host. Every engine now runs inside the lane guard (step 5), the same guard wraps
  `lane-k-run` commands, and the host reaper and the root-only guardrails script (linger, earlyoom, a
  user.slice cap) back it. → OMN-20199
- **The first lane on a fresh omniclaude plugin cache on h908 ended UNSTARTED at 0 turns, twice on 2026-10-07:**
  the plugin install built no `.venv`, the onex hooks' own inline `uv sync` built it during the session, and the
  UserPromptSubmit hook ran the interpreter before `yaml` was installed. The install now syncs the tree before the
  lane starts (step 2). → ledger row 2026-10-08T00:38:20Z lane=hook-yaml-race-0015, OMN-17427

## Time box (OMN-20864)

Operator RULING 2026-10-14T04:56:52Z lane=orchestrator-31d9: a lane is one PR sized for about 90 minutes and reports what
it has instead of running out its clock. Two lanes (omn21077-optb, omn20844-bnc2) hit the 9120 s runtime limit on
2026-10-13/14 and left no result.

- The default `--timeout-min` is 90 (it was 60, and the dispatching sessions passed longer limits by hand).
- Every lane preamble, Claude and Codex, carries a `Time box (mandatory)` line: the lane's runtime limit, and `At 75
  minutes` (the limit minus 15) it stops starting new work, commits and pushes what it has (a branch, or a draft PR) and
  ends with a final message that says what is done and what is not and carries `LANE_RESULT outcome=partial`. The lane
  runs `date -u` before its first tool call and checks it between steps, because nothing else wakes a headless session.
  A `--timeout-min` other than 90 changes both numbers.
- A brief may raise the limit only with a stated reason. `--timeout-min` above 90 with no unfenced
  `Timeout reason: <why 90 minutes is not enough>` line in the brief (an empty or placeholder value does not count) is
  refused before anything is placed or claimed: `main` exits 2 at dispatch, `execute` writes the final receipt
  `status: timeout-refused` and echoes `REMOTE-LANE-TIMEOUT-REFUSED`. A limit at or below 90 never needs a reason, and the
  3 h guard ceiling still applies on top.

## Notes moved from the runner header (OMN-21672)

The runner's module header no longer carries these three notes; they are kept here.

THE REQUIRED-CONTEXTS COPY (OMN-20780). The landing controller keeps ``required-contexts.json`` fresh on its own
host only, so the ruling audit on a lab host read none, or one a landing worker left there hours ago, and called
every check mechanism unjudgeable. Beside the watcher state the runner ships the launching host's file
(``$LANDING_STATE_DIR``, else ``~/.local/state/omni/landing``) to ``<run>.ctx/required-contexts.json`` and exports
ONEX_REQUIRED_CONTEXTS_CACHE, which the audit reads in place of the host's own. Shipped once at dispatch: the
controller re-reads an entry past four hours and the audit trusts one under six. A cache that cannot be read is
recorded as ``required_contexts_snapshot.error`` with one ``REMOTE-LANE-REQUIRED-CONTEXTS-MISSING`` line.


THE DELEGATION RELAY'S SETTINGS (OMN-20471). A lane's delegation dispositions reach the lab bus through
``harness_delegate.relay_emit``, which reads the ``delegation_health`` overlay. The runner exports
``ONEX_SKILL_OVERLAY_ROOTS`` (engine env and settings) at the ``overlays/`` directory of the ``onex-overlays``
plugin tree it shipped to the host, and carries the launching host's ``ONEX_RUNTIME_SSH_HOST`` when it is a
``user@address``. A host that runs the dev lane's runtime container publishes locally and needs no SSH target.

HOOK PREFLIGHT (OMN-19854). ``hook-preflight --worktree <path>``, run by a lane (or by the Codex landing step) before
any commit, runs the repository's commit hooks on the changed files only, in the foreground, under a time budget, and
records each hook's timing; it reruns only failing hooks, three rounds in all, and never bypasses a hook. A hook
unrelated to the change, the budget or the spent rounds ends in ``HOOK-PREFLIGHT BLOCKED`` (exit 3): the staged change
is saved as a patch and ``hook-preflight-blocked.json`` names the hook, its error tail and the patch. The landing
worker prompts (merge-drain) carry the same step.

HOOKS RUN SIDE BY SIDE (OMN-21987). The hooks of one call are independent ``pre-commit run <hook> --files`` processes, so
``--workers N`` (default ``ONEX_HOOK_PREFLIGHT_WORKERS``, else a quarter of the cores, at most 6) runs N at once and
``--workers 1`` is the one-at-a-time loop. Measured 2026-11-03 on h902 with a warm shared cache: omnimarket, a 5-file
commit, 67 hooks, 510 s one after another, 60 percent of it in eight whole-repository scans and one whole-suite test
(``node-auto-wiring-in-process``, 145 s); omnibase_infra, 97 hooks, 302 s. Before the first batch the call runs
``pre-commit install-hooks`` once (``install_hooks_s`` in the result; a cold cache cost 275 s on h902), so no hook takes
the cache's install lock, and when that fails the hooks run one at a time. A rewrite by a hook has no author side by side:
the changed files are restaged and every hook runs once more on the restaged bytes, inside the same round. The commit's own
hook run is unchanged: ``git commit`` still runs every hook, one after another, on the final staged tree.

HOOKS RUN UNDER HOST-WIDE SLOTS (OMN-22870). ``--workers`` bounds the hooks of one call, not the sum over every call on a host.
Measured 2026-11-08 on h901 (80 cores): load1 271.5 at 19:31Z with 14 landing workers and 13 lanes placed; sar showed the run
queue at 74 to 221 and iowait at 0.2 to 0.4 percent (CPU, not the disk copy); three samples of the runnable tasks at 19:58Z
found 36, 41 and 46 of 46 to 58 under a ``hook-preflight`` or ``pre-commit run`` process. Each hook now takes one of
``ONEX_HOOK_PREFLIGHT_HOST_SLOTS`` slots (default a quarter of the cores, never under 6; 20 on an 80-core host) while it runs.
A slot is a flock on a file in ``ONEX_HOOK_PREFLIGHT_SLOT_DIR`` (default ``/tmp/onex-hook-preflight-slots-<uid>``), so a killed
preflight frees its slot. The wait for a slot counts against the call's budget: a call that finds every slot held until its
budget ends reports ``budget`` with ``(no hook slot was free ...)`` and is resumable like any budget stop.
