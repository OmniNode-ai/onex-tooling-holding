"""fseventsd RSS is an observation, never an admission bar."""

from test_lab_host_parity import Lab, lp


def test_fseventsd_rss_is_preserved_in_host_record_without_refusal():
    baseline = lp.parse_parity("PARITY-VENV none\n")
    record = lp.parse_parity("PARITY-VENV none\nPARITY-FSEVENTSD-RSS-KIB 27000000\n")
    assert record.fseventsd_rss_kib == 27000000
    assert record.record()["fseventsd_rss_kib"] == 27000000
    assert record.failures() == baseline.failures()


def test_unreadable_fseventsd_is_not_zero_and_not_a_refusal():
    record = lp.parse_parity("PARITY-VENV none\nPARITY-FSEVENTSD-RSS-KIB unreadable\n")
    assert record.fseventsd_rss_kib is None
    assert record.failures() == lp.parse_parity("PARITY-VENV none\n").failures()


def test_probe_matches_only_the_fseventsd_executable(tmp_path):
    lab = Lab(tmp_path)
    ps = lab.bin / "ps"
    ps.write_text(
        '#!/bin/sh\nprintf "1234 /System/Library/Frameworks/CoreServices.framework/fseventsd\n5678 /usr/sbin/fseventsd\n99000 /tmp/fseventsd-other\n"\n'
    )
    ps.chmod(0o755)
    record = lab.probe([])
    assert record.fseventsd_rss_kib == 6912


def test_probe_denied_ps_reports_unknown(tmp_path):
    lab = Lab(tmp_path)
    ps = lab.bin / "ps"
    ps.write_text("#!/bin/sh\nexit 1\n")
    ps.chmod(0o755)
    assert lab.probe([]).fseventsd_rss_kib is None
