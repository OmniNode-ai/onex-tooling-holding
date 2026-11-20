---
name: lab-rebuild-triage
description: Diagnose a lab-host-a dev-lane rebuild that is not converging, when deploy-agent jobs fail or stall, lane-j lab-pass receipts read FAIL or are missing, or a runtime merge never got a build. Measure the host (load, IO and memory pressure, swap traffic, runner fan-out) before touching the build. Read the agent's own job record and the trigger run, classify each merge as runtime-affecting or not before hunting its receipt, detect a published-but-never-accepted redeploy or a publish/reject loop, and apply the no-hand-restart rules. Use before anyone proposes a restart, a manual redeploy or a rebuild request.
prosthetic: true
replaces_when: "The deploy agent reports its own failure class correctly (a stall from stdout progress, a budget re-sampled under load, a dockerd crash distinct from a build error), the runtime rebuild trigger retries a transient broker DNS failure, and the lab-pass receipt carries the host pressure at build time, on two consecutive saturation incidents diagnosed from the receipt alone. On 2026-09-22 each of those needed a hand diagnosis (OMN-19208, OMN-19209, OMN-19211, OMN-18615)."
restored_from: "none. New process, captured from the 2026-09-22 lab-rebuild-diag and lab-rebuild-unstick runs (ledger rows 2026-09-22T23:02:45Z lane=lab-rebuild-unstick, 2026-09-22T23:22:55Z lane=lab-rebuild-diag, 2026-09-23T00:03:18Z lane=lab-rebuild-unstick STATUS)"
ticket: OMN-19221
---

# Lab rebuild triage (prosthetic)

The dev lane is compose project `omnibase-infra` on `ssh <owner>@192.0.2.127`, rebuilt by the deploy
agent (a systemd **user** unit, `deploy-agent-dev`) from each runtime-affecting merge to
`omnibase_infra` dev. **Rule 24(e) governs everything here:** the agent's own path gets its window
first. A manual warm redeploy is taken **once**, only after that window expires unused, and only
under an authorizing RULING row. Never use `--cold` on a declared lane.

Everything in steps 1 to 4 is read-only. The scripts named below live in this skill's `scripts/`
directory and only read. Never append `2>/dev/null` to any of them, and prove every zero with the
positive control each one prints.

The command path, so the steps below have names to point at:
CI trigger run, then `onex.cmd.omnimarket.redeploy-start.v1`, then `node_redeploy_orchestrator`,
then `onex.cmd.omnimarket.redeploy-deploy-publish.v1`, then `node_redeploy_deploy_effect`, then
`onex.cmd.deploy.rebuild-requested.v1`, then the agent, which answers on
`onex.evt.deploy.rebuild-completed.v1` or `onex.evt.deploy.rebuild-rejected.v1`.

## 1. Measure the host first (read-only)

```bash
ssh <owner>@192.0.2.127 'uptime; nproc; cat /proc/pressure/io /proc/pressure/cpu /proc/pressure/memory; free -g; vmstat 5 3'
ssh <owner>@192.0.2.127 'pgrep -fc "[R]unner.Worker"; pgrep -fc "[p]ytest"; docker ps --format "{{.Names}}" | wc -l'
```

Write the process patterns as `[R]unner.Worker` and `[p]ytest`. Over ssh the remote `bash -c`
command line itself contains the plain pattern, so a plain `pgrep -fc Runner.Worker` counts its own
shell (measured 16 against 15 on 2026-09-23, and 50 against 49 at 18:37Z). Only a compound
command line like the one above keeps that shell: a single-command ssh is exec'd directly, and
both spellings then agree, so do not take agreement on a one-command test as proof either way.

Treat the host as saturated, not the build as broken, when any of these holds:

- load1 is far above `nproc` (32);
- IO `full avg10` is above about 40;
- memory `full avg10` is above about 5, or `vmstat` shows `si` plus `so` above about 50000 KB/s on
  two consecutive samples. Skip `vmstat`'s first line: it is the average since boot, not a sample.
  Swap **used** is not a signal on its own: tens of GB of cold pages can sit in swap on a healthy
  host. Measured 2026-09-23T16:49Z: 62 GB swap used, `si` plus `so` about 16000 to 21000
  KB/s, memory `full avg10` 0.46, load1 5 on 32 CPUs. That is light swap traffic on an idle host,
  not saturation. The same swap used with `so` above 100000 KB/s and memory PSI climbing is
  thrashing;
- dozens of `Runner.Worker` jobs are running.

Check whether one repo's push fans out into many runner jobs, each running `pytest -n auto`. In a
2-CPU container that is still 32 workers per job (ledger row 2026-09-22T23:22:55Z lane=lab-rebuild-diag).

## 2. Read the agent's job record

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/agent_journal_digest.sh" -2h 80
```

The unit is a **user** unit: the digest reads `journalctl --user -u deploy-agent-dev`, and prints
`user_scope_lines` next to `system_scope_lines` as its positive control. System scope (no `--user`)
returns no entries, which reads exactly like a quiet agent. If `user_scope_lines` is 0 too, the
read failed; stop and say so.

Do not read the journal with `tail -200`. During a duplicate-command storm the journal runs to about
450,000 lines in two hours, nearly all per-rejection producer SASL chatter, so the tail is only
noise. The digest counts that noise separately (duplicate rejections per command id, kafka
chatter) and then prints the lifecycle lines only: accepted commands with their `ref=`, phases and
ceilings, job completion or failure, and published results. Its stamps are UTC.

For each job, note the id, the ref, the phase, the ceiling it was granted and the load it sampled.
The job record itself is `/data/omninode/deploy-agent/state/jobs-dev/<command id>.json` (read it
with `ssh ... python3 -c 'import json ...'`; its `command` holds `git_ref` and `requested_by`).
Know the misreadings before you trust a label:

| Label says | Can really be | Check |
| -- | -- | -- |
| `0/61` steps, stall | progress written to stdout, which the parser did not read (fixed by OMN-19208, omnibase_infra#3980) | `ps` on the host for BuildKit runc executors doing work |
| `runtime_image_build_budget_exhausted` | a ceiling sampled once at phase start under low load, then starved (OMN-18615) | the sampled load in the job record against `uptime` now |
| `runtime_image_build_errored` | dockerd crashed mid-build (OMN-19211) | `journalctl -u docker --since "-1h" \| grep -i panic` |
| a job completed at ref X | a job requested by another repo's trigger, pinned to an older infra ref, which rolls the lane backward | `requested_by` and `git_ref` in the job record, and `git merge-base --is-ancestor` against the sha you expected |

## 3. Classify each merge, then find its trigger run

Classify before you hunt a receipt. A merge the trigger's own classifier calls non-runtime never
gets a rebuild and never gets a receipt, so a missing receipt for it is expected, not FAIL-CLOSED
(the release merge eb81f73f, omnibase_infra#3993, logged "No rebuild trigger" and has no receipt by
design).

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/trigger_for_sha.sh" OmniNode-ai/omnibase_infra <merge sha>
```

It prints `sha  pr  run  CLASS  detail`, with CLASS one of `NON_RUNTIME` (no receipt expected),
`PUBLISHED` (with the redeploy-start correlation id and offset), `DETECTED_NOT_PUBLISHED` (with the
cause, for example broker DNS), `NO_TRIGGER_WORKFLOW` (a library repo), `NO_RUN` or
`UNREADABLE` (a merge the PR watcher holds no record of, 14 days back, reads this way). Treat the
last two as unknown, never as PASS.

Do not match trigger runs with `gh run list ... --json headSha`. The trigger runs on
`pull_request: closed`, so `headSha` is the PR's **head** commit, never the merge sha. The script
goes merge sha, then the watcher's merge record (PR, head branch, first trigger run created after
the merge and its jobs: `pr_state_local.py callers merge-sha`), and it confirms the run names the merge sha in
that run's log (`PR_MERGE_SHA: <sha>` in omnibase_infra; `SOURCE_SHA: <sha>`, `source_sha: <sha>` or `source_sha=<sha>`
in omnimarket, whose trigger job is a reusable workflow), the one GitHub read left.

To classify every merge since a known point, run it per first-parent commit:

```bash
python3 "$registry_root/omniclaude/plugins/onex/hooks/lib/canonical_clone_sync.py" refresh OmniNode-ai/omnibase_infra --wait   # not a git fetch (OMN-20495)
for s in $(git -C "$registry_root/omnibase_infra" log --first-parent --format=%H <last PASS sha>..origin/dev); do
  bash "${CLAUDE_SKILL_DIR}/scripts/trigger_for_sha.sh" OmniNode-ai/omnibase_infra "$s"
done
```

A `DETECTED_NOT_PUBLISHED` on `Temporary failure in name resolution` for the lab broker is
transient. Rerunning that run once is the remedy, and it is a gh mutation: it needs the lane's own
authority. Do not wait for a later merge to carry the build (ledger row 2026-09-23T00:57:52Z
lane=friction-to-skills item=F11, run 35793186217).

## 3a. PUBLISHED, but did the agent ever accept it?

For a `PUBLISHED` merge with no receipt, check that the redeploy became an agent job:

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/command_loop_probe.sh" <merge sha> 30
```

It is read-only rpk inside the broker container. It samples the high watermarks of the four
command topics 30s apart, prints each consumer group's lag on the path, groups the last 200
`rebuild-requested` records by correlation id and producer, counts the agent's duplicate
rejections in the last 10 minutes, and for the sha prints its `redeploy-start` offset, the
orchestrator's and deploy effect's committed offsets, and how many agent job records were accepted
at it (with the count of all job records as the positive control). A job counts only when its
`command.git_ref` starts with the sha. A job of another ref that was superseded by the sha
(`superseded_by_sha`), or a record that mentions the sha only in `lineage` or sibling refs, is
counted and printed on its own line, and never selects `BRANCH accepted`: the agent never accepted
the sha itself. When the sha was published and never
accepted with lag 0 on both groups, it also traces the command's correlation id from 60s before its
`redeploy-start` record through `redeploy-deploy-publish`, `rebuild-requested` and
`rebuild-rejected` (up to 3000 records each, with the records read and the seconds covered as the
positive control), counts the agent journal's lines naming it (and how many were job polls
answered 404), and says how far back the deploy effect container's logs reach. That trace took
about 2.5 minutes on 2026-09-23 at 21:30Z.

It ends with `BRANCH` lines naming what it found (`ping-pong` or `no ping-pong`, then
`published-never-accepted` (queued), `published-never-accepted, nothing queued`, `not published`
or `accepted` for the sha). Read the result as one of
these branches. All of them are diagnosis only: **recommend, never act.**

- **Published, never accepted, queued.** The sha has a `redeploy-start` record, no job record's
  `command.git_ref` and no `Accepted command` line names it, and the deploy effect still has lag on
  `redeploy-deploy-publish`. The command is waiting between the orchestrator and the agent, and
  that lag is the queue in front of it. Report the lag and, from its drain rate, the ETA.
- **Published, never accepted, nothing queued.** The same, but the orchestrator's lag on
  `redeploy-start` and the deploy effect's lag on `redeploy-deploy-publish` are both 0. There is no
  queue: the command was consumed and then dropped or deduplicated between the deploy effect and
  the agent, and waiting for a drain gets nothing. Read where the correlation id stops in the
  probe's trace and the deploy effect's handling of it, and report that. Measured 2026-09-23 at
  21:30Z: 962aefc0 (`redeploy-start` offset 435, correlation fe6b9b8d, `requested_by`
  gha/omnimarket/pr-2810) reached `redeploy-deploy-publish` (1 record) but no `rebuild-requested`
  or `rebuild-rejected` record in the next 439s of 3000 read; the agent answered 28 job polls for
  it with 404, and the deploy effect container had restarted at 19:34:42Z, so its logs no longer
  covered 16:24Z. Recommend only.
- **Publish/reject ping-pong.** `rebuild-requested` and `rebuild-rejected` both grow by about the
  same count per sample, one correlation id (with producer
  `redeploy-deploy-publish-monitor-effect`) holds nearly all of the last 200 records, and the agent
  journal shows thousands of `Rejecting command <that id>: duplicate`. The deploy effect is
  re-publishing one old command for every record of its backlog, and the agent is right to reject
  it. Every newer redeploy waits behind that backlog. Report the id, the sha it names, the growth
  rate, the effect's lag and the drain ETA (lag divided by the growth rate). Measured 2026-09-23:
  about 400 rejections per minute on command 2d3ccad1 (sha c159b711), deploy-effect lag about
  21,000, so 6fe05c35 (omnibase_infra#4002, redeploy-start offset 434) was published and never
  accepted. Re-measured at 16:50Z: about 440 rejections per minute, deploy-effect lag 11,465, so
  a drain ETA of about 26 minutes, and still no job named 6fe05c35. Re-measured at 18:29Z: 861
  duplicate rejections in 10 minutes but no growth on either topic during a 30s sample, deploy-effect
  lag 3,822, and still no job named 6fe05c35. The probe reports that case as `ping-pong, idle during
  the sample`: the loop runs in bursts, so re-sample for longer before calling it stopped. A 60s
  sample at 18:39Z showed +88 on both topics, deploy-effect lag 2,172, and still no job named 6fe05c35.
  The backlog then drained on its own: the agent accepted cb5275c0 (6fe05c35) at 19:20:38Z and
  completed it at 19:46:56Z, and at 20:50Z the probe read 0 duplicate rejections in 10 minutes, every
  lag 0, and `BRANCH accepted`. Nobody acted on the lane, which is why this branch is diagnosis only.
- **Accepted, but a different ref.** While a sha waits, the agent can still accept a command
  another repo's trigger published, pinned to an older infra ref. On 2026-09-23 at 15:50Z it
  accepted e074126b (`requested_by` gha/omnimarket/pr-2804, `git_ref` 533b19c2, which is older than
  6fe05c35) and completed it. A completed job is not a build of your sha: check `git_ref` in the
  job record.
- **Accepted and failed.** Go back to step 2's table.
- **Accepted and completed, but no receipt.** A job that completes after its trigger run's
  `Verify dev lane applied the redeploy` job has ended writes no receipt: the sha's lane-j
  receipt is written by that verify job while it runs, or re-emitted later as below.
  `trigger_for_sha.sh` prints the verify job's conclusion as `verify_job=`. Measured 2026-09-23: 6fe05c35's verify job (run 35871621590) ended `cancelled` at
  14:08:57Z with no step run, the agent built the sha at 19:46:56Z, and at 20:50Z step 4 still read
  lane-j `VERDICT NONE`. The receipt can then come only from a job that runs again: a rerun of
  that verify job (a gh mutation, which needs the lane's own authority), or the `Re-emit receipts
  for shas queued behind this merge` job of a later runtime-affecting merge, which runs only when
  that merge's verify job succeeds and only for the shas its guard lists in `reemit_candidates`
  (OMN-18976). Read that list before counting on it. Report the gap; do not rerun anything from
  this skill.

A rebuild request sent while a ping-pong runs is queued behind the same backlog or rejected, so it
does not help. Name the loop in a STATUS row addressed to whoever owns the lane and stop.

## 4. Read the receipts

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/read_receipt.sh" OmniNode-ai/omnibase_infra <sha> lane-j <scratch dir>
```

It reads every `lab-pass-receipt-lane-j-<full sha>` artifact through the REST artifacts API
(list by exact name, then `repos/<repo>/actions/artifacts/<id>/zip`) and returns in seconds. Use
surface `lane-k` or `lane-h` for the k3s receipts (both exist per sha; on 2026-09-23
6fe05c35 read `lane-k` PASS and `lane-h` FAIL, so read both). When no artifact carries the
sha, the script runs a positive control on the same exact-name query: it walks the sha's ancestors,
newest first (up to 60, `CONTROL_DEPTH` to change it), until one of them has a receipt of that
surface, and names it before `VERDICT NONE` (for 6fe05c35 at 21:30Z: c159b711, 6 ancestors read,
4s). When no ancestor has one, the line says `FAILED` and the verdict is `NONE_UNPROVEN`: the zero
is not proven. Then treat the receipt as unknown, never as NONE and never as PASS. List the
artifacts of the sha's own trigger run by id (the run id is the third field of
`trigger_for_sha.sh`) with `gh api repos/<repo>/actions/runs/<run id>/artifacts --jq
'.artifacts[].name'`, and report what that shows; if it cannot settle it, report the receipt as
unknown and name the run. Do not use `gh run download -n <name>` without a run id: it walks every
run, and it hung for more than 120s on 2026-09-23.

A receipt's payload must agree with its artifact name: payload `sha` equal to the full sha and
payload `lane` equal to the surface. When either differs, the script prints
`NAME_PAYLOAD_DISAGREE` with both values, which is not a PASS (the release train refuses the same
case as `lab_receipt_name_payload_disagree`).

An artifact with no `receipt.json` prints `NO_RECEIPT`: that is **no receipt**, not a PASS. A FAIL on
`deployed_revision`, `health_dimensions` or `timed_out_before_ready` during saturation is the
saturation, not the change. A PASS receipt describes the lane at the moment it was taken. If a later
job rebuilt the lane at an older ref (step 2's last table row), the PASS no longer describes what is
running.

## 5. Act, in this order

1. **Reduce load at its source.** Name the fan-out (repo, workflow, job) and land its fix (for
   example the xdist cap, infra_repo#1629). Pausing half the runners during one build needs an
   explicit go from the lead or operator. Never kill another lane's process.
2. **Let the in-flight agent job finish.** If one is building, do not issue a rebuild request
   (ledger row 2026-09-22T23:22:55Z lane=lab-rebuild-diag). If step 3a found a ping-pong, do not
   issue one either: report it and stop.
3. **Issue one deploy-agent-path rebuild request** only if the job failed, none is in flight, no
   loop is running, and an OPERATOR-CONSENT or RULING row authorizes that one request. The only
   sanctioned path is the signed deploy step, `node_branch_deploy_command_effect` (omnimarket),
   run on the dev lane's bus (OMN-24414 retired the hand-run trigger script that read an ambient
   signing key from whichever machine ran it):
   `onex run-node node_branch_deploy_command_effect --timeout 120 --input '<json>'`. The JSON
   carries `correlation_id` (a new UUID), `mode` (`deploy` for an open pull request's head,
   `rollback` to rebuild a named sha, the running dev head included), `runtime_lane` (`dev`),
   `repo`, `pr_number`, `git_ref` (the full 40-character sha, never a branch name),
   `rollback_actor`, `rollback_reason` and `requested_by`. The runtime fills the signing key from
   the secret store under the name the node's overlay gives; no env file, `KAFKA_*` value or ssh
   key is set by hand, and no key is ever printed. Read the terminal event: `published` means the
   signed command is on the agent's topic; `refused` (no signing key, with the reason in
   `detail`) and `failed` (a publish error) mean nothing reached the agent, so do not repeat
   the request: report the detail. Never run it on this skill's own authority.
4. **A warm redeploy by hand** only under rule 24(e): once, after the agent window, with a RULING row.
5. Record the incident with `friction-record` (`/omni:friction-record`), including the unexercised runtime merges it caused.

## Guardrails

- **Never run `docker buildx history ls` on lab-host-a.** It panics dockerd (2026-09-17 and 2026-09-22 22:37Z, OMN-19217, ledger row 2026-09-22T22:41:39Z lane=lab-rebuild-unstick).
- No `--cold`, no raw `docker compose up` on a declared lane, no retag. lane-i and judge are out of scope.
- No consumer-group seek, reset or delete, and no publish, from this skill. The probe reads only.
- A broker memory change applies only when the deps leg runs. Abort at pre-check if IO `full avg10` is above 40 or an agent job is in flight (ledger row 2026-09-22T23:02:45Z lane=lab-rebuild-unstick).
- While the lane cannot converge, report that runtime PRs are stacking unexercised. Do not keep landing them silently (ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F10).

## Known friction (from prior runs)

- **`command_loop_probe.sh` reported `BRANCH accepted` when the only job record carrying the sha was another ref's job superseded by it** (`grep -l` over the job JSON also matched `superseded_by_sha`). At 23:35Z job 5935d13c (status superseded, `git_ref` 533b19c2, `superseded_by_sha` 6fe05c35) was one of the 2 records that 'named' 6fe05c35. A job now counts only when `command.git_ref` starts with the sha, and superseded-by and mention-only records are reported separately. `tests/run_tests.sh` has the case. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.

- **About 3.5h with no convergence past #3963, from runner fan-out:** 128 xdist workers, load1 397, swap about 70GB. → ledger rows 2026-09-23T00:57:52Z lane=friction-to-skills item=F10 and 2026-09-22T23:22:55Z lane=lab-rebuild-diag, infra_repo#1629, OMN-19209
- **Every kill read 0/61** because the parser read stderr. → ledger row 2026-09-22T23:22:55Z lane=lab-rebuild-diag, omnibase_infra#3980, OMN-19208
- **The ceiling was sampled once at load 13,** so #3939 was killed at 1095s. → ledger row 2026-09-22T23:22:55Z lane=lab-rebuild-diag, OMN-18615
- **A read-only probe crashed dockerd.** → ledger row 2026-09-22T22:41:39Z lane=lab-rebuild-unstick, OMN-19217, OMN-19211
- **The rebuild trigger gave up on DNS,** leaving 7954c945 unbuilt. → ledger row 2026-09-23T00:57:52Z lane=friction-to-skills item=F11
- **The broker memory fix (#3941) was merged but not live,** because it applies only when a rebuild reaches the deps leg, which the contention prevented. → ledger row 2026-09-22T23:02:45Z lane=lab-rebuild-unstick, OMN-19085
- **Empty consumer groups after max-poll eviction** during the saturation. → ledger row 2026-09-22T23:22:55Z lane=lab-rebuild-diag, OMN-18975
- **Trigger runs queued up to 40 min** behind the saturation. → ledger row 2026-09-23T00:40:46Z lane=infra-release-cut
- **Fleet CI timeouts on unrelated PRs** in the same window. → ledger rows 2026-09-22T23:03:11Z lane=m4-c10-probe, 2026-09-22T23:38:46Z lane=m4-c12-probe, 2026-09-23T00:02:17Z lane=pc2-runner-register, 2026-09-23T00:13:21Z lane=m4-c13-probe
- **A receipt FAIL on `health_dimensions` was a DLQ replay storm, not the merged sha:** one gate decision replayed about 20,000 times (header `x-replayed-by=node_dlq_replay_effect`), which also left the deploy effect's group Empty behind 19.7k duplicates, so the agent path cannot deliver a rebuild. Read the source topic's record headers and high-watermark growth before blaming the change. → ledger row 2026-09-23T12:18:14Z lane=lab-health-triage, OMN-19240, OMN-19241, OMN-19242
- **Runtime docker logs rotate in about 15 minutes during a storm** (json-file 3 x 10 MB), so the eviction evidence was gone. Capture `docker logs --since` for the runtime containers first, and date a group's last commit from the record at its committed offset (`rpk topic consume -o <offset> -n 1 -f %d`). → ledger row 2026-09-23T12:15:22Z lane=lab-health-triage (FRICTION, OMN-19241)
- **`rpk` inside the broker container refuses without SASL.** The SCRAM principal lives in the env of `omnibase-infra-redpanda-scram-user`, which is a **stopped one-shot** container: read it with `docker inspect`, not `docker exec`, inside the same ssh command, never print it, and never pass it as an `-X user=` / `-X pass=` flag value or via `docker exec -e` (both put the live value on argv, which every user on a shared host reads via `ps`, per OMN-19513). Pipe it over stdin into the exec'd shell instead, which reads it into `RPK_USER`/`RPK_PASS` and exports `RPK_SASL_MECHANISM=SCRAM-SHA-256` before `exec`-ing `rpk` with no credential flag at all (`scripts/command_loop_probe.sh`'s `R()` does this; `tests/test_no_credential_on_rpk_argv.py` in the repo root refuses a regression). → ledger row 2026-09-23T12:15:22Z lane=lab-health-triage (FRICTION, OMN-17214); corrected 2026-09-25, OMN-19513
- **Step 2 read the journal with `tail -200` during a rejection storm** (about 225k lines in 2h, all duplicates), so it showed only noise; the digest script now filters to lifecycle lines and counts the noise apart. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **System-scope `journalctl -u deploy-agent-dev` returns no entries;** the unit is a user unit. The digest reads `--user` and prints both counts as its positive control. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 3 hunted a receipt for a non-runtime merge** (release PR eb81f73f read as FAIL-CLOSED; its trigger log says "No rebuild trigger"). `scripts/trigger_for_sha.sh` classifies first. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`gh run list --json headSha` returns PR heads for `pull_request` runs, not merge shas,** so trigger runs never matched. The script matches merge sha to PR to branch and confirms `PR_MERGE_SHA`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **No branch for a redeploy published but never accepted, or for a publish/reject ping-pong** (command 2d3ccad1 rejected as duplicate tens of thousands of times while 6fe05c35 waited behind a 21k-record deploy-effect backlog). Step 3a now diagnoses both, read-only. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`pgrep -fc Runner.Worker` over ssh counted its own `bash -c`.** Step 1 uses `[R]unner.Worker`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **The swap rule ("tens of GB") ignored used-versus-active swap.** Step 1 now reads `si`/`so` and memory PSI. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 5.3 did not say how to issue a rebuild request.** It now names the signed agent trigger, its transport prerequisites and its consent requirement, and never runs it. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`gh run download -n <name>` with no run id hung for more than 120s.** Step 4 reads receipts through the artifacts API (`scripts/read_receipt.sh`). OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Every `ledger:NNNN` citation went dead when the ledger rolled at 2026-09-23T14:00:47Z.** Citations are now `<row timestamp> lane=<lane>`, which survive a roll. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 5.3 named the hand-run agent trigger as a direct path, which failed with Permission denied and read an ambient signing key.** The trigger is retired (OMN-24414); step 3 now names the signed deploy step and its terminal event. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`read_receipt.sh` printed `VERDICT NONE` with no positive control,** although this skill says every zero is proven by one. It now prints the newest receipt of the same surface in the repo when the sha has none, and step 4 names the `lane-h` surface, which can disagree with `lane-k`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **The probe called a ping-pong "running" from the last 200 records and the 10-minute journal count alone,** while neither topic grew during its own sample (18:29Z). The `BRANCH` line now carries the sampled growth and says `idle during the sample` when there was none. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 3a had no branch for a sha that the agent built after its trigger run's verify job had ended,** so a completed job with lane-j `VERDICT NONE` had no next step (6fe05c35: verify job cancelled at 14:08:57Z, built at 19:46:56Z, still no receipt at 20:50Z). Step 3a now names the only two writers of that receipt and says to read `reemit_candidates` first. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **The swap-traffic threshold (10000 KB/s) flagged an idle host as saturated,** and the first `vmstat` line (the average since boot) was read as a sample. The threshold is now about 50000 KB/s on the samples after the first, next to memory PSI. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`read_receipt.sh` never compared the receipt payload with the artifact name,** so a payload for c159b711 inside a 6fe05c35 artifact, or payload lane lane-k inside a lane-j artifact, read PASS. It now prints `NAME_PAYLOAD_DISAGREE`. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **`read_receipt.sh`'s positive control walked the 1000 newest artifacts,** which covered only 3 to 4 hours, so at 21:18Z it reported FAILED for 6fe05c35 and eb81f73f and every NONE was unproven. The control now runs the same exact-name query on the sha's ancestors, an unproven zero is its own verdict `NONE_UNPROVEN`, and step 4 says what to do with it. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
- **Step 3a called every published-never-accepted sha queued behind the deploy effect's lag,** even with lag 0 on both groups (962aefc0 at 21:18Z), which sent a lane to wait for a drain that never comes. The probe and step 3a now split queued from nothing queued, and trace the correlation id for the second. OMN-19230 lineage, fixed 2026-09-23 by the omni-skill-fixes pass.
