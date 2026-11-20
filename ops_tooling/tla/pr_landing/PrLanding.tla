------------------------------ MODULE PrLanding ------------------------------
(***************************************************************************)
(* OMN-19823 (epic OMN-19822). A model of the per-PR landing state         *)
(* machine of plan knowledge-base#92 section 5.1, keyed by PR, with:       *)
(*  - PRs on one ticket with batch companion mode on (one companion per    *)
(*    ticket, shared by every PR on it);                                   *)
(*  - two concurrent ingress sources: I1 (the autobind command, a PR-state *)
(*    snapshot on opened / synchronize / ready_for_review / hold change /  *)
(*    reopened) and I2+I3 (pr-merged from Actions and from the mirror, so  *)
(*    every merge arrives twice);                                          *)
(*  - duplicate and reordered delivery: `net` holds every published,      *)
(*    undelivered observation; any one can be delivered next (reordering), *)
(*    and a delivered one can stay for a second delivery while the Dups    *)
(*    budget lasts (duplicates); a delivery the row ignores is consumed;   *)
(*  - the orchestrator's state_io row, written by workers under optimistic *)
(*    concurrency (read, reduce, compare-and-set, else retry), with an     *)
(*    in-row outbox of intents drained by a dispatcher;                    *)
(*  - the per-ticket companion lease held by the producer from its read of *)
(*    the ticket's companion to its write;                                 *)
(*  - the completion-bound timer, delivered as an observation;             *)
(*  - the head-match drop rule.                                            *)
(* The reducer is a pure function of (row, observation). No clock, no LLM. *)
(*                                                                         *)
(* Every design choice the plan leaves open, and every change this model   *)
(* proposes, is a BOOLEAN constant, so a .cfg selects "plan as written" or *)
(* "plan with change F<n>" and TLC shows the difference.                   *)
(*                                                                         *)
(* Extension (lane pr-landing-model-extend-83) for the four findings the  *)
(* first model did not check: G1 closed ingress, G2 the verdict            *)
(* change_control_open, G3 the states the completion bound covers, G4 the  *)
(* armed flag on a new head. Constants ClosedIngress, CcLag, CcOpenRow,    *)
(* BoundStates, StallTimer, TimerTagged, NewHeadArm; properties P7         *)
(* (no silent stall), TermKind, P1m and CcOpenUnreached.                   *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, Sequences, TLC

CONSTANTS PRs, Workers, MaxHead, EnvBudget, Dups, TimerBudget, Nil,
  Atomic,          \* TRUE: a delivery reads, reduces and commits in one step (see Deliver)
  Foreign,         \* TRUE: another PR on the ticket may mint the ticket's companion (one-PR configs)
  Checks,          \* FALSE: head-check reads return nothing (the P3 slice: no derive is issued once cmp = merged)
  HeadDrop,        \* plan 5.1: drop an observation whose head is not row.head_sha (except merged/closed)
  OrderedHead,     \* F1: "pushed (new head)" means newer by the source's per-PR sequence, not merely different
  SeqGuard,        \* F2: a same-head snapshot (and closed) applies only if its source sequence is newer than the row's
  HoldAnyState,    \* F3: draft or hold at the row's head parks the row from any waiting state and disarms in NEEDS_AGENT
  CompInflight,    \* F4: a companion command in flight is recorded on the row; no second one is issued
  CompOutcomeExempt, \* F5: a companion outcome is correlated with the command in flight (row.ch), not with
                   \*     head_sha; companion-merged is a ticket fact accepted in COMPANION_PENDING too
  RunAttempt,      \* F7: verdicts carry each check's run attempt; one older than the attempt a re-run started is
                   \*     pending (read again), not a second failure; companion-merged reads before it re-runs
  OutboxSupersede, \* F6: a disarm written to the outbox removes an unsent arm (and an arm an unsent disarm)
  OCC,             \* state_io compare-and-set on the row
  Lease,           \* per-ticket companion lease in the producer
  AtLeastOnce,     \* the dispatcher may perform an effect and crash before removing the intent (one crash)
  EffectIdem,      \* effects and event consumers dedupe on the intent key
  Timers,          \* the completion bound can expire
  Reopen,          \* a closed PR can be reopened (plan: CLOSED leaves on reopened)
  Declines,        \* the companion producer can DECLINE
  ClosedIngress,   \* G1: "none" (plan: no source publishes closed-unmerged), "flag" (I1 fires on closed and a
                   \*     closed event carrying merged=true is read as merged), "noflag" (every closed read as closed)
  CcLag,           \* G2: the classifier's companion fact may lag GitHub once per PR (read from the mirror)
  CcOpenRow,       \* G2: the CHECKS_PENDING row for verdict change_control_open: "none" (no row: dropped),
                   \*     "pending" (read again after the poll interval), "companion_open" (back to COMPANION_OPEN)
  BoundStates,     \* G3: the states the completion bound covers
  StallTimer,      \* G3: the bound expires only when the row has nothing in flight (a bound longer than any round trip)
  TimerTagged,     \* G3: the expiry names the state it was set for and is dropped once the row has left it
  NewHeadArm,      \* G4: on a new head the row "keep"s armed as GitHub has it, "forget"s it, or "disarm"s
  ReopenEval,      \* G5: a reopened snapshot, newer by the ordering key, re-evaluates the row from any
                   \*     non-terminal state (its closed was reordered after it and dropped)
  ClosedCompanion, \* G5: a CLOSED row still applies companion outcomes and companion merged to its
                   \*     companion fields, staying CLOSED, so a reopen evaluates the companion as it is
  ClosedNewer,     \* G5: in CLOSED, any snapshot newer than the row reopens it (I1 publishes snapshots only
                   \*     for an open PR), not only the one marked reopened
  ClosedSeq,       \* G5: in CLOSED, a newer closed advances the row's ordering key, with no second terminal
  ClosedMerged     \* G5: in CLOSED, a merged (possible only after a reopen) moves the row to MERGED in a new
                   \*     episode, with its own terminal

Terminal == {"MERGED", "CLOSED"}
Waiting  == {"COMPANION_PENDING", "COMPANION_OPEN", "CHECKS_PENDING", "READY"}
States   == {"OBSERVED", "PARKED", "COMPANION_PENDING", "COMPANION_OPEN", "CHECKS_PENDING",
             "READY", "ARMED", "NEEDS_AGENT", "MERGED", "CLOSED"}
IntentKinds == {"arm", "disarm", "rerun", "read", "derive", "terminal", "agent"}

VARIABLES
  gh,        \* GitHub truth per PR
  bud,       \* budgets: env (ingress observations left per PR), dup (duplicate deliveries left),
             \* crash (dispatcher crashes left), tm (bound expiries left per PR), fm (foreign mints left)
  net,       \* published observations not yet delivered
  row,       \* the state_io row per PR
  wk,        \* each worker's in-progress read: [p, o, r] or Nil
  comps,     \* number of open companion PRs for the ticket
  cmerged,   \* the ticket's companion has merged
  pq,        \* producer: companion commands received per PR (sequence of heads)
  pst,       \* producer: what it read for the command it is working on (Nil when idle)
  lease,     \* per-ticket lease holder (Nil when free)
  latest,    \* ghost: per PR, the newest (by source sequence) snapshot the orchestrator consumed
  keys,      \* ghost: effect keys performed: rerun <<p,h,check>>, agent <<p,h,reason>>, term <<p,ep,kind>>
  bad        \* ghost: property flags raised at the step that breaks them

vars == <<gh, bud, net, row, wk, comps, cmerged, pq, pst, lease, latest, keys, bad>>

\* an observation. k: snap | merged | closed | verdict | armed | cout | cmerged | timer
Obs(p, k, h, s, d, hd, re, v) ==
  [p |-> p, k |-> k, h |-> h, s |-> s, d |-> d, hd |-> hd, re |-> re, v |-> v, a |-> <<0, 0>>]

GH0(d) == [head |-> 1, s |-> 1, d |-> d, hd |-> FALSE, merged |-> FALSE, closed |-> FALSE,
           armed |-> FALSE, pc |-> "pending", cc |-> "pending", pa |-> 0, ca |-> 0, ah |-> 0]
           \* ah (ghost): the head the workflow's last arm was issued for; GitHub keeps the arm across a push

Row0 == [st |-> "OBSERVED", h |-> 0, sq |-> 0, d |-> FALSE, hd |-> FALSE, ep |-> 0,
         cmp |-> "none", ch |-> 0, armed |-> FALSE, rr |-> {}, ag |-> {}, ob |-> {}, ex |-> <<0, 0>>]

Bad0 == [p1 |-> FALSE, rerunFailed |-> FALSE, dupRerun |-> FALSE, dupAgent |-> FALSE,
         twoTerms |-> FALSE, twoTermsEp |-> FALSE, ungated |-> FALSE]

Init ==
  /\ \E ds \in [PRs -> BOOLEAN] :
       /\ gh = [p \in PRs |-> GH0(ds[p])]
       /\ net = {Obs(p, "snap", 1, 1, ds[p], FALSE, FALSE, "") : p \in PRs}
  /\ bud = [env |-> [p \in PRs |-> EnvBudget], dup |-> Dups, crash |-> IF AtLeastOnce THEN 1 ELSE 0,
            tm |-> [p \in PRs |-> TimerBudget], fm |-> IF Foreign THEN 1 ELSE 0,
            lag |-> [p \in PRs |-> IF CcLag THEN 1 ELSE 0]]
  /\ row = [p \in PRs |-> Row0]
  /\ wk = [w \in Workers |-> Nil]
  /\ comps = 0 /\ cmerged = FALSE
  /\ pq = [p \in PRs |-> <<>>] /\ pst = [p \in PRs |-> Nil] /\ lease = Nil
  /\ latest = [p \in PRs |-> [h |-> 0, s |-> 0, d |-> FALSE, hd |-> FALSE]]
  /\ keys = [rerun |-> {}, agent |-> {}, term |-> {}]
  /\ bad = Bad0

-----------------------------------------------------------------------------
(* GitHub and the ingress publishers. The workflow never runs these.       *)
Live(p) == ~gh[p].merged /\ ~gh[p].closed
Spend(p) == bud.env[p] > 0 /\ bud' = [bud EXCEPT !.env[p] = @ - 1]
SnapOf(p, g, re) == Obs(p, "snap", g.head, g.s, g.d, g.hd, re, "")

EnvUnch == UNCHANGED <<row, wk, comps, cmerged, pq, pst, lease, latest, keys, bad>>

Push(p) ==     \* I1 synchronize: a new head, draft or not; checks restart; auto-merge stays as it was
  /\ Live(p) /\ gh[p].head < MaxHead /\ Spend(p)
  /\ \E d \in BOOLEAN :
       LET g == [gh[p] EXCEPT !.head = @ + 1, !.s = @ + 1, !.d = d, !.pc = "pending", !.cc = "pending",
                              !.pa = 0, !.ca = 0]
       IN gh' = [gh EXCEPT ![p] = g] /\ net' = net \cup {SnapOf(p, g, FALSE)}
  /\ EnvUnch

ReadyFlip(p) == \* I1 ready_for_review, or converted back to draft, at the same head
  /\ Live(p) /\ Spend(p)
  /\ LET g == [gh[p] EXCEPT !.d = ~@, !.s = @ + 1]
     IN gh' = [gh EXCEPT ![p] = g] /\ net' = net \cup {SnapOf(p, g, FALSE)}
  /\ EnvUnch

ToggleHold(p) == \* a hold label or hold marker applied or lifted at the same head
  /\ Live(p) /\ Spend(p)
  /\ LET g == [gh[p] EXCEPT !.hd = ~@, !.s = @ + 1]
     IN gh' = [gh EXCEPT ![p] = g] /\ net' = net \cup {SnapOf(p, g, FALSE)}
  /\ EnvUnch

Close(p) ==
  /\ Live(p) /\ Spend(p)
  /\ gh' = [gh EXCEPT ![p].closed = TRUE, ![p].armed = FALSE, ![p].s = @ + 1]
  /\ net' = IF ClosedIngress = "none" THEN net        \* G1: no source publishes closed-unmerged
           ELSE net \cup {Obs(p, "closed", gh[p].head, gh[p].s + 1, FALSE, FALSE, FALSE, "")}
  /\ EnvUnch

ReopenPR(p) ==
  /\ Reopen /\ gh[p].closed /\ ~gh[p].merged /\ Spend(p)
  /\ LET g == [gh[p] EXCEPT !.closed = FALSE, !.s = @ + 1]
     IN gh' = [gh EXCEPT ![p] = g] /\ net' = net \cup {SnapOf(p, g, TRUE)}
  /\ EnvUnch

PcDone(p) ==   \* the product check finishes on the current head (a read may also find it finished)
  /\ Checks /\ Live(p) /\ gh[p].pc = "pending"
  /\ \E v \in {"green", "failed", "timed_out"} : gh' = [gh EXCEPT ![p].pc = v]
  /\ UNCHANGED <<bud, net>> /\ EnvUnch

CcDone(p) ==   \* the change-control check passes only if the ticket's companion has merged when it runs
  /\ Checks /\ Live(p) /\ gh[p].cc = "pending"
  /\ gh' = [gh EXCEPT ![p].cc = IF cmerged THEN "green" ELSE "red"]
  /\ UNCHANGED <<bud, net>> /\ EnvUnch

GhMerge(p) ==  \* GitHub merges an armed, non-draft PR whose required checks are green (P5)
  /\ Live(p) /\ gh[p].armed /\ ~gh[p].d /\ gh[p].pc = "green" /\ gh[p].cc = "green"
  /\ gh' = [gh EXCEPT ![p].merged = TRUE, ![p].s = @ + 1]
  /\ net' = net \cup {Obs(p, "merged", gh[p].head, 0, FALSE, FALSE, FALSE, "I2"),
                      Obs(p, "merged", gh[p].head, 0, FALSE, FALSE, FALSE, "I3")}
                 \cup (CASE ClosedIngress = "flag"   -> {Obs(p, "merged", gh[p].head, 0, FALSE, FALSE, FALSE, "I1")}
                         [] ClosedIngress = "noflag" -> {Obs(p, "closed", gh[p].head, gh[p].s + 1, FALSE, FALSE, FALSE, "")}
                         [] OTHER -> {})
  /\ UNCHANGED <<bud, row, wk, comps, cmerged, pq, pst, lease, latest, keys>>
  /\ bad' = [bad EXCEPT !.ungated = @ \/ gh[p].head # gh[p].ah]   \* P1m: merged a head no arm was issued for

CompMerge ==   \* the ticket's companion merges; I3 (the mirror) reports it to every PR on the ticket
  /\ comps > 0
  /\ comps' = comps - 1 /\ cmerged' = TRUE
  /\ net' = net \cup {Obs(p, "cmerged", 0, 0, FALSE, FALSE, FALSE, "") : p \in PRs}
  /\ UNCHANGED <<gh, bud, row, wk, pq, pst, lease, latest, keys, bad>>

ForeignMint == \* one-PR configs: another PR on the ticket mints the companion (holding the lease)
  /\ bud.fm > 0 /\ comps = 0 /\ ~cmerged /\ (Lease => lease = Nil)
  /\ bud' = [bud EXCEPT !.fm = 0] /\ comps' = 1
  /\ UNCHANGED <<gh, net, row, wk, cmerged, pq, pst, lease, latest, keys, bad>>

-----------------------------------------------------------------------------
(* The pure reducer: (row, observation) -> [r: row', i: intents, drop].   *)
In(k, h, x) == [k |-> k, h |-> h, x |-> x]
Res(r, i) == [r |-> r, i |-> i, drop |-> FALSE]
Drop(r) == [r |-> r, i |-> {}, drop |-> TRUE]

\* agent-needed, at most once per (head, reason): the row remembers what it emitted
ToAgent(r, reason) ==
  IF <<r.h, reason>> \in r.ag THEN Res([r EXCEPT !.st = "NEEDS_AGENT"], {})
  ELSE Res([r EXCEPT !.st = "NEEDS_AGENT", !.ag = @ \cup {<<r.h, reason>>}], {In("agent", r.h, reason)})

Disarm(r) == IF r.armed THEN {In("disarm", r.h, "")} ELSE {}

\* OBSERVED evaluates at once (plan: "the reducer evaluates at once")
Eval(r) ==
  IF r.d \/ r.hd
  THEN Res([r EXCEPT !.st = "PARKED", !.armed = FALSE], Disarm(r))
  ELSE CASE r.cmp \in {"none", "declined"} ->
              Res([r EXCEPT !.st = "COMPANION_PENDING", !.cmp = IF CompInflight THEN "pending" ELSE "none",
                            !.ch = r.h],
                  {In("derive", r.h, "")})
         [] r.cmp = "pending" -> Res([r EXCEPT !.st = "COMPANION_PENDING"], {})
         [] r.cmp = "open"    -> Res([r EXCEPT !.st = "COMPANION_OPEN"], {})
         [] r.cmp = "merged"  -> Res([r EXCEPT !.st = "CHECKS_PENDING"], {In("read", r.h, "")})

HeadOK(r, o) == ~HeadDrop \/ o.h = r.h
IsNewHead(r, o) == IF OrderedHead THEN o.s > r.sq /\ o.h # r.h ELSE o.h # r.h

Snap(r, o) ==
  IF r.st = "CLOSED" THEN
       IF (o.re \/ ClosedNewer) /\ (~SeqGuard \/ o.s > r.sq)
       THEN Eval([r EXCEPT !.st = "OBSERVED", !.h = o.h, !.sq = o.s, !.d = o.d, !.hd = o.hd, !.ep = @ + 1])
       ELSE Drop(r)
  ELSE IF IsNewHead(r, o) THEN
       LET e == Eval([r EXCEPT !.st = "OBSERVED", !.h = o.h, !.sq = o.s, !.d = o.d, !.hd = o.hd, !.ex = <<0, 0>>,
                               !.armed = IF NewHeadArm = "keep" THEN @ ELSE FALSE])
       IN IF NewHeadArm = "disarm" THEN Res(e.r, e.i \cup Disarm(r)) ELSE e
  ELSE IF ~HeadOK(r, o) THEN Drop(r)
  ELSE IF SeqGuard /\ o.s <= r.sq THEN Drop(r)
  ELSE IF ReopenEval /\ o.re THEN Eval([r EXCEPT !.st = "OBSERVED", !.sq = o.s, !.d = o.d, !.hd = o.hd])
  ELSE LET r1 == [r EXCEPT !.sq = o.s, !.d = o.d, !.hd = o.hd]
           stop == o.d \/ o.hd
       IN CASE r.st = "PARKED" /\ ~stop -> Eval(r1)
            [] r.st = "ARMED" /\ stop -> Res([r1 EXCEPT !.st = "PARKED", !.armed = FALSE], Disarm(r1))
            [] HoldAnyState /\ r.st \in Waiting /\ stop ->
                 Res([r1 EXCEPT !.st = "PARKED", !.armed = FALSE], Disarm(r1))
            [] HoldAnyState /\ r.st = "NEEDS_AGENT" /\ stop ->
                 Res([r1 EXCEPT !.armed = FALSE], Disarm(r1))
            [] OTHER -> Res(r1, {})

Verdict(r, o) ==
  IF r.st # "CHECKS_PENDING" \/ ~HeadOK(r, o) THEN Drop(r)
  ELSE IF RunAttempt /\ (o.a[1] < r.ex[1] \/ o.a[2] < r.ex[2])
  THEN Res(r, {In("read", r.h, "")})          \* a result from before the re-run: still pending, poll again
  ELSE CASE o.v = "green" ->
              IF r.d \/ r.hd                           \* the arm gate WITHHOLDs
              THEN IF HoldAnyState THEN Res([r EXCEPT !.st = "PARKED"], {})
                   ELSE Res([r EXCEPT !.st = "READY"], {})
              ELSE Res([r EXCEPT !.st = "READY", !.armed = TRUE], {In("arm", r.h, o.h)})
         [] o.v = "product_failed" -> ToAgent(r, "real_red")
         [] o.v = "cc_open" ->                      \* G2: T3's change_control_open
              CASE CcOpenRow = "pending"        -> Res(r, {In("read", r.h, "")})
                [] CcOpenRow = "companion_open" -> Res([r EXCEPT !.st = "COMPANION_OPEN", !.cmp = "open"], {})
                [] OTHER                        -> Drop(r)
         [] o.v \in {"timed_out", "cc_stale"} ->
              LET c == IF o.v = "timed_out" THEN "pc" ELSE "cc"
                  j == IF c = "pc" THEN 1 ELSE 2
              IN IF <<r.h, c>> \notin r.rr
                 THEN Res([r EXCEPT !.rr = @ \cup {<<r.h, c>>}, !.ex[j] = o.a[j] + 1],
                          {In("rerun", r.h, c), In("read", r.h, "")})
                 ELSE ToAgent(r, "budget")

Reduce(r, o) ==
  IF o.k = "merged" THEN
       IF ClosedMerged /\ r.st = "CLOSED"
       THEN Res([r EXCEPT !.st = "MERGED", !.ep = @ + 1], {In("terminal", r.ep + 1, "merged")})
       ELSE IF r.st \in Terminal THEN Drop(r)
       ELSE Res([r EXCEPT !.st = "MERGED"], {In("terminal", r.ep, "merged")})
  ELSE IF o.k = "closed" THEN
       IF ClosedSeq /\ r.st = "CLOSED" /\ o.s > r.sq THEN Res([r EXCEPT !.sq = o.s], {})
       ELSE IF r.st \in Terminal \/ (SeqGuard /\ o.s <= r.sq) THEN Drop(r)
       ELSE Res([r EXCEPT !.st = "CLOSED", !.sq = o.s], {In("terminal", r.ep, "closed")})
  ELSE IF r.st \in Terminal /\ ~(o.k = "snap" /\ r.st = "CLOSED")
          /\ ~(ClosedCompanion /\ r.st = "CLOSED" /\ o.k \in {"cout", "cmerged"}) THEN Drop(r)
  ELSE
  CASE o.k = "snap"    -> Snap(r, o)
    [] o.k = "verdict" -> Verdict(r, o)
    [] o.k = "armed"   -> IF r.st = "READY" /\ HeadOK(r, o) THEN Res([r EXCEPT !.st = "ARMED"], {}) ELSE Drop(r)
    [] o.k = "cout" ->   \* companion outcome for a derive issued at head o.h
         IF ~CompOutcomeExempt /\ ~HeadOK(r, o) THEN Drop(r)
         ELSE IF CompOutcomeExempt /\ r.cmp = "pending" /\ o.h # r.ch THEN Drop(r) \* not the command in flight
         ELSE IF r.cmp \in {"open", "merged"} THEN Drop(r)
         ELSE IF o.v = "MINTED"
              THEN Res([r EXCEPT !.cmp = "open",
                                 !.st = IF r.st = "COMPANION_PENDING" THEN "COMPANION_OPEN" ELSE r.st], {})
              ELSE IF r.st = "COMPANION_PENDING"
                   THEN ToAgent([r EXCEPT !.cmp = "declined"], "companion_declined")
                   ELSE Res([r EXCEPT !.cmp = "declined"], {})
    [] o.k = "cmerged" ->  \* ticket-scoped: the companion merged
         IF r.cmp = "merged" THEN Drop(r)
         ELSE IF r.st = "COMPANION_OPEN" \/ (CompOutcomeExempt /\ r.st = "COMPANION_PENDING")
              THEN IF RunAttempt THEN Res([r EXCEPT !.cmp = "merged", !.st = "CHECKS_PENDING"], {In("read", r.h, "")})
                   ELSE IF <<r.h, "cc">> \notin r.rr
                   THEN Res([r EXCEPT !.cmp = "merged", !.st = "CHECKS_PENDING", !.rr = @ \cup {<<r.h, "cc">>}],
                            {In("rerun", r.h, "cc"), In("read", r.h, "")})
                   ELSE Res([r EXCEPT !.cmp = "merged", !.st = "CHECKS_PENDING"], {In("read", r.h, "")})
              ELSE Res([r EXCEPT !.cmp = "merged"], {})
    [] o.k = "timer" ->
         IF ~HeadOK(r, o) \/ (TimerTagged /\ r.st # o.v) THEN Drop(r) ELSE ToAgent(r, "stalled")

-----------------------------------------------------------------------------
(* Orchestrator workers.                                                    *)
AddIntents(r, I) ==
  LET ob0 == IF OutboxSupersede /\ (\E i \in I : i.k = "disarm") THEN {j \in r.ob : j.k # "arm"}
             ELSE IF OutboxSupersede /\ (\E i \in I : i.k = "arm") THEN {j \in r.ob : j.k # "disarm"}
             ELSE r.ob
  IN [r EXCEPT !.ob = ob0 \cup I]

After(r, o) == LET res == Reduce(r, o) IN AddIntents(res.r, res.i)

Consume(L, o) ==
  IF o.k = "snap" /\ o.s > L[o.p].s
  THEN [L EXCEPT ![o.p] = [h |-> o.h, s |-> o.s, d |-> o.d, hd |-> o.hd]] ELSE L

\* P1 is judged at the step that issues an arm: the arm must be for the newest head the
\* orchestrator has consumed, whose newest facts are not draft and not held, and it must be
\* triggered by a green verdict observed for that same head.
ArmBad(p, res, L) ==
  \E i \in res.i : i.k = "arm" /\ ~(i.h = L[p].h /\ ~L[p].d /\ ~L[p].hd /\ i.x = i.h)

\* commit the reduction of observation o against row value r (the value the worker read)
CommitOf(o, r, L) ==
  LET res == Reduce(r, o)
  IN /\ row' = [row EXCEPT ![o.p] = AddIntents(res.r, res.i)]
     /\ latest' = L
     /\ bad' = [bad EXCEPT !.p1 = @ \/ ArmBad(o.p, res, L)]

\* on success the observation may stay for one more delivery while the duplicate budget lasts
MaybeDup(o, netAfter) ==
  \E again \in (IF bud.dup > 0 THEN BOOLEAN ELSE {FALSE}) :
    /\ net' = IF again THEN netAfter \cup {o} ELSE netAfter
    /\ bud' = IF again THEN [bud EXCEPT !.dup = @ - 1] ELSE bud

WUnch == UNCHANGED <<gh, comps, cmerged, pq, pst, lease, keys>>

\* Atomic = TRUE: read, reduce and compare-and-set in one step. Under OCC this is exact: a
\* successful compare-and-set commits Reduce(current row, o) and a failed one changes nothing
\* but the observation's return to `net`, so the reachable row, outbox and ghost states are the
\* same as with concurrent workers. No committed config sets Atomic = FALSE, so a failed compare-and-set is not exercised (OMN-25793, R4).
Deliver ==
  /\ Atomic
  /\ \E o \in net :
       /\ After(row[o.p], o) # row[o.p]
       /\ CommitOf(o, row[o.p], Consume(latest, o))
       /\ MaybeDup(o, net \ {o})
  /\ UNCHANGED wk /\ WUnch

WRead(w) ==    \* a worker takes one undelivered observation (any one: reordering) and reads the row
  /\ ~Atomic /\ wk[w] = Nil
  /\ \E o \in net :
       /\ After(row[o.p], o) # row[o.p]
       /\ wk' = [wk EXCEPT ![w] = [p |-> o.p, o |-> o, r |-> row[o.p]]]
       /\ net' = net \ {o}
  /\ UNCHANGED <<bud, row, latest, bad>> /\ WUnch

WCommit(w) ==  \* compare-and-set; on a conflict the observation goes back (retry)
  /\ wk[w] # Nil
  /\ wk' = [wk EXCEPT ![w] = Nil]
  /\ LET x == wk[w] IN
     IF OCC /\ row[x.p] # x.r
     THEN net' = net \cup {x.o} /\ UNCHANGED <<bud, row, latest, bad>>
     ELSE CommitOf(x.o, x.r, Consume(latest, x.o)) /\ MaybeDup(x.o, net)
  /\ WUnch

Ignore ==      \* a delivery the current row ignores (a drop, a stale or duplicate observation)
  /\ \E o \in net : After(row[o.p], o) = row[o.p] /\ net' = net \ {o}
  /\ UNCHANGED <<bud, row, wk, latest, bad>> /\ WUnch

-----------------------------------------------------------------------------
(* Outbox dispatcher and effects, one effect at a time per PR. There is no *)
(* merge effect (P5). A read returns the head's check results; a check     *)
(* still running when polled is taken to finish at that moment (PcDone and *)
(* CcDone let checks finish earlier, on GitHub's own schedule).             *)
\* T3: a red change-control check is change_control_open while the companion is open (or while the
\* classifier's companion fact lags, G2), change_control_stale once it has merged
Classify(g, lag) == IF g.pc = "failed" THEN "product_failed"
               ELSE IF g.pc = "timed_out" THEN "timed_out"
               ELSE IF g.cc = "red" THEN (IF ~cmerged \/ lag THEN "cc_open" ELSE "cc_stale") ELSE "green"

Dispatch(p) ==
  \E i \in row[p].ob :
  \E crash \in (IF bud.crash > 0 THEN BOOLEAN ELSE {FALSE}) :
  \E lag \in (IF bud.lag[p] > 0 /\ i.k = "read" THEN BOOLEAN ELSE {FALSE}) :
    LET here == Live(p) /\ gh[p].head = i.h
        rk == <<p, i.h, i.x>>
        doR == i.k = "rerun" /\ here /\ ~(EffectIdem /\ rk \in keys.rerun)
        doA == i.k = "agent" /\ ~(EffectIdem /\ rk \in keys.agent)
        doT == i.k = "terminal" /\ ~(EffectIdem /\ \E t \in keys.term : t[1] = p /\ t[2] = i.h)
    IN
    /\ bud' = [bud EXCEPT !.crash = IF crash THEN @ - 1 ELSE @, !.lag[p] = IF lag THEN @ - 1 ELSE @]
    /\ row' = IF crash THEN row ELSE [row EXCEPT ![p].ob = @ \ {i}]
    /\ CASE i.k = "arm" ->
              IF here                                  \* arm carries expectedHeadOid
              THEN /\ gh' = [gh EXCEPT ![p].armed = TRUE, ![p].ah = i.h]
                   /\ net' = net \cup {Obs(p, "armed", i.h, 0, FALSE, FALSE, FALSE, "")}
              ELSE UNCHANGED <<gh, net>>
         [] i.k = "disarm" -> gh' = [gh EXCEPT ![p].armed = FALSE] /\ UNCHANGED net
         [] i.k = "rerun" ->
              /\ gh' = IF doR /\ gh[p][i.x] \in {"red", "timed_out", "failed"}
                       THEN [gh EXCEPT ![p][i.x] = "pending",
                                       ![p][IF i.x = "pc" THEN "pa" ELSE "ca"] = @ + 1] ELSE gh
              /\ UNCHANGED net
         [] i.k = "read" ->
              IF ~here \/ ~Checks THEN UNCHANGED <<gh, net>>
              ELSE \E pc \in (IF gh[p].pc = "pending" THEN {"green", "failed", "timed_out"} ELSE {gh[p].pc}) :
                   LET g == [gh[p] EXCEPT !.pc = pc,
                                          !.cc = IF @ = "pending" THEN (IF cmerged THEN "green" ELSE "red") ELSE @]
                   IN /\ gh' = [gh EXCEPT ![p] = g]
                      /\ net' = net \cup {[Obs(p, "verdict", i.h, 0, FALSE, FALSE, FALSE, Classify(g, lag))
                                             EXCEPT !.a = <<g.pa, g.ca>>]}
         [] OTHER -> UNCHANGED <<gh, net>>
    /\ pq' = IF i.k = "derive" THEN [pq EXCEPT ![p] = Append(@, i.h)] ELSE pq
    /\ keys' = [keys EXCEPT !.rerun = IF doR THEN @ \cup {rk} ELSE @,
                            !.agent = IF doA THEN @ \cup {rk} ELSE @,
                            !.term  = IF doT THEN @ \cup {rk} ELSE @]
    /\ bad' = [bad EXCEPT
                 !.rerunFailed = @ \/ (doR /\ gh[p][i.x] = "failed"),
                 !.dupRerun    = @ \/ (doR /\ rk \in keys.rerun),
                 !.dupAgent    = @ \/ (doA /\ rk \in keys.agent),
                 !.twoTerms    = @ \/ (doT /\ \E t \in keys.term : t[1] = p),
                 !.twoTermsEp  = @ \/ (doT /\ \E t \in keys.term : t[1] = p /\ (t[2] = i.h \/ (t[3] = "merged" /\ i.x = "merged")))]
    /\ UNCHANGED <<wk, comps, cmerged, pst, lease, latest>>

\* the companion producer, open-or-sync; with Lease the ticket lease spans its read and write
ProdRead(p) ==
  /\ Len(pq[p]) > 0 /\ pst[p] = Nil
  /\ Lease => lease \in {Nil, p}
  /\ pst' = [pst EXCEPT ![p] = IF comps > 0 THEN "open" ELSE IF cmerged THEN "merged" ELSE "none"]
  /\ lease' = IF Lease THEN p ELSE lease
  /\ UNCHANGED <<gh, bud, net, row, wk, comps, cmerged, pq, latest, keys, bad>>

ProdWrite(p) ==
  /\ pst[p] # Nil
  /\ \E v \in (IF Declines /\ pst[p] = "none" THEN {"MINTED", "DECLINED"} ELSE {"MINTED"}) :
       /\ IF pst[p] = "none" /\ v = "MINTED" THEN comps' = comps + 1 ELSE UNCHANGED comps
       /\ net' = net \cup {Obs(p, "cout", Head(pq[p]), 0, FALSE, FALSE, FALSE, v)}
  /\ pq' = [pq EXCEPT ![p] = Tail(@)] /\ pst' = [pst EXCEPT ![p] = Nil]
  /\ lease' = IF Lease THEN Nil ELSE lease
  /\ UNCHANGED <<gh, bud, row, wk, cmerged, latest, keys, bad>>

\* G3: nothing for this PR is in flight: no outbox entry, no undelivered observation, no producer
\* command, no worker holding it, and no GitHub check still running or merge GitHub can still make
Pending(p) == \/ row[p].ob # {}
              \/ \E o \in net : o.p = p
              \/ Len(pq[p]) > 0 \/ pst[p] # Nil
              \/ \E w \in Workers : wk[w] # Nil /\ wk[w].p = p
Mergeable(p) == Live(p) /\ gh[p].armed /\ ~gh[p].d /\ gh[p].pc = "green" /\ gh[p].cc = "green"
ChecksRunning(p) == Checks /\ Live(p) /\ (gh[p].pc = "pending" \/ gh[p].cc = "pending")
Stalled(p) == ~Pending(p) /\ ~Mergeable(p) /\ ~ChecksRunning(p) /\ ~(row[p].st = "COMPANION_OPEN" /\ comps > 0)

\* the completion bound of the row's current state expires
Timer(p) ==
  /\ Timers /\ row[p].st \in BoundStates /\ bud.tm[p] > 0
  /\ StallTimer => Stalled(p)
  /\ bud' = [bud EXCEPT !.tm[p] = @ - 1]
  /\ net' = net \cup {Obs(p, "timer", row[p].h, 0, FALSE, FALSE, FALSE, row[p].st)}
  /\ UNCHANGED <<gh, row, wk, comps, cmerged, pq, pst, lease, latest, keys, bad>>

Env(p) == Push(p) \/ ReadyFlip(p) \/ ToggleHold(p) \/ Close(p) \/ ReopenPR(p) \/ GhMerge(p)
          \/ PcDone(p) \/ CcDone(p)
Wf(p)  == Dispatch(p) \/ ProdRead(p) \/ ProdWrite(p) \/ Timer(p)

Next ==
  \/ \E p \in PRs : Env(p) \/ Wf(p)
  \/ CompMerge \/ ForeignMint \/ Ignore \/ Deliver
  \/ \E w \in Workers : WRead(w) \/ WCommit(w)

Spec == Init /\ [][Next]_vars

\* fairness for P6: the workflow, the producer and GitHub's checks keep running
Fair == /\ \A w \in Workers : WF_vars(WRead(w)) /\ WF_vars(WCommit(w))
        /\ WF_vars(Deliver) /\ WF_vars(Ignore)
        /\ \A p \in PRs : WF_vars(Dispatch(p)) /\ WF_vars(ProdRead(p)) /\ WF_vars(ProdWrite(p))
                          /\ WF_vars(PcDone(p)) /\ WF_vars(CcDone(p))
LiveSpec == Spec /\ Fair

-----------------------------------------------------------------------------
(* Properties of plan section 5.2                                          *)
TypeOK == \A p \in PRs : row[p].st \in States /\ (row[p].st # "OBSERVED" \/ row[p].h = 0)

\* P1: never arm at a head that is not the newest observed, or is draft or held there, or
\* whose green verdict was not observed (flag raised by ArmBad at the arming step)
P1 == ~bad.p1

\* P1 corollary: once a PR's row has settled, GitHub is not left armed on a head the
\* orchestrator knows to be draft or held
Settled(p) == row[p].ob = {} /\ \A w \in Workers : wk[w] = Nil \/ wk[w].p # p
P1arm == \A p \in PRs :
  (Live(p) /\ gh[p].armed /\ Settled(p) /\ latest[p].h = gh[p].head) => ~(latest[p].d \/ latest[p].hd)

\* P2: never re-run a check the classifier calls product_failed; at most one re-run per (head, check)
P2 == ~bad.rerunFailed /\ ~bad.dupRerun

\* P3: at most one companion command in flight per PR; at most one open companion per ticket. Every committed config sets AtLeastOnce = FALSE, so P3 is proven for exactly-once dispatch only: with AtLeastOnce = TRUE a derive dispatched with a crash is appended to pq while its intent stays in the outbox, InFlight is 2 and P3 is violated (OMN-25793, R4).
InFlight(p) == Len(pq[p]) + Cardinality({i \in row[p].ob : i.k = "derive"})
P3 == (\A p \in PRs : InFlight(p) <= 1) /\ comps <= 1

\* P4: exactly one terminal per PR (never two; a terminal row has emitted or queued one),
\* and at most one agent-needed per (head, reason)
P4 == /\ ~bad.twoTerms /\ ~bad.dupAgent
      /\ \A p \in PRs : row[p].st \in Terminal =>
            (\E t \in keys.term : t[1] = p) \/ (\E i \in row[p].ob : i.k = "terminal")
\* P4 restated per open episode (the change proposed for CLOSED -> reopened): at most one
\* terminal per (PR, episode), and never two merged terminals
P4ep == ~bad.twoTermsEp /\ ~bad.dupAgent

\* P5: the workflow never merges: its intents are only these kinds, none of which merges;
\* GhMerge (GitHub, on an arm and green checks) is the only action that sets merged
P5 == \A p \in PRs : \A i \in row[p].ob : i.k \in IntentKinds

\* P6 liveness: a PR that stays open, ready, not held and green ends armed or merged
Quiet(p) == Live(p) /\ ~gh[p].d /\ ~gh[p].hd /\ gh[p].pc = "green" /\ gh[p].cc = "green"
P6 == \A p \in PRs : (<>[]Quiet(p)) => <>(row[p].st \in {"ARMED", "MERGED"} \/ gh[p].merged)

\* P7 (G1, G2): no silent stall. A row in a state the workflow owns always has something in
\* flight that will move it: an outbox entry, an undelivered observation, a producer command, or
\* (COMPANION_OPEN) an open companion that can merge. With Checks = FALSE a read returns nothing,
\* so the check-owned states are left out there.
Stuck(p) == /\ row[p].st \in Waiting /\ ~Pending(p)
            /\ ~(row[p].st = "COMPANION_OPEN" /\ comps > 0)
            /\ (Checks \/ row[p].st \in {"COMPANION_PENDING", "COMPANION_OPEN"})
P7 == \A p \in PRs : ~Stuck(p)

\* G1: the terminal matches GitHub: a PR GitHub merged never rests in CLOSED (no reopen)
TermKind == Reopen \/ \A p \in PRs : gh[p].merged => row[p].st # "CLOSED"

\* G4: GitHub merges only a head the workflow armed (the arm gate judged that head)
P1m == ~bad.ungated

\* G2 reachability: a change_control_open verdict for the row's head reaches a CHECKS_PENDING row
CcOpenUnreached == ~\E o \in net : o.k = "verdict" /\ o.v = "cc_open" /\ row[o.p].st = "CHECKS_PENDING"
                                      /\ o.h = row[o.p].h

Sym == Permutations(PRs) \cup Permutations(Workers)
=============================================================================
