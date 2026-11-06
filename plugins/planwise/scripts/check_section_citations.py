#!/usr/bin/env python3
"""Check that every ``§`` section citation in a markdown tree resolves.

The checker reads every markdown file under the scan directories of a plugin
root (``references/``, ``handlers/``, ``agents/``, ``skills/``,
``templates/``) and under each extra root. It parses each ``§`` citation,
binds it to the file named next to it on the line, and resolves the cited
section against that file's headings. A bare continuation after a slash or
comma binds to the same file. A citation that stands apart from the nearest
earlier file name on its line is tried against that file, then against the
file being scanned. A citation with no file earlier on its line resolves
against the file being scanned first, then against the first file named
later on the line that resolves. When neither holds it, the file being
scanned is the reported target.

Two fence rules skip code. The literal rule of
``markdown_parser.extract_headings``: a line whose first non-space characters
are three backticks toggles the fence. The callout-fence rule, for citation
scanning only: a line that, after leading whitespace and every leading ``>``
marker are stripped, starts with three backticks toggles a fence inside a
callout. That state resets on the first line not starting with ``>``. Heading
extraction keeps the literal rule alone.

A cited file name is first tried in the citing file's own directory (a bare
name or a ``./sub/x.md`` path). Candidate files are tried with exact tokens
first, all of them, before any number-prefix fallback; siblings match exact
tokens only. A range end with spaces around its dash needs its own ``§``.
Scanned files are de-duplicated by resolved path. Ledger entries resolve
against the roots (see Ledger below), so a bare basename entry matches only
a file at the top of a root.

A heading-words citation (``§ Heading Words``) is ``ok`` when the line text
after ``§ `` starts with the full title of a heading in the target, compared
case-insensitively with whitespace collapsed; a title may hold commas,
colons, dashes and backticks. Only when no full title matches does the
clause-bounded words prefix decide.

A stage or step citation (``§ Step 2``, ``§ Stage 8b``) matches the
``Step N`` / ``Stage N`` index key first. When the key is absent, it is
``ok`` if a heading's title starts with ``Step N`` / ``Stage N`` and the
next character is not a letter or digit (``## Step 2 — Strip framing``).

Placeholders produce no finding: a ``{``-bearing file name, a ``§{…}``, a
number followed directly by ``{`` or ``.{`` (``§1.{N}``), and a placeholder
segment such as ``§N.x`` or ``§1.N``.

Verdicts, one per citation:

- ``ok``: the target file resolves and holds the cited section. A numbered
  section matches the exact heading token first. A token with a one-letter
  suffix (``3k``) falls back to its number (``3``) only when no exact heading
  exists, and never across files.
- ``dangling``: the target file resolves, the section is absent, and no
  sibling of the same family stem holds it.
- ``redirected``: the section is absent from the target file but present in a
  ``{stem}-Part-N-*.md`` sibling of the target's family stem (or, when the
  target is itself a Part, in its base file or another Part). A numbered
  citation whose ``(file, section)`` is a ``REDIRECTS`` entry is also
  ``redirected``, to the entry's target, even when the cited file keeps a
  stub heading of that number; the note names the entry's source section.
  An entry whose target file or target heading is missing reads
  ``dangling``. A ``redirected`` finding passes by default and fails under
  ``--strict-parts``.
- ``unresolved-target``: no file resolves for the named file, or the name
  matches two files inside the chosen root (the note names the ambiguity).
- ``unreadable``: a scanned file that cannot be read or is not UTF-8. One
  finding per file: ``line`` is the line holding the first bad byte (0 for
  an OS error), ``citation`` and ``section`` are empty, and the note names
  the byte and its offset. The other files' findings still print. It always
  fails the run, and no ledger entry subtracts it. A cited file that cannot
  be read holds no headings, so a citation of it reads ``dangling``.

Ledger (``--ledger PATH``), one entry per line; a blank line or a line
starting with ``#`` is skipped:

- ``path:line:citation`` (the current form). ``citation`` is the citation
  exactly as the finding prints it (``§12``, ``§ Decisions``, or a bare
  range end such as ``19``). It runs to the end of the line; an optional
  reason follows a whitespace-``#`` (``x.md:9:§3 # EXAMPLE``). The entry
  subtracts only the findings on that line whose printed citation is equal,
  so a second citation added to the line still fails.
- ``path:line`` (the line-keyed form, still read). Text after whitespace is
  the reason. It subtracts every finding on its line, and the run prints one
  ``ledger entry is line-keyed; re-key as path:line:citation: <entry>`` note
  per such entry on stderr.

An absolute entry path matches that file. A relative entry path (a leading
``./`` is dropped) resolves against ``--root``, then against each
``--extra-root`` and the extra root's parent directory (the printed key of an
extra-root file starts with the extra root's own name), and the first
existing file wins. It never resolves against the current working directory
and never matches by path suffix. An entry that subtracts no finding is
printed on stderr as ``ledger entry matched no dangling or unresolved-target
finding: <entry>`` and does not change the exit code. Only ``dangling`` and
``unresolved-target`` findings are ledgerable.

Exit codes:

- 0: no ``dangling`` or ``unresolved-target`` finding is left after the
  ledger is subtracted, no ``unreadable`` finding exists (and no
  ``redirected`` finding under ``--strict-parts``).
- 1: at least one such finding is left.
- 2: a usage error, a root or ledger that cannot be read, or a scan that
  finds zero markdown files. One line beginning ``check_section_citations:``
  names the reason on stderr.

``check_tree(plugin_root, extra_roots=(), exclude=(), strict_parts=False,
scan_roots=None)`` is the importable API. It returns every finding, ``ok``
rows included, and raises ``CitationCheckError`` for the exit-2 conditions.
``scan_roots`` names the roots whose citations are scanned; every root is
still indexed for resolution, and None scans every root. The command line
has no matching flag. ``read_ledger``,
``resolve_ledger`` and ``ledger_bases`` load and resolve a ledger.

Report modes (opt-in; heuristic). Names in a brief are free prose, and no
regex pulls them exactly. So these modes report for a human to read, and a
report line is never a verdict alone. When a mode flag is given, the
citation scan does not run, and the default run is unchanged.

- Zone mode: ``--brief FILE --zone TARGET`` (``--zone`` repeats; ``-`` reads
  the brief from stdin). A zone is a backticked or quoted phrase that
  follows "under", "in", "below", "section" or "heading" (an optional "the"
  between). A leading ``#`` run is dropped. A phrase without a leading ``#``
  is skipped when it does not start with a capital, is ``None``, ``True`` or
  ``False``, holds a code character or ``§``, or is one token that holds a
  dot or no lowercase letter. The zone's count is
  the number of headings, across the targets, whose text or title starts
  with the zone (case-insensitive, backticks dropped). Every zone prints with
  its count. A count of 0 prints ``DEAD-ZONE``.
- Locator evidence, in the same mode: a brief line that says "native format"
  or "matching the existing" (not wrapped in quotes or backticks, which
  marks a mention of the rule) needs a locator result (a file name and a count
  after an arrow, ``=`` or ``count``) on that line or the up to three lines
  before it, stopping at a blank line. No result prints ``NO-LOCATOR``. A
  count of 0 with no fallback form ("inline note", "new section" or
  "fallback") in the same lines prints ``NO-FALLBACK``.
- Symbol mode: ``--symbols FILE --source TREE`` (``--source`` repeats). A
  file whose every non-blank, non-``#`` line is one identifier is a list.
  Otherwise a symbol is a backticked identifier that carries a ``(`` or a
  ``.`` qualifier; a dotted name whose last part is a file extension is
  skipped. The count is the number of whole-word matches of the last part in
  the text files under the sources (the symbols file excluded). A count of 0
  prints ``phantom``.

- Path mode: ``--paths TASK...`` (``--project-root DIR`` optional). The
  paths are the backticked spans of a task file's ``## Required Context``
  table File column (a span with a ``/`` or an extension) and of its
  ``## Execution Steps`` (a span with a ``/`` and an extension, or a trailing
  ``/``). A span with whitespace is not a path, and a location suffix
  (``:12``, ``::name``, ``#x``) is cut. A placeholder (``<…>``, ``{…}``,
  ``$``, ``...``) or a glob (``*``, ``?``, ``[``, ``|``) is skipped and
  counted. Each path resolves against these bases, in order: the task
  file's folder; the project root (default: the nearest directory above the
  task file holding ``planwise/config.yaml``; none found is exit 2); and,
  only when ``--root`` is given, ``--root``, each ``--extra-root``, and the
  repository root holding ``--root`` (the nearest directory with ``.git``,
  for ``tests/...`` and ``tools/...`` forms). Every path prints with its
  resolution and the base that resolved it: ``path`` (resolved),
  ``unresolved`` (fails), or ``expected`` (absent, but named on the
  ``**Output:**`` line of the task file or of a sibling task file in its
  folder).
- ``file:line`` mode: ``--file-line FILE...``. A citation is ``name.ext:N``
  or ``name.ext:A-B`` (a backtick may close the name before the colon). The
  file resolves against the citing file's folder, the project root, each
  ``--root`` / ``--extra-root`` tree, then by name or path suffix under
  those trees. Lines are counted from the bytes, split on ``\\n``, so a CRLF
  and an LF copy count the same. The anchor is the nearest backticked or
  quoted text within 80 characters that is not a file name; it is looked for
  in lines ``A-B``, or ``N`` plus or minus 2. Labels: ``file-line`` (holds),
  ``stale-line`` (the file is shorter), ``anchor-moved`` (the note names the
  anchor's live line), ``anchor-absent`` (a report only) and ``unresolved``.
  The mode reports drift; it never rewrites a citation.

The report labels (``DEAD-ZONE``, ``NO-LOCATOR``, ``NO-FALLBACK``,
``phantom``, and the path and ``file:line`` labels) sit outside
``VERDICTS``. A mode run exits 1 when a label in ``MODE_FAILING`` prints, 0
otherwise, and 2 when an input cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True  # an installed plugin must not grow scripts/__pycache__

from markdown_parser import (
    Heading,
    extract_headings,
    numbered_heading_index,
    split_row_cells,
)

SCAN_DIRS = ("references", "handlers", "agents", "skills", "templates")
VERDICTS = ("ok", "dangling", "redirected", "unresolved-target", "unreadable")
# Verdicts a ledger entry may subtract.
LEDGERABLE = ("dangling", "unresolved-target")
_PROG = "check_section_citations"
# --root's default: the plugin holding this script. The parser keeps None so
# path mode can tell an explicit --root from the default.
_DEFAULT_ROOT = str(Path(__file__).resolve().parent.parent)


class Redirect(NamedTuple):
    """Where a moved section now lives: ``section`` None means the whole file."""

    target: str
    section: str | None
    source: str


# The redirect table: one entry per section that left a file, keyed by the
# cited file's basename and the cited section number. A citation of a key
# reads ``redirected`` to the target, whether or not the cited file keeps a
# stub heading of that number. A subsection the cited file does not hold
# (§9.2) takes its section's entry, with its tail kept under the target section
# (§8.2). Only a cited file in the plugin root's references/ directory matches.
# ``source`` names the section of the cited file that records the move. The
# target is resolved from the cited file's own directory first, then by basename.
_EVIDENCE_MAP = "verification-gate-evidence.md (former Section Map; each topic file keeps the number)"
_AUTHORING_MAP = "verification-task-authoring.md (former Section Map; each topic file keeps the number)"
REDIRECTS: dict[tuple[str, str], Redirect] = {
    ("verification-gates.md", "9"): Redirect(
        "measurement-discipline.md", "8", "verification-gates.md § Reserved Section Numbers, ### 9."),
    ("verification-gates.md", "12"): Redirect(
        "verify-caller-before-complete.md", None, "verification-gates.md § Reserved Section Numbers, ### 12."),
    ("verification-gates.md", "8"): Redirect(
        "gate-diff-baseline-pinning.md", "8", "verification-gates.md § The `$..._BASE` Pointer"),
    ("verification-gates.md", "1"): Redirect(
        "gate-runtime-boundary-evidence.md", "1", "verification-gates.md § (former Section Map row §1, now gate-runtime-boundary-evidence.md)"),
    ("verification-gates.md", "7"): Redirect(
        "gate-runtime-boundary-evidence.md", "7", "verification-gates.md § (former Section Map row §7, now gate-runtime-boundary-evidence.md)"),
    ("verification-gate-evidence.md", "1"): Redirect("gate-positive-and-mutation-controls.md", "1", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "2"): Redirect("gate-positive-and-mutation-controls.md", "2", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "3"): Redirect("gate-positive-and-mutation-controls.md", "3", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "4"): Redirect("gate-positive-and-mutation-controls.md", "4", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "5"): Redirect("gate-fixture-provenance.md", "5", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "6"): Redirect("gate-fixture-provenance.md", "6", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "7"): Redirect("gate-fixture-provenance.md", "7", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "8"): Redirect("gate-fixture-provenance.md", "8", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "9"): Redirect("gate-fixture-provenance.md", "9", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "10"): Redirect("gate-artifact-over-instrument.md", "10", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "11"): Redirect("gate-artifact-over-instrument.md", "11", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "12"): Redirect("gate-artifact-over-instrument.md", "12", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "13"): Redirect("gate-artifact-over-instrument.md", "13", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "14"): Redirect("gate-positive-and-mutation-controls.md", "14", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "15"): Redirect("gate-old-home-citation-sweep.md", "15", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "16"): Redirect("gate-generated-input-integrity.md", "16", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "17"): Redirect("gate-generated-input-integrity.md", "17", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "18"): Redirect("gate-generated-input-integrity.md", "18", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "19"): Redirect("gate-script-output-assertions.md", "19", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "20"): Redirect("gate-environment-inputs.md", "20", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "21"): Redirect("gate-generated-input-integrity.md", "21", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "22"): Redirect("gate-environment-inputs.md", "22", _EVIDENCE_MAP),
    ("verification-gate-evidence.md", "23"): Redirect("gate-script-output-assertions.md", "23", _EVIDENCE_MAP),
    ("verification-task-authoring.md", "1"): Redirect("gate-heuristic-verifier-patterns.md", "1", _AUTHORING_MAP),
    ("verification-task-authoring.md", "2"): Redirect("gate-heuristic-verifier-patterns.md", "2", _AUTHORING_MAP),
    ("verification-task-authoring.md", "3"): Redirect("gate-heuristic-verifier-patterns.md", "3", _AUTHORING_MAP),
    ("verification-task-authoring.md", "4"): Redirect("gate-heuristic-verifier-patterns.md", "4", _AUTHORING_MAP),
    ("verification-task-authoring.md", "5"): Redirect("gate-verdict-contract-and-adjudication.md", "5", _AUTHORING_MAP),
    ("verification-task-authoring.md", "6"): Redirect("gate-verdict-contract-and-adjudication.md", "6", _AUTHORING_MAP),
    ("verification-task-authoring.md", "8"): Redirect("gate-absence-and-consistency.md", "8", _AUTHORING_MAP),
    ("verification-task-authoring.md", "9"): Redirect("gate-heuristic-verifier-patterns.md", "9", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10"): Redirect("gate-pre-edit-baseline.md", "10", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.5"): Redirect("gate-pinned-from-real-content.md", "10.5", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.6"): Redirect("gate-input-set-and-compared-window.md", "10.6", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.7"): Redirect("gate-anchor-outcome-set.md", "10.7", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.8"): Redirect("gate-command-semantics.md", "10.8", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.9"): Redirect("gate-command-semantics.md", "10.9", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.10"): Redirect("gate-anchor-outcome-set.md", "10.10", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.11"): Redirect("gate-anchor-outcome-set.md", "10.11", _AUTHORING_MAP),
    ("verification-task-authoring.md", "10.12"): Redirect("gate-anchor-outcome-set.md", "10.12", _AUTHORING_MAP),
    ("verification-task-authoring.md", "11"): Redirect("gate-pinned-from-real-content.md", "11", _AUTHORING_MAP),
    ("verification-task-authoring.md", "12"): Redirect("gate-input-set-and-compared-window.md", "12", _AUTHORING_MAP),
    ("verification-task-authoring.md", "13"): Redirect("gate-heuristic-verifier-patterns.md", "13", _AUTHORING_MAP),
    ("verification-task-authoring.md", "14"): Redirect("gate-input-set-and-compared-window.md", "14", _AUTHORING_MAP),
    ("verification-task-authoring.md", "15"): Redirect("gate-input-set-and-compared-window.md", "15", _AUTHORING_MAP),
    ("verification-task-authoring.md", "16"): Redirect("gate-input-set-and-compared-window.md", "16", _AUTHORING_MAP),
}

# A section number token, kept whole: 15, 15.1, 1.16.5, 3k, 3a.2, 9.B, 9.B.1,
# 3b.archive, 3h.untested-axes. A dotted segment is a number with an optional
# letter suffix, one capital letter, or a lowercase hyphenated word.
_SEGMENT = r"\.(?:[0-9]+[a-z]?|[A-Z](?![A-Za-z])|[a-z][a-z0-9]*(?:-[a-z0-9]+)*)"
_TOKEN = rf"[0-9]+[a-z]?(?:{_SEGMENT})*(?![A-Za-z0-9_])"

# Form: a markdown file name, bare or path-prefixed (`x.md`, references/x.md,
# ../references/x.md). A name holding "{" is a placeholder and is skipped.
_NAME = r"[A-Za-z0-9_{}.~/](?:[A-Za-z0-9_{}./~-]*[A-Za-z0-9_}])?\.md(?![A-Za-z0-9_])"
_FILE_RE = re.compile(rf"(?<![A-Za-z0-9_.{{}}/~<>*-])({_NAME})")

# Form: the glue between a file name and its "§": closing backticks or bold
# marks, a closing link bracket and its (target), optional space, one table
# pipe or dash, and "(". Covers `x.md` §N, x.md §N.M, [x.md §N](...),
# [`x.md`](x.md) §N, [x.md](x.md) (§N), a "| §N" cell after a file cell and
# "[x.md](x.md) — §N".
_GLUE_RE = re.compile(r"[`*\]]*(?:\([^)\s]*\))?[`*]*[ \t]*(?:[|—–][ \t]*)?\(?[ \t]*(?=§)")

# Form: the file named after the citation (§8.7 of `x.md`, §10.4 in x.md).
_TRAIL_RE = re.compile(rf"[ \t]+(?:of|in)[ \t]+[\[`*]*({_NAME})")

# Form: a numbered citation, with at most one space after the sign
# (§15, §15.1, §1.16.5, §3k, §3a.2, §9.B.1, §3h.untested-axes, § 5).
_NUMBERED_RE = re.compile(rf"§[ \t]?({_TOKEN})")

# Form: a range end after a hyphen or an en dash. An unspaced end may be
# bare or carry its own sign (§13-19, §13–§19, §5-§6). An end written with
# spaces around the dash needs its own sign (§13 – §19), so prose such as
# "§5 - 3 rows remain" or "§4 – 2026 update" is not a range.
_RANGE_END_RE = re.compile(rf"(?:[-–](?:§[ \t]?)?|[ \t]*[-–][ \t]*§[ \t]?)({_TOKEN})")

# Form: a stage or step citation (§ Stage 8b, § Step 5), keyed as the
# extractor keys the heading.
_STAGE_RE = re.compile(rf"§[ \t]+(Stage|Step)[ \t]+({_TOKEN})")

# Form: heading words after "§ " (x.md § Read-Tool Hard Limits). The words
# run to the next clause mark; resolution matches a heading that the words
# start with, so trailing prose after the heading does not matter.
_WORDS_RE = re.compile(r"§[ \t]+(?=[A-Z`])([^,;:()\[\]|\"<>]+)")

# Form: the bare continuation after a citation (x.md §a/§b, x.md §a, §b,
# x.md §a and §b). The next "§" binds to the same file.
_CONTINUE_RE = re.compile(r"[ \t]*(?:/|,|&|\band\b|\bor\b|\bto\b)[ \t]*(?=§)")

# A placeholder segment (§N.x, §8.n, §1.N) is skipped, never resolved.
_PLACEHOLDER_SEGMENTS = frozenset({"x", "y", "z", "n", "N", "M", "X"})
_PART_RE = re.compile(r"^(?P<stem>.+?)-Part-[0-9]+-.*\.md$")
_LETTER_SUFFIX_RE = re.compile(r"^([0-9]+)[a-z]$")
_LINE_START_SIGN_RE = re.compile(r"^[ \t>*-]*§")
_CALLOUT_PREFIX_RE = re.compile(r"^\s*(?:>\s*)+")
_TRAILING_FILE_RE = re.compile(rf"(?<![A-Za-z0-9_.{{}}/~<>*-])({_NAME})[`*\]]*(?:\([^)\s]*\))?[`*]*[ \t]*$")


class CitationCheckError(Exception):
    """A condition that stops the check: exit 2 on the command line."""


class Finding(NamedTuple):
    """One parsed citation and its verdict.

    ``file`` is the scanned file's display path, ``path`` its absolute path.
    ``target`` is the resolved file's display path, or the name as written
    when it does not resolve. ``section`` is the cited section, except for a
    redirect-table finding whose entry names a target section: it is then
    that target section, and ``citation`` keeps the cited text. ``fails`` is
    True for a finding that sets exit 1 before the ledger is applied.
    """

    file: str
    path: str
    line: int
    citation: str
    target: str
    section: str
    verdict: str
    note: str
    fails: bool

    def as_json(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "citation": self.citation,
            "target": self.target,
            "section": self.section,
            "verdict": self.verdict,
            "note": self.note,
        }


class _Cite(NamedTuple):
    start: int
    end: int
    kind: str  # "number", "stage" or "words"
    section: str
    skip: bool
    tail: str = ""  # heading-words form: the whole line text after "§ "


def _norm(text: str) -> str:
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"\s+", " ", text).strip().rstrip(".:").strip()
    # A heading may carry its own sign ("### § Inference Defaults").
    return text.lstrip("§ ").lower()


class _Roots:
    """The scan set and the resolution index for one check.

    Every root is indexed for resolution. ``scan_roots`` None scans every
    root; otherwise only the roots it names are scanned for citations.
    Resolution, sibling lookups and root kinds are cached for the check.
    """

    def __init__(self, plugin_root: Path, extra_roots: Iterable[Path], exclude: Iterable[Path],
                 scan_roots: set[Path] | None = None):
        self.root = plugin_root
        self.extras = list(extra_roots)
        self.exclude = list(exclude)
        self.extra_is_file = [e.is_file() for e in self.extras]
        self.bases = [self.root] + [e.parent if f else e for e, f in zip(self.extras, self.extra_is_file)]
        self._resolved: dict[tuple[str, Path | None], tuple[Path | None, str]] = {}
        self._siblings: dict[Path, list[Path]] = {}
        self.by_root: list[list[Path]] = []
        self.scan: list[Path] = []
        # Scanned files and the basename index are de-duplicated by resolved
        # path in first-seen order, so an extra root inside --root (or two
        # overlapping extra roots) never scans or indexes a file twice.
        scanned: set[Path] = set()
        indexed: set[Path] = set()

        def add_scan(files: Iterable[Path]) -> None:
            for p in files:
                if p not in scanned:
                    scanned.add(p)
                    self.scan.append(p)

        def add_index(files: Iterable[Path]) -> list[Path]:
            kept = [p for p in files if p not in indexed]
            indexed.update(kept)
            return kept

        root_files = [p.resolve() for d in SCAN_DIRS for p in sorted((self.root / d).rglob("*.md")) if self._keep(p)]
        if not root_files:
            raise CitationCheckError(f"no markdown files under any scan directory of {self.root}")
        if scan_roots is None or self.root in scan_roots:
            add_scan(root_files)
        self.by_root.append(add_index(p.resolve() for p in sorted(self.root.rglob("*.md")) if self._keep(p)))
        for extra, is_file in zip(self.extras, self.extra_is_file):
            if is_file:
                files = [extra.resolve()] if self._keep(extra) else []
            else:
                files = [p.resolve() for p in sorted(extra.rglob("*.md")) if self._keep(p)]
            if scan_roots is None or extra in scan_roots:
                add_scan(files)
            self.by_root.append(add_index(files))
        self.names: list[dict[str, list[Path]]] = []
        for files in self.by_root:
            names: dict[str, list[Path]] = {}
            for p in files:
                names.setdefault(p.name, []).append(p)
            self.names.append(names)
        self.known = {p for files in self.by_root for p in files}

    def _keep(self, path: Path) -> bool:
        path = path.resolve()
        return not any(path == ex or ex in path.parents for ex in self.exclude)

    def resolve(self, name: str, citing: Path | None = None) -> tuple[Path | None, str]:
        """Resolve a cited file name, memoized by name and citing directory (see ``_resolve``)."""
        local = citing is not None and ("/" not in name or name.startswith("./"))
        key = (name, citing.parent if local else None)
        if key not in self._resolved:
            self._resolved[key] = self._resolve(name, citing if local else None)
        return self._resolved[key]

    def _resolve(self, name: str, citing: Path | None = None) -> tuple[Path | None, str]:
        """Resolve a cited file name.

        A bare name or a ``./sub/x.md`` path is first tried relative to the
        citing file's own directory; an existing, non-excluded file there
        wins. Then a name holding "/" tries the path prefix under ``--root``, then under
        each extra root, then the basename step. A name with no "/" is a
        basename and goes straight to the basename step, so a copy at the top
        of an extra root never wins over a ``--root`` copy of the same name.
        The basename step prefers ``--root``, then the extra roots in order,
        and reports a tie inside the chosen root as an ambiguity.
        """
        if citing is not None and ("/" not in name or name.startswith("./")):
            local = (citing.parent / name).resolve()
            if local in self.known:
                return local, ""
        rel = name
        while rel.startswith(("./", "../")):
            rel = rel.split("/", 1)[1]
        if "/" in rel:
            for base in self.bases:
                candidate = (base / rel).resolve()
                if candidate in self.known:
                    return candidate, ""
        basename = rel.rsplit("/", 1)[-1]
        for idx, names in enumerate(self.names):
            hits = names.get(basename, [])
            if len(hits) == 1:
                return hits[0], ""
            if len(hits) > 1:
                where = self.root if idx == 0 else self.extras[idx - 1]
                return None, f"ambiguous: {len(hits)} files named {basename} under {where}"
        return None, "no file of that name under any root"

    def display(self, path: Path) -> str:
        if path == self.root or self.root in path.parents:
            return path.relative_to(self.root).as_posix()
        for extra, is_file in zip(self.extras, self.extra_is_file):
            if is_file and path == extra:
                return extra.name
            if extra in path.parents:
                return f"{extra.name}/{path.relative_to(extra).as_posix()}"
        return path.as_posix()

    def siblings(self, path: Path) -> list[Path]:
        """Other members of the target's family: base file and its Parts. Memoized by path."""
        if path not in self._siblings:
            self._siblings[path] = self._find_siblings(path)
        return self._siblings[path]

    def _find_siblings(self, path: Path) -> list[Path]:
        m = _PART_RE.match(path.name)
        stem = m.group("stem") if m else path.name[: -len(".md")]
        found = []
        for p in sorted(path.parent.glob("*.md")):
            if p == path or p.resolve() not in self.known:
                continue
            pm = _PART_RE.match(p.name)
            if p.name == f"{stem}.md" or (pm and pm.group("stem") == stem):
                found.append(p)
        return found


class _Headings:
    """Cached headings per file."""

    def __init__(self):
        self._cache: dict[Path, tuple[list[Heading], dict[str, list[Heading]]]] = {}

    def get(self, path: Path) -> tuple[list[Heading], dict[str, list[Heading]]]:
        if path not in self._cache:
            # An unreadable file holds no headings; the scan reports it once.
            text, _, _ = _decode(path)
            heads = extract_headings(text or "")
            self._cache[path] = (heads, numbered_heading_index(heads))
        return self._cache[path]

    def holds(self, path: Path, cite: _Cite, prefix_fallback: bool = False) -> tuple[bool, str]:
        """True when ``path`` holds the cited section.

        ``prefix_fallback`` allows a one-letter-suffix token (``3k``) to match
        its bare number (``3``). Callers pass it only on a second pass, after
        no candidate file held the exact token, and never for siblings.
        """
        heads, index = self.get(path)
        if cite.kind in ("number", "stage"):
            if cite.section in index:
                return True, ""
            m = _LETTER_SUFFIX_RE.match(cite.section)
            if prefix_fallback and cite.kind == "number" and m and m.group(1) in index:
                return True, f"number-prefix fallback to {m.group(1)}"
            if cite.kind == "stage":
                # Stage/step title rule: the index keys "Step N" only before a
                # colon, so a heading "Step N — Title" (dash, period, space or
                # end) also holds the citation when no letter or digit follows.
                n = len(cite.section)
                for h in heads:
                    body = h.raw.lstrip("#").strip().lstrip("§ ")
                    if body.startswith(cite.section) and not body[n:n + 1].isalnum():
                        return True, "stage/step title match"
            return False, ""
        # Full-title rule first: the line text after "§ " starts with the
        # whole title of a heading, which may hold commas, colons, dashes or
        # backticks. The clause-bounded words below are the fallback.
        tail = _norm(cite.tail)
        for h in heads:
            for text in (_norm(h.title), _norm(h.raw.lstrip("#"))):
                if text and tail.startswith(text) and not tail[len(text):len(text) + 1].isalnum():
                    return True, ""
        words = _norm(cite.section)
        for h in heads:
            body = _norm(h.raw.lstrip("#"))
            for text in {body, _norm(h.title)}:
                if not text:
                    continue
                if words == text or words.startswith(text + " "):
                    return True, ""
                if len(words.split()) >= 2 and text.startswith(words + " "):
                    return True, ""
        return False, ""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CitationCheckError(f"cannot read {path}: {exc}") from exc


def _decode(path: Path) -> tuple[str | None, int, str]:
    """Return ``(text, 0, "")``, or ``(None, line, reason)`` for an unreadable file.

    ``line`` is the line that holds the first byte that is not UTF-8, or 0
    when the file cannot be opened.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, 0, f"cannot read: {exc}"
    try:
        return data.decode("utf-8"), 0, ""
    except UnicodeDecodeError as exc:
        line = data.count(b"\n", 0, exc.start) + 1
        return None, line, f"not UTF-8: byte 0x{data[exc.start]:02x} at offset {exc.start}"


def _parse_one(line: str, pos: int) -> list[_Cite]:
    """Parse the citation that starts with the "§" at ``pos``, plus a range end."""
    m = _STAGE_RE.match(line, pos)
    if m:
        return [_Cite(pos, m.end(), "stage", f"{m.group(1)} {m.group(2)}", False)]
    m = _NUMBERED_RE.match(line, pos)
    if m:
        token = m.group(1)
        skip = any(seg in _PLACEHOLDER_SEGMENTS for seg in token.split(".")[1:])
        # A number followed directly by "{" or ".{" is a placeholder
        # (§1.{N}, §2{x}) and produces no finding.
        if line.startswith(("{", ".{"), m.end()):
            return [_Cite(pos, m.end(), "number", token, True)]
        cites = [_Cite(pos, m.end(), "number", token, skip)]
        r = _RANGE_END_RE.match(line, m.end())
        if r:
            end_token = r.group(1)
            end_skip = any(seg in _PLACEHOLDER_SEGMENTS for seg in end_token.split(".")[1:])
            sign = line.find("§", r.start(), r.start(1))
            cites.append(_Cite(sign if sign != -1 else r.start(1), r.end(), "number", end_token, end_skip))
        return cites
    m = _WORDS_RE.match(line, pos)
    if m:
        words = re.sub(r"\.(\s.*)?$", "", m.group(1)).strip().rstrip("*`").strip()
        if words:
            return [_Cite(pos, m.end(), "words", words, False, line[pos + 1:])]
    if line.startswith("§{", pos):
        return [_Cite(pos, pos + 2, "number", "{", True)]
    return []


def _parse_chain(line: str, pos: int) -> list[_Cite]:
    """Parse a citation and every bare continuation that follows it."""
    cites: list[_Cite] = []
    while True:
        found = _parse_one(line, pos)
        if not found:
            return cites
        cites.extend(found)
        c = _CONTINUE_RE.match(line, found[-1].end)
        if not c:
            return cites
        pos = c.end()


def parse_line(line: str, carry: str | None = None) -> list[tuple[str | None, str, _Cite]]:
    """Parse one line into ``(file name or None, binding, citation)`` triples.

    Binding is ``named`` when the file sits next to the citation or its
    chain, ``nearest`` when the citation stands apart and a file is named
    earlier on the line, and ``self`` when no file precedes it (the name is
    then ``None``: the scanned file itself). ``carry`` is a file name that
    ended the previous line; a line that opens with "§" binds its first
    chain to it (a citation wrapped across a line break).
    """
    if "§" not in line:
        return []
    found: list[tuple[str | None, str, _Cite]] = []
    used: set[int] = set()

    def take(name: str | None, binding: str, pos: int, chain: list[_Cite] | None = None) -> None:
        # ``chain`` is the chain already parsed at ``pos``, so it is not parsed twice.
        for cite in _parse_chain(line, pos) if chain is None else chain:
            signs = {i for i in range(cite.start, cite.end) if line[i] == "§"}
            if signs & used:
                continue
            found.append((name, binding, cite))
            used.update(signs)

    if carry and _LINE_START_SIGN_RE.match(line):
        take(carry, "named", line.index("§"))
    for fm in _FILE_RE.finditer(line):
        g = _GLUE_RE.match(line, fm.end())
        if g:
            take(fm.group(1), "named", g.end())
    pos = line.find("§")
    while pos != -1:
        if pos not in used:
            chain = _parse_chain(line, pos)
            trail = _TRAIL_RE.match(line, chain[-1].end) if chain else None
            before = [m.group(1) for m in _FILE_RE.finditer(line, 0, pos)]
            if trail:
                take(trail.group(1), "named", pos, chain)
            elif before:
                take(before[-1], "nearest", pos, chain)
            else:
                take(None, "self", pos, chain)
        pos = line.find("§", pos + 1)
    found.sort(key=lambda item: item[2].start)
    return found


def _scan_lines(content: str) -> Iterable[tuple[int, str, str | None]]:
    """Yield ``(line number, line, carried file name)`` outside fenced code.

    Two fence rules apply. The literal rule: a line whose first non-space
    characters are three backticks toggles the fence. The callout-fence rule:
    a line that, after leading whitespace and every leading ``>`` marker with
    its following whitespace are stripped, starts with three backticks
    toggles a callout fence. Lines inside a callout fence are not scanned,
    and the state resets on the first line that does not start with ``>``.
    Callout prose outside such a block is still scanned. Heading extraction
    keeps the literal rule only.
    """
    in_fence = False
    in_callout_fence = False
    carry: str | None = None
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    for idx, line in enumerate(text.split("\n"), start=1):
        quoted = line.lstrip().startswith(">")
        if not quoted:
            in_callout_fence = False
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            carry = None
            continue
        if in_fence:
            continue
        # Callout-fence rule: a "> ```" line toggles a fence inside a callout.
        if quoted and _CALLOUT_PREFIX_RE.sub("", line).startswith("```"):
            in_callout_fence = not in_callout_fence
            carry = None
            continue
        if in_callout_fence:
            continue
        yield idx, line, carry
        m = _TRAILING_FILE_RE.search(line)
        carry = m.group(1) if m else None


def _redirect_entry(name: str, section: str) -> tuple[Redirect | None, str]:
    """Return ``(entry, tail)``: the entry for ``section`` or its nearest
    ancestor section, and the dotted tail the ancestor leaves (``".2"``)."""
    key = section
    while True:
        entry = REDIRECTS.get((name, key))
        if entry is not None:
            return entry, section[len(key):]
        if "." not in key:
            return None, ""
        key = key.rsplit(".", 1)[0]


def _redirect(roots: _Roots, heads: _Headings, cited: Path, cite: _Cite) -> tuple[str, Path, str, str] | None:
    """Apply the ``REDIRECTS`` entry for ``cited`` and ``cite``, if one exists.

    Returns ``(verdict, file, note, section)``: ``redirected`` to the entry's
    target when the target file resolves and holds the target section (or
    the entry names the whole file), else ``dangling`` on the cited file with
    the entry named in the note. ``section`` is the target's section, or the
    cited section for a whole-file entry or a ``dangling`` result. Returns
    None when no entry matches.
    """
    if cite.kind != "number":
        return None
    # The table records the plugin's own moved sections, so only a file in the
    # plugin's references/ directory matches; a consumer file of the same name
    # keeps its own sections.
    if cited.resolve().parent != (roots.root / "references").resolve():
        return None
    entry, rest = _redirect_entry(cited.name, cite.section)
    if entry is None or (rest and heads.holds(cited, cite)[0]):
        return None
    # A subsection keeps its tail under the target section: §9.2 -> §8.2. A
    # whole-file entry takes the subsection with the file.
    entry = entry._replace(section=entry.section + rest) if entry.section and rest else entry
    shown = f"{entry.target} §{entry.section}" if entry.section else f"{entry.target} (whole file)"
    label = f"redirect table: {cited.name} §{cite.section} -> {shown}; source: {entry.source}"
    target, _ = roots.resolve(entry.target, cited)
    if target is None:
        return "dangling", cited, f"{label}; target file missing", cite.section
    if entry.section is not None:
        probe = _Cite(cite.start, cite.end, "number", entry.section, False)
        if not heads.holds(target, probe)[0]:
            return "dangling", cited, f"{label}; target heading missing", cite.section
    return "redirected", target, label, entry.section or cite.section


def check_tree(
    plugin_root,
    extra_roots: Iterable = (),
    exclude: Iterable = (),
    strict_parts: bool = False,
    scan_roots: Iterable | None = None,
) -> list[Finding]:
    """Check every ``§`` citation under ``plugin_root`` and each extra root.

    ``extra_roots`` are directories or single files; each is scanned and used
    for resolution. ``exclude`` paths are dropped from both. ``scan_roots``
    names the roots (``plugin_root`` or members of ``extra_roots``) whose
    citations are scanned; every root is still indexed for resolution. None,
    the default, scans every root. Relative paths resolve against the current
    working directory. ``strict_parts`` marks ``redirected`` findings as
    failing. Raises ``CitationCheckError`` when a root is missing, a scan
    root is not one of the roots, or the plugin root's scan directories hold
    no markdown.
    """
    root = Path(plugin_root).resolve()
    if not root.is_dir():
        raise CitationCheckError(f"root not found: {plugin_root}")
    extras = []
    for extra in extra_roots:
        p = Path(extra).resolve()
        if not p.exists():
            raise CitationCheckError(f"extra root not found: {extra}")
        extras.append(p)
    scan = None
    if scan_roots is not None:
        scan = {Path(s).resolve() for s in scan_roots}
        stray = sorted(str(s) for s in scan - {root, *extras})
        if stray:
            raise CitationCheckError(f"scan root is not --root or an extra root: {', '.join(stray)}")
    roots = _Roots(root, extras, [Path(e).resolve() for e in exclude], scan)
    heads = _Headings()
    findings: list[Finding] = []
    for path in roots.scan:
        shown = roots.display(path)
        content, bad_line, reason = _decode(path)
        if content is None:
            findings.append(Finding(shown, str(path), bad_line, "", shown, "", "unreadable", reason, True))
            continue
        for lineno, line, carry in _scan_lines(content):
            for name, binding, cite in parse_line(line, carry):
                if cite.skip or (name and "{" in name):
                    continue
                text = line[cite.start:cite.end].strip()
                target, why = roots.resolve(name, path) if name else (path, "")
                later = None
                if binding == "self":
                    # A bare citation with no earlier file resolves against the
                    # scanned file first, then against the first file named
                    # later on the line that resolves.
                    for m in _FILE_RE.finditer(line, cite.end):
                        if "{" in m.group(1):
                            continue
                        hit, _ = roots.resolve(m.group(1), path)
                        if hit is not None:
                            later = hit
                            break
                if target is None and binding == "named":
                    findings.append(Finding(shown, str(path), lineno, text, name, cite.section,
                                            "unresolved-target", why, True))
                    continue
                # A named file decides alone. A citation standing apart from the
                # nearest earlier file name may instead cite the scanned file.
                tries = [t for t in (target, path if binding == "nearest" else None, later) if t is not None]
                verdict, where, note = "dangling", tries[0], ""
                section = cite.section
                later_note = ""
                redirected = None
                # Two passes: exact tokens across every candidate first, so a
                # number-prefix fallback in an earlier candidate never beats an
                # exact heading in a later one. In the exact pass a candidate's
                # redirect-table entry is tried before its headings, so the
                # entry wins over a stub heading of the same number.
                for fallback in (False, True):
                    for t in tries:
                        if not fallback:
                            redirected = _redirect(roots, heads, t, cite)
                            if redirected is not None:
                                break
                        ok, note = heads.holds(t, cite, prefix_fallback=fallback)
                        if ok:
                            verdict, where = "ok", t
                            if later is not None and t == later and t != path:
                                later_note = f"held by the file named later on the line: {roots.display(t)}"
                            break
                    if verdict == "ok" or redirected is not None:
                        break
                if redirected is not None:
                    verdict, where, note, section = redirected
                elif verdict != "ok":
                    note = ""
                    # Siblings match exact tokens only: the fallback never
                    # crosses files.
                    for t in tries:
                        sib = next((s for s in roots.siblings(t) if heads.holds(s, cite)[0]), None)
                        if sib is not None:
                            verdict, where, note = "redirected", sib, f"cited in {roots.display(t)}"
                            break
                if later_note:
                    note = "; ".join(x for x in (note, later_note) if x)
                if binding == "nearest":
                    shown_name = roots.display(target) if target is not None else name
                    note = "; ".join(x for x in (note, f"stands apart; nearest file on the line: {shown_name}") if x)
                fails = verdict == "dangling" or (strict_parts and verdict == "redirected")
                findings.append(Finding(shown, str(path), lineno, text, roots.display(where), section,
                                        verdict, note, fails))
    return findings


class LedgerEntry(NamedTuple):
    """One ledger entry.

    ``path`` is the entry's path as written, with ``\\`` turned into ``/``.
    ``citation`` is None for a line-keyed ``path:line`` entry. ``target`` is
    the absolute POSIX path the entry resolves to (``resolve_ledger``), or
    "" before resolution or when no file exists under any base.
    """

    path: str
    line: int
    citation: str | None
    target: str = ""

    def key(self) -> str:
        head = f"{self.path}:{self.line}"
        return head if self.citation is None else f"{head}:{self.citation}"


_LEDGER_CITED_RE = re.compile(r"^(.+?):([0-9]+):(\S.*)$")
_LEDGER_LINE_RE = re.compile(r"^(.+?):([0-9]+)(?:\s.*)?$")
_LEDGER_REASON_RE = re.compile(r"\s+#")


def read_ledger(path) -> list[LedgerEntry]:
    """Read ``path:line:citation`` and line-keyed ``path:line`` entries, unresolved."""
    entries = []
    for n, raw in enumerate(_read(Path(path)).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LEDGER_CITED_RE.match(line)
        if m:
            citation = _LEDGER_REASON_RE.split(m.group(3), maxsplit=1)[0].strip()
            entries.append(LedgerEntry(m.group(1).replace("\\", "/"), int(m.group(2)), citation))
            continue
        m = _LEDGER_LINE_RE.match(line)
        if not m:
            raise CitationCheckError(f"ledger line {n} is not path:line:citation or path:line: {raw}")
        entries.append(LedgerEntry(m.group(1).replace("\\", "/"), int(m.group(2)), None))
    return entries


def ledger_bases(plugin_root, extra_roots: Iterable = ()) -> list[Path]:
    """The directories a relative ledger entry resolves against, in order.

    ``--root`` first, then for each extra root the directory itself (a
    directory root only) and its parent, because the printed key of an
    extra-root file starts with the extra root's own name.
    """
    bases = [Path(plugin_root).resolve()]
    for extra in extra_roots:
        p = Path(extra).resolve()
        bases.extend([p, p.parent] if p.is_dir() else [p.parent])
    return bases


def resolve_ledger(entries: Iterable[LedgerEntry], bases: Iterable[Path]) -> list[LedgerEntry]:
    """Fill each entry's ``target``: an absolute path as is, a relative one by the first base holding it."""
    bases = list(bases)
    out = []
    for e in entries:
        rel = e.path
        # Strip only a literal leading "./". str.lstrip("./") would strip a
        # character set and turn ".claude/x.md" into "claude/x.md".
        while rel.startswith("./"):
            rel = rel[2:]
        target = ""
        if Path(rel).is_absolute():
            target = Path(rel).resolve().as_posix()
        else:
            for base in bases:
                candidate = (base / rel).resolve()
                if candidate.is_file():
                    target = candidate.as_posix()
                    break
        out.append(e._replace(target=target))
    return out


def _ledgered(finding: Finding, entries: Iterable[LedgerEntry]) -> bool:
    """True when a resolved entry subtracts ``finding``.

    The entry's line and resolved file must match. A three-field entry also
    needs the same printed citation; a line-keyed entry matches every
    citation on its line. Only ``LEDGERABLE`` verdicts are ever subtracted.
    """
    if finding.verdict not in LEDGERABLE:
        return False
    abs_path = Path(finding.path).as_posix()
    for e in entries:
        if e.line != finding.line or not e.target or e.target != abs_path:
            continue
        if e.citation is None or e.citation == finding.citation:
            return True
    return False


# ------------------------------------------------------------- report modes

# Labels a mode prints. The failing ones set exit 1. None is a verdict, so
# VERDICTS and the default run's JSON keys stay as they are.
MODE_LABELS = ("zone", "DEAD-ZONE", "locator", "NO-LOCATOR", "NO-FALLBACK", "symbol", "phantom",
               "path", "expected", "unresolved", "file-line", "stale-line", "anchor-moved", "anchor-absent")
MODE_FAILING = ("DEAD-ZONE", "NO-LOCATOR", "NO-FALLBACK", "phantom", "unresolved", "stale-line", "anchor-moved")


class ModeFinding(NamedTuple):
    """One report line of zone, locator or symbol mode.

    ``count`` is the heading count, the recorded locator count (-1 when the
    row records none), or the symbol's match count.
    """

    mode: str
    file: str
    line: int
    subject: str
    count: int
    label: str
    note: str

    @property
    def fails(self) -> bool:
        return self.label in MODE_FAILING

    def as_json(self) -> dict:
        return {"mode": self.mode, "file": self.file, "line": self.line, "subject": self.subject,
                "count": self.count, "label": self.label, "note": self.note}

    def text(self) -> str:
        count = "none" if self.count < 0 else str(self.count)
        note = f" ({self.note})" if self.note else ""
        return f"{self.file}:{self.line}: {self.label}: {self.mode} \"{self.subject}\" count={count}{note}"


# Form: a zone phrase after a trigger word (under `## Topic Files`, in the
# "Decisions" section, heading `Reviewer Checklists`).
_ZONE_RE = re.compile(
    r"\b(?:under|in|below|section|heading)[ \t]+(?:the[ \t]+)?(?:`([^`\n]+)`|\"([^\"\n]+)\"|“([^”\n]+)”)",
    re.IGNORECASE,
)
_ZONE_CODE_RE = re.compile(r"[_()\[\]{}=<>|\\/*$@;§]")
_ZONE_HASHES_RE = re.compile(r"^#+[ \t]*")
_NATIVE_RE = re.compile(r"native format|matching the existing", re.IGNORECASE)
_LOCATOR_FILE_RE = re.compile(r"[A-Za-z0-9_{}.~/-]+\.[A-Za-z][A-Za-z0-9]{0,4}(?![A-Za-z0-9_])")
_LOCATOR_COUNT_RE = re.compile(r"(?:→|->|=>|=|\bcount\b[ \t]*:?)[ \t]*([0-9]+)(?![0-9.])")
_FALLBACK_RE = re.compile(r"inline note|new section|fallback", re.IGNORECASE)
_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
_SYMBOL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(\()?")
_FILE_EXTS = frozenset({"md", "py", "yaml", "yml", "json", "toml", "txt", "ini", "sh", "ps1", "csv", "js",
                        "ts", "cfg", "template", "lock", "log"})
_SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules"})


def _zone_name(phrase: str) -> str | None:
    """The zone a phrase names, or None when the phrase looks like code or a file."""
    text = phrase.strip()
    hashed = text.startswith("#")
    text = _ZONE_HASHES_RE.sub("", text).strip()
    if not text:
        return None
    if hashed:
        return text
    # A heading title starts with a capital; a code value is not a zone.
    if not text[0].isupper() or text in ("None", "True", "False") or _ZONE_CODE_RE.search(text):
        return None
    if " " not in text and ("." in text or not (text[0].isupper() and any(c.islower() for c in text[1:]))):
        return None
    return text


def extract_zones(text: str) -> list[tuple[int, str]]:
    """Return ``(line, zone)`` for every zone phrase outside fenced code."""
    found = []
    for lineno, line, _ in _scan_lines(text):
        for m in _ZONE_RE.finditer(line):
            zone = _zone_name(next(g for g in m.groups() if g is not None))
            if zone:
                found.append((lineno, zone))
    return found


def zone_count(headings: Iterable[Heading], zone: str) -> int:
    """Count headings whose text or title starts with ``zone`` at a word end."""
    want = _norm(zone)
    n = 0
    for h in headings:
        for text in (_norm(h.raw.lstrip("#")), _norm(h.title)):
            if want and text.startswith(want) and not text[len(want):len(want) + 1].isalnum():
                n += 1
                break
    return n


def _target_headings(targets: Iterable) -> list[tuple[str, list[Heading]]]:
    out = []
    for t in targets:
        p = Path(t)
        if not p.is_file():
            raise CitationCheckError(f"zone target not found: {t}")
        text, _, reason = _decode(p)
        if text is None:
            raise CitationCheckError(f"cannot read zone target {t}: {reason}")
        out.append((p.name, extract_headings(text)))
    return out


def check_zones(text: str, targets: Iterable, brief_name: str = "<brief>") -> list[ModeFinding]:
    """Zone mode: one finding per extracted zone, ``DEAD-ZONE`` at count 0."""
    heads = _target_headings(targets)
    out = []
    for lineno, zone in extract_zones(text):
        per = [(name, zone_count(h, zone)) for name, h in heads]
        total = sum(n for _, n in per)
        note = ", ".join(f"{name}={n}" for name, n in per)
        out.append(ModeFinding("zone", brief_name, lineno, zone, total, "zone" if total else "DEAD-ZONE", note))
    return out


def check_locators(text: str, brief_name: str = "<brief>") -> list[ModeFinding]:
    """Locator evidence: each "native format" / "matching the existing" line needs a locator result."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    for lineno, line, _ in _scan_lines(text):
        # A phrase wrapped in quotes or backticks is a mention of the rule, not a row.
        m = next((x for x in _NATIVE_RE.finditer(line)
                  if line[x.start() - 1:x.start()] not in ('"', "`", "“")), None)
        if not m:
            continue
        window = [line]
        for prev in reversed(lines[max(0, lineno - 4):lineno - 1]):
            if not prev.strip():
                break
            window.insert(0, prev)
        joined = "\n".join(window)
        count_m = _LOCATOR_COUNT_RE.search(joined)
        file_m = _LOCATOR_FILE_RE.search(joined)
        phrase = m.group(0).lower()
        if not (count_m and file_m):
            out.append(ModeFinding("locator", brief_name, lineno, phrase, -1, "NO-LOCATOR",
                                   "no file name and count recorded on the row or the lines above it"))
            continue
        count = int(count_m.group(1))
        evidence = f"evidence: {file_m.group(0)} count={count}"
        if count == 0 and not _FALLBACK_RE.search(joined):
            out.append(ModeFinding("locator", brief_name, lineno, phrase, 0, "NO-FALLBACK",
                                   f"{evidence}; no fallback form stated"))
        else:
            out.append(ModeFinding("locator", brief_name, lineno, phrase, count, "locator", evidence))
    return out


def _symbol_from_span(span: str) -> str | None:
    m = _SYMBOL_RE.match(span.strip())
    if not m or not (m.group(2) or "." in m.group(1)):
        return None
    name = m.group(1)
    if "." in name and name.rsplit(".", 1)[1].lower() in _FILE_EXTS:
        return None
    return name


def extract_symbols(text: str) -> list[tuple[int, str]]:
    """Return ``(line, symbol)`` pairs, first occurrence of each symbol only."""
    rows = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = [(i, r.strip()) for i, r in enumerate(rows, start=1) if r.strip() and not r.strip().startswith("#")]
    if body and all(_SYMBOL_RE.fullmatch(r) or _SYMBOL_RE.fullmatch(r.removesuffix(")")) for _, r in body):
        pairs = [(i, _SYMBOL_RE.match(r).group(1)) for i, r in body]
    else:
        pairs = []
        for lineno, line, _ in _scan_lines(text):
            for m in _BACKTICK_SPAN_RE.finditer(line):
                name = _symbol_from_span(m.group(1))
                if name:
                    pairs.append((lineno, name))
    seen: set[str] = set()
    out = []
    for lineno, name in pairs:
        if name not in seen:
            seen.add(name)
            out.append((lineno, name))
    return out


def _source_texts(sources: Iterable, skip: Iterable = ()) -> list[str]:
    skipped = {Path(s).resolve() for s in skip}
    texts = []
    for src in sources:
        root = Path(src)
        if not root.exists():
            raise CitationCheckError(f"source not found: {src}")
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in files:
            if p.resolve() in skipped or any(part in _SKIP_DIRS for part in p.parts):
                continue
            text, _, _ = _decode(p)
            if text is not None:
                texts.append(text)
    return texts


def check_symbols(text: str, sources: Iterable, symbols_name: str = "<symbols>",
                  skip: Iterable = ()) -> list[ModeFinding]:
    """Symbol mode: one finding per symbol, ``phantom`` when the sources hold no match."""
    texts = _source_texts(sources, skip)
    out = []
    for lineno, name in extract_symbols(text):
        last = name.rsplit(".", 1)[-1]
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(last)}(?![A-Za-z0-9_])")
        count = sum(len(pattern.findall(t)) for t in texts)
        note = f"searched: {last}" if last != name else ""
        out.append(ModeFinding("symbol", symbols_name, lineno, name, count, "symbol" if count else "phantom", note))
    return out


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    text, _, reason = _decode(p)
    if text is None:
        raise CitationCheckError(f"cannot read {path}: {reason or 'missing'}")
    return text


# ------------------------------------------------- path and file:line modes

_PATH_SPAN_RE = re.compile(r"`([^`\n]+)`")
_ANCHOR_RE = re.compile(r"`([^`\n]+)`|\"([^\"\n]+)\"|“([^”\n]+)”")
_PLACEHOLDER_CHARS_RE = re.compile(r"[<>{}$%]|\.\.\.|…")
_GLOB_CHARS_RE = re.compile(r"[*?\[\]|]")
# A path token may end in a location suffix (":12", ":3-9", "::name", "#anchor").
_LOCATION_SUFFIX_RE = re.compile(r"(.+?)(?::[0-9]+(?:-[0-9]+)?|::.*|#.*)?")
_HAS_EXT_RE = re.compile(r"[^/]*\.[A-Za-z][A-Za-z0-9]{0,7}")
# Form: a file:line citation (x.py:12, `x.md`:3-9, C:/a/b.md:4). The name needs
# an extension that starts with a letter, so "12:30" and "1.0.5:3" are skipped.
_FILE_LINE_RE = re.compile(
    r"(?<![A-Za-z0-9_./~{}<>:-])((?:[A-Za-z]:)?[A-Za-z0-9_.~/{}-]*[A-Za-z0-9_}-]\.[A-Za-z][A-Za-z0-9]{0,7})"
    r"[`*]{0,2}:([0-9]+)(?:[-–]([0-9]+))?(?![0-9A-Za-z_])"
)
_ANCHOR_WINDOW = 80
_ANCHOR_SLACK = 2


def find_project_root(start) -> Path | None:
    """The nearest directory at or above ``start`` that holds ``planwise/config.yaml``."""
    p = Path(start).resolve()
    for d in (p, *p.parents):
        if (d / "planwise" / "config.yaml").is_file():
            return d
    return None


def _md_section(text: str, title: str) -> list[tuple[int, str]]:
    """The ``(line, text)`` pairs of the ``## title`` section, fenced code excluded."""
    out: list[tuple[int, str]] = []
    inside = False
    for lineno, line, _ in _scan_lines(text):
        if line.startswith("## "):
            if inside:
                break
            inside = _norm(line[3:]).startswith(title.lower())
            continue
        if inside:
            out.append((lineno, line))
    return out


def path_token(span: str, loose: bool) -> tuple[str, str]:
    """Classify a backticked span: ``("path"|"placeholder"|"glob", path)`` or ``("", span)``.

    A span with whitespace, a URL or a leading ``-`` is not a path. ``loose``
    (a Required Context File cell) takes a span with a ``/`` or an extension;
    otherwise (Execution Steps) the span needs a ``/`` and an extension, or
    a trailing ``/``. A location suffix (``:12``, ``::name``, ``#x``) is cut.
    """
    s = span.strip()
    if not s or any(c.isspace() for c in s) or "://" in s or s.startswith("-"):
        return "", s
    s = _LOCATION_SUFFIX_RE.fullmatch(s).group(1)
    last = s.rstrip("/").rsplit("/", 1)[-1]
    ext = bool(_HAS_EXT_RE.fullmatch(last))
    looks = ("/" in s or ext) if loose else (s.endswith("/") or ("/" in s and ext))
    if not looks:
        return "", s
    if _PLACEHOLDER_CHARS_RE.search(s):
        return "placeholder", s
    if _GLOB_CHARS_RE.search(s):
        return "glob", s
    return "path", s


def _resolve_on_disk(rel: str, bases: Iterable[tuple[str, Path]]) -> tuple[Path | None, str]:
    p = Path(rel).expanduser()
    if p.is_absolute():
        return (p.resolve() if p.exists() else None), "absolute path"
    for label, base in bases:
        candidate = base / rel
        if candidate.exists():
            return candidate.resolve(), label
    return None, ""


def repo_root_of(start) -> Path | None:
    """The nearest directory at or above ``start`` that holds ``.git``."""
    p = Path(start).resolve()
    return next((d for d in (p, *p.parents) if (d / ".git").exists()), None)


def path_bases(folder: Path, project_root: Path, roots: Iterable = ()) -> list[tuple[str, Path]]:
    """Path mode's resolution bases, in order.

    The task file's folder, the project root, then (only when ``roots`` is
    given) ``roots[0]`` (``--root``), each further root (``--extra-root``),
    and last the repository root holding ``roots[0]`` (for ``tests/...`` and
    ``tools/...`` forms).
    """
    bases = [("task folder", folder), ("project root", project_root)]
    roots = [Path(r).resolve() for r in roots]
    for i, r in enumerate(roots):
        bases.append((f"--root {r.as_posix()}" if i == 0 else f"--extra-root {r.as_posix()}",
                      r if r.is_dir() else r.parent))
    repo = repo_root_of(roots[0]) if roots else None
    if repo is not None:
        bases.append((f"repository root {repo.as_posix()}", repo))
    return bases


def _session_outputs(folder: Path, bases: list[tuple[str, Path]]) -> dict[Path, str]:
    """Every path named on an ``**Output:**`` line of a task file in ``folder``, with its file name."""
    owned: dict[Path, str] = {}
    for md in sorted(folder.glob("*.md")):
        text, _, _ = _decode(md)
        for _, line, _ in _scan_lines(text or ""):
            if not line.lstrip().startswith("**Output:**"):
                continue
            for m in _PATH_SPAN_RE.finditer(line):
                kind, rel = path_token(m.group(1), True)
                if kind == "path":
                    for _, b in bases:
                        owned.setdefault((b / rel).resolve(), md.name)
    return owned


def check_paths(task_file, project_root=None, roots: Iterable = ()) -> tuple[list[ModeFinding], dict]:
    """Path mode: every path in a task file's Required Context and Execution Steps resolves.

    Paths come from the backticked spans of the Required Context table's File
    column and of the Execution Steps section. Each resolves against the
    ``path_bases`` in order: the task file's folder, the project root
    (``project_root``, or the nearest directory above the task file holding
    ``planwise/config.yaml``), then, when ``roots`` is given, ``--root``,
    each ``--extra-root`` and the repository root holding ``--root``. The
    note names the base that resolved the path. Labels: ``path`` (resolved),
    ``unresolved`` (fails), and ``expected`` (absent, but named on the
    ``**Output:**`` line of this task file or a sibling task file in the same
    folder, so a task of the session writes it). Returns the findings and
    the skip counts.
    """
    path = Path(task_file)
    text = _read_input(str(task_file))
    folder = path.resolve().parent
    root = Path(project_root).resolve() if project_root else find_project_root(folder)
    if root is None or not root.is_dir():
        raise CitationCheckError(f"no project root for {task_file}: pass --project-root "
                                 "or run inside a tree holding planwise/config.yaml")
    bases = path_bases(folder, root, roots)
    outputs = _session_outputs(folder, bases)
    skipped = {"placeholder": 0, "glob": 0}
    shown = path.as_posix()
    seen: set[str] = set()
    out: list[ModeFinding] = []
    for section, loose in (("Required Context", True), ("Execution Steps", False)):
        col: int | None = None
        for lineno, line in _md_section(text, section):
            source, projected = line, False
            if loose:
                if not line.lstrip().startswith("|"):
                    continue
                cells = split_row_cells(line)
                if col is None:
                    col = next((i for i, c in enumerate(cells) if _norm(c) == "file"), -1)
                    continue
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                source = cells[col] if 0 <= col < len(cells) else line
                projected = "projected" in line.lower()
            for m in _PATH_SPAN_RE.finditer(source):
                kind, rel = path_token(m.group(1), loose)
                if kind in skipped:
                    skipped[kind] += 1
                if kind != "path" or rel in seen:
                    continue
                seen.add(rel)
                hit, via = _resolve_on_disk(rel, bases)
                if hit is not None:
                    out.append(ModeFinding("path", shown, lineno, rel, 1, "path",
                                           f"{section}; via {via}: {hit.as_posix()}"))
                    continue
                owner = next((outputs[c] for c in ((b / rel).resolve() for _, b in bases) if c in outputs), None)
                if owner is not None:
                    out.append(ModeFinding("path", shown, lineno, rel, 0, "expected",
                                           f"{section}; named on the **Output:** line of {owner}, not on disk yet"))
                    continue
                note = f"{section}; tried: " + ", ".join(label.split(" ", 1)[0] if label.startswith("--") else label
                                                        for label, _ in bases)
                if projected:
                    note += "; row marked projected"
                out.append(ModeFinding("path", shown, lineno, rel, 0, "unresolved", note))
    return out, skipped


def count_lines(data: bytes) -> int:
    """Lines in ``data``, split on ``\\n`` only, so CRLF and LF copies count the same."""
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


class _FileIndex:
    """Basename index of every file under the ``--root`` trees, built on first use."""

    def __init__(self, roots: Iterable):
        self.roots = [Path(r).resolve() for r in roots]
        self._names: list[dict[str, list[Path]]] | None = None

    def lookup(self, rel: str) -> tuple[Path | None, str]:
        """Match by name (and path suffix): the first root holding a match decides, as in ``_Roots``."""
        if self._names is None:
            self._names = []
            for r in self.roots:
                names: dict[str, list[Path]] = {}
                files = [r] if r.is_file() else sorted(p for p in r.rglob("*") if p.is_file())
                for p in files:
                    if not any(part in _SKIP_DIRS for part in p.parts):
                        names.setdefault(p.name, []).append(p.resolve())
                self._names.append(names)
        name = rel.rstrip("/").rsplit("/", 1)[-1]
        stem = rel
        while stem.startswith(("./", "../")):
            stem = stem.split("/", 1)[1]
        tail = "/" + stem if "/" in stem else ""
        for root, names in zip(self.roots, self._names):
            hits = [p for p in names.get(name, []) if not tail or p.as_posix().endswith(tail)]
            if len(hits) == 1:
                return hits[0], f"by name under {root.name}"
            if hits:
                return None, f"ambiguous: {len(hits)} files named {rel} under {root.as_posix()}"
        return None, ""


def _pick_anchor(line: str, start: int, end: int) -> str | None:
    """The nearest backticked or quoted text within the window that is not a file name."""
    best: tuple[int, str] | None = None
    for m in _ANCHOR_RE.finditer(line):
        text = next(g for g in m.groups() if g is not None).strip()
        # A file name, a path or a bare ":N" names the citation, not the cited text.
        if len(text) < 3 or text.startswith(":") or _FILE_LINE_RE.search(text) or any(
                _HAS_EXT_RE.fullmatch(word.rstrip("/").rsplit("/", 1)[-1]) for word in text.split()):
            continue
        if m.start() < end and m.end() > start:
            continue
        gap = max(m.start() - end, start - m.end(), 0)
        if gap <= _ANCHOR_WINDOW and (best is None or gap < best[0]):
            best = (gap, text)
    return best[1] if best else None


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_file_lines(text: str, citing, roots: Iterable = (), project_root=None,
                     name: str | None = None) -> tuple[list[ModeFinding], dict]:
    """``file:line`` mode: each ``name.ext:N`` / ``name.ext:A-B`` names a file with that many lines.

    The cited file resolves against the citing file's folder, the project
    root (given, or found above the citing file; omitted when absent), each
    ``roots`` tree joined with the path, then by name (and path suffix)
    under the ``roots`` trees. Lines are counted from the bytes. An anchor
    (backticked or quoted text within 80 characters, not a file name) is
    looked for in lines ``A-B``, or ``N`` plus or minus 2. Labels:
    ``file-line`` (holds), ``stale-line`` (the file is shorter), ``anchor-moved``
    (the anchor is elsewhere; the note names its live line), ``anchor-absent``
    (the anchor is nowhere in the file; a report only) and ``unresolved``.
    The mode reports drift; it never rewrites a citation.
    """
    citing = Path(citing)
    folder = citing.resolve().parent
    proj = Path(project_root).resolve() if project_root else find_project_root(folder)
    roots = [Path(r).resolve() for r in roots]
    bases = [("citing folder", folder)] + ([("project root", proj)] if proj else [])
    bases += [(f"--root {r.name}", r if r.is_dir() else r.parent) for r in roots]
    index = _FileIndex(roots)
    shown = name or citing.as_posix()
    cache: dict[Path, tuple[list[str], int]] = {}
    skipped = {"placeholder": 0}
    out: list[ModeFinding] = []
    for lineno, line, _ in _scan_lines(text):
        for m in _FILE_LINE_RE.finditer(line):
            rel, first = m.group(1), int(m.group(2))
            last = int(m.group(3)) if m.group(3) else None
            if "{" in rel or "}" in rel:
                skipped["placeholder"] += 1
                continue
            subject = f"{rel}:{first}" + (f"-{last}" if last is not None else "")
            hit, via = _resolve_on_disk(rel, bases)
            why = ""
            if hit is not None and not hit.is_file():
                hit = None
            if hit is None:
                hit, why = index.lookup(rel)
                via = why if hit is not None else ""
            if hit is None:
                out.append(ModeFinding("file-line", shown, lineno, subject, -1, "unresolved",
                                       why or "no file of that path under any base"))
                continue
            if hit not in cache:
                data = hit.read_bytes()
                text_lines = [ln.rstrip("\r") for ln in data.decode("utf-8", errors="replace").split("\n")]
                cache[hit] = (text_lines, count_lines(data))
            body, total = cache[hit]
            lo, hi = (first, last) if last is not None else (first - _ANCHOR_SLACK, first + _ANCHOR_SLACK)
            lo, hi = min(lo, hi), max(lo, hi)
            end = last if last is not None else first
            anchor = _pick_anchor(line, m.start(), m.end())
            note = f"{hit.as_posix()} via {via}"
            live = None
            if anchor:
                want = _collapse(anchor)
                hits = [i for i, ln in enumerate(body[:total], start=1) if want in _collapse(ln)]
                inside = [i for i in hits if max(lo, 1) <= i <= hi]
                live = inside[0] if inside else (min(hits, key=lambda i: abs(i - first)) if hits else None)
                note += f"; anchor \"{anchor}\"" + (f" at line {live}" if live else " not found")
            if max(first, end) > total:
                label = "stale-line"
                note = f"file has {total} lines; " + note
            elif anchor and live is None:
                label = "anchor-absent"
            elif anchor and not (lo <= live <= hi):
                label = "anchor-moved"
            else:
                label = "file-line"
            out.append(ModeFinding("file-line", shown, lineno, subject, total, label, note))
    return out, skipped


def _run_modes(args) -> int:
    found: list[ModeFinding] = []
    summary = []
    try:
        if args.paths:
            got: list[ModeFinding] = []
            skips = {"placeholder": 0, "glob": 0}
            # Without an explicit --root, path mode keeps its two bases.
            roots = [args.root, *args.extra_root] if args.root else []
            for task in args.paths:
                rows, skipped = check_paths(task, args.project_root, roots)
                got += rows
                for k, v in skipped.items():
                    skips[k] += v
            found += got
            summary.append(f"path mode: {len(got)} paths in {len(args.paths)} files "
                           f"(unresolved={sum(f.label == 'unresolved' for f in got)}, "
                           f"expected={sum(f.label == 'expected' for f in got)}); "
                           f"skipped {skips['placeholder']} placeholders, {skips['glob']} globs")
        if args.file_line:
            got = []
            skipped_n = 0
            for md in args.file_line:
                rows, skipped = check_file_lines(_read_input(md), md, [args.root or _DEFAULT_ROOT, *args.extra_root],
                                                 args.project_root)
                got += rows
                skipped_n += skipped["placeholder"]
            found += got
            tally = ", ".join(f"{lab}={sum(f.label == lab for f in got)}"
                              for lab in ("stale-line", "anchor-moved", "anchor-absent", "unresolved"))
            summary.append(f"file:line mode: {len(got)} citations ({tally}); skipped {skipped_n} placeholders")
        if args.zone:
            brief = _read_input(args.brief)
            name = "<stdin>" if args.brief == "-" else args.brief
            zones = check_zones(brief, args.zone, name)
            locs = check_locators(brief, name)
            found += zones + locs
            summary.append(f"zone mode: {len(zones)} zones (dead={sum(f.fails for f in zones)}); "
                           f"{len(locs)} locator rows (no-locator="
                           f"{sum(f.label == 'NO-LOCATOR' for f in locs)}, no-fallback="
                           f"{sum(f.label == 'NO-FALLBACK' for f in locs)})")
        if args.symbols:
            syms = check_symbols(_read_input(args.symbols), args.source, args.symbols,
                                 skip=[args.symbols] if args.symbols != "-" else [])
            found += syms
            summary.append(f"symbol mode: {len(syms)} symbols (phantom={sum(f.fails for f in syms)})")
    except CitationCheckError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 2
    for f in found:
        print(json.dumps(f.as_json(), ensure_ascii=False) if args.json else f.text())
    failing = sum(f.fails for f in found)
    print(f"summary: {'; '.join(summary)}; {failing} failing (heuristic report)",
          file=sys.stderr if args.json else sys.stdout)
    return 1 if failing else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Resolve every § section citation in a plugin's markdown tree.",
        epilog="Exit 0 clean, 1 on a dangling or unresolved-target finding left after the ledger, "
        "2 on a usage error, an unreadable root, or a scan that finds zero files.",
    )
    parser.add_argument("--root", default=None,
                        help="plugin root whose references/, handlers/, agents/, skills/ and templates/ are scanned "
                        "(default: the plugin holding this script)")
    parser.add_argument("--extra-root", action="append", default=[], metavar="PATH",
                        help="extra directory or file to scan and resolve against (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATH",
                        help="path removed from scanning and resolution (repeatable)")
    parser.add_argument("--strict-parts", action="store_true",
                        help="fail on redirected findings as well")
    parser.add_argument("--json", action="store_true",
                        help="print one JSON object per finding")
    parser.add_argument("--ledger", metavar="PATH",
                        help="file of path:line:citation entries (or line-keyed path:line) "
                        "subtracted from the failing findings")
    parser.add_argument("--zone", action="append", default=[], metavar="TARGET",
                        help="zone mode (heuristic report): count the --brief's zones as headings in TARGET "
                        "(repeatable), and check its locator evidence")
    parser.add_argument("--brief", metavar="FILE",
                        help="brief or task file read by zone mode ('-' reads stdin)")
    parser.add_argument("--symbols", metavar="FILE",
                        help="symbol mode (heuristic report): file of symbols, or prose with backticked symbols")
    parser.add_argument("--source", action="append", default=[], metavar="TREE",
                        help="directory or file symbol mode searches (repeatable)")
    parser.add_argument("--paths", nargs="+", metavar="TASK",
                        help="path mode: every path in each task file's Required Context and Execution Steps "
                        "resolves on disk")
    parser.add_argument("--file-line", nargs="+", metavar="FILE",
                        help="file:line mode: each name.ext:N or name.ext:A-B citation in each markdown file "
                        "names a file with that many lines, and its anchor sits in the cited range")
    parser.add_argument("--project-root", metavar="DIR",
                        help="project root for --paths and --file-line (default: the nearest directory above "
                        "the file that holds planwise/config.yaml)")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Citations carry "§" and arrows; a Windows console code page cannot encode them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = _parser()
    args = parser.parse_args(argv)
    if bool(args.zone) != bool(args.brief):
        parser.error("--zone and --brief go together")
    if bool(args.symbols) != bool(args.source):
        parser.error("--symbols and --source go together")
    if args.project_root and not (args.paths or args.file_line):
        parser.error("--project-root goes with --paths or --file-line")
    if args.zone or args.symbols or args.paths or args.file_line:
        return _run_modes(args)
    try:
        findings = check_tree(args.root or _DEFAULT_ROOT, args.extra_root, args.exclude, args.strict_parts)
        entries = read_ledger(args.ledger) if args.ledger else []
    except CitationCheckError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 2
    entries = resolve_ledger(entries, ledger_bases(args.root or _DEFAULT_ROOT, args.extra_root))
    gated = [f for f in findings if f.verdict in LEDGERABLE]
    failing = [f for f in findings if f.fails and not _ledgered(f, entries)]
    for f in findings:
        if args.json:
            print(json.dumps(f.as_json(), ensure_ascii=False))
        elif f.verdict == "unreadable":
            print(f"{f.file}:{f.line}: unreadable ({f.note})")
        else:
            note = f" ({f.note})" if f.note else ""
            print(f"{f.file}:{f.line}: {f.verdict}: {f.citation} -> {f.target} §{f.section}{note}")
    for e in entries:
        if e.citation is None:
            print(f"ledger entry is line-keyed; re-key as path:line:citation: {e.key()}", file=sys.stderr)
    for e in entries:
        if not any(_ledgered(f, [e]) for f in gated):
            print(f"ledger entry matched no dangling or unresolved-target finding: {e.key()}", file=sys.stderr)
    # The unreadable count is shown only when non-zero, so a clean run's
    # summary line keeps its four-verdict shape.
    tally = ", ".join(f"{v}={n}" for v in VERDICTS
                      if (n := sum(1 for f in findings if f.verdict == v)) or v != "unreadable")
    print(f"summary: {len(findings)} findings ({tally}); {len(failing)} failing after ledger",
          file=sys.stderr if args.json else sys.stdout)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
