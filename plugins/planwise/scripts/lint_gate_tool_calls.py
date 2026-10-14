#!/usr/bin/env python3
"""Line matchers for native tool calls written inside plan markdown.

``lint_verification_gates`` reads markdown lines directly for the checks that
target a native ``Grep`` or ``Glob`` call, because such a call in a table row
never becomes an extracted command. This module holds the matchers for those
checks. It imports nothing from the linter, so the linter can import it
without a cycle, and a run of the linter as a script never loads a second copy
of itself.

Each matcher takes one line and returns the text of the first offending call,
or ``None``. A line containing the word WRONG is a counter-example, not a
gate, and no matcher fires on it.
"""

import re

# A native ``Grep`` tool call written as ``Grep  pattern='...'``. The value runs
# to the matching quote, so a quote of the other kind may sit inside it.
GREP_TOOL_CALL_RE = re.compile(r"\bGrep\b[^\n]*?\bpattern\s*=\s*(['\"])(.*?)\1")

# A backslash-pipe with a word character directly on each side, such as
# ``a\|b``. That is the shape of an alternation. A backslash-pipe beside
# whitespace, at the pattern start, or after ``^`` anchors a literal pipe in a
# markdown table row and is not matched. The ``(?<!\\\w)`` guard keeps a class
# escape such as ``\w\|`` from counting as a word character.
ESCAPED_PIPE_ALTERNATION_RE = re.compile(r"(?<=\w)(?<!\\\w)\\\|(?=\w)")

# A native ``Glob`` call. The text from one ``Glob`` word to the next (or the
# end of the line) is one call's argument span.
_GLOB_WORD_RE = re.compile(r"\bGlob\b")
_PATTERN_ARG_RE = re.compile(r"\bpattern\s*=\s*(['\"])(.*?)\1")
_PATH_ARG_RE = re.compile(r"\bpath\s*=\s*(['\"])(.*?)\1")

# A pattern that starts with one of these is not folder-led: a recursive or
# wildcard lead, a brace group, an absolute path, or a dot-relative path.
_NOT_FOLDER_LED_START = ("*", "{", "/", "\\", ".", "~")
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")
_GLOB_METACHARACTERS = frozenset("*?[]{}")


# The finding message each matcher's check reports.
GREP_ALTERNATION_MESSAGE = (
    "This Grep tool pattern writes alternation as a backslash-pipe. "
    "The tool uses ripgrep syntax, where that matches a literal pipe, "
    "so the pattern matches nothing. Use a bare pipe outside a table "
    "cell, or split it into one Grep call per alternative"
)
GLOB_FOLDER_LED_MESSAGE = (
    "This Glob tool pattern starts with a folder segment while path is "
    "set. Inside a project the tool anchors a pattern that contains a "
    "slash at the project root and uses path only to filter the "
    "results, so the pattern matches nothing and an absence gate "
    "passes on any tree. Lead the pattern with **/, or name files "
    "only with path set to the folder itself"
)


def iter_tool_calls(paths, matcher):
    """Yield ``(path, line_number, call)`` for each line of each file in
    ``paths`` that ``matcher`` flags. A file that cannot be read is skipped."""
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.split("\n"), start=1):
            call = matcher(line)
            if call is not None:
                yield path, number, call


def grep_alternation_call(line: str):
    """Return the first ``Grep`` call on ``line`` whose pattern writes
    alternation as a backslash-pipe, or ``None``."""
    if "WRONG" in line:
        return None
    for call in GREP_TOOL_CALL_RE.finditer(line):
        if ESCAPED_PIPE_ALTERNATION_RE.search(call.group(2)):
            return call.group(0)
    return None


def _is_folder_led(pattern: str) -> bool:
    """True when the pattern's first segment is a literal folder name."""
    if "/" not in pattern or pattern.startswith(_NOT_FOLDER_LED_START):
        return False
    if _DRIVE_LETTER_RE.match(pattern):
        return False
    first_segment = pattern.split("/", 1)[0]
    return not any(char in _GLOB_METACHARACTERS for char in first_segment)


def glob_folder_led_call(line: str):
    """Return the first ``Glob`` call on ``line`` that sets ``path`` and writes
    a pattern starting with a literal folder segment, or ``None``."""
    if "WRONG" in line:
        return None
    starts = [match.start() for match in _GLOB_WORD_RE.finditer(line)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(line)
        span = line[start:end]
        pattern = _PATTERN_ARG_RE.search(span)
        if pattern is None or _PATH_ARG_RE.search(span) is None:
            continue
        if _is_folder_led(pattern.group(2)):
            return span.rstrip()
    return None
