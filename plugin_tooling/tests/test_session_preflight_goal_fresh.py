"""OMN-17427: session preflight goes red when beta/GOAL.md was produced over a day ago.

Age runs from the commit time of beta/GOAL.md at the clone's HEAD, falling back to state_as_of; a
date-only state_as_of counts as the end of that UTC day, so a goal produced at 20:13Z is still fresh
at 00:05Z the next day.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "plugins/onex-overlays/overlays/session_preflight/overlay.yaml"


def goal_check() -> dict:
    checks = yaml.safe_load(OVERLAY.read_text())["checks"]
    (check,) = [c for c in checks if c["check_id"] == "goal_fresh"]
    return check


def run_check(env_extra: dict[str, str]) -> int:
    env = {k: v for k, v in os.environ.items() if k not in {"ONEX_REMOTE_LANE", "DOCS_REPO_PATH"}}
    env.update(env_extra)
    return subprocess.run(
        goal_check()["command"], shell=True, check=False, env=env, capture_output=True, timeout=30
    ).returncode


def write_goal(kb: Path, stamp: str | None) -> None:
    goal = kb / "beta" / "GOAL.md"
    goal.parent.mkdir(parents=True, exist_ok=True)
    goal.write_text("---\n" + (f"state_as_of: {stamp}\n" if stamp is not None else "") + "---\nrows\n")


def commit_goal(kb: Path, stamp: str | None, hours_ago: float) -> None:
    """Commit beta/GOAL.md in a fresh repository with a commit time hours_ago in the past."""
    write_goal(kb, stamp)
    when = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "person@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "person@example.com",
    }
    for args in (["init", "-q"], ["add", "beta/GOAL.md"], ["commit", "-q", "-m", "goal"]):
        subprocess.run(["git", "-C", str(kb), *args], check=True, env=env, capture_output=True)


def days_ago(days: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d")


def ago(hours: float) -> str:
    moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_check_is_a_blocker_that_carries_its_fix() -> None:
    check = goal_check()
    assert check["severity"] == "blocker"
    assert check["kind"] == "command"
    assert "morning-ground-state" in check["fix"]


def test_a_goal_measured_within_a_day_passes(tmp_path: Path) -> None:
    write_goal(tmp_path, ago(2))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0


def test_a_goal_older_than_a_day_is_red(tmp_path: Path) -> None:
    write_goal(tmp_path, ago(25))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_a_date_only_stamp_from_days_ago_is_red(tmp_path: Path) -> None:
    stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=6)).strftime("%Y-%m-%d")
    write_goal(tmp_path, stamp)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


@pytest.mark.parametrize("stamp", [None, "yesterday-ish", ""])
def test_a_missing_or_unparseable_stamp_is_red_not_green(tmp_path: Path, stamp: str | None) -> None:
    write_goal(tmp_path, stamp)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_a_missing_goal_file_is_red(tmp_path: Path) -> None:
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_the_age_limit_is_the_morning_watchdogs_own_variable(tmp_path: Path) -> None:
    write_goal(tmp_path, ago(25))
    env = {"DOCS_REPO_PATH": str(tmp_path)}
    assert run_check(env) != 0
    assert run_check({**env, "ONEX_MORNING_WATCHDOG_GOAL_MAX_AGE_S": "172800"}) == 0


def test_an_unset_knowledge_base_path_is_left_to_its_own_blocker() -> None:
    assert run_check({}) == 0


def test_a_remote_lane_host_with_a_snapshot_clone_is_not_judged(tmp_path: Path) -> None:
    write_goal(tmp_path, ago(200))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path), "ONEX_REMOTE_LANE": "1"}) == 0


# 20:13Z on one day to 00:05Z on the next is 3 h 52 min. A date-only stamp from two days back is what
# the old probe read as midnight, over 48 h ago, so only the commit time can pass these.
INCIDENT_AGE_HOURS = 3 + 52 / 60


def test_a_goal_produced_at_2013z_passes_at_0005z_the_next_day(tmp_path: Path) -> None:
    commit_goal(tmp_path, days_ago(2), INCIDENT_AGE_HOURS)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0


def test_the_same_goal_fails_24_hours_after_its_commit(tmp_path: Path) -> None:
    commit_goal(tmp_path, days_ago(2), 24 + 1 / 60)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_a_goal_committed_just_inside_the_day_passes(tmp_path: Path) -> None:
    commit_goal(tmp_path, days_ago(2), 24 - 1 / 60)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0


def test_the_commit_time_is_preferred_over_a_full_stamp(tmp_path: Path) -> None:
    commit_goal(tmp_path, ago(30), 2)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0


def test_a_missing_stamp_is_red_even_when_the_commit_is_fresh(tmp_path: Path) -> None:
    commit_goal(tmp_path, None, 1)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_an_uncommitted_edit_is_measured_by_its_own_stamp(tmp_path: Path) -> None:
    commit_goal(tmp_path, ago(50), 50)
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0
    write_goal(tmp_path, ago(1))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0


def test_a_date_only_stamp_counts_as_the_end_of_its_utc_day(tmp_path: Path) -> None:
    # Yesterday's end of day is today 00:00Z, under 24 h ago at any moment of today; read as the
    # start of yesterday it was always over 24 h and always red.
    write_goal(tmp_path, days_ago(1))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) == 0
    write_goal(tmp_path, days_ago(2))
    assert run_check({"DOCS_REPO_PATH": str(tmp_path)}) != 0


def test_the_age_limit_bounds_the_commit_time_too(tmp_path: Path) -> None:
    commit_goal(tmp_path, days_ago(3), 25)
    env = {"DOCS_REPO_PATH": str(tmp_path)}
    assert run_check(env) != 0
    assert run_check({**env, "ONEX_MORNING_WATCHDOG_GOAL_MAX_AGE_S": "172800"}) == 0
