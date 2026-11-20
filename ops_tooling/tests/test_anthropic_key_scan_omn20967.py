# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""No Anthropic key value can enter an overlay or a workflow (OMN-20967, AC5).

Scope plan "Where keys live and how CI reaches them": no Anthropic key in any repository, Actions
variable, Actions secret or workflow; the private overlay holds `secret://` references only.

Integrate-before-build finding (2026-10-12). No committed gate in this repository refuses an
Anthropic key prefix: it carries no detect-secrets baseline and no trufflehog or gitleaks job.
Elsewhere, detect-secrets (omniclaude) ships no Anthropic detector, and the trufflehog jobs of
omnimarket and omniclaude run with --only-verified, which passes a key the vendor no longer
accepts. This ratchet is the prefix refuser for the two paths named below.

Two refusals, both over every file under the scanned paths and neither with an allowlist:

* the Anthropic key prefix anywhere in a file;
* in an overlay YAML, any field named like a credential whose value is not a `secret://`
  reference. A field whose name ends in `_env` names an environment variable, not a value, and is
  exempt from the reference rule only; the prefix refusal still reads it.

The positive controls assemble their key-shaped strings at test time. Nothing key-shaped is
spelled in this file.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit]

REPO = Path(__file__).resolve().parents[1]
OVERLAYS = REPO / "config" / "onex" / "overlays"
WORKFLOWS = REPO / ".github" / "workflows"

# Assembled so this file never spells the prefix it forbids elsewhere.
ANTHROPIC_PREFIX = "sk" + "-" + "ant" + "-"

# A field name is a credential field when one of these words is a whole underscore-separated
# part of it (`max_context_tokens` is not one, `api_key_ref` and `bearer_token` are).
CREDENTIAL_FIELD = re.compile(
    r"(^|_)(api_?key|secret|secret_key|private_key|access_key|token|password|passwd"
    r"|credentials?|authorization|bearer)(_|$)"
)
SECRET_REFERENCE = re.compile(r"^secret://[^\s/][^\s]*$")


def _text_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in suffixes)


def scan_prefix(files: list[Path], root: Path) -> list[str]:
    """Every file that spells the Anthropic key prefix."""
    return [
        f"{path.relative_to(root)}: Anthropic key prefix"
        for path in files
        if ANTHROPIC_PREFIX in path.read_text(encoding="utf-8", errors="replace")
    ]


def _leaves(node: Any) -> Iterator[Any]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _leaves(value)
    elif isinstance(node, list):
        for value in node:
            yield from _leaves(value)
    else:
        yield node


def _credential_violations(node: Any, where: str) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            name = str(key).lower().replace("-", "_")
            here = f"{where}/{key}"
            if name.endswith("_env"):
                name = name[: -len("_env")]
                holds_env_name = True
            else:
                holds_env_name = False
            if not holds_env_name and CREDENTIAL_FIELD.search(name):
                for leaf in _leaves(value):
                    if not (isinstance(leaf, str) and SECRET_REFERENCE.match(leaf)):
                        yield f"{here}: credential field is not a secret:// reference"
            else:
                yield from _credential_violations(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _credential_violations(value, f"{where}[{index}]")


def scan_credential_fields(files: list[Path], root: Path) -> list[str]:
    found: list[str] = []
    for path in files:
        if path.suffix not in (".yaml", ".yml"):
            continue
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            found.extend(
                f"{path.relative_to(root)}: {message}"
                for message in _credential_violations(document, "")
            )
    return found


def scan_overlays(root: Path) -> list[str]:
    files = _text_files(root, (".yaml", ".yml", ".json", ".md", ".txt", ".env"))
    return scan_prefix(files, root) + scan_credential_fields(files, root)


def scan_workflows(root: Path) -> list[str]:
    return scan_prefix(_text_files(root, (".yaml", ".yml")), root)


def _fake_key() -> str:
    return ANTHROPIC_PREFIX + "api03-" + "A" * 40


def test_overlays_hold_no_key_value_and_only_secret_references() -> None:
    files = _text_files(OVERLAYS, (".yaml", ".yml", ".json", ".md", ".txt", ".env"))
    assert len(files) >= 10, "the overlay scan found too few files to mean anything"
    assert scan_overlays(OVERLAYS) == []


def test_workflows_hold_no_key_value() -> None:
    files = _text_files(WORKFLOWS, (".yaml", ".yml"))
    assert len(files) >= 5, "the workflow scan found too few files to mean anything"
    assert scan_workflows(WORKFLOWS) == []


def test_positive_control_prefix_in_an_overlay_fails_the_scan(tmp_path: Path) -> None:
    overlay = tmp_path / "node_x" / "overlay.yaml"
    overlay.parent.mkdir()
    overlay.write_text(f"schema_version: x\nnote: {_fake_key()}\n", encoding="utf-8")
    assert scan_overlays(tmp_path) == ["node_x/overlay.yaml: Anthropic key prefix"]


def test_positive_control_prefix_in_a_comment_fails_the_scan(tmp_path: Path) -> None:
    overlay = tmp_path / "node_x" / "overlay.yaml"
    overlay.parent.mkdir()
    overlay.write_text(f"# {_fake_key()}\nschema_version: x\n", encoding="utf-8")
    assert scan_overlays(tmp_path) == ["node_x/overlay.yaml: Anthropic key prefix"]


def test_positive_control_prefix_in_a_workflow_fails_the_scan(tmp_path: Path) -> None:
    workflow = tmp_path / "gate.yml"
    workflow.write_text(
        "name: gate\njobs:\n  j:\n    steps:\n      - run: echo\n        env:\n"
        f"          K: {_fake_key()}\n",
        encoding="utf-8",
    )
    assert scan_workflows(tmp_path) == ["gate.yml: Anthropic key prefix"]


@pytest.mark.parametrize(
    "line",
    [
        "api_key: not-a-reference",
        "anthropic_api_key: ''",
        "api-key: 12345",
        "bearer_token: env://SOMETHING",
        "credentials: {user: a, password: b}",
        "voters:\n  - voter_id: a\n    api_key_ref: plain-name",
        "secret_key: [secret://a/b, literal]",
    ],
)
def test_positive_control_provider_key_field_that_is_not_a_reference_fails(
    tmp_path: Path, line: str
) -> None:
    overlay = tmp_path / "node_x" / "overlay.yaml"
    overlay.parent.mkdir()
    overlay.write_text(f"schema_version: x\n{line}\n", encoding="utf-8")
    assert scan_overlays(tmp_path), line


@pytest.mark.parametrize(
    "line",
    [
        "api_key: secret://lab/anthropic/pool-1",
        "voters:\n  - voter_id: a\n    api_key_ref: secret://lab/anthropic/pool-1",
        "signing_key_env: LOCAL_LLM_SHARED_SECRET",
        "max_context_tokens: 65536",
        "cost_per_1k_tokens: 0.002",
        "endpoint_ref: LLM_LOCAL_PRIMARY_URL",
    ],
)
def test_negative_control_references_and_non_credential_fields_pass(
    tmp_path: Path, line: str
) -> None:
    overlay = tmp_path / "node_x" / "overlay.yaml"
    overlay.parent.mkdir()
    overlay.write_text(f"schema_version: x\n{line}\n", encoding="utf-8")
    assert scan_overlays(tmp_path) == [], line


def test_an_env_name_field_is_still_read_for_the_prefix(tmp_path: Path) -> None:
    overlay = tmp_path / "node_x" / "overlay.yaml"
    overlay.parent.mkdir()
    overlay.write_text(f"signing_key_env: {_fake_key()}\n", encoding="utf-8")
    assert scan_overlays(tmp_path) == ["node_x/overlay.yaml: Anthropic key prefix"]


