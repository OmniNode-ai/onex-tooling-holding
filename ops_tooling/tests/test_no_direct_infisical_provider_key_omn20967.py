# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""No text tells a person to put a provider API key into Infisical by hand (OMN-20967).

RULING 2026-10-11T15:00:01Z lane=orchestrator-9f8a, question "How do people get their provider API
keys into the secret store?", answer "I don't want to touch infidcsl Directly." The operator does
not enter a provider key in the secret store's web page, with its CLI, or with the seeding skill.
A key goes in through the one registration command (``onex secret register-tenant-key``, or
``onex secret set`` on a customer machine), which prompts with the input hidden.

The scan reads every instruction surface of this repository (documents, lane rules, hook and
launchd READMEs, YAML, shell and Python text outside ``tests/`` and ``docs/tracking/``) one line
at a time. A line is refused when it names a direct route into the store (the seeding skill, the
seeding command, the ``infisical`` CLI, the store's web UI or ``/secret-store-path``) AND names a
provider key (an API key, a provider name or an ``LLM_*_API_KEY`` variable) AND does not say what
not to do (never, not, instead of, refuse). The line that forbids the route is the rule restated,
so it passes. There is no allowlist and no suppression marker.

Scope. The scan covers this repository. The seeding skill and the plans that still tell a person
to use it live in other repositories and carry the same rule there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

REPO = Path(__file__).resolve().parents[1]

SKIPPED_DIRS = frozenset(
    {".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules", "tests"}
)
SKIPPED_PREFIXES = ("docs/tracking/",)
SCANNED_SUFFIXES = frozenset({".md", ".txt", ".rst", ".yaml", ".yml", ".sh", ".py", ".tmpl"})

# A route a person would take to put a value into the store by hand.
DIRECT_ROUTE = re.compile(
    r"infisical-secret|seed_secrets|infisical\s+(secrets|login|run)\b|infisical\s+(web\s+)?(ui|console|dashboard)"
    r"|(web\s+ui|dashboard|console)\s+of\s+infisical|/secret-store-path\b",
    re.IGNORECASE,
)
# A provider key: a key of a model provider, never a store credential or a CI token.
PROVIDER_KEY = re.compile(
    r"provider\s+(api\s+)?keys?|api[\s_-]?keys?\b|\bANTHROPIC_|\bOPENROUTER_|\bOPENAI_|\bGEMINI_"
    r"|\bGLM_|\bLLM_\w*KEY|\bsk-[a-z]",
    re.IGNORECASE,
)
# The line says what not to do, so it restates the rule rather than breaking it.
FORBIDS = re.compile(
    r"\b(never|not|no\s+one|nobody|instead\s+of|refuse[sd]?|refusal|forbid\w*|without)\b|n't",
    re.IGNORECASE,
)


def scan_text(relative: str, text: str) -> list[str]:
    """Every line of one file that sends a person to the store by hand with a provider key."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if DIRECT_ROUTE.search(line) and PROVIDER_KEY.search(line) and not FORBIDS.search(line):
            found.append(f"{relative}:{number}: a provider key is entered in the store by hand")
    return found


def _in_nested_checkout(root: Path, path: Path) -> bool:
    """True when the file sits in another repository's checkout inside this tree.

    CI checks the registry repositories out beside the sources; their text is theirs to scan.
    """
    return any(
        (parent / ".git").exists()
        for parent in path.parents
        if parent != root and root in parent.parents
    )


def surfaces(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIPPED_DIRS.intersection(path.relative_to(root).parts[:-1]):
            continue
        if _in_nested_checkout(root, path):
            continue
        if relative.startswith(SKIPPED_PREFIXES):
            continue
        files.append(path)
    return files


def scan_tree(root: Path) -> list[str]:
    return [
        violation
        for path in surfaces(root)
        for violation in scan_text(
            path.relative_to(root).as_posix(), path.read_text(encoding="utf-8", errors="replace")
        )
    ]


def test_this_repository_tells_no_one_to_enter_a_provider_key_by_hand() -> None:
    assert len(surfaces(REPO)) >= 50, "the scan found too few instruction surfaces to mean anything"
    assert scan_tree(REPO) == []


# Negative control: each planted line is a violation the scan must refuse.
@pytest.mark.parametrize(
    "line",
    [
        "Seed the key with `/omni:infisical-secret` as ANTHROPIC_API_KEY_1.",
        "Open the Infisical web UI and paste the provider API key into /secret-store-path.",
        "Run `infisical secrets set OPENROUTER_API_KEY=...` on the host.",
        "The operator runs onex skill seed_secrets with the OpenAI API key.",
        "    - add the GLM api key with the Infisical console of the lab store",
    ],
)
def test_negative_control_a_planted_by_hand_instruction_is_refused(
    tmp_path: Path, line: str
) -> None:
    (tmp_path / "README.md").write_text(f"# Setup\n\n{line}\n", encoding="utf-8")
    assert scan_tree(tmp_path) == ["README.md:3: a provider key is entered in the store by hand"]


def test_negative_control_the_plant_is_refused_in_a_python_string_and_a_yaml_value(
    tmp_path: Path,
) -> None:
    (tmp_path / "hint.py").write_text(
        'MESSAGE = "seed the API key with /omni:infisical-secret"\n', encoding="utf-8"
    )
    (tmp_path / "notes.yaml").write_text(
        "step: put the provider key in Infisical /secret-store-path\n", encoding="utf-8"
    )
    assert scan_tree(tmp_path) == [
        "hint.py:1: a provider key is entered in the store by hand",
        "notes.yaml:1: a provider key is entered in the store by hand",
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Never seed an API key with /omni:infisical-secret; run `onex secret register-tenant-key`.",
        "Do not paste the provider key into the Infisical web UI.",
        "Run `infisical login --domain https://store.example/api` once (a store identity, no key).",
        "`onex secret register-tenant-key anthropic --tenant <id> --name claude-review-h907`",
        "The reader identity lives in /secret-store-path and holds no model provider value.",
        "Set the ANTHROPIC_API_KEY_ENV name in the overlay.",
    ],
)
def test_positive_control_the_rule_restated_and_the_sanctioned_command_pass(
    tmp_path: Path, line: str
) -> None:
    (tmp_path / "README.md").write_text(f"# Setup\n\n{line}\n", encoding="utf-8")
    assert scan_tree(tmp_path) == []


def test_the_scan_skips_tests_and_the_ledger_but_reads_everything_else(tmp_path: Path) -> None:
    plant = "seed the API key with /omni:infisical-secret\n"
    for skipped in ("tests/t.py", "docs/tracking/ROLLING_WORK_LEDGER.md", ".venv/x.md"):
        (tmp_path / skipped).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / skipped).write_text(plant, encoding="utf-8")
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text(plant, encoding="utf-8")
    assert scan_tree(tmp_path) == [
        "docs/guide.md:1: a provider key is entered in the store by hand"
    ]




def test_negative_control_a_nested_checkout_is_not_scanned_but_this_tree_is(tmp_path: Path) -> None:
    line = "Seed the key with `/omni:infisical-secret` as ANTHROPIC_API_KEY_1.\n"
    nested = tmp_path / "other_repo"
    (nested / ".git").mkdir(parents=True)
    (nested / "plan.md").write_text(line, encoding="utf-8")
    assert scan_tree(tmp_path) == []
    (tmp_path / "plan.md").write_text(line, encoding="utf-8")
    assert scan_tree(tmp_path) == ["plan.md:1: a provider key is entered in the store by hand"]
