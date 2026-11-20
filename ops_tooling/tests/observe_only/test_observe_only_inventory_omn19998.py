"""The inventory of observe-only paths and the ratchet that refuses a new one (OMN-19998).

RULING 2026-09-29T12:02:35Z: no observe-only, report-only, shadow or advisory modes; every checker
acts or blocks, and the existing ones are converted. Plan unit N3 gives two acceptance criteria:

* AC1: ``observe_only_inventory.yaml`` lists every effective observe-only path in the registry
  repositories, each with an owner. The tests below read that file against a scan of the
  repositories, in both directions: a path the scan finds that the file does not list fails, and an
  entry whose path the scan no longer finds fails, so converting a path means deleting its entry.
* AC2: a planted ``continue-on-error: true`` on a gate job, or a planted ``mode: report_only``,
  fails (``-k observe_only_planted_fails``). Each planted sample is written into a scratch tree and
  run through the same comparison the live check uses; each has a positive control (the clean tree
  is admitted) so a refusal is the check and not a broken run.

Without ``ONEX_OBSERVE_ONLY_REGISTRY_ROOT`` the live comparison covers this checkout only, which is
how every change runs it: the required job ``nonblocking-path-inventory`` and the pre-commit hook
(OMN-19998, ``test_observe_only_required_scope_omn19998.py``). The scheduled workflow
``observe-only-inventory-cleanup`` sets it to a directory holding a checkout of every repository the
liveness sources declaration names, and then nothing less than all of them passes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from _observe_only_scan import (
    INTERNAL_REPOSITORY,
    INVENTORY_RELATIVE,
    KINDS,
    REGISTRY_ENV,
    Comparison,
    Entry,
    added_elsewhere,
    base_inventory,
    compare,
    declared_repositories,
    judge,
    live_scope,
    load_inventory,
    render_entries,
    scan_repository,
    scan_scope,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
# OMN-17427: the ref this change is judged against. Set, a stale entry of another repository that
# the base already lists does not fail the change (that repository's merge made it stale; the
# workflow observe-only-inventory-cleanup deletes it). Unset, every stale entry fails.
BASE_ENV = "ONEX_OBSERVE_ONLY_BASE_REF"
PLACEHOLDERS = {"", "unknown", "none", "tbd", "n/a", "-"}

GATE_WORKFLOW = """\
name: CI
on: [pull_request]
jobs:
  gate:
    name: gate
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: uv run pytest -q
"""

CLEAN_WORKFLOW = GATE_WORKFLOW.replace("    continue-on-error: true\n", "")

REPORT_ONLY_CONTRACT = """\
name: node_planted
mode: report_only
"""


def _planted_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / INTERNAL_REPOSITORY
    for relative, text in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return repo


def _compare_planted(tmp_path: Path, files: dict[str, str]) -> Comparison:
    """The live comparison, against the real inventory, over a scratch tree holding ``files``."""
    repo = _planted_tree(tmp_path, files)
    findings = scan_repository(INTERNAL_REPOSITORY, repo)
    return compare(load_inventory(ROOT), findings, {INTERNAL_REPOSITORY})




def test_inventory_file_schema_and_scope_are_declared() -> None:
    document = yaml.safe_load((ROOT / INVENTORY_RELATIVE).read_text(encoding="utf-8"))
    assert document["schema_version"] == "observe-only-inventory/v1"
    assert set(document) == {"schema_version", "repositories", "entries"}
    entry_repos = {entry.repo for entry in load_inventory(ROOT)}
    assert entry_repos <= set(declared_repositories(ROOT))


def test_inventory_matches_scan_of_the_registry() -> None:
    """AC1: every effective observe-only path is listed with an owner, and nothing stale is."""
    scope = live_scope(ROOT, os.environ)
    assert scope[0] == (INTERNAL_REPOSITORY, ROOT)
    entries = load_inventory(ROOT)
    comparison = compare(entries, scan_scope(scope), {repository for repository, _ in scope})
    base_entries = base_inventory(ROOT, os.environ.get(BASE_ENV))
    if base_entries is not None:
        added = added_elsewhere(entries, base_entries)
        assert not added, (
            "entries of other repositories added by this change. A change here is judged against "
            "this checkout only, so an entry for another repository is not how its path gets in; "
            f"remove them from {INVENTORY_RELATIVE}:\n" + render_entries(added)
        )
    verdict = judge(comparison, base_entries)
    _report_elsewhere(verdict.elsewhere)
    result = verdict.blocking
    assert not result.unlisted, (
        "new observe-only paths, which the inventory does not list. Make each check act or block; "
        f"an entry is not how a new path gets in ({INVENTORY_RELATIVE} lists only the paths that "
        "existed when it was written). The entry each would need:\n"
        + render_entries(result.unlisted)
    )
    assert not result.stale, (
        f"inventory entries whose path the scan no longer finds, added by this change or of "
        f"{INTERNAL_REPOSITORY} itself. Delete them from {INVENTORY_RELATIVE}:\n"
        + render_entries(result.stale)
    )
    if REGISTRY_ENV in os.environ:
        assert {repository for repository, _ in scope} == set(declared_repositories(ROOT))


def _report_elsewhere(elsewhere: list[Entry]) -> None:
    """Name the stale entries left to the cleanup in the job summary, without failing on them."""
    if not elsewhere:
        return
    text = (
        f"{len(elsewhere)} inventory entries name paths their own repository converted; the "
        "workflow observe-only-inventory-cleanup deletes them (OMN-17427):\n"
        + render_entries(elsewhere)
    )
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"```text\n{text}\n```\n")










def test_observe_only_planted_fails_report_only_mode(tmp_path: Path) -> None:
    """AC2: a planted ``mode: report_only`` fails."""
    result = _compare_planted(tmp_path, {"contracts/contract.yaml": REPORT_ONLY_CONTRACT})
    assert [(finding.kind, finding.locator) for finding in result.unlisted] == [
        ("observe_mode", "mode")
    ]
    assert not result.ok








