#!/usr/bin/env python3
"""Pure-function repair helpers a lessons migrator applies to a lesson file's
text: backfill a missing frontmatter key from the file's own H1, an index
row, or git; quote a `title:` value an unquoted `#` would truncate; reconcile
an index row's status cell against the file's `status:`; append an
over-title index-row sentence to the lesson body under a dated heading,
skipping only a unit already present verbatim; and normalise a lone CR
inside a cell before splitting it into units.

Every text-producing function here preserves the input's byte-order mark
and its own line-ending style, and touches no line it was not asked to.
None of them reads or writes a file -- the caller owns all I/O.

Reuses `migrate_backlog_repairs`'s and `migrate_backlog_support`'s generic
helpers directly (frontmatter split/parse, one-key replacement, a cell's
first-sentence title, git-or-mtime dating, the sentence splitter and the
exact-presence test). `insert_missing_keys` is NOT reused directly: the
backlog version's insertion order is pinned to the backlog's own seven-key
schema, so this module mirrors its shape against this schema's own key
order instead.
"""

import re
from pathlib import Path

from frontmatter_parser import BOM_CHAR
from migrate_backlog_repairs import (
    created_dates,
    partial_frontmatter,
    replace_key_line,
    title_from_cell,
)
from migrate_backlog_support import (
    contains_exact,
    exact_key,
    plain,
    row_units,
    split_units,
)
from update_backlog import _escape_title


class RepairRefused(Exception):
    """A repair that cannot be safely applied without guessing -- the
    caller reports it and moves on to the next file rather than writing a
    wrong value. The message names the path and the reason."""


# The base frontmatter keys every lesson file carries, in the order the
# shipped lesson template renders them (`templates/lesson.md`). This is a
# superset of the generator's own `REQUIRED_KEYS` (nine keys, render-only):
# it adds `date` and `applied-as`, which the corpus carries on every file
# but the generator does not need to render a row.
_KEY_ORDER = (
    "id", "title", "date", "category", "severity", "language",
    "technology", "domain", "source", "status", "applied-as",
)

# Same fence-matching shape `migrate_backlog_repairs.insert_missing_keys`
# uses -- generic frontmatter-fence matching, not schema-specific, so it is
# re-declared here rather than reached into that module's private names.
_OPEN_FENCE_RE = re.compile(r"\A---[ \t]*(\r\n|\n)")
_CLOSE_FENCE_RE = re.compile(r"(\r\n|\n)---[ \t]*(\r\n|\n|\Z)")

_FILENAME_ID_RE = re.compile(r"^LL-(\d{3,})-")
_ROW_ID_DIGITS_RE = re.compile(r"(\d{3,})")
# A lesson H1 is `# LL-NNN-DOMAIN: Title`, and older files carry
# `# LL-NNN: Title`, `# LL-NNN — Title`, `# LL-NNN - Title` or
# `# LL-NNN-Title`. The title is what follows the id, an optional -DOMAIN
# token (only when a colon or dash separator follows it), and one
# separator -- colon, em dash, en dash or hyphen -- with its whitespace.
_H1_TITLE_RE = re.compile(
    r"^#[ \t]+LL-\d+(?:-[A-Za-z0-9]+(?=[ \t]*(?::|—|–|-[ \t])))?"
    r"[ \t]*(?::|—|–|-)?[ \t]*(.+)$",
    re.MULTILINE,
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# A plain YAML scalar may not open with one of these indicator characters.
# Combined with the ` #` inline-comment trap (an unquoted value truncates at
# a following " #"), this is what triggers quoting a `title:` value.
_YAML_LEAD_SPECIAL = set("!&*?|>%@,[]{}#'\"")


def insert_missing_keys(text: str, missing: dict, nl: str) -> str:
    """Insert each `key: value` line of `missing` just before the closing
    fence, in this schema's own key order, touching no existing line --
    every byte outside the inserted span is unchanged, including the BOM.
    A file with no frontmatter block at all gains a new one at its top
    (after the BOM, in `nl`, followed by one blank line), so the whole
    original text survives as the new file's suffix. Raises ValueError
    when a block opens but never closes. Mirrors
    `migrate_backlog_repairs.insert_missing_keys` against `_KEY_ORDER`
    above instead of the backlog's seven-key one."""
    bom = BOM_CHAR if text.startswith(BOM_CHAR) else ""
    content = text[len(bom):]
    added = "".join(f"{key}: {missing[key]}{nl}" for key in _KEY_ORDER if key in missing)
    open_match = _OPEN_FENCE_RE.match(content)
    if not open_match:
        return f"{bom}---{nl}{added}---{nl}{nl}{content}"
    close_match = _CLOSE_FENCE_RE.search(content, open_match.end())
    if close_match is None:
        raise ValueError("insert_missing_keys: no closing frontmatter fence")
    insert_at = close_match.start() + len(close_match.group(1))
    return bom + content[:insert_at] + added + content[insert_at:]


def _flow_list(cell: str) -> str:
    """Render a comma-separated index-row cell as a flow-form YAML list,
    e.g. "python, yaml" -> "[python, yaml]". An empty cell renders "[]"."""
    items = [plain(part) for part in cell.split(",")]
    items = [item for item in items if item]
    return "[" + ", ".join(items) + "]"


def _first_sentence(cell: str) -> str:
    units = split_units(plain(cell))
    return units[0] if units else plain(cell)


def backfill_plan(path, text: str, row, valid_statuses, today,
                   project_root=None, lessons_dir=None) -> dict:
    """Plan values for every base key (`_KEY_ORDER`) absent from `text`'s
    frontmatter block, as `{key: (value, source)}`. Never writes `text`;
    the caller renders the plan through `insert_missing_keys`.

    `row` is an optional mapping of the legacy index row's lowercase
    column names (`id`, `title`, `category`, `severity`, `language`,
    `technology`, `domain`, `source`, `status`) to that cell's plain or
    lightly-decorated text, or None when no row names this file.

    `project_root`/`lessons_dir` are optional: when both are given, a
    missing `date` falls back through `created_dates` (git) before mtime;
    when either is omitted, it falls straight to mtime, still naming the
    source. Raises `RepairRefused` naming `path` on every condition that
    cannot be repaired without guessing: an unparseable block, no block
    and no row, an id disagreement between the filename and the row, and
    a required value neither the file nor the row can supply. A file with
    no block but a row is planned in full; `insert_missing_keys` then
    creates its block.
    """
    path = Path(path)
    raw_map, has_block, _bom, _nl = partial_frontmatter(text)
    if has_block and raw_map is None:
        raise RepairRefused(f"{path}: frontmatter block present but unparseable")
    if raw_map is None and row is None:
        raise RepairRefused(f"{path}: no frontmatter block and no index row names this file")
    existing = raw_map or {}
    missing_keys = [key for key in _KEY_ORDER if key not in existing]

    plan: dict = {}

    if "id" in missing_keys:
        m = _FILENAME_ID_RE.match(path.name)
        file_num = m.group(1) if m else None
        row_num = None
        if row is not None:
            rm = _ROW_ID_DIGITS_RE.search(plain(str(row.get("id", ""))))
            row_num = rm.group(1) if rm else None
        if file_num is None and row_num is None:
            raise RepairRefused(f"{path}: id cannot be backfilled -- no LL-NNN in the "
                                 f"filename and no id in the index row")
        if file_num is not None and row_num is not None and file_num.lstrip("0") != row_num.lstrip("0"):
            raise RepairRefused(f"{path}: id disagreement -- filename says {file_num!r}, "
                                 f"row says {row_num!r}")
        num = file_num or row_num
        assert num is not None  # the two refusals above rule out both being None
        plan["id"] = (f"LL-{int(num):03d}", "filename" if file_num else "row")

    if "title" in missing_keys:
        h1 = _H1_TITLE_RE.search(text)
        if h1:
            plan["title"] = (h1.group(1).strip(), "h1")
        else:
            cell = str(row.get("title", "")) if row is not None else ""
            if not cell.strip():
                raise RepairRefused(f"{path}: title cannot be backfilled -- no H1 and "
                                     f"no row Title cell")
            plan["title"] = (title_from_cell(_first_sentence(cell)), "row")

    if "date" in missing_keys:
        row_date = str(row.get("date", "")).strip() if row is not None else ""
        row_source_cell = str(row.get("source", "")).strip() if row is not None else ""
        if row_date and _ISO_DATE_RE.match(row_date):
            plan["date"] = (row_date, "row-date")
        elif row_source_cell and _ISO_DATE_RE.match(row_source_cell):
            plan["date"] = (row_source_cell, "row-source")
        elif project_root is not None and lessons_dir is not None:
            dates = created_dates(Path(project_root), [path], Path(lessons_dir))
            value, source = dates[path]
            plan["date"] = (value, source)
        else:
            import datetime
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone()
            plan["date"] = (mtime.date().isoformat(), "mtime")

    for key in ("category", "severity"):
        if key in missing_keys:
            cell = plain(str(row.get(key, ""))) if row is not None else ""
            if not cell:
                raise RepairRefused(f"{path}: {key} cannot be backfilled -- no row {key} cell")
            plan[key] = (cell, "row")

    for key in ("language", "technology", "domain"):
        if key in missing_keys:
            cell = str(row.get(key, "")) if row is not None else ""
            plan[key] = (_flow_list(cell), "row")

    if "source" in missing_keys:
        cell = plain(str(row.get("source", ""))) if row is not None else ""
        if not cell:
            raise RepairRefused(f"{path}: source cannot be backfilled -- no row Source cell")
        plan["source"] = (cell, "row")

    if "status" in missing_keys:
        row_status = plain(str(row.get("status", ""))) if row is not None else ""
        if row_status and row_status in valid_statuses:
            plan["status"] = (row_status, "row")
        else:
            plan["status"] = ("documented", "default")

    if "applied-as" in missing_keys:
        plan["applied-as"] = ("null", "default")  # the value templates/lesson.md ships

    return plan


def quote_title_if_needed(text: str) -> tuple:
    """Quote an unquoted `title:` value that YAML would otherwise truncate
    at an inline `#`, or that opens with a YAML indicator character.
    Returns (text, changed). Never touches an already-quoted value."""
    raw_map, has_block, _bom, _nl = partial_frontmatter(text)
    if not has_block or raw_map is None or "title" not in raw_map:
        return text, False
    current = raw_map["title"].strip()
    if not current or current[0] in ("'", '"'):
        return text, False
    needs_quoting = (" #" in current) or (current[0] in _YAML_LEAD_SPECIAL)
    if not needs_quoting:
        return text, False
    new_value = f'"{_escape_title(current)}"'
    return replace_key_line(text, "title", new_value), True


def reconcile_status(text: str, row_status, mode, valid_statuses) -> tuple:
    """Reconcile an index row's Status cell against the file's own
    `status:`. `mode` is "index-wins" (the row's value overwrites the
    file's, when both are valid and differ), "frontmatter-wins" (the file
    is left untouched and the difference is recorded), or None (refuse,
    naming the mismatch and both flag spellings). Returns
    (text, changed, detail). An invalid status on either side never wins:
    reconciliation is skipped and `detail` names which side was invalid."""
    raw_map, has_block, _bom, _nl = partial_frontmatter(text)
    if not has_block or raw_map is None or "status" not in raw_map:
        return text, False, "no status: key present to reconcile against"
    current = raw_map["status"].strip().strip("'\"")
    if row_status is None:
        return text, False, "no row status to compare"
    row_status = str(row_status).strip()
    if row_status == current:
        return text, False, f"row and frontmatter status already agree ({current!r})"
    row_valid = row_status in valid_statuses
    fm_valid = current in valid_statuses
    if not row_valid or not fm_valid:
        return text, False, (
            f"status differs but is not reconciled -- row={row_status!r} "
            f"(valid={row_valid}), frontmatter={current!r} (valid={fm_valid})"
        )
    if mode is None:
        raise RepairRefused(
            f"status mismatch: row={row_status!r}, frontmatter={current!r}; "
            f"pass --reconcile index-wins or --reconcile frontmatter-wins"
        )
    if mode == "index-wins":
        new_text = replace_key_line(text, "status", row_status)
        return new_text, True, f"index-wins: frontmatter status {current!r} -> {row_status!r}"
    if mode == "frontmatter-wins":
        return text, False, f"frontmatter-wins: kept {current!r}, row said {row_status!r}"
    raise ValueError(f"unknown reconcile mode {mode!r}")


def normalize_lone_cr(cell: str) -> str:
    """A `\\r` not followed by `\\n` becomes a single space. Applied to a
    cell before splitting it into units -- never to a file's own text."""
    return re.sub(r"\r(?!\n)", " ", cell)


def cell_units(title_cell: str, frontmatter_title: str) -> list:
    """Every sentence unit of an index row's Title cell except the one
    equal to the frontmatter title, in order. Normalises a lone CR before
    splitting. The title-equality comparison strips markdown and folds
    case via `exact_key` (mirrors `migrate_backlog_support.row_units`);
    the returned units keep their original markdown, unmodified, because
    they are appended to the lesson body verbatim -- conservation over
    deduplication, since a dropped sentence cannot be recovered later."""
    cell = normalize_lone_cr(title_cell)
    return row_units(cell, frontmatter_title)


def append_index_note(text: str, units: list, nl: str, today) -> tuple:
    """Append every unit not already present verbatim in `text` under
    `## Index Note (migrated {today})`, one paragraph per unit, using
    `nl`. Frontmatter is untouched -- the append is a pure suffix. A unit
    is skipped when its exact-match key already occurs in the exact-match
    key of the whole text (a prior run's own append included), so a
    second call with the same units appends nothing. Returns
    (text, appended, skipped) -- the units actually added, and the ones
    skipped as already present."""
    if not units:
        return text, [], []
    body_key = exact_key(text)
    to_add, appended, skipped = [], [], []
    for unit in units:
        key = exact_key(unit)
        if key and contains_exact(key, body_key):
            skipped.append(unit)
        else:
            to_add.append(unit)
            appended.append(unit)
    if not to_add:
        return text, appended, skipped
    heading = f"## Index Note (migrated {today})"
    block = nl + heading
    for unit in to_add:
        block += nl + nl + unit
    block += nl
    if not text.endswith(("\n", "\r")):
        block = nl + block
    return text + block, appended, skipped


def repair_ledger_rows(records) -> str:
    """Render `records` -- an iterable of (path, repair, before, after,
    source) tuples -- as markdown table data rows (no header), one row
    per record, `before`/`after` truncated to their first 60 characters
    and pipe/newline-escaped for a single table cell."""
    lines = []
    for path, repair, before, after, source in records:
        b = (before or "")[:60].replace("|", "\\|").replace("\n", " ").replace("\r", "")
        a = (after or "")[:60].replace("|", "\\|").replace("\n", " ").replace("\r", "")
        lines.append(f"| {path} | {repair} | {b} | {a} | {source} |")
    return "\n".join(lines)
