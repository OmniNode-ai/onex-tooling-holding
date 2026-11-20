#!/usr/bin/env bash
# Writes every .cfg this lane ran. Baseline: revision 1 (F1-F10) plus the proposed revision-2 values (make_cfg.py defaults).
cd "$(dirname "$0")"
INV="TypeOK P1 P1arm P2 P3 P4 P5"
ONE="PRS={p1} Foreign=TRUE"
LIVE="SPEC=LiveSpec NOSYM PROPS=P6 Declines=FALSE Dups=0 StallTimer=TRUE"
# --- the proposed revision 2 at the full bound
python3 make_cfg.py X_perPR 2 "$INV P7 TermKind" $ONE
python3 make_cfg.py X_perPR_nodup 2 "$INV P7 TermKind" $ONE Dups=0
python3 make_cfg.py X_perPR_notimer 2 "$INV P7 TermKind" $ONE Timers=FALSE
python3 make_cfg.py X_ticket 2 "$INV P7 TermKind" Checks=FALSE CcLag=FALSE Timers=FALSE
python3 make_cfg.py X_ticket_timer 2 "$INV P7 TermKind" Checks=FALSE CcLag=FALSE
python3 make_cfg.py X_reopen 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE
# --- G5 (found by this extension) reopen reordered before its closed
python3 make_cfg.py G5_reopen_noeval 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE ReopenEval=FALSE
python3 make_cfg.py G5_reopen_nocompanion 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE ClosedCompanion=FALSE
python3 make_cfg.py G5_reopen_nonewer 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE ClosedNewer=FALSE
python3 make_cfg.py G5_reopen_noseq 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE ClosedSeq=FALSE
python3 make_cfg.py G5_reopen_nomerged 3 "TypeOK P1 P1arm P2 P3 P4ep P5 P7" $ONE Reopen=TRUE Dups=0 Timers=FALSE ClosedMerged=FALSE
python3 make_cfg.py X_P6 1 "" $ONE $LIVE
python3 make_cfg.py X_P6_eb2 2 "" $ONE $LIVE
# --- G1 closed ingress
python3 make_cfg.py G1_none 2 "$INV P7 TermKind" $ONE ClosedIngress=none
python3 make_cfg.py G1_noflag 2 "$INV P7 TermKind" $ONE ClosedIngress=noflag
# --- G2 change_control_open
python3 make_cfg.py G2_reach_live 2 "CcOpenUnreached" $ONE CcLag=FALSE
python3 make_cfg.py G2_reach_lag 2 "CcOpenUnreached" $ONE
python3 make_cfg.py G2_row_none 2 "$INV P7 TermKind" $ONE CcOpenRow=none
python3 make_cfg.py G2_row_companion_open 2 "$INV P7 TermKind" $ONE CcOpenRow=companion_open
# --- G3 completion bound
python3 make_cfg.py G3_P6_boundParked 1 "" $ONE $LIVE BOUND_PARKED
python3 make_cfg.py G3_P6_untagged 1 "" $ONE $LIVE TimerTagged=FALSE
python3 make_cfg.py G3_P6_untagged_eb2 2 "" $ONE $LIVE TimerTagged=FALSE
python3 make_cfg.py G3_safety_boundParked 2 "$INV P7 TermKind" $ONE BOUND_PARKED
python3 make_cfg.py G3_safety_boundParked_nodup 2 "$INV P7 TermKind" $ONE BOUND_PARKED Dups=0
# --- G4 armed flag on a new head
python3 make_cfg.py G4_keep_P1m 2 "P1m" $ONE
python3 make_cfg.py G4_disarm_P1m 2 "P1m" $ONE NewHeadArm=disarm
python3 make_cfg.py G4_forget 2 "$INV P7 TermKind" $ONE NewHeadArm=forget
python3 make_cfg.py G4_disarm 2 "$INV P7 TermKind" $ONE NewHeadArm=disarm
python3 make_cfg.py G4_disarm_nodup 2 "$INV P7 TermKind" $ONE NewHeadArm=disarm Dups=0
python3 make_cfg.py G4_disarm_P6 1 "" $ONE $LIVE NewHeadArm=disarm
