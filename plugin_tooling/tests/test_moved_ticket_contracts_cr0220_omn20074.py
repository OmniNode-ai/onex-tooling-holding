"""The OMN-19922 ticket contract lives in this repository (OMN-20074).

The scheduled closer resolves a ticket's contract only from ``contracts/<id>.yaml`` on a product
repository's default branch; the change-control repository is being retired.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
MOVED_IDS = ("OMN-19922",)


@pytest.mark.parametrize("ticket_id", MOVED_IDS)
def test_moved_contract_exists(ticket_id: str) -> None:
    assert (CONTRACTS / f"{ticket_id}.yaml").is_file()


@pytest.mark.parametrize("ticket_id", MOVED_IDS)
def test_moved_contract_is_a_mapping_naming_its_ticket(ticket_id: str) -> None:
    data = yaml.safe_load((CONTRACTS / f"{ticket_id}.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["ticket_id"] == ticket_id
