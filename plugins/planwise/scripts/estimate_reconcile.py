#!/usr/bin/env python
"""Reconcile every token-estimate level of a plan folder, read only.

A batch scaffold copies or leaves stale token figures at several levels at once.
This script reads every level and compares each declared figure with the figure
it is meant to equal. It writes nothing. `token_saver.py --write-estimates`
re-rolls the same levels, and this script reads the cells with that module's
parsers, so the two never disagree about what a cell holds.

Command (run with `python -B`):

    check PATH
        PATH is one plan folder, normally `Exec-{Abbrev}/`, or the plan's own
        folder for a standard pass. Every `*-Orchestration.md` under PATH (outside
        `Outputs/`) defines one session: its folder holds the session's task files,
        and the one `*-Sprint-Plan.md` in the folder above is the session's Sprint Plan.

Pairs compared, per session:

    task                  a task's `**Estimated Tokens:**` header against the
                          total after `=` on its `**Context subtotal:**` line
    task-reads            the first `~NK` term of that subtotal line (the reads term)
                          against the sum of the Required Context table's `~Tokens`
                          cells. A cell with no figure is an UNREAD line
    task-self             the `KiB` cell of the Required Context row that names the
                          task file itself, against the file's size in bytes. The
                          threshold is 3%, not 10%, and the drift ignores the 0.05 KiB
                          the cell loses by printing one decimal. A task with no such
                          row, or a row with no figure, is an UNREAD line
    orchestration-cell   each `## Session Task List` row's token cell against the
                          header of the task whose Task ID ends in the row's `#`
    orchestration-total   `**Total Estimated:**` against the sum of the task-list cells
    sprint-row            the Sprint Plan `## Sessions` row holding the session ID
                          against the Orchestration `**Total Estimated:**`
    sprint-details-cell   each task row in the `## Session Details` subsection that
                          names the session ID against that task's header
    sprint-details-total  that subsection's optional `**Total Estimated:**` against
                          the sum of its task cells

and once per Sprint Plan:

    sprint-header         `**Estimated Tokens:**` against the sum of the `## Sessions` rows

Output, one line per pair whose drift is above 10% of the expected figure, then
one line per figure that could not be read, then one total line that is always last:

    MISMATCH <level> <file>:<line> declared <a> expected <b> (<pct>%)
    UNREAD <level> <file>[:<line>] <reason>
    estimates: sessions=<n> mismatches=<m> unread=<u>

<file> is the path relative to PATH with forward slashes. A drift at or under 10%
is rounding and prints nothing. The `task-self` level has its own limit of 3%. For
that level the line reads `declared <a> KiB expected <b> KiB (<pct>%)`. An UNREAD
line names a figure the script could not
parse, such as a `~?K` placeholder or a missing row, and does not change the exit code.

Exit codes: 0 clean, or every drift at or under 10%. 1 one or more MISMATCH lines.
2 a usage error, PATH missing or not a folder, or a plan file unreadable or not
UTF-8 (`ERROR: cannot read plan file <path>`).
"""

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True  # a direct run must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scaffold_plan as sp
from token_saver_writeback import (
    _K_TERM_RE,
    _TOKEN_HEADERS,
    _cells,
    _col,
    _fmt_kib,
    _parse_token_cell,
    _required_context_table,
    _section_bounds,
    _split_eol,
    _table_rows,
    _token_tables,
)

THRESHOLD_PCT = Decimal(10)
SELF_THRESHOLD_PCT = Decimal(3)
# A KiB cell prints one decimal, so it can sit 0.05 KiB from the size it measured.
SELF_ROUNDING_BYTES = Decimal("0.05") * 1024
KIB_CELL_RE = re.compile(r"^~?\s*(\d[\d,]*(?:\.\d+)?)$")
HEADER_RE = re.compile(r"^\*\*Estimated Tokens:\*\*")
TOTAL_RE = re.compile(r"^\*\*Total Estimated:\*\*")
SUBTOTAL_LABEL = "**Context subtotal:**"
TASK_ID_RE = re.compile(r"^\*\*Task ID:\*\*(.*)")


class PlanReadError(Exception):
    """A plan file could not be read or decoded."""


def _k(tokens):
    """1400 -> `~1.4K`, 48000 -> `~48K`."""
    value = (tokens / 1000).normalize()
    return f"~{value:f}K"


def _figure_after(line, start=0):
    """Tokens of the first `~NK` term at or after `start`, or None."""
    m = _K_TERM_RE.search(_split_eol(line)[0], start)
    return Decimal(m.group(1).replace(",", "")) * 1000 if m else None


class Checker:
    def __init__(self, root):
        self.root = root
        self.mismatches = []
        self.unread = []
        self._cache = {}

    def lines(self, path):
        if path not in self._cache:
            try:
                self._cache[path] = sp.read_lf(path).split("\n")
            except (OSError, UnicodeDecodeError) as exc:
                raise PlanReadError(f"cannot read plan file {self.rel(path)}: {exc}") from exc
        return self._cache[path]

    def rel(self, path):
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def compare(self, level, path, idx, declared, expected):
        if declared == expected:
            return
        if expected == 0:
            pct = Decimal(100)
        else:
            pct = abs(declared - expected) / expected * 100
        if pct > THRESHOLD_PCT:
            self.mismatches.append(
                f"MISMATCH {level} {self.rel(path)}:{idx + 1} declared {_k(declared)} "
                f"expected {_k(expected)} ({pct.quantize(Decimal('0.1'))}%)")

    def miss(self, level, path, reason, idx=None):
        where = self.rel(path) + (f":{idx + 1}" if idx is not None else "")
        self.unread.append(f"UNREAD {level} {where} {reason}")

    # -- task level ----------------------------------------------------------
    def task_reads(self, path, lines):
        """Compare the Required Context ~Tokens rows with the subtotal's reads term.

        A missing subtotal line is reported once, by `task`, so it stays silent here.
        """
        s_idx = next((i for i, ln in enumerate(lines) if ln.startswith(SUBTOTAL_LABEL)), None)
        if s_idx is None:
            return
        reads = _figure_after(lines[s_idx], len(SUBTOTAL_LABEL))
        if reads is None:
            self.miss("task-reads", path, "no `~NK` reads term on the Context subtotal line", s_idx)
            return
        table = _required_context_table(lines)
        if table is None:
            self.miss("task-reads", path, "no Required Context table", s_idx)
            return
        header_idx, header = table
        tok = _col(header, _TOKEN_HEADERS)
        if tok is None:
            self.miss("task-reads", path, "no ~Tokens column in the Required Context table",
                      s_idx)
            return
        values = []
        for r in _table_rows(lines, header_idx):
            cells = _cells(_split_eol(lines[r])[0], len(header))
            value = _parse_token_cell(cells[tok]) if len(cells) == len(header) else None
            if value is None:
                self.miss("task-reads", path, "a Required Context row has no figure in the "
                          "~Tokens cell", r)
                return
            values.append(value)
        if values:
            self.compare("task-reads", path, s_idx, reads, sum(values, Decimal(0)))

    def task_self(self, path, lines):
        """Compare the KiB cell of the row that names this task file with its bytes.

        A task with no Required Context table is reported once, by `task-reads`,
        so it stays silent here.
        """
        table = _required_context_table(lines)
        if table is None:
            return
        header_idx, header = table
        file_col = next((i for i, c in enumerate(header) if c.startswith("file")), None)
        kib_col = _col(header, ("kib",))
        if file_col is None or kib_col is None:
            self.miss("task-self", path, "no File or KiB column in the Required Context table",
                      header_idx)
            return
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PlanReadError(f"cannot read plan file {self.rel(path)}: {exc}") from exc
        found = False
        for r in _table_rows(lines, header_idx):
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if len(cells) != len(header) or not self._names_file(cells[file_col], path):
                continue
            found = True
            m = KIB_CELL_RE.match(cells[kib_col].replace("`", "").replace("**", "").strip())
            if m is None:
                self.miss("task-self", path, "no figure in the KiB cell of the row that names "
                          "this task file", r)
                continue
            declared = Decimal(m.group(1).replace(",", ""))
            drift = abs(declared * 1024 - size)
            pct = Decimal(100) if size == 0 else drift / size * 100
            allowed = max(Decimal(0), drift - SELF_ROUNDING_BYTES)
            if (Decimal(100) if size == 0 else allowed / size * 100) > SELF_THRESHOLD_PCT:
                self.mismatches.append(
                    f"MISMATCH task-self {self.rel(path)}:{r + 1} declared {declared:f} KiB "
                    f"expected {_fmt_kib(size)} KiB ({pct.quantize(Decimal('0.1'))}%)")
        if not found:
            self.miss("task-self", path, "no Required Context row names this task file",
                      header_idx)

    @staticmethod
    def _names_file(cell, path):
        """True when a File cell is the bare path of `path`, with no span after it."""
        raw = cell.replace("`", "").replace("**", "").strip().strip("<>").strip()
        raw = raw.replace("\\", "/")
        return bool(raw) and " " not in raw and raw.rsplit("/", 1)[-1] == path.name

    def task(self, path):
        """(task number, header tokens or None) after checking header against subtotal."""
        lines = self.lines(path)
        self.task_reads(path, lines)
        self.task_self(path, lines)
        task_id = next((m.group(1) for ln in lines if (m := TASK_ID_RE.match(ln))), "")
        num = re.search(r"-(\d+)\s*$", task_id.replace("`", "").replace("*", "").strip())
        num = int(num.group(1)) if num else None
        h_idx = next((i for i, ln in enumerate(lines) if HEADER_RE.match(ln)), None)
        header = _figure_after(lines[h_idx]) if h_idx is not None else None
        if header is None:
            self.miss("task", path, "no figure on the **Estimated Tokens:** line"
                      if h_idx is not None else "no **Estimated Tokens:** line", h_idx)
            return num, None
        s_idx = next((i for i, ln in enumerate(lines) if ln.startswith(SUBTOTAL_LABEL)), None)
        if s_idx is None:
            self.miss("task", path, "no **Context subtotal:** line")
            return num, header
        body = _split_eol(lines[s_idx])[0]
        total = _figure_after(body, body.rindex("=")) if "=" in body else None
        if total is None:
            self.miss("task", path, "no `= ~NK` total on the Context subtotal line", s_idx)
            return num, header
        self.compare("task", path, h_idx, header, total)
        return num, header

    # -- task tables (Orchestration and Session Details) ---------------------
    def task_table(self, path, bounds, headers, cell_level, total_level, total_required):
        """Check each numbered row against `headers`; return the session total or None."""
        lines = self.lines(path)
        tables = [t for t in _token_tables(lines, *bounds)
                  if _col(t[3], ("#",)) is not None and _col(t[3], ("task",)) is not None]
        if len(tables) != 1:
            self.miss(cell_level, path, f"{len(tables)} tables with #, Task and token columns",
                      bounds[0])
            return None
        _, tok, rows, header = tables[0]
        num_idx = _col(header, ("#",))
        values, numbers = [], []
        for r in rows:
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if len(cells) != len(header) or not cells[num_idx].strip().isdigit():
                continue
            n = int(cells[num_idx].strip())
            numbers.append(n)
            value = _parse_token_cell(cells[tok])
            if value is None:
                self.miss(cell_level, path, f"row {n} has no figure in {cells[tok].strip()!r}", r)
                values.append(None)
                continue
            values.append(value)
            if headers.get(n) is not None:
                self.compare(cell_level, path, r, value, headers[n])
        for n in sorted(set(headers) - set(numbers)):
            self.miss(cell_level, path, f"no row numbered {n}", bounds[0])
        idx = next((i for i in range(*bounds) if TOTAL_RE.match(lines[i])), None)
        if idx is None:
            if total_required:
                self.miss(total_level, path, "no **Total Estimated:** line", bounds[0])
            return None
        total = _figure_after(lines[idx])
        if total is None:
            self.miss(total_level, path, "no figure on the **Total Estimated:** line", idx)
            return None
        if None not in values:
            self.compare(total_level, path, idx, total, sum(values, Decimal(0)))
        return total

    # -- sprint plan ---------------------------------------------------------
    def sessions_rows(self, path):
        """[(line index, cells, token col, header)] of the `## Sessions` token table."""
        lines = self.lines(path)
        bounds = _section_bounds(lines, "Sessions")
        if bounds is None:
            return None
        out = []
        for _, tok, rows, header in _token_tables(lines, *bounds):
            for r in rows:
                cells = _cells(_split_eol(lines[r])[0], len(header))
                if len(cells) == len(header):
                    out.append((r, cells, tok))
        return out

    def sprint_header(self, path):
        lines = self.lines(path)
        rows = self.sessions_rows(path)
        if rows is None:
            self.miss("sprint-header", path, "no ## Sessions section")
            return
        values = [_parse_token_cell(c[tok]) for _, c, tok in rows if c[0].strip().isdigit()]
        if not values or None in values:
            self.miss("sprint-header", path, "a ## Sessions row has no figure"
                      if values else "no numbered ## Sessions row")
            return
        idx = next((i for i, ln in enumerate(lines) if HEADER_RE.match(ln)), None)
        declared = _figure_after(lines[idx]) if idx is not None else None
        if declared is None:
            self.miss("sprint-header", path, "no figure on the **Estimated Tokens:** line"
                      if idx is not None else "no **Estimated Tokens:** line", idx)
            return
        self.compare("sprint-header", path, idx, declared, sum(values, Decimal(0)))

    def sprint_session(self, path, session_id, orch_total, headers):
        lines = self.lines(path)
        rows = self.sessions_rows(path)
        if rows is None:
            self.miss("sprint-row", path, "no ## Sessions section")
        else:
            hits = [(r, c, tok) for r, c, tok in rows
                    if any(x.replace("`", "").strip() == session_id for x in c)]
            if len(hits) != 1:
                self.miss("sprint-row", path, f"{len(hits)} ## Sessions rows hold {session_id}")
            else:
                r, cells, tok = hits[0]
                value = _parse_token_cell(cells[tok])
                if value is None:
                    self.miss("sprint-row", path, f"no figure in {cells[tok].strip()!r}", r)
                elif orch_total is not None:
                    self.compare("sprint-row", path, r, value, orch_total)
        details = _section_bounds(lines, "Session Details")
        if details is None:
            return
        id_re = rf"(?<![\w-]){re.escape(session_id)}(?![\w-])"
        start = next((i for i in range(*details) if re.match(r"^###\s", lines[i])
                      and re.search(id_re, lines[i])), None)
        if start is None:
            self.miss("sprint-details-cell", path, f"no ### subsection names {session_id}",
                      details[0])
            return
        stop = next((j for j in range(start + 1, details[1])
                     if re.match(r"^#{1,3}\s", lines[j])), details[1])
        self.task_table(path, (start, stop), headers, "sprint-details-cell",
                        "sprint-details-total", total_required=False)

    # -- the walk ------------------------------------------------------------
    def run(self):
        files = sp.collect_plan_files([self.root])
        orchestrations = [f for f in files if sp.file_kind(str(f)) == "orchestration"]
        sprint_plans = set()
        for orch in orchestrations:
            session_dir = orch.parent
            tasks = sorted(f for f in files if f.parent == session_dir
                           and sp.file_kind(str(f)) == "task")
            headers = {}
            for t in tasks:
                num, header = self.task(t)
                if num is not None:
                    headers[num] = header
            lines = self.lines(orch)
            bounds = _section_bounds(lines, "Session Task List") or (0, len(lines))
            orch_total = self.task_table(orch, bounds, headers, "orchestration-cell",
                                         "orchestration-total", total_required=True)
            session_id = orch.name[: -len("-Orchestration.md")]
            plans = sorted(session_dir.parent.glob("*-Sprint-Plan.md"))
            if len(plans) != 1:
                self.miss("sprint-row", orch, f"{len(plans)} *-Sprint-Plan.md files in the "
                          "folder above the session")
                continue
            sprint_plans.add(plans[0])
            self.sprint_session(plans[0], session_id, orch_total, headers)
        for plan in sorted(sprint_plans):
            self.sprint_header(plan)
        return len(orchestrations)


def cmd_check(args):
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"ERROR: not a folder: {args.path}")
        return 2
    checker = Checker(root)
    try:
        sessions = checker.run()
    except PlanReadError as exc:
        print(f"ERROR: {exc}")
        return 2
    for line in checker.mismatches + checker.unread:
        print(line)
    print(f"estimates: sessions={sessions} mismatches={len(checker.mismatches)} "
          f"unread={len(checker.unread)}")
    return 1 if checker.mismatches else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Reconcile the token-estimate levels of a plan folder (read only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one plan folder")
    c.add_argument("path", metavar="PATH")
    args = ap.parse_args(argv)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
