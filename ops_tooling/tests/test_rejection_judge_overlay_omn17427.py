# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""The Hostile Reviewer's rejection judge is declared beside the voters (OMN-17427).

omnibase_infra's thread gate hands each `rejected:` reply to omniintelligence's
`cli_review judge-rejections`, which reads this file with the voters overlay's own
resolver and never chooses a judge that is one of the voters. A broken file here
makes every rejection fail closed on every repository the gate runs on, so this
test refuses one before it reaches main. The shape restates the review_voters_overlay.v1
anthropic voter (omniintelligence ModelReviewVoter): this repository does not depend
on omniintelligence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit]

DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "onex"
    / "overlays"
    / "node_review_voters_overlay_compute"
)
JUDGE = DIRECTORY / "rejection_judge.yaml"
VOTERS = DIRECTORY / "overlay.yaml"
ANTHROPIC_FIELDS = frozenset(
    {
        "voter_id",
        "provider",
        "model",
        "api_key_env",
        "excluded_repositories",
        "required",
        "timeout_seconds",
        "review_deadline_seconds",
        "max_retries",
        "temperature",
        "top_p",
        "review_focus",
        "context_window_tokens",
    }
)
VOTER_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
# The variable hostile-review-thread-gate.yml exports the reviewer's key under.
KEY_ENV = "REVIEW_ANTHROPIC_API_KEY"


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_the_judge_overlay_is_a_review_voters_overlay_v1() -> None:
    data = _load(JUDGE)
    assert data["schema_version"] == "review_voters_overlay.v1"
    assert set(data) <= {"schema_version", "provider_endpoints", "voters"}
    assert data["provider_endpoints"] == {"anthropic": "https://api.anthropic.com"}


def test_every_judge_is_a_claude_api_voter_on_the_reviewers_key() -> None:
    judges = _load(JUDGE)["voters"]
    assert judges
    for judge in judges:
        assert set(judge) <= ANTHROPIC_FIELDS, set(judge) - ANTHROPIC_FIELDS
        assert VOTER_ID.match(judge["voter_id"])
        assert judge["provider"] == "anthropic"
        assert judge["model"].startswith("claude-")
        assert judge["api_key_env"] == KEY_ENV
        assert judge["required"] is True
        assert 0 < judge["timeout_seconds"] <= 1800
        assert judge.get("temperature", 0) <= 1


def test_a_judge_sends_no_sampling_parameter_the_model_refuses() -> None:
    # OMN-20910: the Claude API refuses sampling parameters for this judge model.
    judges = _load(JUDGE)["voters"]
    assert judges
    for voter in judges:
        assert "temperature" not in voter, voter["voter_id"]
        assert "top_p" not in voter, voter["voter_id"]


def test_no_judge_is_a_voter() -> None:
    voters = _load(VOTERS)["voters"]
    voter_ids = {v["voter_id"] for v in voters}
    voter_endpoints = {v.get("endpoint_url") for v in voters}
    for judge in _load(JUDGE)["voters"]:
        assert judge["voter_id"] not in voter_ids
        assert judge.get("endpoint_url") not in voter_endpoints - {None}


def test_the_first_judge_is_not_the_sonnet_model() -> None:
    # The Sonnet voter is behind the h908 gateway; the judge is another model.
    assert "sonnet" not in _load(JUDGE)["voters"][0]["model"]
