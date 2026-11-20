---------------------------- MODULE HostDriftFence ----------------------------
(***************************************************************************)
(* The per-host mutation fence (OMN-20847, sync-mechanisms plan T2).        *)
(*                                                                          *)
(* One host, its dispatch venvs and the lanes admitted onto them. Three     *)
(* actors touch a venv:                                                     *)
(*   - the fix node's update-venv: take the fence, take fix.lock, read the  *)
(*     live lanes, start the mutating child (the reconcile, under its       *)
(*     root's reconcile lock), wait for it, release;                        *)
(*   - the remote-lane runner: take the fence, place the lane on a venv,    *)
(*     release once the lane is live;                                       *)
(*   - the second scheduled writer (the h907 root cron): a reconcile under  *)
(*     the same root lock that takes no fence and reads no lanes.           *)
(* Any holder may crash: the fix node (its child is orphaned and runs on),  *)
(* the child (its mutation is lost, the venv stays stale) and the admitting *)
(* runner. An flock is released when its last descriptor closes, so a dead  *)
(* holder's share of the fence is gone at once; the child keeps the fence   *)
(* only when the fix node passed it the descriptor (ChildHoldsFence).       *)
(*                                                                          *)
(* The fix node's read of the live lanes and its start of the child are two *)
(* steps, as in the handler, so a lane placed between them is a real race.  *)
(*                                                                          *)
(* OMN-20670: the reconcile stages a copy of the venv and exchanges it with *)
(* the live one in one syscall (StagedSwap), so a running lane never sees a *)
(* venv being written, and update-venv no longer reads the live lanes       *)
(* (LaneRead). A busy lab host admits a new lane as one ends (LanesRecur),  *)
(* so with LaneRead the fix node can find a lane running on every attempt   *)
(* and the venv is never repaired.                                          *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS
    Venvs,            \* the host's dispatch venvs, each under its own root
    Lanes,            \* lanes that may be admitted onto the host
    MaxCrashes,       \* bound on crashes of any holder (finite environment)
    FenceEnabled,     \* the fix node and the runner take the fence
    ChildHoldsFence,  \* the fix node passes the fence descriptor to its child
    SecondWriter,     \* the root cron still reconciles venvs on its own
    LaneRead,         \* the fix node defers a venv repair while any lane runs
    StagedSwap,       \* the child writes a staged copy and exchanges it in one step
    LanesRecur        \* a lane that ends may be followed by another admission

ASSUME FenceEnabled \in BOOLEAN /\ ChildHoldsFence \in BOOLEAN
ASSUME SecondWriter \in BOOLEAN /\ MaxCrashes \in Nat
ASSUME LaneRead \in BOOLEAN /\ StagedSwap \in BOOLEAN /\ LanesRecur \in BOOLEAN
ASSUME Venvs \cap Lanes = {} /\ "fix" \notin Venvs \cup Lanes

NoVenv == "none"
\* Fence holders: the fix node, a mutating child (named by its venv), an admitting lane.
Holders == {"fix"} \cup Venvs \cup Lanes

VARIABLES
    fence,      \* the processes holding the fence
    fixPc,      \* idle | fenced | checked | waiting
    target,     \* the venv the fix node is repairing, or NoVenv
    children,   \* venvs a mutating child is reconciling (orphans included)
    cron,       \* the venv the second writer is reconciling, or NoVenv
    rootLock,   \* each venv's root reconcile lock: none | child | cron
    stale,      \* each venv behind its target
    lanePc,     \* each lane: out | admitting | running | done
    laneVenv,   \* the venv a running lane uses, or NoVenv
    crashes

vars == <<fence, fixPc, target, children, cron, rootLock, stale, lanePc, laneVenv, crashes>>

Running == {l \in Lanes : lanePc[l] = "running"}
\* The live venv is written in place: by a child that does not stage, or by the second writer.
\* A staging child writes a sibling no lane uses; its successful exit is the one exchange.
Mutating(v) == (v \in children /\ ~StagedSwap) \/ cron = v
Free == fence = {}
Take(p) == IF FenceEnabled THEN fence \cup {p} ELSE fence

Init ==
    /\ fence = {}
    /\ fixPc = "idle"
    /\ target = NoVenv
    /\ children = {}
    /\ cron = NoVenv
    /\ rootLock = [v \in Venvs |-> "none"]
    /\ stale = [v \in Venvs |-> TRUE]
    /\ lanePc = [l \in Lanes |-> "out"]
    /\ laneVenv = [l \in Lanes |-> NoVenv]
    /\ crashes = 0

(* ---- the fix node -------------------------------------------------------- *)

\* Take the fence (fix.lock follows it in the same step: one fix node per host).
FixTakeFence(v) ==
    /\ fixPc = "idle" /\ stale[v]
    /\ FenceEnabled => Free
    /\ fence' = Take("fix")
    /\ fixPc' = "fenced" /\ target' = v
    /\ UNCHANGED <<children, cron, rootLock, stale, lanePc, laneVenv, crashes>>

Release(f) == f \ {"fix"}

\* A live lane (when the fix node reads them), or another reconcile of the root: DEFERRED,
\* release everything.
FixDefer ==
    /\ fixPc = "fenced"
    /\ (LaneRead /\ Running # {}) \/ rootLock[target] # "none"
    /\ fence' = Release(fence) /\ fixPc' = "idle" /\ target' = NoVenv
    /\ UNCHANGED <<children, cron, rootLock, stale, lanePc, laneVenv, crashes>>

\* The live-lane read finds no lane (between lanes), or the fix node reads none.
FixCheck ==
    /\ fixPc = "fenced" /\ (LaneRead => Running = {})
    /\ fixPc' = "checked"
    /\ UNCHANGED <<fence, target, children, cron, rootLock, stale, lanePc, laneVenv, crashes>>

\* Start the child; it runs under the root lock, or exits 4 (DEFERRED) when that is held.
FixStart ==
    /\ fixPc = "checked"
    /\ IF rootLock[target] = "none"
         THEN /\ children' = children \cup {target}
              /\ rootLock' = [rootLock EXCEPT ![target] = "child"]
              /\ fence' = IF FenceEnabled /\ ChildHoldsFence THEN fence \cup {target} ELSE fence
              /\ fixPc' = "waiting" /\ UNCHANGED target
         ELSE /\ fence' = Release(fence) /\ fixPc' = "idle" /\ target' = NoVenv
              /\ UNCHANGED <<children, rootLock>>
    /\ UNCHANGED <<cron, stale, lanePc, laneVenv, crashes>>

\* The child exits (repaired, or crashed with nothing moved); a fix node waiting on it returns.
ChildExit(v, repaired) ==
    /\ v \in children
    /\ ~repaired => crashes < MaxCrashes
    /\ children' = children \ {v}
    /\ rootLock' = [rootLock EXCEPT ![v] = "none"]
    /\ stale' = IF repaired THEN [stale EXCEPT ![v] = FALSE] ELSE stale
    /\ IF fixPc = "waiting" /\ target = v
         THEN /\ fence' = Release(fence \ {v}) /\ fixPc' = "idle" /\ target' = NoVenv
         ELSE /\ fence' = fence \ {v} /\ UNCHANGED <<fixPc, target>>
    /\ crashes' = IF repaired THEN crashes ELSE crashes + 1
    /\ UNCHANGED <<cron, lanePc, laneVenv>>

\* The fix node dies: its descriptors close; a child it started runs on.
FixCrash ==
    /\ fixPc # "idle" /\ crashes < MaxCrashes
    /\ fence' = Release(fence) /\ fixPc' = "idle" /\ target' = NoVenv
    /\ crashes' = crashes + 1
    /\ UNCHANGED <<children, cron, rootLock, stale, lanePc, laneVenv>>

(* ---- the remote-lane runner --------------------------------------------- *)

Admit(l) ==
    /\ lanePc[l] = "out"
    /\ FenceEnabled => Free
    /\ fence' = Take(l) /\ lanePc' = [lanePc EXCEPT ![l] = "admitting"]
    /\ UNCHANGED <<fixPc, target, children, cron, rootLock, stale, laneVenv, crashes>>

\* The lane is launched on a venv and is live (the fix node's probe sees it) before the
\* runner releases the fence.
Place(l, v) ==
    /\ lanePc[l] = "admitting"
    /\ lanePc' = [lanePc EXCEPT ![l] = "running"]
    /\ laneVenv' = [laneVenv EXCEPT ![l] = v]
    /\ fence' = fence \ {l}
    /\ UNCHANGED <<fixPc, target, children, cron, rootLock, stale, crashes>>

AdmitCrash(l) ==
    /\ lanePc[l] = "admitting" /\ crashes < MaxCrashes
    /\ lanePc' = [lanePc EXCEPT ![l] = "out"] /\ fence' = fence \ {l}
    /\ crashes' = crashes + 1
    /\ UNCHANGED <<fixPc, target, children, cron, rootLock, stale, laneVenv>>

\* With LanesRecur the slot is free again and the runner may admit the next lane into it.
LaneEnds(l) ==
    /\ lanePc[l] = "running"
    /\ lanePc' = [lanePc EXCEPT ![l] = IF LanesRecur THEN "out" ELSE "done"]
    /\ laneVenv' = IF LanesRecur THEN [laneVenv EXCEPT ![l] = NoVenv] ELSE laneVenv
    /\ UNCHANGED <<fence, fixPc, target, children, cron, rootLock, stale, crashes>>

(* ---- the second writer (removed in the main configuration) -------------- *)

CronStart(v) ==
    /\ SecondWriter /\ cron = NoVenv /\ rootLock[v] = "none"
    /\ cron' = v /\ rootLock' = [rootLock EXCEPT ![v] = "cron"]
    /\ UNCHANGED <<fence, fixPc, target, children, stale, lanePc, laneVenv, crashes>>

CronEnds ==
    /\ cron # NoVenv
    /\ stale' = [stale EXCEPT ![cron] = FALSE]
    /\ rootLock' = [rootLock EXCEPT ![cron] = "none"] /\ cron' = NoVenv
    /\ UNCHANGED <<fence, fixPc, target, children, lanePc, laneVenv, crashes>>

Next ==
    \/ \E v \in Venvs : FixTakeFence(v)
    \/ FixDefer \/ FixCheck \/ FixStart \/ FixCrash
    \/ \E v \in Venvs, r \in BOOLEAN : ChildExit(v, r)
    \/ \E l \in Lanes : Admit(l) \/ AdmitCrash(l) \/ LaneEnds(l)
    \/ \E l \in Lanes, v \in Venvs : Place(l, v)
    \/ \E v \in Venvs : CronStart(v)
    \/ CronEnds

\* Admission and crashes have no fairness: the environment may never admit, and need not crash.
\* Taking the fence is strongly fair: the fix node retries on a timer and an admission holds the
\* fence only while it places a lane, so a fence that is free again and again is taken.
Fairness ==
    /\ SF_vars(\E v \in Venvs : FixTakeFence(v))
    /\ WF_vars(FixDefer) /\ WF_vars(FixCheck) /\ WF_vars(FixStart)
    /\ \A v \in Venvs : WF_vars(ChildExit(v, TRUE))
    /\ \A l \in Lanes : WF_vars(\E v \in Venvs : Place(l, v)) /\ WF_vars(LaneEnds(l))
    /\ WF_vars(CronEnds)

Spec == Init /\ [][Next]_vars /\ Fairness

(* ---- properties ---------------------------------------------------------- *)

TypeOK ==
    /\ fence \subseteq Holders
    /\ fixPc \in {"idle", "fenced", "checked", "waiting"}
    /\ target \in Venvs \cup {NoVenv}
    /\ children \subseteq Venvs
    /\ cron \in Venvs \cup {NoVenv}
    /\ rootLock \in [Venvs -> {"none", "child", "cron"}]
    /\ stale \in [Venvs -> BOOLEAN]
    /\ lanePc \in [Lanes -> {"out", "admitting", "running", "done"}]
    /\ laneVenv \in [Lanes -> Venvs \cup {NoVenv}]
    /\ crashes \in 0..MaxCrashes

\* No lane runs on a venv while it is written in place: a lane is never placed on a venv being
\* repaired, and no in-place repair starts while an admitted lane holds a venv (AC2).
NoLaneOnMutatingVenv == \A l \in Running : ~Mutating(laneVenv[l])

\* No two mutations of the host's venvs overlap.
OneMutation == Cardinality(children) + (IF cron = NoVenv THEN 0 ELSE 1) <= 1

\* Every stale venv is repaired (crashes are bounded), also while lanes keep running.
EveryVenvRepaired == \A v \in Venvs : stale[v] ~> ~stale[v]
=============================================================================
