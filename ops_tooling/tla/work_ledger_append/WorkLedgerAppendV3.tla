--------------------------- MODULE WorkLedgerAppendV3 ---------------------------
(***************************************************************************)
(* Version 3 (task M2 of docs-repo                            *)
(* beta/plans/2026-09-28-work-ledger-on-the-bus.md, OMN-19386). v3 is v2    *)
(* (../WorkLedgerAppend.tla, unchanged) plus the stage-3 mechanism of plan  *)
(* section 5:                                                               *)
(*   - the emit leg after the lock (Emit): it may fail, it may duplicate a  *)
(*     confirmed event, and the parity repair replays any unconfirmed      *)
(*     buffered event by event_id (Replay);                                *)
(*   - the projection's confirmation of an event id (proj);                *)
(*   - the roll drops a closed event only when it is confirmed, and defers *)
(*     otherwise (RollConfirm);                                            *)
(*   - readers that fold projection plus local tail (ReaderA, ReaderB),    *)
(*     UNDECIDED with no buffer and no reachable projection.               *)
(* Every v2 knob, action and invariant is kept; v2's comments follow.      *)
(*                                                                         *)
(* Plan task T0 (OMN-19386, gate OMN-16176 AC-1) of docs-repo *)
(* beta/plans/2026-09-24-typed-work-ledger-on-disk-plan.md.                 *)
(*                                                                         *)
(* Version 2. v1 (v1/WorkLedgerAppend.tla, sha256 ed683e75...) was         *)
(* reviewed in REVIEW_VERDICT.md. v2 adds what that verdict required:      *)
(*   A1  ALREADY-PRESENT reads the live file plus the archives rolled at   *)
(*       or after the event's emitted_at (exact bound, MaxRolls = 2);      *)
(*   A2  whether a retry re-stamps emitted_at (new bytes) or replays the   *)
(*       original bytes;                                                   *)
(*   A3  the roll as temp file, archive write, rename, with a crash at     *)
(*       every step; the roll refused before the cutover epoch;            *)
(*   A4  fail closed when the live file is missing;                        *)
(*   the reviewer's hold-verb disarm (HoldDisarm).                         *)
(* A5 (torn tail) is not modelled: a line append stays atomic here.        *)
(*                                                                         *)
(* Every design choice is a CONSTANT, so each invariant has a              *)
(* configuration in which it is expected to fail (the positive controls). *)
(* See README.md for the run matrix.                                       *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    WriteOrder,           \* "jsonl_first" (plan 5.2 steps 5 then 6) | "md_first" (control)
    IdemScope,            \* which files step 2 (ALREADY-PRESENT) reads, see IdemRecs
    RetryRestamp,         \* TRUE: a retry re-stamps emitted_at, so its bytes differ (A2 absent)
    EpochChecksOffset,    \* TRUE: epoch append refuses legacy rows after the review offset (6.2)
    LegacyCheckUnderLock, \* TRUE: the legacy --append reads the epoch under the lock (T9)
    RollMode,             \* "atomic" | "tmp_rename" (A3) | "visible_gap" | "move_then_create"
    RollNeedsCutover,     \* TRUE: the roll refuses to run before the cutover epoch (A3)
    FailClosedMissing,    \* TRUE: a missing live file refuses typed and legacy appends (A4)
    RecheckMode,          \* "none" | "pre_verb" | "pre_verb_and_post_arm" (5.3, T12 AC3)
    HoldDisarm,           \* TRUE: the PR hold's verb disarms the armed PR before exit 0 (verdict T8.1)
    LaneOn,               \* FALSE: the PR lane never moves (the append-invariant runs; it only reads)
    MaxCrashes,
    MaxLegacy,            \* at most 3
    MaxRolls,             \* 0..2
    \* ---- v3 (plan section 5, stage 3) ----
    RollConfirm,          \* "defer" (adopted): roll only when every event it drops is confirmed
                          \* "carry_unconfirmed": keep each unconfirmed closed event in the new file
                          \* "none" (control): the roll ignores the projection (v2's roll)
    ReaderTail,           \* TRUE: the reader folds projection plus local tail; FALSE (control): projection only
    ReaderNoSource        \* "undecided" (adopted): no buffer and no projection answers UNDECIDED
                          \* "md_fallback" (control): it folds a published, possibly stale md copy

ASSUME RollConfirm \in {"defer", "carry_unconfirmed", "none"}
ASSUME ReaderTail \in BOOLEAN
ASSUME ReaderNoSource \in {"undecided", "md_fallback"}
ASSUME WriteOrder \in {"jsonl_first", "md_first"}
ASSUME IdemScope \in {"live", "live_and_all_archives", "live_and_archives_since_emit",
                      "live_and_last_archive", "none"}
ASSUME RetryRestamp \in BOOLEAN /\ EpochChecksOffset \in BOOLEAN
ASSUME LegacyCheckUnderLock \in BOOLEAN /\ RollNeedsCutover \in BOOLEAN
ASSUME FailClosedMissing \in BOOLEAN /\ HoldDisarm \in BOOLEAN /\ LaneOn \in BOOLEAN
ASSUME RollMode \in {"atomic", "tmp_rename", "visible_gap", "move_then_create"}
ASSUME RecheckMode \in {"none", "pre_verb", "pre_verb_and_post_arm"}
ASSUME MaxCrashes \in Nat /\ MaxLegacy \in 0..3 /\ MaxRolls \in 0..2

Writers   == {"w1", "w2", "w3"}
Appenders == Writers \cup {"cutover"}
Procs     == Appenders \cup {"legacy", "roller"}

EvOf(p) == CASE p = "w1" -> "e1"
             [] p = "w2" -> "e2"
             [] p = "w3" -> "e3"
             [] p = "cutover" -> "ep0"

EpOfRoll(i) == CASE i = 1 -> "ep1" [] i = 2 -> "ep2"

\* A JSONL record. target is what a hold holds; ref is what a release names.
\* att stands for the bytes that differ between attempts (emitted_at): two
\* records with one id and different att are the "same id, different content"
\* case of plan 5.2 step 3.3.
RecOf(e, a) ==
    CASE e = "e1" -> [id |-> "e1", kind |-> "hold",    ref |-> "none", target |-> "pr",      att |-> a]
      [] e = "e2" -> [id |-> "e2", kind |-> "release", ref |-> "e1",   target |-> "none",    att |-> a]
      [] e = "e3" -> [id |-> "e3", kind |-> "hold",    ref |-> "none", target |-> "surface", att |-> a]
      [] OTHER    -> [id |-> e,    kind |-> "epoch",   ref |-> "none", target |-> "none",    att |-> a]

LegId(n) == CASE n = 0 -> "L1" [] n = 1 -> "L2" [] n = 2 -> "L3"

VARIABLES
    lock,         \* "none" or the holding process
    jsonl,        \* live ROLLING_WORK_LEDGER.jsonl, a sequence of records
    present,      \* the live file exists
    archives,     \* archive files in roll order, each a sequence of records
    md,           \* ROLLING_WORK_LEDGER.md rows: [id, legacy]
    pc,           \* per-process program counter
    stamp,        \* per appender: number of completed rolls when emitted_at was stamped
    att,          \* per appender: which stamping of its event this is
    acked,        \* event ids whose append exited 0
    conflicts,    \* event ids whose own retry exited 65
    crashes,
    reviewOffset, \* md length when the cutover review list was generated
    epochOffset,  \* the offset the epoch append accepted (0 until then)
    legacyCount,
    rolls,        \* completed (or, for move_then_create, started) rolls
    rollTmp,      \* the roller's temporary file / carry buffer
    carried,      \* ids carried by a roll (duplicates across files that are legitimate)
    prPc,         \* PR lane
    heldSince,    \* lane phase when the PR hold last became visible in the live JSONL
    missed,       \* <<phase, hold acked?>> for each merge that missed a visible hold
    proj          \* v3: the records the lab projection has folded (work_ledger_rows);
                  \*     an event is CONFIRMED when its id is here

vars == <<lock, jsonl, present, archives, md, pc, stamp, att, acked, conflicts, crashes,
          reviewOffset, epochOffset, legacyCount, rolls, rollTmp, carried,
          prPc, heldSince, missed, proj>>

-----------------------------------------------------------------------------
RECURSIVE CatAll(_)
CatAll(s) == IF s = << >> THEN << >> ELSE Head(s) \o CatAll(Tail(s))

Recs(S)  == {S[i] : i \in DOMAIN S}
Ids(S)   == {S[i].id : i \in DOMAIN S}
Count(S, e) == Cardinality({i \in DOMAIN S : S[i].id = e})
MdIds    == {md[i].id : i \in DOMAIN md}
AllArch  == CatAll(archives)
\* archives of completed rolls (a crashed tmp_rename roll can leave one more slot)
DoneArch == IF Len(archives) > rolls THEN CatAll(SubSeq(archives, 1, rolls)) ELSE AllArch

\* Set-based fold (plan 5.3): a hold is open unless a release naming it exists.
\* v3: the fold is written over a SET of records (core fold_work_events is
\* set-based: order-free, identical duplicates count once, a release naming an
\* unknown id releases nothing). The v2 sequence forms apply it to Recs(S).
OpenHoldsR(R) == {r.id : r \in {x \in R :
                    x.kind = "hold" /\ ~\E y \in R : y.kind = "release" /\ y.ref = x.id}}
HeldR(R)      == "e1" \in OpenHoldsR(R)
EpochInR(R)   == \E r \in R : r.kind = "epoch"
OpenHolds(S) == OpenHoldsR(Recs(S))
Held(S)      == HeldR(Recs(S))
EpochIn(S)   == EpochInR(Recs(S))
CutoverDone  == "ep0" \in Ids(jsonl) \cup Ids(AllArch)

MyRec(p) == RecOf(EvOf(p), att[p])

\* What step 2 reads before deciding ALREADY-PRESENT / conflict / write.
IdemRecs(p) ==
    CASE IdemScope = "live" -> Recs(jsonl)                       \* plan 5.2 step 2 as written
      [] IdemScope = "live_and_all_archives" -> Recs(jsonl) \cup Recs(AllArch)
      [] IdemScope = "live_and_archives_since_emit" ->             \* A1
             Recs(jsonl) \cup UNION {Recs(archives[i]) : i \in {j \in DOMAIN archives : j > stamp[p]}}
      [] IdemScope = "live_and_last_archive" ->                    \* control for A1's bound
             Recs(jsonl) \cup (IF archives = << >> THEN {} ELSE Recs(archives[Len(archives)]))
      [] IdemScope = "none" -> {}                                  \* control: no step 2

FirstWrite == IF WriteOrder = "jsonl_first" THEN "write_jsonl" ELSE "write_md"
After(step) == IF WriteOrder = "jsonl_first"
               THEN (IF step = "write_jsonl" THEN "write_md" ELSE "release")
               ELSE (IF step = "write_md" THEN "write_jsonl" ELSE "release")

\* ---- v3: emit, confirmation, and what a roll may drop ----
\* Events that ride the bus: the typed holds and releases and the cutover
\* epoch ep0 (plan section 14 decision 3, recommended). A roll's own epoch
\* record (ep1, ep2) stays local to the buffer and is never emitted.
Emittable(r) == r.kind \in {"hold", "release"} \/ r.id = "ep0"
ProjIds      == {r.id : r \in proj}

\* v2 carried the open holds. v3 "carry_unconfirmed" also keeps every
\* unconfirmed emittable event in the new file (an alternative to deferring).
CarrySeq(S) == SelectSeq(S, LAMBDA r :
                   \/ r.kind = "hold" /\ r.id \in OpenHolds(S)
                   \/ RollConfirm = "carry_unconfirmed" /\ Emittable(r) /\ r.id \notin ProjIds)
\* what a roll of S removes from the live file
Dropped(S)        == Recs(S) \ Recs(CarrySeq(S))
\* plan section 5, Roll: a closed event leaves the live file only if confirmed
DropsConfirmed(S) == \A r \in Dropped(S) : Emittable(r) => r.id \in ProjIds

LanePhase == CASE prPc = "start"  -> "before_first_check"
               [] prPc = "c1done" -> "after_check1"
               [] prPc = "c2done" -> "after_check2"
               [] prPc = "armed"  -> "after_arm"
               [] prPc = "c3done" -> "after_check3"
               [] OTHER           -> "lane_finished"

-----------------------------------------------------------------------------
\* History variable, conjoined to every action: the lane phase at the moment
\* the PR hold became visible in the live JSONL.
HU == heldSince' = IF ~Held(jsonl') THEN "none"
                   ELSE IF Held(jsonl) THEN heldSince
                   ELSE LanePhase

Init ==
    /\ lock = "none"
    /\ jsonl = << >>
    /\ present = TRUE
    /\ archives = << >>
    /\ md = << >>
    /\ pc = [p \in Procs |-> CASE p \in Writers -> "fresh"
                               [] p = "cutover" -> "gen"
                               [] p = "legacy"  -> "idle"
                               [] p = "roller"  -> "idle"]
    /\ stamp = [p \in Appenders |-> 0]
    /\ att = [p \in Appenders |-> 1]
    /\ acked = {}
    /\ conflicts = {}
    /\ crashes = 0
    /\ reviewOffset = 0
    /\ epochOffset = 0
    /\ legacyCount = 0
    /\ rolls = 0
    /\ rollTmp = << >>
    /\ carried = {}
    /\ prPc = "start"
    /\ heldSince = "none"
    /\ missed = {}
    /\ proj = {}

LaneVars == <<prPc, missed>>
FileVars == <<jsonl, present, archives, md>>
MiscVars == <<stamp, att, acked, conflicts, crashes, reviewOffset, epochOffset,
              legacyCount, rolls, rollTmp, carried>>

\* ---- typed append (plan 5.2 step 3), shared by the writers and the cutover ----
\* step 3.1: event_id and emitted_at are assigned before the lock
Stamp(p) ==
    /\ p \in Writers
    /\ pc[p] = "fresh"
    /\ stamp' = [stamp EXCEPT ![p] = rolls]
    /\ pc' = [pc EXCEPT ![p] = "idle"]
    /\ UNCHANGED <<lock, att, acked, conflicts, crashes, reviewOffset, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

Acquire(p) ==
    /\ p \in Writers
    /\ pc[p] = "idle"
    /\ lock = "none"
    \* the releasing lane releases a hold it has seen
    /\ p = "w2" => "e1" \in Ids(jsonl) \cup Ids(AllArch)
    /\ lock' = p
    /\ pc' = [pc EXCEPT ![p] = "check"]
    /\ UNCHANGED MiscVars /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

RetryPc(p) == IF p = "cutover" THEN "wait" ELSE "idle"

\* steps 2 and 3. A4: a missing live file is refused, the lane retries later.
Check(p) ==
    /\ pc[p] = "check"
    /\ LET S == IdemRecs(p) IN
       IF FailClosedMissing /\ ~present THEN
              /\ lock' = "none"
              /\ pc' = [pc EXCEPT ![p] = RetryPc(p)]
              /\ UNCHANGED conflicts
       ELSE IF MyRec(p) \in S THEN                              \* ALREADY-PRESENT
              /\ pc' = [pc EXCEPT ![p] = "ensure_md"]
              /\ UNCHANGED <<lock, conflicts>>
       ELSE IF \E x \in S : x.id = EvOf(p) THEN                 \* exit 65
              /\ lock' = "none"
              /\ pc' = [pc EXCEPT ![p] = "conflict"]
              /\ conflicts' = conflicts \cup {EvOf(p)}
       ELSE
              /\ pc' = [pc EXCEPT ![p] = FirstWrite]
              /\ UNCHANGED <<lock, conflicts>>
    /\ UNCHANGED <<stamp, att, acked, crashes, reviewOffset, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* without A4 a missing live file is created by the append
WriteJsonl(p) ==
    /\ pc[p] = "write_jsonl"
    /\ jsonl' = Append(jsonl, MyRec(p))
    /\ present' = TRUE
    /\ pc' = [pc EXCEPT ![p] = After("write_jsonl")]
    /\ UNCHANGED <<lock, archives, md>> /\ UNCHANGED MiscVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

MdAppendIfAbsent(e) ==
    md' = IF e \in MdIds THEN md ELSE Append(md, [id |-> e, legacy |-> FALSE])

WriteMd(p) ==
    /\ pc[p] = "write_md"
    /\ MdAppendIfAbsent(EvOf(p))
    /\ pc' = [pc EXCEPT ![p] = After("write_md")]
    /\ UNCHANGED <<lock, jsonl, present, archives>> /\ UNCHANGED MiscVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

EnsureMd(p) ==
    /\ pc[p] = "ensure_md"
    /\ MdAppendIfAbsent(EvOf(p))
    /\ pc' = [pc EXCEPT ![p] = "release"]
    /\ UNCHANGED <<lock, jsonl, present, archives>> /\ UNCHANGED MiscVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* exit 0: the only place an append is acknowledged. With HoldDisarm the PR
\* hold's verb disarms the armed PR before it exits 0 (verdict T8.1).
Release(p) ==
    /\ pc[p] = "release"
    /\ lock' = "none"
    /\ acked' = acked \cup {EvOf(p)}
    /\ pc' = [pc EXCEPT ![p] = "emit"]     \* v3: the emit runs after the lock (plan section 5)
    /\ prPc' = IF p = "w1" /\ HoldDisarm /\ prPc \in {"armed", "c3done"} THEN "disarmed" ELSE prPc
    /\ UNCHANGED <<stamp, att, conflicts, crashes, reviewOffset, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED missed
    /\ HU /\ UNCHANGED proj

\* The process dies while holding the lock; the kernel drops the fcntl lock.
\* The lane retries the same event_id later. With RetryRestamp the retry
\* stamps emitted_at again (new bytes); otherwise it replays the original.
Crash(p) ==
    /\ p \in Appenders
    /\ lock = p
    /\ pc[p] \in {"check", "write_jsonl", "write_md", "ensure_md", "release", "offset_check"}
    /\ crashes < MaxCrashes
    /\ lock' = "none"
    /\ crashes' = crashes + 1
    /\ pc' = [pc EXCEPT ![p] = IF p = "cutover" THEN "wait"
                                ELSE IF RetryRestamp THEN "fresh" ELSE "idle"]
    /\ att' = IF RetryRestamp /\ p # "cutover" THEN [att EXCEPT ![p] = att[p] + 1] ELSE att
    /\ UNCHANGED <<stamp, acked, conflicts, reviewOffset, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* render --repair: one missing md row per step, while the lock is free
Repair ==
    /\ lock = "none"
    /\ \E r \in Recs(jsonl) \cup Recs(AllArch) :
          /\ r.id \notin MdIds
          /\ md' = Append(md, [id |-> r.id, legacy |-> FALSE])
    /\ UNCHANGED <<lock, jsonl, present, archives, pc>> /\ UNCHANGED MiscVars
    /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* ---- v3: the emit leg and the projection (plan section 5, stage 3) ----
\* Emit(p): after exit 0 and after the lock is released, the detached emit
\* publishes the appender's own event. It can fail (nothing is confirmed and
\* the failure is logged); a publish of an already-confirmed event is a
\* duplicate and changes nothing (the projection is keyed by event id).
\* The bus and the projection's fold are collapsed into one step: an event is
\* confirmed when this step adds it. Delivery order and redelivery are covered
\* because Emit and Replay can fire in any order, any number of times, and the
\* fold is a set function (M3's property test is the evidence for the real
\* projection writer).
Emit(p) ==
    /\ p \in Appenders
    /\ pc[p] = "emit"
    /\ \/ proj' = proj \cup {MyRec(p)}      \* published and folded
       \/ UNCHANGED proj                    \* failed: the lab or the network is down
    /\ pc' = [pc EXCEPT ![p] = "done"]
    /\ UNCHANGED <<lock, stamp, att, acked, conflicts, crashes, reviewOffset, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU

\* Replay: the parity check's repair mode re-publishes any unconfirmed event
\* it finds in the buffer (live file or an archive), keyed by event id. It reads
\* without the lock, like every other reader of the buffer.
Replay ==
    /\ \E r \in Recs(jsonl) \cup Recs(AllArch) :
          /\ Emittable(r)
          /\ r.id \notin ProjIds
          /\ proj' = proj \cup {r}
    /\ UNCHANGED <<lock, pc>> /\ UNCHANGED MiscVars /\ UNCHANGED FileVars
    /\ UNCHANGED LaneVars
    /\ HU

-----------------------------------------------------------------------------
\* ---- v3: readers (plan sections 0, 6 and 13) ----
\* A reader folds a set of records with the one pure fold and answers
\* UNDECIDED with no epoch (core: NO_EPOCH_REASON), HELD when the PR hold e1 is
\* open, CLEAR otherwise.
Answer(R) == IF ~EpochInR(R) THEN "UNDECIDED" ELSE IF HeldR(R) THEN "HELD" ELSE "CLEAR"

\* the local tail: this host's buffered events the projection has not confirmed
LocalTail == IF ReaderTail THEN {r \in Recs(jsonl) : r.id \notin ProjIds} ELSE {}

\* A published copy of the md that lags the live md: its first k rows
\* (ledger_publish.py pushes the md on a timer).
MdPrefixRecs(k) == {RecOf(md[i].id, 1) : i \in {j \in 1..k : ~md[j].legacy}}

\* the answer of a reader that has neither a buffer nor a reachable projection
NoSourceAnswers == IF ReaderNoSource = "undecided" THEN {"UNDECIDED"}
                   ELSE {Answer(MdPrefixRecs(k)) : k \in 0..Len(md)}

\* Reader A runs on the writing host (it has the buffer). up = the projection
\* is reachable. With it: projection plus local tail; a missing live file does
\* not block it (A4 as amended). Without it: the live buffer alone, which is
\* complete for this host's writes.
ReaderAAnswers(up) ==
    IF up THEN {Answer(proj \cup (IF present THEN LocalTail ELSE {}))}
    ELSE IF present THEN {Answer(Recs(jsonl))}
    ELSE NoSourceAnswers

\* Reader B runs on another host: no buffer, only the projection.
ReaderBAnswers(up) == IF up THEN {Answer(proj)} ELSE NoSourceAnswers

\* The truth: the fold of every record ever appended to the buffer (the
\* archives keep every rolled file, so this is the whole log).
TrueHeld == Held(AllArch \o jsonl)

-----------------------------------------------------------------------------
\* ---- cutover (plan 6) ----
GenList ==
    /\ pc["cutover"] = "gen"
    /\ reviewOffset' = Len(md)
    /\ pc' = [pc EXCEPT !["cutover"] = "wait"]
    /\ UNCHANGED <<lock, stamp, att, acked, conflicts, crashes, epochOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

CutAcquire ==
    /\ pc["cutover"] = "wait"
    /\ lock = "none"
    /\ lock' = "cutover"
    /\ pc' = [pc EXCEPT !["cutover"] = "offset_check"]
    /\ UNCHANGED MiscVars /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

OffsetCheck ==
    /\ pc["cutover"] = "offset_check"
    /\ IF EpochChecksOffset /\ \E i \in (reviewOffset + 1)..Len(md) : md[i].legacy
       THEN /\ lock' = "none"
            /\ pc' = [pc EXCEPT !["cutover"] = "gen"]   \* regenerate the list
            /\ UNCHANGED epochOffset
       ELSE /\ pc' = [pc EXCEPT !["cutover"] = "check"]
            /\ epochOffset' = reviewOffset
            /\ UNCHANGED lock
    /\ UNCHANGED <<stamp, att, acked, conflicts, crashes, reviewOffset,
                   legacyCount, rolls, rollTmp, carried>>
    /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* ---- legacy ledger_lock --append of a decision row ----
LegacyAppend ==
    /\ md' = Append(md, [id |-> LegId(legacyCount), legacy |-> TRUE])
    /\ legacyCount' = legacyCount + 1

LegacyUnderLock ==
    /\ LegacyCheckUnderLock
    /\ pc["legacy"] = "idle"
    /\ legacyCount < MaxLegacy
    /\ lock = "none"
    /\ lock' = "legacy"
    /\ pc' = [pc EXCEPT !["legacy"] = "l_locked"]
    /\ UNCHANGED MiscVars /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* A4: with FailClosedMissing a missing live file refuses; otherwise it reads as "no epoch"
LegacyLockedStep ==
    /\ pc["legacy"] = "l_locked"
    /\ lock' = "none"
    /\ CASE FailClosedMissing /\ ~present ->
              /\ pc' = [pc EXCEPT !["legacy"] = "idle"]
              /\ UNCHANGED <<md, legacyCount>>
         [] EpochIn(jsonl) ->
              /\ pc' = [pc EXCEPT !["legacy"] = "l_done"]      \* exit 65
              /\ UNCHANGED <<md, legacyCount>>
         [] OTHER ->
              /\ LegacyAppend
              /\ pc' = [pc EXCEPT !["legacy"] = "idle"]
    /\ UNCHANGED <<jsonl, present, archives, stamp, att, acked, conflicts, crashes,
                   reviewOffset, epochOffset, rolls, rollTmp, carried>>
    /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* control: the epoch is read before the lock is taken
LegacyPrecheck ==
    /\ ~LegacyCheckUnderLock
    /\ pc["legacy"] = "idle"
    /\ legacyCount < MaxLegacy
    /\ pc' = [pc EXCEPT !["legacy"] = IF EpochIn(jsonl) THEN "l_done" ELSE "l_prechecked"]
    /\ UNCHANGED <<lock>> /\ UNCHANGED MiscVars /\ UNCHANGED FileVars /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

LegacyPrecheckedAppend ==
    /\ pc["legacy"] = "l_prechecked"
    /\ lock = "none"
    /\ LegacyAppend
    /\ pc' = [pc EXCEPT !["legacy"] = "idle"]
    /\ UNCHANGED <<lock, jsonl, present, archives, stamp, att, acked, conflicts, crashes,
                   reviewOffset, epochOffset, rolls, rollTmp, carried>>
    /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* ---- roll with carry (plan 5.2 step 6) ----
RollGuard ==
    /\ pc["roller"] = "idle"
    /\ lock = "none"
    /\ present
    /\ rolls < MaxRolls
    /\ RollNeedsCutover => CutoverDone
    \* v3: the roll defers while any event it would drop is unconfirmed; an
    \* unreachable projection confirms nothing, so it defers too
    /\ RollConfirm = "defer" => DropsConfirmed(jsonl)

RollUnch == UNCHANGED <<md, stamp, att, acked, conflicts, crashes, reviewOffset,
                        epochOffset, legacyCount>> /\ UNCHANGED LaneVars

\* archive slot rolls+1: a crashed tmp_rename roll may already have written it
WriteArchiveSlot ==
    archives' = IF Len(archives) > rolls THEN [archives EXCEPT ![rolls + 1] = jsonl]
                ELSE Append(archives, jsonl)

\* "atomic": one step, the v1 abstraction
RollAtomicStep ==
    /\ RollMode = "atomic"
    /\ RollGuard
    /\ WriteArchiveSlot
    /\ jsonl' = <<RecOf(EpOfRoll(rolls + 1), 1)>> \o CarrySeq(jsonl)
    /\ carried' = carried \cup Ids(CarrySeq(jsonl))
    /\ rolls' = rolls + 1
    /\ UNCHANGED <<lock, present, pc, rollTmp>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

\* "tmp_rename" (A3): build the new file with its carry in a temporary file,
\* write the archive, then rename the temporary file over the live path.
\* "visible_gap" (control): the new file is visible before its carry is copied.
\* "move_then_create" (control): the live file is moved to the archive first,
\* so a crash leaves no live file.
RollStart ==
    /\ RollMode # "atomic"
    /\ RollGuard
    /\ lock' = "roller"
    /\ CASE RollMode = "tmp_rename" ->
              /\ rollTmp' = <<RecOf(EpOfRoll(rolls + 1), 1)>> \o CarrySeq(jsonl)
              /\ pc' = [pc EXCEPT !["roller"] = "r_archive"]
              /\ UNCHANGED <<jsonl, present, archives, rolls, carried>>
         [] RollMode = "visible_gap" ->
              /\ WriteArchiveSlot
              /\ rollTmp' = CarrySeq(jsonl)
              /\ carried' = carried \cup Ids(CarrySeq(jsonl))
              /\ jsonl' = <<RecOf(EpOfRoll(rolls + 1), 1)>>
              /\ rolls' = rolls + 1
              /\ pc' = [pc EXCEPT !["roller"] = "r_copy"]
              /\ UNCHANGED present
         [] RollMode = "move_then_create" ->
              /\ WriteArchiveSlot
              /\ jsonl' = << >>
              /\ present' = FALSE
              /\ rolls' = rolls + 1
              /\ pc' = [pc EXCEPT !["roller"] = "r_create"]
              /\ UNCHANGED <<rollTmp, carried>>
    /\ RollUnch
    /\ HU /\ UNCHANGED proj

RollArchive ==
    /\ pc["roller"] = "r_archive"
    /\ WriteArchiveSlot
    /\ pc' = [pc EXCEPT !["roller"] = "r_rename"]
    /\ UNCHANGED <<lock, jsonl, present, rolls, rollTmp, carried>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

RollRename ==
    /\ pc["roller"] = "r_rename"
    /\ jsonl' = rollTmp
    \* v3: the carry follows the roll's epoch record (Head); v2 took the
    \* non-epoch records, which is the same set when only holds are carried
    /\ carried' = carried \cup Ids(Tail(rollTmp))
    /\ rollTmp' = << >>
    /\ rolls' = rolls + 1
    /\ lock' = "none"
    /\ pc' = [pc EXCEPT !["roller"] = "idle"]
    /\ UNCHANGED <<present, archives>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

RollCopy ==
    /\ pc["roller"] = "r_copy"
    /\ jsonl' = jsonl \o rollTmp
    /\ rollTmp' = << >>
    /\ lock' = "none"
    /\ pc' = [pc EXCEPT !["roller"] = "idle"]
    /\ UNCHANGED <<present, archives, rolls, carried>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

\* move_then_create: create the new live file from the last archive
RollCreate ==
    /\ pc["roller"] = "r_create"
    /\ jsonl' = <<RecOf(EpOfRoll(rolls), 1)>> \o CarrySeq(archives[Len(archives)])
    /\ carried' = carried \cup Ids(CarrySeq(archives[Len(archives)]))
    /\ present' = TRUE
    /\ lock' = "none"
    /\ pc' = [pc EXCEPT !["roller"] = "idle"]
    /\ UNCHANGED <<archives, rolls, rollTmp>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

\* recovery after a crash left no live file: finish the create
RollRecover ==
    /\ RollMode = "move_then_create"
    /\ pc["roller"] = "idle"
    /\ lock = "none"
    /\ ~present
    /\ lock' = "roller"
    /\ pc' = [pc EXCEPT !["roller"] = "r_create"]
    /\ UNCHANGED <<jsonl, present, archives, rolls, rollTmp, carried>> /\ RollUnch
    /\ HU /\ UNCHANGED proj

RollCrash ==
    /\ lock = "roller"
    /\ pc["roller"] \in {"r_archive", "r_rename", "r_copy", "r_create"}
    /\ crashes < MaxCrashes
    /\ lock' = "none"
    /\ crashes' = crashes + 1
    /\ pc' = [pc EXCEPT !["roller"] = "idle"]
    /\ rollTmp' = << >>        \* the temporary file is discarded
    /\ UNCHANGED <<jsonl, present, archives, md, stamp, att, acked, conflicts, reviewOffset,
                   epochOffset, legacyCount, rolls, carried>> /\ UNCHANGED LaneVars
    /\ HU /\ UNCHANGED proj

\* ---- the PR lane and GitHub (plan 5.3 check-then-act, T12 AC3) ----
\* v2: the checker read the live JSONL without the lock; a missing file, or no
\* epoch, was UNDECIDED (exit 2), which the lane treats as held.
\* v3: the lane runs on the writing host and asks reader A with the projection
\* reachable (projection plus local tail). Anything but CLEAR blocks.
Blocked == ReaderAAnswers(TRUE) # {"CLEAR"}

LaneUnchanged == UNCHANGED <<lock, pc>> /\ UNCHANGED MiscVars /\ UNCHANGED FileVars

Check1 ==
    /\ LaneOn
    /\ prPc = "start"
    /\ present /\ EpochIn(jsonl)       \* before the cutover the lane waits
    /\ prPc' = IF Blocked THEN "stopped" ELSE "c1done"
    /\ UNCHANGED missed /\ LaneUnchanged
    /\ HU /\ UNCHANGED proj

Check2 ==
    /\ RecheckMode \in {"pre_verb", "pre_verb_and_post_arm"}
    /\ prPc = "c1done"
    /\ prPc' = IF Blocked THEN "stopped" ELSE "c2done"
    /\ UNCHANGED missed /\ LaneUnchanged
    /\ HU /\ UNCHANGED proj

Arm ==
    /\ \/ RecheckMode = "none" /\ prPc = "c1done"
       \/ RecheckMode # "none" /\ prPc = "c2done"
    /\ prPc' = "armed"
    /\ UNCHANGED missed /\ LaneUnchanged
    /\ HU /\ UNCHANGED proj

Check3 ==
    /\ RecheckMode = "pre_verb_and_post_arm"
    /\ prPc = "armed"
    /\ prPc' = IF Blocked THEN "disarmed" ELSE "c3done"
    /\ UNCHANGED missed /\ LaneUnchanged
    /\ HU /\ UNCHANGED proj

\* auto-merge fires whenever CI is green: any time after the arm, until disarmed
GitHubMerge ==
    /\ prPc \in {"armed", "c3done"}
    /\ prPc' = "merged"
    /\ missed' = IF Held(jsonl) THEN missed \cup {<<heldSince, "e1" \in acked>>} ELSE missed
    /\ LaneUnchanged
    /\ HU /\ UNCHANGED proj

-----------------------------------------------------------------------------
Next ==
    \/ \E p \in Writers : Stamp(p) \/ Acquire(p)
    \/ \E p \in Appenders : Check(p) \/ WriteJsonl(p) \/ WriteMd(p) \/ EnsureMd(p)
                            \/ Release(p) \/ Crash(p)
    \/ Repair
    \/ GenList \/ CutAcquire \/ OffsetCheck
    \/ LegacyUnderLock \/ LegacyLockedStep \/ LegacyPrecheck \/ LegacyPrecheckedAppend
    \/ RollAtomicStep \/ RollStart \/ RollArchive \/ RollRename \/ RollCopy
    \/ RollCreate \/ RollRecover \/ RollCrash
    \/ Check1 \/ Check2 \/ Arm \/ Check3 \/ GitHubMerge
    \/ \E p \in Appenders : Emit(p)
    \/ Replay

Spec == Init /\ [][Next]_vars

-----------------------------------------------------------------------------
TypeOK ==
    /\ lock \in Procs \cup {"none"}
    /\ crashes \in 0..MaxCrashes
    /\ legacyCount \in 0..MaxLegacy
    /\ rolls \in 0..MaxRolls
    /\ Len(archives) \in rolls..(rolls + 1)
    /\ acked \subseteq {"e1", "e2", "e3", "ep0"}
    /\ conflicts \subseteq {"e1", "e2", "e3", "ep0"}
    /\ \A r \in proj : Emittable(r)

\* (1) an exit-0 append has its event_id in the ledger, once per file
NoLostAck ==
    \A e \in acked :
        /\ e \in Ids(jsonl) \cup Ids(AllArch)
        /\ Count(jsonl, e) <= 1
        /\ \A i \in DOMAIN archives : Count(archives[i], e) <= 1

\* (2) every typed md row has its event in the JSONL (live or archived)
MdNeverAhead ==
    \A i \in DOMAIN md : ~md[i].legacy => md[i].id \in Ids(jsonl) \cup Ids(AllArch)

\* (3) once the epoch is in the JSONL, no legacy decision row sits past the
\*     offset the reviewed list covered
NoLegacyDecisionAfterEpoch ==
    CutoverDone => \A i \in DOMAIN md : md[i].legacy => i <= epochOffset

\* (4) fold(archive u live) = fold(live) for the decision the checker makes,
\*     whenever the checker can read a live file
RollPreservesOpen ==
    present => OpenHolds(jsonl) = OpenHolds(AllArch \o jsonl)

\* (5) A2: a lane's retry of its own event never exits 65
NoSpuriousConflict == conflicts = {}

\* (6) A3: no epoch record exists before the reviewed cutover epoch
NoEpochBeforeCutover ==
    (EpochIn(jsonl) \/ EpochIn(AllArch)) => CutoverDone

\* an event is in the live file and a completed archive only because a roll carried it
NoDuplicateOutsideCarry ==
    \A e \in Ids(jsonl) \cap Ids(DoneArch) : e \in carried

\* expected to FAIL in every RecheckMode: the residual check-then-act window
NoMergeWhileHeld == missed = {}

\* the same as MdNeverAhead, only when no process holds the lock
MdNeverAheadAtRest == lock = "none" => MdNeverAhead

-----------------------------------------------------------------------------
\* ---- v3 invariants (plan section 5 stage 3, section 9 A4 and S1) ----

\* (7) Roll: an event that exists only in an archive (a roll dropped it from
\*     the live file) is confirmed in the projection. Equivalently: a lost disk
\*     loses only the live file's unconfirmed tail, never a rolled event
\*     (the intent of S1, "no closed event only in an archive on one disk").
DropOnlyConfirmed ==
    \A r \in Recs(AllArch) : Emittable(r) /\ r.id \notin Ids(jsonl) => r.id \in ProjIds

\* (8) Reader A (the writing host) never answers CLEAR while the PR hold is in
\*     force, whether the projection is reachable or not. A hold placed here
\*     and not yet confirmed counts.
LocalReaderSeesOwnHold ==
    \A up \in BOOLEAN : "CLEAR" \in ReaderAAnswers(up) => ~TrueHeld

\* (9) Reader A never answers HELD for a PR whose hold was released.
LocalReaderNoStaleHold ==
    \A up \in BOOLEAN : "HELD" \in ReaderAAnswers(up) => TrueHeld

\* (10) A4 as amended: a reader with no buffer and no reachable projection
\*      never answers CLEAR. Reader B never has a buffer; reader A uses the
\*      same answer when its live file is missing.
NoClearWithoutSource == "CLEAR" \notin NoSourceAnswers

\* the harm (10) prevents: a held PR read CLEAR from a stale md copy
NoSourceNeverClearsAHold == TrueHeld => "CLEAR" \notin NoSourceAnswers

\* measured residual, expected to FAIL in the adopted design (plan section 13,
\* cross-host lag): reader B, with the projection reachable, reads CLEAR
\* while a hold placed on the writing host is not yet confirmed
RemoteReaderNeverLags == \A up \in BOOLEAN : "CLEAR" \in ReaderBAnswers(up) => ~TrueHeld

\* ---- v3 reachability witnesses: each is expected to be VIOLATED in the
\* adopted design. A violation is a trace to a state where the premise of the
\* named invariant holds, so the invariant's pass is not vacuous. ----

\* DropOnlyConfirmed: a roll has dropped a closed hold or release
NotW_ClosedEventDropped ==
    ~\E r \in Recs(AllArch) : r.kind \in {"hold", "release"} /\ r.id \notin Ids(jsonl)

\* LocalReaderSeesOwnHold: the hold is in force and unconfirmed, the
\* projection has the epoch, and reader A answers HELD (from its tail)
NotW_UnconfirmedHoldSeen ==
    ~(TrueHeld /\ "e1" \notin ProjIds /\ "ep0" \in ProjIds /\ ReaderAAnswers(TRUE) = {"HELD"})

\* LocalReaderNoStaleHold: the hold and its release were both dropped by a
\* roll, and reader A answers CLEAR
NotW_ReleasedPairDroppedClear ==
    ~(/\ \A e \in {"e1", "e2"} : e \in Ids(AllArch) /\ e \notin Ids(jsonl)
      /\ ReaderAAnswers(TRUE) = {"CLEAR"})

\* NoSourceNeverClearsAHold: the hold is in force while some published md
\* prefix has the epoch and not the hold
NotW_HeldWithStaleMd ==
    ~(TrueHeld /\ \E k \in 0..Len(md) : EpochInR(MdPrefixRecs(k)) /\ ~HeldR(MdPrefixRecs(k)))

\* measurement (run with -workers 1): prints each <<phase, acked>> the first
\* time a merge is found to have missed a hold visible in it. Always TRUE.
ASSUME TLCSet(1, {})
CollectMissed ==
    IF missed \subseteq TLCGet(1) THEN TRUE
    ELSE /\ PrintT(<<"MISSED", missed \ TLCGet(1)>>)
         /\ TLCSet(1, TLCGet(1) \cup missed)
=============================================================================
