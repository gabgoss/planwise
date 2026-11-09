#!/usr/bin/env python3
"""Quote-source checker: every block a deliverable labels as a quote must
appear verbatim in one declared source file.

Usage:
    python -B check_quote_sources.py <deliverable.md> --source <file> [--source <file> ...]

Label rule. The label words are ``quote``, ``quoted`` and ``verbatim``
(case-insensitive). Three quote shapes are recognised:

- a fenced block (a ```` ``` ```` or ``~~~`` fence of three or more
  characters, at any indent) whose info string holds a label word as a whole
  whitespace-separated token (```` ```quote ````, ```` ```text verbatim ````),
  or whose nearest non-blank line above is a label line. A backtick fence's
  info string holds no backtick. The opener's indent is removed from each body
  line;
- a run of ``>`` blockquote lines, at any indent, whose nearest non-blank line
  above is a label line. The ``>`` marker and one following space are
  stripped. A lazy continuation line (plain text straight after a ``>`` line)
  joins a labelled run. A further ``>`` run separated from a labelled run only
  by blank lines is a further block under the same label. A fence that wraps
  the whole run is removed, and its body is the block;
- a table cell (kind ``table-cell``): a pipe-led Markdown table, with a
  separator row under its header, makes each body cell of a labelled column a
  quote site. A header cell is labelled when its whole text is a label word
  (``Quote``) or when a label word is its final parenthetical
  (``Claim (verbatim)``). An empty cell and the placeholders ``none``, ``n/a``
  and ``none (gap)`` are not quote sites. A table inside a code fence extracts
  nothing. A table ends at its first non-row line, or at the row above a
  further table's separator row.

A label line is one of four shapes, ignoring ``#``, ``*`` and ``_`` markup:
the label word alone (``Verbatim``, ``**Quote:**``); a line that opens with
the label word and ends in a colon (``Quoted from the source:``); a line
holding the label word in parentheses and ending in a colon (``The line
(verbatim):``); or a line whose last word before the closing colon is the
label word (``Source quote:``). Prose that only uses the word, such as
``Use double quotes around the path:``, is not a label line.

Only labelled blocks and labelled columns are extracted. Prose, comments and
unlabelled code in the deliverable are never compared, so a whole-file match
cannot pass a block by accident.

Normalization. Line endings (CRLF, CR, LF), a leading byte order mark, and
trailing spaces and tabs on each line are normalized, in the deliverable and
in every source. Nothing else is: a changed word, a changed number or changed
inner spacing is a mismatch. A block matches when its normalized text occurs
as one contiguous run inside one normalized source and does not cut a word at
either end: a quote ``un passed`` does not match a source ``the run passed``.
Leading and trailing blank lines of a block are not compared.

Table cells. A cell is compared whole first. The comparison also tries the
cell without one wrapping code span or emphasis pair, and in both its
unescaped and its ``\\|`` pipe forms. When no whole form matches and the cell
holds double-quoted spans, each span is compared instead. A span that matches
no source is UNMATCHED. When every span matches, the cell prints a
``SPAN-ONLY`` line: the text around the spans was not compared. A cell that is
one span and nothing else has no such text, so its span match is a full match
and prints no line. ``SPAN-ONLY`` does not change the exit code.

A labelled block that holds no text is its own finding (an ``EMPTY`` line),
never a match: an empty string occurs in every source. A body row of a
labelled table whose cell count differs from the header, after the code-aware
retry, is its own finding too (a ``MALFORMED`` line), because no column of
that row can be trusted.

Exit contract:
    0  every quote block matched a source (a run with zero quote blocks also
       exits 0, and the summary line prints the count so an empty run is
       visible)
    1  one or more quote blocks matched no source, a labelled block is empty,
       or a labelled table holds a malformed row; each is printed with its
       deliverable line number
    2  the deliverable or a source could not be read, the arguments are
       invalid, or a sibling module could not be imported

The label rule is a heuristic. A block that is a quote but carries no label
is not checked, and neither is an unlabelled column, a table inside a
blockquote, or a table indented four or more spaces. The summary count is the
evidence of what was seen, so a run that reports ``0 quote block(s)`` proves
nothing about the deliverable's quotes.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

# An isolated interpreter (-I) leaves the script's folder off sys.path. Exit 1 means
# "unmatched", so a failed import has to exit 2 rather than end in a traceback.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from markdown_parser import retried_cells, split_row_cells
except ImportError as exc:
    print(f"error: cannot import a sibling module: {exc}", file=sys.stderr)
    sys.exit(2)

_WORD = r"(?:quote|quoted|verbatim)"
INFO_LABEL_RE = re.compile(r"^" + _WORD + r"$", re.IGNORECASE)
HEADER_LABEL_RE = re.compile(
    r"^[*_ \t]*" + _WORD + r"[*_ \t]*$|\(" + _WORD + r"\)[*_ \t]*$", re.IGNORECASE
)
LINE_LABEL_RES = (
    # the label word is the whole line: "Verbatim", "**Quote**", "Quoted:"
    re.compile(r"^[#*_ \t]*" + _WORD + r"[*_ \t:]*$", re.IGNORECASE),
    # the label word opens a line that ends in a colon: "Quoted from the source:"
    re.compile(r"^[#*_ \t]*" + _WORD + r"\b[^\r\n]*:[*_ \t]*$", re.IGNORECASE),
    # the label word in parentheses on a line ending in a colon: "The line (verbatim):"
    re.compile(r"\(" + _WORD + r"\)[^\r\n]*:[*_ \t]*$", re.IGNORECASE),
    # the label word directly before the closing colon: "Source quote:"
    re.compile(r"\b" + _WORD + r"[*_ \t]*:[*_ \t]*$", re.IGNORECASE),
)
_WORD_CHAR = re.compile(r"\w")
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\r\n]*)$")
BLOCKQUOTE_RE = re.compile(r"^[ \t]*>[ ]?([^\r\n]*)$")
TABLE_ROW_RE = re.compile(r"^[ ]{0,3}\|")
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
QUOTED_SPAN_RE = re.compile(r'"([^"\r\n]+)"')
PLACEHOLDER_RE = re.compile(r"^(?:none(?: \(gap\))?|n/a)$", re.IGNORECASE)
WRAPPED_RE = re.compile(r"^(`+|\*{1,3}|_{1,3})(.+)\1$")
# A line that starts its own Markdown block, so it cannot continue a blockquote lazily:
# a heading, a list item, a table row or a thematic break.
LAZY_BREAK_RE = re.compile(r"^[ \t]*(?:#{1,6}(?:[ \t]|$)|[-*+][ \t]|\d+[.)][ \t]|\||(?:[-*_][ \t]*){3,}$)")
# The closing fence of a body may sit up to this many columns past the opener.
_CLOSER_SLACK = 3
MALFORMED_KIND = "table-row"


@dataclass
class QuoteBlock:
    """One labelled block: its 1-based start line and its normalized lines.

    `alternates` holds the other forms a table cell may match in. `spans` holds
    one block per double-quoted span of a table cell. A `MALFORMED_KIND` block
    is a table row whose cell count differs from the header, not a quote.
    """

    line: int
    kind: str
    lines: list[str]
    alternates: list[str] = field(default_factory=list)
    spans: list[QuoteBlock] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def first_line(self) -> str:
        for item in self.lines:
            if item.strip():
                return item
        return ""

    @property
    def forms(self) -> list[str]:
        return [self.text.strip("\n"), *self.alternates]


def normalize_lines(raw: str) -> list[str]:
    """Split on any line ending and drop trailing spaces and tabs per line."""
    unified = raw.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip(" \t") for line in unified.split("\n")]


def normalize_text(raw: str) -> str:
    return "\n".join(normalize_lines(raw))


def _info_labelled(info: str) -> bool:
    """True when a whole whitespace-separated token of a fence info string is a label word."""
    return any(INFO_LABEL_RE.match(token) for token in info.split())


def _labelled(line: str) -> bool:
    """True when the line above a block is a label line, not prose using the word."""
    return any(rx.search(line) for rx in LINE_LABEL_RES)


def _previous_nonblank(lines: list[str], index: int) -> str:
    probe = index - 1
    while probe >= 0:
        if lines[probe].strip():
            return lines[probe]
        probe -= 1
    return ""


def _fence_open(line: str) -> re.Match[str] | None:
    """Match a fence opener. A backtick fence's info string holds no backtick."""
    match = FENCE_RE.match(line)
    if match and match.group(2)[0] == "`" and "`" in match.group(3):
        return None
    return match


def _indent_width(indent: str) -> int:
    return len(indent.expandtabs(4))


def _fence_closes(line: str, opener: re.Match[str]) -> bool:
    """True when `line` is a bare run of the opener's character, at least as long as the opener."""
    match = FENCE_RE.match(line)
    return (
        match is not None
        and match.group(2)[0] == opener.group(2)[0]
        and len(match.group(2)) >= len(opener.group(2))
        and not match.group(3).strip()
        and _indent_width(match.group(1)) <= _indent_width(opener.group(1)) + _CLOSER_SLACK
    )


def _dedent(line: str, indent: str) -> str:
    """Remove up to `indent`'s length of leading spaces and tabs from `line`."""
    cut = 0
    while cut < len(indent) and cut < len(line) and line[cut] in " \t":
        cut += 1
    return line[cut:]


def _fence_body(lines: list[str], opener: re.Match[str], start: int) -> tuple[list[str], int]:
    """Return the dedented body lines from `start`, and the index of the closing line."""
    end = start
    while end < len(lines) and not _fence_closes(lines[end], opener):
        end += 1
    return [_dedent(line, opener.group(1)) for line in lines[start:end]], end


def _lazy_line(line: str, previous: str) -> bool:
    """True when `line` continues the blockquote paragraph that `previous` ended on."""
    if not line.strip() or not previous.strip():
        return False
    return not (_fence_open(line) or _fence_open(previous) or LAZY_BREAK_RE.match(line))


def _blockquote_run(lines: list[str], start: int, labelled: bool) -> tuple[list[str], int]:
    """Return a `>` run's stripped lines and the first index past it."""
    body: list[str] = []
    index = start
    while index < len(lines):
        match = BLOCKQUOTE_RE.match(lines[index])
        if match:
            body.append(match.group(1).rstrip(" \t"))
        elif labelled and _lazy_line(lines[index], body[-1]):
            body.append(lines[index].strip())
        else:
            break
        index += 1
    return body, index


def _unwrap_fence(body: list[str]) -> list[str]:
    """Return a blockquote body without a fence that wraps all of it."""
    filled = [index for index, line in enumerate(body) if line.strip()]
    if len(filled) < 2:
        return body
    opener = _fence_open(body[filled[0]])
    if opener is None or not _fence_closes(body[filled[-1]], opener):
        return body
    return [_dedent(line, opener.group(1)) for line in body[filled[0] + 1 : filled[-1]]]


def _table_shape(header: str, separator: str) -> tuple[list[int], int] | None:
    """Return (labelled column indexes, width), or None when the pair opens no table."""
    rule = split_row_cells(separator)
    if not rule or not all(SEPARATOR_CELL_RE.match(cell) for cell in rule):
        return None
    width = len(rule)
    header_cells = retried_cells(header, split_row_cells(header), width)
    if len(header_cells) != width:
        return None
    return [index for index, cell in enumerate(header_cells) if HEADER_LABEL_RE.search(cell)], width


def _cell_forms(cell: str) -> list[str]:
    """Return the forms a cell may match in, the unescaped form first."""
    plain = cell.replace("\\|", "|")
    forms = [plain, cell, plain.replace("|", "\\|")]
    for form in forms[:]:
        wrapped = WRAPPED_RE.match(form)
        if wrapped and wrapped.group(2).strip():
            forms.append(wrapped.group(2).strip())
    return list(dict.fromkeys(forms))


def _form_block(text: str, line: int) -> QuoteBlock:
    forms = _cell_forms(text)
    return QuoteBlock(line, "table-cell", forms[:1], forms[1:])


def _cell_block(cell: str, line: int) -> QuoteBlock | None:
    """Return the cell's block with its spans, or None for an empty or placeholder cell."""
    if not cell or PLACEHOLDER_RE.match(cell):
        return None
    block = _form_block(cell, line)
    found = QUOTED_SPAN_RE.findall(block.text)
    block.spans = [_form_block(span.rstrip(" \t"), line) for span in found if span.strip()]
    return block


def _table_blocks(
    lines: list[str], start: int, columns: list[int], width: int
) -> tuple[list[QuoteBlock], int]:
    """Read the body rows from `start`; return their blocks and the first index past them."""
    blocks: list[QuoteBlock] = []
    index = start
    while index < len(lines) and TABLE_ROW_RE.match(lines[index]):
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if TABLE_ROW_RE.match(following) and _table_shape(lines[index], following) is not None:
            break  # a further table starts here, with no blank line above it
        cells = retried_cells(lines[index], split_row_cells(lines[index]), width)
        if len(cells) != width:
            blocks.append(QuoteBlock(index + 1, MALFORMED_KIND, [lines[index].strip()]))
        else:
            found = (_cell_block(cells[column], index + 1) for column in columns)
            blocks.extend(block for block in found if block is not None)
        index += 1
    return blocks, index


def extract_quote_blocks(raw: str) -> list[QuoteBlock]:
    """Return every labelled block and table cell, and a `MALFORMED_KIND` block per bad row."""
    lines = normalize_lines(raw)
    blocks: list[QuoteBlock] = []
    index = 0
    total = len(lines)
    run_end: int | None = None  # the first index past the latest labelled blockquote run
    while index < total:
        line = lines[index]
        fence = _fence_open(line)
        if fence:
            body, end = _fence_body(lines, fence, index + 1)
            if _info_labelled(fence.group(3)) or _labelled(_previous_nonblank(lines, index)):
                blocks.append(QuoteBlock(index + 2, "fenced", body))
            index = end + 1
            continue
        if BLOCKQUOTE_RE.match(line):
            follows_run = run_end is not None and not any(item.strip() for item in lines[run_end:index])
            labelled = follows_run or _labelled(_previous_nonblank(lines, index))
            body, end = _blockquote_run(lines, index, labelled)
            if labelled:
                blocks.append(QuoteBlock(index + 1, "blockquote", _unwrap_fence(body)))
                run_end = end
            index = end
            continue
        if TABLE_ROW_RE.match(line) and index + 1 < total:
            shape = _table_shape(line, lines[index + 1])
            if shape and shape[0]:
                found, index = _table_blocks(lines, index + 2, shape[0], shape[1])
                blocks.extend(found)
                continue
        index += 1
    return blocks


def occurs_in(text: str, source: str) -> bool:
    """True when `text` occurs in `source` and does not cut a word at either end."""
    head = r"(?<!\w)" if _WORD_CHAR.match(text[0]) else ""
    tail = r"(?!\w)" if _WORD_CHAR.match(text[-1]) else ""
    return re.search(head + re.escape(text) + tail, source) is not None


def _matches(block: QuoteBlock, sources: dict[str, str]) -> bool:
    """True when one form of the block occurs in one source."""
    return any(occurs_in(form, source) for form in block.forms for source in sources.values())


def find_empty(blocks: list[QuoteBlock]) -> list[QuoteBlock]:
    """Return the labelled blocks that hold no non-blank line."""
    return [block for block in blocks if not block.text.strip()]


def find_unmatched(blocks: list[QuoteBlock], sources: dict[str, str]) -> list[QuoteBlock]:
    """Return the non-empty blocks, or the spans of a cell, that occur in no normalized source."""
    unmatched: list[QuoteBlock] = []
    for block in blocks:
        if not block.text.strip():
            continue  # reported by find_empty, never a match against every source
        if not _matches(block, sources):
            parts = block.spans or [block]
            unmatched.extend(part for part in parts if not _matches(part, sources))
    return unmatched


def find_span_only(blocks: list[QuoteBlock], sources: dict[str, str]) -> list[QuoteBlock]:
    """Return the cells that matched only span by span, so their other text was not compared."""
    return [
        block
        for block in blocks
        if block.spans
        and not QUOTED_SPAN_RE.fullmatch(block.text)  # one span and nothing else: all text compared
        and not _matches(block, sources)
        and all(_matches(span, sources) for span in block.spans)
    ]


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check that every labelled quote block appears verbatim in a declared source."
    )
    parser.add_argument("deliverable", help="the markdown file whose quote blocks are checked")
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="a declared source file (repeatable); each block must occur in one of them",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # A quote may hold a character the console encoding lacks; the report must still print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    deliverable = Path(args.deliverable)
    try:
        raw = _read(deliverable)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read deliverable {deliverable}: {exc}", file=sys.stderr)
        return 2
    sources: dict[str, str] = {}
    for name in args.source:
        try:
            sources[name] = normalize_text(_read(Path(name)))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"error: cannot read source {name}: {exc}", file=sys.stderr)
            return 2
    extracted = extract_quote_blocks(raw)
    malformed = [block for block in extracted if block.kind == MALFORMED_KIND]
    blocks = [block for block in extracted if block.kind != MALFORMED_KIND]
    empty = find_empty(blocks)
    unmatched = find_unmatched(blocks, sources)
    span_only = find_span_only(blocks, sources)
    for block in empty:
        print(f"EMPTY {deliverable}:{block.line} ({block.kind}) labelled quote block holds no text")
    for block in malformed:
        print(
            f"MALFORMED {deliverable}:{block.line} ({block.kind}) "
            f"cell count differs from the header: {block.first_line}"
        )
    for block in unmatched:
        print(
            f"UNMATCHED {deliverable}:{block.line} ({block.kind}) "
            f"first line: {block.first_line}"
        )
    for block in span_only:
        print(
            f"SPAN-ONLY {deliverable}:{block.line} ({block.kind}) "
            f"text around the spans was not compared: {block.first_line}"
        )
    print(
        f"summary: {len(blocks)} quote block(s) checked against "
        f"{len(sources)} source(s); {len(unmatched)} unmatched; {len(empty)} empty; "
        f"{len(malformed)} malformed; {len(span_only)} span-only"
    )
    return 1 if unmatched or empty or malformed else 0


if __name__ == "__main__":
    sys.exit(main())
