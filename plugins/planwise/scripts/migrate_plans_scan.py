#!/usr/bin/env python3
"""Reading a hand-authored plans index for the plans-index migration.

`migrate_plans_index.py` plans the migration. This module finds what the
generator would drop when it replaces the index, and accounts for every line
of the old index:

- the items: HTML comments (from a whole-file scan), Status-cell narratives,
  and table-shaped or prose lines the parser keeps out of its rows;
- table structure: the `| Abbrev |` header, separator rows and parsed rows;
- seed scaffold: the lines of the shipped seed that the generator re-renders;
- layout: blank lines, line endings and the whitespace around a comment;
- uncarried lines: every other non-blank line. They are listed verbatim in
  the ledger, because the generator does not re-render them.

Every line has exactly one owner, so the byte accounting can show a gap: a
line no category claims, or one two categories claim, leaves a non-zero
`Unaccounted`.
"""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

KIND_COMMENT = "HTML comment"
KIND_NARRATIVE = "Status cell text after the leading token"
KIND_TABLE_LINE = "table-shaped line"
KIND_PROSE = "prose line inside the table"

# The non-blank lines of the plans index seed that the generator re-renders: the seed shipped through 1.0.5.1
# (title, legend heading, legend header and six legend rows) plus the four legend rows and the intro line of the
# generated seed. Table header and separator rows are table structure, not scaffold.
SEED_SCAFFOLD = frozenset((
    "# Plans Index",
    ("> Generated from each plan's Master Plan by generate_plans_index.py. Edit the Master Plan's **Status:** "
     "line, then run the generator."),
    "## Status Legend",
    "| Status | Meaning |",
    "| NOT_STARTED | Plan created but no work begun |",
    "| PLANNING | Discovery or session planning in progress |",
    "| READY_TO_EXECUTE | Plan files authored; ready for `/planwise run` |",
    "| REVIEWED | Reviewed by `/planwise review`; no verdict recorded yet |",
    "| APPROVED | Review verdict: validated for execution |",
    "| NEEDS_FIXES | Review verdict: findings to fix before execution |",
    "| IN_PROGRESS | Active execution underway |",
    "| BLOCKED | Waiting on external dependency |",
    "| COMPLETE | All sprints and sessions finished |",
    "| CLOSED | Archived — no further work expected |",
))
_LEADING_RE = re.compile(r"^[^A-Za-z0-9]+")
_MD_HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
_HEADER_RE = re.compile(r"^\|\s*Abbrev\s*\|")
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]*-[\s:|-]*$")


@dataclass
class Item:
    """One piece of hand-written text and where it goes. `dest` is the Master Plan it is appended to,
    or None with a `reason` when it stays in the ledger."""
    line: int
    kind: str
    text: str
    in_region: bool = True
    dest: Path | None = None
    reason: str | None = None
    basis_line: int | None = None
    present: bool = False
    row: object = None
    unclosed: bool = False

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def last_line(self) -> int:
        """The line the item ends on. Only a comment spans lines."""
        return self.line + (self.text.count("\n") if self.kind == KIND_COMMENT else 0)


def scan_comments(text: str, table) -> list:
    """Every HTML comment in the file, by a whole-file scan. The parser's `skipped` list covers only the table
    region, so a comment before the header row or after the legend appears in none of its lists. A comment
    that spans lines is one item, copied from `<!--` through `-->` with its own line endings. An opener with
    no closer before the end of the file is a one-line item flagged `unclosed`, and the lines after it are
    scanned as ordinary lines."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    region_start = table.header_line + 2 if table.header_line else None
    in_region, items, i = False, [], 0
    while i < len(lines):
        number, bare = i + 1, lines[i].rstrip("\r")
        if number == region_start:
            in_region = True
        elif in_region and _MD_HEADING_RE.match(bare):
            in_region = False
        if not bare.strip().startswith("<!--"):
            i += 1
            continue
        end, unclosed = i, False
        if "-->" not in bare.strip()[len("<!--"):]:
            found = next((j for j in range(i + 1, len(lines)) if "-->" in lines[j]), None)
            unclosed = found is None
            end = i if unclosed else found
        chunk = lines[i:end + 1]
        chunk[0] = chunk[0].lstrip()
        items.append(Item(number, KIND_COMMENT, "\n".join(chunk).rstrip(), in_region, unclosed=unclosed))
        i = end + 1
    return items


def narrative(status_raw: str, token: str | None) -> str:
    """The Status cell text after its leading token, leading whitespace removed. A wrapper marker next to
    the token (`**COMPLETE** text`) drops with it. A cell with no token keeps its text after the leading
    decoration."""
    stripped = _LEADING_RE.sub("", status_raw)
    rest = stripped if token is None else stripped[len(token):]
    if rest[:1] in ("*", "_"):
        rest = rest.lstrip("*_")
    return rest.strip()


def _lines(text: str) -> list:
    """`(content, terminator bytes)` per line. Content excludes the line's `\\r` and `\\n`."""
    raw = text.split("\n")
    ends_with_newline = raw[-1] == ""
    if ends_with_newline:
        raw.pop()
    out = []
    for n, chunk in enumerate(raw):
        content = chunk.rstrip("\r")
        newline = 1 if (n < len(raw) - 1 or ends_with_newline) else 0
        out.append((content, len(chunk) - len(content) + newline))
    return out


def classify_lines(text: str, table, items: list) -> dict:
    """Give every line of the index one owner and total the bytes of each owner except the items, which the
    accounting sums from the items themselves. Returns `structure`, `scaffold`, `layout` and `uncarried`
    byte totals and `listed`: the uncarried lines as `(line, text)`, in file order."""
    lines = _lines(text)
    owned, internal = set(), set()
    figures = {"structure": 0, "scaffold": 0, "layout": 0, "uncarried": 0, "listed": []}
    rows = {r.line_number for r in table.rows}
    for item in items:
        if item.kind == KIND_NARRATIVE:
            figures["structure"] -= item.nbytes  # the row line counts as structure; its narrative is an item
            continue
        span = range(item.line, item.last_line + 1)
        owned.update(span)
        internal.update(span[:-1])
        if item.kind == KIND_COMMENT:
            body = sum(len(lines[n - 1][0].encode("utf-8")) for n in span if n <= len(lines))
            body += sum(lines[n - 1][1] for n in span[:-1] if n <= len(lines))
            figures["layout"] += body - item.nbytes  # the whitespace stripped around the comment
    for n, (content, newline) in enumerate(lines, 1):
        size = len(content.encode("utf-8"))
        if n not in internal:
            figures["layout"] += newline
        stripped = content.strip()
        if n in owned:
            continue
        if n in rows or _HEADER_RE.match(stripped) or _SEPARATOR_RE.match(stripped):
            figures["structure"] += size
        elif not stripped:
            figures["layout"] += size
        elif content in SEED_SCAFFOLD:
            figures["scaffold"] += size
        else:
            figures["uncarried"] += size
            figures["listed"].append((n, content))
    return figures
