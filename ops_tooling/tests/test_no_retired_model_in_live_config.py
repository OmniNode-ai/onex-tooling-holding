"""No live routing, lab or collector config names the retired lab model (OMN-19432).

The weights left the Studio on 2026-10-08 and its review vote went to Codex on 2026-10-09; the
Studio's :8130 server serves Qwen3.8-27B. A config that still names the old model routes, labels
or describes a setup that no longer exists. Dated history (the work ledger and its archive) is
outside the scanned trees, and the hygiene gate's refusal list under ``vocabularies/`` is kept on
purpose: it exists to refuse the name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCANNED_TREES = ("config", "src")
SCANNED_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".py", ".md", ".plist", ".service"}
RETIRED = re.compile("gpt" + "[-_ ]?" + "oss", re.IGNORECASE)


def _live_files() -> list[Path]:
    return sorted(
        path
        for tree in SCANNED_TREES
        for path in (REPO / tree).rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix in SCANNED_SUFFIXES
    )


@pytest.mark.unit
def test_scan_covers_the_routing_overlay() -> None:
    names = {path.name for path in _live_files()}
    assert "dev.bifrost.yaml" in names, "positive control: the dev routing overlay is scanned"
    assert "sources.yaml" in names, "positive control: the collector sources are scanned"


@pytest.mark.unit
def test_no_live_config_names_the_retired_model() -> None:
    hits = [
        f"{path.relative_to(REPO)}:{number}"
        for path in _live_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if RETIRED.search(line)
    ]
    assert not hits, f"retired model named in live config: {hits}"
