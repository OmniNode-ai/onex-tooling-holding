"""AGENTS.md carries the lab-proof lane rule of registry_root#602 (OMN-19629).

Codex working in this repository does not load ``$registry_root/CLAUDE.md`` or the registry_root
lane-rules block, so a rule that exists only there does not reach it. registry_root#602
(OMN-18893) moved lab proofs on lab-host-a from the shared dev runtime to a pre-PR slot; this
repository's AGENTS.md states that rule itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

AGENTS = Path(__file__).resolve().parents[1] / "AGENTS.md"


def _section() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    heading = "## Proving a change on the lab before the pull request"
    assert heading in text, "AGENTS.md has no lab-proof section"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def test_lane_rules_lab_proof_section_cites_its_source() -> None:
    section = _section()
    assert "registry_root#602" in section
    assert "OMN-18893" in section


@pytest.mark.parametrize(
    "needle",
    [
        "prepr-<n>-a",
        "prepr_verify_lane.sh --slot <n> --worktree <wt> --reason <r>",
        "prepr_teardown_slot.sh --slot <n> --reason <r>",
        "28085/28086",
        "38085/38086",
        "CLEAN report",
        "capacity",
        "lab-host-c",
        "lab-host-b",
        "host, the lane, the command and what was observed",
    ],
)
def test_lane_rules_lab_proof_section_states_the_rule(needle: str) -> None:
    assert needle in _section(), needle


def test_lane_rules_lab_proof_section_forbids_the_shared_dev_runtime() -> None:
    section = _section()
    assert "never on the shared dev runtime" in section
    assert "only when no slot or surface can carry the proof" in section
