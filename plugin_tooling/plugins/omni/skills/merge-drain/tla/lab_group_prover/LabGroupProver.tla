--------------------------- MODULE LabGroupProver ---------------------------
(***************************************************************************)
(* Batched runtime lab proofs in the landing controller (OMN-18893).       *)
(*                                                                         *)
(* One repository. The landing controller (a launchd tick) owns one        *)
(* write-ahead prover lease per repository; a detached prover process owns *)
(* the lab runs. Per refresh the controller hands the prover every green,  *)
(* unsuspended runtime PR that has no PASS readback and no recorded FAIL   *)
(* at its current head (the candidates), plus every PR that already holds  *)
(* a PASS readback at its current head and is not merged (the pending      *)
(* prefix: it will land first). The prover proves the candidates as one    *)
(* group ON TOP OF the prefix, appends a PASS readback to each member of a *)
(* passing unit, bisects a failing unit, and grows the prefix with every   *)
(* unit that passed, so a later half is proved on top of an earlier one.   *)
(* The landing node merges a PR only with a readback at its current head.  *)
(*                                                                         *)
(* Truth: Fails(S) says whether dev with the set S of PRs applied breaks.  *)
(* It is monotone: a PR that breaks alone (Bad), or a set that breaks only *)
(* together (Interact).                                                    *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences, TLC

CONSTANTS
    PRs, MaxHead, NONE,  \* NONE: a model value (comparable with records)
    Bad,            \* PRs that break dev on their own
    Interact,       \* sets of PRs that break dev only together
    \* guards, each flipped by exactly one mutation config
    UsePrefix,      \* TRUE: prove each unit on top of the pending and passed prefix
    ReleaseRule,    \* "confirmed": release a lease only with no prover process alive
    FailSuppress,   \* TRUE: never hand a PR@head with a recorded FAIL to a prover
    AppendPassedOnly, \* TRUE: a readback only for members of a unit that PASSED
    \* environment budgets
    BPush, BHold, BClose, BCrash, BPDie, BInc, BNoHost, BExpire,
    Track           \* TRUE: record scenario tags in hist

Heads == 1..MaxHead
Fails(S) == (S \cap Bad # {}) \/ (\E I \in Interact : I \subseteq S)
PRsOf(X) == {x[1] : x \in X}

VARIABLES
    head, st, held,
    readback,     \* <<p, h>>: a PASS readback for p at head h is on p's body
    provenPass,   \* ghost: <<p, h>> that was a member of a lab run which PASSED
    mergedHeads,  \* ghost: <<p, h>> merged
    failRec,      \* <<p, h>>: the controller recorded a FAIL (redispatch suppression)
    lease,        \* NONE or [m |-> candidates with heads, pend |-> pending prefix]
    spawning,     \* the controller wrote the lease and has not started the process yet
    procs,        \* live prover processes (reality, not the controller's belief)
    job,          \* the live prover's in-memory job, or NONE
    result,       \* NONE or the result file the prover wrote: [fail |-> ...]
    badSpawn,     \* ghost: a spawn handed a PR@head with a recorded FAIL
    budget,       \* environment counters
    hist

vars == <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, spawning,
          procs, job, result, badSpawn, budget, hist>>

Merged == {p \in PRs : st[p] = "merged"}
Open == {p \in PRs : st[p] = "open"}
Ready(p) == <<p, head[p]>> \in readback
Pending == {p \in Open : Ready(p)}
Cands == {p \in Open \ held :
            /\ ~Ready(p)
            /\ (FailSuppress => <<p, head[p]>> \notin failRec)}

Tag(t) == IF Track THEN hist' = hist \cup {t} ELSE UNCHANGED hist

Budgets == [push |-> 0, hold |-> 0, close |-> 0, crash |-> 0, pdie |-> 0, inc |-> 0,
            nohost |-> 0, expire |-> 0]

Init ==
    /\ head = [p \in PRs |-> 1]
    /\ st = [p \in PRs |-> "open"]
    /\ held = {}
    /\ readback = {}
    /\ provenPass = {}
    /\ mergedHeads = {}
    /\ failRec = {}
    /\ lease = NONE
    /\ spawning = FALSE
    /\ procs = 0
    /\ job = NONE
    /\ result = NONE
    /\ badSpawn = FALSE
    /\ budget = Budgets
    /\ hist = {}

----------------------------------------------------------------------------
(* Controller (one tick is several atomic steps here; the state file is    *)
(* written ahead of every effect, so a crash loses actions, never records) *)

Spawn ==
    /\ lease = NONE /\ ~spawning
    /\ Cands # {}
    /\ lease' = [m |-> {<<p, head[p]>> : p \in Cands}, pend |-> Pending]
    /\ spawning' = TRUE
    /\ badSpawn' = (badSpawn \/ \E p \in Cands : <<p, head[p]>> \in failRec)
    /\ Tag(IF budget.crash > 0 THEN "respawn_after_crash" ELSE "spawn")
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, procs, job,
                   result, budget>>

StartProc ==
    /\ spawning /\ lease # NONE
    /\ spawning' = FALSE
    /\ procs' = procs + 1
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, job,
                   result, badSpawn, budget, hist>>

ControllerCrash ==
    /\ spawning /\ budget.crash < BCrash
    /\ spawning' = FALSE
    /\ budget' = [budget EXCEPT !.crash = @ + 1]
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, procs,
                   job, result, badSpawn, hist>>

\* Record the result (if any) and release the lease. Under the plan rule only when no
\* process of the prover is alive (probe of its group and tag).
Reap ==
    /\ lease # NONE /\ ~spawning
    /\ IF ReleaseRule = "confirmed" THEN procs = 0 ELSE (procs = 0 \/ result # NONE)
    /\ failRec' = IF result = NONE THEN failRec ELSE failRec \cup result.fail
    /\ lease' = NONE
    /\ result' = NONE
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, spawning, procs, job,
                   badSpawn, budget, hist>>

\* The landing node: merge only a PR whose current head carries a readback.
Land(p) ==
    /\ st[p] = "open" /\ p \notin held /\ Ready(p)
    /\ st' = [st EXCEPT ![p] = "merged"]
    /\ mergedHeads' = mergedHeads \cup {<<p, head[p]>>}
    /\ UNCHANGED <<head, held, readback, provenPass, failRec, lease, spawning, procs, job,
                   result, badSpawn, budget, hist>>

----------------------------------------------------------------------------
(* The prover process                                                      *)

Begin ==
    /\ procs > 0 /\ job = NONE /\ lease # NONE /\ result = NONE
    /\ LET live == {x \in lease.m : head[x[1]] = x[2] /\ st[x[1]] = "open"}
       IN job' = [base |-> Merged,
                  prefix |-> IF UsePrefix THEN lease.pend ELSE {},
                  passed |-> {}, appended |-> {}, failed |-> {},
                  queue |-> IF live = {} THEN <<>> ELSE <<live>>,
                  done |-> FALSE, written |-> FALSE]
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, spawning,
                   procs, result, badSpawn, budget, hist>>

Split(u) == {s \in SUBSET u : s # {} /\ s # u}

RunUnit ==
    /\ procs > 0 /\ job # NONE /\ ~job.done /\ job.queue # <<>>
    /\ LET u == Head(job.queue)
           live == {x \in u : head[x[1]] = x[2] /\ st[x[1]] = "open"}   \* build re-checks heads
           runSet == job.base \cup job.prefix \cup PRsOf(live)
       IN \/ /\ live = {}
             /\ job' = [job EXCEPT !.queue = Tail(@)]
             /\ Tag("head_moved")
             /\ UNCHANGED <<provenPass, budget>>
          \/ /\ live # {} /\ budget.nohost < BNoHost        \* no free host: stop, rest not run
             /\ job' = [job EXCEPT !.done = TRUE]
             /\ budget' = [budget EXCEPT !.nohost = @ + 1]
             /\ UNCHANGED <<provenPass, hist>>
          \/ /\ live # {} /\ budget.inc < BInc              \* INCONCLUSIVE: not run, no bisection
             /\ job' = [job EXCEPT !.queue = Tail(@)]
             /\ budget' = [budget EXCEPT !.inc = @ + 1]
             /\ UNCHANGED <<provenPass, hist>>
          \/ /\ live # {} /\ ~Fails(runSet)                 \* PASS
             /\ job' = [job EXCEPT !.queue = Tail(@), !.passed = @ \cup live,
                                   !.prefix = IF UsePrefix THEN @ \cup PRsOf(live) ELSE @]
             /\ provenPass' = provenPass \cup live
             /\ Tag(IF live # u THEN "head_moved"
                    ELSE IF Cardinality(live) > 1 THEN "group_pass"
                    ELSE IF job.passed # {} THEN "half_pass_after_fail" ELSE "solo_pass")
             /\ UNCHANGED budget
          \/ /\ live # {} /\ Fails(runSet) /\ Cardinality(live) > 1   \* FAIL: bisect
             /\ \E a \in Split(live) :
                   job' = [job EXCEPT !.queue = <<a, live \ a>> \o Tail(@),
                                      !.passed = IF AppendPassedOnly THEN @ ELSE @ \cup live]
             /\ Tag("bisect")
             /\ UNCHANGED <<provenPass, budget>>
          \/ /\ live # {} /\ Fails(runSet) /\ Cardinality(live) = 1   \* FAIL: the breaking PR
             /\ job' = [job EXCEPT !.queue = Tail(@), !.failed = @ \cup live]
             /\ Tag(IF PRsOf(live) \cap Bad = {} THEN "blamed_by_interaction" ELSE "blamed_alone")
             /\ UNCHANGED <<provenPass, budget>>
    /\ UNCHANGED <<head, st, held, readback, mergedHeads, failRec, lease, spawning, procs,
                   result, badSpawn>>

\* PATCH one member's body with the readback (unconditional; the readback names the head).
AppendRB ==
    /\ procs > 0 /\ job # NONE
    /\ \E x \in job.passed \ job.appended :
          /\ readback' = readback \cup {x}
          /\ job' = [job EXCEPT !.appended = @ \cup {x}]
    /\ UNCHANGED <<head, st, held, provenPass, mergedHeads, failRec, lease, spawning, procs,
                   result, badSpawn, budget, hist>>

WriteResult ==
    /\ procs > 0 /\ job # NONE /\ ~job.written
    /\ job.queue = <<>> \/ job.done
    /\ job.appended = job.passed
    /\ result' = [fail |-> job.failed]
    /\ job' = [job EXCEPT !.written = TRUE]
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, spawning,
                   procs, badSpawn, budget, hist>>

Exit ==
    /\ procs > 0 /\ job # NONE /\ job.written
    /\ procs' = procs - 1
    /\ job' = NONE
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, spawning,
                   result, badSpawn, budget, hist>>

\* Crash or deadline kill: the process dies with no result file.
ProverDie ==
    /\ procs > 0 /\ budget.pdie < BPDie
    /\ procs' = procs - 1
    /\ job' = NONE
    /\ budget' = [budget EXCEPT !.pdie = @ + 1]
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, failRec, lease, spawning,
                   result, badSpawn, hist>>

----------------------------------------------------------------------------
(* Environment                                                             *)

Push(p) ==
    /\ st[p] = "open" /\ head[p] < MaxHead /\ budget.push < BPush
    /\ head' = [head EXCEPT ![p] = @ + 1]
    /\ budget' = [budget EXCEPT !.push = @ + 1]
    /\ UNCHANGED <<st, held, readback, provenPass, mergedHeads, failRec, lease, spawning, procs,
                   job, result, badSpawn, hist>>

Hold(p) ==
    /\ st[p] = "open" /\ budget.hold < BHold
    /\ held' = IF p \in held THEN held \ {p} ELSE held \cup {p}
    /\ budget' = [budget EXCEPT !.hold = @ + 1]
    /\ UNCHANGED <<head, st, readback, provenPass, mergedHeads, failRec, lease, spawning, procs,
                   job, result, badSpawn, hist>>

Close(p) ==
    /\ st[p] = "open" /\ budget.close < BClose
    /\ st' = [st EXCEPT ![p] = "closed"]
    /\ budget' = [budget EXCEPT !.close = @ + 1]
    /\ UNCHANGED <<head, held, readback, provenPass, mergedHeads, failRec, lease, spawning, procs,
                   job, result, badSpawn, hist>>

\* A recorded FAIL expires (its TTL), so the PR is proved again at the same head.
Expire ==
    /\ failRec # {} /\ budget.expire < BExpire
    /\ \E x \in failRec : failRec' = failRec \ {x}
    /\ budget' = [budget EXCEPT !.expire = @ + 1]
    /\ UNCHANGED <<head, st, held, readback, provenPass, mergedHeads, lease, spawning, procs,
                   job, result, badSpawn, hist>>

Next ==
    \/ Spawn \/ StartProc \/ ControllerCrash \/ Reap \/ \E p \in PRs : Land(p)
    \/ Begin \/ RunUnit \/ AppendRB \/ WriteResult \/ Exit \/ ProverDie
    \/ \E p \in PRs : Push(p) \/ Hold(p) \/ Close(p)
    \/ Expire

Spec == Init /\ [][Next]_vars

Fair ==
    /\ WF_vars(Spawn) /\ WF_vars(StartProc) /\ WF_vars(Reap)
    /\ WF_vars(Begin) /\ WF_vars(RunUnit) /\ WF_vars(AppendRB)
    /\ WF_vars(WriteResult) /\ WF_vars(Exit)
    /\ \A p \in PRs : WF_vars(Land(p))

LiveSpec == Spec /\ Fair

----------------------------------------------------------------------------
(* Properties                                                              *)

TypeOK ==
    /\ head \in [PRs -> Heads]
    /\ st \in [PRs -> {"open", "merged", "closed"}]
    /\ held \subseteq PRs
    /\ readback \subseteq PRs \X Heads
    /\ failRec \subseteq PRs \X Heads
    /\ procs \in 0..2
    /\ spawning \in BOOLEAN

\* LP1: never two prover processes for one repository.
OneProver == procs <= 1

\* LP1': a live prover always has its lease on record (a lease is the only way to start one).
ProverLeased == procs > 0 => lease # NONE

\* LP2: a readback names only a PR@head that was a member of a passing run.
NoUnprovenReadback == readback \subseteq provenPass

\* LP3: the node merges only a PR@head a passing run proved.
NoUnprovenLand == mergedHeads \subseteq provenPass

\* LP4: what has landed plus everything that may land next (a readback at the current head)
\* never breaks dev. This is what the prefix buys: halves are proved on top of each other
\* and on top of every pending readback.
NoLatentBreak == ~Fails(Merged \cup Pending)

\* LP5: no PR@head with a recorded FAIL is handed to a prover (suppression).
NoFailReprove == ~badSpawn

\* LP6: a recorded FAIL blames only a PR that breaks alone or is part of a breaking set.
NoFalseBlame == \A x \in failRec : x[1] \in Bad \/ \E I \in Interact : x[1] \in I

Safety == TypeOK /\ OneProver /\ ProverLeased /\ NoUnprovenReadback /\ NoUnprovenLand
          /\ NoLatentBreak /\ NoFailReprove /\ NoFalseBlame

\* LL1: every open, unheld PR with a stable head ends with a readback at that head, a merge,
\* or a recorded FAIL at that head.
Progress ==
    \A p \in PRs :
        <>[](st[p] # "open" \/ p \in held \/ Ready(p) \/ <<p, head[p]>> \in failRec)

\* Scenario reachability: each NotS is violated by the shortest trace reaching it.
NotGroupPass == "group_pass" \notin hist
NotBisect == "bisect" \notin hist
NotHalfPassAfterFail == "half_pass_after_fail" \notin hist
NotBlamedByInteraction == "blamed_by_interaction" \notin hist
NotRespawnAfterCrash == "respawn_after_crash" \notin hist
NotHeadMoved == "head_moved" \notin hist

=============================================================================
