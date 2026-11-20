---
name: morning-brief
description: The morning brief. Reads the last 72 hours (a parameter) of the rolling ledger, live plus archive/, and the existing readers (ruling_mechanisms.py from queue-status, plans_today.py, the morning fire receipts) and prints one list, each item with its source row and evidence, of what was dropped - (a) operator words captured with no RULING or OPERATOR-CONSENT row, (b) rulings no later lane row cites, with the ruling-mechanism audit lines, (c) merged plans with no tickets, (d) lanes that ended blocked, partial, failed, no-host, no-result or interrupted with no later lane on the work, (e) open CLAIMs silent for 45 minutes, (f) unanswered MSGs and open operator asks, (g) morning ticks whose last outcome was not completed - and writes one lane brief per item. It sends the briefs only with --dispatch and closes or decides nothing. Use for "morning brief", "what did we drop", "set the day up", and every morning.
ticket: OMN-17427
---

# Morning brief

A thin shim over `node_morning_brief_effect` (handler `HandlerMorningBriefRun`); every rule lives in the node.

```bash
python3 -B "${CLAUDE_PLUGIN_ROOT}/src/plugin_tooling_pkg/nodes/node_morning_brief_effect/__main__.py" run \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --hours 72
```

Flags: `--hours` (window), `--ledger` (default `ONEX_LEDGER_PATH`), `--fire-receipts` (default the morning
workflows' `fire-receipts.jsonl` under `$registry_root/.onex_state`), `--out-dir` (default
`$registry_root/.onex_state/morning-brief`), `--json`, and `--dispatch`, which sends each brief through the remote-lane
runner (`--detach --no-placement-wait`, so N lanes cost N starts and no waits) with its section 3a pasted from
`lane_brief.py constraints`. Every lane carries `--repo` (the repository its item names, else `ops_tooling_pkg`),
`--parent` and `--ticket`, and its engine is chosen from the pool's live admission, as the throughput tick's lab fill
chooses it: Claude (sonnet) while a Claude slot is free, Codex when the Claude accounts are limited. The list prints each
sent lane with its engine, repository and the runner's answer (`sent: DETACHED ...` or `refused: <why>`).

The first line is `MORNING_BRIEF now=<ts> hours=<h> items=<n> a=<n> ... g=<n>`; the second names each reader's
outcome, so a reader that failed is printed, never read as an empty list. The briefs and `morning-brief.json` land in
a directory named for the run's minute.

Tests: `tests/test_morning_brief_node.py`.
