#!/usr/bin/env python3
"""Sync a backlog item's status into its own file, under generation.

The backlog index is a build artifact that `generate_backlog_index.py
--write` produces from every item file's frontmatter, so this script never
reads it to locate an item, and never writes to it. `--status` finds the
item's file(s) on disk by frontmatter `id:` (`backlog_dir`, then
`archive_dir` -- a closed item's file lives only in the latter, and the hub
never carries its row), syncs the YAML `status:` field, and moves the file
into `Archive/` for COMPLETE/CLOSED or back out of `Archive/` for any other
status. A failed sync leaves the file exactly where it was -- frontmatter
is the only record of status, so a failed write is a failed command, never
silently followed by a move. `--create` writes a brand-new item's BLI file
from the backlog-item template (unless the file already exists) and prints
the regenerate command; it never writes an index row itself, and its
duplicate-id guard checks both the generated index files (hub, overflow
leaves, Archive shards) and every on-disk item file's own id, since a
freshly created or not-yet-regenerated file has no row in the former.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# Fix Windows cp1252 stdout/stderr encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Import shared config loader
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from constants import ARCHIVE_STATUSES, VALID_STATUSES
from generate_backlog_index import (
    GeneratorError,
    TITLE_MAX_LEN,
    _iter_item_files,
    _read_frontmatter_map,
    _strip_quotes,
)
from markdown_parser import infer_predominant_id_form, normalize_id, render_id
from parse_backlog import collect_all_known_ids
from reconcile_common import (
    read_text_preserving_newlines,
    write_text_preserving_newlines,
)

# Accepted values for the optional top-level `id_format` config key. An
# unrecognized value is announced on stderr and falls back to "bare" — see
# create_backlog_item. That fallback is deliberate and MUST NOT become fatal:
# the permissive behavior shipped first, and existing configs may carry the
# key.
VALID_ID_FORMATS = ("prefixed", "bare")


def archive_item_files(
    backlog_dir: Path, archive_dir: Path, filenames: list[str]
) -> list[tuple[str, bool, str]]:
    """Move item files from backlog_dir to archive_dir.

    Refuses to overwrite: a destination that already exists is reported as
    a failure and left alone, never silently replaced by `shutil.move` (on
    Windows, a same-name destination made `shutil.move` fall back to its
    copy+unlink path, which overwrites the destination with no warning).

    Returns list of (filename, success, message) tuples.
    """
    archive_dir.mkdir(exist_ok=True, parents=True)

    results = []
    for filename in filenames:
        src = backlog_dir / filename
        dst = archive_dir / filename
        if not src.exists():
            if dst.exists():
                results.append((filename, True, "already in Archive"))
            else:
                results.append((filename, False, "file not found"))
            continue
        if dst.exists():
            results.append(
                (filename, False, "refused -- destination already exists in Archive")
            )
            continue
        try:
            shutil.move(str(src), str(dst))
            results.append((filename, True, "moved to Archive"))
        except OSError as e:
            results.append((filename, False, str(e)))

    return results


def restore_item_files(
    backlog_dir: Path, archive_dir: Path, filenames: list[str]
) -> list[tuple[str, bool, str]]:
    """Move item files from archive_dir back to backlog_dir (reopening).

    The mirror of archive_item_files, with the same overwrite refusal, for
    a `--status` transition that sets an open status on a file currently
    sitting in `Archive/` -- the closed <=> `Archive/` invariant
    `reconcile_backlog.py` audits holds in either direction.

    Returns list of (filename, success, message) tuples.
    """
    backlog_dir.mkdir(exist_ok=True, parents=True)

    results = []
    for filename in filenames:
        src = archive_dir / filename
        dst = backlog_dir / filename
        if not src.exists():
            if dst.exists():
                results.append((filename, True, "already in Backlog"))
            else:
                results.append((filename, False, "file not found"))
            continue
        if dst.exists():
            results.append(
                (filename, False, "refused -- destination already exists in Backlog")
            )
            continue
        try:
            shutil.move(str(src), str(dst))
            results.append((filename, True, "moved to Backlog"))
        except OSError as e:
            results.append((filename, False, str(e)))

    return results


def _reconcile_archive_state(
    backlog_dir: Path, archive_dir: Path, paths: list[Path], new_status: str
) -> list[tuple[str, bool, str]]:
    """Move each of paths into or out of Archive/ to match new_status.

    COMPLETE/CLOSED archives a stranded file (idempotent -- an
    already-archived file reports "already in Archive" and nothing
    changes). Any other status reopens a file still sitting in Archive/,
    since the invariant this module and reconcile_backlog.py both hold is
    closed <=> Archive/. Both directions refuse to overwrite an existing
    destination.

    Returns the per-file (filename, success, message) results so the
    caller can fail the command when a move did not succeed -- printing
    the outcome and silently continuing is what let a failed move go
    unnoticed.
    """
    filenames = [path.name for path in paths]
    mover = archive_item_files if new_status in ARCHIVE_STATUSES else restore_item_files
    results = mover(backlog_dir, archive_dir, filenames)
    for filename, success, message in results:
        prefix = "  +" if success else "  !"
        print(f"{prefix} {filename}: {message}")
    return results


def _blocked_moves(
    backlog_dir: Path, archive_dir: Path, paths: list[Path], new_status: str
) -> list[str]:
    """Names of paths whose required archive/reopen move would collide with
    an existing file at the destination.

    Checked BEFORE any frontmatter write, so a refused move never leaves a
    synced-but-stranded file behind -- an open item whose frontmatter says
    COMPLETE but which never reached Archive/, or a closed item whose
    frontmatter was reopened but which never left Archive/. A path already
    sitting in the correct location needs no move and is never blocked.
    """
    archiving = new_status in ARCHIVE_STATUSES
    blocked = []
    for path in paths:
        if archiving and path.parent != archive_dir:
            if (archive_dir / path.name).exists():
                blocked.append(path.name)
        elif not archiving and path.parent == archive_dir:
            if (backlog_dir / path.name).exists():
                blocked.append(path.name)
    return blocked


class SyncStatusResult(NamedTuple):
    """Outcome of one sync_yaml_status attempt.

    `outcome` is one of:
      - "changed": the frontmatter status line was found and rewritten.
      - "absent_file": item_file_path does not exist.
      - "no_frontmatter": the file does not open with a "---" fence, or
        the fence is never closed.
      - "no_status_key": the frontmatter has no "^status:\\s" line to
        rewrite.
    Every outcome other than "changed" means the file was left
    byte-unchanged. The caller MUST surface it -- collapsing all four
    outcomes into a bare True/False is what let a silent no-op read as
    success.
    """

    outcome: str
    path: Path


# Opening fence: "---" as its own line, right at the start of the content
# (after any BOM has been stripped). Closing fence: "---" as its own line
# anywhere after that -- found by requiring a newline (or the fence being
# the very first thing) before it and a newline-or-end-of-file after it, so
# a value like `title: "A --- B"` can never masquerade as the fence a bare
# substring search would have matched first.
_OPEN_FENCE_RE = re.compile(r"\A---[ \t]*(\r\n|\n)")
_CLOSE_FENCE_RE = re.compile(r"(\r\n|\n)---[ \t]*(\r\n|\n|\Z)")


def sync_yaml_status(item_file_path: Path, new_status: str) -> SyncStatusResult:
    """Update the status field in the item file's YAML frontmatter.

    BOM-tolerant (the same tolerance `_find_items_by_id` gets for free from
    `_read_frontmatter_map`) -- a leading BOM is stripped before the fence
    check and restored verbatim on write, so a BOM'd file that this
    module's own disk lookups can find is not then rejected here as
    "no_frontmatter". The closing fence is matched as a `---` LINE, never a
    bare substring search, so a frontmatter value carrying literal `---`
    text of its own cannot truncate the block early.

    Returns a SyncStatusResult naming what happened rather than a bare
    bool, so a caller can tell "nothing needed changing" apart from
    "the file was not touched because something is wrong with it".
    """
    if not item_file_path.exists():
        return SyncStatusResult("absent_file", item_file_path)

    raw = read_text_preserving_newlines(item_file_path)
    bom = "﻿" if raw.startswith("﻿") else ""
    content = raw[len(bom) :]

    open_match = _OPEN_FENCE_RE.match(content)
    if not open_match:
        return SyncStatusResult("no_frontmatter", item_file_path)

    close_match = _CLOSE_FENCE_RE.search(content, open_match.end())
    if close_match is None:
        return SyncStatusResult("no_frontmatter", item_file_path)

    frontmatter = content[open_match.end() : close_match.start()]
    if not re.search(r"^status:\s", frontmatter, re.MULTILINE):
        return SyncStatusResult("no_status_key", item_file_path)

    # [^\r\n]*, not .*$ -- `.` matches \r, so a `.*$` replacement on a CRLF
    # frontmatter silently ate the line's trailing \r along with the old
    # value, downgrading that one line from CRLF to LF.
    #
    # [ \t]*, not \s* -- `\s` matches a newline too, so on an EMPTY status
    # value (`status: \n` or `status:\n`) `\s*` kept consuming through the
    # line break and into the next key's own leading whitespace, and
    # `[^\r\n]*` then swallowed that whole next line into the match --
    # deleting it. `[ \t]*` cannot cross the line break, so it stops at the
    # value (empty or not) and never touches the next key.
    updated_fm = re.sub(
        r"^status:[ \t]*[^\r\n]*",
        f"status: {new_status}",
        frontmatter,
        count=1,
        flags=re.MULTILINE,
    )
    new_content = (
        bom + content[: open_match.end()] + updated_fm + content[close_match.start() :]
    )
    write_text_preserving_newlines(item_file_path, new_content)
    return SyncStatusResult("changed", item_file_path)


def _frontmatter_id(fm_map: dict) -> str | None:
    """Return a file's frontmatter id, normalized the same prefix-aware way
    the index itself compares ids (`normalize_id`).

    Deliberately NOT the generator's own `_normalize_id_text`: that helper
    raises on anything but a pure-digit value, which would silently drop a
    file carrying a prefixed id (e.g. "PFX-005") from every disk-lookup
    result -- exactly the id form `--create` itself can produce when
    `id_format` infers "prefixed" from an existing hand-authored index.
    `normalize_id` recognizes bare and prefixed forms alike and never
    raises. Returns None only when the file has no id value at all.
    """
    raw = fm_map.get("id")
    if raw is None:
        return None
    normalized = normalize_id(_strip_quotes(str(raw).strip()))
    return normalized or None


def _scan_item_frontmatter(backlog_dir: Path, archive_dir: Path, index_path: Path):
    """Yield (path, fm_map) for every on-disk item file whose frontmatter
    can be read.

    The one scan loop `_find_items_by_id` and `_known_ids_from_disk` both
    build on, so the two can never drift on which files are skipped or how
    frontmatter is parsed -- they repeated this loop verbatim before.
    """
    for path in _iter_item_files(backlog_dir, archive_dir, index_path):
        try:
            fm_map = _read_frontmatter_map(path)
        except (GeneratorError, OSError, UnicodeDecodeError):
            continue
        yield path, fm_map


def _find_items_by_id(
    backlog_dir: Path, archive_dir: Path, index_path: Path, item_id: str
) -> list[tuple[Path, str]]:
    """Locate every on-disk item file whose frontmatter id matches item_id.

    Scans backlog_dir before archive_dir (`_iter_item_files`'s own scan
    order), so a closed item (Archive/-only, with no hub row) and an item
    not yet folded into any generated index file are both reachable -- the
    hub is never read. Returns (path, status) pairs; a file whose
    frontmatter can't be read is skipped rather than guessed at.
    """
    target = normalize_id(item_id)
    matches: list[tuple[Path, str]] = []
    for path, fm_map in _scan_item_frontmatter(backlog_dir, archive_dir, index_path):
        file_id = _frontmatter_id(fm_map)
        if file_id is None or file_id != target:
            continue
        status = _strip_quotes(fm_map.get("status", "").strip())
        matches.append((path, status))
    return matches


def _known_ids_from_disk(
    backlog_dir: Path, archive_dir: Path, index_path: Path
) -> dict[str, str]:
    """Map every id an on-disk item file's OWN frontmatter carries to that
    file's path.

    This is the union `--create`'s duplicate guard needs beyond
    `collect_all_known_ids`: a freshly created or freshly renamed item file
    has no row in the hub, an overflow leaf, or an Archive shard until the
    next `--write`. Scans with the generator's own item-file iterator, so an
    item already sitting in `Archive/` is visible too. A file whose
    frontmatter cannot be read is skipped, never guessed at -- collision
    detection is not the place to validate an unrelated file's frontmatter.
    """
    locations: dict[str, str] = {}
    for path, fm_map in _scan_item_frontmatter(backlog_dir, archive_dir, index_path):
        file_id = _frontmatter_id(fm_map)
        if file_id is None:
            continue
        locations.setdefault(file_id, str(path))
    return locations


def _escape_title(feature: str) -> str:
    """Escape a title for embedding in a double-quoted YAML frontmatter value.

    Backslashes first, so an already-escaped quote is never re-escaped. The
    generator's `_strip_quotes` reads this text back unmodified past the
    outer quote pair -- it never unescapes an inner `\\"` or `\\\\` -- so
    this literal escaped string IS the length the generator measures and
    truncates against.
    """
    return feature.replace("\\", "\\\\").replace('"', '\\"')


def _render_bli_file(
    item_id: str,
    feature: str,
    priority: str,
    status: str,
    abbrev: str,
    files_list: list[str],
) -> str:
    """Render a new BLI file body from the backlog-item template structure.

    The heading stays `# {stem}: {feature}` rather than the template's
    `# BB-{ID}-{Domain}: {Title}` form -- an accepted divergence, since the
    stem already carries the ID and domain.
    """
    stem = files_list[0].removesuffix(".md")
    today = datetime.now().astimezone().date().isoformat()
    title = _escape_title(feature)
    # Link form, matching the template's `[name](file.md) - relationship`
    # shape -- not a backticked bare filename.
    related = "\n".join(f"- [{f}]({f}) - file for this item" for f in files_list)
    return (
        "---\n"
        f"id: {item_id}\n"
        f'title: "{title}"\n'
        f"priority: {priority}\n"
        f"status: {status}\n"
        f"abbrev: {abbrev}\n"
        f"created: {today}\n"
        "blocks: []\n"
        "---\n"
        "\n"
        f"# {stem}: {feature}\n"
        "\n"
        f"**Priority:** {priority}\n"
        f"**Domain:** {abbrev}\n"
        "\n"
        "---\n"
        "\n"
        "## Summary\n"
        "\n"
        f"{feature}\n"
        "\n"
        "## Problem\n"
        "\n"
        f"{feature}\n"
        "\n"
        "## Proposed Solution\n"
        "\n"
        "{Describe the approach.}\n"
        "\n"
        "## Acceptance Criteria\n"
        "\n"
        f"- [ ] {feature}\n"
        "\n"
        "## Related\n"
        "\n"
        f"{related}\n"
        "\n"
        "---\n"
        "\n"
        f"*Created: {today}*\n"
    )


def create_backlog_item(args) -> None:
    """Create a new backlog item: write its BLI file (if absent) and nothing else.

    The index is a build artifact that generate_backlog_index.py --write
    produces from every item file's frontmatter, so --create never appends a
    row to it -- only the item file is written. On success it prints the
    regenerate command, so a hand-run user is told the index is now stale.

    In create mode --status is optional and defaults to NOT_STARTED (the open/not-started
    state) — "Open" is not a member of VALID_STATUSES, and the backlog-item template and
    backlog handler both stamp new items NOT_STARTED, so the file and a regenerated index
    row agree.
    """
    missing = [
        name
        for name, val in (
            ("--id", args.id),
            ("--feature", args.feature),
            ("--priority", args.priority),
            ("--abbrev", args.abbrev),
            ("--files", args.files),
        )
        if not val
    ]
    if missing:
        print(
            f"Error: --create requires {', '.join(missing)}.",
            file=sys.stderr,
        )
        sys.exit(1)

    status = (args.status or "NOT_STARTED").upper()
    if status not in VALID_STATUSES:
        print(
            f"Error: Invalid status '{args.status}'. "
            f"Valid values: {', '.join(sorted(VALID_STATUSES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    feature = args.feature.strip()
    # The funnel for the title cap: measured on the frontmatter-ESCAPED
    # form, matching what the generator's `_strip_quotes` reads back on
    # regeneration -- it strips only the enclosing quote pair and never
    # unescapes an inner `\"` or `\\`, so the escaped string IS the length
    # the generator measures and truncates against. Checking the raw
    # feature length here would let a quote- or backslash-heavy title pass
    # this rejection and still get silently truncated on the next
    # `--write` -- exactly the "never silently truncated" invariant this
    # rejection exists to hold. TITLE_MAX_LEN is the one constant, defined
    # in generate_backlog_index.py and imported here, so the writer's
    # rejection and the generator's own truncation can never drift to two
    # different numbers.
    title = _escape_title(feature)
    if len(title) > TITLE_MAX_LEN:
        print(
            f"Error: --feature escapes to {len(title)} characters "
            f"({len(feature)} raw) in frontmatter, exceeding the "
            f"{TITLE_MAX_LEN}-character cap the generator renders against. "
            f"Shorten it, or remove the quote/backslash characters that "
            f"grow it under escaping -- the narrative belongs in the "
            f"item's body (## Summary, ## Problem), never in the title.",
            file=sys.stderr,
        )
        sys.exit(1)

    priority = args.priority
    abbrev = args.abbrev.strip()
    files_list = [f.strip() for f in args.files.split(";") if f.strip()]
    if not files_list:
        print("Error: --files must name at least one file.", file=sys.stderr)
        sys.exit(1)

    config = load_config(Path(__file__))
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    # Read-only: the index is consulted for its predominant stored ID form,
    # never written back to.
    content = read_text_preserving_newlines(index_path)

    # Stored ID form: an explicit id_format config key wins; otherwise infer
    # the index's own predominant existing form (bare on an empty index). A
    # bare config.get() is enough here -- id_format is a plain optional
    # string, and the one check it needs (an unrecognized value) is announced
    # in place below, so a config_loader accessor would add a layer with
    # nothing to do.
    id_format = config.get("id_format")  # "prefixed" | "bare" | None
    prefix = ""
    if id_format is None:
        id_format, prefix = infer_predominant_id_form(content)  # "bare" on an empty index
    elif id_format == "prefixed":
        _, prefix = infer_predominant_id_form(content)
    elif id_format not in VALID_ID_FORMATS:
        # Announce, then continue with the existing permissive fallback --
        # NOT fatal, no non-zero exit. Same stderr convention as
        # score_backlog.py's computed-vs-written shortfall warning, which the
        # backlog handler already requires be surfaced verbatim rather than
        # swallowed.
        print(
            f"WARNING: unrecognized id_format '{id_format}' in config. "
            f"Accepted values: {', '.join(sorted(VALID_ID_FORMATS))}. "
            f"Falling back to 'bare' -- the new row's ID renders in the "
            f"legacy bare form.",
            file=sys.stderr,
        )
        id_format = "bare"
    item_id = render_id(args.id, id_format, prefix=prefix)

    # The generator's own frontmatter reader (`_normalize_id_text`, used by
    # `_extract_fields`/`scan_backlog`) requires a pure-digit id and raises
    # `GeneratorError("non-numeric id value ...")` on anything else --
    # proven empirically against the live generator (`--check` on a
    # `--create`d item under `id_format: prefixed` exits non-zero with
    # exactly that error). So regardless of id_format, the file's real,
    # generator-readable identity is always the bare form. Render THAT into
    # frontmatter, the collision key, and every message, rather than a
    # `--create`-only prefixed label the generator can never read back and
    # `--check`/`--write` would then fail on.
    item_id = render_id(item_id, "bare")

    # The duplicate-id guard reads from disk, not the hub alone: an id can
    # be "known" via a generated index file (hub, overflow leaf, Archive
    # shard) or via an on-disk item file's own frontmatter that hasn't been
    # folded into any of those yet.
    bli_path = backlog_dir / files_list[0]
    key = normalize_id(item_id)
    existing_location = _known_ids_from_disk(backlog_dir, archive_dir, index_path).get(key)
    if existing_location is not None and Path(existing_location) == bli_path:
        # The only known holder of this id IS the --files target itself --
        # a re-run against the same file, not a collision with a DIFFERENT
        # one. The existing-file verification below decides whether that
        # file may actually be reused.
        existing_location = None
    if existing_location is None:
        known_from_index = {normalize_id(i) for i in collect_all_known_ids(config)}
        if key in known_from_index:
            existing_location = (
                "the backlog index -- the hub, a hub overflow leaf, or an "
                "Archive shard"
            )
    if existing_location:
        print(
            f"Error: Item ID '{item_id}' already exists ({existing_location}).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Write the BLI file from the template — never clobber a richer file the
    # handler may have already created in its Phase 7.3 flow. But an
    # existing file is only "richer", not someone else's: verify its OWN
    # frontmatter id actually matches before claiming it, so a stale or
    # mistyped --files argument can never silently misattribute another
    # item's file to this one.
    if bli_path.exists():
        try:
            existing_fm = _read_frontmatter_map(bli_path)
        except (GeneratorError, OSError, UnicodeDecodeError) as e:
            print(
                f"Error: {bli_path.name} already exists and its frontmatter "
                f"could not be read ({e}) -- refusing to claim it for item "
                f"{item_id}. Nothing was written.",
                file=sys.stderr,
            )
            sys.exit(1)
        existing_id = _frontmatter_id(existing_fm)
        if existing_id != normalize_id(item_id):
            print(
                f"Error: {bli_path.name} already exists and carries id "
                f"{existing_fm.get('id', '?')!r}, not {item_id!r} -- "
                f"refusing to overwrite or misattribute it. Nothing was "
                f"written.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  BLI file already exists, carries id {item_id}: {bli_path.name}")
    else:
        bli_path.parent.mkdir(parents=True, exist_ok=True)
        bli_path.write_text(
            _render_bli_file(item_id, feature, priority, status, abbrev, files_list),
            encoding="utf-8",
        )
        print(f"  Created BLI file: {bli_path.name}")

    print(
        f"Created backlog item {item_id}: {feature} [{priority}/{status}/{abbrev}] "
        f"({bli_path.name}). Regenerate the index: generate_backlog_index.py --write"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Update a backlog item's status in the index markdown."
    )
    parser.add_argument("--id", required=True, help="Item ID (e.g., 003)")
    parser.add_argument(
        "--status",
        required=False,
        help=(
            f"New status. Valid: {', '.join(sorted(VALID_STATUSES))}. "
            "Required for a status update; in --create mode it is optional "
            "and defaults to NOT_STARTED."
        ),
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new backlog item (writes the item file only; regenerate the index with generate_backlog_index.py --write) instead of updating an existing item's status.",
    )
    parser.add_argument("--feature", help="Feature / recommendation summary (required when --create).")
    parser.add_argument(
        "--priority",
        choices=["High", "Medium", "Low"],
        help="Priority (required when --create).",
    )
    parser.add_argument("--abbrev", help="Domain abbreviation (required when --create).")
    parser.add_argument(
        "--files",
        help="Affected files, semicolon-separated; the first is the new BLI file written from the template (required when --create).",
    )

    args, _ = parser.parse_known_args()

    # --create takes a fully separate path: build a new item rather than update one.
    if args.create:
        create_backlog_item(args)
        return

    if not args.status:
        print(
            "Error: --status is required (unless --create is used).",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.status.upper() not in VALID_STATUSES:
        print(
            f"Error: Invalid status '{args.status}'. "
            f"Valid values: {', '.join(sorted(VALID_STATUSES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    new_status = args.status.upper()

    # Load config
    config = load_config(Path(__file__))
    index_path = config["_index_path"]
    backlog_dir = config["_backlog_dir"]
    archive_dir = config["_archive_dir"]

    if not index_path.exists():
        print(f"Error: Backlog index not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    # Disk-based lookup: the index is a build artifact generate_backlog_index.py
    # --write produces from every item file's frontmatter, so it is never read
    # here for the item's status or its file location -- a closed item's row
    # never even exists in the hub (it renders only into an Archive shard),
    # and a hub that hasn't been regenerated since the last edit is stale.
    matches = _find_items_by_id(backlog_dir, archive_dir, index_path, args.id)
    if not matches:
        print(
            f"Error: No item file found on disk for ID '{args.id}' under "
            f"{backlog_dir} or {archive_dir}.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(matches) > 1:
        # Duplicate ids are an anomaly reconcile_backlog.py also never acts
        # on (`detect_drift`'s "id also carried by ..." case) -- refuse
        # rather than non-atomically rewrite several files for one id. A
        # human decides which file is the real item.
        listed = ", ".join(str(path) for path, _ in matches)
        print(
            f"Error: {len(matches)} item files carry id '{args.id}' -- "
            f"refusing to update any of them: {listed}",
            file=sys.stderr,
        )
        sys.exit(1)

    path, old_status = matches[0]
    paths = [path]

    # Verify the move CAN succeed BEFORE writing anything. Checked ahead of
    # both branches below, so a refused move never leaves an open item
    # stranded in Archive/, a closed item stranded outside it, or synced
    # frontmatter describing a location the file never reached.
    blocked = _blocked_moves(backlog_dir, archive_dir, paths, new_status)
    if blocked:
        for filename in blocked:
            print(
                f"Error: {filename}'s destination already exists -- "
                f"refusing to move it, and refusing to write its "
                f"frontmatter for a move that cannot complete.",
                file=sys.stderr,
            )
        sys.exit(1)

    if old_status == new_status:
        print(f"Item {args.id} already has status {new_status}. No change.")
        # The status write is a true no-op, but archival is state-coupled, not
        # transition-coupled, in EITHER direction: an item whose file ALREADY
        # carries COMPLETE/CLOSED may still be stranded outside Archive/ (e.g.
        # a closeout that hand-edited the frontmatter without going through
        # this script), and an OPEN item's file may be stranded INSIDE
        # Archive/ the same way. Reconcile the location even on a no-op
        # status change so the invariant holds by state -- this is precisely
        # the reconciliation call an operator reaches for, and it used to hit
        # the early-return and no-op. The frontmatter is left untouched; only
        # the file location is healed.
        results = _reconcile_archive_state(backlog_dir, archive_dir, paths, new_status)
        failed_move = [r for r in results if not r[1]]
        if failed_move:
            for filename, _success, message in failed_move:
                print(f"Error: {filename} could not be moved: {message}", file=sys.stderr)
            sys.exit(1)
        return

    # Sync every matched file's frontmatter BEFORE reporting success or
    # touching the file's location. Frontmatter is now the only record of
    # status, so a failed sync is a failed command -- never archived, and
    # never reported as "Updated" first.
    sync_results = [(path, sync_yaml_status(path, new_status)) for path in paths]
    failed = [(path, result) for path, result in sync_results if result.outcome != "changed"]
    if failed:
        for path, result in failed:
            print(
                f"Error: YAML status NOT synced for {path.name} "
                f"({result.outcome}): {result.path}",
                file=sys.stderr,
            )
        sys.exit(1)

    print(
        f"Updated item {args.id} status: {old_status} → {new_status} "
        f"(frontmatter only -- the index is a generated artifact; "
        f"regenerate it with generate_backlog_index.py --write)"
    )
    for path in paths:
        print(f"  YAML status synced: {path.name}")

    move_results = _reconcile_archive_state(backlog_dir, archive_dir, paths, new_status)
    failed_move = [r for r in move_results if not r[1]]
    if failed_move:
        for filename, _success, message in failed_move:
            print(f"Error: {filename} could not be moved: {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
