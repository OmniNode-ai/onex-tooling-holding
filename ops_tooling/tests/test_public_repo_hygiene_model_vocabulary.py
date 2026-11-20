"""The private model vocabulary the public-repo hygiene gate reads (OMN-20923).

The gate fails closed on a missing or empty ``lab_model_ids`` list and on an
unknown key, but only when it runs. These checks catch a broken edit here, in
the pull request that makes it, before any public repository's gate trips on it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VOCABULARY = (
    Path(__file__).resolve().parents[1]
    / "vocabularies"
    / "public_repo_hygiene_model_vocabulary.yaml"
)
ALLOWED_KEYS = {"schema_version", "lab_model_ids"}
MODEL_ID = re.compile(r"^[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*$")
# Bare words that would flood every public repository if matched as a token.
TOO_GENERIC = {"model", "review", "reviewer", "planner", "local", "codex", "claude"}


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
def test_lab_model_ids_present_non_empty_and_unique_ignoring_case() -> None:
    ids = _parse().get("lab_model_ids")
    assert isinstance(ids, list) and ids, "an empty list disables the rule"
    assert len(ids) == len({i.lower() for i in ids})


@pytest.mark.unit
def test_every_id_is_a_model_slug_and_none_is_a_bare_common_word() -> None:
    ids = _parse()["lab_model_ids"]
    assert isinstance(ids, list)
    for model_id in ids:
        assert MODEL_ID.match(model_id), model_id
        assert model_id.lower() not in TOO_GENERIC, model_id


@pytest.mark.unit
def test_the_ids_the_first_two_consumers_leaked_are_listed() -> None:
    listed = _parse()["lab_model_ids"]
    assert isinstance(listed, list)
    ids = {i.lower() for i in listed}
    assert {"qwen3-review", "qwen3-review-b", "local-studio-planner"} <= ids
