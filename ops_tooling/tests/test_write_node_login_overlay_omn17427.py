"""The write node's comment login is a private node overlay (OMN-17427).

pr-handoff counts a bot PR's lab comment only from the PR author or from a login listed here; the
login is a person's account name, so it is kept in this repository and in no public one. The reader
(plugin-tooling-pkg scripts/write_logins.py) skips an overlay whose `comment_author_logins` is not
a list, so this refuses a malformed edit before it reaches main.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "onex"
    / "overlays"
    / "node_github_repo_write_effect"
    / "overlay.yaml"
)


def test_overlay_carries_only_a_list_of_logins() -> None:
    loaded = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    # `event_bus` names the lane a client reaches this node on (OMN-22355); it carries no login.
    assert set(loaded) == {"comment_author_logins", "event_bus"}
    assert loaded["event_bus"] == {"type": "kafka", "lane": "dev"}
    logins = loaded["comment_author_logins"]
    assert isinstance(logins, list) and logins
    assert all(isinstance(login, str) and login.strip() for login in logins)


def test_logins_are_bare_account_names() -> None:
    # The reader strips "app/" and "[bot]" and lower-cases; a login written with either never
    # matches the way an author reads it, so keep them out of the file.
    logins = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))["comment_author_logins"]
    for login in logins:
        assert login == login.strip().lower()
        assert not login.startswith("app/") and not login.endswith("[bot]")
    assert len(logins) == len(set(logins))
