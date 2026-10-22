#!/usr/bin/env python3
"""Lint checks that read one task file's gate commands, registered into the linter.

``lint_verification_gates`` imports ``CHECKS`` from this module and extends its
``CHECK_REGISTRY`` with it. This module imports nothing from the linter: the
linter runs as ``__main__`` when invoked as a script, so importing it here would
load a second copy that imports this module half-initialised. Each check
therefore takes the lint context duck-typed -- it reads only ``commands``,
``execute``, ``plan_root`` and ``markdown_files()`` -- and builds its finding
with the same six keys the linter's ``make_finding`` writes. The severity
strings equal the linter's ``SEVERITY_*`` constants. A test pins both
agreements, so a change on either side shows up.

Every check here is static except Check 18, which in execute mode asks git
whether a gated path is tracked. That query has a fixed argument vector:
``git -c core.fsmonitor=false ls-files --error-unmatch -- <path>``. It reads
the index and writes nothing. Plan text supplies only the path and the
repository directory, never the executable or the subcommand.
"""

import re
import shlex
import subprocess
from pathlib import Path

from lint_gate_tool_calls import iter_tool_calls

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_UNCERTAIN = "UNCERTAIN"

_GIT_TIMEOUT_SECONDS = 30

# Separators that end one pipeline and start the next on the same line.
_CHAIN_TOKENS = frozenset({"&&", "||", ";"})

# git global options that take the next token as their value.
_GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})

# git diff options that make it report a measurable property of the change.
_DIFF_STAT_OPTIONS = ("--numstat", "--stat", "--shortstat", "--dirstat")

# A grep context flag: -B1, -A2, -C1, a combined -nB1, or the long forms.
_CONTEXT_FLAG_RE = re.compile(r"^-[a-zA-Z]*[ABC]\d*$|^--(before-context|after-context|context)(=\d+)?$")

# A diff operand that names a recorded base: a ``$..._BASE`` variable, a
# template slot naming a base, or a literal commit id of seven or more hex digits.
_BASE_OPERAND_RE = re.compile(r"BASE|^[0-9a-f]{7,40}(\.\.\.?\S*)?$")
_HEAD_OPERAND_RE = re.compile(r"\bHEAD\b")

# A grep pattern that filters out comment lines: a comment marker inside it.
_COMMENT_MARKER_RE = re.compile(r"#|//")
_COMMENT_ONLY_NOTE_RE = re.compile(r"comment[- ]only|no[- ]logic|logic[- ]identical", re.IGNORECASE)

# A ``$( ... )`` command substitution with no nested parenthesis.
_SUBSTITUTION_RE = re.compile(r"\$\(([^()]*)\)")
_ASSIGNED_SUBSTITUTION_RE = re.compile(r"\b([A-Za-z_]\w*)=\$\(([^()]*)\)")
_COMPARATOR_RE = re.compile(r"\s-(ge|gt|le|lt|eq|ne)\s|>=|<=|\s/\s")

# Tolerance language, and the numeric band that makes it safe.
_TOLERANCE_WORD_RE = re.compile(r"\b(approximate(?:ly)?|close enough|within tolerance)\b", re.IGNORECASE)
_NUMERIC_BAND_RE = re.compile(
    r"±\s*\d|\+/-\s*\d|\d\s*%|\bwithin\s+±?\s*\d|tolerance\s*(?:of|:|=|is)?\s*±?\s*\d"
    r"|(?:<=|>=|≤|≥)\s*\d|\d+(?:\.\d+)?\s*(?:to|–)\s*\d"
)
_QUOTE_CHARS = "\"'`“”‘’"

_SUCCESS_CRITERIA_HEADING_RE = re.compile(r"^#{1,6}\s+Success Criteria\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


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


def _tokens(text: str):
    """Tokenise command text for inspection, never for execution. A trailing
    line-continuation backslash is dropped first. Returns None when the text
    does not tokenise."""
    text = text.rstrip().removesuffix("\\")
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return None


def _pipelines(tokens) -> list:
    """Split tokens on ``&&``, ``||`` and ``;`` into pipelines, and each
    pipeline on bare ``|`` into stages. Empty stages are dropped."""
    pipelines: list = []
    stages: list = []
    current: list = []
    for token in tokens:
        if token in _CHAIN_TOKENS or token == "|":
            if current:
                stages.append(current)
            current = []
            if token in _CHAIN_TOKENS:
                if stages:
                    pipelines.append(stages)
                stages = []
        else:
            current.append(token)
    if current:
        stages.append(current)
    if stages:
        pipelines.append(stages)
    return pipelines


def _command_pipelines(command) -> list:
    tokens = _tokens(command.command)
    return _pipelines(tokens) if tokens else []


def _short_flags(stage) -> str:
    """The letters of every short-option cluster in a stage, before ``--``."""
    letters = []
    for token in stage[1:]:
        if token == "--":
            break
        if token.startswith("-") and not token.startswith("--"):
            letters.append(token[1:])
    return "".join(letters)


def _grep_has(stage, short: str, long: str) -> bool:
    return long in stage[1:] or short in _short_flags(stage)


def _is_count_stage(stage) -> bool:
    if stage[0] == "wc":
        return True
    return stage[0] == "grep" and _grep_has(stage, "c", "--count")


def _grep_pattern_and_target(stage):
    """Return ``(pattern, target)`` of a grep stage. A pattern given with
    ``-e`` is honoured. The target is None when no file follows the pattern."""
    positionals = []
    pattern = None
    skip = False
    for index, token in enumerate(stage[1:], start=1):
        if skip:
            skip = False
            continue
        if token in ("-e", "--regexp") and index + 1 < len(stage):
            pattern = stage[index + 1]
            skip = True
            continue
        if token in ("-A", "-B", "-C", "-m", "-f") and index + 1 < len(stage):
            skip = True
            continue
        if token.startswith("-") and token != "-":
            continue
        positionals.append(token)
    if pattern is None:
        if not positionals:
            return None, None
        pattern, positionals = positionals[0], positionals[1:]
    return pattern, (positionals[-1] if positionals else None)


def _git_subcommand(stage):
    """Return ``(repo_dir, index)`` for a git stage: the ``-C`` directory (or
    None) and the index of the subcommand token. ``(None, None)`` when the
    stage is not git or names no subcommand."""
    if not stage or stage[0] != "git":
        return None, None
    repo_dir = None
    index = 1
    while index < len(stage):
        token = stage[index]
        if token in _GIT_VALUE_OPTIONS:
            if token == "-C" and index + 1 < len(stage):
                repo_dir = stage[index + 1]
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return repo_dir, index
    return None, None


def _diff_parts(stage):
    """For a ``git diff`` stage, return ``(repo_dir, operands, paths, scoped)``:
    the revision operands before ``--``, the paths after it, and whether a
    ``--`` path scope is present. None when the stage is not ``git diff``."""
    repo_dir, at = _git_subcommand(stage)
    if at is None or stage[at] != "diff":
        return None
    rest = stage[at + 1:]
    if "--" in rest:
        cut = rest.index("--")
        head, paths, scoped = rest[:cut], rest[cut + 1:], True
    else:
        head, paths, scoped = rest, [], False
    operands = [token for token in head if not token.startswith("-")]
    return repo_dir, operands, paths, scoped


def _added_paths(command) -> set:
    """Paths a ``git add`` (intent-to-add or plain) in this command registers."""
    registered: set = set()
    for stages in _command_pipelines(command):
        for stage in stages:
            _, at = _git_subcommand(stage)
            if at is None or stage[at] != "add":
                continue
            for token in stage[at + 1:]:
                if not token.startswith("-"):
                    registered.add(_norm(token))
    return registered


def _intent_to_add_paths(command) -> set:
    """Paths a ``git add -N`` / ``--intent-to-add`` in this command registers."""
    registered: set = set()
    for stages in _command_pipelines(command):
        for stage in stages:
            _, at = _git_subcommand(stage)
            if at is None or stage[at] != "add":
                continue
            args = stage[at + 1:]
            flags = "".join(t[1:] for t in args if t.startswith("-") and not t.startswith("--"))
            if "N" not in flags and "--intent-to-add" not in args:
                continue
            registered.update(_norm(t) for t in args if not t.startswith("-"))
    return registered


def _norm(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def _commands_by_file(context) -> dict:
    grouped: dict = {}
    for command in context.commands:
        grouped.setdefault(command.file, []).append(command)
    for commands in grouped.values():
        commands.sort(key=lambda c: c.line)
    return grouped


def _is_diff_property(stages, diff_index: int, stage) -> bool:
    if any(option in stage for option in _DIFF_STAT_OPTIONS):
        return True
    return any(_is_count_stage(later) for later in stages[diff_index + 1:])


# A pathspec token that is not one literal path: an expansion, a template
# slot, a glob, or pathspec magic. The character set is the one Check 28
# skips (``_PLACEHOLDER_CHARS`` in ``lint_gate_checks_plan``, which imports
# this module, so it cannot be imported here), plus ``[`` for a glob class.
_UNCHECKABLE_PATH_CHARS = frozenset("<>{}$*?[")


def _checkable_path(token: str) -> bool:
    """True when ``token`` names one literal path that git can be asked about.
    A bare ``.`` and any ``:``-led pathspec magic are skipped, as Check 28
    skips them."""
    if token == "." or token.startswith(":"):
        return False
    return not any(char in _UNCHECKABLE_PATH_CHARS for char in token)


def _path_base(path: str, plan_root: Path):
    """The first of the plan root and its parents under which ``path`` exists,
    or None. A gate with no ``-C`` runs from a directory the plan does not
    state, usually the project root, so the path itself locates it."""
    for base in (plan_root, *plan_root.parents):
        if (base / path).exists():
            return base
    return None


def _resolve_repo(repo_dir, plan_root: Path):
    candidate = Path(repo_dir)
    if candidate.is_absolute():
        return candidate if candidate.is_dir() else None
    for base in (plan_root, *plan_root.parents):
        if (base / candidate).is_dir():
            return base / candidate
    return None


def _git_tracks(repo: Path, path: str):
    """True when git's index holds ``path`` (exit 0), False when git reports
    it untracked (exit 1), and None when git could not be asked: any other
    exit, such as 128 for a directory outside a repository."""
    argv = ["git", "-c", "core.fsmonitor=false", "-C", str(repo),
            "ls-files", "--error-unmatch", "--", path]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_GIT_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(completed.returncode)


def _check18_diff_property_gate_over_untracked_path(context) -> list:
    """Check 18 -- a diff-property gate names a path git does not track
    (gate-baseline-independence.md §1). A ``git diff -- <path>`` whose output
    is counted, or which reports ``--numstat``/``--stat``, measures nothing
    for an untracked path: git has no index entry to compare against, so the
    gate prints zero whether or not the edit happened. In execute mode each
    path is checked with ``git ls-files --error-unmatch``: ERROR when git
    reports it untracked, UNCERTAIN when git could not be asked or the path
    does not resolve. With execution off the tracking state is unknown, so the
    gate is UNCERTAIN. A path that an earlier ``git add`` in the same file
    registers is exempt. A token that is not one literal path -- an expansion,
    a template slot, a glob, ``.`` or pathspec magic -- is not checked.
    """
    findings = []
    for commands in _commands_by_file(context).values():
        registered: set = set()
        for command in commands:
            if command.is_placeholder:
                continue
            gate = command.is_gate
            for stages in _command_pipelines(command):
                for index, stage in enumerate(stages):
                    parts = _diff_parts(stage)
                    if parts is None or not gate or "--no-index" in stage:
                        continue
                    repo_dir, _, paths, _ = parts
                    if not paths or not _is_diff_property(stages, index, stage):
                        continue
                    pending = [p for p in paths if _checkable_path(p) and _norm(p) not in registered]
                    findings.extend(_tracking_findings(context, command, repo_dir, pending))
            registered |= _added_paths(command)
    return findings


def _tracking_findings(context, command, repo_dir, paths) -> list:
    if not paths:
        return []

    def make(severity, message):
        return _finding(check=18, severity=severity, file=command.file, line=command.line,
                        command=command.command, message=message)

    if not context.execute:
        return [make(SEVERITY_UNCERTAIN, (
            "This gate asserts a property of a diff over named paths, and execution is "
            "off, so nothing checked that git tracks them. An untracked path has no "
            "index entry and the gate prints zero whatever was edited. Confirm each "
            "path with git ls-files --error-unmatch"
        ))]
    plan_root = Path(context.plan_root)
    repo = None
    if repo_dir is not None:
        repo = _resolve_repo(repo_dir, plan_root)
        if repo is None:
            return [make(SEVERITY_UNCERTAIN, (
                f"The gate's repository directory {repo_dir!r} does not resolve from the "
                "plan root or any parent, so the tracking state of its paths was not checked"
            ))]
    findings = []
    for path in paths:
        base = repo if repo is not None else _path_base(path, plan_root)
        if base is None:
            findings.append(make(SEVERITY_UNCERTAIN, (
                f"The path {path!r} does not exist under the plan root or any parent, "
                "so whether git tracks it was not checked"
            )))
            continue
        tracked = _git_tracks(base, path)
        if tracked is None:
            findings.append(make(SEVERITY_UNCERTAIN, (
                f"git could not be asked whether {path!r} is tracked, so this "
                "diff-property gate was not checked"
            )))
        elif not tracked:
            findings.append(make(SEVERITY_ERROR, (
                f"This gate asserts a property of a diff over {path!r}, which git does "
                "not track. git diff has no index entry to compare against, so the gate "
                "prints zero whether or not the edit happened. Snapshot a baseline "
                "before the first edit and diff against it"
            )))
    return findings


def _comment_filter_after(stages, diff_index: int) -> bool:
    for later in stages[diff_index + 1:]:
        if later[0] != "grep" or not _grep_has(later, "v", "--invert-match"):
            continue
        pattern, _ = _grep_pattern_and_target(later)
        if pattern and _COMMENT_MARKER_RE.search(pattern):
            return True
    return False


def _check19_intent_to_add_before_comment_only_diff(context) -> list:
    """Check 19 -- ``git add -N <path>`` precedes a comment-only or no-logic
    assertion on the same path (gate-baseline-independence.md §2). Intent-to-add
    records the path against an empty blob, so every pre-existing line of the
    file shows as an addition and the assertion fails correct work, naming
    lines the task never touched. A comment-only assertion is a ``git diff``
    over the path whose pipeline drops comment lines with ``grep -v``, or whose
    note says comment-only or no-logic. ERROR.
    """
    findings = []
    for file, commands in _commands_by_file(context).items():
        intent: set = set()
        for command in commands:
            if command.is_placeholder:
                continue
            note = f"{command.comment} {command.annotation}"
            for stages in _command_pipelines(command):
                for index, stage in enumerate(stages):
                    parts = _diff_parts(stage)
                    if parts is None:
                        continue
                    hit = sorted(_norm(p) for p in parts[2] if _norm(p) in intent)
                    if not hit:
                        continue
                    if not (_comment_filter_after(stages, index) or _COMMENT_ONLY_NOTE_RE.search(note)):
                        continue
                    findings.append(_finding(
                        check=19, severity=SEVERITY_ERROR, file=file, line=command.line,
                        command=command.command,
                        message=(
                            f"An earlier git add -N registers {', '.join(hit)} against an "
                            "empty blob, so this comment-only or no-logic assertion reads "
                            "every pre-existing line as an addition and fails correct work. "
                            "Diff against a baseline copy taken before the first edit"
                        ),
                    ))
            intent |= _intent_to_add_paths(command)
    return findings


def _check20_count_grep_chained_with_and(context) -> list:
    """Check 20 -- a gate line chains a ``grep -c`` to a second command with
    ``&&`` (gate-baseline-independence.md §5). grep exits non-zero when it
    counts zero, so the chain stops on the clean case, the one the gate exists
    to confirm, and the later check never runs. WARNING.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder:
            continue
        tokens = _tokens(command.command)
        if not tokens or "&&" not in tokens:
            continue
        segment: list = []
        for token in tokens:
            if token == "&&":
                stages = _pipelines(segment)
                last = stages[-1][-1] if stages and stages[-1] else None
                if last and last[0] == "grep" and _grep_has(last, "c", "--count"):
                    findings.append(_finding(
                        check=20, severity=SEVERITY_WARNING, file=command.file,
                        line=command.line, command=command.command,
                        message=(
                            "This gate chains a grep -c to a second command with &&. "
                            "grep exits non-zero on a count of zero, so the clean case "
                            "stops the chain and the second check never runs. Run each "
                            "counted check as its own command"
                        ),
                    ))
                    break
                segment = []
            else:
                segment.append(token)
    return findings


def _diff_defects(stages) -> list:
    """The baseline defects of every ``git diff`` stage in one pipeline."""
    defects = []
    for index, stage in enumerate(stages):
        parts = _diff_parts(stage)
        if parts is None or "--no-index" in stage:
            continue
        _, operands, _, scoped = parts
        if any(_BASE_OPERAND_RE.search(op) for op in operands):
            pass
        elif any(_HEAD_OPERAND_RE.search(op) for op in operands):
            defects.append("`HEAD` as the operand")
        else:
            defects.append("no recorded base operand")
        if not scoped:
            filtered = any(later[0] == "grep" for later in stages[index + 1:])
            defects.append("an output filter instead of a `--` path scope" if filtered
                           else "no `--` path scope")
    return defects


def _success_criteria_spans(context):
    """Yield ``(file, line, span)`` for each inline-code ``git … diff`` command
    in a Success Criteria section. A bare two-word mention is prose, not a
    command, and is skipped, as is any line containing WRONG."""
    root = Path(context.plan_root)
    for path in context.markdown_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        inside = False
        for number, raw in enumerate(text.split("\n"), start=1):
            line = raw.rstrip("\r")
            stripped = line.lstrip("> ").strip()
            if _HEADING_RE.match(stripped):
                inside = bool(_SUCCESS_CRITERIA_HEADING_RE.match(stripped))
                continue
            if not inside or "WRONG" in line:
                continue
            for span in _INLINE_CODE_RE.findall(line):
                tokens = _tokens(span)
                if tokens and tokens[0] == "git" and "diff" in tokens and len(tokens) >= 3:
                    yield rel, number, span


def _check21_diff_gate_not_baseline_pinned(context) -> list:
    """Check 21 -- a ``git diff`` in Verification Commands or Success Criteria
    that is not pinned to a recorded base (gate-diff-baseline-pinning.md §8.2,
    §8.3 and §8.5; Reviewer Check 077 steps a and b). The diff must name a
    ``$..._BASE`` operand (or a literal commit id) and scope its paths with
    ``--``. ``HEAD`` moves with every commit, and a downstream grep only hides
    what git already read from the whole working tree. ERROR.
    """
    findings = []
    candidates = [(c.file, c.line, c.command) for c in context.commands]
    candidates.extend(_success_criteria_spans(context))
    for file, line, text in candidates:
        if "WRONG" in text:
            continue
        tokens = _tokens(text)
        if not tokens or "git" not in tokens:
            continue
        defects = []
        for stages in _pipelines(tokens):
            defects.extend(_diff_defects(stages))
        if not defects:
            continue
        findings.append(_finding(
            check=21, severity=SEVERITY_ERROR, file=file, line=line, command=text,
            message=(
                f"This git diff gate has {'; '.join(dict.fromkeys(defects))}. It reads the "
                "whole working tree, so other writers' work fails or passes the gate. "
                "Pin a recorded base before the first edit and write git diff $BASE -- <paths>"
            ),
        ))
    return findings


def _list_reads(stages) -> list:
    """Path lists a pipeline feeds to a command: ``xargs -a <list>`` /
    ``--arg-file`` and ``--pathspec-from-file``."""
    lists = []
    for stage in stages:
        for index, token in enumerate(stage):
            following = stage[index + 1] if index + 1 < len(stage) else None
            if stage[0] == "xargs" and token.startswith("-") and not token.startswith("--"):
                if token.endswith("a") and following:
                    lists.append(following)
                elif "a" in token[1:]:
                    lists.append(token[token.index("a", 1) + 1:])
            elif token in ("--arg-file", "--pathspec-from-file") and following:
                lists.append(following)
            elif token.startswith(("--arg-file=", "--pathspec-from-file=")):
                lists.append(token.split("=", 1)[1])
    return [_norm(name) for name in lists if name]


def _counts_list(stages, name: str) -> bool:
    """True when this pipeline counts ``name``: it reads the list and ends in a
    count, or a counting stage names the list directly."""
    if name in _list_reads(stages) and any(_is_count_stage(s) for s in stages):
        return True
    return any(_is_count_stage(s) and name in (_norm(t) for t in s[1:]) for s in stages)


def _check22_path_list_read_before_counted(context) -> list:
    """Check 22 -- a gate reads a path list through ``xargs -a <list>`` or
    ``--pathspec-from-file=<list>`` and no earlier gate counts that list
    (gate-generated-input-integrity.md §16). A list whose lines end in a
    carriage return matches no file, and git prints nothing for an unmatched
    pathspec, so every "must print nothing" gate that reads it passes. A
    reader that itself ends in a count is the count gate. WARNING.
    """
    findings = []
    for file, commands in _commands_by_file(context).items():
        counted: set = set()
        for command in commands:
            if command.is_placeholder:
                continue
            for stages in _command_pipelines(command):
                for name in _list_reads(stages):
                    if _counts_list(stages, name):
                        counted.add(name)
                        continue
                    if name in counted:
                        continue
                    findings.append(_finding(
                        check=22, severity=SEVERITY_WARNING, file=file, line=command.line,
                        command=command.command,
                        message=(
                            f"This gate reads the path list {name!r}, and no earlier gate "
                            "counts it. A list whose paths fail to match makes git print "
                            "nothing, which passes an empty-output gate. Count the list first"
                        ),
                    ))
                for stage in stages:
                    if _is_count_stage(stage):
                        counted.update(_norm(t) for t in stage[1:] if not t.startswith("-"))
    return findings


def _grep_count_calls(text: str):
    """Yield ``(stages, enclosing_var)`` for the command text itself and for
    each ``$( … )`` substitution inside it, with the variable it is assigned
    to when there is one."""
    assigned = {m.group(2): m.group(1) for m in _ASSIGNED_SUBSTITUTION_RE.finditer(text)}
    for inner in _SUBSTITUTION_RE.findall(text):
        tokens = _tokens(inner)
        if tokens:
            for stages in _pipelines(tokens):
                yield stages, assigned.get(inner)
    if not _SUBSTITUTION_RE.search(text):
        tokens = _tokens(text)
        if tokens:
            for stages in _pipelines(tokens):
                yield stages, None


def _proximity_targets(commands) -> set:
    """Targets of every proximity pipeline: a grep context window piped to a count."""
    targets: set = set()
    for command in commands:
        for stages, _ in _grep_count_calls(command.command):
            first = stages[0]
            if first[0] != "grep" or not any(_CONTEXT_FLAG_RE.match(t) for t in first[1:]):
                continue
            if any(_is_count_stage(s) for s in stages[1:]):
                _, target = _grep_pattern_and_target(first)
                if target:
                    targets.add(_norm(target))
    return targets


def _check23_keyword_count_coverage_denominator(context) -> list:
    """Check 23 -- ``grep -c '{keyword}'`` over a ``.md`` file is the
    denominator of a coverage ratio (gate-heuristic-verifier-patterns.md §4;
    Reviewer Check 059 detection step 2). A keyword count over prose counts
    descriptions, table rows and fenced examples as well as real instances, so
    the ratio is structurally short. The count is a denominator when it is
    assigned to a variable another gate compares, or when a proximity pipeline
    counts tags over the same file. A note that merely says "coverage" is not
    read, because a note denying the ratio ("a count, not a coverage
    threshold") carries the same word. ERROR, the severity of the source check.
    """
    findings = []
    for file, commands in _commands_by_file(context).items():
        proximity = _proximity_targets(commands)
        texts = [c.command for c in commands]
        for command in commands:
            if command.is_placeholder:
                continue
            for stages, variable in _grep_count_calls(command.command):
                if len(stages) != 1:
                    continue
                stage = stages[0]
                if stage[0] != "grep" or not _grep_has(stage, "c", "--count"):
                    continue
                if any(_CONTEXT_FLAG_RE.match(t) for t in stage[1:]):
                    continue
                _, target = _grep_pattern_and_target(stage)
                if not target or not target.endswith(".md"):
                    continue
                compared = variable is not None and any(
                    re.search(r"\$\{?" + re.escape(variable) + r"\b", t) and _COMPARATOR_RE.search(t)
                    for t in texts
                )
                if not (compared or _norm(target) in proximity):
                    continue
                findings.append(_finding(
                    check=23, severity=SEVERITY_ERROR, file=file, line=command.line,
                    command=command.command,
                    message=(
                        f"This keyword count over {target} is the denominator of a coverage "
                        "ratio. It counts prose, table rows and fenced examples that mention "
                        "the keyword, so the ratio is short on correct work. Enumerate the "
                        "real sites, or treat the ratio as an investigate signal"
                    ),
                ))
                break
    return findings


def _check24_basic_grep_escaped_plus_header_filter(context) -> list:
    """Check 24 -- a basic-syntax grep (no ``-E``, ``-F`` or ``-P``) whose
    pattern carries ``\\+\\+``, the shape of a diff header filter
    (gate-predicate-discrimination.md §6). In basic syntax ``\\+`` repeats the
    item before it rather than matching a plus, so ``grep -v '^\\+\\+\\+'``
    deletes every added line and each later stage reads an empty stream.
    WARNING.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder:
            continue
        for stages in _command_pipelines(command):
            for stage in stages:
                if stage[0] != "grep":
                    continue
                flags = _short_flags(stage)
                long_flags = set(stage[1:])
                if any(f in flags for f in "EFP") or long_flags & {
                    "--extended-regexp", "--fixed-strings", "--perl-regexp"
                }:
                    continue
                pattern, _ = _grep_pattern_and_target(stage)
                if not pattern or "\\+\\+" not in pattern:
                    continue
                findings.append(_finding(
                    check=24, severity=SEVERITY_WARNING, file=command.file,
                    line=command.line, command=command.command,
                    message=(
                        f"The basic-syntax pattern {pattern!r} carries \\+, which repeats "
                        "the item before it instead of matching a plus, so a header filter "
                        "built on it removes every added line. Use grep -Ev '^\\+\\+\\+' "
                        "or grep -v '^+++'"
                    ),
                ))
                break
    return findings


def _is_task_file(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if line.startswith("# "):
                    return line.startswith("# Task:")
    except (OSError, UnicodeDecodeError):
        return False
    return False


def _tolerance_call(line: str):
    """Return the tolerance phrase on ``line`` that has no numeric band, or
    None. A phrase wrapped in quotes or backticks is a mention, not a use."""
    if "WRONG" in line:
        return None
    if _NUMERIC_BAND_RE.search(line):
        return None
    for match in _TOLERANCE_WORD_RE.finditer(line):
        before = line[match.start() - 1] if match.start() else ""
        after = line[match.end()] if match.end() < len(line) else ""
        if before and after and before in _QUOTE_CHARS and after in _QUOTE_CHARS:
            continue
        return match.group(0)
    return None


def _check25_tolerance_word_without_numeric_band(context) -> list:
    """Check 25 -- task-file text says "approximate", "close enough" or
    "within tolerance" with no numeric band on the same line
    (gate-verdict-contract-and-adjudication.md §5; Reviewer Check 060
    detection step 4). Without a band the verifier decides the tolerance
    itself, which is the opening for a PASS on a contradicted comparator.
    Task files are the markdown files whose first heading starts ``# Task:``.
    WARNING.
    """
    root = Path(context.plan_root)
    files = [p for p in context.markdown_files() if _is_task_file(p)]
    findings = []
    for path, number, phrase in iter_tool_calls(files, _tolerance_call):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        findings.append(_finding(
            check=25, severity=SEVERITY_WARNING, file=rel, line=number, command=phrase,
            message=(
                f"The spec says {phrase!r} with no numeric band on the line, so the "
                "verifier sets the tolerance itself. State the band (for example "
                "within 2%, or ±3) or require an exact comparison"
            ),
        ))
    return findings


CHECKS = [
    _check18_diff_property_gate_over_untracked_path,
    _check19_intent_to_add_before_comment_only_diff,
    _check20_count_grep_chained_with_and,
    _check21_diff_gate_not_baseline_pinned,
    _check22_path_list_read_before_counted,
    _check23_keyword_count_coverage_denominator,
    _check24_basic_grep_escaped_plus_header_filter,
    _check25_tolerance_word_without_numeric_band,
]
