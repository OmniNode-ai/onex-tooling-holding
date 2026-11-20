"""Bot release PRs land only after release-cut's current-tip premise is READY (OMN-20864)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.test_landing_controller import (
    REPO, SHA, X, Harness, _load_controller, actions, h, plugin, world,
)

PR = f"{REPO}#21"


def release_pr(premise: str, **extra: Any) -> dict[str, Any]:
    return {"head": SHA["c"], "rollup": "SUCCESS", "created_at": "2026-09-20T00:00:00Z",
            "title": "chore: release omnibase_core 0.47.42", "author": "github-actions[bot]",
            "author_is_bot": True, "release_premise": premise, **extra}


def setup_release(h: Harness, premise: str, **extra: Any) -> None:
    h.world.edit(lambda w: w["prs"].pop(X))
    h.world.edit(lambda w: w["prs"].update({PR: release_pr(premise, **extra)}))
    # the dev tip the premise read (replay: the world's base head) and the one release_hold re-reads
    h.world.edit(lambda w: w.setdefault("base_heads", {}).update({f"{REPO}:dev": SHA["d"]}))
    h.open_gate()


def merged(h: Harness) -> list[str]:
    return [e["pr"] for e in h.world.read().get("log", []) if e["kind"] == "merge"]


def receipt(h: Harness) -> dict[str, Any]:
    return json.loads((h.state / "ticks.jsonl").read_text(encoding="utf-8").splitlines()[-1])


def test_ready_release_merges_at_its_head_without_a_worker(h: Harness) -> None:
    setup_release(h, "READY")
    out = h.tick()
    assert out["rc"] == 0, out
    assert [(a["subject"], a["head_sha"]) for a in actions(out, "merge")] == [(f"OmniNode-ai/{PR}", SHA["c"])]
    assert actions(out, "dispatch_worker") == []
    assert receipt(h)["release_premise"][PR]["verdict"] == "READY"
    assert receipt(h)["release_premise"][PR]["tip"] == SHA["d"]
    assert "release_ready=1" in out["summary"]
    assert receipt(h)["performed"].get("merge:merged") == 1, receipt(h)["performed"]


def test_ready_release_is_not_merged_when_dev_moved_since_the_premise_read(h: Harness) -> None:
    # release-cut step 6 merges only while the premise still holds for dev's head at that moment: a premise
    # read at d while dev is now at e (another merge this tick, or one since the read) defers the merge
    setup_release(h, "READY", release_premise_tip=SHA["e"])
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "dispatch_worker") == []
    assert receipt(h)["performed"].get("merge:merged") is None, receipt(h)["performed"]
    assert PR not in merged(h)


def test_ready_release_is_not_merged_when_dev_is_unread_just_before_the_merge(h: Harness) -> None:
    setup_release(h, "READY", release_premise_tip=SHA["d"])
    h.world.edit(lambda w: w.pop("base_heads"))
    out = h.tick()
    assert out["rc"] == 0, out
    assert receipt(h)["performed"].get("merge:merged") is None, receipt(h)["performed"]
    assert PR not in merged(h)


def test_not_ready_release_stays_gated_on_consecutive_ticks(h: Harness) -> None:
    setup_release(h, "NOT_READY")
    for _ in range(2):
        out = h.tick()
        assert out["rc"] == 0, out
        assert actions(out, "merge") == [] and actions(out, "dispatch_worker") == []
        assert receipt(h)["release_premise"][PR]["verdict"] == "NOT_READY"


def test_red_release_does_not_read_a_ready_premise_or_get_a_worker(h: Harness) -> None:
    setup_release(h, "READY", rollup="FAILURE", red=["Tests"], runs=[["Tests", "completed", "failure", ""]])
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "merge") == [] and actions(out, "dispatch_worker") == []
    assert receipt(h)["release_premise"][PR]["verdict"] == "NOT_READY"


def stamp(minutes_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_release_red_under_the_wait_stays_gated(h: Harness) -> None:
    setup_release(h, "READY", rollup="FAILURE", red=["Tests"], runs=[["Tests", "completed", "failure", ""]],
                  last_red_completed_at=stamp(5))
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "merge") == [] and actions(out, "dispatch_worker") == []


@pytest.mark.parametrize("minutes", [5, 45, 24 * 60])
def test_release_pr_2247_red_gets_no_worker_however_long_and_is_reported(h: Harness, minutes: int) -> None:
    # OMN-22314: omnibase_core#2247 (chore: release 0.47.66, red 45 minutes) got landing worker lease L24372, which
    # pushed b5803b0f4d9a, product changes, onto the bot's release branch
    record = json.loads((Path(__file__).resolve().parent / "fixtures/release-pr-2247/record.json").read_text(encoding="utf-8"))
    red = record["red_checks"][:3]
    setup_release(h, "READY", title=record["title"], author=record["author"], author_is_bot=record["author_is_bot"],
                  rollup="FAILURE", red=red, runs=[[c, "completed", "failure", ""] for c in red],
                  last_red_completed_at=stamp(minutes))
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "dispatch_worker") == [] and actions(out, "merge") == []
    assert receipt(h)["release_red"] == [f"OmniNode-ai/{PR}"]
    assert f"release_red=1[OmniNode-ai/{PR}]" in out["summary"]


def test_release_green_after_a_long_red_is_still_gated_by_the_premise(h: Harness) -> None:
    # the lift is for a red head only: once green, a NOT_READY premise gates the release again
    setup_release(h, "NOT_READY", last_red_completed_at=stamp(120))
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "merge") == [] and actions(out, "dispatch_worker") == []


def test_non_bot_release_title_lands_without_a_premise_read(h: Harness) -> None:
    setup_release(h, "NOT_READY", author="ops", author_is_bot=False)
    out = h.tick()
    assert out["rc"] == 0, out
    assert [(a["subject"], a["head_sha"]) for a in actions(out, "merge")] == [(f"OmniNode-ai/{PR}", SHA["c"])]
    assert actions(out, "dispatch_worker") == []
    assert PR not in receipt(h)["release_premise"]


def live_snapshot(controller: Any, root: Path, *, now: datetime, tip: str = SHA["a"], **live_extra: Any) -> Any:
    scripts = Path(__file__).resolve().parent.parent / "plugins/omni/skills/merge-drain/scripts"
    snap = controller.Snapshot(gh=None, source="live", registry_root=root / "clones", scripts_dir=scripts,
                               state_dir=root, now=now)
    snap.records[PR] = {"facts": {"title": release_pr("READY")["title"]}}
    snap.live[PR] = SimpleNamespace(**{"head": SHA["c"], "state": "OPEN", "base": "dev", "draft": False,
                                       "rollup": "SUCCESS", "author_is_bot": True, **live_extra})
    snap.local = SimpleNamespace(branch_view=lambda repo, base, parts: ({"tip": tip}, ""))
    return snap


@pytest.mark.parametrize("verdict", ["READY", "NOT_READY"])
def test_live_premise_cache_is_shared_expires_and_tracks_dev_tip(tmp_path: Path, monkeypatch: Any, verdict: str) -> None:
    controller = _load_controller()
    now = datetime(2026, 10, 12, tzinfo=UTC)
    calls = []

    def run(argv: list[str], **kwargs: Any) -> Any:
        calls.append((argv, kwargs))
        tip = SHA["b"] if len(calls) == 3 else SHA["a"]
        return SimpleNamespace(stdout=f"facts: dev_head={tip[:12]}\nPREMISE {verdict}\n", returncode=0)

    monkeypatch.delenv(controller.RELEASE_PREMISE_CMD_ENV, raising=False)
    monkeypatch.setattr(controller.subprocess, "run", run)
    snap = live_snapshot(controller, tmp_path, now=now)
    assert snap.release_ready(PR) is (verdict == "READY")
    assert snap.release_ready(PR) is (verdict == "READY")  # both decision rounds
    other = f"{REPO}#22"
    snap.records[other], snap.live[other] = snap.records[PR], snap.live[PR]
    assert snap.release_ready(other) is (verdict == "READY")
    assert snap.release[other]["cached"] is True and len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["bash", str((snap.scripts_dir / "../../release-cut/scripts/cut_facts.sh").resolve()),
                    REPO, str((tmp_path / "release-premise" / REPO).resolve())]
    assert Path(argv[-1]).is_dir()
    assert kwargs["timeout"] == 240 and kwargs["env"]["registry_root"] == str(snap.registry_root)
    assert kwargs["capture_output"] and kwargs["text"] and kwargs["check"] is False
    cached = live_snapshot(controller, tmp_path, now=now + timedelta(seconds=899))
    assert cached.release_ready(PR) is (verdict == "READY")
    assert cached.release[PR]["cached"] is True and len(calls) == 1
    expired = live_snapshot(controller, tmp_path, now=now + timedelta(seconds=900))
    assert expired.release_ready(PR) is (verdict == "READY")
    assert expired.release[PR]["cached"] is False and len(calls) == 2
    moved = live_snapshot(controller, tmp_path, now=now + timedelta(seconds=901), tip=SHA["b"])
    assert moved.release_ready(PR) is (verdict == "READY")
    assert len(calls) == 3 and moved.release[PR]["tip"] == SHA["b"]
    saved = json.loads((tmp_path / "release-premise.json").read_text())
    assert saved[f"{REPO}@{SHA['b']}"]["verdict"] == verdict


@pytest.mark.parametrize("value", ["broken", "{}", "[]", '["bash", 1]'])
def test_invalid_premise_override_is_unreadable(tmp_path: Path, monkeypatch: Any, value: str) -> None:
    controller = _load_controller()
    monkeypatch.setenv(controller.RELEASE_PREMISE_CMD_ENV, value)
    snap = live_snapshot(controller, tmp_path, now=datetime(2026, 10, 12, tzinfo=UTC))
    assert snap.release_ready(PR) is False
    assert snap.release[PR]["verdict"] == "UNREADABLE"
    assert snap.release[PR]["why"] == "LANDING_RELEASE_PREMISE_CMD is not a JSON argv list"
    assert json.loads((tmp_path / "release-premise.json").read_text()) == {}


@pytest.mark.parametrize("error", [OSError("cannot execute"), subprocess.TimeoutExpired(["premise"], 240)])
def test_unreadable_premise_retries_next_tick(tmp_path: Path, monkeypatch: Any, error: Exception) -> None:
    controller = _load_controller()
    now = datetime(2026, 10, 12, tzinfo=UTC)
    calls = []

    def run(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        if len(calls) == 1:
            raise error
        return SimpleNamespace(stdout=f"facts: dev_head={SHA['a'][:12]}\nPREMISE READY", returncode=0)

    monkeypatch.setenv(controller.RELEASE_PREMISE_CMD_ENV, '["premise", "--test"]')
    monkeypatch.setattr(controller.subprocess, "run", run)
    snap = live_snapshot(controller, tmp_path, now=now)
    assert snap.release_ready(PR) is False
    assert snap.release[PR]["verdict"] == "UNREADABLE" and str(error) in snap.release[PR]["why"]
    assert json.loads((tmp_path / "release-premise.json").read_text()) == {}
    retry = live_snapshot(controller, tmp_path, now=now + timedelta(seconds=300))
    assert retry.release_ready(PR) is True and len(calls) == 2
    assert calls[1][:2] == ["premise", "--test"]


def test_live_premise_prunes_old_entries_and_refuses_a_moved_dev(tmp_path: Path, monkeypatch: Any) -> None:
    controller = _load_controller()
    now = datetime(2026, 10, 12, tzinfo=UTC)
    (tmp_path / "release-premise.json").write_text(json.dumps({
        "old@tip": {"verdict": "READY", "read_at": "2026-10-10T00:00:00Z"},
        "bad@tip": {"verdict": "READY", "read_at": "invalid"},
    }))
    monkeypatch.setenv(controller.RELEASE_PREMISE_CMD_ENV, '["premise"]')
    monkeypatch.setattr(controller.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=f"facts: dev_head={SHA['b'][:12]}\nPREMISE READY", returncode=0))
    snap = live_snapshot(controller, tmp_path, now=now)
    assert snap.release_ready(PR) is False
    assert snap.release[PR]["verdict"] == "NOT_READY" and "dev moved" in snap.release[PR]["why"]
    assert set(json.loads((tmp_path / "release-premise.json").read_text())) == {f"{REPO}@{SHA['a']}"}


@pytest.mark.parametrize("extra", [{"state": "CLOSED"}, {"draft": True}, {"rollup": "FAILURE"},
                                  {"rollup": "PENDING"}, {"base": "main"}, {"author_is_bot": False}])
def test_ineligible_live_release_never_runs_the_premise(tmp_path: Path, monkeypatch: Any, extra: dict[str, Any]) -> None:
    controller = _load_controller()

    def unexpected(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("an ineligible release PR must not run the premise command")

    monkeypatch.setattr(controller.subprocess, "run", unexpected)
    snap = live_snapshot(controller, tmp_path, now=datetime(2026, 10, 12, tzinfo=UTC), **extra)
    assert snap.release_ready(PR) is False
    if extra.get("author_is_bot") is False:
        assert snap.release == {}
    else:
        assert snap.release[PR]["verdict"] == "NOT_READY"


def test_an_unreadable_repo_does_not_keep_the_premise_read_from_the_others(tmp_path: Path, monkeypatch: Any) -> None:
    # 2026-10-13: omnibase_core#1965 exited 127 on every tick and took the one read per tick, so four other
    # release PRs read "the next tick reads it" on every tick and none of them was ever read
    controller = _load_controller()
    now = datetime(2026, 10, 12, tzinfo=UTC)
    calls: list[str] = []

    def run(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv[-2])
        if argv[-2] == REPO:
            return SimpleNamespace(stdout="", returncode=127)
        return SimpleNamespace(stdout=f"facts: dev_head={SHA['a'][:12]}\nPREMISE READY\n", returncode=0)

    monkeypatch.setenv(controller.RELEASE_PREMISE_CMD_ENV, '["premise"]')
    monkeypatch.setattr(controller.subprocess, "run", run)
    shorts = [PR, "omnibase_spi#353", "omnimemory#607"]
    for tick in range(3):
        snap = live_snapshot(controller, tmp_path, now=now + timedelta(seconds=300 * tick))
        for short in shorts[1:]:
            snap.records[short], snap.live[short] = snap.records[PR], snap.live[PR]
        for short in shorts:
            snap.release_ready(short)
        assert len(calls) == tick + 1, (calls, snap.release)
    assert calls == [REPO, "omnibase_spi", "omnimemory"], calls  # the least recently read repo goes first
    assert snap.release[PR]["verdict"] == "UNREADABLE" and "omnimemory" in snap.release[PR]["why"]
    assert [snap.release[s]["verdict"] for s in shorts[1:]] == ["READY", "READY"]


def test_a_missing_premise_script_is_named_and_never_run(tmp_path: Path, monkeypatch: Any) -> None:
    controller = _load_controller()
    monkeypatch.delenv(controller.RELEASE_PREMISE_CMD_ENV, raising=False)

    def unexpected(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("a missing premise script must not be run")

    monkeypatch.setattr(controller.subprocess, "run", unexpected)
    snap = live_snapshot(controller, tmp_path, now=datetime(2026, 10, 12, tzinfo=UTC))
    snap.scripts_dir = tmp_path / "skills" / "merge-drain" / "scripts"
    assert snap.release_ready(PR) is False
    missing = (tmp_path / "skills" / "release-cut" / "scripts" / "cut_facts.sh").resolve()
    assert snap.release[PR]["verdict"] == "UNREADABLE"
    assert snap.release[PR]["why"] == f"cut_facts.sh is not installed at {missing}"
