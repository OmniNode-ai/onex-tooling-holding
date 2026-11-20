# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-20931: the lab developer-onboarding facts live here, not in a shipped repository.

The table moved byte-identical from the public infrastructure repository's
``deploy/lab/developer-onboarding.yaml``; its shape check moved with it. The
file stays flat, one ``key: value`` per line, because a shell script parses it
with sed before Python exists on a developer machine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FACTS = Path(__file__).resolve().parents[1] / "config" / "lab" / "developer-onboarding.yaml"
# The lane the developer principal grants are declared for (deploy/lab/
# developer-principal-grants.yaml in the infrastructure repository).
GRANTS_LANE = "dev"


def _keys(text: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z_]+):[ \t]*(\S.*)", line)
        assert match, f"not a flat key: value line: {line!r}"
        keys[match.group(1)] = match.group(2)
    return keys


def test_onboarding_facts_are_flat_and_complete() -> None:
    keys = _keys(FACTS.read_text(encoding="utf-8"))
    for required in (
        "schema",
        "tailnet_suffix",
        "lane",
        "principal_issuer_url",
        "lab_model_url",
        "lab_model_name",
    ):
        assert required in keys, required
    assert keys["schema"] == "developer-onboarding.v1"
    assert keys["lane"] == GRANTS_LANE
    assert keys["principal_issuer_url"].startswith("https://")
    assert keys["lab_model_url"].endswith("/v1/chat/completions")


def test_a_nested_line_is_refused() -> None:
    """Positive control: the flat-line check can fail."""
    with pytest.raises(AssertionError, match="not a flat key"):
        _keys("schema: developer-onboarding.v1\nlab:\n  url: x\n")
