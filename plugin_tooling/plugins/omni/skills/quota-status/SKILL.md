---
name: quota-status
description: One read-only check of where provider quota is being spent and where it is refusing. Per provider (GLM, Gemini, OpenRouter, Jev, local) and GitHub it prints calls, capacity events and declared headroom. The CODEX block shows ChatGPT plan usage, headroom, reset times, reading age, credits and daily session totals from local session logs. Use --codex-only for one cheap queue tick read with no lab or ssh. Use when drafting code through Codex, when a delegation refuses, before adding provider lanes, or when asking whether a plan is rate limited.
prosthetic: true
replaces_when: "A durable provider_capacity_events projection (OMN-20154 steps M2 and M3) carries per-attempt provider, HTTP status and code, and routing reads its headroom, so this check reads a table instead of parsing attempt text, on two consecutive sessions. On 2026-09-30 nothing counted calls against a plan window and the only capacity signal was free text inside attempt_history."
restored_from: "none: new skill (OMN-20154)"
ticket: OMN-20154
---

# Quota status (prosthetic)

One command, one block, one verdict. It writes nothing anywhere. This is v1 of the quota tracking the
operator asked for on 2026-09-30: keep the numbers in a skill first, mechanize once the shape is known
(the ticket lists the steps).

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/quota_status.py"
```

Requires `registry_root`, `ONEX_LEDGER_PATH` and the `delegation_health` overlay (the same overlay
`/omni:delegation-health` reads, found through `ONEX_SKILL_OVERLAY_ROOTS`, and the ssh target it names).
`--hours N` changes the reporting window (default 24). Local Codex scan time grows with session history.

For the queue tick, make one cheap local call with no lab, receipt, GitHub or ledger read and no ssh:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/quota_status.py" --codex-only
```

This mode needs no overlay or workspace environment. `--codex-home PATH` overrides `CODEX_HOME`,
which otherwise defaults to `Path.home() / ".codex"`. It prints exactly one `CODEX-QUOTA <json>` line
first, followed by the human CODEX lines. Exit `0` means readable and not LOW, `1` means CODEX-LOW
or a reported rate limit, and `2` means UNREADABLE with a FIX hint. JSON includes primary and secondary
windows, percentage headroom, UTC reset timestamps, seconds to reset, `stale`, `low`, plan, credits,
event timestamp, reading age in seconds and daily session/token totals. A stale reading can exit `0`;
the tick must check `stale` before treating headroom as current.

Exit `0` OK, `1` capacity events seen, `2` UNREADABLE (a source failed; printed by name), `3` UNTRUSTED
(the lab table read zero rows, so a zero has no positive control, CLAUDE.md rule 16).

## What it prints

```
QUOTA-STATUS read=2026-09-30T15:22:18Z window=24h lab db-now=... rows=4298 newest=...
  provider   calls 1h/24h        peak/min hits 24h                       last hit     declared quota
  glm        14/118 ip=3         6        5 (1302x5)                     13:48Z       5h used=33 cap=unrecorded; 168h used=253 cap=unrecorded
  gemini     6/20                5        15 (RESOURCE_EXHAUSTEDx15)     15:19Z       24h used=20/20 headroom=0
  openrouter 19/59               7        0                              -            24h used=59 cap=unrecorded
  local      53/532 ip=6         12       0                              -            no declared quota
  github core 5000/5000 reset 16:22Z graphql 4998/5000 reset 16:16Z (...)
CODEX plan=pro weekly used=22% headroom=78% resets 2026-10-06T13:33:56Z (in 5d 22h) read-age=4m credits balance=62500 has_credits=true unlimited=false
CODEX per-day (UTC): 2026-09-30 sessions=3 tokens=17293
HITS newest first (max 10 of 20):
    15:19Z gemini RESOURCE_EXHAUSTED backend=cloud-gemini-pro via=delegate-skill-orchestrator:code_generation
PATHS (calls by path, top 3):
LANES (ledger TERMINAL cells, N rows in window): lab=55 glm=30 ...; lanes with glm>0: <lane>=<n> ...
LEDGER capacity mentions: 9 (github 2, provider or Claude 7); newest provider or Claude rows:
VERDICT: CAPACITY-EVENTS n=20 in 24h (gemini 15, glm 5) newest 2026-09-30T15:19:54Z
```

## How to read it

| Field | Meaning |
| -- | -- |
| `calls 1h/24h` | Provider calls, one per attempt in an attempt record (a ladder that tried three rungs is three calls). `ip=n` is the part that came from in-process runs |
| `peak/min` | The most calls in one minute by row time. An upper bound, because a ladder's attempts share one row time. Compare it with a per-minute limit such as z.ai 1302 |
| `hits` | Attempts whose error carries a capacity code. `1302` is z.ai's per-minute limit, `1310` its weekly or monthly cap, `1113` no balance or the wrong endpoint, `RESOURCE_EXHAUSTED` Google's quota, `429` any other rate limit |
| `declared quota` | From `quota_limits.json`. `cap=unrecorded` means nobody wrote the plan's numeric cap down: read it off the provider's usage page and record it. `headroom` is the cap minus the calls this workspace recorded, so it is an upper bound: another consumer of the same key is invisible |
| `LANES` | Lanes that reported `glm=` cells on a TERMINAL row. That is the lane-level answer to "who spent the plan" |
| `CODEX` | The newest Codex plan reading by event timestamp. Headroom is `100 - used_percent`; window names come from minutes (`10080` weekly, `300` 5h). A secondary window prints on its own line if present |
| `CODEX per-day (UTC)` | Last seven UTC days, oldest first: sessions on the day of their last event, each recorded final cumulative `total_token_usage.total_tokens` contributing once. Sessions without usage info contribute no measured total; a day with sessions but no recorded total prints `tokens=UNREADABLE` (JSON null) rather than inventing a zero |
| `LEDGER capacity mentions` | Rows that say a usage limit or a rate limit was hit. This is the only place a Claude Code usage-limit kill is recorded, and it is prose |

## Where each number comes from

- **The lab projection.** `delegation_events` on the lab dev lane, through the `delegation_health`
  overlay and `docker exec psql` in a READ ONLY transaction. The one pull covers the widest declared
  window (a week, for the GLM weekly window). The provider of an attempt is read from the host in its
  own error text, then the rendered contract's backend, then the model name.
- **Run receipts.** `$registry_root/.onex_state/runs/*/workflow_result.json`. An in-process run never
  reaches the lab table, so only those are counted from here. If the lab cannot be read, dispatched
  receipts are counted too and the block says so.
- **GitHub.** The operator token's core and graphql buckets, never the rate_limit endpoint body (it read
  `used=0` while real headers read 55 to 351 in the same minutes, OMN-19470). Core comes from the
  `x-ratelimit-limit`, `-remaining`, `-used`, `-reset` and `-resource` headers of one real
  `gh api --include` call; graphql comes from the `rateLimit { limit remaining used resetAt }` field of one
  GraphQL query. A missing header or field, a non-2xx status or a resource other than `core` is
  UNREADABLE, never a full bucket. A reading spends one core and one graphql point (the endpoint was free), so
  read it once per question and never in a loop. The GitHub App bucket is not readable from here. GitHub quota work is owned by the OMN-19470 family; this line is a
  readout only.
- **Codex.** `${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-*.jsonl`, today and the preceding
  seven UTC date directories. The newest `event_msg` with `payload.type=token_count` and non-null
  `payload.rate_limits` supplies the plan windows, credits and rate-limit flag. Null `info` or null
  or missing `rate_limits` on other lines is normal; malformed and incomplete lines are skipped.
  These are Codex session logs, never `auth.json` or credential files. No Codex usage subcommand
  exists. Missing logs or no plan reading is UNREADABLE with a FIX hint, never zero usage.
- **The ledger.** TERMINAL cells and capacity-mention rows in the window.
- **Declared quotas.** `quota_limits.json` beside this file. Each entry has a window, a cap or null, a
  source and an as-of date. Edit it by pull request when a plan or a cap changes. Do not guess a cap.

If a window's `resets_at` (Unix seconds, rendered in UTC) is earlier than the read time, that window
is STALE: it has reset since the reading, so its old `used_percent` no longer applies. The page says
so and JSON sets `stale=true`; it never assumes the reset means zero usage. `read-age` shows how long
ago Codex recorded the measurement. CODEX-LOW appears in the header when either window has less
than 10% headroom or `rate_limit_reached_type` is non-null. In a full run it appends
`CODEX-LOW headroom=<h>%` to VERDICT without changing existing exit codes; an unreadable Codex source
joins the existing `partial` failure handling. Numeric `codex=` ledger cells remain counts, and
`codex=<thread_id>` TERMINAL cells count once in LANES.

Codex is the first drafting route for code work this month, under RULING 2026-09-30T18:01:56Z
lane=codex-first (OMN-20106), while the current ChatGPT plan has about a month left and a couple of
resets. A LOW reading means fall back to the lab route (`lab_crush.py`), then GLM.

## Known gaps (from the OMN-20154 survey; each is on the ticket)

- z.ai 1302 is missing from the runtime's quota policy, so the runtime retries into it. This check
  counts it; the runtime does not yet record it.
- The runtime's quota ledger is in memory and process-local. Nothing durable holds capacity events, so
  this skill parses attempt text. Attempt records carry no provider, status or failure class.
- Attempt text is matched on a status or a provider code, never a bare number, so a weak-output message
  that says "1302 tokens" is not a hit.
- The GLM 5-hour and weekly caps, and the plan tier, are not recorded anywhere. `used` is printed so
  the cap can be compared with the provider's usage page and then written into `quota_limits.json`.

## Guardrails

- Read only: no row, restart, rotation or ledger write comes from this skill.
- Never append `2>/dev/null` to the command (CLAUDE.md rule 16). A source that fails is printed by
  name and the exit code is 2; it is never shown as zero.
- A zero on a provider line needs a positive control: the header names the lab's row count and newest
  row time, and the same block shows other providers' non-zero counts.

## Known friction (from prior runs)

Read this before the first run. Record new friction with `/omni:friction-record` and add a line here
in the same PR.

- **The Codex reading is only as fresh as the newest Codex call on THIS Mac.** Lab hosts have no
  Codex. A quiet day shows an old reading; the page says its age and flags windows that have reset.

- **The first survey read a different, stale analytics database and reported no rate-limit hits in 24
  hours.** The lab projection held 5 z.ai 1302 hits and 10 Gemini 429 hits in the same window. This
  skill reads the lab through the overlay, never `OMNIDASH_ANALYTICS_DB_URL`. → OMN-20154, 2026-09-30
