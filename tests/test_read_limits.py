#!/usr/bin/env python3
"""Unit tests for the Read-tool mechanical limit gates (read_limits.py).

classify_file() + the FIXED read-limit constants (READ_FILE_BYTE_CAP,
READ_PAGE_CAP_TOKENS, READ_LINE_CAP, BYTES_PER_TOKEN) gate a path on the
token page-cap (bytes / the model's bytes-per-token ratio), the byte cap,
the defensive line window, a will-exceed-once-modified projection, and the
cost-or-read fold whose `reason` tag names the driver. The read constants
are FIXED module-level values, NOT `/context`-derived.

Run with:  python -m pytest tests/test_read_limits.py
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

from conftest import _engine  # noqa: E402


# ---------------------------------------------------------------------------
# Step 9 — Read-limit constants + classify_file
# ---------------------------------------------------------------------------
class TestReadLimits(unittest.TestCase):
    """FIXED read-limit constants and classify_file gating."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rso_read_limits_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_lines(self, name: str, n_lines: int, line: str = "x" * 60) -> str:
        path = self.tmp / name
        path.write_text("\n".join(line for _ in range(n_lines)) + "\n", encoding="utf-8")
        return str(path)

    def _write_bytes(self, name: str, n_bytes: int) -> str:
        path = self.tmp / name
        path.write_bytes(b"a" * n_bytes)
        return str(path)

    def test_read_constants_are_fixed_values(self):
        ts = _engine()
        # FIXED module-level values — NOT /context- or config-derived.
        self.assertEqual(ts.READ_FILE_BYTE_CAP, 262144)
        self.assertEqual(ts.READ_BYTE_WARN, 245760)
        self.assertEqual(ts.READ_PAGE_CAP_TOKENS, 25000)
        self.assertEqual(ts.READ_TOKEN_WARN, 22000)
        self.assertEqual(ts.READ_LINE_CAP, 2000)
        self.assertEqual(ts.DEFAULT_BYTES_PER_TOKEN, 2.6)
        # Structural pins: opus and fable share a tokenizer (measured — the
        # identical file produced the identical token count), and every
        # family's densest class (dense-md) is its smallest ratio.
        self.assertEqual(ts.BYTES_PER_TOKEN["opus"], ts.BYTES_PER_TOKEN["fable"])
        for family, ratios in ts.BYTES_PER_TOKEN.items():
            self.assertEqual(
                min(ratios.values()), ratios["dense-md"],
                f"{family}: dense-md must be the gate-conservative (smallest) ratio",
            )
        # The overall most-restrictive measured ratio is the default.
        self.assertEqual(
            ts.DEFAULT_BYTES_PER_TOKEN,
            min(r for fam in ts.BYTES_PER_TOKEN.values() for r in fam.values()),
        )

    def test_cross_model_ratio_band(self):
        """Opus token count must be 1.4–1.55× Sonnet for the same file.

        The bytes-per-token ratios are content-class averages — they are NOT
        expected to match any single fixture exactly. The cross-family band
        (measured ~1.44–1.54× on same-file A/Bs) is the correct drift signal:
        assert direction + band, not an absolute per-byte rate.
        """
        ts = _engine()
        path = self._write_lines("ratio_probe.txt", 500)
        sonnet_tokens = ts.classify_file(path, "sonnet")["tokens"]
        opus_tokens = ts.classify_file(path, "opus")["tokens"]
        ratio = opus_tokens / sonnet_tokens
        self.assertGreaterEqual(
            ratio, 1.4,
            f"Opus/Sonnet token ratio must be ≥ 1.4 (got {ratio:.3f})"
        )
        self.assertLessEqual(
            ratio, 1.55,
            f"Opus/Sonnet token ratio must be ≤ 1.55 (got {ratio:.3f})"
        )
        # Fable shares the opus tokenizer — identical estimate for the same file.
        fable_tokens = ts.classify_file(path, "fable")["tokens"]
        self.assertEqual(fable_tokens, opus_tokens)

    def test_bytes_per_token_helper(self):
        ts = _engine()
        # Unknown/absent model → the overall most-restrictive default.
        self.assertEqual(ts.bytes_per_token(), ts.DEFAULT_BYTES_PER_TOKEN)
        self.assertEqual(ts.bytes_per_token("nonexistent"), ts.DEFAULT_BYTES_PER_TOKEN)
        # Model without a content class → that family's smallest ratio.
        self.assertEqual(
            ts.bytes_per_token("sonnet"), min(ts.BYTES_PER_TOKEN["sonnet"].values())
        )
        # Model + content class → the exact cell.
        self.assertEqual(ts.bytes_per_token("opus", "prose"), ts.BYTES_PER_TOKEN["opus"]["prose"])
        # estimate_tokens rounds up and degrades to 0 on non-positive sizes.
        self.assertEqual(ts.estimate_tokens(0), 0)
        self.assertEqual(ts.estimate_tokens(-5), 0)
        self.assertEqual(ts.estimate_tokens(26), 10)  # 26 / 2.6 = 10 exactly
        self.assertEqual(ts.estimate_tokens(27), 11)  # ceil

    def test_byte_gate_critical_for_every_model(self):
        ts = _engine()
        # ~300 KB straddles the 262144-byte cap.
        path = self._write_bytes("big.bin", 300 * 1024)
        for model in ("haiku", "sonnet", "opus", "fable"):
            result = ts.classify_file(path, model)
            self.assertEqual(
                result["level"], "Critical", f"byte gate must trip on {model}"
            )
            self.assertEqual(
                result["reason"], "read", f"byte gate reason must be read on {model}"
            )

    def test_per_model_token_gate(self):
        ts = _engine()
        # ~1,148 lines × 61 B/line ≈ 70,028 B — under the byte warn and the
        # line window, but the opus/fable tokenizer (2.6 B/tok) estimates
        # ~26.9K tokens (above the 25K page cap) while sonnet (3.7 B/tok)
        # estimates ~18.9K (below the 22K warn).
        path = self._write_lines("mid.txt", 1148)
        sonnet = ts.classify_file(path, "sonnet")
        opus = ts.classify_file(path, "opus")
        self.assertNotEqual(
            sonnet["level"],
            "Critical",
            "sonnet must stay below the token page-cap for a ~70 KB file",
        )
        self.assertEqual(
            opus["level"],
            "Critical",
            "opus (2.6 B/tok) must trip the token page-cap on a ~70 KB file",
        )
        self.assertEqual(opus["reason"], "read")

    def test_token_warn_level(self):
        ts = _engine()
        # ~984 lines ≈ 60,024 B → opus ~23.1K tokens: between the 22K warn
        # and the 25K cap, under the byte warn, under the line window.
        path = self._write_lines("warmish.txt", 984)
        result = ts.classify_file(path, "opus")
        self.assertEqual(result["level"], "Warn")
        self.assertEqual(result["reason"], "read")

    def test_line_gate_defensive_third_criterion(self):
        ts = _engine()
        # 2,500 short lines (17 B each) ≈ 42.5 KB → passes the token gate
        # (~16.3K tokens even at 2.6 B/tok) and the byte gate, but crosses
        # the 2,000-line defensive window → Critical on every model.
        path = self._write_lines("many_short.txt", 2500, line="x" * 16)
        for model in ("haiku", "sonnet", "opus", "fable"):
            result = ts.classify_file(path, model)
            self.assertEqual(
                result["level"], "Critical", f"line gate must trip on {model}"
            )
            self.assertEqual(result["reason"], "read")
            self.assertLess(
                result["tokens"], ts.READ_TOKEN_WARN,
                "fixture must be under the token warn so ONLY the line gate fires",
            )

    def test_will_exceed_once_modified_projection(self):
        ts = _engine()
        # Currently-safe file for opus (~800 lines ≈ 48.8 KB ≈ 18.8K tokens),
        # but a projected byte delta pushes it past the 25K token gate
        # pre-emptively.
        path = self._write_lines("growing.txt", 800)
        safe = ts.classify_file(path, "opus")
        self.assertNotEqual(
            safe["level"], "Critical", "an ~800-line file must be safe for opus today"
        )
        projected = ts.classify_file(path, "opus", projected_added_bytes=30_000)
        self.assertEqual(
            projected["level"],
            "Critical",
            "projected_added_bytes must pre-emptively trip the read gate",
        )
        self.assertEqual(projected["reason"], "read")

    def test_cost_read_fold_takes_max(self):
        ts = _engine()
        # A file whose read arm says Critical (opus ~37.5K tokens) with a cost
        # thresholds dict that says only Warn => fold takes max => Critical,
        # reason=read.
        path = self._write_lines("folded.txt", 1600)  # opus: read=Critical
        cost_thresholds = {"warn": 1000, "critical": 10_000_000}
        result = ts.classify_file(
            path, "opus", thresholds=cost_thresholds
        )
        self.assertEqual(
            result["level"],
            "Critical",
            "fold must take max(cost_level, read_level)",
        )
        self.assertEqual(
            result["reason"],
            "read",
            "fold reason must name the driver (read here)",
        )

    def test_classify_file_reports_bytes_tokens_lines(self):
        ts = _engine()
        path = self._write_lines("small.txt", 100)
        result = ts.classify_file(path, "sonnet")
        # The result must carry the real byte size, a token estimate, and the
        # line count (the third gate's input).
        self.assertEqual(result["bytes"], os.path.getsize(path))
        self.assertGreater(result["tokens"], 0)
        self.assertEqual(result["lines"], 100)


if __name__ == "__main__":
    unittest.main()
