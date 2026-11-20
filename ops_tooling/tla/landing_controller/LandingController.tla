------------------------- MODULE LandingController --------------------------
(***************************************************************************)
(* OMN-17427 (related OMN-19822, OMN-19823). The landing controller of the *)
(* merge-drain-that-merges plan (docs-repo beta/plans/       *)
(* 2026-09-27-merge-drain-that-merges-plan.md, revision 4): the T3         *)
(* model-before-build prerequisite, and the model half of gate G-ACT (T5). *)
(*                                                                         *)
(* It extends the per-PR landing model ../pr_landing/PrLanding.tla one     *)
(* layer up. PrLanding models one PR's reducer row against duplicated,     *)
(* reordered ingress; its results (head-match drop, ordering key, outbox,  *)
(* effect dedupe) are taken as given here, because the controller reads    *)
(* one consistent snapshot per tick. So a PR in this module is its GitHub  *)
(* truth (head, open, merged, suspended, CI), and the vocabulary (heads as *)
(* per-PR sequence numbers, companion, hold, merged) is PrLanding's. The   *)
(* module does not EXTENDS PrLanding textually: that would put all of      *)
(* PrLanding's variables and its ingress network into every state here     *)
(* with nothing reading them, and PrLanding alone reaches ~3*10^8 states.  *)
(*                                                                         *)
(* What this module adds: headless workers with a process lifetime, the    *)
(* per-PR lease keyed repo#pr (R7), recorded outcomes and escalation (R1), *)
(* push evidence and its verification (R1, revision 4), blocker            *)
(* fingerprints and redispatch suppression (R8), the runtime token (R6),   *)
(* repo handover (section 0), batch companions with membership (R2), and   *)
(* rebuild requests with idempotency keys across controller crashes (R2,   *)
(* T6), and the red-PR fixer of OMN-20414 (cause leases, member           *)
(* suppression, attempt budget and park, the fixer HOLD, the caps).       *)
(* OMN-20744 adds the bus owner (retirement plan slice S2): the ci-run-   *)
(* failed path as the claim lease's second writer, with durable claims,   *)
(* cause absorption and the shared lease the controller reads (S5).      *)
(*                                                                         *)
(* procAlive[w] (the live processes of worker w's group plus every process *)
(* carrying w's tag: "main" and "child", a child possibly setsid'd out of  *)
(* the group but still tagged) is kept apart from resultRecorded[w].       *)
(* WorkerResult and RecordResult never touch procAlive; only ProcessExit   *)
(* and Kill shrink it; ConfirmTerminated is enabled only when procAlive[w] *)
(* = {}.                                                                   *)
(*                                                                         *)
(* Every guard a plan rule adds is a CONSTANT whose plan value is listed   *)
(* first, so one .cfg selects "plan as written" and a mutation .cfg        *)
(* selects "plan with guard G removed"; each mutation cfg must show the    *)
(* violation that guard exists to prevent (see README.md).                 *)
(***************************************************************************)
EXTENDS Naturals, FiniteSets, TLC

CONSTANTS
  PRs, Workers, Nil,
  Collab,          \* PRs by a collaborator: never eligible (R2 "excluded")
  Runtime,         \* PRs that need the runtime token to land (R6)
  MaxHead,         \* heads are 1..MaxHead per PR (a push is head + 1)
  Engines,         \* dispatches per PR: sonnet, opus, Codex high (R1 ladder)
  MaxDispatch,     \* bound on dispatches in a run (lease ids 1..MaxDispatch)
  MaxAttempts,     \* R2: attempts per rebuild key before rebuild_exhausted
  MaxComps,        \* bound on companion ids (TypeOK checks it holds)
  InitCi,          \* CI state of every PR's first head: "red", "green", "pending"
  InitComp,        \* TRUE: one companion open at start carrying every PR at head 1
  PushModes,       \* worker push modes, subset of {"ff", "fwl"}
                   \*   ("fwl" = --force-with-lease=<ref>:<old>, a rebase)
  ResultKinds,     \* result kinds a worker may write, subset of
                   \*   {"fix_submitted", "external_blocker", "waiting_ci"}
  \* environment budgets (every environment action is bounded)
  BPush, BForeign, BMPush, BClose, BElig, BBlk, BCrash, BPFail, BDrain,
  Track,           \* TRUE: record scenario tags in hist (reachability cfgs only)
  \* ---- the guards; the plan's value first ----
  LeaseByPR,       \* R7: lease keyed repo#pr (TRUE); FALSE keys it by head
  ReleaseRule,     \* R7: "term" releases only on confirmed termination;
                   \*   "result" (revision 2) on a recorded result;
                   \*   "deadline" when the deadline passes
  DiscardRevoked,  \* S12: a result carrying a revoked lease id is discarded
  Verify,          \* R1: "evidence" (push evidence matched to the ref update,
                   \*   revision 4); "ancestry" (revision 2); "headonly"
  PinMerge,        \* R1/R7: merge/arm under a live lease only at the verified head
  FreeTokenFirst,  \* R6: the token is freed first in the tick after its holder leaves
  MemberElig,      \* R2 (rev 4): merge needs every member eligible AND current
  WaitOnSuspended, \* R2 (rev 4): no close while a member is suspended
  BlockedSuppress, \* R8: no dispatch while blocked with an unchanged fingerprint
  SuppressAny,     \* mutation of R8: also suppress after invalid/timed_out (breaks L2)
  DrainGate,       \* P7: no dispatch while draining; observe-only only with no live worker
  ProducerIdem,    \* T6: the producer returns the existing companion for a fulfilled key
  RedeliverPending,\* R2: a pending, undelivered record is delivered by a later tick
  RetryFailed,     \* R2: a failed request is retried with the same key
  Cover,           \* R2: an uncovered member that is eligible again gets a request
  SeenAny,         \* model finding LC-F1: a rebuild succeeds when a companion carrying
                   \*   its key exists in any state (TRUE); FALSE is the plan text, "open"
  \* ---- the red-PR fixer (OMN-20414; red-PR fixer plan section 2, task T1) ----
  Repos,           \* the repos, each given as the set of its PRs (a partition of PRs)
  Causes,          \* cause keys the tick may form (model values)
  Members,         \* one set per cause: the cause's model value and its member PRs
  Budget,          \* 2.4: counted attempts per cause per park episode
  RepoCap,         \* 2.4: live workers of any kind per repo (plan 6)
  CauseRepoCap,    \* 2.4: live cause workers per repo (plan 2)
  CauseFleetCap,   \* 2.4: live cause workers fleet-wide (plan 4)
  CauseKinds,      \* result kinds a cause worker may write, subset of
                   \*   {"cause_fix_submitted", "cause_not_shared", "external_blocker"}
  BHold, BClaim, BCClaim, BPark,  \* fixer HOLD toggles, per-PR CLAIMs, cause CLAIMs, park ends
  \* ---- the fixer's guards; the plan's value first ----
  MemberSuppress,  \* 2.4: no per-PR dispatch for a member of a leased, fixing or parked cause
  BudgetGate,      \* 2.4: no cause dispatch with the attempt (or spawn-failure) budget spent
  HoldGate,        \* 2.4: no dispatch of any kind in a repo under a fixer HOLD
  CapGate,         \* 2.4: RepoCap, CauseRepoCap and CauseFleetCap checked at dispatch
  EscDedupe,       \* 2.4: "ledger": the escalation's dedupe key is read from the ledger
                   \*   row it wrote; "sidecar": only from the controller's sidecar; "none"
  MemberClaimsOwn, \* 2.3: FALSE, a per-PR CLAIM on a member never owns the cause
  LateExitCounts,  \* model finding LC-F2: an exit with no result after the spawn window
                   \*   and before the deadline counts as an attempt (TRUE); FALSE is the
                   \*   plan text, which counts it nowhere
  \* ---- the bus owner (OMN-20744; landing-controller retirement plan, slice S2) ----
  BusOn,           \* TRUE: the bus path (ci-run-failed -> node_pr_lifecycle_orchestrator) runs
  BusAct,          \* the contract flag ci_red_triage.act: TRUE starts owners, FALSE only decides
  BRestart,        \* runtime restarts of the bus path (an environment budget)
  \* ---- the bus owner's guards; the plan's value first ----
  BusDurable,      \* S2: decisions and owner claims are durable rows (TRUE); FALSE keeps
                   \*   them in process memory, as S0 does, so a restart forgets them
  BusAbsorb,       \* S2: a cause the bus claims absorbs its members' PR-own claims
  BusCas           \* S2/S5: the bus claims through the shared lease (compare-and-set on
                   \*   lease[s], which the controller reads); FALSE keeps a private claim

Ids      == 1..MaxDispatch
Subj     == PRs \cup Causes     \* lease subjects: a PR (repo#pr) or a cause key
Mem(c)   == (CHOOSE s \in Members : c \in s) \ {c}
RepoOf(p) == CHOOSE r \in Repos : p \in r
RepoOfS(s) == IF s \in PRs THEN RepoOf(s) ELSE RepoOf(CHOOSE p \in Mem(s) : TRUE)
BusW == Nil              \* a bus-held lease names no controller worker
ClusterMin      == 3      \* 2.2: a cluster has at least 3 members (2 under a floor: not modeled)
SpawnFailBudget == 3      \* 2.4: three exits with no result in the spawn window park the cause

ASSUME /\ UNION Repos = PRs /\ \A r1, r2 \in Repos : r1 = r2 \/ r1 \cap r2 = {}
       /\ \A c \in Causes : Cardinality({s \in Members : c \in s}) = 1
                          /\ Mem(c) # {} /\ Mem(c) \subseteq PRs
                          /\ \A p, q \in Mem(c) : RepoOf(p) = RepoOf(q)
AllKeys  == SUBSET (PRs \X (1..MaxHead))
Outcomes == {"merged", "armed", "fix_submitted", "external_blocker", "invalid", "timed_out"}

VARIABLES
  \* GitHub truth
  head, open, merged, susp, ci, blk,
  lastp,          \* per PR: the ref update behind the current head [lid, mode]
                  \*   (lid 0: no lease; mode "ff", "fwl" or "bare")
  \* workers (detached process groups)
  wp,             \* PR worker w was dispatched for (Nil: never dispatched)
  wl,             \* lease id worker w runs under (0: none)
  wh,             \* head worker w last knew (its expected old head)
  procAlive,      \* live processes of w's group and tag, subset of {"main", "child"}
  resultRecorded, \* the controller recorded w's result
  wfile,          \* w's result file [k, h]: NoFile, a written result, or ReadFile
  wconf,          \* the controller confirmed w terminated
  \* controller state file
  lease,          \* per PR: Nil or [id, w, dh, lh, heads, dl]
  out,            \* per PR: last recorded outcome [k, fp, why]
  esc,            \* per PR: dispatches so far (engine index)
  awaitH,         \* per PR: head of a verified fix_submitted (0: none)
  nd,             \* dispatch counter
  nout,           \* ghost: outcomes recorded per lease id (P3)
  revoked,        \* revoked lease ids
  token,          \* runtime token holder (Nil: free)
  draining, observe,
  comps,          \* companions [id, key, k, open, ci, merged]; k = set of <<pr, head>>
  rec,            \* rebuild records [k, old, st, att, dlv, dv]
  mem,            \* controller memory not yet in the state file
  pinbox,         \* producer runs delivered, not finished [k, n]
  pfail,          \* keys whose producer run failed, not yet read
  ereq,           \* PRs owed one eligibility rerun after their companion merged
  unc,            \* members dropped by a rebuild while suspended (uncovered)
  \* the red-PR fixer: per-cause record in the state file
  cform,          \* the cause is formed (ClusterForm)
  catt,           \* counted attempts this park episode
  csf,            \* spawn failures this park episode (an exit with no result in the window)
  crev,           \* ghost: leases revoked under a fixer HOLD this episode (counted nowhere)
  cdisp,          \* ghost: cause dispatches this park episode (P11)
  cpark,          \* parked (budget spent, cause still present)
  cfix,           \* the cause's fix PR: "none", "open", "merged"
  cns,            \* cause_not_shared: the member heads that key is blocked for ({}: none)
  nesc,           \* ghost: operator escalation MSG rows written this park episode (P14)
  cesc,           \* the escalation's dedupe key in the controller's sidecar
  \* controller memory not yet acted on / written
  spawnq,         \* cause workers whose lease is written and whose spawn is not done
  escmem,         \* causes whose escalation MSG is written and whose sidecar key is not
  \* environment
  fhold,          \* repos under a fixer HOLD (scope=fixer)
  pclaim,         \* PRs a lane's per-PR CLAIM names (owned)
  cclaim,         \* causes a lane's cause CLAIM names
  \* the bus owner (S2): node_pr_state_emit_effect's detector and the
  \* lifecycle orchestrator's ci_red_triage handler
  bev,            \* ci-run-failed events on the topic, <<pr, head>> (retained: redeliverable)
  bdec,           \* decided keys <<pr, head>> (the check is fixed); durable iff BusDurable
  bown,           \* per subject the owner claim: PR -> the head its owner was started for,
                  \*   cause -> 1; 0: none. Durable iff BusDurable
  babs,           \* per cause the member PRs its claim absorbed; durable iff BusDurable
  brun,           \* subjects whose bus-started lifecycle run is live
  nst,            \* ghost: start commands per owner key <<subject, head>> (0 for a cause)
  \* ghosts
  tlate, bad, hist, bud

gh == <<head, open, merged, susp, ci, blk, lastp>>
wk == <<wp, wl, wh, procAlive, resultRecorded, wfile, wconf>>
ct == <<lease, out, esc, awaitH, nd, nout, revoked>>
dr == <<draining, observe>>
cm == <<comps, rec, mem, pinbox, pfail, ereq, unc>>
cz == <<cform, catt, csf, crev, cdisp, cpark, cfix, cns, nesc, cesc>>
fm == <<spawnq, escmem>>
fe == <<fhold, pclaim, cclaim>>
bz == <<bev, bdec, bown, babs, brun, nst>>
vars == <<gh, wk, ct, token, tlate, dr, cm, bad, hist, bud, cz, fm, fe, bz>>

NoFile   == [k |-> "none", h |-> 0]
ReadFile == [k |-> "read", h |-> 0]

Bad0 == [p4 |-> FALSE, p5 |-> FALSE, p6 |-> FALSE, p7 |-> FALSE, p8 |-> FALSE,
         unauth |-> FALSE, legit |-> FALSE, pin |-> FALSE, p10 |-> FALSE, p12 |-> FALSE,
         dual |-> FALSE, absorb |-> FALSE]

Init ==
  /\ head = [p \in PRs |-> 1] /\ open = [p \in PRs |-> TRUE]
  /\ merged = [p \in PRs |-> FALSE] /\ susp = [p \in PRs |-> FALSE]
  /\ ci = [p \in PRs |-> InitCi] /\ blk = [p \in PRs |-> 0]
  /\ lastp = [p \in PRs |-> [lid |-> 0, mode |-> "ff"]]
  /\ wp = [w \in Workers |-> Nil] /\ wl = [w \in Workers |-> 0]
  /\ wh = [w \in Workers |-> 0] /\ procAlive = [w \in Workers |-> {}]
  /\ resultRecorded = [w \in Workers |-> FALSE] /\ wfile = [w \in Workers |-> NoFile]
  /\ wconf = [w \in Workers |-> FALSE]
  /\ lease = [s \in Subj |-> Nil]
  /\ out = [p \in PRs |-> [k |-> "none", fp |-> 0, why |-> ""]]
  /\ esc = [p \in PRs |-> 0] /\ awaitH = [p \in PRs |-> 0] /\ nd = 0
  /\ nout = [i \in Ids |-> 0] /\ revoked = {}
  /\ token = Nil /\ tlate = FALSE /\ draining = FALSE /\ observe = FALSE
  /\ comps = IF InitComp
             THEN {[id |-> 1, key |-> {<<p, 1>> : p \in PRs}, k |-> {<<p, 1>> : p \in PRs},
                    open |-> TRUE, ci |-> "pending", merged |-> FALSE]}
             ELSE {}
  /\ rec = {} /\ mem = {} /\ pinbox = {} /\ pfail = {} /\ ereq = {} /\ unc = {}
  /\ bad = Bad0 /\ hist = {}
  /\ bud = [push |-> BPush, foreign |-> BForeign, mpush |-> BMPush, close |-> BClose,
            elig |-> BElig, blk |-> BBlk, crash |-> BCrash, pfail |-> BPFail, drain |-> BDrain,
            hold |-> BHold, claim |-> BClaim, cclaim |-> BCClaim, park |-> BPark,
            brestart |-> BRestart]
  /\ cform = [c \in Causes |-> FALSE] /\ catt = [c \in Causes |-> 0] /\ csf = [c \in Causes |-> 0]
  /\ crev = [c \in Causes |-> 0] /\ cdisp = [c \in Causes |-> 0] /\ cpark = [c \in Causes |-> FALSE]
  /\ cfix = [c \in Causes |-> "none"] /\ cns = [c \in Causes |-> {}]
  /\ nesc = [c \in Causes |-> 0] /\ cesc = [c \in Causes |-> FALSE]
  /\ spawnq = {} /\ escmem = {}
  /\ fhold = {} /\ pclaim = {} /\ cclaim = {}
  /\ bev = {} /\ bdec = {} /\ bown = [s \in Subj |-> 0] /\ babs = [c \in Causes |-> {}]
  /\ brun = {} /\ nst = [k \in Subj \X (0..MaxHead) |-> 0]

-----------------------------------------------------------------------------
(* Helpers                                                                 *)
Elig(p)    == open[p] /\ ~susp[p] /\ p \notin Collab
Susp(p)    == open[p] /\ susp[p] /\ p \notin Collab
Cur(m)     == open[m[1]] /\ head[m[1]] = m[2]
EligM(m)   == Elig(m[1])
SuspM(m)   == Susp(m[1])
MemPRs(K)  == {m[1] : m \in K}
Log(T)     == hist' = IF Track THEN hist \cup T ELSE hist
Spend(f)   == bud[f] > 0 /\ bud' = [bud EXCEPT ![f] = @ - 1]
Leased(w)  == wp[w] # Nil /\ lease[wp[w]] # Nil /\ lease[wp[w]].w = w
Blocked(p) == out[p].k = "external_blocker" /\ out[p].fp = blk[p]
\* R6: the holder is merged, closed or dequeued (a hold dequeues it)
TokenDue   == token # Nil /\ (~open[token] \/ susp[token])
\* every acting controller step: not observe-only, and (R6) the token freed first
Ctl        == ~observe /\ (FreeTokenFirst => ~TokenDue) /\ tlate' = (tlate \/ TokenDue)
RecK(K)    == {r \in rec : r.k = K}
HasRec(K)  == RecK(K) # {}
TheRec(K)  == CHOOSE r \in rec : r.k = K
PutRec(K, r) == rec' = (rec \ RecK(K)) \cup {r}
Upd(c, c2) == comps' = (comps \ {c}) \cup {c2}
PendingFor(c)    == \E r \in rec : r.old = c.id /\ r.st = "pending"
Superseded(c)    == \E r \in rec : r.old = c.id /\ r.st = "succeeded"
Orphan(c)        == \A m \in c.k : ~EligM(m) /\ ~SuspM(m)
AllReady(c)      == \A m \in c.k : Cur(m) /\ EligM(m)
NewK(c)          == {<<m[1], head[m[1]]>> : m \in {x \in c.k : EligM(x)}}
NeedsRebuild(c)  == (\E m \in c.k : EligM(m)) /\ ~AllReady(c)
\* the red-PR fixer (2.2 to 2.4)
\* a cluster candidate: red, open, not person-held, not a collaborator's.
\* A per-PR CLAIM (pclaim) does not stop a PR joining a cluster (2.3).
Cand(p)      == open[p] /\ ~susp[p] /\ p \notin Collab /\ ci[p] = "red"
Present(c)   == \E p \in Mem(c) : Cand(p)
\* member suppression: a cause with a live lease, an open fix PR or a park
Suppressed(p) == \E c \in Causes : p \in Mem(c) /\ (lease[c] # Nil \/ cfix[c] = "open" \/ cpark[c])
LeasesIn(r)  == {s \in Subj : RepoOfS(s) = r /\ lease[s] # Nil}
CLeasesIn(r) == {c \in Causes : RepoOfS(c) = r /\ lease[c] # Nil}
CLeases      == {c \in Causes : lease[c] # Nil}
CapPR(p)     == Cardinality(LeasesIn(RepoOf(p))) < RepoCap
CapC(c)      == /\ Cardinality(LeasesIn(RepoOfS(c))) < RepoCap
                /\ Cardinality(CLeasesIn(RepoOfS(c))) < CauseRepoCap
                /\ Cardinality(CLeases) < CauseFleetCap
NSBlocked(c) == cns[c] # {} /\ \A m \in cns[c] : head[m[1]] = m[2]
Owned(p)     == p \in pclaim
\* the bus owner (S2)
CauseOf(p)   == {c \in Causes : p \in Mem(c)}
CtlLive(s)   == \E w \in Workers : wp[w] = s /\ ~wconf[w]
BusHolds(p)  == p \in brun \/ \E c \in CauseOf(p) : c \in brun
BusLeased(s) == lease[s] # Nil /\ lease[s].w = BusW
BusLease(h)  == [id |-> 0, w |-> BusW, dh |-> h, lh |-> h, heads |-> IF h = 0 THEN {} ELSE {h},
                 dl |-> FALSE]

-----------------------------------------------------------------------------
(* GitHub and people. The controller never runs these.                     *)
NewHead(p, lid, mode) ==
  /\ head' = [head EXCEPT ![p] = @ + 1] /\ ci' = [ci EXCEPT ![p] = "pending"]
  /\ lastp' = [lastp EXCEPT ![p] = [lid |-> lid, mode |-> mode]]

MemberPush(p) ==      \* the author pushes while no lease is live on the PR
  /\ open[p] /\ lease[p] = Nil /\ head[p] < MaxHead /\ Spend("mpush")
  /\ NewHead(p, 0, "ff")
  /\ UNCHANGED <<bz, cz, fm, fe, open, merged, susp, blk, wk, ct, token, tlate, dr, cm, bad, hist>>

ForeignRewrite(p) ==  \* a push to the head ref no live lease authorized (bare --force)
  /\ open[p] /\ lease[p] # Nil /\ head[p] < MaxHead /\ Spend("foreign")
  /\ NewHead(p, 0, "bare")
  /\ UNCHANGED <<bz, cz, fm, fe, open, merged, susp, blk, wk, ct, token, tlate, dr, cm, bad, hist>>

MemberClose(p) ==
  /\ open[p] /\ Spend("close")
  /\ open' = [open EXCEPT ![p] = FALSE]
  /\ UNCHANGED <<bz, cz, fm, fe, head, merged, susp, ci, blk, lastp, wk, ct, token, tlate, dr, cm, bad, hist>>

\* a hold, release, gate, draft or do-not-land change with no head change
MemberEligibilityChange(p) ==
  /\ open[p] /\ p \notin Collab /\ Spend("elig")
  /\ susp' = [susp EXCEPT ![p] = ~@]
  /\ hist' = IF Track /\ (\E c \in comps :
                  /\ c.open /\ c.ci = "green" /\ Cardinality(c.k) >= 2
                  /\ \A m \in c.k : open[m[1]] /\ head[m[1]] = m[2] /\ susp'[m[1]] /\ m[1] \notin Collab)
             THEN hist \cup {"allheld"} ELSE hist
  /\ UNCHANGED <<bz, cz, fm, fe, head, open, merged, ci, blk, lastp, wk, ct, token, tlate, dr, cm, bad>>

BlockerChange(p) ==   \* a blocker ref named by the PR's blocked outcome changes state
  /\ Spend("blk")
  /\ blk' = [blk EXCEPT ![p] = @ + 1]
  /\ UNCHANGED <<bz, cz, fm, fe, head, open, merged, susp, ci, lastp, wk, ct, token, tlate, dr, cm, bad, hist>>

CiResult(p) ==        \* CI finishes on the PR's current head
  /\ open[p] /\ ci[p] = "pending"
  /\ \E v \in {"green", "red"} : ci' = [ci EXCEPT ![p] = v]
  /\ UNCHANGED <<bz, cz, fm, fe, head, open, merged, susp, blk, lastp, wk, ct, token, tlate, dr, cm, bad, hist, bud>>

CompCiC(c) ==          \* CI finishes on a companion
  /\ c.open /\ c.ci = "pending"
  /\ \E v \in {"green", "red"} : Upd(c, [c EXCEPT !.ci = v])
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, tlate, dr, rec, mem, pinbox, pfail, ereq, unc, bad, hist, bud>>

RepoDrain ==          \* the operator starts the repo's handover (section 0, step 2). LC-8 (OMN-25793, R6): no guard on spawnq or pinbox; scratch invariants `draining => spawnq = {}` and `observe => pinbox = {}` are violated, a defect of this drain, open.
  /\ ~draining /\ Spend("drain")
  /\ draining' = TRUE
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, tlate, observe, cm, bad, hist>>

ControllerCrash ==    \* the controller loses what it had not written to its state file
  /\ (mem # {} \/ spawnq # {} \/ escmem # {}) /\ Spend("crash")
  /\ mem' = {} /\ spawnq' = {} /\ escmem' = {}
  /\ Log(IF spawnq # {} THEN {"S28c"} ELSE {})
  /\ UNCHANGED <<bz, cz, fe, gh, wk, ct, token, tlate, dr, comps, rec, pinbox, pfail, ereq, unc, bad>>

WorkerTimeout(w) ==   \* the lease deadline passes (the clock)
  /\ Leased(w) /\ ~lease[wp[w]].dl
  /\ LET p == wp[w] IN
     IF ReleaseRule = "deadline"
     THEN /\ lease' = [lease EXCEPT ![p] = Nil]
          /\ bad' = [bad EXCEPT !.p8 = @ \/ procAlive[w] # {}]
     ELSE /\ lease' = [lease EXCEPT ![p].dl = TRUE]
          /\ UNCHANGED bad
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, out, esc, awaitH, nd, nout, revoked, token, tlate, dr, cm, hist, bud>>

-----------------------------------------------------------------------------
(* Workers. Detached, own process group, the lease id as their tag. They   *)
(* keep running whatever the controller records; only exit or kill ends    *)
(* them.                                                                   *)
WorkerPush(w) ==      \* fast-forward, or --force-with-lease naming the head it last knew
  /\ wp[w] \in PRs /\ procAlive[w] # {}
  /\ LET p == wp[w] IN
     /\ open[p] /\ head[p] = wh[w] /\ head[p] < MaxHead /\ Spend("push")
     /\ \E m \in PushModes : NewHead(p, wl[w], m)
     /\ wh' = [wh EXCEPT ![w] = head[p] + 1]
     /\ Log(IF lease[p] # Nil /\ lease[p].w = w /\ lease[p].dl THEN {"S2a"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, open, merged, susp, blk, wp, wl, procAlive, resultRecorded, wfile, wconf,
                 ct, token, tlate, dr, cm, bad>>

ChildSpawn(w) ==      \* a background push, a gh watch, a test run; may setsid out of the group
  /\ "main" \in procAlive[w] /\ "child" \notin procAlive[w]
  /\ procAlive' = [procAlive EXCEPT ![w] = @ \cup {"child"}]
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wp, wl, wh, resultRecorded, wfile, wconf, ct, token, tlate, dr, cm, bad, hist, bud>>

ProcessExit(w) ==     \* the worker, or its child, exits by itself
  /\ \E x \in procAlive[w] : procAlive' = [procAlive EXCEPT ![w] = @ \ {x}]
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wp, wl, wh, resultRecorded, wfile, wconf, ct, token, tlate, dr, cm, bad, hist, bud>>

WorkerResult(w) ==    \* the worker writes its one typed result file
  /\ "main" \in procAlive[w] /\ wfile[w] = NoFile /\ wp[w] \in PRs
  /\ \E k \in ResultKinds :
     \E h \in (IF k = "fix_submitted" THEN 1..head[wp[w]] ELSE {head[wp[w]]}) :
       wfile' = [wfile EXCEPT ![w] = [k |-> k, h |-> h]]
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wp, wl, wh, procAlive, resultRecorded, wconf, ct, token, tlate, dr, cm, bad, hist, bud>>

-----------------------------------------------------------------------------
(* The controller: worker lifecycle (R1, R7, R8), landing (R6), handover.  *)
DispatchTags(p) ==
  (IF out[p].k = "timed_out" /\ out[p].why = "deadline" THEN {"S9"} ELSE {})
  \cup (IF out[p].k = "invalid" /\ out[p].why = "head_mismatch" THEN {"S8"} ELSE {})
  \cup (IF out[p].k = "invalid" /\ out[p].why = "unauthorized_rewrite" THEN {"S17"} ELSE {})
  \cup (IF out[p].k = "invalid" /\ out[p].why = "waiting_ci" THEN {"S10"} ELSE {})
  \cup (IF out[p].k = "external_blocker" THEN {"S11"} ELSE {})

Dispatch(p, w) ==
  /\ Ctl
  /\ wp[w] = Nil /\ nd < MaxDispatch /\ esc[p] < Engines
  /\ Elig(p) /\ ci[p] = "red"
  /\ IF LeaseByPR \/ lease[p] = Nil THEN lease[p] = Nil ELSE lease[p].lh # head[p]
  /\ DrainGate => ~draining
  /\ BlockedSuppress => ~Blocked(p)
  /\ SuppressAny => ~(out[p].k \in {"invalid", "timed_out"} /\ out[p].fp = blk[p])
  /\ ~Owned(p)                                   \* 2.3: an owned PR gets no per-PR worker
  /\ MemberSuppress => ~Suppressed(p)            \* 2.4: member suppression
  /\ HoldGate => RepoOf(p) \notin fhold          \* 2.4: the fixer HOLD
  /\ CapGate => CapPR(p)                         \* 2.4: workers per repo
  /\ LET id == nd + 1 IN
     /\ lease' = [lease EXCEPT ![p] = [id |-> id, w |-> w, dh |-> head[p], lh |-> head[p],
                                       heads |-> {head[p]}, dl |-> FALSE]]
     /\ wp' = [wp EXCEPT ![w] = p] /\ wl' = [wl EXCEPT ![w] = id]
     /\ wh' = [wh EXCEPT ![w] = head[p]]
     /\ procAlive' = [procAlive EXCEPT ![w] = {"main"}]
     /\ nd' = id /\ esc' = [esc EXCEPT ![p] = @ + 1]
     /\ awaitH' = [awaitH EXCEPT ![p] = 0]
  /\ bad' = [bad EXCEPT !.p6 = @ \/ Blocked(p), !.p7 = @ \/ draining,
                        !.p10 = @ \/ Suppressed(p), !.p12 = @ \/ RepoOf(p) \in fhold,
                        !.dual = @ \/ BusHolds(p)]
  /\ Log(DispatchTags(p)
         \cup (IF \E x \in 1..MaxHead : nst[<<p, x>>] > 0 THEN {"SB4"} ELSE {})
         \cup (IF \E c \in Causes : p \in Mem(c) /\ cns[c] # {} /\ esc[p] = 0 /\ "S27n" \in hist
               THEN {"S27"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, resultRecorded, wfile, wconf, out, nout, revoked, token, dr, cm, bud>>

ObserveHead(p) ==     \* R7: a head change under a live lease updates last-seen head in place
  /\ Ctl
  /\ lease[p] # Nil /\ lease[p].lh # head[p] /\ ~BusLeased(p)
  /\ lease' = [lease EXCEPT ![p].lh = head[p], ![p].heads = @ \cup {head[p]}]
  /\ Log(IF lastp[p].lid = lease[p].id THEN {"S1"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, out, esc, awaitH, nd, nout, revoked, token, dr, cm, bad, bud>>

\* The tick reads a result file and records the outcome (R1). Push evidence is
\* abstracted to lastp: the ref update behind the live head names the lease id
\* that authorized it and its mode. Evidence verification accepts exactly a
\* fast-forward or force-with-lease update made under this live lease.
RecordResult(w) ==
  /\ Ctl
  /\ wp[w] \in PRs /\ wfile[w].k \notin {"none", "read"}
  /\ LET p    == wp[w]
         f    == wfile[w]
         id   == wl[w]
         disc == DiscardRevoked /\ id \in revoked
         lz   == lease[p] # Nil /\ lease[p].id = id
         auth == lz /\ lastp[p].lid = id /\ lastp[p].mode \in {"ff", "fwl"}
         okE  == f.h = head[p] /\ auth
         ok   == CASE Verify = "evidence" -> okE
                   [] Verify = "ancestry" -> okE /\ lastp[p].mode = "ff"
                   [] OTHER              -> f.h = head[p]
         k2   == CASE f.k = "external_blocker"   -> "external_blocker"
                   [] f.k = "fix_submitted" /\ ok -> "fix_submitted"
                   [] OTHER                      -> "invalid"
         \* the live head came from a bare push, or from another lease's push
         rewrite == lastp[p].mode = "bare" \/ (lastp[p].lid # 0 /\ lastp[p].lid # id)
         why  == CASE f.k = "waiting_ci"          -> "waiting_ci"
                   [] f.h = head[p] /\ rewrite    -> "unauthorized_rewrite"
                   [] OTHER                      -> "head_mismatch"
         rel  == ReleaseRule = "result" /\ lz
     IN
     /\ wfile' = [wfile EXCEPT ![w] = ReadFile]
     /\ IF disc
        THEN /\ UNCHANGED <<bz, cz, fm, fe, out, awaitH, nout, resultRecorded, lease, bad>>
             /\ Log({"S12late"})
        ELSE /\ out' = [out EXCEPT ![p] = [k |-> k2, fp |-> blk[p],
                                           why |-> IF k2 = "invalid" THEN why ELSE ""]]
             /\ awaitH' = [awaitH EXCEPT ![p] = IF k2 = "fix_submitted" THEN f.h ELSE @]
             /\ nout' = [nout EXCEPT ![id] = @ + 1]
             /\ resultRecorded' = [resultRecorded EXCEPT ![w] = TRUE]
             /\ lease' = IF rel THEN [lease EXCEPT ![p] = Nil] ELSE lease
             /\ bad' = [bad EXCEPT !.p8 = @ \/ (rel /\ procAlive[w] # {}),
                                   !.unauth = @ \/ (k2 = "fix_submitted" /\ ~auth),
                                   !.legit = @ \/ (f.k = "fix_submitted" /\ okE /\ k2 # "fix_submitted")]
             /\ Log((IF k2 # "invalid" /\ "child" \in procAlive[w] THEN {"S13r"} ELSE {})
                    \cup (IF k2 = "fix_submitted" /\ lastp[p].mode = "fwl" THEN {"S16"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wp, wl, wh, procAlive, wconf, esc, nd, revoked, token, dr, cm, bud>>

Kill(w) ==            \* the kill sequence: after a passed deadline, the post-result
                      \* exit grace, or a revocation; SIGTERM, wait, SIGKILL
  /\ Ctl
  /\ Leased(w) /\ procAlive[w] # {}
  /\ lease[wp[w]].dl \/ resultRecorded[w] \/ wl[w] \in revoked
  /\ procAlive' = [procAlive EXCEPT ![w] = {}]
  /\ Log(IF wp[w] \in Causes /\ wl[w] \in revoked THEN {"S24k"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wp, wl, wh, resultRecorded, wfile, wconf, ct, token, dr, cm, bad, bud>>

Revoke(w) ==          \* handover step 3, or a fixer HOLD on the worker's repo (2.4):
                      \* a leased worker with no result is revoked
  /\ Ctl
  /\ draining \/ (wp[w] # Nil /\ RepoOfS(wp[w]) \in fhold)
  /\ Leased(w) /\ ~resultRecorded[w] /\ wl[w] \notin revoked
  /\ revoked' = revoked \cup {wl[w]}
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, lease, out, esc, awaitH, nd, nout, token, dr, cm, bad, hist, bud>>

\* R7: the only release. Signal-0 on the group and the tag scan both empty.
ConfirmTerminated(w) ==
  /\ Ctl
  /\ Leased(w) /\ procAlive[w] = {}
  /\ w \notin spawnq     \* the tick that wrote a cause lease spawns it before it exits (or crashes)
  /\ wfile[w].k \in {"none", "read"} \/ wl[w] \in revoked
  /\ LET p == wp[w] IN
     /\ lease' = [lease EXCEPT ![p] = Nil]
     /\ wconf' = [wconf EXCEPT ![w] = TRUE]
     /\ IF resultRecorded[w]
        THEN UNCHANGED <<bz, out, nout>>
        ELSE /\ out' = IF p \in PRs
                       THEN [out EXCEPT ![p] = [k |-> "timed_out", fp |-> blk[p],
                                                why |-> IF lease[p].dl THEN "deadline" ELSE "exited"]]
                       ELSE out
             /\ nout' = [nout EXCEPT ![wl[w]] = @ + 1]
     \* a cause lease with no recorded result (2.4): revoked under a fixer HOLD
     \* counts nowhere; a passed deadline is an attempt; an exit inside the
     \* spawn window (early) is a spawn failure; a later exit before the
     \* deadline is an attempt under the model's rule (LateExitCounts) and
     \* nothing under the plan text (model finding LC-F2)
     /\ IF p \in Causes /\ ~resultRecorded[w]
        THEN \E early \in BOOLEAN :
               /\ early => ~lease[p].dl
               /\ CASE wl[w] \in revoked -> /\ crev' = [crev EXCEPT ![p] = @ + 1]
                                           /\ UNCHANGED <<bz, catt, csf>>
                    [] lease[p].dl \/ (~early /\ LateExitCounts) ->
                                         /\ catt' = [catt EXCEPT ![p] = @ + 1]
                                         /\ UNCHANGED <<bz, csf, crev>>
                    [] early -> /\ csf' = [csf EXCEPT ![p] = @ + 1]
                                /\ UNCHANGED <<bz, catt, crev>>
                    [] OTHER -> UNCHANGED <<bz, catt, csf, crev>>
        ELSE UNCHANGED <<bz, catt, csf, crev>>
     /\ Log((IF p \in PRs /\ lease[p].dl /\ "S2a" \in hist THEN {"S2"} ELSE {})
            \cup (IF resultRecorded[w] /\ "S13r" \in hist THEN {"S13"} ELSE {})
            \cup (IF p \in Causes /\ wl[w] \in revoked /\ RepoOfS(p) \in fhold /\ "S24k" \in hist
                   THEN {"S24"} ELSE {}))
  /\ UNCHANGED <<bz, cform, cdisp, cpark, cfix, cns, nesc, cesc, fm, fe, gh, wp, wl, wh, procAlive,
                 resultRecorded, wfile, esc, awaitH, nd, revoked, token, dr, cm, bad, bud>>

Land(p) ==            \* merge (or arm) a green, eligible PR; pinned to the verified head
  /\ Ctl
  /\ Elig(p) /\ ci[p] = "green" /\ ~Owned(p)
  /\ p \in Runtime => token = p
  /\ PinMerge => (lease[p] # Nil => awaitH[p] = head[p])
  /\ merged' = [merged EXCEPT ![p] = TRUE] /\ open' = [open EXCEPT ![p] = FALSE]
  /\ bad' = [bad EXCEPT !.pin = @ \/ (lease[p] # Nil /\ awaitH[p] # head[p])]
  /\ Log(IF out[p].k = "fix_submitted" /\ awaitH[p] = head[p] THEN {"S7"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, head, susp, ci, blk, lastp, wk, ct, token, dr, cm, bud>>

TokenGrant(p) ==      \* R6: only to a green, eligible runtime PR
  /\ Ctl
  /\ token = Nil /\ p \in Runtime /\ Elig(p) /\ ci[p] = "green"
  /\ token' = p
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, dr, cm, bad, hist, bud>>

TokenFree ==          \* R6: the first thing a tick does when the holder has left
  /\ ~observe /\ TokenDue
  /\ token' = Nil
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, tlate, dr, cm, bad, hist, bud>>

ObserveOnly ==        \* handover step 4: only with zero leases and zero tagged processes
  /\ Ctl
  /\ draining
  /\ DrainGate => (\A p \in Subj : lease[p] = Nil) /\ (\A w \in Workers : procAlive[w] = {})
  /\ observe' = TRUE
  /\ bad' = [bad EXCEPT !.p7 = @ \/ (\E p \in Subj : lease[p] # Nil)
                                  \/ (\E w \in Workers : procAlive[w] # {})]
  /\ Log((IF revoked # {} THEN {"S12"} ELSE {})
         \cup (IF \E w \in Workers : resultRecorded[w] /\ wconf[w] THEN {"S12r"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, draining, cm, bud>>

-----------------------------------------------------------------------------
(* The controller: companions by membership (R2), rebuild requests with    *)
(* idempotency keys, written ahead of delivery (R2, T6).                   *)
CompanionMergeC(c) ==  \* rule 4: every member eligible and current, companion green
  /\ Ctl
  /\ c.open /\ c.ci = "green" /\ ~PendingFor(c) /\ ~Superseded(c)
  /\ \A m \in c.k : Cur(m) /\ (MemberElig => EligM(m))
  /\ Upd(c, [c EXCEPT !.open = FALSE, !.merged = TRUE])
  /\ ereq' = ereq \cup {q \in MemPRs(c.k) : open[q]}
  /\ bad' = [bad EXCEPT !.p4 = @ \/ ~AllReady(c)]
  /\ Log((IF Cardinality(c.k) = 1 THEN {"S6m"} ELSE {})
         \cup (IF "allheld" \in hist /\ rec = {} THEN {"S14"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, rec, mem, pinbox, pfail, unc, bud>>

EligRerun(p) ==       \* S6: each member's eligibility run is rerun whole once
  /\ Ctl
  /\ p \in ereq
  /\ ereq' = ereq \ {p}
  /\ Log(IF "S6m" \in hist THEN {"S6"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, rec, mem, pinbox, pfail, unc, bad, bud>>

CompanionCloseC(c) ==  \* rule 1 (orphaned), or superseded by a succeeded rebuild
  /\ Ctl
  /\ c.open /\ ~PendingFor(c)
  /\ Superseded(c) \/ (IF WaitOnSuspended THEN Orphan(c) ELSE \A m \in c.k : ~EligM(m))
  /\ Upd(c, [c EXCEPT !.open = FALSE])
  /\ bad' = [bad EXCEPT !.p5 = @ \/ (~Superseded(c) /\ ~Orphan(c))]
  /\ Log(IF ~Superseded(c) /\ Cardinality(c.k) >= 2
            /\ \A m \in c.k : ~open[m[1]] /\ ~merged[m[1]] THEN {"S5"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, rec, mem, pinbox, pfail, ereq, unc, bud>>

\* rule 3: at least one member eligible and some member moved, gone, suspended
\* or excluded. Write-ahead: the pending record goes to the state file, the
\* delivery is only in memory until RebuildDeliver and RecordDelivered.
RebuildRequestC(c) ==
  /\ Ctl
  /\ c.open /\ NeedsRebuild(c) /\ ~Superseded(c)
  /\ LET K == NewK(c) IN
     /\ ~HasRec(K)
     /\ \A q \in MemPRs(K) : lease[q] = Nil       \* R7: no branch-changing action under a lease
     /\ rec' = rec \cup {[k |-> K, old |-> c.id, st |-> "pending", att |-> 1, dlv |-> FALSE, dv |-> 0]}
     /\ mem' = mem \cup {<<"deliver", K>>}
     /\ unc' = unc \cup {m[1] : m \in {x \in c.k : SuspM(x)}}
     /\ Log((IF (\E m \in c.k : ~open[m[1]] /\ ~merged[m[1]]) /\ (\E m \in c.k : Cur(m) /\ EligM(m))
               THEN {"S3"} ELSE {})
            \cup (IF c.ci = "green" /\ Cardinality(K) >= 2
                     /\ \E m \in c.k : open[m[1]] /\ head[m[1]] # m[2] THEN {"S4"} ELSE {})
            \cup (IF "allheld" \in hist /\ Cardinality(K) = 1 /\ \E m \in c.k : SuspM(m)
                     THEN {"S14b"} ELSE {})
            \cup (IF c.ci = "green" /\ (\A m \in c.k : Cur(m)) /\ (\E m \in c.k : SuspM(m))
                     THEN {"S15r"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, pinbox, pfail, ereq, bad, bud>>

CoverRequest(p) ==    \* an uncovered member eligible again gets its own request
  /\ Ctl
  /\ Cover /\ p \in unc /\ Elig(p) /\ lease[p] = Nil
  /\ LET K == {<<p, head[p]>>}
         covered == HasRec(K) \/ \E c \in comps : c.open /\ <<p, head[p]>> \in c.k
     IN
     /\ unc' = unc \ {p}
     /\ IF covered
        THEN UNCHANGED <<bz, cz, fm, fe, rec, mem, hist>>
        ELSE /\ rec' = rec \cup {[k |-> K, old |-> 0, st |-> "pending", att |-> 1, dlv |-> FALSE, dv |-> 0]}
             /\ mem' = mem \cup {<<"deliver", K>>}
             /\ Log(IF "S15r" \in hist THEN {"S15"} ELSE {})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, pinbox, pfail, ereq, bad, bud>>

RebuildDeliver(K) ==  \* this tick's delivery, or a later tick's redelivery of an
                      \* undelivered pending record (after a crash lost the memory)
  /\ Ctl
  /\ HasRec(K)
  /\ LET r == TheRec(K)
         fresh == <<"deliver", K>> \in mem
     IN
     /\ r.st = "pending" /\ ~r.dlv
     /\ fresh \/ (RedeliverPending /\ <<"record", K>> \notin mem)
     /\ pinbox' = pinbox \cup {[k |-> K, n |-> r.dv + 1]}
     /\ PutRec(K, [r EXCEPT !.dv = @ + 1])
     /\ mem' = (mem \ {<<"deliver", K>>}) \cup {<<"record", K>>}
     /\ Log(IF fresh THEN {} ELSE IF r.dv = 0 THEN {"S19d"} ELSE {"S20d"})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, pfail, ereq, unc, bad, bud>>

RecordDelivered(K) == \* delivered_at and the run id reach the state file
  /\ Ctl
  /\ <<"record", K>> \in mem /\ HasRec(K)
  /\ PutRec(K, [TheRec(K) EXCEPT !.dlv = TRUE])
  /\ mem' = mem \ {<<"record", K>>}
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, pinbox, pfail, ereq, unc, bad, hist, bud>>

ProducerSucceedX(x) == \* T6: atomic per key; idempotent returns the existing companion
  /\ x \in pinbox
  /\ pinbox' = pinbox \ {x}
  /\ IF ProducerIdem /\ \E c \in comps : c.key = x.k
     THEN /\ UNCHANGED comps
          /\ Log({"S20p"})
     ELSE /\ comps' = comps \cup {[id |-> Cardinality(comps) + 1, key |-> x.k, k |-> x.k,
                                   open |-> TRUE, ci |-> "pending", merged |-> FALSE]}
          /\ UNCHANGED hist
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, tlate, dr, rec, mem, pfail, ereq, unc, bad, bud>>

ProducerFailX(x) ==
  /\ x \in pinbox /\ Spend("pfail")
  /\ pinbox' = pinbox \ {x}
  /\ pfail' = pfail \cup {x.k}
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, tlate, dr, comps, rec, mem, ereq, unc, bad, hist>>

\* pending -> succeeded: a companion carrying K exists. The plan's text says
\* "an open companion"; TLC (LC_rebuild, before this fix) found the replacement
\* merged by rule 4 before any tick saw it open, leaving K pending forever, the
\* retries returning the merged companion, K parked rebuild_exhausted and the
\* superseded companion never closed (L4 violated). Model finding LC-F1.
RebuildSeen(K) ==
  /\ Ctl
  /\ HasRec(K) /\ TheRec(K).st = "pending"
  /\ \E c \in comps : c.key = K /\ (SeenAny \/ c.open)
  /\ PutRec(K, [TheRec(K) EXCEPT !.st = "succeeded"])
  /\ pfail' = pfail \ {K}
  /\ Log((IF TheRec(K).att = 2 THEN {"S18"} ELSE {})
         \cup (IF "S19d" \in hist THEN {"S19"} ELSE {})
         \cup (IF {"S20d", "S20p"} \subseteq hist THEN {"S20"} ELSE {}))
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, mem, pinbox, ereq, unc, bad, bud>>

RebuildFailed(K) ==   \* pending -> failed when the producer run concluded in failure;
                      \* read by a later tick, so the delivering tick has finished
                      \* (its delivery recorded) or crashed (its memory lost)
  /\ Ctl
  /\ K \in pfail /\ <<"record", K>> \notin mem
  /\ pfail' = pfail \ {K}
  /\ IF HasRec(K) /\ TheRec(K).st = "pending" /\ ~\E c \in comps : c.key = K
     THEN PutRec(K, [TheRec(K) EXCEPT !.st = "failed"])
     ELSE UNCHANGED rec
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, mem, pinbox, ereq, unc, bad, hist, bud>>

RebuildRetry(K) ==    \* failed -> pending after the backoff, same key
  /\ Ctl
  /\ RetryFailed /\ HasRec(K) /\ TheRec(K).st = "failed" /\ TheRec(K).att < MaxAttempts
  /\ PutRec(K, [TheRec(K) EXCEPT !.st = "pending", !.att = @ + 1, !.dlv = FALSE])
  /\ mem' = mem \cup {<<"deliver", K>>}
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, pinbox, pfail, ereq, unc, bad, hist, bud>>

RebuildPark(K) ==     \* the third failure parks the key: rebuild_exhausted, DEGRADED
  /\ Ctl
  /\ HasRec(K) /\ TheRec(K).st = "failed" /\ TheRec(K).att >= MaxAttempts
  /\ PutRec(K, [TheRec(K) EXCEPT !.st = "exhausted"])
  /\ Log({"S18x"})
  /\ UNCHANGED <<bz, cz, fm, fe, gh, wk, ct, token, dr, comps, mem, pinbox, pfail, ereq, unc, bad, bud>>

-----------------------------------------------------------------------------
(* The red-PR fixer (OMN-20414; red-PR fixer plan section 2, task T1).    *)
(* A cause is a second lease subject beside the PR: same lease id space,  *)
(* same lease function, same kill sequence and the same release on        *)
(* confirmed termination (ConfirmTerminated). Revocation under a fixer   *)
(* HOLD goes through Revoke and Kill.                                     *)

\* 2.2: a cluster is at least ClusterMin candidate members sharing one
\* (check, signature); an escalated PR alone becomes a cause of one when no
\* cluster covers it (2.1). A PR belongs to at most one formed cause.
MultiFormable(c) == Cardinality({p \in Mem(c) : Cand(p)}) >= ClusterMin
Formable(c) ==
  IF Cardinality(Mem(c)) = 1
  THEN LET p == CHOOSE q \in Mem(c) : TRUE IN
       /\ Cand(p) /\ esc[p] >= Engines /\ lease[p] = Nil
       /\ ~\E c2 \in Causes : Cardinality(Mem(c2)) > 1 /\ p \in Mem(c2) /\ MultiFormable(c2)
  ELSE MultiFormable(c)

\* a new park episode: the record's counters start again
Fresh(c) ==
  /\ catt' = [catt EXCEPT ![c] = 0] /\ csf' = [csf EXCEPT ![c] = 0]
  /\ crev' = [crev EXCEPT ![c] = 0] /\ cdisp' = [cdisp EXCEPT ![c] = 0]
  /\ cpark' = [cpark EXCEPT ![c] = FALSE] /\ nesc' = [nesc EXCEPT ![c] = 0]
  /\ cesc' = [cesc EXCEPT ![c] = FALSE]

ClusterForm(c) ==
  /\ Ctl
  /\ ~cform[c] /\ ~NSBlocked(c) /\ Formable(c)
  /\ \A c2 \in Causes : cform[c2] => Mem(c2) \cap Mem(c) = {}
  /\ cform' = [cform EXCEPT ![c] = TRUE] /\ cns' = [cns EXCEPT ![c] = {}]
  /\ cfix' = [cfix EXCEPT ![c] = "none"]
  /\ Fresh(c)
  /\ UNCHANGED <<bz, fm, fe, gh, wk, ct, token, dr, cm, bad, hist, bud>>

\* 2.4: one lease per cause key, written to the state file before the spawn
\* (write-ahead); the spawn is CauseSpawn in the same tick.
CauseDispatch(c, w) ==
  /\ Ctl
  /\ wp[w] = Nil /\ nd < MaxDispatch
  /\ cform[c] /\ ~cpark[c] /\ lease[c] = Nil /\ cfix[c] = "none" /\ Present(c)
  /\ BudgetGate => (catt[c] < Budget /\ csf[c] < SpawnFailBudget)
  /\ HoldGate => RepoOfS(c) \notin fhold
  /\ DrainGate => ~draining
  /\ c \notin cclaim                               \* 2.3: a lane's cause CLAIM owns it
  /\ MemberClaimsOwn => Mem(c) \cap pclaim = {}    \* 2.3: per-PR CLAIMs never own a cause
  /\ CapGate => CapC(c)
  /\ LET id == nd + 1 IN
     /\ lease' = [lease EXCEPT ![c] = [id |-> id, w |-> w, dh |-> 0, lh |-> 0,
                                       heads |-> {}, dl |-> FALSE]]
     /\ wp' = [wp EXCEPT ![w] = c] /\ wl' = [wl EXCEPT ![w] = id]
     /\ wh' = [wh EXCEPT ![w] = 0] /\ nd' = id
  /\ spawnq' = spawnq \cup {w}
  /\ cdisp' = [cdisp EXCEPT ![c] = @ + 1]
  /\ bad' = [bad EXCEPT !.p7 = @ \/ draining, !.p12 = @ \/ RepoOfS(c) \in fhold,
                        !.dual = @ \/ c \in brun]
  /\ Log((IF Cardinality(Mem(c)) >= ClusterMin /\ \A p \in Mem(c) : esc[p] = 0 THEN {"S21"} ELSE {})
         \cup (IF Cardinality(Mem(c)) = 1 /\ Engines > 0 THEN {"S26"} ELSE {})
         \cup (IF Mem(c) \cap pclaim # {} THEN {"S25a"} ELSE {})
         \cup (IF "S28c" \in hist THEN {"S28"} ELSE {}))
  /\ UNCHANGED <<bz, gh, procAlive, resultRecorded, wfile, wconf, out, esc, awaitH, nout, revoked,
                 token, dr, cm, bud, cform, catt, csf, crev, cpark, cfix, cns, nesc, cesc, escmem, fe>>

CauseSpawn(w) ==      \* the tick spawns the worker whose lease it wrote
  /\ Ctl
  /\ w \in spawnq
  /\ spawnq' = spawnq \ {w}
  /\ procAlive' = [procAlive EXCEPT ![w] = {"main"}]
  /\ UNCHANGED <<bz, gh, wp, wl, wh, resultRecorded, wfile, wconf, ct, token, dr, cm, bad, hist, bud,
                 cz, escmem, fe>>

\* 2.5: the cause worker writes one typed result. For cause_fix_submitted,
\* h = 1 when the fix PR it names exists, h = 0 for a claim with no PR.
CauseWorkerResult(w) ==
  /\ "main" \in procAlive[w] /\ wfile[w] = NoFile /\ wp[w] \in Causes
  /\ \E k \in CauseKinds :
     \E h \in (IF k = "cause_fix_submitted" THEN {0, 1} ELSE {0}) :
       wfile' = [wfile EXCEPT ![w] = [k |-> k, h |-> h]]
  /\ UNCHANGED <<bz, gh, wp, wl, wh, procAlive, resultRecorded, wconf, ct, token, tlate, dr, cm,
                 bad, hist, bud, cz, fm, fe>>

\* 2.4 and 2.6: the tick records a cause result. An attempt counts when a
\* result is recorded; an unverified fix claim spends it with nothing else.
\* cause_not_shared returns the members to the per-PR path at rung 0 and
\* blocks the key for the member heads it saw. A result carrying a revoked
\* lease id is discarded, as for a per-PR worker.
CauseResult(w) ==
  /\ Ctl
  /\ wp[w] \in Causes /\ wfile[w].k \notin {"none", "read"}
  /\ LET c    == wp[w]
         f    == wfile[w]
         disc == DiscardRevoked /\ wl[w] \in revoked
     IN
     /\ wfile' = [wfile EXCEPT ![w] = ReadFile]
     /\ IF disc
        THEN UNCHANGED <<bz, nout, resultRecorded, catt, cform, cfix, cns, esc, hist>>
        ELSE /\ nout' = [nout EXCEPT ![wl[w]] = @ + 1]
             /\ resultRecorded' = [resultRecorded EXCEPT ![w] = TRUE]
             /\ catt' = [catt EXCEPT ![c] = @ + 1]
             /\ CASE f.k = "cause_fix_submitted" /\ f.h = 1 ->
                       /\ cfix' = [cfix EXCEPT ![c] = "open"]
                       /\ UNCHANGED <<bz, cform, cns, esc, hist>>
                  [] f.k = "cause_not_shared" ->
                       /\ cform' = [cform EXCEPT ![c] = FALSE]
                       /\ cns' = [cns EXCEPT ![c] = {<<p, head[p]>> : p \in Mem(c)}]
                       /\ esc' = [p \in PRs |-> IF p \in Mem(c) THEN 0 ELSE esc[p]]
                       /\ Log({"S27n"})
                       /\ UNCHANGED cfix
                  [] OTHER -> UNCHANGED <<bz, cform, cfix, cns, esc, hist>>
  /\ UNCHANGED <<bz, gh, wp, wl, wh, procAlive, wconf, lease, out, awaitH, nd, revoked, token, dr,
                 cm, bad, bud, csf, crev, cdisp, cpark, nesc, cesc, fm, fe>>

\* 2.6: the controller lands the fix PR like any PR; it then emits one rerun
\* per member head for the cause.
FixMerge(c) ==
  /\ Ctl
  /\ cfix[c] = "open"
  /\ cfix' = [cfix EXCEPT ![c] = "merged"]
  /\ ci' = [p \in PRs |-> IF p \in Mem(c) /\ open[p] /\ ci[p] = "red" THEN "pending" ELSE ci[p]]
  /\ UNCHANGED <<bz, head, open, merged, susp, blk, lastp, wk, ct, token, dr, cm, bad, hist, bud,
                 cform, catt, csf, crev, cdisp, cpark, cns, nesc, cesc, fm, fe>>

\* 2.6: once the members' CI has graded again, a member still failing makes
\* the attempt a failure (the next attempt, or the park); with no member
\* failing, the cause resolves and its record clears.
CauseRecheck(c) ==
  /\ Ctl
  /\ cform[c] /\ lease[c] = Nil /\ cfix[c] \in {"none", "merged"}
  /\ \A p \in Mem(c) : open[p] => ci[p] # "pending"
  /\ IF ~Present(c)
     THEN /\ cform' = [cform EXCEPT ![c] = FALSE] /\ cfix' = [cfix EXCEPT ![c] = "none"]
          /\ Fresh(c)
          /\ Log(IF cfix[c] = "merged" /\ \A p \in Mem(c) : open[p] /\ ci[p] = "green"
                 THEN {"S22"} ELSE {})
     ELSE /\ cfix[c] = "merged"
          /\ cfix' = [cfix EXCEPT ![c] = "none"]
          /\ UNCHANGED <<bz, cform, catt, csf, crev, cdisp, cpark, nesc, cesc, hist>>
  /\ UNCHANGED <<bz, gh, wk, ct, token, dr, cm, bad, bud, cns, fm, fe>>

\* 2.4: the budget is spent and the cause is still present: park it.
CausePark(c) ==
  /\ Ctl
  /\ cform[c] /\ ~cpark[c] /\ lease[c] = Nil /\ cfix[c] = "none" /\ Present(c)
  /\ catt[c] >= Budget \/ csf[c] >= SpawnFailBudget
  /\ cpark' = [cpark EXCEPT ![c] = TRUE]
  /\ UNCHANGED <<bz, gh, wk, ct, token, dr, cm, bad, hist, bud,
                 cform, catt, csf, crev, cdisp, cfix, cns, nesc, cesc, fm, fe>>

\* 2.4: one ledger MSG to=operator per park episode, dedupe key
\* <cause key>@<parked_until>. The MSG row is appended atomically; the key
\* reaches the controller's sidecar afterwards (RecordEscalated). EscDedupe
\* says where the dedupe is read: "ledger" (the MSG row it wrote; the model's
\* rule, model finding LC-F3), "sidecar" (only the sidecar), "none".
OperatorEscalate(c) ==
  /\ Ctl
  /\ cpark[c]
  /\ CASE EscDedupe = "ledger"  -> nesc[c] = 0
       [] EscDedupe = "sidecar" -> ~cesc[c] /\ c \notin escmem
       [] OTHER                 -> nesc[c] <= 1      \* bounded so the mutant stays finite
  /\ nesc' = [nesc EXCEPT ![c] = @ + 1]
  /\ escmem' = escmem \cup {c}
  /\ Log(IF catt[c] >= Budget THEN {"S23"} ELSE {})
  /\ UNCHANGED <<bz, gh, wk, ct, token, dr, cm, bad, bud,
                 cform, catt, csf, crev, cdisp, cpark, cfix, cns, cesc, spawnq, fe>>

RecordEscalated(c) == \* the dedupe key reaches the sidecar
  /\ Ctl
  /\ c \in escmem
  /\ escmem' = escmem \ {c}
  /\ cesc' = [cesc EXCEPT ![c] = TRUE]
  /\ UNCHANGED <<bz, gh, wk, ct, token, dr, cm, bad, hist, bud,
                 cform, catt, csf, crev, cdisp, cpark, cfix, cns, nesc, spawnq, fe>>

\* Environment: the fixer HOLD (a ledger HOLD row scope=fixer, and its
\* RELEASE), lanes' CLAIMs, and the end of a park (a RELEASE row naming the
\* cause, or the 12 hours passing).
FixerHoldOn(r) ==
  /\ r \notin fhold /\ Spend("hold")
  /\ fhold' = fhold \cup {r}
  /\ UNCHANGED <<bz, gh, wk, ct, token, tlate, dr, cm, bad, hist, cz, fm, pclaim, cclaim>>

FixerHoldOff(r) ==
  /\ r \in fhold /\ Spend("hold")
  /\ fhold' = fhold \ {r}
  /\ UNCHANGED <<bz, gh, wk, ct, token, tlate, dr, cm, bad, hist, cz, fm, pclaim, cclaim>>

LaneClaim(p) ==       \* a lane's per-PR CLAIM: the PR is owned
  /\ open[p] /\ p \notin pclaim /\ Spend("claim")
  /\ pclaim' = pclaim \cup {p}
  /\ UNCHANGED <<bz, gh, wk, ct, token, tlate, dr, cm, bad, hist, cz, fm, fhold, cclaim>>

CauseClaim(c) ==      \* a lane's CLAIM naming the cause (cause=, live, not a dispatcher)
  /\ c \notin cclaim /\ Spend("cclaim")
  /\ cclaim' = cclaim \cup {c}
  /\ Log(IF cform[c] /\ lease[c] = Nil /\ ~cpark[c] /\ cfix[c] = "none" /\ Present(c)
            /\ catt[c] < Budget THEN {"S25b"} ELSE {})
  /\ UNCHANGED <<bz, gh, wk, ct, token, tlate, dr, cm, bad, cz, fm, fhold, pclaim>>

ParkEnd(c) ==
  /\ cpark[c] /\ Spend("park")
  /\ Fresh(c)
  /\ escmem' = escmem \ {c}
  /\ UNCHANGED <<bz, gh, wk, ct, token, tlate, dr, cm, bad, hist, cform, cfix, cns, spawnq, fe>>

-----------------------------------------------------------------------------
(* The bus owner (OMN-20744; docs-repo beta/plans/           *)
(* 2026-10-08-landing-controller-retirement-into-lifecycle-nodes.md, S2). *)
(* node_pr_state_emit_effect's detector puts ci-run-failed on the bus for *)
(* a red head (BusEmit); node_pr_lifecycle_orchestrator's ci_red_triage   *)
(* handler decides it once per repo, head and check and starts one owner  *)
(* per owner key (BusHandle). The topic retains its records and a runtime *)
(* restart (BusRestart) re-reads them, so every record may be handled     *)
(* again at any time. The bus is the claim lease's second writer: under   *)
(* BusCas its owner claim is a compare-and-set on the same lease[s] the   *)
(* controller writes and reads (Dispatch and CauseDispatch need lease[s]  *)
(* = Nil; member suppression reads lease[c]), so the controller defers to *)
(* a bus owner and the bus to a controller lease (S5's deferral). A bus   *)
(* lease names no worker (BusW) and is released only when its run ends   *)
(* (BusRunEnd). The check is fixed: a key is <<pr, head>>.                *)

\* The peers the detector attached may be partial: its index is empty after
\* a restart, and in S0's replay a cause formed only at its third member. So
\* a PR-own decision is always possible; a cause only once ClusterMin members
\* are candidates.
BusOpts(p) == {p} \cup {c \in CauseOf(p) : Cardinality(Mem(c)) >= ClusterMin /\ MultiFormable(c)}

BusEmit(p) ==
  /\ BusOn /\ open[p] /\ ci[p] = "red" /\ <<p, head[p]>> \notin bev
  /\ bev' = bev \cup {<<p, head[p]>>}
  /\ UNCHANGED <<gh, wk, ct, token, tlate, dr, cm, bad, hist, bud, cz, fm, fe,
                 bdec, bown, babs, brun, nst>>

\* One decision for a key. A member absorbed by a cause the bus has claimed
\* is owned by that cause, whatever its own decision says (BusAbsorb). A key
\* whose owner is already claimed joins it; otherwise the owner starts, but
\* under BusCas only when the shared lease is free and no cause lease
\* suppresses the PR. With BusAct FALSE (the shipped contract) nothing starts. LC-7 (OMN-25793, R2): a start suppressed by drain still adds its key to bdec, so after a rollback that head gets no owner; the forward handover needs a drain-suppressed start not to persist its key, or a rollback rescan (not modeled).
BusDecide(p, h, s) ==
  LET absorbed == {c \in CauseOf(p) : p \in babs[c] /\ bown[c] # 0}
      o      == IF s \in PRs /\ BusAbsorb /\ absorbed # {} THEN CHOOSE c \in absorbed : TRUE ELSE s
      hk     == IF o \in PRs THEN h ELSE 0
      joined == IF o \in PRs THEN bown[o] = h ELSE bown[o] # 0
      free   == BusCas => (lease[o] = Nil /\ (o \in PRs => ~Suppressed(o)))
      start  == BusAct /\ ~joined /\ free /\ (DrainGate => ~draining)
  IN
  /\ bdec' = bdec \cup {<<p, h>>}
  /\ IF start
     THEN /\ bown' = [bown EXCEPT ![o] = IF o \in PRs THEN h ELSE 1]
          /\ brun' = brun \cup {o}
          /\ nst' = [nst EXCEPT ![<<o, hk>>] = @ + 1]
          /\ lease' = IF BusCas THEN [lease EXCEPT ![o] = BusLease(hk)] ELSE lease
          /\ babs' = IF o \in Causes /\ BusAbsorb THEN [babs EXCEPT ![o] = Mem(o)] ELSE babs
          /\ bad' = [bad EXCEPT
                       !.dual = @ \/ CtlLive(o) \/ (o \in PRs /\ \E c \in CauseOf(o) : CtlLive(c)),
                       !.absorb = @ \/ (o \in PRs /\ \E c \in CauseOf(o) : bown[c] # 0)]
          /\ Log(IF o \in Causes
                    /\ Cardinality({q \in Mem(o) : \E x \in 1..MaxHead : nst[<<q, x>>] > 0}) >= 2
                 THEN {"SB2"} ELSE {})
     ELSE /\ UNCHANGED <<bown, brun, nst, lease, babs, bad>>
          /\ Log(IF o # s /\ joined THEN {"SB3"} ELSE {})
  /\ UNCHANGED <<gh, wk, out, esc, awaitH, nd, nout, revoked, token, tlate, dr, cm, bud, cz, fm, fe,
                 bev>>

\* A (re)delivered ci-run-failed. A decided key yields no second decision and
\* no second start; that it was decided is read from bdec, which a restart
\* empties unless BusDurable.
BusHandle(p, h) ==
  /\ <<p, h>> \in bev
  /\ IF <<p, h>> \in bdec
     THEN /\ Log(IF bud.brestart < BRestart THEN {"SB1"} ELSE {})
          /\ UNCHANGED <<gh, wk, ct, token, tlate, dr, cm, bad, bud, cz, fm, fe, bz>>
     ELSE \E s \in BusOpts(p) : BusDecide(p, h, s)

\* The bus-started lifecycle run concludes; its lease is released. The owner
\* claim stays: the same head (or cause) joins it and starts nothing.
BusRunEnd(s) ==
  /\ s \in brun
  /\ brun' = brun \ {s}
  /\ lease' = IF BusLeased(s) THEN [lease EXCEPT ![s] = Nil] ELSE lease
  /\ UNCHANGED <<gh, wk, out, esc, awaitH, nd, nout, revoked, token, tlate, dr, cm, bad, hist, bud,
                 cz, fm, fe, bev, bdec, bown, babs, nst>>

\* The runtime restarts: process memory is lost; the topic and the lease are not.
BusRestart ==
  /\ BusOn /\ Spend("brestart")
  /\ IF BusDurable
     THEN UNCHANGED <<bdec, bown, babs>>
     ELSE /\ bdec' = {} /\ bown' = [s \in Subj |-> 0] /\ babs' = [c \in Causes |-> {}]
  /\ UNCHANGED <<gh, wk, ct, token, tlate, dr, cm, bad, hist, cz, fm, fe, bev, brun, nst>>

Bus ==
  \/ \E p \in PRs : BusEmit(p)
  \/ \E p \in PRs, h \in 1..MaxHead : BusHandle(p, h)
  \/ \E s \in Subj : BusRunEnd(s)
  \/ BusRestart

-----------------------------------------------------------------------------
(* Named wrappers over constant domains, so TLC prints each step's name in *)
(* a trace (it cannot split an action whose domain is a state variable).   *)
CompIds == 1..MaxComps
CompCi(i)          == \E c \in comps : c.id = i /\ CompCiC(c)
CompanionMerge(i)  == \E c \in comps : c.id = i /\ CompanionMergeC(c)
CompanionClose(i)  == \E c \in comps : c.id = i /\ CompanionCloseC(c)
RebuildRequest(i)  == \E c \in comps : c.id = i /\ RebuildRequestC(c)
ProducerSucceed(K) == \E x \in pinbox : x.k = K /\ ProducerSucceedX(x)
ProducerFail(K)    == \E x \in pinbox : x.k = K /\ ProducerFailX(x)

-----------------------------------------------------------------------------

Env ==
  \/ \E p \in PRs : MemberPush(p) \/ ForeignRewrite(p) \/ MemberClose(p)
                    \/ MemberEligibilityChange(p) \/ BlockerChange(p) \/ CiResult(p)
  \/ \E i \in CompIds : CompCi(i)
  \/ \E w \in Workers : WorkerPush(w) \/ ChildSpawn(w) \/ ProcessExit(w)
                        \/ WorkerResult(w) \/ WorkerTimeout(w)
  \/ \E K \in AllKeys : ProducerSucceed(K) \/ ProducerFail(K)
  \/ RepoDrain \/ ControllerCrash
  \/ \E r \in Repos : FixerHoldOn(r) \/ FixerHoldOff(r)
  \/ \E p \in PRs : LaneClaim(p)
  \/ \E c \in Causes : CauseClaim(c) \/ ParkEnd(c)
  \/ \E w \in Workers : CauseWorkerResult(w)

Controller ==
  \/ \E p \in PRs : ObserveHead(p) \/ Land(p) \/ TokenGrant(p) \/ EligRerun(p) \/ CoverRequest(p)
  \/ \E p \in PRs, w \in Workers : Dispatch(p, w)
  \/ \E w \in Workers : RecordResult(w) \/ Kill(w) \/ Revoke(w) \/ ConfirmTerminated(w)
  \/ \E i \in CompIds : CompanionMerge(i) \/ CompanionClose(i) \/ RebuildRequest(i)
  \/ \E K \in AllKeys : RebuildDeliver(K) \/ RecordDelivered(K) \/ RebuildSeen(K)
                        \/ RebuildRetry(K) \/ RebuildPark(K) \/ RebuildFailed(K)
  \/ TokenFree \/ ObserveOnly
  \/ \E c \in Causes : ClusterForm(c) \/ FixMerge(c) \/ CauseRecheck(c) \/ CausePark(c)
                       \/ OperatorEscalate(c) \/ RecordEscalated(c)
  \/ \E c \in Causes, w \in Workers : CauseDispatch(c, w)
  \/ \E w \in Workers : CauseSpawn(w) \/ CauseResult(w)

Next == Env \/ Controller \/ Bus

Spec == Init /\ [][Next]_vars

\* Weak fairness on every controller step and on the clock, the kill, the
\* producer's success and CI completing. Environment actions that change what
\* people do (pushes, holds, closes, blockers, crashes, producer failures) get
\* none: they are bounded by their budgets and may simply stop.
Fair ==
  /\ \A p \in PRs : WF_vars(ObserveHead(p)) /\ WF_vars(Land(p)) /\ WF_vars(TokenGrant(p))
                    /\ WF_vars(EligRerun(p)) /\ WF_vars(CoverRequest(p)) /\ WF_vars(CiResult(p))
                    /\ WF_vars(\E w \in Workers : Dispatch(p, w))
  /\ \A w \in Workers : WF_vars(RecordResult(w)) /\ WF_vars(Kill(w)) /\ WF_vars(Revoke(w))
                        /\ WF_vars(ConfirmTerminated(w)) /\ WF_vars(WorkerTimeout(w))
  /\ WF_vars(\E i \in CompIds : CompanionMerge(i)) /\ WF_vars(\E i \in CompIds : CompanionClose(i))
  /\ WF_vars(\E i \in CompIds : RebuildRequest(i)) /\ WF_vars(\E i \in CompIds : CompCi(i))
  \* One WF per rebuild step over all keys, not one per key: every key's steps
  \* are finite (attempts, deliveries and crashes are bounded), so no key can
  \* keep a step enabled forever and starve another; per-key fairness over
  \* SUBSET (PRs \X heads) made the liveness check intractable.
  /\ WF_vars(\E K \in AllKeys : RebuildDeliver(K)) /\ WF_vars(\E K \in AllKeys : RecordDelivered(K))
  /\ WF_vars(\E K \in AllKeys : RebuildSeen(K)) /\ WF_vars(\E K \in AllKeys : RebuildRetry(K))
  /\ WF_vars(\E K \in AllKeys : RebuildPark(K)) /\ WF_vars(\E K \in AllKeys : RebuildFailed(K))
  /\ WF_vars(\E K \in AllKeys : ProducerSucceed(K))
  /\ WF_vars(TokenFree)
  \* the red-PR fixer: every controller step, per cause and per worker
  /\ \A c \in Causes : WF_vars(ClusterForm(c)) /\ WF_vars(\E w \in Workers : CauseDispatch(c, w))
                       /\ WF_vars(FixMerge(c)) /\ WF_vars(CauseRecheck(c)) /\ WF_vars(CausePark(c))
                       /\ WF_vars(OperatorEscalate(c)) /\ WF_vars(RecordEscalated(c))
  /\ \A w \in Workers : WF_vars(CauseSpawn(w)) /\ WF_vars(CauseResult(w))

LiveSpec == Spec /\ Fair

-----------------------------------------------------------------------------
(* Properties (plan T3 prerequisite, P1-P9 and L1-L4, as written).         *)
TypeOK ==
  /\ head \in [PRs -> 1..MaxHead] /\ nd \in 0..MaxDispatch
  /\ \A s \in Subj : lease[s] = Nil \/ lease[s].id \in Ids \/ (BusLeased(s) /\ lease[s].id = 0)
  /\ \A w \in Workers : wp[w] \in Subj \cup {Nil}
  /\ \A c \in Causes : cfix[c] \in {"none", "open", "merged"}
  /\ fhold \subseteq Repos /\ pclaim \subseteq PRs /\ cclaim \subseteq Causes
  \* 2.2: a PR belongs to at most one formed cause
  /\ \A c1, c2 \in Causes : c1 # c2 /\ cform[c1] /\ cform[c2] => Mem(c1) \cap Mem(c2) = {}
  /\ \A w \in Workers : procAlive[w] \subseteq {"main", "child"}
  /\ \A p \in PRs : out[p].k \in Outcomes \cup {"none"}
  /\ token = Nil \/ token \in Runtime
  /\ \A c \in comps : c.id \in CompIds    \* MaxComps really bounds the ids

\* P1. At most one live worker per PR; live from dispatch until confirmed
\* terminated. Recording a result does not end liveness; a head change never
\* frees the slot.
\* Over every lease subject: a cause has at most one live worker too (2.4).
P1 == \A p \in Subj : Cardinality({w \in Workers : wp[w] = p /\ ~wconf[w]}) <= 1
\* P1 restated over real processes: never two workers' processes alive on one PR.
P1proc == \A p \in Subj : Cardinality({w \in Workers : wp[w] = p /\ procAlive[w] # {}}) <= 1

\* P2. One holder (by construction), freed before any other controller step
\* once its holder is merged, closed or dequeued (within one tick).
P2 == ~tlate

\* P3. Every dispatch reaches exactly one recorded outcome.
P3 == /\ \A i \in Ids : nout[i] <= 1
      /\ \A w \in Workers : wconf[w] => nout[wl[w]] = 1

P4 == ~bad.p4          \* a companion merges only with every member eligible and current
P5 == ~bad.p5          \* closed only when orphaned or superseded by a succeeded rebuild
P6 == ~bad.p6          \* no dispatch while blocked with the recorded fingerprint unchanged
\* P7. No dispatch in a draining repo; observe-only only with zero live workers.
P7 == /\ ~bad.p7
      /\ observe => (\A p \in Subj : lease[p] = Nil) /\ (\A w \in Workers : procAlive[w] = {})
P8 == ~bad.p8          \* a lease is released only with its worker's procAlive empty
\* P9. At most one companion per rebuild key, across retries, redeliveries and crashes.
P9 == \A K \in {c.key : c \in comps} : Cardinality({c \in comps : c.key = K}) <= 1

\* R1 supporting properties (revision 4, finding 3)
NoUnauth == ~bad.unauth          \* no fix_submitted accepted on a head no lease authorized
NoLegitRejected == ~bad.legit    \* a force-with-lease rebase under the lease is never rejected
NoUnverifiedLand == ~bad.pin     \* under a live lease, land only the verified head

\* The red-PR fixer (OMN-20414 AC1, plan 2.4).
\* P10. No per-PR dispatch for a member of a cause with a live lease, an open
\* fix PR or a park (the ticket names the first two; the plan adds the park).
P10 == ~bad.p10
\* P11. Cause dispatches per park episode stay within the budgets: counted
\* attempts <= Budget, spawn failures <= 3, and every concluded dispatch is
\* counted against one of them (or was revoked by a fixer HOLD), so dispatches
\* per episode <= Budget + 3.
P11 == \A c \in Causes :
         /\ catt[c] <= Budget /\ csf[c] <= SpawnFailBudget
         /\ cdisp[c] <= catt[c] + csf[c] + crev[c] + (IF lease[c] # Nil THEN 1 ELSE 0)
\* P12. No dispatch, cause or per-PR, in a repo under a fixer HOLD.
P12 == ~bad.p12
\* P13. Live workers per repo, live cause workers per repo and fleet-wide
\* within their caps (live: dispatched and not confirmed terminated).
LiveW(r) == {w \in Workers : wp[w] # Nil /\ ~wconf[w] /\ RepoOfS(wp[w]) = r}
P13 == /\ \A r \in Repos : /\ Cardinality(LiveW(r)) <= RepoCap
                          /\ Cardinality({w \in LiveW(r) : wp[w] \in Causes}) <= CauseRepoCap
       /\ Cardinality({w \in Workers : wp[w] \in Causes /\ ~wconf[w]}) <= CauseFleetCap
\* P14. At most one operator escalation MSG per park episode.
P14 == \A c \in Causes : nesc[c] <= 1

\* The bus owner (OMN-20744, plan S2).
\* PB1. One start per owner key (a PR head, or a cause), across runtime
\* restarts and redeliveries: a redelivered ci-run-failed for a decided head
\* starts nothing (the ticket's AC1).
PB1 == \A k \in DOMAIN nst : nst[k] <= 1
\* PB2. No PR-own bus start for a member of a cause the bus has claimed: the
\* cause absorbs its members' PR-own claims.
PB2 == ~bad.absorb
\* NoDual. Never a controller worker and a bus run live on one subject, and
\* neither writer starts on a PR whose cause the other holds (plan 5.2).
NoDual == /\ ~bad.dual
          /\ \A s \in Subj : ~(CtlLive(s) /\ s \in brun)

Safety == TypeOK /\ P1 /\ P1proc /\ P2 /\ P3 /\ P4 /\ P5 /\ P6 /\ P7 /\ P8 /\ P9
          /\ NoUnauth /\ NoLegitRejected /\ NoUnverifiedLand
          /\ P10 /\ P11 /\ P12 /\ P13 /\ P14
          /\ PB1 /\ PB2 /\ NoDual

\* L1. A green companion whose members are all eligible and at their stamped
\* heads is merged (the plan's "within 2 ticks" is the rule order: merge is the
\* first rule that applies to it; the model states the leads-to).
CReady(i) == \E c \in comps : c.id = i /\ c.open /\ c.ci = "green" /\ AllReady(c)
CMerged(i) == \E c \in comps : c.id = i /\ c.merged
L1 == \A i \in 1..MaxComps : CReady(i) ~> (CMerged(i) \/ ~CReady(i))

\* L2. Not blocked, no live worker, budget left: dispatched again after a
\* timeout or an invalid result.
Recover(p) == /\ Elig(p) /\ ci[p] = "red" /\ lease[p] = Nil /\ ~Blocked(p)
              /\ esc[p] < Engines /\ nd < MaxDispatch /\ (\E w \in Workers : wp[w] = Nil)
              /\ ~draining /\ out[p].k \in {"invalid", "timed_out"}
              /\ ~Owned(p) /\ ~Suppressed(p) /\ RepoOf(p) \notin fhold /\ CapPR(p)
L2 == \A p \in PRs : Recover(p) ~> (lease[p] # Nil \/ ~Recover(p))

\* L3. A verified fix_submitted head that goes green is merged or armed with
\* no new worker (Dispatch needs a red head, so no worker can be sent).
AwaitGreen(p) == /\ Elig(p) /\ ~Owned(p) /\ out[p].k = "fix_submitted" /\ awaitH[p] = head[p]
                 /\ ci[p] = "green"
L3 == \A p \in PRs : AwaitGreen(p) ~> (merged[p] \/ ~AwaitGreen(p))

\* L4. A rebuild request reaches succeeded when the producer eventually
\* succeeds (weak fairness on ProducerSucceed), crashes included.
Pending(K) == HasRec(K) /\ TheRec(K).st = "pending"
L4 == \A K \in AllKeys : Pending(K) ~> (HasRec(K) /\ TheRec(K).st = "succeeded")

\* R2 supporting liveness: an uncovered member eligible again is covered.
LCover == \A p \in PRs : (p \in unc /\ Elig(p)) ~> (p \notin unc \/ ~Elig(p))

\* L5. A formed, unheld, unparked, unowned cause with budget left reaches a
\* lease or a park when capacity is free (a free worker, a lease id, the caps).
CauseReady(c) ==
  /\ cform[c] /\ ~cpark[c] /\ lease[c] = Nil /\ cfix[c] = "none" /\ Present(c)
  /\ catt[c] < Budget /\ csf[c] < SpawnFailBudget
  /\ RepoOfS(c) \notin fhold /\ c \notin cclaim /\ ~draining
  /\ nd < MaxDispatch /\ (\E w \in Workers : wp[w] = Nil) /\ CapC(c)
L5 == \A c \in Causes : CauseReady(c) ~> (lease[c] # Nil \/ cpark[c] \/ ~CauseReady(c))

\* L6. A fixer HOLD on a repo leads to every lease there confirmed terminated
\* (or to the HOLD being lifted).
L6 == \A r \in Repos : r \in fhold ~> (r \notin fhold \/ LeasesIn(r) = {})

\* Supporting: a parked cause is escalated once (or released first).
LEsc == \A c \in Causes : cpark[c] ~> (nesc[c] >= 1 \/ ~cpark[c])

\* Symmetry sets for safety-only configs (never with liveness). Workers are
\* interchangeable; PRs are when Runtime and Collab are empty.
SymW  == Permutations(Workers)
SymPW == Permutations(Workers) \cup Permutations(PRs)

-----------------------------------------------------------------------------
(* Scenario reachability. Each NotS is checked as an invariant in its own  *)
(* cfg with Track = TRUE; its violation is the trace that reaches S.       *)
NotS1  == "S1" \notin hist
NotS2  == "S2" \notin hist
NotS3  == "S3" \notin hist
NotS4  == "S4" \notin hist
NotS5  == "S5" \notin hist
NotS6  == "S6" \notin hist
NotS7  == "S7" \notin hist
NotS8  == "S8" \notin hist
NotS9  == "S9" \notin hist
NotS10 == "S10" \notin hist
NotS11 == "S11" \notin hist
NotS12 == ~({"S12", "S12late"} \subseteq hist)
NotS12r == "S12r" \notin hist
NotS13 == "S13" \notin hist
NotS14 == "S14" \notin hist
NotS14b == "S14b" \notin hist
NotS15 == "S15" \notin hist
NotS16 == "S16" \notin hist
NotS17 == "S17" \notin hist
NotS18 == "S18" \notin hist
NotS18x == "S18x" \notin hist
NotS19 == "S19" \notin hist
NotS20 == "S20" \notin hist
\* the red-PR fixer, plan T1 S21 to S28
NotS21 == "S21" \notin hist
NotS22 == "S22" \notin hist
NotS23 == "S23" \notin hist
NotS24 == "S24" \notin hist
NotS25 == ~({"S25a", "S25b"} \subseteq hist)
NotS26 == "S26" \notin hist
NotS27 == "S27" \notin hist
NotS28 == "S28" \notin hist
\* the bus owner, OMN-20744
NotSB1 == "SB1" \notin hist
NotSB2 == "SB2" \notin hist
NotSB3 == "SB3" \notin hist
NotSB4 == "SB4" \notin hist
=============================================================================
