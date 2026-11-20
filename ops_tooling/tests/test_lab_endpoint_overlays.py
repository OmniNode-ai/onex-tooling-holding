"""The lab endpoints that left omniintelligence and omnimemory (OMN-20936) are held here, unchanged.

The shipped repositories keep no default for these endpoints; the node overlays carry the values
they carried before, at omniintelligence 8782c050 and omnimemory 9a072e26.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import cast

import pytest
import yaml
from jsonschema import Draft202012Validator

OVERLAYS = Path(__file__).resolve().parents[1] / "config" / "onex" / "overlays"

REVIEW_PAIRING_DEFAULT_URLS = {
    "qwen3-review": "http://192.0.2.127:8000",
}
NAVIGATION_HISTORY_EMBEDDING_URL = "http://192.0.2.126:8100"


def _load(node: str) -> dict[str, object]:
    raw = yaml.safe_load((OVERLAYS / node / "overlay.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def test_review_pairing_overlay_holds_the_previous_default_urls() -> None:
    raw = _load("review_pairing")
    assert set(raw) == {"default_urls"}
    assert raw["default_urls"] == REVIEW_PAIRING_DEFAULT_URLS


def test_navigation_history_reducer_overlay_holds_the_previous_embedding_url() -> None:
    raw = _load("node_navigation_history_reducer")
    assert raw == {"embedding_url": NAVIGATION_HISTORY_EMBEDDING_URL}


# OMN-22781: the media capability overlay. The path table is the one omnimarket's
# node_media_capability_resolve_compute (OMN-22774) serves each capability at.
MEDIA_NODE = "node_media_capability_resolve_compute"
MEDIA_PATHS = {
    "tts": "/v1/audio/speech",
    "stt": "/v1/audio/transcriptions",
    "embed": "/v1/embeddings",
    "video": "/v1/videos",
}
MEDIA_UNITS = {
    "embed": "onex-media-embed.service",
    "tts": "onex-media-tts.service",
    "stt": "onex-media-stt.service",
    "video": "onex-media-video.service",
}
UNITS_DIR = OVERLAYS / "node_host_installer_net_units"


def _media_rows() -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _load(MEDIA_NODE)["backends"])


def _unit_port(capability: str) -> int:
    text = (UNITS_DIR / MEDIA_UNITS[capability]).read_text(encoding="utf-8")
    found = re.search(r"--port (\d+)", text)
    assert found, MEDIA_UNITS[capability]
    return int(found.group(1))


def _media_refusal(rows: list[dict[str, object]]) -> str | None:
    """The first typed reason the node would refuse one of the four capabilities, or None."""
    for capability, path in MEDIA_PATHS.items():
        named = [row for row in rows if row["capability"] == capability]
        if not named:
            return "no-backend-serving-the-capability"
        if any(not str(row["endpoint_url"]).endswith(path) for row in named):
            return "endpoint-shape-disagrees-with-capability"
        if sum(1 for row in named if row["serving"]) > 1:
            return "two-serving-backends-for-one-capability"
    return None


def _port_disagreements(rows: list[dict[str, object]]) -> list[str]:
    return [
        str(row["backend_id"])
        for row in rows
        if int(str(row["endpoint_url"]).split(":")[2].split("/")[0])
        != _unit_port(str(row["capability"]))
    ]


def test_media_overlay_matches_its_schema() -> None:
    schema = json.loads((OVERLAYS / MEDIA_NODE / "overlay.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(_load(MEDIA_NODE))


@pytest.mark.parametrize("capability", sorted(MEDIA_PATHS))
def test_media_golden_each_row_serves_its_capability_at_its_unit_port(capability: str) -> None:
    rows = [row for row in _media_rows() if row["capability"] == capability]
    assert len(rows) == 1
    assert str(rows[0]["endpoint_url"]).endswith(MEDIA_PATHS[capability])
    assert rows[0]["serving"] is True
    assert _port_disagreements(rows) == []
    assert _media_refusal(_media_rows()) is None
    assert {row["capability"] for row in _media_rows()} == set(MEDIA_PATHS)


def _break(mutate: str) -> list[dict[str, object]]:
    rows = copy.deepcopy(_media_rows())
    if mutate == "shape":
        rows[0]["endpoint_url"] = str(rows[0]["endpoint_url"]).replace(
            "/v1/embeddings", "/v1/chat/completions"
        )
    elif mutate == "duplicate":
        rows.append({**rows[0], "backend_id": "lab-media-embed-second"})
    elif mutate == "missing":
        rows = [row for row in rows if row["capability"] != "video"]
    return rows


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        ("shape", "endpoint-shape-disagrees-with-capability"),
        ("duplicate", "two-serving-backends-for-one-capability"),
        ("missing", "no-backend-serving-the-capability"),
    ],
)
def test_media_refused_each_break_is_a_typed_reason(mutate: str, reason: str) -> None:
    assert _media_refusal(_break(mutate)) == reason


def test_media_port_mismatch_red() -> None:
    assert _port_disagreements(_media_rows()) == []
    rows = copy.deepcopy(_media_rows())
    rows[0]["endpoint_url"] = str(rows[0]["endpoint_url"]).replace(":8100/", ":8002/")
    assert _port_disagreements(rows) == ["lab-media-embed"]
