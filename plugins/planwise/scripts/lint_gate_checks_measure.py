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

Checks 61 and 62 read the first ``**Output:**`` line of each task file and measure
every file it names with ``measure_files`` at its default ratio. A file is near-cap
at 0.9 of ``READ_TOKEN_WARN``, ``READ_LINE_CAP`` or ``READ_BYTE_WARN``.

- Check 61, predicate: a task names a near-cap file on its Output line and no line
  of the task holds ``measure_files``, that file's basename and ``HALT``. Input: the
  task file and the file on disk. Severity: WARNING. It cannot see a path the task
  edits but does not list on its Output line, a measurement written in another form
  than a ``measure_files`` line, or a ceiling figure that is itself wrong.
- Check 62, predicate: a near-cap file is named on the Output lines of two or more
  task files in one folder and no Orchestration file there holds a budget line for it,
  or the budget line's headroom is not its cap minus its live figure, or its ``<= +n``
  terms do not sum below the headroom. Input: the task files, the Orchestration files
  of that folder and the file on disk. Severity: WARNING. It cannot see a stale live
  figure on a budget line.

Each of the two writes ``output paths examined E, resolved R, near-cap K`` to stderr
when a task file names at least one Output path.

Checks 69 to 71 read the unfenced lines of task files that hold no ``WRONG`` label. They
measure nothing, so each one reads only the plan text.

- Check 69, predicate: a checkbox criterion holds a ceiling word and a size figure, and
  holds none of ``guards:``, ``estimat`` and ``not a gate`` outside its code spans; a
  figure that equals a Read gate is silent. Input: task files. Severity: WARNING. It cannot
  see a ceiling outside a checkbox line, or a ``guards:`` label that names a limit which
  does not exist.
- Check 70, predicate: an Output line declares a lettered sibling Part, ``declared ...
  sibling`` or ``sibling ... only if``, and no prose line of the task holds ``re-measure``
  and ``repeat``. Input: task files. Severity: WARNING. It cannot see whether the count was
  re-priced from the measured inputs.
- Check 71, predicate: a line bounds how far a ``cost`` or ``load`` rises, and does not
  name planned additions in a file that states per-file or per-rule deltas. Input: task
  files. Severity: WARNING. It cannot see an addition the exclusion list omits, or a bound
  worded without ``cost`` or ``load``.
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
from lint_gate_checks_plan import _output_paths
from lint_gate_checks_verify import (
    SEVERITY_ERROR,
    SEVERITY_UNCERTAIN,
    SEVERITY_WARNING,
    _finding,
    _task_files,
    _unfenced,
)
from measure_files import measure_files
from read_limits import (
    READ_BYTE_WARN,
    READ_FILE_BYTE_CAP,
    READ_LINE_CAP,
    READ_PAGE_CAP_TOKENS,
    READ_TOKEN_WARN,
)

# --- Check 48: a Required Context size figure against a fresh reading (measurement-discipline.md §8.1) ---
_TOLERANCE = 0.20
_MODEL = "opus"
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SLICE_WORDS_RE = re.compile(r"offset|limit|by heading|§|\bonly\b|slice", re.IGNORECASE)
_UNRESOLVED_CHARS_RE = re.compile(r"[{}<>*?]")

# --- Checks 49 and 50: diff gates (measurement-discipline.md §8.7) ---
_MATCHERS = frozenset({"grep", "egrep", "fgrep", "wc"})
# ``base`` is a whole name segment in every pattern below: the whole name, or the
# tail after ``_`` (or ``-`` in a slot), with an optional ``sha`` or ``commit``
# suffix. A name such as ``$database`` or ``{rebase}`` is no base placeholder.
_BASE_OPERAND_RE = re.compile(
    r"\$\{?(?:\w*_)?base(?:[-_](?:sha|commit))?\b\}?|<(?:[\w-]*[_-])?base(?:[-_](?:sha|commit))?>",
    re.IGNORECASE,
)
_BASE_TOKEN_RE = re.compile(
    r"^(?:\$\{?(?:\w*_)?base(?:[-_](?:sha|commit))?\}?|<(?:[\w-]*[_-])?base(?:[-_](?:sha|commit))?>)$",
    re.IGNORECASE,
)
_LITERAL_BASE_RE = re.compile(r"(?<!\$)\{(?:\w*_)?base(?:[-_](?:sha|commit))?\}", re.IGNORECASE)
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
    against an unresolved base reads empty. The lower-case spellings count too:
    ``$base_sha``, ``<base-sha>`` and ``{base_sha}``. A braced shell variable such as
    ``${BASE}`` is a variable, not a literal placeholder. (b) A block holds a ``$..._BASE`` diff and no
    spanned-file count (``--name-only`` piped to a count, or a ``status --porcelain``
    count), so a diff that spans nothing looks like a clean one. A diff already
    reported by Check 49 is not reported again. Check 21 reports an unpinned or
    unscoped diff and Check 29 reports a base nobody pins, so neither is repeated
    here. WARNING. It cannot see a resolve step in a file other than the task file, a
    base spelled without ``base`` in any case in its name, or a count the block gets from a
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
)
_LEN_CALL_RE = re.compile(r"(?<![\w.])len\(")
_BYTE_MARK_RE = re.compile(r"rb['\"]|\bb['\"]|\.encode\(|read_bytes\(|\bbytes\(")
_TEXT_RUN_RE = re.compile(r"\btext\s*=\s*True|\buniversal_newlines\s*=\s*True|\bencoding\s*=")
_STR_KEEP_TAIL_RE = re.compile(
    r"\.(?:strip|rstrip|lstrip|lower|upper|casefold|replace)\((?:[^()]|\([^()]*\))*\)$"
)
_DECODED_TAIL_RE = re.compile(r"\.read_text\((?:[^()]|\([^()]*\))*\)$|\.decode\((?:[^()]|\([^()]*\))*\)$")
_NAME_RE = re.compile(r"^([A-Za-z_]\w*)(?:\.(stdout|stderr))?$")
_MAX_BINDING_DEPTH = 2


def _balanced_arg(text, start):
    """Return the text between ``start`` and its closing parenthesis, or None."""
    depth = 1
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return None


def _decoded_operand(arg, command, depth=0):
    """True when ``arg`` traces, inside ``command``, to text decoded from bytes."""
    arg = arg.strip()
    while True:
        tail = _STR_KEEP_TAIL_RE.search(arg)
        if not tail:
            break
        arg = arg[:tail.start()]
    if _BYTE_MARK_RE.search(arg):
        return False
    if arg.endswith(".read()") and "open(" in arg:
        return True
    if arg.endswith("stdin.read()") or _DECODED_TAIL_RE.search(arg):
        return True
    named = _NAME_RE.match(arg)
    if not named or depth > _MAX_BINDING_DEPTH:
        return False
    name, stream = named.groups()
    if stream:
        return bool(_TEXT_RUN_RE.search(command))
    bound = re.search(rf"(?<![\w.]){re.escape(name)}\s*=(?!=)\s*([^;\n]+)", command)
    return bool(bound) and _decoded_operand(bound.group(1), command, depth + 1)


def _len_over_decoded_text(command):
    """True when a ``len(`` in ``command`` counts the characters of decoded text."""
    for call in _LEN_CALL_RE.finditer(command):
        arg = _balanced_arg(command, call.end())
        if arg is not None and _decoded_operand(arg, command):
            return True
    return False

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
    ``${#var}`` or ``len(`` over decoded text (measure-aggregate-provenance.md §5).
    Those count characters, so a file with multi-byte characters reads a deficit that
    looks like lost content. A command is read even when it holds a brace, because the
    operand forms carry one (``{print length($0)}``, ``${#var}``).

    A ``len(`` is reported only when its argument traces, in the same command, to
    decoded text: a text-mode ``open(...).read()``, ``.read_text(``, ``.decode(``,
    ``stdin.read()``, a ``.stdout`` or ``.stderr`` in a command that carries
    ``text=True``, ``universal_newlines=True`` or ``encoding=``, or a name bound to
    one of those. A ``wc -c`` elsewhere in the command does not exempt it. One finding
    per offending command. ERROR.

    It does not report a raw-bytes read (``rb``, ``.encode(``, or ``capture_output=True``
    without ``text=True``), an item count (a literal, a comprehension, ``findall``,
    ``split``, ``os.walk`` names), or an operand it cannot trace. It cannot see an
    operand a script computes, a character count that is meant as a character count,
    or an equality stated only in prose.
    """
    findings = []
    for commands in _task_commands(context).values():
        if not any(_BYTE_EQUALITY_RE.search(c.command) for c in commands):
            continue
        for command in commands:
            labels = [label for label, pattern in _CHAR_OPERAND_RES if pattern.search(command.command)]
            if _len_over_decoded_text(command.command):
                labels.append("len() over a decoded string")
            for label in labels:
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


# --- Checks 61 and 62: a near-cap file on a task's Output line (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.14) ---
_NEAR_CAP_FRACTION = 0.9
_OUTPUT_LINE_RE = re.compile(r"^[\s>]*(?:[-*+]\s+)?\*\*Outputs?:\*\*")
_BUDGET_TERM_RE = re.compile(r"<=\s*\+\s*(\d[\d,]*)")
_ANCHOR = "measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md"


def _is_near_cap(fresh: dict) -> bool:
    """True when a ``measure_files`` reading is at 0.9 of the token warn, the line cap
    or the byte warn."""
    return (
        fresh["tokens"] >= _NEAR_CAP_FRACTION * READ_TOKEN_WARN
        or fresh["lines"] >= _NEAR_CAP_FRACTION * READ_LINE_CAP
        or fresh["bytes"] >= _NEAR_CAP_FRACTION * READ_BYTE_WARN
    )


def _output_line_number(lines) -> int:
    for number, line in enumerate(lines, start=1):
        if _OUTPUT_LINE_RE.match(line):
            return number
    return 0


def _near_cap_outputs(context, check: int) -> list:
    """Return ``(rel, line_number, lines, path_text, resolved)`` for each near-cap file
    that resolves from the first ``**Output:**`` line of a task file, once for each task.
    The path resolves as Check 48's does. The file is measured with ``measure_files`` at
    its default ratio, the Read gate's own. The summary ``Check N: output paths examined
    E, resolved R, near-cap K`` goes to stderr when any path was examined, so a run that
    resolved nothing shows ``resolved 0`` and never reads as clean. A plan with no Output
    path prints nothing, as Check 48 does for a plan with no Required Context row."""
    root = Path(context.plan_root)
    examined = resolved_count = 0
    near_cap: dict = {}
    rows = []
    for rel, lines in _task_files(context):
        task_dir = (root / rel).parent
        number = _output_line_number(lines)
        seen = set()
        for path_text in _output_paths(lines):
            examined += 1
            if _UNRESOLVED_CHARS_RE.search(path_text):
                continue
            resolved = _resolve(task_dir, path_text)
            if resolved is None:
                continue
            resolved_count += 1
            key = str(resolved.resolve())
            if key in seen:
                continue
            seen.add(key)
            if key not in near_cap:
                result = measure_files([key], model=None)
                near_cap[key] = bool(result["files"]) and _is_near_cap(result["files"][0])
            if near_cap[key]:
                rows.append((rel, number, lines, path_text, resolved))
    if examined:
        print(
            f"Check {check}: output paths examined {examined}, resolved {resolved_count}, "
            f"near-cap {len(rows)}",
            file=sys.stderr,
        )
    return rows


def _check61_near_cap_output_without_gate(context) -> list:
    """Check 61 -- a task names a near-cap file on its first ``**Output:**`` line and no
    line of the task holds ``measure_files``, that file's basename and ``HALT``
    (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.14). Near-cap is 0.9
    of ``READ_TOKEN_WARN``, ``READ_LINE_CAP`` or ``READ_BYTE_WARN``, read from a fresh
    ``measure_files`` run. A task that grows such a file can cross the gate with no step
    noticing, so it needs a before and after reading against a stated ceiling. One
    finding per near-cap file, at the Output line. WARNING. It cannot see a path the task
    edits but does not list on its Output line. It cannot see a measurement written in
    another form than a ``measure_files`` line. It cannot see a ceiling figure that is
    itself wrong.
    """
    findings = []
    for rel, number, lines, path_text, resolved in _near_cap_outputs(context, 61):
        base = resolved.name
        if any("measure_files" in line and base in line and "HALT" in line for line in lines):
            continue
        findings.append(_finding(
            check=61, severity=SEVERITY_WARNING, file=rel, line=number, command=path_text,
            message=(
                f"This task names {base!r} on its Output line, and a fresh measurement puts "
                "that file at 0.9 of a Read gate or more. No line of the task holds "
                f"measure_files, {base!r} and HALT. A task that grows the file can cross the "
                "gate unseen. Measure it before and after against a stated ceiling, and HALT "
                f"above it ({_ANCHOR}, §8.14)"
            ),
        ))
    return findings


def _budget_lines(context, folder: Path, base: str) -> list:
    """Return ``(rel, number, live, cap, headroom, text)`` for each budget line of ``base``
    in the Orchestration files of ``folder``."""
    root = Path(context.plan_root)
    pattern = re.compile(
        rf"{re.escape(base)}: live ([0-9,]+) \(cap ([0-9,]+), headroom ([0-9,]+)\)"
    )
    found = []
    for path in context.markdown_files():
        if path.parent != folder or "orchestration" not in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        for number, raw in enumerate(text.split("\n"), start=1):
            line = raw.rstrip("\r")
            match = pattern.search(line)
            if match:
                live, cap, headroom = (int(g.replace(",", "")) for g in match.groups())
                found.append((rel, number, live, cap, headroom, line))
    return found


def _check62_shared_near_cap_file_without_budget(context) -> list:
    """Check 62 -- a near-cap file is named on the Output lines of two or more task files
    in one folder (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.14).
    Each task can pass its own ceiling while the sum crosses the cap, so the folder's
    Orchestration file needs one budget line of the form ``{basename}: live N (cap C,
    headroom H)`` with ``<= +x`` terms. The check warns once when no Orchestration file in
    the folder holds that line. It also warns on a budget line whose headroom is not the
    cap minus the live figure, and on one whose ``<= +x`` terms do not sum below the
    headroom. Near-cap is the same reading as Check 61's. WARNING. It cannot see a stale
    live figure on a budget line. The dispatch-time re-take of the live figure is the
    control for that.
    """
    root = Path(context.plan_root)
    groups: dict = {}
    for rel, number, _lines, _path_text, resolved in _near_cap_outputs(context, 62):
        groups.setdefault(((root / rel).parent, str(resolved.resolve())), []).append(
            (rel, number, resolved)
        )
    findings = []
    for (folder, _key), members in groups.items():
        if len(members) < 2:
            continue
        rel, number, resolved = members[0]
        base = resolved.name
        budgets = _budget_lines(context, folder, base)
        if not budgets:
            findings.append(_finding(
                check=62, severity=SEVERITY_WARNING, file=rel, line=number, command=base,
                message=(
                    f"{len(members)} tasks in this folder name {base!r} on their Output lines, "
                    "and a fresh measurement puts it at 0.9 of a Read gate or more. No "
                    "Orchestration file here holds a budget line for it. Each task can pass "
                    "its own ceiling while the sum crosses the cap. Add one line: "
                    f"'{base}: live N (cap C, headroom H); Task 01 <= +a, Task 02 <= +b; "
                    f"sum s < H' ({_ANCHOR}, §8.14)"
                ),
            ))
            continue
        for budget_rel, budget_number, live, cap, headroom, text in budgets:
            terms = sum(int(t.replace(",", "")) for t in _BUDGET_TERM_RE.findall(text))
            if headroom != cap - live:
                findings.append(_finding(
                    check=62, severity=SEVERITY_WARNING, file=budget_rel, line=budget_number,
                    command=text.strip(),
                    message=(
                        f"This budget line for {base!r} states headroom {headroom:,}, and "
                        f"cap {cap:,} minus live {live:,} is {cap - live:,}. Correct the "
                        f"arithmetic ({_ANCHOR}, §8.14)"
                    ),
                ))
            if terms >= headroom:
                findings.append(_finding(
                    check=62, severity=SEVERITY_WARNING, file=budget_rel, line=budget_number,
                    command=text.strip(),
                    message=(
                        f"The '<= +' terms of this budget line for {base!r} sum to {terms:,}, "
                        f"which is not below the headroom of {headroom:,}. The tasks can cross "
                        "the cap together. Lower a term, or move the builder logic to a new "
                        f"module ({_ANCHOR}, §8.14)"
                    ),
                ))
    return findings


# --- Checks 69-71: a ceiling, an overflow rule and a cost bound (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.15) ---
_CHECKBOX_LINE_RE = re.compile(r"^[\s>]*[-*+]\s+\[[ xX]\]")
_CEILING_WORD_RE = re.compile(
    r"\b(?:under|below|at most|never above|no more than)\b|<=|≤", re.IGNORECASE
)
# A figure, an optional K multiplier and a unit: ``6 KiB``, ``22,000-token``, ``25K tokens``.
_SIZE_FIGURE_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)(\s*K(?![A-Za-z]))?[\s-]*(KiB|KB|bytes?|tokens?)(?![A-Za-z])",
    re.IGNORECASE,
)
_CEILING_LABEL_RE = re.compile(r"guards:|estimat|not a gate", re.IGNORECASE)
_GATE_TOKEN_FIGURES = frozenset(
    {READ_PAGE_CAP_TOKENS, READ_TOKEN_WARN, round(_NEAR_CAP_FRACTION * READ_TOKEN_WARN)}
)
_GATE_BYTE_FIGURES = frozenset({READ_FILE_BYTE_CAP, READ_BYTE_WARN})
_SIBLING_PART_RE = re.compile(r"\bPart-\d+[b-z]\b")
# ``[^;]`` keeps the two words of a phrase inside one clause.
_SIBLING_PHRASE_RE = re.compile(
    r"\bdeclared\b[^;]*\bsibling|\bsibling\b[^;]*\bonly if\b", re.IGNORECASE
)
_REMEASURE_RE = re.compile(r"\bre-?measure", re.IGNORECASE)
_REPEAT_RE = re.compile(r"\brepeat", re.IGNORECASE)
_COST_BOUND_RE = re.compile(
    r"\b(?:costs?|loads?)\b.*\b(?:rises?|grows?|increases?)\s+by\s+"
    r"(?:more than|at most|no more than)\s+[~*`]*\d",
    re.IGNORECASE,
)
_PLANNED_ADDITIONS_RE = re.compile(r"\bplanned additions?\b", re.IGNORECASE)
_PER_ITEM_DELTA_RE = re.compile(r"\bper-(?:file|rule)\s+deltas?\b", re.IGNORECASE)


def _task_prose_lines(context):
    """Yield ``(rel, prose, number, line)`` for each line of a task file that is outside a
    fenced block and holds no ``WRONG`` label. ``prose`` is every such line of that file,
    so a silencer reads the same lines a trigger does."""
    for rel, lines in _task_files(context):
        kept = [(number, line) for number, line in _unfenced(lines) if "WRONG" not in line]
        prose = [line for _number, line in kept]
        for number, line in kept:
            yield rel, prose, number, line


def _is_gate_figure(number: str, multiplier: str, unit: str) -> bool:
    """True when the figure equals a Read-gate constant of ``read_limits``."""
    value = float(number.replace(",", ""))
    if multiplier:
        value *= 1000
    unit = unit.lower()
    if unit.startswith("token"):
        return value in _GATE_TOKEN_FIGURES
    return (value if unit.startswith("byte") else value * 1024) in _GATE_BYTE_FIGURES


def _check69_unlabelled_size_ceiling(context) -> list:
    """Check 69 -- a checkbox criterion holds a ceiling word (``under``, ``below``, ``at
    most``, ``no more than``, ``never above``, ``<=``, ``≤``) and a size figure in KiB, KB,
    bytes or tokens, and outside its code spans the line holds none of ``guards:``,
    ``estimat`` and ``not a gate``
    (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.15). A line whose
    every figure equals a Read gate (22,000, 25,000 or 19,800 tokens, 240 or 256 KiB) is
    silent.
    Input: the unfenced, non-``WRONG`` lines of task files, so a Signoff file is not read.
    One finding per line. WARNING. It reads the whole line, so it also warns when ``under``
    or ``below`` names a location beside a size figure. It cannot see a ceiling outside a
    checkbox line, a figure in another unit or with no unit, a criterion that wraps between
    the word and the figure, or a ``guards:`` label that names a limit which does not exist.
    """
    findings = []
    for rel, _prose, number, line in _task_prose_lines(context):
        if not _CHECKBOX_LINE_RE.match(line) or not _CEILING_WORD_RE.search(line):
            continue
        if _CEILING_LABEL_RE.search(_CODE_SPAN_RE.sub("", line)):
            continue
        figures = _SIZE_FIGURE_RE.findall(line)
        if all(_is_gate_figure(*figure) for figure in figures):
            continue
        findings.append(_finding(
            check=69, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
            message=(
                "This criterion states a size ceiling and names no gate for it. A figure "
                "written from a guess then binds the runner. Add 'guards: <the real limit and "
                "the headroom>', or mark the figure as an estimate and 'not a gate' "
                f"({_ANCHOR}, §8.15)"
            ),
        ))
    return findings


def _check70_fixed_overflow_sibling_count(context) -> list:
    """Check 70 -- an ``**Output:**`` line declares a lettered sibling Part (``Part-9b``) or
    holds ``declared ... sibling`` or ``sibling ... only if`` within one clause, and no
    prose line of the task holds both ``re-measure`` and ``repeat``
    (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.15). A sibling count
    fixed from projected inputs leaves no legal exit when the inputs measure larger.
    Input: task files. One finding per matching Output line. WARNING. It also warns on a
    task that only edits an existing lettered Part. It cannot see whether the count was
    re-priced from the measured inputs, an overflow rule stated outside the Output line, or
    a sibling declared in other words.
    """
    findings = []
    for rel, prose, number, line in _task_prose_lines(context):
        if not _OUTPUT_LINE_RE.match(line):
            continue
        if not (_SIBLING_PART_RE.search(line) or _SIBLING_PHRASE_RE.search(line)):
            continue
        if any(_REMEASURE_RE.search(other) and _REPEAT_RE.search(other) for other in prose):
            continue
        findings.append(_finding(
            check=70, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
            message=(
                "This Output line fixes how many sibling files an overflow may create, and no "
                "line of the task says to re-measure and repeat. Inputs larger than projected "
                "then leave no legal exit. State the procedure: move the largest section to "
                "the next sibling Part, re-measure, and repeat until every Part measures OK "
                f"({_ANCHOR}, §8.15)"
            ),
        ))
    return findings


def _check71_unbudgeted_cost_bound(context) -> list:
    """Check 71 -- a line holds ``cost`` or ``load``, then a form of ``rise``, ``grow`` or
    ``increase`` with ``by more than``, ``by at most`` or ``by no more than``, then a figure
    (measurement-discipline-Part-3-RecordedDeltaAndPinnedCount.md §8.15). It is silent when
    the line names planned additions and a prose line states per-file or per-rule deltas.
    Input: the unfenced, non-``WRONG`` lines of task files. One finding per line. WARNING.
    It cannot see a planned addition the exclusion list omits, a bound worded without
    ``cost`` or ``load``, a figure written in words, or a report-only instrument that a
    later step promotes to a gate.
    """
    findings = []
    for rel, prose, number, line in _task_prose_lines(context):
        if not _COST_BOUND_RE.search(line):
            continue
        if _PLANNED_ADDITIONS_RE.search(line) and any(_PER_ITEM_DELTA_RE.search(other) for other in prose):
            continue
        findings.append(_finding(
            check=71, severity=SEVERITY_WARNING, file=rel, line=number, command=line.strip(),
            message=(
                "This cost bound does not exclude the plan's own planned additions, or the "
                "task states no per-file or per-rule delta. Approved new text can then fail "
                "it. Name the planned additions the bound excludes, and report per-file or "
                f"per-rule deltas ({_ANCHOR}, §8.15)"
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
    _check61_near_cap_output_without_gate,
    _check62_shared_near_cap_file_without_budget,
    _check69_unlabelled_size_ceiling,
    _check70_fixed_overflow_sibling_count,
    _check71_unbudgeted_cost_bound,
]
