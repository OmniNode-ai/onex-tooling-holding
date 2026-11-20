# Independent review of the lab stack reaper model (OMN-20864, plan unit M47)

## Round 1: FAIL

Reviewer: a Codex session at high reasoning effort, read-only, run on 2026-10-13 from
about 12:40Z to 12:45Z.
It wrote neither the model nor the design note. Inputs: the model, `cfg/*.cfg`, `results/*.out`,
[README.md](https://example.invalid/private-repo), the expectation table and test in `tests/tla/`, and the operator-run handler
`handler_lab_removal.py`. It reviewed the first revision of the model (digest `d7ab21d6...5454f`),
judged that every mutation counterexample fails for its stated reason, and failed the gate on the
findings below.

**VERDICT: FAIL.** Model digest: `d7ab21d656e67d81031a1a0ee084af3583c743a19a96d462ca29f18979a5454f`

| Finding | Severity | Disposition in round 2 |
| -- | -- | -- |
| The deadline read "not overdue, or alarmed", so an alarm excused a closed stack for good, and an alarm survived reuse into later closures. | BLOCKER | Fixed. `RemovedWithinOneInterval` has no alarm escape. It is checked where its assumptions hold: no overrun, and failures below the in-pass retries (`adopted`, `adopted_two_stacks`). A failed `compose down` is retried within the pass (`Retries = 2`), and `no_retry` must violate it. `OverdueIsAlarmed` is a separate property for broken assumptions (`adopted_faults`, `silent_failure`, `silent_abort`). An alarm belongs to one closure: entering a closure, reuse and removal each clear it. |
| No progress was required: stuttering satisfied everything, a hung pass stopped the clock, and the clock stopped at 3. | BLOCKER | Fixed. The specification has weak fairness on the reaper's steps and on `Tick`, and the temporal `EveryClosedStackRemoved` is checked without symmetry (`adopted_liveness`, `_reopen`, `_two_stacks`). With `PassOverrun`, `Tick` starts the next interval even while a pass runs, killing it. Lanes act only before the last interval, so every closure falls due inside the horizon. `skip_in_flight` must violate the temporal property. |
| "One interval" had been weakened to one interval plus the pass's runtime. | MAJOR | Stated as decision 8 in [README.md](https://example.invalid/private-repo). The ruled interval is the declared deadline D, the timer period P and the pass cap C satisfy P + C ≤ D, and the model's unit is P. |
| The safety abstraction covers registered uses only. A new CLAIM alone protects no stack, and work after the TERMINAL is excluded. | MAJOR | Scope and decision 7 in [README.md](https://example.invalid/private-repo). The protection covers leased uses, and the lease write is part of the compose guard. `terminal_before_quiesce` makes the quiescence assumption load-bearing: it must violate `NoUserLosesStack`. Overlapping incarnations of one lane are listed under "Not modelled". |
| The clock-skew alternative was insufficient: skew below the stamp resolution does not order rows across a second boundary, and a same-second TERMINAL could keep a stack forever. | MAJOR | Fixed. The adopted rule is a TERMINAL that names the CLAIM it closes (`names_claim`), and no stamp is compared. `stamp_ts_skewed` (TERMINAL stamps up to two ahead) must violate `NeverRemoveLive`. The build obligation is the `closes=` cell on TERMINAL rows. |
| An atomic removal hid destructive work outliving a killed pass: the lock dies with the pass while `compose down` goes on. | MAJOR | Fixed. `compose down` is now a daemon step (`DownOk`, `DownFail`) that happens after a killed pass too. The pass fences the stack before the removal, and a lane refuses a fenced stack. A pass waits for an outstanding removal. `no_fence` must violate `NeverRemoveLive`. The supervised removal and the unknown-outcome rule are build obligations. |
| Shared-host identity and exclusion were assumed. The handler's protections were not carried into the build list. | MAJOR | Build obligations in [README.md](https://example.invalid/private-repo): leases keyed by daemon identity, project and generation, a lock file never replaced, and the protections of `stack-down` kept (declared lanes, lane-named containers, foreign files, no `-v`, `--rmi` or prune). |
| The witness showed removal is reachable, not that time advances or a late closure is removed. | MINOR | Added `witness_late_removal` (a stack closed after one pass read the ledger is removed by the next) and `witness_retry`. The temporal runs cover progress. |
| Counterexamples of `no_lock`, `creator_only_lease`, `last_row`, `last_row_no_relay`, `position_order`, `owner_by_ticket`, `stale_view` and `silent_failure` fail for their stated reasons. | MINOR | Kept. `owner_by_ticket` is described as a deadline miss, not as proven retention forever. |
| The bounds reach every mutation but do not justify general progress claims. Symmetry is sound because renaming preserves the actions and invariants. | MINOR | The bounds paragraph and the symmetry note in [README.md](https://example.invalid/private-repo) and the module say so. |
| The Python gates check outcome names, not causes. | MINOR | Stated in [README.md](https://example.invalid/private-repo). Causes are read from the counterexamples and confirmed in review. |

The revision also found a modelling error of its own: in TLA+, `x' = a \/ b` parses as
`(x' = a) \/ b`, so the first draft of round 2 never set its ghost flags. The flags are
parenthesised, and the safety mutations report `NeverRemoveLive` as expected.

## Round 2: FAIL

Reviewer: a second, fresh Codex session at high reasoning effort, read-only, run on 2026-10-13 from
about 13:23Z to 13:31Z. It is neither the modeller nor the round-1 session. It reviewed digest
`7c6a4088...e002`, recomputed that digest, and found every result file opening with it. It
confirmed each round-1 disposition but one, and it confirmed every mutation and witness
counterexample's stated cause. It found the seven passing runs fully explored, and found that
the three temporal runs check `EveryClosedStackRemoved` over the complete state space. It judged
the skew restriction (`Skews`) sound, because only `ClosedByStamp` reads a TERMINAL's stamp. It
failed the gate on two MAJOR findings.

**VERDICT: FAIL.** Model digest: `7c6a40880230b59bbb82927ff6b27ba6d1d386a3fa32e18638dbe78b3d1be002`

| Finding | Severity | Disposition in round 3 |
| -- | -- | -- |
| The horizon repair was incomplete. Lanes could close a stack in interval 2, whose first overdue tick (interval 4) lies past the clock's end at 3, so the deadline check could not see the latest closures retained. | MAJOR | Fixed. `LanesOpen == now < MaxTime - Interval`, so every admitted closure reaches its first overdue tick inside the horizon. All 24 configurations were rerun on the new digest. |
| CLAIM identity collisions. The model's CLAIM identities are unique, but the build note allowed a wall-clock stamp, which two incarnations of one lane can share. | MAJOR | Build obligation in [README.md](https://example.invalid/private-repo): every CLAIM carries an immutable identity unique across the ledger (its `req=` cell or a minted claim id), kept through relay and leases. A duplicate CLAIM identity is refused, and a TERMINAL with no identity or an ambiguous one closes no lease. Tests: a same-second reopen and two live incarnations of one lane name. Decision 2 says the model's stamp stands for that identity. |
| Aggregate weak fairness suffices only for the bounded abstraction. It does not prove progress under endlessly repeated kills. | MINOR | Stated in [README.md](https://example.invalid/private-repo). Eventual removal assumes that some pass eventually runs to its end. Endless kills are the alarmed case. |
| Temporal obligations start only on record closure. A TERMINAL left in an unfair relay outbox never starts one. | MINOR | Stated in [README.md](https://example.invalid/private-repo) under "Not modelled": the deadline starts when the TERMINAL is on the ledger of record, and relay delivery is the relay's obligation. |
| `skip_in_flight` is a final-pass counterexample. | MINOR | Kept as stated, and not generalised to an endlessly ticking timer. |

## Round 3: PASS-WITH-CONDITIONS

Reviewer: a third, fresh Codex session at high reasoning effort, read-only, run on 2026-10-13 from
about 13:37Z to 13:48Z. It is neither the modeller nor either earlier session. Inputs: the same
files as round 2, with this file's round-1 and round-2 dispositions. It confirmed every round-1
and round-2 disposition, and every mutation and witness counterexample's stated cause. It found
the four passing invariant runs and the three temporal runs fully explored, with
`EveryClosedStackRemoved` checked over the complete state space and no symmetry. It found the
temporal checks non-vacuous, because closures and removals are reachable under each temporal
configuration. It judged the `Skews` restriction sound, and found the plan's two properties
represented with their scope and assumptions stated. It recomputed the digest and found all 24
result files opening with it. It found that the bounded model needs no change, and named two
conditions to record as build obligations before the model gates the build.

| Condition | Severity | Disposition |
| -- | -- | -- |
| Teardown inputs are unspecified. `-p` selects a project but does not bind `down` to the leased generation's configuration, so the ambient working directory or environment can change what it removes. | MAJOR | Build obligation "Teardown inputs bound to the leased generation" in [README.md](https://example.invalid/private-repo): the recorded compose files and environment, a fixed working directory, refusal on missing or changed files, and tests for a changed, missing and unrelated configuration. |
| The shared-network protection was wrong. Leaving out `-v` and prune does not keep the project's own networks: `compose down` removes them. | MAJOR | [README.md](https://example.invalid/private-repo) corrected. Build obligation "Shared networks": a shared network is external in the teardown definition, or the removal is refused without proof that the project owns it alone. Test: another live project expecting a temporarily unattached shared network. |
| The reviewed files were untracked and this section was a placeholder. | MINOR | This section records the verdict, and the reviewed digest is published in the pull request that adds the model. |

The 24 configurations' outcomes on this digest are in [README.md](https://example.invalid/private-repo). `tests/tla/test_lab_stack_reaper_model.py`
fails when this digest no longer matches the model and configurations.

**VERDICT: PASS-WITH-CONDITIONS.**

Model digest: `17c4da3210b5638e9deedd06a48b61fa3b0e5875167b87560939a3a723e47e39`
