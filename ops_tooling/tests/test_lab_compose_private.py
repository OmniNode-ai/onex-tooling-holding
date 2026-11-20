"""The lab compose files that left omnibase_infra live here and still parse (OMN-20933).

Operator ruling 2026-10-10T21:57:38Z: lab configuration never lives in a shipped
repository. Each file below moved byte-identical from omnibase_infra ``docker/`` to
``deploy/lab/compose/``. An operator brings each one up by hand with ``docker compose
-f``, so a file that stops parsing here is a lab stack that can no longer be started.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

COMPOSE_DIR = Path(__file__).resolve().parents[1] / "deploy" / "lab" / "compose"

MOVED = (
    "docker-compose.infisical-stability.yml",
    "docker-compose.dns-canary.yml",
)


def _load(name: str) -> dict[str, object]:
    path = COMPOSE_DIR / name
    assert path.is_file(), f"{path} is missing"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{name} is not a YAML mapping"
    return document


@pytest.mark.parametrize("name", MOVED)
def test_moved_compose_file_declares_services(name: str) -> None:
    services = _load(name).get("services")
    assert isinstance(services, dict), f"{name} declares no services"
    assert services, f"{name} declares an empty services block"


def test_infisical_stability_keeps_its_own_project_and_joins_the_lane_network() -> None:
    document = _load("docker-compose.infisical-stability.yml")
    # The project name is literal so a run from this directory lands in the same
    # compose project as the copy it replaces, whatever directory it runs from.
    assert document["name"] == "omnibase-infra-infisical-stability"
    networks = document["networks"]
    assert isinstance(networks, dict)
    assert networks["stability"]["external"] is True


def test_dns_canary_overrides_only_the_dns_of_its_runners() -> None:
    services = _load("docker-compose.dns-canary.yml")["services"]
    assert isinstance(services, dict)
    for name, definition in services.items():
        assert set(definition) == {"dns"}, f"{name} overrides more than dns"
