#!/usr/bin/env python3
"""Unit tests for backlog archival drift detection and reconciliation.

`reconcile_backlog.detect_drift(config)` reads item files, never an index.
It checks each item file's frontmatter `status:` against the file's location.
A COMPLETE/CLOSED item file outside `Archive/` is drift. An open item inside
`Archive/`, a file with no readable status, two files carrying one id, and a
closed item whose filename already exists in `Archive/` are anomalies, which
are reported and never acted on.

`reconcile_backlog.reconcile(config)` re-scans the item files and moves each
still-drifted file into `Archive/`. It never edits or writes any index file.

These tests pin detection on a generated hub that carries no closed rows (the
case the old index-reading audit could not see), the move on `--write`, a
byte-identical index after `--write`, every anomaly kind left unmoved, a clean
tree exiting 0, race safety, and a failed move reported and not counted.

Each test builds an isolated temp planwise tree (config.yaml + item files +
an optional index); none read or mutate the live project's backlog.

Run with:  python -m pytest tests/test_reconcile_backlog.py -q
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_backlog_index
import reconcile_backlog
from reconcile_backlog import detect_drift, reconcile

CONFIG_YAML_FIXTURE = """project:
  name: "BacklogReconcileFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

# A generated hub: no H1 heading, and only open items render here. Closed
# items render into Archive shards, never the hub.
GENERATED_HUB = (
    "| ID | Title | Priority | Status | Abbrev | Score | File |\n"
    "|----|-------|----------|--------|--------|-------|------|\n"
    "| 048 | In flight | Medium | IN_PROGRESS | INFRA | 25 | [open-INFRA-item.md](open-INFRA-item.md) |\n"
)


class _BacklogFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree so detect_drift/reconcile run
    against a hermetic copy instead of the live project's backlog.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_backlog_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.backlog_dir / "00-Index-Backlog.md"

        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML_FIXTURE, encoding="utf-8"
        )

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_reconcile_backlog",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()
        self.write_index(GENERATED_HUB)

    def write_index(self, text: str) -> Path:
        self.index_path.write_text(text, encoding="utf-8")
        return self.index_path

    def write_item(
        self, filename: str, item_id: str, status: str, archived: bool = False
    ) -> Path:
        """Create an item file in the backlog dir or under Archive/."""
        target_dir = self.archive_dir if archived else self.backlog_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / filename
        path.write_text(
            f"---\nid: {item_id}\nstatus: {status}\n---\n\n# {filename}\n",
            encoding="utf-8",
        )
        return path

    def run_reconcile_quietly(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            moved = reconcile(self.config)
        return moved, out.getvalue()


class TestDetectFromItemFiles(_BacklogFixtureBase):
    """detect_drift reads item-file status and location, never the hub."""

    def test_detect_on_generated_hub_without_closed_rows(self):
        # The exact case the old audit could not see: the hub is generated,
        # heading-less, and carries no closed row at all.
        self.write_item("open-INFRA-item.md", "048", "IN_PROGRESS")
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")
        self.assertNotIn("COMPLETE", self.index_path.read_text(encoding="utf-8"))

        result = detect_drift(self.config)

        # The displayed id is the frontmatter's own stored text, un-normalized
        # -- the same zero-padded convention the generator/--next-id use
        # everywhere else. normalize_id governs duplicate-comparison only.
        self.assertEqual([d["id"] for d in result["drifts"]], ["046"])
        self.assertEqual(result["drifts"][0]["file"], "stranded-INFRA-item.md")
        self.assertTrue(result["drifts"][0]["needs_move"])
        self.assertEqual(result["anomalies"], [])

    def test_detect_ignores_hub_content_entirely(self):
        # An empty hub changes nothing: detection comes from the item files.
        self.write_index("")
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")

        self.assertEqual(len(detect_drift(self.config)["drifts"]), 1)

    def test_closed_status_is_also_drift(self):
        self.write_item("closed-PROC-item.md", "060", "CLOSED")

        drifts = detect_drift(self.config)["drifts"]

        self.assertEqual([d["status"] for d in drifts], ["CLOSED"])

    def test_open_item_in_backlog_dir_is_clean(self):
        self.write_item("open-INFRA-item.md", "048", "IN_PROGRESS")

        self.assertEqual(detect_drift(self.config), {"drifts": [], "anomalies": []})

    def test_closed_item_already_archived_is_clean(self):
        self.write_item("archived-DOC-item.md", "045", "COMPLETE", archived=True)

        self.assertEqual(detect_drift(self.config), {"drifts": [], "anomalies": []})

    def test_generated_index_files_are_not_items(self):
        # The hub, a 00- file, and a generated Archive shard carry no item
        # frontmatter. None of them may surface as an unreadable item.
        naming = generate_backlog_index._index_naming(self.index_path)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shard = generate_backlog_index._shard_filename(naming, 1, 10)
        (self.archive_dir / shard).write_text("| ID |\n|----|\n", encoding="utf-8")
        (self.backlog_dir / "00-Changelog.md").write_text("# Log\n", encoding="utf-8")

        self.assertEqual(detect_drift(self.config), {"drifts": [], "anomalies": []})


class TestAnomaliesNeverActedOn(_BacklogFixtureBase):
    """Every anomaly is reported, never drift, and never moved by --write."""

    def test_open_item_in_archive_is_anomaly_and_not_moved(self):
        path = self.write_item("reopened-BUG-item.md", "070", "IN_PROGRESS", archived=True)

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        # Displayed id is the raw stored text, un-normalized -- see above.
        self.assertEqual([a["id"] for a in result["anomalies"]], ["070"])
        self.assertIn("open item", result["anomalies"][0]["reason"])

        moved, _ = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertTrue(path.exists())
        self.assertFalse((self.backlog_dir / "reopened-BUG-item.md").exists())

    def test_unreadable_status_is_anomaly_and_not_moved(self):
        no_fm = self.backlog_dir / "no-frontmatter-item.md"
        no_fm.write_text("# No frontmatter\n", encoding="utf-8")
        no_status = self.backlog_dir / "no-status-item.md"
        no_status.write_text("---\nid: 081\n---\n\n# x\n", encoding="utf-8")

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        self.assertEqual(
            sorted(a["file"] for a in result["anomalies"]),
            ["no-frontmatter-item.md", "no-status-item.md"],
        )

        moved, _ = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertTrue(no_fm.exists())
        self.assertTrue(no_status.exists())

    def test_duplicate_id_is_anomaly_and_neither_moved(self):
        a = self.write_item("first-copy-item.md", "090", "COMPLETE")
        b = self.write_item("second-copy-item.md", "090", "COMPLETE")

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 2)

        moved, _ = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertTrue(a.exists())
        self.assertTrue(b.exists())

    def test_prefixed_and_bare_forms_of_one_id_are_treated_as_a_duplicate(self):
        # _read_item's COMPARISON key now normalizes through the SAME
        # normalize_id-based rule update_backlog.py's own disk lookups use --
        # "PFX-005" and "005" must collide as one id for duplicate detection,
        # even though each file's DISPLAYED id stays its own raw frontmatter
        # text (never normalized for display).
        a = self.write_item("bare-form-item.md", "005", "COMPLETE")
        b = self.write_item("prefixed-form-item.md", "PFX-005", "COMPLETE")

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 2)
        self.assertEqual(
            sorted(a["id"] for a in result["anomalies"]), ["005", "PFX-005"]
        )
        for anomaly in result["anomalies"]:
            self.assertIn("id also carried by", anomaly["reason"])

        moved, _ = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertTrue(a.exists())
        self.assertTrue(b.exists())

    def test_name_collision_in_archive_is_anomaly_and_not_overwritten(self):
        top = self.write_item("same-name-item.md", "091", "COMPLETE")
        archived = self.write_item("same-name-item.md", "092", "COMPLETE", archived=True)
        archived_before = archived.read_bytes()

        result = detect_drift(self.config)
        self.assertEqual(result["drifts"], [])
        # Displayed id is the raw stored text, un-normalized -- see above.
        self.assertEqual([a["id"] for a in result["anomalies"]], ["091"])

        moved, _ = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertTrue(top.exists())
        self.assertEqual(archived.read_bytes(), archived_before)


class TestReconcileMovesFilesOnly(_BacklogFixtureBase):
    """--write moves item files into Archive/ and writes no index."""

    def test_write_moves_closed_item_into_archive(self):
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")

        moved, out = self.run_reconcile_quietly()

        self.assertEqual(moved, 1)
        self.assertFalse((self.backlog_dir / "stranded-INFRA-item.md").exists())
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(detect_drift(self.config)["drifts"], [])
        self.assertIn("generate_backlog_index.py", out)
        self.assertIn("--write", out)

    def test_index_is_byte_identical_after_write(self):
        # A legacy CRLF index whose row still links the stranded file at its
        # old location. The old audit rewrote this link. The new one must
        # leave every byte of the index alone.
        legacy = (
            b"# Backlog Index\r\n\r\n"
            b"| ID  | Feature | Priority | Status | Abbrev | Score | Files |\r\n"
            b"|-----|---------|----------|--------|--------|-------|-------|\r\n"
            b"| 046 | Drift | Medium | COMPLETE | INFRA | - | [01](stranded-INFRA-item.md) |\r\n"
        )
        self.index_path.write_bytes(legacy)
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")

        moved, _ = self.run_reconcile_quietly()

        self.assertEqual(moved, 1)
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())
        self.assertEqual(self.index_path.read_bytes(), legacy)

    def test_module_carries_no_index_writer(self):
        self.assertFalse(hasattr(reconcile_backlog, "update_index_links_to_archive"))
        self.assertFalse(hasattr(reconcile_backlog, "write_text_preserving_newlines"))

    def test_reconcile_only_still_drifted(self):
        # Race safety: a concurrent writer moves the file between detect and
        # reconcile. reconcile re-scans and does nothing.
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")
        self.assertEqual(len(detect_drift(self.config)["drifts"]), 1)

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(
            str(self.backlog_dir / "stranded-INFRA-item.md"),
            str(self.archive_dir / "stranded-INFRA-item.md"),
        )

        moved, out = self.run_reconcile_quietly()
        self.assertEqual(moved, 0)
        self.assertEqual(out, "")
        self.assertTrue((self.archive_dir / "stranded-INFRA-item.md").exists())

    def test_failed_move_is_reported_and_not_counted(self):
        self.write_item("moves-fine-INFRA-item.md", "071", "COMPLETE")
        self.write_item("fails-to-move-INFRA-item.md", "072", "COMPLETE")

        real_archive_item_files = reconcile_backlog.archive_item_files

        def fake_archive_item_files(backlog_dir, archive_dir, filenames):
            results = []
            for filename in filenames:
                if filename == "fails-to-move-INFRA-item.md":
                    results.append((filename, False, "simulated move failure"))
                else:
                    results.extend(
                        real_archive_item_files(backlog_dir, archive_dir, [filename])
                    )
            return results

        with patch(
            "reconcile_backlog.archive_item_files", side_effect=fake_archive_item_files
        ):
            moved, out = self.run_reconcile_quietly()

        self.assertEqual(moved, 1)
        self.assertTrue((self.archive_dir / "moves-fine-INFRA-item.md").exists())
        self.assertTrue((self.backlog_dir / "fails-to-move-INFRA-item.md").exists())
        self.assertIn("! fails-to-move-INFRA-item.md: simulated move failure", out)


class TestCli(_BacklogFixtureBase):
    """The shared reconcile_common CLI shape and exit codes are unchanged."""

    def run_main(self, *extra: str) -> str:
        sys.argv = [
            "reconcile_backlog.py",
            "--config",
            str(self.planwise_dir / "config.yaml"),
            *extra,
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reconcile_backlog.main()  # returning normally is exit 0
        return out.getvalue()

    def test_clean_tree_exits_zero(self):
        self.write_item("open-INFRA-item.md", "048", "IN_PROGRESS")
        self.write_item("archived-DOC-item.md", "045", "COMPLETE", archived=True)

        out = self.run_main()

        self.assertIn("No archival drift detected", out)

    def test_detect_run_never_moves(self):
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")

        out = self.run_main()

        self.assertIn("stranded-INFRA-item.md", out)
        self.assertTrue((self.backlog_dir / "stranded-INFRA-item.md").exists())

    def test_write_prints_moved_file_count(self):
        self.write_item("stranded-INFRA-item.md", "046", "COMPLETE")

        out = self.run_main("--write")

        self.assertIn("Moved 1 file(s) to Archive/.", out)
        self.assertNotIn("row(s)", out)

    def test_missing_index_still_exits_one(self):
        self.index_path.unlink()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            self.run_main()
        self.assertEqual(ctx.exception.code, 1)

    def test_write_exits_nonzero_when_a_move_fails(self):
        # run_reconcile_cli itself returns normally (implicit exit 0)
        # whether or not reconcile()'s consented moves all succeeded --
        # main() must fail the command for a failed move on its own.
        self.write_item("fails-to-move-INFRA-item.md", "073", "COMPLETE")

        def fake_archive_item_files(backlog_dir, archive_dir, filenames):
            return [(f, False, "simulated move failure") for f in filenames]

        err = io.StringIO()
        with patch(
            "reconcile_backlog.archive_item_files", side_effect=fake_archive_item_files
        ):
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                self.run_main("--write")

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("fails-to-move-INFRA-item.md", err.getvalue())
        self.assertIn("simulated move failure", err.getvalue())
        # A failed consented move must leave the file exactly where it was.
        self.assertTrue((self.backlog_dir / "fails-to-move-INFRA-item.md").exists())

    def test_detect_mode_after_a_failed_write_does_not_inherit_stale_failures(self):
        # _last_reconcile_failures is module-level state; a later detect-mode
        # call (which never calls reconcile() at all) must not fail because
        # an EARLIER --write call in the same process recorded a failure.
        self.write_item("fails-to-move-INFRA-item.md", "074", "COMPLETE")

        def fake_archive_item_files(backlog_dir, archive_dir, filenames):
            return [(f, False, "simulated move failure") for f in filenames]

        with patch(
            "reconcile_backlog.archive_item_files", side_effect=fake_archive_item_files
        ):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_main("--write")

        out = self.run_main()  # detect mode, no --write -- must not raise

        self.assertIn("Archival drift detected", out)


if __name__ == "__main__":
    unittest.main()
