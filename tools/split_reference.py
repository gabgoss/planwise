#!/usr/bin/env python3
"""Split whole sections of a reference file into a new `{stem}-Part-N-{Topic}.md` sibling.

Dev-repo writer. Nothing in the shipped plugin calls it and no consumer install
runs it, so it lives outside the shipped subtree with the other maintainer tools.

The tool reproduces the manual split procedure, in this order:

  1. Read every file it may edit with newline="" and refuse one whose line
     endings mix CRLF with bare LF, or that holds a carriage return that ends
     no line.
  2. Locate each requested section by its numbered heading (fenced code is
     skipped) and take the whole section: the heading line up to the next
     heading at the same or a shallower level, or up to a held-in block an
     earlier split left there for a section at the same or a shallower depth.
     A held-in block for a deeper subsection moves with its section. Sections
     move by heading, never by line range, and moved text is never retyped or
     edited.
  3. Verify in memory, before any write: each moved body's sha256 equals its
     sha256 in the new file, and the body appears there exactly once; the
     remainder's sha256 equals the source minus the moved bodies; the heading
     set before the split equals the disjoint union of the heading sets after
     it, so every section keeps its `§N`.
  4. Keep the original filename for Part 1 and append the new Part after the
     last one (a new Part never takes a number an existing Part holds).
  5. Derive one pointer block per family member from the post-split heading
     sets, with the part count templated. A member that already has a block
     gets it replaced in place, and the source gets one inserted when it has
     none (at the first kept line at or after the first level-2 heading; the
     tool refuses when no kept line remains). Write a "held in" line in the
     source where each moved section was, and a `description:` line in the
     new Part that names its section range and the Part-1 file. Together these
     are the in-file segment index. Re-count every `Part k of N` description
     and every "split across N files" line in the family, re-derive each
     `holding §a–§b` range, and point each held-in line at the file that now
     holds its section. Range text the tool cannot re-derive is reported.
  6. Repoint each `x.md §N` citation under every --citing-root to the Part
     that now holds §N. A citation whose sections span parts is left as it is
     and reported, because it must name every part it spans.
  7. Report what it did not edit: handler always-load blocks that name the
     source, whole-file "read x.md" sites, a new Part that no handler, skill
     or agent names, in-file anchor links and bare § mentions the move may
     have made false, and the furniture it does not author (a TOC and a
     Cross-references footer for the new Part).
  8. Measure every resulting text in memory against the Read-tool gates.
     Refuse --apply when one of these measures WARN or OVER: the source
     remainder, the new Part, or any other touched file whose level rises
     (OK to WARN, WARN to OVER). A touched file whose level does not rise is
     reported with both levels as "pre-existing, level unchanged" and never
     refused.
     --allow-warn waives every refusal for the whole run, and the report
     lists every file it waived.
  9. Write every touched file in one atomic multi-file call, re-read each one,
     and restore the in-memory originals if any byte differs. Nothing is ever
     restored through git.

Without --apply the run is a dry run: it prints the plan and writes nothing.

Usage (absolute paths, or paths relative to the working directory):
    python -B tools/split_reference.py --source <path> --sections 16-17 \\
        --part-name Part-3-Topic [--citing-root PATH ...] [--apply] [--json] [--allow-warn]

Exit codes:
    0  ok: a dry run planned cleanly, or --apply wrote and verified every file
    1  refused: mixed line endings, a failed hash or heading check, an
       unsupported family or description shape, a guarded WARN or OVER result
       without --allow-warn, or a post-write mismatch that was rolled back
    2  usage error
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "plugins" / "planwise" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True  # keep the shipped scripts/ tree free of __pycache__

# `_atomic_write_files` is a private name in a backlog module. It is imported as
# is, so this tool is coupled to it: a rename or a signature change there breaks
# this tool. It is the only multi-file atomic writer in the scripts tree.
from backlog_index_disk import _atomic_write_files
from context_calibration import always_load_references
from markdown_parser import extract_headings
from read_limits import (
    READ_BYTE_WARN,
    READ_FILE_BYTE_CAP,
    READ_LINE_CAP,
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
    content_class_for_path,
    estimate_tokens,
)
from reconcile_common import read_text_preserving_newlines

_PART_NAME_RE = re.compile(r"^Part-(?P<n>[0-9]+)-(?P<topic>[A-Z][A-Za-z0-9]*)$")
# A Part file of a split family: `{stem}-Part-{n}-{Topic}.md`. Public, so other
# maintainer tools name a family the same way this one does.
PART_FILE_RE = re.compile(r"^(?P<stem>.+?)-Part-(?P<n>[0-9]+)-.+\.md$")
_TOKEN = r"[0-9]+[a-z]?(?:\.[0-9A-Za-z]+)*"
_TOKEN_RE = re.compile(rf"^{_TOKEN}$")
_RANGE_RE = re.compile(r"^(?P<a>[0-9]+)-(?P<b>[0-9]+)$")
_PART_OF_RE = re.compile(r"\bPart (?P<k>[0-9]+) of (?P<n>[0-9]+)\b")
_PART_NO_TOTAL_RE = re.compile(r"\bPart [0-9]+\b")
_SPLIT_OUT_RE = re.compile(r"\b[Ss]plit out of\b")
_SPLIT_ACROSS_RE = re.compile(r"\b(?P<lead>split across|across the) (?P<n>\w+) files\b")
_POINTER_LEAD = "> [!important] This reference is split across"
_HELD_LEAD_RE = re.compile(r"^> \[!note\] Moved to Parts? [0-9]")
_HELD_LINE_RE = re.compile(
    rf"^> - §(?P<tok>{_TOKEN}) (?P<title>.*) — held in "
    r"\[`(?P<name>[^`]+)`\]\((?P<href>[^)\s]+)\)[ \t]*$"
)
_HOLDING_RE = re.compile(
    rf"holding (?P<range>no numbered section|§{_TOKEN}(?:–§{_TOKEN})?"
    rf"(?:, §{_TOKEN}(?:–§{_TOKEN})?)*)"
)
_TITLE_SUFFIX_RE = re.compile(r"[ \t]+—[ \t]+Part [0-9]+(?::.*)?$")
_BARE_SECTION_RE = re.compile(rf"§(?P<tok>{_TOKEN})")
_ANCHOR_LINK_RE = re.compile(r"\]\(#(?P<slug>[^)\s]+)\)")
_READ_WORD_RE = re.compile(r"\b[Rr]ead\b")
_LEVEL_RANK = {"OK": 0, "WARN": 1, "OVER": 2}
_COUNT_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


class Refused(Exception):
    """A condition the tool refuses on. `main` turns it into exit 1."""


@dataclass
class Section:
    token: str
    level: int
    title: str
    start: int  # 0-based index of the heading line
    end: int  # 0-based index one past the last body line
    body: str = ""
    sha256: str = ""


@dataclass
class Family:
    """The family as it stands after the split, keyed by part number."""

    count: int
    names: dict  # part number -> file name
    tokens: dict  # part number -> outermost numbered sections, in file order
    numbers: dict  # part number -> every numbered section the file holds


@dataclass
class Plan:
    source: Path
    new_part: Path
    part_k: int
    part_count: int
    stem: str = ""
    source_k: int = 1
    topic: str = ""
    family: Family | None = None
    sections: list = field(default_factory=list)
    writes: dict = field(default_factory=dict)  # Path -> resulting text
    originals: dict = field(default_factory=dict)  # Path -> text as read (existing files)
    pending: dict = field(default_factory=dict)  # resolved Path -> resulting text
    texts: dict = field(default_factory=dict)  # resolved Path -> text, read once per run
    unrederived: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    edits: list = field(default_factory=list)
    repoints: list = field(default_factory=list)
    spanning: list = field(default_factory=list)
    reports: dict = field(default_factory=dict)
    measurements: list = field(default_factory=list)


def _read(plan: Plan, path: Path) -> str:
    """Read a file once per run; every later read takes the cached text."""
    key = path.resolve()
    if key not in plan.texts:
        plan.texts[key] = read_text_preserving_newlines(path)
    return plan.texts[key]


def _stage(plan: Plan, path: Path, original, result: str) -> None:
    """Record a resulting text, keyed by path and by resolved path."""
    if original is not None:
        plan.originals[path] = original
    plan.writes[path] = result
    plan.pending[path.resolve()] = result


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lines(text: str) -> list:
    """Split on LF and keep each line's own ending (CRLF stays whole)."""
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def _split_eol(line: str) -> tuple:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _line_ending(path: Path, text: str) -> str:
    """Return the file's one line ending, counted the way the backlog index
    writer detects its own, and refuse a file that holds both."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if text.count("\r") != crlf:
        raise Refused(f"{path}: holds a carriage return that ends no line")
    if crlf and lf:
        raise Refused(f"{path}: mixed line endings ({crlf} CRLF, {lf} LF)")
    return "\r\n" if crlf else "\n"


def _count_word(n: int) -> str:
    return _COUNT_WORDS.get(n, str(n))


def _slug(raw_heading: str) -> str:
    text = re.sub(r"^#{1,6}[ \t]+", "", raw_heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _top(token: str) -> str:
    match = re.match(r"[0-9]+[a-z]?", token)
    return match.group(0) if match else token


def _label(tokens: list) -> str:
    """Collapse section tokens into `§1–§12, §15` form, runs of integers merged."""
    parts, run = [], []
    for token in tokens + [None]:
        if token is not None and token.isdigit() and (not run or int(token) == run[-1] + 1):
            run.append(int(token))
            continue
        if run:
            parts.append(f"§{run[0]}" if len(run) == 1 else f"§{run[0]}–§{run[-1]}")
            run = []
        if token is None:
            break
        if token.isdigit():
            run = [int(token)]
        else:
            parts.append(f"§{token}")
    return ", ".join(parts) if parts else "no numbered section"


def _verb(tokens: list) -> str:
    return "lives" if len(tokens) == 1 else "live"


def _depth(token: str) -> int:
    return token.count(".")


def _outermost(text: str) -> list:
    """Numbered sections not nested under another numbered section of the text.

    `3.2` is nested when `3` is also numbered in the same text, so a part that
    holds `3` with its subsections carries `§3`, and a part that holds only
    `3.2` carries `§3.2`.
    """
    numbers = [h.number for h in extract_headings(text) if h.number]
    present = set(numbers)
    out = []
    for token in numbers:
        parts = token.split(".")
        if not any(".".join(parts[:i]) in present for i in range(1, len(parts))):
            out.append(token)
    return out


def _join_and(items: list) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _unfenced(lines: list) -> set:
    """Indices of the lines outside fenced code."""
    out, fence = set(), None
    for i, line in enumerate(lines):
        mark = line.lstrip()[:3]
        if fence is None and mark in ("```", "~~~"):
            fence = mark
        elif fence is not None and mark == fence:
            fence = None
        elif fence is None:
            out.add(i)
    return out


# --------------------------------------------------------------------------
# Family, frontmatter and sections
# --------------------------------------------------------------------------


def discover_family(source: Path) -> tuple:
    """Return `(stem, source_k, members)`, members mapping part number to path.

    Part 1 is `{stem}.md` when that file exists (it keeps the original
    filename), else `{stem}-Part-1-{Topic}.md`.
    """
    match = PART_FILE_RE.match(source.name)
    stem, source_k = (match["stem"], int(match["n"])) if match else (source.stem, 1)
    members = {}
    base = source.parent / f"{stem}.md"
    if base.is_file():
        members[1] = base
    part_re = re.compile(rf"^{re.escape(stem)}-Part-(?P<n>[0-9]+)-.+\.md$")
    for path in sorted(source.parent.iterdir()):
        found = part_re.match(path.name)
        if not found or not path.is_file():
            continue
        n = int(found["n"])
        if n in members:
            raise Refused(f"two files claim Part {n}: {members[n].name} and {path.name}")
        members[n] = path
    if sorted(members) != list(range(1, len(members) + 1)):
        raise Refused(f"the {stem} family has a gap in its part numbers: {sorted(members)}")
    if source_k not in members or members[source_k].resolve() != source.resolve():
        raise Refused(f"{source.name} is not Part {source_k} of the {stem} family")
    return stem, source_k, members


def _frontmatter_span(lines: list):
    if not lines or _split_eol(lines[0])[0].lstrip("﻿") != "---":
        return None
    for i in range(1, len(lines)):
        if _split_eol(lines[i])[0] == "---":
            return 0, i
    return None


def _description_index(path: Path, lines: list, span):
    if span is None:
        return None
    for i in range(span[0] + 1, span[1]):
        if not lines[i].startswith("description:"):
            continue
        value = _split_eol(lines[i])[0][len("description:"):].strip()
        continued = i + 1 < span[1] and lines[i + 1][:1] in (" ", "\t")
        if value in ("", ">", "|", ">-", "|-", ">+", "|+") or continued:
            raise Refused(f"{path.name}: a multi-line description: is not a shape this tool writes")
        return i
    return None


def _append_to_scalar(content: str, addition: str) -> str:
    key, _, value = content.partition(":")
    value = value.rstrip()
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return f"{key}:{value[:-1]}{addition}{value[-1]}"
    return f"{key}:{value}{addition}"


def _recount_description(path: Path, line: str, member_k: int, old_n: int, new_n: int) -> str:
    """Rewrite one `description:` line for the new part count.

    The one shape this tool writes is `Part k of N`. A first split appends
    `Part 1 of N.` to the source's description. A family member that names a
    part with no total, or carries no part count at all, is refused: the
    count cannot be templated into a sentence the tool did not write.
    """
    content, end = _split_eol(line)
    if _PART_OF_RE.search(content):
        def recount(m):
            return f"Part {m['k']} of {new_n}" if int(m["n"]) == old_n else m.group(0)
        return _PART_OF_RE.sub(recount, content) + end
    if old_n == 1:
        return _append_to_scalar(content, f" Part {member_k} of {new_n}.") + end
    if _SPLIT_OUT_RE.search(content):
        shape = "a free sentence (\"split out of ...\") with no part count"
    elif _PART_NO_TOTAL_RE.search(content):
        shape = "a part number with no total (\"Part 2 — ...\")"
    else:
        shape = "no part count"
    raise Refused(
        f"{path.name}: description: carries {shape}. The tool writes only "
        "\"Part k of N\"; rewrite this description to that shape first."
    )


def parse_sections(spec: str) -> list:
    """`16-17` is an inclusive integer range; `16,18` or `3a` lists tokens."""
    spec = spec.strip()
    ranged = _RANGE_RE.match(spec)
    if ranged:
        a, b = int(ranged["a"]), int(ranged["b"])
        if a > b:
            raise ValueError(f"--sections range runs backwards: {spec}")
        return [str(i) for i in range(a, b + 1)]
    tokens = [token.strip().lstrip("§") for token in spec.split(",")]
    if not tokens or any(not _TOKEN_RE.match(token) for token in tokens):
        raise ValueError(f"--sections must be a-b or a,b,... section numbers: {spec}")
    if len(set(tokens)) != len(tokens):
        raise ValueError(f"--sections names a section twice: {spec}")
    return tokens


def _nested_held(lines: list, lead: int, token: str) -> bool:
    """Whether the held-in block at `lead` marks only sections deeper than `token`.

    A block whose sections the tool cannot read ends the section, as a block
    at the same depth does.
    """
    marked = []
    for line in lines[lead + 1:]:
        if not line.startswith(">"):
            break
        marked += _BARE_SECTION_RE.findall(line)
    return bool(marked) and all(_depth(m) > _depth(token) for m in marked)


def locate_sections(text: str, lines: list, tokens: list) -> list:
    headings = extract_headings(text)
    sections = []
    for token in tokens:
        candidates = [h for h in headings if h.number == token]
        if not candidates:
            raise Refused(f"§{token}: no heading carries this number")
        level = min(h.level for h in candidates)
        at_level = [h for h in candidates if h.level == level]
        if len(at_level) > 1:
            raise Refused(f"§{token}: {len(at_level)} headings at level {level} carry it")
        heading = at_level[0]
        end = len(lines)
        for later in headings:
            if later.line > heading.line and later.level <= heading.level:
                end = later.line - 1
                break
        # A "held in" block an earlier split left in the gap is not part of
        # the section above it, and it stays where it is. A block that marks
        # a deeper subsection of this one (§3.2 inside §3) is part of the
        # section, and it moves with it.
        end = next((j for j in range(heading.line, end)
                    if _HELD_LEAD_RE.match(lines[j]) and not _nested_held(lines, j, token)),
                   end)
        sections.append(Section(token, heading.level, heading.title, heading.line - 1, end))
    if len({s.level for s in sections}) != 1:
        raise Refused("the requested sections sit at different heading levels")
    sections.sort(key=lambda s: s.start)
    for before, after in pairwise(sections):
        if after.start < before.end:
            raise Refused(f"§{after.token} lies inside §{before.token}")
    for section in sections:
        section.body = "".join(lines[section.start:section.end])
        section.sha256 = _sha(section.body)
    return sections


# --------------------------------------------------------------------------
# Building the resulting texts
# --------------------------------------------------------------------------


def _emit(out: list, block: list, eol: str) -> None:
    """Append an inserted block with a blank line on each side.

    `out` holds `(line, original)` pairs; an inserted line has original None.
    """
    if out and not out[-1][0].endswith("\n"):
        out.append((eol, None))
    if out and out[-1][0].strip():
        out.append((eol, None))
    out.extend((line + eol, None) for line in block)
    out.append((eol, None))


def _recount_lines(lines: list, skip: set, old_n: int, new_n: int) -> dict:
    """Map line index to its rewritten text for each "split across N files" line."""
    changed = {}
    if old_n < 2:
        return changed
    old_words = {str(old_n), _count_word(old_n)}

    def recount(m):
        if m["n"] not in old_words:
            return m.group(0)
        return f"{m['lead']} {_count_word(new_n)} files"

    for i, line in enumerate(lines):
        if i in skip:
            continue
        new_line = _SPLIT_ACROSS_RE.sub(recount, line)
        if new_line != line:
            changed[i] = new_line
    return changed


def _rebuild_check(path: Path, out: list, expected: str) -> None:
    """Every line the tool did not insert or rewrite must equal `expected`."""
    rebuilt = "".join(original for _line, original in out if original is not None)
    if _sha(rebuilt) != _sha(expected):
        raise Refused(f"{path.name}: the untouched lines do not hash to the expected text")


def _pointer_blocks(lines: list, start: int) -> list:
    """`(first, end)` line spans of each pointer block outside fenced code."""
    open_lines = _unfenced(lines)
    blocks, i = [], start
    while i < len(lines):
        if i in open_lines and lines[i].startswith(_POINTER_LEAD):
            j = i + 1
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            blocks.append((i, j))
            i = j
        else:
            i += 1
    return blocks


def _pointer_block(family: Family, k: int) -> list:
    """The pointer block for Part k, derived from the post-split heading sets."""
    words = _count_word(family.count)
    own = family.tokens[k]
    others = [j for j in sorted(family.names) if j != k]
    where = _join_and([f"{_label(family.tokens[j])} {_verb(family.tokens[j])} in Part {j}"
                       for j in others])
    links = " ".join(f"Part {j}, [{family.names[j]}]({family.names[j]}), carries "
                     f"{_label(family.tokens[j])}." for j in others)
    return [
        f"{_POINTER_LEAD} {words} files — {where}",
        f"> This part carries {_label(own)}. {links}",
        ">",
        (f"> Section numbers are continuous across the {words} files: a section keeps its "
         f"`§N` wherever it lands. A citation naming {_label(own)} resolves to this file."),
    ]


def _replace_block(out: list, pointer: list, lines: list, block: tuple, eol: str) -> None:
    """Put the new block where the old one was. Each old line stays in `out`
    as an original with no text, so the untouched-lines check still sees it."""
    out.extend((line + eol, None) for line in pointer)
    out.extend(("", lines[j]) for j in range(*block))


def _log_edits(plan: Plan, path: Path, out: list, lines: list, block, pointer: list) -> None:
    for new_line, original in out:
        if original is not None and new_line and new_line != original:
            plan.edits.append({"file": str(path), "before": original.rstrip("\r\n"),
                               "after": new_line.rstrip("\r\n")})
    if block is None:
        if path == plan.source:
            plan.edits.append({"file": str(path), "inserted": "pointer block",
                               "text": pointer[0]})
        return
    plan.edits.append({"file": str(path), "replaced": "pointer block",
                       "before": [line.rstrip("\r\n") for line in lines[block[0]:block[1]]],
                       "text": pointer[0]})


def _unrederived(plan: Plan, path: Path, index: int, kind: str, text: str) -> None:
    plan.unrederived.append({"file": path.name, "source_line": index + 1, "kind": kind,
                             "text": text.strip()[:160]})


def _holder(family: Family, token: str) -> tuple:
    """`(part number, None)` for the one file that holds §token, else `(None, why)`."""
    found = [k for k, numbers in sorted(family.numbers.items()) if token in numbers]
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, f"no family file holds §{token}"
    return None, f"§{token} is numbered in more than one family file"


def _rederive(plan: Plan, path: Path, k: int, lines: list, skip: set) -> tuple:
    """Plan the in-place re-derivations in one family member.

    Returns `(block, changed)`: the span of the member's first pointer block
    (None when it has none), and a map of line index to rewritten line for
    each held-in line and held-in lead that now names a different part.
    Anything the tool cannot re-derive is kept for the may-now-be-false report.
    """
    family = plan.family
    blocks = [b for b in _pointer_blocks(lines, 0) if b[0] not in skip]
    for first, _end in blocks[1:]:
        _unrederived(plan, path, first, "a second pointer block, left as it is", lines[first])
    open_lines = _unfenced(lines)
    changed = {}
    i = 0
    while i < len(lines):
        if i in skip or i not in open_lines or not _HELD_LEAD_RE.match(lines[i]):
            i += 1
            continue
        j, holders, complete = i + 1, [], True
        while j < len(lines) and lines[j].startswith(">"):
            content, end = _split_eol(lines[j])
            match = _HELD_LINE_RE.match(content)
            if content.strip() == ">":
                j += 1
                continue
            if match is None:
                holder, why = None, "not the held-in shape this tool writes"
            else:
                holder, why = _holder(family, match["tok"])
                if holder == k:
                    holder, why = None, f"this file holds §{match['tok']} itself"
            if holder is None:
                complete = False
                _unrederived(plan, path, j, f"held-in line not re-derived: {why}", content)
            else:
                holders.append(holder)
                name, href = family.names[holder], match["href"]
                if name != match["name"]:
                    href = href[:-len(match["name"])] + name \
                        if href.endswith(match["name"]) else name
                    changed[j] = (f"> - §{match['tok']} {match['title']} — held in "
                                  f"[`{name}`]({href})" + end)
            j += 1
        if complete and holders:
            parts = [str(p) for p in sorted(set(holders))]
            lead = (f"> [!note] Moved to Part {parts[0]}" if len(parts) == 1 else
                    f"> [!note] Moved to Parts {_join_and(parts)}")
            content, end = _split_eol(lines[i])
            if lead != content:
                changed[i] = lead + end
        i = j
    return (blocks[0] if blocks else None), changed


def _rederive_description(plan: Plan, path: Path, k: int, line: str, index: int) -> str:
    """Re-derive the `holding §a–§b` range of one `description:` line."""
    content, end = _split_eol(line)
    match = _HOLDING_RE.search(content)
    if match:
        content = (content[:match.start("range")] + _label(plan.family.tokens[k])
                   + content[match.end("range"):])
    elif "§" in content:
        _unrederived(plan, path, index,
                     "description: names sections in a shape the tool cannot re-derive",
                     content)
    return content + end


def _report_recounted_prose(plan: Plan, path: Path, lines: list, recounted: dict,
                            block) -> None:
    for i in sorted(recounted):
        if block is None or not block[0] <= i < block[1]:
            _unrederived(plan, path, i, "a \"split across\" line outside the pointer block: "
                         "count templated, range text not re-derived", lines[i])


def build_source(plan: Plan, text: str, lines: list, eol: str, old_n: int, members: dict) -> str:
    sections = plan.sections
    moved = set()
    for section in sections:
        moved.update(range(section.start, section.end))
    remainder_by_lines = "".join(line for i, line in enumerate(lines) if i not in moved)
    remainder_by_offsets, cursor = "", 0
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for section in sections:
        remainder_by_offsets += text[cursor:offsets[section.start]]
        cursor = offsets[section.end]
    remainder_by_offsets += text[cursor:]
    if _sha(remainder_by_lines) != _sha(remainder_by_offsets):
        raise Refused("the remainder differs between its two derivations")
    plan.checks["remainder_sha256"] = _sha(remainder_by_lines)

    span = _frontmatter_span(lines)
    desc_i = _description_index(plan.source, lines, span)
    floor = span[1] + 1 if span else 0
    recounted = _recount_lines(lines, moved | set(range(floor)), old_n, plan.part_count)

    inside = [first for first, _end in _pointer_blocks(lines, floor) if first in moved]
    if inside:
        raise Refused(f"{plan.source.name}: the pointer block at line {inside[0] + 1} lies "
                      "inside a section this split moves; move the block out of it first")
    block, held_changes = _rederive(plan, plan.source, plan.source_k, lines,
                                    moved | set(range(floor)))
    _report_recounted_prose(plan, plan.source, lines, recounted, block)

    emit_at = None
    if block is None:
        headings = extract_headings(text)
        pointer_at = next((h.line - 1 for h in headings
                           if h.level >= 2 and h.line - 1 >= floor), None)
        if pointer_at is None:
            first_h1 = next((h.line for h in headings if h.level == 1), None)
            pointer_at = first_h1 if first_h1 is not None else floor
        # The first kept line at or after the slot; when the split moves the
        # slot and everything after it, the first kept section heading.
        emit_at = next((j for j in range(pointer_at, len(lines)) if j not in moved), None)
        if emit_at is None:
            emit_at = next((h.line - 1 for h in headings
                            if h.line - 1 >= floor and h.line - 1 not in moved), None)
        if emit_at is None:
            raise Refused(f"{plan.source.name}: no kept position for the pointer block: the "
                          "split moves every section, so the remainder has nowhere to say "
                          "where they went")

    new_name = plan.new_part.name
    pointer = _pointer_block(plan.family, plan.source_k)

    runs = []
    for section in sections:
        if runs and runs[-1][1] == section.start:
            runs[-1] = (runs[-1][0], section.end, runs[-1][2] + [section])
        else:
            runs.append((section.start, section.end, [section]))
    run_at = {start: (end, members_) for start, end, members_ in runs}

    out = []
    i = 0
    while i <= len(lines):
        if i == emit_at:
            _emit(out, pointer, eol)
        if block is not None and i == block[0]:
            _replace_block(out, pointer, lines, block, eol)
            i = block[1]
            continue
        if i in run_at:
            end, run_sections = run_at[i]
            held = [f"> [!note] Moved to Part {plan.part_k}"]
            held += [f"> - §{s.token} {s.title} — held in [`{new_name}`]({new_name})"
                     for s in run_sections]
            _emit(out, held, eol)
            i = end
            continue
        if i == len(lines):
            break
        line = lines[i]
        if i == desc_i:
            recounted_desc = _recount_description(plan.source, line, plan.source_k,
                                                  old_n, plan.part_count)
            out.append((_rederive_description(plan, plan.source, plan.source_k,
                                              recounted_desc, desc_i), line))
        elif i in held_changes:
            out.append((held_changes[i], line))
        elif i in recounted:
            out.append((recounted[i], line))
        else:
            out.append((line, line))
        i += 1

    _rebuild_check(plan.source, out, remainder_by_lines)
    _log_edits(plan, plan.source, out, lines, block, pointer)
    plan.edits.append({"file": str(plan.source), "inserted": "held-in lines",
                       "count": len(sections)})
    if desc_i is None:
        plan.reports.setdefault("notes", []).append(
            f"{plan.source.name} has no description: line, so its part count is not stated")
    return "".join(line for line, _original in out)


def build_new_part(plan: Plan, lines: list, eol: str, stem: str,
                   part1: Path, part1_text: str) -> tuple:
    sections = plan.sections
    new_name = plan.new_part.name
    span = _frontmatter_span(lines)
    desc_i = _description_index(plan.source, lines, span)
    description = (f"description: Part {plan.part_k} of {plan.part_count} of the {stem} "
                   f"reference, holding {_label(plan.family.tokens[plan.part_k])}. Part 1 of "
                   f"{plan.part_count} is {part1.name}.")

    head = []
    copied_keys = []
    if span:
        for i in range(span[0], span[1] + 1):
            if i == desc_i:
                head.append(description + eol)
                continue
            head.append(lines[i])
            if span[0] < i < span[1] and re.match(r"^[A-Za-z_][\w-]*:", lines[i]):
                copied_keys.append(lines[i].split(":", 1)[0])
            if i == span[0] and desc_i is None:
                head.append(description + eol)
    else:
        head += ["---" + eol, description + eol, "---" + eol]

    # The base title is Part 1's document title, with any "— Part k: Topic"
    # suffix taken off, so a split of a later Part does not stack suffixes.
    h1 = next((h for h in extract_headings(part1_text) if h.level == 1 and not h.number), None)
    base_title = _TITLE_SUFFIX_RE.sub("", re.sub(r"^#[ \t]+", "", h1.raw)) if h1 else stem
    topic = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", plan.topic)
    title_line = f"# {base_title} — Part {plan.part_k}: {topic}"

    pointer = _pointer_block(plan.family, plan.part_k)
    head +=[eol, title_line + eol, eol] + [line + eol for line in pointer] + [eol]

    content = "".join(head)
    placed = []
    for section in sections:
        placed.append(len(content))
        content += section.body
        if not section.body.endswith("\n"):
            content += eol
    for section, offset in zip(sections, placed):
        held = content[offset:offset + len(section.body)]
        if _sha(held) != section.sha256 or content.count(section.body) != 1:
            raise Refused(f"§{section.token}: the moved body does not appear once, "
                          f"unchanged, in {new_name}")
    plan.edits.append({"file": str(plan.new_part), "inserted": "pointer block",
                       "text": pointer[0]})
    plan.edits.append({"file": str(plan.new_part), "inserted": "description",
                       "text": description})
    if copied_keys:
        plan.reports.setdefault("notes", []).append(
            f"frontmatter keys copied from the source into {new_name}: "
            f"{', '.join(k for k in copied_keys if k != 'description')} — review each for "
            "the new Part")
    plan.reports["furniture_not_authored"] = [
        f"{new_name}: a Table of Contents and a Cross-references footer",
        (f"{plan.source.name}: its Table of Contents and any intro sentence that counts or "
         "ranges sections"),
    ]
    return content, ("#", title_line)


def recount_member(plan: Plan, path: Path, member_k: int, old_n: int) -> None:
    """Re-derive one family member the split does not move text out of: its
    part counts, its pointer block, its held-in lines and its `holding` range."""
    text = _read(plan, path)
    eol = _line_ending(path, text)
    lines = _lines(text)
    span = _frontmatter_span(lines)
    desc_i = _description_index(path, lines, span)
    floor = set(range(span[1] + 1 if span else 0))
    recounted = _recount_lines(lines, floor, old_n, plan.part_count)
    block, held_changes = _rederive(plan, path, member_k, lines, floor)
    _report_recounted_prose(plan, path, lines, recounted, block)
    pointer = _pointer_block(plan.family, member_k)
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if block is not None and i == block[0]:
            _replace_block(out, pointer, lines, block, eol)
            i = block[1]
            continue
        if i == desc_i:
            recounted_desc = _recount_description(path, line, member_k, old_n, plan.part_count)
            out.append((_rederive_description(plan, path, member_k, recounted_desc, desc_i),
                        line))
        else:
            out.append((held_changes.get(i, recounted.get(i, line)), line))
        i += 1
    _rebuild_check(path, out, text)
    if desc_i is None:
        plan.reports.setdefault("notes", []).append(
            f"{path.name} has no description: line, so its part count is not stated")
    if block is None:
        plan.reports.setdefault("notes", []).append(
            f"{path.name} has no pointer block, so the tool wrote none there")
    result = "".join(line for line, _original in out)
    _log_edits(plan, path, out, lines, block, pointer)
    if result != text:
        _stage(plan, path, text, result)


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------


def _citation_re(name: str):
    n = re.escape(name)
    return re.compile(
        rf"(?<![\w.-]){n}"
        rf"(?P<tail>(?:#[\w-]*)?\)|`?(?:\]\((?P<href>[^)\s]*)\))?)"
        rf"(?P<gap>[ \t]*)§(?P<a>{_TOKEN})"
        rf"(?:(?:[ \t]*–[ \t]*|-)§?(?P<b>{_TOKEN}))?"
        rf"(?P<more>(?:[ \t]*(?:,|/|and|or)[ \t]*§{_TOKEN})*)"
    )


def _cited_tokens(m) -> list:
    a, b = m["a"], m["b"]
    if b and a.isdigit() and b.isdigit() and int(a) <= int(b):
        tokens = [str(i) for i in range(int(a), int(b) + 1)]
    else:
        tokens = [a] + ([b] if b else [])
    return tokens + _BARE_SECTION_RE.findall(m["more"] or "")


def repoint_citations(plan: Plan, citing_files: list, skip: set) -> None:
    name, new_name = plan.source.name, plan.new_part.name
    pattern = _citation_re(name)
    in_href = re.compile(rf"(?<![\w.-]){re.escape(name)}")
    moved = [s.token for s in plan.sections]

    def is_moved(token):
        return any(token == s or token.startswith(s + ".") for s in moved)

    for path in citing_files:
        if path.resolve() in skip:
            continue
        text = _read(plan, path)
        if name not in text:
            continue
        found = []

        def swap(m, path=path, text=text, found=found):
            tokens = _cited_tokens(m)
            flags = [is_moved(t) for t in tokens]
            line_no = text.count("\n", 0, m.start()) + 1
            if not any(flags):
                return m.group(0)
            if not all(flags):
                plan.spanning.append({"file": str(path), "line": line_no,
                                      "citation": m.group(0)})
                return m.group(0)
            href = m["href"]
            tail = m["tail"]
            if href is not None:
                tail = tail.replace(f"]({href})", f"]({in_href.sub(new_name, href)})")
            after = new_name + tail + m.group(0)[len(name) + len(m["tail"]):]
            found.append({"file": str(path), "line": line_no, "before": m.group(0),
                          "after": after})
            return after

        result = pattern.sub(swap, text)
        if result != text:
            _line_ending(path, text)
            plan.repoints.extend(found)
            _stage(plan, path, text, result)


def _citing_files(roots: list) -> list:
    seen, files = set(), []
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*.md"))
        for path in candidates:
            key = path.resolve()
            if path.suffix == ".md" and key not in seen:
                seen.add(key)
                files.append(path)
    return files


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def _pending_text(plan: Plan, path: Path) -> str:
    """The text a file will hold after the split: its pending write, else its
    text as read. Both lookups are keyed by resolved path."""
    content = plan.pending.get(path.resolve())
    return content if content is not None else _read(plan, path)


def report_readers(plan: Plan, citing_files: list) -> None:
    name, new_name = plan.source.name, plan.new_part.name
    plugin_root = plan.source.parent.parent
    reader_dirs = [plugin_root / d for d in ("handlers", "skills", "agents")]
    always_load, whole_file = [], []
    handlers = plugin_root / "handlers"
    if handlers.is_dir():
        for path in sorted(handlers.glob("*.md")):
            if name in always_load_references(_pending_text(plan, path)):
                always_load.append(str(path))
    cite = _citation_re(name)
    scanned, reader_text = set(), []
    readers = [p for d in reader_dirs if d.is_dir() for p in sorted(d.rglob("*.md"))]
    reader_set = set(readers)
    for path in readers + citing_files:
        key = path.resolve()
        if key in scanned:
            continue
        scanned.add(key)
        text = _pending_text(plan, path)
        if path in reader_set:
            reader_text.append(text)
        for line_no, line in enumerate(text.split("\n"), start=1):
            if name in line and _READ_WORD_RE.search(line) and not cite.search(line):
                whole_file.append({"file": str(path), "line": line_no,
                                   "text": line.strip()[:160]})
    plan.reports["always_load_blocks_naming_source"] = always_load
    plan.reports["whole_file_read_sites"] = whole_file
    if any(d.is_dir() for d in reader_dirs):
        cited = new_name in "\n".join(reader_text)
        plan.reports["new_part_uncited_by_handlers_skills_agents"] = not cited
    else:
        plan.reports["new_part_uncited_by_handlers_skills_agents"] = (
            f"not checked: no handlers/, skills/ or agents/ beside {plan.source.parent}")
    stem = plan.stem
    bare = re.compile(rf"(?<![\w.-]){re.escape(stem)}(?![\w.-])`?[ \t]*§")
    plan.reports["bare_stem_section_citations"] = [
        {"file": str(p), "line": n}
        for p in citing_files
        for n, line in enumerate(_pending_text(plan, p).split("\n"), start=1)
        if bare.search(line)
    ]


def report_stale_in_files(plan: Plan, lines: list, members: dict) -> None:
    """Seeds for a stale-reference sweep: what the move may have made false."""
    moved = set()
    for section in plan.sections:
        moved.update(range(section.start, section.end))
    moved_slugs, kept_slugs = set(), set()
    kept_tops, moved_tops = set(), {_top(s.token) for s in plan.sections}
    for heading in extract_headings("".join(lines)):
        (moved_slugs if heading.line - 1 in moved else kept_slugs).add(_slug(heading.raw))
        if heading.line - 1 not in moved and heading.number:
            kept_tops.add(_top(heading.number))
    # Pointer-block and held-in lines are re-derived, not left as they were.
    derived = set()
    for first, end in _pointer_blocks(lines, 0):
        derived.update(range(first, end))
    for i, line in enumerate(lines):
        if _HELD_LEAD_RE.match(line):
            j = i + 1
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            derived.update(range(i, j))
    findings = []
    for i, line in enumerate(lines):
        if i in derived:
            continue
        here = plan.new_part.name if i in moved else plan.source.name
        other_slugs = kept_slugs if i in moved else moved_slugs
        other_tops = kept_tops - moved_tops if i in moved else moved_tops
        for m in _ANCHOR_LINK_RE.finditer(line):
            if m["slug"] in other_slugs:
                findings.append({"file": here, "source_line": i + 1,
                                 "kind": "in-file anchor now crosses files",
                                 "text": m.group(0)})
        for m in _BARE_SECTION_RE.finditer(line):
            if ".md" in line[max(0, m.start() - 80):m.start()]:
                continue
            if _top(m["tok"]) in other_tops:
                findings.append({"file": here, "source_line": i + 1,
                                 "kind": "bare § now names a section in the other file",
                                 "text": m.group(0)})
    # Range text in the family that the re-derivation could not rewrite: a
    # held-in line of another shape, a description range of another shape, a
    # "split across" line outside the pointer block, a second pointer block.
    findings.extend(plan.unrederived)
    plan.reports["may_now_be_false"] = findings


# --------------------------------------------------------------------------
# Measurement and writing
# --------------------------------------------------------------------------


def measure_text(path: Path, content: str) -> dict:
    """Measure a result that exists only in memory, with the same ratio and
    gates `measure_files.measure_file` applies to a file on disk."""
    data = content.encode("utf-8")
    num_bytes = len(data)
    lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    tokens = estimate_tokens(num_bytes, None, content_class_for_path(str(path)))
    if tokens >= READ_PAGE_CAP_TOKENS or num_bytes >= READ_FILE_BYTE_CAP or lines >= READ_LINE_CAP:
        level = "OVER"
    elif tokens >= READ_TOKEN_WARN or num_bytes >= READ_BYTE_WARN:
        level = "WARN"
    else:
        level = "OK"
    return {"path": str(path), "bytes": num_bytes, "lines": lines, "tokens": tokens,
            "level": level}


def _guarded(plan: Plan, path: Path, measured: dict) -> bool:
    """Whether the WARN guard applies to one resulting file.

    The source remainder and the new Part are always guarded. Any other
    touched file (a family member or a citer) is guarded only when its
    level rises (OK -> WARN, WARN -> OVER): a file that was already WARN and
    stays WARN is the split's reader, not its result, whatever a repoint or
    a recount does to its byte count.
    """
    if path == plan.source or path == plan.new_part:
        return True
    before = measured.get("before_level")
    return before is None or _LEVEL_RANK[measured["level"]] > _LEVEL_RANK[before]


def write_and_verify(plan: Plan) -> list:
    """Write every file in one call, re-read each, and roll back on a mismatch.

    Returns the paths whose re-read bytes differed (empty on success).
    """
    _atomic_write_files(dict(plan.writes), [])
    differing = [path for path, content in plan.writes.items()
                 if path.read_bytes() != content.encode("utf-8")]
    if differing:
        restore = dict(plan.originals)
        created = [path for path in plan.writes if path not in plan.originals]
        _atomic_write_files(restore, created)
    return differing


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def _post_split_family(plan: Plan, members: dict, lines: list) -> Family:
    """Each part's heading sets as they stand after the split: the source minus
    the moved sections, the new Part holding them, every other part as read."""
    moved = set()
    for section in plan.sections:
        moved.update(range(section.start, section.end))
    texts = {k: _read(plan, path) for k, path in members.items() if path != plan.source}
    texts[plan.source_k] = "".join(line for i, line in enumerate(lines) if i not in moved)
    texts[plan.part_k] = "".join(s.body if s.body.endswith("\n") else s.body + "\n"
                                 for s in plan.sections)
    names = {k: path.name for k, path in members.items()}
    names[plan.part_k] = plan.new_part.name
    return Family(
        count=plan.part_count,
        names=names,
        tokens={k: _outermost(t) for k, t in texts.items()},
        numbers={k: {h.number for h in extract_headings(t) if h.number}
                 for k, t in texts.items()},
    )


def plan_split(source: Path, tokens: list, part_name: str, citing_roots: list) -> Plan:
    named = _PART_NAME_RE.match(part_name)
    stem, source_k, members = discover_family(source)
    old_n = len(members)
    new_k = int(named["n"])
    if new_k != old_n + 1:
        raise Refused(f"--part-name {part_name}: the {stem} family has {old_n} part(s), so the "
                      f"new part must be Part {old_n + 1} (append, never insert)")
    new_part = source.parent / f"{stem}-{part_name}.md"
    if new_part.exists():
        raise Refused(f"{new_part.name} already exists")
    plan = Plan(source=source, new_part=new_part, part_k=new_k, part_count=new_k,
                stem=stem, source_k=source_k, topic=named["topic"])

    text = _read(plan, source)
    eol = _line_ending(source, text)
    lines = _lines(text)
    plan.sections = locate_sections(text, lines, tokens)
    plan.family = _post_split_family(plan, members, lines)

    source_result = build_source(plan, text, lines, eol, old_n, members)
    part1 = members[1]
    part1_text = source_result if part1 == source else _read(plan, part1)
    new_result, furniture = build_new_part(plan, lines, eol, stem, part1, part1_text)
    _stage(plan, source, text, source_result)
    _stage(plan, new_part, None, new_result)

    before = Counter((h.level, h.raw) for h in extract_headings(text))
    after_source = Counter((h.level, h.raw) for h in extract_headings(source_result))
    after_new = Counter((h.level, h.raw) for h in extract_headings(new_result))
    after_new[(1, furniture[1])] -= 1
    after_new += Counter()
    if before != after_source + after_new:
        missing = before - (after_source + after_new)
        extra = (after_source + after_new) - before
        raise Refused(f"heading sets differ after the split: missing {sorted(missing)}, "
                      f"extra {sorted(extra)}")
    plan.checks["heading_set_frozen"] = {"before": sum(before.values()),
                                         "source_after": sum(after_source.values()),
                                         "new_part_after": sum(after_new.values())}
    plan.checks["moved_body_sha256"] = {s.token: s.sha256 for s in plan.sections}

    for k, path in sorted(members.items()):
        if path != source:
            recount_member(plan, path, k, old_n)

    family = {p.resolve() for p in members.values()} | {new_part.resolve()}
    citing = _citing_files(citing_roots)
    family_hits = [str(p) for p in citing
                   if p.resolve() in family and source.name in _pending_text(plan, p)]
    if family_hits:
        plan.reports.setdefault("notes", []).append(
            "citations of the source inside the family itself are not repointed: "
            + ", ".join(family_hits))
    repoint_citations(plan, citing, family)
    report_readers(plan, citing)
    report_stale_in_files(plan, lines, members)

    for path, content in plan.writes.items():
        measured = measure_text(path, content)
        measured["before_bytes"] = len(plan.originals[path].encode("utf-8")) \
            if path in plan.originals else None
        measured["before_level"] = measure_text(path, plan.originals[path])["level"] \
            if path in plan.originals else None
        measured["guarded"] = _guarded(plan, path, measured)
        if not measured["guarded"] and measured["level"] != "OK":
            measured["note"] = (f"pre-existing, level unchanged "
                                f"({measured['before_level']} -> {measured['level']})")
        plan.measurements.append(measured)
    return plan


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _plan_dict(plan: Plan) -> dict:
    return {
        "source": str(plan.source),
        "new_part": str(plan.new_part),
        "part": f"{plan.part_k} of {plan.part_count}",
        "sections": [{"section": s.token, "title": s.title, "lines": f"{s.start + 1}-{s.end}",
                      "sha256": s.sha256} for s in plan.sections],
        "checks": plan.checks,
        "edits": plan.edits,
        "repoints": plan.repoints,
        "spanning_citations_left_for_dual_citation": plan.spanning,
        "reports": plan.reports,
        "measurements": plan.measurements,
        "files_to_write": [str(p) for p in plan.writes],
    }


def _print_text(result: dict) -> None:
    print(f"status: {result['status']}")
    if result.get("reason"):
        print(f"reason: {result['reason']}")
    plan = result.get("plan")
    if not plan:
        return
    print(f"source: {plan['source']}")
    print(f"new part: {plan['new_part']} (Part {plan['part']})")
    for s in plan["sections"]:
        print(f"  moves §{s['section']} {s['title']} (source lines {s['lines']}) "
              f"sha256 {s['sha256'][:16]}")
    print(f"checks: {json.dumps(plan['checks'])}")
    print(f"edits ({len(plan['edits'])}):")
    for edit in plan["edits"]:
        print(f"  {json.dumps(edit, ensure_ascii=False)}")
    print(f"repoints ({len(plan['repoints'])}):")
    for r in plan["repoints"]:
        print(f"  {r['file']}:{r['line']}  {r['before']}  ->  {r['after']}")
    print(f"spanning citations left for a dual citation "
          f"({len(plan['spanning_citations_left_for_dual_citation'])}):")
    for r in plan["spanning_citations_left_for_dual_citation"]:
        print(f"  {r['file']}:{r['line']}  {r['citation']}")
    print("reports:")
    for key, value in plan["reports"].items():
        print(f"  {key}: {json.dumps(value, ensure_ascii=False)}")
    print("measurements (in-memory results):")
    for m in plan["measurements"]:
        note = f"  ({m['note']})" if m.get("note") else ""
        print(f"  {m['level']:<4} {m['bytes']:>8} B {m['tokens']:>6} tok {m['lines']:>5} lines"
              f"  {m['path']}{note}")
    if result.get("waived"):
        print(f"--allow-warn waived: {', '.join(result['waived'])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="split_reference.py",
        description="Move whole sections of a reference into a new "
                    "{stem}-Part-N-{Topic}.md sibling. Dry run unless --apply. "
                    "Exit 0 ok, 1 refused, 2 usage.")
    parser.add_argument("--source", required=True, help="the reference file to split")
    parser.add_argument("--sections", required=True,
                        help="sections to move: an inclusive range a-b, or a,b,... numbers")
    parser.add_argument("--part-name", required=True,
                        help="the new part's name, Part-N-Topic (N = the family's next part)")
    parser.add_argument("--citing-root", action="append", default=[], metavar="PATH",
                        help="a tree whose x.md §N citations are repointed (repeatable)")
    parser.add_argument("--apply", action="store_true",
                        help="write the files; without it the run writes nothing")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--allow-warn", action="store_true",
                        help="apply even when the source remainder or the new Part "
                             "measures WARN or OVER, or another touched file's level "
                             "rises to WARN or OVER (whole run; the report lists every "
                             "waived file)")
    return parser


def main(argv: list | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # § and — on a cp1252 console
    parser = build_parser()
    args = parser.parse_args(argv)
    source = Path(args.source)
    if not source.is_file():
        parser.error(f"--source is not a file: {source}")
    if not _PART_NAME_RE.match(args.part_name):
        parser.error(f"--part-name must look like Part-3-Topic: {args.part_name}")
    try:
        tokens = parse_sections(args.sections)
    except ValueError as exc:
        parser.error(str(exc))
    roots = [Path(r) for r in args.citing_root]
    for root in roots:
        if not root.exists():
            parser.error(f"--citing-root does not exist: {root}")

    result = {"status": "planned"}
    code = 0
    try:
        plan = plan_split(source, tokens, args.part_name, roots)
        result["plan"] = _plan_dict(plan)
        flagged = [m["path"] for m in plan.measurements
                   if m["guarded"] and m["level"] != "OK"]
        result["pre_existing_level_unchanged"] =[m["path"] for m in plan.measurements
                                            if m.get("note")]
        if args.apply:
            if flagged and not args.allow_warn:
                raise Refused(f"resulting file(s) measure WARN or OVER: {', '.join(flagged)}; "
                              "pass --allow-warn to apply anyway")
            result["waived"] = flagged
            differing = write_and_verify(plan)
            if differing:
                raise Refused("re-read bytes differ from the computed content in "
                              f"{', '.join(map(str, differing))}; originals restored")
            result["status"] = "applied"
        elif flagged:
            result["would_refuse_apply_without_allow_warn"] = flagged
    except Refused as exc:
        result["status"] = "refused"
        result["reason"] = str(exc)
        code = 1
    except OSError as exc:
        result["status"] = "refused"
        result["reason"] = f"write failed and was rolled back: {exc}"
        code = 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_text(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
