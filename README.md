# Operator tooling snapshot

This directory is a snapshot of source only: no git history and none of the private CI that ran
against the original code. It holds two packages.

| Directory | What it is |
| -- | -- |
| `ops_tooling/` | Operator tooling: a typed work-ledger append, the ledger publisher, worktree maintenance tools, launchd and systemd unit templates, and the nodes and handlers behind them. A Python 3.12 uv project. |
| `plugin_tooling/` | An agent plugin: skills, hooks and scripts, with the Python modules they call. |

Ledger data, operator rulings, session transcripts, environment and secrets files, operator prompt
files and the private CI configuration were left out of the snapshot. Host names, addresses, home
paths, person names and repository names were replaced by neutral placeholders, and the two Python
packages were renamed (`ops_tooling_pkg`, `plugin_tooling_pkg`).

## Running the tests

Each package runs its tests with [uv](https://docs.astral.sh/uv/). Keep the virtual environment
outside the tree so the snapshot stays clean:

```bash
cd ops_tooling
UV_PROJECT_ENVIRONMENT=/tmp/venv-ops PYTHONDONTWRITEBYTECODE=1 \
  uv run --frozen pytest -q -p no:cacheprovider
```

`plugin_tooling/` carries no `pyproject.toml`; run its tests with a throwaway environment:

```bash
cd plugin_tooling
UV_PROJECT_ENVIRONMENT=/tmp/venv-plugin PYTHONDONTWRITEBYTECODE=1 \
  uv run --no-project --with pytest --with pyyaml pytest -q -p no:cacheprovider
```

Tests that expected a removed file (a ledger, a ruling, a prompt, a secrets file) or a replaced host
name fail by design; the snapshot report lists each one.
