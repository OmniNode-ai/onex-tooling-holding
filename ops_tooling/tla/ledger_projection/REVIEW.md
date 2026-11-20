# Independent review of the ledger projection model (OMN-20275, plan unit M6)

Each round is a fresh Codex session at high reasoning effort, run read-only in the lane's
worktree on lab host h908, that neither wrote the model nor ran an earlier round. Inputs: the
model, `cfg/*.cfg`, `expected.tsv`, `results/*.out`, `README.md`, the CI check
`tests/tla/test_ledger_projection_model_omn20275.py`, the append half (`tla/ledger_bus_append`),
`bus_emit.py`, and in omnimarket the row event model and the `work_ledger_rows` migrations. The
reviewers did not rerun TLC; they checked each result's digests and read every trace.

The CI check reads the last `VERDICT:` line below. It must approve and name the sha256 of
`LedgerProjection.tla` as committed. A changed model needs a new round.

## Round 1: REJECT (2026-10-13, Codex thread 00000000-0000-4000-8000-000000000000)

On the working tree before the first push.

| Finding | Class | Disposition |
| -- | -- | -- |
| `witness_repair` overstated its evidence: its trace crashed after the file was complete, with no recovery and no duplicate handled. | defect | Two audit history variables, `dropped` and `lenAtCrash`, were added. `NotRepairedAfterCrashAndDuplicate` now requires every row rendered, the node up after its crash, the crash taken before the file was complete, and a duplicate dropped on receipt. The README describes the new trace. |
| `SourceMissing` is fixed, so a later successful read and retries while blocked are unchecked; the head must come from the ledger of record; the typed event model has no `ledger_seq` field and `work_ledger_rows` is keyed on `row_id`. | residual | Added to README "Not modelled"; the repair source is fixed as the ledger of record read by seq. |
| The CI check only counted witnesses. | residual | The check requires each witness's CONSTANTS block to equal an adopted configuration's. |
| The work existed only locally. | residual | Pushed; later rounds review a pushed commit. |

VERDICT: REJECT model-sha256=ecfd29f7377c8a95b08adb1c15f15635abf8f083dd46cfd1e2b908cd13f51ec1

## Round 2: REJECT (2026-10-13, Codex thread 00000000-0000-4000-8000-000000000000)

On pushed commit 16355057514ce24135b4a7cc63bb77ff114650e4. Every round-1 disposition was
judged correct, and no finding on the model was a defect.

| Finding | Class | Disposition |
| -- | -- | -- |
| README.md named a CI step and a pre-commit hook the commit did not contain. | defect | The paragraph now says the step and the hook are added by the commit that records the approving verdict, and that the check fails until then (commit dd4657a5a2331698efbdce125c6dde632851475d). |
| Bounds and abstractions (atomic rows, zero baseline, one owner, trusted source and head, bounded crashes); CI checks stored TLC evidence and does not rerun TLC; no distinct witness per adopted configuration. | residual | Recorded; the first two are in README "Not modelled" and "What deliverable 2 takes from it". |

VERDICT: REJECT model-sha256=c578a49a94f254326c3ca2c7136dc784f4fbcfba7258cabd79f4f8974f9ba824 commit=16355057514ce24135b4a7cc63bb77ff114650e4

## Round 3: APPROVE (2026-10-13, Codex thread 00000000-0000-4000-8000-000000000000)

On pushed commit dd4657a5a2331698efbdce125c6dde632851475d, whose model is byte-identical to
round 2's. No finding was a defect. The reviewer confirmed the commit and digest, all sixteen
result headers and outcomes, the witness trace (crash with one row rendered, recovery, the
redelivered seq 1 dropped, seq 2 repaired, file `<<1, 2, 3>>`), that each mutation flips one flag
and fails for its stated reason, that the history variables guard nothing, and that the README
claims are scoped.

Residuals, recorded as build obligations of deliverable 2 or as limits of this evidence:

- Bounds: three rows, two topics, one republish, one or two crashes, weak fairness and eventual
  service availability.
- Assumptions: complete durable row writes, a zero baseline, one file owner, trustworthy source
  contents and head. Torn-write recovery, baseline handling, `row_id` conflicts and ownership
  enforcement are build obligations.
- A source that later supplies a missing row and the retry behaviour while blocked are unchecked.
  The typed row event lacks `ledger_seq`, and `work_ledger_rows` keeps its `row_id` primary key.
- CI validates the stored TLC evidence and does not rerun TLC; not every adopted configuration
  has its own witness (the two-crash instance has none).
- Recording this verdict and adding the CI step and the check-only hook: done in the commit that
  adds this file.

VERDICT: APPROVE model-sha256=c578a49a94f254326c3ca2c7136dc784f4fbcfba7258cabd79f4f8974f9ba824 commit=dd4657a5a2331698efbdce125c6dde632851475d
