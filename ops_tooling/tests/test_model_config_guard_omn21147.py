# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""OMN-21147: the model-config guard is wired here as a hook and as a job `ci` needs.

Operator ruling 2026-10-15T13:54:36Z: a model id or other deployment fact is never hard-coded in a
repository, it lives in a contract overlay. The check is omnibase_core's
``check-hardcoded-model-config-compute``; this module pins that it runs in this repository the way
the gate contract requires: a pre-commit hook, and a CI job that the required ``ci`` job needs, at
the one core commit every other core gate here uses, over a baseline that can only shrink.

The planted-sample negative control runs in the CI job itself (it needs the pinned core, fetched
over the network, which the pytest shards do not have); the tests below pin that the job carries it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CORE_REPO_URL = "https://github.com/OmniNode-ai/omnibase_core"
HOOK_ID = "check-hardcoded-model-config-compute"
JOB_ID = "model-config-guard"
BASELINE = "config/hardcoded_model_config_baseline.yaml"
GUARD_MODULE = "omnibase_core.validation.hardcoded_model_config.runtime_hardcoded_model_config"
# Family R (a retired value) can never be baselined; the guard refuses to write one.
BASELINE_FAMILIES = {"M", "E", "E-LAN", "D", "L"}


















def test_the_baseline_exists_and_holds_no_retired_value() -> None:
    entries = yaml.safe_load((ROOT / BASELINE).read_text(encoding="utf-8"))["entries"]
    assert entries, "positive control: an empty baseline would pass the next assertion vacuously"
    assert {entry["family"] for entry in entries} <= BASELINE_FAMILIES
    paths = {entry["path"] for entry in entries}
    assert not any("ROLLING_WORK_LEDGER" in path for path in paths), (
        "the append-only ledger is classed HISTORICAL by the guard, not baselined"
    )


# OMN-20910: the omnibase_core dev tag dev-20261019061232-759508560875 (omnibase_core#2053) classes
# the contract overlay tree config/onex/overlays/** as OVERLAY, which refuses retired values only.
# Before it the guard classed that tree SOURCE, so a review-voter endpoint swap in its overlay was
# refused. The hook and the CI job run the same core commit.
OVERLAY_CLASS_CORE_SHA = "759508560875f1a6e4c5c3c41ac6b2254d5ef0f7"




def test_the_baseline_holds_no_contract_overlay_entry() -> None:
    """The overlay tree is not source at the pinned core: an entry for it is stale and fails."""
    entries = yaml.safe_load((ROOT / BASELINE).read_text(encoding="utf-8"))["entries"]
    assert entries, "positive control: an empty baseline would pass vacuously"
    assert not [e for e in entries if e["path"].startswith("config/onex/overlays/")]
