"""Lessons index scan: text-level, quote-aware frontmatter extraction, the
lesson-file discovery walk, and `scan_lessons`, which returns the id-sorted
fields plus every id mismatch and duplicate id. Reads lesson files and never
writes them.

Imports `lessons_index_schema` from this generator, plus `frontmatter_parser`,
`generate_backlog_index`, `parse_lessons`, and `reconcile_common`. Imported by
`lessons_index_run`. Re-exported unchanged by the `generate_lessons_index`
facade.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from generate_backlog_index import _index_naming, is_generated_index_file
from lessons_index_schema import REQUIRED_KEYS, LessonsGeneratorError
from parse_lessons import LESSON_FILE_RE, duplicate_ids, lesson_files
from reconcile_common import read_text_preserving_newlines

# --------------------------------------------------------------------------
# Frontmatter extraction (mirrors generate_backlog_index's item scanner,
# re-written for the lessons schema and its list-shaped fields)
# --------------------------------------------------------------------------

# Ported from score_backlog.py's `_strip_inline_comment` (not imported --
# score_backlog pulls in scoring-only imports this module has no use for),
# then made quote-aware here. `parse_frontmatter_map` hands back a key's raw
# value text verbatim, trailing comment included -- unlike a typed YAML
# load, which strips a comment at the tokenizer level regardless of
# position. Without this, a flow-form list like `technology: [python,
# yaml]  # two` would carry the comment into the last entry. Applied
# line-by-line so a block-form multi-line value (each `- item` on its own
# line) strips a per-line comment without disturbing sibling lines.
#
# Quote-awareness: a raw value may open with a matching `'`/`"` (a
# block-list line may prefix it with `- ` first). Per YAML, a `#` inside a
# quoted scalar is text, never a comment start -- only a `#` appearing
# AFTER the closing quote can begin a comment. An unquoted value keeps the
# plain rule: the first ` #`/`\t#` starts a comment.
_TRAILING_COMMENT_RE = re.compile(r"[ \t]+#.*$")


def _find_closing_quote(value: str, quote: str):
    """Index of `value`'s closing `quote` (which opens `value[0]`), honouring
    `\\"`/`\\\\` escapes inside a double-quoted scalar and `''`-doubling
    inside a single-quoted one. `None` if the quote never closes."""
    i = 1
    n = len(value)
    while i < n:
        ch = value[i]
        if quote == '"' and ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == quote:
            if quote == "'" and i + 1 < n and value[i + 1] == "'":
                i += 2
                continue
            return i
        i += 1
    return None


def _strip_comment_from_line(line: str) -> str:
    """Strip a trailing YAML inline comment from one line, quote-aware."""
    stripped = line.lstrip()
    lead_len = len(line) - len(stripped)
    marker_len = 0
    if stripped[:1] == "-":
        rest = stripped[1:]
        marker_len = 1 + (len(rest) - len(rest.lstrip()))
    value_start = lead_len + marker_len
    value = line[value_start:]
    if value[:1] in ("'", '"'):
        close = _find_closing_quote(value, value[0])
        if close is not None:
            head = line[: value_start + close + 1]
            tail = _TRAILING_COMMENT_RE.sub("", line[value_start + close + 1 :])
            return head + tail
        # Unterminated quote -- nothing after it is comment territory.
        return line
    return _TRAILING_COMMENT_RE.sub("", line)


def _strip_inline_comment(raw: str) -> str:
    """Strip a trailing YAML inline comment from each line of `raw`,
    quote-aware (see the module comment above this function)."""
    return "\n".join(_strip_comment_from_line(line) for line in raw.split("\n"))


def _unescape_double_quoted(inner: str) -> str:
    """Unescape `\\"` to `"` and `\\\\` to `\\` inside a double-quoted
    scalar's already-unquoted inner text, single pass so escape order
    cannot be misread as it would be under sequential `str.replace`."""
    out = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == "\\" and i + 1 < n and inner[i + 1] in ('"', "\\"):
            out.append(inner[i + 1])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present, and
    unescape the scalar's own escape sequences: a double-quoted value
    unescapes `\\"` and `\\\\`, and a single-quoted value unescapes `''`
    to a literal `'`. An unquoted value passes through unchanged."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1]
        if text[0] == '"':
            return _unescape_double_quoted(inner)
        return inner.replace("''", "'")
    return text


_ID_VALUE_RE = re.compile(r"^(?:LL-)?0*(\d+)$")


def _normalize_id_text(raw: str) -> int:
    """Normalise a frontmatter `id:` value to its integer form.

    Accepts a bare digit string, an `LL-`-prefixed form, and a quoted
    form of either. `format_id` renders the canonical `LL-{n:03d}` text
    back out at render time -- this function is never the render step.
    """
    text = _strip_quotes(raw.strip()).strip()
    match = _ID_VALUE_RE.match(text)
    if not match:
        raise LessonsGeneratorError(f"non-numeric id value {raw!r}")
    return int(match.group(1))


_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")


def _split_flow_list_items(inner: str) -> list:
    """Split a flow-list's bracket-stripped inner text on top-level commas,
    quote-aware: a comma inside a `'...'`/`"..."` item is text, never a
    separator, per the same `_find_closing_quote` rule the comment strip
    uses."""
    items = []
    i = 0
    n = len(inner)
    start = 0
    while i < n:
        ch = inner[i]
        if ch in ("'", '"'):
            close = _find_closing_quote(inner[i:], ch)
            i = i + close + 1 if close is not None else i + 1
            continue
        if ch == ",":
            items.append(inner[start:i])
            i += 1
            start = i
            continue
        i += 1
    items.append(inner[start:])
    return items


def _parse_list_field(raw: str) -> list:
    """Parse a `language:`/`technology:`/`domain:`-shaped frontmatter value
    into a list of strings.

    Handles both the flow form written on the key's own line
    (``language: [python, yaml]``) and the block form spread over indented
    `- ` lines, since `parse_frontmatter_map` hands back either shape as
    the key's raw, un-typed value text. Each item is quote-stripped and
    unescaped with the same `_strip_quotes` helper the scalar fields use,
    so a quoted item never keeps its quote characters in the rendered
    cell. The caller comma-joins the result for the rendered cell.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [
            _strip_quotes(part.strip())
            for part in _split_flow_list_items(inner)
            if part.strip()
        ]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_strip_quotes(match.group(1).strip()))
    return items


def _read_frontmatter_map(path: Path) -> dict:
    raw_content = read_text_preserving_newlines(path)
    # See the module docstring's CRLF section: split_frontmatter_block's
    # fence check is LF-only, so a CRLF file's line endings are normalised
    # before the split.
    content = raw_content.replace("\r\n", "\n")
    parts = split_frontmatter_block(content)
    if parts is None:
        raise LessonsGeneratorError(f"{path}: no well-formed frontmatter block")
    raw_text, _body = parts
    fm_map = parse_frontmatter_map(raw_text)
    if fm_map is None:
        raise LessonsGeneratorError(f"{path}: frontmatter block could not be parsed")
    return fm_map


def _extract_fields(path: Path, raw_map: dict, valid_statuses: frozenset) -> dict:
    """Turn a raw {key: value-text} map into the nine typed fields.

    Raises when a required key is absent or empty, or when `status:` is
    not one of the project's declared lesson statuses -- the generator
    reports and stops; it never fills one in.
    """
    missing = [key for key in REQUIRED_KEYS if key not in raw_map]
    if missing:
        raise LessonsGeneratorError(
            f"{path}: missing required frontmatter key(s): {', '.join(missing)}"
        )

    # Strip a trailing inline comment from every raw value before any
    # further parse -- one pass covers id, the scalar fields, and both
    # list-field shapes.
    stripped = {key: _strip_inline_comment(value) for key, value in raw_map.items()}

    fields: dict = {}
    for key in ("title", "category", "severity", "source", "status"):
        value = _strip_quotes(stripped[key].strip())
        if not value:
            raise LessonsGeneratorError(f"{path}: frontmatter key '{key}' is empty")
        fields[key] = value

    if fields["status"] not in valid_statuses:
        raise LessonsGeneratorError(
            f"{path}: status {fields['status']!r} is not a declared lesson "
            f"status ({sorted(valid_statuses)})"
        )

    try:
        fields["id"] = _normalize_id_text(stripped["id"])
    except LessonsGeneratorError as exc:
        raise LessonsGeneratorError(
            f"{path}: unreadable id value {raw_map['id']!r} ({exc})"
        ) from exc

    for key in ("language", "technology", "domain"):
        fields[key] = _parse_list_field(stripped[key])

    # `module:` is not in REQUIRED_KEYS -- most lessons carry no code-bucket
    # module at all. Read it only when present, for the companion's
    # code_bucket Module column (index rendering never reads this key).
    fields["module"] = _strip_quotes(stripped["module"].strip()) if "module" in stripped else ""

    fields["_path"] = path
    return fields


def _iter_lesson_files(lessons_dir: Path, archive_dir: Path, naming) -> list:
    """Every lesson file directly under `lessons_dir` and `Archive/` (each
    scanned non-recursively, BOTH directories always), as a list of
    `(path, in_archive)` pairs. Discovery goes through
    `parse_lessons.lesson_files` -- the same numbered-id, case-insensitive
    `.md` reader every other module in this project imports -- rather than
    a bare `glob('LL-*.md')`, which also matches a non-numbered name like
    `LL-template.md`: that file has no `LL-\\d+` id to extract, so scanning
    it either mis-scans as a lesson or (missing the required frontmatter
    keys) refuses the whole run over a file that was never a lesson. A
    generated index artifact this generator itself would emit (the hub, an
    overflow leaf, or an Archive shard) is skipped -- it is never a lesson
    file.
    """
    pairs = []
    for id_path_pairs, in_archive in (
        (lesson_files(lessons_dir, None), False),
        (lesson_files(None, archive_dir), True),
    ):
        for _lesson_id, path in id_path_pairs:
            if is_generated_index_file(path.name, naming):
                continue
            pairs.append((path, in_archive))
    return pairs


def _check_id_mismatch(path: Path, frontmatter_id: int):
    """None, or a dict naming a lesson whose filename number disagrees
    with its own frontmatter `id:`."""
    match = LESSON_FILE_RE.match(path.name)
    if match is None:
        return None
    filename_id = int(match.group(1))
    if filename_id != frontmatter_id:
        return {"path": path, "filename_id": filename_id, "frontmatter_id": frontmatter_id}
    return None


@dataclass
class LessonScanResult:
    """The result of scanning every lesson file: the extracted, id-sorted
    fields, every filename/frontmatter id mismatch found, and every id
    claimed by more than one file (an anomaly recorded here, not raised --
    a later write path maps it to a refusal).
    """

    items: list
    id_mismatches: list = field(default_factory=list)
    duplicate_ids: dict = field(default_factory=dict)


def scan_lessons(
    lessons_dir: Path, archive_dir: Path, index_path: Path, valid_statuses: frozenset
) -> LessonScanResult:
    """Scan every lesson file and return its extracted fields, id-sorted.

    Every file is checked before any error is raised, so one run reports
    every offending file rather than only the first one found.
    """
    naming = _index_naming(index_path)
    errors = []
    items = []
    id_mismatches = []
    for path, in_archive in _iter_lesson_files(lessons_dir, archive_dir, naming):
        try:
            raw_map = _read_frontmatter_map(path)
            fields = _extract_fields(path, raw_map, valid_statuses)
        except LessonsGeneratorError as exc:
            errors.append(str(exc))
            continue
        fields["_in_archive"] = in_archive
        mismatch = _check_id_mismatch(path, fields["id"])
        if mismatch is not None:
            id_mismatches.append(mismatch)
        items.append(fields)

    if errors:
        raise LessonsGeneratorError("\n".join(errors))

    pairs = [(item["id"], item["_path"]) for item in items]
    dups = duplicate_ids(pairs)

    items.sort(key=lambda item: item["id"])
    return LessonScanResult(items=items, id_mismatches=id_mismatches, duplicate_ids=dups)
