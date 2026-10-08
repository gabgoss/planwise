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

The checks are registered separately in ``CHECK_REGISTRY``; this module
supplies the extraction and execution substrate they are built on.
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


def _quote_closes_in_fence(lines: list, index: int) -> bool:
    """True when the quote left open on ``lines[index]`` closes before the fence ends.

    A stray quote in a one-line command must not swallow the gates after it, so
    a line is joined with its successors only when the join is known to close.
    Otherwise the line stays a command of its own and the resolver refuses it
    as an unterminated quote, as it always has.
    """
    joined = _strip_blockquote(lines[index]).rstrip()
    for raw in lines[index + 1:]:
        line = _strip_blockquote(raw).rstrip()
        if line.strip().startswith("```"):
            return False
        joined = joined + "\n" + line
        if not _scan(joined).unterminated:
            return True
    return False


def _extract_from_file(path: Path, plan_root: Path, text: str) -> list:
    """Extract every command from one markdown file."""
    rel = _relative_name(path, plan_root)
    found: list = []
    section: str | None = None
    pending_block: str | None = None
    fence_block: str | None = None
    in_fence = False
    previous: ExtractedCommand | None = None
    # A quoted argument can span lines (``python -c "`` followed by a script
    # body). The lines of one such command are held here, with the number of
    # the first, until the quote closes -- otherwise each continuation line
    # would be linted as a command of its own.
    open_lines: list = []
    open_start = 0

    lines = text.split("\n")
    for number, raw in enumerate(lines, start=1):
        line = _strip_blockquote(raw).rstrip()
        stripped = line.strip()

        if in_fence:
            if open_lines:
                open_lines.append(line)
                joined = "\n".join(open_lines)
                if _scan(joined).unterminated:
                    continue
                command = _build_command(joined, rel, path, open_start, fence_block)
                open_lines = []
                if command is not None:
                    found.append(command)
                    previous = command
                continue
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
            if _scan(line).unterminated and _quote_closes_in_fence(lines, number - 1):
                open_lines = [line]
                open_start = number
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
            check=False,
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


def _lint(plan_root, execute: bool):
    """Lint a plan tree and return ``(findings, context)``.

    The context keeps each gate's execution result, which is what a coverage
    count is read from.
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
    return findings, context


def lint_plan(plan_root, execute: bool = True) -> list:
    """Lint every verification gate in a plan tree and return its findings.

    With ``execute`` false, no command is run and the checks that need a
    measurement stand down; the checks that read command text still report.
    Nothing is run in that mode, so nothing is refused in it either -- the
    caller turned execution off, rather than the allowlist turning a command
    away.
    """
    findings, _ = _lint(plan_root, execute)
    return findings


def coverage_line(context: LintContext) -> str:
    """Say how many gates the executor actually ran, in one line.

    A report made only of refusals carries no findings about the gates, yet it
    reads as a quiet scan. This line states the denominator so the two cannot
    be confused: ``checked`` counts gates that ran, ``refused`` counts gates
    the allowlist turned away. When gates exist and none ran, the line starts
    with ``NOT CHECKED``.
    """
    gates = [c for c in context.commands if c.is_gate and not c.is_placeholder]
    total = len(gates)
    if not context.execute:
        return f"Coverage: execution disabled; {total} gates not run."
    checked = sum(1 for c in gates if c.result and c.result["executed"])
    refused = total - checked
    if total and not checked:
        return (
            f"Coverage: NOT CHECKED -- 0 of {total} gates ran; {refused} refused. "
            "Derive the verification gates by hand."
        )
    return f"Coverage: checked {checked} of {total} gates; {refused} refused."


# ---------------------------------------------------------------------------
# The checks
#
# Checks 2-6 are static: they read extracted command text (and, where a check
# needs cross-file reasoning, sibling file content) and never run anything.
# Check 8 is static too, but reads markdown lines directly: a native tool call
# never becomes an extracted command, because the extractor reads only fenced
# blocks and lowercase shell verbs.
# Checks 1 and 7 read the ``result`` the executor already stored on a command
# in ``_run_gates`` -- they never execute a command themselves, so a refused
# command they cannot reason about is simply skipped, and its own UNCERTAIN
# finding (already produced by ``_run_gates``) stands as the only report for
# it. Nothing here ever concludes a gate passed.
# Checks 9-16 are static shape checks over a gate's command text and, where a
# check needs it, the bytes of the file the gate targets. They read a piped
# command stage by stage, which the executor refuses whole. Each mechanises a
# rule one of the gate references states in prose.
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
        if token.startswith("-") and not token.startswith("--") and any(
            ch in _RECURSIVE_FLAG_CHARS for ch in token[1:]
        ):
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


# A native ``Grep`` tool call written as ``Grep  pattern='...'``. The value runs
# to the matching quote, so a quote of the other kind may sit inside it.
_GREP_TOOL_CALL_RE = re.compile(r"\bGrep\b[^\n]*?\bpattern\s*=\s*(['\"])(.*?)\1")

# A backslash-pipe with a word character directly on each side, such as
# ``a\|b``. That is the shape of an alternation. A backslash-pipe beside
# whitespace, at the pattern start, or after ``^`` anchors a literal pipe in a
# markdown table row and is not matched. The ``(?<!\\\w)`` guard keeps a class
# escape such as ``\w\|`` from counting as a word character.
_ESCAPED_PIPE_ALTERNATION_RE = re.compile(r"(?<=\w)(?<!\\\w)\\\|(?=\w)")


def _check8_grep_tool_escaped_pipe_alternation(context: LintContext) -> list:
    """Check 8 -- a native ``Grep`` call whose pattern writes alternation as a
    backslash-pipe. The tool uses ripgrep syntax, where that escape matches a
    literal pipe, so the pattern matches nothing and a negative result reads
    as a real absence. A table cell forces the escape for a literal pipe,
    which is how it reaches the agent as raw text.

    Reads markdown lines directly, because a ``Grep`` call in a table row never
    becomes an extracted command. WARNING, not ERROR: the heuristic reads
    intent from the characters beside the escape. A line containing the word
    WRONG is a counter-example, not a gate, and is skipped. A template
    placeholder on the line does not exempt it.
    """
    findings = []
    for path in context.markdown_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = _relative_name(path, context.plan_root)
        for number, line in enumerate(text.split("\n"), start=1):
            # No placeholder skip: a template slot elsewhere on the line, such
            # as in an output cell, says nothing about the pattern's dialect.
            if "WRONG" in line:
                continue
            for call in _GREP_TOOL_CALL_RE.finditer(line):
                if not _ESCAPED_PIPE_ALTERNATION_RE.search(call.group(2)):
                    continue
                findings.append(
                    make_finding(
                        check=8,
                        severity=SEVERITY_WARNING,
                        file=rel,
                        line=number,
                        command=call.group(0),
                        message=(
                            "This Grep tool pattern writes alternation as a "
                            "backslash-pipe. The tool uses ripgrep syntax, "
                            "where that matches a literal pipe, so the pattern "
                            "matches nothing. Use a bare pipe outside a table "
                            "cell, or split it into one Grep call per "
                            "alternative"
                        ),
                    )
                )
                break
    return findings


# ---------------------------------------------------------------------------
# Checks 9-16 -- static shape checks over a gate's command text.
#
# A pipeline tokenises with a bare ``|`` token between its stages, so a static
# check can read each stage even though the executor refuses the whole command.
# Every check below reads the first stage's pattern and target the way Checks
# 3-6 do, and reads a target file's bytes only to classify a shape it has
# already matched. None of them runs anything, and none concludes a gate passed.
# ---------------------------------------------------------------------------

# A grep pattern that is one bare word: no anchor, no space, no metacharacter.
_SINGLE_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
# A grep pattern that is nothing but three or more digits.
_BARE_DIGITS_RE = re.compile(r"^\d{3,}$")
# A grep pattern that starts with a Markdown heading marker instead of ``^``.
_HEADING_PATTERN_RE = re.compile(r"^#{1,6} ")
# A verdict, gate, result or status label followed by its value, as a report
# skeleton prescribes it. The group spans label, colon and value so a caller can
# test whether any emphasis marker sits between them.
_VERDICT_LABEL_RE = re.compile(
    r"(Verdict|Gate|Result|Status):\s*(PASS|FAIL|HALT|WRITTEN|COMPLETE|UNCERTAIN)\b"
)
# A grep context flag: ``-B1``, ``-A2``, ``-C1``, a combined ``-nB1``, or the
# bare letter whose count follows as the next token.
_CONTEXT_FLAG_RE = re.compile(r"^-[a-zA-Z]*[ABC]\d*$|^--(before-context|after-context|context)(=\d+)?$")
# pytest flags that consume the next token as their value, so that token is
# never a path argument.
_PYTEST_VALUE_FLAGS = frozenset(
    {"-c", "-k", "-m", "-p", "-o", "-W", "-n", "--rootdir", "--confcutdir", "--tb",
     "--maxfail", "--durations", "--deselect", "--ignore"}
)
_PLAN_LEVEL_SUFFIXES = ("Master-Plan.md", "Sprint-Plan.md")


def _pipeline_stages(argv) -> list:
    """Split a tokenised command on bare ``|`` tokens into its stages.

    ``shlex`` leaves a pipe as its own token, so ``grep -B1 x f | grep -c y``
    becomes two stages. A command with no pipe is one stage. Empty stages
    (a leading or doubled pipe) are dropped rather than reasoned about.
    """
    stages: list = []
    current: list = []
    for token in argv:
        if token == "|":
            if current:
                stages.append(current)
            current = []
        else:
            current.append(token)
    if current:
        stages.append(current)
    return stages


def _first_grep_stage(command: ExtractedCommand):
    """Return ``(stage, stages)`` when the command's first stage is a grep, else
    ``(None, stages)``. ``stages`` is None when the text does not tokenise."""
    argv = _static_argv(command.command)
    if not argv:
        return None, None
    stages = _pipeline_stages(argv)
    if not stages or stages[0][0] not in ("grep", "rg"):
        return None, stages
    return stages[0], stages


def _target_bytes(target: Path):
    try:
        return target.read_bytes()
    except OSError:
        return None


def _check9_dollar_anchor_over_crlf_target(context: LintContext) -> list:
    """Check 9 -- a pattern anchored on ``$`` with no ``\\r?`` guard. On a CRLF
    file the carriage return sits between the last character and the line
    break, so ``$`` never matches and the gate returns a zero that reads like a
    real absence. ERROR when the target is a readable file with CRLF endings,
    WARNING when the target does not exist yet (its endings are unknown), and
    silent on an LF-only file, a directory target, an escaped ``\\$``, or a
    pattern that already carries a ``\\r`` guard.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        stage, _ = _first_grep_stage(command)
        if stage is None:
            continue
        pattern, target = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None or not pattern.endswith("$") or pattern.endswith("\\$"):
            continue
        if "\\r" in pattern:
            continue
        if target is not None and target.is_dir():
            continue
        severity = SEVERITY_WARNING
        detail = "the target cannot be read here, so its line endings are unknown"
        if target is not None and target.is_file():
            data = _target_bytes(target)
            if data is None or b"\r\n" not in data:
                continue
            severity = SEVERITY_ERROR
            detail = (
                f"{target.name} carries CRLF line endings, so `$` never matches "
                "before the carriage return and the gate returns 0 on a correct file"
            )
        findings.append(
            make_finding(
                check=9,
                severity=severity,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This pattern anchors on `$` with no `\\r?` guard; "
                    f"{detail}. Anchor on `^` only, write `\\r\\?$`, or "
                    "normalise with `tr -d '\\r'` first"
                ),
            )
        )
    return findings


def _check10_single_term_coverage_count(context: LintContext) -> list:
    """Check 10 -- ``grep -c <one word> <file>.md`` against a threshold of two
    or more. ``grep -c`` counts lines, and a soft-wrapped paragraph is one
    line, so the number measures layout: a well-written paragraph that covers
    every clause fails it, and repeating the word anywhere passes it.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        if _INVARIANT_TOKEN in command.annotation:
            continue
        stage, stages = _first_grep_stage(command)
        if stage is None or stage[0] != "grep" or len(stages) != 1:
            continue
        if not _has_count_flag(stage):
            continue
        pattern, target = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None or target is None or not _SINGLE_WORD_RE.match(pattern):
            continue
        if target.suffix.lower() != ".md":
            continue
        expectation = _parse_expectation(_note_for(command))
        if expectation is None or expectation.comparator not in (">=", ">") or expectation.value < 2:
            continue
        findings.append(
            make_finding(
                check=10,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    f"This gate counts lines holding the single term {pattern!r} "
                    "in a prose file against a threshold of "
                    f"{expectation.comparator}{expectation.value}. `grep -c` "
                    "counts lines, so the number measures layout, not coverage: "
                    "a well-written paragraph fails it and a padded one passes. "
                    "Assert each clause by its own distinctive phrase, or use "
                    "`grep -o … | wc -l` and say what an occurrence count proves"
                ),
            )
        )
    return findings


def _check11_verdict_pattern_drops_emphasis(context: LintContext) -> list:
    """Check 11 -- a verdict-line pattern typed from the rendered line. A
    skeleton that prescribes ``**Gate:** PASS`` puts two asterisks between the
    label and the value, so ``grep 'Gate: PASS'`` returns 0 on a passing
    artifact. ERROR when the target file exists and carries the bold form,
    WARNING when the target does not exist yet, silent when the target carries
    the bare form the pattern matches.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        stage, _ = _first_grep_stage(command)
        if stage is None:
            continue
        pattern, target = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None:
            continue
        match = _VERDICT_LABEL_RE.search(pattern)
        if not match or "*" in match.group(0):
            continue
        label = match.group(1)
        severity = SEVERITY_WARNING
        detail = "the target cannot be read here, so copy the verdict line's bytes from its skeleton"
        if target is not None and target.is_file():
            data = _target_bytes(target)
            if data is None:
                continue
            text = data.decode("utf-8", errors="replace")
            if f"**{label}:**" in text:
                severity = SEVERITY_ERROR
                detail = (
                    f"{target.name} writes the line as `**{label}:** …`, so the "
                    "literal the pattern wants is absent and the gate returns 0 "
                    "on a passing artifact"
                )
            else:
                continue
        findings.append(
            make_finding(
                check=11,
                severity=severity,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    f"This pattern reads the verdict label `{label}:` with no "
                    f"emphasis between label and value; {detail}. Use "
                    f"`grep -cF '**{label}:** …'` or `\\*\\*{label}:\\*\\* …`, "
                    "and dry-run it on a passing and a failing copy"
                ),
            )
        )
    return findings


def _check12_heading_counted_by_substring(context: LintContext) -> list:
    """Check 12 -- a heading counted by substring. A pattern that starts with
    the heading marker and no ``^`` also matches every prose line that quotes
    the heading, which the plan that defines the convention always does.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        stage, _ = _first_grep_stage(command)
        if stage is None:
            continue
        pattern, _ = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None or not _HEADING_PATTERN_RE.match(pattern):
            continue
        findings.append(
            make_finding(
                check=12,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    f"This pattern counts a Markdown heading by substring ({pattern!r}), "
                    "so every prose line that quotes the heading counts too. Anchor it "
                    "at the start of the line (`^## …`) and record both counts when "
                    "they differ"
                ),
            )
        )
    return findings


def _check13_bare_numeric_literal(context: LintContext) -> list:
    """Check 13 -- a pattern that is nothing but digits. It matches every
    longer number that contains it, and the near-multiples of one constant
    co-occur in exactly the files where the constant is searched for.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        stage, _ = _first_grep_stage(command)
        if stage is None:
            continue
        pattern, _ = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None or not _BARE_DIGITS_RE.match(pattern):
            continue
        findings.append(
            make_finding(
                check=13,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    f"This pattern is the bare number {pattern}, which also matches "
                    f"{pattern}0 and 1{pattern}. Guard the digit boundaries: "
                    f"`grep -E '(^|[^0-9]){pattern}([^0-9]|$)'`; `\\b` is not enough, "
                    "because a digit is a word character"
                ),
            )
        )
    return findings


def _is_context_flag(token: str) -> bool:
    return bool(_CONTEXT_FLAG_RE.match(token))


def _check14_context_window_counted(context: LintContext) -> list:
    """Check 14 -- a pipeline that counts the output of a ``grep -B/-A/-C``
    context window. The window emits the matching line as well as its
    neighbours, so a per-hit budget is off by the hit count, and a tag written
    on the same line as its call is invisible to a filter aimed at the
    neighbouring line.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        argv = _static_argv(command.command)
        if not argv:
            continue
        stages = _pipeline_stages(argv)
        if len(stages) < 2:
            continue
        window_at = None
        for index, stage in enumerate(stages):
            if stage[0] == "grep" and any(_is_context_flag(token) for token in stage[1:]):
                window_at = index
                break
        if window_at is None:
            continue
        counted = False
        for stage in stages[window_at + 1:]:
            if stage[0] == "grep" and _has_count_flag(stage):
                counted = True
            if stage[0] == "wc":
                counted = True
        if not counted:
            continue
        findings.append(
            make_finding(
                check=14,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This pipeline counts the output of a grep context window. "
                    "The window emits the matching line as well as its neighbours, "
                    "so a per-hit budget is off by the hit count, and a tag on the "
                    "same line as its call is invisible to a filter aimed at the "
                    "neighbouring line. Count the shape on one line, or assert each "
                    "site by anchor"
                ),
            )
        )
    return findings


def _check15_anchored_aggregate_threshold(context: LintContext) -> list:
    """Check 15 -- an anchored aggregate count threshold: ``grep -c '^…'``
    against ``>= N`` with N of two or more. If the sibling tasks produce more
    than one format for the counted construct, the threshold is structurally
    unreachable, and the verifier either fails correct work or fudges to PASS.
    """
    findings = []
    for command in context.commands:
        if command.is_placeholder or not command.is_gate:
            continue
        if _INVARIANT_TOKEN in command.annotation:
            continue
        stage, stages = _first_grep_stage(command)
        if stage is None or stage[0] != "grep" or len(stages) != 1:
            continue
        if not _has_count_flag(stage):
            continue
        pattern, _ = _grep_pattern_and_target(stage, context.plan_root)
        if pattern is None or not pattern.startswith("^"):
            continue
        expectation = _parse_expectation(_note_for(command))
        if expectation is None or expectation.comparator not in (">=", ">") or expectation.value < 2:
            continue
        findings.append(
            make_finding(
                check=15,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This gate ships an anchored aggregate count threshold "
                    f"({expectation.comparator}{expectation.value} over {pattern!r}) as "
                    "its verdict. If the sibling tasks produce more than one format "
                    "for the counted construct, the threshold is unreachable on "
                    "correct work. Enumerate the units and assert the property per "
                    "unit; derive any total from the per-unit results"
                ),
            )
        )
    return findings


def _pytest_path_arguments(stage: list):
    """Return the positional path arguments of a pytest stage, or None when the
    stage is not a pytest invocation."""
    if stage[0] == "pytest":
        rest = stage[1:]
    elif stage[0] in ("python", "python3", "py") and "-m" in stage:
        at = stage.index("-m")
        if at + 1 >= len(stage) or stage[at + 1] != "pytest":
            return None
        rest = stage[at + 2:]
    else:
        return None
    positional = []
    skip_next = False
    for token in rest:
        if skip_next:
            skip_next = False
            continue
        if token in _PYTEST_VALUE_FLAGS:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        positional.append(token)
    return positional


def _check16_unscoped_suite_gate(context: LintContext) -> list:
    """Check 16 -- a task file's Before or After gate that runs ``pytest`` with
    no path argument. The whole suite costs minutes per task and moves for
    reasons outside the task. A per-task gate names the task's own test files;
    a whole-suite baseline is measured once per plan with its tree identity
    recorded. A Master Plan or Sprint Plan is where that once-per-plan value
    belongs, so those files are exempt.
    """
    findings = []
    for command in context.commands:
        if command.block not in (BLOCK_BEFORE, BLOCK_AFTER):
            continue
        if command.is_placeholder or not command.is_gate:
            continue
        if command.file.endswith(_PLAN_LEVEL_SUFFIXES):
            continue
        argv = _static_argv(command.command)
        if not argv:
            continue
        stages = _pipeline_stages(argv)
        if not stages:
            continue
        positional = _pytest_path_arguments(stages[0])
        if positional is None or positional:
            continue
        findings.append(
            make_finding(
                check=16,
                severity=SEVERITY_WARNING,
                file=command.file,
                line=command.line,
                command=command.command,
                message=(
                    "This per-task gate runs the whole test suite: the pytest "
                    "invocation carries no path argument, so the measurement costs "
                    "minutes and moves for reasons outside the task. Scope it to the "
                    "task's own test files, and measure any whole-suite baseline once "
                    "per plan with its tree identity recorded"
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
        _check8_grep_tool_escaped_pipe_alternation,
        _check9_dollar_anchor_over_crlf_target,
        _check10_single_term_coverage_count,
        _check11_verdict_pattern_drops_emphasis,
        _check12_heading_counted_by_substring,
        _check13_bare_numeric_literal,
        _check14_context_window_counted,
        _check15_anchored_aggregate_threshold,
        _check16_unscoped_suite_gate,
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
#
# The first line of stdout is always a ``Coverage:`` line. It starts with
# ``Coverage: NOT CHECKED`` when gates exist and the executor ran none of them.
# That case still exits 1 (all findings are UNCERTAIN), so the line is the only
# signal that separates it from a scan that found real advisory findings.
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
        help="Disable the read-only executor; only the static checks run",
    )
    args, _ = parser.parse_known_args()

    plan_root = Path(args.plan_root)
    if not plan_root.exists():
        print(f"Error: plan root not found at {plan_root}", file=sys.stderr)
        sys.exit(EXIT_ERROR_PRESENT)

    findings, context = _lint(plan_root, execute=not args.no_execute)
    print(coverage_line(context))

    if not findings:
        print("No findings.")
        sys.exit(EXIT_NO_FINDINGS)

    _print_findings(findings)

    if any(finding["severity"] == SEVERITY_ERROR for finding in findings):
        sys.exit(EXIT_ERROR_PRESENT)
    sys.exit(EXIT_ADVISORY_ONLY)


if __name__ == "__main__":
    main()
