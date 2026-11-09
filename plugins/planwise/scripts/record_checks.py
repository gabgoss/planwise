#!/usr/bin/env python3
"""Record checks: three predicates over what an artifact or a commit records.

Subcommands:

  sums         An arithmetic line in a file evaluates true. Two forms are read,
               with thousands separators allowed:
                 (i)  ``a+b+c = n`` or ``a + b = n``
                 (ii) a total written first and its addends in the next
                      parenthesis, as in ``997 lines (271 + 187 + 147, ...)``.
               Input: one or more files. Prints ``evaluated N`` (the count of
               sums found) before any verdict. Exit 0 when N >= 1 and every sum
               is true, 1 listing each false line as
               ``file:line: a+b = n (computed m)``, 2 when N is 0 (a scan that
               saw no sum is not a clean result) or on a usage error.
               Cannot see: offsetting errors in the addends (the printed sum
               holds while two addends are wrong), a sum written in words, a
               sum split over two lines, or a decimal sum. For form (ii) the
               total is the integer in the clause before the parenthesis that
               equals the computed sum, else the integer nearest in value.

  self-count   A line or byte count a file records about itself equals the
               final file. Input: one file, ``--field lines|bytes`` and an
               optional ``--pattern`` regex with one capture group that
               captures the recorded figure (default: a ``Lines:`` or
               ``Bytes:`` header line). Prints ``examined 1 recorded figure``
               before the verdict. Exit 0 equal, 1 printing both numbers,
               2 when the recorded figure is not a number, when the file
               records no figure or on a usage error.
               Lines are the file's own ``\\n`` count. Bytes are the raw bytes
               on disk, so a checkout under CRLF conversion differs from the
               committed blob by the line count. Cannot see: a figure recorded
               outside the pattern, or a file edited after the check ran.

  commit-scope A commit lists no path outside a declared list. Input:
               ``--repo``, ``--rev`` (default HEAD) and ``--declared`` (one
               path per line). Prints the declared-path count first, then runs
               ``git -C <repo> show --stat --name-only --format= <rev>``.
               Exit 0 when every listed path is declared, 1 listing each
               foreign path, 2 on an empty declared list, an unresolvable
               rev or a commit that lists no path. Cannot see: a path declared but not touched, or a change
               to file content inside a declared path.

Rules held by this module: see references/measure-aggregate-provenance.md
section 1 and section 4, and references/measure-artifact-identity.md
section 3.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

NUM = r"\d[\d,]*"
RUN = rf"{NUM}(?:[ \t]*\+[ \t]*{NUM})+"
FORM_I = re.compile(rf"(?<![\d,.]){RUN}[ \t]*=[ \t]*({NUM})(?![\d]|\.\d)")
RUN_RE = re.compile(rf"(?<![\d,.])({RUN})(?![\d,]|\.\d)")
INT_RE = re.compile(rf"(?<![\d,.])({NUM})(?!\.\d)")
FOLLOWS_EQ = re.compile(r"[ \t]*=[ \t]*\d")


def _num(text: str) -> int:
    return int(text.replace(",", ""))


def _addends(run: str) -> list[int]:
    return [_num(p) for p in run.split("+")]


def find_sums(line: str) -> list[tuple[str, int, int]]:
    """Return (display, stated, computed) for each integer sum on a line."""
    found: list[tuple[str, int, int]] = []
    for m in FORM_I.finditer(line):
        run = m.group(0).rsplit("=", 1)[0].strip()
        addends = _addends(run)
        stated = _num(m.group(1).rstrip(","))
        found.append((f"{'+'.join(str(a) for a in addends)} = {stated}", stated, sum(addends)))
    for paren in re.finditer(r"\(([^()]*)\)", line):
        inner = paren.group(1)
        for run_m in RUN_RE.finditer(inner):
            if FOLLOWS_EQ.match(inner, run_m.end()):
                continue  # already read as form (i)
            addends = _addends(run_m.group(1))
            computed = sum(addends)
            before = line[: paren.start()]
            cut = max(before.rfind(")"), before.rfind("|"), before.rfind(";"), before.rfind(":"))
            window = before[cut + 1 :]
            cands = [_num(c.group(1).rstrip(",")) for c in INT_RE.finditer(window)]
            if not cands:
                continue
            stated = computed if computed in cands else min(cands, key=lambda c: abs(c - computed))
            found.append((f"{'+'.join(str(a) for a in addends)} = {stated}", stated, computed))
    return found


def cmd_sums(args: argparse.Namespace) -> int:
    findings: list[str] = []
    evaluated = 0
    for name in args.files:
        path = Path(name)
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            print(f"record_checks: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        for number, line in enumerate(text.splitlines(), start=1):
            for display, stated, computed in find_sums(line):
                evaluated += 1
                if stated != computed:
                    findings.append(f"{name}:{number}: {display} (computed {computed})")
    print(f"evaluated {evaluated}")
    if evaluated == 0:
        print("no sum found: a scan that saw no sum is not a clean result")
        return 2
    for item in findings:
        print(item)
    return 1 if findings else 0


DEFAULT_PATTERNS = {
    "lines": r"(?mi)^[^\w\n]*Lines:[ \t*]*([\d,]+)",
    "bytes": r"(?mi)^[^\w\n]*Bytes:[ \t*]*([\d,]+)",
}


def cmd_self_count(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"record_checks: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    pattern = args.pattern or DEFAULT_PATTERNS[args.field]
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        print(f"record_checks: bad pattern: {exc}", file=sys.stderr)
        return 2
    if rx.groups < 1:
        print("record_checks: pattern needs one capture group", file=sys.stderr)
        return 2
    match = rx.search(data.decode("utf-8", errors="replace"))
    if match is None:
        print("examined 0 recorded figures")
        print(f"{args.file}: no recorded {args.field} figure")
        return 2
    print("examined 1 recorded figure")
    captured = match.group(1).strip()
    if not re.fullmatch(r"\d[\d,]*", captured):
        print(f"{args.file}: recorded figure {captured!r} is not a number")
        return 2
    recorded = _num(captured)
    actual = data.count(b"\n") if args.field == "lines" else len(data)
    if recorded == actual:
        return 0
    print(f"{args.file}: recorded {args.field} {recorded}, actual {actual}")
    return 1


def cmd_commit_scope(args: argparse.Namespace) -> int:
    try:
        raw = Path(args.declared).read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"record_checks: cannot read {args.declared}: {exc}", file=sys.stderr)
        return 2
    declared = {p.strip().replace("\\", "/") for p in raw.split("\n") if p.strip()}
    print(f"declared {len(declared)} paths")
    if not declared:
        print("empty declared list: nothing to compare against")
        return 2
    cmd = ["git", "-C", args.repo, "-c", "core.quotepath=off", "show", "--stat", "--name-only", "--format=", args.rev]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except OSError as exc:
        print(f"record_checks: cannot run git: {exc}", file=sys.stderr)
        return 2
    if proc.returncode != 0:
        print(f"cannot resolve {args.rev}: {proc.stderr.decode('utf-8', errors='replace').strip()}")
        return 2
    listed = [p.strip().replace("\\", "/") for p in proc.stdout.decode("utf-8", errors="replace").splitlines() if p.strip()]
    print(f"commit lists {len(listed)} paths")
    if not listed:
        print("commit lists no paths: the check could not see its subject")
        return 2
    foreign = [p for p in listed if p not in declared]
    for item in foreign:
        print(f"foreign path: {item}")
    return 1 if foreign else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "record checks").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_sums = sub.add_parser("sums", help="evaluate integer sums written in files")
    p_sums.add_argument("files", nargs="+")
    p_sums.set_defaults(func=cmd_sums)
    p_self = sub.add_parser("self-count", help="compare a recorded count with the file")
    p_self.add_argument("file")
    p_self.add_argument("--field", choices=("lines", "bytes"), default="lines")
    p_self.add_argument("--pattern", default=None)
    p_self.set_defaults(func=cmd_self_count)
    p_scope = sub.add_parser("commit-scope", help="list paths a commit holds outside a declared list")
    p_scope.add_argument("--repo", required=True)
    p_scope.add_argument("--rev", default="HEAD")
    p_scope.add_argument("--declared", required=True)
    p_scope.set_defaults(func=cmd_commit_scope)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
