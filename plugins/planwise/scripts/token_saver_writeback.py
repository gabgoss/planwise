#!/usr/bin/env python3
"""Token Saver write-back — the `--write-estimates` mode of the large-file scan.

`token_saver_scan` owns the scan, the report and the command line. This module
owns only what the write-back needs: it prices each Required Context row of
the NAMED task files, writes the measured `KiB` and `~Tokens` cells, and
re-rolls the totals that depend on them. Those totals are the task's
`**Context subtotal:**` reads term and total, its `**Estimated Tokens:**`
header, the session Orchestration's task-list cell and `**Total Estimated:**`,
and in the Sprint Plan the session row, the `**Estimated Tokens:**` header
re-summed from the Sessions table, and the task's cell and session total
under `## Session Details`. Each file is re-rolled whole or left as authored.
It also rewrites the Orchestration's `## Session Surface` block: the rows and
the total line, derived from every task file of the session folder. An
Orchestration without that heading gets no block.
In the Sprint Plan it prices the `KiB` and `~Tokens` cells of the `## Write-Set`
rows. A Write-Set table without those columns is left alone.
In the Master Plan beside the sprint folders it re-rolls the `Count`, `KiB` and
`~Tokens` cells of the `### Write-Sets` rows and the `**Write-set total:**`
line from the Sprint Plans. A Master Plan without them is left alone.
It also writes one `**Measured:**` footer under the Required Context table:
the date, the command, the model and the bytes-per-token ratio the rows were
priced with, so a reader can re-check any row. The date moves only when a row
cell or the footer's own text changes.

Run it through the facade, which owns the argument checks:

    python token_saver.py --scan --plan {plan_path} --write-estimates --task {task file}

The split follows the size of the code, not a change in behaviour. The scan's
`main()` imports this module only inside its `--write-estimates` branch, so a
plain scan never loads it. This module imports the row-parsing and
path-resolution helpers from `token_saver_scan`, so the two modules price a
file the same way.

Every change is computed in memory first and written at the end. A dry run
reports exactly what a real run would write, and a second run over the same
tree writes nothing. The write is all-or-nothing: an error before the write
phase replaces no file, and a failed replace restores every file already
replaced from a byte backup kept beside it.

A `§X–§Y` span resolves through `markdown_parser.extract_headings` and
`numbered_heading_index`, the same resolver the plugin's section-citation
checker uses, so the two read an anchor the same way.
"""

import contextlib
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

from markdown_parser import (
    extract_headings,
    numbered_heading_index,
    retried_cells,
    split_row_cells,
    split_row_cells_code_aware,
    split_row_raw,
)
from read_limits import bytes_per_token, estimate_tokens
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
# `{path} §X–§Y` or `{path} §X`, with an optional trailing parenthetical. A
# token is a number (`3`, `3.2`, `9.B`) or a stage/step key (`Step 5`).
_SEC = r"(?:(?:Step|Stage)\s+)?\w+(?:\.\w+)*"
_SECTION_SPAN_RE = re.compile(
    rf"^(?P<path>.+?)\s+§\s*(?P<x>{_SEC})\.?"
    rf"(?:\s*[-–]\s*§\s*(?P<y>{_SEC})\.?)?\s*(?:\([^()]*\))?$"
)
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
    # Each addend keeps its source cell's places: `~10.0K` -> 10.0, `~20K` -> 20.
    new = lead + " + ".join(f"{v:f}" for v in values_k) + trail
    return line[:m.start("nums")] + new + line[m.end("nums"):]


def _fmt_kib(num_bytes: int) -> str:
    """KiB as `measure_files.py` rounds and prints it."""
    return f"{round(num_bytes / 1024, 1):,}"


def _fmt_k(tokens: Decimal | int, places: str = "0.1") -> str:
    k = (Decimal(tokens) / 1000).quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return f"~{k}K"


class _FileCache(dict):
    """Per-pass cache: each span file is read and split once, however many rows cite it.

    `held` maps a resolved path to the bytes the run will write there. They
    stand in for the disk copy, which predates the run's edits. `sized` and
    `spanned` collect every resolved path whose size or text a price read.
    """

    def __init__(self, held: dict[Path, bytes] | None = None):
        super().__init__()
        self.held = held or {}
        self.sized: set[Path] = set()
        self.spanned: set[Path] = set()

    def _held(self, path: Path, read: set[Path]) -> bytes | None:
        full = path.resolve()
        read.add(full)
        return self.held.get(full)

    def moved(self, original: dict[Path, bytes], new: dict[Path, bytes]) -> list[Path]:
        """The read files whose `new` text or size is not the one this pass priced."""
        out = []
        for path in self.sized | self.spanned:
            was, now = (texts.get(path, original.get(path)) for texts in (self.held, new))
            if was != now and (path in self.spanned or len(was) != len(now)):
                out.append(path)
        return sorted(out)

    def size(self, path: Path) -> int:
        """The file's size: the run's own text when held, else the disk's."""
        data = self._held(path, self.sized)
        return os.path.getsize(path) if data is None else len(data)

    def lines(self, path: Path) -> list[bytes]:
        """The file's lines as bytes, each with its own line ending."""
        return self._load(path)[0]

    def index(self, path: Path) -> tuple[list, dict]:
        """`extract_headings` and `numbered_heading_index` for the file."""
        return self._load(path)[1]

    def _load(self, path: Path) -> tuple[list[bytes], tuple[list, dict]]:
        if path not in self:
            data = self._held(path, self.spanned)
            if data is None:
                data = path.read_bytes()
            parts = data.split(b"\n")
            lines = [p + b"\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
            heads = extract_headings(data.decode("utf-8", errors="replace"))
            self[path] = (lines, (heads, numbered_heading_index(heads)))
        return self[path]


def _line_span_bytes(path: Path, a: int, b: int, cache: _FileCache | None = None) -> int | None:
    lines = (cache if cache is not None else _FileCache()).lines(path)
    if a < 1 or b < a or b > len(lines):
        return None
    return sum(len(x) for x in lines[a - 1:b])


def _pick(heads: list, index: dict, key: str, after: int = 0):
    """The one heading §key names at or after line `after`, or the reason none is.

    Lookup is the citation checker's: the exact `numbered_heading_index` key,
    then, for a stage or step key, a heading whose text starts with it and no
    letter or digit follows. Of several hits, the shallowest is taken; two at
    that level are ambiguous and reported, never guessed.
    """
    hits = [h for h in index.get(key, []) if h.line >= after]
    if not hits and key.startswith(("Step ", "Stage ")):
        hits = [h for h in heads if h.line >= after
                and (b := h.raw.lstrip("#").strip().lstrip("§ ")).startswith(key)
                and not b[len(key):len(key) + 1].isalnum()]
    if not hits:
        return f"§{key} heading not found"
    top = min(h.level for h in hits)
    hits = [h for h in hits if h.level == top]
    return hits[0] if len(hits) == 1 else f"§{key} names {len(hits)} headings"


def _section_span(path: Path, x: str, y: str,
                  cache: _FileCache | None = None) -> tuple[int, int, int] | str:
    """Resolve §X..§Y to (start line, end line, bytes), 1-based and inclusive.

    Headings come from `markdown_parser.extract_headings`, with its fence rule
    (a line starting with three backticks toggles a fence). The span ends
    before the first heading after §Y at §Y's level or higher, or at EOF.
    Returns the reason when a heading is absent or ambiguous.
    """
    cache = cache if cache is not None else _FileCache()
    lines = cache.lines(path)
    heads, index = cache.index(path)
    start = _pick(heads, index, x)
    if isinstance(start, str):
        return start
    end_h = _pick(heads, index, y, start.line)
    if isinstance(end_h, str):
        return end_h
    stop = next((h.line - 1 for h in heads
                 if h.line > end_h.line and h.level <= end_h.level), len(lines))
    return start.line, stop, sum(len(r) for r in lines[start.line - 1:stop])


def _same_file(a: Path, b: Path) -> bool:
    """True when both paths name one existing file."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def price_row(
    cell: str, task_path: Path, plan_root: Path, project_root: Path,
    model: str | None, cache: _FileCache | None = None,
    own_bytes: int | None = None,
) -> dict:
    """Price one Required Context File cell, or say why it is left as authored.

    Returns {"priced": True, "bytes", "tokens", "path", "span", "ratio"} or
    {"priced": False, "reason"}. `ratio` is the bytes-per-token figure the
    row was priced with. A whole-file row is priced only when the
    cell holds a bare path: text after the path that is not one of the two
    span forms means the author priced something narrower than the file.
    `cache` is the pass's `_FileCache`, so a file cited by several span rows
    is read once, and a file the run rewrites is priced at the text it will
    write. File I/O errors propagate as `OSError` to the caller.
    `own_bytes` is the encoded size of the task file's in-memory text. A
    whole-file row that resolves to the task file itself takes that size, not
    the size on disk, because the disk copy predates this run's edits.
    """
    cache = cache if cache is not None else _FileCache()
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
        num_bytes = _line_span_bytes(resolved, a, b, cache)
        if num_bytes is None:
            return {"priced": False, "reason": f"span lines {a}-{b} out of range"}
        span = f"lines {a}-{b} = {b - a + 1} lines / {num_bytes:,} bytes"
    elif s:
        resolved = _resolve(s.group("path"))
        if resolved is None:
            return {"priced": False,
                    "reason": unresolved_reason(s.group("path"), project_root)}
        x, y = s.group("x"), s.group("y") or s.group("x")
        found = _section_span(resolved, x, y, cache)
        if isinstance(found, str):
            return {"priced": False, "reason": f"span §{x}–§{y}: {found}"}
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
        num_bytes = (own_bytes if own_bytes is not None and _same_file(resolved, task_path)
                     else cache.size(resolved))

    _, content = content_class_for(resolved)
    tokens = estimate_tokens(num_bytes, model or "", content)
    return {"priced": True, "bytes": num_bytes, "tokens": tokens,
            "path": str(resolved), "span": span,
            "ratio": bytes_per_token(model or "", content)}


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
        """Write every changed file, or none.

        Each new body and a byte backup of each original go to temp files in
        the target's own directory first. Then each target is replaced. If a
        replace fails, every file already replaced is restored from its
        backup, the failing file is named, and `written` stays empty.
        """
        staged: list[tuple[str, str, Path]] = []  # (new body, backup, target)

        def temp(path: Path, data: bytes) -> str:
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                                       suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            shutil.copymode(path, tmp)
            return tmp

        def cleanup() -> None:
            for new, bak, _ in staged:
                for tmp in (new, bak):
                    with contextlib.suppress(OSError):
                        os.remove(tmp)

        path = None
        try:
            for path in self.changed():
                new = temp(path, "\n".join(self.lines[path]).encode("utf-8"))
                try:
                    bak = temp(path, path.read_bytes())
                except OSError:
                    os.remove(new)
                    raise
                staged.append((new, bak, path))
        except OSError as exc:
            report["errors"].append({"file": str(path), "error": str(exc)})
            cleanup()
            return
        done: list[tuple[str, Path]] = []
        for new, bak, path in staged:
            try:
                os.replace(new, path)
            except OSError as exc:
                report["errors"].append({"file": str(path), "error": f"replace failed: {exc}"})
                for b, p in reversed(done):
                    try:
                        os.replace(b, p)
                    except OSError as rexc:
                        report["errors"].append(
                            {"file": str(p), "error": f"restore failed, backup kept at {b}: {rexc}"})
                        staged[:] = [s for s in staged if s[1] != b]
                cleanup()
                return
            done.append((bak, path))
        cleanup()
        report["written"].extend(str(p) for _, _, p in staged)


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
    """The Task ID without backticks, bold markers or surrounding punctuation."""
    for line in lines:
        m = re.match(r"^\*\*Task ID:\*\*(.*)", line)
        idm = re.search(r"[A-Za-z0-9](?:[\w-]*[A-Za-z0-9])?",
                        m.group(1).replace("`", "").replace("*", "")) if m else None
        if idm:
            return idm.group(0)
    return task_path.stem


_SELF_ROW_PASSES = 8  # a pass that still moves the byte count after this many is not converging
_PASS_LISTS = ("left", "spans", "unreadable")

_FOOTER_LABEL = "**Measured:**"
_FOOTER_COMMAND = "token_saver.py --scan --write-estimates"
_FOOTER_RE = re.compile(r"^\*\*Measured:\*\*\s*(\d{4}-\d{2}-\d{2})(?P<rest> by .*)$")


def _write_measured_footer(lines: list[str], report: dict, where: str, header_idx: int,
                           last_row: int, model: str | None, ratios: set[float],
                           row_changed: bool, today: str) -> None:
    """Write or refresh the one `**Measured:**` footer under the Required Context table.

    The footer names the date, the command, the model and the ratio(s) the
    rows were priced with. An existing footer keeps its date unless a row
    cell changed in this pass or the footer's text after the date differs.
    An absent footer is inserted after the table, with a blank line between,
    so a renderer does not read it as one more table row. A footer that does
    not match the shape is replaced.
    """
    if not ratios:
        return
    ratio_text = " / ".join(f"{r:g}" for r in sorted(ratios))
    rest = f" by {_FOOTER_COMMAND} · {model or 'default'} · {ratio_text} B/tok"
    found = None
    for i in range(last_row + 1, len(lines)):
        body = _split_eol(lines[i])[0]
        if re.match(r"^#{1,6}\s", body):
            break
        if body.startswith(_FOOTER_LABEL):
            found = i
            break
    if found is None:
        eol = _split_eol(lines[header_idx])[1]
        new = f"{_FOOTER_LABEL} {today}{rest}"
        block = [eol, new + eol]
        nxt = last_row + 1
        if nxt < len(lines) and _split_eol(lines[nxt])[0].strip():
            block.append(eol)
        lines[last_row + 1:last_row + 1] = block
        report["changes"].append({"file": where, "line": last_row + 3,
                                  "what": "Measured footer", "old": "", "new": new})
        return
    old, eol = _split_eol(lines[found])
    m = _FOOTER_RE.match(old)
    date = m.group(1) if m and m.group("rest") == rest and not row_changed else today
    new = f"{_FOOTER_LABEL} {date}{rest}"
    if new != old:
        lines[found] = new + eol
        report["changes"].append({"file": where, "line": found + 1,
                                  "what": "Measured footer", "old": old, "new": new})


def _text_bytes(lines: list[str]) -> int:
    """The encoded size of the buffer, which is what `_Buffers.commit` writes."""
    return len("\n".join(lines).encode("utf-8"))


def _write_task(buf: _Buffers, report: dict, task_path: Path, plan_root: Path,
                project_root: Path, cache: _FileCache, today: str) -> str | None:
    """Write one task's row cells, subtotal and header. Returns the header text.

    A task file may cite itself in Required Context. Writing that row changes
    the file's own size, so the write repeats until a pass leaves the encoded
    byte count where it found it. The row, the subtotal and the header then
    describe the bytes that `commit` writes. The report keeps one record per
    changed cell: the value as read, and the value after the last pass.
    """
    lines = buf.get(task_path)
    original = list(lines)
    marks = {key: len(report[key]) for key in _PASS_LISTS}
    n_changes = len(report["changes"])
    merged: dict[tuple, dict] = {}
    for n_pass in range(_SELF_ROW_PASSES):
        measured = _text_bytes(lines)
        for key, n in marks.items():
            del report[key][n:]  # each pass lists them again
        total = _write_task_pass(buf, report, task_path, plan_root, project_root,
                                 cache, measured, today)
        for change in report["changes"][n_changes:]:
            hit = merged.setdefault((change["line"], change["what"]), dict(change))
            hit["new"] = change["new"]
        del report["changes"][n_changes:]
        if total is None:
            if n_pass:  # a later pass failed: the file goes back as authored
                lines[:] = original
            else:
                report["changes"].extend(c for c in merged.values() if c["old"] != c["new"])
            return None
        if _text_bytes(lines) == measured:
            report["changes"].extend(c for c in merged.values() if c["old"] != c["new"])
            return total
    lines[:] = original
    for key, n in marks.items():
        del report[key][n:]
    report["unreadable"].append({"file": str(task_path), "what": "task file size",
                                 "reason": f"the byte count still moved after {_SELF_ROW_PASSES} "
                                           "passes (task file left as authored)"})
    return None


def _write_task_pass(buf: _Buffers, report: dict, task_path: Path, plan_root: Path,
                     project_root: Path, cache: _FileCache, own_bytes: int,
                     today: str) -> str | None:
    """One pass of `_write_task`: row cells, footer, subtotal and header, priced at `own_bytes`.

    The row cells and the `**Measured:**` footer are kept only with a
    re-rolled subtotal: when the subtotal cannot be re-rolled, the whole
    task file stays as authored. `today` is the footer's date for a pass
    that changes a row cell.
    """
    lines = buf.get(task_path)
    text = "\n".join(lines)
    model = parse_agent(text)
    where = str(task_path)
    saved, n_changes = list(lines), len(report["changes"])

    def fail(what: str, reason: str, **extra) -> None:
        lines[:] = saved
        del report["changes"][n_changes:]
        report["unreadable"].append({"file": where, "what": what, "reason": reason, **extra})
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
    ratios: set[float] = set()
    row_indices = _table_rows(lines, header_idx)
    for n, row_idx in enumerate(row_indices, start=1):
        cells = _cells(_split_eol(lines[row_idx])[0], len(header))
        if len(cells) != len(header):
            report["left"].append({"file": where, "row": n,
                                   "reason": "cell count differs from the header"})
            reads_known = False
            continue
        try:
            price = price_row(cells[file_idx], task_path, plan_root, project_root,
                              model, cache, own_bytes)
        except OSError as exc:
            price = {"priced": False, "reason": f"read error: {exc}"}
        if price["priced"]:
            ratios.add(price["ratio"])
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

    if row_indices:
        row_changed = any(c["what"].startswith("row ") for c in report["changes"][n_changes:])
        _write_measured_footer(lines, report, where, header_idx, row_indices[-1], model,
                               ratios, row_changed, today)
    has_subtotal = any(ln.startswith("**Context subtotal:**") for ln in lines)
    if not reads_known and has_subtotal:
        fail("Context subtotal", "a row's ~Tokens has no figure (task file left as authored)")
        return None
    for i, line in enumerate(lines):
        if not line.startswith("**Context subtotal:**"):
            continue
        rerolled = _reroll_subtotal(line, reads, row_k)
        if isinstance(rerolled, str):
            fail("Context subtotal", f"{rerolled} (task file left as authored)", line=i + 1)
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
    # No subtotal line: no identity ties the row cells to a total, so they stay.
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


def _guard(buf: _Buffers, report: dict, path: Path):
    """Snapshot `path`. The returned `fail` restores it whole and reports why."""
    lines = buf.get(path)
    saved, n_changes = list(lines), len(report["changes"])

    def fail(what: str, reason: str) -> None:
        lines[:] = saved
        del report["changes"][n_changes:]
        report["unreadable"].append({"file": str(path), "what": what, "reason": reason})

    return lines, fail


def _write_orchestration(buf: _Buffers, report: dict, orch: Path,
                         task_totals: list[tuple[str, str, str]]) -> str | None:
    """Re-roll the Session Task List; any failure leaves the file as authored."""
    lines, fail = _guard(buf, report, orch)
    bounds = _section_bounds(lines, "Session Task List") or (0, len(lines))
    return _reroll_task_table(buf, report, orch, bounds, task_totals, fail,
                              "Session Task List", total_required=True)


PLAN_TIME_FLAG = "(plan-time estimate)"
_ROLE_RANK = {"READ": 0, "EDIT": 1, "CREATE": 2}
_SURFACE_COLUMNS = ["path", "role", "kib", "~tokens", "cited by"]
_SURFACE_LABEL = "**Session surface:**"
# A trailing `:line`, `:line-line` or parenthetical after whitespace. A drive colon is not a
# qualifier, and neither is text that fills a whole path component, as `(shop)` in `app/(shop)`.
_QUALIFIER_RE = re.compile(r"(?:(?<!^[A-Za-z])(?<=[^/]):\d+(?:[-–]\d+)?|(?<=\S)\s+\([^()]*\))$")
_ORCHESTRATION_GLOB = "*-Orchestration.md"


def _surface_number(text: str, path: Path) -> int | None:
    """The task number: the Task ID's trailing digits, else the file name's."""
    m = (re.search(r"-(\d+)$", _task_id(text.split("\n"), path))
         or re.search(r"-(\d+)-[A-Za-z]+-[^-]+$", path.stem))
    return int(m.group(1)) if m else None


def _folder_text(folder: Path) -> str:
    """A session folder as a plan-relative path: its sprint folder and its own name."""
    return f"{folder.parent.name}/{folder.name}"


def _surface_key(cell: str, task_path: Path, own: dict[str, Path], plan_root: Path,
                 project_root: Path) -> str | None:
    """The one key of the file a Required Context cell names, or None when it names no path.

    `own` maps each plan file's bare name to its session folder. Those files
    are keyed by bare name. Any other file that resolves is keyed by its path
    from the project root, and one that does not by its cleaned text. A
    trailing qualifier drops only when the path resolves without it and not with it.
    """
    text = re.sub(r"^(?:\./+)+", "", _clean_file_cell(cell).replace("\\", "/")).rstrip("/")
    if not text or is_command_corpus(cell):
        return None
    bare = text
    while True:
        key = _known_key(bare, task_path, own, plan_root, project_root)
        if key is not None:
            return key
        m = _QUALIFIER_RE.search(bare)
        if m is None:
            break
        bare = bare[:m.start()].rstrip("/")
    if text.startswith("Outputs/"):
        text = f"{_folder_text(task_path.parent)}/{text}"
    if unresolved_reason(text, project_root).startswith("not a path"):
        return None
    at = f"/{text}".find(f"/{_folder_text(task_path.parent)}/Outputs/")
    return text[at:] if at >= 0 else text


def _known_key(text: str, task_path: Path, own: dict[str, Path], plan_root: Path,
               project_root: Path) -> str | None:
    """The key of a path that names a plan file or resolves, else None."""
    if text in own:
        return text
    base, _, name = text.rpartition("/")
    if name in own and f"/{base}".endswith(f"/{_folder_text(own[name])}"):
        return name
    if text.startswith("Outputs/"):
        # An Outputs/ path reads from the session folder, so no other root is tried.
        found = task_path.parent / text
        resolved = found if found.is_file() else None
        text = f"{_folder_text(task_path.parent)}/{text}"
    else:
        resolved = resolve_context_path(text, task_path, plan_root, project_root)
    if resolved is not None:
        full = resolved.resolve()
        if full.name in own and full.parent == own[full.name].resolve():
            return full.name
        try:
            return full.relative_to(project_root.resolve()).as_posix()
        except ValueError:  # outside the project root: the text is the key
            return text
    return None


def surface_entries(tasks: list[tuple[Path, str]], plan_files: list[tuple],
                    plan_root: Path, project_root: Path) -> list[dict]:
    """One entry per file that the task texts name, in the block's row order.

    `tasks` holds (task file path, its text). The path supplies the name and
    the session folder, and need not exist. `plan_files` holds (bare name, KiB
    cell, ~Tokens cell) of the Orchestration and Recovery files, with None
    cells for no figure. An entry is {"path", "role", "kib", "tokens", "by"}.
    `tokens` is None when no row carries a figure. A path takes the highest
    figure any citing row carries, and the KiB cell of that row.
    """
    numbered = sorted(((_surface_number(text, path), path, text) for path, text in tasks),
                      key=lambda t: (t[0] is None, t[0] or 0, t[1].name))
    own = {path.name: path.parent for _, path, _ in numbered}
    if numbered:
        own.update((row[0], numbered[0][1].parent) for row in plan_files)
    entries: dict[str, dict] = {}

    def add(key: str, kib: str | None = None, tokens: str | None = None,
            role: str = "READ", by: str | None = None) -> None:
        entry = entries.setdefault(key, {"path": key, "role": "READ", "kib": "0.0",
                                         "tokens": None, "by": []})
        if by is not None and by not in entry["by"]:
            entry["by"].append(by)
        if _ROLE_RANK.get(role, 0) > _ROLE_RANK[entry["role"]]:
            entry["role"] = role
        value = _parse_token_cell(tokens) if tokens is not None else None
        if value is not None and (entry["tokens"] is None or value > entry["tokens"]):
            entry["tokens"], entry["kib"] = value, (kib or "").strip() or "0.0"

    for name, kib, tokens in plan_files:
        add(name, kib, tokens, by="orchestrator")
    for _, path, _ in numbered:
        add(path.name)
    fixed = len(entries)
    for number, path, text in numbered:
        label = f"{number:02d}" if number is not None else path.stem
        lines = text.split("\n")
        table = _required_context_table(lines)
        if table is None:
            continue
        header_idx, header = table
        file_idx = next((i for i, c in enumerate(header) if c.startswith("file")), None)
        if file_idx is None:
            continue
        columns = [_col(header, ("kib",)), _col(header, _TOKEN_HEADERS), _col(header, ("role",))]
        for row_idx in _table_rows(lines, header_idx):
            cells = _cells(_split_eol(lines[row_idx])[0], len(header))
            if file_idx >= len(cells):
                continue
            key = _surface_key(cells[file_idx], path, own, plan_root, project_root)
            if key is None:
                continue
            whole = len(cells) == len(header)  # a shifted row names its path and no figure
            kib, tokens, role = (cells[i] if whole and i is not None else None for i in columns)
            add(key, kib, tokens, ((role or "").split() or ["READ"])[0], label)
    out = list(entries.values())
    return out[:fixed] + sorted(out[fixed:], key=lambda e: e["path"])


def surface_row(entry: dict) -> str:
    """One table row of the block."""
    flagged = entry["role"] == "CREATE" or entry["tokens"] is None
    role = f"{entry['role']} {PLAN_TIME_FLAG}" if flagged else entry["role"]
    path = entry["path"].replace("|", "\\|")
    return (f"| `{path}` | {role} | {entry['kib']} | {_fmt_k(entry['tokens'] or 0)} "
            f"| {', '.join(entry['by']) or 'none'} |")


def surface_total(entries: list[dict]) -> str:
    """The block's total line: the sum of the printed `~Tokens` cells, and the row count."""
    total = sum((_parse_token_cell(_fmt_k(e["tokens"] or 0)) for e in entries), Decimal(0))
    return (f"{_SURFACE_LABEL} {_fmt_k(total)} tokens over {len(entries)} files "
            "(information only)")


def role_spellings(key: str, root: Path) -> list[str]:
    """`key`, then each shorter spelling without a trailing qualifier, up to one that exists."""
    spellings = [key]
    while not os.path.exists(root / spellings[-1]):
        m = _QUALIFIER_RE.search(spellings[-1])
        bare = spellings[-1][:m.start()].rstrip("/") if m else ""
        if not bare:
            break
        spellings.append(bare)
    return spellings


def _write_set_keys(rows: list[tuple], named: dict, own: dict[str, Path], plan_root: Path,
                    project_root: Path) -> list[tuple[str, list[str]]]:
    """(the one key of the file, its known Task IDs) per Write-Set row of (path cell, task cell)."""
    out = []
    for cell, task_cell in rows:
        ids = list(dict.fromkeys(i for i in re.findall(r"[A-Za-z0-9][\w-]*", task_cell) if i in named))
        at = named[ids[0]][0] if ids else plan_root / "row"
        key = _surface_key(cell, at, own, plan_root, project_root) or _clean_file_cell(cell)
        out.append((role_spellings(key, project_root)[-1], ids))
    return out


def writeset_figures(rows: list[tuple[str, str]], tasks: list[tuple[Path, str]],
                     shares: dict[str, Decimal | None], plan_root: Path, project_root: Path,
                     cache: _FileCache | None = None, size_of=None) -> list[tuple]:
    """(KiB cell, ~Tokens cell, source) per Write-Set row; the first source found wins.

    `rows` holds (path cell, task cell), `tasks` every task file of the sprint
    with its text, and `shares` each Task ID's output tokens. The sources:
    "cited" is the highest Required Context figure for the path, "measured" the
    file's own price for the costliest Agent of its tasks, and "share" the
    output tokens of a task split over its rows that reach this step. A row
    with none of the three gets (None, None, None). Rows that name one file
    get one figure. A row that names no path gets (None, None, "no path") and
    takes no share. `size_of` gives the present size of the file that holds the rows.
    """
    cache = cache if cache is not None else _FileCache()
    named = {_task_id(text.split("\n"), path): (path, parse_agent(text)) for path, text in tasks}
    own = {path.name: path.parent for path, _ in tasks}
    cited: dict[str, tuple[str, Decimal]] = {}
    for entry in surface_entries(tasks, [], plan_root, project_root):
        key = role_spellings(entry["path"], project_root)[-1]
        if entry["tokens"] is not None and (key not in cited or entry["tokens"] > cited[key][1]):
            cited[key] = (entry["kib"], entry["tokens"])

    keys: list[str] = []
    row_ids: list[list[str]] = []
    ids_of: dict[str, list[str]] = {}
    paths = [r for r in rows if not _names_no_path(r[0])]
    for key, ids in _write_set_keys(paths, named, own, plan_root, project_root):
        keys.append(key)
        row_ids.append(ids)
        ids_of.setdefault(key, []).extend(ids)

    def measure(key: str, ids: list[str]) -> tuple | None:
        at = own[key] / key if key in own else named[ids[0]][0] if ids else plan_root / "row"
        best = None
        for model in {named[i][1] for i in ids} or {None}:
            try:
                price = price_row(key, at, plan_root, project_root, model, cache)
                size = size_of(Path(price["path"])) if size_of and price["priced"] else None
                if size is not None:
                    price = price_row(key, Path(price["path"]), plan_root, project_root,
                                      model, cache, size)
            except OSError:
                continue
            if price["priced"] and (best is None or price["tokens"] > best["tokens"]):
                best = price
        return best and (_fmt_kib(best["bytes"]), _fmt_k(best["tokens"]), "measured")

    figures: dict[str, tuple] = {}
    for key, ids in ids_of.items():
        if key in cited:
            figures[key] = (cited[key][0], _fmt_k(cited[key][1]), "cited")
        elif (found := measure(key, ids)) is not None:
            figures[key] = found
    reached = Counter(i for key, ids in zip(keys, row_ids) if key not in figures for i in ids)
    for key, ids in ids_of.items():
        split = [(shares[i] / reached[i], named[i][1]) for i in ids
                 if key not in figures and shares.get(i) is not None]
        if split:
            tokens, model = max(split, key=lambda s: s[0])
            ratio = bytes_per_token(model or "", content_class_for(Path(key))[1])
            with localcontext() as ctx:
                # An estimate may hold more digits than the default precision, or than a float.
                ctx.prec = max(ctx.prec, tokens.adjusted() + 12)
                kib = (tokens * Decimal(str(ratio)) / 1024).quantize(Decimal("0.1"))
                figures[key] = (f"{kib:,}", _fmt_k(tokens), "share")
    priced = iter([figures.get(key, (None, None, None)) for key in keys])
    return [(None, None, "no path") if _names_no_path(r[0]) else next(priced) for r in rows]


_OUTPUT_ADDEND_RE = re.compile(rf"\+\s*~\s*({_NUM})\s*K\s*\(?output\b")


def _output_tokens(text: str) -> Decimal | None:
    """The output addend of the `**Context subtotal:**` line, in tokens, or None."""
    line = next((ln for ln in text.split("\n") if ln.startswith("**Context subtotal:**")), "")
    m = _OUTPUT_ADDEND_RE.search(line)
    return Decimal(m.group(1).replace(",", "")) * 1000 if m else None


def _write_writeset(buf: _Buffers, report: dict, sprint_plan: Path, plan_root: Path,
                    project_root: Path, cache: _FileCache) -> None:
    """Price the `## Write-Set` rows; any failure leaves the file as it was.

    Only the `KiB` and `~Tokens` cells change. The columns are found by name,
    and a table without them is left alone and not reported. The figures come
    from every task file of the sprint, so every row is priced, also a row of a
    session this run does not name. A row with no figure, or that names no path,
    keeps its cells. The Sprint Plan may be a row itself, so the pass repeats
    until its size settles.
    """
    what = "Write-Set"
    fail = None
    try:
        # A lenient read first, so a Sprint Plan with nothing to price is never loaded.
        lines = buf.lines.get(sprint_plan)
        if lines is None:
            lines = sprint_plan.read_bytes().decode("utf-8", errors="replace").split("\n")
        table = _write_set_table(lines, _section_bounds(lines, what), _WRITE_SET_COLUMNS)
        if table is None:
            return
        lines, fail = _guard(buf, report, sprint_plan)
        head, (path_at, task_at, kib_at, tok_at), width = table
        tasks = [t for folder in sorted(sprint_plan.parent.iterdir()) if folder.is_dir()
                 for t in _surface_tasks(buf, folder) if not _is_orchestration(t[0])]
        shares = {_task_id(text.split("\n"), path): _output_tokens(text) for path, text in tasks}
        before = {}
        for n, i in enumerate(_table_rows(lines, head), start=1):
            cells = _cells(_split_eol(lines[i])[0], width)
            if len(cells) == width:
                before[i] = (n, cells)
            else:
                report["left"].append({"file": str(sprint_plan), "row": f"Write-Set {n}",
                                       "reason": "cell count differs from the header"})

        def size_of(path: Path) -> int | None:
            # Any other file this run rewrites is priced from `cache`.
            return _text_bytes(lines) if _same_file(sprint_plan, path) else None

        for _ in range(_SELF_ROW_PASSES):
            measured = _text_bytes(lines)
            figures = writeset_figures([(c[path_at], c[task_at]) for _, c in before.values()], tasks,
                                       shares, plan_root, project_root, cache, size_of)
            for (i, (_, cells)), (kib, tokens, source) in zip(before.items(), figures):
                if source == "no path":
                    continue
                if source is None:
                    known = _parse_token_cell(cells[tok_at]) is not None
                    kib = cells[kib_at].strip() if known else ""
                    kib, tokens = kib or "0.0", cells[tok_at].strip() if known else _fmt_k(0)
                for at, value in ((kib_at, kib), (tok_at, tokens)):
                    if _cells(_split_eol(lines[i])[0], width)[at].strip() != value:
                        lines[i] = _rewrite_cell(lines[i], at, value, width)
            if _text_bytes(lines) == measured:
                break
        else:
            fail(what, f"the byte count still moved after {_SELF_ROW_PASSES} passes")
            return
    except Exception as exc:  # noqa: BLE001 - the table never blocks the other writes
        reason = f"{type(exc).__name__}: {exc}"
        if fail is not None:
            fail(what, reason)
        else:
            report["unreadable"].append({"file": str(sprint_plan), "what": what, "reason": reason})
        return
    for i, (n, cells) in before.items():
        after = _cells(_split_eol(lines[i])[0], width)
        report["changes"].extend(
            {"file": str(sprint_plan), "line": i + 1, "what": f"{what} row {n} {label}",
             "old": cells[at].strip(), "new": after[at].strip()}
            for at, label in ((kib_at, "KiB"), (tok_at, "~Tokens"))
            if cells[at].strip() != after[at].strip())


_MASTER_LABEL = "**Write-set total:**"
_KIB_CELL_RE = re.compile(rf"^{_NUM}$")
# A path cell that names no path: empty, a dash, `none` with or without a remark, or an unanswered fill.
_NO_PATH_RE = re.compile(r"^(?:[-–—]?|n/a|none(?:[\s(,;:–—].*)?|.*<!-- FILL.*)$", re.IGNORECASE)
_WRITE_SET_COLUMNS = [("path",), ("task",), ("kib",), _TOKEN_HEADERS]


def _names_no_path(cell: str) -> bool:
    """Whether a Write-Set path cell names no path, so its row is neither priced nor counted."""
    return _NO_PATH_RE.match(cell.replace("`", "").replace("*", "").strip()) is not None


def keyed_write_set(rows: list[tuple], tasks: list[tuple[Path, str]], plan_root: Path,
                    project_root: Path) -> list[tuple[str, tuple]]:
    """(path key, row) per Write-Set row that names a path. A row starts with its path and task cells."""
    rows = [r for r in rows if not _names_no_path(r[0])]
    named = {_task_id(text.split("\n"), path): (path, None) for path, text in tasks}
    own = {path.name: path.parent for path, _ in tasks}
    keys = _write_set_keys([r[:2] for r in rows], named, own, plan_root, project_root)
    return [(key, row) for (key, _ids), row in zip(keys, rows)]


def write_set_paths(rows: list[tuple], tasks: list[tuple[Path, str]], plan_root: Path,
                    project_root: Path) -> dict[str, tuple[Decimal, Decimal]] | None:
    """{path key: (KiB, tokens)} of one sprint's Write-Set rows, or None when a row has no figure.

    `rows` holds (path, task, KiB, ~Tokens) cells and `tasks` every task file of
    the plan, so that a path has one key in every sprint. A path takes its
    highest printed ~Tokens cell, and the KiB cell of that row.
    """
    paths: dict[str, tuple[Decimal, Decimal]] = {}
    for key, (_path, _task, kib, tokens) in keyed_write_set(rows, tasks, plan_root, project_root):
        value = _parse_token_cell(tokens)
        if value is None:
            return None
        if key not in paths or value > paths[key][1]:
            kib = kib.strip()
            paths[key] = (Decimal(kib.replace(",", "") if _KIB_CELL_RE.match(kib) else 0), value)
    return paths


def write_set_sums(paths: dict[str, tuple[Decimal, Decimal]]) -> tuple[str, str, str]:
    """The (Count, KiB, ~Tokens) cells of one sprint's distinct paths, summed over printed figures."""
    with localcontext() as ctx:
        # An estimate may hold more digits than the default precision.
        ctx.prec = max([ctx.prec, *(v.adjusted() + 12 for pair in paths.values() for v in pair)])
        kib = sum((k for k, _ in paths.values()), Decimal(0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return str(len(paths)), f"{kib:,}", _fmt_k(sum((t for _, t in paths.values()), Decimal(0)))


def write_set_total(sprints: list[dict[str, tuple[Decimal, Decimal]]]) -> str:
    """The Master Plan's total line: each path of any sprint once, at its highest figure."""
    merged: dict[str, tuple[Decimal, Decimal]] = {}
    for paths in sprints:
        for key, pair in paths.items():
            if key not in merged or pair[1] > merged[key][1]:
                merged[key] = pair
    count, _kib, tokens = write_set_sums(merged)
    return f"{_MASTER_LABEL} {tokens} tokens over {count} distinct paths (information only)"


def _write_set_table(lines: list[str], bounds: tuple[int, int] | None,
                     names: list[tuple[str, ...]]) -> tuple[int, list[int], int] | None:
    """(header line, the columns of `names`, width) of the first table in `bounds` that has them all."""
    for i in range(*bounds) if bounds else ():
        header = _table_header_at(lines, i) or []
        columns = [_col(header, n) for n in names]
        if None not in columns:
            return i, columns, len(header)
    return None


def _sprint_plan_rows(buf: _Buffers, sprint_dir: Path) -> list[tuple] | None:
    """The sized Write-Set rows of a sprint folder's Sprint Plan, or None when it has no readable table."""
    found = sorted(sprint_dir.glob("*Sprint-Plan*.md"))
    if len(found) != 1:
        return None
    lines = buf.lines.get(found[0])
    if lines is None:
        lines = found[0].read_bytes().decode("utf-8", errors="replace").split("\n")
    table = _write_set_table(lines, _section_bounds(lines, "Write-Set"), _WRITE_SET_COLUMNS)
    if table is None:
        return None
    head, columns, width = table
    rows = [_cells(_split_eol(lines[i])[0], width) for i in _table_rows(lines, head)]
    if any(len(cells) != width for cells in rows):
        return None
    return [tuple(cells[at] for at in columns) for cells in rows]


def _write_master(buf: _Buffers, report: dict, plan_dir: Path, plan_root: Path,
                  project_root: Path) -> None:
    """Re-roll the Master Plan's `### Write-Sets` sizes and total.

    Every figure sums the printed cells of the Sprint Plans beside the Master
    Plan: this run's text when loaded, else the disk's. A row whose sprint has no
    sized Write-Set keeps its cells, and the total line then stays too. A
    missing Master Plan, column or total line is left alone and not reported.
    """
    found = sorted(plan_dir.glob("*-Master-Plan.md"))
    if len(found) != 1:
        return
    master, what = found[0], "Write-Sets"
    fail = None
    try:
        # A lenient read first, so a Master Plan with nothing to re-roll is never loaded.
        lines = buf.lines.get(master)
        if lines is None:
            lines = master.read_bytes().decode("utf-8", errors="replace").split("\n")
        start = next((i for i, ln in enumerate(lines) if re.match(rf"^###\s+{what}\b", ln)), None)
        if start is None:
            return
        stop = next((j for j in range(start + 1, len(lines)) if re.match(r"^#{1,3}\s", lines[j])), len(lines))
        table = _write_set_table(lines, (start, stop), [("sprint",), ("count",), ("kib",), _TOKEN_HEADERS])
        total_at = next((i for i in range(start, stop) if lines[i].startswith(_MASTER_LABEL)), None)
        if table is None and total_at is None:
            return
        lines, fail = _guard(buf, report, master)
        folders: dict[int, list[Path]] = {}
        tasks: list[tuple[Path, str]] = []
        for folder in sorted(p for p in plan_dir.iterdir() if p.is_dir()):
            m = re.match(r"Sprint-(\d+)(?:-|$)", folder.name)
            if m is None:
                continue
            folders.setdefault(int(m.group(1)), []).append(folder)
            tasks.extend(t for session in sorted(folder.iterdir()) if session.is_dir()
                         for t in _surface_tasks(buf, session) if not _is_orchestration(t[0]))
        paths = {}
        for number, same in folders.items():
            rows = _sprint_plan_rows(buf, same[0]) if len(same) == 1 else None
            paths[number] = None if rows is None else write_set_paths(rows, tasks, plan_root, project_root)
        head, columns, width = table or (0, [], 0)
        for n, i in enumerate(_table_rows(lines, head) if table else (), start=1):
            cells = _cells(_split_eol(lines[i])[0], width)
            if len(cells) != width:
                report["left"].append({"file": str(master), "row": f"{what} {n}",
                                       "reason": "cell count differs from the header"})
                continue
            m = re.match(r"Sprint-(\d+)(?!\w)", cells[columns[0]].replace("`", "").replace("*", "").strip())
            if m is None:
                continue
            known = paths.setdefault(int(m.group(1)), None)
            if known is not None:
                for at, value, label in zip(columns[1:], write_set_sums(known), ("Count", "KiB", "~Tokens")):
                    _set_cell(buf, report, master, i, at, cells, value, f"{what} {m.group(0)} {label}")
        if total_at is not None and paths and None not in paths.values():
            old, eol = _split_eol(lines[total_at])
            new = write_set_total(list(paths.values()))
            if new != old:
                lines[total_at] = new + eol
                report["changes"].append({"file": str(master), "line": total_at + 1,
                                          "what": "Write-set total", "old": old, "new": new})
    except Exception as exc:  # noqa: BLE001 - the Master Plan never blocks the other writes
        reason = f"{type(exc).__name__}: {exc}"
        if fail is not None:
            fail(what, reason)
        else:
            report["unreadable"].append({"file": str(master), "what": what, "reason": reason})


def _write_write_sets(buf: _Buffers, report: dict, sprint_dirs: list[Path], plan_root: Path,
                      project_root: Path, cache: _FileCache) -> None:
    """Price the Sprint Plans' Write-Sets, then sum them in the Master Plan.

    A Write-Set may name the Master Plan, whose size the sums change, or another
    sprint's Sprint Plan. `write_estimates` repeats the whole pass until they settle.
    """
    root = plan_root.resolve()
    for sprint_dir in sprint_dirs:
        found = sorted(sprint_dir.glob("*Sprint-Plan*.md"))
        if len(found) == 1:
            _write_writeset(buf, report, found[0], plan_root, project_root, cache)
    for plan_dir in dict.fromkeys(s.parent for s in sprint_dirs):
        if plan_dir.resolve() == root or root in plan_dir.resolve().parents:
            _write_master(buf, report, plan_dir, plan_root, project_root)


def _is_orchestration(path: Path) -> bool:
    """Whether a file name is an Orchestration's, not that of a task whose name holds the word."""
    return path.match(_ORCHESTRATION_GLOB)


def _surface_tasks(buf: _Buffers, session_dir: Path) -> list[tuple[Path, str]]:
    """(path, text) of every task file in the folder: this run's text when loaded, else the disk's."""
    tasks = []
    for path in sorted(session_dir.glob("*.md")):
        text = ("\n".join(buf.lines[path]) if path in buf.lines
                else path.read_bytes().decode("utf-8", errors="replace"))
        if (re.search(r"^\*\*Agent:\*\*", text, re.MULTILINE)
                and re.search(r"^##+\s*Required Context", text, re.MULTILINE)):
            tasks.append((path, text))
    return tasks


def _kept_rows(rows: list[str], kept: Counter) -> list[str]:
    """The path cells of the rows that `kept` counts, in file order."""
    left, out = Counter(kept), []
    for row in rows:
        if left[row] > 0:
            left[row] -= 1
            out.append(_cells(row, len(_SURFACE_COLUMNS))[0])
    return out


def _write_session_surface(buf: _Buffers, report: dict, orch: Path, plan_root: Path,
                           project_root: Path, cache: _FileCache) -> None:
    """Rewrite the `## Session Surface` rows and total; any failure leaves the file as it was.

    An Orchestration without the heading is left alone and not reported. The
    block holds the Orchestration's own row, so the pass repeats until the
    byte count settles, as `_write_task` does.
    """
    lines, fail = _guard(buf, report, orch)
    what = "Session Surface"
    try:
        bounds = _section_bounds(lines, what)
        if bounds is None:
            return
        head = next((i for i in range(*bounds) if _table_header_at(lines, i)), None)
        if head is None or _table_header_at(lines, head) != _SURFACE_COLUMNS:
            fail(what, "no table with the block's columns")
            return
        before = [_split_eol(lines[i])[0] for i in _table_rows(lines, head)]
        total_at = next((i for i in range(head, bounds[1])
                         if lines[i].startswith(_SURFACE_LABEL)), None)
        if total_at is None:
            fail(what, "total line not found")
            return
        old_total = _split_eol(lines[total_at])[0]
        present = {}
        for row in before:
            cells = _cells(row, len(_SURFACE_COLUMNS))
            if len(cells) == len(_SURFACE_COLUMNS):
                present[cells[0].replace("`", "").strip()] = (cells[2], cells[3])
        tasks = [t for t in _surface_tasks(buf, orch.parent) if t[0] != orch]
        models = {parse_agent(text) for _, text in tasks} or {None}

        def plan_file(name: str, own_bytes: int) -> tuple:
            best = None
            for model in models:
                try:
                    price = price_row(name, orch, plan_root, project_root, model, cache, own_bytes)
                except OSError:
                    continue
                if price["priced"] and (best is None or price["tokens"] > best["tokens"]):
                    best = price
            if best is None:
                return (name, *present.get(name, (None, None)))
            return name, _fmt_kib(best["bytes"]), _fmt_k(best["tokens"])

        recovery = orch.name.replace("Orchestration", "Recovery")
        eol = _split_eol(lines[head])[1]
        for _ in range(_SELF_ROW_PASSES):
            measured = _text_bytes(lines)
            entries = surface_entries(tasks, [plan_file(orch.name, measured),
                                              plan_file(recovery, measured)],
                                      plan_root, project_root)
            total_at = next(i for i in range(head, len(lines))
                            if lines[i].startswith(_SURFACE_LABEL))
            lines[total_at] = surface_total(entries) + _split_eol(lines[total_at])[1]
            rows = _table_rows(lines, head)
            lines[head + 2:head + 2 + len(rows)] = [surface_row(e) + eol for e in entries]
            if _text_bytes(lines) == measured:
                break
        else:
            fail(what, f"the byte count still moved after {_SELF_ROW_PASSES} passes")
            return
    except Exception as exc:  # noqa: BLE001 - the block never blocks the other writes
        fail(what, f"{type(exc).__name__}: {exc}")
        return
    after = [surface_row(e) for e in entries]
    pairs = [("", row) for row in (Counter(after) - Counter(before)).elements()]
    pairs += [(row, "") for row in (Counter(before) - Counter(after)).elements()]
    old_order, new_order = (_kept_rows(rows, Counter(before) & Counter(after))
                            for rows in (before, after))
    if old_order != new_order:
        pairs.append(("row order: " + ", ".join(old_order), "row order: " + ", ".join(new_order)))
    if surface_total(entries) != old_total:
        pairs.append((old_total, surface_total(entries)))
    report["changes"].extend({"file": str(orch), "line": head + 1, "what": what,
                              "old": old, "new": new} for old, new in pairs)


def _reroll_task_table(buf: _Buffers, report: dict, path: Path, bounds: tuple[int, int],
                       task_totals: list[tuple[str, str, str]], fail, label: str,
                       total_required: bool) -> str | None:
    """Copy each task's header into its row; re-sum `**Total Estimated:**`.

    The table is the one in `bounds` with `#`, Task and token columns. A row
    is the task's when its `#` cell equals the Task ID's trailing number AND
    its Task cell names the task file's name segment. A Task ID is never
    searched for in the row: a Depends On cell cites other tasks' IDs. Any
    task row not found exactly once, or a total that cannot be re-rolled with
    its breakdown, calls `fail`, which leaves the whole file as authored.
    Returns the total text ("" when the optional total line is absent).
    """
    lines = buf.get(path)
    where = str(path)
    tables = [t for t in _token_tables(lines, *bounds)
              if _col(t[3], ("#",)) is not None and _col(t[3], ("task",)) is not None]
    if len(tables) != 1:
        fail(label, f"{len(tables)} tables with #, Task and token columns")
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
        _set_cell(buf, report, path, r, tok, cells, total, f"{label} {task_id}")
    values = [_parse_token_cell(_cells(_split_eol(lines[r])[0], len(header))[tok])
              for r, _ in task_rows]
    if None in values:
        fail("Total Estimated", "a task-list cell has no figure")
        return None
    idx = next((i for i in range(*bounds)
                if re.match(r"^\*\*Total Estimated:\*\*", lines[i])), None)
    if idx is None and not total_required:
        return ""
    return _reroll_k_line(lines, idx, [v / 1000 for v in values], fail, report, where,
                          "Total Estimated")


def _reroll_k_line(lines: list[str], idx: int | None, values_k: list[Decimal], fail,
                   report: dict, where: str, what: str) -> str | None:
    """Set the first `~NK` of line `idx` to the sum of `values_k`, with its breakdown."""
    km = _K_TERM_RE.search(lines[idx]) if idx is not None else None
    if km is None:
        fail(what, "line not found")
        return None
    total_text = _fmt_k_exact(sum(values_k, Decimal(0)), km.group(0))
    line = lines[idx][:km.start()] + total_text + lines[idx][km.end():]
    line = _reroll_breakdown(line, km.start() + len(total_text), values_k)
    if line is None:
        fail(what, "its breakdown does not match the rows one-to-one")
        return None
    if line != lines[idx]:
        report["changes"].append({"file": where, "line": idx + 1, "what": what,
                                  "old": _split_eol(lines[idx])[0],
                                  "new": _split_eol(line)[0]})
        lines[idx] = line
    return total_text


def _write_sprint_plan(buf: _Buffers, report: dict, sprint_plan: Path, session_id: str,
                       total_text: str, task_totals: list[tuple[str, str, str]]) -> None:
    """Re-roll the session's Sprint Plan figures, or leave the file as authored.

    The `## Sessions` row whose cell is the ID takes the session total. The
    `**Estimated Tokens:**` header takes the sum of the Sessions rows. Under
    `## Session Details`, the `###` subsection naming the ID has its task
    cells and its optional `**Total Estimated:**` re-rolled.
    """
    lines, fail = _guard(buf, report, sprint_plan)
    what = f"session row {session_id}"
    bounds = _section_bounds(lines, "Sessions")
    if bounds is None:
        fail(what, "no ## Sessions section")
        return
    hits = []
    for _, tok, rows, header in _token_tables(lines, *bounds):
        for r in rows:
            cells = _cells(_split_eol(lines[r])[0], len(header))
            if len(cells) == len(header) and any(
                    c.replace("`", "").strip() == session_id for c in cells):
                hits.append((r, tok, cells, rows, header))
    if len(hits) != 1:
        fail(what, f"{len(hits)} Sessions rows hold the ID")
        return
    r, tok, cells, rows, header = hits[0]
    _set_cell(buf, report, sprint_plan, r, tok, cells, total_text, what)
    rows_cells = [_cells(_split_eol(lines[x])[0], len(header)) for x in rows]
    values = [_parse_token_cell(c[tok]) for c in rows_cells
              if len(c) == len(header) and c[0].strip().isdigit()]
    if None in values:
        fail("Estimated Tokens", "a Sessions cell has no figure")
        return
    idx = next((i for i, ln in enumerate(lines)
                if re.match(r"^\*\*Estimated Tokens:\*\*", ln)), None)
    if _reroll_k_line(lines, idx, [v / 1000 for v in values], fail, report,
                      str(sprint_plan), "Estimated Tokens") is None:
        return
    details = _section_bounds(lines, "Session Details")
    id_re = rf"(?<![\w-]){re.escape(session_id)}(?![\w-])"
    start = next((i for i in range(*details) if re.match(r"^###\s", lines[i])
                  and re.search(id_re, lines[i])), None) if details else None
    if start is None:
        fail("Session Details", f"no ### subsection names {session_id}")
        return
    stop = next((j for j in range(start + 1, details[1])
                 if re.match(r"^#{1,3}\s", lines[j])), details[1])
    _reroll_task_table(buf, report, sprint_plan, (start, stop), task_totals, fail,
                       "Session Details", total_required=False)


def write_estimates(
    task_paths: list[Path], plan_root: Path, project_root: Path,
    dry_run: bool = False, today: date | None = None,
) -> dict:
    """Write measured cells and re-rolled totals for the named task files.

    Everything is computed in memory first and written at the end, so a dry
    run reports exactly what a real run would write. A second run over the
    same tree writes nothing. `today` dates the `**Measured:**` footer and
    defaults to the current date, so a test can pin it.

    A row may price a file that the same run rewrites after it. So the whole
    pass repeats over the authored text, and prices each such file at the text
    the pass before gave it, until a pass moves no size that a row reads and no
    text that a span row reads. The report is the last pass's. When the passes do not settle, every
    file stays as authored and each file that still moved is reported.
    """
    stamp = (today or datetime.now().astimezone().date()).isoformat()
    held: dict[Path, bytes] = {}
    original: dict[Path, bytes] = {}
    for _ in range(_SELF_ROW_PASSES):
        report = {"plan": str(plan_root), "dry_run": dry_run, "tasks": [str(p) for p in task_paths],
                  "changes": [], "left": [], "spans": [], "unreadable": [],
                  "written": [], "errors": []}
        buf, cache = _Buffers(), _FileCache(held)
        _write_pass(buf, report, task_paths, plan_root, project_root, cache, stamp)
        new = {p.resolve(): "\n".join(buf.lines[p]).encode("utf-8") for p in buf.changed()}
        original.update((p.resolve(), text.encode("utf-8")) for p, text in buf.original.items())
        moved = cache.moved(original, new)
        if report["errors"] or not moved:
            break
        held = new
    else:
        buf = _Buffers()
        report["changes"].clear()
        report["unreadable"].extend(
            {"file": str(p), "what": "cited file",
             "reason": f"its size or text still moved after {_SELF_ROW_PASSES} passes (every file left as authored)"}
            for p in moved)

    # All-or-nothing: an error before the write phase replaces no file.
    if not dry_run and not report["errors"]:
        buf.commit(report)
    return report


def _write_pass(buf: _Buffers, report: dict, task_paths: list[Path], plan_root: Path,
                project_root: Path, cache: _FileCache, stamp: str) -> None:
    """One pass of `write_estimates` over the authored text: every edit, in memory."""
    by_session: dict[Path, list[tuple[str, str, str]]] = {}
    try:
        for task_path in task_paths:
            total = _write_task(buf, report, task_path, plan_root, project_root, cache,
                                stamp)
            if total is not None:
                task_id = _task_id(buf.get(task_path), task_path)
                name = task_path.stem.rsplit("-", 1)[-1]
                by_session.setdefault(task_path.parent, []).append((task_id, name, total))

        for session_dir, totals in by_session.items():
            orch = _one_file(session_dir, _ORCHESTRATION_GLOB, report, "Orchestration")
            if orch is None:
                continue
            total_text = _write_orchestration(buf, report, orch, totals)
            _write_session_surface(buf, report, orch, plan_root, project_root, cache)
            if total_text is None:
                continue
            sprint_plan = _one_file(session_dir.parent, "*Sprint-Plan*.md", report,
                                    "Sprint Plan")
            if sprint_plan is not None:
                session_id = re.sub(r"-\d+$", "", totals[0][0])
                _write_sprint_plan(buf, report, sprint_plan, session_id, total_text, totals)

        # After every session, because a Write-Set row may name a file of any session.
        _write_write_sets(buf, report, list(dict.fromkeys(folder.parent for folder in by_session)),
                          plan_root, project_root, cache)
    except _Undecodable as exc:
        report["errors"].append({"file": exc.args[0], "error": exc.args[1]})
    except OSError as exc:  # a file the run must rewrite could not be read
        report["errors"].append({"file": str(exc.filename or "?"), "error": str(exc)})


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
        out.append("No file was changed: the write is all-or-nothing, and a file "
                   "already replaced is restored from its backup.")
    out.append("")
    out.append(f"Files written: {len(report['written'])}")
    return "\n".join(out)
