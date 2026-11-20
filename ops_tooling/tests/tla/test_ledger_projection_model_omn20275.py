"""The ledger projection model, its results and its verdict agree (OMN-20275, plan unit M6).

``tla/ledger_projection`` holds the TLA+ model of the rendered work-ledger projection, one TLC
configuration per row of ``expected.tsv``, the TLC output of each run in ``results/`` and the
independent review in ``REVIEW.md``. These tests refuse a change that lets them drift apart:

- the review's last verdict approves, and names the sha256 of the model as it is now;
- every configuration has a result produced from the current model and configuration bytes, and
  the result is the one ``expected.tsv`` names;
- every safety and liveness property of the adopted configurations is violated by at least one
  mutation, each mutation flips exactly one design decision, and every adopted pass is backed
  by a reachability witness;
- the README, the design note, fixes the scope, the record identity and the checkpoints.

TLC itself runs on a lab host, not here. Regenerate the results with
``python3 tests/tla/test_ledger_projection_model_omn20275.py --jar <path to tla2tools.jar>``,
which writes each ``results/<config>.out`` with the model and configuration digests on its
first lines. A changed model then needs a fresh review naming its new digest.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

MODEL_DIR = Path(__file__).resolve().parents[2] / "tla" / "ledger_projection"
MODEL = MODEL_DIR / "LedgerProjection.tla"
EXPECTED = MODEL_DIR / "expected.tsv"
REVIEW = MODEL_DIR / "REVIEW.md"
README = MODEL_DIR / "README.md"
CFG_DIR = MODEL_DIR / "cfg"
RESULTS_DIR = MODEL_DIR / "results"

MUTATION_FLAGS = (
    "SkipGap",
    "ContentIdentity",
    "NoSeqDedup",
    "SidecarWatermark",
    "ArrivalOrder",
    "NoRepair",
    "NoBlock",
    "NoHeadProbe",
    "CommitOnReceive",
)
TYPE_INVARIANT = "TypeOK"
KINDS = {"adopted", "variant", "mutation", "witness"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_rows() -> list[tuple[str, str, str]]:
    rows = []
    for line in EXPECTED.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        config, kind, outcome = line.split("\t")
        rows.append((config, kind, outcome))
    return rows


def cfg_flags(text: str) -> dict[str, bool]:
    flags = {}
    for flag in MUTATION_FLAGS:
        match = re.search(rf"^\s*{flag} = (TRUE|FALSE)\s*$", text, re.MULTILINE)
        assert match, f"{flag} is not set"
        flags[flag] = match.group(1) == "TRUE"
    return flags


def cfg_checks(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"^(?:INVARIANTS?|PROPERTY|PROPERTIES)\s+(.+)$", text, re.MULTILINE):
        names.update(match.group(1).split())
    return names


def cfg_constants(text: str) -> str:
    """The CONSTANTS block of a configuration, which fixes the instance and the flags."""
    match = re.search(
        r"^CONSTANTS\n(.*?)^(?:INVARIANTS?|PROPERTY|PROPERTIES)\b", text, re.MULTILINE | re.DOTALL
    )
    assert match, "no CONSTANTS block"
    return match.group(1)


def outcome_of(text: str) -> str:
    """``pass`` or ``violates:<name>``, from one TLC output; ``unknown`` otherwise."""
    if "Model checking completed. No error has been found." in text and "\nrc=0" in text:
        return "pass"
    match = re.search(
        r"^Error: (?:Invariant (\w+) is violated\.|Temporal property (\w+) was violated\.)$",
        text,
        re.MULTILINE,
    )
    if match:
        return f"violates:{match.group(1) or match.group(2)}"
    return "unknown"


def test_projection_model_verdict_names_digest() -> None:
    lines = [
        line
        for line in REVIEW.read_text(encoding="utf-8").splitlines()
        if line.startswith("VERDICT:")
    ]
    assert lines, "REVIEW.md carries no VERDICT line"
    last = lines[-1]
    assert re.match(r"^VERDICT: APPROVE\b", last), f"the last verdict does not approve: {last}"
    match = re.search(r"model-sha256=([0-9a-f]{64})\b", last)
    assert match, f"the last verdict names no model digest: {last}"
    assert match.group(1) == sha256(MODEL), (
        "the approving verdict names another model: the model changed after review "
        f"(verdict {match.group(1)}, model {sha256(MODEL)})"
    )


def test_projection_model_results_match_expected() -> None:
    rows = expected_rows()
    configs = [config for config, _, _ in rows]
    assert len(configs) == len(set(configs)), "expected.tsv names a configuration twice"
    on_disk = sorted(path.stem for path in CFG_DIR.glob("*.cfg"))
    assert sorted(configs) == on_disk, "expected.tsv and cfg/ name different configurations"
    model_digest = sha256(MODEL)
    for config, kind, expected in rows:
        assert kind in KINDS, f"{config}: unknown kind {kind}"
        result = RESULTS_DIR / f"{config}.out"
        assert result.is_file(), f"{config}: no result; run TLC on a lab host"
        text = result.read_text(encoding="utf-8")
        assert f"model-sha256: {model_digest}\n" in text, f"{config}: result is from another model"
        cfg_digest = sha256(CFG_DIR / f"{config}.cfg")
        assert f"cfg-sha256: {cfg_digest}\n" in text, (
            f"{config}: result is from another configuration"
        )
        assert outcome_of(text) == expected, (
            f"{config}: TLC gave {outcome_of(text)}, expected {expected}"
        )


def test_projection_model_every_property_fails_on_a_mutation() -> None:
    rows = expected_rows()
    adopted_checks: set[str] | None = None
    violated_by_mutation: set[str] = set()
    for config, kind, expected in rows:
        text = (CFG_DIR / f"{config}.cfg").read_text(encoding="utf-8")
        flags = cfg_flags(text)
        checks = cfg_checks(text)
        on = [flag for flag, value in flags.items() if value]
        if kind in {"adopted", "witness"}:
            assert not on, f"{config}: an {kind} configuration sets {on}"
        if kind == "adopted":
            assert expected == "pass", f"{config}: an adopted configuration must pass"
            if adopted_checks is None:
                adopted_checks = checks
            assert checks == adopted_checks, f"{config}: checks differ from the other adopted runs"
        if kind in {"mutation", "variant"}:
            assert len(on) == 1, f"{config}: a {kind} flips exactly one decision, not {on}"
        if kind == "mutation":
            name = expected.removeprefix("violates:")
            assert checks == {name}, (
                f"{config}: a mutation checks only the property it must violate"
            )
            violated_by_mutation.add(name)
        if kind == "witness":
            assert expected.startswith("violates:"), f"{config}: a witness must be violated"
    assert adopted_checks, "no adopted configuration"
    properties = adopted_checks - {TYPE_INVARIANT}
    assert {"NoRecordLost", "NoDuplicate", "GapRepairedOrBlocks"} <= properties
    unguarded = properties - violated_by_mutation
    assert not unguarded, f"no mutation violates {sorted(unguarded)}"
    witnesses = [config for config, kind, _ in rows if kind == "witness"]
    assert len(witnesses) >= 3, "the repair, block and tail paths each need a reachability witness"
    adopted_instances = {
        cfg_constants((CFG_DIR / f"{config}.cfg").read_text(encoding="utf-8"))
        for config, kind, _ in rows
        if kind == "adopted"
    }
    for config in witnesses:
        instance = cfg_constants((CFG_DIR / f"{config}.cfg").read_text(encoding="utf-8"))
        assert instance in adopted_instances, f"{config}: witnesses no adopted configuration"


def test_projection_model_design_note_fixes_scope_identity_checkpoints() -> None:
    headings = set(re.findall(r"^## (.+)$", README.read_text(encoding="utf-8"), re.MULTILINE))
    for heading in ("Scope", "Record identity", "Checkpoints", "Gaps", "Results"):
        assert heading in headings, f"README.md has no '## {heading}' section"


def run_tlc(jar: Path, workers: int) -> int:
    """Run every configuration and write its result; returns the number of unexpected outcomes."""
    expected = {config: outcome for config, _, outcome in expected_rows()}
    unexpected = 0
    RESULTS_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ledger-projection-tlc-") as tmp:
        work = Path(tmp)
        shutil.copy(jar, work / "tla2tools.jar")
        shutil.copy(MODEL, work / MODEL.name)
        for cfg in sorted(CFG_DIR.glob("*.cfg")):
            shutil.copy(cfg, work / cfg.name)
            proc = subprocess.run(
                [
                    "java",
                    "-XX:+UseParallelGC",
                    "-cp",
                    "tla2tools.jar",
                    "tlc2.TLC",
                    "-config",
                    cfg.name,
                    "-workers",
                    str(workers),
                    "-deadlock",
                    "-metadir",
                    f"states/{cfg.stem}",
                    MODEL.name,
                ],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            # TLC prints the module and jar paths; keep the work directory out of the record.
            output = f"{proc.stdout}{proc.stderr}".replace(f"{work.resolve()}/", "").replace(
                f"{work}/", ""
            )
            text = (
                f"model-sha256: {sha256(MODEL)}\ncfg-sha256: {sha256(cfg)}\n"
                f"{output}rc={proc.returncode}\n"
            )
            (RESULTS_DIR / f"{cfg.stem}.out").write_text(text, encoding="utf-8")
            got, want = outcome_of(text), expected.get(cfg.stem)
            mark = "ok" if got == want else "UNEXPECTED"
            unexpected += mark != "ok"
            print(f"{mark} {cfg.stem}: {got} (expected {want}), rc={proc.returncode}")
    return unexpected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run TLC over every ledger projection configuration."
    )
    parser.add_argument("--jar", type=Path, required=True, help="path to tla2tools.jar")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    sys.exit(1 if run_tlc(args.jar, args.workers) else 0)
