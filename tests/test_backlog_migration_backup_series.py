"""Regression tests for `_backup()`'s pre-image-divergence repair.

A same-pair backup directory can already hold an earlier run's pre-image of
a target (first-wins). When a later operation in the SAME version pair finds
that target's current bytes no longer match the kept backup, the routine
must not lose the newer pre-image: it writes a numbered sibling
(`{name}.{n}.bak`) alongside the kept backup, and records it in the
DISPOSITIONS row the same way the module records any other backup. A
same-pair re-run whose bytes still match the kept backup must write nothing
new. Fixtures reuse `test_backlog_migration`'s project builder, per that
module's own docstring convention."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_backlog_migration as base
from test_backlog_migration import bm, mig

EDITED = "# Third\n\nThird body, edited between the two runs.\n"


def test_diverged_target_gets_a_numbered_sibling_and_keeps_the_first(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    original = base._snapshot(backlog)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"
    base._write(backlog / "ITEM-003-INFRA-Third.md", EDITED)
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail

    backups = base._pair(cfg) / "backlog"
    first = backups / "ITEM-003-INFRA-Third.md"
    sibling = backups / "ITEM-003-INFRA-Third.md.1.bak"
    # First-wins: the original pre-image made by the failed first run is untouched.
    assert first.read_bytes() == original["ITEM-003-INFRA-Third.md"]
    # The second run's own pre-image (the edited bytes) is not lost.
    assert sibling.exists()
    assert sibling.read_bytes() == EDITED.encode("utf-8")

    rows = (base._pair(cfg) / "DISPOSITIONS.md").read_text(encoding="utf-8")
    assert "ITEM-003-INFRA-Third.md.1.bak" in rows
    assert "current bytes differed, also backed up to" in rows


def test_second_divergence_in_the_same_pair_gets_the_next_free_sibling(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"
    base._write(backlog / "ITEM-003-INFRA-Third.md", EDITED)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"

    edited_again = "# Third\n\nThird body, edited a second time before a third run.\n"
    base._write(backlog / "ITEM-003-INFRA-Third.md", edited_again)
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail

    backups = base._pair(cfg) / "backlog"
    assert (backups / "ITEM-003-INFRA-Third.md.1.bak").read_bytes() == EDITED.encode("utf-8")
    assert (backups / "ITEM-003-INFRA-Third.md.2.bak").read_bytes() == edited_again.encode("utf-8")


def test_same_pair_rerun_with_identical_bytes_writes_no_sibling(tmp_path, monkeypatch):
    cfg, _backlog = base._project(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"

    # No edit between the two runs: the target's current bytes still match
    # what the failed first run already backed up and then restored.
    report = base._migrate(cfg)
    assert report.state == "migrated", report.detail

    backups = base._pair(cfg) / "backlog"
    assert not (backups / "ITEM-003-INFRA-Third.md.1.bak").exists()
    assert report.diverged == {}


def test_repeat_divergence_with_the_same_bytes_reuses_the_existing_sibling(tmp_path, monkeypatch):
    cfg, backlog = base._project(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
        assert base._migrate(cfg).state == "write_failed"
    base._write(backlog / "ITEM-003-INFRA-Third.md", EDITED)
    # Two failed runs over the same edited bytes: the first writes `.1.bak`,
    # the second finds those bytes already backed up and adds no `.2.bak`.
    for _ in range(2):
        with monkeypatch.context() as m:
            m.setattr(mig, "execute", lambda *a: print("FAIL: simulated") or 1)
            report = base._migrate(cfg)
        assert report.state == "write_failed"

    backups = base._pair(cfg) / "backlog"
    sibling = backups / "ITEM-003-INFRA-Third.md.1.bak"
    assert sibling.read_bytes() == EDITED.encode("utf-8")
    assert not (backups / "ITEM-003-INFRA-Third.md.2.bak").exists()
    assert report.diverged == {str(backups / "ITEM-003-INFRA-Third.md"): str(sibling)}


def test_next_free_sibling_skips_an_existing_bak_file(tmp_path):
    dst = tmp_path / "Foo.md"
    dst.write_bytes(b"original")
    (tmp_path / "Foo.md.1.bak").write_bytes(b"taken")
    assert bm._next_free_sibling(dst) == tmp_path / "Foo.md.2.bak"
