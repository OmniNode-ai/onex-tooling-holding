"""The shell refusal carries the failed verb's own error before its detail path."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "plugins" / "omni" / "scripts" / "entrypoint_lib.sh"


def run_verb(
    tmp_path: Path, fake_body: str, *, earlier_verb: bool = False,
) -> subprocess.CompletedProcess[str]:
    fake = tmp_path / "ledger.py"
    fake.write_text(fake_body, encoding="utf-8")
    script = r"""
export registry_root="$TEST_ROOT/home"
export ONEX_LEDGER_PATH="$TEST_ROOT/ledger.md"
export ONEX_LEDGER_DETAIL_DIR="$TEST_ROOT/detail"
unset ONEX_DRY_RUN
ENTRY_NAME=t
source "$LIB"
entry_verb() {
  printf '$ onex-ledger %s\n' "$*" >>"$DETAIL"
  python3 "$FAKE" "$@" >>"$DETAIL" 2>&1
}
entry_start
if [ "$EARLIER_VERB" = 1 ]; then
  entry_verb inbox old || entry_verb_failed $?
fi
entry_verb inbox x || entry_verb_failed $?
"""
    return subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "TEST_ROOT": str(tmp_path),
            "LIB": str(LIB),
            "FAKE": str(fake),
            "EARLIER_VERB": "1" if earlier_verb else "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_traceback_error_reaches_refusal_before_detail_path(tmp_path: Path) -> None:
    result = run_verb(
        tmp_path,
        'import sys\n'
        'print("Traceback (most recent call last):", file=sys.stderr)\n'
        'print("ValueError: hatch hook could not read contract.yaml", file=sys.stderr)\n'
        'sys.exit(2)\n',
    )
    assert result.returncode == 2
    refusals = [line for line in result.stdout.splitlines() if line.startswith("REFUSED ")]
    assert len(refusals) == 1
    assert refusals[0].startswith(
        "REFUSED 2 onex-ledger-command: the ledger command exited 2: "
        "ValueError: hatch hook could not read contract.yaml; detail="
    )


def test_silent_failure_keeps_original_reason(tmp_path: Path) -> None:
    result = run_verb(tmp_path, "import sys\nsys.exit(2)\n")
    assert result.returncode == 2
    detail, = (tmp_path / "detail").iterdir()
    assert result.stdout.splitlines()[0] == (
        f"REFUSED 2 onex-ledger-command: the ledger command exited 2; detail={detail}"
    )


def test_typed_refusal_is_preserved_verbatim(tmp_path: Path) -> None:
    result = run_verb(tmp_path, 'import sys\nprint("REFUSED 65 grammar: bad row")\nsys.exit(65)\n')
    assert result.returncode == 65
    assert result.stdout == "REFUSED 65 grammar: bad row\n"


def test_silent_failure_ignores_earlier_successful_verb_error(tmp_path: Path) -> None:
    result = run_verb(
        tmp_path,
        'import sys\n'
        'if sys.argv[-1] == "old":\n'
        '    print("Error: old")\n'
        '    sys.exit(0)\n'
        'sys.exit(2)\n',
        earlier_verb=True,
    )
    assert result.returncode == 2
    assert "Error: old" not in result.stdout
    detail, = (tmp_path / "detail").iterdir()
    assert result.stdout.splitlines()[0] == (
        f"REFUSED 2 onex-ledger-command: the ledger command exited 2; detail={detail}"
    )
