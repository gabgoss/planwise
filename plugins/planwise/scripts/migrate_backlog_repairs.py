#!/usr/bin/env python3
"""Pure-function frontmatter and text helpers for a backlog-index migrator's
repair flags: filling a missing key, rewriting one key's value, deriving a
title from an index cell, reading an id/abbrev out of a filename, dating a
file from git with an mtime fallback, and pulling soft-dependency bullets
out of free prose.

No function here writes a file or reads the index. Every text-producing
function preserves the input's byte-order mark and its own line-ending
style, so a migration built on these pieces changes only what it means to.
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontmatter_parser import BOM_CHAR, parse_frontmatter_map, split_frontmatter_block
from generate_backlog_index import truncate_title
from migrate_backlog_support import newline_of, plain
from update_backlog import _escape_title

# The seven frontmatter keys, in render order -- shared by render_frontmatter
# and insert_missing_keys so the two can never disagree on ordering.
_KEY_ORDER = ("id", "title", "priority", "status", "abbrev", "created", "blocks")

# A "---" fence line, open or close (BOM already stripped); the close search
# requires a real fence LINE, so a value's own literal "---" text cannot end
# the block early.
_OPEN_FENCE_RE = re.compile(r"\A---[ \t]*(\r\n|\n)")
_CLOSE_FENCE_RE = re.compile(r"(\r\n|\n)---[ \t]*(\r\n|\n|\Z)")

# An item filename: "{PREFIX}-{NNN}[-{NN}]-{ABBREV}-{Topic}.md", prefix any
# alphabetic run -- a consumer's own naming convention supplies it.
_FILENAME_RE = re.compile(r"^[A-Za-z]+-(\d{3,})(?:-\d{2})?-([A-Z][A-Z0-9]*)-")

# The first zero-padded 3+ digit run (contrast sup.ids_in, which collects
# every digit run, including 1-2 digit ones, and returns them sorted).
_ID_RE = re.compile(r"\d{3,}")

# A bullet's marker line, capturing its indent to detect a continuation line.
_BULLET_RE = re.compile(r"^(\s*)-\s")

# A bold heading line such as "**Soft dependencies**" -- structural, never a
# bullet or a continuation of one.
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*[^*]+\*\*\s*:?\s*$")

# One line of `git log --format=%as` output: a bare ISO date.
_DATE_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def partial_frontmatter(text: str) -> tuple[dict | None, bool, str, str]:
    """Split and parse a possibly-partial frontmatter block into
    (raw_map, has_block, bom, newline). `has_block` is False only when
    `text` has no opening "---" fence. `raw_map` is None with `has_block`
    True when the block opens but never closes, or is otherwise
    unparseable -- both are "refuse to repair this file" states."""
    nl = newline_of(text)
    bom = BOM_CHAR if text.startswith(BOM_CHAR) else ""
    normalized = text.replace("\r\n", "\n")
    if not normalized.lstrip(BOM_CHAR).startswith("---\n"):
        return None, False, bom, nl
    split = split_frontmatter_block(normalized)
    if split is None:
        return None, True, bom, nl
    frontmatter_text, _body = split
    return parse_frontmatter_map(frontmatter_text), True, bom, nl


def render_frontmatter(fields: dict, nl: str) -> str:
    """Render a brand-new seven-key frontmatter block plus its blank line.

    Key order and quoting mirror `update_backlog._render_bli_file`'s own
    block exactly. `fields["blocks"]` is a list of id strings; it renders
    flow-style, `[]` when empty.
    """
    title = _escape_title(str(fields["title"]))
    blocks = ", ".join(fields["blocks"])
    lines = [
        "---", f"id: {fields['id']}", f'title: "{title}"',
        f"priority: {fields['priority']}", f"status: {fields['status']}",
        f"abbrev: {fields['abbrev']}", f"created: {fields['created']}",
        f"blocks: [{blocks}]", "---", "", "",
    ]
    return nl.join(lines)


def insert_missing_keys(text: str, missing: dict, nl: str) -> str:
    """Insert each `key: value` line of `missing` just before the closing
    fence, in canonical key order, touching no existing line -- every byte
    outside the inserted span is unchanged, including the BOM. Raises
    ValueError when `text` has no complete frontmatter block to insert
    into."""
    bom = BOM_CHAR if text.startswith(BOM_CHAR) else ""
    content = text[len(bom):]
    open_match = _OPEN_FENCE_RE.match(content)
    if not open_match:
        raise ValueError("insert_missing_keys: no opening frontmatter fence")
    close_match = _CLOSE_FENCE_RE.search(content, open_match.end())
    if close_match is None:
        raise ValueError("insert_missing_keys: no closing frontmatter fence")
    insert_at = close_match.start() + len(close_match.group(1))
    added = "".join(f"{key}: {missing[key]}{nl}" for key in _KEY_ORDER if key in missing)
    return bom + content[:insert_at] + added + content[insert_at:]


def replace_key_line(text: str, key: str, value: str) -> str:
    """Replace one top-level frontmatter key's value with `value`. A
    block-form list value (the key line plus indented `- ` lines) is
    replaced whole, becoming one flow-form line. Raises KeyError when `key`
    has no line in `text`'s frontmatter, including when there is no block
    at all."""
    bom = BOM_CHAR if text.startswith(BOM_CHAR) else ""
    content = text[len(bom):]
    open_match = _OPEN_FENCE_RE.match(content)
    if not open_match:
        raise KeyError(key)
    close_match = _CLOSE_FENCE_RE.search(content, open_match.end())
    if close_match is None:
        raise KeyError(key)
    fm_start, fm_end = open_match.end(), close_match.start()
    frontmatter = content[fm_start:fm_end]
    pattern = re.compile(
        rf"^{re.escape(key)}:[ \t]*[^\r\n]*(?:(?:\r\n|\n)[ \t]+-[ \t][^\r\n]*)*", re.MULTILINE,
    )
    new_frontmatter, count = pattern.subn(f"{key}: {value}", frontmatter, count=1)
    if count == 0:
        raise KeyError(key)
    return bom + content[:fm_start] + new_frontmatter + content[fm_end:]


def title_from_cell(cell: str) -> str:
    """Derive a frontmatter title from an index row's cell: markdown
    stripped and whitespace collapsed (`migrate_backlog_support.plain`),
    then truncated at a word boundary to 120 characters by the generator's
    own `truncate_title` -- the same cap it renders against."""
    rendered, _was_truncated = truncate_title(plain(cell), 120)
    return rendered


def filename_fields(name: str) -> tuple[str, str] | None:
    """Return (id, abbrev) parsed out of an item filename, or None.

    Generic on purpose: `{PREFIX}-{NNN}[-{NN}]-{ABBREV}-...`, where PREFIX
    is any alphabetic run -- a consumer's own naming convention supplies it.
    """
    m = _FILENAME_RE.match(name)
    return None if not m else (m.group(1), m.group(2))


def _run_git(args: list, cwd: Path) -> str | None:
    """Run a git command, returning its stdout, or None on any failure --
    git absent, `cwd` not a repository, or a non-zero exit."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def created_dates(project_root: Path, paths: list, backlog_dir: Path) -> dict:
    """Map each path in `paths` to (YYYY-MM-DD, source). `source` is "git"
    when one bulk `git log --diff-filter=A --name-only` over `backlog_dir`
    finds the path's own earliest add date under its current name;
    "git-follow" when it does not (the path was renamed into its current
    location) and a per-file `--follow --diff-filter=A` query traces an add
    date back through the rename; "mtime" when git is absent, `project_root`
    is not a repository, or neither query returns a result."""
    earliest: dict = {}
    bulk_out = _run_git(
        ["git", "log", "--diff-filter=A", "--name-only", "--format=%as", "--", str(backlog_dir)],
        project_root,
    )
    if bulk_out is not None:
        current_date = None
        for line in bulk_out.splitlines():
            line = line.strip()
            if not line:
                continue
            if _DATE_LINE_RE.match(line):
                current_date = line
                continue
            if current_date is None:
                continue
            rel = line.replace("\\", "/")
            if rel not in earliest or current_date < earliest[rel]:
                earliest[rel] = current_date

    results: dict = {}
    root = Path(project_root).resolve()
    for path in paths:
        try:
            rel = Path(path).resolve().relative_to(root).as_posix()
        except ValueError:
            rel = None
        if rel is not None and rel in earliest:
            results[path] = (earliest[rel], "git")
            continue
        follow_out = _run_git(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%as", "--", str(path)],
            project_root,
        )
        dates = [ln.strip() for ln in (follow_out or "").splitlines() if _DATE_LINE_RE.match(ln.strip())]
        if dates:
            results[path] = (min(dates), "git-follow")
            continue
        results[path] = (date.fromtimestamp(Path(path).stat().st_mtime).isoformat(), "mtime")
    return results


def first_id_in(text: str) -> str | None:
    """The first zero-padded 3+ digit id in `text`, in reading order, or
    None. Contrast `migrate_backlog_support.ids_in`, which collects every
    digit run and returns them sorted."""
    m = _ID_RE.search(text)
    return None if not m else m.group(0).zfill(3)


def dependency_bullets(lines: list) -> list:
    """Pull every `- ` bullet (plus its indented continuation lines) out of
    `lines`, as (line_no, owner_id, bullet_text). A bold heading line such
    as "**Soft dependencies**" is skipped, never treated as a bullet or a
    continuation of one. `owner_id` is `first_id_in(bullet_text)`, None
    when the bullet names no id."""
    results = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if _BOLD_HEADING_RE.match(line):
            i += 1
            continue
        m = _BULLET_RE.match(line)
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        bullet_lines = [line]
        j = i + 1
        while j < n:
            nxt = lines[j]
            if not nxt.strip() or _BULLET_RE.match(nxt) or _BOLD_HEADING_RE.match(nxt):
                break
            if len(nxt) - len(nxt.lstrip()) <= indent:
                break
            bullet_lines.append(nxt)
            j += 1
        results.append((i, first_id_in("\n".join(bullet_lines)), "\n".join(bullet_lines)))
        i = j
    return results
