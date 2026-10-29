#!/usr/bin/env python3
"""Scan a runner's final message for the three disclosure phrases.

Usage:
    python -B scan_runner_disclosures.py <file|->

`-h` or `--help` prints this text to standard output and exits 0.
`-` reads standard input. The batch gate of a delegated session pipes each
runner's status block in. Each phrase below holds placeholders (`X`, `…`)
that stand for any text, so a literal substring match would never fire on a
real message. The placeholders become `.+?` wildcards, the literal words are
escaped, and matching ignores case.

Exit codes: 0 clean, 1 a phrase was found (each hit printed with its line),
2 usage or an unreadable message (an `Error:` line goes to stderr).

Matching joins each paragraph's lines with single spaces, so a hard-wrapped
phrase matches. A blank line ends a paragraph, so a phrase cannot join across
paragraphs. The reported line is the one where the match starts.
"""
import bisect
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

# Capped lazy wildcard: bounds backtracking on one long line.
WILDCARD = ".{1,200}?"

# Reference texts, copied byte for byte from the artifact-over-instrument reference.
PHRASES = (
    "I left X unchanged to preserve the expected gate value",
    "achieved by … so the gate would …",
    "I deviated from the spec to make the gate pass",
)


def compile_phrase(phrase):
    """Turn one reference phrase into a pattern: X and … become wildcards."""
    out = []
    for word in phrase.split():
        if word in ("X", "…"):
            out.append(WILDCARD)
        else:
            out.append(re.escape(word))
    return re.compile(r"\s+".join(out), re.IGNORECASE)


PATTERNS = tuple(compile_phrase(p) for p in PHRASES)


def _paragraphs(text):
    """Yield paragraphs as lists of (line_number, stripped_line); blank lines separate."""
    block = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            block.append((number, line.strip()))
        elif block:
            yield block
            block = []
    if block:
        yield block


def scan(text):
    """Return a list of (line_number, phrase_index, line) for every hit.

    A paragraph (lines between blank lines) is joined with single spaces before
    matching, so a hard-wrapped phrase still matches and a phrase cannot join
    across a blank line. The reported line is where the match starts.
    """
    hits = []
    for block in _paragraphs(text):
        joined = " ".join(line for _, line in block)
        offsets = []
        position = 0
        for _, line in block:
            offsets.append(position)
            position += len(line) + 1
        for index, pattern in enumerate(PATTERNS):
            for match in pattern.finditer(joined):
                at = bisect.bisect_right(offsets, match.start()) - 1
                number, line = block[at]
                hits.append((number, index, line))
    return sorted(hits)


def main(argv):
    if argv in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if argv[0] == "-":
            text = sys.stdin.read()
        else:
            text = Path(argv[0]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: scan_runner_disclosures cannot read the message: {exc}", file=sys.stderr)
        return 2
    hits = scan(text)
    for number, index, line in hits:
        print(f"HIT line {number} phrase {index + 1}: {line}")
    if not hits:
        print("clean: 0 disclosure phrases")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
