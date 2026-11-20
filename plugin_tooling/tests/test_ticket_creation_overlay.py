"""The ticket_creation overlay locates the plan repository for the public guard (OMN-17942).

The public ticket-creation guard may not name the private plan repository or say
where it lives, so its plan-task exemption reads the clone's location from this
overlay through the shared overlay resolver. The guard's policy names the two keys
below; this pins that the committed overlay carries them, and that the location is
relative to the workspace root and not a home-directory path.
"""

from __future__ import annotations

from pathlib import Path

import yaml

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "onex-overlays"
    / "overlays"
    / "ticket_creation"
    / "overlay.yaml"
)


def _load() -> dict[str, object]:
    document = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_the_overlay_names_the_workspace_root_variable() -> None:
    assert _load()["workspace_root_env"] == "registry_root"


def test_the_plan_repository_is_relative_to_the_workspace_root() -> None:
    location = _load()["plan_repo_path"]
    assert isinstance(location, str)
    assert location.strip() == location and location
    assert not location.startswith(("/", "~")), "relative, never a home-directory path"
    home_prefix = "/" + "Users" + "/"  # assembled: the repository bans the literal
    assert home_prefix not in OVERLAY.read_text(encoding="utf-8"), "no home path"
