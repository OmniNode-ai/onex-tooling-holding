--------------------------- MODULE LabStackReaper ---------------------------
(***************************************************************************)
(* The lab stack reaper (OMN-20864, plan unit M47; ruling                  *)
(* 2026-10-12T04:59:58Z: the system removes leftover lab stacks of closed  *)
(* lanes itself).                                                          *)
(*                                                                         *)
(* Lanes CLAIM on the ledger of record, bring a compose stack up or reuse  *)
(* one, stop using it, and end with a TERMINAL. A remote lane's TERMINAL   *)
(* may wait in its relay outbox and reach the ledger after a newer CLAIM   *)
(* of the same lane, and its stamp comes from another host's clock, which  *)
(* may run ahead (Skew). A timer starts one reaper pass per interval; a    *)
(* pass still running at the next start is killed (PassOverrun). The pass  *)
(* reads a view of the ledger (a prefix of the ledger of record) and       *)
(* examines every stack that was up when it started. `docker compose      *)
(* down` runs on the docker daemon: it may fail, and it keeps running when *)
(* the pass that started it is killed.                                     *)
(*                                                                         *)
(* Adopted design (cfg/adopted.cfg):                                       *)
(*   - every lane that brings a stack up or reuses it writes a lease: its  *)
(*     lane name and the stamp of its current CLAIM;                       *)
(*   - every TERMINAL names the CLAIM it closes; a lease is closed when    *)
(*     the view holds the TERMINAL that names its CLAIM;                   *)
(*   - the pass decides under the stack's lock, and before it runs         *)
(*     `compose down` it fences the stack, so no lane reuses it until the  *)
(*     removal is seen to end, even when the pass is killed;               *)
(*   - a pass waits for a removal still running from a killed pass;        *)
(*   - a failed removal is retried within the pass, and alarmed when the   *)
(*     retries are spent; a killed pass alarms every stack that is up;     *)
(*   - the pass reads a view that is current when it starts.               *)
(*                                                                         *)
(* Properties:                                                             *)
(*   NeverRemoveLive          no removal while a use of the stack has no   *)
(*                            TERMINAL closing its CLAIM on the ledger of  *)
(*                            record (a live CLAIM);                       *)
(*   NoUserLosesStack         no lane loses a stack it is using;           *)
(*   RemovedWithinOneInterval a stack TERMINAL-closed in interval t is     *)
(*                            gone before interval t + 2 starts, when no   *)
(*                            pass overruns and failures stay below the    *)
(*                            retries (no alarm excuses it);               *)
(*   OverdueIsAlarmed         under any faults, an overdue closed stack is *)
(*                            alarmed in its current closure;              *)
(*   EveryClosedStackRemoved  (temporal, fairness) every closed stack is   *)
(*                            removed or reused, under bounded faults;     *)
(*   NoRemovalEver, NoLateRemoval, NoRetrySucceeded                        *)
(*                            witnesses, expected VIOLATED.                *)
(*                                                                         *)
(* Time counts timer periods. Lanes act only while now < MaxTime -        *)
(* Interval, so every closure reaches its first overdue tick and its last  *)
(* pass inside the explored horizon.                                       *)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    Lanes,           \* lane names (model values)
    Stacks,          \* compose project names (model values)
    NoStack,         \* a model value outside Stacks
    MaxClaims,       \* CLAIMs per lane; 2 lets a lane reopen
    MaxTime,         \* the last interval explored
    Interval,        \* the deadline, in timer periods (1)
    MaxDownFailures, \* failed `compose down` runs allowed in a behaviour
    Retries,         \* `compose down` attempts per stack per pass
    RelayDelay,      \* TRUE: a TERMINAL waits in the lane's relay outbox
    Skew,            \* how far a TERMINAL's stamp may run ahead
    PassOverrun,     \* TRUE: the timer may kill a pass that is still running
    QuiesceFirst,    \* TRUE: a lane stops using its stacks before its TERMINAL
    \* design switches; the adopted values are in cfg/adopted.cfg
    UseLock,         \* TRUE: decide on the current leases under the lock
    LeaseAdopters,   \* TRUE: a lane reusing a stack adds its lease
    Closure,         \* "names_claim" | "stamp_ts" | "stamp_position" | "last_row"
    Owners,          \* "lease" | "ticket"
    ViewLag,         \* 0: the pass reads a current view; 1: a copy one interval old
    Fence,           \* TRUE: a stack being removed is fenced against reuse
    WaitInFlight,    \* TRUE: a pass waits for a removal still running
    AlarmOnFailure,  \* TRUE: spent retries raise an alarm
    AlarmOnAbort     \* TRUE: a killed pass alarms every stack that is up

NONE == -1

VARIABLES
    ledger,       \* the ledger of record: <<[kind, lane, ts, closes]>>
    outbox,       \* per lane: TERMINAL rows written but not yet relayed
    tsNext,       \* real write order; CLAIM stamps take it
    laneSt,       \* "idle" | "live" | "ended"
    claims,       \* CLAIMs written per lane
    claimTs,      \* the stamp of the lane's newest CLAIM
    up,           \* the stack exists on the docker daemon
    lease,        \* the stack's leases: {[lane, stamp]}
    fence,        \* the stack is fenced against reuse
    downInFlight, \* a `compose down` of the stack is running on the daemon
    lockHeld,     \* the reaper holds the stack's lock
    users,        \* lanes using the stack now (ghost)
    usedBy,       \* every [lane, stamp] that used the stack since it came up (ghost)
    now,          \* the current interval
    pc,           \* the reaper: "start" | "scan" | "idle"
    view,         \* the length of the ledger prefix the pass reads
    todo,         \* stacks the pass has still to examine
    current,      \* the stack whose removal the pass is running, or NoStack
    attempts,     \* failed attempts per stack in this pass
    snapLease,    \* leases as read at pass start (used only without the lock)
    copyLen,      \* the ledger length of a copy one interval old
    lastTickLen,  \* the ledger length at the newest tick
    downFails,    \* failed removals so far
    alarm,        \* per stack: alarmed in its current closure
    closedAt,     \* per stack: the interval its users all closed, or NONE (ghost)
    liveRemoved,  \* a stack was removed under a live CLAIM (ghost)
    removed,      \* a stack has been removed (ghost witness)
    removedLate,  \* a stack closed in an earlier interval was removed (ghost witness)
    retried       \* a removal succeeded after a failed attempt (ghost witness)

laneVars   == <<ledger, outbox, tsNext, laneSt, claims, claimTs>>
stackVars  == <<up, lease, fence, downInFlight, lockHeld, users, usedBy>>
reaperVars == <<now, pc, view, todo, current, attempts, snapLease, copyLen,
                lastTickLen, downFails>>
ghostVars  == <<alarm, closedAt, liveRemoved, removed, removedLate, retried>>
vars == <<laneVars, stackVars, reaperVars, ghostVars>>

Row(k, l, t, c) == [kind |-> k, lane |-> l, ts |-> t, closes |-> c]
Lease(l) == [lane |-> l, stamp |-> claimTs[l]]
Max(S) == CHOOSE m \in S : \A n \in S : n <= m

(***************************************************************************)
(* Truth, on the ledger of record.                                         *)
(***************************************************************************)
\* The TERMINAL that ends the use r (lane r.lane, CLAIM stamp r.stamp).
ClosedInRecord(led, r) ==
    \E i \in 1..Len(led) :
        led[i].kind = "TERMINAL" /\ led[i].lane = r.lane /\ led[i].closes = r.stamp

\* The stack is up, nobody uses it, and every use is TERMINAL-closed.
ClosedTruth(s, up2, users2, used2, led2) ==
    /\ up2[s]
    /\ users2[s] = {}
    /\ \A r \in used2[s] : ClosedInRecord(led2, r)

NextClosedAt(up2, users2, used2, led2) ==
    [s \in Stacks |->
        IF ClosedTruth(s, up2, users2, used2, led2)
        THEN IF closedAt[s] = NONE THEN now ELSE closedAt[s]
        ELSE NONE]

\* An alarm belongs to one closure: a stack entering a closure starts unalarmed.
NextAlarm(closedAt2) ==
    [s \in Stacks |-> IF closedAt[s] = NONE /\ closedAt2[s] # NONE THEN FALSE ELSE alarm[s]]

(***************************************************************************)
(* What the reaper reads: the view, ledger[1..v].                          *)
(***************************************************************************)
LaneSeen(l, v) == \E i \in 1..v : ledger[i].lane = l

\* adopted: the TERMINAL that names the lease's CLAIM.
ClosedByName(r, v) ==
    \E i \in 1..v :
        ledger[i].kind = "TERMINAL" /\ ledger[i].lane = r.lane /\ ledger[i].closes = r.stamp

\* mutation: a TERMINAL of that lane stamped later than the lease's CLAIM.
ClosedByStamp(r, v) ==
    \E i \in 1..v :
        ledger[i].kind = "TERMINAL" /\ ledger[i].lane = r.lane /\ ledger[i].ts > r.stamp

\* mutation: a TERMINAL of that lane placed after the lease's CLAIM row.
ClosedByPosition(r, v) ==
    \E i \in 1..v : \E j \in 1..(i - 1) :
        /\ ledger[i].kind = "TERMINAL" /\ ledger[i].lane = r.lane
        /\ ledger[j].kind = "CLAIM" /\ ledger[j].lane = r.lane /\ ledger[j].ts = r.stamp

\* mutation (the operator-run stack-down's rule): the lane's last row in
\* the view is a TERMINAL.
LastRowClosed(l, v) ==
    LET idx == {i \in 1..v : ledger[i].lane = l}
    IN idx # {} /\ ledger[Max(idx)].kind = "TERMINAL"

LeaseClosed(r, v) ==
    CASE Closure = "names_claim"    -> ClosedByName(r, v)
      [] Closure = "stamp_ts"       -> ClosedByStamp(r, v)
      [] Closure = "stamp_position" -> ClosedByPosition(r, v)
      [] Closure = "last_row"       -> LastRowClosed(r.lane, v)

\* Owners = "ticket": every lane of the stack's ticket that the view shows
\* (all lanes and stacks here carry one carrier ticket).
Removable(L, v) ==
    IF Owners = "ticket"
    THEN LET ls == {l \in Lanes : LaneSeen(l, v)}
         IN ls # {} /\ \A l \in ls : LastRowClosed(l, v)
    ELSE L # {} /\ \A r \in L : LeaseClosed(r, v)

\* A lane may take the stack: the reaper holds no lock on it and, with the
\* fence, no removal of it is outstanding.
Takeable(s) == ~lockHeld[s] /\ (Fence => ~fence[s])

(***************************************************************************)
(* Initial state.                                                          *)
(***************************************************************************)
Init ==
    /\ ledger = << >>
    /\ outbox = [l \in Lanes |-> << >>]
    /\ tsNext = 1
    /\ laneSt = [l \in Lanes |-> "idle"]
    /\ claims = [l \in Lanes |-> 0]
    /\ claimTs = [l \in Lanes |-> 0]
    /\ up = [s \in Stacks |-> FALSE]
    /\ lease = [s \in Stacks |-> {}]
    /\ fence = [s \in Stacks |-> FALSE]
    /\ downInFlight = [s \in Stacks |-> FALSE]
    /\ lockHeld = [s \in Stacks |-> FALSE]
    /\ users = [s \in Stacks |-> {}]
    /\ usedBy = [s \in Stacks |-> {}]
    /\ now = 0
    /\ pc = "start"
    /\ view = 0
    /\ todo = {}
    /\ current = NoStack
    /\ attempts = [s \in Stacks |-> 0]
    /\ snapLease = [s \in Stacks |-> {}]
    /\ copyLen = 0
    /\ lastTickLen = 0
    /\ downFails = 0
    /\ alarm = [s \in Stacks |-> FALSE]
    /\ closedAt = [s \in Stacks |-> NONE]
    /\ liveRemoved = FALSE
    /\ removed = FALSE
    /\ removedLate = FALSE
    /\ retried = FALSE

(***************************************************************************)
(* Lanes. They act only while a closure they cause still falls due inside *)
(* the horizon. Up and Adopt take the stack's lock, so each is one step.   *)
(***************************************************************************)
LanesOpen == now < MaxTime - Interval

Claim(l) ==
    /\ LanesOpen
    /\ laneSt[l] # "live"
    /\ claims[l] < MaxClaims
    /\ ledger' = Append(ledger, Row("CLAIM", l, tsNext, 0))
    /\ claimTs' = [claimTs EXCEPT ![l] = tsNext]
    /\ tsNext' = tsNext + 1
    /\ laneSt' = [laneSt EXCEPT ![l] = "live"]
    /\ claims' = [claims EXCEPT ![l] = @ + 1]
    /\ UNCHANGED <<outbox, stackVars, reaperVars, ghostVars>>

Up(l, s) ==
    /\ LanesOpen
    /\ laneSt[l] = "live"
    /\ ~up[s]
    /\ Takeable(s)
    /\ up' = [up EXCEPT ![s] = TRUE]
    /\ lease' = [lease EXCEPT ![s] = {Lease(l)}]
    /\ users' = [users EXCEPT ![s] = {l}]
    /\ usedBy' = [usedBy EXCEPT ![s] = {Lease(l)}]
    /\ alarm' = [alarm EXCEPT ![s] = FALSE]
    /\ closedAt' = NextClosedAt(up', users', usedBy', ledger)
    /\ UNCHANGED <<laneVars, fence, downInFlight, lockHeld, reaperVars,
                   liveRemoved, removed, removedLate, retried>>

Adopt(l, s) ==
    /\ LanesOpen
    /\ laneSt[l] = "live"
    /\ up[s]
    /\ Takeable(s)
    /\ l \notin users[s]
    /\ users' = [users EXCEPT ![s] = @ \cup {l}]
    /\ usedBy' = [usedBy EXCEPT ![s] = @ \cup {Lease(l)}]
    /\ lease' = IF LeaseAdopters
                THEN [lease EXCEPT ![s] = @ \cup {Lease(l)}]
                ELSE lease
    /\ alarm' = [alarm EXCEPT ![s] = FALSE]
    /\ closedAt' = NextClosedAt(up, users', usedBy', ledger)
    /\ UNCHANGED <<laneVars, up, fence, downInFlight, lockHeld, reaperVars,
                   liveRemoved, removed, removedLate, retried>>

\* Only the stamp_ts rule reads a TERMINAL's stamp, so the skew is explored
\* only there; for every other rule it would add states and no behaviour.
Skews == IF Closure = "stamp_ts" THEN 0..Skew ELSE {0}

\* The lane writes its TERMINAL, naming the CLAIM it closes; its stamp may
\* run ahead by up to Skew. With QuiesceFirst it has stopped using its stacks.
Terminal(l) ==
    /\ LanesOpen
    /\ laneSt[l] = "live"
    /\ \E skew \in Skews :
        LET row == Row("TERMINAL", l, tsNext + skew, claimTs[l])
        IN IF RelayDelay
           THEN /\ outbox' = [outbox EXCEPT ![l] = Append(@, row)]
                /\ ledger' = ledger
           ELSE /\ ledger' = Append(ledger, row)
                /\ outbox' = outbox
    /\ laneSt' = [laneSt EXCEPT ![l] = "ended"]
    /\ users' = IF QuiesceFirst THEN [s \in Stacks |-> users[s] \ {l}] ELSE users
    /\ tsNext' = tsNext + 1
    /\ closedAt' = NextClosedAt(up, users', usedBy, ledger')
    /\ alarm' = NextAlarm(closedAt')
    /\ UNCHANGED <<claims, claimTs, up, lease, fence, downInFlight, lockHeld,
                   usedBy, reaperVars, liveRemoved, removed, removedLate, retried>>

\* Without QuiesceFirst: work the lane started goes on after its TERMINAL.
Quiesce(l, s) ==
    /\ LanesOpen
    /\ laneSt[l] # "live"
    /\ l \in users[s]
    /\ users' = [users EXCEPT ![s] = @ \ {l}]
    /\ closedAt' = NextClosedAt(up, users', usedBy, ledger)
    /\ alarm' = NextAlarm(closedAt')
    /\ UNCHANGED <<laneVars, up, lease, fence, downInFlight, lockHeld, usedBy,
                   reaperVars, liveRemoved, removed, removedLate, retried>>

\* The launching host appends a queued row as it was written.
Relay(l) ==
    /\ LanesOpen
    /\ outbox[l] # << >>
    /\ ledger' = Append(ledger, Head(outbox[l]))
    /\ outbox' = [outbox EXCEPT ![l] = Tail(@)]
    /\ closedAt' = NextClosedAt(up, users, usedBy, ledger')
    /\ alarm' = NextAlarm(closedAt')
    /\ UNCHANGED <<tsNext, laneSt, claims, claimTs, stackVars, reaperVars,
                   liveRemoved, removed, removedLate, retried>>

(***************************************************************************)
(* The reaper: one pass per interval.                                      *)
(***************************************************************************)
ReadView ==
    /\ pc = "start"
    /\ todo' = {s \in Stacks : up[s]}
    \* view and snapLease are read only when deciding, and snapLease only
    \* without the lock; holding them constant otherwise keeps the state small.
    /\ view' = IF todo' = {} THEN 0
               ELSE IF ViewLag = 0 THEN Len(ledger) ELSE copyLen
    /\ snapLease' = IF UseLock THEN snapLease ELSE lease
    /\ attempts' = [s \in Stacks |-> 0]
    /\ pc' = "scan"
    /\ UNCHANGED <<laneVars, stackVars, now, current, copyLen, lastTickLen,
                   downFails, ghostVars>>

\* A stack whose removal from a killed pass is still running is skipped
\* only without WaitInFlight; with it, the pass waits for that removal.
SkipInFlight(s) ==
    /\ pc = "scan"
    /\ current = NoStack
    /\ s \in todo
    /\ downInFlight[s]
    /\ ~WaitInFlight
    /\ todo' = todo \ {s}
    /\ UNCHANGED <<laneVars, stackVars, now, pc, view, current, attempts, snapLease,
                   copyLen, lastTickLen, downFails, ghostVars>>

\* Judge the stack's leases; when they are all closed, take the lock,
\* fence the stack and start `compose down` on the daemon.
Decide(s) ==
    /\ pc = "scan"
    /\ current = NoStack
    /\ s \in todo
    /\ ~downInFlight[s]
    /\ LET L == IF UseLock THEN lease[s] ELSE snapLease[s]
       IN IF up[s] /\ Removable(L, view)
          THEN /\ current' = s
               /\ downInFlight' = [downInFlight EXCEPT ![s] = TRUE]
               /\ lockHeld' = IF UseLock THEN [lockHeld EXCEPT ![s] = TRUE] ELSE lockHeld
               /\ fence' = IF Fence THEN [fence EXCEPT ![s] = TRUE] ELSE fence
               /\ UNCHANGED todo
          ELSE /\ todo' = todo \ {s}
               /\ UNCHANGED <<current, downInFlight, lockHeld, fence>>
    /\ UNCHANGED <<laneVars, up, lease, users, usedBy, now, pc, view, attempts,
                   snapLease, copyLen, lastTickLen, downFails, ghostVars>>

\* `compose down` finishes on the daemon, whether or not its pass lives.
DownOk(s) ==
    /\ downInFlight[s]
    /\ up' = [up EXCEPT ![s] = FALSE]
    /\ lease' = [lease EXCEPT ![s] = {}]
    /\ usedBy' = [usedBy EXCEPT ![s] = {}]
    /\ fence' = [fence EXCEPT ![s] = FALSE]
    /\ downInFlight' = [downInFlight EXCEPT ![s] = FALSE]
    /\ lockHeld' = [lockHeld EXCEPT ![s] = FALSE]
    /\ alarm' = [alarm EXCEPT ![s] = FALSE]
    /\ liveRemoved' = (liveRemoved \/ \E r \in usedBy[s] : ~ClosedInRecord(ledger, r))
    /\ removed' = TRUE
    /\ removedLate' = (removedLate \/ (closedAt[s] # NONE /\ closedAt[s] < now))
    /\ retried' = (retried \/ (current = s /\ attempts[s] > 0))
    /\ IF current = s
       THEN /\ current' = NoStack
            /\ todo' = todo \ {s}
       ELSE UNCHANGED <<current, todo>>
    /\ closedAt' = NextClosedAt(up', users, usedBy', ledger)
    /\ UNCHANGED <<laneVars, users, now, pc, view, attempts, snapLease, copyLen,
                   lastTickLen, downFails>>

\* `compose down` fails. A live pass sees it, lifts the fence and retries
\* while it has attempts left, else alarms. A failure nobody sees leaves the
\* fence for the next pass to resolve.
DownFail(s) ==
    /\ downInFlight[s]
    /\ downFails < MaxDownFailures
    /\ downFails' = downFails + 1
    /\ downInFlight' = [downInFlight EXCEPT ![s] = FALSE]
    /\ lockHeld' = [lockHeld EXCEPT ![s] = FALSE]
    /\ IF current = s
       THEN /\ current' = NoStack
            /\ fence' = [fence EXCEPT ![s] = FALSE]
            /\ attempts' = [attempts EXCEPT ![s] = @ + 1]
            /\ IF attempts[s] + 1 < Retries
               THEN /\ UNCHANGED <<todo, alarm>>
               ELSE /\ todo' = todo \ {s}
                    /\ alarm' = IF AlarmOnFailure THEN [alarm EXCEPT ![s] = TRUE] ELSE alarm
       ELSE UNCHANGED <<current, fence, attempts, todo, alarm>>
    /\ UNCHANGED <<laneVars, up, lease, users, usedBy, now, pc, view, snapLease,
                   copyLen, lastTickLen, closedAt, liveRemoved, removed, removedLate, retried>>

PassDone ==
    /\ pc = "scan"
    /\ todo = {}
    /\ current = NoStack
    /\ pc' = "idle"
    /\ UNCHANGED <<laneVars, stackVars, now, view, todo, current, attempts, snapLease,
                   copyLen, lastTickLen, downFails, ghostVars>>

\* The timer fires. A pass still running is killed (only with PassOverrun):
\* its locks die with it, a `compose down` it started keeps running, and it
\* alarms every stack that is up. The lab-host copy trails by one interval.
Tick ==
    /\ now < MaxTime
    /\ pc = "idle" \/ PassOverrun
    /\ now' = now + 1
    /\ pc' = "start"
    /\ IF pc # "idle"
       THEN /\ lockHeld' = [s \in Stacks |-> FALSE]
            /\ current' = NoStack
            /\ todo' = {}
            /\ alarm' = IF AlarmOnAbort THEN [s \in Stacks |-> alarm[s] \/ up[s]] ELSE alarm
       ELSE UNCHANGED <<lockHeld, current, todo, alarm>>
    /\ copyLen' = IF ViewLag = 0 THEN 0 ELSE lastTickLen
    /\ lastTickLen' = IF ViewLag = 0 THEN 0 ELSE Len(ledger)
    /\ UNCHANGED <<laneVars, up, lease, fence, downInFlight, users, usedBy, view,
                   attempts, snapLease, downFails, closedAt, liveRemoved, removed,
                   removedLate, retried>>

LaneStep ==
    \/ \E l \in Lanes : Claim(l) \/ Terminal(l) \/ Relay(l)
    \/ \E l \in Lanes, s \in Stacks : Up(l, s) \/ Adopt(l, s) \/ Quiesce(l, s)

ReaperStep ==
    \/ ReadView
    \/ \E s \in Stacks : SkipInFlight(s) \/ Decide(s) \/ DownOk(s) \/ DownFail(s)
    \/ PassDone

Next == LaneStep \/ ReaperStep \/ Tick

\* The reaper and the timer make progress; lanes need not.
Spec == Init /\ [][Next]_vars /\ WF_vars(ReaperStep) /\ WF_vars(Tick)

\* Renaming lanes or stacks maps every action and every invariant onto
\* itself, so symmetry reduction is sound for the invariant runs. The
\* temporal run (cfg/adopted_liveness.cfg) does not use it.
Symmetry == Permutations(Lanes) \cup Permutations(Stacks)

(***************************************************************************)
(* Properties.                                                             *)
(***************************************************************************)
TypeOK ==
    /\ laneSt \in [Lanes -> {"idle", "live", "ended"}]
    /\ up \in [Stacks -> BOOLEAN]
    /\ pc \in {"start", "scan", "idle"}
    /\ now \in 0..MaxTime
    /\ view <= Len(ledger)
    /\ current \in Stacks \cup {NoStack}
    /\ \A s \in Stacks : users[s] \subseteq Lanes

NeverRemoveLive == ~liveRemoved

NoUserLosesStack == \A s \in Stacks : users[s] # {} => up[s]

RemovedWithinOneInterval ==
    \A s \in Stacks : closedAt[s] # NONE => now <= closedAt[s] + Interval

OverdueIsAlarmed ==
    \A s \in Stacks : (closedAt[s] # NONE /\ now > closedAt[s] + Interval) => alarm[s]

EveryClosedStackRemoved ==
    \A s \in Stacks : (closedAt[s] # NONE) ~> (closedAt[s] = NONE)

NoRemovalEver == ~removed
NoLateRemoval == ~removedLate
NoRetrySucceeded == ~retried
=============================================================================
