"""Backlog index scan: reads each item file's frontmatter at the text level,
scans the active and Archive backlog dirs, and resolves `blocks:` edges.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backlog_index_schema import (
    REQUIRED_KEYS,
    GeneratorError,
    _index_naming,
    is_generated_index_file,
)
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block
from score_backlog import _strip_inline_comment

_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")
# --------------------------------------------------------------------------
# Frontmatter extraction
#
# `frontmatter_parser` is the one shared split/parse primitive every script
# in this tree already goes through -- reused here rather than re-derived.
# Deliberately NOT layered on top of a YAML-typed parse: PyYAML's implicit
# resolvers turn an unquoted all-octal-digit id like "061" into the int 49,
# and turn an unquoted `created:` value into a `datetime.date`. Both are
# silent value corruption for a renderer whose job is to reproduce the
# author's literal text, so the fields that must stay exact are read at the
# text level via `parse_frontmatter_map` instead of through a YAML loader.
# --------------------------------------------------------------------------


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _normalize_id_text(raw: str) -> str:
    """Zero-pad a frontmatter id/blocks-entry to the 3-digit stored form."""
    digits = _strip_quotes(raw.strip())
    if not digits.isdigit():
        raise GeneratorError(f"non-numeric id value {raw!r}")
    return digits.zfill(3)


def _parse_list_field(raw: str) -> list:
    """Parse a `blocks:`-shaped frontmatter value into a list of id strings.

    Handles both the flow form written on the key's own line
    (``blocks: [007, 009]``) and the block form spread over indented `- `
    lines, since `parse_frontmatter_map` hands back either shape as the
    key's raw, un-typed value text.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [_normalize_id_text(part) for part in inner.split(",") if part.strip()]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_normalize_id_text(match.group(1)))
    return items


def _read_frontmatter_map(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    parts = split_frontmatter_block(content)
    if parts is None:
        raise GeneratorError(f"{path}: no well-formed frontmatter block")
    raw_text, _body = parts
    fm_map = parse_frontmatter_map(raw_text)
    if fm_map is None:
        raise GeneratorError(f"{path}: frontmatter block could not be parsed")
    return fm_map


def _extract_fields(path: Path, raw_map: dict) -> dict:
    """Turn a raw {key: value-text} map into the seven typed fields.

    Raises when a required key is absent, or present but empty -- the
    generator reports a missing key and stops; it never fills one in.
    """
    missing = [key for key in REQUIRED_KEYS if key not in raw_map]
    if missing:
        raise GeneratorError(
            f"{path}: missing required frontmatter key(s): {', '.join(missing)}"
        )

    fields: dict = {}
    for key in ("title", "priority", "status", "abbrev", "created"):
        raw_value = raw_map[key]
        if key == "created":
            # A trailing YAML inline comment on `created:` survives past
            # `parse_frontmatter_map`'s text-level read (score_backlog.py's
            # `_strip_inline_comment` docstring) and would otherwise ship as
            # part of the rendered Created cell.
            raw_value = _strip_inline_comment(raw_value)
        value = _strip_quotes(raw_value.strip())
        if not value:
            raise GeneratorError(f"{path}: frontmatter key '{key}' is empty")
        fields[key] = value

    # `id` and `blocks` get the same inline-comment strip as `created`,
    # ported from score_backlog._strip_inline_comment: `blocks: [007, 009]
    # # two` would otherwise drop the trailing edge, and the generator's
    # edge set must equal the scorer's on every item.
    fields["id"] = _normalize_id_text(_strip_inline_comment(raw_map["id"]))
    fields["blocks"] = _parse_list_field(_strip_inline_comment(raw_map["blocks"]))
    fields["_path"] = path
    return fields


def _scan_one_file(path: Path) -> dict:
    raw_map = _read_frontmatter_map(path)
    return _extract_fields(path, raw_map)


def _iter_item_files(backlog_dir: Path, archive_dir: Path, index_path: Path):
    """Yield every item file under the active and archived backlog dirs.

    Both directories are scanned: an archived item still needs an index
    row, and scoping the scan to the active directory alone would silently
    drop every archived item from the index. A "00-"-prefixed file is a
    generated artifact of the backlog tooling itself (the index, its
    changelog), never an item, and is skipped by that convention.

    An Archive shard this module itself generates
    (`Index-Backlog-NNN-NNN.md`) carries no "00-" prefix and lands inside
    `archive_dir`, which this loop globs with `*.md` -- so it is caught
    instead by `is_generated_index_file`, the same predicate the hub/shard
    namers derive their filenames from. Without this, the scan immediately
    after a `--write` would re-ingest every shard as though it were an item
    file lacking frontmatter, and abort the whole generation -- `--check`
    could never return clean after a `--write`.
    """
    naming = _index_naming(index_path)
    seen: set = set()
    for directory in (backlog_dir, archive_dir):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name.startswith("00-") or is_generated_index_file(path.name, naming):
                continue
            resolved = path.resolve()
            if resolved == index_path.resolve() or resolved in seen:
                continue
            seen.add(resolved)
            yield path


def scan_backlog(backlog_dir: Path, archive_dir: Path, index_path: Path) -> list:
    """Scan every item file and return its extracted fields, id-sorted.

    Every file is checked before any error is raised, so one run reports
    every offending item rather than only the first one found. A repeated
    id across two DIFFERENT item files (a sub-item mistakenly reusing its
    parent's id, or a half-moved archive copy left in both `Backlog/` and
    `Backlog/Archive/`) is refused HERE, at scan time, naming both paths and
    the id -- never allowed to reach rendering. Left unrefused, the
    duplicate would render two rows for one id: `--write` would ship both
    silently, and `--check`'s later duplicate-row quarantine (Finding F2)
    would remove the id from its own fresh-render comparison entirely,
    surfacing as a `KeyError` rather than a reported anomaly (Finding F1 of
    the pre-commit review). Refusing before any row renders is the same
    "never fabricate, never half-ship" discipline every other GeneratorError
    in this scanner already applies to a missing key or a dangling `blocks:`
    entry.
    """
    errors = []
    items = []
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        try:
            items.append(_scan_one_file(path))
        except GeneratorError as exc:
            errors.append(str(exc))

    paths_by_id: dict = {}
    for item in items:
        paths_by_id.setdefault(item["id"], []).append(item["_path"])
    for item_id, paths in paths_by_id.items():
        if len(paths) > 1:
            joined = ", ".join(str(p) for p in paths)
            errors.append(
                f"duplicate id {item_id}: claimed by {len(paths)} item files: {joined}"
            )

    if errors:
        raise GeneratorError("\n".join(errors))
    items.sort(key=lambda item: int(item["id"]))
    return items


# --------------------------------------------------------------------------
# Blocks-edge resolution
# --------------------------------------------------------------------------


def build_blocks_index(items: list) -> dict:
    return {item["id"]: set(item["blocks"]) for item in items}


def validate_blocks_resolve(items: list, known_ids: set) -> None:
    """Abort naming the file and the id when a `blocks:` entry is dangling.

    A bare id that names no scanned item is a data error, never a silent
    drop -- the edge it describes would otherwise disappear from the index
    with no trace that it was ever there.
    """
    errors = []
    for item in items:
        for target in item["blocks"]:
            if target not in known_ids:
                errors.append(
                    f"{item['_path']}: blocks: entry '{target}' names no known item"
                )
    if errors:
        raise GeneratorError("\n".join(errors))


def detect_reciprocal_edges(blocks_index: dict) -> list:
    """Return each unordered pair of ids that block one another.

    A reciprocal edge -- A blocks B and B blocks A -- makes two items block
    each other forever the moment either reopens, so it is reported as an
    anomaly rather than silently accepted, reversed, or dropped. Deciding
    which side of such a pair is the data error is a data-correction call
    outside this generator's scope; this function only detects and names
    the pair.
    """
    seen: set = set()
    edges = []
    for a, targets in blocks_index.items():
        for b in targets:
            if a in blocks_index.get(b, set()):
                pair = frozenset((a, b))
                if pair not in seen:
                    seen.add(pair)
                    edges.append(tuple(sorted((a, b))))
    return edges

