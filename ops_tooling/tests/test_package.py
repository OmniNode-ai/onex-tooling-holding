"""The package imports and reports the version its distribution metadata declares."""

from importlib.metadata import version

import pytest

import ops_tooling_pkg


@pytest.mark.unit
def test_package_version_matches_distribution_metadata() -> None:
    assert ops_tooling_pkg.__version__ == version("ops-tooling-pkg")
