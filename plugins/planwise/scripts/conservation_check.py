#!/usr/bin/env python3
"""Check that a markdown edit kept every heading, sub-rule label and section token.

Predicate: every payload token of the pre-edit file appears in the post-edit
file. The rule is ``references/measurement-discipline.md`` §8.7, sub-rule B:
pair every size gate with a content-conservation gate whose term list is
derived from the pre-edit file. Three token kinds are compared:

- heading: the text of every ATX heading, levels 1 to 6, outside fenced code.
  Headings come from ``markdown_parser.extract_headings``, so a ``# comment``
  line inside a fenced block is never a heading. Trailing whitespace and
  ``\\r`` are stripped. Headings compare as a multiset: a pre-edit file with
  two equal headings needs two in the post-edit file.
- label: every sub-rule label of the form ``> [!kind] X —`` or
  ``> [!kind] Sub-rule X —``, keyed by the number of the nearest numbered
  heading above it (or that heading's text when no numbered heading precedes
  it), the ``Sub-rule`` form, and the letter. The callout kind is not part of
  the key. Labels inside fenced code are skipped by the same literal fence
  rule ``extract_headings`` uses.
- section token: every ``§N``, ``§N.M`` and dotted-letter token such as
  ``§9.A.3``, matched anywhere in the file, the space dropped. A dotted
  segment is a number or one capital letter, read the way
  ``check_section_citations.py`` reads a numbered citation. A sentence-final
  period is not part of the token.
  Section tokens compare as a set: a token is missing only when no
  occurrence remains.

Input: ``--before FILE`` or ``--before-rev REV --repo PATH --path REL`` (the
pre-edit text is read with ``git -C PATH show REV:REL``), and ``--after FILE``.
``--allow-moved FILE`` (repeatable) names a sibling file. A token absent from
``--after`` but present in a sibling counts as moved, not missing, and prints
as ``moved: <token> -> <file>``. CRLF and LF are normalized before parsing,
so line endings are never content.

Exit contract: 0 when no token is missing, 1 when one or more tokens are
missing (one ``missing:`` line each, with its kind and pre-edit line), 2 on a
usage error, an unreadable file, or a revision or path git cannot show.
The last line printed on exit 0 or 1 is the summary with the token count.

What the check cannot see: a rule sentence reworded under a kept heading, a
WRONG/CORRECT pair dropped from a kept section, or a heading moved to another
section. It checks payload coordinates only. A pair lint and a body read
cover the prose.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Importing a sibling must not write __pycache__/ into the shipped scripts
# directory, because the installer copies the working tree.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_parser import extract_headings

# A dotted segment is a number or one capital letter (§9.A.3 is one token).
# A trailing period with nothing after it is sentence punctuation, not a
# segment, so "§8.7." reads as §8.7.
SECTION_TOKEN_RE = re.compile(
    r"§[ \t]?([0-9]+(?:\.(?:[0-9]+|[A-Z](?![A-Za-z0-9])))*)"
)
LABEL_RE = re.compile(
    r"^[ \t]*(?:>[ \t]*)+\[![A-Za-z][A-Za-z0-9_-]*\][ \t]+(Sub-rule[ \t]+)?([A-Z])[ \t]+—"
)


class UsageError(Exception):
    """A condition that stops the check before any comparison: exit 2."""


def normalize(text: str) -> str:
    """Return ``text`` with CRLF and CR line endings turned into LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def heading_text(raw: str) -> str:
    """Return a heading line without its leading ``#`` run and outer whitespace."""
    return raw.lstrip("#").strip()


def _section_key(headings, line_no: int) -> str:
    """Return the nearest numbered heading's number above ``line_no``.

    When no numbered heading precedes the line, return the text of the
    nearest heading above it, or ``(top)`` when there is none.
    """
    numbered = None
    nearest = None
    for h in headings:
        if h.line >= line_no:
            break
        nearest = h
        if h.number is not None:
            numbered = h
    if numbered is not None:
        return f"§{numbered.number}"
    if nearest is not None:
        return heading_text(nearest.raw)
    return "(top)"


def extract_tokens(text: str) -> dict:
    """Return the three token inventories of one markdown text.

    The result maps ``heading`` to a list of ``(text, line)``, ``label`` to a
    list of ``(key, line)`` and ``section`` to a dict of token to first line.
    """
    body = normalize(text)
    headings = extract_headings(body)
    heading_list = [(heading_text(h.raw), h.line) for h in headings]

    labels: list[tuple[str, int]] = []
    sections: dict[str, int] = {}
    in_fence = False
    for idx, line in enumerate(body.split("\n"), start=1):
        for m in SECTION_TOKEN_RE.finditer(line):
            sections.setdefault(f"§{m.group(1)}", idx)
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = LABEL_RE.match(line)
        if m:
            form = "Sub-rule " if m.group(1) else ""
            key = f"{_section_key(headings, idx)} {form}{m.group(2)}"
            labels.append((key, idx))
    return {"heading": heading_list, "label": labels, "section": sections}


def compare(before: dict, after: dict, siblings: list[tuple[str, dict]]):
    """Compare two inventories and return ``(missing, moved, counts)``.

    ``missing`` and ``moved`` are lists of printable lines. ``counts`` maps each
    token kind to the number of pre-edit tokens compared.
    """
    missing: list[str] = []
    moved: list[str] = []

    def sibling_holding(kind: str, token: str) -> str | None:
        for name, inv in siblings:
            if kind == "section":
                if token in inv["section"]:
                    return name
            elif any(t == token for t, _ in inv[kind]):
                return name
        return None

    for kind in ("heading", "label"):
        remaining = Counter(t for t, _ in after[kind])
        for token, line in before[kind]:
            if remaining[token] > 0:
                remaining[token] -= 1
                continue
            shown = f'"{token}"' if kind == "heading" else token
            where = sibling_holding(kind, token)
            if where is not None:
                moved.append(f"moved: {kind} {shown} -> {where}")
            else:
                missing.append(f"missing: {kind} {shown} (pre-edit line {line})")

    for token, line in sorted(before["section"].items(), key=lambda kv: kv[1]):
        if token in after["section"]:
            continue
        where = sibling_holding("section", token)
        if where is not None:
            moved.append(f"moved: section-token {token} -> {where}")
        else:
            missing.append(f"missing: section-token {token} (pre-edit line {line})")

    counts = {
        "heading": len(before["heading"]),
        "label": len(before["label"]),
        "section": len(before["section"]),
    }
    return missing, moved, counts


def read_file(path: str) -> str:
    """Read a file as UTF-8 text, or raise ``UsageError``."""
    try:
        return Path(path).read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc


def read_revision(repo: str, rev: str, rel: str) -> str:
    """Return ``git -C repo show rev:rel`` as text, or raise ``UsageError``."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "show", f"{rev}:{rel}"],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise UsageError(f"cannot run git: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise UsageError(f"git cannot show {rev}:{rel} in {repo}: {err}")
    try:
        return proc.stdout.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UsageError(f"{rev}:{rel} is not UTF-8: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exit 0 when every heading, sub-rule label and § token of the "
            "pre-edit markdown file survives in the post-edit file, 1 listing "
            "each missing token, 2 on a usage error."
        )
    )
    parser.add_argument("--before", help="pre-edit file")
    parser.add_argument("--before-rev", help="git revision that holds the pre-edit text")
    parser.add_argument("--repo", help="git repository for --before-rev")
    parser.add_argument("--path", help="repository-relative path for --before-rev")
    parser.add_argument("--after", required=True, help="post-edit file")
    parser.add_argument(
        "--allow-moved",
        action="append",
        default=[],
        metavar="FILE",
        help="sibling file that may hold a moved token (repeatable)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Tokens hold "§" and "—": write UTF-8 whatever the console code page is.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.before and args.before_rev:
            raise UsageError("give --before or --before-rev, not both")
        if args.before:
            before_text = read_file(args.before)
        elif args.before_rev:
            if not args.repo or not args.path:
                raise UsageError("--before-rev needs --repo and --path")
            before_text = read_revision(args.repo, args.before_rev, args.path)
        else:
            raise UsageError("give --before FILE or --before-rev REV --repo PATH --path REL")
        after_text = read_file(args.after)
        siblings = [(name, extract_tokens(read_file(name))) for name in args.allow_moved]
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    missing, moved, counts = compare(
        extract_tokens(before_text), extract_tokens(after_text), siblings
    )
    for line in missing:
        print(line)
    for line in moved:
        print(line)
    total = sum(counts.values())
    print(
        f"compared {total} tokens (headings {counts['heading']}, labels "
        f"{counts['label']}, section tokens {counts['section']}): "
        f"{len(missing)} missing, {len(moved)} moved"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
