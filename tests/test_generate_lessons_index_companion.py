#!/usr/bin/env python3
"""Unit tests for generate_lessons_index.py's companion half (`--companion`):
bucket classification, ordering and counts, write idempotence and CRLF handling,
drift classes, the legacy-shape refusal, the over-budget warning, config
validation, the overwrite guard, and the shipped companion template.

The shared fixture base and the lesson-item builder live in
test_generate_lessons_index.py, which holds the scan and render half.

Run with:  python -m pytest tests/test_generate_lessons_index_companion.py -q
"""

import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import config_loader
import generate_lessons_index as gli
from test_generate_lessons_index import _GenerateLessonsIndexFixtureBase

# --------------------------------------------------------------------------
# Companion (--companion)
# --------------------------------------------------------------------------


class _CompanionFixtureBase(_GenerateLessonsIndexFixtureBase):
    """Extends the base fixture with a `categorization:` config block (four
    buckets A-D in decision-tree order, C carrying two sub-buckets C1/C2,
    D a `code_bucket`) and a raw-frontmatter lesson writer that can set
    `domain:`/`technology:`/`module:` beyond what `write_lesson`'s flat
    string params express."""

    def setUp(self):
        super().setUp()
        config_path = self.planwise_dir / "config.yaml"
        config_path.write_bytes(config_path.read_bytes() + (
            b"categorization:\n"
            b"  buckets:\n"
            b"  - id: A\n"
            b"    name: Database / SQL\n"
            b"    description: Bucket A description.\n"
            b"    triggers:\n"
            b"      technology: [sql]\n"
            b"  - id: B\n"
            b"    name: Application Code\n"
            b"    description: Bucket B description.\n"
            b"    triggers:\n"
            b"      domain: [APP]\n"
            b"  - id: C\n"
            b"    name: Planwise / Process\n"
            b"    description: Bucket C description.\n"
            b"    triggers:\n"
            b"      domain: [PROC]\n"
            b"    sub_buckets:\n"
            b"    - id: C1\n"
            b"      name: Sub One\n"
            b"      description: Sub one description.\n"
            b"      triggers:\n"
            b"        domain: [SUBONE]\n"
            b"    - id: C2\n"
            b"      name: Sub Two\n"
            b"      description: Sub two description.\n"
            b"      triggers:\n"
            b"        domain: [SUBTWO]\n"
            b"  - id: D\n"
            b"    name: Tooling / Ergonomics\n"
            b"    description: Bucket D description.\n"
            b"    code_bucket: true\n"
            b"    triggers:\n"
            b"      domain: [TOOL]\n"
            b"  decision_tree_order: [A, B, C, D]\n"
            b"  default_bucket: D\n"
            b"  edge_cases_section: true\n"
        ))
        self.config = config_loader.load_config()
        self.companion_path = self.lessons_dir / gli.COMPANION_FILENAME

    def write_domain_lesson(
        self, number: int, *, domain: list, technology: list | None = None,
        status: str = "documented", severity: str = "medium",
        title: str | None = None, module: str | None = None, directory=None,
        crlf: bool = False,
    ) -> Path:
        target_dir = directory if directory is not None else self.lessons_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        title = title or f"Fixture lesson {number}"
        tech = technology if technology is not None else ["claude-code"]
        lines = [
            "---",
            f"id: LL-{number:03d}",
            f"title: {title}",
            "category: process",
            f"severity: {severity}",
            "language: [python]",
            f"technology: [{', '.join(tech)}]",
            f"domain: [{', '.join(domain)}]",
            "source: fixture",
            f"status: {status}",
        ]
        if module is not None:
            lines.append(f"module: {module}")
        lines.append("---")
        lines.append("")
        lines.append(f"# LL-{number:03d}: {title}")
        text = "\n".join(lines) + "\n"
        if crlf:
            text = text.replace("\n", "\r\n")
        path = target_dir / f"LL-{number:03d}-Fixture{number}.md"
        path.write_bytes(text.encode("utf-8"))
        return path

    def run_companion(self, *args):
        return self.run_main("--companion", *args)


class TestCompanionClassification(_CompanionFixtureBase):
    """The curate §5.1 decision tree: first bucket in decision_tree_order
    whose triggers match, first sub-bucket within it, else the bucket's
    own parent table."""

    def test_decision_tree_order_lands_in_earlier_matching_bucket(self):
        # Matches A (technology: sql) and C (domain: PROC); A precedes C.
        self.write_domain_lesson(1, domain=["PROC"], technology=["sql"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        a_section = text.split("## B.")[0]
        c_section = text.split("## C.")[1].split("## D.")[0]
        self.assertIn("LL-001", a_section)
        self.assertNotIn("LL-001", c_section)

    def test_sub_bucket_first_match_wins(self):
        self.write_domain_lesson(1, domain=["PROC", "SUBONE", "SUBTWO"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        c1_section = text.split("### C1.")[1].split("### C2.")[0]
        c2_section = text.split("### C2.")[1].split("## D.")[0]
        self.assertIn("LL-001", c1_section)
        self.assertNotIn("LL-001", c2_section)

    def test_parent_fallback_with_no_sub_bucket_tag(self):
        self.write_domain_lesson(1, domain=["PROC"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        c_parent = text.split("## C.")[1].split("### C1.")[0]
        self.assertIn("LL-001", c_parent)

    def test_default_bucket_on_no_trigger_match(self):
        self.write_domain_lesson(1, domain=["MISC"], technology=["python"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        d_section = text.split("## D.")[1]
        self.assertIn("LL-001", d_section)


class TestCompanionBoldOnLanded(_CompanionFixtureBase):
    """Bold follows `status:` alone (D15), never directory."""

    def test_rule_and_applied_bold_others_plain(self):
        self.write_domain_lesson(1, domain=["PROC"], status="documented")
        self.write_domain_lesson(2, domain=["PROC"], status="promoted")
        self.write_domain_lesson(3, domain=["PROC"], status="applied")
        self.write_domain_lesson(4, domain=["PROC"], status="rule")
        self.write_domain_lesson(5, domain=["PROC"], status="orphaned")
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        self.assertIn("**LL-003**", text)
        self.assertIn("**LL-004**", text)
        self.assertNotIn("**LL-001**", text)
        self.assertNotIn("**LL-002**", text)
        self.assertNotIn("**LL-005**", text)
        self.assertIn("| LL-001 |", text)


class TestCompanionOrdering(_CompanionFixtureBase):
    def test_high_medium_low_then_ascending_id(self):
        self.write_domain_lesson(3, domain=["PROC"], severity="LOW")
        self.write_domain_lesson(1, domain=["PROC"], severity="HIGH")
        self.write_domain_lesson(4, domain=["PROC"], severity="MEDIUM")
        self.write_domain_lesson(2, domain=["PROC"], severity="HIGH")
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        c_parent = text.split("## C.")[1].split("### C1.")[0]
        ids_in_order = re.findall(r"LL-(\d+)", c_parent)
        self.assertEqual(ids_in_order, ["001", "002", "004", "003"])


class TestCompanionCounts(_CompanionFixtureBase):
    def test_counts_per_table_exclude_sub_buckets(self):
        self.write_domain_lesson(1, domain=["PROC", "SUBONE"])
        self.write_domain_lesson(2, domain=["PROC", "SUBONE"])
        self.write_domain_lesson(3, domain=["PROC", "SUBTWO"])
        self.write_domain_lesson(4, domain=["PROC"])
        self.write_domain_lesson(5, domain=["PROC"])
        self.write_domain_lesson(6, domain=["PROC"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        self.assertIn("## C. Planwise / Process (3)", text)
        self.assertIn("### C1. Sub One (2)", text)
        self.assertIn("### C2. Sub Two (1)", text)


class TestCompanionCodeBucket(_CompanionFixtureBase):
    def test_code_bucket_renders_four_columns_with_module(self):
        self.write_domain_lesson(1, domain=["TOOL"], module="config_loader.py")
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        self.assertIn("| ID | Title | Module | Severity |", text)
        self.assertIn("config_loader.py", text)

    def test_code_bucket_module_defaults_to_dash_when_absent(self):
        self.write_domain_lesson(2, domain=["TOOL"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        d_section = text.split("## D.")[1]
        row_line = next(line for line in d_section.split("\n") if "LL-002" in line)
        cells = gli.split_row_cells(row_line)
        self.assertEqual(cells[2], "-")


class TestCompanionZeroLessons(_CompanionFixtureBase):
    """The seed shape Task 4 needs: every bucket and sub-bucket heading at
    (0), each with an empty table -- no lesson files on disk at all."""

    def test_zero_lessons_render_every_heading_with_zero_and_empty_table(self):
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        text = self.companion_path.read_text(encoding="utf-8")
        for heading in (
            "## A. Database / SQL (0)", "## B. Application Code (0)",
            "## C. Planwise / Process (0)", "### C1. Sub One (0)",
            "### C2. Sub Two (0)", "## D. Tooling / Ergonomics (0)",
        ):
            self.assertIn(heading, text)
        self.assertNotIn("LL-", text.split("[Notes]")[0])


class TestCompanionWriteIdempotencyAndCRLF(_CompanionFixtureBase):
    def test_generated_date_alone_is_not_drift(self):
        self.write_domain_lesson(1, domain=["PROC"])
        self.run_companion("--write")
        text = self.companion_path.read_text(encoding="utf-8")
        mutated = re.sub(r"Generated: \d{4}-\d{2}-\d{2}", "Generated: 2000-01-01", text)
        self.assertNotEqual(mutated, text)
        self.companion_path.write_text(mutated, encoding="utf-8")

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 0)
        self.assertNotIn("Generated", out)

    def test_second_write_is_byte_identical(self):
        self.write_domain_lesson(1, domain=["PROC"])
        self.run_companion("--write")
        first = self.companion_path.read_bytes()

        code, _out, _err = self.run_companion("--write")

        self.assertEqual(code, 0)
        second = self.companion_path.read_bytes()
        strip_date = lambda b: re.sub(rb"Generated: \d{4}-\d{2}-\d{2}", b"Generated: DATE", b)
        self.assertEqual(strip_date(first), strip_date(second))

    def test_crlf_companion_stays_crlf_after_write(self):
        self.write_domain_lesson(1, domain=["PROC"])
        self.run_companion("--write")
        self.companion_path.write_bytes(self.companion_path.read_bytes().replace(b"\n", b"\r\n"))

        self.write_domain_lesson(2, domain=["PROC"])
        code, _out, _err = self.run_companion("--write")

        self.assertEqual(code, 0)
        content = self.companion_path.read_bytes()
        self.assertNotIn(b"\n", content.replace(b"\r\n", b""))

    def test_lf_companion_stays_lf_after_write(self):
        self.write_domain_lesson(1, domain=["PROC"])
        code, _out, _err = self.run_companion("--write")
        self.assertEqual(code, 0)
        self.assertNotIn(b"\r\n", self.companion_path.read_bytes())


class _CompanionDriftFixtureBase(_CompanionFixtureBase):
    """LL-001 (documented, HIGH) and LL-002 (rule, MEDIUM), both landing in
    C's parent table -- written once via --write."""

    def setUp(self):
        super().setUp()
        self.write_domain_lesson(1, domain=["PROC"], status="documented", severity="HIGH")
        self.write_domain_lesson(2, domain=["PROC"], status="rule", severity="MEDIUM")
        code, _out, _err = self.run_companion("--write")
        assert code == 0, "companion drift fixture setUp must --write cleanly"


class TestCompanionDriftClasses(_CompanionDriftFixtureBase):
    """Each Step 3 drift class, produced by one targeted mutation of the
    on-disk companion and shown clean beforehand -- a `--check` that
    cannot fail is decoration."""

    def test_missing_row_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("missing-row", out)

        self.write_domain_lesson(3, domain=["PROC"], status="documented")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[missing-row] LL-003", out)

    def test_stale_row_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("stale-row", out)

        text = self.companion_path.read_text(encoding="utf-8")
        mutated = text.replace("Fixture lesson 1", "Mutated Title")
        self.assertNotEqual(mutated, text)
        self.companion_path.write_text(mutated, encoding="utf-8")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[stale-row] LL-001", out)

    def test_orphan_row_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("orphan-row", out)

        text = self.companion_path.read_text(encoding="utf-8")
        anchor = "| **LL-002** | Fixture lesson 2 | MEDIUM |\n"
        self.assertIn(anchor, text)
        mutated = text.replace(anchor, anchor + "| LL-099 | Ghost | MEDIUM |\n")
        self.companion_path.write_text(mutated, encoding="utf-8")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[orphan-row] LL-099", out)

    def test_stale_count_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("stale-count", out)

        text = self.companion_path.read_text(encoding="utf-8")
        mutated = text.replace(
            "## C. Planwise / Process (2)", "## C. Planwise / Process (5)"
        )
        self.assertNotEqual(mutated, text)
        self.companion_path.write_text(mutated, encoding="utf-8")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("stale-count", out)

    def test_duplicate_row_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("duplicate-row", out)

        text = self.companion_path.read_text(encoding="utf-8")
        row_line = "| LL-001 | Fixture lesson 1 | HIGH |\n"
        self.assertIn(row_line, text)
        mutated = text.replace(row_line, row_line + row_line, 1)
        self.companion_path.write_text(mutated, encoding="utf-8")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[duplicate-row] LL-001", out)

    def test_legacy_shape_class(self):
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0)
        self.assertNotIn("legacy-shape", out)

        self.companion_path.write_text("**Last Updated:** 2026-01-01\n\n# Old\n", encoding="utf-8")
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("legacy-shape", out)


class TestCompanionWriteRefusesLegacyShape(_CompanionDriftFixtureBase):
    """The same --replace-legacy override D23 gives the index applies to
    the companion (Step 3)."""

    def test_write_refuses_legacy_shape_without_override(self):
        self.companion_path.write_text("**Last Updated:** 2026-01-01\n", encoding="utf-8")
        before = self.companion_path.read_bytes()

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("legacy", err.lower())
        self.assertEqual(self.companion_path.read_bytes(), before)

    def test_replace_legacy_overwrites_it(self):
        self.companion_path.write_text("**Last Updated:** 2026-01-01\n", encoding="utf-8")

        code, _out, _err = self.run_companion("--write", "--replace-legacy")

        self.assertEqual(code, 0)
        self.assertNotIn("Last Updated", self.companion_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Companion review fixes
# --------------------------------------------------------------------------


class _CompanionReviewFixtureBase(_CompanionFixtureBase):
    """Adds config mutation and the check -> write -> check round trip every
    review-fix regression asserts."""

    def mutate_config(self, old: bytes, new: bytes) -> None:
        config_path = self.planwise_dir / "config.yaml"
        before = config_path.read_bytes()
        self.assertIn(old, before)
        config_path.write_bytes(before.replace(old, new, 1))

    def mutate_companion(self, old: str, new: str) -> None:
        text = self.companion_path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.companion_path.write_bytes(text.replace(old, new, 1).encode("utf-8"))

    def assert_drift_then_heal(self, expected_class: str) -> str:
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 1, out)
        self.assertIn(f"[{expected_class}]", out)
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0, out)
        return out


class TestCompanionNoCategorizationBlockFallsBackToDefault(_CompanionReviewFixtureBase):
    """No `categorization:` block: the CLI renders from the same default the
    bootstrap seeds from, with one INFO line naming the block and --migrate."""

    def setUp(self):
        super().setUp()
        config_path = self.planwise_dir / "config.yaml"
        raw = config_path.read_bytes()
        config_path.write_bytes(raw[: raw.index(b"categorization:")])

    def test_check_and_write_exit_zero_with_info_line(self):
        self.write_domain_lesson(1, domain=["PROC"])

        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        self.assertIn("INFO:", err)
        self.assertIn("categorization:", err)
        self.assertIn("init_project.py --migrate", err)
        self.assertIn("## D. Tooling / Ergonomics (1)", self.companion_path.read_text(encoding="utf-8"))

        code, out, err = self.run_companion("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("INFO:", err)


class TestCompanionCheckIsByteExact(_CompanionReviewFixtureBase):
    """`--check` gates on the whole rendered file (Generated line masked), so
    a change no row-level class can see still fails the check, and --write
    heals it."""

    def setUp(self):
        super().setUp()
        self.write_domain_lesson(1, domain=["PROC"])
        self.write_domain_lesson(2, domain=["TOOL"], module="alpha.py")
        code, _out, err = self.run_companion("--write")
        assert code == 0, err
        code, out, _err = self.run_companion("--check")
        assert code == 0, out

    def test_module_change(self):
        self.write_domain_lesson(2, domain=["TOOL"], module="beta.py")
        out = self.assert_drift_then_heal("stale-row")
        self.assertNotIn("stale-shape", out)
        self.assertIn("beta.py", self.companion_path.read_text(encoding="utf-8"))

    def test_bucket_rename(self):
        self.mutate_config(b"name: Sub One", b"name: Sub Renamed")
        self.assert_drift_then_heal("stale-shape")
        self.assertIn("### C1. Sub Renamed (0)", self.companion_path.read_text(encoding="utf-8"))

    def test_bucket_description_change(self):
        self.mutate_config(b"description: Bucket B description.", b"description: Changed words.")
        self.assert_drift_then_heal("stale-shape")

    def test_code_bucket_toggle(self):
        self.mutate_config(b"    code_bucket: true\n", b"")
        self.assert_drift_then_heal("stale-row")
        self.assertNotIn("| ID | Title | Module | Severity |", self.companion_path.read_text(encoding="utf-8"))

    def test_code_bucket_toggle_on_an_empty_bucket(self):
        # Bucket B holds no rows, so only the table header row changes.
        self.mutate_config(
            b"    description: Bucket B description.\n",
            b"    description: Bucket B description.\n    code_bucket: true\n",
        )
        self.assert_drift_then_heal("stale-shape")

    def test_added_empty_bucket(self):
        self.mutate_config(
            b"  decision_tree_order:",
            b"  - id: E\n"
            b"    name: Extra\n"
            b"    description: Bucket E description.\n"
            b"    triggers:\n"
            b"      domain: [EXTRA]\n"
            b"  decision_tree_order:",
        )
        self.assert_drift_then_heal("stale-shape")
        self.assertIn("## E. Extra (0)", self.companion_path.read_text(encoding="utf-8"))

    def test_changed_footer(self):
        self.mutate_companion("[Notes](", "[Hand Notes](")
        out = self.assert_drift_then_heal("stale-shape")
        self.assertIn("No drift detected", out)

    def test_stale_shape_names_the_first_differing_line(self):
        self.mutate_config(b"description: Bucket B description.", b"description: Changed words.")
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 1)
        disk_lines = self.companion_path.read_text(encoding="utf-8").split("\n")
        expected_line = disk_lines.index("Bucket B description.") + 1
        self.assertIn(f"[stale-shape] line {expected_line}:", out)


class TestCompanionPipeTitleRoundTrips(_CompanionReviewFixtureBase):
    """A title carrying `|` is escaped on render; the row classifier reads
    both sides through the same parser, so a fresh write checks clean."""

    def test_pipe_title_check_clean_after_write(self):
        self.write_domain_lesson(1, domain=["PROC"], title="grep x | wc -l counts")
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        self.assertIn(r"grep x \| wc -l counts", self.companion_path.read_text(encoding="utf-8"))

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 0, out)

    def test_row_classifier_matches_escaped_title(self):
        self.write_domain_lesson(1, domain=["PROC"], title="a | b")
        items = gli.scan_lessons(self.lessons_dir, self.archive_dir, self.index_path, self.valid_statuses).items
        cat = gli._resolve_categorization(self.config)
        text = gli.render_companion_file(items, self.config, gli._index_naming(self.index_path))
        # Force the classifier to run (bytes differ only in the footer) and
        # confirm it names nothing on the escaped-title row itself.
        findings = gli._check_companion_drift(items, text.replace("[Notes]", "[N]"), cat, text)
        self.assertEqual([f["class"] for f in findings], ["stale-shape"])


class TestCompanionBucketIdForms(_CompanionReviewFixtureBase):
    """Int and hyphenated bucket ids round-trip; an id the heading cannot
    carry is rejected with the entry named."""

    def test_int_bucket_id_round_trips(self):
        self.mutate_config(b"  - id: A\n", b"  - id: 1\n")
        self.mutate_config(b"decision_tree_order: [A, B, C, D]", b"decision_tree_order: [1, B, C, D]")
        self.write_domain_lesson(1, domain=["MISC"], technology=["sql"])
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        self.assertIn("## 1. Database / SQL (1)", self.companion_path.read_text(encoding="utf-8"))

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 0, out)

    def test_hyphenated_bucket_id_round_trips(self):
        self.mutate_config(b"  - id: A\n", b"  - id: db-sql\n")
        self.mutate_config(b"decision_tree_order: [A, B, C, D]", b"decision_tree_order: [db-sql, B, C, D]")
        self.write_domain_lesson(1, domain=["MISC"], technology=["sql"])
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        self.assertIn("## db-sql. Database / SQL (1)", self.companion_path.read_text(encoding="utf-8"))

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 0, out)

    def test_bucket_name_with_a_dot_still_parses(self):
        self.mutate_config(b"name: Sub One", b"name: v1.2 Sub")
        self.write_domain_lesson(1, domain=["PROC", "SUBONE"])
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 0, out)

    def test_dotted_bucket_id_is_rejected(self):
        self.mutate_config(b"    - id: C1\n", b"    - id: C.1\n")

        code, _out, err = self.run_companion("--check")

        self.assertEqual(code, 2)
        self.assertIn("'C.1'", err)


class TestCompanionMalformedRow(_CompanionReviewFixtureBase):
    """A short row is `stale-row` (malformed), never an IndexError, and
    --write heals it."""

    def test_short_row_is_stale_row_and_write_heals(self):
        self.write_domain_lesson(4, domain=["PROC"])
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        self.mutate_companion("| LL-004 | Fixture lesson 4 | medium |", "| LL-004 |")

        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[stale-row] LL-004", out)
        self.assertIn("malformed", out)
        code, _out, err = self.run_companion("--write")
        self.assertEqual(code, 0, err)
        code, out, _err = self.run_companion("--check")
        self.assertEqual(code, 0, out)


class TestCompanionDuplicateIdRefusal(_CompanionReviewFixtureBase):
    """Two lesson FILES declaring one id: the companion --write refuses
    exactly as the index --write does, and --check reports it."""

    def setUp(self):
        super().setUp()
        self.write_domain_lesson(1, domain=["PROC"])
        self.write_domain_lesson(1, domain=["PROC"], directory=self.archive_dir)

    def test_index_and_companion_write_both_refuse(self):
        code, _out, err = self.run_main("--write")
        self.assertEqual(code, 2, err)

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("[duplicate-id] LL-001", err)
        self.assertFalse(self.companion_path.exists())

    def test_companion_check_reports_it(self):
        code, out, _err = self.run_companion("--check")

        self.assertEqual(code, 1)
        self.assertIn("[duplicate-id] LL-001", out)


class TestCompanionOverBudgetWriteWarns(_CompanionReviewFixtureBase):
    """A companion projecting over the read budget is written with a stderr
    warning. It is not a refusal: the warning names the tokens, the largest
    table and the read routes for the config's verified CLI version."""

    def setUp(self):
        super().setUp()
        config_path = self.planwise_dir / "config.yaml"
        config_path.write_bytes(config_path.read_bytes() + b'context:\n  verified_cli_version: "2.1.296"\n')
        self.config = config_loader.load_config()
        self.write_domain_lesson(1, domain=["PROC"])
        self.write_domain_lesson(2, domain=["SUBTWO"])
        self.write_domain_lesson(3, domain=["SUBTWO"])

    def test_write_over_budget_exits_0_writes_and_warns(self):
        with patch.object(gli, "READ_TOKEN_WARN", 10):
            code, out, err = self.run_companion("--write")

        self.assertEqual(code, 0, err)
        self.assertTrue(self.companion_path.exists())
        self.assertIn(f"Wrote {self.companion_path}", out)
        warning = [line for line in err.splitlines() if line.startswith("Warning:")]
        self.assertEqual(len(warning), 1, err)
        self.assertIn("tokens (budget 10)", warning[0])
        self.assertRegex(warning[0], r"largest table \w+ has 2 rows")
        self.assertIn("A plain Read still returns it whole.", warning[0])
        self.assertNotIn("allow_large", warning[0])
        self.assertNotIn("Refusing to write", err)

    def test_write_over_a_read_cap_names_the_routes(self):
        import read_limits
        with patch.object(gli, "READ_TOKEN_WARN", 10), patch.object(read_limits, "READ_PAGE_CAP_TOKENS", 10):
            code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 0, err)
        self.assertIn("allow_large", err)
        self.assertIn("Grep", err)

    def test_foreign_companion_refusal_prints_no_write_claim(self):
        self.companion_path.write_bytes(b"# Hand-written companion\n\nNotes kept by hand.\n")
        with patch.object(gli, "READ_TOKEN_WARN", 10):
            code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2, err)
        self.assertNotIn("It was written", err)
        self.assertNotIn("Warning:", err)

    def test_rolled_back_write_prints_no_write_claim(self):
        def boom(*_a, **_k):
            raise OSError("disk full")
        with patch.object(gli, "READ_TOKEN_WARN", 10), patch.object(gli, "_atomic_write_files", boom):
            code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2, err)
        self.assertNotIn("It was written", err)

    def test_json_stdout_stays_one_object_and_the_warning_stays_on_stderr(self):
        with patch.object(gli, "READ_TOKEN_WARN", 10):
            code, out, err = self.run_companion("--write", "--json")

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["written"], [str(self.companion_path)])
        self.assertIn("Warning:", err)

    def test_under_budget_write_prints_no_warning(self):
        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 0, err)
        self.assertNotIn("Warning:", err)

    def test_an_anomaly_still_refuses_over_budget(self):
        self.write_domain_lesson(1, domain=["PROC"], directory=self.archive_dir)
        with patch.object(gli, "READ_TOKEN_WARN", 10):
            code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("Refusing to write", err)
        self.assertFalse(self.companion_path.exists())


class TestCompanionCategorizationErrorIsNotATraceback(_CompanionReviewFixtureBase):
    def test_unresolved_default_bucket_exits_two(self):
        self.mutate_config(b"default_bucket: D", b"default_bucket: E")
        self.write_domain_lesson(1, domain=["MISC"], technology=["python"])

        code, _out, err = self.run_companion("--check")

        self.assertEqual(code, 2)
        self.assertIn("Error:", err)
        self.assertIn("'E'", err)
        self.assertNotIn("Traceback", err)

    def test_json_mode_emits_an_error_object(self):
        self.mutate_config(b"default_bucket: D", b"default_bucket: E")

        code, out, _err = self.run_companion("--check", "--json")

        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(out))

    def test_render_time_categorization_error_is_caught(self):
        self.write_domain_lesson(1, domain=["PROC"])
        with patch.object(gli, "render_companion_file", side_effect=gli.CategorizationError("render failed")):
            code, out, err = self.run_companion("--write", "--json")

        self.assertEqual(code, 2)
        self.assertIn("Error: render failed", err)
        self.assertEqual(json.loads(out), {"error": "render failed"})
        self.assertFalse(self.companion_path.exists())


class TestCompanionConfigValidation(_CompanionReviewFixtureBase):
    def test_bucket_missing_id_exits_two_naming_it(self):
        self.mutate_config(b"  - id: B\n", b"  - slug: code\n")

        code, _out, err = self.run_companion("--check")

        self.assertEqual(code, 2)
        self.assertIn("buckets[1]", err)
        self.assertIn("has no id", err)

    def test_sub_bucket_missing_id_exits_two(self):
        self.mutate_config(b"    - id: C2\n", b"    - slug: two\n")

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("sub_buckets[1]", err)

    def test_duplicate_id_across_levels_exits_two(self):
        self.mutate_config(b"    - id: C2\n", b"    - id: A\n")

        code, _out, err = self.run_companion("--check")

        self.assertEqual(code, 2)
        self.assertIn("'A' is declared by both", err)

    def test_unresolved_decision_tree_entry_exits_two(self):
        self.mutate_config(b"decision_tree_order: [A, B, C, D]", b"decision_tree_order: [A, B, C, Z]")

        code, _out, err = self.run_companion("--check")

        self.assertEqual(code, 2)
        self.assertIn("'Z'", err)


class TestCompanionOverwriteGuard(_CompanionReviewFixtureBase):
    """Only a generated-shaped companion is overwritten without
    --replace-legacy; --replace-legacy names every heading it drops."""

    def test_hand_written_file_without_legacy_markers_is_refused(self):
        self.companion_path.write_bytes(b"# My categorization\n\n## Things\n\nProse.\n")
        before = self.companion_path.read_bytes()

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("not generated-shaped", err)
        self.assertIn("--replace-legacy", err)
        self.assertEqual(self.companion_path.read_bytes(), before)

    def test_refusal_names_upgrade_before_the_flag_and_warns_of_no_backup(self):
        self.companion_path.write_bytes(b"# My categorization\n\n## Things\n\nProse.\n")

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        # The drop listing above the refusal also names the flag, so read the
        # order inside the refusal line itself.
        refusal = next(line for line in err.splitlines() if line.startswith("Error:"))
        upgrade_at = refusal.find("/planwise upgrade")
        flag_at = refusal.find("--replace-legacy")
        self.assertNotEqual(upgrade_at, -1)
        self.assertNotEqual(flag_at, -1)
        self.assertLess(upgrade_at, flag_at)
        self.assertIn("notes file", refusal)
        self.assertIn("backs up every file it rewrites", refusal)
        self.assertIn("keeps no backup", refusal[flag_at:])
        self.assertNotIn("re-run with --replace-legacy", refusal)

    def test_generated_line_alone_is_not_generated_shaped(self):
        self.companion_path.write_bytes(b"# Mine\n\nGenerated: 2026-01-01\n\n---\n\nBody.\n")

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2, err)

    def test_empty_file_is_overwritten(self):
        self.companion_path.write_bytes(b"")

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 0, err)

    def test_replace_legacy_prints_dropped_headings_fence_aware(self):
        self.companion_path.write_bytes(
            b"# Lessons Learned\n\n**Last Updated:** 2026-01-01\n\n"
            b"## C. Planwise / Process (2)\n\n| ID | Title | Severity |\n|---|---|---|\n\n"
            b"## Cross-cutting observations\n\n```\n## Fenced sample\n```\n\n"
            b"### Edge detail\n\n## Classification edge cases\n"
        )

        code, _out, err = self.run_companion("--write", "--replace-legacy")

        self.assertEqual(code, 0, err)
        self.assertIn("dropping: ## Cross-cutting observations", err)
        self.assertIn("dropping: ### Edge detail", err)
        self.assertIn("dropping: ## Classification edge cases", err)
        self.assertNotIn("Fenced sample", err)
        self.assertNotIn("dropping: ## C.", err)

    def test_refusal_lists_what_replace_legacy_would_drop(self):
        self.companion_path.write_bytes(b"**Last Updated:** 2026-01-01\n\n## Old section\n")

        code, _out, err = self.run_companion("--write")

        self.assertEqual(code, 2)
        self.assertIn("## Old section", err)


class TestCompanionScopeSentence(unittest.TestCase):
    naming = gli._index_naming(Path("00-Index-LessonsLearned.md"))

    def test_fallback_without_project_name(self):
        text = gli.render_companion_file([], {"categorization": gli.DEFAULT_CATEGORIZATION}, self.naming)
        self.assertIn("Lessons captured during this project's sessions.\n", text)

    def test_named_project(self):
        config = {"categorization": gli.DEFAULT_CATEGORIZATION, "project": {"name": "Acme"}}
        text = gli.render_companion_file([], config, self.naming)
        self.assertIn("Lessons captured during Acme sessions.\n", text)


class TestCompanionStatusNote(unittest.TestCase):
    naming = gli._index_naming(Path("00-Index-LessonsLearned.md"))

    def test_zero_lesson_render_carries_status_note(self):
        text = gli.render_companion_file([], {"categorization": gli.DEFAULT_CATEGORIZATION}, self.naming)
        for phrase in ("every lesson of every status", "no live owner", "resurfaces ahead of"):
            self.assertIn(phrase, text)

    def test_orphaned_lesson_is_listed_unbolded_in_its_domain_bucket(self):
        item = {
            "id": 5, "title": "x", "severity": "MEDIUM", "status": "orphaned",
            "domain": [], "technology": [],
        }
        text = gli.render_companion_file([item], {"categorization": gli.DEFAULT_CATEGORIZATION}, self.naming)
        self.assertIn("| LL-005 |", text.split("## D.")[1])
        self.assertNotIn("**LL-005**", text)


class TestShippedCompanionTemplateMatchesRender(unittest.TestCase):
    """`templates/categorization-by-domain.md` is the generator's own
    zero-lesson output for the ship-default config, below its leading
    HTML comment. Any renderer change must regenerate it."""

    def test_template_body_equals_zero_lesson_render(self):
        template = (
            Path(__file__).resolve().parent.parent / "plugins" / "planwise"
            / "templates" / "categorization-by-domain.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(template.startswith("<!--"))
        body = template.split("-->\n\n", 1)[1]
        rendered = gli.render_companion_file(
            [], {"categorization": gli.DEFAULT_CATEGORIZATION},
            gli._index_naming(Path("00-Index-LessonsLearned.md")),
        )
        self.assertEqual(gli._mask_generated(body), gli._mask_generated(rendered))


if __name__ == "__main__":
    unittest.main()
