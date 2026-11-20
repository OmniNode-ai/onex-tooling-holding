---------------------------- MODULE LedgerBusAppend ----------------------------
(* OMN-20275, extended by OMN-20537 (work ledger cutover plan task C7, model
   before build for C8, C18 and C21), revised after an independent review.

   A ledger row written on a host without the ledger of record. The writer
   fsyncs its request (row, request id) to a local spool, publishes it as an
   append command, and replays it under the same id while it has not received a
   receipt for it; a receipt it receives removes the request from the spool. A
   published receipt may be lost before the writer receives it.

   One serve process consumes the command partition in one consumer group. For
   each command, under the ledger lock, it checks the ledger for the request id
   and appends the row with ledger_seq = (the ledger file's last seq) + 1, then
   writes the seq to the counter file beside the ledger and releases the lock:
   two writes, with a crash possible between them. It then runs the steps of
   EmitOrder: publish the row event (acknowledged by the broker), publish the
   receipt, commit the offset. It may crash at any point. A redelivered request
   already in the ledger republishes its row event with the seq the ledger holds
   and is answered "duplicate". The row event is what the projection receives
   (`events`).

   Local writers on the ledger host (LocalRows) append through the same lock
   without the bus. The adopted configuration has none: C21 refuses a local
   append from anything but the serve process.

   Invariants:
     NoDuplicateRow, ReceiptTruth, SeqGapless, SeqMatchesFileOrder, EventTruth.
   Liveness:
     EveryRequestAnswered      - every published request gets a published receipt.
     EveryAcceptedRowProjected - every row in the ledger reaches the projection.
     EveryRequestCompleted     - every spooled request leaves the spool, which
                                 needs a receipt the writer actually received.

   Controls and their expected violations are listed in README.md.
*)
EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
  Rows, LocalRows, Refusable,
  MaxCrashes,          \* serve or local-writer crashes
  MaxReplays,          \* spool replays per request (a writer replays each request on its own timeout)
  MaxLosses,           \* receipts lost before the writer receives them
  DedupCheck,          \* the serve checks the ledger for the request id
  SpoolSameId,         \* a replay keeps the request id
  CommitBeforeAppend,  \* the offset is committed at fetch
  SeqUnderLock,        \* the seq base is read inside the lock-held append
  SeqFromFile,         \* the seq base is the ledger file's last seq, not the counter file
  DupRepublish,        \* a duplicate republishes its row event
  EmitOrder,           \* "emit_answer_commit" | "answer_emit_commit" | "answer_commit_emit"
  LocalCanCrash

ASSUME Rows \cap LocalRows = {} /\ Refusable \subseteq Rows
ASSUME EmitOrder \in {"emit_answer_commit", "answer_emit_commit", "answer_commit_emit"}

ReqIds == 1..(Cardinality(Rows) * (1 + MaxReplays))
NoReq == 0
None == "none"

VARIABLES
  bus, offset, ledger, counter, events, holder,
  receipts,   \* published receipts [req, status]
  inflight,   \* per request id: receipts published and neither received nor lost yet
  rcvd,       \* request ids the writer has received a receipt for
  losses,
  spc, todo, sreq, sstat, sseq,
  lpc, lseq,
  crashes, nextReq, sent, spool, replays

vars == <<bus, offset, ledger, counter, events, holder, receipts, inflight, rcvd,
          losses, spc, todo, sreq, sstat, sseq, lpc, lseq, crashes, nextReq,
          sent, spool, replays>>
writerVars == <<nextReq, sent, spool, replays>>
deliveryVars == <<inflight, rcvd, losses>>
serveVars == <<spc, todo, sreq, sstat, sseq>>
localVars == <<lpc, lseq>>

InLedger(i) == \E k \in 1..Len(ledger) : ledger[k].req = i
RowInLedger(r) == \E k \in 1..Len(ledger) : ledger[k].row = r
Answered(i) == \E x \in receipts : x.req = i
Received(i) == i \in rcvd
OnBus(i) == \E k \in 1..Len(bus) : bus[k].req = i
CmdRow(i) == bus[CHOOSE k \in 1..Len(bus) : bus[k].req = i].row
LastSeq == IF Len(ledger) = 0 THEN 0 ELSE ledger[Len(ledger)].seq
SeqBase == IF SeqFromFile THEN LastSeq ELSE counter
EventOf(i) ==
  LET k == CHOOSE k \in 1..Len(ledger) : ledger[k].req = i
  IN [row |-> ledger[k].row, seq |-> ledger[k].seq]
EventOfRow(r) ==
  LET k == CHOOSE k \in 1..Len(ledger) : ledger[k].row = r
  IN [row |-> r, seq |-> ledger[k].seq]

\* The serve's remaining steps for a handled command.
Steps(stat) ==
  IF stat = "refused" \/ (stat = "duplicate" /\ ~DupRepublish)
    THEN <<"answer", "commit">>
  ELSE IF EmitOrder = "emit_answer_commit" THEN <<"emit", "answer", "commit">>
  ELSE IF EmitOrder = "answer_emit_commit" THEN <<"answer", "emit", "commit">>
  ELSE <<"answer", "commit", "emit">>

Init ==
  /\ bus = << >> /\ offset = 0 /\ ledger = << >> /\ counter = 0 /\ events = {}
  /\ holder = None
  /\ receipts = {} /\ inflight = [i \in ReqIds |-> 0] /\ rcvd = {} /\ losses = 0
  /\ spc = "idle" /\ todo = << >> /\ sreq = NoReq /\ sstat = None /\ sseq = 0
  /\ lpc = [l \in LocalRows |-> "todo"] /\ lseq = [l \in LocalRows |-> 0]
  /\ crashes = 0 /\ nextReq = 1 /\ sent = {} /\ spool = {} /\ replays = [r \in Rows |-> 0]

(* ---------------------------------------------------------------- writer *)

SpoolRow(r) ==
  /\ r \notin sent
  /\ nextReq \in ReqIds
  /\ spool' = spool \cup {[row |-> r, req |-> nextReq]}
  /\ sent' = sent \cup {r}
  /\ nextReq' = nextReq + 1
  /\ UNCHANGED <<bus, offset, ledger, counter, events, holder, receipts, replays>>
  /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED localVars /\ UNCHANGED crashes

PublishSpooled(s) ==
  /\ s \in spool
  /\ ~OnBus(s.req)
  /\ bus' = Append(bus, s)
  /\ UNCHANGED <<offset, ledger, counter, events, holder, receipts>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars
  /\ UNCHANGED localVars /\ UNCHANGED crashes

\* The writer has not received a receipt for this request (none sent yet, or lost).
Replay(s) ==
  /\ s \in spool
  /\ OnBus(s.req)
  /\ ~Received(s.req)
  /\ replays[s.row] < MaxReplays
  /\ replays' = [replays EXCEPT ![s.row] = @ + 1]
  /\ IF SpoolSameId
       THEN /\ bus' = Append(bus, s)
            /\ UNCHANGED nextReq
       ELSE /\ nextReq \in ReqIds
            /\ bus' = Append(bus, [row |-> s.row, req |-> nextReq])
            /\ nextReq' = nextReq + 1
  /\ UNCHANGED <<offset, ledger, counter, events, holder, receipts, sent, spool>>
  /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED localVars /\ UNCHANGED crashes

Deliver(i) ==
  /\ inflight[i] > 0
  /\ inflight' = [inflight EXCEPT ![i] = @ - 1]
  /\ rcvd' = rcvd \cup {i}
  /\ UNCHANGED losses
  /\ UNCHANGED <<bus, offset, ledger, counter, events, holder, receipts>>
  /\ UNCHANGED writerVars /\ UNCHANGED serveVars /\ UNCHANGED localVars /\ UNCHANGED crashes

LoseReceipt(i) ==
  /\ inflight[i] > 0
  /\ losses < MaxLosses
  /\ inflight' = [inflight EXCEPT ![i] = @ - 1]
  /\ losses' = losses + 1
  /\ UNCHANGED rcvd
  /\ UNCHANGED <<bus, offset, ledger, counter, events, holder, receipts>>
  /\ UNCHANGED writerVars /\ UNCHANGED serveVars /\ UNCHANGED localVars /\ UNCHANGED crashes

\* Only a receipt the writer received removes the request; a replayed request
\* may still be on the bus, and its later receipt is simply received again.
Unspool(s) ==
  /\ s \in spool
  /\ Received(s.req)
  /\ spool' = spool \ {s}
  /\ UNCHANGED <<bus, offset, ledger, counter, events, holder, receipts,
                 nextReq, sent, replays>>
  /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED localVars /\ UNCHANGED crashes

(* ----------------------------------------------------------------- serve *)

Fetch ==
  /\ spc = "idle"
  /\ offset < Len(bus)
  /\ spc' = "fetched"
  /\ sreq' = bus[offset + 1].req
  /\ IF CommitBeforeAppend THEN offset' = offset + 1 ELSE UNCHANGED offset
  /\ UNCHANGED <<bus, ledger, counter, events, holder, receipts, todo, sstat, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

\* Takes the ledger lock. The dedup read and (adopted) the seq read happen under it.
Handle ==
  /\ spc = "fetched"
  /\ holder = None
  /\ LET r == CmdRow(sreq) IN
     IF DedupCheck /\ InLedger(sreq)
       THEN /\ sstat' = "duplicate" /\ spc' = "work" /\ todo' = Steps("duplicate")
            /\ UNCHANGED <<ledger, holder, sseq>>
     ELSE IF r \in Refusable
       THEN /\ sstat' = "refused" /\ spc' = "work" /\ todo' = Steps("refused")
            /\ UNCHANGED <<ledger, holder, sseq>>
     ELSE IF SeqUnderLock
       THEN /\ ledger' = Append(ledger, [row |-> r, req |-> sreq, seq |-> SeqBase + 1])
            /\ sseq' = SeqBase + 1
            /\ holder' = "serve" /\ spc' = "rowwritten" /\ sstat' = "accepted"
            /\ UNCHANGED todo
     ELSE \* control: the seq base is read without the lock; the lock is not taken yet
          /\ sseq' = SeqBase + 1 /\ spc' = "seqread"
          /\ UNCHANGED <<ledger, holder, sstat, todo>>
  /\ UNCHANGED <<bus, offset, counter, events, receipts, sreq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

AppendLate ==
  /\ spc = "seqread"
  /\ holder = None
  /\ ledger' = Append(ledger, [row |-> CmdRow(sreq), req |-> sreq, seq |-> sseq])
  /\ holder' = "serve" /\ spc' = "rowwritten" /\ sstat' = "accepted"
  /\ UNCHANGED <<bus, offset, counter, events, receipts, todo, sreq, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

\* The second write under the lock: the counter file. Then the lock is released.
WriteCounter ==
  /\ spc = "rowwritten"
  /\ counter' = sseq
  /\ holder' = None
  /\ spc' = "work"
  /\ todo' = Steps("accepted")
  /\ UNCHANGED <<bus, offset, ledger, events, receipts, sreq, sstat, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

DoEmit ==
  /\ spc = "work" /\ todo # << >> /\ Head(todo) = "emit"
  /\ events' = events \cup {EventOf(sreq)}
  /\ todo' = Tail(todo)
  /\ spc' = IF Tail(todo) = << >> THEN "idle" ELSE "work"
  /\ UNCHANGED <<bus, offset, ledger, counter, holder, receipts, sreq, sstat, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

DoAnswer ==
  /\ spc = "work" /\ todo # << >> /\ Head(todo) = "answer"
  /\ receipts' = receipts \cup {[req |-> sreq, status |-> sstat]}
  /\ inflight' = [inflight EXCEPT ![sreq] = @ + 1]
  /\ todo' = Tail(todo)
  /\ spc' = IF Tail(todo) = << >> THEN "idle" ELSE "work"
  /\ UNCHANGED <<bus, offset, ledger, counter, events, holder, sreq, sstat, sseq>>
  /\ UNCHANGED <<rcvd, losses>>
  /\ UNCHANGED writerVars /\ UNCHANGED localVars /\ UNCHANGED crashes

DoCommit ==
  /\ spc = "work" /\ todo # << >> /\ Head(todo) = "commit"
  /\ IF CommitBeforeAppend THEN UNCHANGED offset ELSE offset' = offset + 1
  /\ todo' = Tail(todo)
  /\ spc' = IF Tail(todo) = << >> THEN "idle" ELSE "work"
  /\ UNCHANGED <<bus, ledger, counter, events, holder, receipts, sreq, sstat, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars /\ UNCHANGED crashes

\* A crash releases the lock (fcntl) and forgets everything not yet written.
ServeCrash ==
  /\ spc # "idle"
  /\ crashes < MaxCrashes
  /\ crashes' = crashes + 1
  /\ spc' = "idle" /\ todo' = << >>
  /\ holder' = IF holder = "serve" THEN None ELSE holder
  /\ UNCHANGED <<bus, offset, ledger, counter, events, receipts, sreq, sstat, sseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED localVars

(* ---------------------------------------------- local writers (ledger host) *)

LocalStart(l) ==
  /\ lpc[l] = "todo"
  /\ IF SeqUnderLock
       THEN /\ holder = None
            /\ ledger' = Append(ledger, [row |-> l, req |-> NoReq, seq |-> SeqBase + 1])
            /\ lseq' = [lseq EXCEPT ![l] = SeqBase + 1]
            /\ holder' = l
            /\ lpc' = [lpc EXCEPT ![l] = "rowwritten"]
       ELSE /\ lseq' = [lseq EXCEPT ![l] = SeqBase + 1]
            /\ lpc' = [lpc EXCEPT ![l] = "read"]
            /\ UNCHANGED <<ledger, holder>>
  /\ UNCHANGED <<bus, offset, counter, events, receipts>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED crashes

LocalAppendLate(l) ==
  /\ lpc[l] = "read"
  /\ holder = None
  /\ ledger' = Append(ledger, [row |-> l, req |-> NoReq, seq |-> lseq[l]])
  /\ holder' = l
  /\ lpc' = [lpc EXCEPT ![l] = "rowwritten"]
  /\ UNCHANGED <<bus, offset, counter, events, receipts, lseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED crashes

LocalCounter(l) ==
  /\ lpc[l] = "rowwritten"
  /\ counter' = lseq[l]
  /\ holder' = None
  /\ lpc' = [lpc EXCEPT ![l] = "appended"]
  /\ UNCHANGED <<bus, offset, ledger, events, receipts, lseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED crashes

LocalEmit(l) ==
  /\ lpc[l] = "appended"
  /\ events' = events \cup {EventOfRow(l)}
  /\ lpc' = [lpc EXCEPT ![l] = "done"]
  /\ UNCHANGED <<bus, offset, ledger, counter, holder, receipts, lseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars /\ UNCHANGED crashes

\* A local writer has no redelivery: a crash after its append loses its event.
LocalCrash(l) ==
  /\ LocalCanCrash
  /\ lpc[l] \in {"rowwritten", "appended"}
  /\ crashes < MaxCrashes
  /\ crashes' = crashes + 1
  /\ lpc' = [lpc EXCEPT ![l] = "done"]
  /\ holder' = IF holder = l THEN None ELSE holder
  /\ UNCHANGED <<bus, offset, ledger, counter, events, receipts, lseq>>
  /\ UNCHANGED writerVars /\ UNCHANGED deliveryVars /\ UNCHANGED serveVars

(* ------------------------------------------------------------------ spec *)

ServeStep == Fetch \/ Handle \/ AppendLate \/ WriteCounter \/ DoEmit \/ DoAnswer \/ DoCommit
LocalStep(l) == LocalStart(l) \/ LocalAppendLate(l) \/ LocalCounter(l) \/ LocalEmit(l)

Next ==
  \/ \E r \in Rows : SpoolRow(r)
  \/ \E s \in spool : PublishSpooled(s) \/ Replay(s) \/ Unspool(s)
  \/ \E i \in ReqIds : Deliver(i) \/ LoseReceipt(i)
  \/ ServeStep \/ ServeCrash
  \/ \E l \in LocalRows : LocalStep(l) \/ LocalCrash(l)

Spec ==
  /\ Init /\ [][Next]_vars
  /\ WF_vars(\E s \in spool : PublishSpooled(s))
  /\ WF_vars(\E s \in spool : Replay(s))
  /\ WF_vars(\E s \in spool : Unspool(s))
  /\ WF_vars(\E i \in ReqIds : Deliver(i))
  /\ WF_vars(ServeStep)
  /\ \A l \in LocalRows : WF_vars(LocalStep(l))

(* ------------------------------------------------------------ properties *)

TypeOK ==
  /\ offset \in 0..Len(bus)
  /\ spc \in {"idle", "fetched", "seqread", "rowwritten", "work"}
  /\ holder \in {None, "serve"} \cup LocalRows

NoDuplicateRow ==
  \A i, j \in 1..Len(ledger) : i # j => ledger[i].row # ledger[j].row

ReceiptTruth ==
  \A x \in receipts :
    /\ x.status \in {"accepted", "duplicate"} => InLedger(x.req)
    /\ x.status = "refused" => ~RowInLedger(CmdRow(x.req))

SeqGapless == {ledger[k].seq : k \in 1..Len(ledger)} = 1..Len(ledger)

SeqMatchesFileOrder == \A k \in 1..Len(ledger) : ledger[k].seq = k

EventTruth ==
  \A e \in events : \E k \in 1..Len(ledger) : ledger[k].row = e.row /\ ledger[k].seq = e.seq

EveryRequestAnswered ==
  \A i \in ReqIds : OnBus(i) ~> Answered(i)

EveryAcceptedRowProjected ==
  \A r \in Rows \cup LocalRows : RowInLedger(r) ~> (\E e \in events : e.row = r)

EveryRequestCompleted ==
  \A r \in Rows : (\E s \in spool : s.row = r) ~> (\A s \in spool : s.row # r)
=============================================================================
