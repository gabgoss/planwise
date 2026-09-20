#!/usr/bin/env python3
"""Unit tests for the backlog-index generator (scan/render/shard/budget/check/write).

`generate_backlog_index.py` scans every backlog item file's YAML frontmatter,
renders it into a 9-column table row, shards the corpus into a hub plus
Archive files under a per-file token budget, fills the Score cell via
`score_backlog.compute_score`, and drives `--check`/`--write` against
whatever is currently on disk.

These tests pin: the three column-position contracts three existing scripts
key off (Status at a literal index, Score/File relative to the row's own
length); an escaped-pipe title round-tripping through rendering without
shifting any later column; `shard_for` as a pure function with no lookup
table; all three budget-enforcer paths (fits, must-split, refuses rather
than ships an over-budget row); `--check`'s four classes (clean, drift,
anomaly, stale-score); atomic multi-file write rollback on a mid-write
failure; the D12 guarantee that `--write` never touches an item file; a
hand-edited on-disk row whose cell count no longer matches the header
(built from explicit CRLF bytes, never `Path.write_text`); an unresolvable
`blocks:` entry aborting generation; a reciprocal `blocks:` edge (report
modes still measure, `--write` refuses); the scanner's own-generated-artifact
filter; and stale-generated-file drift + removal, including the load-bearing
"deletes nothing else" guarantee. A final class pins the one exit-code
mapping (`Disposition`/`exit_code_for`) every mode routes through.

Each test builds an isolated temp planwise tree (config.yaml + Backlog/ +
Backlog/Archive/) or exercises a pure function directly; none read the live
project's backlog, and every fixture item is synthetic.

Run with:  python -m pytest -q -c pytest.ini tests/test_generate_backlog_index.py
"""

import difflib
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Allow imports whether pytest is launched from the repo root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "planwise" / "scripts"))

import generate_backlog_index as gbi
import score_backlog
from markdown_parser import split_row_cells, split_row_raw

CONFIG_YAML_FIXTURE = """project:
  name: "GeneratorFixtureProject"
  backlog_dir: "Backlog"
  index_files:
    backlog: "00-Index-Backlog.md"
"""

# A backlog_dir for the pure in-memory rendering tests below, which never
# touch a filesystem -- split_items_to_budget/render_table_body only need a
# Path to compute a relative File-cell link, never to read or write.
_PURE_BACKLOG_DIR = Path("Backlog")


def _make_item(item_id, *, blocks=None, title="Fixture item", priority="Medium",
                status="NOT_STARTED", abbrev="BUG", created="2026-01-01", score="10"):
    """Build an already-scanned item dict, matching what scan_backlog would
    have produced, for tests that exercise rendering/sharding directly."""
    id_str = f"{item_id:03d}"
    return {
        "id": id_str,
        "title": title,
        "priority": priority,
        "status": status,
        "abbrev": abbrev,
        "created": created,
        "blocks": blocks or [],
        "score": score,
        "_path": _PURE_BACKLOG_DIR / f"BB-{id_str}-01-{abbrev}-Fixture.md",
    }


def _one_shard_shards_section():
    """The `## Shards` directory a single closed item (id 990, its own
    century) produces -- a one-row directory, matching Finding F1's probe
    J shape and this session's live-corpus overhead order of magnitude."""
    return gbi.render_shards_section([
        {"min_id": 990, "max_id": 990, "path": "Archive/Index-Backlog-990-990.md"},
    ])


def _hub_wrapper_tokens(shards_section):
    """Replicate build_hub_files' own wrapper-reserve computation exactly,
    so the boundary window this module's tests target is the SAME window
    the production function computes -- never a re-derived approximation."""
    today = datetime.now().astimezone().date()
    generated_line = f"Generated: {today.isoformat()}\n\n"
    leaf0_wrapper = generated_line + "\n" + shards_section
    continuation_wrapper = f"[Back to Backlog Index](00-{gbi.INDEX_FILE_STEM}.md)\n\n"
    wrapper_bytes = max(
        len(leaf0_wrapper.encode("utf-8")), len(continuation_wrapper.encode("utf-8"))
    )
    return gbi.estimate_tokens(wrapper_bytes)


def _boundary_open_items(variable_blocks_len):
    """79 minimal open items (ids 001-079) plus one (id 080) carrying a
    `blocks` list long enough to push the body toward the split boundary.
    Every entry names item 990 -- a KNOWN but CLOSED id, so it resolves
    (no dangling-blocks abort) and contributes nothing to the blocks-count
    scoring factor (that factor only counts entries targeting an OPEN
    item), keeping the row's size the only thing this list inflates."""
    items = [_make_item(i, status="NOT_STARTED") for i in range(1, 80)]
    items.append(
        _make_item(80, status="NOT_STARTED", blocks=["990"] * variable_blocks_len)
    )
    return items


def _body_tokens_for(variable_blocks_len):
    items = _boundary_open_items(variable_blocks_len)
    body, _truncated = gbi.render_table_body(items, _PURE_BACKLOG_DIR)
    _num_bytes, tokens = gbi._measure(body)
    return tokens


def _find_boundary_blocks_len(target_low, target_high):
    """Binary-search the smallest `variable_blocks_len` whose body tokens
    reach the WINDOW's midpoint -- not its bare minimum -- so the fixture
    keeps buffer against small overhead differences (e.g. a computed
    Score's digit width) between this pure in-memory measurement and the
    real CLI reproduction built from the same recipe."""
    target = target_low + (target_high - target_low) // 2
    lo, hi = 0, 400000
    assert _body_tokens_for(lo) < target_low
    assert _body_tokens_for(hi) >= target_high
    while lo < hi:
        mid = (lo + hi) // 2
        if _body_tokens_for(mid) < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _hub_splitting_items(row_count=200, blocks_per_row=500):
    """200 open items, each with a 500-entry `blocks` list (every entry
    naming item 990 -- a known CLOSED id, so each entry resolves and
    contributes nothing to the blocks-count scoring factor, which only
    counts entries targeting an OPEN item) -- dense enough in aggregate to
    force a multi-leaf hub split (case (b)'s density), while no SINGLE row
    is anywhere close to budget alone, so no unsplittable-row refusal is
    at risk of firing instead of the split this is meant to force.
    """
    blocks = ["990"] * blocks_per_row
    return [_make_item(i, status="NOT_STARTED", blocks=blocks) for i in range(1, row_count + 1)]


class _GeneratorFixtureBase(unittest.TestCase):
    """Builds an isolated temp planwise tree: config.yaml + Backlog/ +
    Backlog/Archive/, so the generator's CLI runs against a hermetic copy
    instead of the live project's backlog.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.planwise_dir = self.tmp / "planwise"
        self.backlog_dir = self.planwise_dir / "Backlog"
        self.archive_dir = self.backlog_dir / "Archive"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.planwise_dir / "config.yaml"
        self.config_path.write_text(CONFIG_YAML_FIXTURE, encoding="utf-8")

        saved_argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", saved_argv))

    def write_item(self, item_id, *, title="Fixture item", priority="Medium",
                   status="NOT_STARTED", abbrev="BUG", created="2026-01-01",
                   blocks=None, archived=False, filename=None,
                   extra_frontmatter=""):
        """Write one synthetic item file with valid frontmatter."""
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
            f"{extra_frontmatter}"
            "---\n\n"
            f"# {title}\n"
        )
        target_dir = self.archive_dir if archived else self.backlog_dir
        name = filename or f"BB-{item_id}-01-{abbrev}-Fixture.md"
        path = target_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def run_main(self, *extra_args):
        """Invoke main() against the fixture config, capturing stdout/stderr."""
        sys.argv = ["test_generate_backlog_index", "--config", str(self.config_path), *extra_args]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gbi.main()
        return code, out.getvalue(), err.getvalue()


class TestColumnPositionContract(unittest.TestCase):
    """Three existing scripts read this table by cell position: Status at
    a literal index 3, Score second-to-last, File last. Pinned both as
    module constants and as the actual runtime placement render_row
    produces -- a regression in the constant and a regression in the
    assignment are two different failure modes, and only the second is
    invisible to the module's own import-time asserts."""

    def test_module_level_constants(self):
        self.assertEqual(gbi.COL_STATUS, 3)
        self.assertEqual(gbi.COL_SCORE, gbi.COLUMN_COUNT - 2)
        self.assertEqual(gbi.COL_FILE, gbi.COLUMN_COUNT - 1)

    def test_render_row_places_status_priority_score_file_at_contract_positions(self):
        item = _make_item(1, title="Sample", priority="High", status="IN_PROGRESS", score="42")
        row, _was_truncated = gbi.render_row(item, _PURE_BACKLOG_DIR)
        cells = split_row_cells(row)

        self.assertEqual(len(cells), gbi.COLUMN_COUNT)
        self.assertEqual(cells[3], "IN_PROGRESS")
        self.assertEqual(cells[-2], "42")
        self.assertIn("BB-001-01-BUG-Fixture.md", cells[-1])


class TestEscapedPipeRoundTrip(unittest.TestCase):
    """A `|` inside a title (e.g. quoting a shell pipeline in a code span)
    must round-trip through rendering without shifting every later column
    -- the BB-070 defect class this generator exists to end."""

    RAW_TITLE = r"Run `git diff --name-only | grep dir` first"

    def test_pipe_is_escaped_and_cell_count_matches_header(self):
        item = _make_item(2, title=self.RAW_TITLE, abbrev="INFRA", status="NOT_STARTED")
        row, _was_truncated = gbi.render_row(item, _PURE_BACKLOG_DIR)

        # The raw pipe survives rendering only via escaping -- an
        # unescaped cell would silently shift Status/Score/File left by one.
        self.assertIn(r"\|", row)
        self.assertEqual("|".join(split_row_raw(row)), row)

        cells = split_row_cells(row)
        self.assertEqual(len(cells), gbi.COLUMN_COUNT)
        self.assertEqual(cells[gbi.COL_TITLE], self.RAW_TITLE)
        self.assertEqual(cells[gbi.COL_STATUS], "NOT_STARTED")


class TestShardForIsPure(unittest.TestCase):
    """`shard_for` is a pure function of the id alone -- no registry has to
    stay in sync with which century a given id belongs to."""

    def test_boundary_and_formula(self):
        self.assertEqual(gbi.shard_for(1), gbi.shard_for(100))
        self.assertNotEqual(gbi.shard_for(100), gbi.shard_for(101))
        for item_id in (1, 50, 100, 101, 200, 201, 999):
            self.assertEqual(gbi.shard_for(item_id), (item_id - 1) // 100)

    def test_no_lookup_table_backs_it(self):
        # A pure function has no state to grow: computing the same id
        # repeatedly, and out of numeric order, must be idempotent -- a
        # lookup/registry populated on first use is the failure mode this
        # guards against.
        first_pass = [gbi.shard_for(i) for i in (300, 1, 250, 999, 1)]
        second_pass = [gbi.shard_for(i) for i in (1, 999, 250, 1, 300)]
        self.assertEqual(first_pass[0], second_pass[4])  # 300, computed once each way
        self.assertEqual(first_pass[1], first_pass[4])   # 1, computed twice in one pass


class TestBudgetEnforcerThreePaths(unittest.TestCase):
    """The budget enforcer's three paths, as a pure function over in-memory
    items -- no filesystem, no CLI, so the recursion itself is exercised
    directly."""

    def test_fits_in_one_file_no_split(self):
        items = [_make_item(i) for i in range(1, 21)]
        leaves = gbi.split_items_to_budget(items, _PURE_BACKLOG_DIR)

        self.assertEqual(len(leaves), 1)
        _subset, _body, _num_bytes, tokens, _truncated = leaves[0]
        self.assertLess(tokens, gbi.READ_TOKEN_WARN)

    def test_must_split_and_every_leaf_under_budget(self):
        # Title truncation caps every Title cell at 120 chars regardless of
        # the frontmatter value, so a long title cannot force this density
        # -- inflate the uncapped `blocks` column instead, matching how the
        # real corpus's own dense rows reach it.
        bulky_blocks = [f"{i % 1000:03d}" for i in range(500)]
        items = [_make_item(i, blocks=bulky_blocks) for i in range(1, 201)]

        leaves = gbi.split_items_to_budget(items, _PURE_BACKLOG_DIR)

        self.assertGreater(len(leaves), 1)
        total_rows = 0
        for _subset, _body, _num_bytes, tokens, _truncated in leaves:
            self.assertLess(tokens, gbi.READ_TOKEN_WARN)
            total_rows += len(_subset)
        self.assertEqual(total_rows, 200)

    def test_unsplittable_single_row_refuses_naming_the_row(self):
        huge_blocks = [f"{i % 1000:03d}" for i in range(15000)]
        item = _make_item(1, blocks=huge_blocks)

        with self.assertRaises(gbi.GeneratorError) as ctx:
            gbi.split_items_to_budget([item], _PURE_BACKLOG_DIR)

        message = str(ctx.exception)
        self.assertIn("item 001", message)
        self.assertIn(str(item["_path"]), message)
        self.assertIn("cannot be reduced by sharding further", message)


class TestWriteRefusesOnPathologicalRow(_GeneratorFixtureBase):
    """The budget enforcer's refusal, proven end to end through --write:
    a single row that cannot fit under budget must produce a non-zero exit
    and leave no index file on disk -- never ship a violation."""

    def test_write_refuses_and_writes_no_file(self):
        huge_blocks = [f"{i % 1000:03d}" for i in range(15000)]
        self.write_item("001", blocks=huge_blocks)

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("001", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())


class TestCheckFourClasses(_GeneratorFixtureBase):
    """--check's four classes, reproduced permanently from the
    discrimination runs recorded during this session's development."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01",
                         blocks=["001"])
        self.write_item("003", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="DOC", created="2025-06-01",
                         archived=True, filename="BB-003-01-DOC-Fixture.md")

    def test_clean_after_write(self):
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)

    def test_drift_named_on_frontmatter_change(self):
        self.run_main("--write")

        # Frontmatter is the source of truth -- mutating it directly on
        # disk is exactly what --check exists to catch as drift.
        item_path = self.backlog_dir / "BB-001-01-BUG-Fixture.md"
        text = item_path.read_text(encoding="utf-8")
        item_path.write_text(text.replace("priority: High", "priority: Low"), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("row disagrees with frontmatter", out)

    def test_anomaly_reported_never_healed(self):
        self.run_main("--write")
        (self.backlog_dir / "BB-002-01-INFRA-Fixture.md").unlink()

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("002", out)
        self.assertIn("no longer resolves", out)

        # --write must not fabricate the missing row from the stale cells.
        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        hub_text = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        self.assertNotIn("| 002 |", hub_text)

    def test_stale_score_reported_and_exit_zero(self):
        # Rebuild item 001 with a `created:` recent enough that the age
        # factor has room to move without hitting weights["age_cap"], so
        # advancing the clock changes ONLY the Score cell.
        #
        # CR6 repair: this used to patch `score_backlog.datetime` with a
        # plain `MagicMock`. `compute_score`'s age factor also runs
        # `isinstance(created, datetime)` on that SAME module-level name --
        # with a MagicMock in that position, `created` (always a plain
        # string here) makes that isinstance call raise `TypeError`, which
        # the factor's own `except (ValueError, TypeError): pass` silently
        # swallows, zeroing the age contribution for EVERY item scored
        # during the patch -- not "advancing the clock" at all. The test
        # still reported "Stale scores" because item 002's age factor (already
        # capped at `weights["age_cap"]` under the real clock) dropped to 0
        # once swallowed, a Score-only move for the WRONG reason; item 001,
        # this test's actual subject, never moved. A real `datetime`
        # subclass overriding only `now()` keeps `isinstance` working (a
        # string still correctly fails the check, never raises), so the age
        # factor runs for real and the clock genuinely advances.
        recent = datetime.now().astimezone().date() - timedelta(days=3)
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG",
                         created=recent.isoformat())
        self.run_main("--write")

        advanced_date = recent + timedelta(days=13)

        class _FixedNow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.combine(advanced_date, datetime.min.time())

        with patch.object(score_backlog, "datetime", _FixedNow):
            code, out, _err = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)
        self.assertIn("Stale scores", out)
        self.assertIn("benign and self-healing", out)
        # The SUBJECT item (001) is the one that actually moved -- the
        # swallowed-TypeError defect this repairs made 002 appear to move
        # instead, for an unrelated reason (its already-capped age factor
        # dropping to zero), while 001 never moved at all.
        self.assertIn("- 001:", out)
        self.assertNotIn("- 002:", out)


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


class TestCRLFMalformedRowAnomaly(_GeneratorFixtureBase):
    """A hand-edited generated file's row can end up with the wrong cell
    count. --check must report it as an anomaly, never heal it in place,
    and --write must replace it with the row rendered fresh from
    frontmatter -- never with cells salvaged from the broken row. Built
    from explicit CRLF bytes: Path.write_text normalizes to os.linesep, so
    a CRLF fixture authored that way would test the platform, not the
    code."""

    def test_check_reports_anomaly_and_write_replaces_from_frontmatter(self):
        self.write_item("001", title="Good row", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.run_main("--write")

        hub_path = self.backlog_dir / "00-Index-Backlog.md"
        text = hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        patched = []
        for line in lines:
            if line.strip().startswith("| 001 |"):
                cells = split_row_cells(line)
                cells.pop(gbi.COL_DOMAIN)  # drop one cell -- shifts every later column
                patched.append("|" + "|".join(f" {c} " for c in cells) + "|")
            else:
                patched.append(line)
        crlf_bytes = "\r\n".join(patched).encode("utf-8")
        hub_path.write_bytes(crlf_bytes)

        # Assert the line-ending property on the bytes actually written,
        # not on the string that produced them.
        self.assertIn(b"\r\n", crlf_bytes)
        self.assertEqual(crlf_bytes.count(b"\n"), crlf_bytes.count(b"\r\n"))

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("malformed row", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        rewritten = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        row_001 = next(
            split_row_cells(line) for line in rewritten.split("\n")
            if line.strip().startswith("| 001 |")
        )
        self.assertEqual(len(row_001), gbi.COLUMN_COUNT)
        # Never salvaged from the broken row -- the Domain cell (dropped
        # above) is restored from frontmatter, not left missing or blank.
        self.assertEqual(row_001[gbi.COL_DOMAIN], "BUG")


class TestUnresolvableBlocksAborts(_GeneratorFixtureBase):
    """A `blocks:` entry naming no scanned item is a data error, never a
    silent drop -- generation must abort naming both the file and the id,
    in every mode, with no index file written."""

    def test_write_mode_refuses_naming_file_and_id(self):
        path = self.write_item("001", title="Dangling blocker", blocks=["999"])

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn(str(path), err)
        self.assertIn("999", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_report_mode_also_refuses(self):
        self.write_item("001", title="Dangling blocker", blocks=["999"])

        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 2)
        self.assertIn("999", err)


class TestReciprocalBlocksEdge(_GeneratorFixtureBase):
    """A reciprocal blocks: edge (A blocks B and B blocks A) is reported,
    never silently accepted or reversed. Report modes still reach
    measurement; only --write treats it as refused."""

    def setUp(self):
        super().setUp()
        self.write_item("007", title="A", blocks=["009"])
        self.write_item("009", title="B", blocks=["007"])

    def test_report_mode_exits_one_and_still_measures(self):
        code, out, err = self.run_main("--dry-run")

        self.assertEqual(code, 1)
        self.assertIn("reciprocal blocks edge", err)
        # Measurement still ran -- the report-mode disposition never
        # short-circuits before build_index_files.
        self.assertIn("00-Index-Backlog.md", out)

    def test_write_mode_refuses_and_writes_nothing(self):
        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertIn("reciprocal blocks edge", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())


class TestScannerSkipsOwnGeneratedArtifacts(_GeneratorFixtureBase):
    """`is_generated_index_file` must be invisible to the scanner (so a
    second run never re-ingests its own shard as an item), while an
    ordinary frontmatter-less item-like file still aborts the scan by
    name -- the filter is scoped to this module's own naming shape, not
    "any file lacking frontmatter"."""

    def test_predicate_matches_only_this_modules_own_shapes(self):
        self.assertTrue(gbi.is_generated_index_file("Index-Backlog-001-100.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog-101-200.md"))
        self.assertFalse(gbi.is_generated_index_file("BB-500-01-BUG-NoFrontmatter.md"))

    def test_shard_named_file_skipped_ordinary_file_aborts(self):
        self.write_item("999", title="Real archived item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-999-01-PROC-Fixture.md")
        (self.archive_dir / "Index-Backlog-001-100.md").write_text(
            "not a real item\n", encoding="utf-8"
        )

        index_path = self.backlog_dir / "00-Index-Backlog.md"
        items = gbi.scan_backlog(self.backlog_dir, self.archive_dir, index_path)
        self.assertEqual([i["id"] for i in items], ["999"])

        (self.archive_dir / "BB-500-01-BUG-NoFrontmatter.md").write_text(
            "also not a real item\n", encoding="utf-8"
        )
        with self.assertRaises(gbi.GeneratorError) as ctx:
            gbi.scan_backlog(self.backlog_dir, self.archive_dir, index_path)
        self.assertIn("BB-500-01-BUG-NoFrontmatter.md", str(ctx.exception))


class TestStaleGeneratedFileDriftAndRemoval(_GeneratorFixtureBase):
    """The only delete this generator performs: a stale generated file (on
    disk, matching its own naming predicate, but absent from the freshly
    computed set) is drift for --check and removed by --write -- and
    nothing else is ever touched. This is the load-bearing guarantee."""

    def test_check_names_it_write_removes_only_it(self):
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("990", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-990-01-PROC-Fixture.md")
        self.run_main("--write")

        planted = self.archive_dir / "Index-Backlog-500-500.md"
        planted.write_text(
            "[Back to Backlog Index](../00-Index-Backlog.md)\n\nstale\n", encoding="utf-8"
        )
        # Named "00-"-prefixed like this module's other generated artifacts
        # (e.g. a changelog), so the scanner skips it too and the run never
        # aborts on it -- but its name does NOT match is_generated_index_file,
        # so it must never be reported or removed.
        unrelated = self.archive_dir / "00-Other-Artifact.md"
        unrelated.write_text("unrelated file, not generated, not an item\n", encoding="utf-8")
        unrelated_before = unrelated.read_bytes()
        item_files_before = {
            p: p.read_bytes() for p in self.backlog_dir.rglob("*.md")
            if not gbi.is_generated_index_file(p.name)
        }

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("Index-Backlog-500-500.md", out)
        self.assertIn("stale generated file", out)
        self.assertNotIn("Other-Artifact", out)

        code, out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertIn("Removed stale generated file", out)
        self.assertIn("Index-Backlog-500-500.md", out)

        self.assertFalse(planted.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(unrelated.read_bytes(), unrelated_before)
        for path, before in item_files_before.items():
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


class TestSplitMeasuresShippedFileNotBody(_GeneratorFixtureBase):
    """Finding F1: the split decision now measures body + wrapper, not the
    bare body. A body that used to be accepted as one leaf -- and then
    made the ASSEMBLED file overflow, refusing in every mode with a
    message that blamed an unshardable row -- must now split instead."""

    def test_body_in_boundary_window_splits_instead_of_refusing(self):
        shards_section = _one_shard_shards_section()
        wrapper_tokens = _hub_wrapper_tokens(shards_section)
        target_low = gbi.READ_TOKEN_WARN - wrapper_tokens
        target_high = gbi.READ_TOKEN_WARN

        blocks_len = _find_boundary_blocks_len(target_low, target_high)
        body_tokens = _body_tokens_for(blocks_len)

        # Guard against a vacuous pass: the pre-fix condition must actually
        # hold here -- the bare body alone is under budget (the OLD code
        # would have accepted it as one leaf), yet body + wrapper is not
        # (the OLD code's post-assembly check would then have raised).
        self.assertTrue(target_low <= body_tokens < target_high)
        self.assertLess(body_tokens, gbi.READ_TOKEN_WARN)
        self.assertGreaterEqual(body_tokens + wrapper_tokens, gbi.READ_TOKEN_WARN)

        items = _boundary_open_items(blocks_len) + [_make_item(990, status="COMPLETE", priority="Low")]
        result = gbi.build_index_files(items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive")

        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        shard_leaves = [entry for entry in result["files"] if not entry["path"].startswith("00-")]

        self.assertEqual(len(hub_leaves), 2)
        self.assertEqual(len(shard_leaves), 1)
        for entry in hub_leaves:
            self.assertLess(entry["tokens"], gbi.READ_TOKEN_WARN)
            self.assertEqual(entry["tokens"], gbi.estimate_tokens(entry["bytes"]))

    def test_write_on_boundary_fixture_exits_zero(self):
        shards_section = _one_shard_shards_section()
        wrapper_tokens = _hub_wrapper_tokens(shards_section)
        target_low = gbi.READ_TOKEN_WARN - wrapper_tokens
        target_high = gbi.READ_TOKEN_WARN
        blocks_len = _find_boundary_blocks_len(target_low, target_high)

        # Same guard as the pure-function test above, over the identical
        # in-memory recipe this on-disk fixture is built from.
        body_tokens = _body_tokens_for(blocks_len)
        self.assertTrue(target_low <= body_tokens < target_high)

        for item_id in range(1, 80):
            self.write_item(f"{item_id:03d}", status="NOT_STARTED")
        self.write_item("080", status="NOT_STARTED", blocks=["990"] * blocks_len)
        self.write_item("990", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-990-01-PROC-Fixture.md")

        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 0, err)
        self.assertTrue((self.backlog_dir / "00-Index-Backlog.md").exists())
        overflow_leaves = list(self.backlog_dir.glob("00-Index-Backlog-*.md"))
        self.assertEqual(len(overflow_leaves), 1)


class TestDuplicateRowIsAnomaly(_GeneratorFixtureBase):
    """Finding F2: a same-id duplicate row on disk must never read as
    clean, whichever copy is corrupted and wherever it physically sits --
    the old `{id: cells}` dict silently collapsed two rows into one entry
    (last-wins), so both an identical duplicate and a corrupted-first
    duplicate used to pass --check clean."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("002", title="Open item two", priority="Medium",
                         status="NOT_STARTED", abbrev="INFRA", created="2026-01-01")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"

    def _clean_row_001(self):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        clean_line = next(line for line in lines if line.strip().startswith("| 001 |"))
        return lines, clean_line

    def test_corrupted_first_duplicate_is_one_anomaly_never_last_wins(self):
        lines, clean_line = self._clean_row_001()
        cells = split_row_cells(clean_line)
        cells[gbi.COL_PRIORITY] = "Low"
        cells[gbi.COL_STATUS] = "COMPLETE"
        corrupted_line = "|" + "|".join(f" {c} " for c in cells) + "|"
        insert_at = lines.index(clean_line)
        lines.insert(insert_at, corrupted_line)  # corrupted copy planted BEFORE the clean one
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        duplicate_lines = [line for line in out.split("\n") if "duplicate" in line and "001" in line]
        self.assertEqual(len(duplicate_lines), 1)
        self.assertIn("duplicate row for id 001", out)

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        rewritten = (self.backlog_dir / "00-Index-Backlog.md").read_text(encoding="utf-8")
        rows_001 = [line for line in rewritten.split("\n") if line.strip().startswith("| 001 |")]
        self.assertEqual(len(rows_001), 1)

    def test_identical_duplicate_is_also_an_anomaly(self):
        lines, clean_line = self._clean_row_001()
        insert_at = lines.index(clean_line)
        lines.insert(insert_at, clean_line)  # an exact duplicate of the clean row
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("duplicate row for id 001", out)


class TestStaleScoreShowsValuesAndNonNumericOpenIsDrift(_GeneratorFixtureBase):
    """Finding F3: the stale-score report must show both the on-disk and
    fresh Score values, not only the id, and a non-numeric on-disk Score
    on an OPEN item is drift -- missing/corrupted data, never ordinary
    time-driven aging -- while a CLOSED item's `-` convention (both sides
    already render `-`) never even reaches that branch."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item one", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("003", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="DOC", created="2025-06-01",
                         archived=True, filename="BB-003-01-DOC-Fixture.md")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"

    def _set_item_001_score(self, new_score):
        text = self.hub_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        patched = []
        for line in lines:
            if line.strip().startswith("| 001 |"):
                cells = split_row_cells(line)
                cells[gbi.COL_SCORE] = new_score
                patched.append("|" + "|".join(f" {c} " for c in cells) + "|")
            else:
                patched.append(line)
        self.hub_path.write_text("\n".join(patched), encoding="utf-8")

    def test_numeric_on_disk_score_reports_both_values(self):
        self._set_item_001_score("999")

        code, out, _err = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("999 -> ", out)

        code, out, _err = self.run_main("--check", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["stale_score"]), 1)
        self.assertEqual(payload["stale_score"][0]["on_disk"], "999")
        self.assertTrue(payload["stale_score"][0]["fresh"].isdigit())

    def test_non_numeric_score_on_open_item_is_drift(self):
        self._set_item_001_score("-")

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("001", out)
        self.assertIn("non-numeric on an open item", out)
        self.assertNotIn("Stale scores", out)

    def test_closed_item_dash_score_is_never_drift(self):
        # Item 003 is closed -- its fresh render is ALSO "-", so an
        # unmodified closed row never reaches the Score-only comparison
        # branch, let alone the non-numeric-on-open narrowing.
        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 0)
        self.assertIn("No drift detected", out)


class TestDuplicateItemIdRefusedAtScan(_GeneratorFixtureBase):
    """CR1 (pre-commit review, Finding 1): two item files sharing one id
    must refuse at scan time, before any row renders, naming both paths
    and the id -- never silently emitting two rows for it (the old
    `--write` behavior) or surfacing as a raw `KeyError` (the old
    `--check` behavior)."""

    def setUp(self):
        super().setUp()
        self.path_a = self.write_item("003", title="A copy", filename="BB-003-01-BUG-A.md")
        self.path_b = self.write_item(
            "003", title="B copy", priority="Low", status="COMPLETE", abbrev="PROC",
            created="2025-01-01", archived=True, filename="BB-003-02-PROC-B.md",
        )

    def test_check_refuses_naming_both_paths_and_id(self):
        code, _out, err = self.run_main("--check")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("003", err)
        self.assertIn(str(self.path_a), err)
        self.assertIn(str(self.path_b), err)

    def test_write_refuses_and_writes_no_hub(self):
        code, _out, err = self.run_main("--write")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertFalse((self.backlog_dir / "00-Index-Backlog.md").exists())

    def test_dry_run_refuses(self):
        code, _out, err = self.run_main("--dry-run")

        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


class TestGeneratedFilePatternCoversFourDigitIds(_GeneratorFixtureBase):
    """CR2 (Finding 2): the generated-file pattern must recognize a
    4+-digit id range (`\\d{3,}`), not just the 3-digit `:03d` shape a
    too-narrow `\\d{3}` pattern produced -- a closed item with id >= 1000
    used to have its own shard re-ingested as a frontmatter-less item on
    the very next run, aborting `--check` forever after."""

    def test_pattern_matches_four_digit_ranges(self):
        self.assertTrue(gbi.is_generated_index_file("Index-Backlog-1000-1000.md"))
        self.assertTrue(gbi.is_generated_index_file("00-Index-Backlog-1000-1042.md"))

    def test_write_then_check_stays_clean_for_a_four_digit_id(self):
        self.write_item("001", title="Open item")
        self.write_item("1000", title="Old closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-1000-01-PROC-Fixture.md")

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)
        self.assertTrue((self.archive_dir / "Index-Backlog-1000-1000.md").exists())

        code, _out, _err = self.run_main("--check")
        self.assertEqual(code, 0)


class TestCrossFileDuplicateRowIsAnomaly(_GeneratorFixtureBase):
    """CR3 (Finding 3): a same-id row split across TWO different generated
    files (a stale hub copy of an item whose correct row already moved to
    its Archive shard) must be quarantined and reported exactly once,
    naming every file involved -- neither `_read_disk_table` call alone
    ever sees the collision on its own, so the old last-file-wins
    assignment into `disk_by_id` read it clean."""

    def setUp(self):
        super().setUp()
        self.write_item("001", title="Open item", priority="High",
                         status="IN_PROGRESS", abbrev="BUG", created="2026-01-01")
        self.write_item("150", title="Closed item", priority="Low",
                         status="COMPLETE", abbrev="PROC", created="2025-01-01",
                         archived=True, filename="BB-150-01-PROC-Fixture.md")
        self.run_main("--write")
        self.hub_path = self.backlog_dir / "00-Index-Backlog.md"
        self.shard_path = self.archive_dir / "Index-Backlog-150-150.md"

    def _plant_stale_hub_copy_of_150(self):
        shard_text = self.shard_path.read_text(encoding="utf-8")
        shard_row = next(
            line for line in shard_text.split("\n") if line.strip().startswith("| 150 |")
        )
        stale_row = shard_row.replace("COMPLETE", "IN_PROGRESS")

        lines = self.hub_path.read_text(encoding="utf-8").split("\n")
        insert_at = next(i for i, line in enumerate(lines) if line.strip().startswith("| 001 |"))
        lines.insert(insert_at + 1, stale_row)
        self.hub_path.write_text("\n".join(lines), encoding="utf-8")

    def test_check_names_150_and_both_files(self):
        self._plant_stale_hub_copy_of_150()

        code, out, _err = self.run_main("--check")

        self.assertEqual(code, 1)
        self.assertIn("duplicate row for id 150", out)
        self.assertIn("00-Index-Backlog.md", out)
        self.assertIn("Archive/Index-Backlog-150-150.md", out)

    def test_write_leaves_exactly_one_150_row(self):
        self._plant_stale_hub_copy_of_150()

        code, _out, _err = self.run_main("--write")
        self.assertEqual(code, 0)

        hub_rows = [
            line for line in self.hub_path.read_text(encoding="utf-8").split("\n")
            if line.strip().startswith("| 150 |")
        ]
        shard_rows = [
            line for line in self.shard_path.read_text(encoding="utf-8").split("\n")
            if line.strip().startswith("| 150 |")
        ]
        self.assertEqual(len(hub_rows) + len(shard_rows), 1)


class TestHubDirectoryListsOverflowLeaves(unittest.TestCase):
    """CR4 (Finding 4): the hub's '## Shards' directory must list every
    hub OVERFLOW leaf a split produces, not just Archive shards -- a
    split-off leaf that exists on disk but is not listed in leaf 0 is
    unreachable to any reader who never thinks to look for a same-
    directory sibling file."""

    def test_hub_split_leaves_are_listed_backlinked_and_under_budget(self):
        items = _hub_splitting_items() + [_make_item(990, status="COMPLETE", priority="Low")]

        result = gbi.build_index_files(items, _PURE_BACKLOG_DIR, _PURE_BACKLOG_DIR / "Archive")
        hub_leaves = [entry for entry in result["files"] if entry["path"].startswith("00-")]
        self.assertGreater(len(hub_leaves), 1)

        leaf0 = next(entry for entry in hub_leaves if entry["path"] == "00-Index-Backlog.md")
        overflow_leaves = [entry for entry in hub_leaves if entry is not leaf0]
        self.assertGreater(len(overflow_leaves), 0)

        for entry in hub_leaves:
            self.assertLess(entry["tokens"], gbi.READ_TOKEN_WARN)
        for entry in overflow_leaves:
            self.assertIn(f"]({entry['path']})", leaf0["content"])
            self.assertIn("[Back to Backlog Index](00-Index-Backlog.md)", entry["content"])


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


class TestFactor2RekeyReachesGenerator(unittest.TestCase):
    """`compute_scores_for_items`'s frontmatter-shaped adapter carries no
    `abbrev` key of its own -- confirming the factor-2 re-key (`abbrev ==
    "BUG"`, not a Bug/Fix keyword regex over the title; BIR-S02-02-04)
    reaches this module's UNMODIFIED `compute_scores_for_items`
    automatically, with no edit to this file's production code."""

    def test_bug_item_without_keyword_beats_non_bug_item_by_the_bonus(self):
        tmp = Path(tempfile.mkdtemp(prefix="generate_backlog_index_rekey_test_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        archive_dir = tmp / "Archive"  # never created -- count_archived_by_abbrev
        # treats an absent dir as zero counts, so momentum contributes
        # nothing to either item and cannot mask the bug/fix difference.

        config = {}
        weights = gbi.get_scoring_weights(config)

        bug_item = _make_item(901, title="Plain title, no keyword", abbrev="BUG")
        other_item = _make_item(902, title="Plain title, no keyword", abbrev="INFRA")
        items = [bug_item, other_item]

        gbi.compute_scores_for_items(items, archive_dir, config)

        # Otherwise identical inputs -- the only difference is `abbrev`, so
        # the score gap must equal exactly the configured bug/fix bonus,
        # read from config rather than assumed as a literal 15.
        self.assertEqual(
            int(bug_item["score"]) - int(other_item["score"]), weights["bug_fix_bonus"]
        )


if __name__ == "__main__":
    unittest.main()
