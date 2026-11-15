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
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import measure_files as mf
from read_limits import _read_level, fired_read_gates, read_routes_advice


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
        haiku_tokens = mf.measure_file(path, model="haiku")["tokens"]
        sonnet_tokens = mf.measure_file(path, model="sonnet")["tokens"]
        opus_prose_tokens = mf.measure_file(path, model="opus", content="prose")["tokens"]
        # Haiku 4.5 is the one family that tokenizes lighter → fewer estimated
        # tokens than the conservative default; a looser content class lowers
        # it too. Sonnet 5 shares the Claude 5 tokenizer, so it sits exactly AT
        # the default — asserting it lower is what the 2026-09-07 re-measurement
        # falsified.
        self.assertLess(haiku_tokens, default_tokens)
        self.assertLess(opus_prose_tokens, default_tokens)
        self.assertEqual(sonnet_tokens, default_tokens)

    def test_notebook_and_json_are_auto_detected_and_overridable(self):
        # Same bytes under three names. The notebook and json classes are
        # denser than the text fallback, so with NO flags the estimate must
        # rise with the extension; an explicit --content must override it.
        payload = 60_000
        txt = self._write_bytes("same.txt", payload)
        nb = self._write_bytes("same.ipynb", payload)
        js = self._write_bytes("same.json", payload)
        text = mf.measure_file(txt)
        notebook = mf.measure_file(nb)
        json_file = mf.measure_file(js)
        self.assertIsNone(text["content"])
        self.assertEqual(notebook["content"], "notebook")
        self.assertEqual(json_file["content"], "json")
        self.assertLess(notebook["ratio"], text["ratio"])
        self.assertLess(json_file["ratio"], notebook["ratio"])
        self.assertGreater(notebook["tokens"], text["tokens"])
        self.assertGreater(json_file["tokens"], notebook["tokens"])
        # 60 KB: WARN as text (2.6 → ~23.1K) but OVER as a notebook (2.3 → ~26.1K).
        self.assertEqual(text["level"], "WARN")
        self.assertEqual(notebook["level"], "OVER")
        # Override: --content code on the notebook uses the code cell.
        forced = mf.measure_file(nb, model="sonnet", content="code")
        self.assertEqual(forced["content"], "code")
        self.assertEqual(forced["ratio"], mf.bytes_per_token("sonnet", "code"))
        # The plain report names the per-file ratio when detection diverges
        # from the run-level header.
        report = mf.format_report(mf.measure_files([txt, nb]))
        self.assertIn("content=notebook auto-detected", report)
        # The CLI accepts the new classes.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(mf.main([js, "--model", "opus", "--content", "json"]), 0)
        self.assertIn("content=json", buf.getvalue())

    # -- numeric-table markdown: the line-sniffed table-md class -------------
    def _write_numeric_table(self, name: str, target_bytes: int) -> str:
        row = "| M{n} | -0.087 (0.124) | n=4,344 | 42.17 | -0.512 (0.301) | n=1,205 | 0.64 |"
        rows = ["| Model | A | B | C | D | E | F |", "|---|---:|---:|---:|---:|---:|---:|"]
        size = sum(len(r) + 1 for r in rows)
        n = 0
        while size < target_bytes:
            n += 1
            rows.append(row.format(n=n))
            size += len(rows[-1]) + 1
        path = self.tmp / name
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
        return str(path)

    def test_dense_numeric_table_markdown_is_not_ok_past_the_read_cap(self):
        # ~55 KB of decimal pipe tables read 21.2K tokens (OK) at the flat 2.6
        # ratio, while the Read tool counts such a file near 1.5 bytes per
        # token (about 37K, over the 25K page cap).
        path = self._write_numeric_table("dense.md", 55_000)
        result = mf.measure_file(path, model="opus")
        self.assertGreaterEqual(result["bytes"], 55_000)
        self.assertLess(result["bytes"], 56_000)
        self.assertLess(math.ceil(result["bytes"] / 2.6), 22_000, "the flat ratio calls it OK")
        self.assertIn(result["level"], ("WARN", "OVER"))
        self.assertEqual(result["level"], "OVER")
        self.assertEqual(result["content"], "table-md")
        self.assertLess(result["ratio"], 2.0)
        self.assertEqual(result["ratio"], round(result["bytes"] / result["tokens"], 2))
        self.assertTrue(any(g.startswith("token cap") for g in result["gates"]))
        report = mf.format_report(mf.measure_files([path], model="opus"))
        self.assertIn("content=table-md auto-detected", report)
        self.assertIn(f"ratio {result['ratio']} B/tok", report)

    def test_prose_and_text_index_controls_keep_the_existing_ratio(self):
        prose = self._write_lines("prose.md", 900, line="word " * 12)
        index_row = (
            "| 820 | BUG | Medium | NOT_STARTED | "
            "[BB-820-01-BUG-MeasureFilesTableMd](BB-820-01-BUG-MeasureFilesTableMd.md) |"
        )
        index = self._write_lines("index.md", 700, line=index_row)
        for path in (prose, index):
            result = mf.measure_file(path, model="opus")
            self.assertIsNone(result["content"], path)
            self.assertEqual(result["ratio"], 2.6, path)
            self.assertEqual(result["tokens"], math.ceil(result["bytes"] / 2.6), path)
        report = mf.format_report(mf.measure_files([prose, index], model="opus"))
        self.assertNotIn("auto-detected", report)

    def test_explicit_content_class_turns_the_table_sniff_off(self):
        path = self._write_numeric_table("forced.md", 55_000)
        prose = mf.measure_file(path, model="opus", content="prose")
        self.assertEqual(prose["content"], "prose")
        self.assertEqual(prose["ratio"], 2.9)
        self.assertEqual(prose["tokens"], math.ceil(prose["bytes"] / 2.9))
        named = mf.measure_file(path, model="opus", content="table-md")
        self.assertEqual(named["content"], "table-md")
        self.assertEqual(named["ratio"], 1.4)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(mf.main([path, "--model", "opus", "--content", "table-md"]), 0)
        self.assertIn("content=table-md", buf.getvalue())

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

    # -- --config: version-gated advisory text -------------------------------
    def _config(self, version: str) -> str:
        path = self.tmp / f"config-{version}.yaml"
        path.write_text(
            f'context:\n  verified_cli_version: "{version}"\n', encoding="utf-8"
        )
        return str(path)

    def _run(self, argv: list[str]) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(mf.main(argv), 0)
        return buf.getvalue()

    def test_config_at_floor_prints_routes_not_token_cap(self):
        path = self._write_lines("over_tokens.md", 1148)  # ~26.9K tokens
        out = self._run([path, "--config", self._config("2.1.296")])
        self.assertNotIn("token cap", out)
        # The advice line is the library text, which writes the pages route as `offset`/`limit`.
        for route in ("allow_large", "`offset`/`limit`", "Grep"):
            self.assertIn(route, out)
        self.assertIn("level:  WARN", out)
        result = mf.measure_file(path, cli_version="2.1.296")
        self.assertEqual(result["level"], "WARN")

    def test_config_below_floor_and_no_config_keep_old_text(self):
        path = self._write_lines("over_tokens.md", 1148)
        for argv in ([path], [path, "--config", self._config("2.1.295")]):
            out = self._run(argv)
            self.assertIn("token cap (>= 25,000)", out, argv)
            self.assertIn("level:  OVER", out, argv)
            self.assertNotIn("allow_large", out, argv)

    def test_config_at_floor_keeps_line_gate_over(self):
        path = self._write_lines("many_short.md", 2500, line="x" * 16)
        result = mf.measure_file(path, cli_version="2.1.296")
        self.assertEqual(result["level"], "OVER")
        self.assertEqual(result["gates"], ["line cap (>= 2,000)"])

    def test_missing_config_path_exits_two_and_names_the_path(self):
        path = self._write_lines("over_tokens.md", 1148)
        missing = str(self.tmp / "confg.yaml")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mf.main([path, "--config", missing])
        self.assertEqual(code, 2)
        self.assertIn(missing, err.getvalue())
        self.assertIn("not found", err.getvalue())
        # No report on stdout: the old hard-gate levels must not print silently.
        self.assertNotIn("level:", out.getvalue())

    def test_level_equals_the_mapped_read_level_over_a_size_and_version_grid(self):
        names = {"Green": "OK", "Warn": "WARN", "Critical": "OVER"}
        # Sizes straddle the token warn, token cap, byte warn, byte cap and line cap.
        sizes = (
            ("tiny.md", 10, 60),
            ("token_warn.md", 1000, 60),
            ("token_cap.md", 1148, 60),
            ("byte_warn.md", 3300, 74),
            ("byte_cap.md", 3600, 72),
            ("line_cap.md", 2500, 16),
        )
        versions = ("", "2.1.295", "2.1.296", "2.2.0")
        for name, n_lines, width in sizes:
            path = self._write_lines(name, n_lines, line="x" * width)
            for version in versions:
                result = mf.measure_file(path, cli_version=version)
                expected = names[
                    _read_level(
                        result["bytes"], result["tokens"], result["lines"],
                        cli_version=version,
                    )
                ]
                self.assertEqual(result["level"], expected, (name, version))

    def test_advice_is_empty_below_every_cap_and_never_names_allow_large_below_the_floor(self):
        small = self._write_lines("small.md", 100)
        self.assertEqual(mf.measure_file(small, cli_version="2.1.296")["advice"], "")
        self.assertNotIn("advice:", self._run([small, "--config", self._config("2.1.296")]))
        over = self._write_lines("over_tokens.md", 1148)
        self.assertNotIn("allow_large", mf.measure_file(over, cli_version="2.1.295")["advice"])
        self.assertNotIn("allow_large", mf.measure_file(over)["advice"])

    def test_report_prints_the_advice_once_per_file_and_it_is_the_library_text(self):
        over = self._write_lines("over_tokens.md", 1148)
        for version in ("2.1.295", "2.1.296"):
            result = mf.measure_file(over, cli_version=version)
            expected = read_routes_advice(version, fired_read_gates(
                result["bytes"], result["tokens"], result["lines"]))
            out = self._run([over, "--config", self._config(version)])
            self.assertEqual(out.count("advice:"), 1, version)
            self.assertIn(f"  advice: {expected}", out)
            self.assertEqual(result["advice"], expected)
        # A line-window crossing at the floor names pages and Grep, never allow_large.
        many = self._write_lines("many_short.md", 2500, line="x" * 16)
        self.assertNotIn("allow_large", mf.measure_file(many, cli_version="2.1.296")["advice"])

    def test_usage_docstring_json_line_keeps_its_alignment(self):
        self.assertIn("\n  --json     additionally write", mf.__doc__)


if __name__ == "__main__":
    unittest.main()
