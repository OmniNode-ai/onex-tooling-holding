# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""Incident replay for the branch-protection auditor (OMN-20955, OMN-15547 R5).

The auditor lives in this repository under OMN-20955 (it moved here from
onex_change_control and omnibase_infra), so it keeps the replay case it earned. The
incident it is replayed against is OMN-18346:
``Branch Protection Audit`` failed 47 of its 47 scheduled runs in seven days,
every one on a fleet whose branch protection was healthy. That red came from the
orphaned-required-context check, which stays in omnibase_infra; this auditor was
the other step of the same workflow run and read the same
fleet green. The regression class is therefore ``false_red``: the case pins that
the auditor ACCEPTS the real, healthy payload the failing workflow audited.

The artifact is the live ``main`` branch-protection payload of omniclaude as
captured on 2026-09-13 by the OMN-18346 lane: ordinary PR-merge main, 56
required contexts, every one bound to the GitHub Actions App, ``CI Summary`` and
``verify / verify`` among them. It is the same bytes omnibase_infra commits
(tests/fixtures/omn18346/omniclaude-main-protection.json.captured), copied here
and pinned by the digest below. Only the payload is real. The
GraphQL review rules, the repository settings and the ruleset list the auditor
also reads are the minimal compliant stubs the sibling auditor tests use,
because the OMN-18346 lane captured none of them.

THE DISCRIMINATOR IS LOAD-BEARING. An auditor that accepted everything would
satisfy the accept case and enforce nothing, and a silent audit reads exactly
like a clean fleet in a run log. The same captured payload with ``CI Summary``
removed from it must still be refused, by name.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from test_audit_branch_protection_release_synced import (
    _RULESET_MERGE_QUEUE_DISABLED,
    _fixtures,
    _run_audit,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CAPTURE = (
    _REPO_ROOT / "tests" / "fixtures" / "omn18346" / "omniclaude-main-protection.json.captured"
)
_CAPTURE_SHA256 = "f8b844696a28038fcc1f467b57476745b789a0fd6fb4de11bb0723093b4f321c"

# On 2026-09-13 omniclaude's main was still an ordinary PR-merge target;
# OMN-16642 moved it to a release-synced main two days later. The default fleet
# lists it as release-synced, so the replay states the 2026-09-13 shape.
_ORDINARY_MAIN_ON_2026_09_13: dict[str, object] = {
    "schema_version": "branch_protection_audit_overlay.v1",
    "repos": ["omniclaude"],
    "release_synced_main_repos": [],
}


def _captured_payload() -> dict[str, object]:
    raw = _CAPTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _CAPTURE_SHA256, (
        "the captured artifact changed; a replay over edited bytes proves nothing"
    )
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


@pytest.mark.unit
def test_the_real_auditor_accepts_the_live_omniclaude_main_the_failing_audit_read(
    tmp_path: Path,
) -> None:
    result = _run_audit(
        tmp_path,
        "omniclaude",
        _fixtures("omniclaude", _captured_payload(), [_RULESET_MERGE_QUEUE_DISABLED]),
        overlay=_ORDINARY_MAIN_ON_2026_09_13,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"CI Summary" is a required status check' in result.stdout
    assert "All repos compliant." in result.stdout


@pytest.mark.unit
def test_the_same_auditor_still_refuses_that_payload_without_ci_summary(
    tmp_path: Path,
) -> None:
    """The discriminator: acceptance above is a verdict, not an auditor stuck open."""
    payload = copy.deepcopy(_captured_payload())
    required = payload["required_status_checks"]
    assert isinstance(required, dict)
    required["contexts"] = [c for c in required["contexts"] if c != "CI Summary"]
    required["checks"] = [c for c in required["checks"] if c["context"] != "CI Summary"]

    result = _run_audit(
        tmp_path,
        "omniclaude",
        _fixtures("omniclaude", payload, [_RULESET_MERGE_QUEUE_DISABLED]),
        overlay=_ORDINARY_MAIN_ON_2026_09_13,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert '"CI Summary" not found in required status checks' in result.stdout
