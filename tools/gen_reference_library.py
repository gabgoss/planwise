#!/usr/bin/env python3
"""Regenerate plugins/planwise/references/00-Reference-Library.md from the references.

Dev-repo tool — the library it writes DOES ship, as the one index of every
on-demand reference that skills/planwise/SKILL.md cites. The source of truth
is each reference's own one-line `consult-when:` frontmatter key, so a row can
only go stale by a reference changing without a regeneration, and
tests/test_reference_library.py catches that.

Rules the render follows:

- The scan is every `references/*.md` under `--root`, except the library itself
  (it carries no `consult-when:` key).
- A reference with no `consult-when:` key, or with an empty or multi-line one,
  is refused: exit 1, naming every such file.
- `-Part-N-…` files fold into their family's row. The row links the base file
  first, then each Part in Part order. Its text cell carries every member's
  `consult-when:` value in the same order, joined by `<br>`, with each value
  after the first introduced by its own file's link. A family with no
  unsuffixed base file leads with its lowest Part. Family membership uses
  tools/split_reference.py's `PART_FILE_RE`. Files outside the `-Part-N-`
  naming keep their own rows.
- The library is written with CRLF line endings, whatever mix of endings the
  references use. The rule is fixed here rather than copied from another file,
  because a tree holding both endings has no single "existing" one.

Usage (from the plugin repo root, or with absolute paths):
    python -B tools/gen_reference_library.py                 # rewrite the library
    python -B tools/gen_reference_library.py --check         # exit 1 if it would change
    python -B tools/gen_reference_library.py --root PATH     # a plugin tree other than this repo's

Frontmatter is read through frontmatter_parser after newline normalization, so
a CRLF reference parses exactly like an LF one.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "plugins" / "planwise"
sys.path.insert(0, str(DEFAULT_ROOT / "scripts"))

# sys.path must be set before these imports.
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from markdown_parser import split_row_cells

# `<stem>-Part-<N>-<Topic>.md` — the split tool's own family regex; the stem is the family key.
from split_reference import PART_FILE_RE

LIBRARY_NAME = "00-Reference-Library.md"
SOURCE_KEY = "consult-when"
NEWLINE = "\r\n"
# Joins a family's values inside its one cell; each Part after the first is introduced by its link.
PART_SEPARATOR = "<br>"

# A `|` not already escaped would end the table cell early.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

HEADER = [
    "---",
    ("description: The index of every planwise reference, one row per family, each with the "
     "situation that calls for it. Generated from each reference's consult-when key; never "
     "edit it by hand."),
    "---",
    "",
    "# Reference Library",
    "",
    ("**Purpose:** Find the reference that governs the work in front of you. Each row names a "
     "reference family and the situation that calls for it. A family split into `-Part-N-` "
     "files has one row: the base file first, then each Part. Read the file itself before "
     "acting on a topic it covers."),
    "",
    ("This file is generated. Each row comes from the `consult-when:` frontmatter key of "
     "every file in the family: the base file's value first (or the lowest Part's when the "
     "family has no base file), then each later Part's value, introduced by that Part's link. "
     "To change a row, edit that key in the reference and regenerate with the plugin "
     "repository's `tools/gen_reference_library.py`."),
    "",
    "## Reference Index",
    "",
    "| File | Consult when |",
    "|------|--------------|",
]


class LibrarySourceError(ValueError):
    """One or more references cannot supply a row."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def family_stem(name: str) -> tuple[str, int]:
    """Return (family stem, part number); an unsuffixed base file reports part 0."""
    m = PART_FILE_RE.match(name)
    if m:
        return m.group("stem"), int(m.group("n"))
    return name[:-3], 0


def reference_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "references").glob("*.md") if p.name != LIBRARY_NAME)


def read_consult_when(path: Path) -> str | None:
    """The file's one-line `consult-when:` value, or None when absent, empty or multi-line."""
    text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    split = split_frontmatter_block(text)
    if split is None:
        return None
    fields = parse_frontmatter_map(split[0])
    value = (fields or {}).get(SOURCE_KEY, "")
    if not value or "\n" in value:
        return None
    return value


def _cell(value: str) -> str:
    return _UNESCAPED_PIPE_RE.sub(r"\\|", value)


def _link(name: str) -> str:
    return f"[`{name}`]({name})"


def build_rows(root: Path) -> list[str]:
    files = reference_files(root)
    if not files:
        raise LibrarySourceError([f"no references found under {root / 'references'}"])
    values: dict[str, str] = {}
    problems: list[str] = []
    for path in files:
        value = read_consult_when(path)
        if value is None:
            problems.append(f"{path.name}: no one-line `{SOURCE_KEY}:` frontmatter key")
        else:
            values[path.name] = value
    if problems:
        raise LibrarySourceError(problems)

    families: dict[str, list[tuple[int, str]]] = {}
    for path in files:
        stem, part = family_stem(path.name)
        families.setdefault(stem, []).append((part, path.name))

    rows = []
    for stem in sorted(families):
        members = [name for _, name in sorted(families[stem])]
        file_cell = ", ".join(_link(name) for name in members)
        texts = [values[members[0]]] + [f"{_link(name)}: {values[name]}" for name in members[1:]]
        value = PART_SEPARATOR.join(texts)
        row = f"| {file_cell} | {PART_SEPARATOR.join(_cell(text) for text in texts)} |"
        if split_row_cells(row) != [file_cell, value]:
            raise LibrarySourceError(
                [f"{members[0]}: `{SOURCE_KEY}:` value does not survive as one table cell"])
        rows.append(row)
    return rows


def render_library(root: Path = DEFAULT_ROOT) -> str:
    """The whole library as LF text; `library_bytes` gives the on-disk form."""
    return "\n".join(HEADER + build_rows(root)) + "\n"


def library_bytes(text: str) -> bytes:
    return text.replace("\n", NEWLINE).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the on-disk library differs from a fresh render")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="plugin tree holding references/ (default: this repo's plugins/planwise)")
    args = parser.parse_args(argv)

    library = args.root / "references" / LIBRARY_NAME
    try:
        fresh = library_bytes(render_library(args.root))
    except LibrarySourceError as exc:
        print(f"cannot render {LIBRARY_NAME}:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = library.read_bytes()
        except OSError:
            print(f"reference library missing or unreadable: {library}", file=sys.stderr)
            return 1
        if current != fresh:
            print("reference library is stale - run tools/gen_reference_library.py",
                  file=sys.stderr)
            return 1
        print("reference library is current.")
        return 0

    library.write_bytes(fresh)
    rows = fresh.count(b"\r\n| [")
    print(f"wrote {library} - {rows} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
