#!/usr/bin/env python3
"""Check verifier report tables for verdicts their own numbers contradict.

Both modes read markdown verification reports. A path argument is a file, or
a directory walked for ``*.md`` files. Lines inside a fenced code block are
skipped in both modes, because a fence quotes an example rather than reporting
a result.

``verdicts`` mode (the default)
    A table qualifies when its header row holds columns named Actual, Expected
    and Verdict (case-insensitive, in any order, no aliases). That is the
    ``| Check | Actual | Expected | Verdict |`` shape of
    ``references/gate-verdict-contract-and-adjudication.md`` §5. For each
    qualifying row whose Verdict is PASS, one number parser reads Actual and
    Expected. When both parse, the comparator is evaluated, and a false
    comparator is a contradicted PASS. A row where either side is not numeric
    is not checked.

    Exit 0 when numeric rows were checked and none was contradicted, 1 when
    any PASS row is contradicted, and 3 when no numeric row was checked. A
    check that could not run is never read as clean (§5.1 of the same
    reference).

``--input-set`` mode
    A criterion is a line that carries a verdict (``PASS``, ``FAIL`` or
    ``[UNCERTAIN]``) and names a pinned diff or a sweep: ``git diff``,
    ``--name-only``, a ``find`` command, or the word ``sweep``. The criterion
    must carry a spanned-file count and an untracked count, on the same line
    or the next line (``references/gate-input-set-and-compared-window.md``
    §10.6). Exit 0 when every criterion carries both counts, 1 when any
    criterion lacks one or both.

Exit 2 is usage in both modes.
"""

from __future__ import annotations

import argparse
import operator
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

EXIT_CLEAN = 0
EXIT_FINDING = 1
EXIT_USAGE = 2
EXIT_NOTHING_CHECKED = 3

REQUIRED_COLUMNS = ("actual", "expected", "verdict")

# Comparator forms, matched longest first. Each maps to one operator.
_COMPARATOR_FORMS = (
    ("greater than or equal to", ">="),
    ("less than or equal to", "<="),
    ("no fewer than", ">="),
    ("no less than", ">="),
    ("no more than", "<="),
    ("greater than", ">"),
    ("more than", ">"),
    ("fewer than", "<"),
    ("less than", "<"),
    ("at least", ">="),
    ("at most", "<="),
    ("exactly", "="),
    ("equal to", "="),
    ("equals", "="),
    (">=", ">="),
    ("≥", ">="),
    ("<=", "<="),
    ("≤", "<="),
    ("==", "="),
    ("!=", "!="),
    ("≠", "!="),
    (">", ">"),
    ("<", "<"),
    ("=", "="),
)
_COMPARATOR_OPS = {form.lower(): op for form, op in _COMPARATOR_FORMS}
_OPERATORS = {
    "=": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

_COMPARATOR_ALT = "|".join(
    re.escape(form) for form, _ in sorted(_COMPARATOR_FORMS, key=lambda f: -len(f[0]))
)
_NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
# After the number: an optional percent sign, optional unit words (letters
# only, no digits or operators), and an optional trailing parenthetical.
_TAIL = r"(?:\s*%)?(?:\s+[A-Za-z][A-Za-z'\- ]*?)?(?:\s*\([^()]*\))?"
_VALUE_RE = re.compile(
    rf"^(?:(?P<op>{_COMPARATOR_ALT})\s*)?(?P<num>{_NUMBER}){_TAIL}\s*$",
    re.IGNORECASE,
)

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_QUOTE_PREFIX_RE = re.compile(r"^\s*(?:>\s?)+")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_MARKUP_RE = re.compile(r"[`*]")
_PASS_RE = re.compile(r"^[^A-Za-z]*PASS(?:ED)?\b", re.IGNORECASE)

_VERDICT_WORD_RE = re.compile(r"\b(?:PASS|FAIL)\b|\[UNCERTAIN\]")
_INPUT_SET_RE = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?diff\b"
    r"|--name-only"
    r"|(?:^|[`|;&(]\s*)find\s+(?:[./~\"'$-]|[A-Za-z]:[/\\])"
    r"|\bsweep\b",
    re.IGNORECASE,
)
_SPANNED_RE = re.compile(
    r"\bspanned(?:[- ]files?)?(?:[- ]count)?\s*[:=]?\s*\d+"
    r"|\b\d+\s+(?:files?\s+)?spanned\b",
    re.IGNORECASE,
)
_UNTRACKED_RE = re.compile(
    r"\buntracked(?:[- ]files?)?(?:[- ]count)?\s*[:=]?\s*\d+"
    r"|\b\d+\s+untracked\b",
    re.IGNORECASE,
)


@dataclass
class Line:
    number: int
    text: str
    fenced: bool


@dataclass
class VerdictReport:
    path: Path
    tables: int = 0
    pass_rows: int = 0
    checked: int = 0
    contradicted: list[str] = field(default_factory=list)
    checked_lines: list[str] = field(default_factory=list)


@dataclass
class InputSetReport:
    path: Path
    criteria: int = 0
    findings: list[str] = field(default_factory=list)


def parse_value(cell: str) -> tuple[str, float] | None:
    """Parse a cell as a number, or a comparator plus a number.

    Returns ``(operator, value)``, where a bare number carries ``"="``.
    Returns None when the cell is not numeric. Actual and Expected both go
    through this one parser, so the comparison takes both operands from the
    same instrument.
    """
    text = _MARKUP_RE.sub("", cell).strip()
    match = _VALUE_RE.match(text)
    if match is None:
        return None
    op_text = match.group("op")
    op = _COMPARATOR_OPS[op_text.lower()] if op_text else "="
    return op, float(match.group("num").replace(",", ""))


def is_pass(verdict_cell: str) -> bool:
    """True when the Verdict cell opens with PASS (markup and brackets ignored)."""
    return _PASS_RE.match(_MARKUP_RE.sub("", verdict_cell).strip()) is not None


def compare(actual_cell: str, expected_cell: str) -> bool | None:
    """Evaluate Actual against Expected. None when the row cannot be checked.

    Actual must be a plain measurement: a cell that carries its own
    comparator other than equality is not checked. A bare Expected number
    means equality (§5: PASS requires Actual = Expected).
    """
    actual = parse_value(actual_cell)
    expected = parse_value(expected_cell)
    if actual is None or expected is None or actual[0] != "=":
        return None
    op, threshold = expected
    return _OPERATORS[op](actual[1], threshold)


def read_lines(path: Path) -> list[Line]:
    """Read a file into lines with callout prefixes removed and fences marked."""
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines: list[Line] = []
    fence: str | None = None
    for number, original in enumerate(raw, start=1):
        text = _QUOTE_PREFIX_RE.sub("", original)
        opener = _FENCE_RE.match(text)
        if opener:
            marker = opener.group(1)
            if fence is None:
                fence = marker
                lines.append(Line(number, text, True))
                continue
            if marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
                lines.append(Line(number, text, True))
                continue
        lines.append(Line(number, text, fence is not None))
    return lines


def split_cells(text: str) -> list[str] | None:
    """Split a markdown table row on unescaped pipes. None when not a row."""
    stripped = text.strip()
    if not stripped.startswith("|"):
        return None
    body = stripped[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in _CELL_SPLIT_RE.split(body)]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c.replace(" ", "")) for c in cells)


def _column_name(cell: str) -> str:
    return _MARKUP_RE.sub("", cell).strip().lower()


def check_verdicts(path: Path, verbose: bool) -> VerdictReport:
    report = VerdictReport(path)
    lines = read_lines(path)
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        header = None if line.fenced else split_cells(line.text)
        following = lines[index + 1]
        separator = None if following.fenced else split_cells(following.text)
        if header is None or separator is None or not _is_separator(separator):
            index += 1
            continue
        names = [_column_name(c) for c in header]
        if not all(name in names for name in REQUIRED_COLUMNS):
            index += 2
            continue
        report.tables += 1
        columns = {name: names.index(name) for name in REQUIRED_COLUMNS}
        index += 2
        while index < len(lines) and not lines[index].fenced:
            cells = split_cells(lines[index].text)
            if cells is None:
                break
            _check_row(report, lines[index].number, cells, columns, verbose)
            index += 1
    return report


def _check_row(
    report: VerdictReport,
    number: int,
    cells: list[str],
    columns: dict[str, int],
    verbose: bool,
) -> None:
    if max(columns.values()) >= len(cells):
        return
    if not is_pass(cells[columns["verdict"]]):
        return
    report.pass_rows += 1
    actual = cells[columns["actual"]]
    expected = cells[columns["expected"]]
    holds = compare(actual, expected)
    if holds is None:
        return
    report.checked += 1
    where = f"{report.path}:{number}"
    if not holds:
        report.contradicted.append(
            f"{where}: contradicted PASS: Actual '{actual}' does not satisfy Expected '{expected}'"
        )
    elif verbose:
        report.checked_lines.append(
            f"{where}: checked: Actual '{actual}' satisfies Expected '{expected}'"
        )


def check_input_set(path: Path) -> InputSetReport:
    report = InputSetReport(path)
    lines = read_lines(path)
    for index, line in enumerate(lines):
        if line.fenced:
            continue
        if not _VERDICT_WORD_RE.search(line.text) or not _INPUT_SET_RE.search(line.text):
            continue
        report.criteria += 1
        window = line.text
        if index + 1 < len(lines) and not lines[index + 1].fenced:
            window += "\n" + lines[index + 1].text
        missing = []
        if not _SPANNED_RE.search(window):
            missing.append("spanned-file count")
        if not _UNTRACKED_RE.search(window):
            missing.append("untracked count")
        if missing:
            snippet = line.text.strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            report.findings.append(
                f"{path}:{line.number}: criterion lacks {' and '.join(missing)}: {snippet}"
            )
    return report


def collect_files(arguments: list[str]) -> list[Path]:
    """Expand path arguments. Raises FileNotFoundError on a missing path."""
    files: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.md") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(argument)
    return files


def _run_verdicts(files: list[Path], verbose: bool) -> int:
    totals = VerdictReport(Path("."))
    for path in files:
        report = check_verdicts(path, verbose)
        print(
            f"{path}: {report.tables} qualifying tables, {report.pass_rows} PASS rows, "
            f"{report.checked} numeric rows checked, {len(report.contradicted)} contradicted"
        )
        for message in report.checked_lines + report.contradicted:
            print(message)
        totals.tables += report.tables
        totals.pass_rows += report.pass_rows
        totals.checked += report.checked
        totals.contradicted.extend(report.contradicted)
    print(
        f"total: {len(files)} files, {totals.tables} qualifying tables, "
        f"{totals.pass_rows} PASS rows, {totals.checked} numeric rows checked, "
        f"{len(totals.contradicted)} contradicted"
    )
    if totals.contradicted:
        return EXIT_FINDING
    if totals.checked == 0:
        print("no numeric row checked")
        return EXIT_NOTHING_CHECKED
    return EXIT_CLEAN


def _run_input_set(files: list[Path]) -> int:
    criteria = 0
    findings: list[str] = []
    for path in files:
        report = check_input_set(path)
        criteria += report.criteria
        findings.extend(report.findings)
    for message in findings:
        print(message)
    print(
        f"total: {len(files)} files, {criteria} input-set criteria, "
        f"{len(findings)} lacking a count"
    )
    return EXIT_FINDING if findings else EXIT_CLEAN


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        description="Check verifier report tables for contradicted PASS verdicts "
        "(default), or criteria missing their input-set counts (--input-set).",
    )
    parser.add_argument("paths", nargs="+", help="report files or directories of *.md reports")
    parser.add_argument(
        "--input-set",
        action="store_true",
        help="check that diff- or sweep-fed criteria carry spanned-file and untracked counts",
    )
    parser.add_argument("--verbose", action="store_true", help="also list each checked row that holds")
    args = parser.parse_args(argv)
    try:
        files = collect_files(args.paths)
    except FileNotFoundError as error:
        print(f"error: path not found: {error}", file=sys.stderr)
        return EXIT_USAGE
    if args.input_set:
        return _run_input_set(files)
    return _run_verdicts(files, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
