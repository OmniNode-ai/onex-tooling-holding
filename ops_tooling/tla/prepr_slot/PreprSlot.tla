---------------------------- MODULE PreprSlot ----------------------------
(* OMN-19567 (T3 of the lab-proof-for-every-PR plan, gate for OMN-18895):
   claims, slot holds, head moves and fork approvals for a pre-PR proof slot.

   One PR whose head can move, a set of provers, and host-local slot numbers. A prover reads
   the PR head and is admitted on it, later claims a slot, proves the head it
   was admitted on, and posts a receipt keyed on that head. The required check
   reads the receipts. The model fixes five properties:

     NoTwoProvers      no two provers occupy one slot
     ReleasedSlotEmpty a slot has an occupant exactly when it holds a head
     ReceiptFresh      a posted receipt is keyed on the head it proved
     PassIsCurrent     the required check is green only on a receipt keyed on the
                       PR's current head: a head move invalidates the receipt key
     ForkApproved      a fork head never occupies a slot without an approval
                       bound to that exact head

   `Mutation` switches ONE design rule off. Each mutation must violate the
   property named in its cfg; the design cfgs must hold; the witness cfgs prove
   the interesting steps are reachable, so a green design run is not vacuous. *)
EXTENDS Naturals, FiniteSets

CONSTANTS Provers, Hosts, SlotNumbers, Heads, IsFork, Mutation

\* A physical slot is a pair: two hosts may both have a slot numbered one.
Slots == Hosts \X SlotNumbers

NONE == "none"
NoSlot == <<NONE, NONE>>

VARIABLES occ,        \* slot -> set of provers in it
          slotHead,   \* slot -> the head its proof runs on, or NONE
          seen,       \* prover -> slot it saw free when it read (used by check_then_act)
          checked,    \* prover -> the head it read and was admitted on, or NONE
          evicted,    \* history: a stale slot has been reclaimed
          prHead,     \* the PR's current head
          approved,   \* heads a human approved (a fork approval binds one head)
          receipts    \* posted receipts: the head proved, the head current at posting

vars == <<occ, slotHead, seen, checked, evicted, prHead, approved, receipts>>

Receipt == [head : Heads, atHead : Heads]

TypeOK ==
  /\ occ \in [Slots -> SUBSET Provers]
  /\ slotHead \in [Slots -> Heads \cup {NONE}]
  /\ seen \in [Provers -> Slots \cup {NoSlot}]
  /\ checked \in [Provers -> Heads \cup {NONE}]
  /\ evicted \in BOOLEAN
  /\ prHead \in Heads
  /\ approved \subseteq Heads
  /\ receipts \subseteq Receipt

Init ==
  /\ occ = [s \in Slots |-> {}]
  /\ slotHead = [s \in Slots |-> NONE]
  /\ seen = [p \in Provers |-> NoSlot]
  /\ checked = [p \in Provers |-> NONE]
  /\ evicted = FALSE
  /\ prHead \in Heads
  /\ approved = {}
  /\ receipts = {}

\* Design: a fork head is admitted only when THAT head is approved.
\* approval_any: any approval at all admits the fork (approval not bound to a head).
Admitted(h) ==
  IF ~IsFork THEN TRUE
  ELSE IF Mutation = "approval_any" THEN approved # {} ELSE h \in approved

Holding(p) == \E t \in Slots : p \in occ[t]
Stale(s) == occ[s] # {} /\ slotHead[s] # prHead

\* The required check. Design: green when a receipt is keyed on the current head.
\* pass_any_receipt: green when any receipt exists, whatever head it proved.
Passed ==
  IF Mutation = "pass_any_receipt" THEN receipts # {}
  ELSE \E r \in receipts : r.head = prHead

\* A prover reads the PR head and is admitted on it. The slot claim is a later
\* step, so the head can move in between.
Read(p, s) ==
  /\ checked[p] = NONE /\ ~Holding(p)
  /\ Admitted(prHead)
  /\ checked' = [checked EXCEPT ![p] = prHead]
  /\ seen' = [seen EXCEPT ![p] = IF occ[s] = {} THEN s ELSE NoSlot]
  /\ UNCHANGED <<occ, slotHead, evicted, prHead, approved, receipts>>

\* Design: the claim re-checks the slot is free and takes it in one step, and the
\* slot holds the head the prover was admitted on.
\* check_then_act: trusts the earlier read of the slot instead of re-checking.
\* enter_at_current: records the head current at entry instead of the admitted one.
Enter(p, s) ==
  /\ checked[p] # NONE
  /\ ~Holding(p)
  /\ IF Mutation = "check_then_act" THEN seen[p] = s ELSE occ[s] = {}
  /\ occ' = [occ EXCEPT ![s] = @ \cup {p}]
  /\ slotHead' = [slotHead EXCEPT ![s] =
       IF Mutation = "enter_at_current" THEN prHead ELSE checked[p]]
  /\ checked' = [checked EXCEPT ![p] = NONE]
  /\ seen' = [seen EXCEPT ![p] = NoSlot]
  /\ UNCHANGED <<evicted, prHead, approved, receipts>>

Approve ==
  /\ IsFork
  /\ approved' = approved \cup {prHead}
  /\ UNCHANGED <<occ, slotHead, seen, checked, evicted, prHead, receipts>>

MoveHead(h) ==
  /\ h # prHead
  /\ prHead' = h
  /\ UNCHANGED <<occ, slotHead, seen, checked, evicted, approved, receipts>>

\* Release empties the slot. release_keeps_head forgets to clear the head.
LeaveSlot(p, s) ==
  /\ occ' = [occ EXCEPT ![s] = @ \ {p}]
  /\ slotHead' =
       IF Mutation = "release_keeps_head" \/ occ[s] \ {p} # {}
         THEN slotHead
         ELSE [slotHead EXCEPT ![s] = NONE]

\* Prover ended without a receipt (failed, timed out, or its head moved).
Release(p, s) ==
  /\ p \in occ[s]
  /\ LeaveSlot(p, s)
  /\ UNCHANGED <<seen, checked, evicted, prHead, approved, receipts>>

\* Design: a receipt is posted only for the head still current. post_stale posts anyway.
Post(p, s) ==
  /\ p \in occ[s]
  /\ Mutation = "post_stale" \/ slotHead[s] = prHead
  /\ receipts' = receipts \cup {[head |-> slotHead[s], atHead |-> prHead]}
  /\ LeaveSlot(p, s)
  /\ UNCHANGED <<seen, checked, evicted, prHead, approved>>

\* The scheduler reclaims a slot whose proof's head moved, so a hung prover cannot
\* hold it. An evicted prover is gone from occ, so it cannot post.
Evict(s) ==
  /\ Stale(s)
  /\ occ' = [occ EXCEPT ![s] = {}]
  /\ slotHead' = [slotHead EXCEPT ![s] = NONE]
  /\ evicted' = TRUE
  /\ UNCHANGED <<seen, checked, prHead, approved, receipts>>

Next ==
  \/ \E p \in Provers, s \in Slots : Read(p, s) \/ Enter(p, s) \/ Release(p, s) \/ Post(p, s)
  \/ \E s \in Slots : Evict(s)
  \/ Approve
  \/ \E h \in Heads : MoveHead(h)

Spec == Init /\ [][Next]_vars

NoTwoProvers == \A s \in Slots : Cardinality(occ[s]) <= 1
ReleasedSlotEmpty == \A s \in Slots : (occ[s] = {}) <=> (slotHead[s] = NONE)
ReceiptFresh == \A r \in receipts : r.head = r.atHead
PassIsCurrent == Passed => \E r \in receipts : r.head = prHead
ForkApproved == IsFork => \A s \in Slots : occ[s] # {} => slotHead[s] \in approved

\* Witnesses: each is VIOLATED when its step is reachable.
NoReceiptEver == receipts = {}
NoOccupant == \A s \in Slots : occ[s] = {}
NoEviction == ~evicted
NoPass == ~Passed
=============================================================================
