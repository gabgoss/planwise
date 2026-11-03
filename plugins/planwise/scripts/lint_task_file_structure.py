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

``used-helper`` (Reviewer Check 030, ``references/verify-before-cite.md`` §9.B.7)
    A task whose Required Context or Execution Steps pair a copy, reuse or port
    verb with a ``.py`` path has a ``## USED-Helper Enumeration`` heading (or
    the template's ``###`` form). Severity WARNING.

``field-mapping`` (Reviewer Check 033, ``references/verify-before-cite.md`` §9.B.8)
    A task whose Execution Steps match ``MERGE|UPSERT|ON CONFLICT`` has a
    line-anchored ``### Field Mapping`` heading. Severity WARNING.

``schema-pin`` (``references/verify-before-cite.md`` §9.B.5)
    A task whose Execution Steps carry SQL-emitting verbs has a Schema Pin
    section and a ``Pre-SQL Schema Verification`` block in Notes for Agent.
    Severity WARNING. The message tells "neither present" (the reference's
    flag condition) from "one of the two is absent".

The three content rules report at WARNING because they match prose, and a run
over two live plan trees showed false positives for each. Reviewer Checks 030
and 033 are BLOCKER in the reference; the lint does not gate on a heuristic.

The three content rules read the section text. They run only for a task file
whose output the module classifies as code, a notebook, a schema or a
migration, and the verification exemption silences them too. ``field-mapping``
matches upper-case MERGE, UPSERT and ON CONFLICT in prose, and any case inside
a fence or inline code.
They are heuristics over prose: a hit is a finding to read, not a proof.

Four cross-repo fix-task rules (``references/verify-cross-repo-fix-discipline.md``
§7) fire only on a task that edits a file in another repository. That file is a
target: a path the ``**Output:**`` line names and a Required Context row names
too. It is cross-repo when it resolves outside the repository that holds the
task file, or inside a nested repository below it (§7.7). A Required Context
path the task only reads is no target, so the §7.6 exempt types (audit,
research, decision and triage tasks, which write an in-repo report) never fire.

``cross-repo-binding-source`` (§7.2, BLOCKER)
    A Priority 1 Required Context row names the target and carries
    ``BINDING SOURCE — full read required``. When the task file has no
    repository root to resolve against, the rule cannot decide and reports a
    WARNING naming the path, never a BLOCKER.

``cross-repo-step1-read`` (§7.3, BLOCKER; Reviewer Check 066 (a))
    Execution Step 1 matches ``Read .* in full before any fix reasoning``.

``cross-repo-parser-gate`` (§7.3d, WARNING; Reviewer Check 066 (c))
    An ``**Output:**`` line that names a ``.yaml``, ``.yml``, ``.json`` or
    ``.toml`` file has a ``safe_load``, ``json.load`` or ``tomllib`` gate in
    Success Criteria. A structured file Expected Output only mentions is not a
    file the task writes.

``cross-repo-naked-line-ref`` (§7.3a, WARNING; Reviewer Check 066 (b))
    A step after Step 1 that names ``line N``, ``Step N.N`` or ``LN`` carries a
    content anchor on the same line: a quoted string, a section citation, or a
    code span that is neither a bare path nor a number. Judging the anchor is heuristic, so the
    rule reports and never gates on its own.

These four run on documentation tasks too, and the verification exemption does
not silence them.

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
a non-empty reason, outside a fenced block, exempts the file from every rule
except the four cross-repo rules.

Output is one line per finding, ``{file}:{line}: {severity}: {message}``.
Exit status: 0 when no finding, 1 on any finding, 2 on a usage error (a path
that does not exist, or no task file found under the given paths).

The section reader follows the literal fence rule of
``markdown_parser.extract_headings``: a line whose first non-space characters
are three backticks toggles a fence, and a blockquoted fence line never does
for heading purposes.
"""

import argparse
import os
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
RULE_USED_HELPER = "used-helper"
RULE_FIELD_MAPPING = "field-mapping"
RULE_SCHEMA_PIN = "schema-pin"
RULE_CROSS_REPO_BINDING = "cross-repo-binding-source"
RULE_CROSS_REPO_STEP_ONE = "cross-repo-step1-read"
RULE_CROSS_REPO_PARSER = "cross-repo-parser-gate"
RULE_CROSS_REPO_LINE_REF = "cross-repo-naked-line-ref"

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

# Content rules: helper enumeration, field mapping, schema pin.
_HELPER_VERB_RE = re.compile(
    r"\b(?:cop(?:y|ies|ying|ied)|reus(?:e|es|ing|ed)|port(?:s|ing|ed)?)\b",
    re.IGNORECASE,
)
_PY_PATH_RE = re.compile(r"[\w./\\-]*[\w-]\.py\b")
_USED_HELPER_HEADING_RE = re.compile(r"^#{2,3}[ \t]+USED-Helper Enumeration\b")
# Upper-case in prose, any case inside a fence or inline code. Lower-case
# prose ("merge the lists") never triggers.
_MERGE_UPPER_RE = re.compile(r"\b(?:MERGE|UPSERT|ON CONFLICT)\b")
_MERGE_CODE_RE = re.compile(r"\b(?:MERGE|UPSERT|ON\s+CONFLICT)\b", re.IGNORECASE)
_FIELD_MAPPING_HEADING_RE = re.compile(r"^### Field Mapping\b")
# Upper-case SQL verbs count in prose. Lower-case prose ("update the docs") never does.
_SQL_UPPER_VERB_RE = re.compile(r"\b(?:INSERT|UPDATE|MERGE|CREATE TABLE|ALTER TABLE)\b")
# A statement shape counts in any case, inside a fence or inline code.
_SQL_STATEMENT_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE\s+[\w.\"`\[\]]+\s+SET|MERGE\s+INTO|"
    r"CREATE\s+TABLE|ALTER\s+TABLE)\b",
    re.IGNORECASE,
)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_SCHEMA_PIN_HEADING_RE = re.compile(r"^#{2,4}[ \t]+Schema Pin\b")
_STRUCTURE_SUBSECTION_RE = re.compile(
    r"^#{3,4}[ \t]+(?:Schema Pin|Field Mapping|USED-Helper Enumeration)\b"
)
_PRE_SQL_TEXT ="Pre-SQL Schema Verification"

# Cross-repo fix-task rules (references/verify-cross-repo-fix-discipline.md §7).
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_PATH_SUFFIX_RE = re.compile(r"(?:#[\w-]*|:\d+(?:-\d+)?)$")
_BINDING_ROW_RE = re.compile(r"BINDING SOURCE\s*[—–-]{1,2}\s*full read required")
_PRIORITY_ONE_ROW_RE = re.compile(r"^\|\s*1\s*\|")
_STEP1_READ_RE = re.compile(r"\bRead .* in full before any fix reasoning")
_TOP_STEP_RE = re.compile(r"^(\d+)\.\s")
_STRUCTURED_EXT_RE = re.compile(r"\.(?:ya?ml|json|toml)\b", re.IGNORECASE)
_PARSER_GATE_RE = re.compile(r"safe_load|json\.loads?\b|tomllib")
_NAKED_LINE_REF_RE = re.compile(r"\blines? \d+|\bStep \d+\.\d+|\bL\d+\b", re.IGNORECASE)
_QUOTED_ANCHOR_RE = re.compile(r"\"[^\"\n]{3,}\"|“[^”\n]{3,}”")
_PATH_LIKE_SPAN_RE = re.compile(
    r"^[\w.~-]*(?:[/\\][\w.~-]+)*\.[A-Za-z0-9]+(?::\d+(?:-\d+)?)?$|^[\w.~-]*(?:[/\\][\w.~-]*)+$"
)
_LINE_NUMBER_SPAN_RE = re.compile(r"^(?:L?\d+|lines? \d+|Step \d+(?:\.\d+)?)$", re.IGNORECASE)
_SECTION_ANCHOR_RE = re.compile(r"§\s?\d")
_XREF = "verify-cross-repo-fix-discipline.md"


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


def _section_items(section) -> list:
    """Return (line number, text, in_fence) for each non-fence line of ``section``.

    A missing section gives an empty list. HTML comments on one line are cut
    out, so template guidance in a comment is never a trigger.
    """
    if section is None:
        return []
    items = []
    in_fence = False
    skipping = False
    for offset, raw in enumerate(section.lines, start=1):
        line = _strip_blockquote(raw).rstrip()
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("#"):
            # The structure subsections are the required structure, not steps.
            skipping = bool(_STRUCTURE_SUBSECTION_RE.match(line))
        if skipping:
            continue
        items.append((section.heading_line + offset, _HTML_COMMENT_RE.sub("", line), in_fence))
    return items


def _unfenced_heading(lines: list, pattern) -> bool:
    """True when a line outside fences starts with the heading ``pattern``."""
    return any(pattern.match(line) for _n, line in _unfenced_lines(lines))


def _used_helper_findings(name: str, lines: list, sections: dict) -> list:
    """Rule ``used-helper``: a copied helper module needs an enumeration heading."""
    for key in ("required context", "execution steps"):
        for number, text, in_fence in _section_items(_section_starting(sections, key)):
            if in_fence or not _HELPER_VERB_RE.search(text) or not _PY_PATH_RE.search(text):
                continue
            if _unfenced_heading(lines, _USED_HELPER_HEADING_RE):
                return []
            return [Finding(name, number, SEVERITY_WARNING, RULE_USED_HELPER,
                            "Reviewer Check 030 (verify-before-cite.md §9.B.7): the task "
                            "copies, reuses or ports a helper module but has no "
                            "'USED-Helper Enumeration' heading")]
    return []


def _field_mapping_findings(name: str, lines: list, sections: dict) -> list:
    """Rule ``field-mapping``: MERGE or upsert steps need a ``### Field Mapping`` heading."""
    number = _sql_line(sections, _MERGE_UPPER_RE, _MERGE_CODE_RE)
    if number:
        if _unfenced_heading(lines, _FIELD_MAPPING_HEADING_RE):
            return []
        return [Finding(name, number, SEVERITY_WARNING, RULE_FIELD_MAPPING,
                        "Reviewer Check 033 (verify-before-cite.md §9.B.8): Execution "
                        "Steps match MERGE, UPSERT or ON CONFLICT but the file has no "
                        "'### Field Mapping' heading")]
    return []


def _sql_line(sections: dict, upper_re, code_re):
    """Return the line number of the first SQL trigger in Execution Steps, or 0.

    ``upper_re`` is tried on prose, case-sensitive. ``code_re`` is tried on a
    fenced line and on each inline code span.
    """
    for number, text, in_fence in _section_items(_section_starting(sections, "execution steps")):
        if in_fence:
            hit = code_re.search(text)
        else:
            spans = _INLINE_CODE_RE.findall(text)
            hit = upper_re.search(text) or any(code_re.search(span) for span in spans)
        if hit:
            return number
    return 0


def _schema_pin_findings(name: str, lines: list, sections: dict) -> list:
    """Rule ``schema-pin``: SQL verbs need a Schema Pin and a Pre-SQL verification block."""
    number = _sql_line(sections, _SQL_UPPER_VERB_RE, _SQL_STATEMENT_RE)
    if not number:
        return []
    has_pin = any(_SCHEMA_PIN_HEADING_RE.match(line) or _SCHEMA_PIN_RE.match(line)
                  for _n, line in _unfenced_lines(lines))
    notes = _section_starting(sections, "notes for agent")
    has_block = notes is not None and _PRE_SQL_TEXT in "\n".join(notes.lines)
    if has_pin and has_block:
        return []
    if not has_pin and not has_block:
        return [Finding(name, number, SEVERITY_WARNING, RULE_SCHEMA_PIN,
                        "verify-before-cite.md §9.B.5: Execution Steps emit SQL but the "
                        "file has neither a Schema Pin section nor a 'Pre-SQL Schema "
                        "Verification' block in Notes for Agent")]
    missing = "Schema Pin section" if not has_pin else "'Pre-SQL Schema Verification' block"
    return [Finding(name, number, SEVERITY_WARNING, RULE_SCHEMA_PIN,
                    "verify-before-cite.md §9.B.5: one of the two is absent (the "
                    f"{missing}); Execution Steps emit SQL")]


def _repo_root(path: Path):
    """Return the nearest ancestor of ``path`` (itself included) holding ``.git``, or None."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _path_tokens(text: str) -> list:
    """Return the file paths written as inline code in ``text``.

    A span with a space, a placeholder brace or a glob star is not a path. A
    trailing ``#anchor`` or ``:line`` is cut off.
    """
    tokens = []
    for span in _CODE_SPAN_RE.findall(text):
        span = span.strip()
        if not span or any(c in span for c in " {}*<>|"):
            continue
        span = _PATH_SUFFIX_RE.sub("", span)
        if "/" in span or "\\" in span or _PATH_TOKEN_RE.fullmatch(span):
            tokens.append(span)
    return tokens


def _resolve(token: str, task_dir: Path, plan_root: Path) -> Path:
    """Resolve a written path: absolute as given, relative against the task's folder
    when it exists there, else against the plan's repository root."""
    path = Path(token).expanduser()
    if path.is_absolute():
        return Path(os.path.normpath(path))
    local = Path(os.path.normpath(task_dir / path))
    if local.exists():
        return local
    return Path(os.path.normpath(plan_root / path))


def _is_cross_repo(path: Path, plan_root: Path) -> bool:
    """True when ``path`` lives outside the plan's repository (§7, §7.7).

    Outside the plan's root is cross-repo. Inside it, a nested repository (an
    ancestor below the root that holds ``.git``) is cross-repo too.
    """
    try:
        path.relative_to(plan_root)
    except ValueError:
        return True
    existing = path
    while not existing.exists() and existing != plan_root:
        existing = existing.parent
    root = _repo_root(existing)
    return root is not None and root != plan_root


def _canonical_targets(name: str, lines: list, sections: dict) -> tuple:
    """Return (cross-repo targets, undecided targets) for a task file.

    A target is a path the ``**Output:**`` line names that a Required Context
    row names too: the existing file the task fixes (§7.2). A Required Context
    path the task only reads is no target, so audit, research, decision and
    triage tasks (the §7.6 exempt types, which write an in-repo report) never
    trigger. A target is undecided when the task file has no repository root to
    resolve against. Each list holds (path text, Required Context line).
    """
    _line, output_tokens = _output_paths(lines)
    context =[(n, t) for n, t, f in _section_items(_section_starting(sections, "required context"))
               if not f and t.lstrip().startswith("|")]
    if not output_tokens or not context:
        return [], []
    location = Path(name)
    plan_root = _repo_root(location.resolve().parent) if location.is_file() else None
    if plan_root is None:
        names = {Path(t).as_posix() for t in output_tokens}
        undecided = []
        for number, text in context:
            undecided.extend((t, number) for t in _path_tokens(text) if Path(t).as_posix() in names)
        return [], _first_per_path(undecided)
    task_dir = location.resolve().parent
    outputs = {_resolve(t, task_dir, plan_root) for t in output_tokens}
    targets = []
    for number, text in context:
        for token in _path_tokens(text):
            resolved = _resolve(token, task_dir, plan_root)
            if resolved in outputs and _is_cross_repo(resolved, plan_root):
                targets.append((token, number, resolved))
    return _first_per_path(targets), []


def _output_paths(lines: list) -> tuple:
    """Return (Output line number, paths written as inline code on the Output line)."""
    for number, line in _unfenced_lines(lines):
        match = _OUTPUT_FIELD_RE.match(line.strip())
        if match:
            return number, _path_tokens(match.group(1))
    return 1, []


def _first_per_path(items: list) -> list:
    seen: set = set()
    kept = []
    for item in items:
        key = item[-1] if len(item) == 3 else item[0]
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept


def _binding_row_names(text: str, target, task_dir, plan_root) -> bool:
    """True when a Required Context row is a Priority 1 BINDING SOURCE row for ``target``."""
    plain = text.replace("*", "")
    if not _PRIORITY_ONE_ROW_RE.match(plain.lstrip()) or not _BINDING_ROW_RE.search(plain):
        return False
    tokens = _path_tokens(text)
    if plan_root is None:
        return target in tokens
    return any(_resolve(t, task_dir, plan_root) == target for t in tokens)


def _steps(sections: dict) -> tuple:
    """Return (Execution Steps section, step 1 items, later items) as (line, text) pairs.

    A step starts at a line opening with ``N.``. Fenced lines belong to the step
    they sit in.
    """
    section = _section_starting(sections, "execution steps")
    first: list = []
    later: list = []
    current = 0
    for number, text, _in_fence in _section_items(section):
        match = _TOP_STEP_RE.match(text)
        if match and not _in_fence:
            current = int(match.group(1))
        if current == 1:
            first.append((number, text))
        elif current > 1:
            later.append((number, text))
    return section, first, later


def _has_content_anchor(text: str) -> bool:
    """True when a line names its edit target by content: a quoted string or a
    code span that is neither a bare path nor a line or step number. A section
    citation (``§6``) names a heading, so it is an anchor too."""
    if _QUOTED_ANCHOR_RE.search(text) or _SECTION_ANCHOR_RE.search(text):
        return True
    for span in _CODE_SPAN_RE.findall(text):
        span = span.strip()
        if span and not _LINE_NUMBER_SPAN_RE.match(span) and not _PATH_LIKE_SPAN_RE.match(span):
            return True
    return False


def _cross_repo_findings(name: str, lines: list, sections: dict) -> list:
    """Rules 34 to 37 of the cross-repo fix-task discipline (§7.2, §7.3, §7.3d, §7.3a).

    They run on every task type that is not exempt, documentation tasks included,
    because a cross-repo fix may edit markdown. The verification exemption
    comment does not silence them: it exempts verification, not the fix.
    """
    targets, undecided = _canonical_targets(name, lines, sections)
    findings: list = []
    context = _section_items(_section_starting(sections, "required context"))
    for token, number in undecided:
        if any(_binding_row_names(t, token, None, None) for _n, t, f in context if not f):
            continue
        findings.append(Finding(
            name, number, SEVERITY_WARNING, RULE_CROSS_REPO_BINDING,
            f"{_XREF} §7.2: cannot decide whether '{token}' lives in another repository "
            "(no repository root above the task file); if it does, its Priority 1 row "
            "needs 'BINDING SOURCE — full read required'"))
    if not targets:
        return findings
    location = Path(name).resolve()
    task_dir, plan_root = location.parent, _repo_root(location.parent)
    for token, number, resolved in targets:
        if not any(_binding_row_names(t, resolved, task_dir, plan_root)
                   for _n, t, f in context if not f):
            findings.append(Finding(
                name, number, SEVERITY_BLOCKER, RULE_CROSS_REPO_BINDING,
                f"{_XREF} §7.2: '{token}' lives in another repository and the task edits it, "
                "but no Priority 1 Required Context row names it with 'BINDING SOURCE — "
                "full read required'"))
    section, first, later = _steps(sections)
    step1 = " ".join(t.replace("*", "") for _n, t in first)
    if not _STEP1_READ_RE.search(step1):
        anchor = first[0][0] if first else (section.heading_line if section else 1)
        findings.append(Finding(
            name, anchor, SEVERITY_BLOCKER, RULE_CROSS_REPO_STEP_ONE,
            f"{_XREF} §7.3: Execution Step 1 of a cross-repo fix task does not match "
            "'Read .* in full before any fix reasoning'"))
    # Only a path the Output line declares is a file the task writes. A
    # structured file Expected Output merely mentions (re-read, a report
    # heading) is not an edit.
    output_line, written = _output_paths(lines)
    if any(_STRUCTURED_EXT_RE.search(token) for token in written):
        criteria = _section_starting(sections, "success criteria")
        body = "\n".join(criteria.lines) if criteria else ""
        if not _PARSER_GATE_RE.search(body):
            anchor = criteria.heading_line if criteria else output_line
            findings.append(Finding(
                name, anchor, SEVERITY_WARNING, RULE_CROSS_REPO_PARSER,
                f"{_XREF} §7.3d: the output touches a YAML, JSON or TOML file but Success "
                "Criteria holds no parser-load gate (safe_load, json.load or tomllib)"))
    for number, text in later:
        if _NAKED_LINE_REF_RE.search(text) and not _has_content_anchor(text):
            findings.append(Finding(
                name, number, SEVERITY_WARNING, RULE_CROSS_REPO_LINE_REF,
                f"{_XREF} §7.3a: a later step names a line or step number with no content "
                "anchor (heading text, function name or quoted string); a heuristic signal"))
    return findings


# Content rules, in report order. Each takes (name, lines, sections) and returns
# a list of Finding. A new rule is one function plus one entry here.
_CONTENT_RULES = (_used_helper_findings, _field_mapping_findings, _schema_pin_findings)


def _content_findings(name: str, lines: list, sections: dict) -> list:
    findings: list = []
    for rule in _CONTENT_RULES:
        findings.extend(rule(name, lines, sections))
    return findings


def lint_text(text: str, name: str) -> list:
    """Return the findings for one task file's text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    sections = _sections(text, lines)
    # The cross-repo rules run before both early returns: a cross-repo fix may
    # be a documentation edit, and the exemption covers verification only.
    findings: list = _cross_repo_findings(name, lines, sections)
    if _exemption(lines):
        return findings
    output_text, output_line = _output_text(lines, sections)
    kinds = _kinds_of(output_text)
    if any(_SCHEMA_PIN_RE.match(line) for _n, line in _unfenced_lines(lines)):
        kinds.db_write = True
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
    findings.extend(_content_findings(name, lines, sections))
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
