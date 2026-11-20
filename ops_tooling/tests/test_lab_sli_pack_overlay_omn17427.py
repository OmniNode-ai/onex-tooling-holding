"""Our lab explicitly enables omnimarket's lab SLI pack through its overlay (OMN-17427)."""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


def test_lab_sli_pack_overlay_enables_only_status() -> None:
    path = REPO / "config/onex/overlays/lab_sli_pack/overlay.yaml"
    assert path.is_file()
    overlay = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(overlay, dict)
    assert set(overlay) == {"status"}
    assert isinstance(overlay["status"], str)
    assert overlay["status"] == "enabled"
