---------------------------- MODULE LedgerProjection ----------------------------
(***************************************************************************)
(* The rendered work-ledger projection (OMN-20275, unenforced-rulings plan *)
(* unit M6, deliverable 1).                                                *)
(*                                                                         *)
(* The ledger of record is the serve process's ledger: it assigns each     *)
(* accepted row the gapless ledger_seq under the ledger lock and publishes *)
(* one row event per row (LedgerBusAppend.tla models that half). A         *)
(* projection node on each host renders the rows into a markdown file in   *)
(* ledger_seq order. This module models that node.                         *)
(*                                                                         *)
(* Record identity is (ledger_id, ledger_seq); one ledger, so the seq.     *)
(* row_id, the sha256 of the raw row, is a content check, never identity:  *)
(* two distinct rows may carry the same text.                              *)
(*                                                                         *)
(* Checkpoints:                                                            *)
(*  - the rendered file itself: rows baseline+1 .. W in order, so the      *)
(*    watermark W is the count of complete rows, read from the file on     *)
(*    recovery, never from a second file;                                  *)
(*  - the consumer offset per topic, committed only over events whose seq  *)
(*    is at or below W.                                                    *)
(* The pending set (events received past W+1) is volatile.                 *)
(*                                                                         *)
(* The environment: row events travel on several topics (one per row       *)
(* type), so arrival order across topics is arbitrary; any event may lag;   *)
(* the serve republishes a row event on a duplicate request (at-least-once);*)
(* an accepted row's event may never be published (Unemitted, the live     *)
(* form found by the 2026-10-04 parity measurement); the repair source     *)
(* may be unable to supply a row (SourceMissing); the node may crash.      *)
(*                                                                         *)
(* A gap is a seq W+1 that the node does not hold while it knows a later   *)
(* seq exists (a pending event past it, or the source head read by the lag *)
(* probe). The node repairs a gap by reading that seq from the ledger of   *)
(* record; when the source cannot supply it, the node blocks: it renders   *)
(* nothing past the gap and says so. It never skips.                       *)
(*                                                                         *)
(* Each mutation flag replaces one design decision with its alternative;   *)
(* the README names the property each one must violate.                    *)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets

CONSTANTS
    N,               \* rows accepted by the ledger of record: seqs 1..N
    Topics,          \* the row-event topics
    TopicOf,         \* seq -> the topic its event is published on
    Content,         \* seq -> the row text (equal text for distinct seqs allowed)
    Unemitted,       \* seqs whose row event is never published
    SourceMissing,   \* seqs the repair source cannot supply
    MaxCrashes,      \* node crashes
    MaxRepublish,    \* duplicate row events the serve republishes
    \* mutations, each FALSE in the adopted design
    SkipGap,         \* a gap is skipped instead of repaired or blocked
    ContentIdentity, \* a row whose text is already rendered counts as rendered
    NoSeqDedup,      \* an event at or below W is rendered again
    SidecarWatermark,\* W lives in a second file, written after the rows
    ArrivalOrder,    \* rows are rendered in arrival order, not seq order
    NoRepair,        \* a gap waits for its event and is never repaired
    NoBlock,         \* a gap the source cannot supply is retried silently
    NoHeadProbe,     \* the node never reads the source head
    CommitOnReceive  \* the offset is committed as soon as an event is read

Seqs == 1..N

\* The checked instance (cfg: TopicOf <- CheckedTopicOf, Content <- CheckedContent):
\* seq 2 travels on its own topic, and seqs 1 and 2 carry the same text.
CheckedTopicOf == <<"t1", "t2", "t1">>
CheckedContent == <<"a", "a", "b">>

ASSUME TopicOf \in [Seqs -> Topics]
ASSUME Unemitted \subseteq Seqs /\ SourceMissing \subseteq Seqs

VARIABLES
    appended,   \* the ledger of record holds seqs 1..appended
    log,        \* [Topics -> Seq(Seqs)]: each topic's event log (broker)
    republished,\* duplicate events published so far
    offset,     \* [Topics -> Nat]: committed consumer offset (durable, broker)
    pos,        \* [Topics -> Nat]: the node's read position (volatile)
    pending,    \* seqs received or repaired, not yet rendered (volatile)
    file,       \* Seq(Seqs): the rendered rows (durable)
    sidecar,    \* the second-file watermark (durable; SidecarWatermark only)
    sidecarDue, \* rows written, sidecar not yet written (SidecarWatermark only)
    W,          \* the node's watermark (volatile)
    head,       \* the source head the node last read (volatile)
    blocked,    \* the node reports a gap it cannot repair (volatile)
    up,         \* the node is running
    crashes,
    \* audit history, read only by the reachability controls
    dropped,    \* duplicate events dropped on receipt (seq at or below W)
    lenAtCrash  \* rows in the file at the last crash (-1 before any)

vars == <<appended, log, republished, offset, pos, pending, file, sidecar,
          sidecarDue, W, head, blocked, up, crashes, dropped, lenAtCrash>>

Max(a, b) == IF a >= b THEN a ELSE b
Range(s) == {s[i] : i \in DOMAIN s}

Init ==
    /\ appended = 0
    /\ log = [t \in Topics |-> <<>>]
    /\ republished = 0
    /\ offset = [t \in Topics |-> 0]
    /\ pos = [t \in Topics |-> 0]
    /\ pending = {}
    /\ file = <<>>
    /\ sidecar = 0
    /\ sidecarDue = FALSE
    /\ W = 0
    /\ head = 0
    /\ blocked = FALSE
    /\ up = TRUE
    /\ crashes = 0
    /\ dropped = 0
    /\ lenAtCrash = -1

(***************************************************************************)
(* The ledger of record: append the next row and publish its event        *)
(* (LedgerBusAppend.tla: the event is published before the offset of the *)
(* append command is committed, so an emitted row's event is not lost on   *)
(* the append side). Unemitted rows model a writer that never emits.       *)
(***************************************************************************)
AppendRow ==
    /\ appended < N
    /\ appended' = appended + 1
    /\ log' = IF appended + 1 \in Unemitted THEN log
              ELSE [log EXCEPT ![TopicOf[appended + 1]] = Append(@, appended + 1)]
    /\ UNCHANGED <<republished, offset, pos, pending, file, sidecar, sidecarDue,
                   W, head, blocked, up, crashes, dropped, lenAtCrash>>

\* A redelivered append request republishes its row event (C8).
Republish(k) ==
    /\ k <= appended
    /\ k \notin Unemitted
    /\ republished < MaxRepublish
    /\ republished' = republished + 1
    /\ log' = [log EXCEPT ![TopicOf[k]] = Append(@, k)]
    /\ UNCHANGED <<appended, offset, pos, pending, file, sidecar, sidecarDue,
                   W, head, blocked, up, crashes, dropped, lenAtCrash>>

(***************************************************************************)
(* The projection node.                                                    *)
(***************************************************************************)
\* Under ContentIdentity a row counts as present when its text is rendered.
Present(k) ==
    IF ContentIdentity
    THEN \E i \in DOMAIN file : Content[file[i]] = Content[k]
    ELSE \E i \in DOMAIN file : file[i] = k

\* Read the next event of topic t. An event at or below W is a duplicate.
Receive(t) ==
    /\ up
    /\ pos[t] < Len(log[t])
    /\ LET k == log[t][pos[t] + 1] IN
         /\ pos' = [pos EXCEPT ![t] = @ + 1]
         /\ pending' = IF k <= W /\ ~NoSeqDedup THEN pending ELSE pending \cup {k}
         /\ offset' = IF CommitOnReceive THEN [offset EXCEPT ![t] = pos[t] + 1]
                      ELSE offset
         /\ dropped' = IF k <= W /\ ~NoSeqDedup THEN dropped + 1 ELSE dropped
    /\ UNCHANGED <<appended, log, republished, file, sidecar, sidecarDue, W,
                   head, blocked, up, crashes, lenAtCrash>>

\* Write one row to the file. The adopted rule renders W+1 only.
Render ==
    /\ up
    /\ ~sidecarDue
    /\ \E k \in pending :
         /\ \/ k = W + 1
            \/ ArrivalOrder
            \/ NoSeqDedup /\ k <= W
         /\ pending' = pending \ {k}
         /\ IF ContentIdentity /\ Present(k) /\ k = W + 1
              THEN \* "already projected": advance without writing
                   /\ file' = file
                   /\ W' = W + 1
                   /\ sidecarDue' = sidecarDue
              ELSE /\ file' = Append(file, k)
                   /\ W' = Max(W, k)
                   /\ sidecarDue' = SidecarWatermark
         /\ blocked' = FALSE
    /\ UNCHANGED <<appended, log, republished, offset, pos, sidecar, head, up,
                   crashes, dropped, lenAtCrash>>

\* SidecarWatermark only: the second write, after the rows.
WriteSidecar ==
    /\ up
    /\ sidecarDue
    /\ sidecar' = W
    /\ sidecarDue' = FALSE
    /\ UNCHANGED <<appended, log, republished, offset, pos, pending, file, W,
                   head, blocked, up, crashes, dropped, lenAtCrash>>

\* Commit topic t over its longest read prefix whose events are all at or below W.
CommitTo(t) ==
    LET ok(p) == \A i \in (offset[t] + 1)..p : log[t][i] <= W
    IN  CHOOSE p \in offset[t]..pos[t] :
            ok(p) /\ \A q \in offset[t]..pos[t] : ok(q) => q <= p

Commit(t) ==
    /\ up
    /\ ~CommitOnReceive
    /\ CommitTo(t) > offset[t]
    /\ offset' = [offset EXCEPT ![t] = CommitTo(t)]
    /\ UNCHANGED <<appended, log, republished, pos, pending, file, sidecar,
                   sidecarDue, W, head, blocked, up, crashes, dropped, lenAtCrash>>

\* The lag probe: read the source head.
ProbeHead ==
    /\ up
    /\ ~NoHeadProbe
    /\ head < appended
    /\ head' = appended
    /\ UNCHANGED <<appended, log, republished, offset, pos, pending, file,
                   sidecar, sidecarDue, W, blocked, up, crashes, dropped, lenAtCrash>>

Gap ==
    /\ up
    /\ ~sidecarDue
    /\ W + 1 \notin pending
    /\ \/ \E k \in pending : k > W + 1
       \/ head > W

\* Read seq W+1 from the ledger of record; block when it cannot be supplied.
Repair ==
    /\ Gap
    /\ ~NoRepair
    /\ ~SkipGap
    /\ IF W + 1 \notin SourceMissing
         THEN /\ pending' = pending \cup {W + 1}
              /\ blocked' = blocked
         ELSE /\ pending' = pending
              /\ blocked' = ~NoBlock
    /\ blocked' # blocked \/ pending' # pending
    /\ UNCHANGED <<appended, log, republished, offset, pos, file, sidecar,
                   sidecarDue, W, head, up, crashes, dropped, lenAtCrash>>

\* SkipGap only: give up on W+1 and render the next row held.
Skip ==
    /\ SkipGap
    /\ Gap
    /\ \E k \in pending :
         /\ k > W + 1
         /\ \A j \in pending : j >= k
         /\ file' = Append(file, k)
         /\ W' = k
         /\ pending' = pending \ {k}
    /\ UNCHANGED <<appended, log, republished, offset, pos, sidecar, sidecarDue,
                   head, blocked, up, crashes, dropped, lenAtCrash>>

Crash ==
    /\ up
    /\ crashes < MaxCrashes
    /\ up' = FALSE
    /\ crashes' = crashes + 1
    /\ sidecarDue' = FALSE   \* the second write, if due, is lost
    /\ lenAtCrash' = Len(file)
    /\ UNCHANGED <<appended, log, republished, offset, pos, pending, file,
                   sidecar, W, head, blocked, dropped>>

\* Restart: volatile state is rebuilt from the durable checkpoints.
Recover ==
    /\ ~up
    /\ up' = TRUE
    /\ pos' = offset
    /\ pending' = {}
    /\ W' = IF SidecarWatermark THEN sidecar ELSE Len(file)
    /\ head' = 0
    /\ blocked' = FALSE
    /\ UNCHANGED <<appended, log, republished, offset, file, sidecar,
                   sidecarDue, crashes, dropped, lenAtCrash>>

Next ==
    \/ AppendRow
    \/ \E k \in Seqs : Republish(k)
    \/ \E t \in Topics : Receive(t) \/ Commit(t)
    \/ Render \/ WriteSidecar \/ ProbeHead \/ Repair \/ Skip
    \/ Crash \/ Recover

Fairness ==
    /\ WF_vars(AppendRow)
    /\ \A t \in Topics : WF_vars(Receive(t)) /\ WF_vars(Commit(t))
    /\ WF_vars(Render)
    /\ WF_vars(WriteSidecar)
    /\ WF_vars(ProbeHead)
    /\ WF_vars(Repair)
    /\ WF_vars(Skip)
    /\ WF_vars(Recover)

Spec == Init /\ [][Next]_vars /\ Fairness

(***************************************************************************)
(* Properties.                                                             *)
(***************************************************************************)
TypeOK ==
    /\ appended \in 0..N
    /\ \A t \in Topics : offset[t] <= pos[t] \/ ~up
    /\ pending \subseteq Seqs
    /\ Range(file) \subseteq Seqs

\* Safety: no projected record lost. Every seq up to the highest rendered seq
\* is rendered: the projection never moves past a row it does not hold.
NoRecordLost ==
    \A i \in DOMAIN file : \A k \in 1..file[i] : k \in Range(file)

\* Safety: no duplicate. No seq is rendered twice.
NoDuplicate ==
    \A i, j \in DOMAIN file : i # j => file[i] # file[j]

\* Safety: rows are rendered in seq order.
InOrder ==
    \A i \in DOMAIN file : file[i] = i

\* Liveness: a gap is repaired or blocks.
GapRepairedOrBlocks ==
    \A k \in Seqs :
        (Gap /\ W + 1 = k) ~> (Len(file) >= k \/ blocked)

\* Liveness: every accepted row is rendered, or the node blocks short of it.
\* This also covers a lost tail row, which no later event reveals.
EveryRowProjectedOrBlocked ==
    \A k \in Seqs : <>[](Len(file) >= k \/ blocked)

(***************************************************************************)
(* Reachability controls. Each is checked as an invariant on an adopted    *)
(* configuration and must be violated: the violation is the witness that   *)
(* the adopted run reaches the path it claims, so its pass is not vacuous. *)
(***************************************************************************)
\* Every row rendered by a node that crashed before the file was complete,
\* recovered, and dropped at least one duplicate event on receipt. With seq 2
\* unemitted, row 2 reaches the file only through Repair.
NotRepairedAfterCrashAndDuplicate ==
    ~(/\ Len(file) = N
      /\ up
      /\ crashes = MaxCrashes
      /\ 0 <= lenAtCrash /\ lenAtCrash < N
      /\ dropped >= 1)

\* The node reports a gap the source cannot supply.
NeverBlocked == ~blocked

\* Every row rendered. With the tail seq unemitted, no later event reveals it:
\* only the head probe does.
TailNeverRendered == Len(file) < N

=============================================================================
