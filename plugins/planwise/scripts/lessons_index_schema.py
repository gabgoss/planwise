"""Lessons index schema: the 10-column row layout and its import-time asserts,
the required frontmatter keys, the hub-status set, the config-derived
status resolver, and `LessonsGeneratorError`. Imports no other plugin module.

Imported by `lessons_index_scan`, `lessons_index_render`, `lessons_index_budget`,
`lessons_index_build`, `lessons_index_drift`, `lessons_index_run`, and
`lessons_index_companion`. Re-exported unchanged by the `generate_lessons_index`
facade.
"""

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
# `generate_lessons_index` module docstring). Everything else shards to an Archive-century file.
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


# The six places a lesson's fix can be promoted to.
PROMOTION_TARGETS = ("rule", "code", "claude-md", "agent", "skill", "settings")

# The targets a machine executes, so a check can run against them.
EXECUTABLE_TARGETS = frozenset({"code", "settings"})

# Where a lesson's cause originated, in the order the resolution matrix asks them.
LESSON_ORIGINS = (
    "planwise", "owned-tool", "foreign-tool", "model-call", "own-rules", "own-code", "other",
)

# The origins whose fix is a `code` target.
CODE_ORIGINS = frozenset({"owned-tool", "own-code"})

# The `enforced-by:` kind that records a deliberate absence of a check.
NO_CHECK = "none"


def _unquote_pair(text: str) -> str:
    """Remove one matching pair of surrounding single or double quotes."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_enforced_by(value: str | None) -> tuple[str, str] | None:
    """Split an `enforced-by:` answer into `(kind, text)`, or None when malformed.

    None covers an absent, blank or multi-line value, a value with no colon,
    and a value whose kind part is empty. The kind is the text before the
    first colon, stripped and lower-cased. The text is everything after it,
    stripped, so later colons stay in the text. The kind is never checked
    against a list: the caller holds the configured kinds. `none:` with no
    reason returns `("none", "")` so the caller can report the missing reason.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or "\n" in text or "\r" in text:
        return None
    text = _unquote_pair(text).strip()
    kind, sep, rest = text.partition(":")
    if not sep:
        return None
    kind = kind.strip().lower()
    if not kind:
        return None
    return kind, rest.strip()


def split_targets(value: str | None) -> list[str]:
    """Read a `promotion-target:` value as lower-cased tokens.

    Accepts `[a, b]`, `a, b` and a bare scalar, and strips quotes and
    whitespace. Empty tokens are dropped. It does not split on `|`, so an
    unfilled template value stays one token that no value set contains.
    """
    if not value:
        return []
    tokens: list[str] = []
    for line in value.split("\n"):
        line = line.strip().lstrip("-").strip().strip("[]")
        for part in line.split(","):
            token = _unquote_pair(part.strip()).strip().lower()
            if token:
                tokens.append(token)
    return tokens


class LessonsGeneratorError(Exception):
    """A scan/render condition that must abort before any row renders (a
    missing required key, an unreadable id, an undeclared status), or the
    signal `is_legacy_index` raises for a write path to refuse on unless a
    caller explicitly opts to replace a legacy-shaped on-disk index.
    """
