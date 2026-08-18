#!/usr/bin/env python3
"""Regression fixtures for the shared normalized-text hash pre-image.

`_installed_hash()` (`upgrade_io.py`) is the ONE pre-image every hash
consumer in the `--upgrade` flow hashes against: the `--hash-installed`
subcommand on `init_project.py`'s parser, and `_load_verdict_override()`'s
recompute of a cached `verdicts.json` entry. Before this helper existed, the
handler's documented recipe hashed raw bytes while the cache writer hashed a
text-re-encoded pre-image, so any CRLF-ending installed file was a
guaranteed cache miss on every run.

This module independently reproduces that historical mismatch as a pinned
regression (`TestRawByteVsHelperDiscriminatingPair`), proves the helper's
normalization invariant holds across all four ending/BOM physical forms in
both directions (`TestNormalizedIdentityBothDirections`), proves the CLI
subcommand cannot drift from the helper (`TestHashInstalledSubcommandParity`),
and exercises the diagnostic-hint path through its PRODUCTION 4-argument
call shape -- both live call sites (`artifact_upgrade.py:255`,
`rule_descope_migration.py:322`) now thread the installed path, so the hint
is live, not dormant (`TestVerdictOverrideDiagnosticHint`).

Every digest asserted on here is computed IN-TEST, never hardcoded --
pinning a historical digest value would pin fixture bytes, not the contract.

This file never edits `upgrade_io.py`; a real discrepancy from the
contract is a HALT-and-surface, not a patch.

Run with:  python -m pytest tests/test_installed_hash.py -q
"""

import hashlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from upgrade_io import _installed_hash, _load_verdict_override  # noqa: E402

INIT_PROJECT = (
    Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts" / "init_project.py"
)

BOM = b"\xef\xbb\xbf"

# One logical file, four physical forms. Kept ASCII-only and short so the
# byte math (BOM presence, \r\n vs \n) is easy to verify by inspection.
LOGICAL_CONTENT = "line one\nline two\nline three\n"


def _crlf_bytes(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def _lf_bytes(text: str) -> bytes:
    return text.encode("utf-8")


class _FourFixtureBase(unittest.TestCase):
    """Writes the four content-equivalent physical forms as real files.

    Each fixture carries the SAME logical content (`LOGICAL_CONTENT`) in a
    different physical encoding: BOM present/absent crossed with CRLF/LF
    line endings. Written via `write_bytes()` (no text-mode newline
    translation) so the on-disk bytes are exactly what each test expects.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="installed_hash_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.fixtures = {
            "crlf_bom": self._write("crlf_bom.txt", BOM + _crlf_bytes(LOGICAL_CONTENT)),
            "crlf_nobom": self._write("crlf_nobom.txt", _crlf_bytes(LOGICAL_CONTENT)),
            "lf_bom": self._write("lf_bom.txt", BOM + _lf_bytes(LOGICAL_CONTENT)),
            "lf_nobom": self._write("lf_nobom.txt", _lf_bytes(LOGICAL_CONTENT)),
        }

    def _write(self, name: str, raw_bytes: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(raw_bytes)
        return path


class TestNormalizedIdentityBothDirections(_FourFixtureBase):
    """The four physical forms are ONE logical file -- the helper's digest
    must be identical no matter which ending/BOM combination is treated as
    "shipped" and which as "installed". Both comparison directions
    (CRLF-shipped-vs-LF-installed, and the reverse) collapse to the same
    assertion: the helper hashes the SAME normalized pre-image regardless
    of which fixture it is handed, so there is no direction-dependent
    behavior to pin separately -- these tests name both directions
    explicitly rather than relying on that symmetry argument alone.
    """

    def test_helper_digest_identical_across_all_four_physical_forms(self):
        digests = {name: _installed_hash(path) for name, path in self.fixtures.items()}
        unique = set(digests.values())
        self.assertEqual(
            len(unique), 1,
            f"expected one digest shared by all four physical forms, got {digests}",
        )

    def test_direction_crlf_shipped_vs_lf_installed(self):
        # "shipped" / "installed" are just role labels on two of the four
        # fixtures here -- the helper has no notion of which is which.
        shipped_digest = _installed_hash(self.fixtures["crlf_nobom"])
        installed_digest = _installed_hash(self.fixtures["lf_nobom"])
        self.assertEqual(shipped_digest, installed_digest)

    def test_direction_lf_shipped_vs_crlf_installed(self):
        shipped_digest = _installed_hash(self.fixtures["lf_bom"])
        installed_digest = _installed_hash(self.fixtures["crlf_bom"])
        self.assertEqual(shipped_digest, installed_digest)

    def test_str_source_lands_on_the_same_digest_as_path_source(self):
        # _installed_hash() accepts EITHER a Path (read here) or an
        # already-decoded str (a caller that already read the file itself,
        # e.g. via its own read_text(encoding="utf-8-sig")) -- both must
        # land on the same digest for the same logical content.
        path_digest = _installed_hash(self.fixtures["crlf_bom"])
        str_digest = _installed_hash(self.fixtures["crlf_bom"].read_text(encoding="utf-8-sig"))
        self.assertEqual(path_digest, str_digest)


class TestRawByteVsHelperDiscriminatingPair(_FourFixtureBase):
    """Reproduces the historical failure: hashing a CRLF file's raw bytes
    (the OLD handler-documented one-liner) and hashing it through the
    helper's normalized-text pre-image disagree. This guaranteed a
    verdicts.json cache miss on every CRLF-ending installed file before the
    shared helper existed -- pinned here as a regression, not re-derived
    from the handler prose.
    """

    def test_raw_byte_digest_differs_from_helper_on_crlf_no_bom(self):
        path = self.fixtures["crlf_nobom"]
        raw_byte_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        helper_digest = _installed_hash(path)
        self.assertNotEqual(raw_byte_digest, helper_digest)

    def test_raw_byte_digest_differs_from_helper_on_crlf_with_bom(self):
        path = self.fixtures["crlf_bom"]
        raw_byte_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        helper_digest = _installed_hash(path)
        self.assertNotEqual(raw_byte_digest, helper_digest)

    def test_raw_byte_digest_matches_helper_on_lf_no_bom(self):
        # Contrast case: an LF, no-BOM file needs no normalization at all,
        # so its raw-byte pre-image and the helper's pre-image coincide --
        # proving the mismatches above come from CRLF/BOM specifically, not
        # from hashing itself.
        path = self.fixtures["lf_nobom"]
        raw_byte_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        helper_digest = _installed_hash(path)
        self.assertEqual(raw_byte_digest, helper_digest)


class TestHashInstalledSubcommandParity(_FourFixtureBase):
    """`--hash-installed <path>` on init_project.py's flat parser must print
    EXACTLY the helper's digest -- it is a thin exit-0 wrapper delegating to
    `_installed_hash()`, never an independent recipe of its own.
    """

    def _run_hash_installed(self, path: Path) -> str:
        result = subprocess.run(
            [sys.executable, str(INIT_PROJECT), "--hash-installed", str(path)],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def test_subcommand_output_equals_helper_digest_for_each_physical_form(self):
        for name, path in self.fixtures.items():
            with self.subTest(fixture=name):
                self.assertEqual(self._run_hash_installed(path), _installed_hash(path))


class TestVerdictOverrideDiagnosticHint(_FourFixtureBase):
    """`_load_verdict_override()`'s recompute against a verdicts.json cache
    entry. Called with the PRODUCTION 4-argument call shape (installed_path
    passed, matching both live call sites in artifact_upgrade.py:255 and
    rule_descope_migration.py:322), a stored digest that matches the
    raw-byte pre-image is rejected WITH the actionable hint naming the old
    recipe; the same rejection WITHOUT installed_path (the degraded call
    shape, covered as the contrast case) falls back to the generic note.
    """

    FILENAME = "some-rule.md"

    def _verdict_entry(self, sha256_hex: str) -> dict:
        return {"classification": "SUBSET", "confidence": "exact", "installed_sha256": sha256_hex}

    def test_helper_written_digest_is_accepted(self):
        path = self.fixtures["crlf_bom"]
        installed_raw = path.read_text(encoding="utf-8-sig")
        entry = self._verdict_entry(_installed_hash(path))
        verdicts = {self.FILENAME: entry}

        result = _load_verdict_override(verdicts, self.FILENAME, installed_raw, path)

        self.assertIsNotNone(result)
        self.assertEqual(result.classification, "SUBSET")

    def test_raw_byte_written_digest_is_rejected_with_the_old_recipe_hint(self):
        path = self.fixtures["crlf_bom"]
        installed_raw = path.read_text(encoding="utf-8-sig")
        raw_byte_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # Sanity: this must actually be the discriminating (mismatching)
        # digest, or the rest of this test would pass for the wrong reason.
        self.assertNotEqual(raw_byte_digest, _installed_hash(path))
        entry = self._verdict_entry(raw_byte_digest)
        verdicts = {self.FILENAME: entry}

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            # Production shape: installed_path IS passed.
            result = _load_verdict_override(verdicts, self.FILENAME, installed_raw, path)

        self.assertIsNone(result)
        message = stderr.getvalue()
        self.assertIn("stale installed_sha256", message)
        self.assertIn("OLD raw-byte hash recipe", message)
        self.assertIn("--hash-installed", message)

    def test_raw_byte_written_digest_without_installed_path_degrades_to_the_generic_note(self):
        # Contrast case: a caller holding only pre-read text (no path
        # available) omits the 4th argument -- this is the DEGRADED branch,
        # not the production shape. The hint clause must be ABSENT.
        path = self.fixtures["crlf_bom"]
        installed_raw = path.read_text(encoding="utf-8-sig")
        raw_byte_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entry = self._verdict_entry(raw_byte_digest)
        verdicts = {self.FILENAME: entry}

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = _load_verdict_override(verdicts, self.FILENAME, installed_raw)  # no installed_path

        self.assertIsNone(result)
        message = stderr.getvalue()
        self.assertIn("stale installed_sha256", message)
        self.assertNotIn("OLD raw-byte hash recipe", message)


if __name__ == "__main__":
    unittest.main()
