"""Execution Input lint: check a sprint's Execution Input against the EI rules.

An Execution Input (EI) is one ``*-Execution-Input.md`` file, or a set of
``*-Execution-Input-Part-{N}-{Topic}.md`` files, at the root of a sprint folder.
The header lines ``Extracted from:`` and ``Retention:`` are read from Part 1
only. Parts 2 onward are headerless, and no rule asks them for a header.

Usage:
    python -B lint_execution_input.py --sprint <sprint folder> --master-plan <path>
        [--plan-root <path>]

``--master-plan`` names the Master Plan whose Global Source Map the citation
rule reads; a ``{stem}-Part-2-*.md`` sibling of it is read too. ``--plan-root``
is the folder searched for the source files an EI names on its
``Extracted from:`` line; without it the hedge rule prints
``skipped: no source root``.

Rules, by word id:
    severity-vocabulary   references/ei-fidelity.md §2. An EI that cites a
                          bracketed tag ([BLOCKER], [ERROR], [WARNING], [INFO],
                          [UNCONFIRMED]) holds a line starting
                          ``## Severity Vocabulary``. BLOCKER.
    retention-band-class  references/ei-fidelity.md §3.1. When the Sprint Plan
                          Objective names algorithm, numerical design or model
                          work, the Part 1 header does not declare the generic
                          80 to 120 percent band without the algorithm band.
                          BLOCKER.
    four-site-caveat      references/ei-fidelity.md §4. Each bare UNCONFIRMED
                          marker in an EI primary section also reaches the EI
                          Data Quality Caveats section, an Orchestration success
                          criterion, and a task file's Required Context or
                          Success Criteria. A ``> [!practice]`` callout that
                          carries the marker fires. BLOCKER.
    hedge-preservation    references/ei-fidelity.md §4.5. A hedged sentence in a
                          cited source whose closest EI line keeps neither the
                          hedge nor a dated measurement. ADVISORY: prints
                          candidates and never changes the exit code.
    cross-tier-note       references/ei-citation-and-token-reconciliation.md §5.
                          A Cross-References section cell carried by two or more
                          rows citing distinct sources (of distinct tiers, when
                          the source map states tiers) has a
                          ``**Note (cross-tier duplicate preserved):**``
                          paragraph in the same Part naming every source.
                          BLOCKER.
    retention-threshold   references/ei-citation-and-token-reconciliation.md §5.
                          The Part 1 ``Retention:`` figure, tokens over the whole
                          EI: 0.95 or more passes, 0.80 to below 0.95 is a
                          WARNING, below 0.80 is a BLOCKER. Above 1.20 prints an
                          ADVISORY line.
    spec-citation-pair    references/ei-citation-and-token-reconciliation.md §7.
                          Every ``Spec #N`` token on the ``Extracted from:`` line
                          and in a Cross-References Source cell is followed by
                          ``(filename.md)``, and the number and filename resolve
                          as a pair in the Global Source Map. BLOCKER.
    count-claim           references/ei-citation-and-token-reconciliation.md §7.
                          A count-claim match in sprint markdown outside the EI
                          that cites no ``§``. ADVISORY.

Exit contract:
    0  clean, or advisory output only
    1  one or more BLOCKER findings
    2  one or more WARNING findings and no BLOCKER
    3  the lint did not run: invalid arguments, no EI Part found, a file that
       could not be read or decoded, a Global Source Map with no entries, or a
       sibling module that could not be imported

The first output line is ``N EI Parts read, M rules run``. Each rule then
prints its subject count beside its finding count, so an empty input reads
differently from a clean one.

What the rules cannot see is stated per rule in the comment above each check.
In short: tags and markers inside code spans or fences are mentions, not uses;
the hedge and count rules are heuristics; a citation written in a plural form
(``Specs #3, #4``) is not parsed.

Other modules extend ``RULES`` with one line each.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# An isolated interpreter (-I) leaves the script's folder off sys.path. Exit 1 means
# "BLOCKER finding", so a failed import has to exit 3 rather than end in a traceback.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from markdown_parser import split_row_cells
except ImportError as exc:
    print(f"error: cannot import a sibling module: {exc}", file=sys.stderr)
    sys.exit(3)

EXIT_CLEAN = 0
EXIT_BLOCKER = 1
EXIT_WARNING = 2
EXIT_NOT_RUN = 3

BLOCKER = "BLOCKER"
WARNING = "WARNING"
ADVISORY = "ADVISORY"

PASS_RATIO = 0.95
BLOCK_RATIO = 0.80
INVESTIGATE_RATIO = 1.20

EI_SINGLE_RE = re.compile(r"(?P<stem>.+)-Execution-Input\.md")
EI_PART_RE = re.compile(r"(?P<stem>.+)-Execution-Input-Part-(?P<num>[0-9]+)-[^/\\]+\.md")
HEADING_RE = re.compile(r"(#{1,6})[ \t]+(\S[^\r\n]*)")
FENCE_RE = re.compile(r"[ \t]{0,3}(`{3,}|~{3,})")
CODE_SPAN_RE = re.compile(r"`[^`\r\n]*`")
SEPARATOR_CELL_RE = re.compile(r":?-+:?")

SEVERITY_TAG_RE = re.compile(r"\[(?:BLOCKER|ERROR|WARNING|INFO|UNCONFIRMED)\]")
SEVERITY_HEADING_RE = re.compile(r"##[ \t]+Severity[ \t]+Vocabulary\b")
EXTRACTED_RE = re.compile(r"[*_ \t]*Extracted from:")
RETENTION_RE = re.compile(
    r"[*_ \t]*Retention:[*_ \t]*(?P<value>[0-9][0-9,]*(?:\.[0-9]+)?)[ \t]*(?P<unit>%|percent)?"
)
OBJECTIVE_TITLE_RE = re.compile(r"Objective\b", re.IGNORECASE)
WORK_KEYWORD_RE = re.compile(r"\b(?:algorithm|numerical design|model)", re.IGNORECASE)
_BAND_SEP = r"[ \t]*%?[ \t]*(?:–|-|to)[ \t]*"
GENERIC_BAND_RE = re.compile(r"\b80" + _BAND_SEP + r"120[ \t]*(?:%|percent)", re.IGNORECASE)
ALGORITHM_BAND_RE = re.compile(
    r"\b95" + _BAND_SEP + r"120[ \t]*(?:%|percent)|algorithm[- ]band", re.IGNORECASE
)
MARKER_RE = re.compile(r"\bUNCONFIRMED\b")
PRACTICE_RE = re.compile(r"[ \t]*>[ \t]*\[!practice\]", re.IGNORECASE)
CALLOUT_LINE_RE = re.compile(r"[ \t]*>")
CAVEATS_TITLE_RE = re.compile(r"Data Quality Caveats", re.IGNORECASE)
CRITERIA_TITLE_RE = re.compile(r"Criteri", re.IGNORECASE)
TASK_SITE_TITLE_RE = re.compile(r"Required Context|Success Criteria", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"[ \t]*[-*][ \t]+\[[ xX]\]")
CROSS_REF_TITLE_RE = re.compile(r"Cross-References", re.IGNORECASE)
NOTE_RE = re.compile(r"\*\*Note \(cross-tier duplicate preserved\):\*\*")
SPEC_TOKEN_RE = re.compile(r"Spec #(?P<num>[0-9]+)(?:[ \t]*\((?P<inner>[^()\r\n]*)\))?")
SPEC_NUMBER_RE = re.compile(r"Spec #([0-9]+)")
MAP_TITLE_RE = re.compile(r"Global Source Map", re.IGNORECASE)
MAP_NUMBER_RE = re.compile(r"(?:Spec[ \t]*)?#?[ \t]*([0-9]+)")
# A map cell may elide a long filename's prefix with an ellipsis: `…Part-3-Topic.md`.
MD_NAME_RE = re.compile(r"(?:…)?[A-Za-z0-9_.\-/\\]+\.md\b")
ELISION_PREFIXES = ("…", "...")
# A sentence about the marker, not a claim carrying it: "each UNCONFIRMED caveat".
MARKER_MENTION_RE = re.compile(
    r"\bUNCONFIRMED[ \t]+(?:caveats?|claims?|markers?|items?|occurrences?|tags?)\b"
)
# Pieces dropped from the text before a marker when its subject phrase is taken.
BOLD_LABEL_RE = re.compile(r"\*\*[^*\r\n]+:\*\*")
QUOTED_PIECE_RE = re.compile(r'"[^"\r\n]*"|“[^”\r\n]*”')
PAREN_PIECE_RE = re.compile(r"\([^()\r\n]*\)")
CLAUSE_BREAK_RE = re.compile(r"[;:,|]|\.[ \t]|[—–]")
SUBJECT_LEAD_WORDS = frozenset({"the", "a", "an", "that", "which", "this", "these", "its"})
SUBJECT_TRAIL_WORDS = frozenset({"is", "are", "was", "were", "stays", "remains", "marked", "flagged", "as", "still"})
SUBJECT_MAX_WORDS = 6
KEY_MIN_CHARS = 4
KEY_STOP_WORDS = frozenset(
    {"a", "an", "the", "it", "its", "this", "that", "these", "those", "they", "them", "there", "here",
     "which", "what", "who", "is", "are", "was", "were", "be", "and", "or", "of", "to", "in", "on",
     "for", "with", "as", "at", "by", "still", "also", "some", "each", "every"}
)
HEDGE_MARKERS = (
    "most likely",
    "probably",
    "appears to",
    "pending",
    "preliminary",
    "tentative",
    "subject to",
    "except",
    "reconfirmed",
)
HEDGE_RE = re.compile(r"\b(?:" + "|".join(re.escape(m) for m in HEDGE_MARKERS) + r")\b", re.IGNORECASE)
HEDGE_WORDS = frozenset(word for marker in HEDGE_MARKERS for word in marker.split())
CONTENT_WORD_RE = re.compile(r"[a-z0-9]{4,}")
MEASURED_RE = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b|\bmeasured\b", re.IGNORECASE)
HEDGE_MIN_WORDS = 4
HEDGE_MIN_OVERLAP = 0.6
# The count-claim pattern of references/ei-citation-and-token-reconciliation.md §7, verbatim.
COUNT_CLAIM_RE = re.compile(r"(weights?|components?|columns?|metrics?|fields?) (with )?[0-9]+")
TASK_EXCLUDED_SUFFIXES = ("-Orchestration.md", "-Recovery.md", "-Summary.md", "-Signoff.md")


class LintError(Exception):
    """The lint could not run; the message says why. Maps to exit 3."""


@dataclass
class Doc:
    path: Path
    lines: list[str]


@dataclass
class ExecutionInput:
    stem: str
    parts: list[Doc]

    @property
    def header(self) -> Doc:
        return self.parts[0]


@dataclass
class SourceMap:
    files: dict[int, str]
    tiers: dict[int, str]


@dataclass
class Context:
    sprint: Path
    plan_root: Path | None
    eis: list[ExecutionInput]
    source_map: SourceMap
    sprint_plans: list[Doc]
    orchestrations: list[Doc]
    task_files: list[Doc]
    sprint_markdown: list[Doc]

    @property
    def ei_paths(self) -> set[Path]:
        return {part.path for ei in self.eis for part in ei.parts}


@dataclass
class Finding:
    rule: str
    severity: str
    path: Path
    line: int
    message: str


@dataclass
class RuleResult:
    subjects: int = 0
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Rule:
    word: str
    check: Callable[[Context], RuleResult]


# --------------------------------------------------------------------------- reading


def read_doc(path: Path) -> Doc:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise LintError(f"cannot read {path}: {exc}") from exc
    return Doc(path, text.splitlines())


def discover_parts(sprint: Path) -> dict[str, list[tuple[int, Path]]]:
    """Group the EI files at the sprint root by stem; a single-file EI is Part 1."""
    groups: dict[str, list[tuple[int, Path]]] = {}
    for path in sorted(sprint.iterdir()):
        if not path.is_file():
            continue
        part = EI_PART_RE.fullmatch(path.name)
        if part:
            groups.setdefault(part["stem"], []).append((int(part["num"]), path))
            continue
        single = EI_SINGLE_RE.fullmatch(path.name)
        if single:
            groups.setdefault(single["stem"], []).append((1, path))
    return groups


def fenced_mask(lines: list[str]) -> list[bool]:
    """True for every line inside a fenced code block, fence lines included."""
    mask: list[bool] = []
    opener: str | None = None
    for line in lines:
        fence = FENCE_RE.match(line)
        if opener is None:
            if fence:
                opener = fence.group(1)[0]
                mask.append(True)
                continue
            mask.append(False)
        else:
            mask.append(True)
            if fence and fence.group(1)[0] == opener and not line.strip().strip(opener):
                opener = None
    return mask


def sections(lines: list[str]) -> list[tuple[int, str, int, int]]:
    """Return (level, title, heading index, end index exclusive) for each heading outside fences."""
    mask = fenced_mask(lines)
    heads: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and not mask[index]:
            heads.append((len(match.group(1)), match.group(2).rstrip(" \t#"), index))
    result: list[tuple[int, str, int, int]] = []
    for position, (level, title, start) in enumerate(heads):
        end = len(lines)
        for later_level, _title, later_start in heads[position + 1 :]:
            if later_level <= level:
                end = later_start
                break
        result.append((level, title, start, end))
    return result


def ranges_titled(lines: list[str], title_re: re.Pattern[str]) -> list[range]:
    return [range(start, end) for _level, title, start, end in sections(lines) if title_re.search(title)]


def in_ranges(index: int, spans: list[range]) -> bool:
    return any(index in span for span in spans)


def first_table(lines: list[str], span: range) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Return the header cells and the (index, cells) body rows of the first table in `span`."""
    index = span.start
    while index + 1 < span.stop:
        line = lines[index]
        if line.lstrip().startswith("|"):
            rule = split_row_cells(lines[index + 1])
            if rule and all(SEPARATOR_CELL_RE.fullmatch(cell) for cell in rule):
                header = split_row_cells(line)
                rows: list[tuple[int, list[str]]] = []
                body = index + 2
                while body < span.stop and lines[body].lstrip().startswith("|"):
                    rows.append((body, split_row_cells(lines[body])))
                    body += 1
                return header, rows
        index += 1
    return [], []


def column(header: list[str], name: str, default: int) -> int:
    for position, cell in enumerate(header):
        if cell.strip("*_ ").lower() == name:
            return position
    return default


def load_source_map(master_plan: Path) -> SourceMap:
    """Read number-to-filename pairs from the Global Source Map of the plan and its Part 2."""
    docs = [read_doc(master_plan)]
    docs += [read_doc(path) for path in sorted(master_plan.parent.glob(f"{master_plan.stem}-Part-2-*.md"))]
    files: dict[int, str] = {}
    tiers: dict[int, str] = {}
    for doc in docs:
        for span in ranges_titled(doc.lines, MAP_TITLE_RE):
            _read_map_span(doc.lines, span, files, tiers)
    return SourceMap(files, tiers)


def _read_map_span(lines: list[str], span: range, files: dict[int, str], tiers: dict[int, str]) -> None:
    tier_column: int | None = None
    previous_table_line = False
    for index in span:
        line = lines[index]
        if not line.lstrip().startswith("|"):
            previous_table_line = False
            for number, inner in ((m["num"], m["inner"]) for m in SPEC_TOKEN_RE.finditer(line)):
                name = MD_NAME_RE.search(inner or "")
                if name:
                    files.setdefault(int(number), Path(name.group(0).replace("\\", "/")).name)
            continue
        cells = split_row_cells(line)
        if cells and all(SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells):
            continue
        if not previous_table_line:
            previous_table_line = True
            tier_column = next((i for i, c in enumerate(cells) if "tier" in c.lower()), None)
            continue  # the first row of a table is its header
        number_at = next(
            (i for i, c in enumerate(cells) if MAP_NUMBER_RE.fullmatch(c.strip("`*_ "))), None
        )
        if number_at is None:
            continue
        number = int(MAP_NUMBER_RE.fullmatch(cells[number_at].strip("`*_ ")).group(1))
        for position, cell in enumerate(cells):
            name = MD_NAME_RE.search(cell) if position != number_at else None
            if name:
                files.setdefault(number, Path(name.group(0).replace("\\", "/")).name)
                break
        if tier_column is not None and tier_column < len(cells):
            tiers.setdefault(number, cells[tier_column].strip("`*_ "))


def build_context(sprint: Path, master_plan: Path, plan_root: Path | None) -> Context:
    groups = discover_parts(sprint)
    eis = [
        ExecutionInput(stem, [read_doc(path) for _num, path in sorted(parts)])
        for stem, parts in sorted(groups.items())
    ]
    source_map = load_source_map(master_plan)
    markdown: list[Doc] = []
    plans: list[Doc] = []
    orchestrations: list[Doc] = []
    tasks: list[Doc] = []
    for path in sorted(sprint.rglob("*.md")):
        relative = path.relative_to(sprint)
        doc = read_doc(path)
        markdown.append(doc)
        if "Outputs" in relative.parts[:-1]:
            continue
        if len(relative.parts) == 1:
            if path.name.endswith("-Sprint-Plan.md"):
                plans.append(doc)
        elif path.name.endswith("-Orchestration.md"):
            orchestrations.append(doc)
        elif not path.name.endswith(TASK_EXCLUDED_SUFFIXES):
            tasks.append(doc)
    return Context(sprint, plan_root, eis, source_map, plans, orchestrations, tasks, markdown)


# --------------------------------------------------------------------------- rules


def check_severity_vocabulary(ctx: Context) -> RuleResult:
    """A bracketed tag anywhere in the EI needs the heading somewhere in the EI.

    Cannot see: a tag inside a code fence counts as a citation, as the
    reference's detection grep does; a tag spelled without brackets is not a tag.
    """
    result = RuleResult()
    for ei in ctx.eis:
        result.subjects += 1
        tagged = [
            (part, index)
            for part in ei.parts
            for index, line in enumerate(part.lines)
            if SEVERITY_TAG_RE.search(line)
        ]
        has_heading = any(SEVERITY_HEADING_RE.match(line) for part in ei.parts for line in part.lines)
        if tagged and not has_heading:
            part, index = tagged[0]
            result.findings.append(
                Finding(
                    "severity-vocabulary",
                    BLOCKER,
                    part.path,
                    index + 1,
                    f"{len(tagged)} line(s) cite a bracketed severity tag and no Part holds "
                    "a '## Severity Vocabulary' heading",
                )
            )
    return result


def _header_block(doc: Doc) -> list[tuple[int, str]]:
    """Part 1 lines before its first '## ' heading: the header the EI declares itself in."""
    block: list[tuple[int, str]] = []
    for index, line in enumerate(doc.lines):
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) >= 2:
            break
        block.append((index, line))
    return block


def check_retention_band_class(ctx: Context) -> RuleResult:
    """Objective keywords plus a generic band in the Part 1 header, with no algorithm band.

    Cannot see: a band declared below the first '## ' heading of Part 1, or in
    another Part; an Objective that names the work with other words. The
    keyword 'model' also matches unrelated uses, as the reference's own list does.
    """
    result = RuleResult()
    if not ctx.sprint_plans:
        result.notes.append("retention-band-class: skipped: no *-Sprint-Plan.md at the sprint root")
        return result
    keyword_plans = []
    for plan in ctx.sprint_plans:
        body = [plan.lines[i] for span in ranges_titled(plan.lines, OBJECTIVE_TITLE_RE) for i in span]
        if any(WORK_KEYWORD_RE.search(line) for line in body):
            keyword_plans.append(plan)
    for ei in ctx.eis:
        result.subjects += 1
        header = _header_block(ei.header)
        generic = [(i, line) for i, line in header if GENERIC_BAND_RE.search(line)]
        algorithm = any(ALGORITHM_BAND_RE.search(line) for _i, line in header)
        if keyword_plans and generic and not algorithm:
            result.findings.append(
                Finding(
                    "retention-band-class",
                    BLOCKER,
                    ei.header.path,
                    generic[0][0] + 1,
                    f"{keyword_plans[0].path.name} Objective names algorithm or model work and the "
                    "EI header declares the generic 80 to 120 percent band, not the algorithm band",
                )
            )
    return result


def _callout_lines(lines: list[str]) -> set[int]:
    """Indexes of every line of a '> [!practice]' callout."""
    found: set[int] = set()
    index = 0
    while index < len(lines):
        if PRACTICE_RE.match(lines[index]):
            while index < len(lines) and CALLOUT_LINE_RE.match(lines[index]):
                found.add(index)
                index += 1
            continue
        index += 1
    return found


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def marker_position(line: str) -> int | None:
    """Column of the first UNCONFIRMED used as a claim, or None when every one is a mention."""
    masked = MARKER_MENTION_RE.sub(_blank, CODE_SPAN_RE.sub(_blank, line))
    found = MARKER_RE.search(masked)
    return found.start() if found else None


def key_is_specific(key: str) -> bool:
    """True when a key holds two content words, or one content word of four or more characters."""
    words = [word for word in key.split() if word.casefold().strip(".,;:!?") not in KEY_STOP_WORDS]
    return len(words) >= 2 or any(len(word) >= KEY_MIN_CHARS for word in words)


def carries(text: str, key: str) -> bool:
    """True when `text` holds `key` as whole words, case-folded, any run of whitespace between them."""
    pattern = r"\s+".join(re.escape(word) for word in key.casefold().split())
    return re.search(r"(?<!\w)" + pattern + r"(?!\w)", text.casefold()) is not None


def claim_key(line: str, marker_at: int) -> str | None:
    """The text a site must carry for the claim the marker on `line` caveats, or None.

    The first code span anywhere on the line wins, unless it holds the marker
    itself. Otherwise the key is the subject phrase before the marker: bold
    labels, quoted and parenthesised pieces dropped, the last clause kept,
    leading articles and a trailing 'is'/'stays' trimmed, at most the last six
    words. A key that fails key_is_specific is no key: the caller reports the
    line as unkeyable. The marker word is never a key.
    """
    for span in CODE_SPAN_RE.finditer(line):
        inner = span.group(0).strip("`").strip()
        if inner and not MARKER_RE.search(inner) and key_is_specific(inner):
            return inner
    before = line[:marker_at]
    text = BOLD_LABEL_RE.sub(" ", CODE_SPAN_RE.sub(" ", before))
    text = QUOTED_PIECE_RE.sub(" ", text)
    while PAREN_PIECE_RE.search(text):
        text = PAREN_PIECE_RE.sub(" ", text)
    clause = CLAUSE_BREAK_RE.split(text)[-1]
    words = [word.strip("*_>#\"'[]") for word in clause.split()]
    words = [word for word in words if word]
    while words and words[0].lower() in SUBJECT_LEAD_WORDS:
        words.pop(0)
    while words and words[-1].lower() in SUBJECT_TRAIL_WORDS:
        words.pop()
    key = " ".join(words[-SUBJECT_MAX_WORDS:])
    return key if key and key_is_specific(key) else None


def _key_in(docs: list[Doc], key: str, title_re: re.Pattern[str], checkbox_counts: bool) -> bool:
    for doc in docs:
        spans = ranges_titled(doc.lines, title_re)
        for index, line in enumerate(doc.lines):
            if not carries(line, key):
                continue
            if in_ranges(index, spans) or (checkbox_counts and CHECKBOX_RE.match(line)):
                return True
    return False


def check_four_site_caveat(ctx: Context) -> RuleResult:
    """Each bare UNCONFIRMED claim reaches the four sites; no practice callout carries one.

    Each site check looks for the claim's key (see claim_key) as whole words,
    case-folded, never for the marker word: a site restates the claim, it need
    not repeat the marker. A claim with no specific key is reported as
    unkeyable rather than passed. A marker inside a code span or fence, or followed by a word
    such as 'caveat' or 'claim' ('each UNCONFIRMED caveat'), is a mention, not
    a claim. Cannot see: a claim phrased as such a mention; a site that names
    the item with other words than the subject phrase; a subject longer than
    six words, which is cut to its last six; whether an Orchestration criterion
    actually enforces the exclusion.
    """
    result = RuleResult()
    for ei in ctx.eis:
        caveat_docs: list[tuple[Doc, list[range]]] = [
            (part, ranges_titled(part.lines, CAVEATS_TITLE_RE)) for part in ei.parts
        ]
        for part, caveat_spans in caveat_docs:
            mask = fenced_mask(part.lines)
            practice = _callout_lines(part.lines)
            for index, line in enumerate(part.lines):
                marker_at = marker_position(line)
                if mask[index] or marker_at is None:
                    continue
                result.subjects += 1
                if index in practice:
                    result.findings.append(
                        Finding(
                            "four-site-caveat",
                            BLOCKER,
                            part.path,
                            index + 1,
                            "a '> [!practice]' callout carries UNCONFIRMED; use '> [!constraint]'",
                        )
                    )
                    continue
                if in_ranges(index, caveat_spans):
                    continue  # a Data Quality Caveats line is a site, not a claim
                key = claim_key(line, marker_at)
                if key is None:
                    result.findings.append(
                        Finding(
                            "four-site-caveat",
                            BLOCKER,
                            part.path,
                            index + 1,
                            "unkeyable UNCONFIRMED caveat: no code span and no subject phrase of two "
                            "content words or one word of four or more letters, so no site can be checked",
                        )
                    )
                    continue
                missing = []
                in_caveats = any(
                    carries(doc.lines[i], key) for doc, spans in caveat_docs for s in spans for i in s
                )
                if not in_caveats:
                    missing.append("EI Data Quality Caveats")
                if not _key_in(ctx.orchestrations, key, CRITERIA_TITLE_RE, checkbox_counts=True):
                    missing.append("Orchestration success criterion")
                if not _key_in(ctx.task_files, key, TASK_SITE_TITLE_RE, checkbox_counts=False):
                    missing.append("task file Required Context or Success Criteria")
                if missing:
                    result.findings.append(
                        Finding(
                            "four-site-caveat",
                            BLOCKER,
                            part.path,
                            index + 1,
                            f"UNCONFIRMED claim '{key}' is absent from: {', '.join(missing)}",
                        )
                    )
    return result


def _content_words(text: str) -> set[str]:
    return {word for word in CONTENT_WORD_RE.findall(text.lower()) if word not in HEDGE_WORDS}


def _index_root(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for folder, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(".md"):
                found.setdefault(name, Path(folder) / name)
    return found


def check_hedge_preservation(ctx: Context) -> RuleResult:
    """Advisory: a hedged source sentence whose closest EI line dropped the hedge.

    The closest EI line shares at least 60 percent of the sentence's content
    words. Cannot see: a paraphrase that shares fewer words, a source the plan
    root does not hold, or a resolution cited without a date or the word
    'measured'. A candidate is a prompt to read both lines, never a verdict.
    """
    result = RuleResult()
    if ctx.plan_root is None:
        result.notes.append("hedge-preservation: skipped: no source root")
        return result
    index = _index_root(ctx.plan_root)
    for ei in ctx.eis:
        extracted = next((line for line in ei.header.lines if EXTRACTED_RE.match(line)), "")
        names = []
        for match in SPEC_TOKEN_RE.finditer(extracted):
            name = MD_NAME_RE.search(match["inner"] or "")
            if name:
                names.append(Path(name.group(0).replace("\\", "/")).name)
        ei_lines = [(part, i, line, _content_words(line)) for part in ei.parts for i, line in enumerate(part.lines)]
        for name in dict.fromkeys(names):
            source_path = index.get(name)
            if source_path is None:
                result.notes.append(f"hedge-preservation: source not found under the plan root: {name}")
                continue
            source = read_doc(source_path)
            for number, sentence in enumerate(source.lines):
                hedge = HEDGE_RE.search(sentence)
                words = _content_words(sentence)
                if not hedge or len(words) < HEDGE_MIN_WORDS:
                    continue
                result.subjects += 1
                best = max(ei_lines, key=lambda item: len(words & item[3]), default=None)
                if best is None or len(words & best[3]) / len(words) < HEDGE_MIN_OVERLAP:
                    continue
                part, line_index, ei_line, _words = best
                if HEDGE_RE.search(ei_line) or MEASURED_RE.search(ei_line):
                    continue
                result.findings.append(
                    Finding(
                        "hedge-preservation",
                        ADVISORY,
                        part.path,
                        line_index + 1,
                        f"source {source_path.name}:{number + 1} hedges with '{hedge.group(0)}' and "
                        "this line keeps neither the hedge nor a dated measurement",
                    )
                )
    return result


def _cross_reference_rows(part: Doc) -> list[tuple[int, str, str]]:
    """(index, section cell, source cell) for each row of the part's Cross-References table."""
    rows: list[tuple[int, str, str]] = []
    for span in ranges_titled(part.lines, CROSS_REF_TITLE_RE):
        header, body = first_table(part.lines, span)
        if not header:
            continue
        section_at = column(header, "section", 0)
        source_at = column(header, "source", 1)
        for index, cells in body:
            if max(section_at, source_at) < len(cells):
                rows.append((index, cells[section_at], cells[source_at]))
    return rows


def _note_paragraphs(lines: list[str]) -> list[str]:
    notes: list[str] = []
    for index, line in enumerate(lines):
        if NOTE_RE.search(line):
            paragraph = [line]
            for later in lines[index + 1 :]:
                if not later.strip():
                    break
                paragraph.append(later)
            notes.append(" ".join(paragraph))
    return notes


def _names_source(note: str, number: int, name: str | None) -> bool:
    if re.search(r"Spec #" + str(number) + r"(?![0-9])", note):
        return True
    if not name:
        return False
    for prefix in ELISION_PREFIXES:
        name = name.removeprefix(prefix)
    return bool(name) and name in note


def check_cross_tier_note(ctx: Context) -> RuleResult:
    """A section cited by several rows of distinct sources carries a covering Note.

    Cannot see: a duplicate finding whose rows carry different Section cells,
    sources named without a 'Spec #N' token, or which Note belongs to which
    section (any Note paragraph in the same Part that names every source passes).
    """
    result = RuleResult()
    for ei in ctx.eis:
        for part in ei.parts:
            groups: dict[str, list[tuple[int, set[int], dict[int, str]]]] = {}
            for index, section, source in _cross_reference_rows(part):
                numbers = {int(n) for n in SPEC_NUMBER_RE.findall(source)}
                names = {}
                for match in SPEC_TOKEN_RE.finditer(source):
                    name = MD_NAME_RE.search(match["inner"] or "")
                    if name:
                        names[int(match["num"])] = Path(name.group(0).replace("\\", "/")).name
                if numbers:
                    groups.setdefault(section.strip(), []).append((index, numbers, names))
            notes = _note_paragraphs(part.lines)
            for section, rows in groups.items():
                if len(rows) < 2:
                    continue
                numbers = set().union(*(row[1] for row in rows))
                if len(numbers) < 2:
                    continue
                known = [ctx.source_map.tiers.get(n) for n in numbers]
                if all(known) and len(set(known)) < 2:
                    continue
                result.subjects += 1
                names = {n: nm for row in rows for n, nm in row[2].items()}
                covered = any(
                    all(_names_source(note, n, names.get(n) or ctx.source_map.files.get(n)) for n in numbers)
                    for note in notes
                )
                if not covered:
                    listed = ", ".join(f"Spec #{n}" for n in sorted(numbers))
                    result.findings.append(
                        Finding(
                            "cross-tier-note",
                            BLOCKER,
                            part.path,
                            rows[0][0] + 1,
                            f"section '{section}' is cited from {listed} and no "
                            "'**Note (cross-tier duplicate preserved):**' paragraph in this Part names them all",
                        )
                    )
    return result


def check_retention_threshold(ctx: Context) -> RuleResult:
    """The Part 1 Retention figure against the 0.95 and 0.80 token bands.

    Cannot see: whether the stated figure was measured in tokens over the whole
    EI; the rule reads the figure, it does not recompute it.
    """
    result = RuleResult()
    for ei in ctx.eis:
        result.subjects += 1
        found = next(
            ((i, RETENTION_RE.match(line)) for i, line in enumerate(ei.header.lines) if RETENTION_RE.match(line)),
            None,
        )
        if found is None:
            result.findings.append(
                Finding("retention-threshold", WARNING, ei.header.path, 1, "Part 1 holds no 'Retention:' line")
            )
            continue
        index, match = found
        value = float(match["value"].replace(",", ""))
        ratio = value / 100 if match["unit"] else value
        if not match["unit"] and value > 5:
            result.findings.append(
                Finding(
                    "retention-threshold",
                    WARNING,
                    ei.header.path,
                    index + 1,
                    f"'Retention:' figure {match['value']} has no percent sign and is not a ratio",
                )
            )
            continue
        shown = f"{ratio:.2f}"
        if ratio < BLOCK_RATIO:
            result.findings.append(
                Finding("retention-threshold", BLOCKER, ei.header.path, index + 1, f"retention {shown} is below 0.80")
            )
        elif ratio < PASS_RATIO:
            result.findings.append(
                Finding(
                    "retention-threshold", WARNING, ei.header.path, index + 1, f"retention {shown} is below 0.95"
                )
            )
        elif ratio > INVESTIGATE_RATIO:
            result.findings.append(
                Finding(
                    "retention-threshold",
                    ADVISORY,
                    ei.header.path,
                    index + 1,
                    f"retention {shown} is above 1.20; the header should name the drivers",
                )
            )
    return result


def _citation_surfaces(ei: ExecutionInput) -> list[tuple[Doc, int, str]]:
    surfaces = [(ei.header, i, line) for i, line in enumerate(ei.header.lines) if EXTRACTED_RE.match(line)]
    for part in ei.parts:
        surfaces += [(part, index, source) for index, _section, source in _cross_reference_rows(part)]
    return surfaces


def pair_matches(cited: str, mapped: str) -> bool:
    """True when a cited basename equals the map's, or ends with an elided map name's tail."""
    for prefix in ELISION_PREFIXES:
        if mapped.startswith(prefix):
            tail = mapped[len(prefix) :]
            return bool(tail) and cited.endswith(tail)
    return cited == mapped


def check_spec_citation_pair(ctx: Context) -> RuleResult:
    """Every Spec #N token is a (number, filename) pair the Global Source Map holds.

    Cannot see: a citation outside the 'Extracted from:' line and the
    Cross-References Source cells, or one in a plural form ('Specs #3, #4').
    Filenames are compared by basename. A map name elided with a leading
    ellipsis matches any cited name ending in its tail, so two sources that
    share a tail cannot be told apart.
    """
    result = RuleResult()
    for ei in ctx.eis:
        for doc, index, text in _citation_surfaces(ei):
            for match in SPEC_TOKEN_RE.finditer(text):
                result.subjects += 1
                number = int(match["num"])
                name = MD_NAME_RE.search(match["inner"] or "")
                if name is None:
                    message = f"'Spec #{number}' is not followed by '(filename.md)'"
                else:
                    cited = Path(name.group(0).replace("\\", "/")).name
                    mapped = ctx.source_map.files.get(number)
                    if mapped is not None and pair_matches(cited, mapped):
                        continue
                    message = (
                        f"'Spec #{number} ({cited})' is not in the Global Source Map"
                        if mapped is None
                        else f"'Spec #{number} ({cited})' pairs with {mapped} in the Global Source Map"
                    )
                result.findings.append(Finding("spec-citation-pair", BLOCKER, doc.path, index + 1, message))
    return result


def check_count_claim(ctx: Context) -> RuleResult:
    """Advisory: a count claim in sprint markdown outside the EI that cites no '§'.

    Cannot see: a count phrased with other nouns, or a number written in words.
    A '§' anywhere on the line counts as a citation.
    """
    result = RuleResult()
    ei_paths = ctx.ei_paths
    for doc in ctx.sprint_markdown:
        for index, line in enumerate(doc.lines):
            match = COUNT_CLAIM_RE.search(line)
            if not match:
                continue
            result.subjects += 1
            if doc.path in ei_paths or "§" in line:
                continue
            result.findings.append(
                Finding(
                    "count-claim",
                    ADVISORY,
                    doc.path,
                    index + 1,
                    f"count claim '{match.group(0)}' sits outside the EI and cites no §",
                )
            )
    return result


RULES: list[Rule] = [
    Rule("severity-vocabulary", check_severity_vocabulary),
    Rule("retention-band-class", check_retention_band_class),
    Rule("four-site-caveat", check_four_site_caveat),
    Rule("hedge-preservation", check_hedge_preservation),
    Rule("cross-tier-note", check_cross_tier_note),
    Rule("retention-threshold", check_retention_threshold),
    Rule("spec-citation-pair", check_spec_citation_pair),
    Rule("count-claim", check_count_claim),
]
try:  # the plan-file rules; a missing module makes the lint exit 3 when it runs
    RULES.extend(__import__("lint_execution_input_plan").rules(sys.modules[__name__]))
except ImportError as _exc:
    _PLAN_IMPORT_ERROR = f"cannot import a sibling module: {_exc}"
    RULES.append(Rule("plan-rules", lambda _ctx: (_ for _ in ()).throw(LintError(_PLAN_IMPORT_ERROR))))


# --------------------------------------------------------------------------- CLI


def exit_code(findings: list[Finding]) -> int:
    severities = {finding.severity for finding in findings}
    if BLOCKER in severities:
        return EXIT_BLOCKER
    if WARNING in severities:
        return EXIT_WARNING
    return EXIT_CLEAN


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_NOT_RUN)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Check a sprint's Execution Input against the EI rules.")
    parser.add_argument("--sprint", required=True, help="the sprint folder whose root holds the EI")
    parser.add_argument(
        "--master-plan", required=True, help="the Master Plan that holds the Global Source Map"
    )
    parser.add_argument("--plan-root", help="the folder searched for the EI's cited source files")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    sprint = Path(args.sprint)
    if not sprint.is_dir():
        print(f"0 EI Parts read, {len(RULES)} rules run", flush=True)
        print(f"error: sprint folder not found: {sprint}", file=sys.stderr)
        return EXIT_NOT_RUN
    part_count = sum(len(parts) for parts in discover_parts(sprint).values())
    print(f"{part_count} EI Parts read, {len(RULES)} rules run", flush=True)
    if part_count == 0:
        print(f"error: no *-Execution-Input*.md file at the root of {sprint}", file=sys.stderr)
        return EXIT_NOT_RUN
    plan_root = Path(args.plan_root) if args.plan_root else None
    if plan_root is not None and not plan_root.is_dir():
        print(f"error: plan root not found: {plan_root}", file=sys.stderr)
        return EXIT_NOT_RUN
    try:
        ctx = build_context(sprint, Path(args.master_plan), plan_root)
        if not ctx.source_map.files:
            raise LintError(f"no Global Source Map entries found in {args.master_plan} or its Part 2")
        results = [(rule, rule.check(ctx)) for rule in RULES]
    except LintError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NOT_RUN
    findings: list[Finding] = []
    for rule, result in results:
        for note in result.notes:
            print(note)
        for finding in result.findings:
            print(f"{finding.severity} {finding.rule} {finding.path}:{finding.line} {finding.message}")
        findings += result.findings
    for rule, result in results:
        print(f"{rule.word}: {result.subjects} subject(s), {len(result.findings)} finding(s)")
    code = exit_code(findings)
    counts = {level: sum(1 for f in findings if f.severity == level) for level in (BLOCKER, WARNING, ADVISORY)}
    print(
        f"summary: {counts[BLOCKER]} blocker, {counts[WARNING]} warning, "
        f"{counts[ADVISORY]} advisory over {len(ctx.source_map.files)} source-map entries; exit {code}"
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
