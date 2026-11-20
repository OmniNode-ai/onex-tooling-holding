"""Destination-driven freeze checks in scratch git repositories (OMN-19998, OMN-21374).

The workflow and check-only hook share the gate; destination metadata explains each refusal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from _src_freeze import check, main

REPO = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = [
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".rb",
    ".pl",
]
UNLISTED = "item=unlisted destination=owning_repo task=T0b"
PUBLISHED = "item=node_pub destination=omnimarket task=T1"
NO_CODE = "item=tla/ destination=docs_repo task=T6"
PENDING = "item=launchd_units destination=omnimarket task=T4"
CONFIG = "config/migration/destinations.yaml"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "person@example.com")
    _git(tmp_path, "config", "user.name", "lane")
    _write(
        tmp_path,
        CONFIG,
        yaml.safe_dump(
            {
                "data_dirs": ["config/onex/overlays/", "contracts/", "config/migration/"],
                "code_suffixes": CODE_SUFFIXES,
                "unlisted": {"item": "unlisted", "destination": "owning_repo", "task": "T0b"},
                "no_code": [
                    {"prefix": "tla/", "destination": "docs_repo", "task": "T6"}
                ],
                "items": [
                    {
                        "id": "node_pub",
                        "prefixes": ["src/pkg/nodes/node_pub/"],
                        "destination": "omnimarket",
                        "task": "T1",
                        "status": "published",
                    },
                    {
                        "id": "launchd_units",
                        "prefixes": ["launchd/"],
                        "destination": "omnimarket",
                        "task": "T4",
                        "status": "pending",
                    },
                ],
            }
        ),
    )
    for path, content in {
        "src/pkg/nodes/node_pub/contract.yaml": "name: published\n",
        "src/pkg/nodes/node_pub/handler.py": "VALUE = 1\n",
        "src/pkg/mod.py": "VALUE = 2\n",
        "scripts/tool.py": "print(1)\n",
        "launchd/tick.py": "print('tick')\n",
        "tla/spec.tla": "---- MODULE spec ----\n",
        "contracts/existing.yaml": "name: existing\n",
        "config/onex/overlays/existing.yaml": "enabled: true\n",
    }.items():
        _write(tmp_path, path, content)
    _commit(tmp_path)
    return tmp_path


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")


@pytest.mark.unit
def test_published_edit_is_refused(repo: Path) -> None:
    _write(repo, "src/pkg/nodes/node_pub/handler.py", "VALUE = 3\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [
        f"src/pkg/nodes/node_pub/handler.py: edits a file under a published item; {PUBLISHED}"
    ]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
def test_new_launchd_py_is_refused(repo: Path) -> None:
    _write(repo, "launchd/new_tick.py", "print('new tick')\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [f"launchd/new_tick.py: adds a code file; {PENDING}"]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
def test_no_code_edit_is_refused(repo: Path) -> None:
    _write(repo, "tla/spec.tla", "---- MODULE changed ----\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [
        f"tla/spec.tla: edits a file under a no_code directory; {NO_CODE}"
    ]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
def test_published_delete_passes(repo: Path) -> None:
    _git(repo, "rm", "-q", "src/pkg/nodes/node_pub/contract.yaml")
    _git(repo, "mv", "src/pkg/nodes/node_pub/handler.py", "contracts/handler.py")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == []
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 0


@pytest.mark.unit
def test_new_non_code_file_outside_data_dirs_is_refused(repo: Path) -> None:
    _write(repo, "docs/notes.txt", "notes\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [
        f"docs/notes.txt: adds a file outside the data directories; {UNLISTED}"
    ]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
def test_refusal_message_names_item_destination_and_task(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(repo, "src/pkg/nodes/node_pub/handler.py", "VALUE = 3\n")
    _commit(repo)
    refusal = f"src/pkg/nodes/node_pub/handler.py: edits a file under a published item; {PUBLISHED}"
    assert check(repo, "HEAD^1", "HEAD") == [refusal]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1
    output = capsys.readouterr().out
    assert output == (
        "src freeze (OMN-21374): ops_tooling_pkg takes no new work; it holds data only.\n"
        f"  {refusal}\n"
    )
    assert "item=node_pub" in output
    assert "destination=omnimarket" in output
    assert "task=T1" in output


@pytest.mark.unit
@pytest.mark.parametrize("directory", ["contracts", "config/onex/overlays", "config/migration"])
def test_new_non_code_file_inside_data_dir_passes(
    repo: Path, directory: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(repo, f"{directory}/new.yaml", "name: data\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == []
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 0
    assert capsys.readouterr().out == "src freeze (OMN-21374): no refused change\n"


@pytest.mark.unit
@pytest.mark.parametrize("suffix", ["", *CODE_SUFFIXES])
def test_new_code_inside_data_dir_is_refused(repo: Path, suffix: str) -> None:
    path = f"contracts/new{suffix}"
    _write(repo, path, "#!/usr/bin/env python3\nprint(1)\n" if not suffix else "code\n")
    _commit(repo)
    # Classification reads the committed blob, even if the working copy now differs.
    _write(repo, path, "data\n")
    assert check(repo, "HEAD^1", "HEAD") == [f"{path}: adds a code file; {UNLISTED}"]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "reason", "metadata"),
    [
        ("tla/new.py", "adds a file under a no_code directory", NO_CODE),
        ("src/pkg/nodes/node_pub/new.py", "adds a file under a published item", PUBLISHED),
        ("launchd/notes.txt", "adds a file outside the data directories", PENDING),
    ],
)
def test_addition_uses_first_applicable_reason(
    repo: Path, path: str, reason: str, metadata: str
) -> None:
    _write(repo, path, "new\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [f"{path}: {reason}; {metadata}"]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "reason", "metadata"),
    [
        ("tla/tool.py", "moves a file into a no_code directory", NO_CODE),
        ("src/pkg/nodes/node_pub/tool.py", "moves a file into a published item", PUBLISHED),
        ("launchd/tool.py", None, None),
        ("contracts/tool.py", None, None),
        ("src/pkg/tool.py", None, None),
    ],
)
def test_renames_check_only_frozen_destinations(
    repo: Path, path: str, reason: str | None, metadata: str | None
) -> None:
    _git(repo, "mv", "scripts/tool.py", path)
    _commit(repo)
    expected = [f"{path}: {reason}; {metadata}"] if reason else []
    assert check(repo, "HEAD^1", "HEAD") == expected
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == bool(expected)


@pytest.mark.unit
@pytest.mark.parametrize("path", ["src/pkg/mod.py", "launchd/tick.py", "tla/spec.tla"])
def test_modifications_pass_unless_frozen(repo: Path, path: str) -> None:
    _write(repo, path, "changed\n")
    _commit(repo)
    expected = (
        [f"{path}: edits a file under a no_code directory; {NO_CODE}"]
        if path.startswith("tla/")
        else []
    )
    assert check(repo, "HEAD^1", "HEAD") == expected
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == bool(expected)


@pytest.mark.unit
def test_string_no_code_entry_uses_longest_item_prefix(repo: Path) -> None:
    config = yaml.safe_load((repo / CONFIG).read_text())
    config["no_code"] = ["launchd/"]
    config["items"].append(
        {
            "id": "tick",
            "prefixes": ["launchd/tick.py"],
            "destination": "tick_repo",
            "task": "T2",
            "status": "removed",
        }
    )
    (repo / CONFIG).write_text(yaml.safe_dump(config))
    _write(repo, "launchd/tick.py", "print('changed')\n")
    _commit(repo)
    assert check(repo, "HEAD^1", "HEAD") == [
        "launchd/tick.py: edits a file under a no_code directory; "
        "item=tick destination=tick_repo task=T2"
    ]
    assert main(["--repo", str(repo), "--base", "HEAD^1"]) == 1


@pytest.mark.unit
def test_staged_mode_reads_the_index(repo: Path) -> None:
    path = "contracts/staged"
    _write(repo, path, "#!/bin/sh\necho staged\n")
    assert check(repo, None, None) == []
    assert main(["--repo", str(repo), "--staged"]) == 0
    _git(repo, "add", path)
    _write(repo, path, "data in working copy\n")
    assert check(repo, None, None) == [f"{path}: adds a code file; {UNLISTED}"]
    assert main(["--repo", str(repo), "--staged"]) == 1


@pytest.mark.unit
def test_staged_merge_of_the_base_branch_refuses_only_what_the_branch_adds(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "lane")
    _write(repo, "src/pkg/lane_added.py", "X = 1\n")
    _commit(repo)
    _git(repo, "checkout", "-q", "main")
    _write(repo, "src/pkg/landed_on_main.py", "Y = 1\n")
    _commit(repo)
    _git(repo, "checkout", "-q", "lane")
    _git(repo, "merge", "--no-commit", "--no-ff", "main")
    assert check(repo, None, None) == []
    assert main(["--repo", str(repo), "--staged"]) == 0
    _write(repo, "src/pkg/added_in_merge.py", "Z = 1\n")
    _git(repo, "add", "src/pkg/added_in_merge.py")
    assert check(repo, None, None) == [f"src/pkg/added_in_merge.py: adds a code file; {UNLISTED}"]
    assert main(["--repo", str(repo), "--staged"]) == 1


@pytest.mark.unit
def test_a_missing_base_is_refused_not_passed(repo: Path) -> None:
    assert main(["--repo", str(repo)]) == 2


@pytest.mark.unit
@pytest.mark.parametrize("unreadable", [False, True])
def test_missing_or_unreadable_destinations_is_an_error(
    repo: Path, unreadable: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    config = repo / CONFIG
    config.unlink()
    if unreadable:
        config.mkdir()  # A directory cannot be read as YAML, even when tests run as root.
    assert main(["--repo", str(repo), "--staged"]) == 2
    assert "destinations" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize("content", ["", "items: []\n"])
def test_destinations_missing_a_key_is_an_error(
    repo: Path, content: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / CONFIG).write_text(content)
    assert main(["--repo", str(repo), "--staged"]) == 2
    assert "must declare" in capsys.readouterr().err


@pytest.mark.unit
def test_destinations_override_reads_working_tree(repo: Path) -> None:
    _write(repo, "contracts/new.py", "code\n")
    _commit(repo)
    config = repo / "contracts" / "override.yaml"
    config.write_text((repo / CONFIG).read_text().replace("- .py\n", ""))
    assert main(["--repo", str(repo), "--base", "HEAD^1", "--destinations", str(config)]) == 0
    assert check(repo, "HEAD^1", "HEAD") == [f"contracts/new.py: adds a code file; {UNLISTED}"]


