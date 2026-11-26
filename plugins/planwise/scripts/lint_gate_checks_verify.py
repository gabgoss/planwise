#!/usr/bin/env python3
"""Lint checks that read one task file's gate text, registered into the linter.

Checks 63 to 65 read other lines too: a checkbox criterion in any plan file, and
a spec line in a task or Orchestration file. Check 68 also reads the lines of a
task file, for a native ``Read`` call with a literal ``limit``, in its
Verification Commands and Success Criteria sections only.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check takes
the lint context duck-typed -- it reads only ``commands``, ``plan_root`` and
``markdown_files()`` -- and builds its finding with the same six keys the
linter's ``make_finding`` writes. The severity strings equal the linter's
``SEVERITY_*`` constants. A test pins both agreements.

Every check here is static: none runs a command. Checks 30, 31 and 35 to 38 are
heuristic, because what counts as a gate anchor, a status gate, a documenting
sentence or an extraction step is a judgment, so they report at WARNING and
never decide a verdict alone. Checks 63 to 65 are heuristic in the same way,
because each reads a line shape and cannot trace the claim through the real
structure. Check 68 is heuristic too: it reads a literal bound and cannot see a
bound held in a variable or a length asserted in a later command. It follows
gate-input-set-and-compared-window.md, the section "An Extraction Is Bounded by
Markers and Asserts Its Parsed Length".
"""

import re
from pathlib import Path

from lint_gate_checks_commands import (
    _grep_pattern_and_target,
    _is_task_file,
    _pipelines,
    _short_flags,
    _tokens,
)
from lint_gate_tool_calls import GREP_TOOL_CALL_RE

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_UNCERTAIN = "UNCERTAIN"

# A verified-on-date marker is an ISO date. The word ``unverified`` marks an
# anchor its author could not measure.
_VERIFIED_MARKER_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\bunverified\b", re.IGNORECASE)

# A heading anchor: a search pattern that starts at a markdown heading marker.
_HEADING_ANCHOR_RE = re.compile(r"^\^\s*#")
# The extracted-command blocks whose gate decides PASS or FAIL. The strings
# equal the linter's ``BLOCK_AFTER`` and ``BLOCK_EXIT_CRITERION``.
_ANCHOR_BLOCKS = frozenset({"After", "exit-criterion"})

# A status test: a status word that a gate reads as complete or pending.
_STATUS_TEST_RE = re.compile(
    r"\b(?:is|are|be|been|was|were|marked|reads?|shows?|status(?:\s+(?:is|of))?)\s+"
    r"[`*\"']{0,3}(?:COMPLETE|PENDING|NOT[ _]STARTED|complete|pending)\b"
)
# A line that gates on the status: a checkbox item or a stop word. The bare
# word "gate" is not a cue, because prose that describes a gate file or names
# ``gate-*.md`` carries it without gating on anything.
_GATE_CUE_RE = re.compile(
    r"^\s*(?:>\s*)?[-*]\s+\[[ xX]\]|\b(?:STOP|HALT|prerequisite|precondition)\b",
    re.IGNORECASE,
)
# The artifact a status gate must name: a file, or the table or field it reads.
_ARTIFACT_RE = re.compile(
    r"[\w./{}-]+\.(?:md|json|ya?ml|txt|csv|py)\b|\b(?:table|row|column|field|frontmatter)s?\b",
    re.IGNORECASE,
)

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s")
_SUCCESS_CRITERIA_RE = re.compile(r"^(#{1,6})\s+Success Criteria\b", re.IGNORECASE)
_OUTPUT_FIELD_RE = re.compile(r"^\*\*Output:\*\*\s*(.+)$")
_EXPECTED_OUTPUT_RE = re.compile(r"^#{1,6}\s+Expected Output\b", re.IGNORECASE)
_PLAN_ARTIFACT_RE = re.compile(r"[\w./{}-]+\.md\b")
# The size gate a file-producing task's Success Criteria carries.
_SIZE_GATE_RE = re.compile(r"measure_files|token.*(?:gate|budget|measure)", re.IGNORECASE)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Flags that make a command write: a fixer, an applier, an upgrade.
_WRITER_FLAGS = ("--write", "--fix", "--apply", "--upgrade")
# Flags that keep a writer from writing.
_NO_WRITE_FLAGS = frozenset({"--dry-run", "--check", "--diff", "-n"})
# A token that names a scratch target.
_SCRATCH_RE = re.compile(r"scratch|\btmp\b|\btemp\b|/tmp/|mktemp|\$TMP|\$TEMP", re.IGNORECASE)

# A gate note that expects an absence count: ``expect 0``, ``== 0``, ``MUST be 0``.
_ZERO_EXPECT_RE = re.compile(
    r"\bexpect(?:ed|s)?\s*[:=]?\s*(?:==\s*)?0(?![\d.])|==\s*0(?![\d.])|\bMUST\s+be\s+0(?![\d.])|\bzero\b",
    re.IGNORECASE,
)
# Targets that can carry prose a brief tells the author to write.
_PROSE_BEARING_SUFFIXES = frozenset({".py", ".sql", ".ipynb", ".md", ".sh", ".js", ".ts"})
# A pattern is literal when it holds no regex operator once ``\.`` is read as ``.``.
_REGEX_OPERATOR_RE = re.compile(r"[\[\](){}*+?|^$\\]")
# A sentence that tells the author to write prose about a token.
_DOCUMENTING_VERB_RE = re.compile(
    r"\b(?:explain|explains|document|documents|docstring|comment|describe|describes|mention|mentions)\b|\bnote\s+why\b",
    re.IGNORECASE,
)

# A repeated character class, as an extraction regex writes it. A negated class
# and a POSIX class are skipped.
_CHAR_CLASS_RE = re.compile(r"\[(?![\^:])([^\[\]]+)\](?=[+*]|\{\d)")
_CLASS_LETTERS_RE = re.compile(r"a-z|A-Z")
_CLASS_DIGITS_RE = re.compile(r"0-9|\\d|\\w|:digit:|:alnum:")
# A split result indexed as a parser: ``.split(...)[1]``. A path split on a
# slash is a basename idiom, not a parser.
_SPLIT_INDEX_RE = re.compile(
    r"\.split\((?!\s*['\"][/\\]['\"]\s*[,)])[^()]*\)\s*\[\s*-?\d+\s*\]"
)
# A grep that starts each match with its file path: a recursive or with-filename flag.
_PREFIX_LONG_FLAGS = frozenset({"--recursive", "--with-filename"})
_PREFIX_SHORT_FLAGS = "rRH"
# An exclusion pattern anchored at the line start, at the colon that ends the
# path (a leading or trailing colon), or past the ``:NN:`` prefix.
_PREFIX_ANCHORED_RE = re.compile(r"^\^|^:|:$|:\[0-9\]|:\\d")

# A checkbox criterion that pins a member count for a code symbol, and the
# instruments that satisfy it on the same line. A subject that ends in a
# lowercase file extension names a file, not a symbol, and is skipped.
_COUNT_PIN_RE = re.compile(
    r"(?i)^\s*[-*] \[ \][^\n]*`([^`#\n][^`\n]*)` (?:has|holds|lists|contains) \d+ "
    r"(?:members|surfaces|rows|names|entries|items|elements)\b"
)
_COUNT_INSTRUMENT_RE = re.compile(r"""(?i)len\(|wc -[lc]\b|output_mode=['"]count['"]|\bmeasured\b""")
_FILE_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,5}$")
# A spec line over a two-sided diff: both outcome words in code spans.
_TWO_SIDED_RE = re.compile(r"`changed`[^\n]*`added`|`added`[^\n]*`changed`")
_REMOVED_CELL_RE = re.compile(r"(?i)\b(removed|deleted|disappear\w*)\b")
# A task line that places a step before the first write, and the list of writes.
_FIRST_WRITE_RE = re.compile(
    r"(?i)\b(placed?|placing|sits?|inserted|insert|positioned|goes|lands?)\b[^\n]{0,60}"
    r"\bbefore (the |their |its )?([\w.`-]+['’]s )?(first|any)\b[^\n]{0,30}\bwrites?\b"
)
_WRITES_IN_ORDER_RE = re.compile(r"(?i)writes in (execution )?order")

# A literal extraction bound. A slice with an integer stop on a read result, and
# a native Read call with a literal limit. A slice on anything else is skipped.
_READ_SLICE_RE = re.compile(
    r"\.read(?:_text|_bytes|lines)?\([^()]*\)\s*\[\s*\d*\s*:\s*\d+\s*\]"
)
_READ_LIMIT_RE = re.compile(r"\bRead\b(?=[^\n]*\bfile_path\s*=)[^\n]*?\blimit\s*=\s*\d+")
_WRONG_LABEL_RE = re.compile(r"^\s*(?:>\s*)?WRONG\b")
# The sections whose lines a native Read call is read from: a paged read in an
# instruction step is a read, not a gate.
_READ_SCAN_SECTION_RE = re.compile(r"^(#{1,6})\s+(?:Verification Commands|Success Criteria)\b", re.IGNORECASE)
_LENGTH_COUNT_LONG_OPTIONS = frozenset({"--lines", "--bytes"})
_INTEGER_RE = re.compile(r"^\d+$")
_HEAD_TAIL_COUNT_RE = re.compile(r"^(?:-[nc]\d+|-\d+|--(?:lines|bytes)=\d+)$")
_GREP_MAX_COUNT_RE = re.compile(r"^(?:-[A-Za-z]*m\d+|--max-count=\d+)$")
# A length assertion: ``len(...)`` beside a comparison operator, or the note.
_LENGTH_COMPARISON_RE = re.compile(
    r"\blen\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?:==|!=|>=|<=|>|<)|(?:==|!=|>=|<=|>|<)\s*len\("
)
_PARSED_LENGTH_NOTE_RE = re.compile(r"\bparsed[- ]length\b", re.IGNORECASE)
_EXTRACTION_BOUND_MESSAGE = (
    "This command cuts what it reads at a literal count ({shape}) and asserts no parsed "
    "length. As the source grows the cut returns fewer items, so a count taken from it "
    "passes more readily and reports nothing. Assert the length of the parsed result "
    "(len(...) in a comparison, wc -l or wc -c directly after the cut, or a parsed length note), "
    "or read the whole source "
    "(gate-input-set-and-compared-window.md, the section \"An Extraction Is Bounded by "
    "Markers and Asserts Its Parsed Length\")"
)


def _finding(*, check, severity, file, line, command, message) -> dict:
    """Build a finding with the six keys the linter's ``make_finding`` writes."""
    return {
        "check": check,
        "severity": severity,
        "file": file,
        "line": line,
        "command": command,
        "message": message,
    }


def _task_files(context):
    """Yield ``(rel, lines)`` for each task file, with carriage returns removed.

    A task file is a markdown file whose first heading starts ``# Task:``."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        if not _is_task_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        yield rel, [raw.rstrip("\r") for raw in text.split("\n")]


def _fence_marked(lines):
    """Yield ``(number, line, fenced)``; a fence marker line counts as fenced."""
    fence = None
    for number, line in enumerate(lines, start=1):
        stripped = line.lstrip("> ").strip()
        marker = _FENCE_RE.match(stripped)
        if fence is not None:
            if marker and stripped[0] == fence[0] and len(stripped) >= len(fence):
                fence = None
            yield number, line, True
            continue
        if marker:
            fence = marker.group(1)
            yield number, line, True
            continue
        yield number, line, False


def _unfenced(lines):
    """Yield ``(number, line)`` for each line outside a fenced block."""
    for number, line, fenced in _fence_marked(lines):
        if not fenced:
            yield number, line


def _heading_anchor_commands(context):
    """Yield ``(file, line, text, notes)`` for every non-placeholder gate
    command with a grep stage whose pattern starts at a heading marker. Only
    an After-block gate or an exit criterion decides PASS or FAIL, so a
    Before-block reading is a measurement, not an anchor, and is skipped."""
    for command in context.commands:
        if command.is_placeholder or not command.is_gate or "WRONG" in command.command:
            continue
        if command.block not in _ANCHOR_BLOCKS:
            continue
        tokens = _tokens(command.command)
        if not tokens:
            continue
        for stages in _pipelines(tokens):
            if any(
                stage[0] == "grep" and _HEADING_ANCHOR_RE.match(_grep_pattern_and_target(stage)[0] or "")
                for stage in stages
            ):
                notes = f"{command.command} {command.comment} {command.annotation}"
                yield command.file, command.line, command.command, notes
                break


def _heading_anchor_tool_calls(context):
    """Yield ``(file, line, text, notes)`` for every native ``Grep`` call in a
    task file whose pattern starts at a heading marker. The line after the
    call is part of its notes, because a pre-edit comment sits there."""
    for rel, lines in _task_files(context):
        for index, line in enumerate(lines):
            if "WRONG" in line:
                continue
            for call in GREP_TOOL_CALL_RE.finditer(line):
                if _HEADING_ANCHOR_RE.match(call.group(2)):
                    following = lines[index + 1] if index + 1 < len(lines) else ""
                    yield rel, index + 1, call.group(0), f"{line} {following}"
                    break


def _check30_gate_anchor_without_verified_marker(context) -> list:
    """Check 30 -- a gate anchor carries neither a verified-on-date marker nor
    the word ``unverified`` (verify-anchor-against-artifact.md §1, the rule to
    write anchors from a live read or mark them unverified). A gate anchor here
    is a heading search: a grep gate command, or a native ``Grep`` call in a
    task file, whose pattern starts at a markdown heading marker. The command,
    its comment and its annotation line are read for an ISO date or the word
    ``unverified``. Heuristic, so WARNING: it reports and never gates alone.
    """
    findings = []
    seen = set()
    for source in (_heading_anchor_commands(context), _heading_anchor_tool_calls(context)):
        for file, line, text, notes in source:
            if (file, line) in seen or _VERIFIED_MARKER_RE.search(notes):
                continue
            seen.add((file, line))
            findings.append(_finding(
                check=30, severity=SEVERITY_WARNING, file=file, line=line, command=text,
                message=(
                    "This heading anchor carries no verified-on date and is not marked "
                    "unverified, so a runner cannot tell a measured anchor from one "
                    "restated from the criterion. Record the date of the live read, "
                    "or mark the anchor unverified"
                ),
            ))
    return findings


def _check31_status_gate_names_no_artifact(context) -> list:
    """Check 31 -- a status gate that tests complete or pending names no file
    and no table or field (verify-anchor-against-artifact.md §3). A plan states
    one status in several hand-maintained places, so a gate that names none
    reads whichever the runner opens. A status gate here is a line in a task
    file, outside a fenced block, that is a checkbox item or carries a stop
    word (STOP, HALT, prerequisite, precondition), and tests a status word. Heuristic, so WARNING: it reports and
    never gates alone.
    """
    findings = []
    for rel, lines in _task_files(context):
        for number, line in _unfenced(lines):
            if "WRONG" in line or _HEADING_LINE_RE.match(line.lstrip("> ")):
                continue
            match = _STATUS_TEST_RE.search(line)
            if match is None or not _GATE_CUE_RE.search(line) or _ARTIFACT_RE.search(line):
                continue
            findings.append(_finding(
                check=31, severity=SEVERITY_WARNING, file=rel, line=number,
                command=line.strip(),
                message=(
                    f"This status gate tests {match.group(0)!r} and names no file and no "
                    "table or field. A plan holds the same status in several places, "
                    "so the answer depends on which one the runner opens. Name the "
                    "artifact and the table or field the gate reads"
                ),
            ))
    return findings


def _success_criteria_text(lines) -> str | None:
    """The text of the Success Criteria section, or None when there is none.

    A heading is read only outside a fenced block, so a ``# comment`` line in
    a fenced command does not end the section. Fenced lines stay in the text,
    because the size gate is usually a fenced command."""
    level = None
    body: list = []
    for _number, line, fenced in _fence_marked(lines):
        heading = None if fenced else _HEADING_LINE_RE.match(line)
        if level is not None and heading and len(heading.group(1)) <= level:
            break
        if level is not None:
            body.append(line)
            continue
        criteria = None if fenced else _SUCCESS_CRITERIA_RE.match(line)
        if criteria:
            level = len(criteria.group(1))
    return None if level is None else "\n".join(body)


def _check32_file_producing_task_without_size_gate(context) -> list:
    """Check 32 -- a file-producing task has no measured size gate in its
    Success Criteria (verify-before-cite.md §9.B.8, Reviewer Check 029). Each
    produced file must land under the Read gates, and only a ``measure_files``
    run shows that. A file-producing task here has an ``Expected Output``
    section and an ``**Output:**`` field naming a markdown file. The detection
    is the source check's: Success Criteria matching ``measure_files`` or a
    token gate, budget or measure. ERROR, the source check's BLOCKER.
    """
    findings = []
    for rel, lines in _task_files(context):
        # A fenced sample of a task file is not this task's own field or section.
        if not any(_EXPECTED_OUTPUT_RE.match(line) for _number, line in _unfenced(lines)):
            continue
        output = next(
            ((number, m.group(1)) for number, line in _unfenced(lines)
             if (m := _OUTPUT_FIELD_RE.match(line.strip()))),
            None,
        )
        if output is None or not _PLAN_ARTIFACT_RE.search(output[1]):
            continue
        criteria = _success_criteria_text(lines)
        if criteria is not None and _SIZE_GATE_RE.search(criteria):
            continue
        findings.append(_finding(
            check=32, severity=SEVERITY_ERROR, file=rel, line=output[0],
            command=output[1].strip(),
            message=(
                "This task produces a markdown file, and its Success Criteria carry no "
                "measured size gate. Add a measure_files.py gate on each produced file "
                "so it lands under the Read gates before COMPLETE"
            ),
        ))
    return findings


def _writer_flag(stage):
    """The first writer flag in a stage, or None when the stage does not write."""
    if any(token in _NO_WRITE_FLAGS for token in stage[1:]):
        return None
    for token in stage[1:]:
        if token == "--":
            break
        if token in _WRITER_FLAGS or token.startswith(tuple(f"{flag}=" for flag in _WRITER_FLAGS)):
            return token
    return None


def _check33_writer_command_without_scratch_target(context) -> list:
    """Check 33 -- a verification command runs a writer (``--write``,
    ``--fix``, ``--apply`` or ``--upgrade``) and names no scratch target
    (verification-task-authoring.md §7, the checklist item on an anchor or
    verification command that runs a writer). Run against the live tree, a
    writer changes the files the next gate reads. A stage that also passes
    ``--dry-run``, ``--check`` or ``--diff`` does not write. A scratch target
    is a token naming a scratch, tmp or temp location. ERROR.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or "WRONG" in command.command:
            continue
        tokens = _tokens(command.command)
        if not tokens:
            continue
        flags = [
            flag for stages in _pipelines(tokens) for stage in stages
            if (flag := _writer_flag(stage)) is not None
        ]
        if not flags or any(_SCRATCH_RE.search(token) for token in tokens):
            continue
        findings.append(_finding(
            check=33, severity=SEVERITY_ERROR, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This verification command runs a writer ({flags[0]}) and names no "
                "scratch target, so it rewrites the live files the next gate reads. "
                "Copy the subject to a scratch directory and point the writer there"
            ),
        ))
    return findings


def _literal_token(pattern):
    """The literal text of a grep pattern, or None when it holds regex syntax."""
    if not pattern:
        return None
    token = pattern.replace("\\.", ".")
    if _REGEX_OPERATOR_RE.search(token):
        return None
    return token


def _absence_grep_token(command):
    """The literal token of a zero-expected grep over a prose-bearing target,
    or None when the command is not that shape."""
    note = f"{command.comment} {command.annotation}"
    if "WRONG" in command.command or "WRONG" in note or not _ZERO_EXPECT_RE.search(note):
        return None
    tokens = _tokens(command.command)
    if not tokens:
        return None
    for stages in _pipelines(tokens):
        first = stages[0]
        if first[0] != "grep":
            continue
        pattern, target = _grep_pattern_and_target(first)
        literal = _literal_token(pattern)
        if literal and target and Path(target).suffix.lower() in _PROSE_BEARING_SUFFIXES:
            return literal
    return None


def _check35_absence_gate_over_mandated_prose(context) -> list:
    """Check 35 -- a zero-expected grep over a prose-bearing file, while the
    same task file tells the author to write prose about that token
    (gate-absence-and-consistency.md §8.4, "A comment-strip pre-filter sees only
    whole-line comments"). A docstring, a markdown cell and a trailing comment
    are invisible to a line-anchored comment filter, so the brief demands text
    that the gate then counts. A gate here is a non-placeholder, non-WRONG
    command whose note expects 0, whose grep stage has a literal pattern, and
    whose target ends in a prose-bearing suffix. The mandate is a line outside
    any fenced block that holds the same token, a documenting verb and no
    ``grep``. Heuristic, so WARNING: it reports and never gates alone.
    """
    prose_by_file = {}
    for rel, lines in _task_files(context):
        prose_by_file[rel] = [
            line for _number, line in _unfenced(lines)
            if _DOCUMENTING_VERB_RE.search(line) and "grep" not in line and "WRONG" not in line
        ]
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        token = _absence_grep_token(command)
        if token is None or not any(token in line for line in prose_by_file.get(command.file, ())):
            continue
        findings.append(_finding(
            check=35, severity=SEVERITY_WARNING, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This gate expects {token!r} to be absent, and the same task tells the author "
                "to write prose about it. A comment-strip pre-filter sees only whole-line "
                "comments, so a docstring, a markdown cell or a trailing comment keeps the "
                "token in the count. Reword the prose with a synonym that keeps the meaning, "
                "or replace the instrument with an `ast` or `nbformat` parse "
                "(gate-absence-and-consistency.md, \"A comment-strip pre-filter sees only "
                "whole-line comments\")"
            ),
        ))
    return findings


def _is_wrong(command) -> bool:
    """True when the command's note or annotation labels the line a deliberate
    WRONG example, or the command text starts with the label. The word inside
    the command, such as a pattern that counts WRONG labels, is not a label."""
    return "WRONG" in f"{command.comment} {command.annotation}" or _WRONG_LABEL_RE.match(command.command) is not None


def _digitless_class(text):
    """The first repeated character class in ``text`` that holds letters and an
    underscore but no digit, or None."""
    for match in _CHAR_CLASS_RE.finditer(text):
        body = match.group(1)
        if "_" in body and _CLASS_LETTERS_RE.search(body) and not _CLASS_DIGITS_RE.search(body):
            return match.group(0)
    return None


def _check36_digitless_identifier_class(context) -> list:
    """Check 36 -- a verification command extracts with a repeated character
    class that holds letters and an underscore but no digit
    (gate-instrument-proof-obligations.md §10, the extractor-pitfalls table).
    Against ``country_3_code`` such a class drops the line or truncates the
    capture to ``country_``, and the two lists a gate then compares disagree on
    correct work. A negated class and a class without a repeat are skipped.
    Heuristic, so WARNING: it reports and never gates alone.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or _is_wrong(command):
            continue
        found = _digitless_class(command.command)
        if found is None:
            continue
        findings.append(_finding(
            check=36, severity=SEVERITY_WARNING, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This extraction pattern repeats the class {found}, which holds letters and "
                "an underscore and no digit. An identifier such as country_3_code then drops "
                "the whole line or truncates the capture to country_. Use [a-z0-9_]+ or \\w+, "
                "and assert the length of each derived list before comparing two of them "
                "(gate-instrument-proof-obligations.md, \"Extractor pitfalls\")"
            ),
        ))
    return findings


def _file_operand_count(stage) -> int:
    """The number of file operands a grep stage names."""
    positionals = []
    has_pattern_flag = False
    skip = False
    for token in stage[1:]:
        if skip:
            skip = False
            continue
        if token in ("-e", "--regexp"):
            has_pattern_flag = True
            skip = True
            continue
        if token in ("-A", "-B", "-C", "-m", "-f"):
            skip = True
            continue
        if token.startswith("-") and token != "-":
            continue
        positionals.append(token)
    return len(positionals) if has_pattern_flag else max(len(positionals) - 1, 0)


def _prints_prefix(stage) -> bool:
    """True when a grep stage starts each match with a file path: a recursive
    or with-filename flag, or two or more file operands. ``-n`` alone prints
    only a line number, so a content filter after it is sound."""
    if stage[0] != "grep":
        return False
    if "--no-filename" in stage[1:] or "h" in _short_flags(stage):
        return False
    if _PREFIX_LONG_FLAGS.intersection(stage[1:]):
        return True
    if any(letter in _short_flags(stage) for letter in _PREFIX_SHORT_FLAGS):
        return True
    return _file_operand_count(stage) >= 2


def _is_inverted(stage) -> bool:
    return "v" in _short_flags(stage) or "--invert-match" in stage[1:]


def _exclusion_over_prefix(stages):
    """The pattern of the first inverting grep stage that follows a stage that
    starts each match with a file path, or None. A pattern anchored at the
    start of the line, at the colon that ends the path, or past the ``:NN:``
    prefix is exempt."""
    prefixed = False
    for stage in stages:
        if stage[0] != "grep":
            continue
        if prefixed and _is_inverted(stage):
            pattern, _target = _grep_pattern_and_target(stage)
            if pattern is not None and not _PREFIX_ANCHORED_RE.search(pattern):
                return pattern
        if _prints_prefix(stage):
            prefixed = True
    return None


def _check37_exclusion_over_path_prefix(context) -> list:
    """Check 37 -- an inverting grep follows a grep that starts each match with
    a file path, and its pattern is not anchored past that path
    (gate-instrument-proof-obligations.md §10, the extractor-pitfalls table).
    ``grep -rn X | grep -v NAME`` also drops every file whose path carries
    NAME, so the sweep reports fewer problems and reads as better. A path
    prefix comes from a recursive or with-filename flag, or from two or more
    file operands. A pattern that starts with ``^`` or ``:``, ends with ``:``,
    or carries ``:[0-9]`` or ``:\\d`` is exempt.
    Heuristic, so WARNING: it reports and never gates alone.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or _is_wrong(command):
            continue
        tokens = _tokens(command.command)
        if not tokens:
            continue
        pattern = next(
            (found for stages in _pipelines(tokens)
             if (found := _exclusion_over_prefix(stages)) is not None),
            None,
        )
        if pattern is None:
            continue
        findings.append(_finding(
            check=37, severity=SEVERITY_WARNING, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This pipeline filters prefixed grep output with an exclusion on {pattern!r}. "
                "The prefix starts with the file path, so the exclusion also drops every other "
                "file whose path carries the name. Anchor past the prefix with :[0-9]+:.*TOKEN, "
                "match executable syntax, or exclude by exact file path, and require the repaired "
                "form to return more matches than the broken one "
                "(gate-instrument-proof-obligations.md, \"Extractor pitfalls\")"
            ),
        ))
    return findings


def _check38_split_slice_as_parser(context) -> list:
    """Check 38 -- a verification command indexes the result of ``.split(...)``,
    which uses string slicing as a parser
    (gate-instrument-proof-obligations.md §10, the extractor-pitfalls table).
    The slice stops at the first delimiter that belongs to something else, so a
    count taken from it can be a third of the true count. Heuristic, so
    WARNING: it reports and never gates alone.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or _is_wrong(command):
            continue
        match = _SPLIT_INDEX_RE.search(command.command)
        if match is None:
            continue
        findings.append(_finding(
            check=38, severity=SEVERITY_WARNING, file=command.file, line=command.line,
            command=command.command,
            message=(
                f"This command slices text with {match.group(0)!r} and uses the piece as a parser. "
                "The slice stops at the first delimiter that belongs to something else. "
                "Parse with ast.parse or the format's real parser, and run the gate once on a "
                "known-good and a known-bad input "
                "(gate-instrument-proof-obligations.md, \"Extractor pitfalls\")"
            ),
        ))
    return findings


def _plan_files(context):
    """Yield ``(rel, path, lines)`` for each markdown file outside an ``Outputs``
    folder, with carriage returns removed. A file under ``Outputs`` holds a
    produced record, not a spec, so it is skipped."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        if "Outputs" in rel.split("/")[:-1]:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        yield rel, path, [raw.rstrip("\r") for raw in text.split("\n")]


def _check63_count_pin_without_instrument(context) -> list:
    """Check 63 -- a checkbox criterion pins a code symbol's member count and no
    instrument sits on the line (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md,
    "A pinned count names the artifact and version it was read from"). The
    input is every unfenced, non-WRONG line of a markdown file outside an
    ``Outputs`` folder. The line is satisfied by ``len(``, ``wc -l``, a count
    call or the word ``measured``. A subject that ends in a file extension is
    skipped. Cannot see: a count outside a checkbox, a prose subject and a
    reading of the wrong artifact. Heuristic, so WARNING.
    """
    findings = []
    for rel, _path, lines in _plan_files(context):
        for number, line in _unfenced(lines):
            if "WRONG" in line:
                continue
            match = _COUNT_PIN_RE.search(line)
            if match is None or _FILE_EXTENSION_RE.search(match.group(1)):
                continue
            if _COUNT_INSTRUMENT_RE.search(line):
                continue
            findings.append(_finding(
                check=63, severity=SEVERITY_WARNING, file=rel, line=number,
                command=line.strip(),
                message=(
                    f"This criterion pins a member count for `{match.group(1)}` and shows no "
                    "instrument on the line. A count copied from a comment or from memory can "
                    "differ from the real structure. Measure it with len(), wc or a count call. "
                    "Write the artifact, the version and the date beside the number "
                    "(measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md, "
                    "\"A pinned count names the artifact and version it was read from\")"
                ),
            ))
    return findings


def _check64_two_sided_spec_without_removed_cell(context) -> list:
    """Check 64 -- a spec line names ``changed`` and ``added`` and never the
    removed cell. A diff over two sides has a third cell: the old side is
    present and the new side is absent. The input is every unfenced, non-WRONG
    line of a task file and of an Orchestration file outside an ``Outputs``
    folder. The line is satisfied by ``removed``, ``deleted`` or ``disappear``.
    Cannot see: other outcome words, a matrix written as a table and a spec
    keyed on the container and not the value. Heuristic, so WARNING.
    """
    findings = []
    for rel, path, lines in _plan_files(context):
        if "orchestration" not in path.name.lower() and not _is_task_file(path):
            continue
        for number, line in _unfenced(lines):
            if "WRONG" in line or _TWO_SIDED_RE.search(line) is None:
                continue
            if _REMOVED_CELL_RE.search(line):
                continue
            findings.append(_finding(
                check=64, severity=SEVERITY_WARNING, file=rel, line=number,
                command=line.strip(),
                message=(
                    "This spec line names `changed` and `added` and never the removed cell. "
                    "A diff over two sides also has the case where the old side is present "
                    "and the new side is absent. Code written from this line may emit nothing "
                    "for an asset that disappeared. State what the code emits for that case, "
                    "or state that it emits nothing"
                ),
            ))
    return findings


def _check65_first_write_placement_without_write_list(context) -> list:
    """Check 65 -- a task line places a step before the first write, and the
    file lists no writes in order. An earlier phase may already write files, so
    a gate placed before "the first write" runs late. The input is every
    unfenced, non-WRONG line of a task file. The satisfier is the words "writes
    in order" anywhere in the file. It fires once for each such line. Cannot
    see: whether the list is complete, a hand-off the author missed and an
    unbound placeholder on a delegating route. Heuristic, so WARNING.
    """
    findings = []
    for rel, lines in _task_files(context):
        if _WRITES_IN_ORDER_RE.search("\n".join(lines)):
            continue
        for number, line in _unfenced(lines):
            if "WRONG" in line or _FIRST_WRITE_RE.search(line) is None:
                continue
            findings.append(_finding(
                check=65, severity=SEVERITY_WARNING, file=rel, line=number,
                command=line.strip(),
                message=(
                    "This line places a step before the first write, and the file lists no "
                    "writes in order. An earlier phase may already write files, so the step "
                    "can run late. List every write in execution order, hand-offs included, "
                    "under the words \"writes in order\""
                ),
            ))
    return findings


def _count_after(tokens, index) -> bool:
    """True when ``tokens[index]`` is a plain integer."""
    return index < len(tokens) and _INTEGER_RE.match(tokens[index]) is not None


def _literal_count_stage(stage) -> bool:
    """True when a ``head`` or ``tail`` stage carries a literal count: ``-n N``,
    ``-nN``, ``-N``, ``-c N``, ``-cN`` or the long forms. A ``tail -n +N`` start
    offset and a ``-n -N`` negative count are not a literal count."""
    index = 1
    while index < len(stage):
        token = stage[index]
        if token == "--":
            break
        if token in ("-n", "-c", "--lines", "--bytes"):
            if _count_after(stage, index + 1):
                return True
            index += 2
            continue
        if _HEAD_TAIL_COUNT_RE.match(token):
            return True
        index += 1
    return False


def _grep_max_count(stage) -> bool:
    """True when a grep stage stops after a literal number of matches."""
    for index, token in enumerate(stage[1:], start=1):
        if token == "--":
            break
        if token in ("-m", "--max-count") and _count_after(stage, index + 1):
            return True
        if _GREP_MAX_COUNT_RE.match(token):
            return True
    return False


def _extraction_shapes(command):
    """Yield ``(kind, text, stages, position)`` for each literal extraction bound
    in a command. ``stages`` and ``position`` locate the bounded stage in its
    pipeline, and ``stages`` is None when the command does not tokenise. A
    ``head`` or ``tail`` stage counts only when another stage follows it,
    because a pipeline that ends in one is display."""
    tokens = _tokens(command.command)
    pipelines = _pipelines(tokens) if tokens else []
    for stages in pipelines:
        for position, stage in enumerate(stages):
            if _READ_SLICE_RE.search(" ".join(stage)):
                yield "slice", _READ_SLICE_RE.search(" ".join(stage)).group(0), stages, position
            elif stage[0] in ("head", "tail") and position < len(stages) - 1 and _literal_count_stage(stage):
                yield stage[0], " ".join(stage), stages, position
            elif stage[0] == "grep" and _grep_max_count(stage):
                yield "grep -m", " ".join(stage), stages, position
    if not pipelines:
        match = _READ_SLICE_RE.search(command.command)
        if match is not None:
            yield "slice", match.group(0), None, 0


def _length_count_follows(stages, position) -> bool:
    """True when the stage right after ``position`` is the last stage and is
    ``wc -l`` or ``wc -c``. A stage between the cut and the ``wc`` makes the
    ``wc`` count the filtered output, so it says nothing about the cut."""
    if stages is None or position + 2 != len(stages):
        return False
    after = stages[position + 1]
    return after[0] == "wc" and (
        any(letter in _short_flags(after) for letter in "lc")
        or _LENGTH_COUNT_LONG_OPTIONS.intersection(after[1:]) != set()
    )


def _asserts_parsed_length(command, stages, position) -> bool:
    """True when a ``len(...)`` comparison in the bounded stage's own pipeline,
    or in the command's note, asserts the length of what it parsed, when a
    ``wc`` counts the cut's own output, or when the command, its comment or its
    annotation carries a ``parsed length`` note. A ``len(...)`` comparison in
    another pipeline of the same command does not clear this bound."""
    notes = f"{command.comment} {command.annotation}"
    scope = command.command if stages is None else " ".join(" ".join(stage) for stage in stages)
    return bool(
        _LENGTH_COMPARISON_RE.search(f"{scope} {notes}")
        or _PARSED_LENGTH_NOTE_RE.search(f"{command.command} {notes}")
        or _length_count_follows(stages, position)
    )


def _read_scan_lines(lines):
    """Yield the index of each line inside a Verification Commands or Success
    Criteria section. A heading is read only outside a fenced block, and a
    section ends at the next heading of its own level or a higher one."""
    level = None
    for number, line, fenced in _fence_marked(lines):
        heading = None if fenced else _HEADING_LINE_RE.match(line)
        if level is not None and heading and len(heading.group(1)) <= level:
            level = None
        if level is None:
            section = None if fenced else _READ_SCAN_SECTION_RE.match(line)
            if section:
                level = len(section.group(1))
            continue
        yield number - 1


def _read_limit_calls(context):
    """Yield ``(file, line, text, notes)`` for every native ``Read`` call whose
    arguments carry a literal ``limit``, in the Verification Commands and
    Success Criteria sections of a task file. A paged read in another section,
    such as an Execution Step, is an instruction and is not read. The line after
    the call is part of its notes, because a pre-edit comment sits there."""
    for rel, lines in _task_files(context):
        for index in _read_scan_lines(lines):
            line = lines[index]
            if "WRONG" in line:
                continue
            call = _READ_LIMIT_RE.search(line)
            if call is None:
                continue
            following = lines[index + 1] if index + 1 < len(lines) else ""
            yield rel, index + 1, call.group(0), f"{line} {following}"


def _check68_literal_extraction_bound_without_length_assertion(context) -> list:
    """Check 68 -- a verification command cuts what it reads at a literal count
    and asserts no parsed length (gate-input-set-and-compared-window.md, the
    section "An Extraction Is Bounded by Markers and Asserts Its Parsed Length").
    A byte slice or a ``head`` bound returns fewer
    columns as the file grows, so the assertion over the cut passes more readily
    and reports nothing. A bound here is a slice with a literal integer stop on a
    read result (``.read()[:9000]``), a ``head`` or ``tail`` stage with a literal
    count that feeds another stage, ``grep -m N`` or ``--max-count=N``, and a
    native ``Read`` call with ``limit=N`` in the Verification Commands or
    Success Criteria section of a task file. ``len(...)`` in a comparison in the
    pipeline that holds the bound, a ``parsed length`` note on the command or its
    annotation, or ``wc -l``, ``wc -c``, ``wc --lines`` or ``wc --bytes`` as the
    last stage directly after the bounded stage clears it. A WRONG label is read
    from the command's note or annotation, never from its pattern argument. A stage between the cut and the ``wc`` does not, because the
    ``wc`` then counts the filtered output. A pipeline whose last stage
    is ``head`` or ``tail`` is display, and a slice on something that is not a
    read result is not an extraction. Cannot see: a bound held in a variable, a
    length asserted in a later command and a count that is correct by design.
    Heuristic, so WARNING: it reports and never gates alone.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or _is_wrong(command):
            continue
        shape = next(
            (found for found in _extraction_shapes(command)
             if not _asserts_parsed_length(command, found[2], found[3])),
            None,
        )
        if shape is None:
            continue
        findings.append(_finding(
            check=68, severity=SEVERITY_WARNING, file=command.file, line=command.line,
            command=command.command,
            message=_EXTRACTION_BOUND_MESSAGE.format(shape=f"{shape[0]} bound {shape[1]!r}"),
        ))
    for file, line, text, notes in _read_limit_calls(context):
        if _LENGTH_COMPARISON_RE.search(notes) or _PARSED_LENGTH_NOTE_RE.search(notes):
            continue
        findings.append(_finding(
            check=68, severity=SEVERITY_WARNING, file=file, line=line, command=text,
            message=_EXTRACTION_BOUND_MESSAGE.format(shape=f"Read bound {text!r}"),
        ))
    return findings


CHECKS = [
    _check30_gate_anchor_without_verified_marker,
    _check31_status_gate_names_no_artifact,
    _check32_file_producing_task_without_size_gate,
    _check33_writer_command_without_scratch_target,
    _check35_absence_gate_over_mandated_prose,
    _check36_digitless_identifier_class,
    _check37_exclusion_over_path_prefix,
    _check38_split_slice_as_parser,
    _check63_count_pin_without_instrument,
    _check64_two_sided_spec_without_removed_cell,
    _check65_first_write_placement_without_write_list,
    _check68_literal_extraction_bound_without_length_assertion,
]
