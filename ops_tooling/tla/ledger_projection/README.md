# Ledger projection model (OMN-20275, unenforced-rulings plan unit M6)

Deliverable 1 of unit M6: the design note for the rendered work-ledger projection, the TLA+ model
`LedgerProjection.tla`, its results and the independent verdict (`REVIEW.md`). Deliverable 2, the
node with partition, lag and crash tests, is built only after this one, against this note.

The ruling of 2026-10-12T19:51:09Z (OMN-20275) moves work-ledger authentication to the writer's
broker identity: every host appends over the bus, the ledger service records the broker
principal as the row's writer, and the markdown ledger becomes a rendered projection. The append
half is `tla/ledger_bus_append` (the serve process assigns `ledger_seq` under the ledger lock,
publishes the row event before it commits the command offset, and republishes the event on a
duplicate request). Its README lists the projection consumer as not modelled. This model is
that half.

## Scope

In scope: one projection node per markdown file, on any host, rendering the rows of one ledger
(`ledger_id = rolling-work-ledger`) into a markdown file in `ledger_seq` order. One node owns one
file; deliverable 2 enforces that with an exclusive lock beside the file, as the serve process does
for the ledger of record. Its inputs are:

- the row events of the eleven row types, one topic per type (and version), so arrival order
  across topics is arbitrary (`TopicOf` puts seq 2 on its own topic);
- the ledger of record, read by seq range through the ledger query path, to repair a gap; and its
  head (the highest `ledger_seq`), read by the lag probe.

Out of scope:

- the append path and `ledger_seq` assignment (`tla/ledger_bus_append`);
- the database projection `work_ledger_rows` (omnimarket `node_projection_work_ledger`), which
  may serve as the repair source but is not the rendered file;
- rows that predate `ledger_seq` (seq NULL). The node starts from a baseline file whose last seq
  is recorded in its first line; the history before it is copied once and never re-rendered;
- the rendered text of one row: the node writes the event's `raw_row` as it stands.

## Record identity

A record is `(ledger_id, ledger_seq)`. With one ledger that is the seq. `row_id` (the sha256 of the
raw row) is a content check, never the identity: two distinct rows can carry the same text, and a
projection keyed on the text drops the second (mutation `content_identity`). When an event or a
repair read names a seq the file already holds, the node compares `row_id`: equal is a duplicate
and is dropped; different is a conflict, and the node blocks at that seq rather than overwrite or
skip (a build obligation; the model gives each seq one text).

## Checkpoints

1. **The rendered file is the watermark.** The file holds rows baseline+1 .. W in order, so W is
   the baseline plus the count of complete rows, read from the file on recovery. A torn last line
   is truncated on recovery before W is read. A second file holding W, written after the rows,
   renders a row twice after a crash between the two writes (mutation `sidecar_watermark`).
2. **The consumer offset is committed only over events at or below W**, per topic, as the longest
   read prefix whose seqs are all rendered. A crash then costs a redelivery, never a row.
   Committing on receipt (variant `commit_on_receive`) also passes, because a row lost with its
   event is repaired from the ledger of record; the adopted rule keeps the repair read for
   events that were never published.
3. **The pending set is volatile.** Events received past W+1 wait in memory; a restart drops them
   and rebuilds them from redelivery and repair.

Rendering takes only seq W+1. An event at or below W is a duplicate (redelivery after a crash, the
serve's republish on a duplicate request, a late event after its repair) and is dropped.
Rendering in arrival order (`arrival_order`) or rendering an event at or below W again
(`no_seq_dedup`) breaks order or duplicates a row.

## Gaps

A gap is a seq W+1 the node does not hold while it knows a later seq exists: a pending event past
it, or a source head above W read by the lag probe. The probe is what reveals a lost last row,
which no later event shows (`no_head_probe`). The node repairs a gap by reading W+1 from the
ledger of record. When the source cannot supply it, the node **blocks**: it renders nothing past
the gap, reports the seq, and keeps retrying; a later repair or a late event lifts the block. It
never skips a gap (`skip_gap`), never waits silently for an event that may never come
(`no_repair`), and never retries a missing row silently (`no_block`).

The environment admits: arbitrary interleaving across topics, arbitrary lag, at-least-once
delivery and one republished duplicate (`MaxRepublish`), a row whose event is never published
(`Unemitted`, the live form the 2026-10-04 parity measurement found), a row the repair source
cannot supply (`SourceMissing`) and node crashes (`MaxCrashes`). A network partition between the
node and the broker is a stretch with no node steps; weak fairness assumes it heals.

## Properties

- `NoRecordLost` (safety): every seq up to the highest rendered seq is rendered; the projection
  never moves past a row it does not hold.
- `NoDuplicate` (safety): no seq is rendered twice.
- `InOrder` (safety): row i of the file is seq i.
- `GapRepairedOrBlocks` (liveness): a gap at seq k leads to the file holding k, or the node
  blocking.
- `EveryRowProjectedOrBlocked` (liveness): every accepted row is eventually and permanently
  rendered, or the node is blocked short of it. This covers the lost last row.
- `TypeOK` (type invariant).

Reachability controls are checked on adopted configurations and must be violated: each
violation is the witness that the adopted run reaches the path it claims, so its pass is not
vacuous. `NotRepairedAfterCrashAndDuplicate` is violated by a state in which every row is
rendered by a node that crashed before the file was complete, recovered, and dropped a
duplicate event on receipt (seq 2 is unemitted, so it came by repair). Two audit variables,
`dropped` and `lenAtCrash`, record that history; nothing else reads them. `NeverBlocked` and
`TailNeverRendered` witness the block and the lost-tail path. The CI check requires each witness
configuration to use the constants of an adopted configuration.

## Results

`expected.tsv` names each configuration's kind and expected outcome. Every configuration uses
`N = 3`, two topics, seqs 1 and 2 with equal text, one crash (two in `adopted_two_crashes`) and one
republished duplicate. Run on lab host h908 (2026-10-13, TLC 2026.09.25, 4 workers), each in under
two seconds:

| config | kind | expectation | result |
| -- | -- | -- | -- |
| `adopted` | adopted | pass; seq 2 never published | no error, 5,405 distinct states |
| `adopted_tail` | adopted | pass; seq 3, the last, never published | no error, 8,312 distinct states |
| `adopted_source_gap` | adopted | pass; seq 2 never published and the source cannot supply it | no error, 2,436 distinct states |
| `adopted_two_crashes` | adopted | pass; two crashes | no error, 11,957 distinct states |
| `commit_on_receive` | variant | pass: the repair path carries a row lost with its committed event | no error, 2,391 distinct states |
| `skip_gap` | mutation | `NoRecordLost` | violated: 1 rendered, 3 pending, gap at 2 skipped, file `<<1, 3>>` |
| `content_identity` | mutation | `NoRecordLost` | violated: row 2 has row 1's text and counts as rendered, file `<<1, 3>>` |
| `no_seq_dedup` | mutation | `NoDuplicate` | violated: the republished event of seq 1 is rendered again |
| `sidecar_watermark` | mutation | `NoDuplicate` | violated: crash after the rows, before the second file; recovery reads W 0 and renders seq 1 again |
| `arrival_order` | mutation | `InOrder` | violated: seq 2 arrives first on its own topic and is rendered first |
| `no_repair` | mutation | `GapRepairedOrBlocks` | violated: seq 2 never published, 3 pending, the node waits forever |
| `no_block` | mutation | `GapRepairedOrBlocks` | violated: the source cannot supply seq 2 and the node retries without blocking |
| `no_head_probe` | mutation | `EveryRowProjectedOrBlocked` | violated: seq 3 never published, nothing reveals it, the file stays at `<<1, 2>>` |
| `witness_repair` | witness | `NotRepairedAfterCrashAndDuplicate` violated | violated: seq 1 rendered, crash before its commit, recovery, the redelivered seq 1 dropped, seq 2 repaired, file `<<1, 2, 3>>` |
| `witness_block` | witness | `NeverBlocked` violated | violated: the node blocks at seq 2 |
| `witness_tail` | witness | `TailNeverRendered` violated | violated: seq 3 rendered through the head probe and repair |

Each `results/<config>.out` starts with the sha256 of the model and of its configuration.
Regenerate them on a lab host with
`python3 tests/tla/test_ledger_projection_model_omn20275.py --jar <tla2tools.jar>`.
`tests/tla/test_ledger_projection_model_omn20275.py` refuses a result from another model or
configuration, an outcome other than the expected one, a property no mutation violates, and a
verdict that does not approve the model's current digest. The commit that records the approving
verdict in `REVIEW.md` also adds the two places that run it: the step "The ledger projection
model, its results and its verdict agree (OMN-20275)" in the required `ci` job, and the
check-only pre-commit hook `ledger-projection-model`. Before that commit the check fails by
design, because no verdict approves the model yet.

## What deliverable 2 takes from it

- Identity is `ledger_seq`; `row_id` is compared, never keyed on. A seq present with a different
  `row_id` blocks.
- The watermark is derived from the file, never from a second file; a torn tail is truncated
  before it is read.
- The offset is committed only over rendered seqs.
- Only W+1 is rendered; anything at or below W is dropped after the `row_id` comparison.
- A gap is repaired from the ledger of record; a gap the source cannot supply blocks, visibly,
  and retries. The lag probe reads the source head on a timer so a lost last row is found.
- Tests: partition (events of one seq range split across topics and delivered out of order,
  and a broker outage), lag (a late event after its repair is dropped as a duplicate) and crash
  (between the row write and the commit, and mid-row with a torn tail).

## Not modelled

- More than one node per file: the lock beside the file excludes it; the model has one node.
- The torn last line and the `row_id` conflict: build obligations above, outside the model.
- The repair source's own consistency: the model takes what it returns as the ledger of record's
  row for that seq, and the head the probe reads as the ledger of record's head. The head must
  come from the ledger of record (the serve process), not from a projection's own maximum seq:
  a projection that lost its tail cannot see the loss in its own maximum.
- A source that later supplies a missing row: `SourceMissing` is fixed, so lifting a block by a
  later successful read, and retrying while blocked, are build obligations, not checked here
  (unchanged retries are stuttering in the model). A late event does lift the block in the model.
- Today's code, which deliverable 2 adapts: `bus_emit` puts `ledger_seq` in the event envelope,
  while the typed event model (omnimarket `model_ledger_row_event`) has no `ledger_seq` field;
  and the database projection `work_ledger_rows` is keyed on `row_id`, so of two rows with equal
  text it keeps one, and it cannot serve as the repair source for such a seq. The repair source
  is the ledger of record read by seq.
- Bounds: three rows, two topics, one republished duplicate, one or two crashes. Liveness
  assumes weak fairness of every node step and of the append, so a node that never runs, or a
  broker that never returns, leaves rows unrendered without a block.
