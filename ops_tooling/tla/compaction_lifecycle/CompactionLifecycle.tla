------------------------- MODULE CompactionLifecycle -------------------------
(***************************************************************************)
(* The compaction lifecycle of the context service (OMN-18531, plan task   *)
(* TA.1): candidates, activations and invocations, from the adapter's      *)
(* command to the install confirmation derived from captured transcript   *)
(* records. Plan section 6, "Compaction transaction" and "Boundary         *)
(* algorithm".                                                             *)
(*                                                                         *)
(* One session. Up to NB compactions (boundaries) happen in it; up to NInv *)
(* invocations of the adapter compete for them. An invocation is bound to  *)
(* the boundary that was next when it started (tb), whatever time its      *)
(* receipts are published at.                                              *)
(*                                                                         *)
(* Every mutation flag flips one design decision; a configuration sets at  *)
(* most one. See README.md for the decision each flag names.               *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets

CONSTANTS
    NInv, NB, MaxVV, MaxDup,
    AllowDrop,          \* capture may drop a boundary's compact record
    NoRevalidate,       \* mutation: the activation is minted without recomputing the version vector
    LastWins,           \* mutation: the fold keeps the last event, not the contracted precedence
    FallbackByCandidate,\* mutation: a fallback event is keyed by candidate and folds into its activations
    CompleteOnReply,    \* mutation: an attempt is complete when the edge accepts the package
    PublishWindow,      \* mutation: an activation is judged against the boundary after its publish time
    NoGapRule,          \* mutation: a missing compact record is never resolved to uncertain(capture_gap)
    TrustBoundaryLine   \* mutation: the package is sent before the activation is published, and an
                        \* activation line in a captured boundary is taken as installation

Inv == 1..NInv
Bs == 1..NB
Reasons == {"native", "notsel", "gap"}
Resolved == {"installed", "mismatch", "native", "notsel", "gap", "conflict"}

VARIABLES
    vv,         \* the session's source version vector, as a number that only grows
    nb,         \* boundaries that have happened
    ist,        \* per invocation: idle started kept built minted sentfirst published sent fellback crashed
    kind,       \* per invocation: "pre" (precompute, builds a candidate only) or "real"
    tb,         \* per invocation: the boundary it competes for (nb + 1 when it started)
    pe,         \* per invocation: the boundary after the one it was published at (PublishWindow reads it)
    cvv,        \* per invocation: the version vector of the candidate it picked (0 before)
    actVV,      \* per invocation: the version vector recomputed when the activation was minted
    kept,       \* version vectors of candidates built and kept
    pkg,        \* per invocation: the package reached the edge
    edgeDone,   \* per invocation: the edge has returned (accepted, or native on a miss)
    acc,        \* per invocation: "none" or "ok"
    bcontent,   \* per boundary: what the harness installed
    cap,        \* boundaries whose compact record was captured
    capTail,    \* boundaries after which a later item was captured
    dropped,    \* boundaries whose compact record capture dropped
    pub,        \* receipt events published
    rcv,        \* receipt events the fold has received
    implAct,    \* per activation: the fold's state, updated on every arrival
    dups,       \* redeliveries spent
    completed   \* attempts some consumer has called complete

vars == <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
          cap, capTail, dropped, pub, rcv, implAct, dups, completed>>

Ev(k, id, r) == <<k, id, r>>

(* ---- the fold: a join over a total precedence ---- *)
Strong(x) == x \in {"installed", "mismatch"}
WeakRank(x) == IF x = "native" THEN 1 ELSE IF x = "notsel" THEN 2 ELSE 3
Join(x, y) ==
    IF x = y THEN x
    ELSE IF x = "none" THEN y
    ELSE IF y = "none" THEN x
    ELSE IF x = "conflict" \/ y = "conflict" THEN "conflict"
    ELSE IF {x, y} = {"installed", "mismatch"} THEN "conflict"
    ELSE IF Strong(x) THEN x
    ELSE IF Strong(y) THEN y
    ELSE IF WeakRank(x) >= WeakRank(y) THEN x ELSE y

RECURSIVE SetJoin(_)
SetJoin(V) == IF V = {} THEN "none"
              ELSE LET x == CHOOSE x \in V : TRUE IN Join(x, SetJoin(V \ {x}))

EvVal(e) == IF e[1] = "inst" THEN "installed"
            ELSE IF e[1] = "mism" THEN "mismatch"
            ELSE e[3]

ActEvents(a, S) == {e \in S : e[1] \in {"inst", "mism", "unc"} /\ e[2] = a}
Canon(a, S) == SetJoin({EvVal(e) : e \in ActEvents(a, S)})

Apply(e) ==
    IF e[1] \in {"inst", "mism", "unc"}
    THEN [implAct EXCEPT ![e[2]] = IF LastWins THEN EvVal(e) ELSE Join(implAct[e[2]], EvVal(e))]
    ELSE IF e[1] = "fb" /\ FallbackByCandidate
    THEN [a \in Inv |-> IF a # e[2] /\ cvv[a] # 0 /\ cvv[a] = cvv[e[2]]
                        THEN Join(implAct[a], "conflict") ELSE implAct[a]]
    ELSE implAct

(* ---- what the confirm compute derives from the captured records ---- *)
Evid(j) == \E k \in Bs : k >= j /\ (k \in cap \/ k \in capTail)

DerivFor(a) ==
    LET j == IF PublishWindow THEN pe[a] ELSE tb[a]
        known == Ev("act", a, "-") \in rcv
        atBoundary ==
            IF j \in cap
            THEN (IF bcontent[j] = <<"ok", a>> THEN {Ev("inst", a, "-")}
                  ELSE IF bcontent[j] = <<"bad", a>> THEN {Ev("mism", a, "-")}
                  ELSE IF bcontent[j] = <<"native", 0>> THEN {Ev("unc", a, "native")}
                  ELSE {Ev("unc", a, "notsel")})
            ELSE IF ~NoGapRule /\ j >= 1 /\ j <= NB /\ Evid(j) THEN {Ev("unc", a, "gap")}
            ELSE {}
        trusted == IF TrustBoundaryLine
                   THEN {Ev("inst", a, "-") : k \in {k2 \in cap : bcontent[k2] = <<"ok", a>>}}
                   ELSE {}
    IN (IF known /\ j >= 1 THEN atBoundary ELSE {}) \union trusted

Derivable == UNION {DerivFor(a) : a \in Inv}

(* ---- the world ---- *)
Init ==
    /\ vv = 1 /\ nb = 0
    /\ ist = [i \in Inv |-> "idle"] /\ kind = [i \in Inv |-> "real"]
    /\ tb = [i \in Inv |-> 0] /\ pe = [i \in Inv |-> 0]
    /\ cvv = [i \in Inv |-> 0] /\ actVV = [i \in Inv |-> 0]
    /\ kept = {} /\ pkg = [i \in Inv |-> FALSE]
    /\ edgeDone = [i \in Inv |-> FALSE] /\ acc = [i \in Inv |-> "none"]
    /\ bcontent = [k \in Bs |-> <<"none", 0>>]
    /\ cap = {} /\ capTail = {} /\ dropped = {}
    /\ pub = {} /\ rcv = {} /\ implAct = [i \in Inv |-> "none"]
    /\ dups = 0 /\ completed = {}

Unch(vs) == UNCHANGED vs

Start(i) ==
    /\ ist[i] = "idle" /\ nb < NB
    /\ \E kd \in {"pre", "real"} :
         /\ kind' = [kind EXCEPT ![i] = kd]
         /\ edgeDone' = [edgeDone EXCEPT ![i] = (kd = "pre")]
    /\ ist' = [ist EXCEPT ![i] = "started"]
    /\ tb' = [tb EXCEPT ![i] = nb + 1]
    /\ UNCHANGED <<vv, nb, pe, cvv, actVV, kept, pkg, acc, bcontent, cap, capTail, dropped,
                   pub, rcv, implAct, dups, completed>>

Build(i) ==
    /\ ist[i] = "started"
    /\ \E c \in kept \union {vv} :
         /\ cvv' = [cvv EXCEPT ![i] = c]
         /\ kept' = kept \union {c}
         /\ pub' = pub \union {Ev("prep", c, "-")}
    /\ ist' = [ist EXCEPT ![i] = IF kind[i] = "pre" THEN "kept" ELSE "built"]
    /\ UNCHANGED <<vv, nb, kind, tb, pe, actVV, pkg, edgeDone, acc, bcontent, cap, capTail,
                   dropped, rcv, implAct, dups, completed>>

Mint(i) ==
    /\ ist[i] = "built"
    /\ IF NoRevalidate \/ cvv[i] = vv
       THEN /\ ist' = [ist EXCEPT ![i] = "minted"]
            /\ actVV' = [actVV EXCEPT ![i] = vv]
            /\ pub' = pub
       ELSE /\ ist' = [ist EXCEPT ![i] = "fellback"]
            /\ pub' = pub \union {Ev("fb", i, "-")}
            /\ actVV' = actVV
    /\ UNCHANGED <<vv, nb, kind, tb, pe, cvv, kept, pkg, edgeDone, acc, bcontent, cap, capTail,
                   dropped, rcv, implAct, dups, completed>>

Fail(i) ==
    /\ ist[i] \in {"started", "built"}
    /\ ist' = [ist EXCEPT ![i] = "fellback"]
    /\ pub' = pub \union {Ev("fb", i, "-")}
    /\ UNCHANGED <<vv, nb, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent, cap,
                   capTail, dropped, rcv, implAct, dups, completed>>

Crash(i) ==
    /\ ist[i] \in {"minted", "sentfirst"}
    /\ ist' = [ist EXCEPT ![i] = "crashed"]
    /\ UNCHANGED <<vv, nb, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent, cap,
                   capTail, dropped, pub, rcv, implAct, dups, completed>>

PubAct(i) ==
    /\ ist[i] = (IF TrustBoundaryLine THEN "sentfirst" ELSE "minted")
    /\ pub' = pub \union {Ev("act", i, "-")}
    /\ pe' = [pe EXCEPT ![i] = nb + 1]
    /\ ist' = [ist EXCEPT ![i] = IF TrustBoundaryLine THEN "sent" ELSE "published"]
    /\ UNCHANGED <<vv, nb, kind, tb, cvv, actVV, kept, pkg, edgeDone, acc, bcontent, cap,
                   capTail, dropped, rcv, implAct, dups, completed>>

Send(i) ==
    /\ ist[i] = (IF TrustBoundaryLine THEN "minted" ELSE "published")
    /\ pkg' = [pkg EXCEPT ![i] = TRUE]
    /\ ist' = [ist EXCEPT ![i] = IF TrustBoundaryLine THEN "sentfirst" ELSE "sent"]
    /\ UNCHANGED <<vv, nb, kind, tb, pe, cvv, actVV, kept, edgeDone, acc, bcontent, cap,
                   capTail, dropped, pub, rcv, implAct, dups, completed>>

EdgeAccept(i) ==
    /\ pkg[i] /\ ~edgeDone[i]
    /\ edgeDone' = [edgeDone EXCEPT ![i] = TRUE]
    /\ acc' = [acc EXCEPT ![i] = "ok"]
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, bcontent, cap, capTail,
                   dropped, pub, rcv, implAct, dups, completed>>

EdgeTimeout(i) ==
    /\ ist[i] # "idle" /\ ~edgeDone[i]
    /\ edgeDone' = [edgeDone EXCEPT ![i] = TRUE]
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, acc, bcontent, cap,
                   capTail, dropped, pub, rcv, implAct, dups, completed>>

VVBump ==
    /\ vv < MaxVV /\ vv' = vv + 1
    /\ UNCHANGED <<nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent, cap,
                   capTail, dropped, pub, rcv, implAct, dups, completed>>

Compact ==
    /\ nb < NB
    /\ \A i \in Inv : (ist[i] # "idle" /\ tb[i] = nb + 1) => edgeDone[i]
    /\ \E c \in {<<"native", 0>>}
              \union {<<"ok", i>> : i \in {j \in Inv : ist[j] # "idle" /\ tb[j] = nb + 1 /\ acc[j] = "ok"}}
              \union {<<"bad", i>> : i \in {j \in Inv : ist[j] # "idle" /\ tb[j] = nb + 1 /\ acc[j] = "ok"}} :
         bcontent' = [bcontent EXCEPT ![nb + 1] = c]
    /\ nb' = nb + 1
    /\ UNCHANGED <<vv, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, cap, capTail,
                   dropped, pub, rcv, implAct, dups, completed>>

CaptureB(k) ==
    /\ k <= nb /\ k \notin cap /\ k \notin dropped
    /\ cap' = cap \union {k}
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   capTail, dropped, pub, rcv, implAct, dups, completed>>

DropB(k) ==
    /\ AllowDrop /\ k <= nb /\ k \notin cap /\ k \notin dropped
    /\ dropped' = dropped \union {k}
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, capTail, pub, rcv, implAct, dups, completed>>

CaptureT(k) ==
    /\ k <= nb /\ k \notin capTail
    /\ capTail' = capTail \union {k}
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, dropped, pub, rcv, implAct, dups, completed>>

Deliver ==
    /\ \E e \in pub \ rcv :
         /\ rcv' = rcv \union {e}
         /\ implAct' = Apply(e)
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, capTail, dropped, pub, dups, completed>>

Redeliver ==
    /\ dups < MaxDup
    /\ \E e \in rcv : implAct' = Apply(e)
    /\ dups' = dups + 1
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, capTail, dropped, pub, rcv, completed>>

Confirm ==
    /\ \E e \in Derivable \ pub : pub' = pub \union {e}
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, capTail, dropped, rcv, implAct, dups, completed>>

Complete(a) ==
    /\ a \notin completed
    /\ IF CompleteOnReply THEN acc[a] = "ok" ELSE implAct[a] = "installed"
    /\ completed' = completed \union {a}
    /\ UNCHANGED <<vv, nb, ist, kind, tb, pe, cvv, actVV, kept, pkg, edgeDone, acc, bcontent,
                   cap, capTail, dropped, pub, rcv, implAct, dups>>

Next ==
    \/ \E i \in Inv : Start(i) \/ Build(i) \/ Mint(i) \/ Fail(i) \/ Crash(i) \/ PubAct(i)
                      \/ Send(i) \/ EdgeAccept(i) \/ EdgeTimeout(i) \/ Complete(i)
    \/ \E k \in Bs : CaptureB(k) \/ DropB(k) \/ CaptureT(k)
    \/ VVBump \/ Compact \/ Deliver \/ Redeliver \/ Confirm

Fair ==
    /\ WF_vars(\E i \in Inv : Build(i))
    /\ WF_vars(\E i \in Inv : Mint(i))
    /\ WF_vars(\E i \in Inv : PubAct(i))
    /\ WF_vars(\E i \in Inv : Send(i))
    /\ WF_vars(\E i \in Inv : EdgeTimeout(i))
    /\ WF_vars(\E i \in Inv : Complete(i))
    /\ WF_vars(\E k \in Bs : CaptureB(k))
    /\ WF_vars(\E k \in Bs : CaptureT(k))
    /\ WF_vars(Deliver) /\ WF_vars(Confirm)

Spec == Init /\ [][Next]_vars /\ Fair

(* ---- properties ---- *)
TypeOK ==
    /\ vv \in 1..MaxVV /\ nb \in 0..NB
    /\ ist \in [Inv -> {"idle", "started", "kept", "built", "minted", "sentfirst", "published",
                         "sent", "fellback", "crashed"}]
    /\ acc \in [Inv -> {"none", "ok"}]
    /\ implAct \in [Inv -> Resolved \union {"none"}]
    /\ cap \subseteq Bs /\ capTail \subseteq Bs /\ dropped \subseteq Bs
    /\ rcv \subseteq pub /\ completed \subseteq Inv

\* An installation fact exists only for an activation the runtime published.
NoInstallWithoutActivation ==
    \A a \in Inv : (Ev("inst", a, "-") \in pub \/ Ev("mism", a, "-") \in pub)
                       => Ev("act", a, "-") \in pub

\* The fold's state is a function of the set of events received, whatever the order and copies.
OneStatePerIdentityUnderAnyArrivalOrder ==
    \A a \in Inv : implAct[a] = Canon(a, rcv)

\* A candidate whose version vector changed before the activation was minted is never installed.
StaleCandidateNeverInstalled ==
    \A a \in Inv : Ev("inst", a, "-") \in pub => cvv[a] = actVV[a]

\* An activation's state conflicts only on its own installation evidence, never through
\* another invocation's fallback.
FallbackNeverConflictsWithAnotherInvocation ==
    \A a \in Inv : implAct[a] = "conflict"
                       => (Ev("inst", a, "-") \in rcv /\ Ev("mism", a, "-") \in rcv)

\* No consumer calls an attempt complete before the fold holds installed.
NoCompleteBeforeInstalled ==
    \A a \in completed : implAct[a] = "installed"

\* Every activation of a boundary that happened, whose later item was captured, resolves.
EveryActivationResolves ==
    \A a \in Inv : [](Ev("act", a, "-") \in pub /\ nb >= tb[a] => <>(implAct[a] \in Resolved))

(* ---- reachability controls: each is violated on an adopted configuration ---- *)
NeverInstalled == \A a \in Inv : implAct[a] # "installed"
NeverMismatch == \A a \in Inv : implAct[a] # "mismatch"
NeverNativeNotInstalled == \A a \in Inv : implAct[a] # "native"
NeverNotSelected == \A a \in Inv : implAct[a] # "notsel"
NeverGap == \A a \in Inv : implAct[a] # "gap"
NeverStaleBuilt == \A i \in Inv : ~(ist[i] = "built" /\ cvv[i] # vv)
NeverGapThenInstalled ==
    \A a \in Inv : ~(Ev("unc", a, "gap") \in pub /\ Ev("inst", a, "-") \in pub)
NeverFallbackBesideActivation ==
    \A i, j \in Inv : ~(i # j /\ Ev("fb", i, "-") \in pub /\ cvv[i] # 0 /\ cvv[i] = cvv[j]
                        /\ Ev("act", j, "-") \in pub)
=============================================================================
