-------------------------- MODULE HostDriftSync --------------------------
EXTENDS Integers, FiniteSets

CONSTANTS Hosts, Items, HostOf, MaxAttempts, MaxTime, DeferBound,
          LockEnabled, CheckAttempt, DeferRefunds, PersistEscalation,
          h1, h2, a, b, c

ModelHostOf == [i \in Items |-> IF i = c THEN h2 ELSE h1]

ASSUME /\ HostOf \in [Items -> Hosts]
       /\ MaxAttempts \in Nat \ {0}
       /\ MaxTime \in Nat \ {0}
       /\ DeferBound \in Nat
       /\ DeferBound < MaxTime
       /\ {LockEnabled, CheckAttempt, DeferRefunds, PersistEscalation}
              \subseteq BOOLEAN

Statuses == {"NONE", "QUEUED", "FIXING", "CONFIRMING", "DEFERRED",
             "DONE", "FAILED"}
Busy == {"FIXING", "CONFIRMING"}
Active == {"QUEUED", "FIXING", "CONFIRMING", "DEFERRED"}
Terminal == {"DONE", "FAILED"}
Outcomes == {"APPLIED", "ALERT_ONLY", "DEFERRED", "FAILED"}

VARIABLES status, attempts, defers, issued, highestIssued, checkIssued,
          failedEmits, terminalIssued, staleApplied,
          clock, laneHeld, waited, deferredFor, escalated, escEmits

\* clock: ticks elapsed, bounded by MaxTime (the finite horizon of the model).
\* laneHeld: a lane holds the host; only then does the fix node answer DEFERRED.
\* waited: a tick has passed since the item's latest deferral (retry_at).
\* deferredFor: ticks since the episode's first deferral, -1 outside an episode.
\* escalated: the escalation recorded in the job record (persisted).
\* escEmits: escalation events emitted in the item's latest episode (history).
timeVars == <<clock, laneHeld, waited>>
episodeVars == <<deferredFor, escalated, escEmits>>
vars == <<status, attempts, defers, issued, highestIssued, checkIssued,
          failedEmits, terminalIssued, staleApplied,
          clock, laneHeld, waited, deferredFor, escalated, escEmits>>

Init ==
    /\ status = [i \in Items |-> "NONE"]
    /\ attempts = [i \in Items |-> 0]
    /\ defers = [i \in Items |-> 0]
    /\ issued = [i \in Items |-> 0]
    /\ highestIssued = [i \in Items |-> 0]
    /\ checkIssued = [i \in Items |-> FALSE]
    /\ failedEmits = [i \in Items |-> 0]
    /\ terminalIssued = [i \in Items |-> -1]
    /\ staleApplied = FALSE
    /\ clock = 0
    /\ laneHeld \in [Hosts -> BOOLEAN]
    /\ waited = [i \in Items |-> FALSE]
    /\ deferredFor = [i \in Items |-> -1]
    /\ escalated = [i \in Items |-> FALSE]
    /\ escEmits = [i \in Items |-> 0]

\* Symbolic, retained network history. Attempt numbers issued are contiguous.
\* Replies to any historical request can be delivered repeatedly, in any order.
\* Outcomes are unconstrained: an overapproximation of immutable duplicate
\* payloads, avoiding an exponential set of queued copies (see README).
FixRequests == UNION {{<<i, n>> : n \in 1..highestIssued[i]} : i \in Items}
CheckRequests == {i \in Items : checkIssued[i]}

SyncRequired(i) ==
    IF status[i] = "NONE"
    THEN /\ status' = [status EXCEPT ![i] = "QUEUED"]
         /\ UNCHANGED <<attempts, defers, issued, highestIssued, checkIssued,
                        failedEmits, terminalIssued, staleApplied,
                        timeVars, episodeVars>>
    ELSE UNCHANGED vars

HostFree(i) ==
    \A j \in Items : HostOf[j] = HostOf[i] => status[j] \notin Busy

Schedule(i) ==
    /\ status[i] = "QUEUED"
    /\ ~LockEnabled \/ HostFree(i)
    /\ status' = [status EXCEPT ![i] = "FIXING"]
    /\ attempts' = [attempts EXCEPT ![i] = @ + 1]
    /\ issued' = [issued EXCEPT ![i] = @ + 1]
    /\ highestIssued' = [highestIssued EXCEPT
           ![i] = IF attempts[i] + 1 > @ THEN attempts[i] + 1 ELSE @]
    /\ UNCHANGED <<defers, checkIssued, failedEmits, terminalIssued,
                   staleApplied, timeVars, episodeVars>>

\* A fix that actually ran (any outcome but DEFERRED) ends the deferral episode.
\* escEmits stays as the history of the episode that ended.
EndEpisode(i) ==
    /\ deferredFor' = [deferredFor EXCEPT ![i] = -1]
    /\ escalated' = [escalated EXCEPT ![i] = FALSE]
    /\ UNCHANGED escEmits

\* Caller supplies changes to attempts/defers/network/audit variables.
\* The terminal emit and status update are one orchestrator transition.
RetryOrFail(i) ==
    IF attempts[i] < MaxAttempts
    THEN /\ status' = [status EXCEPT ![i] = "QUEUED"]
         /\ UNCHANGED <<failedEmits, terminalIssued>>
    ELSE /\ status' = [status EXCEPT ![i] = "FAILED"]
         /\ failedEmits' = [failedEmits EXCEPT ![i] = @ + 1]
         /\ terminalIssued' = [terminalIssued EXCEPT ![i] = issued[i]]

Finish(i) ==
    /\ status' = [status EXCEPT ![i] = "DONE"]
    /\ terminalIssued' = [terminalIssued EXCEPT ![i] = issued[i]]
    /\ UNCHANGED failedEmits

FixCompleted(i, n, outcome) ==
    IF status[i] = "FIXING" /\ (~CheckAttempt \/ n = attempts[i])
    THEN /\ outcome = "DEFERRED" => clock < MaxTime /\ laneHeld[HostOf[i]]
         /\ staleApplied' = (staleApplied \/ n # attempts[i])
         /\ UNCHANGED <<issued, highestIssued>>
         /\ CASE outcome = "APPLIED" ->
                    /\ status' = [status EXCEPT ![i] = "CONFIRMING"]
                    /\ checkIssued' = [checkIssued EXCEPT ![i] = TRUE]
                    /\ EndEpisode(i)
                    /\ UNCHANGED <<attempts, defers, failedEmits,
                                   terminalIssued, timeVars>>
                 [] outcome = "ALERT_ONLY" ->
                    /\ Finish(i)
                    /\ EndEpisode(i)
                    /\ UNCHANGED <<attempts, defers, checkIssued, timeVars>>
                 [] outcome = "DEFERRED" ->
                    /\ status' = [status EXCEPT ![i] = "DEFERRED"]
                    /\ defers' = [defers EXCEPT ![i] = @ + 1]
                    /\ attempts' = [attempts EXCEPT
                           ![i] = IF DeferRefunds THEN @ - 1 ELSE @]
                    /\ waited' = [waited EXCEPT ![i] = FALSE]
                    /\ deferredFor' = [deferredFor EXCEPT
                           ![i] = IF @ = -1 THEN 0 ELSE @]
                    /\ escEmits' = [escEmits EXCEPT
                           ![i] = IF deferredFor[i] = -1 THEN 0 ELSE @]
                    /\ UNCHANGED <<checkIssued, failedEmits, terminalIssued,
                                   clock, laneHeld, escalated>>
                 [] outcome = "FAILED" ->
                    /\ RetryOrFail(i)
                    /\ EndEpisode(i)
                    /\ UNCHANGED <<attempts, defers, checkIssued, timeVars>>
    ELSE UNCHANGED vars

FixNode(i) ==
    \E n \in 1..highestIssued[i], outcome \in Outcomes :
        FixCompleted(i, n, outcome)

CheckAnswer(i, converged) ==
    /\ i \in CheckRequests
    /\ IF status[i] = "CONFIRMING"
       THEN IF converged THEN Finish(i) ELSE RetryOrFail(i)
       ELSE UNCHANGED <<status, failedEmits, terminalIssued>>
    /\ UNCHANGED <<attempts, defers, issued, highestIssued, checkIssued,
                   staleApplied, timeVars, episodeVars>>

CheckNode(i) == \E converged \in BOOLEAN : CheckAnswer(i, converged)

Resolved(i) ==
    /\ IF status[i] \in Active
       THEN Finish(i)
       ELSE UNCHANGED <<status, failedEmits, terminalIssued>>
    /\ UNCHANGED <<attempts, defers, issued, highestIssued, checkIssued,
                   staleApplied, timeVars, episodeVars>>

Timeout(i) ==
    /\ status[i] \in Busy
    /\ RetryOrFail(i)
    /\ UNCHANGED <<attempts, defers, issued, highestIssued, checkIssued,
                   staleApplied, timeVars, episodeVars>>

\* retry_at: a deferred item is retried only after time has passed.
DeferredRetry(i) ==
    /\ status[i] = "DEFERRED"
    /\ waited[i]
    /\ status' = [status EXCEPT ![i] = "QUEUED"]
    /\ UNCHANGED <<attempts, defers, issued, highestIssued, checkIssued,
                   failedEmits, terminalIssued, staleApplied,
                   timeVars, episodeVars>>

\* Wall time passes up to the model's horizon. Every active episode ages.
Tick ==
    /\ clock < MaxTime
    /\ clock' = clock + 1
    /\ waited' = [i \in Items |-> TRUE]
    /\ deferredFor' = [i \in Items |->
           IF deferredFor[i] >= 0 /\ status[i] \in Active
           THEN deferredFor[i] + 1 ELSE deferredFor[i]]
    /\ UNCHANGED <<status, attempts, defers, issued, highestIssued,
                   checkIssued, failedEmits, terminalIssued, staleApplied,
                   laneHeld, escalated, escEmits>>

\* A deferring lane ends; a fair environment ends every lane.
LaneEnds(h) ==
    /\ laneHeld[h]
    /\ laneHeld' = [laneHeld EXCEPT ![h] = FALSE]
    /\ UNCHANGED <<status, attempts, defers, issued, highestIssued,
                   checkIssued, failedEmits, terminalIssued, staleApplied,
                   clock, waited, episodeVars>>

\* Escalation is separate from termination: it records itself in the job
\* record and emits one event, and changes nothing else about the item.
Escalate(i) ==
    /\ status[i] \in Active
    /\ deferredFor[i] > DeferBound
    /\ ~escalated[i]
    /\ escalated' = [escalated EXCEPT ![i] = TRUE]
    /\ escEmits' = [escEmits EXCEPT ![i] = @ + 1]
    /\ UNCHANGED <<status, attempts, defers, issued, highestIssued,
                   checkIssued, failedEmits, terminalIssued, staleApplied,
                   timeVars, deferredFor>>

\* An orchestrator restart keeps the job record when the escalation is
\* persisted in it, and forgets it when it is not.
Restart ==
    /\ escalated' = IF PersistEscalation THEN escalated
                     ELSE [i \in Items |-> FALSE]
    /\ UNCHANGED <<status, attempts, defers, issued, highestIssued,
                   checkIssued, failedEmits, terminalIssued, staleApplied,
                   timeVars, deferredFor, escEmits>>

Next == \/ \E i \in Items :
            \/ SyncRequired(i)
            \/ Schedule(i)
            \/ FixNode(i)
            \/ CheckNode(i)
            \/ Resolved(i)
            \/ Timeout(i)
            \/ DeferredRetry(i)
            \/ Escalate(i)
        \/ \E h \in Hosts : LaneEnds(h)
        \/ Tick
        \/ Restart

Spec == Init /\ [][Next]_vars
             /\ \A i \in Items :
                    /\ WF_vars(Schedule(i))
                    /\ WF_vars(FixNode(i))
                    /\ WF_vars(CheckNode(i))
                    /\ WF_vars(Timeout(i))
                    /\ WF_vars(DeferredRetry(i))
                    /\ WF_vars(Escalate(i))
             /\ \A h \in Hosts : WF_vars(LaneEnds(h))
             /\ WF_vars(Tick)

TypeOK ==
    /\ status \in [Items -> Statuses]
    /\ attempts \in [Items -> 0..(MaxAttempts + MaxTime + 1)]
    /\ defers \in [Items -> 0..(MaxTime + 1)]
    /\ issued \in [Items -> 0..(MaxAttempts + MaxTime + 1)]
    /\ highestIssued \in [Items -> 0..(MaxAttempts + MaxTime + 1)]
    /\ checkIssued \in [Items -> BOOLEAN]
    /\ failedEmits \in [Items -> 0..1]
    /\ terminalIssued \in [Items -> ({-1} \cup 0..(MaxAttempts + MaxTime + 1))]
    /\ staleApplied \in BOOLEAN
    /\ clock \in 0..MaxTime
    /\ laneHeld \in [Hosts -> BOOLEAN]
    /\ waited \in [Items -> BOOLEAN]
    /\ deferredFor \in [Items -> ({-1} \cup 0..MaxTime)]
    /\ escalated \in [Items -> BOOLEAN]
    /\ escEmits \in [Items -> 0..2]

OneFixPerHost == \A h \in Hosts :
    Cardinality({i \in Items : HostOf[i] = h /\ status[i] \in Busy}) <= 1

AttemptBound == \A i \in Items :
    /\ attempts[i] <= MaxAttempts
    /\ issued[i] - defers[i] <= MaxAttempts

FixFailedOnce == \A i \in Items :
    /\ failedEmits[i] <= 1
    /\ (failedEmits[i] > 0 =>
           status[i] = "FAILED" /\ attempts[i] = MaxAttempts)
    /\ (status[i] = "FAILED" => failedEmits[i] = 1)

NoDispatchAfterTerminal == \A i \in Items :
    terminalIssued[i] = -1 \/ issued[i] = terminalIssued[i]

\* Additional semantic checks, separate from the requested upper bounds.
DeferredAccounting == \A i \in Items : attempts[i] = issued[i] - defers[i]
ReplyMatchesCurrentAttempt == ~staleApplied

\* One escalation per episode, none before the bound, and it needs the
\* episode that justified it, across a restart.
EscalatedOnce == \A i \in Items : escEmits[i] <= 1
NoEarlyEscalation == \A i \in Items :
    (deferredFor[i] >= 0 /\ (escalated[i] \/ escEmits[i] > 0))
        => deferredFor[i] > DeferBound
RecordMatchesEmit == \A i \in Items :
    (escalated[i] /\ deferredFor[i] >= 0) => escEmits[i] = 1

\* NONE can only be left by SyncRequired; receipt therefore needs no extra bit.
\* Restated over items whose deferring lane ends: Spec carries weak fairness
\* on LaneEnds, and a deferral is only answered while a lane holds the host.
EveryItemTerminates == \A i \in Items :
    (status[i] # "NONE") ~> (status[i] \in Terminal)

\* Escalation does not terminate, retry or refund anything.
EscalationChangesNothingElse ==
    [][\A i \in Items : escEmits'[i] > escEmits[i] =>
           /\ status'[i] = status[i]
           /\ attempts'[i] = attempts[i]
           /\ defers'[i] = defers[i]
           /\ issued'[i] = issued[i]]_vars

\* An item past the bound is escalated, unless it stops being active or its
\* episode ends first.
EscalatedWhenDue == \A i \in Items :
    (status[i] \in Active /\ deferredFor[i] > DeferBound)
        ~> (escalated[i] \/ escEmits[i] > 0 \/ status[i] \notin Active
            \/ deferredFor[i] < 0)
=============================================================================
