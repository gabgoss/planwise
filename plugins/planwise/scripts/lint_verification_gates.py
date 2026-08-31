#!/usr/bin/env python3
"""Detect verification gates that cannot answer the question they were written to answer.

A verification gate exists to establish one thing: did the work happen? It does
that only when its value differs before and after the work. A gate whose
pre-edit value already satisfies its post-edit expectation, whose pattern can
never match under the interpreter it runs in, or whose target file no longer
owns the thing being asserted, passes whether or not the work was done. A gate
that cannot fail is indistinguishable, downstream, from a gate that verified
something.

This module has two halves.

``extract_commands``
    Walks a plan tree and pulls every command out of task files'
    ``Verification Commands`` Before/After blocks and out of exit-criteria
    sections, preserving each command verbatim and carrying the provenance a
    finding needs in order to name its source: file, line, block, trailing
    comment, and adjacent annotation line.

``run_command``
    Runs a command only when its executable is one of four read-only names.
    Anything else is refused, reported, and never run.

The executor is a security boundary, not a convenience. Its input is command
text lifted verbatim out of markdown that a person or an agent wrote, which
makes it untrusted by construction however trustworthy the author was. The
rules are absolute:

* Four bare executable names are allowed. Nothing else, ever.
* Refusal is the default. The predicate is "is this on the allowlist?", never
  "is this on a denylist?". A path form of an allowed name is refused too, so
  the allowlist cannot be widened by spelling.
* No interpreter. A command is tokenised into an argument vector and run
  directly, so metacharacters in a plan file stay inert instead of being
  interpreted on the author's behalf.
* A command carrying an unquoted metacharacter -- a pipeline, a redirection, a
  chain, a substitution, an expansion, a wildcard -- is refused whole. It is
  never decomposed and partly run, and never rewritten into something runnable.
* No bypass. No argument, no attribute, and no environment variable re-enables
  a refused command.
* A refused command is UNCERTAIN, never a pass. Reporting "no finding" for a
  command nobody ran would let a clean report stand over gates nobody
  inspected, which is the single failure mode that makes the whole tool
  unsound.

Every allowed executable reads and none writes, so read-only behaviour follows
from the allowlist itself rather than from anything this module has to remember
to do at call time.

The seven checks are registered separately; this module supplies the extraction
and execution substrate they are built on.
"""

import argparse
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from markdown_parser import is_section_boundary

# The whole allowlist. Four bare names, each of which only ever reads.
ALLOWED_EXECUTABLES = frozenset(
    {
        'grep',
        'wc',
        'ls',
        'test',
    }
)

DEFAULT_TIMEOUT_SECONDS = 30

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_UNCERTAIN = "UNCERTAIN"

# A command that could not be run has no verdict, so it reports the same value
# as a check that could not reach one. There is deliberately no passing
# disposition in this module: nothing here may conclude that a gate is fine.
DISPOSITION_UNCERTAIN = SEVERITY_UNCERTAIN

BLOCK_BEFORE = "Before"
BLOCK_AFTER = "After"
BLOCK_EXIT_CRITERION = "exit-criterion"

_SECTION_VERIFICATION = "verification-commands"
_SECTION_EXIT_CRITERIA = "exit-criteria"

# Characters that would change a command's meaning if an interpreter ever saw
# them. Their presence outside quotes refuses the command whole.
_METACHARACTERS = frozenset("|&;<>()$`*?[]{}~!\n")

# Substitution stays live inside double quotes, so it is refused there too.
_INTERPOLATING = frozenset("$`")

_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
_BLOCKQUOTE_RE = re.compile(r"^\s*>[ \t]?")
_BLOCK_LABEL_RE = re.compile(r"^\*\*(Before|After)\b", re.IGNORECASE)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# An unresolved template slot is not a command. Recognising one keeps a
# template's illustrative Before/After block from being linted as though an
# author had written a real gate there.
_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}|<[^<>\s][^<>]*>")

# A command-shaped inline span: a bare lowercase executable name followed by at
# least one argument. A bare path, a table cell, and a lone token are not
# commands and must not be treated as though somebody meant to run them.
_COMMAND_SHAPED_RE = re.compile(r"^[a-z][a-z0-9_.-]*\s+\S")


@dataclass
class _Scan:
    """Where the quoting boundaries fall in one line of command text."""

    comment_at: int
    metacharacters: list
    unterminated: bool
    masked: str


def _scan(text: str) -> _Scan:
    """Locate the trailing comment and any live metacharacters in ``text``.

    Quoting is honoured the way an interpreter would honour it, because that is
    the only reading under which "outside a quoted pattern" means anything: a
    wildcard inside a search pattern is data, and the same wildcard outside one
    would be expanded. ``masked`` returns the text with quoted spans blanked to
    spaces and its length preserved, so a caller can search the unquoted
    regions by index without re-deriving the boundaries.
    """
    metacharacters: list = []
    masked = list(text)
    comment_at = -1
    quote = ""
    index = 0
    length = len(text)

    while index < length:
        char = text[index]
        if quote == "'":
            masked[index] = " "
            if char == "'":
                quote = ""
        elif quote == '"':
            masked[index] = " "
            if char == "\\" and index + 1 < length:
                masked[index + 1] = " "
                index += 2
                continue
            if char == '"':
                quote = ""
            elif char in _INTERPOLATING:
                metacharacters.append(char)
        else:
            if char == "\\" and index + 1 < length:
                # An escaped character is literal, so it changes nothing.
                index += 2
                continue
            if char in ("'", '"'):
                quote = char
                masked[index] = " "
            elif char == "#" and (index == 0 or text[index - 1].isspace()):
                comment_at = index
                break
            elif char in _METACHARACTERS:
                metacharacters.append(char)
        index += 1

    return _Scan(comment_at, metacharacters, bool(quote), "".join(masked))


@dataclass
class ExtractedCommand:
    """One command lifted out of a plan file, with the provenance to cite it.

    ``command`` is the command text exactly as written, with only the trailing
    comment removed. It is never whitespace-normalised, unquoted, or rewritten:
    a check that looks for a missing flag reads the text as the author typed
    it, so normalising here would destroy the evidence the checks depend on.
    ``raw`` keeps the whole source line, comment included.
    """

    file: str
    path: Path
    line: int
    block: str
    command: str
    comment: str = ""
    annotation: str = ""
    raw: str = ""
    is_placeholder: bool = False
    result: dict | None = None

    @property
    def is_gate(self) -> bool:
        """True when the author recorded an expectation against this command.

        A command with neither a trailing comment nor an adjacent annotation
        line states no expectation, so there is nothing for a check to compare
        a measurement against and nothing to run it for.
        """
        return bool(self.comment or self.annotation)


def _strip_blockquote(line: str) -> str:
    """Drop one level of blockquote marker, leaving the content untouched."""
    match = _BLOCKQUOTE_RE.match(line)
    return line[match.end():] if match else line


def _relative_name(path: Path, plan_root: Path) -> str:
    try:
        return path.relative_to(plan_root).as_posix()
    except ValueError:
        return path.name


def _section_for_heading(stripped: str) -> str | None:
    """Classify a heading, or return None when it opens neither section.

    The heading text must *begin* with the section name. A prose heading that
    merely mentions one -- a document title naming its subject, say -- opens
    nothing, which is the difference between reading a plan's gates and reading
    every document that talks about gates.
    """
    text = stripped.lstrip("#").strip().lower()
    if text.startswith("verification commands"):
        return _SECTION_VERIFICATION
    if text.startswith("exit criteria"):
        return _SECTION_EXIT_CRITERIA
    return None


def _build_command(line: str, rel: str, path: Path, number: int, block: str):
    """Split one source line into command text, trailing comment, provenance."""
    scan = _scan(line)
    head = line if scan.comment_at < 0 else line[: scan.comment_at]
    comment = "" if scan.comment_at < 0 else line[scan.comment_at:].strip()
    command = head.rstrip()
    if not command.strip():
        return None
    return ExtractedCommand(
        file=rel,
        path=path,
        line=number,
        block=block,
        command=command,
        comment=comment,
        raw=line,
        # Searched over the UNMASKED command text, not scan.masked: a
        # template placeholder ({ABBREV}, {NN}) normally lives inside a
        # quoted grep pattern, and the masking pass blanks quoted spans to
        # spaces -- which would make exactly that, the normal place for a
        # placeholder to live, invisible to this check.
        is_placeholder=bool(_PLACEHOLDER_RE.search(head)),
    )


def _exit_criterion_commands(line: str, rel: str, path: Path, number: int) -> list:
    """Pull command-shaped text out of one exit-criterion line.

    Exit criteria are prose, so a command usually arrives inside an inline code
    span alongside file names, verdict tokens and table fragments that are not
    commands at all. Those are filtered by shape rather than by guesswork.
    """
    found = []
    for span in _INLINE_CODE_RE.findall(line):
        candidate = span.strip()
        if not _COMMAND_SHAPED_RE.match(candidate):
            continue
        command = _build_command(candidate, rel, path, number, BLOCK_EXIT_CRITERION)
        if command is not None:
            found.append(command)
    if found:
        return found

    stripped = line.strip()
    if stripped.startswith(("-", "*", "|", ">", "#", "`")):
        return []
    if not _COMMAND_SHAPED_RE.match(stripped):
        return []
    command = _build_command(line, rel, path, number, BLOCK_EXIT_CRITERION)
    return [command] if command is not None else []


def _extract_from_file(path: Path, plan_root: Path, text: str) -> list:
    """Extract every command from one markdown file."""
    rel = _relative_name(path, plan_root)
    found: list = []
    section: str | None = None
    pending_block: str | None = None
    fence_block: str | None = None
    in_fence = False
    previous: ExtractedCommand | None = None

    for number, raw in enumerate(text.split("\n"), start=1):
        line = _strip_blockquote(raw).rstrip()
        stripped = line.strip()

        if in_fence:
            if stripped.startswith("```"):
                in_fence = False
                fence_block = None
                previous = None
                continue
            if not stripped:
                continue
            if section == _SECTION_EXIT_CRITERIA:
                found.extend(_exit_criterion_commands(line, rel, path, number))
                continue
            if fence_block is None:
                continue
            if stripped.startswith("#"):
                # A standalone comment line annotates the command above it --
                # this is where a recorded pre-edit value lives.
                if previous is not None and not previous.annotation:
                    previous.annotation = stripped
                continue
            command = _build_command(line, rel, path, number, fence_block)
            if command is not None:
                found.append(command)
                previous = command
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            heading_section = _section_for_heading(stripped)
            if heading_section is not None:
                # A heading that itself opens a recognized section always
                # takes effect, whatever section (if any) was open before.
                section = heading_section
                pending_block = None
                continue
            if section is not None and len(heading_match.group(1)) > 2:
                # A ###-or-deeper subheading nested inside an already-open
                # Verification Commands / Exit Criteria section does not
                # open a *different* recognized section, so it must be
                # transparent to extraction -- the section stays open
                # through it. Only a top-level (#/##) heading, or one that
                # itself names a recognized section, is a real boundary.
                continue
            section = None
            pending_block = None
            continue
        if is_section_boundary(stripped):
            section = None
            pending_block = None
            continue
        if section is None:
            continue

        if section == _SECTION_VERIFICATION:
            label = _BLOCK_LABEL_RE.match(stripped)
            if label:
                pending_block = (
                    BLOCK_BEFORE if label.group(1).lower() == "before" else BLOCK_AFTER
                )
                continue

        if stripped.startswith("```"):
            in_fence = True
            previous = None
            if section == _SECTION_VERIFICATION:
                # A fenced block claims the label above it, once. A block with
                # no label -- an illustrative aside inside the same section --
                # carries no Before/After identity and is not a gate.
                fence_block = pending_block
                pending_block = None
            else:
                fence_block = BLOCK_EXIT_CRITERION
            continue

        if section == _SECTION_EXIT_CRITERIA:
            found.extend(_exit_criterion_commands(line, rel, path, number))

    return found


def extract_commands(plan_root) -> list:
    """Walk a plan tree and return every command it states a gate for.

    Each command carries the file, line and block it came from, so a finding
    can cite its source rather than describe it.
    """
    plan_root = Path(plan_root)
    commands: list = []
    for path in sorted(plan_root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        commands.extend(_extract_from_file(path, plan_root, text))
    return commands


def _refused(detail: str) -> dict:
    """Build the one refusal shape, so every path reports refusal identically."""
    return {
        "executed": False,
        "disposition": DISPOSITION_UNCERTAIN,
        "reason": f"{detail}, so it was not run and this gate could not be checked",
    }


def resolve_argv(command_text: str):
    """Tokenise command text into an argument vector, or explain the refusal.

    Returns ``(argv, None)`` when the text is a single plain command, and
    ``(None, reason)`` otherwise. Quotes are resolved here because an argument
    vector is what gets run; the extracted text itself is left verbatim for the
    checks to read.
    """
    scan = _scan(command_text)
    if scan.unterminated:
        return None, "the command has an unterminated quote"
    if scan.metacharacters:
        offenders = "".join(sorted(set(scan.metacharacters)))
        return None, (
            f"the command carries unquoted metacharacters ({offenders}) that "
            "would change its meaning under an interpreter"
        )
    try:
        argv = shlex.split(command_text, posix=True)
    except ValueError:
        return None, "the command could not be tokenised into an argument vector"
    if not argv:
        return None, "the command is empty"
    return argv, None


def _argv_refusal(argv) -> str | None:
    """Return why ``argv`` may not run, or None when the allowlist admits it."""
    if not isinstance(argv, (list, tuple)) or not argv:
        return "no command was supplied"
    if not all(isinstance(part, str) for part in argv):
        return "the command is not a list of strings"
    executable = argv[0]
    if not executable:
        return "the command names no executable"
    if "/" in executable or "\\" in executable:
        return (
            f"{executable!r} is a path rather than a bare name, and the "
            "allowlist admits four bare names only"
        )
    if executable not in ALLOWED_EXECUTABLES:
        return f"{executable!r} is not one of the four allowed read-only executables"
    return None


def run_command(argv, *, cwd=None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Run ``argv`` if and only if the allowlist admits its executable.

    Returns ``{"executed": True, "returncode", "stdout", "stderr"}`` on a run,
    and the refusal shape -- ``{"executed": False, "disposition": "UNCERTAIN",
    "reason": ...}`` -- otherwise.

    There is no bypass, and adding one would defeat the module. This function
    takes no flag, reads no environment variable, and consults no attribute
    that could re-admit a refused executable; refusal is decided by membership
    in ``ALLOWED_EXECUTABLES`` and by nothing else. ``cwd`` chooses the
    directory a command's relative paths resolve against and ``timeout`` bounds
    how long it may run -- neither influences whether it runs at all.

    The argument vector is passed straight to the operating system, so no
    interpreter ever sees the text and metacharacters cannot take effect.
    """
    refusal = _argv_refusal(argv)
    if refusal is not None:
        return _refused(refusal)

    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _refused(f"the command did not finish within {timeout} seconds")
    except OSError as exc:
        return _refused(f"the command could not be started ({exc.strerror or exc})")

    return {
        "executed": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def execute_command(command: ExtractedCommand, *, plan_root=None,
                    timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Resolve one extracted command and run it, or report why it was refused."""
    argv, refusal = resolve_argv(command.command)
    if argv is None:
        return _refused(refusal)
    return run_command(argv, cwd=plan_root, timeout=timeout)


@dataclass
class LintContext:
    """Everything a check needs, so a new check adds no new plumbing."""

    plan_root: Path
    execute: bool
    commands: list = field(default_factory=list)

    def markdown_files(self) -> list:
        """Every markdown file in the plan tree, for checks that read siblings."""
        return sorted(p for p in self.plan_root.rglob("*.md") if p.is_file())


# Each entry takes a LintContext and returns a list of findings. Checks are
# registered rather than hard-wired so that adding one touches this list and
# the check's own function, and nothing else.
CHECK_REGISTRY: list = []


def make_finding(*, check, severity: str, file: str, line: int, command: str,
                 message: str) -> dict:
    """Build a finding.

    Every finding names the check that raised it (or None, when no check did),
    its severity, and the file, line and command text it is about, so a report
    can cite the gate instead of describing it.
    """
    return {
        "check": check,
        "severity": severity,
        "file": file,
        "line": line,
        "command": command,
        "message": message,
    }


def _run_gates(context: LintContext) -> list:
    """Run the gates that state an expectation, and report every refusal.

    Only commands that record an expectation are run: a command with no
    recorded expectation has nothing to compare a measurement against, so
    running it would produce a value no check consumes.

    A refusal is reported here rather than swallowed. Treating "could not run"
    as "no finding" would put a clean report over a gate nobody inspected,
    which reads exactly like a gate that passed.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        result = execute_command(command, plan_root=context.plan_root)
        command.result = result
        if not result["executed"]:
            findings.append(
                make_finding(
                    check=None,
                    severity=SEVERITY_UNCERTAIN,
                    file=command.file,
                    line=command.line,
                    command=command.command,
                    message=result["reason"],
                )
            )
    return findings


def lint_plan(plan_root, execute: bool = True) -> list:
    """Lint every verification gate in a plan tree and return its findings.

    With ``execute`` false, no command is run and the checks that need a
    measurement stand down; the checks that read command text still report.
    Nothing is run in that mode, so nothing is refused in it either -- the
    caller turned execution off, rather than the allowlist turning a command
    away.
    """
    plan_root = Path(plan_root)
    context = LintContext(
        plan_root=plan_root,
        execute=execute,
        commands=extract_commands(plan_root),
    )

    findings: list = []
    if execute:
        findings.extend(_run_gates(context))
    for check in CHECK_REGISTRY:
        findings.extend(check(context))
    return findings


# ---------------------------------------------------------------------------
# The seven checks
#
# Checks 2-6 are static: they read extracted command text (and, where a check
# needs cross-file reasoning, sibling file content) and never run anything.
# Checks 1 and 7 read the ``result`` the executor already stored on a command
# in ``_run_gates`` -- they never execute a command themselves, so a refused
# command they cannot reason about is simply skipped, and its own UNCERTAIN
# finding (already produced by ``_run_gates``) stands as the only report for
# it. Nothing here ever concludes a gate passed.
# ---------------------------------------------------------------------------

_PRE_EDIT_TOKEN = "pre-edit:"
_INVARIANT_TOKEN = "invariant:"
_BASELINE_RE = re.compile(r"baseline:\s*(\d+)", re.IGNORECASE)

_EXPECT_KEYWORD_RE = re.compile(
    r"expect\s*(>=|<=|==|>|<|≥|≤)?\s*(\d+)", re.IGNORECASE
)
_BARE_COMPARATOR_RE = re.compile(r"(?<![\w.])(>=|<=|≥|≤)\s*(\d+)")
_BARE_NUMBER_ONLY_RE = re.compile(r"^#?\s*(\d+)\s*$")

_SECTION_ANCHOR_RE = re.compile(r"§(\d+)(?:\.(\d+))?")
_MD_LINK_RE = re.compile(r"[\w./\\-]+\.md")
_OUTPUT_FIELD_RE = re.compile(r"^\*\*Output:\*\*\s*(.+)$", re.MULTILINE)
_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
_VERDICT_MARKER_RE = re.compile(r"\*\*Verdict:\*\*")

_RECURSIVE_FLAG_CHARS = frozenset("rR")


@dataclass
class _Expectation:
    """A parsed ``{comparator}{value}`` reading lifted out of a gate's own
    comment or annotation text."""

    comparator: str | None
    value: int

    def satisfies(self, measured: int) -> bool:
        if self.comparator in (None, "=="):
            return measured == self.value
        if self.comparator == ">=":
            return measured >= self.value
        if self.comparator == "<=":
            return measured <= self.value
        if self.comparator == ">":
            return measured > self.value
        if self.comparator == "<":
            return measured < self.value
        return False


def _normalize_comparator(token: str | None) -> str | None:
    return {"≥": ">=", "≤": "<="}.get(token, token)


def _parse_expectation(note: str):
    """Read a stated expectation out of a gate's own comment/annotation text.

    Tries the keyworded form first (``expect >=1``, ``expect 0``), then the
    bare comparator form some authors write without the word ``expect``
    (``>=2``). A gate stating no expectation at all -- prose only -- returns
    None, and a caller must treat that as "nothing to evaluate", not as zero.
    """
    match = _EXPECT_KEYWORD_RE.search(note)
    if not match:
        match = _BARE_COMPARATOR_RE.search(note)
    if not match:
        # A trailing-comment gate can be terse enough to state only the bare
        # number and nothing else -- no "expect" keyword, no comparator
        # symbol. Treat a comment/annotation pair that reduces (once the
        # leading '#' and surrounding whitespace are stripped) to nothing
        # but digits as an implicit equality expectation. Anything with
        # additional words does not match this, so it cannot mask an
        # unparseable gate as a false zero.
        bare = _BARE_NUMBER_ONLY_RE.match(note.strip())
        if not bare:
            return None
        return _Expectation(None, int(bare.group(1)))
    comparator, value = match.group(1), match.group(2)
    return _Expectation(_normalize_comparator(comparator), int(value))


def _static_argv(command_text: str):
    """Tokenise command text for read-only inspection, never for execution.

    Returns None rather than raising when the text does not tokenise cleanly;
    a static check simply has nothing to look at then.
    """
    try:
        return shlex.split(command_text, posix=True)
    except ValueError:
        return None


def _positional_tokens(argv) -> list:
    return [token for token in argv[1:] if not token.startswith("-")]


def _grep_pattern_and_target(argv, plan_root: Path):
    """Split a grep-shaped argv into its search pattern and its file/dir
    target. The target is None when the command carries only one positional
    token -- a pattern with no explicit target is not a shape any of these
    checks reason about.
    """
    positionals = _positional_tokens(argv)
    if not positionals:
        return None, None
    pattern = positionals[0]
    if len(positionals) < 2:
        return pattern, None
    candidate = positionals[-1]
    target = plan_root if candidate in (".", "./") else plan_root / candidate
    return pattern, target


def _has_recursive_flag(argv) -> bool:
    for token in argv[1:]:
        if token == "--recursive":
            return True
        if token.startswith("-") and not token.startswith("--"):
            if any(ch in _RECURSIVE_FLAG_CHARS for ch in token[1:]):
                return True
    return False


def _has_extended_flag(argv) -> bool:
    for token in argv[1:]:
        if token == "--extended-regexp":
            return True
        if token.startswith("-") and not token.startswith("--") and "E" in token[1:]:
            return True
    return False


def _has_count_flag(argv) -> bool:
    for token in argv[1:]:
        if token == "--count":
            return True
        if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
            return True
    return False


def _note_for(command: ExtractedCommand) -> str:
    return f"{command.comment} {command.annotation}"


def _measured_value(command: ExtractedCommand):
    """Read the single number a gate's own output represents.

    ``wc -l`` reports it as the first field of its first output line;
    ``grep -c`` as a bare count (or one ``path:count`` pair per file,
    summed); a bare ``grep`` (no ``-c``) and ``ls`` report it as their
    output's line count -- one match, or one entry, per line. Returns None
    for a command that was not executed or whose shape this module does not
    know how to read a number out of -- a caller must treat that as "cannot
    evaluate", never as zero.
    """
    result = command.result
    if not result or not result.get("executed"):
        return None
    argv = _static_argv(command.command)
    if not argv:
        return None
    executable = argv[0]
    stdout = result.get("stdout", "")
    lines = stdout.splitlines()

    if executable == "wc":
        first = next((line for line in lines if line.strip()), "")
        token = first.strip().split()[0] if first.strip() else None
        try:
            return int(token)
        except (TypeError, ValueError):
            return None

    if executable == "grep":
        if _has_count_flag(argv):
            non_empty = [line for line in lines if line.strip()]
            if len(non_empty) == 1:
                candidate = non_empty[0].strip()
                try:
                    return int(candidate)
                except ValueError:
                    candidate = candidate.rsplit(":", 1)[-1]
                    try:
                        return int(candidate)
                    except ValueError:
                        return None
            total = 0
            counted = False
            for line in non_empty:
                try:
                    total += int(line.rsplit(":", 1)[-1])
                    counted = True
                except ValueError:
                    continue
            return total if counted else None
        return len(lines)

    if executable == "ls":
        return len([line for line in lines if line.strip()])

    return None


# Under POSIX basic regular expressions, these seven characters are literal
# unless escaped -- escaping them is what turns on grouping, an interval, an
# alternation, or a one-or-more/zero-or-one repeat (the last three are GNU
# extensions grep itself supports). Python's `re` module -- like extended
# regular expressions -- inverts that convention: unescaped, they are
# special; escaped, they are literal.
_BRE_SPECIAL_WHEN_ESCAPED = frozenset("(){}|+?")


def _translate_bre_to_python(pattern: str) -> str:
    """Translate a grep basic regular expression into the equivalent Python
    ``re`` pattern.

    Swapping the escape state of exactly ``_BRE_SPECIAL_WHEN_ESCAPED`` is the
    whole translation: every other character -- including ``.``, ``*``,
    ``^``, ``$``, ``[...]``, and any other escape such as ``\\.`` -- already
    means the same thing under BRE and under Python, so it passes through
    untouched.
    """
    out = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "\\" and index + 1 < length:
            nxt = pattern[index + 1]
            if nxt in _BRE_SPECIAL_WHEN_ESCAPED:
                # BRE: escaped -> special. Python: unescaped -> special.
                out.append(nxt)
            else:
                # Every other escape already agrees between BRE and Python
                # (\. is a literal dot in both, \\ is a literal backslash in
                # both, and so on), so it passes through verbatim.
                out.append(char)
                out.append(nxt)
            index += 2
            continue
        if char in _BRE_SPECIAL_WHEN_ESCAPED:
            # BRE: unescaped -> literal. Python: escaped -> literal.
            out.append("\\" + char)
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _compile_grep_pattern(pattern: str, extended: bool):
    """Compile a grep search pattern into the Python regex grep would
    actually match against, honouring the same BRE/ERE distinction Check 3's
    other branch already tracks via ``_has_extended_flag``. An extended
    (``-E``) pattern already shares Python's own escaping convention for
    ``( ) { } | + ?`` and passes through unchanged; a basic pattern is
    translated first. Returns None when the result does not compile, so a
    caller has nothing to count against rather than an exception to catch.
    """
    translated = pattern if extended else _translate_bre_to_python(pattern)
    try:
        return re.compile(translated)
    except re.error:
        return None


def _count_line_and_occurrence_totals(pattern: str, text: str, extended: bool = False):
    """Count how many lines a grep pattern touches, and how many times it
    occurs in total -- the two quantities ``grep -c`` conflates when a
    pattern can match more than once on the same line.

    The pattern is evaluated as the regex grep actually runs, never as a
    literal substring: a pattern carrying an escaped metacharacter (``\\.``,
    a character class, an escaped-or-bare group) must be matched the way the
    interpreter matches it, or a pattern using exactly the syntax this
    absorption sub-check exists to reason about would miscount. ``extended``
    selects BRE-to-Python translation (the default, matching grep's own
    default with no ``-E``) or passes an ERE pattern through unchanged.
    Returns ``(0, 0)`` when the pattern does not compile at all -- nothing to
    count is the safe reading, never a fabricated zero-vs-nonzero disparity.
    """
    compiled = _compile_grep_pattern(pattern, extended)
    if compiled is None:
        return 0, 0
    occurrence_total = 0
    line_total = 0
    for line in text.split("\n"):
        hits = sum(1 for _ in compiled.finditer(line))
        if hits:
            occurrence_total += hits
            line_total += 1
    return line_total, occurrence_total


def _check1_vacuous_after_gate(context: LintContext) -> list:
    """Check 1 -- a gate whose live pre-edit measurement already satisfies
    its stated expectation cannot tell whether the work happened. Exempt
    when the author marked the gate ``invariant:`` -- ``pre == post`` is the
    intended outcome there, not a defect.
    """
    if not context.execute:
        return []
    findings = []
    for command in context.commands:
        if command.block != BLOCK_AFTER or command.is_placeholder or not command.is_gate:
            continue
        if _INVARIANT_TOKEN in command.annotation:
            continue
        expectation = _parse_expectation(_note_for(command))
        if expectation is None:
            continue
        measured = _measured_value(command)
        if measured is None:
            continue
        if expectation.satisfies(measured):
            findings.append(
                make_finding(
                    check=1,
                    severity=SEVERITY_ERROR,
                    file=command.file,
                    line=command.line,
                    command=command.command,
                    message=(
                        f"This gate's live pre-edit measurement is {measured}, "
                        "which already satisfies its stated expectation -- it "
                        "would pass with zero work done, so it cannot tell "
                        "whether the work happened"
                    ),
                )
            )
    return findings


def _check2_missing_pre_edit_baseline(context: LintContext) -> list:
    """Check 2 -- an After-block gate with no inline pre-edit annotation
    beside its expectation. The gate may be fine; nothing in the artifact
    establishes that, which is indistinguishable from an author who never
    measured at all.
    """
    findings = []
    for command in context.commands:
        if command.block != BLOCK_AFTER or command.is_placeholder or not command.is_gate:
            continue
        if _PRE_EDIT_TOKEN in command.annotation:
            continue
        findings.append(
            make_finding(
                check=2,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This After-block gate carries no inline pre-edit "
                    "annotation beside its expectation, so whether it could "
                    "ever have failed is unknowable from the artifact"
                ),
            )
        )
    return findings


def _check3_bre_ere_and_line_count_absorption(context: LintContext) -> list:
    """Check 3 -- a grep pattern carrying ``(``, ``)``, or an escaped ``|``
    with no ``-E`` may not group or alternate the way its author intended
    under basic regular expressions. The same check also covers the
    absorbed variant: a ``grep -c`` gate whose stated count was measured as
    occurrences, when ``-c`` itself only ever counts matching LINES.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        argv = _static_argv(command.command)
        if not argv or argv[0] != "grep":
            continue
        pattern, target = _grep_pattern_and_target(argv, context.plan_root)
        if pattern is None:
            continue

        if not _has_extended_flag(argv) and ("(" in pattern or ")" in pattern or "\\|" in pattern):
            findings.append(
                make_finding(
                    check=3,
                    severity=SEVERITY_ERROR,
                    file=command.file,
                    line=command.line,
                    command=command.command,
                    message=(
                        "This grep pattern contains '(', ')', or an escaped "
                        "'|' but the command carries no -E, so under basic "
                        "regular expressions these characters may not group "
                        "or alternate the way the author intended"
                    ),
                )
            )

        if _has_count_flag(argv) and target is not None and target.is_file():
            expectation = _parse_expectation(_note_for(command))
            if expectation is not None and expectation.comparator in (None, "=="):
                try:
                    text = target.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    text = None
                if text is not None:
                    line_total, occurrence_total = _count_line_and_occurrence_totals(
                        pattern, text, extended=_has_extended_flag(argv)
                    )
                    if line_total != occurrence_total and occurrence_total == expectation.value:
                        findings.append(
                            make_finding(
                                check=3,
                                severity=SEVERITY_ERROR,
                                file=command.file,
                                line=command.line,
                                command=command.command,
                                message=(
                                    "This pattern matches more than once on "
                                    "at least one line of its target, but "
                                    "grep -c counts matching LINES, not "
                                    "occurrences -- the stated count was "
                                    "measured as occurrences, and the two "
                                    "quantities disagree"
                                ),
                            )
                        )
    return findings


def _check4_self_matching_sweep(context: LintContext) -> list:
    """Check 4 -- an expect-0 sweep that recurses over a tree containing the
    very files this task's own Output field names, with no exclusion filter
    for that family, matches the task's own correct output and halts a
    chain that succeeded.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        expectation = _parse_expectation(_note_for(command))
        if expectation is None or expectation.value != 0 or expectation.comparator not in (None, "=="):
            continue
        argv = _static_argv(command.command)
        if not argv or argv[0] != "grep" or not _has_recursive_flag(argv):
            continue
        _, target = _grep_pattern_and_target(argv, context.plan_root)
        if target is None or not target.is_dir():
            continue
        if "--exclude" in command.command:
            continue
        try:
            text = command.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        output_match = _OUTPUT_FIELD_RE.search(text)
        if not output_match or "new" not in output_match.group(1).lower():
            continue
        if not _BACKTICK_SPAN_RE.search(output_match.group(1)):
            continue
        findings.append(
            make_finding(
                check=4,
                severity=SEVERITY_ERROR,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This tree-wide expect-0 sweep runs over a tree that "
                    "includes the new files this task's own Output field "
                    "names, with no exclusion filter for that family -- the "
                    "sweep can match the task's own correct output and halt "
                    "a chain that succeeded"
                ),
            )
        )
    return findings


def _check5_stale_ownership(context: LintContext) -> list:
    """Check 5 -- an absence assertion naming a file and a section anchor,
    where a sibling file in the same plan routes that section out of the
    named file. The assertion no longer describes the file it targets.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        note = _note_for(command)
        expectation = _parse_expectation(note)
        if expectation is None or expectation.value != 0 or expectation.comparator not in (None, "=="):
            continue
        anchor = _SECTION_ANCHOR_RE.search(note)
        if not anchor:
            continue
        major = anchor.group(1)
        argv = _static_argv(command.command)
        if not argv or argv[0] != "grep":
            continue
        _, target = _grep_pattern_and_target(argv, context.plan_root)
        if target is None or not target.is_file():
            continue
        target_name = target.name
        anchor_token = f"§{major}"
        found = False
        for md_path in context.markdown_files():
            if md_path == command.path:
                continue
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line in text.split("\n"):
                if target_name not in line or anchor_token not in line:
                    continue
                other_files = {
                    m for m in _MD_LINK_RE.findall(line) if Path(m).name != target_name
                }
                if other_files:
                    found = True
                    break
            if found:
                break
        if found:
            findings.append(
                make_finding(
                    check=5,
                    severity=SEVERITY_ERROR,
                    file=command.file,
                    line=command.line,
                    command=command.command,
                    message=(
                        f"This absence assertion names {target_name} and "
                        f"section {anchor_token}, but a routing decision "
                        f"elsewhere in the plan moves {anchor_token} out of "
                        "that file to a different owner in the same plan -- "
                        "the assertion no longer describes the file it "
                        "targets"
                    ),
                )
            )
    return findings


def _check6_substring_over_own_vocabulary(context: LintContext) -> list:
    """Check 6 -- a gate greping a generated verification report for a bare
    token, when the report's own legend, column headers, and criterion rows
    can legitimately contain that token too.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        argv = _static_argv(command.command)
        if not argv or argv[0] != "grep":
            continue
        pattern, target = _grep_pattern_and_target(argv, context.plan_root)
        if pattern is None or target is None or not target.is_file():
            continue
        if pattern.startswith("^") or "\\|" in pattern or "Verdict" in pattern:
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not _VERDICT_MARKER_RE.search(text):
            continue
        findings.append(
            make_finding(
                check=6,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This gate searches a generated verification report for "
                    f"a bare token ({pattern!r}) rather than its "
                    "machine-readable verdict line or status-cell pattern -- "
                    "the report's own legend, headers, and criterion rows "
                    "can legitimately carry that token too"
                ),
            )
        )
    return findings


def _check7_contradicted_before_baseline(context: LintContext) -> list:
    """Check 7 -- a Before-block gate whose stated baseline disagrees with
    what it measures against the live pre-edit tree. The baseline was
    authored from intent, not from a run.
    """
    if not context.execute:
        return []
    findings = []
    for command in context.commands:
        if command.block != BLOCK_BEFORE or command.is_placeholder or not command.is_gate:
            continue
        match = _BASELINE_RE.search(_note_for(command))
        if not match:
            continue
        stated = int(match.group(1))
        measured = _measured_value(command)
        if measured is None:
            continue
        if measured != stated:
            findings.append(
                make_finding(
                    check=7,
                    severity=SEVERITY_ERROR,
                    file=command.file,
                    line=command.line,
                    command=command.command,
                    message=(
                        f"This Before-block gate states a baseline of "
                        f"{stated}, but executing it against the live "
                        f"pre-edit tree measures {measured} -- the recorded "
                        "baseline was authored from intent, not from a run"
                    ),
                )
            )
    return findings


CHECK_REGISTRY.extend(
    [
        _check1_vacuous_after_gate,
        _check2_missing_pre_edit_baseline,
        _check3_bre_ere_and_line_count_absorption,
        _check4_self_matching_sweep,
        _check5_stale_ownership,
        _check6_substring_over_own_vocabulary,
        _check7_contradicted_before_baseline,
    ]
)


# ---------------------------------------------------------------------------
# CLI
#
# Invocation:  python lint_verification_gates.py {plan_root} [--no-execute]
#
# Exit codes distinguish three outcomes a caller must be able to tell apart
# without parsing output text:
#   0  no findings at all.
#   1  findings present, none at ERROR -- WARNING and UNCERTAIN advise only.
#   2  at least one finding at ERROR -- the caller should halt.
# ---------------------------------------------------------------------------

EXIT_NO_FINDINGS = 0
EXIT_ADVISORY_ONLY = 1
EXIT_ERROR_PRESENT = 2


def _print_findings(findings) -> None:
    for finding in findings:
        check = finding["check"]
        label = f"Check {check}" if check is not None else "Refusal"
        print(f"[{finding['severity']}] {label}: {finding['file']}:{finding['line']} -- {finding['message']}")
        print(f"    {finding['command']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lint a plan tree for verification gates that cannot "
        "answer the question they were written to answer."
    )
    parser.add_argument("plan_root", help="Path to the plan tree to lint")
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="Disable the read-only executor; only the five static checks run",
    )
    args, _ = parser.parse_known_args()

    plan_root = Path(args.plan_root)
    if not plan_root.exists():
        print(f"Error: plan root not found at {plan_root}", file=sys.stderr)
        sys.exit(EXIT_ERROR_PRESENT)

    findings = lint_plan(plan_root, execute=not args.no_execute)

    if not findings:
        print("No findings.")
        sys.exit(EXIT_NO_FINDINGS)

    _print_findings(findings)

    if any(finding["severity"] == SEVERITY_ERROR for finding in findings):
        sys.exit(EXIT_ERROR_PRESENT)
    sys.exit(EXIT_ADVISORY_ONLY)


if __name__ == "__main__":
    main()
