"""Read-only review of transferred customizations left by earlier upgrades.

An upgrade moves a customization-bearing installed rule to
`{planwise_root}/upgrade-transfers/{from}-to-{to}/{filename}` before it adopts
the shipped body (`upgrade_io._transfer_customization`). Nothing re-reads that
file on a later upgrade, so a transfer whose content the plugin later shipped
sits on disk with no step that can say so.

This module closes that gap. It strips the provenance wrapper from each
transfer, compares the preserved body with the CURRENT shipped counterpart
through the same structural primitive the upgrade writer uses, and reports one
status per file. It never writes, moves, or deletes anything. The deletion
offer lives in the upgrade handler and needs a human confirm per file.
"""

import ast
import json
from pathlib import Path

try:
    from rule_divergence import (
        _classify_diverged,
        _destructively_removable,
        _verdict_not_analyzed,
        normalize_rule_for_diff,
    )
except ImportError:
    raise ImportError(
        "rule_divergence is required for transfer_review's structural-verdict "
        "classification; the scripts/ directory appears to be partially "
        "installed"
    )

# The wrapper `_transfer_customization` writes ahead of the preserved body:
# a frontmatter block, this heading, one boilerplate paragraph, then a `---`
# separator line. The preserved body may open with its own `---` frontmatter,
# which belongs to the body, so the split takes the FIRST separator after the
# heading and nothing later.
_HEADING_PREFIX = "# Transferred customization:"
_BODY_SEPARATOR = "\n\n---\n\n"

# One status per transfer file. Only `now-upstream` may be offered for
# deletion, and only after a per-file confirm.
STATUS_NOW_UPSTREAM = "now-upstream"
STATUS_STILL_UNIQUE = "still-unique"
STATUS_NO_COUNTERPART = "no-counterpart"
STATUS_NOT_A_TRANSFER = "not-a-transfer"
STATUS_UNREADABLE = "unreadable"


def split_transfer(text: str) -> "tuple[dict, str] | None":
    """Split a transfer file into (header fields, preserved body).

    Returns None when the text does not carry the wrapper shape, so a stray
    file in a pair folder is reported rather than mistaken for a transfer.
    The header values stay strings, except `unique_blocks`, which the writer
    stores as a Python list literal and this parses back into a list.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    header: dict = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            header[key.strip()] = value.strip()
    rest = text[end + len("\n---\n"):].lstrip("\n")
    if not rest.startswith(_HEADING_PREFIX):
        return None
    cut = rest.find(_BODY_SEPARATOR)
    if cut == -1:
        return None
    blocks = header.get("unique_blocks")
    if blocks is not None:
        try:
            parsed = ast.literal_eval(blocks)
        except (ValueError, SyntaxError):
            parsed = []
        header["unique_blocks"] = [str(b) for b in parsed] if isinstance(parsed, list) else []
    return header, rest[cut + len(_BODY_SEPARATOR):]


def _title_key(text: str) -> str:
    """Lowercase a heading or callout title with its markup stripped."""
    text = text.strip().lstrip("#>").strip()
    if text.startswith("[!"):
        end = text.find("]")
        if end != -1:
            text = text[end + 1:]
    return text.replace("`", "").strip().lower()


def _labels_in_shipped(labels: "list[str]", shipped_raw: str) -> "list[str]":
    """Return the labels that also appear as a heading or callout title in the
    shipped file.

    The structural verdict calls a block unique when its content is not
    contained in the shipped file. A block whose title still exists upstream
    was usually revised there, not dropped, so the human read should start
    from that diff. Matching is by title only and says nothing about content.
    """
    titles = [
        _title_key(line) for line in shipped_raw.splitlines()
        if line.lstrip().startswith(("#", ">"))
    ]
    return [
        label for label in labels
        if (key := _title_key(label)) and any(key in title for title in titles)
    ]


def _row(pair: str, path: Path, status: str, **extra) -> dict:
    row = {
        "pair": pair,
        "path": str(path),
        "filename": path.name,
        "status": status,
        "classification": "n/a",
        "confidence": "n/a",
        "unique_blocks": [],
        "unique_blocks_titled_in_shipped": [],
        "recorded_unique_blocks": [],
        "shipped": None,
    }
    row.update(extra)
    return row


def _review_one(cfg, pair: str, path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return _row(pair, path, STATUS_UNREADABLE)
    split = split_transfer(text)
    if split is None:
        return _row(pair, path, STATUS_NOT_A_TRANSFER)
    header, body = split
    source = header.get("source_filename") or path.name
    recorded = header.get("unique_blocks", [])
    # Reject a header value that would leave the references folder.
    if Path(source).name != source:
        return _row(pair, path, STATUS_NOT_A_TRANSFER, filename=source)
    shipped = cfg.plugin_root / "references" / source
    try:
        shipped_raw = shipped.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _row(pair, path, STATUS_NO_COUNTERPART, filename=source,
                    recorded_unique_blocks=recorded)
    verdict = _classify_diverged(
        normalize_rule_for_diff(body), normalize_rule_for_diff(shipped_raw))
    if _verdict_not_analyzed(verdict):
        status = STATUS_STILL_UNIQUE
    elif _destructively_removable(verdict):
        status = STATUS_NOW_UPSTREAM
    else:
        status = STATUS_STILL_UNIQUE
    unique = list(getattr(verdict, "unique_blocks", None) or [])
    return _row(
        pair, path, status, filename=source,
        classification=getattr(verdict, "classification", "HAS_UNIQUE"),
        confidence=getattr(verdict, "confidence", "unique"),
        unique_blocks=unique,
        unique_blocks_titled_in_shipped=_labels_in_shipped(unique, shipped_raw),
        recorded_unique_blocks=recorded,
        shipped=shipped.relative_to(cfg.plugin_root).as_posix(),
    )


def review_transfers(cfg, exclude_pair: "str | None" = None) -> list[dict]:
    """Return one row per transfer file under `upgrade-transfers/*-to-*/`.

    `exclude_pair` names a `{from}-to-{to}` folder to skip, so the upgrade
    handler can review earlier pairs while this run's own transfers keep the
    Step 4.1 case A flow. Rows sort by (pair, path). A pair folder with no
    files contributes nothing. Read-only.
    """
    root = cfg.project_root / cfg.planwise_root / "upgrade-transfers"
    rows: list[dict] = []
    for pair_dir in sorted(p for p in root.glob("*-to-*") if p.is_dir()):
        if pair_dir.name == exclude_pair:
            continue
        for path in sorted(f for f in pair_dir.rglob("*") if f.is_file()):
            rows.append(_review_one(cfg, pair_dir.name, path))
    return rows


def run_review_transfers(cfg, exclude_pair: "str | None" = None) -> int:
    """Execute the --review-transfers diagnostic. Prints json.dumps(rows), an
    empty array when no transfer is on disk, and returns 0. Read-only."""
    print(json.dumps(review_transfers(cfg, exclude_pair)))
    return 0
