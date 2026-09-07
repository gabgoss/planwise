#!/usr/bin/env python3
"""Unit tests for the Step 8c Token Saver large-file scan (token_saver_scan.py).

The scan walks a plan's task files, resolves each Required Context row to a
real path, classifies it against the task's assigned model via
`read_limits.classify_file`, and exits non-zero when any file lands Warn or
worse. These tests pin the behaviours that were silently absent before the
driver existed — a hand-written `PAGED` annotation and a computed one used to
be indistinguishable — plus the parsing hazards a naive walker gets wrong.

Run with:  python -m pytest tests/test_token_saver_scan.py
"""

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import token_saver  # noqa: E402
import token_saver_scan as tss  # noqa: E402

# The current template's column set and the one earlier plans emit. A parser
# that reads by POSITION passes on one and silently reads the wrong cell on the
# other, so both appear in the tests.
TEMPLATE_COLUMNS = "| Priority | File | KiB | ~Tokens | Purpose |"
LEGACY_COLUMNS = "| Priority | File | Est. Lines | Est. Tokens | Purpose |"


def _task(columns: str, rows: str, agent: str = "Sonnet") -> str:
    return (
        f"# Task: {agent}-Probe\n\n"
        f"**Task ID:** XX-S01-01-01\n"
        f"**Agent:** {agent}\n"
        f"**Estimated Tokens:** ~10K\n\n"
        "---\n\n"
        "## Required Context <!-- REQUIRED -->\n\n"
        f"{columns}\n"
        "|----------|------|----:|--------:|---------|\n"
        f"{rows}\n\n"
        "---\n\n"
        "## Execution Steps\n\n1. Do the thing.\n"
    )


class TestParsing(unittest.TestCase):
    """Header/table parsing, including the two live column layouts."""

    def test_parse_agent(self):
        self.assertEqual(tss.parse_agent("**Agent:** Sonnet\n"), "sonnet")
        self.assertEqual(tss.parse_agent("**Agent:** Opus\n"), "opus")
        # A qualifier after the model name must not leak into the key.
        self.assertEqual(tss.parse_agent("**Agent:** Opus (1M)\n"), "opus")
        self.assertIsNone(tss.parse_agent("no agent field here\n"))

    def test_parse_required_context_both_column_layouts(self):
        rows = "| 1 | `a/b.md` | 10 | ~4K | why it is needed |"
        for columns in (TEMPLATE_COLUMNS, LEGACY_COLUMNS):
            parsed = tss.parse_required_context(_task(columns, rows))
            self.assertEqual(len(parsed), 1, columns)
            # The File cell, not the KiB / Est. Lines cell that sits beside it.
            self.assertEqual(parsed[0]["file_cell"], "`a/b.md`", columns)
            self.assertEqual(parsed[0]["purpose"], "why it is needed", columns)

    def test_parse_required_context_stops_at_next_section(self):
        text = _task(TEMPLATE_COLUMNS, "| 1 | `a/b.md` | 10 | ~4K | why |")
        text += "\n## Another Table\n\n| Priority | File |\n|---|---|\n| 1 | `z.md` |\n"
        parsed = tss.parse_required_context(text)
        self.assertEqual([r["file_cell"] for r in parsed], ["`a/b.md`"])

    def test_clean_file_cell_strips_decoration_and_span(self):
        self.assertEqual(tss._clean_file_cell("`a/b.md`"), "a/b.md")
        self.assertEqual(tss._clean_file_cell("**`a/b.md`**"), "a/b.md")
        # A span row cites `path §X–§Y (...)`; the path ends at the section mark.
        self.assertEqual(
            tss._clean_file_cell("`a/b.md` §3–§7 (§7 runs to EOF)"), "a/b.md"
        )

    def test_command_corpus_rows_are_not_paths(self):
        self.assertTrue(tss.is_command_corpus("Grep family over scope"))
        self.assertTrue(tss.is_command_corpus("`python parse_backlog.py --all`"))
        self.assertFalse(tss.is_command_corpus("`planwise/config.yaml`"))


class TestClassificationHelpers(unittest.TestCase):
    """Content class, annotations, and the recommendation ladder."""

    def test_doc_gets_no_content_class_so_the_ratio_stays_conservative(self):
        label, content = tss.content_class_for(Path("x/index.md"))
        self.assertEqual(label, "doc")
        # None -> bytes_per_token falls back to the family's smallest ratio.
        # Guessing "prose" on a dense table index under-estimates its tokens.
        self.assertIsNone(content)
        self.assertEqual(tss.content_class_for(Path("x/a.py")), ("code", "code"))
        self.assertEqual(
            tss.content_class_for(Path("x/a.json")), ("dense", "dense-md")
        )

    def test_annotations_are_computed_not_written(self):
        over_tokens = {"tokens": 30_000, "bytes": 1_000}
        self.assertEqual(
            tss.annotations_for(over_tokens, "sonnet"),
            ["⚠ PAGED ≥25K sonnet-tok"],
        )
        over_bytes = {"tokens": 100, "bytes": 300 * 1024}
        self.assertIn("⚠ REFACTOR ≥256 KiB",
                      tss.annotations_for(over_bytes, "opus"))
        self.assertEqual(tss.annotations_for({"tokens": 10, "bytes": 10}, "opus"), [])

    def test_read_critical_never_recommends_1m_exception(self):
        read_critical = {"level": "Critical", "reason": "read"}
        text = tss.recommend(read_critical, "doc")
        self.assertIn("paged read", text)
        self.assertIn("Do NOT flag 1M-exception", text)

    def test_cost_critical_is_the_only_1m_exception(self):
        cost_critical = {"level": "Critical", "reason": "cost"}
        self.assertIn("1M-exception", tss.recommend(cost_critical, "doc"))
        warn = {"level": "Warn", "reason": "read"}
        self.assertIn("backlog item", tss.recommend(warn, "code"))
        notice = {"level": "Notice", "reason": "cost"}
        self.assertIn("no backlog item", tss.recommend(notice, "doc"))

    def test_remedy_differentiates_by_file_type(self):
        warn = {"level": "Warn", "reason": "read"}
        self.assertIn("refactor into smaller modules", tss.recommend(warn, "code"))
        self.assertIn("Multi-Part split", tss.recommend(warn, "doc"))
        self.assertIn("extract only the needed", tss.recommend(warn, "dense"))


class TestGrouping(unittest.TestCase):
    def test_worst_verdict_wins_and_tasks_aggregate(self):
        findings = [
            {"path": "p", "level": "Warn", "reason": "read", "tokens": 22_500,
             "task": "t1", "model": "haiku"},
            {"path": "p", "level": "Critical", "reason": "read", "tokens": 30_000,
             "task": "t2", "model": "opus"},
        ]
        grouped = tss.group_findings(findings)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["level"], "Critical")
        self.assertEqual(grouped[0]["model"], "opus")
        self.assertEqual(sorted(grouped[0]["tasks"]), ["t1", "t2"])


class TestPlanScan(unittest.TestCase):
    """End-to-end scan over a synthetic plan tree."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tss_plan_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = self.tmp
        self.plan = self.tmp / "Plans" / "Probe"
        (self.plan / "Session-01").mkdir(parents=True)
        self.config = {
            "context": {
                "token_saver": True,
                "token_saver_session_target": 150_000,
                "token_saver_runner_overhead": 1_000,
            }
        }

    def _write_context_file(self, name: str, n_bytes: int) -> str:
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 60 + b"\n" * 1 + b"y" * (max(0, n_bytes - 61)))
        return name

    def _write_task(self, name: str, rows: str, agent: str = "Sonnet"):
        (self.plan / "Session-01" / name).write_text(
            _task(TEMPLATE_COLUMNS, rows, agent), encoding="utf-8"
        )

    def test_small_plan_is_all_green(self):
        self._write_context_file("docs/small.md", 2_000)
        self._write_task("T-01.md", "| 1 | `docs/small.md` | 2 | ~1K | why |")
        result = tss.scan_plan(self.plan, self.config, self.project)
        self.assertEqual(result["summary"]["critical"], 0)
        self.assertEqual(result["summary"]["warn"], 0)
        self.assertEqual(result["summary"]["green"], 1)
        self.assertEqual(result["findings"], [])

    def test_oversized_file_is_read_critical_and_named(self):
        # 100 KB of markdown: ~38.5K tokens at the conservative 2.6 B/tok ratio,
        # past the 25,000-token page cap, so read-reason Critical.
        self._write_context_file("docs/big.md", 100_000)
        self._write_task("T-01.md", "| 1 | `docs/big.md` | 98 | ~38K | why |")
        result = tss.scan_plan(self.plan, self.config, self.project)
        self.assertEqual(result["summary"]["critical"], 1)
        finding = result["findings"][0]
        self.assertEqual(finding["level"], "Critical")
        self.assertEqual(finding["reason"], "read")
        self.assertIn("Do NOT flag 1M-exception", finding["recommendation"])
        self.assertTrue(any("PAGED" in a for a in finding["annotations"]))

    def test_token_saver_off_makes_the_scan_a_no_op(self):
        self._write_context_file("docs/big.md", 100_000)
        self._write_task("T-01.md", "| 1 | `docs/big.md` | 98 | ~38K | why |")
        off = {"context": dict(self.config["context"], token_saver=False)}
        result = tss.scan_plan(self.plan, off, self.project)
        self.assertFalse(result["token_saver_effective"])
        self.assertEqual(result["summary"]["files"], 0)
        self.assertIsNone(result["thresholds"])

    def test_master_plan_off_override_beats_project_on(self):
        (self.plan / "P-Master-Plan.md").write_text(
            "# Plan\n\n**Token Saver:** off\n", encoding="utf-8"
        )
        self._write_context_file("docs/big.md", 100_000)
        self._write_task("T-01.md", "| 1 | `docs/big.md` | 98 | ~38K | why |")
        result = tss.scan_plan(self.plan, self.config, self.project)
        self.assertFalse(result["token_saver_effective"])

    def test_model_comes_from_the_task_not_a_default(self):
        # ~70 KB: over the page cap on the Claude 5 tokenizer (2.6 B/tok),
        # under the warn on Haiku 4.5 (3.5 B/tok). Same file, two verdicts.
        self._write_context_file("docs/mid.md", 70_000)
        self._write_task("T-sonnet.md",
                         "| 1 | `docs/mid.md` | 68 | ~27K | why |", agent="Sonnet")
        self._write_task("T-haiku.md",
                         "| 1 | `docs/mid.md` | 68 | ~20K | why |", agent="Haiku")
        result = tss.scan_plan(self.plan, self.config, self.project)
        by_model = {t["model"]: t["files"][0]["level"] for t in result["tasks"]}
        self.assertEqual(by_model["sonnet"], "Critical")
        self.assertEqual(by_model["haiku"], "Green")

    def test_projected_growth_flags_a_file_pre_emptively(self):
        self._write_context_file("docs/growing.md", 50_000)
        self._write_task(
            "T-01.md",
            "| 1 | `docs/growing.md` | 49 | ~19K | rewritten here, +30000 bytes |",
        )
        result = tss.scan_plan(self.plan, self.config, self.project)
        finding = result["tasks"][0]["files"][0]
        self.assertEqual(finding["projected_added_bytes"], 30_000)
        # 50,000 alone is safe; 80,000 crosses the 25,000-token page cap.
        self.assertEqual(finding["level"], "Critical")

    def test_unresolved_rows_are_bucketed_not_dumped(self):
        self._write_task(
            "T-01.md",
            "| 1 | `Outputs/later.md` | 1 | ~1K | not written yet |\n"
            "| 2 | `docs/BB-*.md` | 1 | ~1K | a set, not a file |\n"
            "| 3 | `docs/gone.md` | 1 | ~1K | genuinely absent |",
        )
        result = tss.scan_plan(self.plan, self.config, self.project)
        reasons = {u["cell"]: u["reason"] for u in result["unresolved"]}
        self.assertEqual(reasons["Outputs/later.md"], "plan output (not yet created)")
        self.assertEqual(reasons["docs/BB-*.md"], "pattern")
        self.assertEqual(reasons["docs/gone.md"], "missing")

    def test_command_corpus_row_is_skipped_silently(self):
        self._write_task(
            "T-01.md",
            "| 1 | Grep the handler family over scripts/ | 1 | ~1K | corpus |",
        )
        result = tss.scan_plan(self.plan, self.config, self.project)
        self.assertEqual(result["summary"]["files"], 0)
        self.assertEqual(result["unresolved"], [])


class TestCli(unittest.TestCase):
    """Exit codes and the facade entry point Step 8c cites."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tss_cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_facade_exposes_the_runnable_scan(self):
        # Step 8c cites `python token_saver.py --scan --plan ... --config ...`.
        self.assertTrue(callable(token_saver.main))

    def test_missing_plan_directory_is_a_usage_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = tss.main(["--scan", "--plan", str(self.tmp / "nope")])
        self.assertEqual(code, 2)
        self.assertIn("not a directory", buf.getvalue())

    def test_bad_projected_pair_is_a_usage_error(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = tss.main(
                ["--scan", "--plan", str(self.tmp), "--projected", "a/b.md=lots"]
            )
        self.assertEqual(code, 2)
        self.assertIn("PATH=BYTES", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
