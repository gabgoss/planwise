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
Scanned files are de-duplicated by resolved path. A ledger entry with no
``/`` matches only the exact printed file key.

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
  target is itself a Part, in its base file or another Part). It passes by
  default and fails under ``--strict-parts``.
- ``unresolved-target``: no file resolves for the named file, or the name
  matches two files inside the chosen root (the note names the ambiguity).

Exit codes:

- 0: no ``dangling`` or ``unresolved-target`` finding is left after the
  ledger is subtracted (and no ``redirected`` finding under
  ``--strict-parts``).
- 1: at least one such finding is left.
- 2: a usage error, a root or ledger that cannot be read, or a scan that
  finds zero markdown files. One line beginning ``check_section_citations:``
  names the reason on stderr.

``check_tree(plugin_root, extra_roots=(), exclude=(), strict_parts=False)``
is the importable API. It returns every finding, ``ok`` rows included, and
raises ``CitationCheckError`` for the exit-2 conditions.
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

from markdown_parser import Heading, extract_headings, numbered_heading_index

SCAN_DIRS = ("references", "handlers", "agents", "skills", "templates")
VERDICTS = ("ok", "dangling", "redirected", "unresolved-target")
_PROG = "check_section_citations"

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
    when it does not resolve. ``fails`` is True for a finding that sets exit
    1 before the ledger is applied.
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
    """The scan set and the resolution index for one check."""

    def __init__(self, plugin_root: Path, extra_roots: Iterable[Path], exclude: Iterable[Path]):
        self.root = plugin_root
        self.extras = list(extra_roots)
        self.exclude = list(exclude)
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
        add_scan(root_files)
        self.by_root.append(add_index(p.resolve() for p in sorted(self.root.rglob("*.md")) if self._keep(p)))
        for extra in self.extras:
            if extra.is_file():
                files = [extra.resolve()] if self._keep(extra) else []
            else:
                files = [p.resolve() for p in sorted(extra.rglob("*.md")) if self._keep(p)]
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

    def _bases(self) -> list[Path]:
        return [self.root] + [e if e.is_dir() else e.parent for e in self.extras]

    def resolve(self, name: str, citing: Path | None = None) -> tuple[Path | None, str]:
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
            for base in self._bases():
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
        for extra in self.extras:
            if extra.is_file() and path == extra:
                return extra.name
            if extra in path.parents:
                return f"{extra.name}/{path.relative_to(extra).as_posix()}"
        return path.as_posix()

    def siblings(self, path: Path) -> list[Path]:
        """Other members of the target's family: base file and its Parts."""
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
            heads = extract_headings(_read(path))
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

    def take(name: str | None, binding: str, pos: int) -> None:
        for cite in _parse_chain(line, pos):
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
                take(trail.group(1), "named", pos)
            elif before:
                take(before[-1], "nearest", pos)
            else:
                take(None, "self", pos)
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


def check_tree(
    plugin_root,
    extra_roots: Iterable = (),
    exclude: Iterable = (),
    strict_parts: bool = False,
) -> list[Finding]:
    """Check every ``§`` citation under ``plugin_root`` and each extra root.

    ``extra_roots`` are directories or single files; each is scanned and used
    for resolution. ``exclude`` paths are dropped from both. Relative paths
    resolve against the current working directory. ``strict_parts`` marks
    ``redirected`` findings as failing. Raises ``CitationCheckError`` when a
    root is missing or the plugin root's scan directories hold no markdown.
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
    roots = _Roots(root, extras, [Path(e).resolve() for e in exclude])
    heads = _Headings()
    findings: list[Finding] = []
    for path in roots.scan:
        shown = roots.display(path)
        for lineno, line, carry in _scan_lines(_read(path)):
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
                later_note = ""
                # Two passes: exact tokens across every candidate first, so a
                # number-prefix fallback in an earlier candidate never beats an
                # exact heading in a later one.
                for fallback in (False, True):
                    for t in tries:
                        ok, note = heads.holds(t, cite, prefix_fallback=fallback)
                        if ok:
                            verdict, where = "ok", t
                            if later is not None and t == later and t != path:
                                later_note = f"held by the file named later on the line: {roots.display(t)}"
                            break
                    if verdict == "ok":
                        break
                if verdict != "ok":
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
                findings.append(Finding(shown, str(path), lineno, text, roots.display(where), cite.section,
                                        verdict, note, fails))
    return findings


def read_ledger(path) -> list[tuple[str, int]]:
    """Read ``path:line`` pairs, one per line; text after the number is the reason."""
    entries = []
    for n, raw in enumerate(_read(Path(path)).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(.+?):([0-9]+)(?:\s.*)?$", line)
        if not m:
            raise CitationCheckError(f"ledger line {n} is not path:line: {raw}")
        entries.append((m.group(1).replace("\\", "/"), int(m.group(2))))
    return entries


def _ledgered(finding: Finding, entries: list[tuple[str, int]]) -> bool:
    abs_path = Path(finding.path).as_posix()
    for p, line in entries:
        if line != finding.line:
            continue
        # Strip only a literal leading "./" prefix. str.lstrip("./") would
        # strip a character set and turn ".claude/x.md" into "claude/x.md".
        rel = p
        while rel.startswith("./"):
            rel = rel[2:]
        if p in (finding.file, abs_path) or rel == finding.file:
            return True
        # A bare basename entry matches only the exact printed key; suffix
        # matching applies only to entries holding "/".
        if "/" in rel and abs_path.endswith("/" + rel):
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Resolve every § section citation in a plugin's markdown tree.",
        epilog="Exit 0 clean, 1 on a dangling or unresolved-target finding left after the ledger, "
        "2 on a usage error, an unreadable root, or a scan that finds zero files.",
    )
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
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
                        help="file of path:line pairs subtracted from the failing findings")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Citations carry "§" and arrows; a Windows console code page cannot encode them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        findings = check_tree(args.root, args.extra_root, args.exclude, args.strict_parts)
        entries = read_ledger(args.ledger) if args.ledger else []
    except CitationCheckError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 2
    gated = [f for f in findings if f.verdict in ("dangling", "unresolved-target")]
    failing = [f for f in findings if f.fails and not (f in gated and _ledgered(f, entries))]
    for f in findings:
        if args.json:
            print(json.dumps(f.as_json(), ensure_ascii=False))
        else:
            note = f" ({f.note})" if f.note else ""
            print(f"{f.file}:{f.line}: {f.verdict}: {f.citation} -> {f.target} §{f.section}{note}")
    unused = [e for e in entries if not any(_ledgered(f, [e]) for f in gated)]
    for p, line in unused:
        print(f"ledger entry matched no dangling or unresolved-target finding: {p}:{line}", file=sys.stderr)
    tally = ", ".join(f"{v}={sum(1 for f in findings if f.verdict == v)}" for v in VERDICTS)
    print(f"summary: {len(findings)} findings ({tally}); {len(failing)} failing after ledger",
          file=sys.stderr if args.json else sys.stdout)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
