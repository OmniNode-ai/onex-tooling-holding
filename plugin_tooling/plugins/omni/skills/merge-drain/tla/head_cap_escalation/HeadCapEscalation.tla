------------------------- MODULE HeadCapEscalation -------------------------
(***************************************************************************)
(* The landing controller never leaves a PR gated with no next action      *)
(* (OMN-19998, RULING 2026-10-14T05:17:57Z).                               *)
(*                                                                         *)
(* Before this change a PR whose head had its MAX_DISPATCHES_PER_HEAD      *)
(* workers (head_cap), whose last worker left no result (no_result_file)   *)
(* or no attempt (no_attempt:<kind>) was worker-gated until its head moved *)
(* and nothing acted on it: tick 2392 held 23 PRs that way.                *)
(*                                                                         *)
(* The controller now escalates such a PR once per head, in order:         *)
(*   superseded  the change is already on its base: close it              *)
(*   conflict    conflicting merge state: one conflict worker (opus)       *)
(*   triage      one triage worker (opus): fix, superseded or needs-person *)
(*   needs_person a visible hold naming who and why, posted once           *)
(* A green, armed PR that has not merged an hour after it was first seen   *)
(* armed (armedStall) gets the same treatment. The hold lifts when the     *)
(* head moves; every stage is keyed by the head, so a new head starts      *)
(* again at the node's own ladder.                                         *)
(*                                                                         *)
(* An escalation worker is a lease the controller writes into the node's   *)
(* write-ahead state, so it shares the node's one-lease-per-PR rule, its   *)
(* probes, deadline, kill sequence and release.                            *)
(*                                                                         *)
(* idle[p] counts the controller ticks in a row at which p is open, not    *)
(* held by a person, and has no next action: no lease, no node dispatch    *)
(* or merge it can take, no escalation stage left to take. NoIdle bounds   *)
(* it by K.                                                                *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS
  PRs,          \* PR ids
  MaxHead,      \* heads per PR are 1..MaxHead
  Cap,          \* the node's per-head worker cap (MAX_DISPATCHES_PER_HEAD)
  K,            \* the idle bound, in controller ticks
  Escalate,     \* FALSE: the controller before this change (mutation)
  OnceGuard,    \* FALSE: a stage is not recorded as done (mutation)
  NeedsPerson,  \* FALSE: no needs-person stage after triage (mutation)
  LeaseGuard,   \* FALSE: escalate while a lease is live (mutation)
  StallEscalate \* FALSE: an armed stall is not escalated (mutation)

Stages == {"superseded", "conflict", "triage", "needs_person"}
NoLease == "none"

VARIABLES
  open,        \* the PR is open
  head,        \* its head (1..MaxHead)
  red,         \* CI red at this head (needs a worker)
  conflicting, \* merge state conflicting at this head
  stall,       \* green, armed and not merged for an hour at this head
  sent,        \* node workers sent to this head
  lease,       \* "none", "node" or "esc"
  leases,      \* how many leases the PR holds (OneLease bounds it)
  done,        \* escalation stages taken at this head
  starts,      \* per stage, how many times it was taken at this head
  held,        \* the needs-person hold is in force
  posts,       \* needs-person comments posted at this head
  idle         \* ticks in a row with no next action

vars == <<open, head, red, conflicting, stall, sent, lease, leases, done, starts, held, posts, idle>>

NeedsWorker(p) == red[p] \/ conflicting[p]
\* the node's ladder is spent at this head, or the PR is a stalled armed one
Spent(p) == open[p] /\ ((NeedsWorker(p) /\ sent[p] = Cap) \/ (StallEscalate /\ stall[p]))

\* the next stage, in order; conflict only for a conflicting PR
NextStage(p) ==
  IF "superseded" \notin done[p] THEN "superseded"
  ELSE IF conflicting[p] /\ "conflict" \notin done[p] THEN "conflict"
  ELSE IF "triage" \notin done[p] THEN "triage"
  ELSE IF NeedsPerson /\ "needs_person" \notin done[p] THEN "needs_person"
  ELSE "none"

\* what can still act on p without the escalation
NodeCanAct(p) ==
  \/ lease[p] # NoLease
  \/ NeedsWorker(p) /\ sent[p] < Cap
  \/ ~NeedsWorker(p) /\ ~stall[p]        \* a green PR the node merges

HasNext(p) == ~open[p] \/ held[p] \/ NodeCanAct(p)

ResetHead(p) ==
  /\ sent' = [sent EXCEPT ![p] = 0]
  /\ done' = [done EXCEPT ![p] = {}]
  /\ starts' = [starts EXCEPT ![p] = [s \in Stages |-> 0]]
  /\ held' = [held EXCEPT ![p] = FALSE]
  /\ posts' = [posts EXCEPT ![p] = 0]
  /\ stall' = [stall EXCEPT ![p] = FALSE]

Init ==
  /\ open = [p \in PRs |-> TRUE]
  /\ head = [p \in PRs |-> 1]
  /\ red \in [PRs -> BOOLEAN]
  /\ conflicting \in [PRs -> BOOLEAN]
  /\ stall = [p \in PRs |-> FALSE]
  /\ sent = [p \in PRs |-> 0]
  /\ lease = [p \in PRs |-> NoLease]
  /\ leases = [p \in PRs |-> 0]
  /\ done = [p \in PRs |-> {}]
  /\ starts = [p \in PRs |-> [s \in Stages |-> 0]]
  /\ held = [p \in PRs |-> FALSE]
  /\ posts = [p \in PRs |-> 0]
  /\ idle = [p \in PRs |-> 0]

(* The node: one worker per head step, up to the cap, never beside a lease. *)
NodeDispatch(p) ==
  /\ open[p] /\ NeedsWorker(p) /\ lease[p] = NoLease /\ sent[p] < Cap
  /\ lease' = [lease EXCEPT ![p] = "node"]
  /\ leases' = [leases EXCEPT ![p] = @ + 1]
  /\ sent' = [sent EXCEPT ![p] = @ + 1]
  /\ UNCHANGED <<open, head, red, conflicting, stall, done, starts, held, posts, idle>>

(* The node merges a green, unconflicted PR that is not stalled. *)
Merge(p) ==
  /\ open[p] /\ ~NeedsWorker(p) /\ ~stall[p] /\ lease[p] = NoLease
  /\ open' = [open EXCEPT ![p] = FALSE]
  /\ UNCHANGED <<head, red, conflicting, stall, sent, lease, leases, done, starts, held, posts, idle>>

(* A worker ends: it pushed a fix (a new head), its triage judged the PR    *)
(* superseded and the controller closed it, or it left nothing.           *)
WorkerEnds(p) ==
  /\ lease[p] # NoLease
  /\ lease' = [lease EXCEPT ![p] = NoLease]
  /\ leases' = [leases EXCEPT ![p] = @ - 1]
  /\ \/ /\ head[p] < MaxHead
        /\ head' = [head EXCEPT ![p] = @ + 1]
        /\ red' \in [PRs -> BOOLEAN] /\ \A q \in PRs \ {p} : red'[q] = red[q]
        /\ conflicting' \in [PRs -> BOOLEAN] /\ \A q \in PRs \ {p} : conflicting'[q] = conflicting[q]
        /\ ResetHead(p)
        /\ UNCHANGED <<open, idle>>
     \/ /\ lease[p] = "esc" /\ "triage" \in done[p]
        /\ open' = [open EXCEPT ![p] = FALSE]
        /\ UNCHANGED <<head, red, conflicting, stall, sent, done, starts, held, posts, idle>>
     \/ UNCHANGED <<open, head, red, conflicting, stall, sent, done, starts, held, posts, idle>>

(* A person pushes (the hold lifts with the head), or the PR's armed green *)
(* head stops merging.                                                     *)
Push(p) ==
  /\ open[p] /\ head[p] < MaxHead
  /\ head' = [head EXCEPT ![p] = @ + 1]
  /\ red' \in [PRs -> BOOLEAN] /\ \A q \in PRs \ {p} : red'[q] = red[q]
  /\ conflicting' \in [PRs -> BOOLEAN] /\ \A q \in PRs \ {p} : conflicting'[q] = conflicting[q]
  /\ ResetHead(p)
  /\ UNCHANGED <<open, lease, leases, idle>>

Stall(p) ==
  /\ open[p] /\ ~red[p] /\ ~stall[p] /\ lease[p] = NoLease
  /\ stall' = [stall EXCEPT ![p] = TRUE]
  /\ UNCHANGED <<open, head, red, conflicting, sent, lease, leases, done, starts, held, posts, idle>>

Take(p, s) ==
  /\ done' = [done EXCEPT ![p] = IF OnceGuard THEN @ \cup {s} ELSE @]
  /\ starts' = [starts EXCEPT ![p][s] = @ + 1]

(* One controller tick for p: the escalation step, then the idle count. *)
Tick(p) ==
  LET esc == Escalate /\ Spent(p) /\ ~held[p] /\ (lease[p] = NoLease \/ ~LeaseGuard)
                      /\ NextStage(p) # "none"
      s == NextStage(p)
  IN
  IF esc THEN
    /\ Take(p, s)
    /\ idle' = [idle EXCEPT ![p] = 0]
    /\ CASE s = "superseded" ->
              \* the change is on its base (closed) or it is not (next stage)
              /\ open' \in {[open EXCEPT ![p] = FALSE], open}
              /\ UNCHANGED <<lease, leases, held, posts>>
         [] s \in {"conflict", "triage"} ->
              /\ lease' = [lease EXCEPT ![p] = "esc"]
              /\ leases' = [leases EXCEPT ![p] = @ + 1]
              /\ UNCHANGED <<open, held, posts>>
         [] s = "needs_person" ->
              /\ held' = [held EXCEPT ![p] = TRUE]
              /\ posts' = [posts EXCEPT ![p] = @ + 1]
              /\ UNCHANGED <<open, lease, leases>>
    /\ UNCHANGED <<head, red, conflicting, stall, sent>>
  ELSE
    /\ idle' = [idle EXCEPT ![p] = IF HasNext(p) THEN 0 ELSE IF @ > K THEN @ ELSE @ + 1]
    /\ UNCHANGED <<open, head, red, conflicting, stall, sent, lease, leases, done, starts, held, posts>>

Next == \E p \in PRs :
  NodeDispatch(p) \/ Merge(p) \/ WorkerEnds(p) \/ Push(p) \/ Stall(p) \/ Tick(p)

Spec == Init /\ [][Next]_vars

\* The controller ticks and workers end; nothing else is promised.
LiveSpec == Spec /\ \A p \in PRs : WF_vars(Tick(p)) /\ WF_vars(WorkerEnds(p))
                                   /\ WF_vars(NodeDispatch(p)) /\ WF_vars(Merge(p))

(* ---------------------------------------------------------- properties *)
TypeOK ==
  /\ open \in [PRs -> BOOLEAN] /\ head \in [PRs -> 1..MaxHead]
  /\ lease \in [PRs -> {NoLease, "node", "esc"}]
  /\ done \in [PRs -> SUBSET Stages]

\* AC1/AC3: no open, unheld PR goes more than K ticks with no next action
NoIdle == \A p \in PRs : idle[p] <= K

\* one lease per PR: an escalation worker never runs beside the node's
OneLease == \A p \in PRs : leases[p] <= 1

\* each stage at most once per head, and the needs-person comment once
StageOnce == \A p \in PRs : \A s \in Stages : starts[p][s] <= 1
PostOnce == \A p \in PRs : posts[p] <= 1

\* the order: superseded first, triage before a person is named
Ordered == \A p \in PRs :
  /\ (done[p] \cap {"conflict", "triage", "needs_person"} # {}) => "superseded" \in done[p]
  /\ "needs_person" \in done[p] => "triage" \in done[p]

\* a hold always names a person: it is the needs-person stage, at this head
HeldNamed == \A p \in PRs : held[p] => ("needs_person" \in done[p] /\ posts[p] = 1)

Safety == TypeOK /\ NoIdle /\ OneLease /\ StageOnce /\ PostOnce /\ Ordered /\ HeldNamed

\* every spent, unheld PR ends closed, held for a person, or with a next action
Resolves == \A p \in PRs : (Spent(p) /\ ~held[p]) ~> (~open[p] \/ held[p] \/ ~Spent(p))
=============================================================================
