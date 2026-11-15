"""Tests for tools/bump_version.py, the dev-repo release helper.

Every manifest is a copy in `tmp_path`. The module's two path constants are
patched to those copies, so no test touches the real manifests.
"""

import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))

import bump_version as bv

MANIFEST = '{\r\n  "name": "planwise",\r\n  "version": "1.0.5.7",\r\n  "description": "x"\r\n}\r\n'


@pytest.fixture
def manifests(tmp_path, monkeypatch):
    market = tmp_path / "marketplace.json"
    plugin = tmp_path / "plugin.json"
    for path in (market, plugin):
        path.write_bytes(MANIFEST.encode("utf-8"))
    monkeypatch.setattr(bv, "MARKETPLACE_PATH", market)
    monkeypatch.setattr(bv, "PLUGIN_PATH", plugin)
    return market, plugin


@pytest.mark.parametrize("version", ["1.1.0", "0.0.1", "10.20.30", "2.0.0-rc.1"])
def test_semver_accepted(version):
    assert bv.is_semver(version)


@pytest.mark.parametrize("version", ["1.0.5.8", "1.1", "v1.1.0", "01.1.0", "1.1.0 ", ""])
def test_non_semver_rejected(version):
    assert not bv.is_semver(version)


def test_main_refuses_four_part_version_and_writes_nothing(manifests, capsys):
    before = [p.read_bytes() for p in manifests]
    assert bv.main(["1.0.5.8"]) == 2
    assert "not a semver version" in capsys.readouterr().err
    assert [p.read_bytes() for p in manifests] == before


def test_main_bumps_both_manifests_and_keeps_crlf(manifests):
    assert bv.main(["1.1.0"]) == 0
    for path in manifests:
        data = path.read_bytes()
        assert b'"version": "1.1.0",\r\n' in data
        assert data.count(b"\r\n") == MANIFEST.count("\r\n")
        assert b"\n" not in data.replace(b"\r\n", b"")
