#!/usr/bin/env python3
"""Read one backlog item's YAML frontmatter, typed and at the text level.

`read_item_frontmatter` reads an item file once and returns its frontmatter
as a dict, with the item body and the file's line count riding along. The
keys `id`, `created`, `blocks`, `refined` and `needs_plan` are overlaid from
a text-level read, because YAML's implicit typing mangles a zero-padded id
and the no-YAML fallback must still see the two route flags.

This is a library with no CLI. The backlog router (`score_backlog`) imports
this module and re-exports its names, so `score_backlog.read_item_frontmatter`
and `score_backlog._strip_inline_comment` still resolve for existing callers.
This module imports nothing from the router.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from frontmatter_parser import parse_frontmatter_map, split_frontmatter_block

# Try yaml import; fall back to regex extraction if unavailable
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _strip_quotes(text: str) -> str:
    """Strip one layer of matching quote characters, if present."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


_LIST_ITEM_RE = re.compile(r"^-\s*(.+)$")

# A trailing ` #...`/`\t#...` YAML inline comment, matched per line. Applied
# only to `id`, `created`, and `blocks` (`_strip_inline_comment`'s callers) --
# these three never legitimately contain a `#`, so stripping it unconditionally
# before any further parsing is safe and needs no quoting-aware lookahead.
_TRAILING_COMMENT_RE = re.compile(r"[ \t]+#.*$")


def _strip_inline_comment(raw: str) -> str:
    """Strip a trailing YAML inline comment from each line of `raw`.

    `parse_frontmatter_map` hands back the key's raw value text verbatim,
    comment included -- unlike `yaml.safe_load`, which strips a YAML comment
    at the tokenizer level regardless of position. Without this, a value
    like ``blocks: [007, 009]  # two`` overlays the octal-safe text-level
    read with ``['007', '009]  # two']`` (the comment swallowed into the
    last list entry), and ``created: 2026-01-15  # filed`` overlays a
    correctly-YAML-parsed date with a string `date.fromisoformat` cannot
    parse, silently zeroing the age factor. Applied line-by-line so a
    block-form multi-line value (each ``- id`` on its own line) strips a
    per-line comment without disturbing sibling lines.
    """
    return "\n".join(_TRAILING_COMMENT_RE.sub("", line) for line in raw.split("\n"))


def _parse_blocks_field(raw: str) -> list:
    """Parse a `blocks:`-shaped value into a list of id strings, as written.

    Handles the flow form (`blocks: [007, 009]`) and the block form spread
    over indented `- ` lines — `parse_frontmatter_map` hands back either
    shape as the key's raw, un-typed value text. Entries are kept exactly as
    authored (no re-padding); scoring and routing already normalize on
    comparison.
    """
    text = raw.strip()
    if not text or text == "[]":
        return []
    if text.startswith("["):
        inner = text.strip("[]\n ")
        if not inner:
            return []
        return [_strip_quotes(part.strip()) for part in inner.split(",") if part.strip()]
    items = []
    for line in text.split("\n"):
        line = line.strip()
        match = _LIST_ITEM_RE.match(line)
        if match:
            items.append(_strip_quotes(match.group(1).strip()))
    return items


# The route flags read at the text level for the no-YAML fallback only.
_FLAG_KEYS: tuple[str, ...] = ("refined", "needs_plan")


def _text_level_scoring_fields(raw: str) -> dict:
    """Extract `id`, `created`, `blocks`, `refined` and `needs_plan` from
    frontmatter text directly, bypassing YAML's implicit type resolvers.

    `yaml.safe_load` turns an unquoted zero-padded, all-octal-digit `id:`
    like "061" into the int 49 (YAML 1.1 reads a leading-zero digit string as
    octal), and turns a numeric `blocks:` entry the same way. Reading these
    fields at the text level via the shared `parse_frontmatter_map` —
    the same primitive `generate_backlog_index.py` already uses for exactly
    this reason — keeps them exactly as the author wrote them. `refined` and
    `needs_plan` are read here so the no-YAML fallback still sees them; they
    come back as the authored text (`true`, `yes`), which `compute_item_shape`
    reads as true. When PyYAML is present, its typed value for these two
    keys wins and this text is not overlaid. Returns {}
    when `parse_frontmatter_map` cannot attribute the text to any key at all
    (structurally unparseable); a key simply absent from the frontmatter is
    just absent from the result, not an error.
    """
    fm_map = parse_frontmatter_map(raw)
    if fm_map is None:
        return {}
    fields: dict = {}
    if "id" in fm_map:
        candidate = _strip_quotes(_strip_inline_comment(fm_map["id"]).strip())
        if candidate:
            fields["id"] = candidate
    if "created" in fm_map:
        candidate = _strip_quotes(_strip_inline_comment(fm_map["created"]).strip())
        if candidate:
            fields["created"] = candidate
    if "blocks" in fm_map:
        fields["blocks"] = _parse_blocks_field(_strip_inline_comment(fm_map["blocks"]))
    for key in _FLAG_KEYS:
        if key in fm_map:
            candidate = _strip_quotes(_strip_inline_comment(fm_map[key]).strip())
            if candidate:
                fields[key] = candidate
    return fields


def read_item_frontmatter(filepath: Path) -> dict:
    """Read YAML frontmatter from an item file. Returns dict or empty dict.

    The split is the shared `frontmatter_parser` primitive; only the file I/O
    and the typed-value parse are this function's own. Absence of any kind —
    a missing file, no frontmatter block, an unterminated one, or a block YAML
    cannot parse — is reported the same way, as an empty dict, because every
    caller here reads scoring inputs off the result and must not have to
    distinguish "no data" from "bad data" mid-scoring.

    `id`, `created`, `blocks`, `refined` and `needs_plan` are overlaid from
    `_text_level_scoring_fields` after the YAML load (or read directly from it
    when no YAML is available). `yaml.safe_load` mistypes the first three, and
    the last two must survive the no-YAML fallback — see
    `_text_level_scoring_fields`'s docstring. The overlay costs no second file
    read: `raw` is the same frontmatter text already split out below.

    The item body is retained from this same read and returned under `_body`
    — the whole file is already loaded here and the body was previously
    thrown away. `_line_count` (the whole file's newline count, `wc -l`
    semantics) rides along for the same reason. `--route` consumes both;
    nothing else does.
    """
    if not filepath.exists():
        return {}
    content = filepath.read_text(encoding="utf-8")
    parts = split_frontmatter_block(content)
    if parts is None:
        return {}
    raw, body = parts

    if HAS_YAML:
        try:
            fm = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            return {}
        if not isinstance(fm, dict):
            # A frontmatter block that is a bare scalar or a list (e.g. a
            # stray "- one\n- two") parses without error but isn't a
            # mapping -- `.update()` on it would raise AttributeError and
            # abort the whole scoring run for one malformed file, against
            # this function's own "reported the same way, as an empty
            # dict" contract.
            return {}
        overlay = _text_level_scoring_fields(raw)
        for key in _FLAG_KEYS:
            if key in fm:
                # PyYAML already typed it (`yes` and `on` are True); the raw
                # text must not replace that typed value.
                overlay.pop(key, None)
        fm.update(overlay)
    else:
        # The fallback reads the scoring keys `created`/`blocks` and the route
        # keys `refined`/`needs_plan` — never `id`, which nothing in this
        # no-YAML path has ever read.
        fm = {
            key: value
            for key, value in _text_level_scoring_fields(raw).items()
            if key != "id"
        }

    fm["_body"] = body
    fm["_line_count"] = content.count("\n")
    return fm
