"""Only a populated client binding can use its default maximum mode."""

from pathlib import Path

import pytest
import yaml
from _observe_only_scan import scan_repository


def _scan(tmp_path: Path, section: dict[str, object]) -> list[str]:
    contract = tmp_path / "contract.yaml"
    contract.write_text(yaml.safe_dump({"client_bindings": {"client": section}}))
    return [finding.locator for finding in scan_repository("sample", tmp_path)]


def test_explicitly_empty_bindings_have_no_effective_default_mode(tmp_path: Path) -> None:
    assert _scan(tmp_path, {"default_max_mode": "observe", "bindings": []}) == []


@pytest.mark.parametrize("bindings", [[{"name": "hook"}], None, {}, ""])
def test_nonempty_or_malformed_bindings_retain_observe_finding(
    tmp_path: Path, bindings: object
) -> None:
    assert _scan(tmp_path, {"default_max_mode": "observe", "bindings": bindings}) == [
        "client_bindings/client/default_max_mode"
    ]


def test_missing_bindings_retain_observe_finding(tmp_path: Path) -> None:
    assert _scan(tmp_path, {"default_max_mode": "observe"}) == [
        "client_bindings/client/default_max_mode"
    ]


def test_empty_bindings_do_not_hide_other_observe_settings(tmp_path: Path) -> None:
    assert _scan(
        tmp_path,
        {"default_max_mode": "observe", "bindings": [], "mode": "report_only"},
    ) == ["client_bindings/client/mode"]


def test_unrelated_empty_list_does_not_hide_default_mode(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text("default_max_mode: observe\nbindings: []\n")
    (finding,) = scan_repository("sample", tmp_path)
    assert finding.locator == "default_max_mode"
