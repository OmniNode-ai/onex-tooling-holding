"""Every node package's contract.yaml names handlers, models and entry points that exist.

OMN-20563: the canonical-shape burn-down moves modules into ``src/ops_tooling_pkg/nodes/``.
A contract that names a handler class, a model or a console entry point that does not resolve
is a contract that lies, so this test resolves each one.
"""

from __future__ import annotations

import importlib
from importlib.metadata import distribution
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

NODES = Path(__file__).resolve().parents[2] / "src" / "ops_tooling_pkg" / "nodes"
CONTRACTS = sorted(NODES.glob("node_*/contract.yaml"))


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _resolve(dotted: str) -> type:
    module, _, attr = dotted.rpartition(".")
    resolved = getattr(importlib.import_module(module), attr)
    assert isinstance(resolved, type), f"{dotted} is not a class"
    return resolved


def test_there_is_at_least_one_node() -> None:
    assert CONTRACTS, f"no node contract under {NODES}"


def test_installed_onex_nodes_equal_the_opted_in_contracts() -> None:
    expected: dict[str, str] = {}
    for path in sorted(NODES.glob("*/contract.yaml")):
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected.update(contract.get("entry_points", {}).get("onex.nodes", {}))
    registered = [
        ep for ep in distribution("ops-tooling-pkg").entry_points if ep.group == "onex.nodes"
    ]
    installed = {ep.name: ep.value for ep in registered}
    assert installed == expected, (
        f"opted-in-but-not-registered: {sorted(expected.keys() - installed.keys())}; "
        f"registered-but-not-opted-in: {sorted(installed.keys() - expected.keys())}; "
        "entry point metadata differs from contracts; run uv sync to rebuild it"
    )
    for ep in registered:
        ep.load()


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda p: p.parent.name)
def test_contract_name_matches_its_package(contract: Path) -> None:
    assert f"node_{_load(contract)['name']}" == contract.parent.name


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda p: p.parent.name)
def test_contract_handlers_resolve_to_def_b_handlers(contract: Path) -> None:
    routing = _load(contract)["handler_routing"]
    assert routing["routing_strategy"] in ("operation_match", "payload_type_match")
    operations = [entry["operation"] for entry in routing["handlers"]]
    assert len(operations) == len(set(operations)), "an operation is routed twice"
    for entry in routing["handlers"]:
        handler = entry["handler"]
        cls = getattr(importlib.import_module(handler["module"]), handler["name"])
        assert isinstance(cls, type)
        assert cls.__name__.startswith("Handler")
        assert callable(cls.__dict__.get("handle")), f"{cls.__name__} has no handle()"
        for key in ("input_model", "output_model"):
            model = _resolve(entry[key])
            assert model.__name__.startswith("Model"), f"{entry[key]} is not a Model"
        hints = cls.__dict__["handle"].__annotations__
        assert hints["request"] == _resolve(entry["input_model"]).__name__
        assert hints["return"] == _resolve(entry["output_model"]).__name__


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda p: p.parent.name)
def test_contract_entry_points_match_the_package_metadata(contract: Path) -> None:
    declared = _load(contract).get("entry_points", {}).get("console_scripts", {})
    # This package's own metadata, not every distribution's: omnimarket ships a console script
    # of the same name for the architecture discovery node it moved there (OMN-20679), and the
    # environment's merged view answers with whichever distribution it lists last.
    installed = {
        ep.name: ep.value
        for ep in distribution("ops-tooling-pkg").entry_points
        if ep.group == "console_scripts"
    }
    for name, target in declared.items():
        assert installed.get(name) == target, (
            f"{name}: contract {target}, installed {installed.get(name)}"
        )


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda p: p.parent.name)
def test_contract_data_files_exist(contract: Path) -> None:
    for rel in _load(contract).get("data_files", {}).values():
        assert (contract.parent / rel).is_file(), rel
