"""Unit + end-to-end tests for the OMN-17427 wall-clock guard in the
onex-ledger command (ported from registry_root tests/test_ledger_lock_clock_guard.py,
OMN-19347).

Context (fact): from ~2026-09-01T20:20Z an orchestrating session passed
guessed wall-clock values as a "now" argument into workflow scripts; the
values ran 30 minutes to ~3 hours ahead of the real clock and lanes copied
them into the leading timestamp of ledger rows. Nothing in ledger_lock.py
inspected the row's own timestamp, so every one of those rows landed. These
tests pin the three cases the guard must separate: a row stamped AHEAD of the
clock (refused), a row stamped far BEHIND it (refused), and a row stamped
inside the tolerance window (lands).

"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops_tooling_pkg.ledger import lock as ll

NOW = datetime(2026, 9, 2, 10, 50, 28, tzinfo=UTC)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def row(moment: datetime, lane: str = "clock-guard-test") -> str:
    return f"- {stamp(moment)} NOTE lane={lane} actor=test outcome=OK (OMN-17427)."


# --------------------------------------------------------------------------
# row_leading_timestamp: what the guard considers a stamped row at all
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("- 2026-09-02T10:45:00Z NOTE lane=x", datetime(2026, 9, 2, 10, 45, tzinfo=UTC)),
        ("2026-09-02T10:45:00Z CLAIM LOCKED lane=x", datetime(2026, 9, 2, 10, 45, tzinfo=UTC)),
        # minutes-only shape, live in the real ledger ("- 2026-09-01T21:45Z CLAIM ...")
        ("- 2026-09-01T21:45Z CLAIM lane=x", datetime(2026, 9, 1, 21, 45, tzinfo=UTC)),
        # dot-separated shape, also live ("- <ts> · OMN-17519 · lane=... · NOTE ·")
        (
            "- 2026-09-02T10:25Z · OMN-17519 · lane=x · NOTE ·",
            datetime(2026, 9, 2, 10, 25, tzinfo=UTC),
        ),
        ("- 2026-09-02T03:45:00+00:00 NOTE", datetime(2026, 9, 2, 3, 45, tzinfo=UTC)),
    ],
)
def test_row_leading_timestamp_parses_live_row_shapes(line: str, expected: datetime) -> None:
    assert ll.row_leading_timestamp(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "",
        "## §5 ACTION LOG",
        "| OMN-17427 | session | claimed | 2026-09-02T10:45:00Z |",
        "  continuation text mentioning 2026-09-02T10:45:00Z mid-line",
        "- not a timestamp at all",
    ],
)
def test_row_leading_timestamp_is_none_for_unstamped_lines(line: str) -> None:
    """A line with no leading instant is not this gate's business -- headings,
    table rows and continuation lines must pass through untouched."""
    assert ll.row_leading_timestamp(line) is None


# --------------------------------------------------------------------------
# clock_skew_reason: ahead / behind / in-window
# --------------------------------------------------------------------------


def test_row_stamped_ahead_of_the_clock_is_refused_and_names_both_times() -> None:
    ahead = NOW + timedelta(minutes=142)
    reason = ll.clock_skew_reason(row(ahead), NOW)
    assert reason is not None
    assert "AHEAD" in reason
    assert stamp(ahead) in reason, "rejection must name the row's stamped time"
    assert stamp(NOW) in reason, "rejection must name the real wall clock"


def test_row_stamped_behind_the_clock_beyond_a_day_is_refused_and_names_both_times() -> None:
    behind = NOW - timedelta(hours=25)
    reason = ll.clock_skew_reason(row(behind), NOW)
    assert reason is not None
    assert "BEHIND" in reason
    assert stamp(behind) in reason
    assert stamp(NOW) in reason


@pytest.mark.parametrize(
    "delta",
    [
        timedelta(0),
        timedelta(minutes=4, seconds=59),
        timedelta(minutes=5),
        timedelta(minutes=-30),
        timedelta(hours=-23, minutes=-59),
        timedelta(hours=-24),
    ],
)
def test_rows_inside_the_tolerance_window_are_accepted(delta: timedelta) -> None:
    """Both boundaries are inclusive: exactly 5m ahead and exactly 24h behind
    still land. Only strictly beyond a tolerance is refused."""
    assert ll.clock_skew_reason(row(NOW + delta), NOW) is None


@pytest.mark.parametrize(
    "delta",
    [timedelta(minutes=5, seconds=1), timedelta(minutes=18), timedelta(hours=3)],
)
def test_the_real_misstamp_magnitudes_are_all_refused(delta: timedelta) -> None:
    """The live mis-stamps ranged from ~6 minutes to ~2.5 hours ahead; every
    magnitude in that band must be refused, not only the extreme one."""
    assert ll.clock_skew_reason(row(NOW + delta), NOW) is not None


def test_unstamped_line_never_produces_a_reason() -> None:
    assert ll.clock_skew_reason("## §5 ACTION LOG (append-only)", NOW) is None


# --------------------------------------------------------------------------
# validate_clock_skew_payload: multi-line payloads and the override bypass
# --------------------------------------------------------------------------


def test_payload_reason_names_every_offending_line_one_indexed() -> None:
    payload = "\n".join(
        [
            row(NOW, lane="fine"),
            row(NOW + timedelta(minutes=20), lane="ahead-one"),
            row(NOW + timedelta(minutes=90), lane="ahead-two"),
        ]
    )
    reason = ll.validate_clock_skew_payload(payload, NOW)
    assert reason is not None
    assert "line 2" in reason
    assert "line 3" in reason
    assert "line 1" not in reason


def test_clean_payload_passes() -> None:
    payload = "\n".join([row(NOW), row(NOW - timedelta(minutes=3))])
    assert ll.validate_clock_skew_payload(payload, NOW) is None


def test_now_override_cannot_be_used_to_move_the_clock_past_the_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The root cause was a guessed 'now' handed to the writer. If
    LEDGER_LOCK_NOW could carry that guess, the guard would validate a
    mis-stamped row against an equally mis-stamped clock and pass it."""
    monkeypatch.setenv(ll.NOW_OVERRIDE_ENV, "2026-09-02T13:12:00Z")
    faked = datetime.now(UTC) + timedelta(hours=2, minutes=30)
    reason = ll.validate_clock_skew_payload(row(faked), faked)
    assert reason is not None
    assert ll.NOW_OVERRIDE_ENV in reason


# --------------------------------------------------------------------------
# End-to-end through main(): the append path actually refuses / lands
# --------------------------------------------------------------------------


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    # Not named ROLLING_WORK_LEDGER.md: that name is governed by the row
    # grammar (OMN-19256), which judges the row TYPE before the clock guard
    # judges the stamp, and these rows are legacy-shaped on purpose. The clock
    # guard is not scoped by file name, so the name changes nothing it tests.
    path = tmp_path / "clock_guard_ledger.md"
    path.write_text("## §5 ACTION LOG (append-only)\n", encoding="utf-8")
    return path


def _append(ledger: Path, line: str, monkeypatch: pytest.MonkeyPatch) -> int:
    # Pin the reference clock to the real one so the guard's own override
    # check passes; the row under test is what varies.
    monkeypatch.setenv(ll.NOW_OVERRIDE_ENV, stamp(datetime.now(UTC)))
    return ll.main([str(ledger), "--append", line])


def test_append_of_a_future_stamped_row_exits_65_and_writes_nothing(
    ledger: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = ledger.read_text(encoding="utf-8")
    rc = _append(ledger, row(datetime.now(UTC) + timedelta(hours=2, minutes=22)), monkeypatch)
    assert rc == 65
    assert ledger.read_text(encoding="utf-8") == before, "a refused row must not land"
    assert "OMN-17427 clock guard" in capsys.readouterr().err


def test_append_of_a_stale_stamped_row_exits_65_and_writes_nothing(
    ledger: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = ledger.read_text(encoding="utf-8")
    rc = _append(ledger, row(datetime.now(UTC) - timedelta(hours=30)), monkeypatch)
    assert rc == 65
    assert ledger.read_text(encoding="utf-8") == before
    assert "OMN-17427 clock guard" in capsys.readouterr().err


def test_append_of_an_in_window_row_lands(ledger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    line = row(datetime.now(UTC))
    rc = _append(ledger, line, monkeypatch)
    assert rc == 0
    assert line in ledger.read_text(encoding="utf-8"), "an honestly stamped row must still land"
