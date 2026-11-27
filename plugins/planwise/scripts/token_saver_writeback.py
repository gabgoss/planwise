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
It never changes a `Role` cell. It names each one that holds no `READ`, `EDIT`
or `CREATE`, in every task file of a named task's session folder.

Those derived figures live in `token_saver_derived`: the session surface, the
task-list and Sprint Plan re-rolls, and the Write-Set sizes. The functions that
run a write import it, so the two modules do not import each other at the top.

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
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
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
# A dash between the path and its span, as `_clean_file_cell` ends a path.
_SPAN_SEP = r"(?:\s+(?:—|--))?"
# A span may carry a parenthetical note. A list joins spans with a comma or `and`.
_NOTE = r"\s*(?:\([^()]*\))?"
_NOTE_RE = re.compile(r"\([^()]*\)")
_JOIN = r"\s*(?:,\s*(?:and\s+)?|and\s+)"
# A comma inside a number separates thousands, unless a dash follows the group:
# in `4-23,100-169` the `100` starts the next range.
_FIRST = r"\d+(?:,\d{3}(?!\d))*"
_LAST = r"\d+(?:,\d{3}(?!\d|\s*[-–]))*"
_RANGE = rf"{_FIRST}\s*[-–]\s*{_LAST}"
_RANGE_RE = re.compile(rf"({_FIRST})\s*[-–]\s*({_LAST})")
# `{path} lines {a}-{b}`, then any further ranges of the same file.
_LINES_SPAN_RE = re.compile(
    rf"^(?P<path>.+?){_SPAN_SEP}\s+(?P<spans>lines?\s+{_RANGE}{_NOTE}"
    rf"(?:{_JOIN}(?:lines?\s+)?{_RANGE}{_NOTE})*)$"
)
# `{path} §X–§Y` or `{path} §X`, then any further section spans. A token is a
# number (`3`, `3.2`, `9.B`) or a stage/step key (`Step 5`).
_SEC = r"(?:(?:Step|Stage)\s+)?\w+(?:\.\w+)*"
_SEC_ITEM = rf"§\s*(?P<x>{_SEC})\.?(?:\s*[-–]\s*§\s*(?P<y>{_SEC})\.?)?"
_SEC_ITEM_RE = re.compile(_SEC_ITEM)
_SEC_MORE = rf"§\s*{_SEC}\.?(?:\s*[-–]\s*§\s*{_SEC}\.?)?"
_SECTION_SPAN_RE = re.compile(
    rf"^(?P<path>.+?){_SPAN_SEP}\s+(?P<spans>{_SEC_ITEM}{_NOTE}"
    rf"(?:{_JOIN}{_SEC_MORE}{_NOTE})*)$"
)
# Where the path ends in a cell that did not resolve whole: at a space, an
# opening parenthesis, a comma, a semicolon, or the `:` or `#` of a line range.
_PATH_HEAD_END_RE = re.compile(r"[\s(,;]|[:#](?=L?\d)")
_QUALIFIED_ROW = "qualified row (text after the path is not a span form)"
_SPAN_LIST_REASON = "qualified row (text between the spans is not a span list)"
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
    stand in for the disk copy, which predates the run's edits. `sized`
    collects every resolved path whose size a price read. `spans` maps each span
    read, as (reader, path, its other arguments), to what it returned.
    """

    def __init__(self, held: dict[Path, bytes] | None = None):
        super().__init__()
        self.held = held or {}
        self.sized: set[Path] = set()
        self.spans: dict[tuple, object] = {}

    def moved(self, original: dict[Path, bytes], new: dict[Path, bytes]) -> list[Path]:
        """The read files whose `new` size or cited span is not the one this pass priced."""
        out = set()
        for path in self.sized:
            was, now = (texts.get(path, original.get(path)) for texts in (self.held, new))
            if was != now and len(was) != len(now):
                out.add(path)
        later = _FileCache(new)
        for (reader, path, *args), was in self.spans.items():
            full = path.resolve()
            if self.held.get(full) != new.get(full) and reader(path, *args, later) != was:
                out.add(full)
        return sorted(out)

    def span(self, reader, path: Path, *args):
        """`reader`'s answer for a span of `path`, recorded for `moved`."""
        found = self.spans[(reader, path, *args)] = reader(path, *args, self)
        return found

    def size(self, path: Path) -> int:
        """The file's size: the run's own text when held, else the disk's."""
        full = path.resolve()
        self.sized.add(full)
        data = self.held.get(full)
        return os.path.getsize(path) if data is None else len(data)

    def lines(self, path: Path) -> list[bytes]:
        """The file's lines as bytes, each with its own line ending."""
        return self._load(path)[0]

    def index(self, path: Path) -> tuple[list, dict]:
        """`extract_headings` and `numbered_heading_index` for the file."""
        return self._load(path)[1]

    def _load(self, path: Path) -> tuple[list[bytes], tuple[list, dict]]:
        if path not in self:
            data = self.held.get(path.resolve())
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


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort (first, last) line pairs and join those that overlap."""
    out: list[tuple[int, int]] = []
    for first, last in sorted(spans):
        if out and first <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], last))
        else:
            out.append((first, last))
    return out


def _path_group_reason(path: str) -> str | None:
    """Why a span regex's path group is not a bare path, or None when it is."""
    whole, bare = path.strip().strip("<>").strip(), _clean_file_cell(path)
    if bare == whole:
        return None
    # A `§` or a number range is a span left behind. Anything else is prose.
    return _SPAN_LIST_REASON if re.search(r"§|\d\s*[-–]\s*\d", whole[len(bare):]) else _QUALIFIED_ROW


def price_row(
    cell: str, task_path: Path, plan_root: Path, project_root: Path,
    model: str | None, cache: _FileCache | None = None,
    own_bytes: int | None = None,
) -> dict:
    """Price one Required Context File cell, or say why it is left as authored.

    Returns {"priced": True, "bytes", "tokens", "path", "span", "ratio"} or
    {"priced": False, "reason"}. `ratio` is the bytes-per-token figure the
    row was priced with. A whole-file row is priced only when the
    cell holds a bare path. A cell may list several line ranges or several
    section spans of one file, and every one is priced. Other text after the
    path means the author priced something else, so the row stays as authored.
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

    def _unresolved(path_text: str) -> dict:
        """Why no file was found. A file the cell starts with is not `missing`."""
        head = _PATH_HEAD_END_RE.split(raw, maxsplit=1)[0]
        # A head with no extension needs a number or `§` after it. Without
        # one, `dir/My Notes.md` is a spaced path, not a range on `dir/My`.
        narrows = head != raw and (Path(head).suffix or re.search(r"[\d§]", raw[len(head):]))
        if narrows and _resolve(head) is not None:
            return {"priced": False, "reason": _QUALIFIED_ROW}
        return {"priced": False, "reason": unresolved_reason(path_text, project_root)}

    span = None
    m = _LINES_SPAN_RE.match(raw)
    s = _SECTION_SPAN_RE.match(raw) if not m else None
    if (m or s) and (reason := _path_group_reason((m or s).group("path"))):
        return {"priced": False, "reason": reason}
    if m:
        resolved = _resolve(m.group("path"))
        if resolved is None:
            return _unresolved(m.group("path"))
        pairs = [(int(a.replace(",", "")), int(b.replace(",", "")))
                 for a, b in _RANGE_RE.findall(_NOTE_RE.sub("", m.group("spans")))]
        # Each authored range is checked before the merge, so the report names it.
        total = len(cache.lines(resolved))
        for a, b in pairs:
            if not 1 <= a <= b <= total:
                return {"priced": False, "reason": f"span lines {a}-{b} out of range"}
        merged = _merge(pairs)
        num_bytes = sum(cache.span(_line_span_bytes, resolved, a, b) for a, b in merged)
        span = (f"lines {', '.join(f'{a}-{b}' for a, b in merged)} = "
                f"{sum(b - a + 1 for a, b in merged)} lines / {num_bytes:,} bytes")
    elif s:
        resolved = _resolve(s.group("path"))
        if resolved is None:
            return _unresolved(s.group("path"))
        intervals, texts, num_bytes = [], [], 0
        # Notes are dropped first, so `(§3 runs to EOF)` adds no item.
        for item in _SEC_ITEM_RE.finditer(_NOTE_RE.sub("", s.group("spans"))):
            x, y = item.group("x"), item.group("y") or item.group("x")
            found = cache.span(_section_span, resolved, x, y)
            if isinstance(found, str):
                return {"priced": False, "reason": f"span §{x}–§{y}: {found}"}
            first, last, size = found
            intervals.append((first, last))
            texts.append(f"§{x} at :{first} → §{y} ends at :{last}")
            num_bytes += size
        merged = _merge(intervals)
        count = sum(b - a + 1 for a, b in merged)
        if count != sum(b - a + 1 for a, b in intervals):  # overlap: each line once
            sizes = [cache.span(_line_span_bytes, resolved, a, b) for a, b in merged]
            # The heading parser also breaks a line at a lone carriage return.
            if None in sizes:
                return {"priced": False, "reason": "span sections end past the last line of the file"}
            num_bytes = sum(sizes)
        span = f"{'; '.join(texts)} = {count} lines / {num_bytes:,} bytes"
    else:
        if _clean_file_cell(cell) != raw:
            return {"priced": False, "reason": _QUALIFIED_ROW}
        resolved = _resolve(cell)
        if resolved is None:
            return _unresolved(cell)
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
    span that a span row reads. The report and the text written are the last
    pass's. When the passes do not settle, each file that still moved is also
    reported as unreadable, because a later run may move the rows that cite it.
    """
    stamp = (today or datetime.now().astimezone().date()).isoformat()
    held: dict[Path, bytes] = {}
    original: dict[Path, bytes] = {}
    for _ in range(_SELF_ROW_PASSES):
        report = {"plan": str(plan_root), "dry_run": dry_run, "tasks": [str(p) for p in task_paths],
                  "changes": [], "left": [], "spans": [], "unreadable": [], "roles": [],
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
        report["unreadable"].extend(
            {"file": str(p), "what": "cited file",
             "reason": f"its size or cited span still moved after {_SELF_ROW_PASSES} passes, "
                       "so a later run may move the rows that cite it"}
            for p in moved)

    # All-or-nothing: an error before the write phase replaces no file.
    if not dry_run and not report["errors"]:
        buf.commit(report)
    return report


def _report_unknown_roles(buf: _Buffers, report: dict, task_paths: list[Path]) -> None:
    """Name each `Role` cell that holds no role, in every session folder of a named task.

    Every task file of a folder feeds its surface block, so a sibling that the
    run did not name is read too. It runs before any edit, so no later failure
    and no missing block hides a cell. A folder that cannot be read is passed
    over, because a report never stops a write.
    """
    # Imported here, not at the top: the derived module imports this one.
    from token_saver_derived import _is_orchestration, _surface_tasks, unknown_roles

    for folder in dict.fromkeys(path.parent for path in task_paths):
        try:
            tasks = _surface_tasks(buf, folder)
        except OSError:
            continue
        for path, text in tasks:
            if _is_orchestration(path):
                continue
            report["roles"].extend(
                {"file": str(path), "row": n,
                 "reason": f"Role cell {cell!r} is not READ, EDIT or CREATE; a session surface counts it as {read}"}
                for n, _, cell, read in unknown_roles(text.split("\n")))


def _write_pass(buf: _Buffers, report: dict, task_paths: list[Path], plan_root: Path,
                project_root: Path, cache: _FileCache, stamp: str) -> None:
    """One pass of `write_estimates` over the authored text: every edit, in memory."""
    # Imported here, not at the top: the derived module imports this one.
    from token_saver_derived import (
        _one_file,
        _session_orchestration,
        _write_orchestration,
        _write_session_surface,
        _write_sprint_plan,
        _write_write_sets,
    )

    _report_unknown_roles(buf, report, task_paths)
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
            orch = _session_orchestration(session_dir, report)
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
    if report["roles"]:
        out.append("")
        out.append(f"Role cells that hold no role ({len(report['roles'])}):")
        out.extend(f"  {item['file']} row {item['row']}: {item['reason']}" for item in report["roles"])
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
