#!/usr/bin/env python3
"""Unit tests for the backlog-index generator's CLI, write path and guards.

`generate_backlog_index.py` scans every backlog item file's YAML frontmatter,
renders it into a 9-column table row, shards the corpus into a hub plus
Archive files under a per-file token budget, fills the Score cell via
`score_backlog.compute_score`, and drives `--check`/`--write` against
whatever is currently on disk.

This file pins: atomic multi-file write rollback on a mid-write failure; the
D12 guarantee that `--write` never touches an item file; line-ending
preservation; the one exit-code mapping (`Disposition`/`exit_code_for`) every
mode routes through; output paths that follow config; a failed write exiting
as refused; the changelog footer; scan overrides reaching the report
pipeline; `_cmd_check` returning what `main()` returns; and the refusal of a
legacy or unrecognized index.

Three sibling files hold the other classes. This map lets an old pytest node
id that names one of them under this file still resolve:

`test_generate_backlog_index_budget.py`:
- TestColumnPositionContract
- TestEscapedPipeRoundTrip
- TestShardForIsPure
- TestBudgetEnforcerThreePaths
- TestWriteRefusesOnPathologicalRow
- TestSplitMeasuresShippedFileNotBody
- TestHubDirectoryListsOverflowLeaves
- TestFactor2RekeyReachesGenerator
- TestHubBudgetIsHalfThePageCap
- TestCrlfCheckoutBytesAreBudgeted
- TestShardSplitCountsCrlfBytes
- TestHubDirectoryIsComplete
- TestPrintedReportShowsBudgetAndRatio

`test_generate_backlog_index_scan.py`:
- TestUnresolvableBlocksAborts
- TestReciprocalBlocksEdge
- TestBlocksCycles
- TestInvertedBlocksEdge
- TestScannerSkipsOwnGeneratedArtifacts
- TestDuplicateItemIdRefusedAtScan
- TestGeneratedFilePatternCoversFourDigitIds
- TestInlineCommentStrippedAtReadSites
- TestScanBacklogOverridesSkipInvalidDisk

`test_generate_backlog_index_drift.py`:
- TestCheckFourClasses
- TestCRLFMalformedRowAnomaly
- TestStaleGeneratedFileDriftAndRemoval
- TestDuplicateRowIsAnomaly
- TestStaleScoreShowsValuesAndNonNumericOpenIsDrift
- TestCrossFileDuplicateRowIsAnomaly
- TestTruncationWarningIsOneLinePerRun
- TestTruncatedTableReasonReplacesMisleadingText
- TestMissingArchiveShardIsDrift

Each test builds an isolated temp planwise tree (config.yaml + Backlog/ +
Backlog/Archive/) or exercises a pure function directly; none read the live
project's backlog, and every fixture item is synthetic.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index.py
"""

import difflib
import hashlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import migrate_backlog_support as sup
from generate_backlog_index_fixtures import (
    _GeneratorFixtureBase,
)


class TestAtomicWriteRollsBackOnMidFailure(unittest.TestCase):
    """A mid-write failure must leave the prior on-disk state intact --
    no partial shard set, no leftover temp file, no committed new file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_atomic_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.hub = self.tmp / "00-Index-Backlog.md"
        self.shard = self.tmp / "Archive" / "Index-Backlog-001-100.md"
        self.shard.parent.mkdir(parents=True, exist_ok=True)
        self.hub.write_text("ORIGINAL HUB\n", encoding="utf-8")
        self.shard.write_text("ORIGINAL SHARD\n", encoding="utf-8")

    def test_mid_write_failure_leaves_prior_state_intact(self):
        new_shard = self.tmp / "Archive" / "Index-Backlog-101-200.md"
        files_to_write = {
            self.hub: "NEW HUB\n",
            self.shard: "NEW SHARD\n",
            new_shard: "BRAND NEW\n",
        }
        hub_before = self.hub.read_bytes()
        shard_before = self.shard.read_bytes()

        real_replace = gbi.os.replace
        call_count = {"n": 0}

        def flaky_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise OSError("simulated mid-write failure")
            return real_replace(src, dst)

        with patch.object(gbi.os, "replace", side_effect=flaky_replace), self.assertRaises(OSError):
            gbi._atomic_write_files(files_to_write, [])

        self.assertEqual(self.hub.read_bytes(), hub_before)
        self.assertEqual(self.shard.read_bytes(), shard_before)
        self.assertFalse(new_shard.exists())
        self.assertEqual(list(self.tmp.rglob("*.tmp")), [])


class TestD12ItemFileNeverWritten(_GeneratorFixtureBase):
    """Master Plan D12: the generator never writes an item file. A route_*
    keyed item -- content this generator does not even read -- must
    survive --write byte-for-byte."""

    def test_write_leaves_item_file_byte_identical(self):
        path = self.write_item(
            "001", title="Routed item", priority="High", status="NOT_STARTED",
            abbrev="BUG", created="2026-01-01",
            extra_frontmatter=(
                "route_hint: direct-fix\n"
                "route_evidence: reproduced locally\n"
                "route_dated: 2026-09-19\n"
            ),
        )
        before = path.read_bytes()

        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertEqual(path.read_bytes(), before)


class TestLineEndingsPreservedOneRowDiff(_GeneratorFixtureBase):
    """`--write` must preserve the EXISTING generated-file line-ending
    convention (`detect_line_ending`) rather than always shipping the `\n`
    `build_index_files` renders internally -- detected once per run so the
    hub and every Archive shard agree. A one-row content change must
    therefore still produce a one-row diff, not a whole-file rewrite
    disguised as one by a silent LF/CRLF flip."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        self.write_item("003", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="DOC", created="2025-06-01",
                         archived=True, filename="BB-003-01-DOC-Fixture.md")

    def test_crlf_convention_preserved_and_one_row_changes_one_line(self):
        self.run_main("--write")

        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        shard_path = self.archive_dir / "Index-Backlog-003-003.md"

        # Rewrite the on-disk hub as CRLF from explicit bytes -- never
        # Path.write_text, which would normalize to os.linesep instead of
        # the exact byte sequence this test needs to control.
        crlf_bytes = hub_path.read_bytes().replace(b"\n", b"\r\n")
        hub_path.write_bytes(crlf_bytes)
        self.assertEqual(crlf_bytes.count(b"\r\n"), crlf_bytes.count(b"\n"))

        # An EOL-only difference is never drift.
        code, _out, _err = self.run_main("--check")
        self.assertEqual(code, 0)

        old_hub_bytes = hub_path.read_bytes()

        # Change one item's frontmatter -- the one row this must ripple to.
        item_path = self.backlog_dir / "BB-001-01-BUG-Fixture.md"
        text = item_path.read_text(encoding="utf-8")
        item_path.write_text(text.replace("priority: High", "priority: Medium"), encoding="utf-8")

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        new_hub_bytes = hub_path.read_bytes()

        # The existing CRLF convention was preserved, not flipped back to LF.
        self.assertGreater(new_hub_bytes.count(b"\r\n"), 0)
        self.assertEqual(new_hub_bytes.count(b"\r\n"), new_hub_bytes.count(b"\n"))

        # A one-row content change produces a one-row diff -- not a
        # whole-file rewrite disguised as one by a silent EOL flip.
        old_lines = old_hub_bytes.decode("utf-8").splitlines(keepends=True)
        new_lines = new_hub_bytes.decode("utf-8").splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
        changed = [
            line for line in diff
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        self.assertEqual(len(changed), 2)  # exactly one before/after line pair
        self.assertTrue(any(line.startswith("-") and "001" in line for line in changed))
        self.assertTrue(any(line.startswith("+") and "001" in line for line in changed))

        # One convention across the whole generated set -- the Archive
        # shard (item 003, closed) is CRLF too.
        shard_bytes = shard_path.read_bytes()
        self.assertGreater(shard_bytes.count(b"\r\n"), 0)
        self.assertEqual(shard_bytes.count(b"\r\n"), shard_bytes.count(b"\n"))

    def test_no_pre_existing_hub_defaults_to_lf(self):
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        hub_bytes = (self.backlog_dir / "00-Index-Backlog.md").read_bytes()
        self.assertEqual(hub_bytes.count(b"\r\n"), 0)
        self.assertGreater(hub_bytes.count(b"\n"), 0)


class TestExitCodeMapping(unittest.TestCase):
    """The one exit-code mapping every mode routes through, pinned directly
    per its own disposition table: 0 clean, 1 drift/anomaly (and a
    reciprocal edge in a report mode), 2 refused (and a reciprocal edge on
    --write)."""

    def test_clean(self):
        self.assertEqual(
            gbi.exit_code_for(write_mode=False, reciprocal_edge=False, drift_or_anomaly=False),
            gbi.Disposition.CLEAN,
        )

    def test_drift_or_anomaly_in_report_mode(self):
        self.assertEqual(
            gbi.exit_code_for(write_mode=False, reciprocal_edge=False, drift_or_anomaly=True),
            gbi.Disposition.DRIFT_OR_ANOMALY,
        )

    def test_reciprocal_edge_in_report_mode_is_drift_or_anomaly(self):
        self.assertEqual(
            gbi.exit_code_for(write_mode=False, reciprocal_edge=True, drift_or_anomaly=False),
            gbi.Disposition.DRIFT_OR_ANOMALY,
        )

    def test_reciprocal_edge_on_write_is_refused(self):
        self.assertEqual(
            gbi.exit_code_for(write_mode=True, reciprocal_edge=True, drift_or_anomaly=False),
            gbi.Disposition.REFUSED,
        )

    def test_disposition_constants(self):
        self.assertEqual(gbi.Disposition.CLEAN, 0)
        self.assertEqual(gbi.Disposition.DRIFT_OR_ANOMALY, 1)
        self.assertEqual(gbi.Disposition.REFUSED, 2)


class TestOutputPathsFollowConfig(unittest.TestCase):
    """CR5 (Finding 5): every generated filename -- hub, hub overflow leaf,
    and Archive shard -- must be derived from the project's own configured
    `index_files.backlog` path and archive dir, never a hardcoded
    `00-Index-Backlog.md` no other script in a differently-named project
    would recognize."""

    CONFIG_YAML = """project:
  name: "CustomNamingFixtureProject"
  backlog_dir: "Backlog"
  archive_dir: "Backlog/OldClosed"
  index_files:
    backlog: "Backlog-Index.md"
"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_naming_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.planwise_dir / "Backlog" / "OldClosed"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(self.CONFIG_YAML, encoding="utf-8")

        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def write_item(self, item_id, *, title="Fixture item", priority="Medium",
                   status="NOT_STARTED", abbrev="BUG", created="2026-01-01",
                   blocks=None, archived=False, filename=None):
        blocks = blocks or []
        blocks_yaml = "[]" if not blocks else "[" + ", ".join(blocks) + "]"
        content = (
            "---\n"
            f"id: {item_id}\n"
            f"title: {title}\n"
            f"priority: {priority}\n"
            f"status: {status}\n"
            f"abbrev: {abbrev}\n"
            f"created: {created}\n"
            f"blocks: {blocks_yaml}\n"
            "---\n\n"
            f"# {title}\n"
        )
        target_dir = self.archive_dir if archived else self.backlog_dir
        name = filename or f"BB-{item_id}-01-{abbrev}-Fixture.md"
        path = target_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def run_main(self, *extra_args):
        sys.argv = ["test_generate_backlog_index", "--config", str(self.config_path), *extra_args]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gbi.main()
        return code, out.getvalue(), err.getvalue()

    def test_write_uses_configured_hub_name_not_the_default(self):
        self.write_item("001", title="Open item")

        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertTrue((self.backlog_dir / "Backlog-Index.md").exists())
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_shards_land_under_the_configured_archive_dir(self):
        self.write_item("001", title="Open item")
        self.write_item("150", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-150-01-PROC-Fixture.md")

        code, _out, _err = self.run_main("--write")

        self.assertEqual(code, 0)
        self.assertTrue((self.archive_dir / "Backlog-Index-150-150.md").exists())

        code, _out, _err = self.run_main("--check")
        self.assertEqual(code, 0)

    def test_naming_recognition_is_config_scoped_not_default(self):
        fixture_naming = gbi._index_naming(self.backlog_dir / "Backlog-Index.md")
        self.assertTrue(gbi.is_generated_index_file("Backlog-Index-150-150.md", fixture_naming))
        self.assertFalse(gbi.is_generated_index_file("Backlog-Index-150-150.md"))  # default naming
        self.assertFalse(gbi.is_generated_index_file("00-Index-Backlog.md", fixture_naming))

    def test_changelog_uses_the_configured_hub_name_via_fallback(self):
        # closeout review Finding 1: a hub that doesn't follow the
        # "00-Index-{X}" shape falls back to "00-{hub_stem}-Changelog{suffix}"
        # -- the SAME name migrate_backlog_index.artifact_paths computes.
        fixture_naming = gbi._index_naming(self.backlog_dir / "Backlog-Index.md")
        self.assertEqual(gbi._changelog_filename(fixture_naming), "00-Backlog-Index-Changelog.md")

        self.write_item("001", title="Open item")
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertTrue((self.backlog_dir / "00-Backlog-Index-Changelog.md").exists())


class TestFailedWriteExitsRefusedNotDrift(_GeneratorFixtureBase):
    """CR7 (Finding 6): an uncaught `OSError` mid-`--write` must be
    reported and refused (exit 2), never let a traceback escape and read
    as if `--check` had found drift -- and the internal rollback's own
    state guarantee (Task 3's atomicity proof) must still hold."""

    def test_first_replace_failure_refuses_names_path_no_traceback(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.run_main("--write")

        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        before_hash = hashlib.sha256(hub_path.read_bytes()).hexdigest()

        def flaky_replace(src, dst):
            raise OSError(13, "simulated locked file", str(dst))

        with patch.object(gbi.os, "replace", side_effect=flaky_replace):
            code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn(str(hub_path), err)

        after_hash = hashlib.sha256(hub_path.read_bytes()).hexdigest()
        self.assertEqual(before_hash, after_hash)


class TestChangelogFooter(_GeneratorFixtureBase):
    """Pre-write repair, Execution Step 4 (user decision (a)): the hub
    carries a fixed, byte-identical pointer to the changelog after
    `## Shards`, and `--check` treats a hand-deleted footer as drift.

    Closeout review Finding 1 extends this: `_changelog_filename` is the
    ONE namer the footer, `--write`'s missing-changelog bootstrap, `--check`'s
    missing-target drift, and `migrate_backlog_index.artifact_paths` all
    share -- covered here for the default naming; custom-hub-name coverage
    lives in `TestOutputPathsFollowConfig` above."""

    def _footer_line(self):
        naming = gbi._index_naming(self.backlog_dir / "00-Index-Backlog.md")
        return gbi._footer_line(naming)

    def test_changelog_filename_default(self):
        naming = gbi._index_naming(self.backlog_dir / "00-Index-Backlog.md")
        self.assertEqual(gbi._changelog_filename(naming), "00-Changelog-Backlog.md")

    def test_footer_present_and_stable_across_two_writes(self):
        self.write_item(1)
        code1, _out1, _err1 = self.run_main("--write")
        self.assertEqual(code1, 0)
        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        content1 = hub_path.read_text(encoding="utf-8")
        footer_line = self._footer_line()
        self.assertIn(footer_line.strip(), content1)
        self.assertTrue(content1.endswith(footer_line))

        code2, _out2, _err2 = self.run_main("--write")
        self.assertEqual(code2, 0)
        content2 = hub_path.read_text(encoding="utf-8")
        self.assertEqual(content1, content2)

    def test_check_flags_a_hand_deleted_footer_as_drift(self):
        self.write_item(1)
        self.run_main("--write")
        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        content = hub_path.read_text(encoding="utf-8")
        footer_line = self._footer_line()
        self.assertTrue(content.endswith(footer_line))
        hub_path.write_text(content[: -len(footer_line)], encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("footer is missing from the hub", out)

    def test_write_creates_a_missing_changelog_header_only(self):
        self.write_item(1)
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        changelog_path = self.backlog_dir / "00-Changelog-Backlog.md"
        self.assertTrue(changelog_path.exists())
        self.assertEqual(
            changelog_path.read_text(encoding="utf-8"),
            "[← 00-Index-Backlog.md](00-Index-Backlog.md)\n",
        )

    def test_write_never_overwrites_an_existing_changelog(self):
        self.write_item(1)
        changelog_path = self.backlog_dir / "00-Changelog-Backlog.md"
        changelog_path.write_text("[← 00-Index-Backlog.md](00-Index-Backlog.md)\n\n"
                                   "## Entry 1\n\nSomething happened.\n", encoding="utf-8")
        before = changelog_path.read_bytes()

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertEqual(changelog_path.read_bytes(), before)

    def test_check_fails_on_a_missing_changelog_target(self):
        self.write_item(1)
        self.run_main("--write")
        changelog_path = self.backlog_dir / "00-Changelog-Backlog.md"
        changelog_path.unlink()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("00-Changelog-Backlog.md", out)
        self.assertIn("does not exist", out)


class TestRunReportPipelineOverridesRoundTrip(_GeneratorFixtureBase):
    """`overrides` threads through `_run_report_pipeline` as it does through
    the scan (`TestScanBacklogOverridesSkipInvalidDisk` in
    `test_generate_backlog_index_scan.py`), so the report a caller measures
    reflects the planned backfill, not the invalid on-disk block."""

    def test_overrides_reach_the_rendered_report(self):
        path = self.write_item("001", title="On-disk broken", priority="High",
                                status="NOT_STARTED", abbrev="BUG")
        text = path.read_text(encoding="utf-8")
        broken_text = "\n".join(
            line for line in text.split("\n") if not line.startswith("created:")
        )
        path.write_text(broken_text, encoding="utf-8")
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        naming = gbi._index_naming(index_path)

        override_text = (
            "---\nid: 001\ntitle: Override title\npriority: High\n"
            "status: NOT_STARTED\nabbrev: BUG\ncreated: 2026-02-02\n"
            "blocks: []\n---\n\n# Override title\n"
        )
        items, reciprocal, report = gbi._run_report_pipeline(
            self.backlog_dir, self.archive_dir, index_path, naming, {},
            overrides={path.resolve(): override_text},
        )

        self.assertEqual(reciprocal, [])
        self.assertEqual(items[0]["title"], "Override title")
        self.assertIn("Override title", report["files"][0]["content"])


class TestCmdCheckMatchesMainOnFourDigitFixture(_GeneratorFixtureBase):
    """`_cmd_check` is the same callable `main()`'s `--check` branch now
    delegates to -- proven by reproducing the four-digit-id round-trip
    fixture (`TestGeneratedFilePatternCoversFourDigitIds` in
    `test_generate_backlog_index_scan.py`) and calling `_cmd_check`
    directly, in-process, with no argv/CLI involved."""

    def test_cmd_check_returns_the_same_code_as_main(self):
        self.write_item("001", title="Open item")
        self.write_item("1000", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-1000-01-PROC-Fixture.md")
        self.run_main("--write")

        main_code, _out, _err = self.run_main("--check")

        index_path = self.backlog_dir / "00-Index-Backlog.md"
        naming = gbi._index_naming(index_path)
        direct_code = gbi._cmd_check(
            self.backlog_dir, self.archive_dir, index_path, naming, {}, json_out=False,
        )

        self.assertEqual(direct_code, main_code)
        self.assertEqual(direct_code, 0)


class TestGeneratorRefusesLegacyOrUnrecognizedIndex(_GeneratorFixtureBase):
    """BB-380 fold (Session-02): `--write` and `--check` refuse loudly on a
    hand-authored or unrecognized hub instead of silently overwriting it
    or reporting drift over zero rows."""

    LEGACY_INDEX_TEXT = (
        "# Backlog Index\n\n"
        "## Backlog Items\n\n"
        "| ID | Feature | Priority | Status | Abbrev | Created | Files |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 001 | Sample item | Medium | NOT_STARTED | BUG | 2026-01-01 "
        "| [file](001-Sample.md) |\n\n"
        "*Last Updated: 2026-01-01 — created*\n"
    )
    UNRECOGNIZED_INDEX_TEXT = "# Backlog Index\n\n| Foo | Bar |\n|---|---|\n| 1 | 2 |\n"

    def _write_index_text(self, text):
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        index_path.write_text(text, encoding="utf-8")
        return index_path

    def _snapshot(self):
        return {p: p.read_bytes() for p in self.planwise_dir.rglob("*") if p.is_file()}

    def test_write_refuses_legacy_hub_and_leaves_tree_unchanged(self):
        self._write_index_text(self.LEGACY_INDEX_TEXT)
        before = self._snapshot()

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("hand-authored", err)
        self.assertIn("--replace-legacy", err)
        self.assertIn("WITHOUT a backup", err)
        self.assertEqual(self._snapshot(), before)

    def test_write_replace_legacy_overwrites_and_becomes_migrated(self):
        self._write_index_text(self.LEGACY_INDEX_TEXT)

        code, _out, _err = self.run_main("--write", "--replace-legacy")

        self.assertEqual(code, 0)
        index_path = self.backlog_dir / "00-Index-Backlog.md"
        shape, _detail = sup.classify_shape(index_path.read_text(encoding="utf-8"))
        self.assertEqual(shape, "migrated")

    def test_check_refuses_legacy_hub(self):
        self._write_index_text(self.LEGACY_INDEX_TEXT)

        code, _out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertIn("hand-authored", err)
        self.assertIn("/planwise upgrade", err)

    def test_write_refuses_unrecognized_hub(self):
        self._write_index_text(self.UNRECOGNIZED_INDEX_TEXT)
        before = self._snapshot()

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertNotIn("hand-authored", err)
        self.assertIn("unrecognized index shape", err)
        self.assertIn("migrate_backlog_index.py", err)
        self.assertIn("--report", err)
        self.assertIn("--replace-legacy", err)
        self.assertIn("WITHOUT a backup", err)
        self.assertEqual(self._snapshot(), before)

    def test_check_refuses_unrecognized_hub(self):
        self._write_index_text(self.UNRECOGNIZED_INDEX_TEXT)

        code, _out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertNotIn("hand-authored", err)
        self.assertIn("unrecognized index shape", err)
        self.assertIn("--report", err)

    def test_generated_fixture_write_and_check_unchanged(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)


class TestGeneratorGuardSkipsAlreadyMigratedPointerFooter(unittest.TestCase):
    """A legacy-shaped table whose single footer is already a migration
    pointer (`moved to [...](...)`) has already been processed by
    `migrate_backlog_index.py` -- only the table itself is still in the
    old shape, and `--write`/`--check` must finish regenerating it without
    `--replace-legacy`. A genuine untouched legacy footer must still be
    refused. Uses a custom index name, matching the scenario a pre-existing
    migrator test exercises."""

    CONFIG_YAML = """project:
  name: "PointerFooterFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "Backlog-Index.md"
"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_pointer_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(self.CONFIG_YAML, encoding="utf-8")
        (self.backlog_dir / "001-Sample.md").write_text(
            "---\nid: 001\ntitle: Sample item\npriority: Medium\n"
            "status: NOT_STARTED\nabbrev: BUG\ncreated: 2026-01-01\n"
            "blocks: []\n---\n\n# Sample item\n",
            encoding="utf-8",
        )
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def run_main(self, *extra_args):
        sys.argv = ["test_generate_backlog_index", "--config", str(self.config_path), *extra_args]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gbi.main()
        return code, out.getvalue(), err.getvalue()

    def test_pointer_footer_legacy_table_passes_write_and_check(self):
        index_path = self.backlog_dir / "Backlog-Index.md"
        index_path.write_text(
            "## Backlog Items\n\n"
            "| ID | Feature | Priority | Status | Abbrev | Created | Files |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 001 | Sample item | Medium | NOT_STARTED | BUG | 2026-01-01 "
            "| [file](001-Sample.md) |\n\n"
            "*Last Updated: 2026-01-01 — moved to "
            "[00-Backlog-Index-Changelog.md](00-Backlog-Index-Changelog.md)*\n",
            encoding="utf-8",
        )
        (self.backlog_dir / "00-Backlog-Index-Changelog.md").write_bytes(
            b"[\xe2\x86\x90 Backlog-Index.md](Backlog-Index.md)\n\n## Entry 1\n\n 2026-01-01 \xe2\x80\x94 created\n\n"
        )

        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 0, err)

        code, _out, err = self.run_main("--check")
        self.assertEqual(code, 0, err)

    def test_genuine_legacy_footer_is_still_refused(self):
        index_path = self.backlog_dir / "Backlog-Index.md"
        index_path.write_text(
            "## Backlog Items\n\n"
            "| ID | Feature | Priority | Status | Abbrev | Created | Files |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 001 | Sample item | Medium | NOT_STARTED | BUG | 2026-01-01 "
            "| [file](001-Sample.md) |\n\n"
            "*Last Updated: 2026-01-01 — created*\n",
            encoding="utf-8",
        )

        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 2)
        self.assertIn("hand-authored", err)


if __name__ == "__main__":
    unittest.main()
