"""Lessons index generator — column layout, required keys, hub statuses, and the generator error."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# --------------------------------------------------------------------------
# Column layout
#
# Position is asserted here by named constant, not by a comment next to a
# list literal, mirroring generate_backlog_index's own schema module -- a
# shift that only a comment recorded would not fail until something
# downstream silently read the wrong column.
# --------------------------------------------------------------------------

COL_ID = 0
COL_TITLE = 1
COL_CATEGORY = 2
COL_SEVERITY = 3
COL_LANGUAGE = 4
COL_TECHNOLOGY = 5
COL_DOMAIN = 6
COL_SOURCE = 7
COL_STATUS = 8
COL_FILE = 9
COLUMN_COUNT = 10

HEADER_CELLS = [
    "ID", "Title", "Category", "Severity", "Language", "Technology",
    "Domain", "Source", "Status", "File",
]

assert len(HEADER_CELLS) == COLUMN_COUNT
assert HEADER_CELLS[COL_ID] == "ID"
assert HEADER_CELLS[COL_TITLE] == "Title"
assert HEADER_CELLS[COL_CATEGORY] == "Category"
assert HEADER_CELLS[COL_SEVERITY] == "Severity"
assert HEADER_CELLS[COL_LANGUAGE] == "Language"
assert HEADER_CELLS[COL_TECHNOLOGY] == "Technology"
assert HEADER_CELLS[COL_DOMAIN] == "Domain"
assert HEADER_CELLS[COL_SOURCE] == "Source"
assert HEADER_CELLS[COL_STATUS] == "Status"
assert HEADER_CELLS[COL_FILE] == "File"
assert COL_STATUS == 8               # a reader may key off status at a literal index
assert COL_FILE == COLUMN_COUNT - 1  # a reader may key off file at len(cells)-1

# The nine keys every lesson file's frontmatter must carry. `date:`,
# `applied-as:`, `promoted-to:`, `promoted-date:` and any unknown key are
# read (if present) and ignored -- this generator never writes them back.
REQUIRED_KEYS = (
    "id", "title", "category", "severity", "language",
    "technology", "domain", "source", "status",
)

# Hub membership: decided by status alone, never by directory (see the
# module docstring). Everything else shards to an Archive-century file.
HUB_STATUSES = frozenset({"documented", "orphaned"})

# Fallback declared-status set when config.yaml carries no `lesson_statuses:`
# key at all. `HUB_STATUSES` (a subset) stays the hub-routing rule either way.
_DEFAULT_LESSON_STATUSES = ("documented", "orphaned", "promoted", "applied", "rule")


def _resolve_valid_statuses(config: dict) -> frozenset:
    """The declared `lesson_statuses:` set, or `_DEFAULT_LESSON_STATUSES`
    when the key is absent from `config.yaml` entirely -- printing one
    stderr note naming the fallback. Without this, `config.get(...) or []`
    resolves a missing key to an empty `frozenset()`, and since nothing is
    ever a member of an empty set, EVERY lesson's status fails the
    membership check and the whole run refuses -- a project whose
    config.yaml predates this key must still generate cleanly. A key that
    IS present but set to an empty list is left empty, not defaulted: that
    is a deliberate project choice, and silently overriding it would hide
    a real misconfiguration instead of reporting it.
    """
    raw = config.get("lesson_statuses")
    if raw is None:
        print(
            "Note: config.yaml declares no lesson_statuses; falling back "
            f"to the default set ({', '.join(_DEFAULT_LESSON_STATUSES)}).",
            file=sys.stderr,
        )
        return frozenset(_DEFAULT_LESSON_STATUSES)
    return frozenset(raw)


class LessonsGeneratorError(Exception):
    """A scan/render condition that must abort before any row renders (a
    missing required key, an unreadable id, an undeclared status), or the
    signal `is_legacy_index` raises for a write path to refuse on unless a
    caller explicitly opts to replace a legacy-shaped on-disk index.
    """
