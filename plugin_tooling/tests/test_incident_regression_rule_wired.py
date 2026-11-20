"""OMN-17427: an incident is closed only with a regression test built from its real data (RULING 2026-10-17T09:03:06Z).

The rule lives in the two places a lane meets an incident: the friction-record skill (the FRICTION row and its TERMINAL) and the
create-ticket skill (the criterion the closer binds). This suite holds both to the rule's three parts, refuses a copy that has lost
one, and holds the worked example the skills cite to the files that exist: every fixture of the incident set is read by a test.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/omni/skills"
FRICTION = SKILLS / "friction-record/SKILL.md"
CREATE = SKILLS / "create-ticket/SKILL.md"
FIXTURES = ROOT / "tests/fixtures/incidents-2026-10-17"
RULING = "RULING 2026-10-17T09:03:06Z"
FRICTION_PARTS = (
    "### An incident closes with a regression test built from its real data",
    "captured as a fixture and scrubbed of secrets and person names",
    "fails on the broken code",
    "lives in the repository that owns the code",
    "leaves the incident open",
)
CREATE_PARTS = (
    "**An incident ticket**",
    "a regression test built from the\n  incident's recorded data (fixture path) fails on the broken code and passes on the fix",
    "never values the author\n  imagined",
)


def missing(text: str, parts: tuple[str, ...]) -> list[str]:
    return [part for part in (RULING, *parts) if part not in text]


def test_friction_record_carries_the_whole_rule() -> None:
    assert missing(FRICTION.read_text(), FRICTION_PARTS) == []


def test_create_ticket_binds_an_incident_to_its_regression_test() -> None:
    assert missing(CREATE.read_text(), CREATE_PARTS) == []


def test_a_copy_that_lost_a_part_of_the_rule_is_refused() -> None:
    """The negative control: each part, removed from the real text, is reported."""
    for part in FRICTION_PARTS:
        assert missing(FRICTION.read_text().replace(part, ""), FRICTION_PARTS) == [part]
    for part in CREATE_PARTS:
        assert missing(CREATE.read_text().replace(part, ""), CREATE_PARTS) == [part]


def test_every_incident_fixture_is_read_by_an_incident_test() -> None:
    readers = "\n".join(p.read_text() for p in sorted((ROOT / "tests").glob("test_incident_*.py")) if p.name != Path(__file__).name)
    fixtures = sorted(p.name for p in FIXTURES.iterdir())
    assert fixtures, "the incident fixture directory is empty"
    assert [name for name in fixtures if name not in readers] == []
