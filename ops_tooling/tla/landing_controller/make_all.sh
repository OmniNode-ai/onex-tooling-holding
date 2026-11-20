#!/usr/bin/env bash
# Regenerates every cfg/*.cfg from make_cfg.py. Idempotent.
set -euo pipefail
cd "$(dirname "$0")"
rm -f cfg/*.cfg
m() { python3 make_cfg.py "$@"; }

# ---- verification: safety, TLC must report "No error has been found" ----
m VW_lease   INV=Safety SYM=SymW PRs="{p1}" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=3 MaxHead=3 BPush=2 BForeign=1
m VW_block   INV=Safety SYM=SymW PRs="{p1}" MaxHead=2 BBlk=1 BPush=1
m VW_drain   INV=Safety SYM=SymPW MaxHead=2 BDrain=1 BPush=1
m VW_token   INV=Safety SYM=SymPW Runtime="{p1, p2}" Workers="{w1}" MaxDispatch=1 InitCi='"pending"' BElig=2 BMPush=1 BClose=1
m VC_members INV=Safety SYM=SymPW InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BElig=2 BClose=1
m VC_moves   INV=Safety SYM=SymPW InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BMPush=1 BClose=1 BElig=1
m VC_rebuild INV=Safety SYM=SymPW InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BMPush=1 BCrash=1 BPFail=1
m VC_crash2  INV=Safety SYM=SymPW InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BMPush=1 BCrash=2
m VC_rebuild_fail INV=Safety SYM=SymPW InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BMPush=1 BPFail=3
m VX_mixed   INV=Safety SYM=SymPW InitComp=TRUE InitCi='"pending"' Workers="{w1}" MaxDispatch=1 BPush=1 BElig=1

# ---- verification: liveness under LiveSpec (weak fairness), no symmetry ----
m LW_recover SPEC=LiveSpec PROPS="L2 L3" INV=Safety PRs="{p1}" Workers="{w1, w2}" MaxDispatch=2 MaxHead=2 BPush=1 BForeign=1
m LW_token   SPEC=LiveSpec PROPS="L3" INV=Safety Runtime="{p1}" Workers="{w1}" MaxDispatch=1 InitCi='"pending"' BElig=1
m LC_members SPEC=LiveSpec PROPS="L1 LCover" INV=Safety InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"pending"' BElig=2 BClose=1
m LC_rebuild_crash SPEC=LiveSpec PROPS="L1 L4" INV=Safety InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"red"' BMPush=1 BCrash=1
m LC_rebuild_fail  SPEC=LiveSpec PROPS="L1 L4" INV=Safety InitComp=TRUE Workers="{w1}" MaxDispatch=0 InitCi='"red"' BMPush=1 BPFail=2

# ---- mutations: each removes one guard; TLC MUST report the named violation ----
m M_P1_lease_by_head      INV="P1 P1proc" LeaseByPR=FALSE PRs="{p1}" Workers="{w1, w2}" BPush=1
m M_P8_release_on_result  INV="P8" ReleaseRule='"result"' PRs="{p1}" Workers="{w1, w2}"
m M_P8_release_on_deadline INV="P8" ReleaseRule='"deadline"' PRs="{p1}" Workers="{w1, w2}"
m M_P3_keep_revoked       INV="P3" DiscardRevoked=FALSE PRs="{p1}" Workers="{w1}" MaxDispatch=1 BDrain=1
m M_R1_ancestry           INV="NoLegitRejected" Verify='"ancestry"' PRs="{p1}" Workers="{w1}" MaxDispatch=1 BPush=1
m M_R1_headonly           INV="NoUnauth" Verify='"headonly"' PRs="{p1}" Workers="{w1}" MaxDispatch=1 BForeign=1
m M_R1_no_pin             INV="NoUnverifiedLand" PinMerge=FALSE PRs="{p1}" Workers="{w1}" MaxDispatch=1 MaxHead=3 BPush=2
m M_P2_token_late         INV="P2" FreeTokenFirst=FALSE Runtime="{p1, p2}" Workers="{w1}" MaxDispatch=1 InitCi='"pending"' BClose=1
m M_P4_member_elig        INV="P4" MemberElig=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"pending"' BElig=1
m M_P5_close_suspended    INV="P5" WaitOnSuspended=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"pending"' BElig=2
m M_P6_redispatch_blocked INV="P6" BlockedSuppress=FALSE PRs="{p1}" Workers="{w1, w2}"
m M_P7_no_drain_gate      INV="P7" DrainGate=FALSE PRs="{p1}" Workers="{w1}" MaxDispatch=1 BDrain=1
m M_P9_producer_not_idem  INV="P9" ProducerIdem=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"pending"' BMPush=1 BCrash=1
m M_L2_stop_after_invalid SPEC=LiveSpec PROPS="L2" SuppressAny=TRUE PRs="{p1}" Workers="{w1, w2}"
m M_L4_no_redeliver       SPEC=LiveSpec PROPS="L4" RedeliverPending=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"red"' BMPush=1 BCrash=1
m M_L4_no_retry           SPEC=LiveSpec PROPS="L4" RetryFailed=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"red"' BMPush=1 BPFail=1
m M_L4_seen_open_only    SPEC=LiveSpec PROPS="L4" SeenAny=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"red"' BMPush=1
m M_LCover_no_cover       SPEC=LiveSpec PROPS="LCover" Cover=FALSE InitComp=TRUE MaxDispatch=0 Workers="{w1}" InitCi='"pending"' BElig=2

# ---- scenarios S1-S20: Track=TRUE; the NotS invariant's violation is the trace ----
s() { local n="$1"; shift; m "S_$n" Track=TRUE INV="Safety NotS$n" "$@"; }
W1='Workers={w1}'
s 1   PRs="{p1}" "$W1" MaxDispatch=1 BPush=1
s 2   PRs="{p1}" "$W1" MaxDispatch=1 BPush=1
s 3   InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BClose=1
s 4   InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BMPush=1
s 5   InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BClose=2
s 6   InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' PRs="{p1}"
s 7   PRs="{p1}" "$W1" MaxDispatch=1 BPush=1 ResultKinds='{"fix_submitted"}'
s 8   PRs="{p1}" Workers="{w1, w2}" BPush=1 ResultKinds='{"fix_submitted"}'
s 9   PRs="{p1}" Workers="{w1, w2}" ResultKinds='{}'
s 10  PRs="{p1}" Workers="{w1, w2}" ResultKinds='{"waiting_ci"}'
s 11  PRs="{p1}" Workers="{w1, w2}" ResultKinds='{"external_blocker"}' BBlk=1
s 12  PRs="{p1}" "$W1" MaxDispatch=1 BDrain=1
s 12r PRs="{p1}" "$W1" MaxDispatch=1 BDrain=1
s 13  PRs="{p1}" "$W1" MaxDispatch=1 BPush=1 ResultKinds='{"fix_submitted"}'
s 14  InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BElig=4
s 14b InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BElig=3
s 15  InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BElig=2
s 16  PRs="{p1}" "$W1" MaxDispatch=1 BPush=1 PushModes='{"fwl"}' ResultKinds='{"fix_submitted"}'
s 17  PRs="{p1}" Workers="{w1, w2}" BForeign=1 ResultKinds='{"fix_submitted"}'
s 18  InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BMPush=1 BPFail=1
s 18x InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BMPush=1 BPFail=3
s 19  InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BMPush=1 BCrash=1
s 20  InitComp=TRUE MaxDispatch=0 "$W1" InitCi='"pending"' BMPush=1 BCrash=1

# ---- the red-PR fixer (OMN-20414, plan T1) ----
# A three-member cluster c1 in one repo; Members lists each cause's model value with its PRs.
CL='PRs={p1, p2, p3}'; CC='Causes={c1}'; CM='Members={{c1, p1, p2, p3}}'
# An escalated PR alone (2.1): p1 parks on the per-PR ladder (Engines=1), then c1 = {p1}.
EL='PRs={p1}'; EM='Members={{c1, p1}}'
EB='CauseKinds={"external_blocker"}'

# verification, safety
m VF_cause    INV=Safety SYM=SymPW "$CL" "$CC" "$CM" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=1 MaxHead=1 BPark=1
m VF_notshared INV=Safety SYM=SymPW "$CL" "$CC" "$CM" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=1 CauseKinds='{"cause_not_shared"}' BMPush=1
m VF_hold     INV=Safety SYM=SymPW "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1 BHold=2
m VF_claims   INV=Safety SYM=SymPW "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1 BClaim=2 BCClaim=1
m VF_crash    INV=Safety SYM=SymPW "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 BCrash=2 BPark=1
m VF_caps     INV=Safety SYM=SymW PRs="{p1, p2, p3}" Repos="{{p1, p2}, {p3}}" Causes="{c1, c2}" Members="{{c1, p1}, {c2, p3}}" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=1 MaxHead=1 RepoCap=1 CauseRepoCap=1 CauseFleetCap=1

# verification, liveness
m LF_cause     SPEC=LiveSpec PROPS="L5 LEsc" INV=Safety "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1
m LF_hold      SPEC=LiveSpec PROPS="L6 L5" INV=Safety "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 BHold=2
m LF_escalated SPEC=LiveSpec PROPS="L2 L5 LEsc" INV=Safety "$EL" "$CC" "$EM" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=1 MaxHead=1
m LF_mixed     SPEC=LiveSpec PROPS="L2 L5 LEsc" INV=Safety "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1

# mutations (each flips one fixer guard)
m M_P10_member_dispatch  INV="P10" MemberSuppress=FALSE "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1
m M_P11_no_budget        INV="P11" BudgetGate=FALSE "$CL" "$CC" "$CM" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=0 MaxHead=1 "$EB"
m M_P12_hold_ignored     INV="P12" HoldGate=FALSE "$CL" "$CC" "$CM" Workers="{w1}" MaxDispatch=1 Engines=0 MaxHead=1 BHold=1
m M_P13_no_repo_cap      INV="P13" CapGate=FALSE PRs="{p1, p2}" Workers="{w1, w2}" RepoCap=1
m M_P14_escalate_twice   INV="P14" EscDedupe='"none"' "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 "$EB"
m M_L5_no_cause_dispatch SPEC=LiveSpec PROPS="L5" MemberClaimsOwn=TRUE "$CL" "$CC" "$CM" Workers="{w1}" MaxDispatch=1 Engines=0 MaxHead=1 BClaim=1
# model findings against plan 2.4, kept as mutations of the model's rule (as LC-F1 is)
m M_P11_late_exit_uncounted INV="P11" LateExitCounts=FALSE "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 CauseKinds='{}'
m M_P14_sidecar_dedupe   INV="P14" EscDedupe='"sidecar"' "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 "$EB" BCrash=1

# scenarios S21-S28
s 21 "$CL" "$CC" "$CM" "$W1" MaxDispatch=1 Engines=1 MaxHead=1
s 22 "$CL" "$CC" "$CM" "$W1" MaxDispatch=1 Engines=0 MaxHead=1 CauseKinds='{"cause_fix_submitted"}'
s 23 "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 "$EB"
s 24 "$CL" "$CC" "$CM" "$W1" MaxDispatch=1 Engines=0 MaxHead=1 BHold=1
s 25 "$CL" "$CC" "$CM" "$W1" MaxDispatch=1 Engines=0 MaxHead=1 BClaim=1 BCClaim=1 CauseKinds='{}'
s 26 "$EL" "$CC" "$EM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1 ResultKinds='{}'
s 27 "$EL" "$CC" "$EM" Workers="{w1, w2, w3}" MaxDispatch=3 Engines=1 MaxHead=1 ResultKinds='{}' CauseKinds='{"cause_not_shared"}'
s 28 "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=0 MaxHead=1 BCrash=1 CauseKinds='{}'

# ---- the bus owner (OMN-20744, retirement plan S2): a second writer of the claim lease ----
# The bus path decides each ci-run-failed record once per repo, head and check and starts
# one owner per owner key; the topic redelivers, a runtime restart re-reads it. Safety only.
B='BusOn=TRUE'

# verification, safety (Safety includes PB1, PB2 and NoDual); VB_restart and VB_runner carry BDrain=1 (OMN-25793, R11)
m VB_restart INV=Safety SYM=SymW "$B" PRs="{p1}" Workers="{w1}" MaxDispatch=1 Engines=1 MaxHead=2 BMPush=1 BRestart=2 BDrain=1
m VB_runner  INV=Safety SYM=SymPW "$B" PRs="{p1, p2}" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=2 BMPush=1 BRestart=1 BDrain=1
m VB_cause   INV=Safety SYM=SymW "$B" "$CL" "$CC" "$CM" Workers="{w1}" MaxDispatch=1 Engines=1 MaxHead=2 InitCi='"pending"' BMPush=1 BRestart=1
m VB_mixed   INV=Safety SYM=SymW "$B" "$CL" "$CC" "$CM" Workers="{w1, w2}" MaxDispatch=2 Engines=1 MaxHead=1
m VB_shadow  INV=Safety SYM=SymW "$B" BusAct=FALSE "$CL" "$CC" "$CM" Workers="{w1}" MaxDispatch=1 Engines=1 MaxHead=2 InitCi='"pending"' BMPush=1 BRestart=1

# mutations (each flips one bus guard)
m M_PB1_memory_claims  INV="PB1" BusDurable=FALSE "$B" PRs="{p1}" Workers="{w1}" MaxDispatch=0 MaxHead=1 BRestart=1
m M_PB2_no_absorb      INV="PB2" BusAbsorb=FALSE "$B" "$CL" "$CC" "$CM" Workers="{w1}" MaxDispatch=0 MaxHead=1
m M_PB3_private_claim  INV="NoDual" BusCas=FALSE "$B" PRs="{p1}" Workers="{w1}" MaxDispatch=1 MaxHead=1

# scenarios SB1-SB4
b() { local n="$1"; shift; m "S_B$n" Track=TRUE INV="Safety NotSB$n" "$B" "$@"; }
b 1 PRs="{p1}" "$W1" MaxDispatch=0 MaxHead=1 BRestart=1
b 2 "$CL" "$CC" "$CM" "$W1" MaxDispatch=0 MaxHead=1 InitCi='"pending"'
b 3 "$CL" "$CC" "$CM" "$W1" MaxDispatch=0 MaxHead=1
b 4 PRs="{p1}" "$W1" MaxDispatch=1 Engines=1 MaxHead=1
