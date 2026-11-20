"""OMN-24046: the overlays repository is the one home of overlay values.

The onex-overlays plugin under plugins/onex-overlays/overlays/ must hold no overlay the overlays repository also holds:
a copy in the plugin sits lowest in a host's overlay root order and goes stale (the plugin's copy of
node_factory_floor_publish_effect lacked the required limits key), and a host whose roots lack the overlays clone would
read the stale copy and refuse every cycle. The overlays repository cannot be read in CI, so the names it holds are
spelled here and the test never skips; an overlay that moves to the overlays repository adds its name to the list in the
same change that deletes it from the plugin.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_OVERLAYS = REPO_ROOT / "plugins" / "onex-overlays" / "overlays"

HELD_BY_OVERLAYS_REPO = (
    "delegation_routing",
    "node_factory_floor_effect",
    "node_factory_floor_publish_effect",
    "node_job_log_filler_effect",
    "node_tart_host_admission_compute",
    "node_walk_lifecycle_controls_compute",
)


def duplicated(plugin_overlays: Path, held: Iterable[str]) -> list[str]:
    """The sorted names in `held` for which plugin_overlays / name is a directory."""
    return sorted(name for name in held if (plugin_overlays / name).is_dir())


def test_plugin_holds_none_of_the_overlays_the_overlays_repo_holds() -> None:
    assert duplicated(PLUGIN_OVERLAYS, HELD_BY_OVERLAYS_REPO) == []
    # Positive control: the check reads a real directory that still holds overlays, so a pass over a missing or empty tree fails here.
    assert any((child / "overlay.yaml").is_file() for child in PLUGIN_OVERLAYS.iterdir())


def test_control_a_plugin_tree_that_still_ships_a_held_overlay_is_named(tmp_path: Path) -> None:
    plugin = tmp_path / "overlays"
    (plugin / "node_factory_floor_publish_effect").mkdir(parents=True)
    (plugin / "node_factory_floor_publish_effect" / "overlay.yaml").write_text("cycle: 1\n")
    (plugin / "cloud_fill").mkdir()
    assert duplicated(plugin, HELD_BY_OVERLAYS_REPO) == ["node_factory_floor_publish_effect"]


def test_control_a_plugin_tree_holding_none_of_them_is_empty(tmp_path: Path) -> None:
    plugin = tmp_path / "overlays"
    (plugin / "cloud_fill").mkdir(parents=True)
    assert duplicated(plugin, HELD_BY_OVERLAYS_REPO) == []
