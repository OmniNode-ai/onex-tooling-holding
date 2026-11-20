# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""The private omnibase_core pre-push host table keeps the shape its reader needs (OMN-20939)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "config" / "lab" / "prepush_hosts.omnibase_core.tsv"
VOCABULARIES = ROOT / "vocabularies"
COLUMNS = 13


def _rows() -> list[list[str]]:
    rows = []
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def test_every_row_has_the_thirteen_columns_the_hook_reads() -> None:
    rows = _rows()
    assert rows, "the private table carries the lab rows"
    for row in rows:
        assert len(row) == COLUMNS, f"{row[0]} has {len(row)} columns"


def test_labels_are_unique_and_modes_are_known() -> None:
    rows = _rows()
    labels = [r[0] for r in rows]
    assert len(labels) == len(set(labels))
    assert {r[11] for r in rows} <= {"authorizing", "shadow", "disabled"}


def test_every_capacity_row_carries_an_absolute_uv_path_and_a_floor() -> None:
    for row in _rows():
        if row[1] == "capacity":
            assert row[5].startswith("/"), row[0]
            assert row[6][0].isdigit(), row[0]


@pytest.mark.parametrize(
    "name",
    ["hardcoded_model_config_lab_denylist.yaml", "decommissioned_patterns.lab.conf"],
)
def test_detector_denylists_are_present(name: str) -> None:
    assert (VOCABULARIES / name).read_text(encoding="utf-8").strip()
