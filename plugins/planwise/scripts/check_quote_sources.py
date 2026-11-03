#!/usr/bin/env python3
"""Quote-source checker: every block a deliverable labels as a quote must
appear verbatim in one declared source file.

Usage:
    python -B check_quote_sources.py <deliverable.md> --source <file> [--source <file> ...]

Label rule. The label words are ``quote``, ``quoted`` and ``verbatim``
(case-insensitive, whole word). Two block shapes are recognised:

- a fenced block (a ```` ``` ```` or ``~~~`` fence of three or more
  characters) whose info string names a label word (```` ```quote ````,
  ```` ```text verbatim ````), or whose nearest non-blank line above is a
  label line;
- a run of ``>`` blockquote lines whose nearest non-blank line above is a
  label line. The ``>`` marker and one following space are stripped.

A label line is one of four shapes, ignoring ``#``, ``*`` and ``_`` markup:
the label word alone (``Verbatim``, ``**Quote:**``); a line that opens with
the label word and ends in a colon (``Quoted from the source:``); a line
holding the label word in parentheses and ending in a colon (``The line
(verbatim):``); or a line whose last word before the closing colon is the
label word (``Source quote:``). Prose that only uses the word, such as
``Use double quotes around the path:``, is not a label line.

Only labelled blocks are extracted. Prose, comments and unlabelled code in
the deliverable are never compared, so a whole-file match cannot pass a
block by accident.

Normalization. Line endings (CRLF, CR, LF) and trailing spaces and tabs on
each line are normalized, in the deliverable and in every source. Nothing
else is: a changed word, a changed number or changed inner spacing is a
mismatch. A block matches when its normalized text occurs as one contiguous
run inside one normalized source and does not cut a word at either end: a
quote ``un passed`` does not match a source ``the run passed``. Leading and
trailing blank lines of a block are not compared.

A labelled block that holds no text is its own finding (an ``EMPTY`` line),
never a match: an empty string occurs in every source.

Exit contract:
    0  every quote block matched a source (a run with zero quote blocks also
       exits 0, and the summary line prints the count so an empty run is
       visible)
    1  one or more quote blocks matched no source, or a labelled block is
       empty; each is printed with its deliverable line number
    2  the deliverable or a source could not be read, or the arguments are
       invalid

The label rule is a heuristic. A block that is a quote but carries no label
is not checked, and the summary count is the evidence of what was seen.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

_WORD = r"(?:quote|quoted|verbatim)"
INFO_LABEL_RE = re.compile(r"\b" + _WORD + r"\b", re.IGNORECASE)
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
FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})([^\r\n]*)$")
BLOCKQUOTE_RE = re.compile(r"^[ ]{0,3}>[ ]?([^\r\n]*)$")


@dataclass
class QuoteBlock:
    """One labelled block: its 1-based start line and its normalized lines."""

    line: int
    kind: str
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def first_line(self) -> str:
        for item in self.lines:
            if item.strip():
                return item
        return ""


def normalize_lines(raw: str) -> list[str]:
    """Split on any line ending and drop trailing spaces and tabs per line."""
    unified = raw.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip(" \t") for line in unified.split("\n")]


def normalize_text(raw: str) -> str:
    return "\n".join(normalize_lines(raw))


def _info_labelled(info: str) -> bool:
    """True when a fence info string names the label word."""
    return bool(INFO_LABEL_RE.search(info))


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


def extract_quote_blocks(raw: str) -> list[QuoteBlock]:
    """Return every labelled fenced block and labelled blockquote run."""
    lines = normalize_lines(raw)
    blocks: list[QuoteBlock] = []
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            info = fence.group(2)
            close_re = re.compile(
                r"^[ ]{0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$"
            )
            body_start = index + 1
            end = body_start
            while end < total and not close_re.match(lines[end]):
                end += 1
            if _info_labelled(info) or _labelled(_previous_nonblank(lines, index)):
                blocks.append(QuoteBlock(body_start + 1, "fenced", lines[body_start:end]))
            index = end + 1
            continue
        quote = BLOCKQUOTE_RE.match(line)
        if quote:
            start = index
            body: list[str] = []
            while index < total:
                match = BLOCKQUOTE_RE.match(lines[index])
                if not match:
                    break
                body.append(match.group(1).rstrip(" \t"))
                index += 1
            if _labelled(_previous_nonblank(lines, start)):
                blocks.append(QuoteBlock(start + 1, "blockquote", body))
            continue
        index += 1
    return blocks


def occurs_in(text: str, source: str) -> bool:
    """True when `text` occurs in `source` and does not cut a word at either end."""
    head = r"(?<!\w)" if _WORD_CHAR.match(text[0]) else ""
    tail = r"(?!\w)" if _WORD_CHAR.match(text[-1]) else ""
    return re.search(head + re.escape(text) + tail, source) is not None


def find_empty(blocks: list[QuoteBlock]) -> list[QuoteBlock]:
    """Return the labelled blocks that hold no non-blank line."""
    return [block for block in blocks if not block.text.strip()]


def find_unmatched(blocks: list[QuoteBlock], sources: dict[str, str]) -> list[QuoteBlock]:
    """Return the non-empty blocks whose text occurs in no normalized source."""
    unmatched: list[QuoteBlock] = []
    for block in blocks:
        text = block.text.strip("\n")
        if not text.strip():
            continue  # reported by find_empty, never a match against every source
        if not any(occurs_in(text, source) for source in sources.values()):
            unmatched.append(block)
    return unmatched


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


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
    blocks = extract_quote_blocks(raw)
    empty = find_empty(blocks)
    unmatched = find_unmatched(blocks, sources)
    for block in empty:
        print(f"EMPTY {deliverable}:{block.line} ({block.kind}) labelled quote block holds no text")
    for block in unmatched:
        print(
            f"UNMATCHED {deliverable}:{block.line} ({block.kind}) "
            f"first line: {block.first_line}"
        )
    print(
        f"summary: {len(blocks)} quote block(s) checked against "
        f"{len(sources)} source(s); {len(unmatched)} unmatched; {len(empty)} empty"
    )
    return 1 if unmatched or empty else 0


if __name__ == "__main__":
    sys.exit(main())
