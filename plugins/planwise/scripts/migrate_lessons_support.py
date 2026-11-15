#!/usr/bin/env python3
"""Helpers for the lessons-index migrator: recognise the on-disk shape,
locate every region of a legacy hub by heading, extract the header
changelog and the Rule Promotion Log with their bytes accounted for, route
each log row to its century file, decide each prose section's disposition
against the shipped seed text, render the changelog and promotion-log
files, and stage every output for one atomic replace.

Every function here is pure except the two staging helpers, which are
imported rather than redefined. Generic backlog-migration machinery
(staging, dedup-key normalisation, git-state checks) is imported from the
sibling backlog-migration modules unchanged; what is lessons-shaped is
written here and says so in its own docstring.
"""
import re
from pathlib import Path

from backlog_index_schema import IndexNaming, _changelog_filename, _index_naming
from generate_lessons_index import _promotion_log_filename
from lessons_bootstrap import _LESSONS_SEED_SRC_NAMES
from migrate_backlog_checks import (  # noqa: F401  (re-exported; lessons-agnostic)
    git_state,
    tree_gate,
    write_gate,
)
from migrate_backlog_support import (  # noqa: F401  (re-exported for callers)
    Refusal,
    contains_exact,
    discard,
    exact_key,
    newline_of,
    normalize,
    replace_all,
    row_cells,
    stage_all,
)
from parse_lessons import (
    GENERATED_LINE_RE,
    MASTER_TABLE_HEADING_RE,
    PROMOTION_LOG_HEADING_RE,
    detect_index_shape,
)
from read_limits import (  # noqa: F401  (re-exported for the banner)
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
)

# --------------------------------------------------------------------------
# Refusal collection -- one planning pass reports every refusal it finds
# --------------------------------------------------------------------------

FIX_ROW = "fix by hand: repair or remove each Master Table row named"
FIX_RESOLVE = "fix by hand: make each id named resolve to exactly one lesson file"
FIX_LESSON = "fix by hand: repair each lesson file named"
FIX_LOG_ROW = "fix by hand: repair or remove each Rule Promotion Log row named"
FIX_FOREIGN = "fix by hand: move each file named aside or delete it"
FIX_BACKFILL = "pass --backfill-frontmatter"
FIX_QUOTES = "pass --quote-titles"
FIX_RECONCILE = "pass --reconcile index-wins or --reconcile frontmatter-wins"
FIX_HARVEST = "pass --harvest-cells"
FIX_RELOCATE = "pass --relocate-prose"


class RefusalSet(Refusal):
    """Every refusal one planning pass found, raised once at its end.

    `items` is `[(fix, detail), ...]` in the order found: `fix` names the
    flag or hand fix that closes the refusal (one of the `FIX_*` names),
    and `detail` names its row, file or line. The message groups the
    details under their fix, in first-seen order. A subclass of `Refusal`,
    so a caller catching `Refusal` still catches it."""

    def __init__(self, items):
        self.items = list(items)
        groups: dict = {}
        for fix, detail in self.items:
            groups.setdefault(fix, []).append(detail)
        lines = [f"{len(self.items)} refusal(s); nothing was written. Each group names what closes it:"]
        for fix, details in groups.items():
            lines.append(f"{fix} ({len(details)}):")
            lines += [f"  - {detail}" for detail in details]
        message = "\n".join(lines)
        Exception.__init__(self, message)  # the multi-line message is never split or rejected
        self.reason = message
        self.fix = "; ".join(groups)
        self.question = None

    def lines(self) -> list:
        """One line per refusal: its detail, then what closes it."""
        return [f"{detail} -- {fix}" for fix, detail in self.items]


# --------------------------------------------------------------------------
# Shape recognition
# --------------------------------------------------------------------------

MASTER_TABLE_HEADING = "Master Table"
PROMOTION_LOG_HEADING = "Rule Promotion Log"


def classify_shape(text: str):
    """Return (shape, detail). Wraps `parse_lessons.detect_index_shape`,
    the one shape detector -- never re-derived (routed condition: a lone
    shape detector is imported, not carried a second time). `shape` is
    "legacy", "generated" or "unrecognized" (`detect_index_shape`'s
    "empty" renamed to this migrator's report vocabulary). `detail` names
    which heading matched for "legacy", the `Generated:` line for
    "generated", and what was looked for and not found for
    "unrecognized"."""
    raw = detect_index_shape(text)
    if raw == "legacy":
        master = bool(MASTER_TABLE_HEADING_RE.search(text))
        log = bool(PROMOTION_LOG_HEADING_RE.search(text))
        if master and log:
            which = "'## Master Table' and '## Rule Promotion Log' headings"
        elif master:
            which = "'## Master Table' heading"
        else:
            which = "'## Rule Promotion Log' heading"
        return "legacy", f"{which} present"
    if raw == "generated":
        line = GENERATED_LINE_RE.search(text)
        detail = line.group(0) if line else "Generated:"
        return "generated", f"{detail!r} line present"
    return "unrecognized", "no '## Master Table', '## Rule Promotion Log' or 'Generated:' line found"


# --------------------------------------------------------------------------
# Region location
# --------------------------------------------------------------------------

_HEADING_LINE_RE = re.compile(r"^##\s+(.+?)\s*$")
_LAST_UPDATED_LINE_RE = re.compile(r"^\*\*Last Updated:\*\*.*$")
_PREVIOUS_RE = re.compile(r"^<!--\s*Previous:", re.DOTALL)
_KNOWN_COND_RE = re.compile(r"^<!--\s*known-condition:", re.DOTALL)
_COUNTER_LINE_RE = re.compile(r"^\*\*Next available ID:\*\*.*$")
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")


def _fenced_lines(lines: list) -> list:
    """One flag per line: True when the line opens, sits inside, or closes
    a fenced code block. A fence opens on a ``` or ~~~ run of three or
    more and closes on a run of the SAME character at least as long, with
    nothing after it but whitespace; a backtick opener whose info string
    carries a backtick is not a fence. An opener that never closes is not
    a fence either -- its line stays body text and the walk resumes on the
    next line -- so one stray run cannot hide every heading after it."""
    flags = [False] * len(lines)
    i = 0
    while i < len(lines):
        m = _FENCE_RE.match(lines[i].rstrip("\r"))
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            char, width = m.group(1)[0], len(m.group(1))
            for j in range(i + 1, len(lines)):
                c = _FENCE_RE.match(lines[j].rstrip("\r"))
                if c and c.group(1)[0] == char and len(c.group(1)) >= width and not c.group(2).strip():
                    flags[i:j + 1] = [True] * (j + 1 - i)
                    i = j
                    break
        i += 1
    return flags


def _comment_units(lines: list, start: int, end: int, fenced: list) -> list:
    """Every HTML comment that opens a line in `lines[start:end]`, outside
    a fence, as (first_line, last_line_exclusive, raw_text). A comment
    runs to the first line holding `-->`; one that never closes before
    `end` is its opening line alone."""
    units, i = [], start
    while i < end:
        if not fenced[i] and lines[i].strip().startswith("<!--"):
            j = i
            while j < end - 1 and "-->" not in lines[j]:
                j += 1
            if "-->" not in lines[j]:
                j = i
            units.append((i, j + 1, "\n".join(lines[i:j + 1])))
            i = j + 1
        else:
            i += 1
    return units


def _counter_block(lines: list, idx: int, fenced: list) -> tuple:
    """(comments, end): the HTML comments that follow the counter line at
    `idx` -- blank lines between them allowed -- and the exclusive line
    index where the counter block ends. A legacy hub keeps its counter's
    drift record here, so these comments are header history, never a
    section's own text."""
    comments, i = [], idx + 1
    while True:
        j = i
        while j < len(lines) and not lines[j].strip():
            j += 1
        units = _comment_units(lines, j, len(lines), fenced) if j < len(lines) else []
        if not units or units[0][0] != j:
            return comments, (comments[-1][1] if comments else idx + 1)
        comments.append(units[0])
        i = units[0][1]


def _section_key(sections: dict, heading: str) -> str:
    """`heading` itself for its first occurrence; `"{heading} [n]"` for a
    later one, with `n` counted up until the key is unused, so no section
    ever overwrites another."""
    key, n = heading, 1
    while key in sections:
        n += 1
        key = f"{heading} [{n}]"
    return key


def locate_regions(text: str) -> dict:
    """Every recognised region of a legacy lessons hub, located by heading
    text -- never by a fixed line number, so this works on any consumer's
    hub. The heading walk is fence-aware (`_fenced_lines`): a `## ` line
    inside a fenced code block is body text, never a section. Returns:

    - "header": the preamble's `**Last Updated:**` line as
      (line_index, raw_line), and its HTML comments -- plus the comments
      of the counter block -- each as (line_index, raw_text) under
      "previous", "known_condition" (the first one) or "drift_comments".
      A comment may span lines.
    - "counter": the first `**Next available ID:**` line outside a fence,
      as (line_index, raw_line) or None. The counter block is that line
      plus the comments that follow it (`_counter_block`).
    - "sections": key -> {"heading", "line_start", "line_end", "body"},
      one entry per `## ` heading in on-disk order: heading line to the
      next `## ` heading or EOF. The key is the heading text; a repeated
      heading keeps every occurrence under a key disambiguated by
      `_section_key`, and "heading" always holds the real text. `body` is
      the section's exact text after its heading line, minus the counter
      block when the block sits inside it.
    - "spans": (kind, name, start, end) character spans over `text`,
      kind "header", "counter" or "section". They never overlap and
      together cover every character once, so the header side owns the
      counter and its comments and no section carries them a second
      time."""
    lines = text.split("\n")
    fenced = _fenced_lines(lines)
    names: dict = {}
    for i, ln in enumerate(lines):
        match = None if fenced[i] else _HEADING_LINE_RE.match(ln.strip())
        if match:
            names[i] = match.group(1)
    heading_idxs = sorted(names)
    first = heading_idxs[0] if heading_idxs else len(lines)
    counter = next(((i, ln) for i, ln in enumerate(lines)
                    if not fenced[i] and _COUNTER_LINE_RE.match(ln.strip())), None)
    block_comments, block = [], (0, 0)
    if counter is not None:
        block_comments, block_end = _counter_block(lines, counter[0], fenced)
        block = (counter[0], block_end)

    # Each line's owner is (kind, key): the key is the section's heading
    # line index, so two sections sharing a heading text never merge.
    owner: list = [("header", -1)] * len(lines)
    for k, idx in enumerate(heading_idxs):
        end = heading_idxs[k + 1] if k + 1 < len(heading_idxs) else len(lines)
        owner[idx:end] = [("section", idx)] * (end - idx)
    owner[block[0]:block[1]] = [("counter", -1)] * (block[1] - block[0])

    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)
    runs: list = []  # [kind, key, start, end]
    for i, (kind, key) in enumerate(owner):
        start, end = offsets[i], min(offsets[i + 1], len(text))
        if runs and runs[-1][0] == kind and runs[-1][1] == key:
            runs[-1][3] = end
        else:
            runs.append([kind, key, start, end])

    sections = {}
    for k, idx in enumerate(heading_idxs):
        end = heading_idxs[k + 1] if k + 1 < len(heading_idxs) else len(lines)
        body_start = min(offsets[idx + 1], len(text))
        body = "".join(text[max(s, body_start):e] for kind, key, s, e in runs
                       if kind == "section" and key == idx and e > body_start)
        sections[_section_key(sections, names[idx])] = {
            "heading": names[idx], "line_start": idx, "line_end": end, "body": body}
    spans = [(kind, names.get(key, "") if kind == "section" else "", s, e) for kind, key, s, e in runs]

    units = [u for u in _comment_units(lines, 0, first, fenced) if not block[0] <= u[0] < block[1]]
    units = sorted(units + block_comments)
    previous = [(u[0], u[2]) for u in units if _PREVIOUS_RE.match(u[2].strip())]
    known = [(u[0], u[2]) for u in units if _KNOWN_COND_RE.match(u[2].strip())]
    header = {
        "last_updated": next(((i, lines[i]) for i in range(first)
                              if not block[0] <= i < block[1] and _LAST_UPDATED_LINE_RE.match(lines[i].strip())),
                             None),
        "previous": previous,
        "known_condition": known[0] if known else None,
        "drift_comments": [(u[0], u[2]) for u in units
                           if (u[0], u[2]) not in previous and (u[0], u[2]) not in known[:1]],
    }
    return {"header": header, "counter": counter, "sections": sections, "spans": spans}


# --------------------------------------------------------------------------
# Header changelog extraction
# --------------------------------------------------------------------------

def extract_header_changelog(text: str) -> list:
    """Every relocatable header-history span, in on-disk order: the
    `**Last Updated:**` line's trailing history text (the text after its
    date, when present), each `<!-- Previous: ... -->` comment's inner
    text, every other header comment -- the preamble's and the counter
    block's, a drift record -- and finally the `<!-- known-condition: ...
    -->` note, flagged "drop-with-ledger" because it names a project's own
    schedule that a consumer never had. A comment may span lines. Each
    segment is `{"kind", "text", "flag"}`."""
    header = locate_regions(text)["header"]
    segments = []
    if header["last_updated"]:
        _, ln = header["last_updated"]
        m = re.match(r"^\*\*Last Updated:\*\*\s*(?:\d{4}-\d{2}-\d{2})?\s*(.*)$", ln.strip())
        history = m.group(1).strip() if m else ""
        if history:
            segments.append({"kind": "last-updated", "text": history, "flag": None})
    for _, ln in header["previous"]:
        m = re.match(r"^<!--\s*Previous:\s*(.*?)\s*-->\s*$", ln.strip(), re.DOTALL)
        segments.append({"kind": "previous", "text": (m.group(1) if m else ln.strip()), "flag": None})
    for _, ln in header["drift_comments"]:
        segments.append({"kind": "drift-comment", "text": ln.strip(), "flag": None})
    if header["known_condition"]:
        _, ln = header["known_condition"]
        segments.append({"kind": "known-condition", "text": ln.strip(), "flag": "drop-with-ledger"})
    return segments


# --------------------------------------------------------------------------
# Changelog rendering
# --------------------------------------------------------------------------

_RELOCATED_TITLE = "Relocated hand-written index sections (migrated {date})"


def render_relocated_entry(sections: list, today: str) -> str:
    """The one changelog-entry body a relocated (non-dropped) prose
    section lands in: titled "Relocated hand-written index sections
    (migrated YYYY-MM-DD)", each relocated section byte-verbatim under its
    own heading demoted from `## ` to `### `. The demotion is the only
    change: `body` -- the section's exact text after its heading line, as
    `locate_regions` returns it -- follows the `### ` line unchanged, blank
    lines and trailing rule included. `sections` is `[(heading, body),
    ...]`, in on-disk order."""
    out = _RELOCATED_TITLE.format(date=today) + "\n\n"
    for heading, body in sections:
        if not out.endswith("\n"):
            out += "\n"
        out += f"### {heading}\n{body}"
    return out if out.endswith("\n") else out + "\n"


def _entry_body(seg) -> str:
    return seg["text"] if isinstance(seg, dict) else seg


def _archive_naming(naming, changelog_name: str, year: str) -> IndexNaming:
    """The archive file's own naming, derived from the CURRENT changelog
    filename the generator already computed -- the stem is never
    re-derived a second time. `_changelog_filename` recognises the
    `00-Index-{X}` shape, so building a synthetic hub_stem of
    `00-Index-{X}-Archive-{YYYY}` makes it emit
    `00-Changelog-{X}-Archive-{YYYY}{suffix}` for free."""
    prefix, suffix = "00-Changelog-", naming.suffix
    x = changelog_name[len(prefix):-len(suffix)] if changelog_name.startswith(prefix) else naming.hub_stem
    stem = f"00-Index-{x}-Archive-{year}"
    return IndexNaming(hub_name=stem + suffix, hub_stem=stem, suffix=suffix, archive_stem=naming.archive_stem)


def render_changelog(segments: list, index_name: str, nl: str, today: str) -> list:
    """`00-Changelog-{X}.md`, opening with the backlink, then `## Entry N`
    sections newest-first (`segments[0]` is the newest). Numbers are stable
    ascending across the whole family: the newest of `len(segments)`
    entries is Entry `len(segments)`, the oldest is Entry 1, so the
    numbers descend top to bottom through the main file, the archive, and
    every further part, the scheme `lessons_changelog.py --append` extends
    with max + 1. Each item of
    `segments` is either a dict carrying a "text" key (as
    `extract_header_changelog` returns) or a plain pre-rendered entry body
    string (e.g. from `render_relocated_entry`).

    When the whole file would measure at or over `READ_TOKEN_WARN`, the
    oldest entries move to `00-Changelog-{X}-Archive-{YYYY}.md`, linked
    both ways, and past `READ_PAGE_CAP_TOKENS` into `-Part-{NN}.md` parts.
    The layout, the rendering and the read-back check are
    `lessons_changelog.render_family`'s -- the engine `--append`, `--split`
    and the upgrade re-split use -- so the next `plan_split` finds nothing
    to move. Each body is taken in `lessons_changelog.canonical_body` form
    (no blank line at either end). Raises `Refusal` when a body would not
    read back as one entry. Returns `[(filename, text), ...]`, the current
    file first, in `nl` newlines."""
    import lessons_changelog  # deferred: lessons_changelog imports this module

    top = len(segments)
    entries = [(top - i, "", lessons_changelog.canonical_body(_entry_body(seg))) for i, seg in enumerate(segments)]
    return [(name, text.replace("\n", nl))
            for name, text in lessons_changelog.render_family(entries, _index_naming(Path(index_name)),
                                                              index_name, today[:4])]


def changelog_part_filename(naming, k: int) -> str:
    """`{stem}-Part-{kk}{suffix}`, derived from `_changelog_filename`'s own
    result -- never from the hub name directly. Mirror of
    `migrate_backlog_support.changelog_part_filename`, kept local because
    the archive-part naming here nests under a synthetic `-Archive-{YYYY}`
    naming this module builds (see `_archive_naming`), not the caller's
    plain hub naming."""
    stem_path = Path(_changelog_filename(naming))
    return f"{stem_path.stem}-Part-{k:02d}{stem_path.suffix}"


# --------------------------------------------------------------------------
# Rule Promotion Log
# --------------------------------------------------------------------------

_LOG_HEADER = "| Date | Lesson ID | Artifact Created | File |"
_LOG_SEP = "|------|-----------|-----------------|------|"
_LOG_SEP_RE = re.compile(r"^\|[-\s|:]+\|$")


def is_placeholder_row(cells) -> bool:
    """True for a table row whose every cell is empty after stripping --
    the empty placeholder row the legacy seed ships under its Master Table
    and Rule Promotion Log separators. A row with any cell filled is never
    a placeholder, however malformed it is otherwise."""
    return all(not str(cell).strip() for cell in cells)


def split_placeholder_rows(rows: list) -> tuple:
    """`(kept, skipped_lines)`: parsed Master Table `rows` without their
    placeholder rows, and the 1-based line of each one skipped."""
    return ([row for row in rows if not is_placeholder_row(row.cells)],
            [row.line for row in rows if is_placeholder_row(row.cells)])


def walk_promotion_log(text: str, refusals: list | None = None, skipped: list | None = None,
                       leftover: list | None = None) -> list:
    """Every Rule Promotion Log data row, walked -- never keyed by id, so a
    repeated lesson id is reported by the caller instead of silently
    collapsed (count rows before keying). Rows are found by splitting on
    `"\\n"` only, never `str.splitlines()`, so a lone CR inside a cell (not
    part of a `"\\r\\n"` pair) is data, never a row terminator.

    A 3-cell row is kept as SHORT: `short` is flagged True and no 4th cell
    is invented. A physical line whose cells do not resolve to 3 or 4, and
    whose next physical line does not itself open a new row with `|`, is a
    fragmented row: the continuation is joined (with no leading `|`)
    until the cells resolve, or the row is refused, naming the line. A
    row with no `LL-` id in its Lesson ID cell is refused the same way.
    A table whose header is not the recognised `| Date | Lesson ID | ...`
    header -- or a recognised header not followed by its separator -- is
    refused naming its first line, and its lines are consumed with it.

    A placeholder row (`is_placeholder_row`) is skipped, and its line is
    appended to `skipped` when a list is given. With `refusals` given,
    each refusal is appended as `(FIX_LOG_ROW, detail)` and the walk goes
    on; without it, the first one raises `Refusal`. With `leftover`
    given, every section line the table walk did not consume -- intro
    prose, a callout, a note, blank lines -- is appended to it as
    `(line_no, raw_line)`, so the caller can relocate or refuse it
    (`promotion_log_residue`) rather than lose it.

    The walk skips the counter block when it sits inside the section: the
    counter line and its drift comments belong to the header side
    (`locate_regions` "spans"), so they are never log rows or residue, and
    every line lands in exactly one region.

    Returns `[{"line", "cells", "lesson_id", "short", "fragmented"}, ...]`."""
    regions = locate_regions(text)
    section = regions.get("sections", {}).get(PROMOTION_LOG_HEADING)
    if section is None:
        return []
    lines = text.split("\n")
    counter_spans = [(s, e) for kind, _name, s, e in regions["spans"] if kind == "counter"]
    offset = sum(len(ln) + 1 for ln in lines[:section["line_start"] + 1])
    body, numbers = [], []  # the section's own lines, and each one's 1-based line number
    for idx in range(section["line_start"] + 1, section["line_end"]):
        if not any(s <= offset < e for s, e in counter_spans):
            body.append(lines[idx])
            numbers.append(idx + 1)
        offset += len(lines[idx]) + 1
    rows = []

    def refuse(detail: str) -> None:
        if refusals is None:
            raise Refusal(detail, fix=FIX_LOG_ROW)
        refusals.append((FIX_LOG_ROW, detail))

    i, header_seen, sep_seen = 0, False, False
    while i < len(body):
        raw = body[i].rstrip("\r")
        s = raw.strip()
        line_no = numbers[i]
        if not sep_seen and s.startswith("|"):
            if not header_seen and s.lower().replace(" ", "").startswith("|date|"):
                header_seen = True
                i += 1
                continue
            if header_seen and _LOG_SEP_RE.match(s):
                sep_seen = True
                i += 1
                continue
            what = ("follows the recognised header but is not its separator" if header_seen else
                    f"is a table whose header is not the recognised header {_LOG_HEADER!r}")
            refuse(f"promotion-log line {line_no} {what}: {raw!r}")
            while i + 1 < len(body) and body[i + 1].lstrip().startswith("|"):
                i += 1
            i += 1
            continue
        if not sep_seen or not s.startswith("|"):
            if leftover is not None:
                leftover.append((line_no, body[i]))
            i += 1
            continue
        cells = row_cells(raw)
        closed = raw.rstrip().endswith("|")
        if closed and is_placeholder_row(cells):
            if skipped is not None:
                skipped.append(line_no)
            i += 1
            continue
        joined_raw, j = raw, i
        while (not closed or len(cells) not in (3, 4)) and j + 1 < len(body) and body[j + 1].strip() != "" \
                and not body[j + 1].lstrip().startswith("|"):
            j += 1
            joined_raw = joined_raw.rstrip() + " " + body[j].strip()
            cells = row_cells(joined_raw)
            closed = joined_raw.rstrip().endswith("|")
        lid_match = re.search(r"LL-(\d+)", cells[1]) if len(cells) > 1 else None
        problem = None
        if len(cells) not in (3, 4) or not closed:
            problem = "does not resolve to 3 or 4 cells after joining any continuation text"
        elif lid_match is None or int(lid_match.group(1)) < 1:
            problem = "has no parseable LL- id in its Lesson ID cell"
        if problem:
            refuse(f"promotion-log row at line {line_no} {problem}: {raw!r}")
            i = j + 1
            continue
        rows.append({
            "line": line_no, "cells": tuple(cells),
            "lesson_id": int(lid_match.group(1)) if lid_match else None,
            "short": len(cells) == 3, "fragmented": j != i,
        })
        i = j + 1
    return rows


_THEMATIC_BREAK_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")


def promotion_log_residue(leftover: list) -> tuple:
    """`(body, content_lines)` for the lines `walk_promotion_log` left
    unconsumed. `content_lines` are the 1-based line numbers of every
    line carrying content -- anything but a blank line or a bare
    horizontal rule, which is section structure the seed carries too.
    When there is none, returns `("", [])`: nothing to relocate. Otherwise
    `body` keeps every leftover line byte-verbatim, in order, with runs of
    blank lines collapsed to one and none at either end, ending in a
    newline -- the text a relocated-sections changelog entry carries."""
    content = [n for n, raw in leftover if raw.strip() and not _THEMATIC_BREAK_RE.match(raw.strip())]
    if not content:
        return "", []
    kept: list = []
    for _n, raw in leftover:
        if not raw.strip() and (not kept or not kept[-1].strip()):
            continue
        kept.append(raw)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n", content


# The Archive century bands of the promotion log, in ascending order: each
# pair is (highest lesson id the band holds, the band's filename label). An
# id above the last upper bound belongs to the hub-side file. This table is
# the single owner of the band boundaries: `log_destination` routes by it and
# `century_log_filenames` lists from it, so the two cannot disagree.
_CENTURY_BANDS = (
    (50, "001-050"),
    (75, "051-075"),
    (100, "076-100"),
    (200, "101-200"),
)


def _century_filename(stem: str, label: str, naming) -> str:
    return f"Archive/{stem}-{label}{naming.suffix}"


def log_destination(lesson_id: int, naming) -> str:
    """The append target as a pure function of the id alone: <=50, 51-75,
    76-100 and 101-200 to their Archive century file, >=201 to the
    hub-side file (the bands are `_CENTURY_BANDS`). `naming` is a lessons
    `IndexNaming` (see `_index_naming`); every filename derives from it,
    never hardcoded, so a custom `index_files.lessons` renames every
    century file along with the hub. A promotion-log writer that appends
    rows after migration routes each row through this same function, so
    keep its `(lesson_id: int, naming) -> str` signature stable."""
    if lesson_id is None or lesson_id < 1:
        raise Refusal(f"promotion-log row names lesson id {lesson_id!r}, out of the expected range",
                      "correct the lesson id in that row to an existing lesson, or delete the row")
    hub_name = _promotion_log_filename(naming)
    stem = Path(hub_name).stem.removeprefix("00-")
    for upper_bound, label in _CENTURY_BANDS:
        if lesson_id <= upper_bound:
            return _century_filename(stem, label, naming)
    return hub_name


def century_log_filenames(naming) -> list:
    """Every Archive century filename of the promotion log, in band order
    (lowest ids first) -- the files `log_destination` can return other than
    the hub-side file. Derived from the same band table as
    `log_destination`, so a caller that enumerates the century files asks
    the owner of the bands instead of probing it with hardcoded ids."""
    stem = Path(_promotion_log_filename(naming)).stem.removeprefix("00-")
    return [_century_filename(stem, label, naming) for _upper_bound, label in _CENTURY_BANDS]


def _existing_archive_parts(lessons_dir: Path, naming) -> list:
    """The Archive century filenames that exist on disk right now, sorted
    ascending -- the same set and order `render_promotion_logs` lists in a
    hub's `Parts:` line. Derived by asking `century_log_filenames` -- never
    hardcoding the band boundaries or the stem -- for every band's file,
    then checking which of those files are present. The one helper both
    `render_promotion_logs` (the migrator) and the guarded promotion-log
    writer call, so the two cannot disagree about which parts exist."""
    return sorted(n for n in century_log_filenames(naming) if (lessons_dir / n).is_file())


def render_promotion_logs(rows: list, naming, nl: str, lessons_dir: "Path | None" = None) -> list:
    """Group `rows` (as `walk_promotion_log` returns) by `log_destination`
    and render each file: a backlink to the hub, then the 4-column table
    (`Date | Lesson ID | Artifact Created | File`). The hub-side file
    additionally lists every Archive part it owns, and is rendered whenever
    any Archive part is, even when no row routes to it (a family under 201
    lessons has only century files). With `lessons_dir`, that listing is the
    sorted union of the parts the rows route to and the century files
    already on disk there (`_existing_archive_parts`), so a century file no
    row routes to is still listed; the file itself is neither rendered nor
    rewritten. Without it, only the routed parts are listed. No rows render
    nothing, whatever is on disk. Returns `[(filename, text), ...]`."""
    hub_name = _promotion_log_filename(naming)
    by_dest: dict = {}
    for row in rows:
        dest = log_destination(row["lesson_id"], naming)
        by_dest.setdefault(dest, []).append(row)
    listed = {d for d in by_dest if d != hub_name}
    if rows and lessons_dir is not None:
        listed |= set(_existing_archive_parts(lessons_dir, naming))
    archive_parts = sorted(listed)
    if archive_parts:
        by_dest.setdefault(hub_name, [])
    out = []
    for dest in sorted(by_dest):
        dest_rows = sorted(by_dest[dest], key=lambda r: r["line"])
        lines = [f"[← {naming.hub_name}]({naming.hub_name})"]
        if dest == hub_name and archive_parts:
            listing = ", ".join(f"[{p}]({p})" for p in archive_parts)
            lines.append(f"Parts: {listing}")
        lines += ["", _LOG_HEADER, _LOG_SEP]
        for row in dest_rows:
            cells = list(row["cells"]) + [""] * (4 - len(row["cells"]))
            lines.append("| " + " | ".join(cells) + " |")
        out.append((dest, nl.join(lines) + nl))
    return out


# --------------------------------------------------------------------------
# Prose-section disposition
# --------------------------------------------------------------------------

def section_disposition(heading: str, body: str, seed_bodies: dict) -> tuple:
    """"drop" when `normalize(body)` equals the same heading's body in the
    seed table (whitespace-collapsed, case-folded, line endings ignored --
    `normalize` is imported from `migrate_backlog_support`, one lookup
    covers both shipped seed tags, since 1.0.5 and 1.0.5.1 are
    byte-identical); "relocate" otherwise, including when the heading is
    not in the table at all -- heading match is exact, so a reworded
    heading always relocates rather than false-matching a differently
    named seed section."""
    seed_body = seed_bodies.get(heading)
    if seed_body is not None and normalize(body) == normalize(seed_body):
        return "drop", f"'{heading}' text equals the shipped seed's"
    return "relocate", f"'{heading}' text differs from the shipped seed's (or the seed carries no such section)"


def seed_normalized(text: str) -> str:
    """`text` with one leading BOM removed and every CRLF turned into LF:
    the form in which a seeded file and its source compare equal, whatever
    line endings a checkout or an editor gave either copy."""
    return text.removeprefix(chr(0xFEFF)).replace("\r\n", "\n")


# The plugin's own seed/ directory: the lessons bootstrap copies its
# changelog and promotion-log seeds from here byte for byte.
_SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
_SEPARATOR_4_RE = re.compile(r"^\|(?:[ \t]*-+[ \t]*\|){4}$")
# The hub's `Parts:` listing line as `render_promotion_logs` writes it: the
# prefix, then one or more `[text](href)` links separated by commas.
_PARTS_LINE_RE = re.compile(r"^Parts:[ \t]*\[[^\]]*\]\([^)]*\)(?:[ \t]*,[ \t]*\[[^\]]*\]\([^)]*\))*$")


def _bootstrap_log_seeds() -> tuple:
    """The normalised text of every seed the lessons bootstrap copies to a
    changelog or promotion-log path: each name after the hub in
    `lessons_bootstrap._LESSONS_SEED_SRC_NAMES`, read from the seed/
    directory it copies from. A seed missing from this install is left
    out."""
    seeds = []
    for name in _LESSONS_SEED_SRC_NAMES[1:]:
        try:
            seeds.append(seed_normalized((_SEED_DIR / name).read_bytes().decode("utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return tuple(seeds)


def header_only(text: str, index_name: str) -> bool:
    """True when `text` (a changelog or promotion-log file's content) holds
    only its opener. Such a file carries no content a refusal would
    protect, so a caller treats it as absent, never as foreign. Both forms
    compare with any BOM removed and line endings ignored:

    - the generated opener: the backlink to `index_name`, alone or followed
      by an optional `Parts:` listing line, an optional blank line, the
      4-column log header, and a separator whose four cells are runs of `-`,
      with zero data rows. The listing line is derived from the century
      files on disk, so nothing a refusal would protect is lost with it. It
      counts only when it is a `Parts:` prefix followed by links and
      separators and nothing else; any other line in that position is
      hand-written content and the file is foreign. One data row, or any
      line past the separator, makes the file foreign;
    - the exact text the lessons bootstrap seeds (`_bootstrap_log_seeds`).
      Its backlink names the default hub, so it matches even in a project
      whose index has a custom name."""
    norm = seed_normalized(text)
    if norm in _bootstrap_log_seeds():
        return True
    backlink = f"[← {index_name}]({index_name})"
    lines = norm.strip().split("\n")
    if lines == [backlink]:
        return True
    if lines[0] != backlink:
        return False
    rest = lines[1:]
    if rest and _PARTS_LINE_RE.match(rest[0].strip()):
        rest = rest[1:]
    if rest and not rest[0].strip():
        rest = rest[1:]
    return (len(rest) == 2 and rest[0].strip() == _LOG_HEADER
            and bool(_SEPARATOR_4_RE.match(rest[1].strip())))


# --------------------------------------------------------------------------
# Seed bodies -- shipped constant, never read from a consumer's install
# cache at migration time: an older install cache may no longer exist,
# and the plugin's current seed/ may now be generated-shape. One body per
# heading; the git tags 1.0.5 and 1.0.5.1
# are byte-identical for this file, so a single table covers both. Each
# body is a whole section as the fence-aware `locate_regions` sees it: the
# Lesson File Template body keeps the `## ` lines fenced inside its
# example block, because a fenced heading is body text, not a section.
# --------------------------------------------------------------------------

SEED_BODIES = {
    "Naming Convention": (
        "**Format:** `LL-{NNN}-{Domain}-{Name}.md`\n"
        "\n"
        "| Component | Description | Example |\n"
        "|-----------|-------------|---------|\n"
        "| `LL` | Lessons Learned prefix | LL |\n"
        "| `{NNN}` | Global sequence number (zero-padded to 3 digits) | 001, 023 |\n"
        "| `{Domain}` | Abbreviation from config.yaml (`abbreviations` + `lesson_abbreviations`) | DOC, TOOL |\n"
        "| `{Name}` | PascalCase descriptive name | QueryFilterTranslation |\n"
        "\n"
        "---\n"
    ),
    "Status Definitions": (
        "| Status | Meaning |\n"
        "|--------|---------|\n"
        "| `documented` | Captured; not yet owned by any backlog item. |\n"
        "| `promoted` | Fully captured into actionable backlog item(s); archived; awaiting landing; "
        "the backlog item is the live owner. **archived ≠ landed.** |\n"
        "| `applied` | Lesson applied to improve a process or pattern |\n"
        "| `rule` | Lesson promoted to a `.claude/` artifact |\n"
        "| `orphaned` | Content was fully captured into an owning item that has since closed without "
        "landing it, and no live item currently owns it. Work-surfacing: resurfaces ahead of "
        "`documented` in the next promotion pass. |\n"
        "\n"
        "---\n"
    ),
    "Quick Reference": (
        "| Action | How |\n"
        "|--------|-----|\n"
        "| Find lessons by tag | `/lessons python regex` |\n"
        "| Find by domain | `/lessons myproject` |\n"
        "| Find by category | `/lessons anti-pattern` |\n"
        "| List all lessons | `/lessons` (no arguments) |\n"
        "| Create new lesson | Use template below, next ID = LL-001 |\n"
        "\n"
        "---\n"
    ),
    "Lesson File Template": (
        "```yaml\n"
        "---\n"
        "id: LL-{NNN}\n"
        "title: {Descriptive title}\n"
        "date: {YYYY-MM-DD}\n"
        "source: {session reference}\n"
        "category: {anti-pattern | pattern | process}\n"
        "severity: {low | medium | high}\n"
        "language: [{python | csharp | javascript | ...}]\n"
        "technology: [{specific tech}]\n"
        "domain: [{project domains}]\n"
        "status: documented\n"
        "applied-as: null\n"
        "promotion-target: [rule|code|claude-md|agent|skill|settings]   # one or more target types; "
        "multi-value = coarse / split-candidate\n"
        "# promoted-to:                                                  # owning backlog item id(s), "
        "e.g. BB-{NNN}; set at capture-archive\n"
        "# rule-as:                                                      # DEPRECATED alias for "
        "applied-as — read for back-compat, never written\n"
        "---\n"
        "\n"
        "# LL-{NNN}-{Domain}: {Same title as frontmatter}\n"
        "\n"
        "## Context\n"
        "\n"
        "{What happened — specific file, function, input, error.}\n"
        "\n"
        "## Lesson\n"
        "\n"
        "{The insight or fix. Include WRONG/CORRECT code examples for anti-patterns.}\n"
        "\n"
        "## Applies To\n"
        "\n"
        "{When this lesson is relevant — technologies, file patterns, scenarios.}\n"
        "```\n"
        "\n"
        "### Pointer Fields — Authoritative Definition\n"
        "\n"
        "Two frontmatter fields answer two different questions. This table is the single source of "
        "truth for their meaning; every other document that mentions them defers here rather than "
        "restating the semantics.\n"
        "\n"
        "| Field | Answers | Value form | Written when |\n"
        "|-------|---------|-----------|--------------|\n"
        "| `promoted-to:` | **Who owns the work?** | Backlog item id(s) — `BB-{NNN}`, listing every "
        "owner when a lesson decomposed across several items | At capture-archive, when the lesson "
        "becomes owned |\n"
        "| `applied-as:` | **Where did it land?** | Path(s) to the artifact(s) actually created — a "
        "scalar, or a YAML list when a lesson landed in several files | At landing, replacing `null` "
        "or a `PENDING:BB-{NNN}` marker |\n"
        "\n"
        "`applied-as:` is the artifact pointer for **both** terminal statuses (`rule` and `applied`) "
        "— the `status:` field, not a second pointer key, records which kind of landing it was.\n"
        "\n"
        "> [!constraint] `rule-as:` is deprecated — read it, never write it\n"
        "> An older scheme inverted these two fields: `applied-as:` held the owning backlog item and a "
        "separate `rule-as:` held the artifact. That scheme is superseded. Tooling MUST still **read** "
        "`rule-as:` so pre-existing lessons keep resolving, but MUST NOT **write** it, and MUST NOT "
        "treat its presence as an error.\n"
        ">\n"
        "> Migrating a legacy lesson is a **value remap between two keys, not a key rename**: the "
        "artifact path moves from `rule-as:` into `applied-as:`, and whatever `applied-as:` previously "
        "held (an owning backlog item) moves into `promoted-to:` — normalised to id form, since a "
        "stored path to a backlog item breaks as soon as that item is archived. Preserve a list-valued "
        "pointer as a YAML list; do not flatten it to a delimited string.\n"
        ">\n"
        "> WRONG — relabel one key and call it migrated:\n"
        "> ```yaml\n"
        "> status: rule\n"
        "> applied-as: {backlog-dir}/BB-{NNN}-{SB}-{Domain}-{Topic}.md   # still the OWNER, now under "
        "the artifact key\n"
        "> ```\n"
        "> CORRECT — remap the values, then drop the legacy key:\n"
        "> ```yaml\n"
        "> status: rule\n"
        "> applied-as: references/{artifact}.md §{N}                      # the artifact\n"
        "> promoted-to: BB-{NNN}                                          # the owner\n"
        "> ```\n"
    ),
    "Archive": (
        "A lesson is moved to `Archive/` when **fully captured** — either single-promote "
        "(→ `applied`/`rule`) or promote-batch (→ `promoted`). Archived lessons remain "
        "searchable via `/lessons <terms>` (search globs recurse into `Archive/`).\n"
        "\n"
        "**Location:** `{lessons-dir}/Archive/`\n"
        "\n"
        "---\n"
    ),
}
