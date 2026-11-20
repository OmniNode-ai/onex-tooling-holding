"""Runs the lab stack reaper model's configurations and pins what each must show (OMN-20864).

The model is ``tla/lab_stack_reaper/LabStackReaper.tla`` (plan unit M47, deliverable 1).
``EXPECTED`` names every configuration's required outcome: ``PASS`` for the adopted design and
its controls, or the one property (an invariant, or the temporal property) a mutation or a
witness must violate. The model digest is the sha256 over
the module and every configuration, in name order, each preceded by its path relative to the model
directory; the independent review in ``REVIEW.md`` names it, and every result file opens with it.

Run on a lab host (rule 21), from anywhere, with java and tla2tools.jar (v1.8.0 or later):

    TLA2TOOLS_JAR=<path to tla2tools.jar> python3 tests/tla/lab_stack_reaper_tlc.py [config ...]

The jar is copied beside the model (gitignored), so TLC prints no path outside the model directory.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[2] / "tla" / "lab_stack_reaper"
MODULE = "LabStackReaper.tla"
PASS = "PASS"
NEVER_REMOVE_LIVE = "NeverRemoveLive"
NO_USER_LOSES_STACK = "NoUserLosesStack"
DEADLINE = "RemovedWithinOneInterval"
OVERDUE_ALARMED = "OverdueIsAlarmed"
EVENTUALLY_REMOVED = "EveryClosedStackRemoved"

# config -> PASS, or the property it must violate.
EXPECTED: dict[str, str] = {
    "adopted": PASS,
    "adopted_two_stacks": PASS,
    "adopted_faults": PASS,
    "adopted_lagged_copy": PASS,
    "adopted_liveness": PASS,
    "adopted_liveness_reopen": PASS,
    "adopted_liveness_two_stacks": PASS,
    "witness_removal": "NoRemovalEver",
    "witness_late_removal": "NoLateRemoval",
    "witness_retry": "NoRetrySucceeded",
    "no_lock": NEVER_REMOVE_LIVE,
    "creator_only_lease": NEVER_REMOVE_LIVE,
    "last_row": NEVER_REMOVE_LIVE,
    "last_row_no_relay": NEVER_REMOVE_LIVE,
    "position_order": NEVER_REMOVE_LIVE,
    "stamp_ts_skewed": NEVER_REMOVE_LIVE,
    "no_fence": NEVER_REMOVE_LIVE,
    "terminal_before_quiesce": NO_USER_LOSES_STACK,
    "owner_by_ticket": DEADLINE,
    "stale_view": DEADLINE,
    "no_retry": DEADLINE,
    "silent_failure": OVERDUE_ALARMED,
    "silent_abort": OVERDUE_ALARMED,
    "skip_in_flight": EVENTUALLY_REMOVED,
}
TLC_TIMEOUT_S = 3600


def model_files(model_dir: Path = MODEL_DIR) -> list[Path]:
    """The module, then every configuration in name order."""
    return [model_dir / MODULE, *sorted((model_dir / "cfg").glob("*.cfg"))]


def model_digest(model_dir: Path = MODEL_DIR) -> str:
    digest = hashlib.sha256()
    for path in model_files(model_dir):
        digest.update(path.relative_to(model_dir).as_posix().encode() + b"\n")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_config(name: str, jar: Path, workers: int) -> int:
    """One TLC run; writes results/<name>.out opening with the model digest."""
    out = MODEL_DIR / "results" / f"{name}.out"
    out.parent.mkdir(exist_ok=True)
    local_jar = MODEL_DIR / "tla2tools.jar"
    if local_jar.is_symlink() or not local_jar.exists():
        local_jar.unlink(missing_ok=True)
        shutil.copyfile(jar, local_jar)
    argv = [
        "java",
        "-XX:+UseParallelGC",
        "-cp",
        "tla2tools.jar",
        "tlc2.TLC",
        "-config",
        f"cfg/{name}.cfg",
        "-workers",
        str(workers),
        "-deadlock",
        "-noGenerateSpecTE",
        "-metadir",
        f"states/{name}",
        MODULE,
    ]
    try:
        proc = subprocess.run(
            argv,
            cwd=MODEL_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=TLC_TIMEOUT_S,
        )
        rc, text = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        rc, text = 124, f"TLC timed out after {TLC_TIMEOUT_S}s\n"
    out.write_text(f"model_digest={model_digest()}\n{text}rc={rc}\n", encoding="utf-8")
    return rc


def main(argv: list[str]) -> int:
    jar = os.environ.get("TLA2TOOLS_JAR", "").strip()
    if not jar:
        print("set TLA2TOOLS_JAR to the path of tla2tools.jar", file=sys.stderr)
        return 2
    names = argv or sorted(EXPECTED)
    unknown = sorted(set(names) - set(EXPECTED))
    if unknown:
        print(f"no expectation for {', '.join(unknown)}", file=sys.stderr)
        return 2
    workers = int(os.environ.get("TLC_WORKERS", "4"))
    for name in names:
        rc = run_config(name, Path(jar), workers)
        print(f"{name}: rc={rc} expected={EXPECTED[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
