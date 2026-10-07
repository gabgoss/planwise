"""Lessons index companion: the categorization decision tree, the default
buckets, and rendering of the categorization companion file (`--companion`).

Imports `lessons_index_schema` from this generator, plus `generate_backlog_index`
and `parse_lessons`. Imported by `lessons_index_companion_drift`, and by
`lessons_bootstrap` through the `generate_lessons_index` facade, which
re-exports it unchanged.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_backlog_index import (
    _changelog_filename,
    _escape_cell,
    _generated_line,
    truncate_title,
)
from lessons_index_schema import LessonsGeneratorError
from parse_lessons import format_id

# --------------------------------------------------------------------------
# Categorization companion (--companion)
#
# `00-Categorization-By-Domain.md` is rendered from the SAME frontmatter
# scan the index uses (`lessons_index_scan.scan_lessons`) -- no second frontmatter
# reader. Membership runs the project's `config.yaml: categorization`
# decision tree (curate's own §5.1 algorithm): the first bucket in
# `decision_tree_order` whose `triggers.technology`/`triggers.domain`
# shares a value with the lesson's own list wins; within that bucket, the
# first sub-bucket (in the bucket's own `sub_buckets` order) whose trigger
# matches wins, else the lesson lands in the bucket's own parent table; a
# lesson matching no bucket at all lands in `default_bucket`'s parent
# table, never one of its sub-buckets.
#
# The companion is not a hub: one file, no counter, no Archive shard, no
# `## Master Table` heading -- regenerated whole on every --write. The
# hand-written prose (cross-cutting observations, classification edge
# cases) lives in a sibling notes file this module never reads or writes;
# the companion's footer only points at it by name.
# --------------------------------------------------------------------------

COMPANION_FILENAME = "00-Categorization-By-Domain.md"
NOTES_FILENAME = "00-Categorization-Notes-LessonsLearned.md"

# Bold marks a landed lesson, exactly as the index's own File-cell-free
# companion row still needs to show lifecycle state -- never the file's
# directory.
_LANDED_STATUSES = frozenset({"applied", "rule"})

_SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# `## {id}. {name} (N)` / `### {sub_id}. {sub_name} (N)` -- the same shape
# lessons_bootstrap.py's zero-lesson renderer emits. Group 2 is the bucket
# or sub-bucket id token (e.g. "A", "C1", "db-sql"), used to compare a disk
# row's table against the fresh classification without re-deriving heading
# text. The token is any run of non-space, non-dot characters, so the first
# `.` after it is always the separator and a bucket NAME may carry dots of
# its own; `_validate_categorization` rejects an id the token cannot hold.
_COMPANION_HEADING_RE = re.compile(r"^(#{2,3})\s+([^\s.]+)\.\s+.+?\((\d+)\)\s*$")
_COMPANION_ID_CELL_RE = re.compile(r"^\*{0,2}LL-(\d+)\*{0,2}$")
_COMPANION_LEGACY_LAST_UPDATED_RE = re.compile(r"^\*\*Last Updated:\*\*", re.MULTILINE)
_COMPANION_LEGACY_HEADING_RE = re.compile(r"^##\s+Cross-cutting observations\s*$", re.MULTILINE)
_COMPANION_GENERATED_RE = re.compile(r"^Generated: .*$", re.MULTILINE)
_COMPANION_TO_RE = re.compile(r"^\*\*Companion to:\*\*", re.MULTILINE)
_COMPANION_ANY_HEADING_RE = re.compile(r"^#{2,3}\s+\S")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Fallback categorization used when a project's config.yaml has no
# `categorization:` block. Mirrors the buckets baked into
# config.yaml.template. `--companion` renders from it (with an INFO line)
# and lessons_bootstrap.py seeds the zero-lesson companion from it and
# re-exports it under the same name for the `--migrate` flow. It lives here,
# beside its renderer, because lessons_bootstrap already imports this
# module -- the reverse import would be a cycle.
DEFAULT_CATEGORIZATION = {
    "buckets": [
        {
            "id": "A",
            "slug": "database",
            "name": "Database / SQL",
            "description": "Lessons that touch the live database, schema, or DDL semantics.",
        },
        {
            "id": "B",
            "slug": "code",
            "name": "Application Code",
            "description": "Lessons about language-level patterns, type-checking, lint, runtime behaviour.",
        },
        {
            "id": "C",
            "slug": "process",
            "name": "Planwise / Process",
            "description": "Lessons about planning, scaffolding, dispatch, signoff, review.",
            "sub_buckets": [],
        },
        {
            "id": "D",
            "slug": "tooling",
            "name": "Tooling / Ergonomics",
            "description": "Toolchain, shell, notebook, IDE, harness ergonomics.",
        },
    ],
    "decision_tree_order": ["A", "B", "C", "D"],
    "default_bucket": "D",
    "edge_cases_section": True,
}


def _companion_path(lessons_dir: Path) -> Path:
    return lessons_dir / COMPANION_FILENAME


class CategorizationError(LessonsGeneratorError):
    """config.yaml carries no usable `categorization:` block."""


def has_categorization_block(config: dict) -> bool:
    """True when `config` declares a `categorization:` block with at least
    one bucket mapping -- the condition under which DEFAULT_CATEGORIZATION
    is NOT the fallback."""
    cat = config.get("categorization")
    return isinstance(cat, dict) and bool(
        [b for b in (cat.get("buckets") or []) if isinstance(b, dict)]
    )


def _validate_id(raw, where: str) -> str:
    """The str form of one bucket/sub-bucket id, or CategorizationError
    naming `where`. An id must be non-empty and carry no whitespace or
    `.`, because the rendered heading `## {id}. {name} (N)` is how
    `--check` reads a row's table back -- an id the heading cannot hold
    would never round-trip."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise CategorizationError(f"config.yaml categorization: {where} has no id.")
    if re.search(r"[\s.]", text):
        raise CategorizationError(
            f"config.yaml categorization: {where} id {text!r} contains whitespace "
            "or '.', which the rendered heading cannot carry."
        )
    return text


def _validate_categorization(cat: dict) -> None:
    """Every bucket and sub-bucket has a usable, unique id (unique across
    both levels, since both share one heading namespace), `default_bucket`
    names a bucket, and every `decision_tree_order` entry names a bucket.
    Raises CategorizationError naming the offending entry."""
    seen: dict = {}
    bucket_ids = set()
    for index, bucket in enumerate(cat.get("buckets") or []):
        if not isinstance(bucket, dict):
            continue
        where = f"buckets[{index}] ({bucket.get('name', 'unnamed')!s})"
        bucket_id = _validate_id(bucket.get("id"), where)
        if bucket_id in seen:
            raise CategorizationError(
                f"config.yaml categorization: id {bucket_id!r} is declared by both "
                f"{seen[bucket_id]} and {where}."
            )
        seen[bucket_id] = where
        bucket_ids.add(bucket_id)
        subs = bucket.get("sub_buckets")
        if subs is not None and not isinstance(subs, list):
            raise CategorizationError(
                f"config.yaml categorization: {where} sub_buckets must be a list."
            )
        for sub_index, sub in enumerate(subs or []):
            if not isinstance(sub, dict):
                continue
            sub_where = f"{where} sub_buckets[{sub_index}] ({sub.get('name', 'unnamed')!s})"
            sub_id = _validate_id(sub.get("id"), sub_where)
            if sub_id in seen:
                raise CategorizationError(
                    f"config.yaml categorization: id {sub_id!r} is declared by both "
                    f"{seen[sub_id]} and {sub_where}."
                )
            seen[sub_id] = sub_where
    default_id = cat.get("default_bucket")
    if default_id is None or str(default_id) not in bucket_ids:
        raise CategorizationError(
            f"config.yaml categorization: default_bucket {default_id!r} is not a "
            "declared bucket id."
        )
    for entry in cat.get("decision_tree_order") or []:
        if str(entry) not in bucket_ids:
            raise CategorizationError(
                f"config.yaml categorization: decision_tree_order entry {entry!r} "
                "is not a declared bucket id."
            )


def _resolve_categorization(config: dict) -> dict:
    if not has_categorization_block(config):
        raise CategorizationError(
            "config.yaml declares no usable categorization: block "
            "(categorization.buckets is empty or the key is missing)."
        )
    cat = config["categorization"]
    _validate_categorization(cat)
    return cat


def _ordered_buckets(cat: dict) -> list:
    """Buckets in `decision_tree_order`, any bucket the order omits
    appended at the end so a config editing mistake never silently drops
    a bucket from the render. Ids compare as str, so a YAML int id and its
    quoted form are one bucket."""
    buckets = [b for b in (cat.get("buckets") or []) if isinstance(b, dict)]
    buckets_by_id = {str(b["id"]): b for b in buckets}
    order = cat.get("decision_tree_order") or [b["id"] for b in buckets]
    ordered = [buckets_by_id[str(bid)] for bid in order if str(bid) in buckets_by_id]
    ordered_ids = {str(b["id"]) for b in ordered}
    for b in buckets:
        if str(b["id"]) not in ordered_ids:
            ordered.append(b)
    return ordered


def _bucket_matches(item: dict, triggers: dict) -> bool:
    for field_name in ("technology", "domain"):
        trigger_values = (triggers or {}).get(field_name) or []
        if trigger_values and set(item.get(field_name) or []) & set(trigger_values):
            return True
    return False


def _first_sub_bucket_match(item: dict, sub_buckets: list):
    for sub in sub_buckets or []:
        if isinstance(sub, dict) and _bucket_matches(item, sub.get("triggers")):
            return sub
    return None


def classify_lesson(item: dict, cat: dict) -> tuple:
    """(bucket, sub_bucket_or_None) for one scanned lesson item, per
    curate §5.1. `default_bucket` never carries a sub-bucket -- a lesson
    that matches no trigger at all lands in the default bucket's own
    parent table."""
    for bucket in _ordered_buckets(cat):
        if _bucket_matches(item, bucket.get("triggers")):
            return bucket, _first_sub_bucket_match(item, bucket.get("sub_buckets"))
    buckets_by_id = {str(b["id"]): b for b in (cat.get("buckets") or []) if isinstance(b, dict)}
    default_id = cat.get("default_bucket")
    default_bucket = buckets_by_id.get(str(default_id))
    if default_bucket is None:
        raise CategorizationError(
            f"config.yaml default_bucket {default_id!r} is not a declared bucket id"
        )
    return default_bucket, None


def _row_sort_key(item: dict) -> tuple:
    severity = str(item.get("severity", "")).strip().upper()
    return (_SEVERITY_ORDER.get(severity, len(_SEVERITY_ORDER)), item["id"])


def partition_companion(items: list, cat: dict) -> dict:
    """{bucket_id: {"bucket": ..., "parent": [items], "subs": {sub_id:
    {"sub": ..., "items": [items]}}}} in decision-tree order (dict
    insertion order preserves it) -- every bucket and sub-bucket the
    config declares is present even with zero items, which is what lets
    the zero-lesson render show every heading. Each table's items are
    sorted HIGH -> MEDIUM -> LOW, ascending id within a tier.
    """
    table: dict = {}
    for bucket in _ordered_buckets(cat):
        table[bucket["id"]] = {
            "bucket": bucket,
            "parent": [],
            "subs": {
                sub["id"]: {"sub": sub, "items": []}
                for sub in (bucket.get("sub_buckets") or [])
                if isinstance(sub, dict)
            },
        }
    for item in items:
        bucket, sub = classify_lesson(item, cat)
        entry = table[bucket["id"]]
        if sub is not None:
            entry["subs"][sub["id"]]["items"].append(item)
        else:
            entry["parent"].append(item)
    for entry in table.values():
        entry["parent"].sort(key=_row_sort_key)
        for sub_entry in entry["subs"].values():
            sub_entry["items"].sort(key=_row_sort_key)
    return table


def _companion_table_header(code_bucket: bool) -> tuple:
    if code_bucket:
        return "| ID | Title | Module | Severity |", "|---|---|---|---|"
    return "| ID | Title | Severity |", "|---|---|---|"


def _companion_row(item: dict) -> tuple:
    """(bold, title_cell, severity_cell, module_cell) -- the rendered,
    escaped form of each cell the row can carry. The renderer picks which
    cells to join; the drift checker reads the joined row back through
    `split_row_cells` rather than comparing these escaped values."""
    rendered_title, _ = truncate_title(item["title"])
    bold = item["status"] in _LANDED_STATUSES
    title_cell = _escape_cell(rendered_title)
    severity_cell = _escape_cell(item["severity"])
    module_cell = _escape_cell(item.get("module") or "-")
    return bold, title_cell, severity_cell, module_cell


def _render_companion_row(item: dict, code_bucket: bool) -> str:
    bold, title_cell, severity_cell, module_cell = _companion_row(item)
    id_cell = format_id(item["id"])
    if bold:
        id_cell = f"**{id_cell}**"
    cells = [id_cell, title_cell]
    if code_bucket:
        cells.append(module_cell)
    cells.append(severity_cell)
    return "|" + "|".join(f" {c} " for c in cells) + "|"


def _render_companion_table(items: list, code_bucket: bool) -> str:
    header, sep = _companion_table_header(code_bucket)
    lines = [header, sep]
    lines.extend(_render_companion_row(item, code_bucket) for item in items)
    return "\n".join(lines) + "\n"


def render_companion_body(table: dict, cat: dict) -> str:
    blocks = []
    for bucket_id, entry in table.items():
        bucket = entry["bucket"]
        code_bucket = bool(bucket.get("code_bucket"))
        section = [
            f"## {bucket_id}. {bucket.get('name', '')} ({len(entry['parent'])})",
            "",
            str(bucket.get("description", "")),
            "",
            _render_companion_table(entry["parent"], code_bucket),
        ]
        for sub_id, sub_entry in entry["subs"].items():
            sub = sub_entry["sub"]
            sub_items = sub_entry["items"]
            section.extend([
                f"### {sub_id}. {sub.get('name', '')} ({len(sub_items)})",
                "",
                str(sub.get("description", "")),
                "",
                _render_companion_table(sub_items, code_bucket),
            ])
        blocks.append("\n".join(section))
    return "\n\n".join(blocks) + "\n"


def render_companion_header(config: dict, naming) -> str:
    index_name = naming.hub_name
    scope = (config.get("categorization") or {}).get("scope")
    if not scope:
        project_name = (config.get("project") or {}).get("name")
        if project_name:
            scope = f"Lessons captured during {project_name} sessions."
        else:
            scope = "Lessons captured during this project's sessions."
    return (
        "# Lessons Learned — Categorization by Domain\n"
        "\n"
        f"{_generated_line()}"
        f"**Companion to:** [{index_name}]({index_name})\n"
        "\n"
        "## Scope\n"
        "\n"
        f"{scope}\n"
    )


def render_companion_footer() -> str:
    return f"[Notes]({NOTES_FILENAME})\n"


def render_companion_file(items: list, config: dict, naming) -> str:
    cat = _resolve_categorization(config)
    table = partition_companion(items, cat)
    return (
        render_companion_header(config, naming)
        + "\n---\n\n"
        + render_companion_body(table, cat)
        + "\n---\n\n"
        + render_companion_footer()
        + f"[Changelog]({_changelog_filename(naming)})\n"
    )
