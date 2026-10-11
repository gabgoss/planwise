#!/usr/bin/env python3
"""Unit tests for parse_plans: the single read path for the plans index.

Three readers are pinned here:

  (a) Master Plan field readers: status normalization, Created anywhere in the
      file, and the Last Updated footer that is not always the last line.
  (b) The depth-bounded disk walk and its inverse.
  (c) The tolerant table parser: it reads past comments, accepts bare, bold,
      linked and escaped cells, counts rows before keying, and names a
      repeated Path.

Each guard has a producing test (the guard fires) and a non-producing test (it
stays silent), so a mutation that neuters the guard turns one of them red.
Every fixture is built under a temp dir. None reads the live plans tree.

Run with:  python -m pytest tests/test_parse_plans.py -q
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import parse_plans
from parse_plans import (
    detect_index_shape,
    enumerate_master_plans,
    master_plan_path_for,
    normalize_status,
    parse_index_table,
    read_master_plan_fields,
)

HEADER = "| Abbrev | Name | Status | Created | Last Updated | Path |"
SEPARATOR = "|--------|------|--------|---------|--------------|------|"

# The 20 Status cells that carry text after their leading token, verbatim from
# the measured legacy index, each with the token a reader must return.
NARRATIVE_STATUS_CELLS = [
    ('IN_PROGRESS — 2 of 7 sessions complete; Sprint 01 signed off PARTIAL (Tier-S spend 1.81× over ceiling, cost model to be re-priced)', 'IN_PROGRESS'),
    ('READY_TO_EXECUTE — Sprint-00 ExternalReference added (3 sessions, 10 tasks); 8 sessions total', 'READY_TO_EXECUTE'),
    ("CLOSED — superseded 2026-08-26. Sprint-01 COMPLETE (PASS); Sprint-02 Session-01 PARTIAL (21/31) and Session-02 INCONCLUSIVE (7/9 attempted, 17 never attempted) stand as historical record. BB-182's per-turn tool-use-overhead cost-model finding (Deliverable 1) is folded into TSO's Sprint-01 Part-4 BudgetsAndCalibration scope instead of a dedicated BPV re-cost; the 200-claim verification campaign itself (24 of Session-02's 26 designs, all of Sprints 03–05) is NOT carried forward and has no other home. See Master Plan Status field", 'CLOSED'),
    ('COMPLETE — 6 of 6 sprints; 16/16 change rows dispositioned, 0 skipped. 17 plugin files deferred-effect until the 1.0.5 release; re-measure closed as a data gap with a named owner', 'COMPLETE'),
    ('IN_PROGRESS — Discovery COMPLETE; 32 dispatch prompts ready in `BacklogRouteSweep/Prompts/`', 'IN_PROGRESS'),
    ('COMPLETE — all three sprints signed off PASS 2026-08-31', 'COMPLETE'),
    ('COMPLETE — all 3 sprints, signoffs PASS 5/5, 9/9, 5/5', 'COMPLETE'),
    ('COMPLETE — verdict ADOPT 2026-09-04 (136-run thorough campaign on Fable 5.1; C beats A 10/10, human net +7; guards ok); `.claude/rules/plain-language.md` installed live (941 tokens); all 4 sprints signed off (S04 PASS 6/6); follow-ups BB-194..BB-200', 'COMPLETE'),
    ('READY_TO_EXECUTE — awaiting `/planwise review` in its own session', 'READY_TO_EXECUTE'),
    ("IN_PROGRESS — Sprint-01 FullGridSweep: Session-01 HarnessPrep COMPLETE 2026-09-13 (harness partitioned by instrument, `--only` validated, `sweeps_v3.cmd` written, preflight `READY`, zero runs spent); Session-02 Sweep COMPLETE 2026-09-13 (CLI 2.1.270 so both verify gates re-ran and passed; 160/160 new rows `ok`, zero mismatches, every cell n=4, $45.37, 4 h 32 min over four launches — the Bash-tool launch was killed by Claude Code's memory guard on this 8 GB machine, so the sweep ran detached via WMI with the user-profile Scripts dir on PATH and a hidden console; `phase0-` ids now duplicated 2–3× in runs.csv by the verify re-run, baseline 634, four flags routed to Session-03); Session-03 ScoreAndCompare COMPLETE 2026-09-14 (audit C1–C7 PASS, every flag cell n_ok ≥ 4, `Harness/grid_aggregate.py` + 10 tests, suite 172 passed scope 0, `Results/ELL-Grid-Comparison.md` written, design §4/§11 updated, $0; decide: task-runner target `medium` — Sonnet `pooled_baseline_run` 6/32 low vs 19/28 medium vs 20/28 high, p = 0.0002 — and reviewer floor stays `high`, every review cell n=4; two flags routed to Session-04, one to the Master Plan); Session-04 AdjacentLadder COMPLETE 2026-09-14 (ladder in both scorers, `adjacent_ladder` + `population.phase0_occurrence_kept` in `grid_aggregate.py`, `## Adjacent ladder` on the comparison, §11 pointer; 11 new tests, suite 184 passed scope 0, $0; step on `pooled_baseline_run` at low–medium for both models, `pooled_pass` saturated, review ladder disagrees at medium–high; Session-03's Flag 2 needed an Option A scope expansion because it contradicted Task 2's key-equality gate). Sprint-01 COMPLETE; the plan now awaits the user's decision on `ELL-Recommendations-Plan.md` after reading the comparison and its ladder. The 524 first-sweep rows are void as effort evidence (all ran at `high`, ELL-Design.md §10); the grid sweep fills {sonnet, opus} × {low, medium, high, xhigh} through the `--effort` flag path and writes `Results/ELL-Grid-Comparison.md`. Session-04 AdjacentLadder added 2026-09-13 (4 sessions, 13 tasks, ~358K): the adjacent-level ladder as an aggregation change beside the fixed baselines, no CLI spend", 'IN_PROGRESS'),
    ('COMPLETE — memo recommends "do not adopt now" (the Python kit stays shipped, the POC folder stays a lab); winner `module-boundary` (RUN-06 PASS); `module-clear` PASS; `module-store` PASS as boundary; headless: `-p` no, stream-json no, `claude --bg` yes with the flag in the `--settings` overlay; README final, `DECISION-MEMO.md`, control lab `## Run 3`, commit `eed35a0`', 'COMPLETE'),
    ('READY_TO_EXECUTE — reviewed 2026-09-13 (NEEDS_FIXES as reviewed; all 15 findings fixed the same day)', 'READY_TO_EXECUTE'),
    ("COMPLETE (2026-09-17 — memo: Phase 2 promotes `compact` only, not `clear`, not by default, gated on the HMP memo's conditions 1–2, RUN-07 at the 240,000 floor, and two module fixes; BB-233 Phase-2 item, BB-234/235 filed; plan-wide `cli` cost 84.57 USD, D11 stands)", 'COMPLETE'),
    ('IN_PROGRESS (RBF-S01-01 COMPLETE 2026-09-16, latest run under `run_layer_stop: on` with four layer-edge stops and one compaction at the L1 boundary resumed from the Session Boundary Note, 10/10 outputs verified by column-sum gate after one Task 4 repair dispatch, git commit skipped for reset_fixture.py; awaiting reset_fixture.py double-run validation and RunBoundaryPOC arm dispatch)', 'IN_PROGRESS'),
    ('COMPLETE (all 3 sessions 2026-09-19; real run 2.1.277→2.1.278 filed 135 items BB-239..BB-373; D8 met by BB-239 via Route A, `18167bb2`; harvest bulk pass over the rest waits on BB-376)', 'COMPLETE'),
    ('COMPLETE (Sprint-02 Session 03 COMPLETE 2026-09-17 — `pins.py`/`--update-version-json` (BB-229), `offsets.py`/offset table (BB-230), `watch --live`/ceiling re-stated `0.05 -> 0.25` (BB-231), README/SKILL.md closeout, BB-227–231 archived, 101/5 tests; Session 02 COMPLETE 2026-09-17 — `probe.py`, `classic_subsets` (BB-227), tool-table names (BB-228), three snapshots re-captured, 91/5 tests; Session 01 COMPLETE 2026-09-17 — `consumer_plan.py` + `consumer-plan` subcommand + `watch --consumer-plan`. Sprint-02 planned 2026-09-16: `consumer_plan.py` + `watch --consumer-plan`, `wip/` probes promoted, BB-227–BB-231 — 3 sessions / 11 tasks / ~474K; Sprint 01 COMPLETE 2026-09-16, 8/8 criteria; baseline 2.1.272 → 2.1.273 `ed4788c`, 2.1.274 re-anchored `9aabbe25`)', 'COMPLETE'),
    ('COMPLETE — BHH-S01-01 executed 2026-09-23; plugin 8858c17; BB-384 COMPLETE', 'COMPLETE'),
    ('COMPLETE — S01-04 DocsAndEndToEnd COMPLETE 2026-09-26: manifest rows and docs (Tasks 1-2), e2e + real-corpus proof surfaced 7 defects (Task 3), fixed by ad-hoc Tasks 5-6 (defects A-E, D17 ambiguous-unit parking, D15 amendment); closeout: BB-393/379/380/238/381/382 COMPLETE with delivered_by BCR, BB-232 CLOSED as superseded, 4 Token Saver items filed (BB-406..409), index regenerated, BIR-S05 flag propagated. Release gate: v1.0.5.2 may now merge to main.', 'COMPLETE'),
    ('COMPLETE — BIM-S01-01 executed 2026-09-24 (facade + 7 siblings; G1-G5 PASS; E1-E4 byte-identical; BB-389 ACs met)', 'COMPLETE'),
    ('COMPLETE — body status line retired: writers stopped, `--body-status` pass wired into backlog Phase 1 and doctor Stage 19, 137 lines backfilled, BB-096 closed (follow-ups BB-386 to BB-391)', 'COMPLETE'),
]


def row(abbrev="ABC", name="Name", status="COMPLETE", created="2026-01-01", updated="2026-01-02", path="Name/"):
    return f"| {abbrev} | {name} | {status} | {created} | {updated} | {path} |"


def table(*rows, prefix=""):
    return prefix + "\n".join([HEADER, SEPARATOR, *rows]) + "\n"


class _TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="parse_plans_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str, newline=None) -> Path:
        target = self.tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)
        return target


class TestNormalizeStatus(unittest.TestCase):
    def test_status_shapes_reduce_to_the_leading_token(self):
        cases = [
            ("COMPLETE", "COMPLETE"),
            ("IN_PROGRESS — Discovery complete; awaiting user review", "IN_PROGRESS"),
            ("**COMPLETE** all sprints done", "COMPLETE"),
            ("✅ **COMPLETE (2026-08-12) — shipped", "COMPLETE"),
            ("COMPLETE. Sprint-01 done, Sprint-02 planned", "COMPLETE"),
            ("_IN_PROGRESS_", "IN_PROGRESS"),
            ("COMPLETE (2026-09-17 — memo)", "COMPLETE"),
            ("IN_PROGRESS -- awaiting user transfer", "IN_PROGRESS"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), expected)

    def test_ready_to_execute_keeps_its_underscores(self):
        self.assertEqual(normalize_status("READY_TO_EXECUTE"), "READY_TO_EXECUTE")
        self.assertEqual(normalize_status("READY_TO_EXECUTE — reviewed"), "READY_TO_EXECUTE")

    def test_trailing_underscore_is_dropped_from_the_run(self):
        self.assertEqual(normalize_status("COMPLETE_ notes"), "COMPLETE")

    def test_a_token_with_a_digit_keeps_its_underscores_and_digit(self):
        self.assertEqual(normalize_status("ON_HOLD2"), "ON_HOLD2")
        self.assertEqual(normalize_status("ON_HOLD2 — parked"), "ON_HOLD2")

    def test_a_run_ending_inside_a_word_never_truncates_to_a_shorter_token(self):
        for raw in ("ON_holdX", "ON_hold", "COMPLETEd", "ON_HOLD_x"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_status(raw))

    def test_a_value_with_no_token_returns_none(self):
        for raw in ("✅", "**✅**", "complete", "Complete", "", "2026-09-01", "   ", "---"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_status(raw))

    def test_none_input_returns_none(self):
        self.assertIsNone(normalize_status(None))

    def test_every_narrative_cell_returns_its_leading_token(self):
        self.assertEqual(len(NARRATIVE_STATUS_CELLS), 20)
        for cell, token in NARRATIVE_STATUS_CELLS:
            with self.subTest(cell=cell[:60]):
                self.assertEqual(normalize_status(cell), token)

    def test_every_narrative_cell_survives_the_table_parser(self):
        rows = []
        for i, (cell, _token) in enumerate(NARRATIVE_STATUS_CELLS):
            self.assertNotIn("|", cell)
            rows.append(row(abbrev=f"N{i:02d}", status=cell, path=f"Plan{i}/"))
        result = parse_index_table(table(*rows))
        self.assertEqual(len(result.rows), 20)
        self.assertEqual(result.unparsed, [])
        for parsed, (cell, token) in zip(result.rows, NARRATIVE_STATUS_CELLS):
            self.assertEqual(parsed.status_raw, cell)
            self.assertEqual(parsed.status_token, token)


class TestThreeFormCells(unittest.TestCase):
    def test_bare_bold_linked_and_escaped_pipe_rows_all_parse(self):
        content = table(
            row(abbrev="ABC", path="Abc/"),
            row(abbrev="**ABD**", path="Abd/"),
            row(abbrev="[ABE](ABE/ABE-Master-Plan.md)", path="Abe/"),
            row(abbrev="ABF", name="A \\| B", path="Abf/"),
        )
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["ABC", "ABD", "ABE", "ABF"])
        self.assertEqual(result.unparsed, [])
        self.assertEqual(result.rows[3].name, "A | B")

    def test_linked_bold_and_backticked_paths_unwrap(self):
        content = table(
            row(abbrev="AAA", path="[Plan/Meta-AAA/](Plan/Meta-AAA/)"),
            row(abbrev="BBB", path="**Plan/Exec-BBB/**"),
            row(abbrev="CCC", path="`Plan/CCC/`"),
            row(abbrev="`**[DDD](x.md)**`", path="**[`Plan/DDD/`](Plan/DDD/)**"),
        )
        result = parse_index_table(content)
        self.assertEqual([r.path for r in result.rows], ["Plan/Meta-AAA/", "Plan/Exec-BBB/", "Plan/CCC/", "Plan/DDD/"])
        self.assertEqual(result.rows[3].abbrev, "DDD")

    def test_a_missing_trailing_slash_is_added(self):
        result = parse_index_table(table(row(path="Plan/Exec-X")))
        self.assertEqual(result.rows[0].path, "Plan/Exec-X/")

    def test_a_plain_path_is_left_alone(self):
        result = parse_index_table(table(row(path="Plan/")))
        self.assertEqual(result.rows[0].path, "Plan/")

    def test_row_records_carry_every_field(self):
        result = parse_index_table(table(row(abbrev="XYZ", name="Xyz", status="✅ COMPLETE", created="2026-02-03", updated="2026-02-04", path="Xyz/")))
        parsed = result.rows[0]
        self.assertEqual(parsed.line_number, 3)
        self.assertEqual(parsed.abbrev, "XYZ")
        self.assertEqual(parsed.name, "Xyz")
        self.assertEqual(parsed.status_raw, "✅ COMPLETE")
        self.assertEqual(parsed.status_token, "COMPLETE")
        self.assertEqual(parsed.created, "2026-02-03")
        self.assertEqual(parsed.last_updated, "2026-02-04")
        self.assertEqual(parsed.path, "Xyz/")
        self.assertEqual(len(parsed.cells), 6)


# The line layout of the measured legacy index: a synthetic row at each row
# line, a one-line comment at each comment line, blanks elsewhere.
ROW_LINES = (
    list(range(5, 22))
    + [34, 37, 40, 42, 44, 46, 47, 49, 50, 51, 54, 55, 57, 60, 62, 64, 65, 66, 67, 70, 72, 74, 78, 79, 80, 82, 83, 85, 87, 88, 95, 97]
)
COMMENT_LINES = [
    22, 24, 25, 28, 30, 32, 35, 38, 41, 43, 45, 48, 52, 53, 56, 58, 59, 61, 63, 68, 69, 71, 73, 75, 76, 81, 84, 86,
    89, 90, 91, 93, 96, 98, 100, 102, 104, 106, 109,
]  # fmt: skip
LEGEND_HEADING_LINE = 113
DUPLICATE_ABBREV_LINES = {16: "PRV", 17: "PRV", 20: "PPB", 21: "PPB", 34: "EVS", 37: "EVS", 42: "BPV", 44: "BPV", 46: "NTD", 47: "NTD"}
DUPLICATE_FIRST_LINES = {16, 20, 34, 42, 46}


def build_legacy_index() -> str:
    """The comment-interleaved shape: 49 rows, 39 comments, then a legend."""
    lines = {1: "# Plans Index", 3: HEADER, 4: SEPARATOR}
    for line in ROW_LINES:
        abbrev = DUPLICATE_ABBREV_LINES.get(line, f"P{line:03d}")
        if line in DUPLICATE_ABBREV_LINES:
            kind = "Meta" if line in DUPLICATE_FIRST_LINES else "Exec"
            path = f"Plan{abbrev}/{kind}-{abbrev}/"
        else:
            path = f"Plan{line}/"
        lines[line] = row(abbrev=abbrev, name=f"Plan {line}", path=path)
    for line in COMMENT_LINES:
        lines[line] = f"<!-- comment at line {line}: Status was | COMPLETE | once -->"
    lines[LEGEND_HEADING_LINE] = "## Status Legend"
    lines[115] = "| Status | Meaning |"
    lines[116] = "|--------|---------|"
    for offset, status in enumerate(["NOT_STARTED", "PLANNING", "IN_PROGRESS", "BLOCKED", "COMPLETE", "CLOSED"]):
        lines[117 + offset] = f"| {status} | meaning of {status} |"
    return "\n".join(lines.get(n, "") for n in range(1, 123)) + "\n"


class TestRowsPastComments(unittest.TestCase):
    def test_layout_constants_match_the_measured_census(self):
        self.assertEqual(len(ROW_LINES), 49)
        self.assertEqual(len(COMMENT_LINES), 39)
        self.assertEqual(len(set(ROW_LINES) & set(COMMENT_LINES)), 0)

    def test_49_rows_are_read_past_39_comments(self):
        result = parse_index_table(build_legacy_index())
        self.assertEqual(len(result.rows), 49)
        self.assertEqual(len(result.table_lines), 49)
        comments = [s for s in result.skipped if s.kind == "comment"]
        self.assertEqual(len(comments), 39)
        self.assertEqual(result.unparsed, [])
        self.assertEqual(result.duplicates, [])

    def test_rows_keep_file_order_and_their_line_numbers(self):
        result = parse_index_table(build_legacy_index())
        self.assertEqual([r.line_number for r in result.rows], ROW_LINES)
        self.assertEqual([s.line_number for s in result.skipped if s.kind == "comment"], COMMENT_LINES)

    def test_no_legend_row_is_read_as_a_plan(self):
        result = parse_index_table(build_legacy_index())
        abbrevs = {r.abbrev for r in result.rows}
        for legend_status in ("NOT_STARTED", "PLANNING", "IN_PROGRESS", "BLOCKED", "COMPLETE", "CLOSED", "Status"):
            self.assertNotIn(legend_status, abbrevs)
        self.assertLess(max(r.line_number for r in result.rows), LEGEND_HEADING_LINE)

    def test_five_abbrev_pairs_share_an_abbrev_but_not_a_path(self):
        result = parse_index_table(build_legacy_index())
        abbrevs = [r.abbrev for r in result.rows]
        repeated = {a for a in abbrevs if abbrevs.count(a) > 1}
        self.assertEqual(repeated, {"PRV", "PPB", "EVS", "BPV", "NTD"})
        self.assertEqual(result.duplicates, [])

    def test_the_reader_does_not_stop_at_the_first_comment(self):
        content = table(row(abbrev="AAA", path="A/"), "<!-- a note -->", row(abbrev="BBB", path="B/"))
        self.assertEqual([r.abbrev for r in parse_index_table(content).rows], ["AAA", "BBB"])

    def test_crlf_content_reads_the_same_rows(self):
        lf = build_legacy_index()
        crlf = lf.replace("\n", "\r\n")
        self.assertEqual(
            [(r.line_number, r.abbrev, r.path) for r in parse_index_table(crlf).rows],
            [(r.line_number, r.abbrev, r.path) for r in parse_index_table(lf).rows],
        )

    def test_a_multi_line_comment_is_skipped_whole(self):
        content = table(
            row(abbrev="AAA", path="A/"),
            "<!-- first line",
            "| not | a | row | of | this | table |",
            "## not a heading",
            "last line -->",
            row(abbrev="BBB", path="B/"),
        )
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA", "BBB"])
        self.assertEqual([s.kind for s in result.skipped], ["comment"] * 4)
        self.assertEqual(result.unparsed, [])

    def test_an_unclosed_comment_opener_skips_only_its_own_line(self):
        content = table(
            row(abbrev="AAA", path="A/"),
            "<!-- never closed",
            row(abbrev="BBB", path="B/"),
            "stray prose",
            row(abbrev="CCC", path="C/"),
        )
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA", "BBB", "CCC"])
        self.assertEqual([(s.kind, s.text) for s in result.skipped],
                         [("comment", "<!-- never closed"), ("prose", "stray prose")])
        self.assertEqual(result.unparsed, [])

    def test_a_closed_comment_after_an_unclosed_opener_still_hides_its_lines(self):
        content = table(
            row(abbrev="AAA", path="A/"),
            "<!-- opens here",
            row(abbrev="BBB", path="B/"),
            "closes here -->",
            row(abbrev="CCC", path="C/"),
        )
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA", "CCC"])
        self.assertEqual([s.kind for s in result.skipped], ["comment"] * 3)

    def test_prose_and_blank_lines_are_recorded_and_skipped(self):
        content = table(row(abbrev="AAA", path="A/"), "", "stray prose", row(abbrev="BBB", path="B/"))
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA", "BBB"])
        self.assertEqual([s.kind for s in result.skipped], ["blank", "prose"])

    def test_the_region_ends_at_the_first_heading(self):
        content = table(row(abbrev="AAA", path="A/")) + "\n## Legend\n\n" + "| BBB | n | COMPLETE | 2026-01-01 | 2026-01-01 | B/ |\n"
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA"])

    def test_a_repeated_separator_row_is_skipped_not_unparsed(self):
        content = table(row(abbrev="AAA", path="A/"), SEPARATOR, row(abbrev="BBB", path="B/"))
        result = parse_index_table(content)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.unparsed, [])
        self.assertEqual([s.kind for s in result.skipped], ["separator"])
        self.assertEqual(len(result.table_lines), 2)

    def test_no_header_or_no_separator_gives_no_rows_and_no_header_line(self):
        for content in ("", "# Title\n\nno table here\n", HEADER + "\n" + row() + "\n"):
            with self.subTest(content=content[:20]):
                result = parse_index_table(content)
                self.assertEqual(result.rows, [])
                self.assertIsNone(result.header_line)

    def test_no_six_cell_line_gives_an_empty_count(self):
        for content in ("", "# Title\n\nno table here\n", HEADER + "\n"):
            with self.subTest(content=content[:20]):
                result = parse_index_table(content)
                self.assertEqual((result.table_lines, result.unparsed), ([], []))

    def test_header_line_is_reported_one_based(self):
        self.assertEqual(parse_index_table("# T\n\n" + table(row())).header_line, 3)


class TestDuplicatePath(unittest.TestCase):
    def test_a_repeated_path_keeps_both_rows_and_names_both_lines(self):
        content = table(
            row(abbrev="AAA", path="Shared/"),
            row(abbrev="BBB", path="Other/"),
            row(abbrev="CCC", path="Shared/"),
        )
        result = parse_index_table(content)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.duplicates, [("Shared/", (3, 5))])
        self.assertEqual([r.abbrev for r in result.rows if r.path == "Shared/"], ["AAA", "CCC"])

    def test_paths_that_differ_only_by_wrapper_still_collide(self):
        content = table(row(abbrev="AAA", path="Shared/"), row(abbrev="BBB", path="**Shared**"))
        self.assertEqual([d.path for d in parse_index_table(content).duplicates], ["Shared/"])

    def test_three_rows_on_one_path_report_all_three_lines(self):
        content = table(row(path="P/"), row(abbrev="B", path="P/"), row(abbrev="C", path="P/"))
        self.assertEqual(parse_index_table(content).duplicates, [("P/", (3, 4, 5))])

    def test_a_shared_abbrev_with_distinct_paths_is_not_a_duplicate(self):
        content = table(row(abbrev="PRV", path="Plan/Meta-PRV/"), row(abbrev="PRV", path="Plan/Exec-PRV/"))
        result = parse_index_table(content)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.duplicates, [])


class TestUnparsed(unittest.TestCase):
    def test_a_five_cell_row_is_named_with_its_line_and_count(self):
        content = table(row(abbrev="AAA", path="A/"), "| BBB | Name | COMPLETE | 2026-01-01 | B/ |")
        result = parse_index_table(content)
        self.assertEqual([r.abbrev for r in result.rows], ["AAA"])
        self.assertEqual(len(result.table_lines), 2)
        self.assertEqual(len(result.unparsed), 1)
        self.assertEqual(result.unparsed[0].line_number, 4)
        self.assertEqual(result.unparsed[0].reason, "cell-count 5")

    def test_a_seven_cell_row_is_named_too(self):
        result = parse_index_table(table("| A | B | C | D | E | F | G |"))
        self.assertEqual(result.unparsed[0].reason, "cell-count 7")

    def test_an_empty_abbrev_or_empty_path_is_unparsed(self):
        result = parse_index_table(table(row(abbrev="", path="A/"), row(abbrev="BBB", path="")))
        self.assertEqual([u.reason for u in result.unparsed], ["empty-abbrev", "empty-path"])
        self.assertEqual(result.rows, [])

    def test_six_cell_rows_leave_unparsed_empty(self):
        result = parse_index_table(table(row(abbrev="AAA", path="A/"), row(abbrev="BBB", path="B/")))
        self.assertEqual(result.unparsed, [])
        self.assertEqual(len(result.table_lines), len(result.rows))


class TestOutsideTheRegion(unittest.TestCase):
    """A six-cell line the region rule leaves outside is counted, never dropped."""

    LEGEND = "## Status Legend\n\n| Status | Meaning |\n|--------|---------|\n| COMPLETE | done |\n"

    def test_a_six_cell_line_after_a_heading_is_unparsed_and_counted(self):
        content = table(row(abbrev="AAA", path="A/")) + "\n## Notes\n\n" + row(abbrev="BBB", path="B/") + "\n\n" + self.LEGEND
        result = parse_index_table(content)
        lines = content.split("\n")
        after_heading = next(n for n, text in enumerate(lines, 1) if text.startswith("| BBB"))
        self.assertEqual([r.abbrev for r in result.rows], ["AAA"])
        self.assertEqual([(u.line_number, u.reason) for u in result.unparsed], [(after_heading, "outside-table-region")])
        self.assertIn(after_heading, [t.line_number for t in result.table_lines])
        self.assertEqual(len(result.table_lines), 2)

    def test_the_legend_two_cell_lines_are_not_counted(self):
        result = parse_index_table(table(row(abbrev="AAA", path="A/")) + "\n" + self.LEGEND)
        self.assertEqual(result.unparsed, [])
        self.assertEqual(len(result.table_lines), 1)

    def test_a_row_after_the_legend_is_unparsed_and_counted(self):
        content = table(row(abbrev="AAA", path="A/")) + "\n" + self.LEGEND + row(abbrev="ZZZ", path="Z/") + "\n"
        result = parse_index_table(content)
        self.assertEqual([(u.reason, u.text.split()[1]) for u in result.unparsed], [("outside-table-region", "ZZZ")])
        self.assertEqual([t.text.split()[1] for t in result.table_lines], ["AAA", "ZZZ"])

    def test_a_second_header_and_separator_after_a_heading_are_not_counted(self):
        content = table(row(abbrev="AAA", path="A/")) + "\n## Again\n\n" + HEADER + "\n" + SEPARATOR + "\n"
        result = parse_index_table(content)
        self.assertEqual(result.unparsed, [])
        self.assertEqual(len(result.table_lines), 1)

    def test_a_six_cell_line_above_the_header_is_unparsed_and_counted(self):
        content = row(abbrev="TOP", path="T/") + "\n" + table(row(abbrev="AAA", path="A/"))
        result = parse_index_table(content)
        self.assertEqual([(u.line_number, u.reason) for u in result.unparsed], [(1, "outside-table-region")])
        self.assertEqual([r.abbrev for r in result.rows], ["AAA"])

    def test_with_no_header_row_every_six_cell_line_counts(self):
        renamed = HEADER.replace("| Abbrev |", "| Abbr |")
        content = "\n".join([renamed, SEPARATOR, row(abbrev="AAA", path="A/")]) + "\n"
        result = parse_index_table(content)
        self.assertEqual(result.rows, [])
        self.assertIsNone(result.header_line)
        self.assertEqual([u.line_number for u in result.unparsed], [1, 3])
        self.assertEqual([t.line_number for t in result.table_lines], [1, 3])
        self.assertEqual({u.reason for u in result.unparsed}, {"outside-table-region"})


class TestMasterPlanFields(_TmpDirCase):
    def plan(self, body: str, name="X-Master-Plan.md", **kwargs) -> Path:
        return self.write(name, body, **kwargs)

    def test_status_fields_from_a_plain_plan(self):
        path = self.plan("# X\n\n**Status:** IN_PROGRESS — two sessions left\n**Created:** 2026-08-08\n")
        fields = read_master_plan_fields(path)
        self.assertEqual(fields.status_raw, "IN_PROGRESS — two sessions left")
        self.assertEqual(fields.status_token, "IN_PROGRESS")
        self.assertEqual(fields.created, "2026-08-08")
        self.assertEqual(fields.path, path)

    def test_a_decorated_status_line_normalizes(self):
        path = self.plan("**Status:** ✅ **COMPLETE (2026-08-12) — shipped\n")
        self.assertEqual(read_master_plan_fields(path).status_token, "COMPLETE")

    def test_a_file_without_a_status_line_gives_none_for_both(self):
        fields = read_master_plan_fields(self.plan("# X\n\nNo status here.\n"))
        self.assertIsNone(fields.status_raw)
        self.assertIsNone(fields.status_token)

    def test_an_empty_status_line_does_not_borrow_the_next_line(self):
        fields = read_master_plan_fields(self.plan("**Status:**\nCOMPLETE\n"))
        self.assertIsNone(fields.status_token)

    def test_created_at_line_45_is_read(self):
        body = "\n".join(["filler"] * 44) + "\n**Created:** 2026-08-08\n"
        self.assertEqual(body.split("\n").index("**Created:** 2026-08-08"), 44)
        self.assertEqual(read_master_plan_fields(self.plan(body)).created, "2026-08-08")

    def test_a_file_without_created_gives_none(self):
        self.assertIsNone(read_master_plan_fields(self.plan("**Status:** COMPLETE\n")).created)

    def test_last_updated_footer_on_line_188_of_190(self):
        lines = ["filler"] * 187 + ["*Last Updated: 2026-09-24 (closeout)*", "", "trailing note"]
        self.assertEqual(len(lines), 190)
        fields = read_master_plan_fields(self.plan("\n".join(lines) + "\n"))
        self.assertEqual(fields.last_updated, "2026-09-24")

    def test_the_footer_wins_over_a_header_date(self):
        body = "**Last Updated:** 2026-05-28\n\nbody\n\n*Last Updated: 2026-06-30 (final)*\n"
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-06-30")

    def test_the_header_date_is_used_when_there_is_no_footer(self):
        body = "**Last Updated:** 2026-05-28 (Session-02 COMPLETE)\n\nbody\n"
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-05-28")

    def test_a_footer_without_a_date_falls_back_to_the_header(self):
        body = "**Last Updated:** 2026-05-28\n\n*Last Updated: recently*\n"
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-05-28")

    def test_neither_form_gives_none(self):
        self.assertIsNone(read_master_plan_fields(self.plan("# X\n\nbody\n")).last_updated)

    def test_the_last_of_two_footers_wins(self):
        body = "*Last Updated: 2026-01-01*\n\nmore\n\n*Last Updated: 2026-02-02*\n"
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-02-02")

    def test_an_append_after_the_footer_does_not_move_the_date(self):
        body = (
            "**Status:** COMPLETE\n\nbody\n\n*Last Updated: 2026-09-20 (done)*\n\n"
            "## Index Notes (harvested 2026-09-28)\n\n"
            "> [!note] Historical notes moved from the plans index on 2026-09-28.\n\n"
            "<!-- an old note quoting *Last Updated: 2099-01-01* mid-line -->\n"
        )
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-09-20")

    def test_an_appended_line_that_starts_like_a_footer_does_move_the_date(self):
        # The anchor is the line start. This pins that the guard above is the
        # anchor and not a blanket "ignore anything after the first footer".
        body = "*Last Updated: 2026-09-20*\n\n*Last Updated: 2026-09-29 (again)*\n"
        self.assertEqual(read_master_plan_fields(self.plan(body)).last_updated, "2026-09-29")

    def test_a_bold_header_line_is_not_mistaken_for_a_footer(self):
        body = "**Last Updated:** 2026-05-28\n"
        self.assertEqual(parse_plans._FOOTER_LINE_RE.findall(body), [])

    def test_crlf_files_read_the_same_fields(self):
        body = "**Status:** COMPLETE\r\n**Created:** 2026-01-02\r\n\r\n*Last Updated: 2026-03-04*\r\n"
        fields = read_master_plan_fields(self.plan(body, newline=""))
        self.assertEqual(fields.status_raw, "COMPLETE")
        self.assertEqual(fields.created, "2026-01-02")
        self.assertEqual(fields.last_updated, "2026-03-04")


class TestEnumerateMasterPlans(_TmpDirCase):
    def touch(self, rel: str) -> Path:
        return self.write(rel, "**Status:** COMPLETE\n")

    def test_depth_one_and_a_meta_exec_pair_give_three_entries(self):
        self.touch("Alpha/ALP-Master-Plan.md")
        self.touch("Beta/Meta-BET/BET-META-Master-Plan.md")
        self.touch("Beta/Exec-BET/BET-Master-Plan.md")
        entries = enumerate_master_plans(self.tmp)
        self.assertEqual(
            [(e.path, e.abbrev, e.name) for e in entries],
            [
                ("Alpha/", "ALP", "Alpha"),
                ("Beta/Exec-BET/", "BET", "Beta (Exec)"),
                ("Beta/Meta-BET/", "BET", "Beta (Meta / Discovery)"),
            ],
        )
        self.assertEqual(entries[0].file, self.tmp / "Alpha" / "ALP-Master-Plan.md")

    def test_the_path_is_relative_posix_with_a_trailing_slash(self):
        self.touch("Beta/Meta-BET/BET-META-Master-Plan.md")
        (entry,) = enumerate_master_plans(self.tmp)
        self.assertEqual(entry.path, "Beta/Meta-BET/")
        self.assertNotIn(str(self.tmp), entry.path)
        self.assertNotIn("\\", entry.path)

    def test_a_plain_filename_inside_a_meta_folder_is_accepted(self):
        self.touch("Beta/Meta-BET/BET-Master-Plan.md")
        (entry,) = enumerate_master_plans(self.tmp)
        self.assertEqual((entry.abbrev, entry.name), ("BET", "Beta (Meta / Discovery)"))

    def test_the_depth_four_decoy_and_a_non_meta_exec_folder_are_ignored(self):
        self.touch("Plan/Harness/corpus/plantree/RVL-Master-Plan.md")
        self.touch("Plan/Harness/X-Master-Plan.md")
        self.touch("Plan/PLN-Master-Plan.md")
        entries = enumerate_master_plans(self.tmp)
        self.assertEqual([e.path for e in entries], ["Plan/"])

    def test_a_meta_filename_at_depth_one_is_not_a_plan(self):
        self.touch("Plan/PLN-META-Master-Plan.md")
        self.assertEqual(enumerate_master_plans(self.tmp), [])

    def test_a_plan_root_with_no_master_plan_gives_no_entry(self):
        self.touch("Plan/Notes.md")
        self.touch("Plan/Meta-PLN/Notes.md")
        self.assertEqual(enumerate_master_plans(self.tmp), [])

    def test_two_master_plans_in_one_directory_give_two_entries_with_one_path(self):
        self.touch("Plan/AAA-Master-Plan.md")
        self.touch("Plan/BBB-Master-Plan.md")
        entries = enumerate_master_plans(self.tmp)
        self.assertEqual([(e.path, e.abbrev) for e in entries], [("Plan/", "AAA"), ("Plan/", "BBB")])

    def test_one_master_plan_per_directory_gives_no_shared_path(self):
        self.touch("Plan/AAA-Master-Plan.md")
        self.touch("Other/BBB-Master-Plan.md")
        paths = [e.path for e in enumerate_master_plans(self.tmp)]
        self.assertEqual(len(paths), len(set(paths)))

    def test_entries_are_sorted_by_path(self):
        for rel in ("Zed/ZED-Master-Plan.md", "Alpha/ALP-Master-Plan.md", "Mid/Exec-MID/MID-Master-Plan.md"):
            self.touch(rel)
        paths = [e.path for e in enumerate_master_plans(self.tmp)]
        self.assertEqual(paths, sorted(paths))

    def test_a_missing_plans_dir_gives_an_empty_list(self):
        self.assertEqual(enumerate_master_plans(self.tmp / "nope"), [])

    def test_loose_files_in_the_plans_dir_are_ignored(self):
        self.touch("ROOT-Master-Plan.md")
        self.touch("00-Index-Plans.md")
        self.assertEqual(enumerate_master_plans(self.tmp), [])

    def test_master_plan_path_for_inverts_the_walk(self):
        self.touch("Alpha/ALP-Master-Plan.md")
        self.touch("Beta/Meta-BET/BET-META-Master-Plan.md")
        self.touch("Beta/Exec-BET/BET-Master-Plan.md")
        for entry in enumerate_master_plans(self.tmp):
            with self.subTest(path=entry.path):
                self.assertEqual(master_plan_path_for(self.tmp, entry.path, entry.abbrev), entry.file)

    def test_master_plan_path_for_names_the_meta_file_by_the_last_segment(self):
        self.assertEqual(
            master_plan_path_for(self.tmp, "Beta/Meta-BET/", "BET"),
            self.tmp / "Beta" / "Meta-BET" / "BET-META-Master-Plan.md",
        )
        self.assertEqual(
            master_plan_path_for(self.tmp, "Beta/Exec-BET", "BET"),
            self.tmp / "Beta" / "Exec-BET" / "BET-Master-Plan.md",
        )
        self.assertEqual(
            master_plan_path_for(self.tmp, "Alpha/", "ALP"),
            self.tmp / "Alpha" / "ALP-Master-Plan.md",
        )

    def test_a_meta_path_falls_back_to_a_plain_file_only_when_the_meta_file_is_absent(self):
        self.touch("Beta/Meta-BET/BET-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Beta/Meta-BET/", "BET"),
            self.tmp / "Beta" / "Meta-BET" / "BET-Master-Plan.md",
        )
        self.touch("Beta/Meta-BET/BET-META-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Beta/Meta-BET/", "BET"),
            self.tmp / "Beta" / "Meta-BET" / "BET-META-Master-Plan.md",
        )

    def test_an_exec_folder_holding_only_the_meta_filename_resolves_to_it(self):
        self.touch("Xplan/Exec-X/X-META-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Xplan/Exec-X/", "X"),
            self.tmp / "Xplan" / "Exec-X" / "X-META-Master-Plan.md",
        )

    def test_an_exec_folder_prefers_the_plain_filename_when_both_exist(self):
        self.touch("Xplan/Exec-X/X-Master-Plan.md")
        self.touch("Xplan/Exec-X/X-META-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Xplan/Exec-X/", "X"),
            self.tmp / "Xplan" / "Exec-X" / "X-Master-Plan.md",
        )

    def test_a_top_level_meta_folder_resolves_to_the_plain_filename_like_the_walk(self):
        self.touch("Meta-Foo/FOO-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Meta-Foo/", "FOO"),
            self.tmp / "Meta-Foo" / "FOO-Master-Plan.md",
        )
        self.touch("Meta-Foo/FOO-META-Master-Plan.md")
        self.assertEqual(
            master_plan_path_for(self.tmp, "Meta-Foo/", "FOO"),
            self.tmp / "Meta-Foo" / "FOO-Master-Plan.md",
        )
        self.assertEqual([e.file.name for e in enumerate_master_plans(self.tmp)], ["FOO-Master-Plan.md"])

    def test_a_top_level_meta_folder_with_no_file_names_the_plain_filename(self):
        self.assertEqual(
            master_plan_path_for(self.tmp, "Meta-Foo/", "FOO"),
            self.tmp / "Meta-Foo" / "FOO-Master-Plan.md",
        )

    def test_master_plan_path_for_inverts_the_walk_on_a_mixed_tree(self):
        for rel in (
            "Alpha/ALP-Master-Plan.md",
            "Beta/Meta-BET/BET-META-Master-Plan.md",
            "Beta/Exec-BET/BET-Master-Plan.md",
            "Xplan/Exec-X/X-META-Master-Plan.md",
            "Yplan/Meta-Y/Y-Master-Plan.md",
            "Meta-Foo/FOO-Master-Plan.md",
            "Meta-Foo2/FOO2-META-Master-Plan.md",
            "Meta-Foo2/FOO2-Master-Plan.md",
        ):
            self.touch(rel)
        entries = enumerate_master_plans(self.tmp)
        self.assertEqual(len(entries), 7)
        for entry in entries:
            with self.subTest(path=entry.path, file=entry.file.name):
                self.assertEqual(master_plan_path_for(self.tmp, entry.path, entry.abbrev), entry.file)

    def test_a_path_that_is_not_prefixed_by_the_plans_dir(self):
        result = master_plan_path_for(self.tmp, "Alpha/", "ALP")
        self.assertEqual(result.relative_to(self.tmp).as_posix(), "Alpha/ALP-Master-Plan.md")


class TestDetectIndexShape(unittest.TestCase):
    def test_generated_needs_the_generated_line_and_the_header(self):
        content = "# Plans Index\n\nGenerated: 2026-09-29\n\n" + table(row())
        self.assertEqual(detect_index_shape(content), "generated")

    def test_a_header_without_a_generated_line_is_legacy(self):
        self.assertEqual(detect_index_shape("# Plans Index\n\n" + table(row())), "legacy")

    def test_a_generated_line_without_the_header_is_empty(self):
        self.assertEqual(detect_index_shape("# Plans Index\n\nGenerated: 2026-09-29\n"), "empty")

    def test_empty_and_unrecognized_files_are_empty(self):
        for content in ("", "# Title\n\nprose\n", "| ID | Name |\n|---|---|\n"):
            with self.subTest(content=content[:20]):
                self.assertEqual(detect_index_shape(content), "empty")

    def test_a_generated_mention_mid_line_does_not_count(self):
        self.assertEqual(detect_index_shape("see Generated: elsewhere\n" + table(row())), "legacy")


if __name__ == "__main__":
    unittest.main()
