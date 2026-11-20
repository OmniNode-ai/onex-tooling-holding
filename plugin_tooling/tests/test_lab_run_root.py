"""The host table alone chooses the lab disk and report retention period."""

import json
import subprocess

import pytest
from wire_script import unwired
from test_lab_host_parity import lp, rl


def test_data_disk_is_read_from_host_table(tmp_path):
    table = tmp_path / "hosts.yaml"
    table.write_text(
        "hosts:\n  - name: lab\n    target: lab.invalid\n    lab_work_root: /data/omni/lab-run\n    report_retention_days: 3\n"
    )
    host = next(
        h for h in lp.load_pool({"ONEX_LAB_RUN_HOSTS": str(table)}) if h.name == "lab"
    )
    assert host.lab_work_root == "/data/omni/lab-run"
    assert host.report_retention_days == 3


def test_absent_disk_keeps_existing_root():
    host = lp.load_pool(
        {"LANDING_POOL_HOSTS": json.dumps([dict(name="lab", target="lab.invalid")])}
    )[0]
    assert host.lab_work_root is None
    assert rl.lab_work_script(rl.scratch_script("run-1"), None) == rl.scratch_script(
        "run-1"
    )


@pytest.mark.parametrize(
    "value",
    ["/data/../lab-run", "/data/$(oops)/lab-run", "relative/lab-run", "/data/wrong"],
)
def test_bad_disk_declaration_refuses_before_remote_execution(value):
    with pytest.raises(ValueError):
        lp.lab_work_root(value)


def test_all_host_transports_render_data_disk(tmp_path):
    root = tmp_path / "data/lab-run"
    home = tmp_path / "home"
    home.mkdir()
    host = lp.Host("lab", None, frozenset(), None, False, lab_work_root=str(root))
    scripts = []

    def fake(argv, **kw):
        scripts.append(unwired(argv[-1]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    rl._ssh(host, "lane", rl.scratch_script("run-1"), run=fake)
    rl.put_snapshot(host, "lane", "run-1", b"bytes", run=fake)
    assert len(scripts) == 2
    assert all(str(root) in s and "$HOME/lab-run" not in s for s in scripts)
    done = subprocess.run(
        ["/bin/sh", "-c", scripts[0]],
        env={"HOME": str(home), "PATH": "/bin:/usr/bin"},
        capture_output=True,
    )
    assert done.returncode == 0
    assert (root / "runs/run-1").is_dir()
    assert (root / "runs/run-1.ctx").is_dir()
    assert not (home / "lab-run").exists()


def test_engine_and_context_follow_the_same_declared_disk(tmp_path, monkeypatch):
    from test_remote_lane import POOL, SHA, FakeRun, fake_read, ns, stream_ok, RESULT

    monkeypatch.setenv(
        "LANDING_POOL_HOSTS",
        json.dumps([{**row, "lab_work_root": "/data/omni/lab-run"} for row in POOL]),
    )
    monkeypatch.setenv("LANDING_PLACEMENT_DIR", str(tmp_path / "placement"))
    monkeypatch.setenv("ONEX_REMOTE_LANE_DIR", str(tmp_path / "lanes"))
    monkeypatch.setenv("LANDING_STATE_DIR", str(tmp_path / "landing"))
    run, stream = FakeRun(), stream_ok([RESULT])
    code = rl.execute(
        ns(tmp_path, repo="plugin-tooling-pkg", sha=SHA),
        echo=lambda _: None,
        run=run,
        read=fake_read({"mac": 0.0, "h907": 1.0, "h908": 9.0, "h904": 0.0}),
        stream=stream,
    )
    assert code == 0
    engine = unwired(stream.calls[0][-1])
    assert 'LR="/data/omni/lab-run"' in engine
    assert "$HOME/lab-run" not in engine
    receipt = json.loads(
        (tmp_path / "lanes/rl-test/rlane-rl-test-abc123.json").read_text()
    )
    assert receipt["retention"]["rc"] == 0
