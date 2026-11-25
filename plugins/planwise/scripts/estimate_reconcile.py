#!/usr/bin/env python
"""Reconcile every token-estimate level of a plan folder, read only.

A batch scaffold copies or leaves stale token figures at several levels at once.
This script reads every level and compares each declared figure with the figure
it is meant to equal. It writes nothing. `token_saver.py --write-estimates`
re-rolls the same levels, and this script reads the cells with that module's
parsers, so the two never disagree about what a cell holds.

Command (run with `python -B`):

    check PATH [--config FILE]
        PATH is one plan folder, normally `Exec-{Abbrev}/`, or the plan's own
        folder for a standard pass. Every `*-Orchestration.md` under PATH (outside
        `Outputs/`) defines one session: its folder holds the session's task files,
        and the one `*-Sprint-Plan.md` in the folder above is the session's Sprint Plan.
        --config names the config file that gives the project root, which the paths in
        a table resolve against. Without it, the write-back's own config search runs:
        it walks up from the working directory, and when it finds no config there, it
        walks up from the folder of its own script. Its notes on stderr name the config
        it found. The working directory is the root when both walks find none.

A caller in the same process runs `reconcile(path, project_root)` and reads the lines,
the counts and the exit code from the `Report` it returns.

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

The levels below read the cells that the build and the write-back derive. Each one is
silent when its table, heading or line is absent, as in a plan built before that cell
existed. `exact` means no drift is allowed. The other limits are 10%. No level reads a
`Role` cell or a size of the Orchestration or Recovery file. A Write-Set row that no
task cites is not compared, but a cell of it with no figure is an UNREAD line. A total
line whose table is absent or lacks the columns is an UNREAD line.

Per Orchestration with a `## Session Surface` table:

    surface-tokens        each path's `~Tokens` cell against the highest Required Context
                          cell of the task rows that carry the row's spelling, or against
                          zero when no such row has a figure
    surface-kib           the `KiB` cell against the `KiB` cell of that citing row
    surface-rows          the paths of the rows against the paths the task files name,
                          exact. A path's spelling changes when its file lands on disk or
                          is removed. The rows of one file are the ones the write-back
                          writes now, or the ones it wrote in the file's other state. An
                          extra row reads `declared 1 expected 0` on its own line, and a
                          missing one `declared 0 expected 1` on the header
    surface-total         the total line's figure against the sum of the `~Tokens` cells
    surface-files         the total line's file count against the number of rows, exact

Per Sprint Plan with a sized `## Write-Set` table:

    writeset-tokens       the `~Tokens` cell of each path a task cites against the
                          highest citing cell of the sprint's task files
    writeset-kib          the `KiB` cell against the `KiB` cell of that citing row

Per Master Plan with a sized `### Write-Sets` table or a `**Write-set total:**` line:

    master-count          each row's `Count` against the distinct paths of the sprint's
                          Write-Set, exact
    master-sizes          each row's `KiB` and `~Tokens` against the sum over those paths,
                          each at its highest figure
    master-total          the total line's figure against the sum over the distinct paths
                          of all sprints, each at its highest figure
    master-files          the total line's path count against those paths, exact

The write-back changes no cell of a sprint that has no sized Write-Set or has a row with
no figure, and then it leaves the total line too. These cells are not compared, and one
UNREAD line per such sprint says so.

Output, one line per pair whose drift is above 10% of the expected figure, then
one line per figure that could not be read, then one total line that is always last:

    MISMATCH <level> <file>:<line> declared <a> expected <b> (<pct>%)
    UNREAD <level> <file>[:<line>] <reason>
    estimates: sessions=<n> mismatches=<m> unread=<u>

<file> is the path relative to PATH with forward slashes. A drift at or under 10%
is rounding and prints nothing, except at an exact level, which has no limit. The
`task-self` level has its own limit of 3%. A `KiB` cell prints as
`declared <a> KiB expected <b> KiB (<pct>%)`, and an exact level prints plain numbers.
An UNREAD line names a figure the script could not
parse, such as a `~?K` placeholder or a missing row, and does not change the exit code.

Exit codes: 0 clean, or every drift at or under 10%. 1 one or more MISMATCH lines.
2 a usage error, PATH missing or not a folder, or a plan file unreadable or not
UTF-8 (`ERROR: cannot read plan file <path>`), or a config file that cannot be read,
whether `--config` names it or the search found it, or any other error that stops the
check (`ERROR: <type>: <message>`). The search passes over a file it cannot open or
decode, so only a found file that does not parse stops the check.
"""

import argparse
import contextlib
import io
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

sys.dont_write_bytecode = True  # a direct run must not grow scripts/__pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader
import scaffold_plan as sp
from token_saver_scan import config_project_root
from token_saver_writeback import (
    _K_TERM_RE,
    _KIB_CELL_RE,
    _MASTER_LABEL,
    _SURFACE_LABEL,
    _TOKEN_HEADERS,
    _WRITE_SET_COLUMNS,
    _Buffers,
    _cells,
    _col,
    _fmt_k,
    _fmt_kib,
    _identity,
    _is_orchestration,
    _parse_token_cell,
    _required_context_table,
    _section_bounds,
    _split_eol,
    _sprint_plan_rows,
    _surface_key,
    _surface_tasks,
    _table_rows,
    _token_tables,
    _write_set_table,
    keyed_write_set,
    path_figures,
    surface_entries,
    write_set_sums,
    write_set_total,
    writeset_figures,
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
OVER_RE = re.compile(r"\bover (\d[\d,]*)\b")
FOUND_CONFIG_RE = re.compile(r"found config at (.+)")
# A root that holds no file: nothing exists below a file, and the depth outlasts any `../`.
NO_FILES = Path(__file__).resolve().joinpath(*["-"] * 24)


class PlanReadError(Exception):
    """A plan file could not be read or decoded."""


def error_text(exc):
    """One line that names an error. A `PlanReadError` is its own message."""
    if isinstance(exc, PlanReadError):
        return str(exc)
    first = next(iter(str(exc).splitlines()), "")
    return f"{type(exc).__name__}: {first}" if first else type(exc).__name__


def _k(tokens):
    """1400 -> `~1.4K`, 48000 -> `~48K`."""
    value = (tokens / 1000).normalize()
    return f"~{value:f}K"


def _figure_after(line, start=0):
    """Tokens of the first `~NK` term at or after `start`, or None."""
    m = _K_TERM_RE.search(_split_eol(line)[0], start)
    return Decimal(m.group(1).replace(",", "")) * 1000 if m else None


def _kib(size):
    """1.50 -> `1.50 KiB`, the figure as its cell prints it."""
    return f"{size:f} KiB"


def _kib_figure(cell):
    """The figure of a `KiB` cell, or None."""
    m = KIB_CELL_RE.match(cell.replace("`", "").replace("**", "").strip())
    return Decimal(m.group(1).replace(",", "")) if m else None


def _over_count(line):
    """The count of an `over N files` or `over N distinct paths` line, or None."""
    m = OVER_RE.search(line)
    return Decimal(m.group(1).replace(",", "")) if m else None


def _context_cells(tasks):
    """(task path, File cell) of each Required Context row that `surface_entries` reads."""
    for path, text in tasks:
        lines = text.split("\n")
        table = _required_context_table(lines)
        head, header = table or (0, [])
        file_at = next((i for i, c in enumerate(header) if c.startswith("file")), None)
        for r in _table_rows(lines, head) if file_at is not None else ():
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if file_at < len(cells):
                yield path, cells[file_at]


class Checker:
    def __init__(self, root, project_root):
        self.root = root
        self.project_root = project_root
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

    def compare(self, level, path, idx, declared, expected, show=_k, limit=THRESHOLD_PCT):
        if declared == expected:
            return
        if expected == 0:
            pct = Decimal(100)
        else:
            pct = abs(declared - expected) / expected * 100
        if pct > limit:
            self.mismatches.append(
                f"MISMATCH {level} {self.rel(path)}:{idx + 1} declared {show(declared)} "
                f"expected {show(expected)} ({pct.quantize(Decimal('0.1'))}%)")

    def exact(self, level, path, idx, declared, expected):
        """Compare two counts with no drift allowed."""
        self.compare(level, path, idx, Decimal(declared), Decimal(expected), str, Decimal(0))

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
            declared = _kib_figure(cells[kib_col])
            if declared is None:
                self.miss("task-self", path, "no figure in the KiB cell of the row that names "
                          "this task file", r)
                continue
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

    # -- derived cells -------------------------------------------------------
    def derived(self, level, path, check):
        """Run one derived check. A figure it cannot derive is an UNREAD line."""
        try:
            check(path)
        except PlanReadError:
            raise
        except Exception as exc:  # noqa: BLE001 - one odd cell never stops the other levels
            self.miss(level, path, f"not derived ({error_text(exc)})")

    def folder_tasks(self, folder):
        """(path, text) of each task file in a session folder, read as the write-back reads it."""
        try:
            return [t for t in _surface_tasks(_Buffers(), folder) if not _is_orchestration(t[0])]
        except OSError as exc:
            raise PlanReadError(f"cannot read plan file in {self.rel(folder)}: {exc}") from exc

    def sprint_tasks(self, sprint_dir):
        return [t for folder in sorted(sprint_dir.iterdir()) if folder.is_dir()
                for t in self.folder_tasks(folder)]

    def sized(self, level, path, idx, cells, tok_at, kib_at, tokens, kib):
        """Compare one row's `~Tokens` and `KiB` cells with the citing cells `tokens` and `kib`."""
        for name, at, read, expected, show in (("tokens", tok_at, _parse_token_cell, tokens, _k),
                                               ("kib", kib_at, _kib_figure, kib, _kib)):
            declared = read(cells[at])
            if declared is None:
                self.miss(f"{level}-{name}", path, f"no figure in {cells[at].strip()!r}", idx)
            elif expected is not None and read(expected) is None:
                self.miss(f"{level}-{name}", path, f"its citing row has no figure in {expected!r}", idx)
            elif expected is not None:
                self.compare(f"{level}-{name}", path, idx, declared, read(expected), show)

    def total_line(self, levels, path, idx, label, total, count):
        """Compare a derived total line's figure and count. A None expectation is not compared."""
        line = self.text_lines(path)[idx]
        declared = _figure_after(line, len(label))
        if declared is None:
            self.miss(levels[0], path, f"no figure on the {label} line", idx)
        elif total is not None:
            self.compare(levels[0], path, idx, declared, total)
        declared = _over_count(line)
        if declared is None:
            self.miss(levels[1], path, f"no count on the {label} line", idx)
        elif count is not None:
            self.exact(levels[1], path, idx, declared, count)

    def text_lines(self, path):
        """The lines of a file that no other level reads, so a stray byte in it is no error."""
        if path not in self._cache:
            try:
                text = path.read_bytes().decode("utf-8", errors="replace")
            except OSError as exc:
                raise PlanReadError(f"cannot read plan file {self.rel(path)}: {exc}") from exc
            self._cache[path] = text.replace("\r\n", "\n").split("\n")
        return self._cache[path]

    def surface_rows(self, orch, tasks, plan_files):
        """Per named file, the row sets a correct table may hold, as {row path: surface entry}.

        The first set is what the producer writes now. The second is what it wrote before the
        file landed. An absent file may have been there at the write, so the sets after those
        hold its one key as a path from each folder the producer looks in. A file of two or more
        keys gets no such set: its single landed row would hide the other rows' deletion.
        """
        session_dir, root = orch.parent, self.project_root
        plan_dir = session_dir.parent.parent
        away_dir = NO_FILES / session_dir.parent.name / session_dir.name
        states = []
        for folder, plan_at, root_at in ((session_dir, plan_dir, root), (away_dir, NO_FILES, NO_FILES)):
            placed = [(folder / path.name, text) for path, text in tasks]
            own = dict.fromkeys([*plan_files, *(p.name for p, _ in placed)], folder)
            entries = {e["path"]: e for e in surface_entries(
                placed, [(name, None, None) for name in plan_files], plan_at, root_at)}
            keys = [_surface_key(cell, path, own, plan_at, root_at)
                    for path, cell in _context_cells(placed)]
            states.append((own, entries, [*own, *keys]))
        (own, now, keys_now), (_own, before, keys_before) = states
        files = {}
        for key, earlier in zip(keys_now, keys_before):
            if key is not None:
                sets = files.setdefault(_identity(key, own, root), ({}, {}))
                sets[0][key] = now[key]
                if earlier is not None:
                    sets[1][earlier] = before[earlier]
        folders = [session_dir, plan_dir, *(p for p in plan_dir.parents if root in p.parents)]
        out = []
        for identity, (present, earlier) in files.items():
            options = [present, earlier]
            if len(present) == 1 and identity not in own and not (root / identity).is_file():
                ((key, entry),) = present.items()
                options += [{path: entry} for path in (
                    identity, *(_identity((at / key).as_posix(), own, root) for at in folders))]
            out.append(options)
        return out

    def surface(self, orch):
        lines = self.lines(orch)
        bounds = _section_bounds(lines, "Session Surface")
        if bounds is None:
            return
        total_at = next((i for i in range(*bounds) if lines[i].startswith(_SURFACE_LABEL)), None)
        table = _write_set_table(lines, bounds, [("path",), ("kib",), _TOKEN_HEADERS])
        if table is None:
            if total_at is not None:
                self.miss("surface-total", orch, "no table with Path, KiB and ~Tokens columns", total_at)
            return
        head, (path_at, kib_at, tok_at), width = table
        rows = {r: _cells(_split_eol(lines[r])[0], width) for r in _table_rows(lines, head)}
        names = {r: cells[path_at].replace("`", "").strip() for r, cells in rows.items()
                 if len(cells) == width}
        plan_files = [orch.name, orch.name.replace("Orchestration", "Recovery")]
        expected = {}
        for options in self.surface_rows(orch, self.folder_tasks(orch.parent), plan_files):
            held = [set(names.values()) & set(option) for option in options]
            # The set that the rows match best. A tie goes to the first.
            best = min(range(len(options)), key=lambda i: (-len(held[i]), len(options[i]) - len(held[i])))
            for key, entry in options[best].items():  # two files of one landed row: the higher figure
                if key not in expected or (entry["tokens"] or 0) > (expected[key]["tokens"] or 0):
                    expected[key] = entry
        values, seen = [], {}
        for r, cells in rows.items():
            if r not in names:
                self.miss("surface-rows", orch, "cell count differs from the header", r)
                values.append(None)
                continue
            name = names[r]
            seen[name] = seen.get(name, 0) + 1
            entry = expected.get(name)
            if entry is None:
                self.exact("surface-rows", orch, r, 1, 0)
            elif seen[name] > 1:
                self.exact("surface-rows", orch, r, seen[name], 1)
            values.append(_parse_token_cell(cells[tok_at]))
            sized = entry is not None and name not in plan_files
            self.sized("surface", orch, r, cells, tok_at, kib_at,
                       _fmt_k(entry["tokens"] or 0) if sized else None, entry["kib"] if sized else None)
        if len(names) == len(rows):  # an unreadable row may be the missing one
            for _ in set(expected) - set(seen):
                self.exact("surface-rows", orch, head, 0, 1)
        if total_at is not None:
            self.total_line(("surface-total", "surface-files"), orch, total_at, _SURFACE_LABEL,
                            None if None in values else sum(values, Decimal(0)), len(rows))

    def writeset(self, plan):
        lines = self.lines(plan)
        table = _write_set_table(lines, _section_bounds(lines, "Write-Set"), _WRITE_SET_COLUMNS)
        if table is None:
            return
        head, (path_at, task_at, kib_at, tok_at), width = table
        rows = []
        for r in _table_rows(lines, head):
            cells = _cells(_split_eol(lines[r])[0], width)
            if len(cells) == width:
                rows.append((r, cells))
            else:
                self.miss("writeset-tokens", plan, "cell count differs from the header", r)
        figures = writeset_figures([(c[path_at], c[task_at]) for _, c in rows],
                                   self.sprint_tasks(plan.parent), {}, plan.parent.parent,
                                   self.project_root)
        for (r, cells), (kib, tokens, source) in zip(rows, figures):
            if source == "no path":
                continue
            cited = source == "cited"
            self.sized("writeset", plan, r, cells, tok_at, kib_at,
                       tokens if cited else None, kib if cited else None)
            cell = cells[kib_at].strip()
            if _kib_figure(cell) is not None and _KIB_CELL_RE.match(cell) is None:
                self.miss("writeset-kib", plan, f"no figure in {cell!r} that the sum reads", r)

    def master(self, master):
        lines = self.text_lines(master)
        start = next((i for i, ln in enumerate(lines) if re.match(r"^###\s+Write-Sets\b", ln)), None)
        if start is None:
            return
        stop = next((j for j in range(start + 1, len(lines)) if re.match(r"^#{1,3}\s", lines[j])),
                    len(lines))
        table = _write_set_table(lines, (start, stop),
                                 [("sprint",), ("count",), ("kib",), _TOKEN_HEADERS])
        total_at = next((i for i in range(start, stop) if lines[i].startswith(_MASTER_LABEL)), None)
        if table is None and total_at is None:
            return
        plan_dir = master.parent
        at = start if total_at is None else total_at
        if len(list(plan_dir.glob("*-Master-Plan.md"))) != 1:
            self.miss("master-sizes", master, "not compared: the folder holds more than one Master Plan", at)
            return
        folders, tasks = {}, []
        for folder in sorted(p for p in plan_dir.iterdir() if p.is_dir()):
            m = re.match(r"Sprint-(\d+)(?:-|$)", folder.name)
            if m is not None:
                folders.setdefault(int(m.group(1)), []).append(folder)
                tasks.extend(self.sprint_tasks(folder))
        paths, no_kib = {}, set()  # a sprint whose figures the write-back cannot sum has no paths
        for number, same in folders.items():
            rows = _sprint_plan_rows(_Buffers(), same[0]) if len(same) == 1 else None
            keyed = keyed_write_set(rows or [], tasks, plan_dir, self.project_root)
            paths[number] = None if rows is None else path_figures(keyed)
            if any(_KIB_CELL_RE.match(row[2].strip()) is None for _, row in keyed):
                no_kib.add(number)  # the sum would count an unreadable cell as zero
        head, columns, width = table or (0, [], 0)
        row_of = {}
        for r in _table_rows(lines, head) if table else ():
            cells = _cells(_split_eol(lines[r])[0], width)
            if len(cells) != width:
                self.miss("master-count", master, "cell count differs from the header", r)
                continue
            sprint_at, count_at, kib_at, tok_at = columns
            m = re.match(r"Sprint-(\d+)(?!\w)", cells[sprint_at].replace("`", "").replace("*", "").strip())
            if m is None:
                self.miss("master-sizes", master, f"no sprint in {cells[sprint_at].strip()!r}", r)
                continue
            number = int(m.group(1))
            row_of.setdefault(number, r)
            known = paths.setdefault(number, None)
            if known is None:
                continue
            declared = cells[count_at].replace("`", "").replace("*", "").strip()
            if declared.isdecimal():
                self.exact("master-count", master, r, declared, len(known))
            else:
                self.miss("master-count", master, f"no figure in {declared!r}", r)
            if number in no_kib:
                self.miss("master-sizes", master, "KiB not compared: a Write-Set row of the sprint "
                          "has no KiB figure", r)
            _count, kib, tokens = write_set_sums(known)
            for cell_at, read, expected, show in ((kib_at, _kib_figure, kib, _kib),
                                                  (tok_at, _parse_token_cell, tokens, _k)):
                value = read(cells[cell_at])
                if value is None:
                    self.miss("master-sizes", master, f"no figure in {cells[cell_at].strip()!r}", r)
                elif cell_at != kib_at or number not in no_kib:
                    self.compare("master-sizes", master, r, value, read(expected), show)
        for number in sorted(n for n, known in paths.items() if known is None):
            self.miss("master-sizes", master, f"Sprint-{number:02d} and the total line are not compared: "
                      "no sized Write-Set with a figure in every row", row_of.get(number, at))
        if total_at is not None:
            summed = list(paths.values())
            if not summed:
                self.miss("master-total", master, "not compared: no sprint folder beside the Master Plan", at)
            whole = bool(summed) and None not in summed
            self.total_line(("master-total", "master-files"), master, total_at, _MASTER_LABEL,
                            _figure_after(write_set_total(summed)) if whole else None,
                            len(set().union(*summed)) if whole else None)

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
        for orch in orchestrations:
            self.derived("surface-rows", orch, self.surface)
        for plan in sorted(sprint_plans):
            self.derived("writeset-tokens", plan, self.writeset)
        for master in (f for f in files if sp.file_kind(str(f)) == "master"):
            self.derived("master-sizes", master, self.master)
        return len(orchestrations)


class Report(NamedTuple):
    """What one check of a plan folder found."""

    sessions: int
    mismatches: list
    unread: list

    @property
    def summary(self):
        return (f"estimates: sessions={self.sessions} mismatches={len(self.mismatches)} "
                f"unread={len(self.unread)}")

    @property
    def lines(self):
        """Every output line of the command, in order."""
        return [*self.mismatches, *self.unread, self.summary]

    @property
    def exit_code(self):
        return 1 if self.mismatches else 0


def reconcile(path, project_root=None):
    """Check one plan folder in process and return its `Report`. It prints and writes nothing.

    `project_root` is the root that `config_project_root` gives for the project's config.
    Without it, the working directory is the root. Raises `PlanReadError` for a `path` that
    is no folder and for a plan file that cannot be read.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise PlanReadError(f"not a folder: {path}")
    checker = Checker(root, Path(project_root or Path.cwd()).resolve())
    sessions = checker.run()
    return Report(sessions, checker.mismatches, checker.unread)


def _searched_root():
    """The root of the config that the write-back's own search finds, or None when it finds none.

    The search's notes print on stderr, because they name the config it found. A found
    config that does not parse stops the write-back, and here it raises a `PlanReadError`.
    """
    notes = io.StringIO()
    try:
        with contextlib.redirect_stderr(notes):
            root = config_project_root(config_loader.load_config())
    except SystemExit:  # no config found
        return None
    except Exception as exc:
        sys.stderr.write(notes.getvalue())
        found = FOUND_CONFIG_RE.search(notes.getvalue())
        name = found.group(1) if found else "that the search found"
        raise PlanReadError(f"cannot read config file {name}: {error_text(exc)}") from exc
    sys.stderr.write(notes.getvalue())
    return root


def cmd_check(args):
    try:
        if args.config:
            project_root = sp.config_root(args.config)  # `config_project_root` of the loaded config
            if project_root is None:
                raise PlanReadError(f"cannot read config file {args.config}")
        else:
            project_root = _searched_root()
        report = reconcile(args.path, project_root)
    except Exception as exc:  # noqa: BLE001 - exit 1 means a mismatch, so a crash never returns it
        print(f"ERROR: {error_text(exc)}")
        return 2
    for line in report.lines:
        print(line)
    return report.exit_code


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Reconcile the token-estimate levels of a plan folder (read only).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one plan folder")
    c.add_argument("path", metavar="PATH")
    c.add_argument("--config", metavar="FILE",
                   help="config file that gives the project root (else the search up from the working "
                        "directory, then up from the script's folder, else the working directory)")
    args = ap.parse_args(argv)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
