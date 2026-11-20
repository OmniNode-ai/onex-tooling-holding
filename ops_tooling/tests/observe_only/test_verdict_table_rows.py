"""A verdict row's mode matches a client input rather than configuring a check."""

from pathlib import Path

import pytest
import yaml
from _observe_only_scan import scan_repository


def _scan(tmp_path: Path, document: dict[str, object]) -> list[str]:
    contract = tmp_path / "contract.yaml"
    contract.write_text(yaml.safe_dump(document))
    return [finding.locator for finding in scan_repository("sample", tmp_path)]


@pytest.mark.parametrize("action", ["proceed_native", "refuse"])
def test_verdict_row_mode_with_action_is_not_a_setting(tmp_path: Path, action: str) -> None:
    assert (
        _scan(tmp_path, {"verdict_table": [{"row": "x", "mode": "observe", "action": action}]})
        == []
    )


def test_verdict_row_mode_without_action_keeps_finding(tmp_path: Path) -> None:
    assert _scan(tmp_path, {"verdict_table": [{"row": "x", "mode": "observe"}]}) == [
        "verdict_table/[0]/mode"
    ]


def test_nested_verdict_table_mode_keeps_finding(tmp_path: Path) -> None:
    assert _scan(
        tmp_path,
        {"nested": {"verdict_table": [{"row": "x", "mode": "observe", "action": "refuse"}]}},
    ) == ["nested/verdict_table/[0]/mode"]


def test_verdict_row_keeps_other_observe_settings(tmp_path: Path) -> None:
    assert _scan(
        tmp_path,
        {
            "verdict_table": [
                {"row": "x", "mode": "observe", "action": "refuse", "report_only": True}
            ]
        },
    ) == ["verdict_table/[0]/report_only"]


def test_top_level_mode_beside_verdict_table_keeps_finding(tmp_path: Path) -> None:
    assert _scan(
        tmp_path,
        {
            "mode": "observe",
            "verdict_table": [{"row": "x", "mode": "observe", "action": "refuse"}],
        },
    ) == ["mode"]
