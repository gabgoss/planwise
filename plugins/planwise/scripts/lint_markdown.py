#!/usr/bin/env python3
"""Lint markdown files against the callout and markdown conventions.

Usage:
    python -B lint_markdown.py [--strict] [--catalog PATH] <file.md|dir> [<file.md|dir> ...]

Input: one or more markdown files, or directories (walked for `*.md`).

Rules, each reported under its own name as `path:line: rule: message`:

- `callout-type`: a `> [!type]` callout whose type is not one of the catalogued
  types. The closed type list is read at run time from the type headings
  (`### `> [!type]``) inside the `## 1. Callout Catalog` section of
  `callout-conventions.md` section 1 (a PATTERN heading is not a type). The
  list awaits adjudication against the types the project-side rules use, so
  this rule is report-only: it prints its hits and does not change the exit
  code unless `--strict` is passed.
- `pitfall-shape`: a `[!pitfall]` callout must hold both `Problem:` and
  `Solution:` (callout-conventions.md, the pitfall entry).
- `callout-nesting`: callout nesting is at most 2 levels
  (callout-conventions.md section 5).
- `heading-h1`: exactly one H1 per document; `heading-skip`: no skipped
  heading level (markdown-conventions.md section 1; plain-presentation.md
  Headings).
- `frontmatter-description`: a rule file (a path with a `rules` folder) or a
  skill file (`SKILL.md`) needs a non-empty `description` key
  (markdown-conventions.md section 3).
- `link-extension`: a local link whose target has no file extension at all.
  A target ending `.md` passes, and so does a target with another extension
  such as `.py`. A scheme link, an `#anchor` and a `{placeholder}` are skipped
  (markdown-conventions.md section 6).
- `table-empty-cell`: a table cell with no text, separator row skipped
  (plain-presentation.md Tables).

Exit codes: 0 clean (rule `callout-type` hits alone are printed and exit 0
without `--strict`), 1 a finding, 2 a usage error or an unreadable input or
catalog (an `Error:` line goes to stderr).

What it cannot see: a callout or link written inside a fenced code block is
skipped by design. A callout that is not at the start of a line (after the
`>` markers) is not read. Heading numbers and anchors are not resolved, so a
link whose `#anchor` points nowhere passes. The type list is only as
current as the catalog file it reads.

The last line of output is `rule counts: ...` with one count per rule, so an
empty result still shows how many files were read: `N files read`.
"""
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from markdown_parser import extract_headings, split_row_cells_code_aware

RULES = (
    "callout-type",
    "pitfall-shape",
    "callout-nesting",
    "heading-h1",
    "heading-skip",
    "frontmatter-description",
    "link-extension",
    "table-empty-cell",
)
DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "references" / "callout-conventions.md"
MAX_NESTING = 2

QUOTE_PREFIX_RE = re.compile(r"^[ \t]{0,3}(?:>[ \t]?)+")
OPENER_RE = re.compile(r"^[ \t]{0,3}((?:>[ \t]?)+)\[!([A-Za-z]+)\]")
TYPE_HEADING_RE = re.compile(r"^###[ \t]+`>[ \t]*\[!([A-Za-z]+)\]`([^\n]*)$")
SECTION_RE = re.compile(r"^##[ \t]+([^\n]*)$")
SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:[ \t]+\"[^\"]*\")?\)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
PROBLEM_RE = re.compile(r"Problem(?:\*\*)?:")
SOLUTION_RE = re.compile(r"Solution(?:\*\*)?:")


def read_type_list(catalog_text):
    """Return the distinct callout types from the catalog's section 1, in order.

    A type heading is `### `> [!type]`` inside the `## 1.` section. A heading
    whose tail holds PATTERN is a usage pattern, not a type.
    """
    types = []
    in_section = False
    for line in catalog_text.replace("\r\n", "\n").split("\n"):
        section = SECTION_RE.match(line)
        if section:
            in_section = section.group(1).lstrip().startswith("1.")
            continue
        if not in_section:
            continue
        heading = TYPE_HEADING_RE.match(line)
        if heading and "PATTERN" not in heading.group(2) and heading.group(1).lower() not in types:
            types.append(heading.group(1).lower())
    return types


def prepare(content):
    """Return the content with the frontmatter blanked, so line numbers stay true."""
    text = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    split = split_frontmatter_block(text)
    if split is None:
        return text, None
    frontmatter, body = split
    consumed = text[: len(text) - len(body)]
    return "\n" * consumed.count("\n") + body, frontmatter


def scan_lines(text):
    """Return (line_number, inner_text, depth) for every line outside a fence."""
    out = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        prefix = QUOTE_PREFIX_RE.match(line)
        depth = prefix.group(0).count(">") if prefix else 0
        inner = line[prefix.end():] if prefix else line
        if inner.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((number, inner, depth, line))
    return out


def check_callouts(lines, types, text):
    """Rules callout-type, callout-nesting and pitfall-shape."""
    findings = []
    raw_lines = dict(enumerate(text.split("\n"), start=1))
    for number, _inner, _depth, raw in lines:
        opener = OPENER_RE.match(raw)
        if not opener:
            continue
        kind = opener.group(2).lower()
        depth = opener.group(1).count(">")
        if kind not in types:
            findings.append((number, "callout-type", f"[!{opener.group(2)}] is not one of the {len(types)} catalogued types"))
        if depth > MAX_NESTING:
            findings.append((number, "callout-nesting", f"[!{opener.group(2)}] nests {depth} levels deep (limit {MAX_NESTING})"))
        if kind == "pitfall":
            body = []
            cursor = number
            while cursor in raw_lines and raw_lines[cursor].lstrip().startswith(">"):
                if cursor > number:
                    again = OPENER_RE.match(raw_lines[cursor])
                    if again and again.group(1).count(">") <= depth:
                        break
                body.append(raw_lines[cursor])
                cursor += 1
            joined = "\n".join(body)
            missing = [name for name, pat in (("Problem:", PROBLEM_RE), ("Solution:", SOLUTION_RE)) if not pat.search(joined)]
            if missing:
                findings.append((number, "pitfall-shape", "[!pitfall] lacks " + " and ".join(missing)))
    return findings


def check_headings(text):
    """Rules heading-h1 and heading-skip."""
    findings = []
    headings = extract_headings(text)
    h1s = [h for h in headings if h.level == 1]
    if not h1s:
        findings.append((1, "heading-h1", "no H1 title"))
    for extra in h1s[1:]:
        findings.append((extra.line, "heading-h1", "more than one H1"))
    previous = None
    for heading in headings:
        if previous is not None and heading.level > previous.level + 1:
            findings.append((heading.line, "heading-skip", f"H{previous.level} is followed by H{heading.level}"))
        previous = heading
    return findings


def check_description(path, frontmatter):
    """Rule frontmatter-description, for a rule file or a skill file."""
    is_rule = "rules" in Path(path).parts[:-1] or Path(path).name == "SKILL.md"
    if not is_rule:
        return []
    fields = parse_frontmatter_map(frontmatter) if frontmatter is not None else None
    value = (fields or {}).get("description", "")
    if value.strip() in ("", ">", "|"):
        return [(1, "frontmatter-description", "a rule or skill file needs a non-empty description key")]
    return []


def check_links(lines):
    """Rule link-extension."""
    findings = []
    for number, inner, _depth, _raw in lines:
        for match in LINK_RE.finditer(CODE_SPAN_RE.sub("", inner)):
            target = match.group(1)
            if SCHEME_RE.match(target) or target[0] in "#{<":
                continue
            local = target.split("#")[0]
            if not local or local.endswith("/"):
                continue
            if Path(local).suffix == "":
                findings.append((number, "link-extension", f"local link `{target}` has no file extension (expected .md)"))
    return findings


def check_tables(lines):
    """Rule table-empty-cell; the separator row is skipped."""
    findings = []
    index = 0
    while index < len(lines) - 1:
        number, inner, _depth, _raw = lines[index]
        following = lines[index + 1]
        if (
            inner.lstrip().startswith("|")
            and following[0] == number + 1
            and following[1].lstrip().startswith("|")
            and SEPARATOR_RE.match(following[1])
        ):
            rows = [(number, inner)]
            last = following[0]
            index += 2
            while index < len(lines) and lines[index][0] == last + 1 and lines[index][1].lstrip().startswith("|"):
                last = lines[index][0]
                rows.append((last, lines[index][1]))
                index += 1
            for row_number, row in rows:
                if any(cell == "" for cell in split_row_cells_code_aware(row)):
                    findings.append((row_number, "table-empty-cell", "table row has an empty cell"))
        else:
            index += 1
    return findings


def lint_text(path, content, types):
    """Return sorted (line, rule, message) findings for one document."""
    text, frontmatter = prepare(content)
    lines = scan_lines(text)
    findings = check_callouts(lines, types, text) + check_headings(text) + check_description(path, frontmatter)
    findings += check_links(lines) + check_tables(lines)
    return sorted(findings)


def collect_files(paths):
    files = []
    for raw in paths:
        target = Path(raw)
        if target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
        elif target.is_file():
            files.append(target)
        else:
            raise OSError(f"no such file or directory: {raw}")
    return files


def main(argv):
    args = list(argv)
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    catalog = DEFAULT_CATALOG
    if "--catalog" in args:
        at = args.index("--catalog")
        if at + 1 >= len(args):
            print("Error: --catalog needs a path", file=sys.stderr)
            return 2
        catalog = Path(args[at + 1])
        del args[at:at + 2]
    if not args or any(a.startswith("--") for a in args):
        print("Usage: lint_markdown.py [--strict] [--catalog PATH] <file.md|dir> ...", file=sys.stderr)
        return 2
    try:
        types = read_type_list(catalog.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: cannot read the callout catalog {catalog}: {exc}", file=sys.stderr)
        return 2
    if not types:
        print(f"Error: no callout types found in {catalog}", file=sys.stderr)
        return 2
    try:
        files = collect_files(args)
        counts = dict.fromkeys(RULES, 0)
        failing = 0
        for path in files:
            content = path.read_text(encoding="utf-8")
            for line, rule, message in lint_text(path.as_posix(), content, types):
                counts[rule] += 1
                if rule != "callout-type" or strict:
                    failing += 1
                print(f"{path.as_posix()}:{line}: {rule}: {message}")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"{len(files)} files read, {len(types)} catalogued types")
    print("rule counts: " + ", ".join(f"{rule}={count}" for rule, count in counts.items()))
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
