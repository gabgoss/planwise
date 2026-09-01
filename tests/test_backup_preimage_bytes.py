#!/usr/bin/env python3
"""Regression fixtures for the byte-exact pre-image copy primitive.

`_copy_bytes_exact()` (`upgrade_io.py`) is the ONE copy primitive every
pre-image/backup site uses: the upgrade writer's `_write_backup_preimage()`
(every destructive adoption/removal under `--upgrade`), the `--prune-stale`
pre-image copy, and the `--prune-upgrade-leftovers` backup copy. Before this
helper existed, the first two were TEXT round-trips (`read_text` ->
`write_text`): universal-newline translation on read plus the platform's
native ending on write rewrote CRLF files LF on POSIX and LF files CRLF on
Windows, a `utf-8` read choked on any non-UTF-8 byte with a
`UnicodeDecodeError` that escaped the `OSError` guard, and the function's
own docstring promised "CURRENT bytes" one line above the code that broke it.

Every fixture here is written with `write_bytes`, never `write_text`:
`Path.write_text` translates `\\n` to the platform ending, so a text-written
fixture on Windows is already CRLF on disk and the old round-trip restored
it by accident. Only an explicit byte image can discriminate on every
platform — an LF fixture catches the Windows rewrite, a CRLF fixture catches
the POSIX one, and both are asserted.

This is the PRESERVE-bytes half of the module's CRLF split; the sibling
`test_installed_hash.py` pins the NORMALIZE-before-hash half. The two have
opposite correct answers and must never be unified.

Run with:  python -m pytest tests/test_backup_preimage_bytes.py -q
"""

import contextlib
import datetime
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import init_project as ip  # noqa: E402
import doctor_cli  # noqa: E402 -- patch-target home for the prune sweeps
from upgrade_io import _copy_bytes_exact, _write_backup_preimage  # noqa: E402

from conftest import _MigrationFixtureBase  # noqa: E402

BOM = b"\xef\xbb\xbf"

# One logical body, every physical form a consumer's checkout can carry.
# Each is a distinct byte image, so a copy that normalizes ANY of them
# fails at least one subtest on every platform.
PHYSICAL_FORMS: dict[str, bytes] = {
    "lf": b"---\ndescription: fixture rule\n---\n# Body\n\nline one\nline two\n",
    "crlf": b"---\r\ndescription: fixture rule\r\n---\r\n# Body\r\n\r\nline one\r\nline two\r\n",
    "bom_lf": BOM + b"---\ndescription: fixture rule\n---\n# Body\n\nline one\n",
    "bom_crlf": BOM + b"---\r\ndescription: fixture rule\r\n---\r\n# Body\r\n\r\nline one\r\n",
    "mixed": b"line one\r\nline two\nline three\rline four\r\n",
    "no_trailing_newline": b"line one\r\nline two",
    # 0xE9 is not valid UTF-8 on its own: the old text round-trip raised
    # UnicodeDecodeError (a ValueError) straight through the OSError guard.
    "non_utf8": b"caf\xe9\r\nline two\r\n",
}


class TestCopyBytesExactPrimitive(unittest.TestCase):
    """The primitive itself: an exact byte image, every physical form."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="preimage_bytes_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_every_physical_form_survives_byte_for_byte(self):
        for name, payload in PHYSICAL_FORMS.items():
            with self.subTest(form=name):
                src = self.tmp / f"{name}-src.md"
                dst = self.tmp / f"{name}-dst.md"
                src.write_bytes(payload)
                _copy_bytes_exact(src, dst)
                self.assertEqual(
                    dst.read_bytes(), payload,
                    f"{name}: the copy must be the exact bytes of the source",
                )

    def test_primitive_never_uses_text_mode(self):
        src = self.tmp / "src.md"
        dst = self.tmp / "dst.md"
        src.write_bytes(PHYSICAL_FORMS["bom_crlf"])
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("read_text")), \
                mock.patch.object(Path, "write_text", side_effect=AssertionError("write_text")):
            _copy_bytes_exact(src, dst)
        self.assertEqual(dst.read_bytes(), PHYSICAL_FORMS["bom_crlf"])

    def test_missing_source_raises_oserror_for_the_caller_guard(self):
        with self.assertRaises(OSError):
            _copy_bytes_exact(self.tmp / "absent.md", self.tmp / "dst.md")


class TestWriteBackupPreimageIsByteCopy(unittest.TestCase):
    """`_write_backup_preimage()` honours its own "CURRENT bytes" contract."""

    FROM, TO = "1.0.0", "1.1.0"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="preimage_backup_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project_root = self.tmp / "project"
        self.rules_dir = self.project_root / ".claude" / "rules" / "planwise"
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = ip.InitConfig(
            project_name="FixtureProject",
            project_root=self.project_root,
            plugin_root=self.tmp / "plugin",
        )

    def _backup_path_for(self, dst: Path) -> Path:
        return (
            self.project_root / self.cfg.planwise_root / "upgrade-backups"
            / f"{self.FROM}-to-{self.TO}" / dst.relative_to(self.project_root)
        )

    def test_backup_is_byte_identical_for_every_physical_form(self):
        for name, payload in PHYSICAL_FORMS.items():
            with self.subTest(form=name):
                dst = self.rules_dir / f"{name}.md"
                dst.write_bytes(payload)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    ok = _write_backup_preimage(self.cfg, self.FROM, self.TO, dst)
                self.assertTrue(ok, f"{name}: backup must succeed ({stderr.getvalue()})")
                self.assertEqual(stderr.getvalue(), "", f"{name}: no warning on success")
                backup = self._backup_path_for(dst)
                self.assertTrue(backup.exists(), f"{name}: mirrored pre-image must exist")
                self.assertEqual(
                    backup.read_bytes(), payload,
                    f"{name}: the backup must be the exact pre-write bytes "
                    "(line endings and BOM included)",
                )
                self.assertEqual(
                    dst.read_bytes(), payload,
                    f"{name}: the source must be untouched by the backup",
                )

    def test_bom_crlf_file_round_trips_unchanged(self):
        """The item's headline case, pinned on its own: BOM + CRLF, bytes in
        == bytes out, and the CR bytes are literally present in the backup."""
        payload = PHYSICAL_FORMS["bom_crlf"]
        dst = self.rules_dir / "bom-crlf.md"
        dst.write_bytes(payload)
        self.assertTrue(_write_backup_preimage(self.cfg, self.FROM, self.TO, dst))
        backup_bytes = self._backup_path_for(dst).read_bytes()
        self.assertEqual(backup_bytes, payload)
        self.assertTrue(backup_bytes.startswith(BOM), "the BOM must survive")
        self.assertEqual(
            backup_bytes.count(b"\r\n"), payload.count(b"\r\n"),
            "every CRLF must survive — none normalized to LF",
        )

    def test_no_text_mode_io_on_the_preimage_path(self):
        dst = self.rules_dir / "guarded.md"
        dst.write_bytes(PHYSICAL_FORMS["crlf"])
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("read_text")), \
                mock.patch.object(Path, "write_text", side_effect=AssertionError("write_text")):
            ok = _write_backup_preimage(self.cfg, self.FROM, self.TO, dst)
        self.assertTrue(ok)
        self.assertEqual(self._backup_path_for(dst).read_bytes(), PHYSICAL_FORMS["crlf"])

    def test_non_utf8_source_is_backed_up_not_crashed(self):
        """Regression: the text round-trip raised UnicodeDecodeError (not an
        OSError) on a non-UTF-8 pre-image, escaping the guard and aborting the
        whole run. A byte copy has no decode step to fail."""
        dst = self.rules_dir / "latin1.md"
        dst.write_bytes(PHYSICAL_FORMS["non_utf8"])
        try:
            ok = _write_backup_preimage(self.cfg, self.FROM, self.TO, dst)
        except UnicodeDecodeError as exc:  # pragma: no cover - the defect itself
            self.fail(f"backup must not decode the pre-image: {exc}")
        self.assertTrue(ok)
        self.assertEqual(self._backup_path_for(dst).read_bytes(), PHYSICAL_FORMS["non_utf8"])

    def test_missing_source_returns_false_with_warning_never_raises(self):
        dst = self.rules_dir / "absent.md"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            ok = _write_backup_preimage(self.cfg, self.FROM, self.TO, dst)
        self.assertFalse(ok)
        self.assertIn("could not back up", stderr.getvalue())


class TestPruneStalePreimageIsByteCopy(_MigrationFixtureBase):
    """`--prune-stale`'s pre-image copy uses the same byte-exact primitive.

    The sweeps are patched to hand the prune writer one synthetic REMOVABLE
    finding, so the assertion pins the COPY primitive alone — not the sweep's
    own classification of a CRLF/BOM body (that is the normalize-before-
    compare half, covered elsewhere).
    """

    def _pin_version_gate_ok(self):
        self.cfg.plugin_version = "1.0.4"
        config_dir = self.project_root / self.cfg.planwise_root
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8"
        )

    def _removable_finding(self, path: Path) -> dict:
        return {
            "path": str(path), "filename": path.name, "verdict": "REMOVABLE",
            "reason": "fixture: untouched de-scoped copy", "approx_tokens": 12,
        }

    def test_prune_backup_is_byte_identical_for_every_physical_form(self):
        self._pin_version_gate_ok()
        for name, payload in PHYSICAL_FORMS.items():
            with self.subTest(form=name):
                installed = self.rules_dir / f"{name}.md"
                installed.write_bytes(payload)
                finding = self._removable_finding(installed)
                with mock.patch.object(
                    doctor_cli, "sweep_stale_descoped_rules", return_value=[finding]
                ), mock.patch.object(
                    doctor_cli, "sweep_orphaned_agent_mirrors", return_value=[]
                ), contextlib.redirect_stdout(io.StringIO()):
                    result = ip._run_prune_stale(self.cfg)
                self.assertEqual(result, 0)
                self.assertFalse(installed.exists(), f"{name}: REMOVABLE must be unlinked")
                today = datetime.date.today().isoformat()
                backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
                # Each subtest run creates its own prune-{today}[-N]/ folder;
                # the copy lands in whichever folder this run created.
                copies = [p for p in backups_root.glob(f"prune-{today}*/{name}.md")]
                self.assertEqual(len(copies), 1, f"{name}: exactly one pre-image copy expected")
                self.assertEqual(
                    copies[0].read_bytes(), payload,
                    f"{name}: the prune pre-image must be the exact removed bytes",
                )

    def test_prune_copy_never_uses_text_mode(self):
        self._pin_version_gate_ok()
        installed = self.rules_dir / "guarded.md"
        installed.write_bytes(PHYSICAL_FORMS["bom_crlf"])
        finding = self._removable_finding(installed)
        # PRUNED.md itself is a text write by design; only the COPY must stay
        # in byte mode, so the guard fires on read_text (the copy's decode
        # step) and lets the log's write_text through. The version gate reads
        # config.yaml in text mode before the copy runs, so it is pinned to
        # "ok" rather than tripping the guard for an unrelated read.
        with mock.patch.object(
            doctor_cli, "_doctor_version_gate", return_value={"state": "ok", "report": ""}
        ), mock.patch.object(
            doctor_cli, "sweep_stale_descoped_rules", return_value=[finding]
        ), mock.patch.object(
            doctor_cli, "sweep_orphaned_agent_mirrors", return_value=[]
        ), mock.patch.object(
            Path, "read_text", side_effect=AssertionError("read_text on the prune copy path")
        ), contextlib.redirect_stdout(io.StringIO()):
            result = ip._run_prune_stale(self.cfg)
        self.assertEqual(result, 0)
        self.assertFalse(installed.exists())
        today = datetime.date.today().isoformat()
        backups_root = self.project_root / self.cfg.planwise_root / "upgrade-backups"
        copies = list(backups_root.glob(f"prune-{today}*/guarded.md"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_bytes(), PHYSICAL_FORMS["bom_crlf"])


if __name__ == "__main__":
    unittest.main()
