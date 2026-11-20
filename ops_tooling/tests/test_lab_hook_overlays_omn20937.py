# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-20937: the lab hosts of omniclaude's hooks live here, not in the shipped repository.

Four files moved byte-identical out of omniclaude: the hook edge's lane broker table,
the dispatch claim gate's host list, the gap skill's lab legacy pattern and the code
graph query's embedding service. Their readers are standard library only (a bash
parser for the first), so the shapes below are checked line by line, not through a
YAML library alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

LAB = Path(__file__).resolve().parents[1] / "config" / "lab"


def _load(name: str) -> dict[str, object]:
    loaded = yaml.safe_load((LAB / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), name
    return loaded


def test_hook_edge_lane_table_holds_the_three_lane_brokers() -> None:
    table = _load("hook_edge_lane.yaml")
    assert table["lane_host"] == "192.0.2.127"
    lanes = table["known_lanes"]
    assert isinstance(lanes, dict)
    assert {name: entry["bootstrap_servers"] for name, entry in lanes.items()} == {
        "dev": "192.0.2.127:19092",
        "lane-i": "192.0.2.127:39092",
        "prod": "192.0.2.127:49092",
    }


def test_hook_edge_lane_table_keeps_the_shape_the_shell_resolver_parses() -> None:
    """Two-space lane keys, four-space `bootstrap_servers:` lines, a column-0 `known_lanes:`."""
    lines = (LAB / "hook_edge_lane.yaml").read_text(encoding="utf-8").splitlines()
    assert "known_lanes:" in lines
    lane_keys = [m.group(1) for line in lines if (m := re.fullmatch(r"  ([a-z-]+):", line))]
    brokers = [line for line in lines if re.fullmatch(r'    bootstrap_servers: "[^"#]+"', line)]
    assert lane_keys == ["dev", "lane-i", "prod"]
    assert len(brokers) == len(lane_keys)


def test_dispatch_claim_hosts_is_a_flat_list_with_the_lab_host_first() -> None:
    assert _load("dispatch_claim_hosts.yaml")["hosts"] == ["192.0.2.127"]
    items = [
        line
        for line in (LAB / "dispatch_claim_hosts.yaml").read_text(encoding="utf-8").splitlines()
        if line.startswith("  - ")
    ]
    assert items == ['  - "192.0.2.127"']


def test_gap_legacy_denylist_entry_has_the_shipped_entry_shape() -> None:
    patterns = _load("gap_legacy_denylist.yaml")["patterns"]
    assert isinstance(patterns, list) and len(patterns) == 1
    entry = patterns[0]
    assert entry["pattern"] == "192.0.2.126:29092"
    assert set(entry) == {"pattern", "reason", "replacement_hint"}


def test_code_graph_query_embedding_url_is_one_flat_line() -> None:
    assert _load("code_graph_query.yaml") == {"embedding_url": "http://192.0.2.126:8100"}
    flat = [
        line
        for line in (LAB / "code_graph_query.yaml").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert flat == ['embedding_url: "http://192.0.2.126:8100"']


def test_a_nested_embedding_line_would_not_be_flat() -> None:
    """Positive control: the flat-line check can fail."""
    nested = ["embedding:", '  url: "http://x"']
    assert nested != ['embedding_url: "http://x"']
    assert not re.fullmatch(r'embedding_url: "[^"]+"', nested[0])
