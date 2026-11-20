"""The retired Mac Studio rung is declared nowhere and takes no share (OMN-20489, OMN-17427).

OMN-20489 kept `reasoning` off the Studio rung, which served Qwen3.8-27B at about 19 tokens a
second under a 120 s per-call ceiling. The lab-host-d planner was retired on 2026-10-27 (nothing listens
on :8130), so the rung is gone from the lane overlay and host-drift stops reporting its served
model as refused. The classes it served route to local-heavy-reasoning on lab-host-a, which serves the
same model. This test holds that the rung stays gone and that no spread peer is offered any class
the rung used to serve.
"""

from __future__ import annotations

from pathlib import Path

import omnimarket
import pytest
import yaml
from omnibase_infra.runtime.render_bifrost_delegation_contract import (
    render_bifrost_delegation_contract,
)
from omnimarket.adapters.llm.bifrost.config_loader_bifrost_delegation import (
    load_bifrost_backend_placements,
)
from omnimarket.models.delegation.model_delegation_backend_placement import (
    ModelPlacedDelegationBackend,
)

pytestmark = [pytest.mark.unit]

OVERLAY = (
    Path(__file__).resolve().parents[1] / "config" / "lab" / "lane-overlays" / "dev.bifrost.yaml"
)
BASE_CONTRACT = Path(omnimarket.__file__).resolve().parent / "configs" / "bifrost_delegation.yaml"

STUDIO = "local-studio-planner"
RUNG = "local-heavy-reasoning"


def _placed(tmp_path: Path) -> dict[str, ModelPlacedDelegationBackend]:
    rendered = render_bifrost_delegation_contract(
        source_path=BASE_CONTRACT,
        overlay_path=OVERLAY,
        target_path=tmp_path / "rendered.yaml",
        environ={},
        verify_endpoints=False,
    )
    return {
        backend.backend_id: backend
        for backend in load_bifrost_backend_placements(config_path=rendered)
    }


def test_the_retired_studio_rung_is_not_declared(tmp_path: Path) -> None:
    assert STUDIO not in _placed(tmp_path)
    declared = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))["backends"]
    assert STUDIO not in {b["backend_id"] for b in declared}
    assert not any(":8130/" in b["endpoint_url"] for b in declared)


def test_the_classes_the_studio_served_stay_on_the_rung(tmp_path: Path) -> None:
    placed = _placed(tmp_path)
    for task_class in ("review", "reasoning", "planning", "research", "escalation"):
        assert STUDIO not in _spread_group(placed, task_class)


def _spread_group(placed: dict[str, ModelPlacedDelegationBackend], task_class: str) -> list[str]:
    """The rung and each spread peer offered the class, in declaration order."""
    members = [RUNG]
    for backend_id, backend in placed.items():
        placement = backend.placement
        if RUNG not in placement.fallback_for:
            continue
        if placement.use_for is not None and task_class not in placement.use_for:
            continue
        members.append(backend_id)
    return members
