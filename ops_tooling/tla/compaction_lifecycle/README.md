# Compaction lifecycle model (OMN-18531, plan task TA.1)

The TLA+ model `CompactionLifecycle.tla` of the compaction lifecycle in the context service plan
(`beta/plans/2026-10-01-claude-code-context-and-delegation-adapter-plan.md` in
docs_repo, section 6 "Compaction transaction" and "Boundary algorithm", task TA.1).
It is the model-before-build step the plan names for Track A: TA.11 (the orchestrator) and TA.13
(the receipts projection and install confirmation) cite it. Nothing here changes runtime code.

## Scope

In scope, for one session:

- **Per candidate:** `prepared`, and `conflict` for differing `assembly_hash` under one
  `candidate_id`. A candidate is named by the version vector it was built at (`cvv`).
- **Per activation:** `activated`, then `installed`, `install_mismatch`, `not_installed`
  (`native_compaction`, `not_selected`), `uncertain(capture_gap)` or `conflict`.
- **Per invocation:** `fallback`.
- **Actors:** precompute (an invocation of kind `pre` that builds and keeps a candidate), manual
  and auto trigger (invocations of kind `real`), two concurrent invocations on the same inputs
  (`NInv = 2`, they may share one kept candidate), an edge that misses its deadline while the
  orchestrator completes (`EdgeTimeout`, then the activation is published late), the harness
  compacting natively or with an accepted package (`Compact`), and the capture stream.

Out of scope, and so not claimed: chunking of the package reply (P15); the session barrier of
transaction step 2 (its three failures enter as the nondeterministic `Fail`, a `fallback` before
`activated`); the boundary algorithm's chain walk and `preservedMessages` handling (the model
takes the boundary's content as given: native, an accepted activation, or an accepted activation
whose installed text differs); the per-session current-context projection (`retired`, boundary
algorithm step 5); tenancy; real time. The T0.1 rows the plan marks `untested` (P7a to P7c,
precompute) are not assumed to hold: `pre` invocations are a possibility the model allows, not a
claim that the harness supports them.

## Identities

- `candidate_id` is the version vector at build (`cvv`). Two invocations on the same inputs build
  the same candidate; a precompute's kept candidate is reused by a later invocation.
- `activation_id` is one per invocation that returns a package (the model uses the invocation's
  number). `invocation_id` is the invocation's number. One activation is never shared.
- An invocation is bound to the boundary that is next when it starts (`tb`). The model checks the
  binding the plan's rule needs, because the plan's wording, "published between the previous
  boundary and it", fixes the binding to the publish time, and a late publish is stranded (see
  Findings).

## Environment

The environment admits, with no fairness: the version vector growing at any time (`VVBump`, up to
`MaxVV`); an orchestrator that fails before `activated` (`Fail`) or crashes after minting
(`Crash`); the edge timing out at any point before its boundary; a boundary record being dropped
by capture (`AllowDrop`); a later item of the session being captured before the boundary's own
record, or the record being captured late (capture delay and reordering, in every configuration); receipt events delivered in any order, and any received event redelivered up to
`MaxDup` times. Capture duplicates are not modelled separately: the captured sets are sets, so a
duplicate capture is the same state, and the event duplicates it would cause are the redeliveries.
Weak fairness is assumed for the orchestrator's steps, the edge timeout, capture of a boundary
record that was not dropped, capture of the later item, delivery and the confirm compute. It is
not assumed for `Start`, `Fail`, `Crash`, `Compact`, `VVBump` or `DropB`.

The fold of an activation joins the received facts by this precedence: `installed` and
`install_mismatch` dominate `uncertain(capture_gap)`, which dominates `not_installed(not_selected)`,
which dominates `not_installed(native_compaction)`; `installed` joined with `install_mismatch` is
`conflict`. The plan states the first rule and the `conflict` rule; the order among the three weak
facts is this model's choice (a join needs a total order, and a gap is the one that alarms).
`installed` is derived only for an activation whose `activated` event the confirm compute has
received, because the observed hash is compared with the one that event carries.

## Properties

Safety (`INVARIANT`):

- `NoInstallWithoutActivation`: an `installed` or `install_mismatch` fact is published only for an
  activation whose `activated` event was published.
- `OneStatePerIdentityUnderAnyArrivalOrder`: the fold's state of an activation, updated on each
  arrival including redeliveries, equals the join over the set of events received.
- `StaleCandidateNeverInstalled`: an installed activation's candidate version vector equals the
  one recomputed when the activation was minted (the P7c revalidation).
- `FallbackNeverConflictsWithAnotherInvocation`: an activation is `conflict` only on its own
  `installed` and `install_mismatch` evidence, never through another invocation's `fallback` of
  the same candidate.
- `NoCompleteBeforeInstalled`: an attempt is called complete only when the fold holds `installed`.

Liveness (`PROPERTY`), under the fairness above:

- `EveryActivationResolves`: for every activation whose boundary has happened, the fold reaches
  `installed`, `install_mismatch`, `not_installed`, `uncertain` or `conflict`. The antecedent is
  the plan's "captured stream advances": the boundary happened, and weak fairness delivers the
  later item.

`TypeOK` is checked everywhere. The candidate `conflict` is a definition in the fold (differing
`assembly_hash` under one `candidate_id`), not a checked property; the model does not build
differing hashes. An activation `conflict` is a state of the join the model's environment cannot
reach on its own (one boundary never yields both facts); the configuration `fallback_by_candidate`
shows the property is what keeps another invocation's fallback from reaching it.

Reachability controls are checked on adopted instances and must be violated: each violation is the
witness that the adopted runs reach the path they claim. They cover `installed`,
`install_mismatch`, `not_installed` for both reasons, `uncertain(capture_gap)`, a candidate stale
at mint, a fallback beside another invocation's activation of the same candidate, and an
`uncertain(capture_gap)` published and then followed by `installed` for the same activation.

## Findings

1. **The activation's boundary must come from the invocation, not from the publish time**
   (mutation `publish_window`, violates `EveryActivationResolves`). With an edge that misses its
   deadline, the harness compacts natively and the orchestrator publishes `activated` afterwards.
   Judged against "the boundary after its publish", that activation waits for a boundary that may
   never come, and no later captured item resolves it. TA.13's step 4 must attach an activation to
   the boundary the invocation was issued for, taken from what the command carries
   (`newest_turn`), so it resolves to `not_installed(native_compaction)` from that boundary's own
   native record, as the transaction's step 8 says it does.
2. **The weak facts are published, then superseded**, and `uncertain(capture_gap)` is not final.
   A later item can be captured before the compact record, so the confirm compute can publish
   `capture_gap` and later `installed` for one activation (witness `gap_then_installed`). The
   precedence (mutation `last_wins`, violates `OneStatePerIdentityUnderAnyArrivalOrder`) and the
   rule that a gap is a published fact, not a verdict, are both needed; the alarm on a gap should
   be conditioned on its still standing when the fold settles.
3. **A missing compact record needs the gap rule** (mutation `no_gap_rule`). When capture drops
   the record, only the rule "a later item with no compact record for the boundary" resolves the
   activation.
4. **`installed` must be judged against a published activation** (mutation `trust_boundary_line`).
   If the package can be sent before `activated` is published, an orchestrator crash between the
   two leaves an activation line in the transcript with no activation; trusting the line alone
   publishes an installation fact for it. The adopted order is publish `activated`, then send; the
   confirm compute waits for the received `activated` event.
5. **Complete is the fold's, not the reply's** (mutation `complete_on_reply`), **revalidation is
   needed at mint** (mutation `no_revalidate`), and **a fallback is keyed by invocation, never by
   candidate** (mutation `fallback_by_candidate`).

## Results

`expected.tsv` names each configuration's kind and expected outcome; each result in `results/`
carries the model and configuration digests on its first lines. Run on lab host h907 on
2026-10-15 with TLC 2.19 (2024-08-08), Temurin JRE 21.0.12, 3 workers. The adopted safety
instance is `NInv = 2`, `NB = 2`, `MaxVV = 2`, `MaxDup = 1`; the liveness instance is
`NB = 1`, `MaxVV = 1` (a liveness check at `NB = 2` did not finish in nine minutes).

| config | kind | expectation | result |
| -- | -- | -- | -- |
| `adopted` | adopted | the five safety properties hold | no error, 6,354,386 distinct states |
| `adopted_drop` | adopted | the same, with capture dropping a record | no error, 10,659,230 distinct states |
| `adopted_live` | adopted | `EveryActivationResolves` | no error, 53,745 distinct states |
| `no_revalidate` | mutation | `StaleCandidateNeverInstalled` | violated |
| `last_wins` | mutation | `OneStatePerIdentityUnderAnyArrivalOrder` | violated |
| `fallback_by_candidate` | mutation | `FallbackNeverConflictsWithAnotherInvocation` | violated |
| `complete_on_reply` | mutation | `NoCompleteBeforeInstalled` | violated |
| `trust_boundary_line` | mutation | `NoInstallWithoutActivation` | violated |
| `publish_window` | mutation | `EveryActivationResolves` | violated: a lasso with the activation published after its boundary |
| `no_gap_rule` | mutation | `EveryActivationResolves` | violated: a lasso with the compact record dropped and a later item captured |
| `witness_*` | witness | the reachability controls above | each violated |

The five safety properties and the liveness property each have a mutation that violates them
(`tests/tla/test_compaction_lifecycle_model_omn18531.py` refuses a change that removes one). The
design-review verdict is not part of this change: the plan asks that it be cited in TA.11's PR body.
