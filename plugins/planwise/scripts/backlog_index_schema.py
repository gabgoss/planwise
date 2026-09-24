"""Backlog index schema: the 9-column row layout and its import-time asserts,
the required frontmatter keys, and the config-derived hub, shard, and
changelog filenames. Imports no other plugin module.

Re-exported unchanged by the `generate_backlog_index` facade.
"""

import re
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# --------------------------------------------------------------------------
# Column layout
#
# Position is asserted here by named constant, not by a comment next to a
# list literal -- several existing scripts read this table by cell position,
# and a shift that only a comment recorded would not fail until something
# downstream silently read the wrong column.
# --------------------------------------------------------------------------

COL_ID = 0
COL_TITLE = 1
COL_PRIORITY = 2
COL_STATUS = 3
COL_DOMAIN = 4
COL_CREATED = 5
COL_BLOCKS = 6
COL_SCORE = 7
COL_FILE = 8
COLUMN_COUNT = 9

HEADER_CELLS = [
    "ID", "Title", "Priority", "Status", "Domain", "Created", "Blocks", "Score", "File",
]

# The header text is the readable spec; these assertions are the enforced
# one. If a future edit moves a column, this fails at import time instead of
# at whatever downstream script reads the shifted cell.
assert len(HEADER_CELLS) == COLUMN_COUNT
assert HEADER_CELLS[COL_ID] == "ID"
assert HEADER_CELLS[COL_TITLE] == "Title"
assert HEADER_CELLS[COL_PRIORITY] == "Priority"
assert HEADER_CELLS[COL_STATUS] == "Status"
assert HEADER_CELLS[COL_DOMAIN] == "Domain"
assert HEADER_CELLS[COL_CREATED] == "Created"
assert HEADER_CELLS[COL_BLOCKS] == "Blocks"
assert HEADER_CELLS[COL_SCORE] == "Score"
assert HEADER_CELLS[COL_FILE] == "File"

# Existing scripts don't all read these columns the same way today. Some
# key off position relative to the row's own length (len(cells)-1 for File,
# len(cells)-2 for Score) -- the two asserts below protect exactly that
# contract, so a column appended after File fails here instead of silently
# shifting what those readers see. Others (parse_backlog.py, score_backlog.py)
# read an ABSOLUTE index into the legacy 6/7-column layout and locate the
# table by finding a "## Backlog Items" heading this module's generated
# files do not emit -- those readers are not compatible with this 9-column
# layout at all, by absolute position or by table-location, and no
# assertion here can make them so. Reconciling them to this layout is a
# separate rework, not a consequence of anything asserted below.
assert COL_STATUS == 3               # a reader keys off status at a literal index 3
assert COL_SCORE == COLUMN_COUNT - 2  # a writer keys off score at len(cells)-2
assert COL_FILE == COLUMN_COUNT - 1   # a reader keys off file at len(cells)-1

# The seven keys the item-file template requires. "blocks" may legitimately
# be an empty list; every other key must resolve to a non-empty scalar.
REQUIRED_KEYS = ("id", "title", "priority", "status", "abbrev", "created", "blocks")

TITLE_MAX_LEN = 120

# The default/legacy filename stem, kept as a live module constant because
# it is also the fallback naming basis below when no project config is in
# play (this module's own pure-function tests build fixtures against it
# directly). The REAL naming a live project uses is derived from its
# configured `index_files.backlog` path via `_index_naming` below (Finding
# F5) -- never this hardcoded constant -- so a project whose index is not
# named "00-Index-Backlog.md" gets a hub/shard/overflow-leaf naming the
# rest of the toolchain (`config["_index_path"]`, `config["_archive_dir"]`)
# actually agrees with, instead of one no other script would recognize.
INDEX_FILE_STEM = "Index-Backlog"

# The hub's pointer to the changelog (Execution Step 4, user decision (a)):
# a single byte-identical line on every run, carrying no date, so `--check`
# compares it like any other generated line instead of it vanishing
# silently the first time `--write` regenerates the hub. Its filename is
# derived from `naming` by `_changelog_filename`, defined next to
# `_hub_filename`/`_shard_filename` below (closeout review Finding 1) --
# never a hardcoded constant, so a custom `index_files.backlog` gets a
# changelog name `migrate_backlog_index.artifact_paths` agrees with,
# instead of always "00-Changelog-Backlog.md" regardless of project naming.

IndexNaming = namedtuple("IndexNaming", ["hub_name", "hub_stem", "suffix", "archive_stem"])

# The fallback naming: what every namer below produces when no project
# config is available (a bare pure-function call, as this module's own
# tests make). Equivalent to what `_index_naming` derives from an
# `index_path` of `00-Index-Backlog.md`.
_DEFAULT_INDEX_NAMING = IndexNaming(
    hub_name=f"00-{INDEX_FILE_STEM}.md",
    hub_stem=f"00-{INDEX_FILE_STEM}",
    suffix=".md",
    archive_stem=INDEX_FILE_STEM,
)


def _index_naming(index_path: Path) -> IndexNaming:
    """Derive every generated filename shape from the project's configured
    index path -- the hub name, its overflow-leaf stem, and the Archive
    shard stem all come from this ONE source (Finding F5), so a custom
    `index_files.backlog` in config.yaml (e.g. `Backlog-Index.md`) is
    honored instead of a hardcoded `00-Index-Backlog.md` no other script in
    the project would recognize. `archive_stem` strips a leading `00-`
    (the hub's own "generated artifact" marker): an Archive shard has never
    carried that prefix, and stripping it structurally rather than via a
    second hardcoded constant is what keeps the namer and the scanner's
    skip-filter (`is_generated_index_file`, built from this same tuple)
    unable to drift apart.
    """
    hub_name = index_path.name
    hub_stem = index_path.stem
    suffix = index_path.suffix
    archive_stem = hub_stem.removeprefix("00-")
    return IndexNaming(hub_name=hub_name, hub_stem=hub_stem, suffix=suffix, archive_stem=archive_stem)


def _generated_index_file_pattern(naming: IndexNaming) -> re.Pattern:
    """One regex built from the SAME `naming` the hub/shard namers below
    use, so the scanner's skip-filter and the namers cannot drift apart by
    construction (the property the old hardcoded-constant version claimed
    but did not fully hold -- Finding F2: the id-range group here is
    `\\d{3,}`, matching every digit width `_hub_filename`/`_shard_filename`'s
    `:03d` formatting can ever produce, not the too-narrow `\\d{3}` a
    4+-digit id such as 1000 fell outside of).
    """
    range_pattern = r"-\d{3,}-\d{3,}"
    return re.compile(
        r"^(?:"
        + re.escape(naming.hub_name)
        + r"|" + re.escape(naming.hub_stem) + range_pattern + re.escape(naming.suffix)
        + r"|" + re.escape(naming.archive_stem) + range_pattern + re.escape(naming.suffix)
        + r")$"
    )


def is_generated_index_file(name: str, naming: IndexNaming | None = None) -> bool:
    """True for any filename this module itself emits under `naming` (the
    hub, a hub overflow leaf, or an Archive shard). None of these is ever
    an item file. `naming` defaults to the fallback stem
    (`_DEFAULT_INDEX_NAMING`) when the caller has no project config in
    play -- a real CLI run always passes the config-derived naming instead.
    """
    return bool(_generated_index_file_pattern(naming or _DEFAULT_INDEX_NAMING).match(name))


class GeneratorError(Exception):
    """A condition that must abort generation before any row renders."""

def _hub_filename(naming: IndexNaming, min_id: int, max_id: int, index: int) -> str:
    """Leaf 0 is the canonical hub filename; every later leaf is an
    overflow continuation named by its own id range -- the hub is bounded
    by open-item count, which is not bounded by construction, so it must be
    able to shard too.
    """
    if index == 0:
        return naming.hub_name
    return f"{naming.hub_stem}-{min_id:03d}-{max_id:03d}{naming.suffix}"


def _shard_filename(naming: IndexNaming, min_id: int, max_id: int) -> str:
    return f"{naming.archive_stem}-{min_id:03d}-{max_id:03d}{naming.suffix}"


_CHANGELOG_HUB_RE = re.compile(r"^00-Index-(.+)$")


def _changelog_filename(naming: IndexNaming) -> str:
    """The one namer for the changelog file: what the hub's footer points
    at, and what `migrate_backlog_index.artifact_paths` creates -- both
    scripts import this function rather than deriving the name twice, so
    they cannot disagree on it (closeout review Finding 1).

    When the hub follows the `00-Index-{X}{suffix}` shape, the changelog is
    `00-Changelog-{X}{suffix}`. For the default/live project's own
    `00-Index-Backlog.md`, X = "Backlog", giving the existing
    `00-Changelog-Backlog.md` this function must never rename. A hub that
    does not follow that shape (a custom `project.index_files.backlog`,
    e.g. `Backlog-Index.md`) falls back to `00-{hub_stem}-Changelog{suffix}`.
    """
    match = _CHANGELOG_HUB_RE.match(naming.hub_stem)
    if match:
        return f"00-Changelog-{match.group(1)}{naming.suffix}"
    return f"00-{naming.hub_stem}-Changelog{naming.suffix}"


def _footer_line(naming: IndexNaming) -> str:
    return f"[Changelog]({_changelog_filename(naming)})\n"

