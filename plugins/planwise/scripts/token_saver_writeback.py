#!/usr/bin/env python3
"""Token Saver write-back — the `--write-estimates` mode of the large-file scan.

`token_saver_scan` owns the scan, the report and the command line. This module
owns only what the write-back needs: it prices each Required Context row of
the NAMED task files, writes the measured `KiB` and `~Tokens` cells, and
re-rolls the totals that depend on them. Those totals are the task's
`**Context subtotal:**` reads term and total, its `**Estimated Tokens:**`
header, the session Orchestration's task-list cell and `**Total Estimated:**`,
and the Sprint Plan's session row.

Run it through the facade, which owns the argument checks:

    python token_saver.py --scan --plan {plan_path} --write-estimates --task {task file}

The split follows the size of the code, not a change in behaviour. The scan's
`main()` imports this module only inside its `--write-estimates` branch, so a
plain scan never loads it. This module imports the row-parsing and
path-resolution helpers from `token_saver_scan`, so the two modules price a
file the same way.

Every change is computed in memory first and written at the end. A dry run
reports exactly what a real run would write, a second run over the same tree
writes nothing, and on any error no file is replaced.
"""

import contextlib
import os
import re
import shutil
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

from markdown_parser import (
    retried_cells,
    split_row_cells,
    split_row_cells_code_aware,
    split_row_raw,
)
from read_limits import estimate_tokens
from token_saver_scan import (
    _clean_file_cell,
    content_class_for,
    is_command_corpus,
    parse_agent,
    resolve_context_path,
    unresolved_reason,
)

# ---------------------------------------------------------------------------
# Write-back (--write-estimates)
# ---------------------------------------------------------------------------
# `{path} lines {a}-{b}`, with an optional trailing parenthetical.
_LINES_SPAN_RE = re.compile(
    r"^(?P<path>.+?)\s+lines?\s+(?P<a>\d[\d,]*)\s*[-–]\s*(?P<b>\d[\d,]*)"
    r"\s*(?:\([^()]*\))?$"
)
# `{path} §X–§Y` or `{path} §X`, with an optional trailing parenthetical.
_SECTION_SPAN_RE = re.compile(
    r"^(?P<path>.+?)\s+§\s*(?P<x>\w+(?:\.\w+)*)\.?"
    r"(?:\s*[-–]\s*§\s*(?P<y>\w+(?:\.\w+)*)\.?)?\s*(?:\([^()]*\))?$"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HEADING_TOKEN_RE = re.compile(r"^(?:§\s*|Section\s+|Part\s+)?(\w+(?:\.\w+)*)")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_NUM = r"\d[\d,]*(?:\.\d+)?"
# A breakdown after a K term: `(reads: 3.9 + 0.4)` or `tokens (24.5 + 52.6)`.
_BREAKDOWN_RE = re.compile(
    r"(?:\s+[A-Za-z][\w-]*)*\s*\((?P<label>\s*[A-Za-z][\w ]*:)?(?P<nums>[^()]*)\)"
)
_NUM_LIST_RE = re.compile(rf"^\s*{_NUM}(?:\s*\+\s*{_NUM})*\s*$")
_TOKEN_CELL_RE = re.compile(r"^~?\s*(\d[\d,]*(?:\.\d+)?)\s*([Kk])?$")
_K_TERM_RE = re.compile(r"~\s*(\d[\d,]*(?:\.\d+)?)\s*K")
_SUBTOTAL_BODY_RE = re.compile(
    r"^\s*~\s*[\d.,]+\s*K(?:\s+[A-Za-z][\w-]*)*"
    r"(?P<adds>(?:\s*[+−-]\s*~\s*[\d.,]+\s*K(?:\s+[A-Za-z][\w-]*)*)*)\s*$"
)
_ADDEND_RE = re.compile(r"([+−-])\s*~\s*(\d[\d,]*(?:\.\d+)?)\s*K")
_TOKEN_HEADERS = ("~tokens", "tokens", "est. tokens", "estimated tokens")


def _split_eol(line: str) -> tuple[str, str]:
    """Split a line (from `text.split("\\n")`) into its body and its `\\r`."""
    return (line[:-1], "\r") if line.endswith("\r") else (line, "")


def _table_header_at(lines: list[str], i: int) -> list[str] | None:
    """The header cells when line `i` opens a table (header + separator)."""
    if i + 1 >= len(lines):
        return None
    head, sep = _split_eol(lines[i])[0].strip(), _split_eol(lines[i + 1])[0].strip()
    if not (head.startswith("|") and sep.startswith("|")):
        return None
    sep_cells = split_row_cells(sep)
    if not sep_cells or not set("".join(sep_cells)) <= set("-: "):
        return None
    return [c.lower() for c in split_row_cells(head)]


def _table_rows(lines: list[str], header_idx: int) -> list[int]:
    """Line indices of the body rows of the table whose header is at `header_idx`."""
    rows = []
    i = header_idx + 2
    while i < len(lines) and _split_eol(lines[i])[0].strip().startswith("|"):
        rows.append(i)
        i += 1
    return rows


def _cells(body: str, width: int) -> list[str]:
    """Logical cells for a header of `width` columns; a code span may hold a pipe."""
    return retried_cells(body, split_row_cells(body), width)


def _raw_segments(body: str, width: int) -> list[str]:
    """`split_row_raw` segments, merged where a code span holds a pipe."""
    segments = split_row_raw(body)
    if len(split_row_cells(body)) == width:
        return segments
    lead = 1 if body.strip().startswith("|") else 0
    merged, k = segments[:lead], lead
    for cell in split_row_cells_code_aware(body, keep_escapes=True):
        parts = [segments[k]]
        k += 1
        while "|".join(parts).strip() != cell and k < len(segments):
            parts.append(segments[k])
            k += 1
        merged.append("|".join(parts))
    return merged + segments[k:]


def _rewrite_cell(line: str, cell_idx: int, value: str, width: int) -> str:
    """Replace one logical cell of a table row, keeping its padding and escapes."""
    body, eol = _split_eol(line)
    segments = _raw_segments(body, width)
    raw_idx = cell_idx + (1 if body.strip().startswith("|") else 0)
    seg = segments[raw_idx]
    m = re.match(r"^(\s*)(.*?)(\s*)$", seg, re.DOTALL)
    segments[raw_idx] = f"{m.group(1) or ' '}{value}{m.group(3) or ' '}"
    return "|".join(segments) + eol


def _parse_token_cell(cell: str) -> Decimal | None:
    """`~1.4K` -> 1400, `**~1.4K**` -> 1400, `~1,234` -> 1234; else None."""
    m = _TOKEN_CELL_RE.match(cell.replace("`", "").replace("**", "").strip())
    if not m:
        return None
    value = Decimal(m.group(1).replace(",", ""))
    return value * 1000 if m.group(2) else value


def _k_places(text: str) -> int:
    """Decimal places of the first `~N.NK` figure in `text` (0 for whole K)."""
    m = re.search(r"\d(?:\.(\d+))?\s*K", text)
    return len(m.group(1)) if m and m.group(1) else 0


def _fmt_k_at(value_k: Decimal, places: int) -> str:
    q = Decimal(1).scaleb(-places)
    return f"~{value_k.quantize(q, rounding=ROUND_HALF_UP)}K"


def _fmt_k_exact(value_k: Decimal, authored: str) -> str:
    """A sum at the authored precision, widened to 0.1K when it needs it."""
    exact = 0 if value_k == value_k.to_integral_value() else 1
    return _fmt_k_at(value_k, max(_k_places(authored), exact))


def _reroll_breakdown(line: str, pos: int, values_k: list[Decimal]) -> str | None:
    """Re-roll the `(a + b + …)` breakdown right after a K term ending at `pos`.

    Returns the line (unchanged when there is no breakdown, or when every
    authored addend already equals its source), or None when a breakdown is
    present but its addends cannot be matched one-to-one to the sources.
    """
    m = _BREAKDOWN_RE.match(line, pos)
    if not m:
        return line
    nums = m.group("nums")
    if not re.match(r"\s*\d", nums) or not (m.group("label") or "+" in nums):
        return line  # a prose parenthetical, not a breakdown
    if not _NUM_LIST_RE.match(nums):
        return None
    old = [Decimal(x.replace(",", "")) for x in re.findall(_NUM, nums)]
    if len(old) != len(values_k):
        return None
    if old == values_k:
        return line
    lead, trail = nums[:len(nums) - len(nums.lstrip())], nums[len(nums.rstrip()):]
    new = lead + " + ".join(f"{v.normalize():f}" for v in values_k) + trail
    return line[:m.start("nums")] + new + line[m.end("nums"):]


def _fmt_kib(num_bytes: int) -> str:
    """KiB as `measure_files.py` rounds and prints it."""
    return f"{round(num_bytes / 1024, 1):,}"


def _fmt_k(tokens: Decimal | int, places: str = "0.1") -> str:
    k = (Decimal(tokens) / 1000).quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return f"~{k}K"


def _file_lines(path: Path) -> list[bytes]:
    """The file's lines as bytes, each with its own line ending."""
    data = path.read_bytes()
    parts = data.split(b"\n")
    lines = [p + b"\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _line_span_bytes(path: Path, a: int, b: int) -> int | None:
    lines = _file_lines(path)
    if a < 1 or b < a or b > len(lines):
        return None
    return sum(len(x) for x in lines[a - 1:b])


def _section_span(path: Path, x: str, y: str) -> tuple[int, int, int] | None:
    """Resolve §X..§Y to (start line, end line, bytes), 1-based and inclusive.

    §X is the first heading whose number token equals X (`## 3. Name`,
    `## Section 3: Name`, `### 3.2 Name`). The span ends before the first
    heading after §Y at §Y's level or higher, or at EOF when none follows.
    Headings inside fenced code blocks are ignored. A fence closes only on
    the same character, at least as long, with no info string (CommonMark).
    """
    lines = _file_lines(path)
    headings = []
    fence = None
    for i, raw in enumerate(lines):
        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        fm = _FENCE_RE.match(text)
        if fm:
            marker = fm.group(1)
            if fence is None:
                fence = marker
            elif (marker[0] == fence[0] and len(marker) >= len(fence)
                  and not fm.group(2).strip()):
                fence = None
            continue
        if fence:
            continue
        hm = _HEADING_RE.match(text)
        if hm:
            tm = _HEADING_TOKEN_RE.match(hm.group(2))
            token = tm.group(1).rstrip(".") if tm else ""
            headings.append((i, len(hm.group(1)), token))
    start = next((h for h in headings if h[2] == x), None)
    if start is None:
        return None
    end_h = next((h for h in headings if h[2] == y and h[0] >= start[0]), None)
    if end_h is None:
        return None
    stop = next(
        (h[0] for h in headings if h[0] > end_h[0] and h[1] <= end_h[1]),
        len(lines),
    )
    return start[0] + 1, stop, sum(len(r) for r in lines[start[0]:stop])


def price_row(
    cell: str, task_path: Path, plan_root: Path, project_root: Path,
    model: str | None,
) -> dict:
    """Price one Required Context File cell, or say why it is left as authored.

    Returns {"priced": True, "bytes", "tokens", "path", "span"} or
    {"priced": False, "reason"}. A whole-file row is priced only when the
    cell holds a bare path: text after the path that is not one of the two
    span forms means the author priced something narrower than the file.
    """
    raw = cell.replace("`", "").replace("**", "").strip().strip("<>").strip()
    if not raw:
        return {"priced": False, "reason": "empty File cell"}
    if is_command_corpus(cell):
        return {"priced": False, "reason": "command corpus"}

    def _resolve(text: str) -> Path | None:
        return resolve_context_path(text, task_path, plan_root, project_root)

    span = None
    m = _LINES_SPAN_RE.match(raw)
    s = _SECTION_SPAN_RE.match(raw) if not m else None
    if m:
        resolved = _resolve(m.group("path"))
        if resolved is None:
            return {"priced": False,
                    "reason": unresolved_reason(m.group("path"), project_root)}
        a, b = int(m.group("a").replace(",", "")), int(m.group("b").replace(",", ""))
        num_bytes = _line_span_bytes(resolved, a, b)
        if num_bytes is None:
            return {"priced": False, "reason": f"span lines {a}-{b} out of range"}
        span = f"lines {a}-{b} = {b - a + 1} lines / {num_bytes:,} bytes"
    elif s:
        resolved = _resolve(s.group("path"))
        if resolved is None:
            return {"priced": False,
                    "reason": unresolved_reason(s.group("path"), project_root)}
        x, y = s.group("x"), s.group("y") or s.group("x")
        found = _section_span(resolved, x, y)
        if found is None:
            return {"priced": False, "reason": f"span §{x}–§{y} heading not found"}
        first, last, num_bytes = found
        span = (f"§{x} at :{first} → §{y} ends at :{last} = "
                f"{last - first + 1} lines / {num_bytes:,} bytes")
    else:
        if _clean_file_cell(cell) != raw:
            return {"priced": False,
                    "reason": "qualified row (text after the path is not a span form)"}
        resolved = _resolve(cell)
        if resolved is None:
            return {"priced": False, "reason": unresolved_reason(cell, project_root)}
        num_bytes = os.path.getsize(resolved)

    _, content = content_class_for(resolved)
    tokens = estimate_tokens(num_bytes, model or "", content)
    return {"priced": True, "bytes": num_bytes, "tokens": tokens,
            "path": str(resolved), "span": span}


def _required_context_table(lines: list[str]) -> tuple[int, list[str]] | None:
    """(header line index, lowered header cells) of the Required Context table."""
    in_section = False
    for i, line in enumerate(lines):
        body = _split_eol(line)[0]
        if re.match(r"^##+\s*Required Context", body):
            in_section = True
            continue
        if in_section and re.match(r"^##+\s", body):
            return None
        if in_section:
            header = _table_header_at(lines, i)
            if header is not None:
                return i, header
    return None


def _col(header: list[str], names: tuple[str, ...]) -> int | None:
    return next((i for i, c in enumerate(header) if c in names), None)


def _reroll_subtotal(line: str, reads: Decimal,
                     row_k: list[Decimal]) -> tuple[str, str, str] | str:
    """Rewrite the reads term, its breakdown and the total of a subtotal line.

    Returns (new line, new reads text, new total text), or the reason the
    line is left: it lacks the template's shape (one reads term, signed `~NK`
    addends, `= ~TK total`), or its reads breakdown does not match the rows
    one-to-one. Each figure keeps its authored precision; the reads term
    widens to 0.1K only when the rows' sum needs it.
    """
    body, eol = _split_eol(line)
    label = "**Context subtotal:**"
    if not body.startswith(label) or "=" not in body:
        return "not the template's one-line shape"
    eq = body.rindex("=")
    terms = body[len(label):eq]
    while re.search(r"\([^()]*\)", terms):
        terms = re.sub(r"\([^()]*\)", " ", terms)
    m = _SUBTOTAL_BODY_RE.match(terms)
    total_m = _K_TERM_RE.search(body, eq)
    reads_m = _K_TERM_RE.search(body, len(label))
    if not m or not total_m or not reads_m:
        return "not the template's one-line shape"
    reads_k = reads / 1000
    total_k = reads_k
    for sign, value in _ADDEND_RE.findall(m.group("adds")):
        v = Decimal(value.replace(",", ""))
        total_k += v if sign == "+" else -v
    reads_text = _fmt_k_exact(reads_k, reads_m.group(0))
    total_text = _fmt_k_at(total_k, _k_places(total_m.group(0)))
    rerolled = _reroll_breakdown(body, reads_m.end(), row_k)
    if rerolled is None:
        return "the reads breakdown does not match the rows one-to-one"
    shift = len(rerolled) - len(body)
    body = rerolled
    t_start, t_end = total_m.start() + shift, total_m.end() + shift
    new = (body[:reads_m.start()] + reads_text + body[reads_m.end():t_start]
           + total_text + body[t_end:])
    return new + eol, reads_text, total_text


class _Undecodable(Exception):
    """A file the run must rewrite is not valid UTF-8."""


class _Buffers:
    """In-memory copies of every file a run touches, written once at the end.

    Every file is decoded as strict UTF-8, the same policy `main()` applies
    to `--task`; an undecodable file raises `_Undecodable`.
    """

    def __init__(self):
        self.lines: dict[Path, list[str]] = {}
        self.original: dict[Path, str] = {}

    def get(self, path: Path) -> list[str]:
        if path not in self.lines:
            try:
                text = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError as exc:
                raise _Undecodable(str(path), f"not UTF-8 ({exc.reason} at byte "
                                              f"{exc.start})") from None
            self.original[path] = text
            self.lines[path] = text.split("\n")
        return self.lines[path]

    def changed(self) -> list[Path]:
        return [p for p, ls in self.lines.items() if "\n".join(ls) != self.original[p]]

    def commit(self, report: dict) -> None:
        """Write every changed file, or none: temp files first, then replace."""
        temps: list[tuple[str, Path]] = []
        try:
            for path in self.changed():
                fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                                           suffix=".tmp")
                temps.append((tmp, path))
                with os.fdopen(fd, "wb") as f:
                    f.write("\n".join(self.lines[path]).encode("utf-8"))
                shutil.copymode(path, tmp)
        except OSError as exc:
            report["errors"].append({"file": str(path), "error": str(exc)})
            for tmp, _ in temps:
                with contextlib.suppress(OSError):
                    os.remove(tmp)
            return
        for tmp, path in temps:
            try:
                os.replace(tmp, path)
                report["written"].append(str(path))
            except OSError as exc:
                report["errors"].append({"file": str(path), "error": str(exc)})
                with contextlib.suppress(OSError):
                    os.remove(tmp)


def _set_cell(buf: _Buffers, report: dict, path: Path, line_idx: int,
              cell_idx: int, cells: list[str], value: str, what: str) -> None:
    lines = buf.get(path)
    if cells[cell_idx].strip() == value:
        return
    lines[line_idx] = _rewrite_cell(lines[line_idx], cell_idx, value, len(cells))
    report["changes"].append(
        {"file": str(path), "line": line_idx + 1, "what": what,
         "old": cells[cell_idx].strip(), "new": value}
    )


def _set_k_after_label(buf: _Buffers, report: dict, path: Path, label_re: str,
                       value: str, what: str) -> bool:
    """Rewrite the first `~NK` after a bold label line; False when absent."""
    lines = buf.get(path)
    for i, line in enumerate(lines):
        lm = re.match(label_re, line)
        if not lm:
            continue
        km = _K_TERM_RE.search(line, lm.end())
        if not km:
            return False
        old = km.group(0)
        if old != value:
            lines[i] = line[:km.start()] + value + line[km.end():]
            report["changes"].append({"file": str(path), "line": i + 1,
                                      "what": what, "old": old, "new": value})
        return True
    return False


def _task_id(lines: list[str], task_path: Path) -> str:
    for line in lines:
        m = re.match(r"^\*\*Task ID:\*\*\s*(\S+)", line)
        if m:
            return m.group(1)
    return task_path.stem


def _write_task(buf: _Buffers, report: dict, task_path: Path, plan_root: Path,
                project_root: Path) -> str | None:
    """Write one task's row cells, subtotal and header. Returns the header text."""
    lines = buf.get(task_path)
    text = "\n".join(lines)
    model = parse_agent(text)
    where = str(task_path)
    table = _required_context_table(lines)
    if table is None:
        report["unreadable"].append({"file": where, "what": "Required Context table",
                                     "reason": "no table found"})
        return None
    header_idx, header = table
    file_idx = next((i for i, c in enumerate(header) if c.startswith("file")), None)
    kib_idx = _col(header, ("kib",))
    tok_idx = _col(header, _TOKEN_HEADERS)
    if file_idx is None or kib_idx is None or tok_idx is None:
        report["left"].append({"file": where, "row": "table",
                               "reason": "no File, KiB or ~Tokens column "
                                         "(table left untouched)"})
        return None

    reads = Decimal(0)
    row_k: list[Decimal] = []
    reads_known = True
    for n, row_idx in enumerate(_table_rows(lines, header_idx), start=1):
        cells = _cells(_split_eol(lines[row_idx])[0], len(header))
        if len(cells) != len(header):
            report["left"].append({"file": where, "row": n,
                                   "reason": "cell count differs from the header"})
            reads_known = False
            continue
        price = price_row(cells[file_idx], task_path, plan_root, project_root, model)
        if price["priced"]:
            _set_cell(buf, report, task_path, row_idx, kib_idx, cells,
                      _fmt_kib(price["bytes"]), f"row {n} KiB")
            _set_cell(buf, report, task_path, row_idx, tok_idx, cells,
                      _fmt_k(price["tokens"]), f"row {n} ~Tokens")
            if price["span"]:
                report["spans"].append({"file": where, "row": n,
                                        "resolved": price["span"]})
            cells = _cells(_split_eol(lines[row_idx])[0], len(header))
        else:
            report["left"].append({"file": where, "row": n,
                                   "cell": cells[file_idx],
                                   "reason": price["reason"]})
        value = _parse_token_cell(cells[tok_idx])
        if value is None:
            reads_known = False
            report["unreadable"].append({"file": where, "what": f"row {n} ~Tokens",
                                         "reason": f"no figure in {cells[tok_idx]!r}"})
        else:
            reads += value
            row_k.append(value / 1000)

    if not reads_known:
        report["unreadable"].append({"file": where, "what": "Context subtotal",
                                     "reason": "a row's ~Tokens has no figure"})
        return None
    for i, line in enumerate(lines):
        if not line.startswith("**Context subtotal:**"):
            continue
        rerolled = _reroll_subtotal(line, reads, row_k)
        if isinstance(rerolled, str):
            report["unreadable"].append({"file": where, "what": "Context subtotal",
                                         "line": i + 1, "reason": rerolled})
            return None
        new_line, _reads_text, total_text = rerolled
        if new_line != line:
            lines[i] = new_line
            report["changes"].append({"file": where, "line": i + 1,
                                      "what": "Context subtotal",
                                      "old": _split_eol(line)[0],
                                      "new": _split_eol(new_line)[0]})
        if not _set_k_after_label(buf, report, task_path,
                                  r"^\*\*Estimated Tokens:\*\*", total_text,
                                  "Estimated Tokens"):
            report["unreadable"].append({"file": where, "what": "Estimated Tokens",
                                         "reason": "header line not found"})
        return total_text
    report["unreadable"].append({"file": where, "what": "Context subtotal",
                                 "reason": "line not found"})
    return None


def _one_file(folder: Path, pattern: str, report: dict, what: str) -> Path | None:
    found = sorted(folder.glob(pattern))
    if len(found) != 1:
        report["unreadable"].append({"file": str(folder), "what": what,
                                     "reason": f"{len(found)} files match {pattern}"})
        return None
    return found[0]


def _token_tables(lines: list[str], start: int = 0,
                  stop: int | None = None) -> list[tuple[int, int, list[int], list[str]]]:
    """Tables with a token column in lines[start:stop]: (header, token col, rows, header)."""
    out = []
    for i in range(start, len(lines) if stop is None else stop):
        header = _table_header_at(lines, i)
        if header is None or (i > 0 and _split_eol(lines[i - 1])[0].strip().startswith("|")):
            continue
        tok = _col(header, _TOKEN_HEADERS)
        if tok is not None:
            out.append((i, tok, _table_rows(lines, i), header))
    return out


def _section_bounds(lines: list[str], title: str) -> tuple[int, int] | None:
    """(start, stop) line indices of the `## {title}` section, or None."""
    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{title}\b", line):
            stop = next((j for j in range(i + 1, len(lines))
                         if re.match(r"^##?\s", lines[j])), len(lines))
            return i, stop
    return None


def _write_orchestration(buf: _Buffers, report: dict, orch: Path,
                         task_totals: list[tuple[str, str, str]]) -> str | None:
    """Copy each task's header into its task-list row; re-sum the total.

    A row is the task's when its `#` cell equals the Task ID's trailing number
    AND its Task cell names the task file's name segment. A Task ID is never
    searched for in the row: a Depends On cell cites other tasks' IDs. Any
    task row not found exactly once, or a total that cannot be re-rolled
    with its breakdown, leaves the whole file as authored.
    """
    lines = buf.get(orch)
    where = str(orch)
    saved, n_changes = list(lines), len(report["changes"])

    def fail(what: str, reason: str) -> None:
        lines[:] = saved
        del report["changes"][n_changes:]
        report["unreadable"].append({"file": where, "what": what, "reason": reason})

    bounds = _section_bounds(lines, "Session Task List") or (0, len(lines))
    tables = [t for t in _token_tables(lines, *bounds)
              if _col(t[3], ("#",)) is not None and _col(t[3], ("task",)) is not None]
    if len(tables) != 1:
        fail("Session Task List", f"{len(tables)} tables with #, Task and token columns")
        return None
    _, tok, rows, header = tables[0]
    num_idx, task_idx = _col(header, ("#",)), _col(header, ("task",))
    task_rows = []  # footer and total rows carry no number in `#`
    for r in rows:
        cells = _cells(_split_eol(lines[r])[0], len(header))
        if len(cells) == len(header) and cells[num_idx].strip().isdigit():
            task_rows.append((r, cells))
    found = []
    for task_id, name, total in task_totals:
        m = re.search(r"-(\d+)$", task_id)
        if not m:
            fail(f"task row {task_id}", "the Task ID has no trailing -NN number")
            return None
        hits = [t for t in task_rows if int(t[1][num_idx]) == int(m.group(1))]
        if len(hits) != 1:
            fail(f"task row {task_id}",
                 f"{len(hits)} task rows numbered {int(m.group(1))}")
            return None
        if not re.search(rf"(?<!\w){re.escape(name)}(?!\w)",
                         hits[0][1][task_idx].replace("`", "")):
            fail(f"task row {task_id}",
                 f"row {int(m.group(1))}'s Task cell does not name {name!r}")
            return None
        found.append((hits[0], task_id, total))
    for (r, cells), task_id, total in found:
        _set_cell(buf, report, orch, r, tok, cells, total, f"task list {task_id}")
    values = [_parse_token_cell(_cells(_split_eol(lines[r])[0], len(header))[tok])
              for r, _ in task_rows]
    if None in values:
        fail("Total Estimated", "a task-list cell has no figure")
        return None
    values_k = [v / 1000 for v in values]
    idx = next((i for i in range(*bounds)
                if re.match(r"^\*\*Total Estimated:\*\*", lines[i])), None)
    km = _K_TERM_RE.search(lines[idx]) if idx is not None else None
    if km is None:
        fail("Total Estimated", "line not found")
        return None
    total_text = _fmt_k_exact(sum(values_k, Decimal(0)), km.group(0))
    line = lines[idx][:km.start()] + total_text + lines[idx][km.end():]
    line = _reroll_breakdown(line, km.start() + len(total_text), values_k)
    if line is None:
        fail("Total Estimated", "its breakdown does not match the task rows one-to-one")
        return None
    if line != lines[idx]:
        report["changes"].append({"file": where, "line": idx + 1, "what": "Total Estimated",
                                  "old": _split_eol(lines[idx])[0],
                                  "new": _split_eol(line)[0]})
        lines[idx] = line
    return total_text


def _write_sprint_row(buf: _Buffers, report: dict, sprint_plan: Path,
                      session_id: str, total_text: str) -> None:
    """Copy the session total into the `## Sessions` row whose cell is the ID."""
    lines = buf.get(sprint_plan)
    what = f"session row {session_id}"
    bounds = _section_bounds(lines, "Sessions")
    if bounds is None:
        report["unreadable"].append({"file": str(sprint_plan), "what": what,
                                     "reason": "no ## Sessions section"})
        return
    hits = []
    for _, tok, rows, header in _token_tables(lines, *bounds):
        for r in rows:
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if len(cells) == len(header) and any(
                    c.replace("`", "").strip() == session_id for c in cells):
                hits.append((r, tok, cells))
    if len(hits) != 1:
        report["unreadable"].append({"file": str(sprint_plan), "what": what,
                                     "reason": f"{len(hits)} Sessions rows hold the ID"})
        return
    r, tok, cells = hits[0]
    _set_cell(buf, report, sprint_plan, r, tok, cells, total_text, what)


def write_estimates(
    task_paths: list[Path], plan_root: Path, project_root: Path,
    dry_run: bool = False,
) -> dict:
    """Write measured cells and re-rolled totals for the named task files.

    Everything is computed in memory first and written at the end, so a dry
    run reports exactly what a real run would write. A second run over the
    same tree writes nothing.
    """
    report = {"plan": str(plan_root), "dry_run": dry_run, "tasks": [str(p) for p in task_paths],
              "changes": [], "left": [], "spans": [], "unreadable": [],
              "written": [], "errors": []}
    buf = _Buffers()
    by_session: dict[Path, list[tuple[str, str, str]]] = {}
    try:
        for task_path in task_paths:
            total = _write_task(buf, report, task_path, plan_root, project_root)
            if total is not None:
                task_id = _task_id(buf.get(task_path), task_path)
                name = task_path.stem.rsplit("-", 1)[-1]
                by_session.setdefault(task_path.parent, []).append((task_id, name, total))

        for session_dir, totals in by_session.items():
            orch = _one_file(session_dir, "*Orchestration*.md", report, "Orchestration")
            if orch is None:
                continue
            total_text = _write_orchestration(buf, report, orch, totals)
            if total_text is None:
                continue
            sprint_plan = _one_file(session_dir.parent, "*Sprint-Plan*.md", report,
                                    "Sprint Plan")
            if sprint_plan is not None:
                session_id = re.sub(r"-\d+$", "", totals[0][0])
                _write_sprint_row(buf, report, sprint_plan, session_id, total_text)
    except _Undecodable as exc:
        report["errors"].append({"file": exc.args[0], "error": exc.args[1]})

    # All-or-nothing: an error before the write phase replaces no file.
    if not dry_run and not report["errors"]:
        buf.commit(report)
    return report


def format_write_report(report: dict) -> str:
    mode = "dry run, nothing written" if report["dry_run"] else "write"
    out = [f"Write-back estimates — {report['plan']} ({mode})",
           f"Scoped tasks: {len(report['tasks'])}", ""]
    if report["changes"]:
        out.append(f"Cell changes ({len(report['changes'])}):")
        for c in report["changes"]:
            out.append(f"  {c['file']}:{c['line']}  {c['what']}: {c['old']} -> {c['new']}")
    else:
        out.append("Cell changes: none (every cell already matches)")
    if report["spans"]:
        out.append("")
        out.append("Span rows priced on their span (Span resolved):")
        for s in report["spans"]:
            out.append(f"  {s['file']} row {s['row']}: {s['resolved']}")
    if report["left"]:
        out.append("")
        out.append(f"Rows left as authored ({len(report['left'])}):")
        for item in report["left"]:
            cell = f" {item['cell']}" if item.get("cell") else ""
            out.append(f"  {item['file']} row {item['row']}:{cell} — {item['reason']}")
    if report["unreadable"]:
        out.append("")
        out.append(f"Totals not re-rolled ({len(report['unreadable'])}) — reported, never guessed:")
        for u in report["unreadable"]:
            out.append(f"  {u['file']}: {u['what']} — {u['reason']}")
    for e in report["errors"]:
        out.append(f"ERROR: {e['file']}: {e['error']}")
    if report["errors"] and not report["written"]:
        out.append("No file was replaced: the write is all-or-nothing.")
    out.append("")
    out.append(f"Files written: {len(report['written'])}")
    return "\n".join(out)
