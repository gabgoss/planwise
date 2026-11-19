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


def _read_frontmatter_map(path: Path, text: str | None = None) -> dict:
    """Parse `text` when given (an in-memory override), else read `path`."""
    content = text if text is not None else path.read_text(encoding="utf-8")
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


def _scan_one_file(path: Path, text: str | None = None) -> dict:
    raw_map = _read_frontmatter_map(path, text)
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


def scan_backlog(
    backlog_dir: Path, archive_dir: Path, index_path: Path, *, overrides: dict | None = None
) -> list:
    """Scan every item file and return its extracted fields, id-sorted.

    Every file is checked before any error is raised, so one run reports
    every offending item rather than only the first one found. A repeated
    id across two DIFFERENT item files (a sub-item mistakenly reusing its
    parent's id, or a half-moved archive copy left in both `Backlog/` and
    `Backlog/Archive/`) is refused HERE, at scan time, naming both paths and
    the id -- never allowed to reach rendering. Left unrefused, the
    duplicate would render two rows for one id: `--write` would ship both
    silently, and `--check`'s later duplicate-row quarantine
    would remove the id from its own fresh-render comparison entirely,
    surfacing as a `KeyError` rather than a reported anomaly. Refusing before any row renders is the
    same
    "never fabricate, never half-ship" discipline every other GeneratorError
    in this scanner already applies to a missing key or a dangling `blocks:`
    entry.

    `overrides` maps a resolved item-file path to text not yet on disk, so
    a caller can plan a backfill in memory and scan the planned result. An
    unmatched key is silently unused.
    """
    overrides = overrides or {}
    errors = []
    items = []
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        try:
            items.append(_scan_one_file(path, overrides.get(path.resolve())))
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


# A search over a cycle-rich graph can run long, so both limits bound it. A clean backlog
# has no cycle, and the search then ends after one pass over the graph.
CYCLE_REPORT_LIMIT = 50
CYCLE_STEP_BUDGET = 200_000


def _strongly_connected(blocks_index: dict) -> list:
    """Return each strongly connected component of the `blocks:` graph that holds
    three or more ids, as a sorted id list. Iterative Tarjan, so a long chain of
    items cannot hit the recursion limit."""
    index_of: dict = {}
    low: dict = {}
    on_stack: set = set()
    stack: list = []
    components: list = []
    counter = 0
    for root in sorted(blocks_index):
        if root in index_of:
            continue
        work = [(root, iter(sorted(blocks_index.get(root, ()))))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in blocks_index:
                    continue
                if child not in index_of:
                    index_of[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(blocks_index.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index_of[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                members = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    members.append(member)
                    if member == node:
                        break
                if len(members) >= 3:
                    components.append(sorted(members))
    return components


def detect_blocks_cycles(blocks_index: dict) -> list:
    """Return each cycle of three or more ids in the `blocks:` graph, as an id list.

    `detect_reciprocal_edges` reports the two-id case, so this reports only the
    longer ones: A blocks B, B blocks C and C blocks A makes all three wait on
    one another forever. A cycle is listed once, starting at its smallest id, in
    the order its edges run. At most `CYCLE_REPORT_LIMIT` cycles come back, and
    the search stops after `CYCLE_STEP_BUDGET` steps, so a tangled graph cannot
    stall the run. Like the reciprocal check, it only detects and names.
    """
    cycles: list = []
    steps = 0
    for members in _strongly_connected(blocks_index):
        member_set = set(members)
        for start in members:
            # Only ids at or above `start` may join the path, so each cycle is found from its smallest id.
            path = [start]
            frames = [iter(sorted(t for t in blocks_index.get(start, ()) if t in member_set and t >= start))]
            on_path = {start}
            while frames:
                steps += 1
                if steps > CYCLE_STEP_BUDGET or len(cycles) >= CYCLE_REPORT_LIMIT:
                    return cycles
                try:
                    target = next(frames[-1])
                except StopIteration:
                    frames.pop()
                    on_path.discard(path.pop())
                    continue
                if target == start:
                    if len(path) >= 3:
                        cycles.append(list(path))
                    continue
                if target in on_path:
                    continue
                path.append(target)
                on_path.add(target)
                frames.append(iter(sorted(t for t in blocks_index.get(target, ()) if t in member_set and t >= start)))
    return cycles


# --------------------------------------------------------------------------
# Direction check: prose that says "waits on N" against the item's own blocks:
# --------------------------------------------------------------------------

# `B waits for A` is written as `blocks: [B]` in A's file. An item whose prose says it waits on N, and
# whose own `blocks:` lists N, has the edge written backwards. The phrase list is the one the authoring
# rule names. The window stops at a full stop or a line end, so a later sentence cannot lend its id.
_WAIT_PHRASE_RE = re.compile(
    r"\b(?:blocked by|depends on|lands after|waits for)\b[^.\n]{0,80}?\bBB-(\d+)((?:\s*(?:,|and|&|/)\s*BB-\d+)*)",
    re.IGNORECASE,
)
_WAIT_TAIL_ID_RE = re.compile(r"BB-(\d+)")
_WAIT_SECTIONS = frozenset({"Summary", "Problem", "Resolution", "Dependencies", "Related"})
_SECTION_HEADING_RE = re.compile(r"^##[ \t]+(.*?)[ \t]*$")


def extract_waiting_ids(body: str) -> list:
    """Return the ids an item body names after a waiting phrase, in 3-digit form.

    Reads only the sections in `_WAIT_SECTIONS`. A quoted line, a fenced block and an `**Evidence:**`
    paragraph are skipped, so user text and recorded evidence cannot raise the anomaly.
    """
    ids: list = []
    section = None
    in_fence = False
    in_evidence = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _SECTION_HEADING_RE.match(line)
        if heading:
            section = heading.group(1)
            in_evidence = False
            continue
        if section not in _WAIT_SECTIONS:
            continue
        if not stripped:
            in_evidence = False
            continue
        if stripped.startswith("**Evidence"):
            in_evidence = True
        if in_evidence or stripped.startswith(">"):
            continue
        for match in _WAIT_PHRASE_RE.finditer(line):
            found = [match.group(1)] + _WAIT_TAIL_ID_RE.findall(match.group(2))
            ids.extend(digits.zfill(3) for digits in found)
    return ids


def detect_inverted_edges(items: list) -> tuple:
    """Return `(edges, scanned)`: each `(item_id, target_id)` where the item's prose waits on
    `target_id` and its own `blocks:` lists `target_id`, and the number of item bodies read.

    Prose can be stale, so this only reports. The user decides which side is right, as with a
    reciprocal pair. An item file that cannot be read is not counted as scanned.
    """
    edges = []
    scanned = 0
    for item in items:
        try:
            content = Path(item["_path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts = split_frontmatter_block(content)
        if parts is None:
            continue
        scanned += 1
        own_blocks = set(item["blocks"])
        for waited in dict.fromkeys(extract_waiting_ids(parts[1])):
            if waited != item["id"] and waited in own_blocks:
                edges.append((item["id"], waited))
    return edges, scanned

