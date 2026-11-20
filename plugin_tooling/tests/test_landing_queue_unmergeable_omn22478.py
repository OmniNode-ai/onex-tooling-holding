"""OMN-22478: a merge-queue entry GitHub marks UNMERGEABLE is a conflicting PR, and the controller sends the conflict
worker at once instead of leaving it ``queued`` until GitHub ejects it.

omnibase_infra#5727 (2026-11-06): dev #5731 appended to the file #5727 also appended to, GitHub enqueued it at
12:56:31Z already UNMERGEABLE at position 2, the controller read it ``queued`` on every tick from 12:58Z to 13:13Z and
sent no worker, GitHub ejected it merge_conflict at 13:20:31Z, and only then did the conflict worker start. The rows
below are that entry and its record.
"""

from __future__ import annotations

import pytest

from tests.test_landing_controller import REPO, SHA, Harness, _green, actions, h, plugin, world

FIXTURES = (h, plugin, world)  # pytest finds these fixtures by the imported names

# ------------------------------------------------------------------------------ a whole tick


def test_a_tick_sends_the_conflict_worker_for_an_unmergeable_queue_entry(h: Harness) -> None:
    pr = f"{REPO}#11"
    h.world.edit(lambda w: w["prs"].update({pr: _green(SHA["c"], queued=True, queue_state="UNMERGEABLE")}))
    h.world.edit(lambda w: w["prs"].pop(f"{REPO}#10", None))
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 0, out
    [worker] = actions(out, "dispatch_worker")
    assert worker["subject"] == f"OmniNode-ai/{pr}" and worker["brief"]["brief_class"].startswith("conflict"), worker
    assert actions(out, "merge") == []


@pytest.mark.parametrize("state", ["QUEUED", "AWAITING_CHECKS", "MERGEABLE"])
def test_negative_control_a_tick_leaves_every_other_queue_entry_alone(h: Harness, state: str) -> None:
    pr = f"{REPO}#11"
    h.world.edit(lambda w: w["prs"].update({pr: _green(SHA["c"], queued=True, queue_state=state)}))
    h.world.edit(lambda w: w["prs"].pop(f"{REPO}#10", None))
    h.open_gate()
    out = h.tick()
    assert out["rc"] == 0, out
    assert actions(out, "dispatch_worker") == [] and actions(out, "merge") == []
