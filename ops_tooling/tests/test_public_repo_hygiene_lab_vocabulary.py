"""The private lab vocabulary the public-repo hygiene gate reads (OMN-19766).

The gate fails closed on a missing or empty ``lab_lane_ids`` list and on an
unknown key, but only when it runs. These checks catch a broken edit here, in
the pull request that makes it, before any public repository's gate trips on it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VOCABULARY = (
    Path(__file__).resolve().parents[1] / "vocabularies" / "public_repo_hygiene_lab_vocabulary.yaml"
)
ALLOWED_KEYS = {"schema_version", "lab_lane_ids"}
LANE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Bare words that would flood every public repository if matched as a token.
TOO_GENERIC = {"dev", "judge", "dogfood", "lab", "prod", "local", "omnibase-infra"}


def _parse() -> dict[str, object]:
    """The gate's restricted subset: top-level scalars and scalar lists."""
    data: dict[str, object] = {}
    section: list[str] | None = None
    for raw in VOCABULARY.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not raw.startswith(" "):
            key, _, value = line.partition(":")
            assert key not in data, f"duplicate key {key!r}"
            if value.strip():
                data[key] = value.strip()
                section = None
            else:
                section = []
                data[key] = section
            continue
        assert section is not None, f"indented line outside a list: {raw!r}"
        assert line.startswith('- "') and line.endswith('"'), f"not a quoted item: {raw!r}"
        section.append(line[3:-1])
    return data


@pytest.mark.unit
def test_only_known_keys() -> None:
    assert set(_parse()) <= ALLOWED_KEYS


@pytest.mark.unit
def test_lab_lane_ids_present_non_empty_and_unique() -> None:
    ids = _parse().get("lab_lane_ids")
    assert isinstance(ids, list) and ids, "an empty list disables the class"
    assert len(ids) == len(set(ids))


@pytest.mark.unit
def test_every_id_is_a_lowercase_slug_and_none_is_a_bare_common_word() -> None:
    ids = _parse()["lab_lane_ids"]
    assert isinstance(ids, list)
    for lane_id in ids:
        assert LANE_ID.match(lane_id), lane_id
        assert lane_id not in TOO_GENERIC, lane_id
