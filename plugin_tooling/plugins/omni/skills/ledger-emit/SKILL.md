---
name: ledger-emit
description: "Put one rolling-ledger row on the message bus as its typed work-ledger event, by running the work-ledger emit node. A thin shim: it holds no Kafka client and no producer, it runs `node_work_ledger_emit_effect`, which types the row and hands it to the durable emit-effect spool (never-drop for duty_critical topics). Use to emit a row that is already on the ledger (a backfill, or a row written while the onex-ledger dual write is off), and to check that a row can be typed. It never appends to the markdown ledger; `/omni:ledger-write` does that, and the markdown file stays authoritative in stage 1."
ticket: OMN-19513
---

# Ledger emit

Stage 1 of retiring the manual markdown ledger (RULING 2026-09-28T20:30:33Z, lane orchestrator-83,
ticket OMN-19513). Every canonical row type has one event on one topic family,
`onex.evt.omnimarket.work-ledger-<type>.v1`, all `duty_critical`. The node
`node_work_ledger_emit_effect` (omnimarket) types a row and hands it to
`node_event_emit_effect`'s spool outbox, so a lab outage loses no row. The lab's
`node_projection_work_ledger` folds the events.

This skill is only the way to run that node. Publishing is the node base's job: no skill and no
lane calls Kafka.

## Run it

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/emit.sh" --row "<the exact ledger row>"
```

The row is the line exactly as it stands on the ledger (or a multi-line row through
`--row-file <path>`). The reply is the node's typed result. Read three fields:

- `accepted: true` means the event is durable on the spool, whether or not the broker was reachable.
  `published: false` beside it means the lab was unreachable and the spool holds it.
- `refusal` set means the row cannot be typed (no stamp, or a type outside the eleven canonical
  ones). Nothing was spooled. Fix the row's type; do not emit a legacy type.
- `error` set means typing worked but the spool refused the event.

`registry_root` must be set (no default). `ONEX_BIN` overrides the CLI wrapper, which is
`$registry_root/omnibase_infra/scripts/onex`.

## What it does not do

- It does not append to the rolling ledger. Write rows with `/omni:ledger-write`, and let the
  `onex-ledger` dual write (`ONEX_LEDGER_BUS_EMIT=on`) emit them; this skill is for the row that
  is already on the file.
- It does not read the projection. The parity check
  (`python -m omnimarket.nodes.node_projection_work_ledger.parity`) compares the file with it.
- It is not consent, and emitting a row never authorises anything the row would not.

## Known friction

- The Mac's published copy of the node (`node_work_ledger_emit_effect`) exists only once the
  omnimarket release carrying it is installed in the CLI venv. Before that, `onex node` answers
  `Unknown node`. Read that as "not released yet", not as a broken row.
