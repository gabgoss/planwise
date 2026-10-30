#!/usr/bin/env python3
"""Check the section structure of task files against the verification rules.

A task file that produces code, tests, a schema, a migration or a notebook must
say how its output is verified. The plan reviewer checks this by reading the
file. This script makes the structural part of those reviewer checks
mechanical. It reads a task file's ``**Output:**`` line, its
``## Expected Output`` section and its ``## Verification Commands`` section, and
reports what is missing.

Rules, each named after the reviewer check it mechanises (the checks live in
``references/gate-exit-verdict-and-smoke-reports.md``):

``verification-section`` (Reviewer Checks 013 and 014)
    A task whose output names code, test, schema, migration or notebook files
    has a ``## Verification Commands`` heading. The section holds at least one
    ``{...-cmd}`` placeholder row or at least one concrete command line in a
    fenced block under a ``**Before`` or ``**After`` label. A template slot such as ``{cmd_after_1}`` left in the section
    is a slot nobody filled, never a command.

``per-type-commands`` (Reviewer Checks 034, 035 and 036)
    Notebook output carries an execution command. Code output carries a lint
    command, and a format command too when the section uses the placeholder
    table. Database-write output carries a connectivity check in the Before
    block, never only in the After block.

``verify-callout`` (Reviewer Check 015)
    A task whose output is runnable (code, a notebook or a migration) carries a
    ``> [!verify]`` callout that holds both a ``**Before`` and an ``**After``
    line.

Placeholder versus inline commands. The template's Per-File-Type table is one
way to satisfy the section rule, not the only way. A plan may omit the table
and write concrete commands inline. The script therefore never asks for the
table. It asks for a ``{...-cmd}`` placeholder OR a concrete command, and it
satisfies each per-type rule with the placeholder OR a recognised concrete
command (``ruff check`` for lint, ``ruff format`` for format, and so on). The
format row belongs to the table, so a section with concrete commands and no
placeholder owes a lint command but no separate formatter: a project that pins
one lint command carries its style rules in that linter's configuration. A
placeholder slot left unfilled is told apart from an omitted table by its
shape: ``{cmd_before_N}`` and ``{cmd_after_N}`` are slots, and a section whose
only fenced lines are slots, comments or ``<!-- NEEDS-COMMAND -->`` markers
holds no command.

Exemption. The comment ``<!-- VERIFICATION: not-applicable (reason) -->`` with
a non-empty reason, outside a fenced block, exempts the whole file.

Output is one line per finding, ``{file}:{line}: {severity}: {message}``.
Exit status: 0 when no finding, 1 on any finding, 2 on a usage error (a path
that does not exist, or no task file found under the given paths).

The section reader follows the literal fence rule of
``markdown_parser.extract_headings``: a line whose first non-space characters
are three backticks toggles a fence, and a blockquoted fence line never does
for heading purposes.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__
from markdown_parser import extract_headings

EXIT_CLEAN = 0
EXIT_FINDING = 1
EXIT_USAGE = 2

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"

RULE_SECTION = "verification-section"
RULE_PER_TYPE = "per-type-commands"
RULE_CALLOUT = "verify-callout"

# {Abbrev}-S{XX}-{YY}-{##}-{Agent}-{TaskName}.md, per templates/task-file.md.
_TASK_FILE_NAME_RE = re.compile(
    r"^[A-Za-z0-9]+-S\d{2}-\d{2}-\d{2}-(?:Haiku|Sonnet|Opus)-[^/\\]+\.md$"
)
_TASK_ID_RE = re.compile(r"^\*\*Task ID:\*\*", re.MULTILINE)
_OUTPUT_FIELD_RE = re.compile(r"^\*\*Output:\*\*(.*)$")
_EXEMPTION_RE = re.compile(
    r"<!--\s*VERIFICATION:\s*not-applicable\s*\(\s*([^)]*?)\s*\)\s*-->", re.IGNORECASE
)
_BLOCKQUOTE_RE = re.compile(r"^\s*>[ \t]?")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_RE = re.compile(r"^\s*```")

# Placeholder vocabulary of the template's Per-File-Type table.
_CMD_PLACEHOLDER_RE = re.compile(r"\{[a-z][a-z-]*-cmd\}")
# A Before/After slot of the template that nobody filled in.
_UNFILLED_SLOT_RE = re.compile(r"\{cmd_(?:before|after)_[A-Za-z0-9]+\}")
_NEEDS_COMMAND_RE = re.compile(r"<!--\s*NEEDS-COMMAND\s*-->")
_ONLY_PLACEHOLDER_RE = re.compile(r"^(?:\{[^{}]*\}\s*)+(?:#.*)?$")

# A file path token with an extension: backticked spans and bare words both.
_PATH_TOKEN_RE = re.compile(r"[\w./\\{}*-]+\.([A-Za-z0-9]+)\b")

_CODE_EXTENSIONS = frozenset(
    {
        "py", "js", "mjs", "cjs", "ts", "tsx", "jsx", "go", "rs", "java", "kt",
        "cs", "rb", "php", "sh", "bash", "ps1", "psm1", "c", "h", "cpp", "hpp",
        "cc", "swift", "scala", "lua", "pl", "r",
    }
)
_NOTEBOOK_EXTENSIONS = frozenset({"ipynb"})
_SCHEMA_EXTENSIONS = frozenset({"sql", "ddl", "prisma", "graphql", "gql", "avsc", "proto"})
_MIGRATION_WORD_RE = re.compile(r"\bmigrations?/", re.IGNORECASE)

# Concrete commands that satisfy a per-type rule in place of its placeholder.
# A placeholder starts with "{", so it sits outside the leading word boundary.
_LINT_COMMAND_RE = re.compile(
    r"\{lint-cmd\}|\b(?:ruff\s+check|flake8|pylint|eslint|mypy|pyright|"
    r"golangci-lint|cargo\s+clippy|shellcheck|rubocop|tsc|Invoke-ScriptAnalyzer)\b",
    re.IGNORECASE,
)
_FORMAT_COMMAND_RE = re.compile(
    r"\{format-cmd\}|\b(?:ruff\s+format|black|isort|prettier|gofmt|cargo\s+fmt|"
    r"dotnet\s+format|clang-format|rustfmt)\b",
    re.IGNORECASE,
)
_EXEC_COMMAND_RE = re.compile(
    r"\{(?:notebook-)?exec-cmd\}|\b(?:nbconvert[^\n]*--execute|papermill|nbclient|"
    r"nbmake|nbval)\b",
    re.IGNORECASE,
)
_CONNECTIVITY_COMMAND_RE = re.compile(
    r"(?:\{connectivity-check-cmd\}|\bpg_isready\b|\bmysqladmin\s+ping\b|"
    r"\bselect\s+1\b)",
    re.IGNORECASE,
)
_SCHEMA_PIN_RE = re.compile(r"^\*\*Schema Pin\*\*")
_VERIFY_CALLOUT_RE = re.compile(r"^\s*>\s*\[!verify\]", re.IGNORECASE)
_BEFORE_LABEL_RE = re.compile(r"^\*\*Before\b", re.IGNORECASE)
_AFTER_LABEL_RE = re.compile(r"^\*\*After\b", re.IGNORECASE)


@dataclass
class Finding:
    """One structural finding, citing the line it anchors to."""

    file: str
    line: int
    severity: str
    rule: str
    message: str

    def render(self) -> str:
        return f"{self.file}:{self.line}: {self.severity}: [{self.rule}] {self.message}"


@dataclass
class OutputKinds:
    """Which kinds of artifact a task's output names."""

    code: bool = False
    notebook: bool = False
    schema: bool = False
    migration: bool = False
    db_write: bool = False

    @property
    def needs_verification(self) -> bool:
        return self.code or self.notebook or self.schema or self.migration

    @property
    def runnable(self) -> bool:
        return self.code or self.notebook or self.migration


@dataclass
class Section:
    """One ``##`` section: its heading line and its body lines, 1-based."""

    heading_line: int
    lines: list


def _strip_blockquote(line: str) -> str:
    match = _BLOCKQUOTE_RE.match(line)
    return line[match.end():] if match else line


def _unfenced_lines(lines: list) -> list:
    """Return (number, line) pairs outside fenced code, by the literal fence rule."""
    kept = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append((number, line))
    return kept


def _sections(text: str, lines: list) -> dict:
    """Map each ``##`` heading title (lower case) to its section.

    A section runs from its heading to the next heading of level 1 or 2, so a
    ``###`` subsection stays inside it. The first section of a title wins.
    """
    headings = extract_headings(text)
    found: dict = {}
    top = [h for h in headings if h.level <= 2]
    for index, heading in enumerate(top):
        if heading.level != 2:
            continue
        end = top[index + 1].line - 1 if index + 1 < len(top) else len(lines)
        title = heading.title.split("<!--")[0].strip().lower()
        if title not in found:
            found[title] = Section(heading.line, lines[heading.line:end])
    return found


def _section_starting(sections: dict, prefix: str):
    for title, section in sections.items():
        if title.startswith(prefix):
            return section
    return None


def _kinds_of(text: str) -> OutputKinds:
    kinds = OutputKinds()
    for match in _PATH_TOKEN_RE.finditer(text):
        ext = match.group(1).lower()
        token = match.group(0)
        if ext in _CODE_EXTENSIONS:
            kinds.code = True
        elif ext in _NOTEBOOK_EXTENSIONS:
            kinds.notebook = True
        elif ext in _SCHEMA_EXTENSIONS:
            kinds.schema = True
            if ext in ("sql", "ddl"):
                kinds.db_write = True
        if _MIGRATION_WORD_RE.search(token):
            kinds.migration = True
            kinds.db_write = True
    return kinds


def _output_text(lines: list, sections: dict) -> tuple:
    """Return the text that names the task's output, and the Output line number."""
    parts = []
    output_line = 1
    for number, line in _unfenced_lines(lines):
        match = _OUTPUT_FIELD_RE.match(line.strip())
        if match:
            parts.append(match.group(1))
            output_line = number
            break
    expected = _section_starting(sections, "expected output")
    if expected is not None:
        body = []
        in_fence = False
        for line in expected.lines:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            # A ### subsection of Expected Output is template guidance (the
            # moved-references slot), not a statement of what is produced.
            if line.startswith("### "):
                break
            body.append(line)
        parts.append(_HTML_COMMENT_RE.sub("", "\n".join(body)))
    return "\n".join(parts), output_line


def _fenced_command_lines(section: Section) -> list:
    """Return (line number, text, block) for each line inside a fence in ``section``.

    ``block`` is ``Before`` or ``After`` when a ``**Before`` or ``**After``
    label stands above the fence, and ``""`` otherwise. A label is claimed by
    the next fence only, so an illustrative fence later in the section (a
    WRONG/CORRECT exemplar) carries no block and is not a command.
    """
    result = []
    in_fence = False
    pending = ""
    block = ""
    for offset, raw in enumerate(section.lines, start=1):
        number = section.heading_line + offset
        line = _strip_blockquote(raw).rstrip()
        stripped = line.strip()
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            if in_fence:
                block, pending = pending, ""
            continue
        if in_fence:
            result.append((number, stripped, block))
            continue
        if _BEFORE_LABEL_RE.match(stripped):
            pending = "Before"
        elif _AFTER_LABEL_RE.match(stripped):
            pending = "After"
    return result


def _is_concrete_command(text: str) -> bool:
    if not text or text.startswith("#"):
        return False
    if _NEEDS_COMMAND_RE.search(text) or text.startswith("<!--"):
        return False
    if _UNFILLED_SLOT_RE.search(text):
        return False
    return not _ONLY_PLACEHOLDER_RE.match(text)


def _exemption(lines: list) -> bool:
    for _number, line in _unfenced_lines(lines):
        match = _EXEMPTION_RE.search(line)
        if match and match.group(1):
            return True
    return False


def _verify_callout_complete(lines: list) -> tuple:
    """Return (callout found, has Before, has After) for the first complete callout."""
    found = False
    for number, line in _unfenced_lines(lines):
        if not _VERIFY_CALLOUT_RE.match(line):
            continue
        found = True
        before = after = False
        for raw in lines[number:]:
            if not _BLOCKQUOTE_RE.match(raw):
                break
            body = _strip_blockquote(raw).strip()
            before = before or bool(_BEFORE_LABEL_RE.match(body))
            after = after or bool(_AFTER_LABEL_RE.match(body))
        if before and after:
            return True, True, True
    return found, False, False


def lint_text(text: str, name: str) -> list:
    """Return the findings for one task file's text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if _exemption(lines):
        return []
    sections = _sections(text, lines)
    output_text, output_line = _output_text(lines, sections)
    kinds = _kinds_of(output_text)
    if any(_SCHEMA_PIN_RE.match(line) for _n, line in _unfenced_lines(lines)):
        kinds.db_write = True
    findings: list = []
    if not kinds.needs_verification:
        return findings

    verification = _section_starting(sections, "verification commands")
    if verification is None:
        findings.append(
            Finding(name, output_line, SEVERITY_BLOCKER, RULE_SECTION,
                    "Reviewer Check 013: output names code, test, schema, migration "
                    "or notebook files, but the file has no '## Verification Commands' "
                    "section")
        )
    else:
        body = "\n".join(verification.lines)
        fenced = _fenced_command_lines(verification)
        commands = [t for _n, t, b in fenced if b and _is_concrete_command(t)]
        placeholders = _CMD_PLACEHOLDER_RE.findall(body)
        # Only a fenced line is a command line. Prose that names a slot, as the
        # template's own instructions do, is not a slot left unfilled.
        slots = [s for _n, t, _b in fenced for s in _UNFILLED_SLOT_RE.findall(t)]
        if slots:
            findings.append(
                Finding(name, verification.heading_line, SEVERITY_BLOCKER, RULE_SECTION,
                        "Reviewer Check 014: template slot left unfilled in Verification "
                        f"Commands ({', '.join(sorted(set(slots)))})")
            )
        if not placeholders and not commands:
            findings.append(
                Finding(name, verification.heading_line, SEVERITY_BLOCKER, RULE_SECTION,
                        "Reviewer Check 014: Verification Commands holds no {...-cmd} "
                        "placeholder row and no concrete command")
            )
        findings.extend(_per_type_findings(name, verification, kinds, body))

    if kinds.runnable:
        found, before, after = _verify_callout_complete(lines)
        if not (before and after):
            anchor = verification.heading_line if verification else output_line
            detail = ("has no '> [!verify]' callout" if not found
                      else "has a '> [!verify]' callout without both **Before and **After")
            findings.append(
                Finding(name, anchor, SEVERITY_BLOCKER, RULE_CALLOUT,
                        f"Reviewer Check 015: task with a runnable output {detail}")
            )
    return findings


def _per_type_findings(name: str, section: Section, kinds: OutputKinds, body: str) -> list:
    findings: list = []
    anchor = section.heading_line
    if kinds.notebook and not _EXEC_COMMAND_RE.search(body):
        findings.append(
            Finding(name, anchor, SEVERITY_ERROR, RULE_PER_TYPE,
                    "Reviewer Check 034: notebook output but no {exec-cmd} or notebook "
                    "execution command in Verification Commands")
        )
    if kinds.code:
        missing = []
        has_lint = bool(_LINT_COMMAND_RE.search(body))
        if not has_lint:
            missing.append("lint ({lint-cmd})")
        # The format half is a row of the placeholder table. A section that
        # uses the table's vocabulary owes {format-cmd} or a formatter. A
        # section that omits the table and pins concrete commands inline owes
        # a lint command, and that command carries the project's style rules.
        uses_table = bool(_CMD_PLACEHOLDER_RE.search(body))
        if uses_table and not _FORMAT_COMMAND_RE.search(body):
            missing.append("format ({format-cmd})")
        if missing:
            findings.append(
                Finding(name, anchor, SEVERITY_ERROR, RULE_PER_TYPE,
                        "Reviewer Check 035: code output but Verification Commands has "
                        f"no {' or '.join(missing)} command")
            )
    if kinds.db_write and not _connectivity_in_before(section):
        where = ("is in the After block only" if _CONNECTIVITY_COMMAND_RE.search(body)
                 else "is absent")
        findings.append(
            Finding(name, anchor, SEVERITY_WARNING, RULE_PER_TYPE,
                    "Reviewer Check 036: database-write output, but the connectivity "
                    f"check {where}; it belongs in the Before block")
        )
    return findings


def _connectivity_in_before(section: Section) -> bool:
    """True when a fenced line under a ``**Before`` label names a connectivity check."""
    for _n, text, block in _fenced_command_lines(section):
        if block == "Before" and _CONNECTIVITY_COMMAND_RE.search(text):
            return True
    return False


def _is_task_file(path: Path) -> bool:
    if not _TASK_FILE_NAME_RE.match(path.name):
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_TASK_ID_RE.search(head))


def collect_task_files(paths: list) -> tuple:
    """Return (task files, missing paths) for the given files or directories.

    A directory is walked recursively, and only files named and shaped like a
    task file are kept. A file named directly is kept when it carries a
    ``**Task ID:**`` line, whatever its name.
    """
    files: list = []
    missing: list = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            missing.append(raw)
            continue
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                missing.append(raw)
                continue
            if _TASK_ID_RE.search(text):
                files.append(path)
            continue
        files.extend(p for p in sorted(path.rglob("*.md")) if _is_task_file(p))
    return files, missing


def lint_paths(paths: list) -> tuple:
    """Return (findings, files checked, usage error or None)."""
    files, missing = collect_task_files(paths)
    if missing:
        return [], files, f"path not found: {', '.join(missing)}"
    if not files:
        return [], files, "no task file found under the given paths"
    findings: list = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(lint_text(text, path.as_posix()))
    return findings, files, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check task-file section structure against the verification rules."
    )
    parser.add_argument("paths", nargs="+", help="task files or plan directories")
    args = parser.parse_args(argv)
    findings, files, error = lint_paths(args.paths)
    if error:
        print(f"usage error: {error}", file=sys.stderr)
        return EXIT_USAGE
    for finding in findings:
        print(finding.render())
    print(f"checked {len(files)} task file(s); {len(findings)} finding(s)", file=sys.stderr)
    return EXIT_FINDING if findings else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
