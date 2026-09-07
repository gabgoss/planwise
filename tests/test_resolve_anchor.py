#!/usr/bin/env python3
"""Regression tests for resolve_anchor.py.

Four behaviours are under test: the three anchor schemes, the claims
ledger's collision avoidance, the claim's self-invalidation once the anchor
is physically present, and the relocation-redirect warning.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts")
)

import resolve_anchor  # noqa: E402


TOPLEVEL_DOC = """# A Reference

## 1. First

Body.

## 2. Second

Body.

## 11. Eleventh

Body.
"""

SUB_DOC = """# A Reference

### 9.B.1 First

Body.

### 9.B.19 Nineteenth

Body.

### 9.A.40 A different family entirely

Body.
"""

TABLE_DOC = """# Error Pattern Catalog

| Row | Pattern | Severity |
|-----|---------|----------|
| 1 | Something | Low |
| 109 | Something else | High |
"""


class _ResolveAnchorFixtureBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="resolve_anchor_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ledger = self.tmp / ".anchor-claims.json"

    def write_doc(self, name: str, body: str) -> Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    def run_main(self, argv_tail: list[str]) -> tuple[str, str, object]:
        """Invoke resolve_anchor.main(); return (stdout, stderr, exit_code).

        exit_code is None when main() returned instead of calling sys.exit().
        """
        saved_argv = sys.argv
        sys.argv = ["resolve_anchor"] + argv_tail
        out, err = io.StringIO(), io.StringIO()
        exit_code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    resolve_anchor.main()
                except SystemExit as e:
                    exit_code = e.code
        finally:
            sys.argv = saved_argv
        return out.getvalue(), err.getvalue(), exit_code

    def run_json(self, argv_tail: list[str]) -> dict:
        out, _, code = self.run_main(argv_tail + ["--json"])
        self.assertIsNone(code, msg=f"expected a clean exit, got {code}")
        return json.loads(out)


class TestAnchorSchemes(_ResolveAnchorFixtureBase):
    def test_heading_toplevel_returns_max_and_next_free(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)

        result = self.run_json(["--file", str(doc), "--scheme", "heading-toplevel"])

        # 11, not 2 -- the scan takes the maximum, not the last line matched.
        self.assertEqual(result["max_found"], 11)
        self.assertEqual(result["next_free"], 12)
        self.assertEqual(result["scheme"], "heading-toplevel")

    def test_heading_sub_is_scoped_to_its_own_prefix(self):
        doc = self.write_doc("ref.md", SUB_DOC)

        result = self.run_json(
            ["--file", str(doc), "--scheme", "heading-sub", "--prefix", "9.B."]
        )

        # The 9.A.40 heading is a different family and must not raise the max.
        self.assertEqual(result["max_found"], 19)
        self.assertEqual(result["next_free"], 20)

    def test_heading_sub_without_a_prefix_is_a_usage_error(self):
        doc = self.write_doc("ref.md", SUB_DOC)

        _, err, code = self.run_main(["--file", str(doc), "--scheme", "heading-sub"])

        self.assertEqual(code, 2)
        self.assertIn("--prefix", err)

    def test_table_row_reads_the_first_pipe_delimited_column(self):
        doc = self.write_doc("catalog.md", TABLE_DOC)

        result = self.run_json(["--file", str(doc), "--scheme", "table-row"])

        self.assertEqual(result["max_found"], 109)
        self.assertEqual(result["next_free"], 110)

    def test_a_file_with_no_anchors_starts_at_one(self):
        doc = self.write_doc("empty.md", "# Nothing here\n\nJust prose.\n")

        result = self.run_json(["--file", str(doc), "--scheme", "heading-toplevel"])

        self.assertEqual(result["max_found"], 0)
        self.assertEqual(result["next_free"], 1)

    def test_a_missing_file_is_a_usage_error(self):
        _, err, code = self.run_main(
            ["--file", str(self.tmp / "absent.md"), "--scheme", "table-row"]
        )

        self.assertEqual(code, 2)
        self.assertIn("File not found", err)


class TestClaimsLedger(_ResolveAnchorFixtureBase):
    def test_a_second_concurrent_claim_returns_one_higher(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)  # live max 11
        argv = [
            "--file", str(doc),
            "--scheme", "heading-toplevel",
            "--ledger", str(self.ledger),
        ]

        first = self.run_json(argv + ["--claim", "item-a"])
        second = self.run_json(argv + ["--claim", "item-b"])

        # Neither caller inserted anything, so the file's max is still 11 for
        # both. Without the ledger both would compute 12.
        self.assertEqual(first["claimed"], 12)
        self.assertEqual(second["claimed"], 13)
        self.assertEqual(second["next_free"], 12)  # the raw scan is unchanged
        self.assertEqual(second["prior_live_claims"], [12])

    def test_a_second_claim_warns_that_the_raw_next_free_was_reserved(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)
        argv = [
            "--file", str(doc),
            "--scheme", "heading-toplevel",
            "--ledger", str(self.ledger),
        ]
        self.run_json(argv + ["--claim", "item-a"])

        _, err, code = self.run_main(argv + ["--claim", "item-b"])

        self.assertIsNone(code)  # advisory, never fatal
        self.assertIn("unconsumed claim", err)

    def test_a_claim_is_released_once_the_anchor_is_present_in_the_file(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)  # live max 11
        argv = [
            "--file", str(doc),
            "--scheme", "heading-toplevel",
            "--ledger", str(self.ledger),
        ]

        first = self.run_json(argv + ["--claim", "item-a"])
        self.assertEqual(first["claimed"], 12)

        # Insert the claimed anchor -- the act that consumes the claim.
        doc.write_text(TOPLEVEL_DOC + "\n## 12. Twelfth\n\nBody.\n", encoding="utf-8")

        second = self.run_json(argv + ["--claim", "item-b"])

        # 13, NOT 14: the now-real anchor settles the claim rather than
        # stacking on top of it.
        self.assertEqual(second["max_found"], 12)
        self.assertEqual(second["claimed"], 13)
        self.assertEqual(second["prior_live_claims"], [])

        # The settled claim is pruned from the ledger rather than accumulating.
        ledger_data = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual([c["claimed_value"] for c in ledger_data["claims"]], [13])

    def test_claims_for_different_keys_do_not_interfere(self):
        toplevel = self.write_doc("ref.md", TOPLEVEL_DOC)
        catalog = self.write_doc("catalog.md", TABLE_DOC)

        first = self.run_json(
            ["--file", str(toplevel), "--scheme", "heading-toplevel",
             "--ledger", str(self.ledger), "--claim", "item-a"]
        )
        second = self.run_json(
            ["--file", str(catalog), "--scheme", "table-row",
             "--ledger", str(self.ledger), "--claim", "item-b"]
        )

        self.assertEqual(first["claimed"], 12)
        self.assertEqual(second["claimed"], 110)  # its own space, not 13

    def test_the_ledger_defaults_to_the_target_repository_root(self):
        (self.tmp / ".git").mkdir()
        nested = self.tmp / "plugins" / "refs"
        nested.mkdir(parents=True)
        doc = nested / "ref.md"
        doc.write_text(TOPLEVEL_DOC, encoding="utf-8")

        result = self.run_json(
            ["--file", str(doc), "--scheme", "heading-toplevel", "--claim", "item-a"]
        )

        self.assertEqual(Path(result["ledger"]), self.tmp / ".anchor-claims.json")
        self.assertTrue((self.tmp / ".anchor-claims.json").exists())

    def test_a_malformed_ledger_is_reported_not_silently_reset(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)
        self.ledger.write_text("{not json", encoding="utf-8")

        _, err, code = self.run_main(
            ["--file", str(doc), "--scheme", "heading-toplevel",
             "--ledger", str(self.ledger), "--claim", "item-a"]
        )

        self.assertEqual(code, 2)
        self.assertIn("unreadable", err)


class TestRelocationWarning(_ResolveAnchorFixtureBase):
    def test_a_segment_index_marker_warns_without_failing(self):
        doc = self.write_doc(
            "ref.md",
            TOPLEVEL_DOC + "\n## Segment Index\n\n| Section | Now in |\n",
        )

        out, err, code = self.run_main(
            ["--file", str(doc), "--scheme", "heading-toplevel", "--json"]
        )

        # Advisory only: the number is still returned and the exit is clean.
        self.assertIsNone(code)
        self.assertIn("relocation-redirect marker", err)
        self.assertEqual(json.loads(out)["max_found"], 11)

    def test_a_clean_file_produces_no_relocation_warning(self):
        doc = self.write_doc("ref.md", TOPLEVEL_DOC)

        _, err, code = self.run_main(
            ["--file", str(doc), "--scheme", "heading-toplevel"]
        )

        # The known-good half of the dry-run: the marker check discriminates
        # instead of firing on everything.
        self.assertIsNone(code)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
