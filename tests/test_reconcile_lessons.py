#!/usr/bin/env python3
"""Unit tests for lessons-index "Next available ID" counter drift.

The counter is a denormalized cache of one fact — the highest lesson ID that
exists anywhere — written only by capture mode. Any lesson authored off that
path (a hand-written closeout capture, a task-runner deliverable) leaves it
stale, and the next capture reads a value below the true max and reuses an ID.

`reconcile_lessons.compute_next_id(config)` derives the true next ID from the
union of three sources: the working lessons directory, `Archive/`, and the index
Master Table. `detect_drift(config)` reports a counter BEHIND that value as
drift and reports four conditions as anomalies (missing counter line, counter
AHEAD of the true value, a Master-Table row whose file is gone, a lesson file
with no Master-Table row). `reconcile(config)` re-reads the index fresh and
bumps a still-stale counter, rewriting nothing else.

These tests pin: the live stale-counter reproduction and its heal; a correct
counter producing no false drift; each of the three sources contributing to the
max independently (including a lesson present only in `Archive/`, and a
Master-Table row that outlived its file — whose ID must still not be reused); a
fresh project's counter legitimately resting at LL-001; race-safety (reconcile
re-reads and will not re-bump a counter a concurrent capture already advanced);
the never-move-backwards guarantee; Master-Table section scoping (a lesson ID in
the Rule Promotion Log is not a lesson row); bolded row IDs still counting; and
CRLF line-ending preservation on the destructive write.

Each test builds an isolated temp planwise tree (config.yaml + lessons index +
lesson files); none read or mutate the live project's lessons.

Run with:  python -m pytest tests/test_reconcile_lessons.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader  # noqa: E402
from reconcile_lessons import (  # noqa: E402
    compute_next_id,
    detect_drift,
    reconcile,
)


CONFIG_YAML_FIXTURE = """project:
  name: "LessonsReconcileFixtureProject"
  lessons_dir: "LessonsLearned"
  index_files:
    lessons: "00-Index-LessonsLearned.md"
"""

MASTER_TABLE_HEADER = (
    "| ID | Title | Category | Severity | Language | Technology | Domain | Source | Status |\n"
    "|----|-------|----------|----------|----------|------------|--------|--------|--------|\n"
)

# A Rule Promotion Log row carries a lesson ID in its SECOND cell and lives in a
# different section. It must never be read as a Master-Table entry — LL-999 here
# would otherwise drive every fixture's next ID to LL-1000.
PROMOTION_LOG = (
    "\n---\n\n## Rule Promotion Log\n\n"
    "| Date | Lesson ID | Artifact Created | File |\n"
    "|------|-----------|-----------------|------|\n"
    "| 2026-01-01 | LL-999 | fixture-artifact | references/fixture.md |\n"
)


class _LessonsFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree: config.yaml + lessons index +
    lesson files, so compute_next_id/detect_drift/reconcile run against a
    hermetic copy instead of the live project's lessons index.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reconcile_lessons_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.lessons_dir = self.planwise_dir / "LessonsLearned"
        self.archive_dir = self.lessons_dir / "Archive"
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.lessons_dir / "00-Index-LessonsLearned.md"

        (self.planwise_dir / "config.yaml").write_text(
            CONFIG_YAML_FIXTURE, encoding="utf-8"
        )

        # load_config() reads --config from sys.argv; inject it for the test.
        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))
        sys.argv = [
            "test_reconcile_lessons",
            "--config",
            str(self.planwise_dir / "config.yaml"),
        ]
        self.config = config_loader.load_config()

    def index_text(self, counter: str | None, row_ids, bold_ids=()) -> str:
        """Render an index with the given counter and Master-Table row IDs.

        `counter=None` omits the counter line entirely (an index predating the
        convention). `bold_ids` renders those IDs as `**LL-NNN**`.
        """
        counter_block = f"**Next available ID:** {counter}\n\n" if counter else ""
        rows = ""
        for n in row_ids:
            label = f"**LL-{n:03d}**" if n in bold_ids else f"LL-{n:03d}"
            rows += f"| {label} | Fixture lesson {n} | process | medium | - | - | PROC | fixture | documented |\n"
        return (
            "# Lessons Learned Index\n\n"
            "**Purpose:** Fixture index.\n\n"
            "---\n\n"
            "## Naming Convention\n\n"
            f"{counter_block}"
            "---\n\n"
            "## Master Table\n\n"
            f"{MASTER_TABLE_HEADER}{rows}"
            f"{PROMOTION_LOG}"
        )

    def write_index(self, counter, row_ids, bold_ids=()) -> Path:
        self.index_path.write_text(
            self.index_text(counter, row_ids, bold_ids), encoding="utf-8"
        )
        return self.index_path

    def write_lesson(self, number: int, archived: bool = False) -> Path:
        """Create a lesson file in the working dir or under Archive/."""
        target_dir = self.archive_dir if archived else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"LL-{number:03d}-PROC-Fixture{number}.md"
        path.write_text(
            f"---\nid: LL-{number:03d}\nstatus: documented\n---\n\n"
            f"# LL-{number:03d}-PROC: Fixture lesson {number}\n",
            encoding="utf-8",
        )
        return path

    def read_index(self) -> str:
        return self.index_path.read_text(encoding="utf-8")

    def stated_counter(self) -> str:
        for line in self.read_index().splitlines():
            if "Next available ID:" in line:
                return line.split("LL-")[1].strip().rstrip("*")
        return ""


class TestComputeNextId(_LessonsFixtureBase):
    """The union-of-three-sources derivation behind every other operation."""

    def test_empty_project_next_is_001(self):
        # Fresh project: no lesson files, no master rows. The seed index's
        # starting LL-001 is correct, not drifted.
        self.write_index("LL-001", [])

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-001")
        self.assertIsNone(result["max_found"])

    def test_archive_only_lesson_counts(self):
        # A lesson archived at capture is absent from the working directory.
        # Reading only the working dir would compute LL-002 and reuse LL-002.
        self.write_index("LL-003", [1, 2])
        self.write_lesson(1)
        self.write_lesson(2, archived=True)

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-003")
        self.assertEqual(result["max_found"], 2)
        self.assertIn("Archive/", result["found_in"])

    def test_master_row_without_file_still_counts(self):
        # A master-table row can outlive a deleted file. Its ID must still bound
        # the counter — a retired ID is not free for reuse.
        self.write_index("LL-006", [1, 5])
        self.write_lesson(1)

        result = compute_next_id(self.config)

        self.assertEqual(result["next_id"], "LL-006")
        self.assertEqual(result["found_in"], ["master table"])

    def test_promotion_log_row_is_not_a_lesson_row(self):
        # LL-999 appears in the Rule Promotion Log (second cell, different
        # section). Section scoping must keep it out of the max.
        self.write_index("LL-002", [1])
        self.write_lesson(1)

        self.assertEqual(compute_next_id(self.config)["next_id"], "LL-002")

    def test_bolded_master_row_id_counts(self):
        # An index that bolds applied/rule lessons must not make those rows
        # invisible to the scan.
        self.write_index("LL-008", [7], bold_ids={7})
        self.write_lesson(7)

        self.assertEqual(compute_next_id(self.config)["next_id"], "LL-008")

    def test_next_id_ignores_the_stated_counter(self):
        # The whole point: the true next ID is derived, never read from the
        # cache line it exists to correct.
        self.write_index("LL-002", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)

        self.assertEqual(compute_next_id(self.config)["next_id"], "LL-004")


class TestDetectDrift(_LessonsFixtureBase):
    """Read-only drift + anomaly classification."""

    def test_stale_counter_detected(self):
        # Reproduction of the live case: the counter read LL-002 while LL-003
        # already existed on disk and in the master table.
        self.write_index("LL-002", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)

        result = detect_drift(self.config)

        self.assertEqual(result["anomalies"], [])
        self.assertEqual(len(result["drifts"]), 1)
        drift = result["drifts"][0]
        self.assertEqual(drift["field"], "next_available_id")
        self.assertEqual(drift["stated"], "LL-002")
        self.assertEqual(drift["expected"], "LL-004")
        self.assertEqual(drift["max_found"], "LL-003")

    def test_correct_counter_no_false_drift(self):
        # The repaired state must read clean — no drift AND no anomalies.
        self.write_index("LL-004", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])
        self.assertEqual(result["next_id"], "LL-004")

    def test_empty_lessons_dir_no_drift(self):
        self.write_index("LL-001", [])

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(result["anomalies"], [])

    def test_archive_only_lesson_drives_drift(self):
        self.write_index("LL-002", [1, 2])
        self.write_lesson(1)
        self.write_lesson(2, archived=True)

        drifts = detect_drift(self.config)["drifts"]

        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0]["expected"], "LL-003")

    def test_master_row_without_file_is_anomaly(self):
        # The row bounds the counter (so no drift at LL-006) but the missing
        # file is surfaced for a human — never fabricated.
        self.write_index("LL-006", [1, 5])
        self.write_lesson(1)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        anomaly = result["anomalies"][0]
        self.assertEqual(anomaly["kind"], "row_without_file")
        self.assertEqual(anomaly["id"], "LL-005")

    def test_file_without_master_row_is_anomaly(self):
        # The other direction: a hand-authored lesson whose master-table row was
        # never added. Surfaced with its filename, never fabricated into a row.
        self.write_index("LL-003", [1])
        self.write_lesson(1)
        self.write_lesson(2)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        anomalies = [a for a in result["anomalies"] if a["kind"] == "file_without_row"]
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["id"], "LL-002")
        self.assertEqual(anomalies[0]["file"], "LL-002-PROC-Fixture2.md")

    def test_counter_ahead_is_anomaly_not_drift(self):
        # Ahead of the true max is not a collision risk and may reflect a
        # deliberately retired ID — anomaly, never drift.
        self.write_index("LL-020", [1, 2])
        for n in (1, 2):
            self.write_lesson(n)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["kind"], "counter_ahead")
        self.assertEqual(result["anomalies"][0]["id"], "LL-020")

    def test_missing_counter_line_is_anomaly(self):
        self.write_index(None, [1])
        self.write_lesson(1)

        result = detect_drift(self.config)

        self.assertEqual(result["drifts"], [])
        self.assertEqual(len(result["anomalies"]), 1)
        self.assertEqual(result["anomalies"][0]["kind"], "missing_counter_line")
        self.assertEqual(result["next_id"], "LL-002")


class TestReconcile(_LessonsFixtureBase):
    """The consent-gated write path."""

    def test_reconcile_bumps_stale_counter_and_touches_nothing_else(self):
        self.write_index("LL-002", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)

        outcome = reconcile(self.config)

        self.assertTrue(outcome["written"])
        self.assertEqual(outcome["from"], "LL-002")
        self.assertEqual(outcome["to"], "LL-004")
        # Only the counter value changed — the rest of the index is identical.
        self.assertEqual(self.read_index(), self.index_text("LL-004", [1, 2, 3]))
        # And the heal is complete.
        self.assertEqual(detect_drift(self.config)["drifts"], [])

    def test_reconcile_noop_when_counter_current(self):
        self.write_index("LL-004", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)
        before = self.read_index()

        outcome = reconcile(self.config)

        self.assertFalse(outcome["written"])
        self.assertEqual(self.read_index(), before)

    def test_reconcile_never_lowers_a_counter_ahead(self):
        self.write_index("LL-020", [1, 2])
        for n in (1, 2):
            self.write_lesson(n)
        before = self.read_index()

        outcome = reconcile(self.config)

        self.assertFalse(outcome["written"])
        self.assertEqual(self.read_index(), before)
        self.assertEqual(self.stated_counter(), "020")

    def test_reconcile_re_reads_and_skips_a_concurrently_healed_counter(self):
        # Race safety: a counter detect found stale may already have been bumped
        # by a concurrent capture. reconcile must re-read and leave it alone
        # rather than write a value computed before that capture landed.
        self.write_index("LL-002", [1, 2, 3])
        for n in (1, 2, 3):
            self.write_lesson(n)

        pre = detect_drift(self.config)
        self.assertEqual(len(pre["drifts"]), 1)

        # Simulate a concurrent capture: LL-004 written, row added, counter bumped.
        self.write_lesson(4)
        self.write_index("LL-005", [1, 2, 3, 4])
        before = self.read_index()

        outcome = reconcile(self.config)

        self.assertFalse(outcome["written"])
        self.assertEqual(self.read_index(), before)

    def test_reconcile_does_not_write_without_a_counter_line(self):
        self.write_index(None, [1])
        self.write_lesson(1)
        before = self.read_index()

        outcome = reconcile(self.config)

        self.assertFalse(outcome["written"])
        self.assertEqual(self.read_index(), before)

    def test_reconcile_preserves_crlf_line_endings(self):
        # The destructive write must preserve the file's original line endings.
        crlf = self.index_text("LL-002", [1, 2, 3]).replace("\n", "\r\n")
        with open(self.index_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(crlf)
        for n in (1, 2, 3):
            self.write_lesson(n)

        outcome = reconcile(self.config)
        self.assertTrue(outcome["written"])

        raw = self.index_path.read_bytes()
        self.assertIn(b"\r\n", raw)
        # No bare LF introduced: every LF must be part of a CRLF pair.
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        self.assertEqual(self.stated_counter(), "004")


if __name__ == "__main__":
    unittest.main()
