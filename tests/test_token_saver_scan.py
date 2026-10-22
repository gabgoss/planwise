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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports whether pytest is launched from the repo root or from inside
# tests/ — mirrors the sibling test modules' self-locating sys.path line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import token_saver
import token_saver_scan as tss
import token_saver_writeback as tsw

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

    def test_purpose_cell_with_escaped_pipe_does_not_shift_columns(self):
        # A Purpose cell may legitimately name a shell pipeline inline. A
        # naive `.split("|")` there would shift the row's own trailing
        # columns, but here Purpose is the last column, so the hazard is a
        # phantom extra cell rather than a shift -- either way the File
        # cell must still resolve to exactly the same value as a clean row.
        row = r"| 1 | `a/b.md` | 10 | ~4K | uses \| in a shell pipeline |"
        parsed = tss.parse_required_context(_task(TEMPLATE_COLUMNS, row))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["file_cell"], "`a/b.md`")
        self.assertEqual(parsed[0]["purpose"], "uses | in a shell pipeline")

    def test_command_corpus_rows_are_not_paths(self):
        self.assertTrue(tss.is_command_corpus("Grep family over scope"))
        self.assertTrue(tss.is_command_corpus("`python parse_backlog.py --all`"))
        self.assertFalse(tss.is_command_corpus("`planwise/config.yaml`"))


class TestClassificationHelpers(unittest.TestCase):
    """Content class, annotations, and the recommendation ladder."""

    def test_doc_gets_no_content_class_so_the_ratio_stays_conservative(self):
        label, content = tss.content_class_for(Path("x/index.md"))
        self.assertEqual(label, "doc")
        # None -> bytes_per_token falls back to the family's densest text
        # ratio. Guessing "prose" on a dense table index under-estimates.
        self.assertIsNone(content)
        self.assertEqual(tss.content_class_for(Path("x/a.py")), ("code", "code"))
        # JSON and notebook files carry their own measured classes, both
        # denser than dense-md; other dense structures stay on dense-md.
        self.assertEqual(tss.content_class_for(Path("x/a.json")), ("dense", "json"))
        self.assertEqual(tss.content_class_for(Path("x/a.ipynb")), ("dense", "notebook"))
        self.assertEqual(tss.content_class_for(Path("x/a.csv")), ("dense", "dense-md"))
        # `.min.js` is a double extension — Path.suffix is `.js`, so it must
        # be matched on the name, not the suffix.
        self.assertEqual(tss.content_class_for(Path("x/lib.min.js")), ("dense", "dense-md"))
        self.assertEqual(tss.content_class_for(Path("x/lib.js")), ("code", "code"))

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


class TestUnresolvedReason(unittest.TestCase):
    """A single token is always a path; only a multi-word cell can be prose."""

    def test_suffixless_and_output_paths_read_missing_not_prose(self):
        root = Path(tempfile.gettempdir())
        for cell in ("`Makefile`", "`src/output_writer.py`", "`src/orchard/`",
                     "`docs/output-format.md`"):
            self.assertEqual(tss.unresolved_reason(cell, root), "missing", cell)

    def test_prose_cells_still_read_prose(self):
        root = Path(tempfile.gettempdir())
        for cell in ("the full suite summary output", "ruff output lines",
                     "Grep 'ledger' over src/orchard"):
            self.assertEqual(
                tss.unresolved_reason(cell, root),
                "not a path (prose or command output)", cell,
            )


GUIDE = (
    "# Guide\n"
    "intro line\n"
    "## 1. First\n"
    + "first body line\n" * 40
    + "## 2. Second\n"
    + "second body line\n" * 60
    + "```\n## 9. Not a heading inside a fence\n```\n"
    "### 2.1 Sub\n"
    + "sub body line\n" * 30
    + "## 3. Third\n"
    + "third body line\n" * 50
)

TASK_ROWS = (
    "| 1 | `kit/tool.py` | 9.9 | ~9.9K | whole file |\n"
    "| 2 | `kit/guide.md` lines 3-12 | 9.9 | ~9.9K | line span |\n"
    "| 3 | `kit/guide.md` §2–§3 (§3 runs to EOF) | 9.9 | ~9.9K | section span |\n"
    "| 4 | Grep handler family over scripts/ — 10 lines / 400 bytes returned"
    " | 0.4 | ~0.2K | corpus |\n"
    "| 5 | `Outputs/later.md` | 1.0 | ~0.4K | not written yet |"
)


def _wb_task(rows: str, subtotal: str, task_id: str = "DM-S01-01-01",
             estimated: str = "~10K", columns: str = TEMPLATE_COLUMNS) -> str:
    return (
        "# Task: Sonnet-Probe\n\n"
        f"**Task ID:** {task_id}\n"
        "**Agent:** Sonnet\n"
        f"**Estimated Tokens:** {estimated}\n\n"
        "---\n\n"
        "## Required Context\n\n"
        f"{columns}\n"
        "|----------|------|----:|--------:|---------|\n"
        f"{rows}\n\n"
        f"{subtotal}\n\n"
        "---\n\n"
        "## Execution Steps\n\n1. Do the thing.\n"
    )


SUBTOTAL = ("**Context subtotal:** ~40.0K (reads — the sum of the ~Tokens column)"
            " + ~5K (output) + ~3K (working) = **~48K total**")

# The real Session Task List shape: `#` holds the task's number, Task holds
# its name segment and a description, and Depends On cites OTHER tasks' IDs.
# No cell holds the row's own Task ID.
TASK_LIST_HEAD = (
    "| # | Task | Agent | Est. Tokens | Depends On |\n"
    "|---|------|-------|-------------|------------|\n"
)
ORCHESTRATION = (
    "# Orchestration\n\n"
    "## Required Reading\n\n"
    "| Priority | File | Purpose |\n"
    "|---|---|---|\n"
    "| 1 | `DM-S01-01-Orchestration.md` (this file) | Session plan |\n\n"
    "## Session Task List\n\n"
    + TASK_LIST_HEAD
    + "| 1 | Probe: price the kit files | Sonnet | ~10K | cross-sprint: DM-S00-02-01 |\n"
    "| 2 | Other: read what Probe wrote | Sonnet | ~20K | 1; DM-S01-01-01 |\n\n"
    "**Total Estimated:** ~30K tokens (10 + 20)\n\n"
    "## Task Files\n\n"
    "| # | Task File | Agent |\n"
    "|---|-----------|-------|\n"
    "| 1 | [DM-S01-01-01-Sonnet-Probe.md](DM-S01-01-01-Sonnet-Probe.md) | Sonnet |\n"
)

# The real Sprint Plan shape: the Sessions table carries the session ID in its
# own cell, and each session's own task table (with cross-session cells that
# cite `<session>-01`) sits under Session Details.
SPRINT_PLAN = (
    "# Sprint Plan\n\n"
    "**Estimated Tokens:** ~45K total across all sessions\n\n"
    "## Sessions\n\n"
    "| Session | ID | Name | Objective | Est. Tokens |\n"
    "|---------|----|------|-----------|-------------|\n"
    "| 1 | DM-S01-01 | Beta | Price the kit | ~30K |\n"
    "| 2 | DM-S01-02 | Gamma | Use the prices | ~15K |\n\n"
    "## Session Details\n\n"
    "### Session 01: Beta\n\n"
    + TASK_LIST_HEAD
    + "| 1 | Probe: price the kit files | Sonnet | ~10K | - |\n"
    "| 2 | Other: read what Probe wrote | Sonnet | ~20K | 1 |\n\n"
    "**Total Estimated:** ~30K tokens (10 + 20)\n\n"
    "### Session 02: Gamma\n\n"
    + TASK_LIST_HEAD
    + "| 1 | Use: apply the prices | Sonnet | ~15K | cross-session: DM-S01-01-01 |\n\n"
    "**Total Estimated:** ~15K tokens\n"
)


class TestWriteEstimates(unittest.TestCase):
    """`--write-estimates`: row pricing, totals, scope, idempotence, dry run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tss_write_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = self.tmp
        self.plan = self.tmp / "Plans" / "Demo"
        self.sprint = self.plan / "Sprint-01-Alpha"
        self.session = self.sprint / "Session-01-Beta"
        self.session.mkdir(parents=True)
        kit = self.project / "kit"
        kit.mkdir()
        (kit / "tool.py").write_bytes(b"def f():\n    return 1\n" * 300)
        (kit / "guide.md").write_bytes(GUIDE.encode("utf-8"))
        self.task = self.session / "DM-S01-01-01-Sonnet-Probe.md"
        self.task.write_text(_wb_task(TASK_ROWS, SUBTOTAL), encoding="utf-8")
        (self.session / "DM-S01-01-Orchestration.md").write_text(
            ORCHESTRATION, encoding="utf-8")
        (self.sprint / "DM-S01-Sprint-Plan.md").write_text(SPRINT_PLAN, encoding="utf-8")

    def _run(self, *tasks, dry_run=False):
        return tsw.write_estimates(list(tasks) or [self.task], self.plan,
                                   self.project, dry_run=dry_run)

    def _row_cells(self, n: int) -> list[str]:
        text = self.task.read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith(f"| {n} |")]
        return tss.split_row_cells(rows[0])

    def _main(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tss.main(["--scan", "--plan", str(self.plan), *extra])
        return code, out.getvalue(), err.getvalue()

    def _loaded_after(self, *extra) -> bool:
        """Run `main` in a fresh interpreter; True when it loaded the write-back."""
        scripts = Path(tss.__file__).resolve().parent
        probe = (
            "import contextlib, io, sys\n"
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "import token_saver_scan\n"
            "assert 'token_saver_writeback' not in sys.modules\n"
            "with contextlib.redirect_stdout(io.StringIO()):\n"
            "    token_saver_scan.main(sys.argv[1:])\n"
            "print('token_saver_writeback' in sys.modules)\n"
        )
        done = subprocess.run(
            [sys.executable, "-B", "-c", probe, "--scan", "--plan", str(self.plan), *extra],
            capture_output=True, text=True, check=True)
        return done.stdout.strip() == "True"

    # -- lazy import ------------------------------------------------------
    def test_plain_scan_never_loads_the_writeback_module(self):
        self.assertFalse(self._loaded_after())

    def test_write_estimates_loads_the_writeback_module(self):
        self.assertTrue(self._loaded_after("--write-estimates", "--task", str(self.task),
                                           "--dry-run"))

    # -- scope -----------------------------------------------------------
    def test_refuses_without_task_scope(self):
        before = self.task.read_bytes()
        code, _out, err = self._main("--write-estimates")
        self.assertEqual(code, 2)
        self.assertIn("--task", err)
        self.assertEqual(self.task.read_bytes(), before)

    def test_scoped_run_writes_the_named_task(self):
        before = self.task.read_bytes()
        code, out, _err = self._main("--write-estimates", "--task", str(self.task))
        self.assertEqual(code, 0)
        self.assertNotEqual(self.task.read_bytes(), before)
        self.assertIn("Files written: 3", out)

    def test_task_and_dry_run_need_the_mode(self):
        code, _out, err = self._main("--task", str(self.task))
        self.assertEqual(code, 2)
        self.assertIn("only with --write-estimates", err)

    def test_unscoped_sibling_task_is_not_rewritten(self):
        sibling = self.session / "DM-S01-01-02-Sonnet-Other.md"
        sibling.write_text(_wb_task(TASK_ROWS, SUBTOTAL, task_id="DM-S01-01-02"),
                           encoding="utf-8")
        before = sibling.read_bytes()
        self._run(self.task)
        self.assertEqual(sibling.read_bytes(), before)

    # -- row pricing -----------------------------------------------------
    def test_whole_file_row_matches_the_class_matched_measurer(self):
        import measure_files
        self._run()
        path = str(self.project / "kit" / "tool.py")
        measured = measure_files.measure_file(path, "sonnet", "code")
        cells = self._row_cells(1)
        self.assertEqual(cells[2], f"{measured['kib']:,}")
        self.assertEqual(cells[3], tsw._fmt_k(measured["tokens"]))
        # The no-flag measurer form prices code at the text fallback, so it
        # disagrees with the cell: the code class is the scan's decision.
        plan_form = measure_files.measure_file(path, "sonnet")
        self.assertNotEqual(plan_form["tokens"], measured["tokens"])

    def test_lines_span_is_priced_on_its_span(self):
        self._run()
        lines = (self.project / "kit" / "guide.md").read_bytes().split(b"\n")
        span = sum(len(x) + 1 for x in lines[2:12])
        whole = (self.project / "kit" / "guide.md").stat().st_size
        cells = self._row_cells(2)
        self.assertEqual(cells[2], tsw._fmt_kib(span))
        self.assertNotEqual(cells[2], tsw._fmt_kib(whole))

    def test_lines_span_row_resolves_in_the_scan(self):
        # The row used to read `missing`: the resolver kept the ` lines a-b`
        # suffix as part of the path. A suffix that is not the span form
        # still reads missing.
        config = {"context": {"token_saver": True,
                              "token_saver_session_target": 150_000,
                              "token_saver_runner_overhead": 1_000}}
        self.task.write_text(_wb_task(
            "| 1 | `kit/guide.md` lines 3-12 | 1 | ~1K | span |\n"
            "| 2 | `kit/guide.md` lines three | 1 | ~1K | not a span |", SUBTOTAL),
            encoding="utf-8")
        result = tss.scan_plan(self.plan, config, self.project)
        self.assertEqual(result["summary"]["files"], 1)
        self.assertEqual([u["cell"] for u in result["unresolved"]],
                         ["kit/guide.md lines three"])

    def test_section_span_runs_to_eof(self):
        report = self._run()
        data = (self.project / "kit" / "guide.md").read_bytes()
        expected = len(data) - data.index(b"## 2. Second")
        cells = self._row_cells(3)
        self.assertEqual(cells[2], tsw._fmt_kib(expected))
        self.assertTrue(any("§2 at :" in s["resolved"] for s in report["spans"]))

    def test_section_span_bounded_stops_at_the_next_heading(self):
        data = (self.project / "kit" / "guide.md").read_bytes()
        first = data.index(b"## 1. First")
        bounded = data.index(b"## 2. Second") - first
        found = tsw._section_span(self.project / "kit" / "guide.md", "1", "1")
        self.assertEqual(found[2], bounded)
        # A heading inside a fence is not a heading; an absent one is reported.
        self.assertIsNone(tsw._section_span(self.project / "kit" / "guide.md", "9", "9"))

    def test_command_corpus_row_is_left_as_authored(self):
        report = self._run()
        self.assertEqual(self._row_cells(4)[2:4], ["0.4", "~0.2K"])
        self.assertTrue(any(item["reason"] == "command corpus" for item in report["left"]))
        # The file row with the same authored cells did change.
        self.assertNotEqual(self._row_cells(1)[2:4], ["9.9", "~9.9K"])

    def test_unresolved_and_qualified_rows_are_left_and_reported(self):
        self.task.write_text(_wb_task(
            "| 1 | `Outputs/later.md` | 1.0 | ~0.4K | not yet |\n"
            "| 2 | `kit/tool.py` — Section 1 | 2.0 | ~0.8K | narrower than the file |",
            SUBTOTAL), encoding="utf-8")
        report = self._run()
        reasons = sorted(item["reason"] for item in report["left"])
        self.assertEqual(reasons, [
            "plan output (not yet created)",
            "qualified row (text after the path is not a span form)",
        ])
        self.assertEqual(self._row_cells(2)[2:4], ["2.0", "~0.8K"])

    def test_table_without_kib_column_is_untouched(self):
        self.task.write_text(_wb_task(
            "| 1 | `kit/tool.py` | 300 | ~2K | legacy layout |", SUBTOTAL,
            columns=LEGACY_COLUMNS), encoding="utf-8")
        before = self.task.read_bytes()
        report = self._run()
        self.assertEqual(self.task.read_bytes(), before)
        self.assertIn("no File, KiB or ~Tokens column", report["left"][0]["reason"])

    # -- totals ----------------------------------------------------------
    def test_subtotal_header_orchestration_and_sprint_reroll(self):
        self._run()
        text = self.task.read_text(encoding="utf-8")
        reads = sum(tsw._parse_token_cell(self._row_cells(n)[3]) for n in range(1, 6))
        sub = next(ln for ln in text.splitlines() if ln.startswith("**Context subtotal:**"))
        self.assertIn(tsw._fmt_k(reads), sub)
        total = int((reads / 1000 + 8).quantize(tsw.Decimal("1"),
                                                 rounding=tsw.ROUND_HALF_UP))
        self.assertIn(f"**~{total}K total**", sub)
        self.assertIn(f"**Estimated Tokens:** ~{total}K", text)
        orch = (self.session / "DM-S01-01-Orchestration.md").read_text(encoding="utf-8")
        # Found by number and name, never by the ID a Depends On cell cites.
        self.assertIn(f"| 1 | Probe: price the kit files | Sonnet | ~{total}K |", orch)
        self.assertIn("| 2 | Other: read what Probe wrote | Sonnet | ~20K | 1; DM-S01-01-01 |",
                      orch)
        # The breakdown is re-rolled from the same addends as the sum.
        self.assertIn(f"**Total Estimated:** ~{total + 20}K tokens ({total} + 20)", orch)
        sprint = (self.sprint / "DM-S01-Sprint-Plan.md").read_text(encoding="utf-8")
        self.assertIn(f"| 1 | DM-S01-01 | Beta | Price the kit | ~{total + 20}K |", sprint)
        self.assertIn("| 2 | DM-S01-02 | Gamma | Use the prices | ~15K |", sprint)
        # Session Details tables and totals are never touched.
        self.assertIn("| 1 | Probe: price the kit files | Sonnet | ~10K | - |", sprint)
        self.assertEqual(sprint.count("**Total Estimated:** ~30K tokens (10 + 20)"), 1)

    def test_unreadable_subtotal_is_reported_not_guessed(self):
        odd = "**Context subtotal:** ~40.0K reads × 1.2 + ~5K output = **~53K total**"
        self.task.write_text(_wb_task(TASK_ROWS, odd), encoding="utf-8")
        report = self._run()
        text = self.task.read_text(encoding="utf-8")
        self.assertIn(odd, text)
        self.assertIn("**Estimated Tokens:** ~10K", text)
        self.assertTrue(any(u["what"] == "Context subtotal" for u in report["unreadable"]))

    # -- idempotence and dry run ------------------------------------------
    def test_second_run_writes_nothing(self):
        first = self._run()
        self.assertGreater(len(first["changes"]), 0)
        snapshot = {p: p.read_bytes() for p in self.plan.rglob("*.md")}
        second = self._run()
        self.assertEqual(second["changes"], [])
        self.assertEqual(second["written"], [])
        self.assertEqual({p: p.read_bytes() for p in self.plan.rglob("*.md")}, snapshot)

    def test_dry_run_writes_nothing(self):
        snapshot = {p: p.read_bytes() for p in self.plan.rglob("*.md")}
        report = self._run(dry_run=True)
        self.assertGreater(len(report["changes"]), 0)
        self.assertEqual(report["written"], [])
        self.assertEqual({p: p.read_bytes() for p in self.plan.rglob("*.md")}, snapshot)

    def test_crlf_line_endings_survive(self):
        self.task.write_bytes(_wb_task(TASK_ROWS, SUBTOTAL).replace("\n", "\r\n")
                              .encode("utf-8"))
        self._run()
        data = self.task.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


class TestWriteBackRealShapes(unittest.TestCase):
    """Review fixes: real Orchestration and Sprint Plan shapes, precision,
    breakdowns, atomic writes, footers, fences, --config, code-span pipes."""

    setUp = TestWriteEstimates.setUp
    _run = TestWriteEstimates._run
    _row_cells = TestWriteEstimates._row_cells
    _main = TestWriteEstimates._main

    def _orch(self) -> Path:
        return self.session / "DM-S01-01-Orchestration.md"

    def _sprint(self) -> Path:
        return self.sprint / "DM-S01-Sprint-Plan.md"

    def _snapshot(self) -> dict:
        return {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}

    def _measured_rows(self) -> tuple[str, list]:
        """One whole-file row whose cells already equal the measurement."""
        price = tsw.price_row("`kit/tool.py`", self.task, self.plan, self.project, "sonnet")
        kib, tok = tsw._fmt_kib(price["bytes"]), tsw._fmt_k(price["tokens"])
        return f"| 1 | `kit/tool.py` | {kib} | {tok} | whole file |", [kib, tok]

    # -- finding 1: the task row is found by number and name ----------------
    def test_task_row_whose_name_differs_is_reported_and_orch_untouched(self):
        self._orch().write_text(ORCHESTRATION.replace("Probe: price", "Sample: price"),
                                encoding="utf-8")
        before = self._orch().read_bytes()
        report = self._run()
        self.assertEqual(self._orch().read_bytes(), before)
        self.assertTrue(any("does not name 'Probe'" in u["reason"]
                            for u in report["unreadable"]))

    def test_duplicate_task_number_is_reported_not_guessed(self):
        self._orch().write_text(ORCHESTRATION.replace("| 2 | Other", "| 1 | Other"),
                                encoding="utf-8")
        before = self._orch().read_bytes()
        report = self._run()
        self.assertEqual(self._orch().read_bytes(), before)
        self.assertTrue(any(u["reason"] == "2 task rows numbered 1"
                            for u in report["unreadable"]))

    # -- finding 2: the Sessions row is matched by the whole-cell ID --------
    def test_sessions_row_without_the_id_cell_is_reported(self):
        self._sprint().write_text(SPRINT_PLAN.replace("| DM-S01-01 | Beta", "| - | Beta"),
                                  encoding="utf-8")
        before = self._sprint().read_bytes()
        report = self._run()
        self.assertEqual(self._sprint().read_bytes(), before)
        self.assertTrue(any(u["reason"] == "0 Sessions rows hold the ID"
                            for u in report["unreadable"]))

    # -- finding 3: authored precision; a correct plan writes nothing -------
    def test_correct_plan_at_tenth_k_precision_writes_nothing(self):
        row, (_kib, tok) = self._measured_rows()
        reads = tsw._parse_token_cell(tok) / 1000
        total = reads + tsw.Decimal("4.5")
        sub = (f"**Context subtotal:** ~{reads}K (reads: {reads}) + ~4.5K (output)"
               f" = **~{total}K total**")
        self.task.write_text(_wb_task(row, sub, estimated=f"~{total}K"), encoding="utf-8")
        self._orch().write_text(ORCHESTRATION.replace("~10K | cross", f"~{total}K | cross")
                                .replace("~30K tokens (10 + 20)",
                                         f"~{total + 20}K tokens ({total} + 20)"),
                                encoding="utf-8")
        self._sprint().write_text(SPRINT_PLAN.replace("Price the kit | ~30K",
                                                      f"Price the kit | ~{total + 20}K"),
                                  encoding="utf-8")
        before = self._snapshot()
        report = self._run()
        self.assertEqual(report["changes"], [])
        self.assertEqual(report["unreadable"], [])
        self.assertEqual(self._snapshot(), before)

    def test_whole_k_total_stays_whole_k(self):
        line = "**Context subtotal:** ~1.5K + ~4K (output) = **~6K total**"
        new, reads_text, total_text = tsw._reroll_subtotal(
            line, tsw.Decimal(1500), [tsw.Decimal("1.5")])
        self.assertEqual((reads_text, total_text), ("~1.5K", "~6K"))
        self.assertEqual(new, line)
        tenth = "**Context subtotal:** ~1.5K + ~4K (output) = **~5.5K total**"
        self.assertEqual(tsw._reroll_subtotal(tenth, tsw.Decimal(1500),
                                              [tsw.Decimal("1.5")])[2], "~5.5K")

    # -- finding 4: a breakdown is re-rolled with its sum, or reported ------
    def test_reads_breakdown_is_rerolled_with_its_sum(self):
        sub = ("**Context subtotal:** ~49.5K (reads: 9.9 + 9.9 + 9.9 + 0.2 + 0.4)"
               " + ~5K (output) = **~55K total**")
        self.task.write_text(_wb_task(TASK_ROWS, sub), encoding="utf-8")
        self._run()
        line = next(ln for ln in self.task.read_text(encoding="utf-8").splitlines()
                    if ln.startswith("**Context subtotal:**"))
        addends = [tsw.Decimal(x) for x in
                   line.split("(reads: ")[1].split(")")[0].split(" + ")]
        expected = [tsw._parse_token_cell(self._row_cells(n)[3]) / 1000 for n in range(1, 6)]
        self.assertEqual(addends, expected)
        self.assertIn(tsw._fmt_k(sum(expected) * 1000), line)

    def test_breakdown_that_does_not_match_the_rows_is_left_and_reported(self):
        sub = ("**Context subtotal:** ~19.8K (reads: 9.9 + 9.9) + ~5K (output)"
               " = **~25K total**")
        self.task.write_text(_wb_task(TASK_ROWS, sub), encoding="utf-8")
        report = self._run()
        self.assertIn(sub, self.task.read_text(encoding="utf-8"))
        self.assertTrue(any("breakdown" in u["reason"] for u in report["unreadable"]))

    def test_orchestration_breakdown_mismatch_leaves_the_file(self):
        self._orch().write_text(ORCHESTRATION.replace("(10 + 20)", "(5 + 5 + 20)"),
                                encoding="utf-8")
        before = self._orch().read_bytes()
        report = self._run()
        self.assertEqual(self._orch().read_bytes(), before)
        self.assertTrue(any(u["what"] == "Total Estimated" and "breakdown" in u["reason"]
                            for u in report["unreadable"]))

    # -- finding 5: all-or-nothing writes, one decoding policy --------------
    def test_failed_temp_write_replaces_no_file(self):
        before = self._snapshot()
        real, calls = tsw.tempfile.mkstemp, []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(*args, **kwargs)

        tsw.tempfile.mkstemp = flaky
        self.addCleanup(setattr, tsw.tempfile, "mkstemp", real)
        report = self._run()
        self.assertEqual(report["written"], [])
        self.assertTrue(report["errors"])
        self.assertEqual(self._snapshot(), before)  # no file changed, no temp left

    def test_undecodable_orchestration_is_reported_not_a_traceback(self):
        self._orch().write_bytes(ORCHESTRATION.encode("utf-8") + b"\xff\xfe cp1252\n")
        before = self._snapshot()
        code, out, _err = self._main("--write-estimates", "--task", str(self.task))
        self.assertEqual(code, 3)
        self.assertIn("not UTF-8", out)
        self.assertEqual(self._snapshot(), before)

    def test_undecodable_task_is_a_usage_error(self):
        self.task.write_bytes(_wb_task(TASK_ROWS, SUBTOTAL).encode("utf-8") + b"\x81")
        code, _out, err = self._main("--write-estimates", "--task", str(self.task))
        self.assertEqual(code, 2)
        self.assertIn("not UTF-8", err)

    # -- finding 6: only numbered task rows are summed; bold parses ---------
    def test_footer_row_is_not_summed_and_bold_cell_parses(self):
        self._orch().write_text(
            ORCHESTRATION.replace("| ~20K | 1;", "| **~20K** | 1;")
            .replace("DM-S01-01-01 |\n\n", "DM-S01-01-01 |\n| | **Total** | | **~30K** | |\n\n"),
            encoding="utf-8")
        report = self._run()
        orch = self._orch().read_text(encoding="utf-8")
        cells = next(tss.split_row_cells(ln) for ln in orch.splitlines()
                     if ln.startswith("| 1 | Probe"))
        total = tsw._parse_token_cell(cells[3]) / 1000
        self.assertIn(f"**Total Estimated:** ~{total + 20}K tokens", orch)
        self.assertFalse(any(u["file"].endswith("Orchestration.md")
                             for u in report["unreadable"]))

    def test_unparseable_task_cell_is_reported(self):
        self._orch().write_text(ORCHESTRATION.replace("| ~20K | 1;", "| TBD | 1;"),
                                encoding="utf-8")
        before = self._orch().read_bytes()
        report = self._run()
        self.assertEqual(self._orch().read_bytes(), before)
        self.assertTrue(any(u["reason"] == "a task-list cell has no figure"
                            for u in report["unreadable"]))

    # -- finding 7: fence character AND length ------------------------------
    def test_longer_fence_is_not_closed_by_a_shorter_one(self):
        doc = self.project / "kit" / "fenced.md"
        doc.write_text(
            "## 2. Two\nbody\n````markdown\n```python\n## 3. Fake\n```\n````\n"
            "tail\n## 3. Real\nthree\n", encoding="utf-8")
        data = doc.read_bytes()
        self.assertEqual(tsw._section_span(doc, "2", "2")[2], data.index(b"## 3. Real"))
        self.assertEqual(tsw._section_span(doc, "3", "3")[0], 9)  # the real one

    def test_closing_fence_with_an_info_string_does_not_close(self):
        doc = self.project / "kit" / "fenced2.md"
        doc.write_text("## 1. One\n```\n```text\n## 2. Fake\n```\n## 2. Real\nx\n",
                       encoding="utf-8")
        self.assertEqual(tsw._section_span(doc, "2", "2")[0], 6)

    # -- finding 8: --config is passed to load_config -----------------------
    def test_config_flag_sets_the_project_root(self):
        cfg = self.project / "planwise" / "config.yaml"
        cfg.parent.mkdir()
        cfg.write_text("project:\n  name: Demo\n", encoding="utf-8")
        self.task.write_text(_wb_task("| 1 | `{project_root}/kit/tool.py` | 9.9 | ~9.9K | x |",
                                      SUBTOTAL), encoding="utf-8")
        code, out, _err = self._main("--write-estimates", "--dry-run", "--config", str(cfg),
                                     "--task", str(self.task))
        self.assertEqual(code, 0)
        self.assertIn("row 1 KiB: 9.9 ->", out)

    def test_config_for_another_root_leaves_the_placeholder_row_missing(self):
        cfg = self.tmp / "elsewhere" / "planwise" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("project:\n  name: Other\n", encoding="utf-8")
        self.task.write_text(_wb_task("| 1 | `{project_root}/kit/tool.py` | 9.9 | ~9.9K | x |",
                                      SUBTOTAL), encoding="utf-8")
        code, out, _err = self._main("--write-estimates", "--dry-run", "--config", str(cfg),
                                     "--task", str(self.task))
        self.assertEqual(code, 0)
        self.assertNotIn("row 1 KiB", out)
        self.assertIn("missing", out)

    def test_missing_config_file_is_a_usage_error(self):
        code, _out, err = self._main("--write-estimates", "--config",
                                     str(self.tmp / "none.yaml"), "--task", str(self.task))
        self.assertEqual(code, 2)
        self.assertIn("--config", err)

    # -- finding 9: a code span holding a pipe parses ------------------------
    def test_code_span_pipe_row_keeps_the_reroll(self):
        row, (kib, tok) = self._measured_rows()
        rows = (row.replace("| 1 |", "| `P|1` |") + "\n"
                "| 2 | `grep -c x | wc -l` output | 0.1 | ~0.1K | count |")
        self.task.write_text(_wb_task(rows.replace(kib, "9.9", 1), SUBTOTAL),
                             encoding="utf-8")
        report = self._run()
        text = self.task.read_text(encoding="utf-8")
        self.assertIn(f"| `P|1` | `kit/tool.py` | {kib} | {tok} | whole file |", text)
        self.assertIn("| 2 | `grep -c x | wc -l` output | 0.1 | ~0.1K | count |", text)
        self.assertFalse(any(u["what"] == "Context subtotal" for u in report["unreadable"]))

    def test_unbalanced_pipe_row_still_stops_the_reroll(self):
        rows = "| 1 | grep x | wc -l output | 0.1 | ~0.1K | count |"
        self.task.write_text(_wb_task(rows, SUBTOTAL), encoding="utf-8")
        report = self._run()
        self.assertTrue(any(item["reason"] == "cell count differs from the header"
                            for item in report["left"]))
        self.assertIn(SUBTOTAL, self.task.read_text(encoding="utf-8"))

    # -- finding 10: words are counted before root substitution -------------
    def test_root_with_a_space_keeps_a_single_token_missing(self):
        root = Path(tempfile.gettempdir()) / "Some User" / "proj"
        self.assertEqual(
            tss.unresolved_reason("`{project_root}/src/output_writer.py`", root), "missing")
        self.assertEqual(
            tss.unresolved_reason("`{project_root}/the full output`", root),
            "not a path (prose or command output)")


if __name__ == "__main__":
    unittest.main()
