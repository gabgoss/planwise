"""Lessons index generator — companion shape parse, drift check, and integrity scan."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lessons_index_companion import (
    _COMPANION_ANY_HEADING_RE,
    _COMPANION_GENERATED_RE,
    _COMPANION_HEADING_RE,
    _COMPANION_ID_CELL_RE,
    _COMPANION_LEGACY_HEADING_RE,
    _COMPANION_LEGACY_LAST_UPDATED_RE,
    _COMPANION_TO_RE,
    _FENCE_RE,
    COMPANION_FILENAME,
    _ordered_buckets,
    _render_companion_row,
    classify_lesson,
)
from markdown_parser import split_row_cells
from parse_lessons import format_id
from reconcile_common import read_text_preserving_newlines


def _companion_line_ending(companion_path: Path) -> str:
    """Mirrors `detect_line_ending`'s CRLF-wins-on-a-tie convention
    detection, applied to the one companion file directly -- there is no
    shard family to walk for a single non-hub artifact."""
    if not companion_path.exists():
        return "\n"
    content = read_text_preserving_newlines(companion_path)
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    return "\r\n" if crlf_count >= lf_count else "\n"


def is_legacy_companion(content: str) -> bool:
    """True when `content` carries the hand-written shape the companion
    is being cut over from: a `**Last Updated:**` line, or the
    `## Cross-cutting observations` heading. A consumer migration path
    reuses this class name -- do not rename it.
    """
    return bool(_COMPANION_LEGACY_LAST_UPDATED_RE.search(content)) or bool(
        _COMPANION_LEGACY_HEADING_RE.search(content)
    )


def _parse_companion_shape(content: str) -> tuple:
    """Walk `content` once into (headings, rows). `headings` is one entry
    per `## `/`### ` bucket/sub-bucket heading, in document order, even a
    zero-row table (`declared_count` vs `actual`, for `stale-count`).
    `rows` is every data row, tagged with the heading it fell under and
    that heading's bucket/sub-bucket id token (`table_id`), walked in
    document order -- never keyed by id, which is what lets a repeated id
    surface as `duplicate-row` instead of silently overwriting itself.
    """
    headings = []
    rows = []
    current = None
    for raw_line in content.split("\n"):
        line = raw_line.rstrip("\r")
        heading_match = _COMPANION_HEADING_RE.match(line)
        if heading_match:
            current = {
                "heading_text": line.strip(),
                "table_id": heading_match.group(2),
                "declared_count": int(heading_match.group(3)),
                "actual": 0,
            }
            headings.append(current)
            continue
        if not line.startswith("|"):
            continue
        cells = split_row_cells(line)
        if not cells:
            continue
        id_match = _COMPANION_ID_CELL_RE.match(cells[0].strip())
        if not id_match:
            continue
        if current is not None:
            current["actual"] += 1
        rows.append({
            "id": int(id_match.group(1)),
            "bold": cells[0].strip().startswith("**"),
            "cells": cells,
            "table_id": current["table_id"] if current else None,
            "heading_text": current["heading_text"] if current else None,
        })
    return headings, rows


def _fresh_companion_rows(items: list, cat: dict) -> dict:
    """{id: {"table_id", "bold", "cells"}} for the fresh classification.
    `cells` is the fresh row rendered and then read back through
    `split_row_cells` -- the same parser the disk row went through -- so
    the row classifier always compares like with like (an escaped `|` in a
    title, a Module cell, a column count)."""
    fresh = {}
    for item in items:
        bucket, sub = classify_lesson(item, cat)
        code_bucket = bool(bucket.get("code_bucket"))
        cells = split_row_cells(_render_companion_row(item, code_bucket))
        fresh[item["id"]] = {
            "table_id": str(sub["id"] if sub is not None else bucket["id"]),
            "bold": cells[0].startswith("**"),
            "cells": cells,
        }
    return fresh


def _mask_generated(content: str) -> str:
    return _COMPANION_GENERATED_RE.sub("Generated: <date>", content, count=1)


def _first_difference(disk_content: str, fresh_content: str):
    """(1-based line number, disk line, fresh line) of the first line
    where the two differ. A missing line reads as ''."""
    disk_lines = disk_content.split("\n")
    fresh_lines = fresh_content.split("\n")
    for index in range(max(len(disk_lines), len(fresh_lines))):
        disk_line = disk_lines[index] if index < len(disk_lines) else ""
        fresh_line = fresh_lines[index] if index < len(fresh_lines) else ""
        if disk_line != fresh_line:
            return index + 1, disk_line, fresh_line
    return None


def _clip(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def is_generated_companion(content: str) -> bool:
    """True when `content`'s header -- everything above its first `---`
    rule -- carries both the `Generated:` line and the `**Companion to:**`
    line this module renders. Only a generated-shaped file may be
    overwritten by `--companion --write` without `--replace-legacy`."""
    header = content.split("\n---\n", 1)[0]
    return bool(_COMPANION_GENERATED_RE.search(header)) and bool(_COMPANION_TO_RE.search(header))


def _companion_headings_to_drop(disk_content: str, fresh_ids: set) -> list:
    """Every `## `/`### ` heading in `disk_content` that is not a bucket or
    sub-bucket heading of the fresh render -- what `--replace-legacy`
    discards, named so the operator sees it. Lines inside a ``` or ~~~
    fence are skipped: a fenced `## ` line is sample text, not a section.
    """
    dropped = []
    in_fence = False
    for raw_line in disk_content.split("\n"):
        line = raw_line.rstrip("\r")
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not _COMPANION_ANY_HEADING_RE.match(line):
            continue
        heading_match = _COMPANION_HEADING_RE.match(line)
        if heading_match and heading_match.group(2) in fresh_ids:
            continue
        dropped.append(line.strip())
    return dropped


def _companion_table_ids(cat: dict) -> set:
    ids = set()
    for bucket in _ordered_buckets(cat):
        ids.add(str(bucket["id"]))
        for sub in bucket.get("sub_buckets") or []:
            if isinstance(sub, dict):
                ids.add(str(sub["id"]))
    return ids


def _scan_integrity_findings(result) -> list:
    """`duplicate-id` / `id-mismatch` findings for two lesson FILES that
    claim one id, or a filename that disagrees with its frontmatter id.
    Shared by the index and companion `--write` refusals and the companion
    `--check` report."""
    findings = []
    for lesson_id, paths in result.duplicate_ids.items():
        findings.append({
            "class": "duplicate-id", "id": format_id(lesson_id),
            "detail": f"claimed by {', '.join(str(p) for p in paths)}",
        })
    for mismatch in result.id_mismatches:
        findings.append({
            "class": "id-mismatch", "id": str(mismatch["path"]),
            "detail": (
                f"filename says {format_id(mismatch['filename_id'])}, "
                f"frontmatter says {format_id(mismatch['frontmatter_id'])}"
            ),
        })
    return findings


def _check_companion_drift(items: list, disk_content: str, cat: dict, fresh_content: str) -> list:
    """Compare the on-disk companion (already `\\r\\n`-normalised by the
    caller) against `fresh_content`, the companion this run renders.

    The gate is the whole file: with the `Generated:` line masked on both
    sides, equal content is no drift. Only on a mismatch does the row
    classifier run, to name what differs in the six row-level classes:
    `missing-row`, `stale-row`, `orphan-row`, `stale-count`,
    `duplicate-row`, `legacy-shape`. A mismatch that no row-level class
    explains -- a heading, description, scope, column schema, bucket set,
    or footer change -- is one `stale-shape` finding naming the first
    differing line.

    A legacy-shaped file is not meaningfully comparable row-by-row --
    `legacy-shape` plus a `missing-row` per known lesson is the expected
    pre-cutover reading, mirroring `_check_lessons_drift`'s own legacy
    branch.
    """
    findings = []
    if is_legacy_companion(disk_content):
        findings.append({
            "class": "legacy-shape", "id": COMPANION_FILENAME,
            "detail": "companion carries a **Last Updated:** line or a "
            "## Cross-cutting observations heading",
        })
        for item in items:
            findings.append({
                "class": "missing-row", "id": format_id(item["id"]),
                "detail": "no on-disk generated row (companion is not generated-shaped)",
            })
        return findings

    masked_disk = _mask_generated(disk_content)
    masked_fresh = _mask_generated(fresh_content)
    if masked_disk == masked_fresh:
        return findings

    headings, rows = _parse_companion_shape(disk_content)
    fresh_by_id = _fresh_companion_rows(items, cat)

    seen_ids = set()
    for row in rows:
        rid = row["id"]
        if rid in seen_ids:
            findings.append({
                "class": "duplicate-row", "id": format_id(rid),
                "detail": f"appears more than once (also under {row['heading_text']})",
            })
            continue
        seen_ids.add(rid)
        fresh = fresh_by_id.get(rid)
        if fresh is None:
            findings.append({
                "class": "orphan-row", "id": format_id(rid),
                "detail": f"row under {row['heading_text']} has no lesson file",
            })
            continue
        reasons = []
        if row["table_id"] != fresh["table_id"]:
            reasons.append("table")
        if row["bold"] != fresh["bold"]:
            reasons.append("bold/status")
        disk_cells, fresh_cells = row["cells"], fresh["cells"]
        if len(disk_cells) != len(fresh_cells):
            reasons.append(
                f"malformed ({len(disk_cells)} cell(s), expected {len(fresh_cells)})"
            )
        else:
            if disk_cells[1] != fresh_cells[1]:
                reasons.append("Title")
            if len(fresh_cells) == 4 and disk_cells[2] != fresh_cells[2]:
                reasons.append("Module")
            if disk_cells[-1] != fresh_cells[-1]:
                reasons.append("Severity")
        if reasons:
            findings.append({
                "class": "stale-row", "id": format_id(rid),
                "detail": f"{', '.join(reasons)} differ(s) from frontmatter",
            })

    for item in items:
        if item["id"] not in seen_ids:
            findings.append({
                "class": "missing-row", "id": format_id(item["id"]),
                "detail": "no on-disk row",
            })

    for heading in headings:
        if heading["declared_count"] != heading["actual"]:
            findings.append({
                "class": "stale-count", "id": heading["heading_text"],
                "detail": f"declared ({heading['declared_count']}) != "
                f"actual rows ({heading['actual']})",
            })

    if not findings:
        difference = _first_difference(masked_disk, masked_fresh)
        line_no, disk_line, fresh_line = difference if difference else (0, "", "")
        findings.append({
            "class": "stale-shape", "id": f"line {line_no}",
            "detail": f"on disk {_clip(disk_line)!r}, generated {_clip(fresh_line)!r} "
            "(a heading, description, scope, column schema, Module cell, bucket "
            "set, or footer differs from the render)",
        })

    return findings
