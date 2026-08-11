#!/usr/bin/env python3
"""Unit tests for the Read-tool mechanical limit gates (read_limits.py).

classify_file() + the FIXED read-limit constants (READ_FILE_BYTE_CAP,
READ_PAGE_CAP_TOKENS, TOKENS_PER_LINE) gate a path on a byte cap, a per-model
token page-cap, a will-exceed-once-modified projection, and the cost-or-read
fold whose `reason` tag names the driver. The read constants are FIXED
module-level values, NOT `/context`-derived.

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
        self.assertEqual(
            ts.TOKENS_PER_LINE,
            {"haiku": 13, "sonnet": 13, "opus": 19},
        )

    def test_cross_model_ratio_band(self):
        """Opus token count must be 1.4–1.55× Sonnet for the same file.

        The 13/19 TOKENS_PER_LINE constants are a *mixed code/prose average* —
        they are NOT expected to match any dense or sparse single fixture.
        This ratio band (measured 1.51×; hardcoded 19/13 = 1.46) is the correct
        drift signal: assert direction + band, not absolute per-line rate.
        """
        ts = _engine()
        # Use a moderately long mixed-content file to reduce noise.
        path = self._write_lines("ratio_probe.txt", 500)
        sonnet_result = ts.classify_file(path, "sonnet")
        opus_result = ts.classify_file(path, "opus")
        sonnet_tokens = sonnet_result["tokens"]
        opus_tokens = opus_result["tokens"]
        ratio = opus_tokens / sonnet_tokens
        self.assertGreaterEqual(
            ratio, 1.4,
            f"Opus/Sonnet token ratio must be ≥ 1.4 (got {ratio:.3f})"
        )
        self.assertLessEqual(
            ratio, 1.55,
            f"Opus/Sonnet token ratio must be ≤ 1.55 (got {ratio:.3f})"
        )

    def test_byte_gate_critical_for_every_model(self):
        ts = _engine()
        # ~300 KB straddles the 262144-byte cap.
        path = self._write_bytes("big.bin", 300 * 1024)
        for model in ("haiku", "sonnet", "opus"):
            result = ts.classify_file(path, model)
            self.assertEqual(
                result["level"], "Critical", f"byte gate must trip on {model}"
            )
            self.assertEqual(
                result["reason"], "read", f"byte gate reason must be read on {model}"
            )

    def test_per_model_token_gate(self):
        ts = _engine()
        # ~1600 lines: sonnet 13 tok/line ~= 20.8K (below 25K),
        # opus 19 tok/line ~= 30.4K (above 25K).
        path = self._write_lines("mid.txt", 1600)
        sonnet = ts.classify_file(path, "sonnet")
        opus = ts.classify_file(path, "opus")
        self.assertNotEqual(
            sonnet["level"],
            "Critical",
            "sonnet must stay below the token page-cap for a 1600-line file",
        )
        self.assertEqual(
            opus["level"],
            "Critical",
            "opus (19 tok/line) must trip the token page-cap on a 1600-line file",
        )
        self.assertEqual(opus["reason"], "read")

    def test_will_exceed_once_modified_projection(self):
        ts = _engine()
        # Currently-safe file for opus (~800 lines ~= 15.2K), but a projected
        # addition pushes it past the 25K opus token gate pre-emptively.
        path = self._write_lines("growing.txt", 800)
        safe = ts.classify_file(path, "opus")
        self.assertNotEqual(
            safe["level"], "Critical", "800-line file must be safe for opus today"
        )
        projected = ts.classify_file(path, "opus", projected_added_lines=700)
        self.assertEqual(
            projected["level"],
            "Critical",
            "projected_added_lines must pre-emptively trip the read gate",
        )
        self.assertEqual(projected["reason"], "read")

    def test_cost_read_fold_takes_max(self):
        ts = _engine()
        # A small file (read says Green/Notice) but a cost thresholds dict that
        # says Warn, and a read that says Critical => fold takes max => Critical,
        # reason=read. To force read=Critical we use a large file; cost=Warn via
        # a thresholds dict that classifies the same byte size only as Warn.
        path = self._write_lines("folded.txt", 1600)  # opus: read=Critical
        # cost thresholds chosen so the cost arm classifies this as Warn only.
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

    def test_classify_file_reports_bytes_and_tokens(self):
        ts = _engine()
        path = self._write_lines("small.txt", 100)
        result = ts.classify_file(path, "sonnet")
        # The result must carry the real byte size and a token estimate.
        self.assertEqual(result["bytes"], os.path.getsize(path))
        self.assertGreater(result["tokens"], 0)


if __name__ == "__main__":
    unittest.main()
