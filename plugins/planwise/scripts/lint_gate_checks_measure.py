#!/usr/bin/env python3
"""Lint checks that read the measurement rules' text in task files.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check takes
the lint context duck-typed and builds its finding with the same six keys the
linter's ``make_finding`` writes. The sibling modules ``lint_gate_checks_verify``,
``lint_gate_checks_commands`` and ``lint_gate_checks_dispatch`` supply the task-file
reader, the command tokeniser and the Required Context row reader.

Each docstring states the predicate, the input, the severity and what the check
cannot see. Exit contract at the linter level: a finding at ERROR exits 2, a finding
at WARNING or UNCERTAIN exits 1 and no finding exits 0.

``measure_summary`` returns how many Required Context rows Check 48 examined,
skipped and measured, so a caller can tell an empty input from a clean one.
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from lint_gate_checks_commands import (
    _command_pipelines,
    _diff_parts,
    _git_subcommand,
    _grep_pattern_and_target,
    _is_count_stage,
)
from lint_gate_checks_dispatch import _required_context_rows
from lint_gate_checks_verify import (
    SEVERITY_ERROR,
    SEVERITY_UNCERTAIN,
    SEVERITY_WARNING,
    _finding,
    _task_files,
)
from measure_files import measure_files

# --- Check 48: a Required Context size figure against a fresh reading (measurement-discipline.md §8.1) ---
_TOLERANCE = 0.20
_MODEL = "opus"
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SLICE_WORDS_RE = re.compile(r"offset|limit|by heading|§|\bonly\b|slice", re.IGNORECASE)
_UNRESOLVED_CHARS_RE = re.compile(r"[{}<>*?]")

# --- Checks 49 and 50: diff gates (measurement-discipline.md §8.7) ---
_MATCHERS = frozenset({"grep", "egrep", "fgrep", "wc"})
_BASE_OPERAND_RE = re.compile(r"\$\{?[A-Za-z0-9_]*BASE\b\}?|<[A-Za-z0-9_]*BASE>")
_BASE_TOKEN_RE = re.compile(r"^(?:\$\{?[A-Za-z0-9_]*BASE\}?|<[A-Za-z0-9_]*BASE>)$")
_LITERAL_BASE_RE = re.compile(r"\{BASE\}")
_CAT_FILE_RE = re.compile(r"cat-file\s+-\w*e\b")


def _is_whole_file_cell(file_cell: str, kib_cell: str) -> bool:
    """True when the row names one file with no section qualifier. The plan's own
    spelling is ``file`` followed by ``whole`` or an empty remainder."""
    spans = _CODE_SPAN_RE.findall(file_cell)
    if len(spans) != 1 or _SLICE_WORDS_RE.search(kib_cell):
        return False
    remainder = _CODE_SPAN_RE.sub("", file_cell, count=1).strip(" —–-:()")
    if not remainder:
        return True
    return remainder.lower().startswith("whole") and not _SLICE_WORDS_RE.search(remainder)


def _stated_number(cell: str):
    match = _NUMBER_RE.search(cell)
    if match is None:
        return None
    return float(match.group(0).replace(",", ""))


def _stated_tokens(cell: str):
    """A ``~Tokens`` cell as a count: ``~10.1K`` reads 10100, ``~10,075`` reads 10075."""
    value = _stated_number(cell)
    if value is None:
        return None
    return value * 1000 if re.search(r"\d\s*[Kk]\b", cell) else value


def _column(header, word: str):
    for index, cell in enumerate(header):
        if word in cell.lower():
            return index
    return None


def _project_root(start: Path):
    """The nearest directory at or above ``start`` that holds ``cloned-repos`` or
    ``planwise/config.yaml``, else None."""
    for base in (start, *start.parents):
        if (base / "cloned-repos").is_dir() or (base / "planwise" / "config.yaml").is_file():
            return base
    return None


def _resolve(task_dir: Path, rel: str):
    """Resolve a cited path against the task file's folder, then the project root."""
    candidate = Path(rel)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    bases = [task_dir]
    root = _project_root(task_dir.resolve())
    if root is not None:
        bases.append(root)
    for base in bases:
        if (base / rel).is_file():
            return base / rel
    return None


def _size_rows(context):
    """Yield ``(rel, number, line, path_text, resolved, stated_kib, stated_tokens)`` for
    each whole-file Required Context row that states a KiB or ~Tokens value.
    ``resolved`` is None when the path does not resolve to a file."""
    root = Path(context.plan_root)
    for rel, lines in _task_files(context):
        task_dir = (root / rel).parent
        for number, line, cells, header in _required_context_rows(lines):
            file_index = _column(header, "file")
            file_index = 0 if file_index is None else file_index
            kib_index = _column(header, "kib")
            tok_index = _column(header, "token")
            if file_index >= len(cells):
                continue
            kib_cell = cells[kib_index] if kib_index is not None and kib_index < len(cells) else ""
            tok_cell = cells[tok_index] if tok_index is not None and tok_index < len(cells) else ""
            stated_kib = _stated_number(kib_cell)
            stated_tokens = _stated_tokens(tok_cell)
            if stated_kib is None and stated_tokens is None:
                continue
            if not _is_whole_file_cell(cells[file_index], kib_cell):
                continue
            path_text = _CODE_SPAN_RE.search(cells[file_index]).group(1).strip()
            resolved = None
            if not _UNRESOLVED_CHARS_RE.search(path_text):
                resolved = _resolve(task_dir, path_text)
            yield rel, number, line, path_text, resolved, stated_kib, stated_tokens


def measure_summary(context) -> dict:
    """Return Check 48's subject counts: rows ``examined``, ``skipped`` (unresolved)
    and ``measured``, and the printable ``line``. ``measured`` of 0 with rows examined
    reads as NOT CHECKED."""
    examined = skipped = 0
    for _rel, _n, _line, _text, resolved, _kib, _tokens in _size_rows(context):
        examined += 1
        if resolved is None:
            skipped += 1
    measured = examined - skipped
    return {
        "examined": examined,
        "skipped": skipped,
        "measured": measured,
        "line": f"rows examined {examined}, skipped {skipped} (unresolved), measured {measured}",
    }


def _check48_required_context_size_mismatch(context) -> list:
    """Check 48 -- a Required Context row that names one whole file and states a
    ``KiB`` or ``~Tokens`` value disagrees with a fresh ``measure_files`` reading by
    more than 20 % (measurement-discipline.md §8.1). The ``KiB`` field is compared
    first because it holds for every model, and ``~Tokens`` only when ``KiB`` is
    empty or ``—``, against the opus estimate. A whole-file row has no section
    qualifier, ``offset``, ``limit`` or heading selector, and its spelling is the
    path followed by ``whole`` or nothing. A path resolves against the task file's
    folder first, then the nearest directory holding ``cloned-repos`` or
    ``planwise/config.yaml``. The check writes ``rows examined N, skipped M
    (unresolved), measured K`` to stderr, and a run that measured nothing
    after examining rows reports one UNCERTAIN finding that reads NOT CHECKED, never
    clean. Advisory, so WARNING. It cannot see a section-slice row (out of reach by
    design), a row in a file whose size changes after the task is written, a path
    that resolves nowhere (counted as skipped), or a figure in prose.
    """
    findings = []
    examined = skipped = 0
    for rel, number, line, path_text, resolved, stated_kib, stated_tokens in _size_rows(context):
        examined += 1
        if resolved is None:
            skipped += 1
            continue
        result = measure_files([str(resolved)], model=_MODEL)
        if not result["files"]:
            skipped += 1
            continue
        fresh = result["files"][0]
        if stated_kib is not None:
            stated, actual, unit = stated_kib, fresh["bytes"] / 1024, "KiB"
        else:
            stated, actual, unit = stated_tokens, float(fresh["tokens"]), "tokens"
        if abs(stated - actual) <= _TOLERANCE * max(actual, 1e-9):
            continue
        findings.append(_finding(
            check=48, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
            message=(
                f"This Required Context row states {stated:g} {unit} for {path_text!r}, and a "
                f"fresh measurement reads {actual:.1f} {unit}, a miss above 20 %. A stale size "
                "misleads the dispatch budget. Re-take the figure with measure_files and "
                "stamp it (measurement-discipline.md, §8.1)"
            ),
        ))
    measured = examined - skipped
    if examined:
        print(
            f"Check 48: rows examined {examined}, skipped {skipped} (unresolved), measured {measured}",
            file=sys.stderr,
        )
    if examined and measured == 0:
        findings.append(_finding(
            check=48, severity=SEVERITY_UNCERTAIN, file="(all task files)", line=0,
            command=f"rows examined {examined}, skipped {skipped} (unresolved), measured 0",
            message=(
                "NOT CHECKED. Check 48 examined whole-file Required Context rows and resolved "
                "none, so no size figure was measured. Run the linter where the cited paths "
                "resolve from the task file folder or the project root"
            ),
        ))
    return findings


def _task_commands(context) -> dict:
    """Map ``(file, block)`` to the commands of a task file, in file order."""
    task_names = {rel for rel, _lines in _task_files(context)}
    grouped: dict = {}
    for command in context.commands:
        if command.file in task_names and "WRONG" not in command.command:
            grouped.setdefault((command.file, command.block), []).append(command)
    return grouped


def _stage_is_diff(stage) -> bool:
    parts = _diff_parts(stage)
    return parts is not None


def _diff_piped_to_matcher(command) -> bool:
    for stages in _command_pipelines(command):
        for index, stage in enumerate(stages):
            if _stage_is_diff(stage) and any(later[0] in _MATCHERS for later in stages[index + 1:]):
                return True
    return False


def _carries_count(commands) -> bool:
    """True when a command of the block holds a ``status --porcelain`` untracked count
    or a ``--name-only`` file count: a diff or status stage followed by a count stage."""
    for command in commands:
        for stages in _command_pipelines(command):
            for index, stage in enumerate(stages):
                later = stages[index + 1:]
                _repo, at = _git_subcommand(stage)
                if at is None:
                    continue
                if stage[at] == "status" and "--porcelain" in stage and any(
                    s[0] in _MATCHERS for s in later
                ):
                    return True
                if stage[at] == "diff" and "--name-only" in stage and any(
                    _is_count_stage(s) for s in later
                ):
                    return True
    return False


def _check49_diff_matcher_without_counts(context) -> list:
    """Check 49 -- a gate block pipes ``git diff`` into a matcher (``grep`` or ``wc``) and
    the same block carries neither a ``git status --porcelain`` untracked count nor a
    ``--name-only`` file count (measurement-discipline.md §8.7). The matcher then
    counts lines of a diff that never lists an untracked file and never says how many
    files the diff spanned, so an empty result reads as clean. A block is the Before
    or After group of one task file. ERROR. It overlaps Check 18 and Check 21 only
    on the same line, and it reports what neither reports: the missing counts. It
    cannot see a count held in a different block, a count in prose, or a diff built
    through a shell variable or script.
    """
    findings = []
    for commands in _task_commands(context).values():
        if _carries_count(commands):
            continue
        for command in commands:
            if not _diff_piped_to_matcher(command):
                continue
            findings.append(_finding(
                check=49, severity=SEVERITY_ERROR, file=command.file, line=command.line,
                command=command.command,
                message=(
                    "This gate pipes git diff into a matcher and its block holds no git status "
                    "--porcelain untracked count and no --name-only file count. An untracked "
                    "file never reaches the diff, so an empty result reads as clean. Add both "
                    "counts to the block (measurement-discipline.md, §8.7)"
                ),
            ))
    return findings


def _base_diff_command(command) -> bool:
    for stages in _command_pipelines(command):
        for stage in stages:
            parts = _diff_parts(stage)
            if parts is not None and any(_BASE_TOKEN_RE.match(op) for op in parts[1]):
                return True
    return False


def _check50_base_gate_unresolved_or_uncounted(context) -> list:
    """Check 50 -- a gate that pins a base commit is unguarded, in one of two ways
    (measurement-discipline.md §8.7). (a) The task file uses a ``$..._BASE`` or
    ``<..._BASE>`` operand and holds no ``cat-file -e`` resolve step, or a command line
    holds the literal placeholder ``{BASE}``: the base may not resolve, and a diff
    against an unresolved base reads empty. (b) A block holds a ``$..._BASE`` diff and no
    spanned-file count (``--name-only`` piped to a count, or a ``status --porcelain``
    count), so a diff that spans nothing looks like a clean one. A diff already
    reported by Check 49 is not reported again. Check 21 reports an unpinned or
    unscoped diff and Check 29 reports a base nobody pins, so neither is repeated
    here. WARNING. It cannot see a resolve step in a file other than the task file, a
    base spelled without ``BASE`` in its name, or a count the block gets from a
    script.
    """
    findings = []
    grouped = _task_commands(context)
    by_file: dict = {}
    for (file, _block), commands in grouped.items():
        by_file.setdefault(file, []).extend(commands)
    resolve_text = {}
    for commands in by_file.values():
        for command in commands:
            if command.file not in resolve_text:
                try:
                    resolve_text[command.file] = command.path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    resolve_text[command.file] = ""
    for file, commands in by_file.items():
        resolved = _CAT_FILE_RE.search(resolve_text[file]) is not None
        reported_operand = False
        for command in commands:
            if _LITERAL_BASE_RE.search(command.command):
                findings.append(_finding(
                    check=50, severity=SEVERITY_WARNING, file=file, line=command.line,
                    command=command.command,
                    message=(
                        "This command line holds the literal placeholder {BASE}. No dispatcher "
                        "fills it, so the gate runs against nothing. Name the recorded base "
                        "variable and resolve it first (measurement-discipline.md, §8.7)"
                    ),
                ))
            elif not resolved and not reported_operand and _BASE_OPERAND_RE.search(command.command):
                reported_operand = True
                findings.append(_finding(
                    check=50, severity=SEVERITY_WARNING, file=file, line=command.line,
                    command=command.command,
                    message=(
                        "This gate uses a recorded base operand and the task file holds no "
                        "cat-file -e step that proves the base resolves. A diff against an "
                        "unresolved base reads empty. Add git cat-file -e <base> before the "
                        "first diff (measurement-discipline.md, §8.7)"
                    ),
                ))
    for commands in grouped.values():
        if _carries_count(commands):
            continue
        for command in commands:
            if _base_diff_command(command) and not _diff_piped_to_matcher(command):
                findings.append(_finding(
                    check=50, severity=SEVERITY_WARNING, file=command.file, line=command.line,
                    command=command.command,
                    message=(
                        "This base-pinned diff gate sits in a block with no spanned-file count. "
                        "A diff that spans no file reads like a clean one. Add git diff "
                        "--name-only piped to wc -l, or a git status --porcelain count, to the "
                        "block (measurement-discipline.md, §8.7)"
                    ),
                ))
                break
    return findings


# --- Check 51: a character-counted operand in a byte identity (measure-aggregate-provenance.md §5) ---
_BYTE_EQUALITY_RE = re.compile(r"\s-eq\s|==|\bequals?\b|\bbytes?\b", re.IGNORECASE)
_CHAR_OPERAND_RES = (
    ("awk length", re.compile(r"\bawk\b[^|]*\blength\b")),
    ("${#var}", re.compile(r"\$\{#[A-Za-z_]\w*\}")),
    ("len() over a decoded string", re.compile(r"\blen\(")),
)
_BYTE_READ_RE = re.compile(r"rb['\"]|\.encode\(|read_bytes\(|\bbytes\(|\bwc\s+-c\b")

# --- Check 52: a character class right after the diff sign (gate-predicate-discrimination.md §6) ---
_SIGN_CLASS_RE = re.compile(
    r"\^(?:\\?\+\[\^\\?\+\]|\\?-\[\^\\?-\]|\[[+\-]{2}\]\[\^\\?[+\-]{1,2}\])"
)
_DIFF_WORD_RE = re.compile(r"\bdiff\b", re.IGNORECASE)

# --- Check 53: a blob byte count against a checkout pin (measurement-discipline.md §8.12) ---
_BLOB_BYTES_RE = re.compile(r"\bgit\b[^|;&]*\bshow\s+[^|;&\s]*[^|;&\s:]:[^|;&\s]+[^|;&]*\|\s*wc\s+-\w*c\b")
_BLOB_LINES_RE = re.compile(r"\bgit\b[^|;&]*\bshow\s+[^|;&\s]*:[^|;&\s]+[^|;&]*\|\s*wc\s+-\w*l\b")
_CHECKOUT_BYTES_RES = (
    re.compile(r"(?<!\|)(?<!\| )\bwc\s+-c\s+[^\s|;&)<-][^\s|;&)]*"),
    re.compile(r"\bwc\s+-c\s*<\s*[^\s|;&)]+"),
)
_NUMERIC_PIN_RE = re.compile(r"(?:\s-eq\s|==|!=|\s-ne\s)\s*\"?\d{3,}")


def _check51_char_count_in_byte_identity(context) -> list:
    """Check 51 -- a gate block asserts byte equality (``-eq``, ``==``, ``equals`` or
    the word ``byte``) and a command in it takes an operand from ``awk`` ``length``,
    ``${#var}`` or ``len(`` over a decoded string (measure-aggregate-provenance.md §5).
    Those count characters, so a file with multi-byte characters reads a deficit that
    looks like lost content. A command is read even when it holds a brace, because the
    operand forms carry one (``{print length($0)}``, ``${#var}``). A ``len(`` in a command that also reads raw bytes
    (``rb``, ``.encode(``, ``wc -c``) is not reported. One finding per offending
    command. ERROR. It cannot see an operand a script computes, a character count that
    is meant as a character count, or an equality stated only in prose.
    """
    findings = []
    for commands in _task_commands(context).values():
        if not any(_BYTE_EQUALITY_RE.search(c.command) for c in commands):
            continue
        for command in commands:
            for label, pattern in _CHAR_OPERAND_RES:
                if not pattern.search(command.command):
                    continue
                if label.startswith("len") and _BYTE_READ_RE.search(command.command):
                    continue
                findings.append(_finding(
                    check=51, severity=SEVERITY_ERROR, file=command.file, line=command.line,
                    command=command.command,
                    message=(
                        f"This command takes an operand from {label}, which counts characters, "
                        "and its block asserts byte equality. A file with multi-byte characters "
                        "reads a false deficit. Take every operand from one byte instrument: "
                        "wc -c or a raw-bytes read "
                        "(measure-aggregate-provenance.md, §5)"
                    ),
                ))
                break
    return findings


def _check52_character_class_after_diff_sign(context) -> list:
    """Check 52 -- a gate counts or filters diff lines with a character class right
    after the sign: ``'^-[^-]'``, ``'^+[^+]'`` or ``'^[+-][^+-]'`` (the escaped
    ``\\+`` and ``\\-`` spellings too). The class removes the ``+++`` and ``---``
    headers and also every added or removed line that starts with a hyphen, such as a
    bullet. The repair anchors the filter on the sign alone and removes the headers by
    name (gate-predicate-discrimination.md §6). A pattern with ``\\+\\+`` in basic
    syntax is Check 24's and is not reported here. The command must name ``diff``.
    ERROR. It cannot see a pattern built in a variable, an alternation that hides the
    form, or a filter in a script.
    """
    findings = []
    for commands in _task_commands(context).values():
        for command in commands:
            if not _DIFF_WORD_RE.search(command.command):
                continue
            hit = None
            for stages in _command_pipelines(command):
                for stage in stages:
                    if stage[0] not in {"grep", "egrep"}:
                        continue
                    pattern, _target = _grep_pattern_and_target(stage)
                    if pattern and _SIGN_CLASS_RE.search(pattern):
                        hit = pattern
                        break
                if hit:
                    break
            if hit is None:
                continue
            findings.append(_finding(
                check=52, severity=SEVERITY_ERROR, file=command.file, line=command.line,
                command=command.command,
                message=(
                    f"The diff filter {hit!r} puts a character class right after the sign. It "
                    "drops the header lines and every added or removed line that starts with a "
                    "hyphen, such as a bullet. Anchor the filter on the sign alone and remove "
                    "the +++ and --- headers by name: grep -E '^[+-]' | grep -vE '^(\\+\\+\\+|---)' "
                    "(gate-predicate-discrimination.md, §6)"
                ),
            ))
    return findings


def _check53_blob_bytes_against_checkout_pin(context) -> list:
    """Check 53 -- a gate takes ``git show <rev>:<path> | wc -c`` and compares it with a
    checkout byte pin, and its block holds no ``git show <rev>:<path> | wc -l`` term
    (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.12). Under
    ``core.autocrlf`` the blob holds LF and the checkout holds CRLF, so the two counts
    differ by the line count and the gap reads as lost content. A checkout pin is a
    ``wc -c`` on a file operand in the block, or a ``-eq`` or ``==`` against a literal
    of three digits or more in the same command. One finding per blob byte count.
    WARNING. It cannot see a pin held in prose, a pin in another block, or blob bytes
    compared with blob bytes by a script.
    """
    findings = []
    for commands in _task_commands(context).values():
        if any(_BLOB_LINES_RE.search(c.command) for c in commands):
            continue
        checkout = any(
            pattern.search(c.command)
            for c in commands
            if not _BLOB_BYTES_RE.search(c.command)
            for pattern in _CHECKOUT_BYTES_RES
        )
        for command in commands:
            if not _BLOB_BYTES_RE.search(command.command):
                continue
            if not (checkout or _NUMERIC_PIN_RE.search(command.command)):
                continue
            findings.append(_finding(
                check=53, severity=SEVERITY_WARNING, file=command.file, line=command.line,
                command=command.command,
                message=(
                    "This gate reads blob bytes with git show and compares them with a checkout "
                    "byte pin, and the block adds no git show | wc -l term. Under core.autocrlf "
                    "the two differ by the line count. Add the blob line count, or take both "
                    "sides from the checkout "
                    "(measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md, §8.12)"
                ),
            ))
    return findings


CHECKS = [
    _check48_required_context_size_mismatch,
    _check49_diff_matcher_without_counts,
    _check50_base_gate_unresolved_or_uncounted,
    _check51_char_count_in_byte_identity,
    _check52_character_class_after_diff_sign,
    _check53_blob_bytes_against_checkout_pin,
]
