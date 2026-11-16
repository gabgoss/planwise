#!/usr/bin/env python3
"""Shipped text passes a close-command status or outcome value joined to its
flag with `=`, never as a separate word.

Inside a git worktree, Claude Code refuses a Bash command that carries the bare
word `complete` or `source` as an argument, quoted or not, in any letter case.
A shipped line that teaches `--status COMPLETE` therefore teaches a command an
agent cannot run there. The `=` form (`--status=COMPLETE`) runs everywhere.

Predicate: for every text file under plugins/planwise, no line matches
SEPARATE_WORD_RE. The pattern flags the close word itself and the placeholder
shapes whose value can be that word (`{...}`, `STATUS`, `S`, `OUTCOME`).

Positive clause: every file in EQUALS_FORM_FILES carries at least one
`--status=` or `--outcome=` line, so the test cannot pass on a tree where the
flags were deleted instead of repointed.

What this cannot see: a value passed through a shell variable, a flag built
by string concatenation in code, and a close word split from its flag across
two lines.

Run with:  python -m pytest -q -c pytest.ini tests/test_close_command_flag_form.py
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "planwise"

SEPARATE_WORD_RE = re.compile(
    r"""--(status|outcome)\s+["']?((?i:complete)\b|\{|STATUS\b|S\b|OUTCOME\b)"""
)
EQUALS_FORM_RE = re.compile(r"--(status|outcome)=")

# The files that carry the close command, each of which must show the `=` form.
EQUALS_FORM_FILES = (
    "scripts/update_backlog.py",
    "scripts/backlog_loop.py",
    "handlers/backlog.md",
    "handlers/backlog-Part-2-LoopMode.md",
    "handlers/backlog-Part-4-Refine.md",
    "handlers/run.md",
    "references/auto-mode-policy.md",
    "references/backlog-schema.md",
    "references/session-planning-protocol.md",
    "references/task-file-and-tracking-requirements.md",
)

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def text_files(root: Path) -> list[tuple[str, str]]:
    """Every UTF-8 text file under root as (relative posix path, text)."""
    files: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIP_DIRS.intersection(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # a binary file carries no command text
            continue
        files.append((path.relative_to(root).as_posix(), text))
    return files


def separate_word_hits(files: list[tuple[str, str]]) -> list[str]:
    """`path:line` for each line that pins the separate-word form."""
    return [
        f"{rel}:{lineno}"
        for rel, text in files
        for lineno, line in enumerate(text.splitlines(), start=1)
        if SEPARATE_WORD_RE.search(line)
    ]


def files_without_equals_form(files: list[tuple[str, str]], required) -> list[str]:
    by_path = dict(files)
    return [rel for rel in required if not EQUALS_FORM_RE.search(by_path.get(rel, ""))]


# ---- Controls -------------------------------------------------------------


def test_predicate_flags_known_bad_lines():
    bad = (
        "python update_backlog.py --id 900 --status COMPLETE",
        'backlog_loop.py --mark --outcome "complete" --run r --id 1',
        "update_backlog.py --status {new_status}",
        "update_backlog.py --id ID --status STATUS",
        "backlog_loop.py --init [--status S]",
        "backlog_loop.py --mark --outcome OUTCOME",
    )
    assert [line for line in bad if not SEPARATE_WORD_RE.search(line)] == []


def test_predicate_passes_equals_form_and_other_values():
    good = (
        "python update_backlog.py --id 900 --status=COMPLETE",
        "backlog_loop.py --mark --outcome=COMPLETE --run r --id 1",
        "update_backlog.py --status={new_status}",
        "update_backlog.py --id 838 --status IN_PROGRESS",
        "parse_backlog.py --status NOT_STARTED",
        "the --status flag completes the transition",
    )
    assert [line for line in good if SEPARATE_WORD_RE.search(line)] == []


def test_scan_saw_the_plugin_tree():
    files = text_files(PLUGIN_ROOT)
    seen = {rel for rel, _ in files}
    assert len(files) > 100, f"scan read only {len(files)} text files under {PLUGIN_ROOT}"
    assert [rel for rel in EQUALS_FORM_FILES if rel not in seen] == []


# ---- Real tree ------------------------------------------------------------


def test_no_shipped_line_pins_the_separate_word_form():
    hits = separate_word_hits(text_files(PLUGIN_ROOT))
    listing = "\n".join(hits)
    assert not hits, f"lines that pass the value as a separate word:\n{listing}"


def test_every_close_command_file_carries_the_equals_form():
    missing = files_without_equals_form(text_files(PLUGIN_ROOT), EQUALS_FORM_FILES)
    assert not missing, f"files with no --status= or --outcome= line: {missing}"
