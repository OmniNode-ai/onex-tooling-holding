"""Private deployment settings must not shadow the owning routing contract."""

from pathlib import Path

import omnimarket
import pytest
from omnimarket.handlers.node_overlay_reader import find_node_overlay
from omnimarket.routing.routing_tiers_path import (
    ROUTING_TIERS_OVERLAY_NODE,
    ROUTING_TIERS_PACKAGED_DEFAULT_PATH,
    resolve_routing_tiers_path,
)

ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = ROOT / "config/onex/overlays"
CONFIGS = Path(omnimarket.__file__).resolve().parent / "configs"


def test_private_configuration_does_not_copy_the_routing_ladder() -> None:
    environ = {"ONEX_SKILL_OVERLAY_ROOTS": str(OVERLAYS)}
    assert find_node_overlay(ROUTING_TIERS_OVERLAY_NODE, environ) is None


def test_private_install_resolves_the_owning_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEX_SKILL_OVERLAY_ROOTS", str(OVERLAYS))
    monkeypatch.delenv("DELEGATION_ROUTING_TIERS_PATH", raising=False)
    assert resolve_routing_tiers_path() == ROUTING_TIERS_PACKAGED_DEFAULT_PATH


def test_runtime_loader_accepts_the_owning_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real loader, including its registered backend placements."""
    from omnimarket.nodes.node_delegation_routing_reducer.handlers import (
        handler_delegation_routing as routing,
    )

    monkeypatch.setenv("ONEX_SKILL_OVERLAY_ROOTS", str(OVERLAYS))
    monkeypatch.delenv("DELEGATION_ROUTING_TIERS_PATH", raising=False)
    monkeypatch.setenv("BIFROST_CONTRACT_PATH", str(CONFIGS / "bifrost_delegation.yaml"))
    monkeypatch.delenv("BIFROST_OVERLAY_PATH", raising=False)
    monkeypatch.setattr(routing, "_config", None)
    monkeypatch.setattr(routing, "_config_spread_peers", None)
    monkeypatch.setattr(routing, "_config_spread_weights", None)
    config = routing._get_config()
    assert config.tiers
    for tier in config.tiers:
        assert tier.models
        refs = [model.backend_ref for model in tier.models]
        assert len(refs) == len(set(refs))


def test_other_private_node_overlays_are_still_discoverable() -> None:
    """Positive control: removing the ladder must not hide deployment settings."""
    node = "node_integration_sweep_orchestrator"
    assert find_node_overlay(node, {"ONEX_SKILL_OVERLAY_ROOTS": str(OVERLAYS)}) == (
        OVERLAYS / node / "overlay.yaml"
    )
