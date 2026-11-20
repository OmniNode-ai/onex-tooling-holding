# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""Our lab's Hostile Reviewer voters are a private node overlay (OMN-20923).

Operator RULING 2026-10-10T21:57:38Z: no lab or deployment configuration lives
in a shipped repository. The voter list moved here from omnibase_infra
docker/lane-overlays/hostile-review-voters.yaml. The shipped workflows fetch it
at run time and omniintelligence's node_review_voters_overlay_compute validates
it on every gate run; this test refuses a broken file before it reaches main,
so a bad edit here cannot take the gate down on three repositories at once.

The field set mirrors omniintelligence ModelReviewVoter (review_voters_overlay.v1).
This repository does not depend on omniintelligence, so the shape is restated
here and kept narrow: anything the schema would refuse, this refuses too.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit]

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "onex"
    / "overlays"
    / "node_review_voters_overlay_compute"
    / "overlay.yaml"
)

VOTER_FIELDS = frozenset(
    {
        "voter_id",
        "provider",
        "model",
        "api_key_env",
        "excluded_repositories",
        "backend_id",
        "endpoint_url",
        "overflow_endpoint_urls",
        "overflow_after_seconds",
        "model_id_source",
        "api_model_id",
        "required",
        "timeout_seconds",
        "max_retries",
        "temperature",
        "top_p",
        "review_focus",
        "enable_thinking",
        "reasoning_effort",
        "constrain_findings_schema",
        "context_window_tokens",
        "review_deadline_seconds",
    }
)
VOTER_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def _overlay() -> dict[str, Any]:
    data = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _voters() -> list[dict[str, Any]]:
    voters = _overlay()["voters"]
    assert isinstance(voters, list)
    return voters


def test_overlay_is_a_review_voters_overlay_v1() -> None:
    data = _overlay()
    assert data["schema_version"] == "review_voters_overlay.v1"
    assert set(data) <= {
        "schema_version",
        "backend_overlay",
        "provider_endpoints",
        "voters",
        "substitute_votes",
    }


def test_overlay_is_self_contained() -> None:
    """Every voter names its own endpoint; nothing resolves through a lab
    delegation overlay in a public repository. A provider anthropic voter names no
    endpoint: the overlay's provider_endpoints entry is its base URL (OMN-20910)."""
    data = _overlay()
    assert "backend_overlay" not in data
    for voter in _voters():
        assert "backend_id" not in voter, voter["voter_id"]
        if voter.get("provider") == "anthropic":
            assert "endpoint_url" not in voter, voter["voter_id"]
            assert data["provider_endpoints"]["anthropic"], voter["voter_id"]
        else:
            assert voter.get("endpoint_url"), voter["voter_id"]


def test_every_voter_has_only_schema_fields_and_a_valid_id() -> None:
    ids = [v["voter_id"] for v in _voters()]
    assert len(set(ids)) == len(ids)
    for voter in _voters():
        assert VOTER_ID.match(voter["voter_id"]), voter["voter_id"]
        assert set(voter) <= VOTER_FIELDS, set(voter) - VOTER_FIELDS
        assert isinstance(voter["required"], bool), voter["voter_id"]
        assert 0 < float(voter["timeout_seconds"]) <= 1800, voter["voter_id"]
        if voter.get("model_id_source", "served") == "served":
            assert not voter.get("api_model_id"), voter["voter_id"]


def test_two_required_voters_on_distinct_endpoints() -> None:
    """The quorum needs two distinct models; two entries on one endpoint
    serving one model count once, so the required voters must not share one."""
    required = [v for v in _voters() if v["required"] is True]
    assert len(required) >= 2
    netlocs = set()
    for voter in required:
        url = voter.get("endpoint_url") or _overlay()["provider_endpoints"][voter["provider"]]
        parsed = urllib.parse.urlsplit(url)
        assert parsed.scheme in {"http", "https"}, voter["voter_id"]
        assert parsed.hostname, voter["voter_id"]
        netlocs.add(parsed.netloc)
    assert len(netlocs) == len(required)


def test_overflow_endpoints_are_other_hosts_and_bounded_by_the_timeout() -> None:
    """OMN-20923: a voter's overflow list holds endpoints other than its own, and
    the per-endpoint give-up time cannot exceed the voter's timeout. The
    resolver in omniintelligence refuses the same shapes at run time."""
    overflowing = [v for v in _voters() if v.get("overflow_endpoint_urls")]
    for voter in overflowing:
        urls = voter["overflow_endpoint_urls"]
        assert isinstance(urls, list) and all(isinstance(u, str) for u in urls)
        assert len(set(urls)) == len(urls), voter["voter_id"]
        assert voter["endpoint_url"] not in urls, voter["voter_id"]
        for url in urls:
            parsed = urllib.parse.urlsplit(url)
            assert parsed.scheme in {"http", "https"}, voter["voter_id"]
            assert parsed.hostname, voter["voter_id"]
        after = voter.get("overflow_after_seconds")
        if after is not None:
            assert 0 < float(after) <= float(voter["timeout_seconds"]), voter["voter_id"]


def test_overflow_after_seconds_needs_an_overflow_endpoint() -> None:
    for voter in _voters():
        if "overflow_after_seconds" in voter:
            assert voter.get("overflow_endpoint_urls"), voter["voter_id"]


def test_an_overflow_endpoint_never_collapses_the_two_voters_onto_one_host() -> None:
    """The overflow of one voter must not be the endpoint of another required
    voter: that would make two votes come from one server when it overflows."""
    required = [v for v in _voters() if v["required"] is True]
    for voter in required:
        others = {o.get("endpoint_url") for o in required if o is not voter}
        assert not (set(voter.get("overflow_endpoint_urls", [])) & others), voter["voter_id"]


# omnimarket's hostile-reviewer.yml runs omniintelligence's retry_budget over
# this overlay on every gate run (--job-timeout-seconds 3600
# --setup-overhead-seconds 300) and fails the job when the budget does not fit,
# so an overlay that does not fit fails every omnimarket review. Spelled here,
# not read from that clone (OMN-18968).
_OMNIMARKET_JOB_TIMEOUT_SECONDS = 3600
_OMNIMARKET_SETUP_OVERHEAD_SECONDS = 300
_TRANSPORT_DEFAULT_MAX_RETRIES = 3


def _worst_case_seconds(voter: dict[str, Any]) -> float:
    """Mirror retry_budget.compute_sequential_worst_case for one voter:
    every attempt times out, backoff 2, 4, 8 ... s between attempts (14 s for
    three retries, as retry_budget prints it), plus one un-retried give-up per
    overflow endpoint. A voter with review_deadline_seconds (OMN-20910) is
    budgeted at that ceiling, the longest a chunked review of it may take."""
    if "review_deadline_seconds" in voter:
        return float(voter["review_deadline_seconds"])
    timeout = float(voter["timeout_seconds"])
    retries = int(voter.get("max_retries", _TRANSPORT_DEFAULT_MAX_RETRIES))
    backoff = sum(2.0 ** (i + 1) for i in range(retries))
    overflow = len(voter.get("overflow_endpoint_urls", [])) * min(
        timeout, float(voter.get("overflow_after_seconds", timeout))
    )
    return (1 + retries) * timeout + backoff + overflow


def test_the_voters_fit_the_omnimarket_retry_budget() -> None:
    total = sum(_worst_case_seconds(v) for v in _voters())
    assert total + _OMNIMARKET_SETUP_OVERHEAD_SECONDS < _OMNIMARKET_JOB_TIMEOUT_SECONDS, total


def test_every_voter_has_a_chunk_scaled_review_deadline() -> None:
    """OMN-20910: a diff in many chunks gets timeout_seconds per chunk up to
    this ceiling, never less than one call."""
    for voter in _voters():
        deadline = float(voter["review_deadline_seconds"])
        assert float(voter["timeout_seconds"]) <= deadline <= 7200, voter["voter_id"]


def test_substitute_votes_shape() -> None:
    """OMN-20947: the off-CI receipt policy mirrors omniintelligence
    ModelSubstituteVotePolicy; anything that model refuses, this refuses."""
    policy = _overlay().get("substitute_votes")
    if policy is None:
        return
    assert set(policy) <= {
        "reviewers",
        "receipts_per_vote",
        "receipt_max_age_seconds",
        "signing_key_env",
    }
    reviewers = policy["reviewers"]
    assert isinstance(reviewers, list) and reviewers
    ids = [r["reviewer_id"] for r in reviewers]
    assert len(set(ids)) == len(ids)
    voter_ids = {v["voter_id"] for v in _voters()}
    for reviewer in reviewers:
        assert set(reviewer) == {"reviewer_id", "github_logins"}
        assert VOTER_ID.match(reviewer["reviewer_id"])
        assert reviewer["reviewer_id"] not in voter_ids
        assert reviewer["github_logins"]
    per_vote = policy.get("receipts_per_vote", 1)
    assert 1 <= per_vote <= len(reviewers)
    assert 0 < policy["receipt_max_age_seconds"] <= 7 * 24 * 3600
    assert re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", policy["signing_key_env"])


# OMN-17292: every voter declares a context window that carries a long diff line.
# The run on omnibase_infra#5312 head ab2f3b71de572ffa3df7850ec4a629d21611e7ef (job
# 121057507828) returned degraded: the required voter correctness failed in 0.0 s with
# "review context cannot fit a diff line and header". It declared no context_window_tokens,
# so omniintelligence's ModelReviewVoter default 32768 applied. omniintelligence's
# adapter_ai_reviewer.py sizes chunks in UTF-8 bytes, despite the token names:
# W - min(2 * 8192, W // 2) - prompt overhead - 1024. The measured overhead of the
# correctness voter's prompts and focus is 6282 bytes, so 32768 left 9078 bytes, and the
# #5312 diff carries one 11303-byte line (a deleted PyPI JSON fixture line). The lab
# endpoint's /v1/models reports Qwen3.8-27B with max_model_len 131072 (read 2026-10-25).
_MAX_REVIEW_TOKENS = 8192
_CONTEXT_MARGIN = 1024
_DEFAULT_WINDOW_TOKENS = 32768
MEASURED_OVERHEAD_BYTES = 6282
MEASURED_LONGEST_LINE_BYTES = 11303
FILE_HEADER_ALLOWANCE_BYTES = 1024
SERVED_WINDOW_TOKENS = 131072


def chunk_budget_bytes(window: int) -> int:
    """The reviewer's chunk budget in bytes for a declared window, with the measured overhead."""
    return (
        window
        - min(2 * _MAX_REVIEW_TOKENS, window // 2)
        - MEASURED_OVERHEAD_BYTES
        - _CONTEXT_MARGIN
    )


def window_violations(document: dict[str, Any]) -> list[str]:
    """What keeps a voter's declared window from carrying the measured diff line."""
    found: list[str] = []
    required_bytes = MEASURED_LONGEST_LINE_BYTES + FILE_HEADER_ALLOWANCE_BYTES
    for voter in document["voters"]:
        name = voter["voter_id"]
        if "context_window_tokens" not in voter:
            found.append(f"{name}: missing context_window_tokens")
        window = voter.get("context_window_tokens", _DEFAULT_WINDOW_TOKENS)
        budget = chunk_budget_bytes(window)
        if budget <= required_bytes:
            found.append(f"{name}: chunk budget {budget} bytes must exceed {required_bytes} bytes")
        if window > SERVED_WINDOW_TOKENS:
            found.append(f"{name}: window {window} exceeds served window {SERVED_WINDOW_TOKENS}")
    return found


def test_every_voter_declares_a_window_that_fits_the_measured_line() -> None:
    assert window_violations(_overlay()) == []


def test_the_undeclared_default_window_is_refused() -> None:
    """Positive control: without the declaration the 32768 default cannot fit the line."""
    document = _overlay()
    for voter in document["voters"]:
        if voter["voter_id"] == "sonnet":
            voter.pop("context_window_tokens", None)
    violations = window_violations(document)
    assert "sonnet: missing context_window_tokens" in violations
    assert "sonnet: chunk budget 9078 bytes must exceed 12327 bytes" in violations


def test_a_window_above_the_served_window_is_refused() -> None:
    """Positive control: a declaration larger than the endpoint holds is refused."""
    document = _overlay()
    document["voters"][0]["context_window_tokens"] = SERVED_WINDOW_TOKENS * 2
    assert any("exceeds served window" in v for v in window_violations(document))
