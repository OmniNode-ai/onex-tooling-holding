"""The open-claims verb: which CLAIMs are still open, and what the ledger itself says."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from ops_tooling_pkg.ledger import verbs

pytestmark = pytest.mark.unit

NOW = "2026-03-02T12:00:00Z"


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tracking" / "ROLLING_WORK_LEDGER.md"
    path.parent.mkdir()
    path.write_text("## Work ledger\n", encoding="utf-8")
    monkeypatch.setenv("ONEX_LEDGER_DETAIL_DIR", str(tmp_path / "detail"))
    monkeypatch.delenv("ONEX_DRY_RUN", raising=False)
    monkeypatch.delenv("ONEX_LEDGER_PATH", raising=False)
    return path


def run(ledger: Path, *args: str) -> tuple[int, list[str]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = verbs.main(["open-claims", "--ledger", str(ledger), "--now", NOW, *args])
    return code, output.getvalue().splitlines()


def write(ledger: Path, *rows: str) -> None:
    ledger.write_text("## Work ledger\n" + "\n".join(rows) + "\n", encoding="utf-8")


def test_open_claim_printed_and_terminal_closes(ledger: Path) -> None:
    write(ledger, "2026-03-02T10:00:00Z | CLAIM | lane=alpha | ticket=OMN-17427 | worktree=none")
    code, lines = run(ledger)
    assert code == 0
    assert lines[0] == (
        f"open-claims since=beginning claims=1 open=1 ledger-newest=2026-03-02T10:00:00Z now={NOW}"
    )
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T10:00:00Z L2 ticket=OMN-17427 "
        "newest-row=2026-03-02T10:00:00Z kind=CLAIM age=2h00m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )
    code, lines = run(ledger, "--lane", "other")
    assert code == 0
    assert lines == [
        f"open-claims since=beginning claims=1 open=0 ledger-newest=2026-03-02T10:00:00Z now={NOW}"
    ]
    write(
        ledger,
        "2026-03-02T10:00:00Z | CLAIM | lane=alpha | ticket=OMN-17427 | worktree=none",
        "2026-03-02T11:00:00Z | TERMINAL | lane=alpha | friction=none | outcome=done",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines == [
        f"open-claims since=beginning claims=1 open=0 ledger-newest=2026-03-02T11:00:00Z now={NOW}"
    ]


def test_closes_claim_names_one_claim(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
        "2026-03-02T10:00:00Z | TERMINAL | lane=alpha | closes-CLAIM=2026-03-02T09:00:00Z | "
        "friction=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0] == (
        f"open-claims since=beginning claims=2 open=1 ledger-newest=2026-03-02T10:00:00Z now={NOW}"
    )
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T09:30:00Z L3 ticket=OMN-10002 "
        "newest-row=2026-03-02T10:00:00Z kind=TERMINAL age=2h00m rows=2 host=none run=none "
        "leases=none liveness=unknown"
    )


def test_closes_claim_matching_nothing_falls_back(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
        "2026-03-02T10:00:00Z | TERMINAL | lane=alpha | closes-CLAIM=2026-01-01T00:00:00Z | "
        "friction=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines == [
        f"open-claims since=beginning claims=2 open=0 ledger-newest=2026-03-02T10:00:00Z now={NOW}"
    ]


def test_closes_claim_of_another_lane_closes_nothing(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T10:00:00Z | TERMINAL | lane=beta | closes-CLAIM=2026-03-02T09:00:00Z | "
        "friction=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[3] == "open=1"
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T09:00:00Z L2 ticket=OMN-10001 "
        "newest-row=2026-03-02T09:00:00Z kind=CLAIM age=3h00m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )


def test_reused_lane_and_earlier_stamped_terminal(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | TERMINAL | lane=alpha | friction=none",
        "2026-03-02T10:00:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[3] == "open=1"
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T10:00:00Z L4 ticket=OMN-10002 "
        "newest-row=2026-03-02T10:00:00Z kind=CLAIM age=2h00m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T08:30:00Z | TERMINAL | lane=alpha | friction=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[3] == "open=1"
    assert "claim=2026-03-02T09:00:00Z" in lines[1]


def test_closeout_and_legacy_closes_cell(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
        "2026-03-02T10:00:00Z | CLOSEOUT | lane=alpha | removed the worktree",
    )
    code, lines = run(ledger)
    assert code == 0 and lines[0].split()[3] == "open=0"
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
        "2026-03-02T10:00:00Z | TERMINAL | lane=alpha | closes=2026-03-02T09:00:00Z | "
        "friction=none",
    )
    code, lines = run(ledger)
    assert code == 0 and lines[0].split()[3] == "open=1"
    assert "claim=2026-03-02T09:30:00Z" in lines[1]
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=alpha | ticket=OMN-10002 | worktree=none",
        "2026-03-02T10:00:00Z | TERMINAL | lane=alpha | friction=none",
    )
    code, lines = run(ledger)
    assert code == 0 and lines[0].split()[3] == "open=0"


def test_lane_key_must_be_anchored(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | worktree=none",
        "2026-03-02T09:30:00Z | STATUS | lane=watcher | prose about notlane=x and lane=alpha here",
        "2026-03-02T10:00:00Z | TERMINAL | notlane=alpha | friction=none",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[3] == "open=1"
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T09:00:00Z L2 ticket=OMN-10001 "
        "newest-row=2026-03-02T09:00:00Z kind=CLAIM age=3h00m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )


def test_liveness_evidence_cells(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T09:00:00Z | CLAIM | lane=alpha | ticket=OMN-10001 | host=lab-2 | run=run-91",
        "2026-03-02T10:30:00Z | STATUS | lane=alpha | still working",
        "2026-03-02T11:15:00Z | MSG | from=alpha | to=operator | "
        "id=2026-03-02T11:15:00Z-alpha | update",
        "2026-03-02T09:10:00Z | CLAIM | lane=landing-abc123 | ticket=OMN-10002 | worktree=none",
        "2026-03-02T09:20:00Z | STATUS | lane=landing-abc123 | lease=xyz789",
        "2026-03-02T09:30:00Z | CLAIM | lane=gamma | ticket=OMN-10003 | worktree=none",
        "2026-03-02T09:40:00Z | STATUS | lane=gamma | lease-id=lease-1",
        "2026-03-02T09:50:00Z | STATUS | lane=gamma | lease_id=lease-2",
        "2026-03-02T09:35:00Z | CLAIM | lane=delta | ticket=OMN-10004 | worktree=none",
        "2026-03-02T09:45:00Z | STATUS | lane=delta | lease=operator",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[2] == "claims=4" and lines[0].split()[3] == "open=4"
    assert lines[1] == (
        "OPEN-CLAIM lane=alpha claim=2026-03-02T09:00:00Z L2 ticket=OMN-10001 "
        "newest-row=2026-03-02T11:15:00Z kind=MSG age=0h45m rows=3 host=lab-2 run=run-91 "
        "leases=none liveness=unknown"
    )
    assert lines[2].startswith("OPEN-CLAIM lane=landing-abc123 claim=2026-03-02T09:10:00Z ")
    assert "leases=xyz789,landing-abc123" in lines[2]
    assert "leases=lease-1,lease-2" in lines[3]
    assert "leases=none" in lines[4] and "host=none run=none" in lines[4]
    assert all(line.endswith("liveness=unknown") for line in lines[1:])


def test_since_and_archive_roll(ledger: Path) -> None:
    write(
        ledger,
        "2026-03-02T08:00:00Z | CLAIM | lane=ancient | ticket=OMN-10001 | worktree=none",
        "2026-03-02T08:15:00Z | CLAIM | lane=old | ticket=OMN-10002 | worktree=none",
        "2026-03-02T08:30:00Z | TERMINAL | lane=old | friction=none",
        "2026-03-02T09:30:00Z | CLAIM | lane=fresh | ticket=OMN-10003 | worktree=none",
    )
    code, lines = run(ledger, "--since", "2026-03-02T08:45:00Z")
    assert code == 0
    assert lines[0] == (
        f"open-claims since=2026-03-02T08:45:00Z claims=3 open=1 "
        f"ledger-newest=2026-03-02T09:30:00Z now={NOW}"
    )
    assert lines[1] == (
        "OPEN-CLAIM lane=fresh claim=2026-03-02T09:30:00Z L5 ticket=OMN-10003 "
        "newest-row=2026-03-02T09:30:00Z kind=CLAIM age=2h30m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )
    archive = ledger.parent / "archive" / "ROLLING_WORK_LEDGER_2026-01-01-split.md"
    archive.parent.mkdir()
    archive.write_text(
        "# Rolled ledger\n"
        "2026-01-01T09:00:00Z | CLAIM | lane=arch-lane | ticket=OMN-90001 | worktree=none\n",
        encoding="utf-8",
    )
    code, lines = run(ledger)
    assert code == 0
    assert lines[0].split()[2] == "claims=4" and lines[0].split()[3] == "open=3"
    assert lines[1] == (
        "OPEN-CLAIM lane=arch-lane claim=2026-01-01T09:00:00Z "
        "ROLLING_WORK_LEDGER_2026-01-01-split.md:L2 ticket=OMN-90001 "
        "newest-row=2026-01-01T09:00:00Z kind=CLAIM age=1443h00m rows=1 host=none run=none "
        "leases=none liveness=unknown"
    )
    assert lines[2].startswith("OPEN-CLAIM lane=ancient claim=2026-03-02T08:00:00Z L2 ")
    assert lines[3].startswith("OPEN-CLAIM lane=fresh claim=2026-03-02T09:30:00Z L5 ")
