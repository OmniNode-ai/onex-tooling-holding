---
name: delegation-health
description: One read-only check that lab delegation is actually flowing. Counts delegation_events in the lab projection per provider over 1h, 2h and 24h, marks the providers the rendered routing expects to carry traffic (the first ordinary rung of each expected tier, never a rung the contract marks explicit_pin_only), reports each pin-only rung with its smoke or pinned-run evidence, judges weighted spread peers with zero first-choice attempts despite enough eligible traffic, counts the lanes running from the ledger, lists lanes claimed since the change that closed without delegated= cells, and prints the share of real runs that ended in a timeout, and prints one VERDICT (OK, DEGRADED with a FIX line, UNREADABLE, UNTRUSTED). queue-status and the session preflight run it too. Use when someone asks "is delegation running", "is GLM being used", after a dev-lane redeploy, and before blaming lanes for not delegating.
prosthetic: true
replaces_when: "A delegation-health projection or node on the bus reports per-provider event rates and a quiet-rung alarm that the dashboard renders and the session-start workflow reads, on two consecutive sessions. On 2026-09-27 the operator had to ask whether delegation was running on the lab host at all; no report said which rung was quiet."
restored_from: "none: new skill (OMN-19855)"
ticket: OMN-19855
---

# Delegation health (prosthetic)

One command, one block, one verdict. It reads only: the lab projection in a READ ONLY transaction,
the contract the runtime rendered, and the ledger.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/delegation_health.py"
```

Requires `registry_root` and `ONEX_LEDGER_PATH`, and the `delegation_health` overlay (below). Takes
about three seconds. `--quiet` prints only the VERDICT and FIX lines (the preflight row uses it).

Exit `0` OK, `1` DEGRADED, `2` UNREADABLE (overlay, ssh, container, query or contract read failed;
the reason and one FIX line are printed), `3` UNTRUSTED (the table read zero rows in total, so a
zero has no positive control, CLAUDE.md rule 16). Exits 2 and 3 are never reported as healthy.

## What it prints

```
DELEGATION-HEALTH read=<UTC> db-now=<UTC> window=120m table rows=N newest=<UTC>
  <provider> <model> 1h=a 120m=b 24h=c last=<UTC> backends=<ids> EXPECTED(<tier>)
  ...
  per-backend attempts (attempt_history, real events; a climb counts as an attempt):
    <backend_id> <host:port> tier=<tier> 1h=a 120m=b 24h=c accepted=d
  accepted runs by backend/host (delegation_events backend_id and host columns, ...):
    <backend_id> <host> 1h=a 120m=b 24h=c newest=<UTC>
    not recorded (backend_id or host NULL or blank) 1h=a 120m=b 24h=c newest=<UTC> (never counted under a backend)
  pin-only rung <backend_id> (<provider>/<model>, <tier>; ordinary routing excludes it): <evidence>
  spread-peer check: min expected 5 first-choice attempts in 120m (attempts: the attempt that enters a tier, in each real event's attempt_history)
    spread peer <backend_id> (<model>, weight <w>) expected=<n> observed=<n>
  outcomes (real runs, terminal_failure_cause): timeouts 1h=a/b 120m=c/d (p%) 24h=e/f; DEGRADED at 50% of at least 20 runs in 120m
  lanes running (open CLAIM, row inside window): N <lanes>
  terminals without delegated= cells, lanes claimed since <stamp> (report only): <lane>=<n> ...
VERDICT: OK | DEGRADED reason=... | UNREADABLE reason=...
FIX: <the one command to run next>
```

## How to read the verdict

| Verdict | Meaning | What to do |
| -- | -- | -- |
| `DEGRADED ... local/<model> ... had 0 events` | the local rung answered nothing in the window while lanes ran | run the FIX smoke; if it answers, lanes are not delegating: brief text steps through `onex delegate` (`/omni:lane-brief` part 3a.9) |
| `DEGRADED ... <provider>/<model> (<tier> rung <backend_id>) had 0 events` for a non-local tier | the first ordinary rung of that tier answered nothing; unpinned it answers only after the rungs before it refuse | run the FIX smoke, which pins `--backend-id <backend_id>`; a refusal naming the fault-pin guard is the dev-lane pin defect, record it with `/omni:friction-record` |
| `DEGRADED pin-only rung <backend_id> ... had N attempts and 0 accepted answers in 24h` | a smoke or pinned run reached the rung and none was accepted | run the FIX smoke with the pin; if it answers pong the line clears, if it fails the rung is down |
| `DEGRADED harness rung <backend_id> ... had N attempts and 0 accepted answers in 24h` | a Claude Code harness outside the rendered contract ran and none of its answers was accepted, even with no lanes running | run the FIX through harness-delegate; read `receipt.json` error and check |
| `DEGRADED timeouts dominate: <a> of <b> real delegations (<p>%) in 120m ended in timeout` | at least half of the real runs in the window (and at least 20 runs) got no terminal event before the deadline, so no model answered them; the rungs' own counts say nothing about those runs (OMN-19998). Judged with or without lanes running | run the FIX smoke; if it times out too, the request is not reaching a consumer that can route it: compare the members of the delegation-request consumer group on the dev broker with the dev runtime's own container, and read the dead-letter topic for `failure_class=no_dispatcher` |
| `DEGRADED expected tier <t> has no model with a live endpoint` | the rendered contract routes that tier nowhere | a routing defect on the lane: read the contract the FIX names |
| `DEGRADED typed-decision rung <backend_id> ...: credential <secret_ref> is not registered on <host>` | the Jev rung's key is not in that host's local credential store, so every decide step abstains `credential_not_registered` and decisions drop a rung (OMN-20406) | register the key the FIX line names with `onex secret set <secret_ref>` (stdin value) on that host; rule 22 needs a durable OPERATOR-CONSENT row naming the credential first, and no lane creates it |
| `DEGRADED spread peer <backend_id> ... drew 0 first-choice attempts` | its weighted share of real eligible traffic met the overlay minimum, but it drew nothing | read the runtime's rendered placement and sample `backend_id_for_tier` over 1000 random keys for an eligible class; if the share is correct, check traffic reaches `onex delegate --locus deployed-lane` |
| `UNREADABLE` | the read failed | run the FIX line; never read "no events" from it |
| `UNTRUSTED` | zero rows in the whole table | the writer or the migration, never "nobody delegated" |

A pin-only rung prints `no smoke or pinned run in 24h` when nothing reached it, and that is a report,
never DEGRADED; `PASS attempts=<n> accepted=<n> in 24h, newest <UTC>` is the proof it is alive; `FAIL`
is the DEGRADED case above.

An expected rung whose backend row was read is judged by that backend's own attempts in the window: a
model that two backends serve keeps the model's count alive while one of them is silent, and the verdict
no longer reads the model's count for it. The timeout share reads `terminal_failure_cause` from the row as
JSON, so a table without the column reads as not judged and says so on the outcomes line.

With no lanes running, a quiet expected provider is not judged. Spread peers are judged from real
eligible traffic regardless of ledger lane status. The terminals line is a
report, never a refusal. A lane listed there closed a TERMINAL with neither `delegated=<n> runs=<ids>`
nor `delegated=0 delegation_reason=<why>`, which is the contract `onex-delegation-accounting`
(ops_tooling_pkg) counts. The check uses that module's own classification, so the two never
disagree. Only lanes whose first CLAIM is at or after `SILENT_SINCE` in the script (the moment this
became mechanical) are listed; `--silent-since <stamp>` reads another window.

## Where each number comes from

- **The lab.** The `delegation_health` overlay in the onex-overlays plugin names the environment
  variable holding the ssh target, the compose project, its postgres and runtime services, the
  database and the rendered contract's path. The script names no host, lane or database of its own
  (deployment facts come from overlays). It finds the overlay through `--overlay`,
  `DELEGATION_HEALTH_OVERLAY_PATH`, or `<root>/delegation_health/overlay.yaml` for each root in
  `ONEX_SKILL_OVERLAY_ROOTS`, the root the session preflight already reads.
- **Counts.** `delegation_events`, the projection the dashboards read, through `docker exec psql` on
  the compose postgres, the same access as the delegation smoke. Windows are in the database clock.
  Events carry the model, not the backend, so a model served by two backends (the lab-host-a and .202
  hosts both serve the local model) is one count, and the line names every backend it covers.
  The per-backend block (OMN-19432) reads each event's `attempt_history`, which names the backend of
  every attempt, so the lab-host-a and .202 hosts and every cloud rung get their own line: host, tier,
  attempts in 1h, the quiet window and 24h, and accepted answers. A backend with no attempt in 24h is
  marked `IDLE(24h)`, or `PIN-ONLY` when the contract excludes it from ordinary routing. It is a report and never changes the verdict. Jev is not a ladder rung, so its
  line counts the decisions the lanes' TERMINAL rows claim in `jev=` cells, read through the work-ledger reader node
  (24h rows) when the overlay names `jev_reader`; a stale, not-moved or unreadable reader answer prints no jev line and
  the ledger file is never read in its place (remove `jev_reader` from the overlay to roll back to the file scan). In this block the host
  comes from the backend's endpoint in the rendered contract, and a climb counts as an attempt, so
  attempts exceed events.
- **Accepted runs by backend/host (OMN-20162).** A separate block reads the `backend_id` and `host`
  columns delegation_events carries for the accepting attempt, grouped by both, so two hosts serving
  one model are two lines from a column. It counts real runs with an accepted answer
  (`quality_gate_passed` true and `terminal_ok` not false), each once, in 1h, the quiet window and
  24h; it never counts attempts and is never mixed with the block above. A run whose `backend_id` or
  `host` is NULL, empty or only whitespace (written before the columns, or with no accepting rung
  recorded) is one `not recorded` line and is never counted under a backend. Any other value is kept
  exactly as stored, never trimmed, so two stored values never share a line. A value that is not one
  printable word (a tab, newline or carriage return in it, a space, whitespace at an edge, or a
  leading `"`) prints as its JSON text in double quotes with the character escaped, for example
  `"192.0.2.127\tx"`, on its own line; the read sends each key as JSON text, so such a character
  can neither shift a count into another cell nor split a row. A row the parser cannot read is
  counted on one `unreadable rows=N` line and never under a backend. Before the migration that adds the
  columns reaches the database, the block prints `unavailable` and the rest of the read is unchanged:
  the query never names the columns (it reads the row as JSON and their presence from `pg_attribute`),
  so the one READ ONLY transaction does not fail. It is a report and never changes the verdict.
  Events with no model are listed as `unmatched`; they are failed runs.
- **Expected providers.** For each tier in the overlay's `expected_tiers`, the first model whose
  backend has a live endpoint and is not `explicit_pin_only` in the contract the runtime rendered, from
  the routing tiers it loaded. Other providers are also judged by the spread-peer check when their
  placement is `spread`.
- **Pin-only rungs (OMN-20341).** The runtime never routes ordinary work to a backend whose rendered
  contract entry carries `explicit_pin_only: true`, so the check reads that flag and never hardcodes a
  backend, provider or tier. Each such live rung in an expected tier is reported, not expected: a tier
  whose live rungs are all pin-only is not an unresolved tier. The evidence is the per-backend
  attempt rows already read (a smoke or any pinned run is a real event whose `attempt_history` names
  the backend): attempts and accepted answers in 24h and the newest attempt. A present result with no
  accepted answer is DEGRADED with a FIX; an absent result is reported; a present passing result is the
  proof. Pin-only rungs never enter the spread-peer or quiet-expected checks. The contract carries no
  flag for an escalation-only rung, so none is judged differently.
- **Harness rungs (OMN-17427).** Lanes call Claude Code harnesses outside the rendered contract;
  harness-delegate writes `harness:<name>:<model>` in each attempt's backend id. Every such rung in
  the projection gets a PASS or FAIL line with attempts, accepted answers and newest timestamps in
  24h. A present result with no accepted answer is DEGRADED regardless of lanes running. The
  overlay's optional `harness_rungs` list declares names to report even when idle; no attempts is
  report only because lanes reach the harness after the lab rung refuses. Acceptance is an explicit
  `accept` decision, or, for legacy harness attempts with a null decision, a passed quality gate.
  Models reached only through these attempts print provider `harness` and the harness backend ids.
- **Typed-decision (Jev) credential (OMN-20406).** Jev is not a ladder rung, so the checks above never see
  it fail. The contract's `typed_decision` backend answers only when its `secret_ref` is in the lab
  host's local credential store, `~/.omninode/delegation/delegation.sqlite`, table
  `local_inference_credentials`; with no value there every decide step abstains
  `credential_not_registered` and the decision drops to the next rung or to the lane. The lab read
  now also runs a host-side probe (`CRED_PY`, after the `@@CRED` marker) over the `secret_ref` of each
  `typed_decision` backend the contract read returned. It opens the store read-only, selects
  `secret_ref` only (never `secret_value`), and prints the host, the store state (`readable`,
  `absent`, or `unreadable: <error>`) and a registered flag per ref. A ref not in the store makes
  the verdict DEGRADED whether or not lanes run, with a FIX line naming the exact key. The probe
  checks the one host the overlay's remote target names, so the other lab hosts need the same check against
  their own store. A probe that returns nothing or unparseable output is UNREADABLE; a lab read with
  no credential section is reported and not judged.
- **Spread peers (OMN-20237).** The rendered backend's `placement` names its tier, rungs
  (`fallback_for`), mode, optional weight (default 1.0), and optional `use_for`. Eligible classes
  are the rung's routing-tier `use_for`, intersected with the peer's `use_for` when present.
  For each rung and eligible class, the group is the rung (weight 1.0) and its eligible spread peers.
  Only real events' tier-entry attempts count (OMN-20844), grouped by backend and `task_type` in
  the quiet window: the first `attempt_history` element, and any later element whose `tier` differs
  from the element before it. The router draws a tier's first choice over the rung and its peers
  when a run starts and again when it climbs into a tier, so a peer that is drawn by a climb sits at
  ordinal 2 or later with `attempt_kind` `whole_escalation`; counting ordinal 1 alone read such a peer
  as zero. Attempts that stay in the tier (a retry, or a sibling after the tier's pick failed) are not
  draws. The query sends each event's `(tier, backend)` path, identical paths counted once, and the
  script folds them. Expected draws sum each class's group traffic times the peer's weight divided
  by the group's total weights, across its rungs. Observed draws count the peer's eligible classes
  once. Zero observed draws with expected draws at least `spread_peer_min_expected` is DEGRADED.
  The deployment overlay sets the threshold (currently 5); below that, zero is plausible by chance.
  Absent means the check is off, and the report says
  `spread-peer check: off (the overlay sets no spread_peer_min_expected)`. A present value must be
  a positive integer or the verdict is UNREADABLE. `fallback` placements are outside this check.
  The per-backend `IDLE(24h)` tag remains a report; the spread-peer finding changes the verdict.
- **Lanes running.** Open CLAIMs whose lane wrote a row inside the window, by merge-drain's
  canonical dangling-CLAIM definition (`drain_map.py`).

In-process runs (`--locus in-process`) never reach the lab projection, so they are not counted here.
That is deliberate: the lab record is the measure lanes are held to.

## Watch mode (OMN-17427)

```bash
uv run --with rich python3 "${CLAUDE_SKILL_DIR}/scripts/delegation_health.py" --watch
```

A live, color-coded view of the same `delegation_events` table, read only: a header with accepted and
failed counts per backend over the last 15 minutes, total cost and the hosts and models that answered,
then the newest 20 rows (America/New_York time, task, routed model, answering backend, host, attempt
chain, latency, cost, status). Green is accepted, magenta escalated, fallback or retried and then accepted,
red failed with its cause, dim no answering backend. The status cell says how the run got there and why the
earlier attempt failed, from `attempt_history`: `accepted - escalated from local-coder (quality gate)` (the
earlier backend failed the quality gate and the run climbed), `accepted - fallback from byok-openrouter
(rate_limited)` (the earlier backend failed on the provider side, or the answer is a substitution),
`accepted - retried x2 (rate_limited)` (the answering backend itself failed first), `failed - byok-openrouter
x3 quota_exhausted, no fallback` (one backend, nothing else tried) or `failed - quality gate on <backend>,
after 1 other backend`. The cell wraps onto a second line inside its column. Rows are written when a delegation finishes, so
the view shows completed delegations only; there is no in-flight state to show. Options: `--interval`
(default 2s), `--backfill` (default 20 rows), `--caller-filter REGEX` (a leading `!` hides matching
`caller_lane`s, for example harness traffic). A failed read shows a red banner with the time of the
last good read and retries; Ctrl-C exits 0.

Replay fallback when the lab or network is down, with no lab access:
`--replay "${CLAUDE_SKILL_DIR}/tests/fixtures/delegation_events_sample.json" --speed 60` in place of
`--watch` (pauses are capped at 3s).

## Using every model (OMN-19432)

RULING 2026-09-30T15:07:51Z (OMN-20237): no model is a fallback-only rung and every usable model
takes real traffic. Weighted spread peers with enough eligible traffic and zero first choices are
DEGRADED; the runtime sampling FIX distinguishes a routing defect from traffic missing the deployed lane.

RULING 2026-09-30T15:09:11Z: no model is a reserve. Read the per-backend block before and after a routing
change: every local host, GLM, OpenRouter and the Jev cells should show attempts, and an `IDLE(24h)` line is
a routing defect to explain (order, tier coverage, a missing spread peer, a stale code path), never a
finding to accept.

## Guardrails

- Read only: no row, restart, redeploy, rotation or ledger write comes from this skill.
- Never append `2>/dev/null` to the command (CLAUDE.md rule 16).
- Jev (the TypeSafe AI plugin) is not a delegation route by operator ruling of 2026-09-22; it is
  used through its own Claude Code plugin, so this check never lists it.

## Known friction (from prior runs)

Read this before the first run. Record new friction with `/omni:friction-record` and add a line here
in the same PR.

- **A lab deploy removed the market package from the infra image and the health read returned
  empty JSON.** The rendered contract and configured routing file were readable, but the read
  imported `omnimarket` to locate the latter. It now reads `DELEGATION_ROUTING_TIERS_PATH`, the
  runtime's own binding. A failed container read stops the remote script with its original
  error; the credential probe and cleanup cannot mask it. This restores the read, not a stopped
  runtime or stale projection. → lane runtime-reads-1640, OMN-19855

- **The operator had to ask whether delegation ran on the lab host at all.** A live read that day
  showed 154 local and 12 GLM events in 24h; nothing reported which rung was quiet or which lanes
  wrote TERMINALs without delegation cells. → dispatch to lane delegation-enforce-83 2026-09-27,
  OMN-19855
- **A weighted spread peer drew zero delegations for a day and the check said OK.** It was printed as
  `IDLE(24h)`, which is a report, while the lane overlay had only just bound it and the client locus
  probe refused every deployed-lane run. A weighted spread peer that draws nothing while its share of
  eligible traffic meets `spread_peer_min_expected` is now DEGRADED, from the traffic itself rather
  than from lanes running. → lane gptoss-traffic-20237 2026-10-01, OMN-20237
- **A spread peer the router had drawn three times in 120m was reported as drawing zero.** The
  check counted ordinal 1 of each `attempt_history`; a peer that is drawn when a run climbs into its
  tier sits at ordinal 2 or later, so only pinned and direct starts were counted. The count now takes
  the attempt that enters each tier. → lane omn20844-spcnt 2026-10-13, OMN-20844
- **A pinned rung that routing never picks was reported DEGRADED.** queue-status printed `DEGRADED
  reason=delegation gemini/gemini-2.5-flash (cheap_cloud rung cloud-gemini-pro) had 0 events in 120m
  while N lanes ran` at 2026-10-02T08:32:37Z, for a rung the contract marks `explicit_pin_only`; a
  pinned smoke answered pong two minutes later. The expected-rung list now skips pin-only rungs and
  reports them with their smoke evidence. → lane pinonly-rung-20341 2026-10-02, OMN-20341
- **GLM read as 0 accepted and unmatched for a day.** The check read 239 GLM attempts in 24h and 0
  accepted, while 220 of the 241 GLM events since 2026-10-02T04:44Z had passed their check:
  harness-delegate emitted no acceptance decision, and the retired
  direct cloud-glm rung left no GLM endpoint in the rendered contract. Harness attempts now emit
  decisions and reasons; legacy passed checks count as accepted, and harness rungs have their own
  evidence lines and verdict. → lane glm-route-2a21 2026-10-03, OMN-17427
