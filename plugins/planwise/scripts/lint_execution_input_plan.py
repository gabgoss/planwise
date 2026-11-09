"""Execution Input lint, plan-file rules: the EI rules whose subject is a plan file.

This module adds ten rules to ``lint_execution_input.py``. It reads nothing on its
own: the core module builds the ``Context`` (the EI Parts, the Sprint Plan, the
Orchestrations, the task files) and passes itself to ``rules()``, so every
reader, table helper and result type is the core's, not a copy.

Rules, by word id:
    threshold-alignment     references/ei-fidelity.md §3. A token figure on an
                            EI Threshold or Budget section line that names a
                            session differs from the Sprint Plan Sessions row or
                            the Orchestration Total Estimated by more than 10
                            percent. BLOCKER.
    cross-tier-propagation  references/ei-citation-and-token-reconciliation.md §6.
                            Each cross-tier Note's sources reach a docstring
                            requirement, a grep line and a fixture comment in a
                            task file, and a signoff line. BLOCKER per missing
                            surface.
    token-reconciliation    references/ei-citation-and-token-reconciliation.md §8.
                            abs(EI total - Sprint Plan EI total) / Sprint Plan EI
                            total above 0.10, or task estimates that do not sum
                            to the Orchestration total, then the Sessions row,
                            then the Sprint Plan total. BLOCKER.
    verbatim-line-range     references/ei-citation-and-token-reconciliation.md §8.2.
                            An EI section a task copies verbatim lacks body
                            delimiters, or the task's line range sits within 5
                            percent of the section length and more than 10
                            percent above the body block. BLOCKER.
    size-band-derivation    references/ei-citation-and-token-reconciliation.md §8.3.
                            A line band in a plan or task file lacks an inline
                            derivation or the signal-not-target clause, or its
                            stated spans do not add up. WARNING.
    cross-sprint-touch      references/ei-completeness.md §9.1. A file this
                            sprint and an earlier sprint both write has a
                            Cross-Sprint File Touches row, its first writing
                            task opens with a grep gate, and an unordered pair
                            has a "MUST NOT run concurrently" row. BLOCKER.
    repoint-cluster         references/ei-completeness.md §9.2. An EI repoint
                            map holds fewer rows for a cluster than the audit
                            cites lines for it. BLOCKER.
    repair-covers-verify    references/ei-completeness.md §9.3. A file in an EI
                            verification section, or an audit file the EI cites,
                            is in no EI repair section. BLOCKER.
    body-citation-presence  references/ei-source-promise-integrity.md §10.1. A
                            finding a Consolidated Context part names in its
                            Driving Findings line or a Cross-References row has
                            no body prose and no ``[source-doc-only`` marker.
                            BLOCKER.
    pre-extraction-step     references/ei-source-promise-integrity.md §10.2. A
                            task step that extracts verbatim cites a section no
                            heading carries. BLOCKER, or WARNING when the task is
                            verification-aware. An existence test only: it never
                            claims a present section carries the cited prose.

No-subject rules:
    repoint-cluster and repair-covers-verify print ``no subject`` and never fire
    when the sprint holds no audit table of their kind. body-citation-presence
    prints ``skipped: no source root`` without ``--plan-root``.
    token-reconciliation prints ``no subject`` for its EI-total half when the
    Sprint Plan states no EI token total, because an EI figure against a
    Sprint Plan figure of another kind is not a like-for-like comparison.

What each rule cannot see is stated in the docstring of its check function.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

DEVIATION_LIMIT = 0.10
SECTION_NEAR = 0.05
BODY_ABOVE = 0.10
SUM_TOLERANCE_K = 0.5

THRESHOLD_TITLE_RE = re.compile(r"Threshold|Budget", re.IGNORECASE)
SESSIONS_TITLE_RE = re.compile(r"Sessions\b", re.IGNORECASE)
WRITE_SET_TITLE_RE = re.compile(r"Write[- ]Set", re.IGNORECASE)
CROSS_SPRINT_TITLE_RE = re.compile(r"Cross-Sprint File Touches", re.IGNORECASE)
STEPS_TITLE_RE = re.compile(r"Execution Steps", re.IGNORECASE)
CRITERIA_TITLE_RE = re.compile(r"Success Criteria", re.IGNORECASE)
AUDIT_TITLE_RE = re.compile(r"\baudit\b", re.IGNORECASE)
REPOINT_TITLE_RE = re.compile(r"repoint", re.IGNORECASE)
REPAIR_TITLE_RE = re.compile(r"repair|repoint|\bfix", re.IGNORECASE)
VERIFY_TITLE_RE = re.compile(r"verif|sweep", re.IGNORECASE)

K_FIGURE_RE = re.compile(r"~?(?P<value>[0-9][0-9,]*(?:\.[0-9]+)?)[ \t]*K\b")
TOKENS_FIGURE_RE = re.compile(r"(?P<value>[0-9][0-9,]*)[ \t]*tokens\b", re.IGNORECASE)
TASK_ESTIMATE_RE = re.compile(r"[*_ \t]*Estimated Tokens:[*_ \t]*(?P<rest>[^\r\n]*)")
SPRINT_ESTIMATE_RE = re.compile(r"[*_ \t]*Estimated Tokens:[*_ \t]*(?P<rest>[^\r\n]*\btotal\b[^\r\n]*)")
ORCH_TOTAL_RE = re.compile(r"[*_ \t]*Total Estimated:[*_ \t]*(?P<rest>[^\r\n]*)")
RETENTION_LINE_RE = re.compile(r"[*_ \t]*Retention:")
EI_TOTAL_HEADER_RE = re.compile(r"[*_ \t]*EI total:[*_ \t]*(?P<rest>[^\r\n]*)", re.IGNORECASE)
# Adjacent words only: a looser match took "EI Part 3 ... the plan total ~1,881K",
# a sprint figure of another kind, as the EI total.
PLAN_EI_TOTAL_RE = re.compile(r"\b(?:EI|Execution Input)(?:[ \t]+token)?[ \t]+total\b(?P<rest>[^\r\n]{0,40})")
SESSION_FOLDER_RE = re.compile(r"Session-(?P<num>[0-9]+)-(?P<name>[^\\/]+)")
SPRINT_FOLDER_RE = re.compile(r"Sprint-(?P<num>[0-9]+)\b")
TASK_ID_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*-S[0-9]{2}-[0-9]{2}-[0-9]{2}\b")
FIRST_STEP_RE = re.compile(r"[ \t]*1\.[ \t]")
PATH_TOKEN_RE = re.compile(r"`(?P<path>[^`\s*{}<>]+)`")
FILE_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]+")
PATH_PREFIXES = ("cloned-repos/planwise/", "plugins/planwise/", "./")
ALIAS_LEGEND_RE = re.compile(r"`(?P<alias>[A-Za-z][A-Za-z0-9]{0,3})`[ \t]*=[ \t]*`(?P<prefix>[^`\s]+/)`")
UNORDERED_RE = re.compile(r"unordered|concurren|\bnone\b", re.IGNORECASE)
NOT_CONCURRENT_RE = re.compile(r"MUST NOT run concurrently")

SPEC_NUMBER_RE = re.compile(r"Spec #(?P<num>[0-9]+)(?![0-9])")
DOCSTRING_RE = re.compile(r"docstring", re.IGNORECASE)
GREP_RE = re.compile(r"\bgrep", re.IGNORECASE)
FIXTURE_RE = re.compile(r"fixture", re.IGNORECASE)

SECTION_REF_RE = re.compile(r"§[ \t]*(?P<ref>[0-9]+(?:\.[0-9]+)*)")
VERBATIM_COPY_RE = re.compile(r"\bcopy\b[^\r\n]*?\bverbatim\b[^\r\n]*?\bfrom\b[^\r\n]*?§", re.IGNORECASE)
BODY_DELIMITER_RE = re.compile(r"Body Content runs from[ \t]*`(?P<start>[^`]+)`[ \t]*through[ \t]*`(?P<end>[^`]+)`")
VERBATIM_BODY_TITLE_RE = re.compile(r"Verbatim Body", re.IGNORECASE)
LINE_RANGE_RE = re.compile(r"~?(?P<low>[0-9][0-9,]*)[ \t]*(?:-|–|to)[ \t]*~?(?P<high>[0-9][0-9,]*)[ \t]*lines\b")
EXTRACT_STEP_RE = re.compile(r"\bextract(?:ed)?[ \t]+verbatim\b|\bverbatim[ \t]+from[ \t]+(?:EI[ \t]+)?§", re.IGNORECASE)
VERIFICATION_AWARE_RE = re.compile(r"pre-extraction|fallback hierarch|§[ \t]*10\.3\b|halt on absence", re.IGNORECASE)

SIGNAL_CLAUSE_RE = re.compile(r"signal,?[ \t]+not[ \t]+a[ \t]+target|signal-not-target", re.IGNORECASE)
DERIVATION_RE = re.compile(
    r"\btotal\b[^\r\n]{0,40}?[-−][ \t]*[0-9]|[0-9][ \t]*[-−][ \t]*[0-9][0-9,]*[^\r\n]{0,30}?=[ \t]*[0-9]",
    re.IGNORECASE,
)
TOTAL_MINUS_RE = re.compile(r"(?P<total>[0-9][0-9,]*)[ \t]+total[ \t]*[-−][ \t]*(?P<removed>[0-9][0-9,]*)", re.IGNORECASE)
SPAN_RE = re.compile(r"(?P<start>[0-9]+)[ \t]*[-–][ \t]*(?P<end>[0-9]+)[ \t]*=[ \t]*(?P<count>[0-9]+)")

CITED_LINE_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+:[0-9]+")
CONSOLIDATED_RE = re.compile(r"Consolidated-Context", re.IGNORECASE)
DRIVING_RE = re.compile(r"[*_ \t]*Driving Findings:[*_ \t]*(?P<rest>[^\r\n]*)", re.IGNORECASE)
DEFERRED_MARKER_RE = re.compile(r"\[(?:source-doc-only|deferred)", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"`(?P<inner>[^`\r\n]+)`")
SOURCE_FILENAME_RE = re.compile(r"[A-Za-z0-9_./\\-]*[A-Za-z0-9_-]\.(?:md|py)\b")
IDENTIFIER_CUT_RE = re.compile(r"[ \t]*(?:§|\(|\[|—|:)")

core: Any = None  # the lint_execution_input module, bound by rules()


# --------------------------------------------------------------------------- shared helpers


def _note(word: str, text: str) -> str:
    return f"{word}: {text}"


def _finding(word: str, severity: str, path: Path, index: int, message: str) -> Any:
    return core.Finding(word, severity, path, index + 1, message)


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _k_figure(text: str) -> float | None:
    """The first figure in thousands of tokens: '~495K' or '81,231 tokens'."""
    k_match = K_FIGURE_RE.search(text)
    tokens_match = TOKENS_FIGURE_RE.search(text)
    if k_match and (tokens_match is None or k_match.start() <= tokens_match.start()):
        return _number(k_match["value"])
    if tokens_match:
        return _number(tokens_match["value"]) / 1000
    return None


def _tables(lines: list[str], span: range) -> list[tuple[list[str], list[tuple[int, list[str]]]]]:
    """Every table in `span`, each as the core's (header cells, (index, cells) rows)."""
    found = []
    start = span.start
    while start < span.stop:
        header, rows = core.first_table(lines, range(start, span.stop))
        if not header:
            break
        found.append((header, rows))
        start = (rows[-1][0] if rows else start + 1) + 1
    return found


def _column_index(header: list[str], pattern: str) -> int | None:
    test = re.compile(pattern, re.IGNORECASE)
    return next((i for i, cell in enumerate(header) if test.search(cell)), None)


def _paths(text: str) -> list[str]:
    """Backticked file paths in `text`, without wildcards or placeholders."""
    paths = []
    for match in PATH_TOKEN_RE.finditer(text):
        token = match["path"].rstrip(",.;")
        if "/" in token or FILE_EXTENSION_RE.fullmatch(Path(token).suffix or "-"):
            paths.append(token)
    return paths


def _titled(lines: list[str], title_re: re.Pattern[str]) -> list[tuple[str, int, int]]:
    """(title, heading index, end index) for each heading of level 2 or deeper matching `title_re`.

    A level-1 heading is the document title and spans the whole file, so a word
    in it would put every table of the file in scope.
    """
    return [(title, start, end) for level, title, start, end in core.sections(lines) if level >= 2 and title_re.search(title)]


def _normal(path: str) -> str:
    path = path.replace("\\", "/")
    for prefix in PATH_PREFIXES:
        path = path.removeprefix(prefix)
    return path


def _same_file(left: str, right: str) -> bool:
    a, b = _normal(left), _normal(right)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def _session_rows(ctx: Any) -> list[tuple[Any, int, str, str, str, float | None]]:
    """(plan doc, line index, session number, id, name, est K) per Sessions table row."""
    rows = []
    for plan in ctx.sprint_plans:
        for span in core.ranges_titled(plan.lines, SESSIONS_TITLE_RE):
            header, body = core.first_table(plan.lines, span)
            est_at = _column_index(header, r"tokens")
            if est_at is None:
                continue
            num_at = _column_index(header, r"^session")
            id_at = _column_index(header, r"^id\b")
            name_at = _column_index(header, r"^name\b")
            for index, cells in body:
                def cell(at: int | None, row: list[str] = cells) -> str:
                    return row[at].strip("`*_ ") if at is not None and at < len(row) else ""

                rows.append((plan, index, cell(num_at), cell(id_at), cell(name_at), _k_figure(cell(est_at))))
    return rows


def _session_folder(ctx: Any, number: str, name: str) -> Path | None:
    folders = [path for path in sorted(ctx.sprint.iterdir()) if path.is_dir()]
    for folder in folders:
        match = SESSION_FOLDER_RE.fullmatch(folder.name)
        if match and name and match["name"] == name:
            return folder
    for folder in folders:
        match = SESSION_FOLDER_RE.fullmatch(folder.name)
        if match and number.isdigit() and int(match["num"]) == int(number):
            return folder
    return None


def _orchestration_total(ctx: Any, folder: Path | None) -> tuple[Any, int, float] | None:
    for doc in ctx.orchestrations:
        if folder is None or doc.path.parent != folder:
            continue
        for index, line in enumerate(doc.lines):
            match = ORCH_TOTAL_RE.match(line)
            value = _k_figure(match["rest"]) if match else None
            if value is not None:
                return doc, index, value
    return None


def _task_estimate(doc: Any) -> float | None:
    for line in doc.lines[:20]:
        match = TASK_ESTIMATE_RE.match(line)
        if match:
            return _k_figure(match["rest"])
    return None


def _heading_matches(title: str, ref: str) -> bool:
    pattern = r"(?:Section[ \t]+|§[ \t]*)?" + re.escape(ref) + r"(?!\.?[0-9])"
    return re.match(pattern, title) is not None


def _find_section(docs: list[Any], ref: str) -> tuple[Any, int, int] | None:
    """(doc, heading index, end index) of the first heading numbered `ref`."""
    for doc in docs:
        for _level, title, start, end in core.sections(doc.lines):
            if _heading_matches(title, ref):
                return doc, start, end
    return None


def _ei_docs(ctx: Any) -> list[Any]:
    return [part for ei in ctx.eis for part in ei.parts]


def _non_ei_docs(ctx: Any) -> list[Any]:
    ei_paths = ctx.ei_paths
    return [doc for doc in ctx.sprint_markdown if doc.path not in ei_paths]


def _audit_tables(ctx: Any, column_pattern: str) -> list[tuple[Any, list[str], list[tuple[int, list[str]]], int]]:
    """Tables under an 'audit' heading outside the EI whose header holds `column_pattern`."""
    found = []
    for doc in _non_ei_docs(ctx):
        for _title, start, end in _titled(doc.lines, AUDIT_TITLE_RE):
            for header, rows in _tables(doc.lines, range(start, end)):
                at = _column_index(header, column_pattern)
                if at is not None:
                    found.append((doc, header, rows, at))
    return found


# --------------------------------------------------------------------------- rules


def check_threshold_alignment(ctx: Any) -> Any:
    """An EI Threshold or Budget figure against the Sprint Plan and Orchestration.

    A subject is a line in an EI section titled Threshold or Budget that names a
    session by its Sessions-table id or name and carries a token figure. Cannot
    see: a percentage threshold, a figure that names no session, or a session
    the Sessions table does not list. Deviation is measured against the plan
    figure.
    """
    word = "threshold-alignment"
    result = core.RuleResult()
    sessions = _session_rows(ctx)
    for part in _ei_docs(ctx):
        mask = core.fenced_mask(part.lines)
        for span in core.ranges_titled(part.lines, THRESHOLD_TITLE_RE):
            for index in span:
                line = part.lines[index]
                value = None if mask[index] else _k_figure(line)
                if value is None:
                    continue
                for _plan, _row, number, session_id, name, planned in sessions:
                    keys = [key for key in (session_id, name) if key]
                    if not any(re.search(r"(?<![\w-])" + re.escape(key) + r"(?![\w-])", line) for key in keys):
                        continue
                    result.subjects += 1
                    label = session_id or name
                    targets = [("Sprint Plan Sessions row", planned)]
                    total = _orchestration_total(ctx, _session_folder(ctx, number, name))
                    if total is not None:
                        targets.append(("Orchestration Total Estimated", total[2]))
                    for source, target in targets:
                        if target and abs(value - target) / target > DEVIATION_LIMIT:
                            result.findings.append(
                                _finding(
                                    word,
                                    core.BLOCKER,
                                    part.path,
                                    index,
                                    f"{label}: EI figure {value:g}K differs from the {source} {target:g}K "
                                    "by more than 10 percent",
                                )
                            )
    return result


def check_cross_tier_propagation(ctx: Any) -> Any:
    """Each cross-tier Note's sources reach the four implementation surfaces.

    A surface is a task-file line that names every 'Spec #N' of the Note and the
    word docstring, grep or fixture, and a line naming every 'Spec #N' in a
    sprint file whose name holds 'Signoff'. Cannot see: a surface that names the
    sources by filename only, a Note with fewer than two 'Spec #N' tokens, or
    whether the cited value is one code consumes at all.
    """
    word = "cross-tier-propagation"
    result = core.RuleResult()
    signoff_docs = [doc for doc in ctx.sprint_markdown if "signoff" in doc.path.name.lower()]
    surfaces: list[tuple[str, list[Any], re.Pattern[str] | None]] = [
        ("task-file docstring requirement", ctx.task_files, DOCSTRING_RE),
        ("task-file citation-token grep", ctx.task_files, GREP_RE),
        ("task-file fixture comment", ctx.task_files, FIXTURE_RE),
        ("signoff line", signoff_docs, None),
    ]
    for part in _ei_docs(ctx):
        for index, line in enumerate(part.lines):
            if not core.NOTE_RE.search(line):
                continue
            paragraph = core._note_paragraphs(part.lines[index:])[0]
            numbers = sorted({int(m["num"]) for m in SPEC_NUMBER_RE.finditer(paragraph)})
            if len(numbers) < 2:
                result.notes.append(_note(word, f"{part.path.name}:{index + 1} Note names under two 'Spec #N' sources"))
                continue
            result.subjects += 1
            tokens = [re.compile(r"Spec #" + str(n) + r"(?![0-9])") for n in numbers]

            def carries(text: str, test: re.Pattern[str] | None, tokens: list[re.Pattern[str]] = tokens) -> bool:
                return (test is None or test.search(text) is not None) and all(t.search(text) for t in tokens)

            missing = [
                name for name, docs, test in surfaces if not any(carries(text, test) for doc in docs for text in doc.lines)
            ]
            if missing:
                listed = ", ".join(f"Spec #{n}" for n in numbers)
                result.findings.append(
                    _finding(word, core.BLOCKER, part.path, index, f"Note citing {listed} has no {'; no '.join(missing)}")
                )
    return result


def _ei_total(ctx: Any) -> tuple[Any, int, float] | None:
    for ei in ctx.eis:
        for index, line in core._header_block(ei.header):
            header_total = EI_TOTAL_HEADER_RE.match(line)
            if header_total and _k_figure(header_total["rest"]) is not None:
                return ei.header, index, _k_figure(header_total["rest"])
            if RETENTION_LINE_RE.match(line):
                match = TOKENS_FIGURE_RE.search(line)
                if match:
                    return ei.header, index, _number(match["value"]) / 1000
    return None


def _plan_ei_total(ctx: Any) -> tuple[Any, int, float] | None:
    for plan in ctx.sprint_plans:
        mask = core.fenced_mask(plan.lines)
        for index, line in enumerate(plan.lines):
            match = PLAN_EI_TOTAL_RE.search(line)
            value = _k_figure(match["rest"]) if match and not mask[index] else None
            if value is not None:
                return plan, index, value
    return None


def check_token_reconciliation(ctx: Any) -> Any:
    """EI total against the Sprint Plan's EI total; task, Orchestration and Sprint sums.

    The EI total is an 'EI total:' header line or the first 'N tokens' figure on
    the Part 1 Retention line. The Sprint Plan's EI total is the phrase 'EI
    total' (or 'Execution Input total') followed within 40 characters by a
    figure. Cannot see:
    the Master Plan Sprint Overview row, a figure stated in other words, or a
    task file without an 'Estimated Tokens:' header line.
    """
    word = "token-reconciliation"
    result = core.RuleResult()
    ei_total = _ei_total(ctx)
    plan_total = _plan_ei_total(ctx)
    if plan_total is None:
        result.notes.append(_note(word, "no subject for the EI total: the Sprint Plan states no EI token total"))
    elif ei_total is None:
        result.notes.append(_note(word, "no subject for the EI total: Part 1 states no EI token total"))
    else:
        result.subjects += 1
        doc, index, value = ei_total
        planned = plan_total[2]
        if planned and abs(value - planned) / planned > DEVIATION_LIMIT:
            result.findings.append(
                _finding(
                    word,
                    core.BLOCKER,
                    doc.path,
                    index,
                    f"EI total {value:g}K deviates {abs(value - planned) / planned:.0%} from the Sprint Plan "
                    f"EI total {planned:g}K ({plan_total[0].path.name}:{plan_total[1] + 1})",
                )
            )
    sessions = _session_rows(ctx)
    session_sum = 0.0
    for plan, row, number, session_id, name, planned in sessions:
        folder = _session_folder(ctx, number, name)
        estimates = [_task_estimate(doc) for doc in ctx.task_files if folder is not None and doc.path.parent == folder]
        figures = [figure for figure in estimates if figure is not None]
        session_sum += planned or 0.0
        if not figures:
            result.notes.append(_note(word, f"session {session_id or name}: no task estimate found"))
            continue
        result.subjects += 1
        task_sum = sum(figures)
        total = _orchestration_total(ctx, folder)
        label = session_id or name
        if total is not None and abs(task_sum - total[2]) > SUM_TOLERANCE_K:
            result.findings.append(
                _finding(
                    word,
                    core.BLOCKER,
                    total[0].path,
                    total[1],
                    f"{label}: task estimates sum to {task_sum:g}K, the Orchestration states {total[2]:g}K",
                )
            )
        carried = total[2] if total is not None else task_sum
        if planned is not None and abs(carried - planned) > SUM_TOLERANCE_K:
            result.findings.append(
                _finding(
                    word,
                    core.BLOCKER,
                    plan.path,
                    row,
                    f"{label}: the Sessions row states {planned:g}K, the session sums to {carried:g}K",
                )
            )
    for plan in ctx.sprint_plans:
        for index, line in enumerate(plan.lines[:20]):
            match = SPRINT_ESTIMATE_RE.match(line)
            stated = _k_figure(match["rest"]) if match else None
            if stated is None or not sessions:
                continue
            result.subjects += 1
            if abs(stated - session_sum) > SUM_TOLERANCE_K:
                result.findings.append(
                    _finding(
                        word,
                        core.BLOCKER,
                        plan.path,
                        index,
                        f"the Sprint Plan states {stated:g}K in total, the Sessions rows sum to {session_sum:g}K",
                    )
                )
    return result


def _body_block(lines: list[str], start: int, end: int) -> tuple[int, str] | None:
    """(body line count, how found) for the delimited body inside a section, or None."""
    for index in range(start, end):
        match = BODY_DELIMITER_RE.search(lines[index])
        if match:
            first = next((i for i in range(index + 1, end) if lines[i].strip() == match["start"].strip()), None)
            if first is None:
                return 0, "the start delimiter names no line of the section"
            last = next((i for i in range(first, end) if lines[i].strip() == match["end"].strip()), None)
            if last is None:
                return 0, "the end delimiter names no line of the section"
            return last - first + 1, "delimiter line"
    for _level, title, head, stop in core.sections(lines[start:end]):
        if VERBATIM_BODY_TITLE_RE.search(title):
            return stop - head - 1, "Verbatim Body heading"
    return None


def check_verbatim_line_range(ctx: Any) -> Any:
    """A verbatim-copy section has body delimiters, and the task range counts the body.

    A subject is a task-file line that says copy ... verbatim ... from ... §X.
    Delimiters are a 'Body Content runs from `A` through `B`' line naming two
    lines of the section, or a 'Verbatim Body' subheading. Cannot see: a
    delimiter in other words, a range stated outside the task's Success
    Criteria, or a section cited in a Consolidated Context part rather than
    the EI.
    """
    word = "verbatim-line-range"
    result = core.RuleResult()
    ei_docs = _ei_docs(ctx)
    for task in ctx.task_files:
        mask = core.fenced_mask(task.lines)
        criteria = core.ranges_titled(task.lines, CRITERIA_TITLE_RE)
        ranges = [
            LINE_RANGE_RE.search(task.lines[i]) for span in criteria for i in span if LINE_RANGE_RE.search(task.lines[i])
        ]
        for index, line in enumerate(task.lines):
            match = VERBATIM_COPY_RE.search(line)
            if mask[index] or not match:
                continue
            ref = SECTION_REF_RE.search(line, match.end() - 1)
            found = _find_section(ei_docs, ref["ref"]) if ref else None
            if found is None:
                result.notes.append(_note(word, f"{task.path.name}:{index + 1} cites no EI section a heading carries"))
                continue
            result.subjects += 1
            doc, start, end = found
            body = _body_block(doc.lines, start, end)
            if body is None or body[0] == 0:
                reason = "has no body delimiters" if body is None else body[1]
                result.findings.append(
                    _finding(word, core.BLOCKER, doc.path, start, f"§{ref['ref']}, copied verbatim by {task.path.name}, {reason}")
                )
                continue
            section_lines = end - start
            for found_range in ranges:
                middle = (_number(found_range["low"]) + _number(found_range["high"])) / 2
                near_section = abs(middle - section_lines) / section_lines <= SECTION_NEAR
                above_body = middle > body[0] * (1 + BODY_ABOVE)
                if near_section and above_body:
                    result.findings.append(
                        _finding(
                            word,
                            core.BLOCKER,
                            task.path,
                            index,
                            f"range {found_range.group(0)} matches §{ref['ref']}'s {section_lines} section lines, "
                            f"not its {body[0]}-line body block",
                        )
                    )
    return result


def _paragraph(lines: list[str], index: int) -> str:
    end = index
    while end < len(lines) and lines[end].strip():
        end += 1
    return " ".join(lines[index:end])


def check_size_band_derivation(ctx: Any) -> Any:
    """A line band carries its derivation and the signal-not-target clause; spans add up.

    A band is 'N-M lines' (or 'N to M lines') in a Sprint Plan, Orchestration or
    task file, outside code fences. The derivation and the clause are searched
    in the band's paragraph: its line and the lines that follow up to a blank
    line. Cannot see: a band in tokens or rows, a band phrased 'between N and M',
    a derivation in a separate paragraph, or a modelling error in arithmetic
    that adds up.
    """
    word = "size-band-derivation"
    result = core.RuleResult()
    for doc in [*ctx.sprint_plans, *ctx.orchestrations, *ctx.task_files]:
        mask = core.fenced_mask(doc.lines)
        for index, line in enumerate(doc.lines):
            band = LINE_RANGE_RE.search(line)
            if mask[index] or not band:
                continue
            result.subjects += 1
            paragraph = _paragraph(doc.lines, index)
            problems = []
            if not DERIVATION_RE.search(paragraph):
                problems.append("no inline derivation")
            if not SIGNAL_CLAUSE_RE.search(paragraph):
                problems.append("no signal-not-target clause")
            spans = list(SPAN_RE.finditer(paragraph))
            for span in spans:
                measured = int(span["end"]) - int(span["start"]) + 1
                if measured != int(span["count"]):
                    problems.append(f"span {span['start']}-{span['end']} states {span['count']}, measures {measured}")
            total = TOTAL_MINUS_RE.search(paragraph)
            if total and spans:
                span_sum = sum(int(span["count"]) for span in spans)
                if span_sum != _number(total["removed"]):
                    problems.append(f"the spans sum to {span_sum}, the derivation subtracts {total['removed']}")
            if problems:
                result.findings.append(
                    _finding(word, core.WARNING, doc.path, index, f"band '{band.group(0)}': {'; '.join(problems)}")
                )
    return result


def _alias_legend(lines: list[str], span: range) -> dict[str, str]:
    """Alias to prefix pairs a Write-Set section states in prose: "`S` = `plugins/planwise/scripts/`"."""
    legend: dict[str, str] = {}
    for index in span:
        if lines[index].lstrip().startswith("|"):
            continue
        for match in ALIAS_LEGEND_RE.finditer(lines[index]):
            legend.setdefault(match["alias"], match["prefix"])
    return legend


def _plan_legend(doc: Any) -> dict[str, str]:
    """The alias legend every Write-Set section of a plan states, merged."""
    legend: dict[str, str] = {}
    for span in core.ranges_titled(doc.lines, WRITE_SET_TITLE_RE):
        for alias, prefix in _alias_legend(doc.lines, span).items():
            legend.setdefault(alias, prefix)
    return legend


def _expand_alias(path: str, legend: dict[str, str]) -> str:
    head, slash, rest = path.partition("/")
    return legend[head] + rest if slash and head in legend else path


def _write_set(doc: Any) -> list[tuple[int, str, list[str]]]:
    """(row index, path, task ids) for each path of the first Write-Set table.

    A path written with an alias the section's own legend defines ("`S` =
    `plugins/planwise/scripts/`") is expanded to the full path. A plan that uses
    an alias and states no legend keeps the alias, and its rows match only paths
    written the same way.
    """
    entries = []
    for span in core.ranges_titled(doc.lines, WRITE_SET_TITLE_RE):
        legend = _alias_legend(doc.lines, span)
        header, rows = core.first_table(doc.lines, span)
        path_at = _column_index(header, r"path|file") or 0
        task_at = _column_index(header, r"task")
        for index, cells in rows:
            if path_at >= len(cells):
                continue
            tasks = TASK_ID_RE.findall(cells[task_at]) if task_at is not None and task_at < len(cells) else []
            entries += [(index, _expand_alias(path, legend), tasks) for path in _paths(cells[path_at])]
        break
    return entries


def _sibling_plans(ctx: Any) -> list[tuple[int, Any]]:
    """(sprint number, Sprint Plan) for every sibling sprint folder of a lower number."""
    own = SPRINT_FOLDER_RE.match(ctx.sprint.name)
    if own is None or not ctx.sprint.parent.is_dir():
        return []
    found = []
    for folder in sorted(ctx.sprint.parent.iterdir()):
        match = SPRINT_FOLDER_RE.match(folder.name)
        if not folder.is_dir() or match is None or folder == ctx.sprint:
            continue
        if int(match["num"]) >= int(own["num"]):
            continue
        found += [(int(match["num"]), core.read_doc(path)) for path in sorted(folder.glob("*-Sprint-Plan.md"))]
    return found


def _first_step_greps(ctx: Any, task_id: str) -> bool | None:
    """True when the task's first Execution Step names a grep; None when no task file is found."""
    for doc in ctx.task_files:
        if not doc.path.name.startswith(task_id + "-"):
            continue
        for span in core.ranges_titled(doc.lines, STEPS_TITLE_RE):
            for index in span:
                if FIRST_STEP_RE.match(doc.lines[index]):
                    return GREP_RE.search(doc.lines[index]) is not None
        return False
    return None


def check_cross_sprint_touch(ctx: Any) -> Any:
    """A file this sprint and an earlier sprint both write is declared and gated.

    The shared set is the intersection of this Sprint Plan's Write-Set paths with
    the Write-Set paths of every lower-numbered sibling sprint's Sprint Plan.
    Each shared file needs a Cross-Sprint File Touches row, a first writing task
    (the first task id in its Write-Set row) whose Execution Step 1 names a grep,
    and, when the row's Ordering cell says the pair is unordered, a 'MUST NOT
    run concurrently' line naming the file in a Master Plan file beside the
    sprint folders. Write-Set paths written with an alias are expanded through
    the legend the Write-Set section states ("`S` = `plugins/planwise/scripts/`").
    Cannot see: a file a Write-Set table does not list, an alias the plan uses
    without stating a legend (such a path matches no full-path row, so it reads
    as undeclared), a later sprint's obligations, or whether the grep gate names
    the prior task's marker.
    """
    word = "cross-sprint-touch"
    result = core.RuleResult()
    own = [entry for plan in ctx.sprint_plans for entry in _write_set(plan)]
    earlier = [(number, plan, entry) for number, plan in _sibling_plans(ctx) for entry in _write_set(plan)]
    if not own or not earlier:
        result.notes.append(_note(word, "no subject: no Write-Set table here or in an earlier sprint's Sprint Plan"))
        return result
    touch_rows = []
    for plan in ctx.sprint_plans:
        legend = _plan_legend(plan)  # a touch row may use the Write-Set's aliases too
        for span in core.ranges_titled(plan.lines, CROSS_SPRINT_TITLE_RE):
            header, rows = core.first_table(plan.lines, span)
            file_at = _column_index(header, r"file|path") or 0
            order_at = _column_index(header, r"order")
            for index, cells in rows:
                ordering = cells[order_at] if order_at is not None and order_at < len(cells) else ""
                files = [_expand_alias(p, legend) for p in _paths(cells[file_at])] if file_at < len(cells) else []
                touch_rows += [(plan, index, path, ordering) for path in files]
    master_lines = [
        line
        for path in sorted(ctx.sprint.parent.glob("*-Master-Plan*.md"))
        for line in core.read_doc(path).lines
    ] + [line for plan in ctx.sprint_plans for line in plan.lines]
    seen: set[str] = set()
    for index, path, tasks in own:
        prior = [(number, plan) for number, plan, entry in earlier if _same_file(entry[1], path)]
        if not prior or _normal(path) in seen:
            continue
        seen.add(_normal(path))
        result.subjects += 1
        plan_path = ctx.sprint_plans[0].path
        sprints = ", ".join(sorted({f"sprint {number}" for number, _plan in prior}))
        declared = [row for row in touch_rows if _same_file(row[2], path)]
        if not declared:
            result.findings.append(
                _finding(word, core.BLOCKER, plan_path, index, f"{path} is also written by {sprints} and has no Cross-Sprint File Touches row")
            )
        if tasks:
            gated = _first_step_greps(ctx, tasks[0])
            if gated is False:
                result.findings.append(
                    _finding(word, core.BLOCKER, plan_path, index, f"{path}: first writing task {tasks[0]} has no Step-1 grep gate")
                )
            elif gated is None:
                result.notes.append(_note(word, f"{path}: no task file found for {tasks[0]}"))
        for row_plan, row_index, _file, ordering in declared:
            if not UNORDERED_RE.search(ordering):
                continue
            name = Path(_normal(path)).name
            if not any(NOT_CONCURRENT_RE.search(line) and name in line for line in master_lines):
                result.findings.append(
                    _finding(
                        word,
                        core.BLOCKER,
                        row_plan.path,
                        row_index,
                        f"{path}: the pair is unordered and no 'MUST NOT run concurrently' row names the file",
                    )
                )
    return result


def check_repoint_cluster(ctx: Any) -> Any:
    """An EI repoint map holds a row for every line the audit cites for a cluster.

    The audit range table is a table under an 'audit' heading outside the EI
    with a Cluster column. Its cited lines are the 'file:line' tokens of the
    row. A map row counts for the cluster when any of its cells holds the
    cluster cell's text, in a table under an EI heading that names 'repoint'.
    Cannot see: a cluster written differently in the map, or cited lines not
    written as 'file:line'.
    """
    word = "repoint-cluster"
    result = core.RuleResult()
    audits = _audit_tables(ctx, r"cluster")
    if not audits:
        result.notes.append(_note(word, "no subject: no audit range table in the sprint"))
        return result
    map_rows: list[tuple[Any, int, list[str]]] = []
    for part in _ei_docs(ctx):
        for _title, start, end in _titled(part.lines, REPOINT_TITLE_RE):
            for _header, rows in _tables(part.lines, range(start, end)):
                map_rows += [(part, index, cells) for index, cells in rows]
    for doc, _header, rows, cluster_at in audits:
        for index, cells in rows:
            if cluster_at >= len(cells):
                continue
            cluster = cells[cluster_at].strip("`*_ ")
            cited = sum(len(CITED_LINE_RE.findall(cell)) for position, cell in enumerate(cells) if position != cluster_at)
            if not cluster or not cited:
                continue
            result.subjects += 1
            mapped = sum(1 for _part, _row, row in map_rows if any(cluster in cell for cell in row))
            if mapped < cited:
                result.findings.append(
                    _finding(
                        word,
                        core.BLOCKER,
                        doc.path,
                        index,
                        f"cluster '{cluster}': the audit cites {cited} line(s), the EI repoint map holds {mapped} row(s)",
                    )
                )
    return result


def check_repair_covers_verify(ctx: Any) -> Any:
    """Repair scope covers verification scope: verify_files minus repair_files is empty.

    verify_files are the backticked paths under EI headings naming verification
    or a sweep; repair_files those under EI headings naming repair, repoint or
    fix. A file of the audit grep table (a table under an 'audit' heading
    outside the EI with a File or Path column) that the EI cites and no repair
    section names also fires. Files compare by path tail. Cannot see: a repair
    authorized in a task file rather than the EI, or a file named without
    backticks.
    """
    word = "repair-covers-verify"
    result = core.RuleResult()
    audits = _audit_tables(ctx, r"^(?:files?|paths?)\b")
    if not audits:
        result.notes.append(_note(word, "no subject: no audit grep table in the sprint"))
        return result
    verify: list[tuple[Any, int, str]] = []
    repair: list[str] = []
    ei_text = []
    for part in _ei_docs(ctx):
        ei_text += [(part, index, line) for index, line in enumerate(part.lines)]
        for level, title, start, end in core.sections(part.lines):
            if level < 2:
                continue
            paths = [(index, path) for index in range(start, end) for path in _paths(part.lines[index])]
            if REPAIR_TITLE_RE.search(title):
                repair += [path for _index, path in paths]
            elif VERIFY_TITLE_RE.search(title):
                verify += [(part, index, path) for index, path in paths]
    reported: set[str] = set()
    for part, index, path in verify:
        result.subjects += 1
        if any(_same_file(path, fixed) for fixed in repair) or _normal(path) in reported:
            continue
        reported.add(_normal(path))
        result.findings.append(
            _finding(word, core.BLOCKER, part.path, index, f"{path} is in a verification section and no repair section")
        )
    for doc, _header, rows, file_at in audits:
        for index, cells in rows:
            for path in _paths(cells[file_at]) if file_at < len(cells) else []:
                cited = next(((p, i) for p, i, line in ei_text if Path(_normal(path)).name in line), None)
                if cited is None:
                    continue
                result.subjects += 1
                if any(_same_file(path, fixed) for fixed in repair) or _normal(path) in reported:
                    continue
                reported.add(_normal(path))
                result.findings.append(
                    _finding(
                        word,
                        core.BLOCKER,
                        doc.path,
                        index,
                        f"{path} is in the audit table and cited in the EI ({cited[0].path.name}:{cited[1] + 1}) "
                        "but in no repair section",
                    )
                )
    return result


def _identifier(item: str) -> str:
    span = CODE_SPAN_RE.search(item)
    if span:
        return span["inner"].strip()
    return IDENTIFIER_CUT_RE.split(item.strip(), maxsplit=1)[0].strip("*_ ")


def _items(text: str) -> list[str]:
    return [piece.strip() for chunk in text.split(";") for piece in chunk.split(",") if piece.strip()]


def _source_identifiers(chunk: str) -> list[str]:
    """Identifier-shaped items of a Source-cell chunk: code spans, 'Spec #N' tokens, filenames.

    Free prose yields nothing. A filename is reduced to its basename, whether it
    is bare or the whole of a code span (`references/x.md` matches a body that
    says x.md).
    """
    found = []
    for match in CODE_SPAN_RE.finditer(chunk):
        inner = match["inner"].strip()
        whole_name = SOURCE_FILENAME_RE.fullmatch(inner)
        found.append(Path(inner.replace("\\", "/")).name if whole_name else inner)
    rest = CODE_SPAN_RE.sub(" ", chunk)
    found += [match.group(0) for match in SPEC_NUMBER_RE.finditer(rest)]
    found += [Path(match.group(0).replace("\\", "/")).name for match in SOURCE_FILENAME_RE.finditer(rest)]
    return [item for item in dict.fromkeys(found) if re.search(r"[A-Za-z]", item)]


def _named_in(identifier: str, lines: list[str]) -> bool:
    pattern = re.compile(re.escape(identifier) + (r"(?![0-9])" if identifier[-1].isdigit() else ""))
    return any(pattern.search(line) for line in lines)


def check_body_citation_presence(ctx: Any) -> Any:
    """Every finding a Consolidated Context part names has body prose or a marker.

    The parts are the 'Consolidated-Context' files the Part 1 'Extracted from:'
    line cites, found by name under --plan-root. A finding is each comma- or
    semicolon-separated item of the Driving Findings line (its identifier is
    its first code span or its text up to the first '§', '(', '[' or ':'), and
    each identifier-shaped item of a Cross-References Source cell: a code span,
    a 'Spec #N' token, or a '.md' or '.py' filename (by basename). A
    '[source-doc-only' or '[deferred' marker covers every item of its
    semicolon-separated chunk. The body is every line outside the header block,
    the Driving Findings line and the Cross-References section. Cannot see: a
    finding a Source cell names in free prose (prose yields no item, so it can
    never fire), prose that names a finding in other words, or a Driving
    Findings item that itself holds a comma.
    """
    word = "body-citation-presence"
    result = core.RuleResult()
    if ctx.plan_root is None:
        result.notes.append(_note(word, "skipped: no source root"))
        return result
    names = []
    for ei in ctx.eis:
        extracted = next((line for line in ei.header.lines if core.EXTRACTED_RE.match(line)), "")
        for match in core.SPEC_TOKEN_RE.finditer(extracted):
            name = core.MD_NAME_RE.search(match["inner"] or "")
            if name and CONSOLIDATED_RE.search(name.group(0)):
                names.append(Path(name.group(0).replace("\\", "/")).name)
    if not names:
        result.notes.append(_note(word, "no subject: the EI cites no Consolidated Context part"))
        return result
    index_of = core._index_root(ctx.plan_root)
    for name in dict.fromkeys(names):
        path = index_of.get(name)
        if path is None:
            result.notes.append(_note(word, f"source not found under the plan root: {name}"))
            continue
        doc = core.read_doc(path)
        excluded = {index for index, _line in core._header_block(doc)}
        promised: list[tuple[int, str, bool]] = []
        for index, line in enumerate(doc.lines):
            driving = DRIVING_RE.match(line)
            if driving:
                excluded.add(index)
                promised += [
                    (index, _identifier(item), DEFERRED_MARKER_RE.search(item) is not None)
                    for item in _items(driving["rest"])
                ]
        for span in core.ranges_titled(doc.lines, core.CROSS_REF_TITLE_RE):
            excluded.update(span)
        for index, _section, source in core._cross_reference_rows(doc):
            for chunk in source.split(";"):
                marked = DEFERRED_MARKER_RE.search(chunk)
                named = chunk[: marked.start()] if marked else chunk
                promised += [(index, identifier, marked is not None) for identifier in _source_identifiers(named)]
        body = [line for index, line in enumerate(doc.lines) if index not in excluded]
        for index, identifier, covered in promised:
            if not identifier or not re.search(r"[A-Za-z]", identifier):
                continue
            result.subjects += 1
            if covered or _named_in(identifier, body):
                continue
            result.findings.append(
                _finding(
                    word,
                    core.BLOCKER,
                    doc.path,
                    index,
                    f"'{identifier}' is named as a source and has no body prose and no [source-doc-only marker",
                )
            )
    return result


def check_pre_extraction_step(ctx: Any) -> Any:
    """A verbatim-extraction step cites a section some heading carries.

    A subject is each '§N' on an Execution Steps line matching 'extract
    verbatim' or 'verbatim from §'. It is resolved against the EI headings, or
    against the headings of the file a 'Spec #N (file.md)' on the same line
    names when --plan-root finds it. Existence test only: a present section
    passes whether or not it carries the cited prose. Cannot see: a step outside
    an Execution Steps section, or a cited section named without a '§' number.
    """
    word = "pre-extraction-step"
    result = core.RuleResult()
    ei_docs = _ei_docs(ctx)
    index_of = core._index_root(ctx.plan_root) if ctx.plan_root is not None else {}
    for task in ctx.task_files:
        aware = any(VERIFICATION_AWARE_RE.search(line) for line in task.lines)
        mask = core.fenced_mask(task.lines)
        for span in core.ranges_titled(task.lines, STEPS_TITLE_RE):
            for index in span:
                line = task.lines[index]
                if mask[index] or not EXTRACT_STEP_RE.search(line):
                    continue
                targets = ei_docs
                spec = core.SPEC_TOKEN_RE.search(line)
                if spec:
                    name = core.MD_NAME_RE.search(spec["inner"] or "")
                    source = index_of.get(Path(name.group(0).replace("\\", "/")).name) if name else None
                    if source is None:
                        result.notes.append(
                            _note(word, f"{task.path.name}:{index + 1} cites a source the plan root does not hold")
                        )
                        continue
                    targets = [core.read_doc(source)]
                for ref in SECTION_REF_RE.finditer(line):
                    result.subjects += 1
                    if _find_section(targets, ref["ref"]) is not None:
                        continue
                    severity = core.WARNING if aware else core.BLOCKER
                    state = "verification-aware" if aware else "has no pre-extraction step"
                    result.findings.append(
                        _finding(word, severity, task.path, index, f"§{ref['ref']} is absent, and the task {state}")
                    )
    return result


_CHECKS: list[tuple[str, Callable[[Any], Any]]] = [
    ("threshold-alignment", check_threshold_alignment),
    ("cross-tier-propagation", check_cross_tier_propagation),
    ("token-reconciliation", check_token_reconciliation),
    ("verbatim-line-range", check_verbatim_line_range),
    ("size-band-derivation", check_size_band_derivation),
    ("cross-sprint-touch", check_cross_sprint_touch),
    ("repoint-cluster", check_repoint_cluster),
    ("repair-covers-verify", check_repair_covers_verify),
    ("body-citation-presence", check_body_citation_presence),
    ("pre-extraction-step", check_pre_extraction_step),
]

WORDS = [word for word, _check in _CHECKS]


def rules(module: ModuleType) -> list[Any]:
    """Bind the core module and return its Rule objects for the ten plan-file rules."""
    global core
    core = module
    return [module.Rule(word, check) for word, check in _CHECKS]
