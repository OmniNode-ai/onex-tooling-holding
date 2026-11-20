"""OMN-20864: typed rows preserve actor/model and TERMINAL delegation rules."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from ops_tooling_pkg.ledger import lock

pytestmark = pytest.mark.unit


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tracking" / "ROLLING_WORK_LEDGER.md"
    path.parent.mkdir()
    path.write_text("## Work ledger\n", encoding="utf-8")
    monkeypatch.setenv("ONEX_LEDGER_DETAIL_DIR", str(tmp_path / "detail"))
    monkeypatch.delenv("ONEX_DRY_RUN", raising=False)
    monkeypatch.delenv("ONEX_LEDGER_PATH", raising=False)
    return path


def call(*args: str) -> tuple[int, list[str]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = lock.main(list(args))
    return code, output.getvalue().splitlines()


def test_status_preserves_actor_and_model(ledger: Path) -> None:
    code, lines = call(
        "row",
        "STATUS",
        "--ledger",
        str(ledger),
        "--lane",
        "remote-lane",
        "--actor",
        "script:onex-remote-lane",
        "--model",
        "claude-opus",
        "--text",
        "probe",
    )
    assert code == 0
    assert lines[0].startswith("OK STATUS ")
    row = ledger.read_text(encoding="utf-8").splitlines()[-1]
    assert "| actor=script:onex-remote-lane | model=claude-opus |" in row


@pytest.mark.parametrize(
    ("identity", "expected_code"),
    [
        (("--actor", "script:onex-remote-lane", "--model", "claude-opus"), 0),
        ((), 65),
        (("--actor", "claude:opus:remote-lane", "--model", "claude-opus"), 65),
    ],
)
def test_terminal_machine_exemption_keeps_delegation_required(
    ledger: Path, identity: tuple[str, ...], expected_code: int
) -> None:
    before = ledger.read_text(encoding="utf-8")
    code, lines = call(
        "row",
        "TERMINAL",
        "--ledger",
        str(ledger),
        "--lane",
        "remote-lane",
        "--ticket",
        "OMN-20864",
        "--friction",
        "none",
        "--outcome",
        "done",
        *identity,
    )
    assert code == expected_code
    if expected_code == 0:
        assert lines[0].startswith("OK TERMINAL ")
        row = ledger.read_text(encoding="utf-8").splitlines()[-1]
        assert "| actor=script:onex-remote-lane | model=claude-opus |" in row
    else:
        assert lines[0].startswith("REFUSED 65 ")
        assert "OMN-17427" in lines[0]
        assert ledger.read_text(encoding="utf-8") == before


def test_terminal_executor_with_delegation_preserves_identity(ledger: Path) -> None:
    code, lines = call(
        "row",
        "TERMINAL",
        "--ledger",
        str(ledger),
        "--lane",
        "remote-lane",
        "--ticket",
        "OMN-20864",
        "--friction",
        "none",
        "--outcome",
        "done",
        "--actor",
        "claude:opus:remote-lane",
        "--model",
        "claude-opus",
        "--kv",
        "delegated=1",
        "--kv",
        "runs=r1",
    )
    assert code == 0
    assert lines[0].startswith("OK TERMINAL ")
    row = ledger.read_text(encoding="utf-8").splitlines()[-1]
    assert "| actor=claude:opus:remote-lane | model=claude-opus |" in row
    assert "| delegated=1 | runs=r1" in row


def test_claim_print_only_keeps_cell_order(ledger: Path) -> None:
    before = ledger.read_text(encoding="utf-8")
    code, lines = call(
        "row",
        "CLAIM",
        "--ledger",
        str(ledger),
        "--lane",
        "claim-test",
        "--ticket",
        "OMN-17427",
        "--actor",
        "codex",
        "--model",
        "gpt-6",
        "--worktree",
        "none",
        "--print-only",
    )
    assert code == 0
    assert len(lines) == 1
    assert lines[0].startswith("ROW ")
    assert "ticket=OMN-17427 | actor=codex | model=gpt-6 |" in lines[0]
    assert ledger.read_text(encoding="utf-8") == before
