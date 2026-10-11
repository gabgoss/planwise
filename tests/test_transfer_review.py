#!/usr/bin/env python3
"""Tests for the read-only review of transferred customizations left by an
earlier upgrade pair (`transfer_review.py`, the `--review-transfers` flag,
and the doctor sweep's `review:` line).

Every transfer file in these tests is written by the real
`upgrade_io._transfer_customization()` writer, so the wrapper the review
strips cannot drift from the wrapper the upgrade writes. The two content
fixtures the backlog item names -- an earlier-pair transfer whose content is
now shipped, and one whose content is not -- each reach their branch below.

Run with:  python -m unittest tests/test_transfer_review.py
"""

import contextlib
import io
import json
import subprocess
import sys
import types
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import doctor_cli
import init_project as ip
import transfer_review
from upgrade_io import _transfer_customization

from conftest import _MigrationFixtureBase

EARLIER = "1.0.5-to-1.0.5.1"
CURRENT = "1.0.5.1-to-1.0.5.2"

SECTION_A = (
    "## Alpha rule\n\n"
    "Every alpha write must name its owner before the writer runs.\n"
    "The owner field records who approved the write and when it happened.\n"
    "A missing owner stops the write and prints the alpha error text.\n\n"
)
SECTION_B = (
    "## Beta rule\n\n"
    "Every beta read must quote the source line before the reader acts.\n"
    "The quote field records which file and which line the reader used.\n"
    "A missing quote stops the read and prints the beta error text.\n\n"
)
SECTION_LOCAL = (
    "## Gamma local rule\n\n"
    "This project routes every gamma export through the staging warehouse.\n"
    "The staging step records the export batch and the reviewing engineer.\n"
    "A gamma export without a batch record is rejected at the loading dock.\n\n"
)
SECTION_B_REVISED = (
    "## Beta rule\n\n"
    "Every beta read must cite the source anchor, never a bare line number.\n"
    "The anchor field records the heading and the content that was used.\n"
    "A missing anchor stops the read and prints the revised beta text.\n\n"
)


def _rule(*sections: str) -> str:
    return "---\ndescription: fixture rule\n---\n\n# Fixture rule\n\n" + "".join(sections)


def _verdict(unique_blocks=None):
    return types.SimpleNamespace(
        classification="HAS_UNIQUE", unique_blocks=unique_blocks or [], notes="")


class _TransferFixture(_MigrationFixtureBase):
    def transfer(self, filename: str, body: str, pair: str = EARLIER,
                 unique_blocks=None) -> Path:
        """Write a transfer file with the real writer, then return its path."""
        from_v, to_v = pair.split("-to-")
        path = _transfer_customization(
            self.cfg, filename, "rule", body, _verdict(unique_blocks), from_v, to_v)
        self.assertIsNotNone(path, "the real writer failed to write the fixture")
        return path

    def ship(self, filename: str, body: str) -> Path:
        path = self.refs_dir / filename
        path.write_text(body, encoding="utf-8")
        return path

    def review(self, **kw) -> list[dict]:
        return transfer_review.review_transfers(self.cfg, **kw)


class TestSplitTransfer(_TransferFixture):
    def test_round_trip_through_the_real_writer_returns_the_exact_body(self):
        body = _rule(SECTION_A, SECTION_LOCAL)
        path = self.transfer("r.md", body, unique_blocks=["Gamma local rule"])

        header, stripped = transfer_review.split_transfer(path.read_text(encoding="utf-8"))

        self.assertEqual(stripped, body)
        self.assertEqual(header["source_filename"], "r.md")
        self.assertEqual(header["unique_blocks"], ["Gamma local rule"])

    def test_body_with_its_own_frontmatter_keeps_that_frontmatter(self):
        body = _rule(SECTION_A)
        path = self.transfer("r.md", body)

        _header, stripped = transfer_review.split_transfer(path.read_text(encoding="utf-8"))

        self.assertTrue(stripped.startswith("---\ndescription: fixture rule\n---\n"))

    def test_text_without_the_wrapper_is_not_split(self):
        self.assertIsNone(transfer_review.split_transfer("# Just a note\n"))
        self.assertIsNone(transfer_review.split_transfer("---\nk: v\n---\n\n# Other heading\n"))


class TestReviewBranches(_TransferFixture):
    def test_content_now_shipped_is_now_upstream(self):
        self.ship("r.md", _rule(SECTION_A, SECTION_B, SECTION_LOCAL))
        self.transfer("r.md", _rule(SECTION_A, SECTION_B), unique_blocks=["Beta rule"])

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_NOW_UPSTREAM)
        self.assertEqual(row["classification"], "SUBSET")
        self.assertEqual(row["unique_blocks"], [])
        self.assertEqual(row["recorded_unique_blocks"], ["Beta rule"])
        self.assertEqual(row["shipped"], "references/r.md")
        self.assertEqual(row["pair"], EARLIER)

    def test_content_not_shipped_is_still_unique_and_names_the_block(self):
        self.ship("r.md", _rule(SECTION_A, SECTION_B))
        self.transfer("r.md", _rule(SECTION_A, SECTION_LOCAL))

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_STILL_UNIQUE)
        self.assertEqual(row["classification"], "HAS_UNIQUE")
        self.assertTrue(any("Gamma local rule" in b for b in row["unique_blocks"]))
        self.assertEqual(row["unique_blocks_titled_in_shipped"], [])

    def test_a_revised_block_with_a_shipped_title_stays_still_unique(self):
        # The shipped file carries the same title with changed content. The
        # title match is a hint for the human read, never a SUBSET verdict.
        self.ship("r.md", _rule(SECTION_A, SECTION_B_REVISED))
        self.transfer("r.md", _rule(SECTION_A, SECTION_B))

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_STILL_UNIQUE)
        self.assertTrue(any("Beta rule" in b for b in row["unique_blocks"]))
        self.assertTrue(
            any("Beta rule" in b for b in row["unique_blocks_titled_in_shipped"]))

    def test_missing_shipped_file_is_no_counterpart(self):
        self.transfer("gone.md", _rule(SECTION_A), unique_blocks=["Alpha rule"])

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_NO_COUNTERPART)
        self.assertIsNone(row["shipped"])
        self.assertEqual(row["recorded_unique_blocks"], ["Alpha rule"])

    def test_file_without_the_wrapper_is_not_a_transfer(self):
        stray = self.project_root / "planwise" / "upgrade-transfers" / EARLIER / "note.md"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("# a stray note\n", encoding="utf-8")

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_NOT_A_TRANSFER)

    def test_header_filename_that_leaves_references_is_not_a_transfer(self):
        self.ship("r.md", _rule(SECTION_A))
        path = self.transfer("r.md", _rule(SECTION_A))
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "source_filename: r.md", "source_filename: ../r.md"),
            encoding="utf-8")

        (row,) = self.review()

        self.assertEqual(row["status"], transfer_review.STATUS_NOT_A_TRANSFER)

    def test_uniquified_transfer_name_resolves_through_the_header(self):
        # A second transfer of one rule lands as `r-{from}-to-{to}.md`; the
        # review must compare it with `references/r.md`, not with its own name.
        self.ship("r.md", _rule(SECTION_A, SECTION_B))
        self.transfer("r.md", _rule(SECTION_A))
        second = self.transfer("r.md", _rule(SECTION_A))
        self.assertNotEqual(second.name, "r.md")

        rows = self.review()

        self.assertEqual(len(rows), 2)
        self.assertEqual({r["filename"] for r in rows}, {"r.md"})
        self.assertEqual(
            {r["status"] for r in rows}, {transfer_review.STATUS_NOW_UPSTREAM})


class TestPairScopeAndReadOnly(_TransferFixture):
    def test_this_runs_own_pair_is_excluded(self):
        self.ship("r.md", _rule(SECTION_A, SECTION_B))
        self.transfer("r.md", _rule(SECTION_A), pair=EARLIER)
        self.transfer("r.md", _rule(SECTION_A), pair=CURRENT)

        rows = self.review(exclude_pair=CURRENT)

        self.assertEqual([r["pair"] for r in rows], [EARLIER])

    def test_no_transfer_directory_returns_an_empty_list(self):
        self.assertEqual(self.review(), [])

    def test_review_changes_nothing_on_disk(self):
        self.ship("r.md", _rule(SECTION_A, SECTION_B))
        self.transfer("r.md", _rule(SECTION_A))
        self.transfer("r.md", _rule(SECTION_LOCAL), pair=CURRENT)

        def snapshot():
            return {
                str(p.relative_to(self.tmp)): p.read_bytes()
                for p in self.tmp.rglob("*") if p.is_file()
            }

        before = snapshot()
        self.review()
        self.review(exclude_pair=CURRENT)

        self.assertEqual(snapshot(), before)


class TestCommandLineFlag(unittest.TestCase):
    """`init_project.py --review-transfers` against the real shipped plugin.

    A transfer of a real shipped reference, whose preserved body is that
    reference's own text, must reach `now-upstream` end to end.
    """

    def setUp(self):
        import shutil
        import tempfile

        self.tmp = Path(tempfile.mkdtemp(prefix="transfer_review_cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = ip.InitConfig(
            project_name="CliFixture",
            project_root=self.tmp,
            plugin_root=SCRIPTS.parent,
        )

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "init_project.py"),
             "--project-root", str(self.tmp), "--root", "planwise", *extra],
            capture_output=True, text=True, timeout=120, check=False,
        )

    def test_flag_prints_one_json_row_per_transfer_and_needs_no_name(self):
        shipped = (SCRIPTS.parent / "references" / "do-the-hard-things.md").read_text(
            encoding="utf-8")
        _transfer_customization(
            self.cfg, "do-the-hard-things.md", "rule", shipped, _verdict(),
            "1.0.5", "1.0.5.1")

        result = self._run("--review-transfers")

        self.assertEqual(result.returncode, 0, result.stderr)
        (row,) = json.loads(result.stdout)
        self.assertEqual(row["status"], transfer_review.STATUS_NOW_UPSTREAM)
        self.assertEqual(row["pair"], "1.0.5-to-1.0.5.1")

    def test_upgrade_pair_skips_this_runs_own_folder(self):
        _transfer_customization(
            self.cfg, "do-the-hard-things.md", "rule", "# body\n", _verdict(),
            "1.0.5", "1.0.5.1")

        result = self._run("--review-transfers", "--upgrade-pair", "1.0.5-to-1.0.5.1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_no_transfer_directory_prints_an_empty_array(self):
        result = self._run("--review-transfers")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_upgrade_pair_alone_is_still_a_parser_error(self):
        result = self._run("--upgrade-pair", "1.0.5-to-1.0.5.1")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--upgrade-pair only applies", result.stderr)


class TestDoctorReviewLine(_TransferFixture):
    def test_transfer_finding_prints_a_review_line_and_case_c_action(self):
        self.ship("r.md", _rule(SECTION_A, SECTION_B))
        self.transfer("r.md", _rule(SECTION_A))                    # now upstream
        self.transfer("s.md", _rule(SECTION_LOCAL))                # still unique
        self.ship("s.md", _rule(SECTION_A))
        # Pin the plugin version so the doctor's version-state gate resolves "ok".
        config = self.project_root / "planwise" / "config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f'plugin_version: "{self.cfg.plugin_version}"\n', encoding="utf-8")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            doctor_cli._run_doctor(self.cfg)
        out = buf.getvalue()

        self.assertIn("review:  1 now upstream, 1 still unique, 0 other", out)
        self.assertIn("Step 4.1 case C — never auto-pruned", out)
        self.assertNotIn("remove with /planwise doctor --prune-upgrade-leftovers", out.split(
            "recovery-leftover sweep")[1].split("settings-grant sweep")[0])


if __name__ == "__main__":
    unittest.main()
