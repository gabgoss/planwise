#!/usr/bin/env python3
"""Unit tests for the file measurement CLI (measure_files.py).

measure_file()/measure_files() report bytes, KiB, lines, and bytes-estimated
tokens per file and classify each against the three Read-tool gates in
priority order (tokens, then bytes, then lines) at OK|WARN|OVER, with the
WARN thresholds as the binding split targets for generated artifacts. The
CLI exits 1 when any named file is missing, and --json writes a temp-file
payload announced as `JSON: {path}`.

Run with:  python -m pytest tests/test_measure_files.py
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import measure_files as mf  # noqa: E402


class TestMeasureFiles(unittest.TestCase):
    """measure_file()/measure_files() gating + CLI surface."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_measure_files_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_lines(self, name: str, n_lines: int, line: str = "x" * 60) -> str:
        path = self.tmp / name
        # newline="\n" keeps the byte math platform-deterministic (no CRLF).
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(line for _ in range(n_lines)) + "\n")
        return str(path)

    def _write_bytes(self, name: str, n_bytes: int) -> str:
        path = self.tmp / name
        path.write_bytes(b"a" * n_bytes)
        return str(path)

    # -- known-clean input: every gate silent -------------------------------
    def test_small_file_is_ok(self):
        path = self._write_lines("small.md", 100)  # ~6.1 KB
        result = mf.measure_file(path)
        self.assertEqual(result["level"], "OK")
        self.assertEqual(result["gates"], [])
        self.assertEqual(result["lines"], 100)
        self.assertEqual(result["bytes"], 100 * 61)
        self.assertEqual(result["kib"], round(100 * 61 / 1024, 1))

    # -- known-bad inputs: each gate must discriminate ----------------------
    def test_token_warn_band(self):
        # ~60 KB → ~23.1K tokens at the default 2.6 ratio: between the 22K
        # warn and the 25K cap; under the byte warn and the line window.
        path = self._write_lines("warmish.md", 984)
        result = mf.measure_file(path)
        self.assertEqual(result["level"], "WARN")
        self.assertTrue(any(g.startswith("token warn") for g in result["gates"]))

    def test_token_cap_over(self):
        # ~70 KB → ~26.9K tokens at 2.6: over the page cap, under the byte
        # warn, under the line window — the PRIMARY gate binds first.
        path = self._write_lines("over_tokens.md", 1148)
        result = mf.measure_file(path)
        self.assertEqual(result["level"], "OVER")
        self.assertTrue(any(g.startswith("token cap") for g in result["gates"]))

    def test_byte_cap_over(self):
        path = self._write_bytes("big.bin", 300 * 1024)  # over 262,144
        result = mf.measure_file(path)
        self.assertEqual(result["level"], "OVER")
        self.assertTrue(any(g.startswith("byte cap") for g in result["gates"]))

    def test_line_gate_over_on_many_short_lines(self):
        # 2,500 × 17 B lines ≈ 42.5 KB ≈ 16.3K tokens — OK on tokens and
        # bytes, OVER on the defensive 2,000-line window alone.
        path = self._write_lines("many_short.md", 2500, line="x" * 16)
        result = mf.measure_file(path)
        self.assertEqual(result["level"], "OVER")
        self.assertEqual(result["gates"], ["line cap (>= 2,000)"])

    # -- model/content ratio selection --------------------------------------
    def test_model_ratio_changes_estimate(self):
        path = self._write_lines("probe.md", 500)
        default_tokens = mf.measure_file(path)["tokens"]
        sonnet_tokens = mf.measure_file(path, model="sonnet")["tokens"]
        opus_prose_tokens = mf.measure_file(path, model="opus", content="prose")["tokens"]
        # Sonnet-family tokenizes lighter → fewer estimated tokens than the
        # conservative default; a looser content class lowers it too.
        self.assertLess(sonnet_tokens, default_tokens)
        self.assertLess(opus_prose_tokens, default_tokens)

    # -- multi-file + errors -------------------------------------------------
    def test_multi_file_summary_and_missing_file(self):
        ok = self._write_lines("a.md", 10)
        missing = str(self.tmp / "does-not-exist.md")
        result = mf.measure_files([ok, missing])
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["ok"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["path"], missing)

    # -- CLI surface ---------------------------------------------------------
    def test_cli_exit_codes_and_json_payload(self):
        ok = self._write_lines("a.md", 10)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mf.main([ok, "--json"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        json_line = [ln for ln in out.splitlines() if ln.startswith("JSON: ")]
        self.assertEqual(len(json_line), 1, "--json must announce the payload path")
        payload_path = json_line[0][len("JSON: "):]
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["files"][0]["level"], "OK")
        self.assertEqual(payload["summary"]["total"], 1)
        shutil.rmtree(Path(payload_path).parent, ignore_errors=True)

        # A missing file exits 1 (stderr carries the error).
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = mf.main([str(self.tmp / "nope.md")])
        self.assertEqual(code, 1)
        self.assertIn("ERROR:", err.getvalue())

    def test_cli_md_table_output(self):
        ok = self._write_lines("a.md", 10)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mf.main([ok, "--md"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("| File | KiB | Lines | ~Tokens | Level |", out)
        self.assertIn("| OK |", out)


if __name__ == "__main__":
    unittest.main()
