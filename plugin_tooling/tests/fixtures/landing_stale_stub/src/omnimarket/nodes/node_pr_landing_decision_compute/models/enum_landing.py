"""Pinned vocabularies plus the stale-refresh seam (OMN-20508)."""

from __future__ import annotations

from enum import StrEnum


class EnumLandingSuspension(StrEnum):
    HOLD = "hold"
    GATE = "gate"
    DRAFT = "draft"
    DO_NOT_LAND = "do_not_land"


class EnumLandingResultKind(StrEnum):
    MERGED = "merged"
    ARMED = "armed"
    FIX_SUBMITTED = "fix_submitted"
    EXTERNAL_BLOCKER = "external_blocker"
    WAITING_CI = "waiting_ci"
    WAITING_ORDER = "waiting_order"
    REPORT_ONLY = "report_only"
    BLOCKED = "blocked"
    UNPARSEABLE = "unparseable"


class EnumLandingBriefClass(StrEnum):
    REAL_RED = "real_red"
    CASCADE_RED = "cascade_red"
    BEHIND = "behind"
    CONFLICT_MECHANICAL = "conflict_mechanical"
    CONFLICT_SUBSTANTIVE = "conflict_substantive"
    COMPANION_RED = "companion_red"
    COMPANION_ORPHAN = "companion_orphan"
    RUNTIME = "runtime"


class EnumLandingActionKind(StrEnum):
    MERGE = "merge"
    RERUN = "rerun"
    UPDATE_BRANCH = "update_branch"
    ELIGIBILITY_RERUN = "eligibility_rerun"
    COMPANION_REBUILD = "companion_rebuild"
    COMPANION_CLOSE = "companion_close"
    DISPATCH_WORKER = "dispatch_worker"
    KILL_WORKER = "kill_worker"
    DISCARD_RESULT = "discard_result"
    OBSERVE_ONLY = "observe_only"


class EnumLandingDegradedReason(StrEnum):
    LEASE_STUCK = "lease_stuck"
    ESCALATION_EXHAUSTED = "escalation_exhausted"
    REBUILD_EXHAUSTED = "rebuild_exhausted"
    STALE_REFRESH_EXHAUSTED = "stale_refresh_exhausted"


class EnumLandingMergeState(StrEnum):
    CLEAN = "clean"
    BEHIND = "behind"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
