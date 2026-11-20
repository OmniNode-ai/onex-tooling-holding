"""Scheduled auth ignores fixed and inherited tokens; pool exhaustion alerts once.

OMN-22104: the tick draws its Claude token from the pool (``node_claude_token_pool_effect
resolve``), marks the drawn label limited on a usage limit and reruns once on the next live label.
``RECORDED_REFUSAL`` is the refusal line the tick log recorded; it holds no secret.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from _trigger_delegation_step import pool_env
from test_morning_tick_package_workflow import DRIVER, _drive, _receipts

pytestmark = pytest.mark.unit
RECORDED_REFUSAL = "You've hit your weekly limit · resets Oct 15, 9am (America/New_York)\n"
FAKE_TOKEN = "test-pool-oauth-value"
LIMIT_BANNER = "You've hit your weekly limit · resets 9am (America/New_York)"
LIMITED_TOKEN_CLAUDE = (
    'if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then\n'
    f'  echo "{LIMIT_BANNER}"\n'
    "  exit 1\nfi\n"
    "echo MORNING_TRIGGER_SELFTEST_OK\nexit 0\n"
)


def _run(
    tmp_path: Path, body: str = "", *, empty: bool = False, **extra: str
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    seen = tmp_path / "seen_token_len"
    env = pool_env(tmp_path, [] if empty else [{"label": "scheduled", "token": FAKE_TOKEN}])
    result, _ = _drive(
        tmp_path,
        DRIVER,
        "hourly-tick",
        f'printf "%s\\n" "${{#CLAUDE_CODE_OAUTH_TOKEN}}" >> "{seen}"\n' + body,
        **(env | {"ONEX_MORNING_SELFTEST": "1"} | extra),
    )
    return result, seen, tmp_path / "home/.onex_state/morning-workflows/fire-receipts.jsonl"


def _rows(receipts: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in receipts.read_text().splitlines()]


def _write_token(tmp_path: Path) -> None:
    token_file = tmp_path / "home/.config/omni/claude-oauth-token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("unused-fixed-token\n")


def _alert_lib(tmp_path: Path) -> tuple[Path, Path]:
    lib, sent = tmp_path / "alert-channel.sh", tmp_path / "alerts.txt"
    lib.write_text(f'alert_channel_send() {{ printf "%s\\n" "$*" >> "{sent}"; return 0; }}\n')
    return lib, sent


def test_fixed_token_file_and_inherited_token_cannot_override_pool(tmp_path: Path) -> None:
    _write_token(tmp_path)
    result, seen, receipts = _run(tmp_path, CLAUDE_CODE_OAUTH_TOKEN="inherited-unused")
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text().split() == [str(len(FAKE_TOKEN))]
    assert _rows(receipts)[-1]["auth_source"] == "pool"
    assert FAKE_TOKEN not in result.stdout + result.stderr + receipts.read_text()


def test_empty_pool_ignores_fixed_token_and_uses_login(tmp_path: Path) -> None:
    _write_token(tmp_path)
    result, seen, receipts = _run(tmp_path, empty=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text().split() == ["0"]
    assert _rows(receipts)[-1]["auth_source"] == "keychain"


def test_usage_limited_token_reruns_once_on_login_and_alerts_once(tmp_path: Path) -> None:
    lib, sent = _alert_lib(tmp_path)
    result, seen, receipts = _run(tmp_path, LIMITED_TOKEN_CLAUDE, ONEX_ALERT_CHANNEL_LIB=str(lib))
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text().split() == [str(len(FAKE_TOKEN)), "0"]
    rows = _rows(receipts)
    fallbacks = [r for r in rows if r.get("phase") == "auth_fallback"]
    assert len(fallbacks) == 1 and fallbacks[0]["auth_source"] == "keychain-fallback"
    assert fallbacks[0]["limited_label"] == "scheduled"
    assert rows[-1]["phase"] == "completed"
    assert "weekly limit" in str(rows[-1]["auth_fallback_reason"])
    alerts = sent.read_text().splitlines()
    assert len(alerts) == 1 and alerts[0].startswith("claude_auth_fallback ")
    assert FAKE_TOKEN not in result.stdout + result.stderr + receipts.read_text() + alerts[0]


def test_second_limited_fire_records_without_alerting_again(tmp_path: Path) -> None:
    lib, sent = _alert_lib(tmp_path)
    for _ in range(2):
        result, _, receipts = _run(tmp_path, LIMITED_TOKEN_CLAUDE, ONEX_ALERT_CHANNEL_LIB=str(lib))
        assert result.returncode == 0, result.stdout + result.stderr
    assert len(sent.read_text().splitlines()) == 1
    assert len([r for r in _rows(receipts) if r.get("phase") == "auth_fallback"]) == 2


def test_limited_login_after_pool_exhaustion_has_no_third_run(tmp_path: Path) -> None:
    result, seen, receipts = _run(tmp_path, f'echo "{LIMIT_BANNER}"\nexit 1\n')
    assert result.returncode == 1
    assert seen.read_text().split() == [str(len(FAKE_TOKEN)), "0"]
    assert _rows(receipts)[-1]["phase"] == "failed"


def test_unreachable_alert_channel_does_not_stop_login_fallback(tmp_path: Path) -> None:
    result, seen, receipts = _run(
        tmp_path, LIMITED_TOKEN_CLAUDE, ONEX_ALERT_CHANNEL_LIB=str(tmp_path / "absent.sh")
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text().split() == [str(len(FAKE_TOKEN)), "0"]
    fallback = next(r for r in _rows(receipts) if r.get("phase") == "auth_fallback")
    assert fallback["alert_exit"] != 0


def entry(label: str, **flags: bool) -> dict[str, object]:
    return {"label": label, "token": "test-secret-" + label, **flags}


def run_pool(
    tmp_path: Path, entries: list[dict[str, object]], body: str = "", **extra: str
) -> tuple[subprocess.CompletedProcess[str], list[str], list[dict[str, object]]]:
    env = pool_env(tmp_path, entries)
    seen = tmp_path / "seen.jsonl"
    body = f'printf \'%s\\n\' "${{CLAUDE_CODE_OAUTH_TOKEN:-login}}" >> "{seen}"\n' + body
    result, _ = _drive(tmp_path, DRIVER, "hourly-tick", body, **(env | extra))
    return (
        result,
        seen.read_text().splitlines() if seen.exists() else [],
        _receipts(tmp_path, "hourly-tick"),
    )


def calls(tmp_path: Path) -> list[list[str]]:
    return [json.loads(line) for line in (tmp_path / "pool-calls.jsonl").read_text().splitlines()]


def assert_private(
    tmp_path: Path,
    result: subprocess.CompletedProcess[str],
    rows: list[dict[str, object]],
    entries: list[dict[str, object]],
) -> None:
    public = result.stdout + result.stderr + json.dumps(rows)
    for log in (tmp_path / "home/.onex_state/morning-workflows/runs").glob("*.log"):
        public += log.read_text()
    for item in entries:
        assert str(item["token"]) not in public
    assert not list((tmp_path / "home/.onex_state/morning-workflows").glob(".pool-*"))


def test_resolve_skips_excluded_limited_and_revoked(tmp_path: Path) -> None:
    entries = [
        entry("h907-own"),
        entry("spent", limited=True),
        entry("gone", revoked=True),
        entry("live"),
    ]
    result, seen, rows = run_pool(tmp_path, entries, CLAUDE_CODE_OAUTH_TOKEN="inherited-secret")
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen == [entries[-1]["token"]]
    assert rows[-1]["auth_source"] == "pool" and rows[-1]["token_label"] == "live"
    assert calls(tmp_path) == [["resolve"]]
    assert_private(tmp_path, result, rows, entries)


def test_recorded_refusal_usage_limit_rotates_once(tmp_path: Path) -> None:
    refusal = tmp_path / "usage_limit.log"
    refusal.write_text(RECORDED_REFUSAL)
    entries = [entry("first"), entry("second")]
    body = f'if [[ "$CLAUDE_CODE_OAUTH_TOKEN" == *first ]]; then cat "{refusal}"; exit 1; fi\n'
    result, seen, rows = run_pool(tmp_path, entries, body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen == [e["token"] for e in entries]
    assert calls(tmp_path)[0] == ["resolve"]
    mark = calls(tmp_path)[1]
    assert mark[:3] == ["mark-limited", "--label", "first"]
    assert mark[3] == "--seconds" and float(mark[4]) > 0
    assert calls(tmp_path)[2] == ["resolve"]
    assert rows[-1]["token_label"] == "second"
    assert_private(tmp_path, result, rows, entries)


def test_usage_limit_without_reset_uses_overlay_default_then_login(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(json.dumps({"excluded_labels": ["h907-own"], "limit_default_seconds": 321}))
    entries = [entry("only")]
    result, seen, rows = run_pool(
        tmp_path,
        entries,
        'if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then\n'
        'echo "Claude usage limit reached."; exit 1; fi\n',
        ONEX_MORNING_TOKEN_POOL_OVERLAY=str(overlay),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen == [entries[0]["token"], "login"]
    assert calls(tmp_path)[1] == ["mark-limited", "--label", "only", "--seconds", "321"]
    assert rows[-1]["auth_source"] == "keychain-fallback"
    assert_private(tmp_path, result, rows, entries)


def test_empty_pool_uses_login(tmp_path: Path) -> None:
    result, seen, rows = run_pool(tmp_path, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen == ["login"] and rows[-1]["auth_source"] == "keychain"


def test_pool_error_never_spends_interactive_login(tmp_path: Path) -> None:
    result, seen, _ = run_pool(tmp_path, [entry("live")], FAKE_POOL_ERROR="1")
    assert result.returncode != 0 and seen == []


def test_usage_limit_mark_failure_never_spends_login(tmp_path: Path) -> None:
    result, seen, _ = run_pool(
        tmp_path,
        [entry("first"), entry("second")],
        'echo "Claude usage limit reached."; exit 1\n',
        FAKE_POOL_MARK_ERROR="1",
    )
    assert result.returncode == 69 and seen == ["test-secret-first"]
    assert [c[0] for c in calls(tmp_path)] == ["resolve", "mark-limited"]


def test_token_file_is_private_and_removed_after_child_exit(tmp_path: Path) -> None:
    probe = (
        "import glob,os,stat; "
        'paths=glob.glob(os.environ["registry_root"]+"/.onex_state/morning-workflows/.pool-token.*"); '
        "assert len(paths)==1; assert stat.S_IMODE(os.stat(paths[0]).st_mode)==0o600"
    )
    body = f"{shlex.quote(sys.executable)} -c {shlex.quote(probe)} || exit 99\n"
    entries = [entry("live")]
    result, seen, rows = run_pool(tmp_path, entries, body)
    assert result.returncode == 0 and seen == ["test-secret-live"]
    assert_private(tmp_path, result, rows, entries)


def test_non_limit_failure_does_not_rotate(tmp_path: Path) -> None:
    entries = [entry("live")]
    result, seen, rows = run_pool(tmp_path, entries, 'echo "network unavailable"; exit 1\n')
    assert result.returncode == 1 and seen == [entries[0]["token"]]
    assert calls(tmp_path) == [["resolve"]]
    assert_private(tmp_path, result, rows, entries)


def test_usage_limit_second_label_is_marked_without_third_attempt(tmp_path: Path) -> None:
    entries = [entry("first"), entry("second"), entry("third")]
    result, seen, rows = run_pool(tmp_path, entries, 'echo "Claude usage limit reached."; exit 1\n')
    assert result.returncode == 1 and seen == [e["token"] for e in entries[:2]]
    assert [c[0] for c in calls(tmp_path)] == ["resolve", "mark-limited", "resolve", "mark-limited"]
    assert rows[-1]["token_label"] == "second"


def test_usage_limit_marks_seconds_until_the_banner_reset(tmp_path: Path) -> None:
    reset = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    local = reset.astimezone(ZoneInfo("America/New_York"))
    banner = "You've hit your weekly limit · resets " + local.strftime(
        "%b %d, %I:%M%p (America/New_York)"
    )
    body = f'if [[ "$CLAUDE_CODE_OAUTH_TOKEN" == *first ]]; then echo "{banner}"; exit 1; fi\n'
    result, seen, _ = run_pool(tmp_path, [entry("first"), entry("second")], body)
    assert result.returncode == 0 and len(seen) == 2
    marked = float(calls(tmp_path)[1][4])
    remaining = reset.timestamp() - datetime.now(UTC).timestamp()
    assert remaining <= marked <= remaining + 5


@pytest.mark.parametrize("entries", [[], [entry("h907-own")], [entry("spent", limited=True)]])
def test_no_eligible_pool_label_uses_login(
    tmp_path: Path, entries: list[dict[str, object]]
) -> None:
    result, seen, rows = run_pool(tmp_path, entries)
    assert result.returncode == 0 and seen == ["login"]
    assert rows[-1]["token_label"] == ""


def test_invalid_overlay_refuses_without_login(tmp_path: Path) -> None:
    overlay = tmp_path / "invalid.yaml"
    overlay.write_text('{"excluded_labels": [], "limit_default_seconds": 0}')
    result, seen, _ = run_pool(
        tmp_path, [entry("live")], ONEX_MORNING_TOKEN_POOL_OVERLAY=str(overlay)
    )
    assert result.returncode == 69 and seen == []


def test_overlay_exclusion_is_data(tmp_path: Path) -> None:
    overlay = tmp_path / "own.yaml"
    overlay.write_text(json.dumps({"excluded_labels": ["other"], "limit_default_seconds": 600}))
    result, seen, _ = run_pool(
        tmp_path, [entry("other"), entry("allowed")], ONEX_MORNING_TOKEN_POOL_OVERLAY=str(overlay)
    )
    assert result.returncode == 0 and seen == ["test-secret-allowed"]
